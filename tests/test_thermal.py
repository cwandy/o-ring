"""Phase 1 acceptance tests for thermal.py (SPEC §11, Faz 1)."""

import numpy as np
import pytest

from oring_designer.loader import load_dataset
from oring_designer.models import DataQuality, TableSegment, ThermalStrainData
from oring_designer.thermal import (
    REFERENCE_T_K,
    NoThermalDataError,
    OutOfRangeError,
    ThermalDataError,
    build_curve,
    eps_th,
    scale_dimension,
    scale_factor,
    scale_factor_with_quality,
)

DS = load_dataset()
ALL = {**DS.seal_materials, **DS.housing_materials}
CURVES = {mid: build_curve(m.thermal_strain, mid) for mid, m in ALL.items()}
WITH_DATA = sorted(mid for mid, c in CURVES.items() if c.has_data)
WITHOUT_DATA = sorted(mid for mid, c in CURVES.items() if not c.has_data)


def test_expected_data_coverage():
    assert WITH_DATA == sorted(
        ["vmq", "ptfe", "pctfe", "al6061", "al7075", "al1100", "al3003", "ss304", "ss316", "in718"]
    )


# --------------------------------------------------------------------------- scale = 1 at T_ref


@pytest.mark.parametrize("mid", sorted(ALL))
def test_scale_is_one_at_default_reference(mid):
    assert scale_factor(CURVES[mid], REFERENCE_T_K) == 1.0


@pytest.mark.parametrize("mid", WITH_DATA)
def test_eps_is_zero_at_293_15(mid):
    assert abs(eps_th(CURVES[mid], REFERENCE_T_K)) < 1e-12


@pytest.mark.parametrize("mid", [m for m in WITH_DATA if m != "al7075"])
@pytest.mark.parametrize("T_ref", [150.0, 250.0, 290.0])
def test_scale_is_one_at_non_default_reference(mid, T_ref):
    """K1: the corrected formula gives exactly 1 at any T_ref, not only 293.15 K."""
    c = CURVES[mid]
    assert scale_factor(c, T_ref, T_ref_K=T_ref) == 1.0
    # and the computed path (T slightly off T_ref) is continuous to 1
    assert scale_factor(c, T_ref + 1e-6, T_ref_K=T_ref) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("mid", [m for m in WITH_DATA if m != "al7075"])
def test_scaling_is_consistent_between_references(mid):
    """L(T1->T2) * L(T2->T1) = 1 and scaling composes."""
    c = CURVES[mid]
    a, b, d = 80.0, 200.0, 280.0
    assert scale_factor(c, a, b) * scale_factor(c, b, a) == pytest.approx(1.0, abs=1e-14)
    assert scale_factor(c, a, b) * scale_factor(c, b, d) == pytest.approx(
        scale_factor(c, a, d), abs=1e-14
    )


def test_scale_dimension():
    c = CURVES["ss304"]
    L = scale_dimension(0.1, c, 77.0)
    assert L == pytest.approx(0.1 * (1 + eps_th(c, 77.0)), rel=1e-12)
    assert L < 0.1


# --------------------------------------------------------------------------- monotonic tables

# NIST fits are not exactly continuous at T_low (<= 2.6e-7 strain, kept as published).
MONOTONE_TOL = 1e-6


@pytest.mark.parametrize("mid", WITH_DATA)
def test_tables_are_monotone(mid):
    c = CURVES[mid]
    assert np.all(np.diff(c.eps_values) >= -MONOTONE_TOL)
    T = np.linspace(c.T_min_K, c.T_max_K, 5000)
    assert np.all(np.diff(c.eps(T)) >= -MONOTONE_TOL)


# --------------------------------------------------------------------------- source values


def _nist_y(coeffs, T, T_low, f):
    a, b, cc, d, e = coeffs
    return f if T < T_low else a + b * T + cc * T**2 + d * T**3 + e * T**4


@pytest.mark.parametrize(
    "mid, coeffs, T_low, f",
    [
        ("ss304", (-2.9554e2, -3.9811e-1, 9.2683e-3, -2.0261e-5, 1.7127e-8), 23, -300.04),
        ("al6061", (-4.1277e2, -3.0389e-1, 8.7696e-3, -9.9821e-6, 0.0), 18, -415.45),
        ("in718", (-2.368e2, -2.120e-1, 5.497e-3, -6.882e-6, 0.0), 20, -238.87),
    ],
)
@pytest.mark.parametrize("T", [10.0, 77.0, 150.0, 250.0])
def test_nist_fit_reproduced(mid, coeffs, T_low, f, T):
    """Independent evaluation of the NIST TRC formula, re-referenced to 293.15 K."""
    y_T = _nist_y(coeffs, T, T_low, f) * 1e-5
    y_ref = _nist_y(coeffs, REFERENCE_T_K, T_low, f) * 1e-5
    expected = (1 + y_T) / (1 + y_ref) - 1
    assert eps_th(CURVES[mid], T) == pytest.approx(expected, abs=1e-10)


@pytest.mark.parametrize(
    "mid, T, contraction_1e5",
    [("pctfe", 80, 962), ("pctfe", 20, 1114), ("al1100", 20, 415), ("vmq", 100, 2066)],
)
def test_monograph29_values_reproduced(mid, T, contraction_1e5):
    """NBS Monograph 29 values (293 K reference), re-referenced exactly to 293.15 K.

    The table has a point at 293 K where e_s = 0, so eps(293) = 1/(1 + e_s(293.15)) - 1
    gives the reference offset used by build_curve.
    """
    c = CURVES[mid]
    e_ref = 1.0 / (1.0 + eps_th(c, 293.0)) - 1.0
    assert 0.0 < e_ref < 5e-5  # 0.15 K of expansion
    expected = (1.0 - contraction_1e5 * 1e-5) / (1.0 + e_ref) - 1.0
    assert eps_th(c, T) == pytest.approx(expected, abs=1e-12)


