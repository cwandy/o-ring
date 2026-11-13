"""Phase 3 tests: temperature sweep, separate seal/housing temperatures, plots, UI page."""

from pathlib import Path

import numpy as np
import pytest

from oring_designer.checks import Design, Status, run_checks
from oring_designer.gland_types import ORing, PistonGland, ThermalState
from oring_designer.loader import load_dataset
from oring_designer.sweep import (
    summary_status,
    sweep,
    temperatures,
    to_frame,
    worst_by_family,
)
from oring_designer.viz.plots import clearance_figure, squeeze_fill_figure, thermal_strain_figure
from oring_designer.thermal import build_curve

MM = 1e-3
DS = load_dataset()
APP = Path(__file__).resolve().parents[1] / "app"


def design(**kw):
    base = dict(gland=PistonGland(50.0 * MM, 49.9 * MM, 44.2 * MM, 4.8 * MM),
                oring=ORing(43.7 * MM, 3.53 * MM), seal_material="vmq",
                groove_material="al6061", pressure_Pa=50e5, hardness_shore_a=70)
    base.update(kw)
    return Design(**base)


def test_temperature_grid():
    assert list(temperatures(200, 220, 10)) == [200, 210, 220]
    assert list(temperatures(200, 215, 10)) == [200, 210, 215]
    with pytest.raises(ValueError):
        temperatures(200, 100, 10)


def test_equilibrium_matches_single_point_checks():
    T = temperatures(220, 300, 20)
    pts = sweep(design(), DS, T)
    for p in pts:
        st, res = run_checks(design(), DS, ThermalState(p.T_housing_K, p.T_housing_K, p.T_housing_K))
        assert p.state == st
        assert [r.code for r in p.results] == [r.code for r in res]
        assert p.T_seal_K == p.T_housing_K


def test_lag_mode_offsets_seal_temperature():
    pts = sweep(design(), DS, temperatures(240, 280, 20), mode="lag", delta_T_K=15.0)
    assert all(p.T_seal_K == pytest.approx(p.T_housing_K + 15.0) for p in pts)
    eq = sweep(design(), DS, temperatures(240, 280, 20))
    # a warmer seal is larger, so squeeze is higher than at equilibrium
    assert all(a.state.squeeze_nominal > b.state.squeeze_nominal for a, b in zip(pts, eq))


def test_mating_offset():
    pts = sweep(design(mating_material="ss304"), DS, [250.0], mating_delta_K=-20.0)
    assert pts[0].T_mating_K == 230.0


def test_no_data_points_are_kept_and_low_temp_still_fails():
    """Al 6061 data end at 373.15 K: points above are 'no data'; below 219.15 K the VMQ
    seal FAILs even where geometry exists.

    Inconel 718 data end at 300 K: the point at 320 K is 'no data', yet the seal temperature
    check still runs at the cold point.
    """
    pts = sweep(design(), DS, temperatures(200, 400, 20))
    df = to_frame(pts)
    hot = df.T_housing_K > 373.15
    assert df.loc[hot, "no_data"].notna().all()
    assert df.loc[hot, "squeeze_min"].isna().all()
    assert df.loc[~hot, "no_data"].isna().all()
    cold = next(p for p in pts if p.T_housing_K == 200)
    assert cold.status is Status.FAIL

    inc = sweep(design(groove_material="in718"), DS, [200.0, 320.0])
    assert inc[1].state is None and inc[1].no_data
    assert any(r.code == "temp_low_fail" for r in inc[0].results)


def test_lag_seal_temperature_drives_low_temp_check():
    """Housing at 240 K but seal lagging 30 K colder (210 K) -> FAIL."""
    pts = sweep(design(), DS, [240.0], mode="lag", delta_T_K=-30.0)
    assert any(r.code == "temp_low_fail" for r in pts[0].results)


def test_worst_by_family_and_summary():
    pts = sweep(design(), DS, temperatures(210, 300, 10))
    worst = {w.family: w for w in worst_by_family(pts)}
    assert worst["temp_low"].result.status is Status.FAIL
    assert worst["temp_low"].T_seal_K == 210.0
    assert worst["squeeze"].result.status is Status.WARN  # drops below band when cold
    assert summary_status(pts) is Status.FAIL


def test_frame_columns():
    df = to_frame(sweep(design(), DS, temperatures(250, 300, 25)))
    for col in ("T_housing_K", "T_seal_K", "squeeze_min", "squeeze_max", "fill", "stretch",
                "diametral_clearance_m", "max_extrusion_gap_m", "allowed_gap_m", "status"):
        assert col in df
    assert df["allowed_gap_m"].notna().all()


# --------------------------------------------------------------------------- plots


def test_plots_build():
    df = to_frame(sweep(design(), DS, temperatures(200, 400, 10)))  # > 373 K: no data band
    fig = squeeze_fill_figure(df, "degC", squeeze_band=(0.16, 0.23), squeeze_max=0.30,
                              fill_band=(0.6, 0.85), fill_hard_max=0.9,
                              low_temp_limit_K=219.15, low_temp_band_K=8.0)
    names = {tr.name for tr in fig.data}
    assert len(names) == 4
    assert fig.layout.hovermode == "x unified"
    assert any((s.fillcolor or "").startswith("rgba(82, 81, 78, 0.18") for s in fig.layout.shapes)
    assert len(clearance_figure(df, "K", "in").data) == 3
    curves = {k: build_curve(DS.seal_materials[k].thermal_strain, k) for k in ("ptfe", "nbr")}
    assert len(thermal_strain_figure(curves).data) == 2


# --------------------------------------------------------------------------- UI


def test_check_page_renders_default_design():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP / "pages" / "1_Yuva_Kontrol.py")).run(timeout=60)
    assert not at.exception
    assert len(at.table) >= 2  # point table + sweep table
    texts = " ".join(m.value for m in at.markdown)
    assert "Genel sonuç" in texts


def test_check_page_face_and_inch_units():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP / "pages" / "1_Yuva_Kontrol.py")).run(timeout=60)
    at.sidebar.radio[0].set_value("in").run(timeout=60)
    gland_radio = next(r for r in at.radio if "face" in r.options or "Face (alın)" in r.options)
    gland_radio.set_value("face").run(timeout=60)
    assert not at.exception
