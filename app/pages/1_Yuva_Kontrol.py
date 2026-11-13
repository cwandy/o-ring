"""Yuva Kontrol: check an existing gland design at one point and over a temperature sweep."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ for `common`

from common import (data_banner, dataset, result_rows, section_view, sidebar_units, status_label,
                    status_table)
from design_form import UnitInputs, design_form
from oring_designer.checks import Design, overall_status, run_checks
from oring_designer.geometry import GeometryError
from oring_designer.gland_types import ThermalState
from oring_designer.i18n import render_check, t
from oring_designer.sweep import summary_status, sweep, temperatures, to_frame, worst_by_family
from oring_designer.thermal import ThermalDataError
from oring_designer.viz.plots import clearance_figure, squeeze_fill_figure


st.title(t("ui.page_check"))

ds = dataset()
ui = UnitInputs(sidebar_units())
L_UNIT, T_UNIT = ui.L_UNIT, ui.T_UNIT
temperature, temp_delta, fmt_T = ui.temperature, ui.temp_delta, ui.fmt_T
T_ref = temperature(t("ui.T_ref"), 293.15, "T_ref", container=st.sidebar)

form = design_form(ds, ui)
design, kind, mating_delta = form.design, form.kind, form.mating_delta_K
ring_cs = design.oring.cs_m

# --------------------------------------------------------------------------- operating point
st.divider()
st.subheader(t("ui.point"))
p1, p2 = st.columns(2)
with p1:
    T_seal = temperature(t("ui.T_seal"), T_ref, "T_seal_pt")
with p2:
    T_housing = temperature(t("ui.T_housing"), T_ref, "T_housing_pt")
state = ThermalState(T_seal, T_housing, T_housing + mating_delta, T_ref)

try:
    st_point, res_point = run_checks(design, ds, state)
except ThermalDataError as exc:
    st.error(f"{t('ui.no_data_point')} ({exc})")
    st_point, res_point = None, []
except GeometryError as exc:
    st.error(t("ui.invalid_input", error=exc))
    st.stop()

if st_point is not None:
    data_banner(any(r.data_quality is not None and r.data_quality.needs_warning for r in res_point))
    st.markdown(f"**{t('ui.overall')}: {status_label(overall_status(res_point))}**")
    k = 1e3 if L_UNIT == "mm" else 1 / 0.0254
    st.caption(t("ui.geometry_summary", sq_min=st_point.squeeze_min, sq_max=st_point.squeeze_max,
                 fill=st_point.fill, stretch=st_point.stretch, cs=st_point.cs_eff_m * k, unit=L_UNIT))
    st.subheader(t("ui.results_point"))
    status_table(result_rows(res_point))

# --------------------------------------------------------------------------- sweep
st.divider()
st.subheader(t("ui.sweep"))
s1, s2, s3, s4 = st.columns(4)
with s1:
    T_min = temperature(t("ui.T_min"), 200.0, "T_min")
with s2:
    T_max = temperature(t("ui.T_max"), 300.0, "T_max")
with s3:
    step = temp_delta(t("ui.T_step"), 5.0, "T_step")
with s4:
    mode = st.radio(t("ui.mode"), ["equilibrium", "lag"],
                    format_func=lambda k: t(f"ui.mode_{k}"))
    delta = temp_delta(t("ui.delta_T"), 10.0, "delta_T") if mode == "lag" else 0.0


@st.cache_data(show_spinner=False)
def run_sweep(design: Design, T_min: float, T_max: float, step: float, mode: str, delta: float,
              mating_delta: float, T_ref: float):
    pts = sweep(design, dataset(), temperatures(T_min, T_max, max(step, 0.1)), mode, delta,
                mating_delta, T_ref)
    return pts, to_frame(pts)


try:
    points, df = run_sweep(design, min(T_min, T_max), max(T_min, T_max), step, mode, delta,
                           mating_delta, T_ref)
except (GeometryError, ValueError) as exc:
    st.error(t("ui.invalid_input", error=exc))
    st.stop()

worst = worst_by_family(points)
data_banner(any(w.result.data_quality is not None and w.result.data_quality.needs_warning
                for w in worst) or df["no_data"].notna().any())
st.markdown(f"**{t('ui.overall')}: {status_label(summary_status(points))}**")
st.subheader(t("ui.results_sweep"))
status_table([(w.result.status, render_check(w.result), f"{fmt_T(w.T_housing_K)} / {fmt_T(w.T_seal_K)}")
              for w in worst])

seal = ds.seal_materials[design.seal_material]
rules = ds.rule_set(seal.group, "static_face" if kind == "face" else "static_radial")
band = rules.recommended_squeeze.band_for(ring_cs) if rules.recommended_squeeze else None
low = seal.low_temp_limit_K.value if seal.low_temp_limit_K else None
fig = squeeze_fill_figure(
    df, temp_unit=T_UNIT,
    squeeze_band=(band.min, band.max) if band else None,
    squeeze_max=rules.squeeze_max.value if rules.squeeze_max else None,
    fill_band=(rules.fill_min.value, rules.fill_max.value)
    if rules.fill_min and rules.fill_min.value is not None and rules.fill_max else None,
    fill_hard_max=rules.fill_hard_max.value if rules.fill_hard_max else None,
    low_temp_limit_K=low if seal.group == "elastomer" else None,
    low_temp_band_K=ds.common_rules.low_temp_warning_band_K.value,
    seal_offset_K=delta,
)
st.plotly_chart(fig, use_container_width=True, theme=None)
if kind != "face":
    st.plotly_chart(clearance_figure(df, T_UNIT, L_UNIT), use_container_width=True, theme=None)
st.subheader(t("ui.section"))
T_lo, T_hi = min(T_min, T_max), max(T_min, T_max)
section_states = [
    (f"{fmt_T(T)}" + ("" if mode == "equilibrium" else f" / {fmt_T(T + delta)}"),
     ThermalState(T + delta, T, T + mating_delta, T_ref))
    for T in (T_lo, T_ref, T_hi)
]
section_view(design, ds, section_states, kind, L_UNIT, key="section_side_check")
with st.expander(t("ui.data_table")):
    st.dataframe(df, use_container_width=True)
