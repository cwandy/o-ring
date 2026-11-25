"""Trelleborg PTFE O-ring Table 48 groove dimensions."""

import pytest

from oring_designer.groove_calc import GrooveInput, calculate
from oring_designer.loader import load_dataset
from oring_designer.ptfe_catalog import groove

DS = load_dataset()


@pytest.mark.parametrize("cs,h,b,r", [(1.50, 1.30, 1.7, 0.2), (1.78, 1.60, 2.0, 0.4), (2.65, 2.35, 2.9, 0.6),
                                      (3.53, 3.15, 3.9, 1.0), (5.30, 4.80, 5.9, 1.2), (8.40, 7.55, 9.2, 2.0)])
def test_table_48_rows(cs, h, b, r):
    g = groove(cs * 1e-3)
    assert (g.depth_m, g.width_m, g.radius_m) == pytest.approx((h * 1e-3, b * 1e-3, r * 1e-3))
    assert not g.interpolated and g.depth_tol_m == pytest.approx((0, 0.05e-3))


def test_interpolation_and_ratio_extrapolation():
    assert groove(3.2e-3).interpolated
    small = groove(1.0e-3)  # first row 1.50: h 1.30, b4 1.7, r1 0.2
    assert small.extrapolated and small.depth_m == pytest.approx(1.30e-3 / 1.5)
    assert small.width_m == pytest.approx(1.7e-3 / 1.5) and small.radius_m == pytest.approx(0.2e-3 / 1.5)
    big = groove(9.0e-3)  # last row 8.40: h 7.55, b4 9.2
    assert big.extrapolated and big.width_m == pytest.approx(9.2e-3 * 9.0 / 8.4)


def test_calculator_uses_catalogue_for_ptfe_and_pctfe():
    base = dict(cs_m=3.53e-3, gland="face", T_min_K=260, T_max_K=300, pressure_Pa=5e6, housing_material="ss304")
    r = calculate(GrooveInput(seal_material="ptfe", hardness_shore_a=None, catalog_thermal_centre=False, **base), DS)
    assert (r.depth_m, r.width_m, r.radius_m) == pytest.approx((3.15e-3, 3.9e-3, 1.0e-3))
    assert r.catalog == "trelleborg_ptfe_oring" and "ptfe_catalog" in r.notes
    assert r.tolerances["gland.groove_depth_m"].lower_m == 0 and r.tolerances["gland.groove_depth_m"].upper_m == pytest.approx(0.05e-3)
    # no Parker elastomer absolute-minimum rule on PTFE
    assert not any(x.code == "squeeze_min_abs" for x, _ in r.wc.worst_results.values())
    p = calculate(GrooveInput(seal_material="pctfe", hardness_shore_a=None, catalog_thermal_centre=False, **base), DS)
    assert p.catalog == "trelleborg_ptfe_oring" and "pctfe_ptfe_table" in p.notes  # PTFE table as proxy
    assert p.width_m == pytest.approx(3.9e-3)


def test_thermal_centring_of_catalogue_depth():
    base = dict(seal_material="ptfe", cs_m=3.53e-3, gland="face", T_min_K=77.0, T_max_K=373.15, pressure_Pa=5e6,
                hardness_shore_a=None, housing_material="ss304")
    raw = calculate(GrooveInput(**base, catalog_thermal_centre=False), DS)
    cen = calculate(GrooveInput(**base), DS)
    assert raw.depth_m == pytest.approx(3.15e-3) and cen.catalog_depth_m == pytest.approx(3.15e-3)
    assert cen.depth_m < raw.depth_m and "catalog_thermal_centre" in cen.notes
    s_cat = raw.nominal_at(293.15)
    s_cat = (s_cat.squeeze_min + s_cat.squeeze_max) / 2
    pt = cen.per_temperature
    mean_ends = (pt.squeeze_nominal.iloc[0] + pt.squeeze_nominal.iloc[-1]) / 2
    assert mean_ends == pytest.approx(s_cat, abs=0.003)  # within the 0.01 mm depth rounding
    assert cen.width_m == raw.width_m and cen.radius_m == raw.radius_m
