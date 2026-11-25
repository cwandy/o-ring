"""Desktop (Qt) UI smoke tests, run headless (QT_QPA_PLATFORM=offscreen)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DESKTOP = Path(__file__).resolve().parents[1] / "desktop"
try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - missing Qt system libraries
    pytest.skip(f"Qt not available: {exc}", allow_module_level=True)

sys.path.insert(0, str(DESKTOP))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(app):
    import main

    w = main.MainWindow()
    for p in w.pages:
        p._run()
    return w


def _errors(w):
    return [p.error.text() for p in w.pages if not p.error.isHidden()]


def test_all_pages_compute_without_error(window):
    assert _errors(window) == []
    calc = window.pages[0]
    assert calc.cards[0].value.text().endswith("mm")


def test_check_page_iso_class_and_tolerance_analysis(window):
    page = window.pages[1]
    tol = page.dim_tol[("piston", "bore")]
    tol.cls.setCurrentIndex(tol.cls.findData("H8"))
    assert tol.deviations() == pytest.approx((0.0, 39e-6))  # 50 mm: 40 < D <= 50, H8 = +39/0 um
    assert not tol.lo.isEnabled()
    page._run()
    page._run_tol()
    assert page.tol_banner.isHidden() or page.tol_banner.text() == ""
    assert page.tol_summary.rowCount() >= 5
    assert page._report.tolerances["gland.bore_diameter_m"].upper_m == pytest.approx(39e-6)


def test_check_page_all_gland_types(window):
    page = window.pages[1]
    for i in (1, 2, 0):
        page.kind.group.buttons()[i].setChecked(True)
        page._run()
        assert page.error.isHidden(), page.error.text()


def test_default_corner_radius_is_0_3_mm(window):
    page = window.pages[1]
    for kind in ("piston", "rod", "face"):
        assert page.dim_value[(kind, "radius")].si() == pytest.approx(0.3e-3)


def test_units_switch_keeps_si_values(window, app):
    page = window.pages[1]
    v = page.dim_value[("piston", "bore")]
    before = v.si()
    window.len_box.setCurrentText("in")
    assert v.suffix().strip() == "in"
    assert v.si() == pytest.approx(before)
    window.len_box.setCurrentText("mm")
    assert v.value() == pytest.approx(before * 1e3)


def test_size_page_shows_proposal_detail(window):
    page = window.pages[2]
    assert page._ok, "no proposals"
    assert page.table.currentRow() == 0
    assert page.dims.rowCount() >= 5


def test_spring_page_face(window):
    page = window.pages[3]
    page.kind.group.buttons()[2].setChecked(True)
    page._run()
    assert page.error.isHidden(), page.error.text()


def test_check_page_report_and_dxf(window):
    from oring_designer.export.dxf import gland_profile, to_bytes
    from oring_designer.export.report import build_report, to_pdf
    from ui import dataset

    page = window.pages[1]
    page._run()
    assert to_pdf(build_report(page._report, dataset())).startswith(b"%PDF")
    assert b"SECTION" in to_bytes(gland_profile(page._design, "mm", ""))


def test_formulas_dialog_and_details_toggle(window, monkeypatch):
    from PySide6.QtWidgets import QDialog

    import ui

    shown = {}
    monkeypatch.setattr(QDialog, "exec", lambda self: shown.setdefault("dlg", self))
    ui.show_formulas(window)
    from PySide6.QtWidgets import QTextBrowser

    text = shown["dlg"].findChild(QTextBrowser).toPlainText()
    assert "W'² · (D_temas + W') = W² · (ID + W)" in text and "F_basınç" in text
    page = window.pages[0]
    assert page.details_widget.isHidden()
    page.details_btn.setChecked(True)
    assert not page.details_widget.isHidden()
    page.details_btn.setChecked(False)


def test_calc_force_for_ptfe_and_pressure(window):
    page = window.pages[0]
    page.seal.setCurrentIndex(page.seal.findData("ptfe"))
    page._run()
    assert not page.cards[8].isVisibleTo(page)  # force calculation off by default
    page.groups[page.force_title].setChecked(True)
    page._run()
    assert page.error.isHidden(), page.error.text()
    assert page.cards[8].isVisibleTo(page) and page.cards[8].value.text().endswith("kN")
    before = page.cards[8].value.text()
    page.pressure.set_si(100e5)
    page._run()
    assert page.cards[8].value.text() != before  # clamp load includes the pressure load
    page.pressure.set_si(50e5)
    page.seal.setCurrentIndex(page.seal.findData("vmq"))
    page._run()


def test_check_ring_tolerance_auto_as568(window):
    page = window.pages[1]
    page.kind.group.buttons()[0].setChecked(True)
    page._run()
    rid_t = page.ring["piston"][1]
    assert rid_t.deviations()[1] == pytest.approx(0.015 * 0.0254)
    assert rid_t.hi.isHidden() and not rid_t.hi_lab.isHidden()  # fixed value shown as text


def test_spring_catalogue_mode(window):
    page = window.pages[3]
    page.kind.group.buttons()[0].setChecked(True)
    page._run()
    assert page.error.isHidden(), page.error.text()
    assert page.m_groove.si() == pytest.approx(40.6e-3)  # PVA3: 50 - 9.4
    assert "PVA3" in page.cat_banner.text()
    assert page.seal_note.text()  # seal dimensions not entered -> note
    page.kind.group.buttons()[2].setChecked(True)  # face, internal: Variseal HF DVE2 at 50 mm
    page._run()
    assert page.error.isHidden(), page.error.text()
    assert "DVE3" in page.cat_banner.text() and page.m_depth.si() == pytest.approx(4.7e-3)  # 50 mm: DVE3


def test_schematic_input_boxes_linked_both_ways(window):
    page = window.pages[1]
    page.kind.group.buttons()[0].setChecked(True)
    page._run()
    ed = page.schematic._editors["bore"]
    src = page.dim_value[("piston", "bore")]
    assert ed.si() == pytest.approx(src.si())
    ed.set_si(51e-3)
    ed.edited.emit()  # typing on the drawing updates the input on the left
    assert src.si() == pytest.approx(51e-3)
    src.set_si(50e-3)
    page._run()  # and the other way round
    assert page.schematic._editors["bore"].si() == pytest.approx(50e-3)
