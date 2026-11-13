"""Thermal strain lookup and dimension scaling (SPEC §6.1, decisions K1, K2, K3, K13).

Definitions
-----------
eps(T) = (L_T - L_293.15) / L_293.15 is the integrated thermal strain referenced to
293.15 K. No constant CTE is used anywhere (SPEC §2.4).

Scaling (K1, exact, not an approximation)::

    L(T) = L_ref * (1 + eps(T)) / (1 + eps(T_ref))

because both L(T) and L_ref are related to the same L_293.15 by their own eps value. The
result does not depend on which reference temperature the table uses.

Re-referencing source tables
----------------------------
Sources publish strain relative to their own reference temperature T_s (e.g. 293 K for NIST
and NBS Monograph 29, 298.15 K for PTFE, which has a transition at about 20 C). With
e_s(T) = (L_T - L_Ts)/L_Ts the strain relative to 293.15 K is::

    eps(T) = (1 + e_s(T)) / (1 + e_s(293.15)) - 1

``e_s(293.15)`` is interpolated from the source data. Simplification: when 293.15 K lies
just outside a table that ends at T_s and |T_s - 293.15| <= 0.5 K (e.g. 7075-T6, last
point 293 K), T_s is treated as 293.15 K. The error is below 1e-5 strain, well inside the
source uncertainty.

Interpolation
-------------
PCHIP (shape-preserving piecewise cubic Hermite) through all points of all segments
(K13): it is monotone wherever the data are, so it does not overshoot across the PTFE
transitions as a cubic spline would. Between tabulated points the true curve is unknown;
for the PTFE transition region the table is dense (1 K steps) for that reason.

NIST ``nist_poly4`` fits are sampled at 1 K steps (plus the range ends, T_low and
293.15 K) and then treated like a table. Below T_low the NIST value is the constant f.
The published fits are not exactly continuous at T_low (e.g. Inconel 718: the polynomial at
20 K is 2.6e-7 below f); this source artefact is kept as published.

Out-of-range behaviour (K2)
---------------------------
Outside the data range :class:`OutOfRangeError` is raised. With
``allow_extrapolation=True`` the curve is continued linearly with its end slope and the
result is reported as ``extrapolated``. A material without data (K3) raises
:class:`NoThermalDataError`, except that scaling at exactly T = T_ref returns 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
from scipy.interpolate import PchipInterpolator

from .models import (
    DataQuality,
    NistPoly4Segment,
    TableSegment,
    ThermalStrainData,
    worst_quality,
)

REFERENCE_T_K = 293.15
REFERENCE_EQUIVALENCE_K = 0.5
_NIST_SAMPLE_STEP_K = 1.0
_T_EQUAL_TOL_K = 1e-9


class ThermalDataError(ValueError):
    """Base class for thermal data problems."""


class OutOfRangeError(ThermalDataError):
    """Requested temperature lies outside the material's data range."""


class NoThermalDataError(ThermalDataError):
    """The material has no sourced thermal strain data."""


@dataclass(frozen=True)
class _QualityBand:
    T_min_K: float
    T_max_K: float
    quality: DataQuality
    source: str | None


# --------------------------------------------------------------------------- building


def _nist_value(seg: NistPoly4Segment, T: np.ndarray) -> np.ndarray:
    c = seg.coefficients
    y = c["a"] + c["b"] * T + c["c"] * T**2 + c["d"] * T**3 + c["e"] * T**4
    if seg.T_low_K is not None:
        y = np.where(T < seg.T_low_K, seg.f, y)
    return y * seg.scale


def _segment_points(seg: TableSegment | NistPoly4Segment) -> tuple[np.ndarray, np.ndarray]:
    """Source-referenced strain e_s(T) for one segment."""
    if isinstance(seg, TableSegment):
        T = np.array([p[0] for p in seg.points], dtype=float)
        v = np.array([p[1] for p in seg.points], dtype=float) * seg.scale
        return T, (v if seg.quantity == "expansion" else -v)
    lo, hi = seg.range_K
    grid = set(np.arange(np.ceil(lo), np.floor(hi) + 1.0, _NIST_SAMPLE_STEP_K).tolist())
    grid |= {lo, hi}
    if seg.T_low_K is not None and lo <= seg.T_low_K <= hi:
        grid.add(float(seg.T_low_K))
    if lo <= REFERENCE_T_K <= hi:
        grid.add(REFERENCE_T_K)
    T = np.array(sorted(grid), dtype=float)
    return T, _nist_value(seg, T)


