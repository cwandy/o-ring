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


def test_interpolation_and_range():
    assert groove(3.2e-3).interpolated
    assert groove(9.0e-3) is None


def test_calculator_uses_catalogue_for_ptfe_only():
    base = dict(cs_m=3.53e-3, gland="face", T_min_K=260, T_max_K=300, pressure_Pa=5e6, housing_material="ss304")
    r = calculate(GrooveInput(seal_material="ptfe", hardness_shore_a=None, **base), DS)
    assert (r.depth_m, r.width_m, r.radius_m) == pytest.approx((3.15e-3, 3.9e-3, 1.0e-3))
    assert r.catalog == "trelleborg_ptfe_oring" and "ptfe_catalog" in r.notes
    assert r.tolerances["gland.groove_depth_m"].lower_m == 0 and r.tolerances["gland.groove_depth_m"].upper_m == pytest.approx(0.05e-3)
    # no Parker elastomer absolute-minimum rule on PTFE
    assert not any(x.code == "squeeze_min_abs" for x, _ in r.wc.worst_results.values())
    p = calculate(GrooveInput(seal_material="pctfe", hardness_shore_a=None, **(base | {"T_min_K": 260})), DS)
    assert p.catalog is None
