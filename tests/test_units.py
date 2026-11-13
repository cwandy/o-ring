import pytest

from oring_designer import units


def test_length():
    assert units.length_to_m(1.0, "in") == pytest.approx(0.0254, rel=1e-12)
    assert units.length_to_m(2.5, "mm") == pytest.approx(0.0025, rel=1e-12)
    assert units.length_from_m(0.0254, "in") == pytest.approx(1.0, rel=1e-12)


def test_temperature():
    assert units.temperature_to_K(0.0, "degC") == pytest.approx(273.15)
    assert units.temperature_to_K(-40.0, "degF") == pytest.approx(233.15)
    assert units.temperature_from_K(77.0, "degC") == pytest.approx(-196.15)


def test_pressure():
    assert units.pressure_to_Pa(1.0, "bar") == pytest.approx(1e5)
    assert units.pressure_to_Pa(1.0, "MPa") == pytest.approx(1e6)
    assert units.pressure_to_Pa(1.0, "psi") == pytest.approx(6894.757, rel=1e-6)
    assert units.pressure_from_Pa(1e5, "bar") == pytest.approx(1.0)
