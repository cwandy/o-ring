"""Standard O-ring size selection and gland dimension proposal (SPEC §8).

For every standard O-ring that fits the requested diameter and cross-section range, a gland
is designed and verified over the whole temperature range and at all tolerance corners
(worst-case, ``tolerance.worst_case``). Elastomers only; thermoplastic seals are Phase 7.

Procedure per candidate
-----------------------
1. Candidate window (at T_ref):
   * piston: the ring I.D. must be stretched onto the groove bottom by 0 .. stretch_max.
   * rod: the ring I.D. is stretched onto the rod by 0 .. stretch_max.
   * face, internal pressure: ring O.D. bears on the groove O.D. (given), O.D. compression
     0 .. min(1 %, .060 in) (Parker Design Chart 4-3); external: ring I.D. on the groove I.D.
     (given), I.D. stretch 0 .. min(1 %, .060 in).
2. Gland depth L: iterated so that the worst-case squeeze range (all temperatures and
   tolerance corners) is centred on the middle of Parker's recommended band for the
   cross-section. Update: L <- L + (mid - target) * W_nom (from squeeze = 1 - L/W).
3. Groove width: chosen so the nominal fill at T_ref is 75 % (Parker optimum) and the
   worst-case fill does not exceed the rule-set fill_max (85 %); the larger width wins.
4. Rounding: diameters to ``round_diameter_m`` (default 0.01 mm), width up to
   ``round_width_m`` (default 0.05 mm); the final verification uses the rounded values.
5. Score (lower is better): |squeeze mid - band mid| / band half-width + squeeze outside
   the band / half-width + fill outside 60-85 % per 5 % + 0.5 * |nominal fill - 75 %| / 10 %
   + 0.5 * max stretch / 5 % + (piston) negative stretch at any corner / 0.5 %. Ranking: worst status first (PASS < WARN < FAIL), then score.

Defaults that are engineering choices, not source data (all are inputs): machining
tolerance of diameters +/-0.025 mm, groove width +0.10/-0 mm, face groove depth
+/-0.025 mm. The diametral clearance defaults to Parker Design Chart 4-2 E for the
cross-section (maximum halved for silicone, chart note (c)); the groove radius to the
middle of the chart R band.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from .checks import Design, Status
from .gland_types import FaceGland, Gland, ORing, PistonGland, RodGland, ThermalState
from .loader import Dataset, load_standard_sizes
from .thermal import REFERENCE_T_K, ThermalDataError
from .tolerance import Tolerance, WorstCaseResult, worst_case

INCH = 0.0254
FILL_TARGET = 0.75
_RANK = {Status.PASS: 0, Status.WARN: 1, Status.FAIL: 2}


@dataclass(frozen=True)
class SelectorInput:
    gland_type: Literal["piston", "rod", "face"]
    nominal_diameter_m: float  # piston: bore; rod: rod; face: groove O.D. (internal) / I.D. (external)
    seal_material: str
    groove_material: str
    mating_material: str | None = None
    pressure_Pa: float = 0.0
    hardness_shore_a: float | None = 70.0
    fluid: str | None = None
    face_pressure_direction: Literal["internal", "external"] = "internal"
    T_min_K: float = REFERENCE_T_K
    T_max_K: float = REFERENCE_T_K
    T_ref_K: float = REFERENCE_T_K
    n_temperatures: int = 5
    lag_delta_K: float = 0.0  # extra states with T_seal = T_housing + lag_delta_K
    cs_min_m: float = 0.0
    cs_max_m: float = math.inf
    standards: tuple[str, ...] = ("AS568", "ISO3601-1 A", "ISO3601-1 G")
    nominal_tol_m: float = 0.025e-3  # +/- on the given diameter (bore / rod / face groove)
    diameter_tol_m: float = 0.025e-3  # +/- on machined diameters (groove, piston O.D., throat)
    width_tol_m: float = 0.10e-3  # +tol / -0 on the groove width
    depth_tol_m: float = 0.025e-3  # +/- on the face groove depth
    clearance_m: tuple[float, float] | None = None  # diametral (min, max); None = Parker chart
    swell: float = 0.0
    cs_method: str = "volume_centroid"
    round_diameter_m: float = 0.01e-3
    round_width_m: float = 0.05e-3
    max_candidates: int = 40


@dataclass
class Proposal:
    standard: str
    size: str
    ring: ORing
    ring_tol: tuple[float, float]  # (id_tol_m, cs_tol_m), symmetric
    design: Design
    tolerances: dict[str, Tolerance]
    depth_m: float
    width_m: float
    radius_m: float
    clearance_m: float | None
    wc: WorstCaseResult | None
    status: Status | None
    score: float
    score_parts: dict[str, float] = field(default_factory=dict)
    band: tuple[float, float] | None = None
    error: str | None = None


# --------------------------------------------------------------------------- helpers


def _round(x: float, step: float) -> float:
    return round(x / step) * step


def _round_up(x: float, step: float) -> float:
    return math.ceil(x / step - 1e-9) * step


def _states(inp: SelectorInput) -> list[ThermalState]:
    temps = sorted({*np.linspace(inp.T_min_K, inp.T_max_K, max(inp.n_temperatures, 2)).tolist(),
                    inp.T_ref_K} if inp.T_max_K > inp.T_min_K else {inp.T_min_K, inp.T_ref_K})
    states = [ThermalState(T, T, None, inp.T_ref_K) for T in temps]
    if inp.lag_delta_K:
        states += [ThermalState(T + inp.lag_delta_K, T, None, inp.T_ref_K) for T in temps]
    return states


def _clearance(inp: SelectorInput, ds: Dataset, cs_m: float) -> tuple[float, float] | None:
    if inp.gland_type == "face":
        return None
    if inp.clearance_m is not None:
        return inp.clearance_m
    seal = ds.seal_materials[inp.seal_material]
    gd = ds.rule_set(seal.group, "static_radial").gland_dimensions
    row = gd.row_for(cs_m) if gd else None
    if row is None or row.clearance_min_in is None:
        raise ValueError(f"no Parker clearance for CS {cs_m * 1e3:.2f} mm; enter the clearance")
    cmax = row.clearance_max_in * (0.5 if seal.id in ("vmq", "pvmq") else 1.0)
    return row.clearance_min_in * INCH, max(cmax, row.clearance_min_in) * INCH


def _radius(inp: SelectorInput, ds: Dataset, cs_m: float) -> float:
    seal = ds.seal_materials[inp.seal_material]
    gtype = "static_face" if inp.gland_type == "face" else "static_radial"
    gd = ds.rule_set(seal.group, gtype).gland_dimensions
    row = gd.row_for(cs_m) if gd else None
    if row is None or row.radius_min_in is None:
        return 0.0
    return (row.radius_min_in + row.radius_max_in) / 2 * INCH


def candidates(inp: SelectorInput, ds: Dataset, sizes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Standard sizes inside the cross-section range and the diameter window (see module doc)."""
    sizes = load_standard_sizes(ds.data_dir) if sizes is None else sizes
    seal = ds.seal_materials[inp.seal_material]
    rules = ds.rule_set(seal.group, "static_face" if inp.gland_type == "face" else "static_radial")
    smax = rules.stretch_max.value if rules.stretch_max and rules.stretch_max.value else 0.05
    df = sizes[sizes.standard.isin(inp.standards)
               & (sizes.cs_m >= inp.cs_min_m - 1e-9) & (sizes.cs_m <= inp.cs_max_m + 1e-9)].copy()
    D = inp.nominal_diameter_m
    if inp.gland_type == "piston":
        band_mid = df.cs_m.map(lambda c: _band_mid(rules, c))
        groove_est = D - 2 * df.cs_m * (1 - band_mid)
        ok = (df.id_m < groove_est) & (df.id_m >= groove_est / (1 + smax))
        key = (groove_est - df.id_m) / df.id_m
    elif inp.gland_type == "rod":
        ok = (df.id_m <= D) & (df.id_m >= D / (1 + smax))
        key = (D - df.id_m) / df.id_m
    else:
        tol = np.minimum(rules.face_seating_tolerance_rel.value,
                         rules.face_seating_tolerance_abs_m.value / D)
        if inp.face_pressure_direction == "internal":
            od = df.id_m + 2 * df.cs_m
            key = (od - D) / od
        else:
            key = (D - df.id_m) / df.id_m
        ok = (key >= 0) & (key <= tol)
    df["window_key"] = key
    df = df[ok].sort_values("window_key")
    return df.head(inp.max_candidates)


