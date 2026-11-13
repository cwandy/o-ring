"""Shared design input form (materials, gland, O-ring, operating conditions)."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from oring_designer import units
from oring_designer.checks import Design
from oring_designer.gland_types import FaceGland, ORing, PistonGland, RodGland
from oring_designer.i18n import t
from oring_designer.loader import Dataset


class UnitInputs:
    """Number inputs in the user's display units; values returned in SI."""

    def __init__(self, u: dict[str, str]):
        self.L_UNIT, self.T_UNIT, self.P_UNIT = u["length"], u["temp"], u["pressure"]
        self.T_LABEL = {"degC": "°C", "K": "K", "degF": "°F"}[self.T_UNIT]
        self.FMT = "%.3f" if self.L_UNIT == "mm" else "%.4f"

    def length(self, label: str, default_mm: float, key: str, min_value: float | None = 0.0,
               container=st) -> float:
        """Number input in the chosen length unit; returns metres."""
        default = units.length_from_m(default_mm * 1e-3, self.L_UNIT)
        v = container.number_input(f"{label} [{self.L_UNIT}]", value=round(default, 4),
                                   min_value=min_value, format=self.FMT,
                                   key=f"{key}_{self.L_UNIT}")
        return units.length_to_m(v, self.L_UNIT)

    def temperature(self, label: str, default_K: float, key: str, container=st) -> float:
        default = units.temperature_from_K(default_K, self.T_UNIT)
        v = container.number_input(f"{label} [{self.T_LABEL}]", value=round(default, 2),
                                   format="%.2f", key=f"{key}_{self.T_UNIT}")
        return units.temperature_to_K(v, self.T_UNIT)

    def temp_delta(self, label: str, default_K: float, key: str, container=st) -> float:
        """Temperature difference input (K and °C share the scale, °F is 5/9)."""
        factor = 9 / 5 if self.T_UNIT == "degF" else 1.0
        v = container.number_input(f"{label} [{self.T_LABEL}]", value=default_K * factor,
                                   format="%.1f", key=f"{key}_{self.T_UNIT}")
        return v / factor

    def fmt_T(self, T_K: float) -> str:
        return f"{units.temperature_from_K(T_K, self.T_UNIT):.1f} {self.T_LABEL}"

    def fmt_L(self, L_m: float) -> str:
        v = units.length_from_m(L_m, self.L_UNIT)
        return f"{v:.3f} mm" if self.L_UNIT == "mm" else f"{v:.4f} in"


@dataclass(frozen=True)
class FormResult:
    design: Design
    kind: str
    mating_delta_K: float


def design_form(ds: Dataset, ui: UnitInputs) -> FormResult:
    """Render the design inputs and return the Design (dimensions at T_ref, SI)."""
    length, temp_delta = ui.length, ui.temp_delta
    L_UNIT, P_UNIT = ui.L_UNIT, ui.P_UNIT
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

    return FormResult(design, kind, mating_delta)
