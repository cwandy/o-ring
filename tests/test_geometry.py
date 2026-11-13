"""Phase 2 tests: single-temperature geometry (SPEC §11, Faz 2).

Hand-calculated examples A (piston), B (rod), C/D (face internal/external) and a
comparison with Parker ORD 5700 Design Charts 4-2 and 4-3.

W_eff for the volume-centroid method was obtained independently by bisection of
W'^2 (D_contact + W') = W^2 (ID + W); all other expected values are written out below.
"""

import math

import pytest

from oring_designer import geometry as g
from oring_designer.gland_types import (
    FaceGland,
    ORing,
    PistonGland,
    RodGland,
    ThermalState,
    evaluate,
)
from oring_designer.loader import load_dataset
from oring_designer.thermal import build_curve, scale_factor

MM = 1e-3
IN = 0.0254
DS = load_dataset()
CURVE = {k: build_curve(m.thermal_strain, k) for k, m in {**DS.seal_materials, **DS.housing_materials}.items()}


# --------------------------------------------------------------------------- formulas


@pytest.mark.parametrize(
    "X, Y",
    [
        (0.0, 0.0),  # -0.005 clamped to 0
        (2.0, -0.005 + 1.19 * 2 - 0.19 * 4 - 0.001 * 8 + 0.008 * 16),  # 1.735 %
        (3.0, -0.005 + 1.19 * 3 - 0.19 * 9 - 0.001 * 27 + 0.008 * 81),  # 2.476 %
        (5.0, 0.56 + 0.59 * 5 - 0.0046 * 25),  # 3.395 %
        (25.0, 0.56 + 0.59 * 25 - 0.0046 * 625),  # 12.435 %
    ],
)
def test_parker_observed_curve(X, Y):
    assert g.parker_observed_reduction(X / 100) == pytest.approx(Y / 100, abs=1e-12)


def test_parker_observed_out_of_range():
    with pytest.raises(g.GeometryError):
        g.parker_observed_reduction(0.26)


def test_parker_calculated_curve():
    # Parker Fig. 3-3 'calculated': Y = 100 (1 - 10/sqrt(100 + X)); at 26 % about 10.9 %
    assert g.volume_id_reduction(0.26) == pytest.approx(1 - 10 / math.sqrt(126), rel=1e-12)


def test_volume_centroid_identity():
    w = g.volume_centroid_cs(3.53, 43.0, 43.6)
    assert w**2 * (43.6 + w) == pytest.approx(3.53**2 * (43.0 + 3.53), rel=1e-12)
    assert g.volume_centroid_cs(3.53, 43.0, 42.0) == 3.53  # not stretched


def test_gland_area_corner_radius():
    assert g.gland_area(2.0, 4.0, 0.5) == pytest.approx(8.0 - 2 * (1 - math.pi / 4) * 0.25)


def test_eccentricity_bounds():
    with pytest.raises(g.GeometryError):
        g.radial_gland_depths(3.0, 0.1, 0.06)
    with pytest.raises(g.GeometryError):
        g.max_extrusion_gap(-0.01)


# --------------------------------------------------------------------------- Parker design charts


# (W nominal in, W tol in, L min in, L max in, squeeze min in, squeeze max in, % min, % max)
CHART_4_2 = [
    (0.070, 0.003, 0.050, 0.052, 0.015, 0.023, 22, 32),
    (0.103, 0.003, 0.081, 0.083, 0.017, 0.025, 17, 24),
    (0.139, 0.004, 0.111, 0.113, 0.022, 0.032, 16, 23),
    (0.210, 0.005, 0.170, 0.173, 0.032, 0.045, 15, 21),
    (0.275, 0.006, 0.226, 0.229, 0.040, 0.055, 15, 20),
]
CHART_4_3 = [
    (0.070, 0.003, 0.050, 0.054, 0.013, 0.023, 19, 32),
    (0.103, 0.003, 0.074, 0.080, 0.020, 0.032, 20, 30),
    (0.139, 0.004, 0.101, 0.107, 0.028, 0.042, 20, 30),
    (0.210, 0.005, 0.152, 0.162, 0.043, 0.063, 21, 30),
    (0.275, 0.006, 0.201, 0.211, 0.058, 0.080, 21, 29),
    (0.375, 0.007, 0.276, 0.286, 0.082, 0.106, 22, 28),
    (0.500, 0.008, 0.370, 0.380, 0.112, 0.138, 22, 27),
]


