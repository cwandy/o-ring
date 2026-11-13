"""Single-temperature gland geometry: stretch, cross-section reduction, squeeze, gland fill,
clearance and eccentricity (SPEC §6.2-6.5). All lengths in metres, results as fractions.

Formulas and sources
--------------------
Stretch (SPEC §6.2, Parker ORD 5700 3.5)::

    stretch = (D_contact - ID) / ID

D_contact is the diameter the O-ring I.D. sits on (piston: groove bottom; rod: rod; face,
external pressure: groove I.D.). Negative stretch means the ring is not stretched.

Cross-section reduction due to stretch (SPEC §6.3), selectable ``method``:

* ``"volume_centroid"`` (default, decision K14): torus volume pi^2/4 * D_c * W^2 is
  conserved, with centroid diameters D_c = ID + W before and D_c' = D_contact + W' after
  installation. Solved exactly: W'^2 (D_contact + W') = W^2 (ID + W).
* ``"volume_id"``: Parker's "calculated" curve (Fig. 3-3), same assumption but with the
  I.D. stretch X used as centroid stretch: Y = 100 (1 - 10 / sqrt(100 + X)).
* ``"parker_observed"``: Parker's empirical "observed" curve (Fig. 3-3, GM data), X = I.D.
  stretch in percent, Y = percent reduction of the compression diameter::

      0 <= X <= 3 : Y = -0.005 + 1.19X - 0.19X^2 - 0.001X^3 + 0.008X^4
      3 <  X <= 25: Y = 0.56 + 0.59X - 0.0046X^2

  Notes: Y(0) = -0.005 is clamped to 0; the two branches differ by 0.19 points at X = 3
  (2.476 vs 2.290); X > 25 % is outside the published range and raises an error.

No reduction is applied for X <= 0 (compressed ring); the small increase of the
cross-section of a circumferentially compressed ring is neglected.

Squeeze (SPEC §6.4)::

    squeeze = (W_eff - L) / W_eff

L is the gland depth: for radial glands the radial distance from groove bottom to the
mating surface (Parker Design Chart 4-2, "L gland depth"), for face glands the groove depth
(metal-to-metal contact assumed, Parker Design Chart 4-3 note).

Eccentricity: with radial offset e between groove part and mating part the gland depth
varies between L_nom - e and L_nom + e around the circumference, and the one-sided
extrusion gap between c/2 - e and c/2 + e (c = diametral clearance). Full eccentricity
(e = c/2) is the default worst case: all clearance on one side (decision K15).

Gland fill (SPEC §6.5)::

    fill = A_oring * (1 + swell) / A_gland,   A_oring = pi W_eff^2 / 4

A_gland = L * groove width - corner deduction. The gland is taken as a rectangle (groove
wall to wall, groove bottom to mating surface); optional groove bottom radii r reduce the
area by (1 - pi/4) r^2 per corner (two bottom corners). Simplifications: volumetric swell is
applied to the area only (decision A5); the deformed O-ring shape is not modelled.
"""

from __future__ import annotations

import math
from typing import Literal

CsReductionMethod = Literal["volume_centroid", "volume_id", "parker_observed"]
PARKER_OBSERVED_MAX_STRETCH_PCT = 25.0


class GeometryError(ValueError):
    """Invalid geometry input or a formula used outside its range."""


def _positive(**values: float) -> None:
    for name, value in values.items():
        if not value > 0:
            raise GeometryError(f"{name} must be > 0 (got {value})")


# --------------------------------------------------------------------------- stretch


def stretch(contact_diameter_m: float, oring_id_m: float) -> float:
    """(D_contact - ID) / ID. Negative when the ring is not stretched."""
    _positive(contact_diameter_m=contact_diameter_m, oring_id_m=oring_id_m)
    return (contact_diameter_m - oring_id_m) / oring_id_m


def circumferential_compression(oring_od_m: float, groove_od_m: float) -> float:
    """(OD - D_groove_outer) / OD: how much the O-ring O.D. is compressed by the groove O.D.

    Positive means the ring O.D. is forced smaller (rod glands, face glands under internal
    pressure). Negative means the O.D. does not touch the groove outer wall.
    """
    _positive(oring_od_m=oring_od_m, groove_od_m=groove_od_m)
    return (oring_od_m - groove_od_m) / oring_od_m


# --------------------------------------------------------------------------- cross-section


def parker_observed_reduction(stretch_fraction: float) -> float:
    """Parker Fig. 3-3 empirical curve. Returns the fractional reduction of W."""
    X = stretch_fraction * 100.0
    if X <= 0.0:
        return 0.0
    if X > PARKER_OBSERVED_MAX_STRETCH_PCT:
        raise GeometryError(
            f"stretch {X:.2f} % outside Parker empirical range (0-25 %)"
        )
    if X <= 3.0:
        Y = -0.005 + 1.19 * X - 0.19 * X**2 - 0.001 * X**3 + 0.008 * X**4
    else:
        Y = 0.56 + 0.59 * X - 0.0046 * X**2
    return max(Y, 0.0) / 100.0


