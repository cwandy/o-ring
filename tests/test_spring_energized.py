"""Phase 7 tests: thermoplastic rule set overrides and spring-energized seal mode."""

from pathlib import Path

import pytest

from oring_designer.checks import Design, Status, run_checks, with_rule_overrides
from oring_designer.gland_types import ORing, PistonGland, ThermalState
from oring_designer.loader import load_dataset
from oring_designer.models import DataQuality
from oring_designer.spring_energized import (
    SeDesign, SeGland, SeLimits, SeSeal, check, evaluate, se_frame, se_sweep,
)
from oring_designer.sweep import temperatures, worst_by_family
from oring_designer.thermal import scale_factor

MM = 1e-3
DS = load_dataset()
APP = Path(__file__).resolve().parents[1] / "app"


def se(kind="piston", limits=SeLimits(), jacket="ptfe", groove="ss304", **kw):
    if kind == "piston":
        g = SeGland("piston", 50 * MM, 49.9 * MM, 43.6 * MM, 4.5 * MM, **kw)
        seal = SeSeal(3.4 * MM, 4.0 * MM, 43.6 * MM)
    elif kind == "rod":
        g = SeGland("rod", 20 * MM, 20.1 * MM, 26.4 * MM, 4.5 * MM, **kw)
        seal = SeSeal(3.4 * MM, 4.0 * MM, 26.4 * MM)
    else:
        direction = kw.pop("pressure_direction", "internal")
        wall = 40 * MM if direction == "internal" else 30 * MM
        g = SeGland("face", 0, 0, wall, 4.5 * MM, 3.2 * MM, direction, **kw)
        seal = SeSeal(3.4 * MM, 4.0 * MM, wall)
    return SeDesign(g, seal, limits, jacket, groove)


def codes(results):
    return {r.code: r for r in results}


# --------------------------------------------------------------------------- geometry


def test_piston_at_reference_hand_calculation():
    st = evaluate(se(), DS, ThermalState())
    assert st.depth_nominal_m / MM == pytest.approx(3.2)  # (50 - 43.6) / 2
    assert st.compression_min_m / MM == pytest.approx(3.4 - 3.25)  # wide side L + c/2
    assert st.compression_max_m / MM == pytest.approx(3.4 - 3.15)  # tight side L - c/2
    assert st.max_extrusion_gap_m / MM == pytest.approx(0.1)
    assert st.axial_clearance_m / MM == pytest.approx(0.5)
    assert st.static_fit == pytest.approx(0.0, abs=1e-15)
    assert st.data_quality is None


def test_piston_at_77K_uses_jacket_and_housing_strain():
    k_p, k_s = scale_factor(DS.curve("ptfe"), 77.0), scale_factor(DS.curve("ss304"), 77.0)
    st = evaluate(se(), DS, ThermalState(77.0, 77.0))
    L = (50 - 43.6) / 2 * k_s
    assert st.compression_min_m / MM == pytest.approx(3.4 * k_p - (L + 0.05 * k_s), rel=1e-12)
    assert st.static_fit == pytest.approx(k_s / k_p - 1, rel=1e-12)
    assert st.static_fit > 0  # PTFE shrinks onto the groove bottom
    assert st.compression_min_m < 0.15 * MM  # PTFE contracts ~4x more than steel: less compression


def test_rod_seal_loosens_in_groove_when_cold():
    st = evaluate(se("rod"), DS, ThermalState(77.0, 77.0))
    assert st.static_fit < 0
    assert codes(check(se("rod"), st))["se_fit_loose"].status is Status.WARN


@pytest.mark.parametrize("direction, sign", [("internal", -1), ("external", +1)])
def test_face_static_fit_direction(direction, sign):
    st = evaluate(se("face", pressure_direction=direction), DS, ThermalState(77.0, 77.0))
    assert st.max_extrusion_gap_m is None
    assert sign * st.static_fit > 0  # internal: seal O.D. pulls away from the groove O.D.


# --------------------------------------------------------------------------- limits (K23)


def test_missing_catalog_limits_warn():
    res = codes(check(se(), evaluate(se(), DS, ThermalState())))
    for c in ("se_compression_min_no_limit", "se_compression_max_no_limit", "se_gap_no_limit"):
        assert res[c].status is Status.WARN and res[c].data_quality is DataQuality.PLACEHOLDER
    assert res["se_axial_ok"].status is Status.PASS


def test_catalog_limits_pass_and_fail():
    lim = SeLimits(compression_min_m=0.10 * MM, compression_max_m=0.30 * MM,
                   extrusion_gap_max_m=0.08 * MM, axial_clearance_min_m=0.6 * MM, static_fit_min=0.0)
    res = codes(check(se(limits=lim), evaluate(se(limits=lim), DS, ThermalState())))
    assert res["se_compression_min_ok"].status is Status.PASS
    assert res["se_compression_max_ok"].status is Status.PASS
    assert res["se_gap_fail"].status is Status.FAIL  # 0.10 > 0.08
    assert res["se_axial_fail"].status is Status.FAIL  # 0.5 < 0.6
    assert res["se_fit_ok"].data_quality is DataQuality.USER_INPUT


def test_sweep_cryogenic_range():
    lim = SeLimits(compression_min_m=0.10 * MM, compression_max_m=0.30 * MM, extrusion_gap_max_m=0.12 * MM)
    pts = se_sweep(se(limits=lim), DS, temperatures(77, 300, 10))
    worst = {w.family: w for w in worst_by_family(pts)}
    assert worst["se_compression_min"].result.status is Status.FAIL  # loses compression when cold
    assert worst["se_compression_min"].T_housing_K == 77.0
    df = se_frame(pts)
    assert df.compression_min_m.is_monotonic_increasing  # warmer -> more compression


def test_sweep_no_data_and_extrapolated():
    pts = se_sweep(se(jacket="pctfe"), DS, [250.0, 350.0])
    assert pts[1].state is None and pts[1].no_data
    pts = se_sweep(se(), DS, [40.0])
    assert "thermal_data_quality" in codes(pts[0].results)  # PTFE < 80 K extrapolated by source


# --------------------------------------------------------------------------- thermoplastic O-ring rules


def tp_design():
    return Design(gland=PistonGland(50 * MM, 49.9 * MM, 44.2 * MM, 4.8 * MM),
                  oring=ORing(43.7 * MM, 3.53 * MM), seal_material="ptfe", groove_material="al6061")


def test_thermoplastic_limits_missing_then_user_input():
    _, res = run_checks(tp_design(), DS)
    missing = {r.params.get("rule") for r in res if r.code == "rule_missing"}
    assert {"squeeze_max", "fill_hard_max"} <= missing
    ds2 = with_rule_overrides(DS, "thermoplastic", "static_radial",
                              {"squeeze_max": 0.15, "fill_max": 0.80, "fill_hard_max": 0.90})
    _, res2 = run_checks(tp_design(), ds2)
    c = codes(res2)
    assert c["squeeze_over_max"].data_quality is DataQuality.USER_INPUT  # 18.9 % > 15 %
    assert {r.params["rule"] for r in res2 if r.code == "rule_missing"} == {"stretch_max"}
    for code in ("tp_split_groove_required", "tp_cold_flow", "tp_spring_energized_recommended"):
        assert c[code].status is Status.WARN
    assert DS.rule_set("thermoplastic", "static_radial").squeeze_max.value is None  # unchanged


def test_spring_energized_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP / "pages" / "4_Yayli_Conta.py")).run(timeout=120)
    assert not at.exception
    assert len(at.table) >= 1