@pytest.mark.parametrize("row", CHART_4_2 + CHART_4_3)
def test_parker_design_chart_squeeze(row):
    """Squeeze at the tolerance extremes reproduces Parker's tabulated values.

    Parker: minimum squeeze = W_min - L_max, maximum = W_max - L_min; the percentages are
    rounded in the charts (within one point).
    """
    W, tol, L_min, L_max, sq_min, sq_max, pct_min, pct_max = row
    w_lo, w_hi = (W - tol) * IN, (W + tol) * IN
    assert (w_lo - L_max * IN) / IN == pytest.approx(sq_min, abs=5e-7)
    assert (w_hi - L_min * IN) / IN == pytest.approx(sq_max, abs=5e-7)
    assert 100 * g.squeeze(w_lo, L_max * IN) == pytest.approx(pct_min, abs=1.0)
    assert 100 * g.squeeze(w_hi, L_min * IN) == pytest.approx(pct_max, abs=1.0)


# --------------------------------------------------------------------------- example A: piston


def _piston_A(**kw):
    return PistonGland(
        bore_diameter_m=50.0 * MM, piston_diameter_m=49.9 * MM, groove_diameter_m=43.6 * MM,
        groove_width_m=4.8 * MM, **kw,
    )


def test_example_A_piston_at_reference():
    st = evaluate(_piston_A(), ORing(43.0 * MM, 3.53 * MM), CURVE["vmq"], CURVE["al6061"])
    W_eff = 3.5082672287130867  # mm, bisection
    L, e = (50.0 - 43.6) / 2, (50.0 - 49.9) / 2  # 3.2 mm, full eccentricity 0.05 mm
    assert st.stretch == pytest.approx((43.6 - 43.0) / 43.0, rel=1e-12)
    assert st.cs_eff_m / MM == pytest.approx(W_eff, abs=1e-9)
    assert st.depth_nominal_m / MM == pytest.approx(L)
    assert st.squeeze_nominal == pytest.approx((W_eff - L) / W_eff, abs=1e-9)
    assert st.squeeze_min == pytest.approx((W_eff - (L + e)) / W_eff, abs=1e-9)  # 7.36 %
    assert st.squeeze_max == pytest.approx((W_eff - (L - e)) / W_eff, abs=1e-9)  # 10.21 %
    assert st.fill == pytest.approx(math.pi * W_eff**2 / 4 / (L * 4.8), abs=1e-9)
    assert st.max_extrusion_gap_m / MM == pytest.approx(0.10)
    assert st.data_quality is None  # no thermal data used at T_ref


def test_example_A_concentric():
    st = evaluate(_piston_A(eccentricity_m=0.0), ORing(43.0 * MM, 3.53 * MM), CURVE["vmq"], CURVE["al6061"])
    assert st.squeeze_min == pytest.approx(st.squeeze_max)
    assert st.max_extrusion_gap_m / MM == pytest.approx(0.05)


@pytest.mark.parametrize(
    "method, W_eff",
    [
        ("volume_centroid", 3.5082672287130867),
        ("volume_id", 3.53 / math.sqrt(1 + 0.6 / 43.0)),
        ("parker_observed", 3.53 * (1 - (-0.005 + 1.19 * (60 / 43) - 0.19 * (60 / 43) ** 2
                                        - 0.001 * (60 / 43) ** 3 + 0.008 * (60 / 43) ** 4) / 100)),
    ],
)
def test_example_A_cs_methods(method, W_eff):
    st = evaluate(_piston_A(), ORing(43.0 * MM, 3.53 * MM), CURVE["vmq"], CURVE["al6061"],
                  cs_method=method)
    assert st.cs_eff_m / MM == pytest.approx(W_eff, abs=1e-9)


# --------------------------------------------------------------------------- example B: rod


