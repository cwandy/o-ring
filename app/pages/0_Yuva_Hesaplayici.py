"""Yuva Hesaplayıcı: groove depth, width, tolerances, temperature behaviour and forces
from material, cross-section, temperature range and pressure."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ for `common`

from common import data_banner, dataset, sidebar_units, status_label, status_table
from design_form import UnitInputs
from oring_designer import units
from oring_designer.checks import Status, run_checks
from oring_designer.force import face_clamp_load, load_per_length
from oring_designer.gland_types import ThermalState
from oring_designer.groove_calc import GrooveInput, TemperatureRangeError, calculate
from oring_designer.i18n import render_check, t, t_list
from oring_designer.thermal import ThermalDataError
from oring_designer.viz.plots import groove_envelope_figure, range_gauge
from oring_designer.viz.section import section_figure

st.title(t("ui.page_calc"))
st.caption(t("ui.calc_intro"))
ds = dataset()
ui = UnitInputs(sidebar_units())
T_ref = ui.temperature(t("ui.T_ref"), 293.15, "T_ref", container=st.sidebar)
LU = ui.L_UNIT
CS_STD = {"AS568": [1.78, 2.62, 3.53, 5.33, 6.99], "ISO 3601": [1.80, 2.65, 3.55, 5.30, 7.00]}


def L(x_m: float) -> str:
    return ui.fmt_L(x_m)


def Lnum(x_m: float) -> str:
    return L(x_m).split()[0]


# --------------------------------------------------------------------------- inputs
with st.container(border=True):
    c1, c2, c2b = st.columns(3)
    with c1:
        seal_ids = list(ds.seal_materials)
        seal_id = st.selectbox(t("ui.seal_material"), seal_ids, index=seal_ids.index("vmq"),
                               format_func=lambda k: ds.seal_materials[k].name)
        is_elastomer = ds.seal_materials[seal_id].group == "elastomer"
    with c2:
        housing_ids = list(ds.housing_materials)
        housing_id = st.selectbox(t("ui.housing_material"), housing_ids, index=housing_ids.index("ss304"),
                                  format_func=lambda k: ds.housing_materials[k].name)
    with c2b:
        st.selectbox(t("ui.temper"), [x.id for x in ds.housing_materials[housing_id].tempers],
                     format_func=lambda k: next(x.name for x in ds.housing_materials[housing_id].tempers
                                                if x.id == k), key=f"calc_temper_{housing_id}")
    options = [f"{std} {v:.2f}" for std, vals in CS_STD.items() for v in vals] + [t("ui.cs_custom")]

    def cs_label(o: str) -> str:
        if o == t("ui.cs_custom"):
            return o
        std, mm = o.rsplit(" ", 1)
        v = f"{float(mm):.2f}" if LU == "mm" else f"{float(mm) / 25.4:.3f}"
        return f"{v} {'AS' if std == 'AS568' else 'ISO'}"

    choice = st.pills(f"{t('ui.cross_section')} [{LU}]", options, default="AS568 3.53",
                      format_func=cs_label, key="calc_cs")
    if choice is None or choice == t("ui.cs_custom"):
        cs_m = ui.length(t("ui.cs_custom_value"), 2.5, "calc_cs_custom")
    else:
        cs_m = float(choice.split()[-1]) * 1e-3
    r1, r2, r3, r4 = st.columns(4)
    with r1:
        gland = st.segmented_control(t("ui.gland_type"), ["face", "radial"], default="face",
                                     format_func=lambda k: t(f"ui.gland_{k}"), key="calc_gland") or "face"
        direction = "internal"
        if gland == "face":
            direction = st.radio(t("ui.pressure_direction"), ["internal", "external"], horizontal=True,
                                 format_func=lambda k: t(f"ui.{k}"), key="calc_dir")
    with r2:
        T_lo = ui.temperature(t("ui.T_low"), 220.0, "calc_T_lo")
    with r3:
        T_hi = ui.temperature(t("ui.T_high"), 300.0, "calc_T_hi")
    with r4:
        p_disp = st.number_input(f"{t('ui.pressure')} [{ui.P_UNIT}]",
                                 value=round(units.pressure_from_Pa(50e5, ui.P_UNIT), 3), min_value=0.0,
                                 key=f"calc_p_{ui.P_UNIT}")
        pressure = units.pressure_to_Pa(p_disp, ui.P_UNIT)
        hardness = st.number_input(t("ui.hardness"), value=70.0, min_value=50.0, max_value=90.0, step=5.0,
                                   key="calc_hard") if is_elastomer else None

    with st.expander(t("ui.optional_inputs")):
        e1, e2, e3 = st.columns(3)

        def opt_length(col, label, key):
            v = col.number_input(f"{label} [{LU}]", value=None, min_value=0.0, format=ui.FMT,
                                 key=f"{key}_{LU}")
            return None if v is None else units.length_to_m(v, LU)

        ring_id = opt_length(e1, t("ui.ring_id_opt"), "calc_rid")
        fluid = e1.selectbox(t("ui.fluid"), [None, *ds.fluids], key="calc_fluid",
                             format_func=lambda k: t("ui.no_fluid") if k is None else ds.fluids[k].name)
        tmin = e2.number_input(t("ui.target_min"), value=None, min_value=0.0, max_value=0.9, step=0.01,
                               format="%.3f", key="calc_tmin")
        tmax = e2.number_input(t("ui.target_max"), value=None, min_value=0.0, max_value=0.9, step=0.01,
                               format="%.3f", key="calc_tmax")
        fill_lim = e2.number_input(t("ui.fill_limit_opt"), value=None, min_value=0.3, max_value=0.95,
                                   step=0.01, format="%.2f", key="calc_fill")
        cs_tol = opt_length(e3, t("ui.cs_tol_opt"), "calc_cstol")
        depth_tol = opt_length(e3, t("ui.depth_tol_opt"), "calc_dtol")
        width_tol = opt_length(e3, t("ui.width_tol_opt"), "calc_wtol")
        stretch = 0.0
        if gland == "radial":
            stretch = e1.number_input(t("ui.install_stretch_opt"), value=0.0, min_value=0.0, max_value=0.05,
                                      step=0.005, format="%.3f", key="calc_stretch")

target = (tmin, tmax) if tmin is not None and tmax is not None and tmin < tmax else None
if not is_elastomer and target is None:
    st.warning(t("ui.target_required"))
    st.stop()

inp = GrooveInput(
    seal_material=seal_id, cs_m=cs_m, gland=gland, T_min_K=min(T_lo, T_hi), T_max_K=max(T_lo, T_hi),
    T_ref_K=T_ref, pressure_Pa=pressure, hardness_shore_a=hardness, housing_material=housing_id,
    fluid=fluid, face_direction=direction, cs_tol_m=cs_tol, target_squeeze=target, fill_limit=fill_lim,
    depth_tol_m=depth_tol, width_tol_m=width_tol, install_stretch=stretch,
    round_depth_m=0.0001 * 0.0254 if LU == "in" else 0.01e-3,
    round_width_m=0.001 * 0.0254 if LU == "in" else 0.05e-3,
)


@st.cache_data(show_spinner=True)
def run(inp: GrooveInput):
    return calculate(inp, dataset())


try:
    res = run(inp)
except TemperatureRangeError as exc:
    if exc.usable is None:
        st.error(t("ui.no_thermal_data"))
    else:
        st.error(t("ui.usable_range", lo=ui.fmt_T(exc.usable[0]), hi=ui.fmt_T(exc.usable[1])))
    st.stop()
except ValueError as exc:
    st.error(t("ui.invalid_input", error=exc))
    st.stop()

# --------------------------------------------------------------------------- headline results
worst = [r for r, _ in res.wc.worst_results.values()]
data_banner(any(r.data_quality is not None and r.data_quality.needs_warning for r in worst))
for note in res.notes:
    if note == "backup_ring_required":
        st.error(t("ui.backup_required"))
    elif note == "parker_row_nearest":
        st.info(t("ui.parker_nearest"))
pr = res.parker_ref
sq_lo, sq_hi = res.squeeze_range
nom_ref = res.nominal_at(T_ref)
k1, k2, k3, k4 = st.columns(4)
k1.metric(t("ui.kpi_depth_face" if gland == "face" else "ui.kpi_depth_radial"), L(res.depth_m), border=True)
k1.caption(t("ui.cap_depth", tol=Lnum(res.depth_tol_m), a=Lnum(pr["depth_min_m"]), b=Lnum(pr["depth_max_m"])))
k2.metric(t("ui.kpi_width"), L(res.width_m), border=True)
k2.caption(t("ui.cap_width", tol=Lnum(res.width_tol_m), gmin=Lnum(res.width_min_m),
             a=Lnum(pr["width_min_m"]), b=Lnum(pr["width_max_m"])))
k3.metric(t("ui.kpi_squeeze"), f"{sq_lo * 100:.1f}–{sq_hi * 100:.1f} %", border=True)
k3.caption(t("ui.cap_squeeze", a=res.target[0], b=res.target[1],
             n=(nom_ref.squeeze_min + nom_ref.squeeze_max) / 2, T=ui.fmt_T(T_ref)))
k4.metric(t("ui.kpi_fill"), f"{res.fill_max:.1%}", border=True)
k4.caption(t("ui.cap_fill", lim=res.fill_limit, head=res.fill_limit - res.fill_max))

per_T = res.per_temperature
k5, k6, k7, k8 = st.columns(4)
if gland == "radial":
    k5.metric(t("ui.kpi_machine_depth"), L(res.machine_depth_m), border=True)
    k5.caption(t("ui.cap_machine"))
    k6.metric(t("ui.kpi_clearance"), f"{Lnum(res.clearance_m[0])}–{L(res.clearance_m[1])}", border=True)
    k6.caption(t("ui.cap_clearance", gap=L(res.allowed_gap_m)) if res.allowed_gap_m else t("ui.cap_clearance_nogap"))
else:
    k5.metric(t("ui.kpi_cs_tol"), f"± {L(res.cs_tol_m)}", border=True)
    k5.caption(t("ui.cap_cs_tol", src=t("ui.cs_tol_user") if cs_tol is not None else
                 (t("ui.cs_tol_std") if res.cs_tol_m > 0 else t("ui.cs_tol_none"))))
    k6.metric(t("ui.kpi_finish"), "0.4 µm" if fluid in ("ghe",) else "0.8 µm", border=True)
    k6.caption(t("ui.finish_face_gas") if fluid in ("ghe",) else t("ui.finish_static"))
k7.metric(t("ui.kpi_radius"), L(res.radius_m), border=True)
k7.caption(t("ui.cap_radius", a=Lnum(pr["radius_min_m"]), b=Lnum(pr["radius_max_m"])))
lo_row, hi_row = per_T.iloc[0], per_T.iloc[-1]
k8.metric(t("ui.kpi_volume"), f"{lo_row.volume_change:+.2%}", border=True)
k8.caption(t("ui.cap_volume", Tlo=ui.fmt_T(lo_row.T_K), vlo=lo_row.volume_change, Thi=ui.fmt_T(hi_row.T_K),
             vhi=hi_row.volume_change))

st.markdown(f"**{t('ui.overall')}: {status_label(res.status)}**")

# --------------------------------------------------------------------------- gauges + section
g1, g2 = st.columns(2)
rules = ds.rule_set(ds.seal_materials[seal_id].group, "static_face" if gland == "face" else "static_radial")
fmin = res.wc.output_min["fill"]
hard = rules.fill_hard_max.value if rules.fill_hard_max and rules.fill_hard_max.value else None
g1.plotly_chart(range_gauge(sq_lo, sq_hi, res.target, max(0.45, sq_hi * 1.15), t("ui.gauge_squeeze")),
                width="stretch", theme=None)
g2.plotly_chart(range_gauge(fmin, res.fill_max, (0.60, res.fill_limit), 1.0, t("ui.gauge_fill"), hard),
                width="stretch", theme=None)

st.subheader(t("ui.section_title_calc"))
side = "nominal"
if gland == "radial":
    side = st.radio(t("ui.section_side"), ["nominal", "tight", "wide"], horizontal=True,
                    format_func=lambda k: t(f"plots.side_{k}"), key="calc_side")
panels = []
for T in (inp.T_min_K, T_ref, inp.T_max_K):
    try:
        panels.append((ui.fmt_T(T), run_checks(res.design, ds, ThermalState(T, T, None, T_ref))[0]))
    except ThermalDataError:
        panels.append((ui.fmt_T(T), None))
st.plotly_chart(section_figure(panels, "face" if gland == "face" else "piston", side, LU, direction,
                               res.radius_m), width="stretch", theme=None)

# --------------------------------------------------------------------------- forces
st.subheader(t("ui.force_title"))
if hardness is None:
    st.info(t("ui.force_na"))
else:
    sq_nom = (nom_ref.squeeze_min + nom_ref.squeeze_max) / 2
    q_nom = load_per_length(ds, cs_m, sq_nom, hardness, ring_id)
    q_max = load_per_length(ds, cs_m, sq_hi, hardness, ring_id)
    to_unit = (lambda q: f"{q / 1000:.2f} N/mm") if LU == "mm" else (lambda q: f"{q / 175.1268:.1f} lbf/in")
    rows = []
    for label, q in ((t("ui.force_at_nominal", sq=sq_nom, T=ui.fmt_T(T_ref)), q_nom),
                     (t("ui.force_at_max", sq=sq_hi), q_max)):
        rows.append({t("ui.force_cond"): label,
                     t("ui.force_range"): "–" if q is None else f"{to_unit(q.min_N_per_m)} – {to_unit(q.max_N_per_m)}",
                     t("ui.force_typical"): "–" if q is None else
                     f"{to_unit(q.typical_min_N_per_m)} – {to_unit(q.typical_max_N_per_m)}"})
    st.markdown(f"**{t('ui.force_per_length')}**")
    st.table(pd.DataFrame(rows).style.hide(axis="index"))
    if q_nom is None or q_max is None:
        st.info(t("ui.force_na"))
    if ring_id is None:
        st.info(t("ui.force_need_id"))
    elif q_max is not None:
        fN = (lambda f: f"{f / 1000:.2f} kN") if LU == "mm" else (lambda f: f"{f / 4.4482216:.0f} lbf")
        D_seal = ring_id + 2 * cs_m
        clamp = face_clamp_load(q_max, ring_id, cs_m, D_seal, pressure, direction)
        f1, f2, f3 = st.columns(3)
        f1.metric(t("ui.force_total"), f"{fN(clamp.compression_N[0])} – {fN(clamp.compression_N[1])}", border=True)
        if gland == "face":
            f2.metric(t("ui.force_pressure", d=L(D_seal)), fN(clamp.pressure_N), border=True)
            f3.metric(t("ui.force_clamp"), fN(clamp.clamp_min_N), border=True)
            st.caption(t("ui.force_clamp_note") + ("" if direction == "internal" else " " + t("ui.force_external")))
        else:
            st.caption(t("ui.force_radial_note"))

# --------------------------------------------------------------------------- temperature behaviour
st.subheader(t("ui.temp_behaviour"))
st.plotly_chart(groove_envelope_figure(per_T, ui.T_UNIT, res.target, res.fill_limit, hard),
                width="stretch", theme=None)
tab = pd.DataFrame({
    t("ui.col_T"): [ui.fmt_T(T) for T in per_T.T_K],
    t("ui.col_cs_T"): [L(v) for v in per_T.cs_m],
    t("ui.col_sq_range"): [f"{a:.1%} – {b:.1%}" for a, b in zip(per_T.squeeze_lo, per_T.squeeze_hi)],
    t("ui.col_sq_nom"): [f"{v:.1%}" for v in per_T.squeeze_nominal],
    t("ui.col_fill_max"): [f"{v:.1%}" for v in per_T.fill_max],
    t("ui.col_dv"): [f"{v:+.2%}" for v in per_T.volume_change],
})
if gland == "radial":
    tab[t("ui.col_gap")] = [L(v) for v in per_T.gap_max_m]
st.dataframe(tab, hide_index=True, width="stretch")
st.download_button(t("ui.download_csv"), per_T.to_csv(index=False).encode("utf-8"),
                   file_name="yuva_sicaklik.csv", mime="text/csv")

# --------------------------------------------------------------------------- checks and method
st.subheader(t("ui.calc_checks"))
order = {Status.FAIL: 0, Status.WARN: 1, Status.PASS: 2}
status_table([(r.status, render_check(r), None) for r in sorted(worst, key=lambda r: order[r.status])])
with st.expander(t("ui.method")):
    for item in t_list("ui.method_items"):
        st.markdown(f"- {item}")
