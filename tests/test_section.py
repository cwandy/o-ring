"""Phase 6 tests: scaled cross-section drawing (SPEC §9, §11 Faz 6)."""

import math

import pytest

from oring_designer.checks import Design, run_checks
from oring_designer.gland_types import FaceGland, ORing, PistonGland, ThermalState
from oring_designer.loader import load_dataset
from oring_designer.viz.section import compressed_stadium, section_figure

MM = 1e-3
DS = load_dataset()


def piston():
    return Design(gland=PistonGland(50 * MM, 49.9 * MM, 44.2 * MM, 4.8 * MM, 0.25 * MM),
                  oring=ORing(43.7 * MM, 3.53 * MM), seal_material="vmq", groove_material="al6061")


def face(direction="internal"):
    gid, god = (27.5, 36.8) if direction == "internal" else (29.95, 39.25)
    return Design(gland=FaceGland(gid * MM, god * MM, 2.65 * MM, direction),
                  oring=ORing(29.87 * MM, 3.53 * MM), seal_material="vmq", groove_material="al6061")


def state_of(design, T=293.15):
    return run_checks(design, DS, ThermalState(T, T))[0]


# --------------------------------------------------------------------------- stadium approximation


@pytest.mark.parametrize("cs, h", [(3.53, 2.9), (3.53, 2.0), (1.78, 1.3), (6.99, 5.6)])
def test_stadium_preserves_area_and_height(cs, h):
    s = compressed_stadium(cs, h)
    assert s.height == h and not s.capped
    assert s.area == pytest.approx(math.pi * cs**2 / 4, rel=1e-12)
    assert s.width > cs  # flattened ring is wider than the free ring


def test_stadium_uncompressed_and_capped():
    assert compressed_stadium(3.0, 3.2) == compressed_stadium(3.0, 3.0)
    s = compressed_stadium(3.53, 2.0, max_width=4.0)
    assert s.capped and s.width == 4.0


# --------------------------------------------------------------------------- figure


def _traces(fig, col):
    axis = "x" if col == 1 else f"x{col}"
    return [tr for tr in fig.data if tr.xaxis == axis]


def test_three_panels_real_scale():
    d = piston()
    panels = [("T_min", state_of(d, 220.0)), ("T_ref", state_of(d)), ("T_max", None)]
    fig = section_figure(panels, "piston", corner_radius_m=0.25 * MM)
    assert [a.text for a in fig.layout.annotations[:3]] == ["T_min", "T_ref", "T_max"]
    assert len(_traces(fig, 1)) == 4 and len(_traces(fig, 2)) == 4  # parts, free, compressed
    assert len(_traces(fig, 3)) == 0  # no data
    assert any(a.text == "veri yok" for a in fig.layout.annotations)
    # same ranges and 1:1 aspect in every panel
    assert fig.layout.xaxis.range == fig.layout.xaxis2.range == fig.layout.xaxis3.range
    assert fig.layout.yaxis.scaleanchor == "x" and fig.layout.yaxis2.scaleanchor == "x2"
    assert fig.layout.yaxis.scaleratio == 1


@pytest.mark.parametrize("side, attr", [("nominal", "depth_nominal_m"), ("tight", "depth_min_m"),
                                        ("wide", "depth_max_m")])
def test_side_sets_mating_surface(side, attr):
    st = state_of(piston())
    fig = section_figure([("x", st)], "piston", side)
    mating = [tr for tr in fig.data if tr.name == "Karşı parça"][0]
    assert min(mating.y) == pytest.approx(getattr(st, attr) * 1e3)
    comp = [tr for tr in fig.data if tr.name == "Sıkışmış o-ring (yaklaşık)"][0]
    assert max(comp.y) == pytest.approx(getattr(st, attr) * 1e3)


def test_face_ring_against_pressure_side_wall():
    for direction in ("internal", "external"):
        st = state_of(face(direction))
        fig = section_figure([("x", st)], "face", pressure_direction=direction)
        comp = [tr for tr in fig.data if tr.name == "Sıkışmış o-ring (yaklaşık)"][0]
        G = st.gland_width_m * 1e3
        if direction == "internal":
            assert max(comp.x) == pytest.approx(G)
        else:
            assert min(comp.x) == pytest.approx(0.0, abs=1e-12)


def test_labels_show_squeeze_and_fill():
    st = state_of(piston())
    fig = section_figure([("x", st)], "piston", "nominal", "in")
    texts = " ".join(a.text for a in fig.layout.annotations)
    assert f"squeeze {st.squeeze_nominal:.1%}" in texts and f"doluluk {st.fill:.1%}" in texts
    assert f"L {st.depth_nominal_m / 0.0254:.4f}" in texts
    assert "[in]" in fig.layout.title.text
