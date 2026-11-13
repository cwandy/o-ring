"""Spring-energized seal mode (SPEC §11 Faz 7, K23).

Gland and seal dimensions come from the user's manufacturer catalog (entered at T_ref);
the program checks thermal clearances and compression over temperature. Catalog limits
that are not entered produce WARN ``<check>_no_limit`` (no values are assumed).

Geometry (lengths in m, at the thermal state):
* piston (seal in the piston groove, lip on the bore): L = (D_bore - D_groove)/2 is the
  radial gland depth; the static side is the seal I.D. on the groove bottom, static fit
  = (D_groove - d_static) / d_static (positive: seal held on the groove bottom).
* rod (seal in the housing groove, lip on the rod): L = (D_groove - d_rod)/2; static side
  is the seal O.D. in the groove, fit = (d_static - D_groove) / d_static.
* face: L = groove depth (metal-to-metal contact); static side is the seal O.D. on the
  groove O.D. wall (internal pressure) or the seal I.D. on the groove I.D. wall (external);
  fit as for rod / piston respectively.

Radial (face: axial) compression delta = h_free - L, evaluated on the wide side (L + e,
minimum compression) and the tight side (L - e, maximum compression), e = eccentricity
(default full, c/2). Extrusion gap (radial glands) = c/2 + e. Axial clearance = groove
width - seal width.

Simplifications: the jacket (PTFE / PCTFE) and the housing parts strain freely with their
own thermal data; the metallic spring and its load change with temperature are not
modelled; the seal is a rigid ring for thermal scaling (no installation stress).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .checks import CheckResult, Status, overall_status
from .gland_types import ThermalState
from .loader import Dataset
from .models import DataQuality, worst_quality
from .thermal import ThermalDataError, scale_factor_with_quality

Kind = Literal["piston", "rod", "face"]


@dataclass(frozen=True)
class SeGland:
    kind: Kind
    mating_diameter_m: float  # piston: bore; rod: rod; face: unused (0)
    groove_part_diameter_m: float  # piston: piston O.D.; rod: throat; face: unused (0)
    groove_diameter_m: float  # piston: groove bottom; rod: groove O.D.; face: pressure-side groove wall
    groove_width_m: float  # axial (radial glands) or radial (face) width
    groove_depth_m: float = 0.0  # face only
    pressure_direction: Literal["internal", "external"] = "internal"  # face only
    eccentricity_m: float | None = None


@dataclass(frozen=True)
class SeSeal:
    free_height_m: float  # radial (radial glands) or axial (face) free section height
    width_m: float  # axial (radial glands) or radial (face) seal width
    static_diameter_m: float  # diameter of the static sealing side (see module doc)


@dataclass(frozen=True)
class SeLimits:
    """Catalog limits (absolute, m). None = not entered (WARN)."""

    compression_min_m: float | None = None
    compression_max_m: float | None = None
    extrusion_gap_max_m: float | None = None
    axial_clearance_min_m: float = 0.0
    static_fit_min: float | None = None


@dataclass(frozen=True)
class SeDesign:
    gland: SeGland
    seal: SeSeal
    limits: SeLimits
    jacket_material: str
    groove_material: str
    mating_material: str | None = None


@dataclass(frozen=True)
class SeState:
    depth_nominal_m: float
    depth_min_m: float
    depth_max_m: float
    free_height_m: float
    compression_min_m: float  # wide side
    compression_max_m: float  # tight side
    max_extrusion_gap_m: float | None
    axial_clearance_m: float
    static_fit: float
    data_quality: DataQuality | None


def evaluate(d: SeDesign, ds: Dataset, state: ThermalState) -> SeState:
    g, s = d.gland, d.seal
    mating = d.mating_material or d.groove_material
    k_seal, q1 = scale_factor_with_quality(ds.curve(d.jacket_material), state.T_seal_K, state.T_ref_K)
    k_gr, q2 = scale_factor_with_quality(ds.curve(d.groove_material), state.T_housing_K, state.T_ref_K)
    k_mt, q3 = scale_factor_with_quality(ds.curve(mating), state.mating_K, state.T_ref_K)
    qs = [q for q in (q1, q2, q3) if q is not None]
    h, b, d_static = s.free_height_m * k_seal, s.width_m * k_seal, s.static_diameter_m * k_seal
    width = g.groove_width_m * k_gr
    groove = g.groove_diameter_m * k_gr
    gap = None
    if g.kind == "face":
        L = g.groove_depth_m * k_gr
        L_min = L_max = L
        fit = ((d_static - groove) / d_static if g.pressure_direction == "internal"
               else (groove - d_static) / d_static)
    else:
        mate = g.mating_diameter_m * k_mt
        part = g.groove_part_diameter_m * k_gr
        if g.kind == "piston":
            L, c = (mate - groove) / 2, mate - part
            fit = (groove - d_static) / d_static
        else:
            L, c = (groove - mate) / 2, part - mate
            fit = (d_static - groove) / d_static
        if c < 0:
            raise ValueError("negative diametral clearance: parts interfere")
        e = c / 2 if g.eccentricity_m is None else g.eccentricity_m
        if e > c / 2 + 1e-15:
            raise ValueError("eccentricity exceeds half the diametral clearance")
        L_min, L_max, gap = L - e, L + e, c / 2 + e
    return SeState(L, L_min, L_max, h, h - L_max, h - L_min, gap, width - b, fit,
                   worst_quality(*qs) if qs else None)


def _limit(code: str, value: float, limit: float | None, too_low: bool, params: dict) -> CheckResult:
    if limit is None:
        return CheckResult(f"{code}_no_limit", Status.WARN, value, None, params,
                           DataQuality.PLACEHOLDER)
    bad = value < limit if too_low else value > limit
    return CheckResult(f"{code}_{'fail' if bad else 'ok'}", Status.FAIL if bad else Status.PASS,
                       value, limit, params | {"limit_mm": limit * 1e3}, DataQuality.USER_INPUT)


def check(d: SeDesign, st: SeState) -> list[CheckResult]:
    lim = d.limits
    out: list[CheckResult] = []
    if st.compression_min_m <= 0:
        out.append(CheckResult("se_no_contact", Status.FAIL, st.compression_min_m, 0.0,
                               {"value_mm": st.compression_min_m * 1e3}))
    out.append(_limit("se_compression_min", st.compression_min_m, lim.compression_min_m, True,
                      {"value_mm": st.compression_min_m * 1e3}))
    out.append(_limit("se_compression_max", st.compression_max_m, lim.compression_max_m, False,
                      {"value_mm": st.compression_max_m * 1e3}))
    if st.max_extrusion_gap_m is not None:
        out.append(_limit("se_gap", st.max_extrusion_gap_m, lim.extrusion_gap_max_m, False,
                          {"value_mm": st.max_extrusion_gap_m * 1e3}))
    ax_bad = st.axial_clearance_m < lim.axial_clearance_min_m
    out.append(CheckResult("se_axial_fail" if ax_bad else "se_axial_ok",
                           Status.FAIL if ax_bad else Status.PASS, st.axial_clearance_m,
                           lim.axial_clearance_min_m,
                           {"value_mm": st.axial_clearance_m * 1e3,
                            "limit_mm": lim.axial_clearance_min_m * 1e3}))
    p = {"fit": st.static_fit}
    if lim.static_fit_min is not None:
        bad = st.static_fit < lim.static_fit_min
        out.append(CheckResult("se_fit_fail" if bad else "se_fit_ok", Status.FAIL if bad else Status.PASS,
                               st.static_fit, lim.static_fit_min, p | {"limit": lim.static_fit_min},
                               DataQuality.USER_INPUT))
    elif st.static_fit < 0:
        out.append(CheckResult("se_fit_loose", Status.WARN, st.static_fit, 0.0, p))
    else:
        out.append(CheckResult("se_fit_seated", Status.PASS, st.static_fit, 0.0, p))
    if st.data_quality is not None and st.data_quality.needs_warning:
        out.append(CheckResult("thermal_data_quality", Status.WARN, st.data_quality.value,
                               params={"value": st.data_quality.value}, data_quality=st.data_quality))
    return out


@dataclass(frozen=True)
class SePoint:
    T_housing_K: float
    T_seal_K: float
    state: SeState | None
    results: tuple[CheckResult, ...]
    status: Status
    no_data: str | None


def se_sweep(d: SeDesign, ds: Dataset, T_housing_K, mode: str = "equilibrium",
             delta_T_K: float = 0.0, mating_delta_K: float = 0.0,
             T_ref_K: float = 293.15) -> list[SePoint]:
    pts = []
    for T in np.asarray(T_housing_K, dtype=float):
        state = ThermalState(float(T + (delta_T_K if mode == "lag" else 0.0)), float(T),
                             float(T + mating_delta_K), T_ref_K)
        try:
            st = evaluate(d, ds, state)
            res, reason = check(d, st), None
        except ThermalDataError as exc:
            st, res, reason = None, [], str(exc)
        status = overall_status(res) if res else Status.WARN
        pts.append(SePoint(float(T), state.T_seal_K, st, tuple(res), status, reason))
    return pts


def se_frame(points: list[SePoint]) -> pd.DataFrame:
    rows = []
    for p in points:
        s = p.state
        rows.append({
            "T_housing_K": p.T_housing_K, "T_seal_K": p.T_seal_K,
            "compression_min_m": s.compression_min_m if s else np.nan,
            "compression_max_m": s.compression_max_m if s else np.nan,
            "free_height_m": s.free_height_m if s else np.nan,
            "max_extrusion_gap_m": s.max_extrusion_gap_m if s and s.max_extrusion_gap_m is not None else np.nan,
            "axial_clearance_m": s.axial_clearance_m if s else np.nan,
            "static_fit": s.static_fit if s else np.nan,
            "status": p.status.value, "no_data": p.no_data,
        })
    return pd.DataFrame(rows)
