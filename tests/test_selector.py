"""Phase 5 tests: standard size tables and size/gland proposal (SPEC §8, §11 Faz 5)."""

from pathlib import Path

import pytest

from oring_designer.checks import Status
from oring_designer.loader import load_dataset, load_standard_sizes
from oring_designer.selector import SelectorInput, candidates, design_gland, proposal_table, select

IN = 0.0254
MM = 1e-3
DS = load_dataset()
SIZES = load_standard_sizes()
APP = Path(__file__).resolve().parents[1] / "app"


# --------------------------------------------------------------------------- tables


def test_standard_tables_loaded():
    counts = SIZES.standard.value_counts().to_dict()
    assert counts == {"AS568": 349, "ISO3601-1 A": 360, "ISO3601-1 G": 280}
    assert (SIZES.id_tol_m > 0).all() and (SIZES.cs_tol_m > 0).all()


@pytest.mark.parametrize(
    "size, id_in, id_tol, cs_in, cs_tol",
    [
        ("AS568-001", 0.029, 0.004, 0.040, 0.003),
        ("AS568-133", 1.799, 0.015, 0.103, 0.003),  # Parker Table 9-1
        ("AS568-201", 0.171, 0.005, 0.139, 0.004),  # handbook typo .055 corrected
        ("AS568-452", 11.475, 0.060, 0.275, 0.006),  # nominal printed '11 1/2'
        ("AS568-475", 25.940, 0.120, 0.275, 0.006),
    ],
)
def test_as568_rows(size, id_in, id_tol, cs_in, cs_tol):
    r = SIZES[SIZES["size"] == size].iloc[0]
    assert r.id_m == pytest.approx(id_in * IN) and r.id_tol_m == pytest.approx(id_tol * IN)
    assert r.cs_m == pytest.approx(cs_in * IN) and r.cs_tol_m == pytest.approx(cs_tol * IN)


def test_as568_inch_metric_consistency():
    """Every AS568 row: inch and metric columns of Parker Table 9-1 agree (except noted rows)."""
    import pandas as pd

    df = pd.read_csv(Path(DS.data_dir) / "standards" / "as568.csv", comment="#", dtype={"dash": str})
    assert (abs(df.cs_in * 25.4 - df.cs_mm) <= 0.02).all()
    ok = df.notes.isna()
    assert (abs(df.id_tol_in * 25.4 - df.id_tol_mm)[ok] <= 0.02).all()


@pytest.mark.parametrize(
    "size, tol",
    [("4.5 x 2.65 A", 0.13), ("112 x 7.00 A", 0.74), ("109 x 3.55 A", 0.72), ("400 x 7.00 A", 2.29)],
)
def test_iso_series_a_rows(size, tol):
    """Parker Table 9-5 spot checks (incl. 'x' availability marks)."""
    r = SIZES[SIZES["size"] == size].iloc[0]
    assert r.id_tol_m == pytest.approx(tol * MM)


def test_iso_unavailable_combination_absent():
    assert SIZES[SIZES["size"] == "109 x 1.80 A"].empty  # no 'x' in the handbook


# --------------------------------------------------------------------------- candidates


def base(**kw):
    d = dict(gland_type="piston", nominal_diameter_m=50 * MM, seal_material="nbr",
             groove_material="al6061", pressure_Pa=50e5)
    d.update(kw)
    return SelectorInput(**d)


def test_piston_candidates_are_stretched_onto_groove():
    inp = base(cs_min_m=2.5 * MM, cs_max_m=3.6 * MM)
    c = candidates(inp, DS, SIZES)
    assert len(c) > 0
    assert ((c.window_key > 0) & (c.window_key <= 0.05)).all()
    assert c.cs_m.between(2.5 * MM, 3.6 * MM).all()


def test_face_internal_candidates_seat_on_groove_od():
    inp = base(gland_type="face", nominal_diameter_m=36.8 * MM)
    c = candidates(inp, DS, SIZES)
    od = c.id_m + 2 * c.cs_m
    assert ((od >= 36.8 * MM) & ((od - 36.8 * MM) / od <= 0.01)).all()


def test_no_candidates():
    assert select(base(cs_min_m=20 * MM, cs_max_m=21 * MM), DS, SIZES) == []


def test_thermoplastic_not_supported():
    with pytest.raises(ValueError):
        select(base(seal_material="ptfe"), DS, SIZES)


# --------------------------------------------------------------------------- comparison with Parker


def _row(size):
    return SIZES[SIZES["size"] == size].iloc[0]


def test_face_depth_matches_parker_design_chart_4_3():
    """.139 face gland at room temperature: Parker L = .101-.107 in."""
    inp = base(gland_type="face", nominal_diameter_m=(29.74 * MM + 2 * 0.139 * IN) - 0.05 * MM)
    p = design_gland(inp, DS, _row("AS568-217"))
    assert p.error is None
    assert 0.101 * IN <= p.depth_m <= 0.107 * IN


def test_piston_depth_matches_parker_design_chart_4_2():
    """.139 male gland at room temperature: Parker L = .111-.113 in (squeeze 16-23 %)."""
    ring = _row("AS568-224")  # I.D. 1.734 in
    bore = ring.id_m + 0.02 * ring.id_m + 2 * 0.112 * IN  # ~2 % stretch
    p = design_gland(base(nominal_diameter_m=bore, pressure_Pa=0.0), DS, ring)
    assert p.error is None
    assert 0.109 * IN <= p.depth_m <= 0.114 * IN


# --------------------------------------------------------------------------- proposal quality


def test_proposals_ranked_and_verified():
    inp = base(seal_material="vmq", T_min_K=240, T_max_K=300, cs_min_m=2.5 * MM, cs_max_m=3.6 * MM)
    props = select(inp, DS, SIZES)
    assert props
    rank = {Status.PASS: 0, Status.WARN: 1, Status.FAIL: 2}
    keys = [(rank[p.status], p.score) for p in props if p.error is None]
    assert keys == sorted(keys)
    for p in props:
        assert p.wc.output_max["fill"] <= 0.85 + 1e-9  # width chosen for fill_max
        assert set(p.wc.table.T_housing_K) >= {240.0, 300.0, 293.15}
        assert p.tolerances["oring.cs_m"].upper_m == pytest.approx(_row(p.size).cs_tol_m)
        # rounded to 0.01 mm groove diameter and 0.05 mm width
        g = p.design.gland
        assert round(g.groove_diameter_m / 1e-5) == pytest.approx(g.groove_diameter_m / 1e-5, abs=1e-6)
        assert round(g.groove_width_m / 5e-5) == pytest.approx(g.groove_width_m / 5e-5, abs=1e-6)
    top = props[0]
    lo, hi = top.wc.output_min["squeeze_min"], top.wc.output_max["squeeze_max"]
    assert abs((lo + hi) / 2 - sum(top.band) / 2) < 0.01  # centred on Parker band
    df = proposal_table(props)
    assert list(df["size"]) == [p.size for p in props]


def test_missing_thermal_data_reported_not_raised():
    inp = base(groove_material="ph17_4", T_min_K=200, T_max_K=300, cs_min_m=3.5 * MM, cs_max_m=3.6 * MM)
    props = select(inp, DS, SIZES)
    assert props and all(p.error and p.status is None for p in props)


def test_size_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP / "pages" / "3_Olcu_Oner.py")).run(timeout=180)
    assert not at.exception
    assert len(at.table) >= 1