def _band(rules, cs_m: float):
    rec = rules.recommended_squeeze
    return rec.band_for(cs_m) if rec else None


def _band_mid(rules, cs_m: float) -> float:
    b = _band(rules, cs_m)
    return (b.min + b.max) / 2 if b else 0.20


# --------------------------------------------------------------------------- design of one gland


def _build(inp: SelectorInput, ring: ORing, ring_tol: tuple[float, float], L: float, W: float,
           R: float, c: tuple[float, float] | None) -> tuple[Design, dict[str, Tolerance]]:
    D = inp.nominal_diameter_m
    tn, td = Tolerance.symmetric(inp.nominal_tol_m), Tolerance.symmetric(inp.diameter_tol_m)
    tw = Tolerance(0.0, inp.width_tol_m)
    tols = {"oring.id_m": Tolerance.symmetric(ring_tol[0]), "oring.cs_m": Tolerance.symmetric(ring_tol[1])}
    gland: Gland
    if inp.gland_type == "piston":
        c_nom = (c[0] + c[1]) / 2
        gland = PistonGland(D, D - c_nom, D - 2 * L, W, R)
        tols |= {"gland.bore_diameter_m": tn, "gland.piston_diameter_m": td,
                 "gland.groove_diameter_m": td, "gland.groove_width_m": tw}
    elif inp.gland_type == "rod":
        c_nom = (c[0] + c[1]) / 2
        gland = RodGland(D, D + c_nom, D + 2 * L, W, R)
        tols |= {"gland.rod_diameter_m": tn, "gland.throat_diameter_m": td,
                 "gland.groove_diameter_m": td, "gland.groove_width_m": tw}
    else:
        if inp.face_pressure_direction == "internal":
            gland = FaceGland(D - 2 * W, D, L, "internal", R)
            tols |= {"gland.groove_od_m": tn, "gland.groove_id_m": td}
        else:
            gland = FaceGland(D, D + 2 * W, L, "external", R)
            tols |= {"gland.groove_id_m": tn, "gland.groove_od_m": td}
        tols |= {"gland.groove_depth_m": Tolerance.symmetric(inp.depth_tol_m)}
    design = Design(gland=gland, oring=ring, seal_material=inp.seal_material,
                    groove_material=inp.groove_material, mating_material=inp.mating_material,
                    pressure_Pa=inp.pressure_Pa, hardness_shore_a=inp.hardness_shore_a,
                    fluid=inp.fluid, cs_method=inp.cs_method, swell=inp.swell)
    return design, tols