def test_example_B_rod_at_reference():
    gl = RodGland(rod_diameter_m=20.0 * MM, throat_diameter_m=20.1 * MM,
                  groove_diameter_m=26.0 * MM, groove_width_m=4.8 * MM)
    st = evaluate(gl, ORing(19.8 * MM, 3.53 * MM), CURVE["vmq"], CURVE["ss304"])
    W_eff = 3.5160111682680784  # mm, bisection with D_contact = rod = 20.0
    L, e = (26.0 - 20.0) / 2, (20.1 - 20.0) / 2
    assert st.stretch == pytest.approx(0.2 / 19.8, rel=1e-12)
    assert st.cs_eff_m / MM == pytest.approx(W_eff, abs=1e-9)
    assert st.circumferential_compression == pytest.approx((26.86 - 26.0) / 26.86, rel=1e-12)
    assert st.squeeze_min == pytest.approx((W_eff - (L + e)) / W_eff, abs=1e-9)  # 13.25 %
    assert st.squeeze_max == pytest.approx((W_eff - (L - e)) / W_eff, abs=1e-9)  # 16.10 %
    assert st.fill == pytest.approx(math.pi * W_eff**2 / 4 / (L * 4.8), abs=1e-9)
    assert st.max_extrusion_gap_m / MM == pytest.approx(0.10)


# --------------------------------------------------------------------------- examples C, D: face


def test_example_C_face_internal_pressure():
    gl = FaceGland(groove_id_m=27.5 * MM, groove_od_m=36.8 * MM, groove_depth_m=2.65 * MM,
                   pressure_direction="internal")
    st = evaluate(gl, ORing(29.87 * MM, 3.53 * MM), CURVE["vmq"], CURVE["al6061"])
    assert st.stretch < 0 and st.cs_eff_m == pytest.approx(3.53 * MM)  # ID not stretched
    assert st.circumferential_compression == pytest.approx((36.93 - 36.8) / 36.93, rel=1e-12)
    assert st.squeeze_min == st.squeeze_max == pytest.approx((3.53 - 2.65) / 3.53, abs=1e-12)
    assert st.fill == pytest.approx(math.pi * 3.53**2 / 4 / (2.65 * 4.65), abs=1e-9)
    assert st.max_extrusion_gap_m is None


def test_example_D_face_external_pressure():
    gl = FaceGland(groove_id_m=29.95 * MM, groove_od_m=39.25 * MM, groove_depth_m=2.65 * MM,
                   pressure_direction="external")
    st = evaluate(gl, ORing(29.87 * MM, 3.53 * MM), CURVE["vmq"], CURVE["al6061"])
    assert st.stretch == pytest.approx(0.08 / 29.87, rel=1e-12)
    W_eff = g.volume_centroid_cs(3.53, 29.87, 29.95)
    assert st.cs_eff_m / MM == pytest.approx(W_eff, abs=1e-12)
    assert st.squeeze_nominal == pytest.approx((W_eff - 2.65) / W_eff, abs=1e-12)


# --------------------------------------------------------------------------- thermal state


def test_thermal_state_scales_each_part_with_its_material():
    """K5: piston (groove part) in SS 304, bore (mating part) in Al 6061, ring VMQ."""
    gl = _piston_A(eccentricity_m=0.0)
    ring = ORing(43.0 * MM, 3.53 * MM)
    state = ThermalState(T_seal_K=230.0, T_housing_K=200.0, T_mating_K=150.0)
    st = evaluate(gl, ring, CURVE["vmq"], CURVE["ss304"], CURVE["al6061"], state)
    k_seal = scale_factor(CURVE["vmq"], 230.0)
    k_ss = scale_factor(CURVE["ss304"], 200.0)
    k_al = scale_factor(CURVE["al6061"], 150.0)
    assert st.cs_m == pytest.approx(3.53 * MM * k_seal, rel=1e-12)
    assert st.diametral_clearance_m == pytest.approx(50.0 * MM * k_al - 49.9 * MM * k_ss, rel=1e-12)
    assert st.depth_nominal_m == pytest.approx((50.0 * MM * k_al - 43.6 * MM * k_ss) / 2, rel=1e-12)
    assert st.stretch == pytest.approx((43.6 * k_ss - 43.0 * k_seal) / (43.0 * k_seal), rel=1e-12)
    assert st.data_quality is not None


def test_cold_elastomer_loses_squeeze():
    """Elastomer contracts ~5x more than aluminium: squeeze drops when cold."""
    gl, ring = _piston_A(), ORing(43.0 * MM, 3.53 * MM)
    warm = evaluate(gl, ring, CURVE["vmq"], CURVE["al6061"])
    cold = evaluate(gl, ring, CURVE["vmq"], CURVE["al6061"], state=ThermalState(220.0, 220.0))
    assert cold.squeeze_nominal < warm.squeeze_nominal
    assert cold.stretch > warm.stretch
