"""Phase 2 tests: rule checks (PASS/WARN/FAIL) and message rendering."""

import pytest

from oring_designer.checks import (
    Design,
    Status,
    allowed_extrusion_gap_m,
    check_housing,
    overall_status,
    run_checks,
)
from oring_designer.gland_types import FaceGland, ORing, PistonGland, ThermalState
from oring_designer.i18n import render_check
from oring_designer.loader import load_dataset

MM = 1e-3
DS = load_dataset()


def piston(bore=50.0, piston_d=49.9, groove=43.6, width=4.8, **kw):
    return PistonGland(bore * MM, piston_d * MM, groove * MM, width * MM, **kw)


def design(**kw):
    """Example A (Parker .139-like cross-section) with a sound default configuration."""
    base = dict(
        gland=piston(groove=44.2),  # L = 2.9 mm
        oring=ORing(43.7 * MM, 3.53 * MM),
        seal_material="vmq",
        groove_material="al6061",
        pressure_Pa=50e5,
        hardness_shore_a=70,
    )
    base.update(kw)
    return Design(**base)


def codes(results):
    return {r.code: r for r in results}


def test_sound_design_passes_geometry():
    st, res = run_checks(design(), DS)
    c = codes(res)
    assert c["squeeze_in_band"].status is Status.PASS
    assert c["fill_ok"].status is Status.PASS
    assert c["stretch_ok"].status is Status.PASS
    assert c["extrusion_ok"].status is Status.PASS
    assert c["temp_low_ok"].status is Status.PASS


# --------------------------------------------------------------------------- temperature (K20)


def test_below_low_temp_limit_is_fail_even_with_good_squeeze():
    """SPEC §6.8: below the limit the result is FAIL regardless of squeeze."""
    st, res = run_checks(design(), DS, ThermalState(T_seal_K=210.0, T_housing_K=210.0))
    c = codes(res)
    assert c["temp_low_fail"].status is Status.FAIL
    assert c["temp_low_fail"].limit == pytest.approx(219.15)
    assert overall_status(res) is Status.FAIL


def test_within_band_above_limit_warns():
    _, res = run_checks(design(), DS, ThermalState(T_seal_K=222.0, T_housing_K=222.0))
    assert codes(res)["temp_low_band"].status is Status.WARN


def test_high_temperature_limit_for_vmq():
    _, res = run_checks(design(), DS)
    assert codes(res)["temp_high_ok"].limit == pytest.approx(204 + 273.15)


# --------------------------------------------------------------------------- geometry rules


def test_no_contact_is_fail():
    _, res = run_checks(design(gland=piston(groove=42.5)), DS)  # L = 3.75 > W
    assert codes(res)["squeeze_no_contact"].status is Status.FAIL


def test_low_squeeze_warns_below_band():
    # Example A: L = 3.2 mm -> squeeze 7.4-10.2 % < Parker band 16-23 %
    _, res = run_checks(design(gland=piston(), oring=ORing(43.0 * MM, 3.53 * MM)), DS)
    c = codes(res)
    assert c["squeeze_below_band"].status is Status.WARN
    assert "squeeze_min_abs" not in c  # 0.258 mm > 0.178 mm


def test_absolute_minimum_squeeze_fail():
    # L = 3.45 mm, full eccentricity -> deepest side 3.50 mm vs W_eff ~3.51 mm
    _, res = run_checks(design(gland=piston(groove=43.1), oring=ORing(43.0 * MM, 3.53 * MM)), DS)
    assert codes(res)["squeeze_min_abs"].status is Status.FAIL


def test_fill_over_hard_max_fails():
    _, res = run_checks(design(gland=piston(groove=44.2, width=3.2)), DS)
    assert codes(res)["fill_over_hard_max"].status is Status.FAIL


def test_stretch_over_max_and_negative():
    _, res = run_checks(design(oring=ORing(41.5 * MM, 3.53 * MM)), DS)  # 6.5 %
    assert codes(res)["stretch_over_max"].status is Status.WARN
    _, res = run_checks(design(oring=ORing(44.5 * MM, 3.53 * MM)), DS)
    assert codes(res)["stretch_negative"].status is Status.WARN


def test_face_seating_rules():
    ring = ORing(29.87 * MM, 3.53 * MM)
    ok = FaceGland(27.5 * MM, 36.8 * MM, 2.65 * MM, "internal")
    gap = FaceGland(27.5 * MM, 37.2 * MM, 2.65 * MM, "internal")
    ext = FaceGland(29.95 * MM, 39.25 * MM, 2.65 * MM, "external")
    assert codes(run_checks(design(gland=ok, oring=ring), DS)[1])["face_internal_ok"].status is Status.PASS
    assert codes(run_checks(design(gland=gap, oring=ring), DS)[1])["face_internal_not_seated"].status is Status.WARN
    assert codes(run_checks(design(gland=ext, oring=ring), DS)[1])["face_external_ok"].status is Status.PASS
    assert "extrusion_no_gap" in codes(run_checks(design(gland=ok, oring=ring), DS)[1])


