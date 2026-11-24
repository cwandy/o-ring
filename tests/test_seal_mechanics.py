"""Lindley (1966) toroidal ring relations."""

import math

import pytest

from oring_designer.loader import load_dataset
from oring_designer.seal_mechanics import alpha_beta, contact_pressure, load_per_length, modulus

# Lindley Table 2: x/d, alpha_T, beta_T
TABLE2 = [(0.049, 0.014, 0.000), (0.101, 0.042, 0.001), (0.152, 0.080, 0.005), (0.201, 0.126, 0.010),
          (0.245, 0.173, 0.018), (0.305, 0.249, 0.035), (0.357, 0.326, 0.059), (0.398, 0.395, 0.086),
          (0.455, 0.504, 0.143), (0.500, 0.601, 0.208)]


@pytest.mark.parametrize("r,a,b", TABLE2)
def test_alpha_beta_reproduce_table_2(r, a, b):
    aa, bb = alpha_beta(r)
    assert aa == pytest.approx(a, abs=0.0015) and bb == pytest.approx(b, abs=0.0012)  # table printed to 3 decimals


def test_appendix_1_modulus_and_k():
    m = modulus(55)
    assert m.E_Pa == pytest.approx(32.5 * 0.0980665e6) and m.k == pytest.approx(0.64) and not m.extrapolated
    assert modulus(90).extrapolated


def test_small_strain_limit_equation_9():
    # f = 1.26 E d^-1/2 x^3/2 for small x/d (paper, equation (9), k beta ignored)
    d, s = 5e-3, 0.02
    E, k = modulus(55).E_Pa, modulus(55).k
    f = load_per_length(d, s, 55)
    assert f == pytest.approx(1.26 * E * d**-0.5 * (s * d) ** 1.5, rel=0.03)


def test_contact_pressure_definition():
    d, s = 3.53e-3, 0.2
    assert contact_pressure(d, s, 70) == pytest.approx(load_per_length(d, s, 70) / (d * math.sin(math.acos(0.8))))


def test_reference_defined():
    assert "lindley1966" in load_dataset().references
