"""Phase 4 tests: worst-case, RSS, Monte Carlo (SPEC §7, §11 Faz 4)."""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from oring_designer.checks import Design
from oring_designer.gland_types import FaceGland, ORing, PistonGland, ThermalState
from oring_designer.loader import load_dataset
from oring_designer.tolerance import (
    DEFAULT_MC_SAMPLES,
    Tolerance,
    monte_carlo,
    rss,
    toleranceable_fields,
    worst_case,
)
from oring_designer.viz.plots import mc_histogram

IN = 0.0254
MM = 1e-3
DS = load_dataset()
APP = Path(__file__).resolve().parents[1] / "app"

# Parker Design Chart 4-3, .139 cross-section face gland: L = .101-.107, W = .139 +/- .004
L_NOM, L_TOL, W_NOM, W_TOL = 0.104 * IN, 0.003 * IN, 0.139 * IN, 0.004 * IN


def face_design():
    ring = ORing(29.87 * MM, W_NOM)
    god = (29.87 * MM + 2 * W_NOM) - 0.08 * MM  # internal pressure: groove OD just below ring OD
    gland = FaceGland(groove_id_m=27.0 * MM, groove_od_m=god, groove_depth_m=L_NOM,
                      pressure_direction="internal")
    return Design(gland=gland, oring=ring, seal_material="vmq", groove_material="al6061")


FACE_TOLS = {"gland.groove_depth_m": Tolerance.symmetric(L_TOL), "oring.cs_m": Tolerance.symmetric(W_TOL)}


def piston_design():
    return Design(gland=PistonGland(50.0 * MM, 49.9 * MM, 44.2 * MM, 4.8 * MM),
                  oring=ORing(43.7 * MM, 3.53 * MM), seal_material="vmq",
                  groove_material="al6061", pressure_Pa=50e5, hardness_shore_a=70)


PISTON_TOLS = {
    "gland.bore_diameter_m": Tolerance(0, 0.05 * MM),
    "gland.piston_diameter_m": Tolerance(-0.05 * MM, 0),
    "gland.groove_diameter_m": Tolerance.symmetric(0.025 * MM),
    "oring.id_m": Tolerance.symmetric(0.3 * MM),
    "oring.cs_m": Tolerance.symmetric(0.1 * MM),
}


# --------------------------------------------------------------------------- tolerance model


def test_tolerance_model():
    t = Tolerance(-0.02, 0.04)
    assert t.mid_m == pytest.approx(0.01) and t.sigma_m == pytest.approx(0.01)
    assert Tolerance.symmetric(-0.1) == Tolerance(-0.1, 0.1)
    with pytest.raises(ValueError):
        Tolerance(0.1, -0.1)


def test_toleranceable_fields():
    assert toleranceable_fields(piston_design()) == [
        "gland.bore_diameter_m", "gland.piston_diameter_m", "gland.groove_diameter_m",
        "gland.groove_width_m", "gland.corner_radius_m", "oring.id_m", "oring.cs_m"]
    assert "gland.groove_depth_m" in toleranceable_fields(face_design())
    with pytest.raises(ValueError):
        worst_case(piston_design(), {"gland.groove_depth_m": Tolerance(0, 1e-5)}, DS)


# --------------------------------------------------------------------------- worst case


def test_worst_case_reproduces_parker_face_chart():
    """Corners of L and W give Parker's 20-30 % (.028-.042 in) squeeze range."""
    wc = worst_case(face_design(), FACE_TOLS, DS)
    assert len(wc.table) == 1 + 4
    lo = (W_NOM - W_TOL - (L_NOM + L_TOL)) / (W_NOM - W_TOL)
    hi = (W_NOM + W_TOL - (L_NOM - L_TOL)) / (W_NOM + W_TOL)
    assert wc.output_min["squeeze_min"] == pytest.approx(lo, abs=1e-12)  # 20.7 %
    assert wc.output_max["squeeze_max"] == pytest.approx(hi, abs=1e-12)  # 29.4 %
    assert 0.20 <= lo and hi <= 0.30  # inside Parker's tabulated 20-30 %


