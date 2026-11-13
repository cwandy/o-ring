"""Phase 8 tests: DXF gland profile and design report (SPEC §11 Faz 8)."""

import io
import math
import re
import zipfile

import ezdxf
import pytest

from oring_designer.checks import Design
from oring_designer.export.dxf import gland_profile, to_bytes
from oring_designer.export.report import ReportInput, build_report, to_markdown, to_markdown_zip, to_pdf
from oring_designer.gland_types import FaceGland, ORing, PistonGland, RodGland
from oring_designer.loader import load_dataset
from oring_designer.tolerance import Tolerance

MM = 1e-3
DS = load_dataset()


def piston(r=0.25):
    return Design(gland=PistonGland(50 * MM, 49.9 * MM, 44.2 * MM, 4.8 * MM, r * MM),
                  oring=ORing(43.7 * MM, 3.53 * MM), seal_material="vmq", groove_material="al6061",
                  pressure_Pa=50e5, hardness_shore_a=70)


def rod():
    return Design(gland=RodGland(20 * MM, 20.1 * MM, 26 * MM, 4.8 * MM, 0.25 * MM),
                  oring=ORing(19.8 * MM, 3.53 * MM), seal_material="vmq", groove_material="ss304")


def face():
    return Design(gland=FaceGland(27.5 * MM, 36.8 * MM, 2.65 * MM, "internal", 0.25 * MM),
                  oring=ORing(29.87 * MM, 3.53 * MM), seal_material="vmq", groove_material="al6061")


def reread(design, unit="mm"):
    data = to_bytes(gland_profile(design, unit, "test"))
    return ezdxf.read(io.StringIO(data.decode("utf-8")))


# --------------------------------------------------------------------------- DXF


def test_dxf_piston_geometry():
    doc = reread(piston())
    assert doc.header["$INSUNITS"] == 4
    assert {"GROOVE", "MATING", "ORING", "DIMS", "NOTES"} <= {l.dxf.name for l in doc.layers}
    msp = doc.modelspace()
    poly = msp.query("LWPOLYLINE[layer=='GROOVE']")[0]
    ys = {round(p[1], 6) for p in poly.get_points("xyb")}
    assert {22.1, 24.95} <= ys  # groove bottom 44.2/2, piston surface 49.9/2
    bulges = [p[2] for p in poly.get_points("xyb") if p[2] != 0]
    assert len(bulges) == 2 and all(abs(abs(b) - math.tan(math.pi / 8)) < 1e-9 for b in bulges)
    line = msp.query("LINE[layer=='MATING']")[0]
    assert line.dxf.start.y == pytest.approx(25.0)  # bore 50 / 2
    circle = msp.query("CIRCLE[layer=='ORING']")[0]
    assert circle.dxf.radius == pytest.approx(3.53 / 2)
    assert circle.dxf.center.y == pytest.approx(22.1 + 3.53 / 2)
    assert len(msp.query("DIMENSION")) == 3


def test_dxf_inch_units_and_no_radius():
    doc = reread(piston(r=0.0), "in")
    assert doc.header["$INSUNITS"] == 1
    poly = doc.modelspace().query("LWPOLYLINE")[0]
    assert all(p[2] == 0 for p in poly.get_points("xyb"))
    assert min(p[1] for p in poly.get_points("xyb")) == pytest.approx(22.1 / 25.4)


def test_dxf_rod_and_face():
    msp = reread(rod()).modelspace()
    circle = msp.query("CIRCLE")[0]
    assert circle.dxf.center.y == pytest.approx(10.0 + 3.53 / 2)  # ring on the rod
    msp = reread(face()).modelspace()
    circle = msp.query("CIRCLE")[0]
    assert circle.dxf.center.x == pytest.approx(36.8 / 2 - 3.53 / 2)  # against the O.D. wall
    assert circle.dxf.center.y == pytest.approx(-2.65 + 3.53 / 2)
    assert len(msp.query("DIMENSION")) == 2


# --------------------------------------------------------------------------- report


@pytest.fixture(scope="module")
def report():
    tols = {"gland.bore_diameter_m": Tolerance.symmetric(0.025 * MM),
            "oring.cs_m": Tolerance.symmetric(0.1 * MM)}
    inp = ReportInput(piston(), T_min_K=200, T_max_K=320, T_step_K=10, tolerances=tols,
                      mc_samples=500, oring_label="örnek")
    return build_report(inp, DS)


def test_report_content(report):
    labels = dict(report.inputs)
    assert labels["Conta malzemesi"] == "VMQ (silikon)" and labels["Basınç"] == "50.00 bar"
    assert labels["O-ring (iç çap × kesit)"].startswith("örnek: 43.700 mm")
    assert report.point_status == "GEÇER"
    assert report.sweep_status == "KALIR"  # below -54 °C in the sweep
    assert set(report.figures) == {"squeeze_fill.png", "clearance.png", "section.png"}
    assert all(png.startswith(b"\x89PNG") for png in report.figures.values())
    refs = {r[0] for r in report.sources}
    assert {"parker_ord5700", "nist_trc_al6061", "nbs_mono29"} <= refs
    assert report.verify == []  # VMQ + Al 6061 data are all sourced
    assert len(report.assumptions) == 8
    assert len(report.tolerance_rows) == 5


def test_markdown_and_zip(report):
    md = to_markdown(report)
    for h in ("# O-Ring Yuva Tasarım Raporu", "## 1. Girdiler", "## 6. Kullanılan veriler ve kaynaklar",
              "![section](figures/section.png)"):
        assert h in md
    z = zipfile.ZipFile(io.BytesIO(to_markdown_zip(report)))
    assert set(z.namelist()) == {"rapor.md", "figures/squeeze_fill.png", "figures/clearance.png",
                                 "figures/section.png"}


def test_pdf(report):
    pdf = to_pdf(report)
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type /Page\b", pdf)) >= 2


def test_face_report_and_missing_data():
    rep = build_report(ReportInput(face(), T_min_K=250, T_max_K=290), DS)
    assert "clearance.png" not in rep.figures and rep.tolerance_rows == []
    ph = Design(gland=piston().gland, oring=piston().oring, seal_material="vmq", groove_material="ph17_4")
    rep = build_report(ReportInput(ph, T_min_K=150, T_max_K=290, T_step_K=20), DS)
    assert rep.point_rows
    assert any("ph17_4" in v for v in rep.verify)  # Clark-method estimate below 200 K is listed
    assert to_pdf(rep).startswith(b"%PDF")
