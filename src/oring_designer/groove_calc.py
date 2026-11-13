"""Groove calculator: groove depth, width and tolerances from material, cross-section,
temperature range and pressure (the inverse of the gland check).

Method
------
The groove profile is designed for a gland of very large diameter (``D_SYN`` = 1 m), where
curvature does not matter, and checked with the full model (``tolerance.worst_case`` over
the temperature range x tolerance corners, ``checks.run_checks``):

1. Target squeeze band: Parker Design Chart 4-2 (radial) / 4-3 (face) band of the nearest
   cross-section (elastomers), or the user's band (required for thermoplastics, no source).
2. Gland depth L: bisection so that the worst-case squeeze range over all temperatures and
   corners (cross-section tolerance, depth tolerance, clearance band) is centred on the
   target band. Rounded to ``round_depth_m``.
3. Groove width: minimum width = width at which the worst-case fill equals the fill limit
   (fill is proportional to 1/width); recommended width = the larger of the minimum and the
   width giving 75 % nominal fill at T_ref (Parker optimum). Rounded up to ``round_width_m``.
4. Radial glands: diametral clearance band = Parker Design Chart 4-2 E (max halved for
   silicone), its maximum capped by the extrusion limit at the pressure and hardness (full
   eccentricity: one-sided gap = clearance). If even the minimum E exceeds the extrusion
   limit, the extrusion check fails and a back-up ring is required.

Defaults taken from Parker Design Charts (nearest cross-section row): depth tolerance =
half the tabulated L range, width tolerance = tabulated G range (+tol / -0), corner radius
= middle of the R range. Cross-section tolerance = AS568 / ISO 3601-1 value of the matching
standard cross-section. All of these can be overridden.

Simplifications: groove part and mating part are of the same housing material at the same
temperature; for radial glands the ring is installed with the given I.D. stretch (default
0) and full eccentricity is assumed; face glands assume metal-to-metal contact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Literal

import numpy as np
import pandas as pd

from .checks import Design, Status, allowed_extrusion_gap_m
from .gland_types import FaceGland, ORing, PistonGland, ThermalState
from .loader import Dataset, load_standard_sizes
from .thermal import REFERENCE_T_K, scale_factor
from .tolerance import Tolerance, WorstCaseResult, worst_case

D_SYN = 1.0  # m, reference diameter of the synthetic gland
INCH = 0.0254
FILL_TARGET = 0.75
_RANK = {Status.PASS: 0, Status.WARN: 1, Status.FAIL: 2}


@dataclass(frozen=True)
class GrooveInput:
    seal_material: str
    cs_m: float
    gland: Literal["face", "radial"] = "face"
    T_min_K: float = REFERENCE_T_K
    T_max_K: float = REFERENCE_T_K
    T_ref_K: float = REFERENCE_T_K
    pressure_Pa: float = 0.0
    hardness_shore_a: float | None = 70.0
    housing_material: str = "ss304"
    fluid: str | None = None
    face_direction: Literal["internal", "external"] = "internal"
    cs_tol_m: float | None = None  # None: from the standard size tables
    target_squeeze: tuple[float, float] | None = None  # None: Parker band (elastomers)
    fill_limit: float | None = None  # None: rule set fill_max
    depth_tol_m: float | None = None  # None: Parker chart
    width_tol_m: float | None = None  # None: Parker chart
    radius_m: float | None = None  # None: Parker chart
    clearance_m: tuple[float, float] | None = None  # radial; None: Parker chart + extrusion limit
    install_stretch: float = 0.0  # radial: I.D. stretch on the groove bottom
    swell: float = 0.0
    n_temperatures: int = 9
    cs_method: str = "volume_centroid"
    round_depth_m: float = 0.01e-3
    round_width_m: float = 0.05e-3


@dataclass
class GrooveResult:
    inp: GrooveInput
    design: Design  # synthetic gland (D = 1 m) at the solved dimensions
    tolerances: dict[str, Tolerance]
    depth_m: float  # gland depth L (face: groove depth)
    depth_tol_m: float
    machine_depth_m: float  # radial: groove depth from the groove-part surface (L - c/2)
    width_min_m: float
    width_m: float  # recommended, nominal
    width_tol_m: float  # +tol / -0
    radius_m: float
    cs_tol_m: float
    clearance_m: tuple[float, float] | None
    allowed_gap_m: float | None
    target: tuple[float, float]
    fill_limit: float
    wc: WorstCaseResult
    per_temperature: pd.DataFrame
    status: Status
    parker_ref: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def squeeze_range(self) -> tuple[float, float]:
        return self.wc.output_min["squeeze_min"], self.wc.output_max["squeeze_max"]

    @property
    def fill_max(self) -> float:
        return self.wc.output_max["fill"]

    def nominal_at(self, T_K: float) -> pd.Series:
        df = self.wc.table
        rows = df[(df.corner == "nominal") & np.isclose(df.T_housing_K, T_K)]
        return rows.iloc[0]


# --------------------------------------------------------------------------- defaults from data


def _rules(ds: Dataset, inp: GrooveInput):
    seal = ds.seal_materials[inp.seal_material]
    return seal, ds.rule_set(seal.group, "static_face" if inp.gland == "face" else "static_radial")


def _parker_row(ds: Dataset, inp: GrooveInput):
    """Nearest Parker chart row (elastomer rule set; thermoplastics use the same geometry)."""
    rs = ds.rule_set("elastomer", "static_face" if inp.gland == "face" else "static_radial")
    gd = rs.gland_dimensions
    row = gd.row_for(inp.cs_m, tol_in=1.0) if gd else None
    exact = gd.row_for(inp.cs_m) is not None if gd else False
    return row, exact


def _cs_tolerance(inp: GrooveInput, ds: Dataset) -> tuple[float, str | None]:
    if inp.cs_tol_m is not None:
        return inp.cs_tol_m, None
    sizes = load_standard_sizes(ds.data_dir)
    match = sizes[np.isclose(sizes.cs_m, inp.cs_m, atol=0.005e-3)]
    if match.empty:
        return 0.0, "cs_tol_unknown"
    return float(match.cs_tol_m.max()), None


def _band(ds: Dataset, inp: GrooveInput, rules) -> tuple[float, float]:
    if inp.target_squeeze is not None:
        lo, hi = inp.target_squeeze
        if not 0 < lo < hi < 1:
            raise ValueError("target squeeze must satisfy 0 < min < max < 1")
        return lo, hi
    rec = rules.recommended_squeeze
    if rec is None:
        raise ValueError("no recommended squeeze band for this material: enter the target squeeze")
    b = min(rec.bands, key=lambda b: abs(b.cs_nominal_in - inp.cs_m / INCH))
    return b.min, b.max


# --------------------------------------------------------------------------- synthetic design


def _design(inp: GrooveInput, L: float, G: float, R: float, c_nom: float | None) -> Design:
    W = inp.cs_m
    if inp.gland == "face":
        if inp.face_direction == "internal":
            god, gid = D_SYN, D_SYN - 2 * G
            ring_id = god - 2 * W  # ring O.D. on the groove O.D.
        else:
            gid, god = D_SYN, D_SYN + 2 * G
            ring_id = gid
        gland = FaceGland(gid, god, L, inp.face_direction, R)
    else:
        groove = D_SYN - 2 * L
        gland = PistonGland(D_SYN, D_SYN - c_nom, groove, G, R)
        ring_id = groove / (1 + inp.install_stretch)
    return Design(gland=gland, oring=ORing(ring_id, W), seal_material=inp.seal_material,
                  groove_material=inp.housing_material, pressure_Pa=inp.pressure_Pa,
                  hardness_shore_a=inp.hardness_shore_a, fluid=inp.fluid, cs_method=inp.cs_method,
                  swell=inp.swell)


def _tolerances(inp: GrooveInput, cs_tol: float, depth_tol: float, width_tol: float,
                c: tuple[float, float] | None) -> dict[str, Tolerance]:
    tols = {"oring.cs_m": Tolerance.symmetric(cs_tol)}
    if inp.gland == "face":
        tols["gland.groove_depth_m"] = Tolerance.symmetric(depth_tol)
        if inp.face_direction == "internal":
            tols["gland.groove_id_m"] = Tolerance(-2 * width_tol, 0.0)  # width +tol / -0
        else:
            tols["gland.groove_od_m"] = Tolerance(0.0, 2 * width_tol)
    else:
        tols["gland.groove_diameter_m"] = Tolerance.symmetric(2 * depth_tol)
        tols["gland.piston_diameter_m"] = Tolerance.symmetric((c[1] - c[0]) / 2)
        tols["gland.groove_width_m"] = Tolerance(0.0, width_tol)
    return {k: v for k, v in tols.items() if v.lower_m != 0 or v.upper_m != 0}


def _states(inp: GrooveInput) -> list[ThermalState]:
    lo, hi = min(inp.T_min_K, inp.T_max_K), max(inp.T_min_K, inp.T_max_K)
    temps = sorted({*np.linspace(lo, hi, max(inp.n_temperatures, 2)).round(6).tolist(), inp.T_ref_K})
    return [ThermalState(T, T, None, inp.T_ref_K) for T in temps]


# --------------------------------------------------------------------------- solver


class TemperatureRangeError(ValueError):
    """The requested temperatures are outside the thermal data of the materials."""

    def __init__(self, usable: tuple[float, float] | None, materials: list[str]):
        self.usable, self.materials = usable, materials
        rng = "none" if usable is None else f"{usable[0]:.2f}-{usable[1]:.2f} K"
        super().__init__(f"temperatures outside thermal data of {materials}; usable range: {rng}")


def usable_range(ds: Dataset, seal_material: str, housing_material: str) -> tuple[float, float] | None:
    """Temperature range covered by the thermal data of both materials (None: no data)."""
    cs, ch = ds.curve(seal_material), ds.curve(housing_material)
    if not (cs.has_data and ch.has_data):
        return None
    lo, hi = max(cs.T_min_K, ch.T_min_K), min(cs.T_max_K, ch.T_max_K)
    return (lo, hi) if lo <= hi else None


def calculate(inp: GrooveInput, ds: Dataset) -> GrooveResult:
    if inp.cs_m <= 0:
        raise ValueError("cross-section must be > 0")
    temps = {inp.T_min_K, inp.T_max_K}
    if temps != {inp.T_ref_K}:
        rng = usable_range(ds, inp.seal_material, inp.housing_material)
        if rng is None or min(temps) < rng[0] - 1e-9 or max(temps) > rng[1] + 1e-9:
            raise TemperatureRangeError(rng, [inp.seal_material, inp.housing_material])
    seal, rules = _rules(ds, inp)
    target = _band(ds, inp, rules)
    mid = sum(target) / 2
    fill_limit = inp.fill_limit or (rules.fill_max.value if rules.fill_max and rules.fill_max.value
                                    else 0.85)
    row, exact = _parker_row(ds, inp)
    notes: list[str] = []
    if not exact:
        notes.append("parker_row_nearest")
    cs_tol, note = _cs_tolerance(inp, ds)
    if note:
        notes.append(note)
    depth_tol = inp.depth_tol_m if inp.depth_tol_m is not None else (
        (row.depth_max_in - row.depth_min_in) / 2 * INCH)
    width_tol = inp.width_tol_m if inp.width_tol_m is not None else (
        (row.width_max_in - row.width_min_in) * INCH)
    R = inp.radius_m if inp.radius_m is not None else (row.radius_min_in + row.radius_max_in) / 2 * INCH
    parker = {"depth_min_m": row.depth_min_in * INCH, "depth_max_m": row.depth_max_in * INCH,
              "width_min_m": row.width_min_in * INCH, "width_max_m": row.width_max_in * INCH,
              "cs_nominal_m": row.cs_nominal_in * INCH,
              "radius_min_m": row.radius_min_in * INCH, "radius_max_m": row.radius_max_in * INCH}

    c, allowed = None, None
    if inp.gland == "radial":
        if inp.hardness_shore_a is not None and seal.group == "elastomer":
            allowed, _ = allowed_extrusion_gap_m(ds.extrusion_limits, inp.pressure_Pa,
                                                 inp.hardness_shore_a, seal.id in ("vmq", "pvmq"))
        if inp.clearance_m is not None:
            c = inp.clearance_m
        else:
            cmin = row.clearance_min_in * INCH
            cmax = row.clearance_max_in * INCH * (0.5 if seal.id in ("vmq", "pvmq") else 1.0)
            cmax = max(cmax, cmin)
            if allowed is not None and allowed < cmax:
                cmax = max(allowed, cmin)
                if allowed < cmin:
                    notes.append("backup_ring_required")
            c = (cmin, cmax)
        parker |= {"clearance_min_m": row.clearance_min_in * INCH,
                   "clearance_max_m": row.clearance_max_in * INCH}
    c_nom = None if c is None else (c[0] + c[1]) / 2

    states = _states(inp)
    W = inp.cs_m
    tols = _tolerances(inp, cs_tol, depth_tol, width_tol, c)

    def evaluate(L: float, G: float) -> WorstCaseResult:
        return worst_case(_design(inp, L, G, R, c_nom), tols, ds, states)

    # 2. depth by bisection on the squeeze mid-point (decreasing in L)
    G0 = max(1.6 * W, 2 * R + 1e-6)
    lo_L, hi_L = 0.30 * W, 0.995 * W
    for _ in range(40):
        L = (lo_L + hi_L) / 2
        wc = evaluate(L, G0)
        m = (wc.output_min["squeeze_min"] + wc.output_max["squeeze_max"]) / 2
        if m > mid:
            lo_L = L
        else:
            hi_L = L
    L = round(((lo_L + hi_L) / 2) / inp.round_depth_m) * inp.round_depth_m

    # 3. width from fill (fill ~ 1/width)
    wc = evaluate(L, G0)
    nominal_ref = wc.table[(wc.table.corner == "nominal") & np.isclose(wc.table.T_housing_K, inp.T_ref_K)].iloc[0]
    G_min = G0 * wc.output_max["fill"] / fill_limit
    G_rec = max(G_min, G0 * nominal_ref["fill"] / FILL_TARGET, 2 * R + 1e-6)
    G_min = math.ceil(G_min / inp.round_width_m - 1e-9) * inp.round_width_m
    G_rec = math.ceil(G_rec / inp.round_width_m - 1e-9) * inp.round_width_m
    wc = evaluate(L, G_rec)

    status = max(wc.family_status.values(), key=lambda s: _RANK[s])
    per_T = _per_temperature(inp, ds, wc)
    return GrooveResult(
        inp=inp, design=_design(inp, L, G_rec, R, c_nom), tolerances=tols, depth_m=L,
        depth_tol_m=depth_tol, machine_depth_m=L - (c_nom / 2 if c_nom else 0.0),
        width_min_m=G_min, width_m=G_rec, width_tol_m=width_tol, radius_m=R, cs_tol_m=cs_tol,
        clearance_m=c, allowed_gap_m=allowed, target=target, fill_limit=fill_limit, wc=wc,
        per_temperature=per_T, status=status, parker_ref=parker, notes=notes,
    )


def _per_temperature(inp: GrooveInput, ds: Dataset, wc: WorstCaseResult) -> pd.DataFrame:
    """Per temperature: tolerance envelope and nominal values, ring/gland scaled sizes."""
    df = wc.table
    seal_c, house_c = ds.curve(inp.seal_material), ds.curve(inp.housing_material)
    rows = []
    for T, g in df.groupby("T_housing_K"):
        nom = g[g.corner == "nominal"].iloc[0]
        ks = scale_factor(seal_c, T, inp.T_ref_K)
        kh = scale_factor(house_c, T, inp.T_ref_K)
        rows.append({
            "T_K": T,
            "squeeze_lo": g.squeeze_min.min(), "squeeze_hi": g.squeeze_max.max(),
            "squeeze_nominal": (nom.squeeze_min + nom.squeeze_max) / 2,
            "fill_max": g.fill.max(), "fill_nominal": nom.fill,
            "cs_m": inp.cs_m * ks, "volume_change": ks**3 - 1.0, "housing_scale": kh,
            "gap_max_m": g.max_extrusion_gap_m.max(),
        })
    return pd.DataFrame(rows)