@dataclass(frozen=True)
class ThermalStrainCurve:
    """Thermal strain eps(T) referenced to 293.15 K, with per-range data quality."""

    name: str
    T_K: np.ndarray
    eps_values: np.ndarray
    bands: tuple[_QualityBand, ...]

    @property
    def has_data(self) -> bool:
        return self.T_K.size > 0

    @property
    def T_min_K(self) -> float:
        self._require_data()
        return float(self.T_K[0])

    @property
    def T_max_K(self) -> float:
        self._require_data()
        return float(self.T_K[-1])

    def _require_data(self) -> None:
        if not self.has_data:
            raise NoThermalDataError(
                f"{self.name}: kaynaklı termal büzülme verisi yok (no sourced thermal strain data)"
            )

    def quality_at(self, T_K: float) -> DataQuality:
        """Data quality at T. Gaps between segments take the weaker neighbouring quality."""
        self._require_data()
        for band in self.bands:
            if band.T_min_K <= T_K <= band.T_max_K:
                return band.quality
        below = [b for b in self.bands if b.T_max_K < T_K]
        above = [b for b in self.bands if b.T_min_K > T_K]
        if below and above:
            return worst_quality(below[-1].quality, above[0].quality)
        return DataQuality.EXTRAPOLATED  # outside the data range

    @cached_property
    def _interp(self) -> PchipInterpolator:
        return PchipInterpolator(self.T_K, self.eps_values, extrapolate=False)

    @cached_property
    def _dinterp(self):
        return self._interp.derivative()

    def eps(self, T_K, allow_extrapolation: bool = False):
        """eps(T) relative to 293.15 K. Accepts a scalar or an array."""
        self._require_data()
        T = np.asarray(T_K, dtype=float)
        lo, hi = self.T_min_K, self.T_max_K
        outside = (T < lo) | (T > hi)
        if np.any(outside) and not allow_extrapolation:
            bad = T[outside]
            raise OutOfRangeError(
                f"{self.name}: T = {bad.min() if bad.min() < lo else bad.max():.2f} K veri aralığı "
                f"dışında [{lo:.2f}, {hi:.2f}] K (outside data range)"
            )
        result = self._interp(np.clip(T, lo, hi))
        if np.any(outside):
            d = self._dinterp
            result = np.where(T < lo, self.eps_values[0] + d(lo) * (T - lo), result)
            result = np.where(T > hi, self.eps_values[-1] + d(hi) * (T - hi), result)
        return float(result) if result.ndim == 0 else result

    def eps_with_quality(self, T_K: float, allow_extrapolation: bool = False):
        return self.eps(T_K, allow_extrapolation), self.quality_at(T_K)


def build_curve(data: ThermalStrainData, name: str = "material") -> ThermalStrainCurve:
    """Merge the segments of ``data`` and re-reference them to 293.15 K (see module doc)."""
    if not data.segments:
        return ThermalStrainCurve(name, np.empty(0), np.empty(0), ())

    pieces = []
    for seg in data.segments:
        T, e = _segment_points(seg)
        pieces.append((T, e, seg))
    pieces.sort(key=lambda p: p[0][0])
    for (T1, _, _), (T2, _, _) in zip(pieces, pieces[1:]):
        if T2[0] <= T1[-1]:
            raise ThermalDataError(f"{name}: thermal strain segments overlap at {T2[0]} K")

    T = np.concatenate([p[0] for p in pieces])
    e_src = np.concatenate([p[1] for p in pieces])
    bands = [
        _QualityBand(float(p[0][0]), float(p[0][-1]), p[2].data_quality, p[2].source)
        for p in pieces
    ]

    if T[0] <= REFERENCE_T_K <= T[-1]:
        e_ref = float(PchipInterpolator(T, e_src)(REFERENCE_T_K))
        eps = (1.0 + e_src) / (1.0 + e_ref) - 1.0
    elif abs(data.reference_T_K - REFERENCE_T_K) <= REFERENCE_EQUIVALENCE_K and (
        np.isclose(T[-1], data.reference_T_K) or np.isclose(T[0], data.reference_T_K)
    ):
        idx = -1 if np.isclose(T[-1], data.reference_T_K) else 0
        T = T.copy()
        T[idx] = REFERENCE_T_K
        b = bands[idx]
        bands[idx] = _QualityBand(
            min(b.T_min_K, REFERENCE_T_K), max(b.T_max_K, REFERENCE_T_K), b.quality, b.source
        )
        eps = e_src
    else:
        raise ThermalDataError(
            f"{name}: cannot re-reference to {REFERENCE_T_K} K "
            f"(data range {T[0]}-{T[-1]} K, source reference {data.reference_T_K} K)"
        )
    return ThermalStrainCurve(name, T, eps, tuple(bands))


# --------------------------------------------------------------------------- public API


def eps_th(curve: ThermalStrainCurve, T_K, allow_extrapolation: bool = False):
    """Thermal strain relative to 293.15 K at ``T_K`` (scalar or array)."""
    return curve.eps(T_K, allow_extrapolation)


def scale_factor_with_quality(
    curve: ThermalStrainCurve,
    T_K: float,
    T_ref_K: float = REFERENCE_T_K,
    allow_extrapolation: bool = False,
) -> tuple[float, DataQuality | None]:
    """L(T)/L(T_ref) = (1 + eps(T)) / (1 + eps(T_ref)) and the weakest data quality used.

    At T == T_ref the factor is exactly 1 and no material data is used (quality ``None``),
    so this also works for materials without data (K3).
    """
    if abs(T_K - T_ref_K) < _T_EQUAL_TOL_K:
        return 1.0, None
    e_T, q_T = curve.eps_with_quality(T_K, allow_extrapolation)
    e_ref, q_ref = curve.eps_with_quality(T_ref_K, allow_extrapolation)
    return (1.0 + e_T) / (1.0 + e_ref), worst_quality(q_T, q_ref)


def scale_factor(
    curve: ThermalStrainCurve,
    T_K: float,
    T_ref_K: float = REFERENCE_T_K,
    allow_extrapolation: bool = False,
) -> float:
    return scale_factor_with_quality(curve, T_K, T_ref_K, allow_extrapolation)[0]


def scale_dimension(
    L_ref_m: float,
    curve: ThermalStrainCurve,
    T_K: float,
    T_ref_K: float = REFERENCE_T_K,
    allow_extrapolation: bool = False,
) -> float:
    """Dimension at ``T_K`` of a part whose size is ``L_ref_m`` at ``T_ref_K``.

    Assumes free (unconstrained) isotropic thermal strain of the part.
    """
    return L_ref_m * scale_factor(curve, T_K, T_ref_K, allow_extrapolation)
