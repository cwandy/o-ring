"""Groove calculator and compression force tests."""

import math
from pathlib import Path

import pytest

from oring_designer.force import LBF_PER_IN_TO_N_PER_M, face_clamp_load, load_per_length
from oring_designer.groove_calc import GrooveInput, TemperatureRangeError, calculate, usable_range
from oring_designer.loader import load_dataset

IN = 0.0254
DS = load_dataset()
APP = Path(__file__).resolve().parents[1] / "app"


def calc(**kw):
    base = dict(seal_material="vmq", cs_m=0.139 * IN)
    base.update(kw)
    return calculate(GrooveInput(**base), DS)


# --------------------------------------------------------------------------- Parker comparison


def test_face_depth_matches_parker_chart_4_3():
    r = calc(gland="face")
    assert 0.101 * IN <= r.depth_m <= 0.107 * IN
    assert r.depth_tol_m == pytest.approx(0.003 * IN)  # half of .101-.107
    assert r.width_tol_m == pytest.approx(0.010 * IN)  # .177-.187
    assert r.cs_tol_m == pytest.approx(0.004 * IN)  # AS568 -2xx
    lo, hi = r.squeeze_range
    assert abs((lo + hi) / 2 - 0.25) < 0.01 and r.target == (0.20, 0.30)


def test_radial_depth_matches_parker_chart_4_2():
    r = calc(gland="radial", seal_material="nbr")
    assert 0.111 * IN <= r.depth_m <= 0.113 * IN
    assert r.clearance_m == pytest.approx((0.003 * IN, 0.006 * IN))
    assert r.machine_depth_m == pytest.approx(r.depth_m - 0.0045 * IN / 2)


def test_width_satisfies_fill_limit():
    r = calc(gland="face", T_min_K=220, T_max_K=300, housing_material="al6061")
    assert r.fill_max <= r.fill_limit + 1e-9
    assert r.width_m >= r.width_min_m
    nominal = r.nominal_at(293.15)
    assert nominal.fill <= 0.75 + 1e-9  # recommended width gives <= 75 % nominal fill


def test_per_temperature_table():
    r = calc(T_min_K=220, T_max_K=300, housing_material="al6061")
    df = r.per_temperature
    assert df.T_K.min() == 220 and df.T_K.max() == 300
    assert df.volume_change.is_monotonic_increasing
    assert df.loc[df.T_K == 293.15, "volume_change"].iloc[0] == pytest.approx(0.0, abs=1e-12)
    assert (df.squeeze_lo <= df.squeeze_nominal).all() and (df.squeeze_nominal <= df.squeeze_hi).all()


# --------------------------------------------------------------------------- materials and limits


def test_thermoplastic_needs_target_squeeze():
    with pytest.raises(ValueError):
        calc(seal_material="pctfe", cs_m=1.78e-3)
    r = calc(seal_material="pctfe", cs_m=1.78e-3, T_min_K=93, T_max_K=300, target_squeeze=(0.08, 0.16))
    assert r.target == (0.08, 0.16)
    assert r.per_temperature.volume_change.iloc[0] < -0.02  # PCTFE shrinks ~1 % linear by 93 K


def test_temperature_outside_data():
    with pytest.raises(TemperatureRangeError) as e:
        calc(T_min_K=220, T_max_K=330)
    assert e.value.usable == (20.0, 300.0)
    assert usable_range(DS, "nbr", "ss304") is None
    calc(seal_material="nbr")  # at T_ref only: works without thermal data


def test_backup_ring_required_at_high_pressure():
    r = calc(gland="radial", pressure_Pa=200e5)  # silicone, 2900 psi
    assert "backup_ring_required" in r.notes
    assert r.wc.family_status["extrusion"].value == "FAIL"


def test_custom_cross_section_uses_nearest_parker_row():
    r = calc(cs_m=2.0e-3, cs_tol_m=0.08e-3)
    assert "parker_row_nearest" in r.notes and r.cs_tol_m == 0.08e-3


# --------------------------------------------------------------------------- force


@pytest.mark.parametrize("cs, pct, hard, lo, hi", [
    (0.139, 20, 70, 4.521, 29.093), (0.070, 40, 90, 35.046, 93.619), (0.275, 5, 50, 1.503, 3.247)])
def test_force_reproduces_chart_points(cs, pct, hard, lo, hi):
    q = load_per_length(DS, cs * IN, pct / 100, hard)
    assert q.min_N_per_m / LBF_PER_IN_TO_N_PER_M == pytest.approx(lo, rel=1e-6)
    assert q.max_N_per_m / LBF_PER_IN_TO_N_PER_M == pytest.approx(hi, rel=1e-6)
    third = (hi - lo) / 3
    assert q.typical_min_N_per_m / LBF_PER_IN_TO_N_PER_M == pytest.approx(lo + third, rel=1e-6)


def test_force_outside_chart_and_large_ring():
    assert load_per_length(DS, 0.139 * IN, 0.45, 70) is None
    assert load_per_length(DS, 0.139 * IN, 0.20, 95) is None
    q = load_per_length(DS, 0.139 * IN, 0.20, 70, ring_id_m=0.05)  # > 1 in: lower half
    assert q.typical_max_N_per_m == pytest.approx((q.min_N_per_m + q.max_N_per_m) / 2)


def test_face_clamp_load_formula():
    q = load_per_length(DS, 0.139 * IN, 0.25, 70, 0.03)
    c = face_clamp_load(q, 0.03, 0.139 * IN, 0.037, 55e5)
    circ = math.pi * (0.03 + 0.139 * IN)
    assert c.compression_N[1] == pytest.approx(q.max_N_per_m * circ)
    assert c.pressure_N == pytest.approx(55e5 * math.pi * 0.037**2 / 4)
    assert c.clamp_min_N == pytest.approx(c.compression_N[1] + c.pressure_N)
    assert face_clamp_load(q, 0.03, 0.139 * IN, 0.037, 55e5, "external").pressure_N == 0.0


def test_calculator_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP / "pages" / "0_Yuva_Hesaplayici.py")).run(timeout=180)
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Yuva derinliği H" in labels and "Yuva genişliği G" in labels
