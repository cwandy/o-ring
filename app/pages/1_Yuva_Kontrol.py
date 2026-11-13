"""Yuva Kontrol: check an existing gland design at one point and over a temperature sweep."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ for `common`

from common import data_banner, dataset, result_rows, sidebar_units, status_label, status_table
from oring_designer import units
from oring_designer.checks import Design, overall_status, run_checks
from oring_designer.geometry import GeometryError
from oring_designer.gland_types import FaceGland, ORing, PistonGland, RodGland, ThermalState
from oring_designer.i18n import render_check, t
from oring_designer.sweep import summary_status, sweep, temperatures, to_frame, worst_by_family
from oring_designer.thermal import ThermalDataError
from oring_designer.viz.plots import clearance_figure, squeeze_fill_figure


st.title(t("ui.page_check"))

ds = dataset()
u = sidebar_units()
L_UNIT, T_UNIT, P_UNIT = u["length"], u["temp"], u["pressure"]
T_LABEL = {"degC": "°C", "K": "K", "degF": "°F"}[T_UNIT]
FMT = "%.3f" if L_UNIT == "mm" else "%.4f"


def length(label: str, default_mm: float, key: str, min_value: float = 0.0) -> float:
    """Number input in the chosen length unit; returns metres."""
    default = units.length_from_m(default_mm * 1e-3, L_UNIT)
    v = st.number_input(f"{label} [{L_UNIT}]", value=round(default, 4), min_value=min_value,
                        format=FMT, key=f"{key}_{L_UNIT}")
    return units.length_to_m(v, L_UNIT)


def temperature(label: str, default_K: float, key: str, container=st) -> float:
    default = units.temperature_from_K(default_K, T_UNIT)
    v = container.number_input(f"{label} [{T_LABEL}]", value=round(default, 2), format="%.2f",
                               key=f"{key}_{T_UNIT}")
    return units.temperature_to_K(v, T_UNIT)


def temp_delta(label: str, default_K: float, key: str) -> float:
    """Temperature difference input (K and °C share the scale, °F is 5/9)."""
    factor = 9 / 5 if T_UNIT == "degF" else 1.0
    v = st.number_input(f"{label} [{T_LABEL}]", value=default_K * factor, format="%.1f",
                        key=f"{key}_{T_UNIT}")
    return v / factor


def fmt_T(T_K: float) -> str:
    return f"{units.temperature_from_K(T_K, T_UNIT):.1f} {T_LABEL}"


T_ref = temperature(t("ui.T_ref"), 293.15, "T_ref", container=st.sidebar)

# --------------------------------------------------------------------------- inputs
seal_ids = list(ds.seal_materials)
housing_ids = list(ds.housing_materials)
c1, c2, c3 = st.columns(3)

with c1:
    st.subheader(t("ui.materials"))
    seal_id = st.selectbox(t("ui.seal_material"), seal_ids, index=seal_ids.index("vmq"),
                           format_func=lambda k: ds.seal_materials[k].name)
    groove_id = st.selectbox(t("ui.groove_material"), housing_ids, index=housing_ids.index("al6061"),
                             format_func=lambda k: ds.housing_materials[k].name)
    st.selectbox(t("ui.temper"), [x.id for x in ds.housing_materials[groove_id].tempers],
                 format_func=lambda k: k, key=f"temper_{groove_id}")
    mating_id, mating_delta = None, 0.0
    if st.checkbox(t("ui.mating_separate")):
        mating_id = st.selectbox(t("ui.mating_material"), housing_ids,
                                 index=housing_ids.index(groove_id),
                                 format_func=lambda k: ds.housing_materials[k].name)
        st.selectbox(t("ui.temper"), [x.id for x in ds.housing_materials[mating_id].tempers],
                     key=f"temper_m_{mating_id}")
        mating_delta = temp_delta(t("ui.mating_delta"), 0.0, "mating_delta")

with c2:
    st.subheader(t("ui.gland"))
    kind = st.radio(t("ui.gland_type"), ["piston", "rod", "face"], horizontal=True,
                    format_func=lambda k: t(f"ui.{k}"))
    try:
        if kind == "piston":
            bore = length(t("ui.bore_diameter"), 50.0, "bore")
            piston_d = length(t("ui.piston_diameter"), 49.9, "piston")
            groove = length(t("ui.groove_diameter_piston"), 44.2, "groove_p")
            width = length(t("ui.groove_width"), 4.8, "width_p")
            radius = length(t("ui.corner_radius"), 0.0, "radius_p")
            ring_default = (43.7, 3.53)
        elif kind == "rod":
            rod = length(t("ui.rod_diameter"), 20.0, "rod")
            throat = length(t("ui.throat_diameter"), 20.1, "throat")
            groove = length(t("ui.groove_diameter_rod"), 26.0, "groove_r")
            width = length(t("ui.groove_width"), 4.8, "width_r")
            radius = length(t("ui.corner_radius"), 0.0, "radius_r")
            ring_default = (19.8, 3.53)
        else:
            direction = st.radio(t("ui.pressure_direction"), ["internal", "external"],
                                 horizontal=True, format_func=lambda k: t(f"ui.{k}"))
            gid = length(t("ui.groove_id"), 27.5, "gid")
            god = length(t("ui.groove_od"), 36.8, "god")
            depth = length(t("ui.groove_depth"), 2.65, "gdepth")
            radius = length(t("ui.corner_radius"), 0.0, "radius_f")
            ring_default = (29.87, 3.53)
        ecc = None
        if kind != "face" and not st.checkbox(t("ui.full_eccentricity"), value=True):
            ecc = length(t("ui.eccentricity"), 0.0, "ecc")
    except Exception as exc:  # pragma: no cover - widget errors
        st.error(t("ui.invalid_input", error=exc))
        st.stop()

with c3:
    st.subheader(t("ui.oring"))
    ring_id = length(t("ui.oring_id"), ring_default[0], f"rid_{kind}")
    ring_cs = length(t("ui.oring_cs"), ring_default[1], f"rcs_{kind}")
    hardness = st.number_input(t("ui.hardness"), value=70.0, min_value=30.0, max_value=95.0, step=5.0)
    swell = st.number_input(t("ui.swell"), value=0.0, min_value=-0.2, max_value=0.5, step=0.01,
                            format="%.2f")
    cs_method = st.selectbox(t("ui.cs_method"), ["volume_centroid", "volume_id", "parker_observed"],
                             format_func=lambda k: t(f"ui.cs_{k}"))
    st.subheader(t("ui.operating"))
    p_disp = st.number_input(f"{t('ui.pressure')} [{P_UNIT}]",
                             value=round(units.pressure_from_Pa(50e5, P_UNIT), 3),
                             min_value=0.0, key=f"p_{P_UNIT}")
    pressure = units.pressure_to_Pa(p_disp, P_UNIT)
    fluid = st.selectbox(t("ui.fluid"), [None, *ds.fluids],
                         format_func=lambda k: t("ui.no_fluid") if k is None else ds.fluids[k].name)

if kind == "piston":
    gland = PistonGland(bore, piston_d, groove, width, radius, ecc)
elif kind == "rod":
    gland = RodGland(rod, throat, groove, width, radius, ecc)
else:
    gland = FaceGland(gid, god, depth, direction, radius)

design = Design(gland=gland, oring=ORing(ring_id, ring_cs), seal_material=seal_id,
                groove_material=groove_id, mating_material=mating_id, pressure_Pa=pressure,
                hardness_shore_a=hardness, fluid=fluid, cs_method=cs_method, swell=swell)

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

seal = ds.seal_materials[seal_id]
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
with st.expander(t("ui.data_table")):
    st.dataframe(df, use_container_width=True)