def test_worst_case_over_states_and_status():
    states = [ThermalState(), ThermalState(250.0, 250.0), ThermalState(300.0, 300.0)]
    wc = worst_case(piston_design(), PISTON_TOLS, DS, states)
    assert len(wc.table) == len(states) * (1 + 2**5)
    assert set(wc.table.T_housing_K) == {293.15, 250.0, 300.0}
    # bore +0.05 / piston -0.05 widen the gap to 0.2 mm > allowed 0.113 mm
    assert wc.family_status["extrusion"].value == "FAIL"
    result, corner = wc.worst_results["extrusion"]
    assert result.code == "extrusion_fail"
    assert corner["gland.bore_diameter_m"] == pytest.approx(50.05 * MM)


# --------------------------------------------------------------------------- RSS


def test_rss_matches_analytic_linearisation():
    """squeeze = 1 - L/W: ds/dL = -1/W, ds/dW = L/W^2, sigma = band/6."""
    r = rss(face_design(), FACE_TOLS, DS)
    sL, sW = 2 * L_TOL / 6, 2 * W_TOL / 6
    expected = math.hypot(sL / W_NOM, L_NOM * sW / W_NOM**2)
    assert r.mean["squeeze_min"] == pytest.approx(1 - L_NOM / W_NOM)
    assert r.sigma["squeeze_min"] == pytest.approx(expected, rel=1e-5)
    assert r.sensitivities.loc["squeeze_min", "gland.groove_depth_m"] == pytest.approx(-1 / W_NOM, rel=1e-5)


def test_rss_uses_middle_of_asymmetric_band():
    tols = {"gland.groove_depth_m": Tolerance(0, 2 * L_TOL)}
    r = rss(face_design(), tols, DS)
    assert r.mean["squeeze_min"] == pytest.approx(1 - (L_NOM + L_TOL) / W_NOM)


# --------------------------------------------------------------------------- Monte Carlo


def test_monte_carlo_seed_reproducible():
    a = monte_carlo(face_design(), FACE_TOLS, DS, n=500, seed=7)
    b = monte_carlo(face_design(), FACE_TOLS, DS, n=500, seed=7)
    c = monte_carlo(face_design(), FACE_TOLS, DS, n=500, seed=8)
    pd.testing.assert_frame_equal(a.samples, b.samples)
    assert not a.samples.equals(c.samples)


def test_monte_carlo_normal_statistics():
    mc = monte_carlo(face_design(), FACE_TOLS, DS, n=4000, seed=1)
    x = mc.samples["x:gland.groove_depth_m"]
    assert x.mean() == pytest.approx(L_NOM, abs=4 * (L_TOL / 3) / math.sqrt(4000))
    assert x.std() == pytest.approx(L_TOL / 3, rel=0.05)
    r = rss(face_design(), FACE_TOLS, DS)
    assert mc.samples["squeeze_min"].std() == pytest.approx(r.sigma["squeeze_min"], rel=0.06)


def test_monte_carlo_uniform_inside_worst_case():
    mc = monte_carlo(face_design(), FACE_TOLS, DS, n=2000, distribution="uniform", seed=3)
    wc = worst_case(face_design(), FACE_TOLS, DS)
    x = mc.samples["x:oring.cs_m"]
    assert x.min() >= W_NOM - W_TOL and x.max() <= W_NOM + W_TOL
    s = mc.samples["squeeze_min"]
    assert s.min() >= wc.output_min["squeeze_min"] - 1e-12
    assert s.max() <= wc.output_max["squeeze_min"] + 1e-12


def test_monte_carlo_rates_default_n():
    assert DEFAULT_MC_SAMPLES == 20_000
    mc = monte_carlo(piston_design(), PISTON_TOLS, DS, seed=1)
    assert mc.n == 20_000 and len(mc.samples) == 20_000
    assert np.allclose(mc.family_rates.sum(axis=1), 1.0)
    assert sum(mc.overall_rates.values()) == pytest.approx(1.0)
    assert mc.family_rates.loc["extrusion", "FAIL"] > 0.99  # mean gap 0.15 mm > 0.113 mm


def test_histogram_builds():
    mc = monte_carlo(face_design(), FACE_TOLS, DS, n=300, seed=1)
    fig = mc_histogram(mc.samples["squeeze_min"], "Squeeze", [(0.20, "bant alt")],
                       [(0.207, 0.294, "worst-case")])
    assert len(fig.data) == 3 and len(fig.layout.shapes) == 3  # histogram + 2 legend entries


def test_tolerance_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP / "pages" / "2_Tolerans_Analizi.py")).run(timeout=120)
    assert not at.exception
    assert len(at.table) >= 3
    assert any("GEÇER" in m.label for m in at.metric)
