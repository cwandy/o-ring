"""Gland types (piston, rod, face) evaluated at one thermal state (SPEC §6, K5).

All input dimensions are given at the reference temperature ``T_ref_K`` and in metres.
Each dimension is scaled with the material and temperature of the part it belongs to:

* O-ring (ID, CS): seal material at ``T_seal_K``.
* Groove part (the part carrying the groove): its material at ``T_housing_K``.
* Mating part (bore of a piston gland, rod of a rod gland): its material at ``T_mating_K``
  (defaults to the groove part material and ``T_housing_K``, K5).

Part assignment
---------------
Piston (male gland): groove part = piston (piston O.D., groove bottom diameter, groove
width); mating part = cylinder bore.
Rod (female gland): groove part = housing (throat/bore diameter, groove outer diameter,
groove width); mating part = rod.
Face: groove part = flange with the groove (groove I.D., O.D., depth). The flat mating face
does not change the gland depth (metal-to-metal contact assumed).

Simplifications: free isotropic thermal strain of every part (no stress from fits or
pressure, no bore breathing); the O-ring scales freely before it is constrained by the
gland; uniform temperature within each part.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import geometry as g
from .models import DataQuality, worst_quality
from .thermal import REFERENCE_T_K, ThermalStrainCurve, scale_factor_with_quality


@dataclass(frozen=True)
class ORing:
    id_m: float
    cs_m: float

    @property
    def od_m(self) -> float:
        return self.id_m + 2.0 * self.cs_m


@dataclass(frozen=True)
class PistonGland:
    bore_diameter_m: float
    piston_diameter_m: float
    groove_diameter_m: float
    groove_width_m: float
    corner_radius_m: float = 0.0
    eccentricity_m: float | None = None  # None = full eccentricity
    kind: Literal["piston"] = "piston"


@dataclass(frozen=True)
class RodGland:
    rod_diameter_m: float
    throat_diameter_m: float
    groove_diameter_m: float
    groove_width_m: float
    corner_radius_m: float = 0.0
    eccentricity_m: float | None = None
    kind: Literal["rod"] = "rod"


@dataclass(frozen=True)
class FaceGland:
    groove_id_m: float
    groove_od_m: float
    groove_depth_m: float
    pressure_direction: Literal["internal", "external"]
    corner_radius_m: float = 0.0
    kind: Literal["face"] = "face"


Gland = PistonGland | RodGland | FaceGland


@dataclass(frozen=True)
class ThermalState:
    T_seal_K: float = REFERENCE_T_K
    T_housing_K: float = REFERENCE_T_K
    T_mating_K: float | None = None  # None = same as T_housing_K
    T_ref_K: float = REFERENCE_T_K

    @property
    def mating_K(self) -> float:
        return self.T_housing_K if self.T_mating_K is None else self.T_mating_K


@dataclass(frozen=True)
class GlandState:
    """Geometry of a gland at one thermal state. Lengths in m, ratios as fractions."""

    kind: str
    oring_id_m: float
    cs_m: float  # thermally scaled, before stretch
    cs_eff_m: float  # after stretch reduction
    contact_diameter_m: float
    stretch: float
    circumferential_compression: float | None
    depth_nominal_m: float
    depth_min_m: float
    depth_max_m: float
    squeeze_nominal: float
    squeeze_min: float  # at the deepest point (eccentric wide side)
    squeeze_max: float  # at the shallowest point
    squeeze_min_abs_m: float
    gland_width_m: float
    fill: float
    diametral_clearance_m: float | None
    max_extrusion_gap_m: float | None
    data_quality: DataQuality | None  # weakest thermal data quality used (None: none used)


def _scale(curve: ThermalStrainCurve, T_K: float, T_ref_K: float):
    return scale_factor_with_quality(curve, T_K, T_ref_K)


def evaluate(
    gland: Gland,
    oring: ORing,
    seal_curve: ThermalStrainCurve,
    groove_curve: ThermalStrainCurve,
    mating_curve: ThermalStrainCurve | None = None,
    state: ThermalState = ThermalState(),
    cs_method: g.CsReductionMethod = "volume_centroid",
    swell: float = 0.0,
) -> GlandState:
    """Evaluate gland geometry at ``state``. See module docstring for assumptions."""
    mating_curve = groove_curve if mating_curve is None else mating_curve
    k_seal, q_seal = _scale(seal_curve, state.T_seal_K, state.T_ref_K)
    k_groove, q_groove = _scale(groove_curve, state.T_housing_K, state.T_ref_K)
    k_mate, q_mate = _scale(mating_curve, state.mating_K, state.T_ref_K)
    qualities = [q for q in (q_seal, q_groove, q_mate) if q is not None]
    quality = worst_quality(*qualities) if qualities else None

    ring_id = oring.id_m * k_seal
    cs = oring.cs_m * k_seal
    ring_od = ring_id + 2.0 * cs

    if isinstance(gland, PistonGland):
        bore = gland.bore_diameter_m * k_mate
        piston = gland.piston_diameter_m * k_groove
        groove = gland.groove_diameter_m * k_groove
        width = gland.groove_width_m * k_groove
        radius = gland.corner_radius_m * k_groove
        contact = groove
        circ = None
        depth = (bore - groove) / 2.0
        clearance = bore - piston
        ecc = gland.eccentricity_m
    elif isinstance(gland, RodGland):
        rod = gland.rod_diameter_m * k_mate
        throat = gland.throat_diameter_m * k_groove
        groove = gland.groove_diameter_m * k_groove
        width = gland.groove_width_m * k_groove
        radius = gland.corner_radius_m * k_groove
        contact = rod
        circ = g.circumferential_compression(ring_od, groove)
        depth = (groove - rod) / 2.0
        clearance = throat - rod
        ecc = gland.eccentricity_m
    elif isinstance(gland, FaceGland):
        gid = gland.groove_id_m * k_groove
        god = gland.groove_od_m * k_groove
        depth = gland.groove_depth_m * k_groove
        radius = gland.corner_radius_m * k_groove
        width = (god - gid) / 2.0
        contact = gid
        circ = g.circumferential_compression(ring_od, god)
        clearance = None
        ecc = None
    else:  # pragma: no cover - guarded by typing
        raise g.GeometryError(f"unknown gland type {gland!r}")

    s = g.stretch(contact, ring_id)
    cs_eff = g.effective_cs(cs, ring_id, contact, cs_method) if s > 0 else cs

    if clearance is None:
        d_min = d_max = depth
        gap = None
    else:
        d_min, d_max = g.radial_gland_depths(depth, clearance, ecc)
        gap = g.max_extrusion_gap(clearance, ecc)

    return GlandState(
        kind=gland.kind,
        oring_id_m=ring_id,
        cs_m=cs,
        cs_eff_m=cs_eff,
        contact_diameter_m=contact,
        stretch=s,
        circumferential_compression=circ,
        depth_nominal_m=depth,
        depth_min_m=d_min,
        depth_max_m=d_max,
        squeeze_nominal=g.squeeze(cs_eff, depth),
        squeeze_min=g.squeeze(cs_eff, d_max),
        squeeze_max=g.squeeze(cs_eff, d_min),
        squeeze_min_abs_m=cs_eff - d_max,
        gland_width_m=width,
        fill=g.gland_fill(cs_eff, depth, width, radius, swell),
        diametral_clearance_m=clearance,
        max_extrusion_gap_m=gap,
        data_quality=quality,
    )
