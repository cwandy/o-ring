"""DXF gland profile (SPEC §11 Faz 8).

Axial half-section at the reference temperature in true radius coordinates, in the chosen
length unit (mm or inch, DXF $INSUNITS set accordingly):

* piston / rod: x = axial position (0 .. groove width G), y = radius;
* face: x = radius, y = axial position (flange face at y = 0, groove bottom at -depth).

Layers: GROOVE (groove part outline incl. corner radii as polyline arcs), MATING (mating
surface), ORING (free O-ring cross-section, nominal), DIMS (dimensions), NOTES (text).
The O-ring is drawn at its installed position (on the groove bottom for piston glands, on
the rod for rod glands, against the pressure-side wall for face glands) with its nominal
free cross-section; compression is not drawn.
"""

from __future__ import annotations

import io
import math

import ezdxf
from ezdxf.document import Drawing

from ..checks import Design
from ..gland_types import FaceGland, PistonGland, RodGland

SCALE = {"mm": 1e3, "in": 1 / 0.0254}
INSUNITS = {"mm": 4, "in": 1}
LAYERS = {"GROOVE": 7, "MATING": 8, "ORING": 5, "DIMS": 3, "NOTES": 2}


def _bulge(start, end, center) -> float:
    """Polyline bulge for the arc from start to end around center (shortest sweep)."""
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    return math.tan(sweep / 4)


def _u_profile(x0: float, x1: float, surface: float, bottom: float, r: float, land: float,
               ) -> list[tuple[float, float, float]]:
    """Groove outline (x, y, bulge) from the left land to the right land.

    ``surface``: y of the groove-part surface; ``bottom``: y of the groove bottom (below or
    above the surface); ``r``: bottom corner radius.
    """
    s = 1.0 if bottom < surface else -1.0  # groove opens upward (+1) or downward (-1)
    r = min(r, (x1 - x0) / 2, abs(surface - bottom))
    pts: list[tuple[float, float, float]] = [(x0 - land, surface, 0.0), (x0, surface, 0.0)]
    if r > 0:
        a, b, c = (x0, bottom + s * r), (x0 + r, bottom), (x0 + r, bottom + s * r)
        pts.append((*a, _bulge(a, b, c)))
        a2, b2, c2 = (x1 - r, bottom), (x1, bottom + s * r), (x1 - r, bottom + s * r)
        pts.append((*b, 0.0))
        pts.append((*a2, _bulge(a2, b2, c2)))
        pts.append((*b2, 0.0))
    else:
        pts += [(x0, bottom, 0.0), (x1, bottom, 0.0)]
    pts += [(x1, surface, 0.0), (x1 + land, surface, 0.0)]
    return pts


def gland_profile(design: Design, length_unit: str = "mm", title: str = "") -> Drawing:
    k = SCALE[length_unit]
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = INSUNITS[length_unit]
    for name, color in LAYERS.items():
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    g, ring = design.gland, design.oring
    W, r = ring.cs_m * k, g.corner_radius_m * k
    dec = 3 if length_unit == "mm" else 4
    dim = dict(dimstyle="EZDXF", dxfattribs={"layer": "DIMS"},
               override={"dimtxt": 0.08 * W, "dimasz": 0.08 * W, "dimlfac": 1.0, "dimdec": dec,
                         "dimexe": 0.04 * W, "dimexo": 0.04 * W})

    if isinstance(g, (PistonGland, RodGland)):
        G = g.groove_width_m * k
        land = G
        if isinstance(g, PistonGland):
            surface, bottom, mating = g.piston_diameter_m / 2 * k, g.groove_diameter_m / 2 * k, g.bore_diameter_m / 2 * k
            ring_y = bottom + W / 2
            labels = {"surface": "Ø piston", "bottom": "Ø groove", "mating": "Ø bore"}
        else:
            surface, bottom, mating = g.throat_diameter_m / 2 * k, g.groove_diameter_m / 2 * k, g.rod_diameter_m / 2 * k
            ring_y = mating + W / 2
            labels = {"surface": "Ø throat", "bottom": "Ø groove", "mating": "Ø rod"}
        pts = _u_profile(0.0, G, surface, bottom, r, land)
        msp.add_lwpolyline(pts, format="xyb", dxfattribs={"layer": "GROOVE"})
        msp.add_line((-land, mating), (G + land, mating), dxfattribs={"layer": "MATING"})
        msp.add_circle((G / 2, ring_y), W / 2, dxfattribs={"layer": "ORING"})
        msp.add_linear_dim(base=(0, bottom - math.copysign(0.6 * W, surface - bottom)),
                           p1=(0, bottom), p2=(G, bottom), **dim).render()
        msp.add_linear_dim(base=(-0.5 * land, 0), p1=(0, bottom), p2=(0, mating), angle=90, **dim).render()
        msp.add_linear_dim(base=(G + 0.4 * land, 0), p1=(G, bottom), p2=(G, surface), angle=90, **dim).render()
        offsets = {"mating": 0.25 * W, "surface": -0.25 * W, "bottom": 0.0}
        if isinstance(g, RodGland):
            offsets = {"mating": -0.25 * W, "surface": 0.25 * W, "bottom": 0.0}
        for key, y in (("surface", surface), ("bottom", bottom), ("mating", mating)):
            msp.add_text(f"{labels[key]} {2 * y:.{dec}f}", height=0.08 * W,
                         dxfattribs={"layer": "NOTES"}).set_placement((G + land * 1.05, y + offsets[key]))
    elif isinstance(g, FaceGland):
        gi, go, H = g.groove_id_m / 2 * k, g.groove_od_m / 2 * k, g.groove_depth_m * k
        land = go - gi
        pts = _u_profile(gi, go, 0.0, -H, r, land)
        msp.add_lwpolyline(pts, format="xyb", dxfattribs={"layer": "GROOVE"})
        msp.add_line((gi - land, 0.0), (go + land, 0.0), dxfattribs={"layer": "MATING"})
        cx = go - W / 2 if g.pressure_direction == "internal" else gi + W / 2
        msp.add_circle((cx, -H + W / 2), W / 2, dxfattribs={"layer": "ORING"})
        msp.add_linear_dim(base=(0, -H - 0.6 * W), p1=(gi, -H), p2=(go, -H), **dim).render()
        msp.add_linear_dim(base=(gi - 0.5 * land, 0), p1=(gi, -H), p2=(gi, 0.0), angle=90, **dim).render()
        msp.add_text(f"Ø groove ID {2 * gi:.{dec}f}  Ø groove OD {2 * go:.{dec}f}", height=0.08 * W,
                     dxfattribs={"layer": "NOTES"}).set_placement((gi - land, 0.6 * W))
    else:  # pragma: no cover
        raise TypeError(f"unsupported gland {g!r}")

    note = (f"{title}  O-ring ID {ring.id_m * k:.{dec}f} x CS {W:.{dec}f} [{length_unit}]; "
            "dimensions at reference temperature")
    msp.add_text(note.strip(), height=0.08 * W, dxfattribs={"layer": "NOTES"}).set_placement(
        (pts[0][0], pts[0][1] + (1.6 * W if not isinstance(g, FaceGland) else 1.2 * W)))
    return doc


def to_bytes(doc: Drawing) -> bytes:
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
