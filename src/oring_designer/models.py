"""Pydantic v2 data models for the YAML data files.

Every numeric datum carries ``source`` (an id in ``data/references.yaml``) and
``data_quality`` (SPEC §2, K12). A value whose quality is not ``placeholder`` must
have both a value and a source; a placeholder may leave either empty.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataQuality(str, Enum):
    MEASURED_REFERENCE = "measured_reference"
    LITERATURE = "literature"
    VENDOR = "vendor"
    USER_MEASURED = "user_measured"
    USER_INPUT = "user_input"  # value entered by the user for one design (e.g. catalog data)
    EXTRAPOLATED = "extrapolated"
    PLACEHOLDER = "placeholder"

    @property
    def needs_warning(self) -> bool:
        """True for qualities that must be flagged in the UI (SPEC §2.1)."""
        return self in (DataQuality.EXTRAPOLATED, DataQuality.PLACEHOLDER)


# Ordering used to report the weakest quality involved in a result.
_QUALITY_RANK = {
    DataQuality.MEASURED_REFERENCE: 0,
    DataQuality.LITERATURE: 1,
    DataQuality.VENDOR: 1,
    DataQuality.USER_MEASURED: 1,
    DataQuality.USER_INPUT: 1,
    DataQuality.EXTRAPOLATED: 2,
    DataQuality.PLACEHOLDER: 3,
}


def worst_quality(*qualities: DataQuality) -> DataQuality:
    """Return the weakest of the given qualities."""
    return max(qualities, key=lambda q: _QUALITY_RANK[q])


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reference(_Strict):
    id: str
    citation: str
    url: str | None = None
    accessed: str | None = None
    notes: str | None = None


class _Sourced(_Strict):
    source: str | None = None
    data_quality: DataQuality
    notes: str | None = None


class QualifiedValue(_Sourced):
    """A scalar value with provenance."""

    value: float | None = None

    @model_validator(mode="after")
    def _non_placeholder_needs_value_and_source(self) -> QualifiedValue:
        if self.data_quality is DataQuality.USER_INPUT:
            if self.value is None:
                raise ValueError("user_input requires a 'value'")
        elif self.data_quality is not DataQuality.PLACEHOLDER:
            if self.value is None or self.source is None:
                raise ValueError("non-placeholder value requires both 'value' and 'source'")
        return self


class QualifiedFlag(_Sourced):
    """A boolean property with provenance (e.g. hydrogen embrittlement susceptibility)."""

    value: bool | None = None


# --------------------------------------------------------------------------- thermal strain


class TableSegment(_Sourced):
    """Tabulated thermal strain.

    ``quantity='expansion'``  : value = (L_T - L_ref) / L_ref
    ``quantity='contraction'``: value = (L_ref - L_T) / L_ref  (NBS Monograph 29 convention)
    Values are multiplied by ``scale``.
    """

    kind: Literal["table"]
    quantity: Literal["expansion", "contraction"]
    scale: float = 1.0
    points: list[tuple[float, float]] = Field(min_length=1)

    @model_validator(mode="after")
    def _strictly_increasing_T(self) -> TableSegment:
        temps = [t for t, _ in self.points]
        if any(b <= a for a, b in zip(temps, temps[1:])):
            raise ValueError("table temperatures must be strictly increasing")
        return self


class NistPoly4Segment(_Sourced):
    """NIST TRC curve fit: y = a + bT + cT^2 + dT^3 + eT^4 for T > T_low, y = f below.

    y = (L_T - L_ref) / L_ref / scale. Valid on ``range_K``.
    """

    kind: Literal["nist_poly4"]
    coefficients: dict[Literal["a", "b", "c", "d", "e"], float]
    scale: float = 1.0
    T_low_K: float | None = None
    f: float | None = None
    range_K: tuple[float, float]
    fit_error_pct: float | None = None

    @model_validator(mode="after")
    def _check(self) -> NistPoly4Segment:
        if set(self.coefficients) != {"a", "b", "c", "d", "e"}:
            raise ValueError("coefficients a..e are all required")
        if (self.T_low_K is None) != (self.f is None):
            raise ValueError("T_low_K and f must be given together")
        if self.range_K[0] >= self.range_K[1]:
            raise ValueError("range_K must be increasing")
        return self


ThermalSegment = Annotated[TableSegment | NistPoly4Segment, Field(discriminator="kind")]


class ThermalStrainData(_Strict):
    """Thermal strain as published: the source reference temperature and its segments.

    An empty segment list means no sourced data (decision K3).
    """

    reference_T_K: float
    segments: list[ThermalSegment] = Field(default_factory=list)


# --------------------------------------------------------------------------- materials


class SealMaterial(_Strict):
    id: str
    name: str
    group: Literal["elastomer", "thermoplastic"]
    grade: str | None = None
    hardness_shore_a: QualifiedValue | None = None
    hardness_shore_d: QualifiedValue | None = None
    low_temp_limit_K: QualifiedValue | None = None
    tg_K: QualifiedValue | None = None
    tr10_K: QualifiedValue | None = None
    high_temp_limit_K: QualifiedValue | None = None
    thermal_strain: ThermalStrainData
    phase_transition_notes: str | None = None
    volume_swell: dict[str, QualifiedValue] = Field(default_factory=dict)
    notes: str | None = None


class Temper(_Strict):
    id: str
    name: str
    notes: str | None = None


class CryoToughness(_Strict):
    warning: bool
    threshold_K: QualifiedValue
    notes: str | None = None


class HousingMaterial(_Strict):
    id: str
    name: str
    tempers: list[Temper] = Field(min_length=1)
    thermal_strain: ThermalStrainData
    cryo_toughness: CryoToughness | None = None
    hydrogen_embrittlement: QualifiedFlag | None = None
    notes: str | None = None


# --------------------------------------------------------------------------- fluids


class Compatibility(_Sourced):
    status: Literal["ok", "conditional", "not_ok", "unknown"] = "unknown"


class Fluid(_Strict):
    id: str
    name: str
    boiling_point_K: QualifiedValue | None = None  # informational only
    compatibility: dict[str, Compatibility] = Field(default_factory=dict)

    def compatibility_with(self, seal_id: str) -> Compatibility:
        """Compatibility entry for a seal material; ``unknown`` when not filled in."""
        return self.compatibility.get(
            seal_id, Compatibility(status="unknown", data_quality=DataQuality.PLACEHOLDER)
        )


# --------------------------------------------------------------------------- design rules


class RuleLimit(QualifiedValue):
    """A design-rule limit; ``severity`` is the status given when it is violated."""

    severity: Literal["warn", "fail"] = "warn"


class SqueezeBand(_Strict):
    cs_nominal_in: float
    min: float
    max: float


class RecommendedSqueeze(_Sourced):
    bands: list[SqueezeBand]

    def band_for(self, cs_m: float, tol_in: float = 0.005) -> SqueezeBand | None:
        """Band whose nominal cross-section is within ``tol_in`` inch of ``cs_m``."""
        cs_in = cs_m / 0.0254
        best = min(self.bands, key=lambda b: abs(b.cs_nominal_in - cs_in))
        return best if abs(best.cs_nominal_in - cs_in) <= tol_in else None


class GlandDimensionRow(_Strict):
    cs_nominal_in: float
    clearance_min_in: float | None = None
    clearance_max_in: float | None = None
    radius_min_in: float | None = None
    radius_max_in: float | None = None
    eccentricity_max_in: float | None = None
    depth_min_in: float | None = None
    depth_max_in: float | None = None
    width_min_in: float | None = None
    width_max_in: float | None = None


class GlandDimensions(_Sourced):
    rows: list[GlandDimensionRow]

    def row_for(self, cs_m: float, tol_in: float = 0.005) -> GlandDimensionRow | None:
        cs_in = cs_m / 0.0254
        best = min(self.rows, key=lambda r: abs(r.cs_nominal_in - cs_in))
        return best if abs(best.cs_nominal_in - cs_in) <= tol_in else None


class RuleSet(_Strict):
    material_group: Literal["elastomer", "thermoplastic"]
    gland_type: Literal["static_radial", "static_face", "dynamic_reciprocating"]
    squeeze_max: RuleLimit | None = None
    fill_min: RuleLimit | None = None
    fill_max: RuleLimit | None = None
    fill_hard_max: RuleLimit | None = None
    stretch_min: RuleLimit | None = None
    stretch_max: RuleLimit | None = None
    circumferential_compression_max: RuleLimit | None = None
    face_seating_tolerance_rel: RuleLimit | None = None
    face_seating_tolerance_abs_m: RuleLimit | None = None
    recommended_squeeze: RecommendedSqueeze | None = None
    gland_dimensions: GlandDimensions | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: str | None = None


class CommonRules(_Strict):
    squeeze_min_abs_m: RuleLimit
    low_temp_warning_band_K: RuleLimit
    backup_ring_check_pressure_Pa: RuleLimit


class ExtrusionCurve(_Strict):
    hardness_shore_a: float
    points: list[tuple[float, float]] = Field(min_length=2)  # (pressure, clearance), source units


class ExtrusionLimits(_Sourced):
    pressure_unit: Literal["psi"]
    clearance_unit: Literal["in"]
    silicone_clearance_factor: float
    silicone_factor_notes: str | None = None
    reference_temperature_K: float | None = None
    curves: list[ExtrusionCurve] = Field(default_factory=list)