def design_gland(inp: SelectorInput, ds: Dataset, row: pd.Series, iterations: int = 5) -> Proposal:
    seal = ds.seal_materials[inp.seal_material]
    rules = ds.rule_set(seal.group, "static_face" if inp.gland_type == "face" else "static_radial")
    ring = ORing(float(row.id_m), float(row.cs_m))
    ring_tol = (float(row.id_tol_m), float(row.cs_tol_m))
    band = _band(rules, ring.cs_m)
    target = _band_mid(rules, ring.cs_m)
    fill_max = rules.fill_max.value if rules.fill_max and rules.fill_max.value else 0.85
    c = _clearance(inp, ds, ring.cs_m)
    R = _radius(inp, ds, ring.cs_m)
    states = _states(inp)
    L = ring.cs_m * (1 - target)
    W = max(math.pi * ring.cs_m**2 / 4 / (L * FILL_TARGET), 2 * R + 1e-6)
    base = Proposal(row.standard, row["size"], ring, ring_tol, None, {}, L, W, R,
                    None if c is None else (c[0] + c[1]) / 2, None, None, math.inf,
                    band=(band.min, band.max) if band else None)
    try:
        for i in range(iterations + 1):
            last = i == iterations
            if last:  # rounding to practical values, then final verification
                if inp.gland_type == "piston":
                    L = (inp.nominal_diameter_m - _round(inp.nominal_diameter_m - 2 * L, inp.round_diameter_m)) / 2
                elif inp.gland_type == "rod":
                    L = (_round(inp.nominal_diameter_m + 2 * L, inp.round_diameter_m) - inp.nominal_diameter_m) / 2
                else:
                    L = _round(L, inp.round_diameter_m)
                W = _round_up(W, inp.round_width_m)
            design, tols = _build(inp, ring, ring_tol, L, W, R, c)
            wc = worst_case(design, tols, ds, states)
            if last:
                break
            lo, hi = wc.output_min["squeeze_min"], wc.output_max["squeeze_max"]
            nominal = wc.table[(wc.table.corner == "nominal")
                               & (wc.table.T_housing_K == inp.T_ref_K)
                               & (wc.table.T_seal_K == inp.T_ref_K)].iloc[0]
            L += ((lo + hi) / 2 - target) * ring.cs_m
            W_nom = W * nominal["fill"] / FILL_TARGET
            W_max = W * wc.output_max["fill"] / fill_max
            W = max(W_nom, W_max, 2 * R + 1e-6)
    except (ThermalDataError, ValueError) as exc:
        base.error = str(exc)
        return base

    base.design, base.tolerances, base.depth_m, base.width_m, base.wc = design, tols, L, W, wc
    base.status = max(wc.family_status.values(), key=lambda s: _RANK[s])
    base.score_parts = _score(wc, band, target, inp)
    base.score = sum(base.score_parts.values())
    return base


