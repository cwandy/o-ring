"""Yaylı Conta: spring-energized seal check from catalog dimensions over temperature."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ for `common`

from common import data_banner, dataset, sidebar_units, status_label, status_table
from design_form import UnitInputs
from oring_designer.i18n import render_check, t
from oring_designer.spring_energized import SeDesign, SeGland, SeLimits, SeSeal, se_frame, se_sweep
from oring_designer.sweep import summary_status, temperatures, worst_by_family
from oring_designer.viz.plots import se_figure

st.title(t("ui.page_se"))
st.caption(t("ui.se_intro"))
ds = dataset()
ui = UnitInputs(sidebar_units())
T_ref = ui.temperature(t("ui.T_ref"), 293.15, "T_ref", container=st.sidebar)
st.caption(t("ui.se_example_note"))

jackets = [k for k, m in ds.seal_materials.items() if m.group == "thermoplastic"]
housing_ids = list(ds.housing_materials)


def optional(label: str, default_mm: float, key: str) -> float | None:
    """Catalog limit: entered only when the box is ticked (K23)."""
    if st.checkbox(f"{label} — {t('ui.enter_limit')}", key=f"chk_{key}"):
        return ui.length(label, default_mm, key)
    return None


c1, c2, c3 = st.columns(3)
with c1:
    st.subheader(t("ui.materials"))
    jacket = st.selectbox(t("ui.jacket_material"), jackets, format_func=lambda k: ds.seal_materials[k].name)
    groove_id = st.selectbox(t("ui.groove_material"), housing_ids, index=housing_ids.index("ss304"),
                             format_func=lambda k: ds.housing_materials[k].name)
    mating_id, mating_delta = None, 0.0
    if st.checkbox(t("ui.mating_separate")):
        mating_id = st.selectbox(t("ui.mating_material"), housing_ids, index=housing_ids.index(groove_id),
                                 format_func=lambda k: ds.housing_materials[k].name)
        mating_delta = ui.temp_delta(t("ui.mating_delta"), 0.0, "se_mating_delta")
    st.subheader(t("ui.sweep"))
    T_min = ui.temperature(t("ui.T_min"), 77.0, "se_T_min")
    T_max = ui.temperature(t("ui.T_max"), 300.0, "se_T_max")
    step = ui.temp_delta(t("ui.T_step"), 5.0, "se_step")
    mode = st.radio(t("ui.mode"), ["equilibrium", "lag"], format_func=lambda k: t(f"ui.mode_{k}"))
    delta = ui.temp_delta(t("ui.delta_T"), 10.0, "se_delta") if mode == "lag" else 0.0

with c2:
    st.subheader(t("ui.se_gland"))
    kind = st.radio(t("ui.gland_type"), ["piston", "rod", "face"], horizontal=True,
                    format_func=lambda k: t(f"ui.{k}"))
    direction, depth, ecc = "internal", 0.0, None
    if kind == "piston":
        mate = ui.length(t("ui.bore_diameter"), 50.0, "se_bore")
        part = ui.length(t("ui.piston_diameter"), 49.9, "se_piston")
        groove = ui.length(t("ui.groove_diameter_piston"), 43.6, "se_groove_p")
        static_default, static_label = 43.6, t("ui.se_static_piston")
    elif kind == "rod":
        mate = ui.length(t("ui.rod_diameter"), 20.0, "se_rod")
        part = ui.length(t("ui.throat_diameter"), 20.1, "se_throat")
        groove = ui.length(t("ui.groove_diameter_rod"), 26.4, "se_groove_r")
        static_default, static_label = 26.4, t("ui.se_static_rod")
    else:
        direction = st.radio(t("ui.pressure_direction"), ["internal", "external"], horizontal=True,
                             format_func=lambda k: t(f"ui.{k}"))
        mate = part = 0.0
        groove = ui.length(t(f"ui.se_groove_wall_face_{direction}"), 40.0 if direction == "internal" else 30.0,
                           f"se_wall_{direction}")
        depth = ui.length(t("ui.groove_depth"), 3.2, "se_depth")
        static_default, static_label = (40.0 if direction == "internal" else 30.0), t(f"ui.se_static_face_{direction}")
    width = ui.length(t("ui.groove_width"), 4.5, f"se_width_{kind}")
    if kind != "face" and not st.checkbox(t("ui.full_eccentricity"), value=True, key="se_full_ecc"):
        ecc = ui.length(t("ui.eccentricity"), 0.0, "se_ecc")

with c3:
    st.subheader(t("ui.se_seal"))
    h = ui.length(t("ui.se_free_height"), 3.4, f"se_h_{kind}")
    b = ui.length(t("ui.se_width"), 4.0, f"se_b_{kind}")
    d_static = ui.length(static_label, static_default, f"se_ds_{kind}_{direction}")
    st.subheader(t("ui.se_limits"))
    cmin = optional(t("ui.se_comp_min"), 0.10, "se_cmin")
    cmax = optional(t("ui.se_comp_max"), 0.40, "se_cmax")
    gmax = optional(t("ui.se_gap_max"), 0.10, "se_gmax") if kind != "face" else None
    axmin = ui.length(t("ui.se_axial_min"), 0.0, "se_axmin")
    fit_min = None
    if st.checkbox(f"{t('ui.se_fit_min')} — {t('ui.enter_limit')}", key="chk_fit"):
        fit_min = st.number_input(t("ui.se_fit_min"), value=0.0, format="%.4f", key="se_fit_min")

design = SeDesign(
    gland=SeGland(kind, mate, part, groove, width, depth, direction, ecc),
    seal=SeSeal(h, b, d_static),
    limits=SeLimits(cmin, cmax, gmax, axmin, fit_min),
    jacket_material=jacket, groove_material=groove_id, mating_material=mating_id,
)


@st.cache_data(show_spinner=False)
def run(design: SeDesign, T_lo: float, T_hi: float, step: float, mode: str, delta: float,
        mating_delta: float, T_ref: float):
    pts = se_sweep(design, dataset(), temperatures(T_lo, T_hi, max(step, 0.1)), mode, delta,
                   mating_delta, T_ref)
    return pts, se_frame(pts)


try:
    points, df = run(design, min(T_min, T_max), max(T_min, T_max), step, mode, delta, mating_delta, T_ref)
except ValueError as exc:
    st.error(t("ui.invalid_input", error=exc))
    st.stop()

st.divider()
worst = worst_by_family(points)
data_banner(df["no_data"].notna().any()
            or any(w.result.data_quality is not None and w.result.data_quality.needs_warning for w in worst))
st.markdown(f"**{t('ui.overall')}: {status_label(summary_status(points))}**")
st.subheader(t("ui.se_results"))
status_table([(w.result.status, render_check(w.result),
               f"{ui.fmt_T(w.T_housing_K)} / {ui.fmt_T(w.T_seal_K)}") for w in worst])
st.plotly_chart(se_figure(df, ui.T_UNIT, ui.L_UNIT, (cmin, cmax), gmax), use_container_width=True,
                theme=None)
with st.expander(t("ui.data_table")):
    st.dataframe(df, use_container_width=True)
