"""Variseal M2 catalogue lookup and automatic O-ring tolerances."""

import pytest

from oring_designer.loader import load_dataset
from oring_designer.oring_tol import standard_tolerance
from oring_designer.variseal import VarisealRangeError, groove


def test_catalogue_examples():
    # catalogue ordering examples: rod d = 80 -> RVA3, D1 = 89.4; bore D = 80 -> PVA3, d1 = 70.6
    r = groove("rod", 80e-3, 15e6)
    assert (r.series, r.groove_diameter_m, r.groove_width_m) == ("RVA3", pytest.approx(89.4e-3), pytest.approx(7.1e-3))
    assert r.s_max_m == pytest.approx(0.20e-3) and (r.mating_class, r.groove_class) == ("h9", "H9")
    p = groove("piston", 80e-3, 1e6)
    assert (p.series, p.groove_diameter_m) == ("PVA3", pytest.approx(70.6e-3))
    assert p.s_max_m == pytest.approx(0.50e-3) and (p.mating_class, p.groove_class) == ("H9", "h9")


def test_table_42_and_123_spot_values():
    for d, D1 in ((3.0, 5.9), (16.0, 20.5), (36.0, 42.2), (140.0, 152.2)):
        assert groove("rod", d * 1e-3, 1e6).groove_diameter_m == pytest.approx(D1 * 1e-3)
    for D, d1 in ((6.0, 3.1), (20.0, 15.5), (50.0, 40.6), (250.0, 237.8)):
        assert groove("piston", D * 1e-3, 1e6).groove_diameter_m == pytest.approx(d1 * 1e-3)


def test_backup_ring_above_40_MPa_and_ranges():
    g = groove("rod", 50e-3, 45e6)
    assert g.backup_ring and g.s_max_m is None
    assert not groove("rod", 30e-3, 1e6).standard_range is False  # 30 mm: RVA2 standard
    with pytest.raises(VarisealRangeError):
        groove("piston", 2e-3, 1e6)
    with pytest.raises(VarisealRangeError):
        groove("face", 20e-3, 1e6)


def test_sources_defined():
    refs = load_dataset().references
    assert {"trelleborg_variseal_m2_rod", "trelleborg_variseal_m2_piston"} <= set(refs)


def test_as568_automatic_tolerance():
    t = standard_tolerance(43.7e-3, 3.53e-3)  # AS568-224: ID 1.725 +/-0.015 in, CS .139 +/-.004 in
    assert t.size == "AS568-224"
    assert t.id_tol_m == pytest.approx(0.015 * 0.0254) and t.cs_tol_m == pytest.approx(0.004 * 0.0254)
