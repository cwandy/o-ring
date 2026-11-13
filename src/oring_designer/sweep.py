"""Temperature sweep with separate seal and housing temperatures (SPEC §7, K2, K5).

Two modes:

* ``equilibrium``: T_seal = T_housing = T (mating part at T as well).
* ``lag``: T_seal = T_housing + delta_T_K (cool-down/warm-up transient; positive delta means
  the seal lags warmer than the housing). The mating part follows the housing plus
  ``mating_delta_K``.

At each point the gland is evaluated and checked (``checks.run_checks``). Where thermal data
are missing (outside a table range, or a material without data, K2/K3), the point is kept
with ``no_data`` set and only the seal temperature checks are run: a seal below its
low-temperature limit is therefore still reported as FAIL (SPEC §6.8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .checks import CheckResult, Design, Status, check_temperature, overall_status, run_checks
from .gland_types import GlandState, ThermalState
from .loader import Dataset
from .thermal import REFERENCE_T_K, ThermalDataError

SweepMode = Literal["equilibrium", "lag"]


@dataclass(frozen=True)
class SweepPoint:
    T_housing_K: float
    T_seal_K: float
    T_mating_K: float
    state: GlandState | None
    results: tuple[CheckResult, ...]
    status: Status
    no_data: str | None  # reason text (English, from the thermal error) or None


def temperatures(T_min_K: float, T_max_K: float, step_K: float) -> np.ndarray:
    """Inclusive grid from T_min to T_max."""
    if step_K <= 0 or T_max_K < T_min_K:
        raise ValueError("invalid temperature grid")
    n = int(np.floor((T_max_K - T_min_K) / step_K + 1e-9)) + 1
    grid = T_min_K + step_K * np.arange(n)
    if grid[-1] < T_max_K - 1e-9:
        grid = np.append(grid, T_max_K)
    return grid


def sweep(
    design: Design,
    ds: Dataset,
    T_housing_K: np.ndarray,
    mode: SweepMode = "equilibrium",
    delta_T_K: float = 0.0,
    mating_delta_K: float = 0.0,
    T_ref_K: float = REFERENCE_T_K,
) -> list[SweepPoint]:
    """Evaluate ``design`` over a grid of housing temperatures."""
    seal = ds.seal_materials[design.seal_material]
    band = ds.common_rules.low_temp_warning_band_K
    d_seal = delta_T_K if mode == "lag" else 0.0
    points: list[SweepPoint] = []
    for T in np.asarray(T_housing_K, dtype=float):
        state = ThermalState(
            T_seal_K=float(T + d_seal),
            T_housing_K=float(T),
            T_mating_K=float(T + mating_delta_K),
            T_ref_K=T_ref_K,
        )
        try:
            gs, results = run_checks(design, ds, state)
            reason = None
        except ThermalDataError as exc:
            gs, results, reason = None, check_temperature(seal, state.T_seal_K, band), str(exc)
        status = overall_status(results)
        points.append(
            SweepPoint(float(T), state.T_seal_K, state.mating_K, gs, tuple(results), status, reason)
        )
    return points


def to_frame(points: list[SweepPoint]) -> pd.DataFrame:
    """One row per temperature; geometry columns are NaN where data are missing."""
    rows = []
    for p in points:
        s = p.state
        rows.append(
            {
                "T_housing_K": p.T_housing_K,
                "T_seal_K": p.T_seal_K,
                "T_mating_K": p.T_mating_K,
                "squeeze_min": s.squeeze_min if s else np.nan,
                "squeeze_nominal": s.squeeze_nominal if s else np.nan,
                "squeeze_max": s.squeeze_max if s else np.nan,
                "fill": s.fill if s else np.nan,
                "stretch": s.stretch if s else np.nan,
                "cs_eff_m": s.cs_eff_m if s else np.nan,
                "depth_nominal_m": s.depth_nominal_m if s else np.nan,
                "diametral_clearance_m": (
                    s.diametral_clearance_m if s and s.diametral_clearance_m is not None else np.nan
                ),
                "max_extrusion_gap_m": (
                    s.max_extrusion_gap_m if s and s.max_extrusion_gap_m is not None else np.nan
                ),
                "allowed_gap_m": _allowed_gap(p.results),
                "data_quality": s.data_quality.value if s and s.data_quality else None,
                "status": p.status.value,
                "no_data": p.no_data,
            }
        )
    return pd.DataFrame(rows)


def _allowed_gap(results: tuple[CheckResult, ...]) -> float:
    for r in results:
        if r.code in ("extrusion_ok", "extrusion_fail") and r.limit is not None:
            return float(r.limit)
    return np.nan


_FAMILIES = (
    "temp_low", "temp_high", "temp_glassy", "squeeze", "fill", "stretch", "circ_compression",
    "face_internal", "face_external", "backup", "extrusion", "cryo_toughness", "hydrogen",
    "fluid", "tp_", "thermal_data_quality", "rule_missing",
)


def check_family(result: CheckResult) -> str:
    """Group related codes (e.g. squeeze_in_band / squeeze_below_band -> squeeze)."""
    for fam in _FAMILIES:
        if result.code.startswith(fam):
            if fam == "rule_missing":
                return f"rule_missing:{result.params.get('rule')}"
            if fam in ("tp_", "cryo_toughness", "hydrogen"):
                return result.code + str(result.params.get("material", ""))
            return fam
    return result.code


def severity_key(result: CheckResult) -> tuple[int, float]:
    """Ordering key: status first, then the distance to the limit.

    For WARN/FAIL the occurrence furthest past the limit is the most severe (e.g. the largest
    extrusion gap); for PASS the occurrence closest to its limit (smallest margin).
    """
    rank = {Status.PASS: 0, Status.WARN: 1, Status.FAIL: 2}[result.status]
    excess = 0.0
    if isinstance(result.value, (int, float)) and isinstance(result.limit, (int, float)):
        margin = abs(float(result.value) - float(result.limit))
        # violations: further past the limit is worse; passes: closer to the limit is worse
        excess = margin if result.status is not Status.PASS else -margin
    return rank, excess


@dataclass(frozen=True)
class WorstCase:
    family: str
    result: CheckResult
    T_housing_K: float
    T_seal_K: float


def worst_by_family(points: list[SweepPoint]) -> list[WorstCase]:
    """Most severe result of each check family over the sweep (first occurrence wins ties)."""
    rank = {Status.PASS: 0, Status.WARN: 1, Status.FAIL: 2}
    worst: dict[str, WorstCase] = {}
    for p in points:
        for r in p.results:
            fam = check_family(r)
            cur = worst.get(fam)
            if cur is None or severity_key(r) > severity_key(cur.result):
                worst[fam] = WorstCase(fam, r, p.T_housing_K, p.T_seal_K)
    return sorted(worst.values(), key=lambda w: -rank[w.result.status])


def summary_status(points: list[SweepPoint]) -> Status:
    return overall_status([CheckResult("_", p.status) for p in points])