def _score(wc: WorstCaseResult, band, target: float, inp: SelectorInput) -> dict[str, float]:
    lo, hi = wc.output_min["squeeze_min"], wc.output_max["squeeze_max"]
    hw = (band.max - band.min) / 2 if band else 0.05
    parts = {"squeeze_centre": abs((lo + hi) / 2 - target) / hw}
    parts["squeeze_outside"] = ((max(0.0, band.min - lo) + max(0.0, hi - band.max)) / hw) if band else 0.0
    fmin, fmax = wc.output_min["fill"], wc.output_max["fill"]
    nom = wc.table[wc.table.corner == "nominal"]["fill"].mean()
    parts["fill"] = max(0.0, fmax - 0.85) / 0.05 + max(0.0, 0.60 - fmin) / 0.05 \
        + 0.5 * abs(nom - FILL_TARGET) / 0.10
    parts["stretch"] = 0.0 if inp.gland_type == "face" else 0.5 * max(wc.output_max["stretch"], 0.0) / 0.05
    if inp.gland_type == "piston":  # ring loose on the groove bottom at some corner
        parts["stretch_negative"] = max(0.0, -wc.output_min["stretch"]) / 0.005
    return parts


# --------------------------------------------------------------------------- driver


def select(inp: SelectorInput, ds: Dataset, sizes: pd.DataFrame | None = None) -> list[Proposal]:
    """Design and rank a gland for every candidate standard O-ring."""
    seal = ds.seal_materials[inp.seal_material]
    if seal.group != "elastomer":
        raise ValueError("size proposal is implemented for elastomers (thermoplastics: phase 7)")
    cands = candidates(inp, ds, sizes)
    props = [design_gland(inp, ds, row) for _, row in cands.iterrows()]
    ok = [p for p in props if p.error is None]
    bad = [p for p in props if p.error is not None]
    ok.sort(key=lambda p: (_RANK[p.status], p.score))
    return ok + bad


def proposal_table(props: list[Proposal]) -> pd.DataFrame:
    """Summary table (SI units) of ranked proposals."""
    rows = []
    for p in props:
        r = {"standard": p.standard, "size": p.size, "id_m": p.ring.id_m, "cs_m": p.ring.cs_m,
             "status": p.status.value if p.status else "NO_DATA", "score": p.score,
             "depth_m": p.depth_m, "width_m": p.width_m, "error": p.error}
        if p.wc is not None:
            r |= {"squeeze_lo": p.wc.output_min["squeeze_min"], "squeeze_hi": p.wc.output_max["squeeze_max"],
                  "fill_lo": p.wc.output_min["fill"], "fill_hi": p.wc.output_max["fill"],
                  "stretch_hi": p.wc.output_max["stretch"]}
        rows.append(r)
    return pd.DataFrame(rows)
