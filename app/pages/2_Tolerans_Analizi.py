"""Tolerans Analizi: worst-case, RSS and Monte Carlo over the drawing tolerances."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ for `common`

from common import data_banner, dataset, sidebar_units, status_label, status_table
from design_form import UnitInputs, design_form
from oring_designer.checks import Design, allowed_extrusion_gap_m
from oring_designer.geometry import GeometryError
from oring_designer.gland_types import ThermalState
from oring_designer.i18n import family_label, render_check, t
from oring_designer.thermal import ThermalDataError
from oring_designer.tolerance import (
    DEFAULT_MC_SAMPLES,
    Tolerance,
    monte_carlo,
    nominal_value,
    rss,
    toleranceable_fields,
    worst_case,
)
from oring_designer.viz.plots import mc_histogram

st.title(t("ui.page_tolerance"))
ds = dataset()
ui = UnitInputs(sidebar_units())
T_ref = ui.temperature(t("ui.T_ref"), 293.15, "T_ref", container=st.sidebar)
form = design_form(ds, ui)
design: Design = form.design

FIELD_LABEL = {
    "bore_diameter_m": "ui.bore_diameter", "piston_diameter_m": "ui.piston_diameter",
    "rod_diameter_m": "ui.rod_diameter", "throat_diameter_m": "ui.throat_diameter",
    "groove_width_m": "ui.groove_width", "corner_radius_m": "ui.corner_radius",
    "groove_id_m": "ui.groove_id", "groove_od_m": "ui.groove_od", "groove_depth_m": "ui.groove_depth",
    "id_m": "ui.oring_id", "cs_m": "ui.oring_cs",
}
DEFAULT_TOL_MM = {"oring.cs_m": 0.10, "oring.id_m": 0.30, "gland.corner_radius_m": 0.0}


def field_label(path: str) -> str:
    name = path.split(".")[1]
    if name == "groove_diameter_m":
        return t("ui.groove_diameter_piston" if form.kind == "piston" else "ui.groove_diameter_rod")
    return t(FIELD_LABEL[name])


# --------------------------------------------------------------------------- inputs
st.divider()
st.subheader(t("ui.tolerances"))
st.caption(t("ui.tolerance_note"))
tols: dict[str, Tolerance] = {}
for path in toleranceable_fields(design):
    d = DEFAULT_TOL_MM.get(path, 0.025)
    a, b, c = st.columns([2, 1, 1])
    a.markdown(f"{field_label(path)} — {ui.fmt_L(nominal_value(design, path))}")
    lo = ui.length(t("ui.tol_lower"), -d, f"tl_{form.kind}_{path}", min_value=None, container=b)
    hi = ui.length(t("ui.tol_upper"), d, f"tu_{form.kind}_{path}", min_value=None, container=c)
    if lo != 0 or hi != 0:
        tols[path] = Tolerance(min(lo, hi), max(lo, hi))

st.subheader(t("ui.analysis_state"))
s1, s2 = st.columns(2)
T_seal = ui.temperature(t("ui.T_seal"), T_ref, "tol_T_seal", container=s1)
T_housing = ui.temperature(t("ui.T_housing"), T_ref, "tol_T_housing", container=s2)
state = ThermalState(T_seal, T_housing, T_housing + form.mating_delta_K, T_ref)
states = [state]
if st.checkbox(t("ui.wc_temps")):
    w1, w2 = st.columns(2)
    T_lo = ui.temperature(t("ui.T_min"), 250.0, "wc_T_min", container=w1)
    T_hi = ui.temperature(t("ui.T_max"), 300.0, "wc_T_max", container=w2)
    states += [ThermalState(T, T, T + form.mating_delta_K, T_ref) for T in (T_lo, T_hi)]

st.subheader(t("ui.mc_settings"))
m1, m2, m3 = st.columns(3)
n = int(m1.number_input(t("ui.mc_n"), value=DEFAULT_MC_SAMPLES, min_value=100, max_value=200_000,
                        step=1000))
dist = m2.radio(t("ui.mc_dist"), ["normal", "uniform"], format_func=lambda k: t(f"ui.dist_{k}"))
seed = int(m3.number_input(t("ui.mc_seed"), value=1, min_value=0, step=1))


@st.cache_data(show_spinner=True)
def analyse(design: Design, tols: dict, state: ThermalState, states: tuple, n: int, dist: str,
            seed: int):
    ds_ = dataset()
    return (worst_case(design, tols, ds_, list(states)), rss(design, tols, ds_, state),
            monte_carlo(design, tols, ds_, state, n, dist, seed))


if not tols:
    st.info(t("ui.tolerances"))
    st.stop()
try:
    wc, rs, mc = analyse(design, tols, state, tuple(states), n, dist, seed)
except (ThermalDataError, GeometryError, ValueError) as exc:
    st.error(t("ui.tol_error", error=exc))
    st.stop()

# --------------------------------------------------------------------------- results
st.divider()
worst_list = [r for r, _ in wc.worst_results.values()]
data_banner(any(r.data_quality is not None and r.data_quality.needs_warning for r in worst_list))

nominal = wc.table[wc.table.corner == "nominal"].iloc[0]
outputs = ["squeeze_min", "squeeze_max", "fill", "stretch", "max_extrusion_gap_m"]
if form.kind != "piston":
    outputs.append("circumferential_compression")
if form.kind == "face":
    outputs.remove("max_extrusion_gap_m")


def fmt(key: str, v: float) -> str:
    if pd.isna(v):
        return "–"
    return ui.fmt_L(v) if key.endswith("_m") else f"{v:.2%}"


st.subheader(t("ui.summary_table"))
rows = []
for k in outputs:
    s = mc.samples[k]
    rows.append({
        t("ui.col_output"): t(f"ui.out_{k}"),
        t("ui.col_nominal"): fmt(k, nominal[k]),
        t("ui.col_wc"): f"{fmt(k, wc.output_min[k])} – {fmt(k, wc.output_max[k])}",
        t("ui.col_rss"): f"{fmt(k, rs.low(k))} – {fmt(k, rs.high(k))}",
        t("ui.col_mc"): f"{fmt(k, s.min())} – {fmt(k, s.max())}",
        t("ui.col_mc_mean"): fmt(k, s.mean()),
    })
st.table(pd.DataFrame(rows).style.hide(axis="index"))

c1, c2 = st.columns(2)
with c1:
    st.subheader(t("ui.wc_results"))
    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    items = sorted(wc.worst_results.values(), key=lambda rv: order[rv[0].status.value])
    status_table([(r.status, render_check(r), None) for r, _ in items])
with c2:
    st.subheader(t("ui.mc_rates"))
    st.metric(t("ui.overall_pass_rate"), f"{mc.overall_rates['PASS']:.1%}")
    rates = mc.family_rates.copy()
    rates.index = [family_label(f) for f in rates.index]
    rates.index.name = t("ui.col_family")
    rates = rates.rename(columns={"PASS": status_label("PASS"), "WARN": status_label("WARN"),
                                  "FAIL": status_label("FAIL")})
    st.table(rates.style.format("{:.1%}"))

# --------------------------------------------------------------------------- histograms
st.subheader(t("ui.histograms"))
seal = ds.seal_materials[design.seal_material]
rules = ds.rule_set(seal.group, "static_face" if form.kind == "face" else "static_radial")
band = rules.recommended_squeeze.band_for(design.oring.cs_m) if rules.recommended_squeeze else None


def lim(rule):
    return rule.value if rule is not None and rule.value is not None else None


limits = {
    "squeeze_min": [(band.min, t("ui.band_min"))] if band else [],
    "squeeze_max": ([(band.max, t("ui.band_max"))] if band else [])
    + ([(lim(rules.squeeze_max), t("ui.limit"))] if lim(rules.squeeze_max) else []),
    "fill": [(v, t("ui.limit")) for v in (lim(rules.fill_max), lim(rules.fill_hard_max)) if v],
    "stretch": [(lim(rules.stretch_max), t("ui.limit"))] if lim(rules.stretch_max) else [],
    "max_extrusion_gap_m": [],
    "circumferential_compression": [],
}
if design.hardness_shore_a is not None and seal.group == "elastomer":
    allowed, _ = allowed_extrusion_gap_m(ds.extrusion_limits, design.pressure_Pa,
                                         design.hardness_shore_a, seal.id in ("vmq", "pvmq"))
    if allowed is not None:
        limits["max_extrusion_gap_m"] = [(allowed, t("ui.allowed"))]

cols = st.columns(2)
for i, k in enumerate(outputs):
    is_len = k.endswith("_m")
    scale = (1e3 if ui.L_UNIT == "mm" else 1 / 0.0254) if is_len else 1.0
    fig = mc_histogram(
        mc.samples[k], t(f"ui.out_{k}"), limits.get(k),
        [(wc.output_min[k], wc.output_max[k], t("ui.wc_range")),
         (rs.low(k), rs.high(k), t("ui.rss_range"))],
        scale=scale, fmt=(".3f" if ui.L_UNIT == "mm" else ".4f") if is_len else ".1%",
        unit=f"[{ui.L_UNIT}]" if is_len else "",
    )
    cols[i % 2].plotly_chart(fig, use_container_width=True, theme=None)

with st.expander(t("ui.sensitivities")):
    per_unit = 1e-3 if ui.L_UNIT == "mm" else 0.0254  # ratios per mm / per inch
    sens = rs.sensitivities.loc[outputs].copy()
    for k in outputs:
        if not k.endswith("_m"):
            sens.loc[k] *= per_unit
    sens = sens.rename(index=lambda k: t(f"ui.out_{k}") + ("" if k.endswith("_m") else f" / {ui.L_UNIT}"),
                       columns=field_label)
    st.dataframe(sens.style.format("{:.4g}"), use_container_width=True)
with st.expander(t("ui.mc_table")):
    st.dataframe(mc.samples.head(2000), use_container_width=True)
