"""Design rule checks returning :class:`CheckResult` (SPEC §6.6-6.9, K20-K22).

Every check returns a status (PASS / WARN / FAIL), the evaluated value, the limit, a message
``code`` and ``params``. Display text is produced from ``i18n/tr.yaml`` under
``checks.<code>`` (K11); the core never produces Turkish text.

Rule sources are in ``data/design_rules.yaml`` and ``data/extrusion_limits.yaml``. A rule whose
limit is a placeholder (no value) produces WARN with code ``rule_missing``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gland_types import FaceGland, Gland, GlandState, ORing, PistonGland, RodGland, ThermalState
from .gland_types import evaluate as evaluate_gland
from .geometry import CsReductionMethod
from .loader import Dataset
from .models import DataQuality, ExtrusionLimits, RuleLimit, RuleSet, SealMaterial

PSI_TO_PA = 6894.757293168361
INCH_TO_M = 0.0254
SILICONE_IDS = frozenset({"vmq", "pvmq"})
HYDROGEN_FLUIDS = frozenset({"lh2"})


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    code: str
    status: Status
    value: Any = None
    limit: Any = None
    params: dict[str, Any] = field(default_factory=dict)
    data_quality: DataQuality | None = None


@dataclass(frozen=True)
class Design:
    """Everything needed to check one gland (dimensions at T_ref, SI units)."""

    gland: Gland
    oring: ORing
    seal_material: str
    groove_material: str
    mating_material: str | None = None  # None = same as groove material (K5)
    pressure_Pa: float = 0.0
    hardness_shore_a: float | None = None
    fluid: str | None = None
    cs_method: CsReductionMethod = "volume_centroid"
    swell: float = 0.0


def _sev(limit: RuleLimit) -> Status:
    return Status.FAIL if limit.severity == "fail" else Status.WARN


def _missing(name: str) -> CheckResult:
    return CheckResult("rule_missing", Status.WARN, params={"rule": name},
                       data_quality=DataQuality.PLACEHOLDER)


def _K_to_C(T: float) -> float:
    return T - 273.15


def rule_set_for(ds: Dataset, seal: SealMaterial, gland: Gland) -> RuleSet:
    gland_type = "static_face" if isinstance(gland, FaceGland) else "static_radial"
    return ds.rule_set(seal.group, gland_type)


# --------------------------------------------------------------------------- temperature


def check_temperature(seal: SealMaterial, T_seal_K: float, band_K: RuleLimit) -> list[CheckResult]:
    """K20: FAIL below the static low-temperature limit (or Tg), WARN within ``band_K`` above."""
    out: list[CheckResult] = []
    if seal.group == "elastomer":
        tr10 = seal.tr10_K
        if tr10 is not None and tr10.value is not None and band_K.value is not None:
            limit, quality = tr10.value - band_K.value, tr10.data_quality
        elif seal.low_temp_limit_K is not None and seal.low_temp_limit_K.value is not None:
            limit, quality = seal.low_temp_limit_K.value, seal.low_temp_limit_K.data_quality
        else:
            limit, quality = None, DataQuality.PLACEHOLDER
        p = {"T_K": T_seal_K, "T_C": _K_to_C(T_seal_K)}
        if limit is None:
            out.append(CheckResult("temp_low_unknown", Status.WARN, T_seal_K, None, p, quality))
        else:
            p |= {"limit_K": limit, "limit_C": _K_to_C(limit)}
            if T_seal_K < limit:
                out.append(CheckResult("temp_low_fail", Status.FAIL, T_seal_K, limit, p, quality))
            elif band_K.value is not None and T_seal_K < limit + band_K.value:
                p |= {"band_K": band_K.value}
                out.append(CheckResult("temp_low_band", Status.WARN, T_seal_K, limit, p, quality))
            else:
                out.append(CheckResult("temp_low_ok", Status.PASS, T_seal_K, limit, p, quality))
        tg = seal.tg_K
        if tg is not None and tg.value is not None and T_seal_K < tg.value:
            out.append(CheckResult("temp_glassy", Status.FAIL, T_seal_K, tg.value,
                                   {"T_K": T_seal_K, "tg_K": tg.value}, tg.data_quality))
    hi = seal.high_temp_limit_K
    p = {"T_K": T_seal_K, "T_C": _K_to_C(T_seal_K)}
    if hi is None or hi.value is None:
        out.append(CheckResult("temp_high_unknown", Status.WARN, T_seal_K, None, p,
                               DataQuality.PLACEHOLDER))
    else:
        p |= {"limit_K": hi.value, "limit_C": _K_to_C(hi.value)}
        status = Status.FAIL if T_seal_K > hi.value else Status.PASS
        code = "temp_high_fail" if status is Status.FAIL else "temp_high_ok"
        out.append(CheckResult(code, status, T_seal_K, hi.value, p, hi.data_quality))
    return out


# --------------------------------------------------------------------------- squeeze, fill, stretch


def check_squeeze(st: GlandState, rules: RuleSet, min_abs: RuleLimit, cs_ref_m: float) -> list[CheckResult]:
    out: list[CheckResult] = []
    p = {"squeeze_min": st.squeeze_min, "squeeze_max": st.squeeze_max,
         "squeeze_min_abs_mm": st.squeeze_min_abs_m * 1e3}
    if st.squeeze_min <= 0:
        out.append(CheckResult("squeeze_no_contact", Status.FAIL, st.squeeze_min, 0.0, p))
        return out
    if min_abs.value is None:
        out.append(_missing("squeeze_min_abs_m"))
    elif st.squeeze_min_abs_m < min_abs.value:
        out.append(CheckResult("squeeze_min_abs", _sev(min_abs), st.squeeze_min_abs_m,
                               min_abs.value, p | {"limit_mm": min_abs.value * 1e3},
                               min_abs.data_quality))
    if rules.squeeze_max is None or rules.squeeze_max.value is None:
        out.append(_missing("squeeze_max"))
    elif st.squeeze_max > rules.squeeze_max.value:
        out.append(CheckResult("squeeze_over_max", _sev(rules.squeeze_max), st.squeeze_max,
                               rules.squeeze_max.value, p | {"limit": rules.squeeze_max.value},
                               rules.squeeze_max.data_quality))
    rec = rules.recommended_squeeze
    band = rec.band_for(cs_ref_m) if rec is not None else None
    if band is None:
        out.append(CheckResult("squeeze_band_na", Status.WARN, (st.squeeze_min, st.squeeze_max),
                               None, p | {"cs_mm": cs_ref_m * 1e3}))
    else:
        q = rec.data_quality
        bp = p | {"band_min": band.min, "band_max": band.max}
        if st.squeeze_min < band.min:
            out.append(CheckResult("squeeze_below_band", Status.WARN, st.squeeze_min, band.min, bp, q))
        if st.squeeze_max > band.max:
            out.append(CheckResult("squeeze_above_band", Status.WARN, st.squeeze_max, band.max, bp, q))
        if band.min <= st.squeeze_min and st.squeeze_max <= band.max:
            out.append(CheckResult("squeeze_in_band", Status.PASS,
                                   (st.squeeze_min, st.squeeze_max), (band.min, band.max), bp, q))
    return out


def check_fill(st: GlandState, rules: RuleSet) -> list[CheckResult]:
    p = {"fill": st.fill}
    hard, hi, lo = rules.fill_hard_max, rules.fill_max, rules.fill_min
    if hard is None or hard.value is None:
        return [_missing("fill_hard_max")]
    if st.fill > hard.value:
        return [CheckResult("fill_over_hard_max", _sev(hard), st.fill, hard.value,
                            p | {"limit": hard.value}, hard.data_quality)]
    if hi is not None and hi.value is not None and st.fill > hi.value:
        return [CheckResult("fill_over_max", _sev(hi), st.fill, hi.value, p | {"limit": hi.value},
                            hi.data_quality)]
    if lo is not None and lo.value is not None and st.fill < lo.value:
        return [CheckResult("fill_under_min", _sev(lo), st.fill, lo.value, p | {"limit": lo.value},
                            lo.data_quality)]
    return [CheckResult("fill_ok", Status.PASS, st.fill, hard.value, p)]


def check_stretch(st: GlandState, rules: RuleSet, gland: Gland) -> list[CheckResult]:
    out: list[CheckResult] = []
    p = {"stretch": st.stretch}
    mx = rules.stretch_max
    if isinstance(gland, PistonGland) and st.stretch < 0:
        out.append(CheckResult("stretch_negative", Status.WARN, st.stretch, 0.0, p))
    if mx is None or mx.value is None:
        out.append(_missing("stretch_max"))
    elif st.stretch > mx.value:
        out.append(CheckResult("stretch_over_max", _sev(mx), st.stretch, mx.value,
                               p | {"limit": mx.value}, mx.data_quality))
    elif not out:
        out.append(CheckResult("stretch_ok", Status.PASS, st.stretch, mx.value, p | {"limit": mx.value}))
    return out


def check_rod_compression(st: GlandState, rules: RuleSet) -> list[CheckResult]:
    c = st.circumferential_compression
    p = {"compression": c}
    if c is None or c <= 0:
        return [CheckResult("circ_compression_ok", Status.PASS, c, None, p)]
    lim = rules.circumferential_compression_max
    if lim is None or lim.value is None:
        return [CheckResult("circ_compression_no_limit", Status.WARN, c, None, p,
                            DataQuality.PLACEHOLDER)]
    if c > lim.value:
        return [CheckResult("circ_compression_over_max", _sev(lim), c, lim.value,
                            p | {"limit": lim.value}, lim.data_quality)]
    return [CheckResult("circ_compression_ok", Status.PASS, c, lim.value, p)]


def check_face_seating(st: GlandState, rules: RuleSet, gland: FaceGland) -> list[CheckResult]:
    """Parker Design Chart 4-3: the ring must bear on the low-pressure-side groove wall.

    Internal pressure: groove O.D. = mean O-ring O.D., minus 1 % (max .060 in) -> O.D.
    compression 0..tol. External pressure: groove I.D. = mean ring I.D., plus 1 % (max .060
    in) -> I.D. stretch 0..tol.
    """
    rel, ab = rules.face_seating_tolerance_rel, rules.face_seating_tolerance_abs_m
    if rel is None or rel.value is None or ab is None or ab.value is None:
        return [_missing("face_seating_tolerance")]
    if gland.pressure_direction == "internal":
        ring_d = st.oring_id_m + 2 * st.cs_m
        value = st.circumferential_compression
        prefix = "face_internal"
    else:
        ring_d = st.oring_id_m
        value = st.stretch
        prefix = "face_external"
    tol = min(rel.value, ab.value / ring_d)
    p = {"value": value, "tol": tol}
    if value < 0:
        return [CheckResult(f"{prefix}_not_seated", _sev(rel), value, (0.0, tol), p, rel.data_quality)]
    if value > tol:
        return [CheckResult(f"{prefix}_over", _sev(rel), value, (0.0, tol), p, rel.data_quality)]
    return [CheckResult(f"{prefix}_ok", Status.PASS, value, (0.0, tol), p, rel.data_quality)]


# --------------------------------------------------------------------------- extrusion


def allowed_extrusion_gap_m(
    limits: ExtrusionLimits, pressure_Pa: float, hardness_shore_a: float, silicone: bool = False
) -> tuple[float | None, float | None]:
    """Allowed one-sided extrusion gap from Parker Fig. 3-2 (K21).

    Returns ``(allowed_gap_m, curve_hardness)``. ``allowed_gap_m`` is None when no curve
    applies (hardness below the softest curve). Interpolation is linear in clearance vs
    log10(pressure), matching the chart's logarithmic pressure axis. Below the lowest chart
    pressure the lowest-pressure value is used (conservative); above the curve's end the
    allowed gap is zero.
    """
    usable = [c for c in limits.curves if c.hardness_shore_a <= hardness_shore_a]
    if not usable:
        return None, None
    curve = max(usable, key=lambda c: c.hardness_shore_a)
    p_psi = max(pressure_Pa / PSI_TO_PA, 1e-12)
    pts = sorted(curve.points)
    lp = math.log10(p_psi)
    logs = [math.log10(p) for p, _ in pts]
    if lp <= logs[0]:
        clearance_in = pts[0][1]
    elif lp >= logs[-1]:
        clearance_in = pts[-1][1]
    else:
        for (l1, (_, c1)), (l2, (_, c2)) in zip(zip(logs, pts), zip(logs[1:], pts[1:])):
            if l1 <= lp <= l2:
                clearance_in = c1 + (c2 - c1) * (lp - l1) / (l2 - l1)
                break
    factor = limits.silicone_clearance_factor if silicone else 1.0
    return clearance_in * INCH_TO_M * factor, curve.hardness_shore_a


def check_extrusion(st: GlandState, design: Design, ds: Dataset, seal: SealMaterial) -> list[CheckResult]:
    out: list[CheckResult] = []
    bp = ds.common_rules.backup_ring_check_pressure_Pa
    if bp.value is not None and design.pressure_Pa > bp.value:
        out.append(CheckResult("backup_investigate", _sev(bp), design.pressure_Pa, bp.value,
                               {"p_bar": design.pressure_Pa / 1e5, "limit_bar": bp.value / 1e5},
                               bp.data_quality))
    if st.max_extrusion_gap_m is None:
        out.append(CheckResult("extrusion_no_gap", Status.PASS))
        return out
    if seal.group != "elastomer":
        out.append(CheckResult("extrusion_chart_na", Status.WARN))
        return out
    if design.hardness_shore_a is None:
        out.append(CheckResult("extrusion_no_hardness", Status.WARN))
        return out
    limits = ds.extrusion_limits
    allowed, curve_h = allowed_extrusion_gap_m(
        limits, design.pressure_Pa, design.hardness_shore_a, seal.id in SILICONE_IDS
    )
    gap = st.max_extrusion_gap_m
    p = {"gap_mm": gap * 1e3, "p_bar": design.pressure_Pa / 1e5, "hardness": design.hardness_shore_a}
    if allowed is None:
        out.append(CheckResult("extrusion_no_curve", Status.WARN, gap, None, p, limits.data_quality))
    elif gap > allowed:
        out.append(CheckResult("extrusion_fail", Status.FAIL, gap, allowed,
                               p | {"allowed_mm": allowed * 1e3, "curve": curve_h},
                               limits.data_quality))
    else:
        out.append(CheckResult("extrusion_ok", Status.PASS, gap, allowed,
                               p | {"allowed_mm": allowed * 1e3, "curve": curve_h},
                               limits.data_quality))
    return out


# --------------------------------------------------------------------------- materials, fluid


def check_housing(ds: Dataset, design: Design, state: ThermalState) -> list[CheckResult]:
    out: list[CheckResult] = []
    parts = [("groove", design.groove_material, state.T_housing_K)]
    mating = design.mating_material or design.groove_material
    if mating != design.groove_material or state.mating_K != state.T_housing_K:
        parts.append(("mating", mating, state.mating_K))
    for role, mid, T in parts:
        m = ds.housing_materials[mid]
        tough = m.cryo_toughness
        if tough is not None and tough.warning:
            thr = tough.threshold_K
            p = {"material": m.name, "role": role, "T_K": T}
            if thr.value is None:
                if T < state.T_ref_K:
                    out.append(CheckResult("cryo_toughness_unknown", Status.WARN, T, None, p,
                                           thr.data_quality))
            elif T < thr.value:
                out.append(CheckResult("cryo_toughness", Status.WARN, T, thr.value,
                                       p | {"limit_K": thr.value}, thr.data_quality))
        h2 = m.hydrogen_embrittlement
        if design.fluid in HYDROGEN_FLUIDS and h2 is not None and h2.value:
            out.append(CheckResult("hydrogen_embrittlement", Status.WARN, None, None,
                                   {"material": m.name, "role": role}, h2.data_quality))
    return out


def check_fluid(ds: Dataset, design: Design) -> list[CheckResult]:
    if design.fluid is None:
        return []
    fluid = ds.fluids[design.fluid]
    comp = fluid.compatibility_with(design.seal_material)
    p = {"fluid": fluid.name, "seal": ds.seal_materials[design.seal_material].name}
    status = {"ok": Status.PASS, "not_ok": Status.FAIL}.get(comp.status, Status.WARN)
    return [CheckResult(f"fluid_{comp.status}", status, comp.status, None, p, comp.data_quality)]


def check_thermoplastic(rules: RuleSet) -> list[CheckResult]:
    return [CheckResult(f"tp_{code}", Status.WARN) for code in rules.warnings]


def check_data_quality(st: GlandState) -> list[CheckResult]:
    if st.data_quality is not None and st.data_quality.needs_warning:
        return [CheckResult("thermal_data_quality", Status.WARN, st.data_quality.value,
                            params={"value": st.data_quality.value}, data_quality=st.data_quality)]
    return []


# --------------------------------------------------------------------------- driver


def run_checks(
    design: Design, ds: Dataset, state: ThermalState = ThermalState()
) -> tuple[GlandState, list[CheckResult]]:
    """Evaluate the gland at ``state`` and run all applicable checks."""
    seal = ds.seal_materials[design.seal_material]
    groove = ds.housing_materials[design.groove_material]
    mating = ds.housing_materials[design.mating_material or design.groove_material]
    st = evaluate_gland(
        design.gland,
        design.oring,
        ds.curve(seal.id),
        ds.curve(groove.id),
        ds.curve(mating.id),
        state,
        design.cs_method,
        design.swell,
    )
    rules = rule_set_for(ds, seal, design.gland)
    common = ds.common_rules
    results: list[CheckResult] = []
    results += check_temperature(seal, state.T_seal_K, common.low_temp_warning_band_K)
    results += check_squeeze(st, rules, common.squeeze_min_abs_m, design.oring.cs_m)
    results += check_fill(st, rules)
    results += check_stretch(st, rules, design.gland)
    if isinstance(design.gland, RodGland):
        results += check_rod_compression(st, rules)
    if isinstance(design.gland, FaceGland):
        results += check_face_seating(st, rules, design.gland)
    results += check_extrusion(st, design, ds, seal)
    if seal.group == "thermoplastic":
        results += check_thermoplastic(rules)
    results += check_housing(ds, design, state)
    results += check_fluid(ds, design)
    results += check_data_quality(st)
    return st, results


def overall_status(results: list[CheckResult]) -> Status:
    if any(r.status is Status.FAIL for r in results):
        return Status.FAIL
    if any(r.status is Status.WARN for r in results):
        return Status.WARN
    return Status.PASS
