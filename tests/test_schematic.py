"""Dimensioned gland schematic (SVG) and the page layout that shows it next to the inputs."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from oring_designer.i18n import t
from oring_designer.viz.schematic import gland_schematic

PAGES = Path(__file__).resolve().parents[1] / "app" / "pages"


def _texts(svg: str) -> list[str]:
    root = ET.fromstring(svg)
    return [el.text or "" for el in root.iter("{http://www.w3.org/2000/svg}text")]


@pytest.mark.parametrize("kind", ["piston", "rod", "face"])
@pytest.mark.parametrize("seal", ["oring", "spring"])
@pytest.mark.parametrize("direction", ["internal", "external"])
def test_schematic_is_valid_svg_with_values(kind, seal, direction):
    dims = {"bore": "50.000", "piston": "49.900", "rod": "20.000", "throat": "20.100", "groove_d": "44.200",
            "groove_id": "27.500", "groove_od": "36.800", "width": "4.800", "depth": "2.900",
            "radius": "0.300", "cs": "3.530", "gap": "0.100", "ring_id": "43.700", "seal_h": "3.400",
            "seal_b": "4.000"}
    texts = _texts(gland_schematic(kind, dims, "mm", direction, seal))
    joined = " ".join(texts)
    assert "L 2.900" in joined and "G 4.800" in joined
    assert t("schematic.not_to_scale") in texts
    assert any("43.700 mm" == s for s in texts)  # legend-only key with unit


def test_schematic_omits_unknown_and_marks_pending():
    texts = _texts(gland_schematic("piston", {"bore": None, "depth": "…", "cs": "3.530"}, "in"))
    assert not any(s.startswith("ØA") for s in texts)
    assert "…" in texts  # pending value shown without a unit
    assert "3.530 in" in texts


def test_schematic_rod_groove_symbol_and_bad_kind():
    texts = _texts(gland_schematic("rod", {"groove_d": "26.000"}, "mm"))
    assert "ØF 26.000" in texts
    with pytest.raises(ValueError):
        gland_schematic("dynamic", {}, "mm")


@pytest.mark.parametrize("page,radio_label,options", [
    ("0_Yuva_Hesaplayici.py", None, None),
    ("1_Yuva_Kontrol.py", "ui.gland_type", ["piston", "rod", "face"]),
    ("3_Olcu_Oner.py", "ui.gland_type", ["piston", "rod", "face"]),
    ("4_Yayli_Conta.py", "ui.gland_type", ["piston", "rod", "face"]),
])
def test_pages_render_schematic(page, radio_label, options):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGES / page)).run(timeout=120)
    assert not at.exception, at.exception
    assert at.get("image"), "schematic image missing"
    if radio_label:
        radio = next(r for r in at.radio if r.label == t(radio_label))
        for opt in options:
            radio.set_value(opt)
            at.run(timeout=120)
            assert not at.exception, (opt, at.exception)
            assert at.get("image")
            radio = next(r for r in at.radio if r.label == t(radio_label))


def test_tolerance_page_renders_schematic():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGES / "2_Tolerans_Analizi.py")).run(timeout=120)
    assert not at.exception, at.exception
    assert at.get("image")


def test_backup_rings_drawn():
    from oring_designer.viz.schematic import BACKUP, gland_schematic

    dims = {"bore": "50", "width": "4.8", "cs": "3.53"}
    for kind in ("piston", "rod"):
        assert BACKUP not in gland_schematic(kind, dims, "mm")
        assert gland_schematic(kind, dims, "mm", backup=1).count(BACKUP) == 1
        assert gland_schematic(kind, dims, "mm", backup=2).count(BACKUP) == 2