# --------------------------------------------------------------------------- extrusion (K21)


def test_extrusion_lookup_hand_calculation():
    """100 bar = 1450.4 psi between chart points 1000 psi (.0074 in) and 1500 psi (.0039 in)."""
    allowed, curve = allowed_extrusion_gap_m(DS.extrusion_limits, 100e5, 70)
    assert curve == 70
    assert allowed / MM == pytest.approx(0.106436, abs=1e-5)
    silicone, _ = allowed_extrusion_gap_m(DS.extrusion_limits, 100e5, 70, silicone=True)
    assert silicone == pytest.approx(0.4 * allowed)


def test_extrusion_intermediate_hardness_uses_lower_curve():
    assert allowed_extrusion_gap_m(DS.extrusion_limits, 50e5, 85)[1] == 80
    assert allowed_extrusion_gap_m(DS.extrusion_limits, 50e5, 60) == (None, None)


def test_extrusion_below_and_above_chart():
    low, _ = allowed_extrusion_gap_m(DS.extrusion_limits, 1e5, 90)  # 14.5 psi < 100 psi
    assert low == pytest.approx(0.0342 * 0.0254)
    high, _ = allowed_extrusion_gap_m(DS.extrusion_limits, 300e5, 70)  # > 3000 psi
    assert high == 0.0


def test_extrusion_fail_recommends_backup_ring():
    # Example A gap 0.10 mm; silicone at 100 bar allows 0.0426 mm -> FAIL; >103.5 bar warns
    _, res = run_checks(design(pressure_Pa=110e5), DS)
    c = codes(res)
    assert c["extrusion_fail"].status is Status.FAIL
    assert c["backup_investigate"].status is Status.WARN
    assert "destek halkası" in render_check(c["extrusion_fail"])


def test_extrusion_without_hardness_warns():
    _, res = run_checks(design(hardness_shore_a=None), DS)
    assert codes(res)["extrusion_no_hardness"].status is Status.WARN


# --------------------------------------------------------------------------- materials and fluids


def test_lox_with_nbr_fails_and_unknown_warns():
    _, res = run_checks(design(seal_material="nbr", fluid="lox"), DS)
    assert codes(res)["fluid_not_ok"].status is Status.FAIL
    _, res = run_checks(design(fluid="ln2"), DS)
    assert codes(res)["fluid_unknown"].status is Status.WARN


def test_thermoplastic_rule_set_warnings():
    _, res = run_checks(design(seal_material="ptfe"), DS)
    c = codes(res)
    for code in ("tp_split_groove_required", "tp_cold_flow", "tp_spring_energized_recommended",
                 "extrusion_chart_na", "rule_missing"):
        assert c[code].status is Status.WARN


def test_ph_steel_cryo_toughness_warning():
    d = design(groove_material="ph17_4")
    res = check_housing(DS, d, ThermalState(T_housing_K=150.0))
    assert res[0].code == "cryo_toughness_unknown" and res[0].status is Status.WARN
    assert check_housing(DS, d, ThermalState()) == []


def test_hydrogen_flag():
    res = check_housing(DS, design(groove_material="in718", fluid="lh2"), ThermalState())
    assert any(r.code == "hydrogen_embrittlement" for r in res)


def test_extrapolated_thermal_data_flagged():
    d = design(seal_material="ptfe")
    _, res = run_checks(d, DS, ThermalState(T_seal_K=40.0, T_housing_K=40.0))
    assert codes(res)["thermal_data_quality"].status is Status.WARN


# --------------------------------------------------------------------------- messages


SCENARIOS = [
    (design(), ThermalState()),
    (design(), ThermalState(210.0, 210.0)),
    (design(), ThermalState(222.0, 222.0)),
    (design(pressure_Pa=110e5), ThermalState()),
    (design(seal_material="ptfe", fluid="lox"), ThermalState(40.0, 40.0)),
    (design(seal_material="nbr", fluid="lox", hardness_shore_a=None), ThermalState()),
    (design(gland=piston(groove=42.5)), ThermalState()),
    (design(gland=FaceGland(27.5 * MM, 37.2 * MM, 2.65 * MM, "internal"),
            oring=ORing(29.87 * MM, 3.53 * MM)), ThermalState()),
]


@pytest.mark.parametrize("d, state", SCENARIOS)
def test_every_result_renders_in_turkish(d, state):
    _, res = run_checks(d, DS, state)
    for r in res:
        text = render_check(r)
        assert text and "{" not in text