def test_al7075_reference_equivalence():
    """Table ends at 293 K; 293 K is treated as 293.15 K (documented simplification)."""
    c = CURVES["al7075"]
    assert c.T_max_K == REFERENCE_T_K
    assert eps_th(c, 116.0) == pytest.approx(-314e-5, abs=1e-12)


# --------------------------------------------------------------------------- PTFE transition


def test_ptfe_table_is_dense_in_transition_region():
    T = set(np.round(CURVES["ptfe"].T_K, 2))
    for k in range(283, 314):
        assert round(k + 0.15, 2) in T, f"missing {k + 0.15} K"


def test_ptfe_interpolation_passes_through_points_without_overshoot():
    c = CURVES["ptfe"]
    mask = (c.T_K >= 283.0) & (c.T_K <= 314.0)
    Tp, ep = c.T_K[mask], c.eps_values[mask]
    assert np.allclose(c.eps(Tp), ep, atol=1e-15)
    for (t1, e1), (t2, e2) in zip(zip(Tp, ep), zip(Tp[1:], ep[1:])):
        mid = c.eps(np.linspace(t1, t2, 11))
        assert np.all(mid >= min(e1, e2) - 1e-15) and np.all(mid <= max(e1, e2) + 1e-15)


def test_ptfe_transition_is_resolved():
    """Slope across the ~20 C transition is several times the slope at 50-100 C."""
    c = CURVES["ptfe"]
    slope_tr = (eps_th(c, 294.15) - eps_th(c, 292.15)) / 2.0
    slope_hi = (eps_th(c, 373.15) - eps_th(c, 323.15)) / 50.0
    assert slope_tr > 3.0 * slope_hi


def test_ptfe_rereferenced_from_25C():
    """Source reference is 298.15 K; e_s(293.15) is the digitized table point at 293.15 K."""
    c = CURVES["ptfe"]
    seg = ALL["ptfe"].thermal_strain.segments[2]
    e_ref = dict(seg.points)[293.15] * seg.scale
    assert -0.0016 < e_ref < -0.0013  # about -0.15 %
    assert eps_th(c, 298.15) == pytest.approx(1 / (1 + e_ref) - 1, rel=1e-9)
    # Monograph 29 value at 20 K (2110e-5 below 25 C) seen from 293.15 K
    assert eps_th(c, 20.0) == pytest.approx((1 - 0.02110) / (1 + e_ref) - 1, rel=1e-9)


# --------------------------------------------------------------------------- range errors


@pytest.mark.parametrize("mid, T", [("ss304", 350.0), ("al7075", 77.0), ("ptfe", 10.0), ("ptfe", 450.0)])
def test_out_of_range_raises_clear_error(mid, T):
    with pytest.raises(OutOfRangeError) as exc:
        eps_th(CURVES[mid], T)
    msg = str(exc.value)
    assert mid in msg and "veri aralığı dışında" in msg and f"{T:.2f}" in msg


def test_out_of_range_in_array_raises():
    with pytest.raises(OutOfRangeError):
        eps_th(CURVES["ss304"], np.array([100.0, 200.0, 301.0]))


def test_explicit_extrapolation_is_flagged():
    c = CURVES["ss304"]
    value, quality = scale_factor_with_quality(c, 320.0, allow_extrapolation=True)
    assert value > 1.0
    assert quality is DataQuality.EXTRAPOLATED


@pytest.mark.parametrize("mid", WITHOUT_DATA)
def test_material_without_data(mid):
    c = CURVES[mid]
    assert scale_factor_with_quality(c, REFERENCE_T_K) == (1.0, None)
    assert scale_factor_with_quality(c, 250.0, T_ref_K=250.0) == (1.0, None)
    with pytest.raises(NoThermalDataError):
        scale_factor(c, 250.0)


# --------------------------------------------------------------------------- quality bands


@pytest.mark.parametrize(
    "T, quality",
    [
        (40.0, DataQuality.EXTRAPOLATED),  # monograph extrapolation below 80 K
        (70.0, DataQuality.EXTRAPOLATED),  # gap between segments -> weaker neighbour
        (150.0, DataQuality.LITERATURE),
        (293.15, DataQuality.LITERATURE),
    ],
)
def test_ptfe_quality_bands(T, quality):
    assert CURVES["ptfe"].quality_at(T) is quality


def test_scale_reports_weakest_quality():
    _, q = scale_factor_with_quality(CURVES["ptfe"], 40.0)
    assert q is DataQuality.EXTRAPOLATED
    _, q = scale_factor_with_quality(CURVES["ss304"], 77.0)
    assert q is DataQuality.MEASURED_REFERENCE


# --------------------------------------------------------------------------- building errors


def _table(points, quantity="expansion"):
    return TableSegment(
        kind="table", quantity=quantity, points=points, source="x", data_quality="literature"
    )


def test_overlapping_segments_rejected():
    data = ThermalStrainData(
        reference_T_K=293.15,
        segments=[_table([(100, -0.001), (293.15, 0.0)]), _table([(200, 0.0), (300, 0.001)])],
    )
    with pytest.raises(ThermalDataError):
        build_curve(data, "bad")


def test_unreferencable_table_rejected():
    data = ThermalStrainData(reference_T_K=77.0, segments=[_table([(20, -0.001), (77, 0.0)])])
    with pytest.raises(ThermalDataError):
        build_curve(data, "bad")
