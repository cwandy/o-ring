"""Ölçü Öner: standard O-ring and gland proposal from a diameter and operating conditions."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ for `common`

from common import (data_banner, dataset, outputs_section, section_view, sidebar_units, status_label,
                    status_table)
from oring_designer.export.report import ReportInput
from design_form import UnitInputs
from oring_designer import units
from oring_designer.i18n import render_check, t
from oring_designer.selector import SelectorInput, select
from oring_designer.gland_types import ThermalState
from oring_designer.sweep import sweep, temperatures, to_frame
from oring_designer.viz.plots import squeeze_fill_figure

st.title(t("ui.page_size"))
st.caption(t("ui.size_intro"))
ds = dataset()
ui = UnitInputs(sidebar_units())
T_ref = ui.temperature(t("ui.T_ref"), 293.15, "T_ref", container=st.sidebar)
INCH = ui.L_UNIT == "in"

# --------------------------------------------------------------------------- inputs
elastomers = [k for k, m in ds.seal_materials.items() if m.group == "elastomer"]
housing_ids = list(ds.housing_materials)
c1, c2, c3 = st.columns(3)
with c1:
    st.subheader(t("ui.gland"))
    kind = st.radio(t("ui.gland_type"), ["piston", "rod", "face"], horizontal=True,
                    format_func=lambda k: t(f"ui.{k}"))
    direction = "internal"
    if kind == "face":
        direction = st.radio(t("ui.pressure_direction"), ["internal", "external"], horizontal=True,
                             format_func=lambda k: t(f"ui.{k}"))
    label = t(f"ui.nominal_{kind}" if kind != "face" else f"ui.nominal_face_{direction}")
    default_D = {"piston": 50.0, "rod": 20.0, "face": 36.8}[kind]
    D = ui.length(label, default_D, f"sel_D_{kind}_{direction}")
    st.markdown(f"**{t('ui.cs_range')}**")
    cs_min = ui.length(t("ui.cs_min"), 1.7, "sel_cs_min")
    cs_max = ui.length(t("ui.cs_max"), 3.6, "sel_cs_max")
    standards = st.multiselect(t("ui.standards"), ["AS568", "ISO3601-1 A", "ISO3601-1 G"],
                               default=["AS568", "ISO3601-1 A", "ISO3601-1 G"])
with c2:
    st.subheader(t("ui.materials"))
    seal_id = st.selectbox(t("ui.seal_material"), elastomers, index=elastomers.index("vmq"),
                           format_func=lambda k: ds.seal_materials[k].name)
    st.caption(t("ui.only_elastomers"))
    groove_id = st.selectbox(t("ui.groove_material"), housing_ids, index=housing_ids.index("al6061"),
                             format_func=lambda k: ds.housing_materials[k].name)
    mating_id = None
    if kind != "face" and st.checkbox(t("ui.mating_separate")):
        mating_id = st.selectbox(t("ui.mating_material"), housing_ids, index=housing_ids.index(groove_id),
                                 format_func=lambda k: ds.housing_materials[k].name)
    st.subheader(t("ui.operating"))
    p_disp = st.number_input(f"{t('ui.pressure')} [{ui.P_UNIT}]",
                             value=round(units.pressure_from_Pa(50e5, ui.P_UNIT), 3), min_value=0.0,
                             key=f"sel_p_{ui.P_UNIT}")
    hardness = st.number_input(t("ui.hardness"), value=70.0, min_value=30.0, max_value=95.0, step=5.0)
    fluid = st.selectbox(t("ui.fluid"), [None, *ds.fluids],
                         format_func=lambda k: t("ui.no_fluid") if k is None else ds.fluids[k].name)
with c3:
    st.subheader(t("ui.sweep"))
    T_min = ui.temperature(t("ui.T_min"), 240.0, "sel_T_min")
    T_max = ui.temperature(t("ui.T_max"), 300.0, "sel_T_max")
    n_T = int(st.number_input(t("ui.n_temps"), value=5, min_value=2, max_value=15))
    lag = ui.temp_delta(t("ui.lag_delta"), 0.0, "sel_lag")
    with st.expander(t("ui.tol_inputs")):
        tol_nom = ui.length(t("ui.tol_nominal"), 0.025, "sel_tn")
        tol_d = ui.length(t("ui.tol_diameter"), 0.025, "sel_td")
        tol_w = ui.length(t("ui.tol_width"), 0.10, "sel_tw")
        tol_depth = ui.length(t("ui.tol_depth"), 0.025, "sel_tdp")
        clearance = None
        if kind != "face" and st.checkbox(t("ui.clearance_override")):
            clearance = (ui.length(t("ui.clearance_min"), 0.05, "sel_cmin"),
                         ui.length(t("ui.clearance_max"), 0.10, "sel_cmax"))

inp = SelectorInput(
    gland_type=kind, nominal_diameter_m=D, seal_material=seal_id, groove_material=groove_id,
    mating_material=mating_id, pressure_Pa=units.pressure_to_Pa(p_disp, ui.P_UNIT),
    hardness_shore_a=hardness, fluid=fluid, face_pressure_direction=direction,
    T_min_K=min(T_min, T_max), T_max_K=max(T_min, T_max), T_ref_K=T_ref, n_temperatures=n_T,
    lag_delta_K=lag, cs_min_m=min(cs_min, cs_max), cs_max_m=max(cs_min, cs_max),
    standards=tuple(standards), nominal_tol_m=tol_nom, diameter_tol_m=tol_d, width_tol_m=tol_w,
    depth_tol_m=tol_depth, clearance_m=clearance,
    round_diameter_m=0.0005 * 0.0254 if INCH else 0.01e-3,
    round_width_m=0.001 * 0.0254 if INCH else 0.05e-3,
)


@st.cache_data(show_spinner=True)
def run(inp: SelectorInput):
    return select(inp, dataset())


props = run(inp)
st.divider()
if not props:
    st.info(t("ui.no_candidates"))
    st.stop()

ok = [p for p in props if p.error is None]
for p in props:
    if p.error is not None:
        st.warning(t("ui.proposal_error", size=p.size, error=p.error))
if not ok:
    st.stop()


def pm(v: float, tol: float) -> str:
    return f"{ui.fmt_L(v)} ± {ui.fmt_L(tol).split()[0]}"


st.subheader(t("ui.proposals"))
rows = []
for p in ok:
    wc = p.wc
    rows.append({
        t("ui.col_status"): status_label(p.status),
        t("ui.col_size"): p.size,
        t("ui.col_id"): pm(p.ring.id_m, p.ring_tol[0]),
        t("ui.col_cs"): pm(p.ring.cs_m, p.ring_tol[1]),
        t("ui.col_squeeze"): f"{wc.output_min['squeeze_min']:.1%} – {wc.output_max['squeeze_max']:.1%}",
        t("ui.col_fill"): f"{wc.output_min['fill']:.1%} – {wc.output_max['fill']:.1%}",
        t("ui.col_stretch"): f"{wc.output_min['stretch']:.2%} – {wc.output_max['stretch']:.2%}",
        t("ui.col_score"): f"{p.score:.2f}",
    })
st.table(pd.DataFrame(rows).style.hide(axis="index"))

# --------------------------------------------------------------------------- details
st.subheader(t("ui.proposal_detail"))
choice = st.selectbox(t("ui.col_size"), range(len(ok)), format_func=lambda i: f"{i + 1}. {ok[i].size}")
p = ok[choice]
g = p.design.gland
tol = p.tolerances


def dim(label_key: str, field: str, value: float, sym: bool = True) -> dict:
    tv = tol.get(f"gland.{field}")
    if tv is None:
        tol_txt = "–"
    elif tv.lower_m == 0:
        tol_txt = f"+{ui.fmt_L(tv.upper_m).split()[0]} / 0"
    else:
        tol_txt = f"± {ui.fmt_L(tv.upper_m).split()[0]}"
    return {t("ui.col_dim"): t(label_key), t("ui.col_value"): ui.fmt_L(value), t("ui.col_tol"): tol_txt}


dims = []
if kind == "piston":
    dims += [dim("ui.bore_diameter", "bore_diameter_m", g.bore_diameter_m),
             dim("ui.piston_diameter", "piston_diameter_m", g.piston_diameter_m),
             dim("ui.groove_diameter_piston", "groove_diameter_m", g.groove_diameter_m),
             dim("ui.groove_width", "groove_width_m", g.groove_width_m)]
elif kind == "rod":
    dims += [dim("ui.rod_diameter", "rod_diameter_m", g.rod_diameter_m),
             dim("ui.throat_diameter", "throat_diameter_m", g.throat_diameter_m),
             dim("ui.groove_diameter_rod", "groove_diameter_m", g.groove_diameter_m),
             dim("ui.groove_width", "groove_width_m", g.groove_width_m)]
else:
    dims += [dim("ui.groove_id", "groove_id_m", g.groove_id_m),
             dim("ui.groove_od", "groove_od_m", g.groove_od_m),
             dim("ui.groove_depth", "groove_depth_m", g.groove_depth_m)]
dims.append({t("ui.col_dim"): t("ui.gland_depth_ref"), t("ui.col_value"): ui.fmt_L(p.depth_m),
             t("ui.col_tol"): "–"})
dims.append({t("ui.col_dim"): t("ui.corner_radius"), t("ui.col_value"): ui.fmt_L(p.radius_m),
             t("ui.col_tol"): "–"})
if p.clearance_m is not None:
    dims.append({t("ui.col_dim"): t("ui.diametral_clearance_nom"),
                 t("ui.col_value"): ui.fmt_L(p.clearance_m), t("ui.col_tol"): "–"})
st.markdown(f"**{t('ui.gland_dims')}** — {p.size}: {pm(p.ring.id_m, p.ring_tol[0])} × "
            f"{pm(p.ring.cs_m, p.ring_tol[1])}")
st.table(pd.DataFrame(dims).style.hide(axis="index"))

worst = [r for r, _ in p.wc.worst_results.values()]
data_banner(any(r.data_quality is not None and r.data_quality.needs_warning for r in worst))
st.markdown(f"**{t('ui.wc_checks')}: {status_label(p.status)}**")
order = {"FAIL": 0, "WARN": 1, "PASS": 2}
status_table([(r.status, render_check(r), None) for r in sorted(worst, key=lambda r: order[r.status.value])])

# nominal design over the temperature range
seal = ds.seal_materials[seal_id]
rules = ds.rule_set(seal.group, "static_face" if kind == "face" else "static_radial")
pts = sweep(p.design, ds, temperatures(inp.T_min_K, inp.T_max_K, max((inp.T_max_K - inp.T_min_K) / 40, 0.5)),
            T_ref_K=T_ref)
fig = squeeze_fill_figure(
    to_frame(pts), temp_unit=ui.T_UNIT, squeeze_band=p.band,
    squeeze_max=rules.squeeze_max.value if rules.squeeze_max else None,
    fill_band=(rules.fill_min.value, rules.fill_max.value),
    fill_hard_max=rules.fill_hard_max.value,
    low_temp_limit_K=seal.low_temp_limit_K.value if seal.low_temp_limit_K else None,
    low_temp_band_K=ds.common_rules.low_temp_warning_band_K.value,
)
st.plotly_chart(fig, use_container_width=True, theme=None)

st.subheader(t("ui.section"))
section_view(p.design, ds, [(ui.fmt_T(T), ThermalState(T, T, None, T_ref))
                            for T in (inp.T_min_K, T_ref, inp.T_max_K)],
             kind, ui.L_UNIT, key="section_side_size")

outputs_section(
    ReportInput(p.design, T_ref, None, inp.T_min_K, inp.T_max_K,
                max((inp.T_max_K - inp.T_min_K) / 40, 0.5), "equilibrium", 0.0, 0.0, ui.L_UNIT, ui.T_UNIT,
                ui.P_UNIT, oring_label=p.size, tolerances=p.tolerances, mc_samples=5000),
    p.design, ui.L_UNIT, key=f"size_{choice}", label=p.size)