def volume_id_reduction(stretch_fraction: float) -> float:
    """Parker Fig. 3-3 'calculated' curve: Y = 1 - 1/sqrt(1 + X) with X the I.D. stretch."""
    if stretch_fraction <= 0.0:
        return 0.0
    return 1.0 - 1.0 / math.sqrt(1.0 + stretch_fraction)


def volume_centroid_cs(cs_m: float, oring_id_m: float, contact_diameter_m: float) -> float:
    """Solve W'^2 (D_contact + W') = W^2 (ID + W) for W' (Newton, monotone cubic)."""
    _positive(cs_m=cs_m, oring_id_m=oring_id_m, contact_diameter_m=contact_diameter_m)
    if contact_diameter_m <= oring_id_m:
        return cs_m
    target = cs_m**2 * (oring_id_m + cs_m)
    w = cs_m
    for _ in range(50):
        f = w**2 * (contact_diameter_m + w) - target
        df = 2 * w * contact_diameter_m + 3 * w**2
        step = f / df
        w -= step
        if abs(step) < 1e-15:
            break
    return w


def effective_cs(
    cs_m: float,
    oring_id_m: float,
    contact_diameter_m: float,
    method: CsReductionMethod = "volume_centroid",
) -> float:
    """Cross-section (compression diameter) after installation stretch."""
    if method == "volume_centroid":
        return volume_centroid_cs(cs_m, oring_id_m, contact_diameter_m)
    s = stretch(contact_diameter_m, oring_id_m)
    if method == "volume_id":
        return cs_m * (1.0 - volume_id_reduction(s))
    if method == "parker_observed":
        return cs_m * (1.0 - parker_observed_reduction(s))
    raise GeometryError(f"unknown cross-section reduction method: {method}")


# --------------------------------------------------------------------------- squeeze, gap


def squeeze(cs_eff_m: float, gland_depth_m: float) -> float:
    """(W_eff - L) / W_eff. Negative: no contact (gap between ring and mating surface)."""
    _positive(cs_eff_m=cs_eff_m)
    return (cs_eff_m - gland_depth_m) / cs_eff_m


def radial_gland_depths(
    nominal_depth_m: float, diametral_clearance_m: float, eccentricity_m: float | None = None
) -> tuple[float, float]:
    """(min, max) gland depth around the circumference for a radial gland.

    ``eccentricity_m`` = radial offset between the parts; ``None`` = full eccentricity
    (c/2, all clearance on one side). It cannot exceed c/2 (parts would interfere).
    """
    e = full_eccentricity(diametral_clearance_m) if eccentricity_m is None else eccentricity_m
    _check_eccentricity(e, diametral_clearance_m)
    return nominal_depth_m - e, nominal_depth_m + e


def max_extrusion_gap(diametral_clearance_m: float, eccentricity_m: float | None = None) -> float:
    """Largest one-sided radial gap: c/2 + e (= c at full eccentricity)."""
    e = full_eccentricity(diametral_clearance_m) if eccentricity_m is None else eccentricity_m
    _check_eccentricity(e, diametral_clearance_m)
    return diametral_clearance_m / 2.0 + e


def full_eccentricity(diametral_clearance_m: float) -> float:
    return max(diametral_clearance_m, 0.0) / 2.0


def _check_eccentricity(e: float, c: float) -> None:
    if e < 0:
        raise GeometryError("eccentricity must be >= 0")
    if c < 0:
        raise GeometryError(f"negative diametral clearance {c:.3e} m: parts interfere")
    if e > c / 2.0 + 1e-15:
        raise GeometryError("eccentricity exceeds half the diametral clearance")


# --------------------------------------------------------------------------- gland fill


def oring_area(cs_eff_m: float) -> float:
    return math.pi * cs_eff_m**2 / 4.0


def gland_area(depth_m: float, width_m: float, corner_radius_m: float = 0.0) -> float:
    """Rectangular gland area minus two groove-bottom corner radii."""
    _positive(depth_m=depth_m, width_m=width_m)
    if corner_radius_m < 0 or 2 * corner_radius_m > width_m or corner_radius_m > depth_m:
        raise GeometryError("corner radius does not fit the gland")
    return depth_m * width_m - 2.0 * (1.0 - math.pi / 4.0) * corner_radius_m**2


def gland_fill(
    cs_eff_m: float,
    depth_m: float,
    width_m: float,
    corner_radius_m: float = 0.0,
    swell: float = 0.0,
) -> float:
    return oring_area(cs_eff_m) * (1.0 + swell) / gland_area(depth_m, width_m, corner_radius_m)
