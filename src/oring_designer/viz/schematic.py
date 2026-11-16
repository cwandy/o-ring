"""Dimensioned gland schematic (not to scale) as an SVG string.

One fixed, stylised half-section per gland type with the dimension symbols placed on it and
their current values written next to them; a legend below lists every dimension given.
Used beside the input fields so that the user sees which number is which.

Kinds: ``piston`` (groove in the piston, also used for the calculator's radial gland),
``rod`` (groove in the housing bore) and ``face`` (groove in a flange face, axis vertical).
``seal="spring"`` draws a spring-energised U-jacket instead of an O-ring.

``dims`` is an ordered mapping key -> value text (``None`` = not known, omitted). Keys with
a place on the drawing: bore, piston, groove_d, rod, throat, groove_id, groove_od, width,
depth, radius, cs, gap, seal_h, seal_b. Any other key (ring_id, machine_depth, ...) appears
in the legend only.
"""

from __future__ import annotations

import math
from html import escape

from ..i18n import t

INK = "#1f1f1d"
INK_2 = "#52514e"
RING = "#2a78d6"
PRESSURE = "#d03b2f"
W = 640  # drawing width (px of the viewBox)
XR = 620  # right edge of the parts
H = 350  # drawing height without the legend

SYMBOL = {
    "bore": "ØA", "piston": "ØC", "groove_d": "ØB", "rod": "ØD", "throat": "ØT",
    "groove_id": "ØD₁", "groove_od": "ØD₂", "width": "G", "depth": "L", "radius": "R",
    "cs": "W", "gap": "E", "ring_id": "d₁", "machine_depth": "Lₘ", "seal_h": "h", "seal_b": "b",
    "static_d": "Øs",
}
ROD_GROOVE = "ØF"  # groove diameter of a rod gland


SOLID = {"url(#hA)": "#dddcd6", "url(#hB)": "#c7c6bf"}  # fills without hatching (SVG Tiny)


def _defs(tiny: bool) -> str:
    if tiny:
        return ""
    return (
        '<defs>'
        '<pattern id="hA" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<rect width="7" height="7" fill="#dddcd6"/><line x1="0" y1="0" x2="0" y2="7" stroke="#b9b8b1" '
        'stroke-width="1.3"/></pattern>'
        '<pattern id="hB" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">'
        '<rect width="7" height="7" fill="#c7c6bf"/><line x1="0" y1="0" x2="0" y2="7" stroke="#a3a29b" '
        'stroke-width="1.3"/></pattern>'
        '</defs>'
    )


class _Svg:
    """SVG builder. Arrow heads are explicit triangles and text halos are a separate white
    copy, so the output also renders in SVG Tiny renderers (Qt), where ``tiny`` replaces the
    hatch patterns by solid fills."""

    def __init__(self, tiny: bool = False) -> None:
        self.parts: list[str] = []
        self.tiny = tiny

    def add(self, s: str) -> None:
        self.parts.append(s)

    def poly(self, pts, fill: str, stroke: str = INK, width: float = 1.4) -> None:
        if self.tiny:
            fill = SOLID.get(fill, fill)
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" '
                 'stroke-linejoin="round"/>')

    def _head(self, x_tip, y_tip, x_from, y_from, color: str, size: float) -> None:
        dx, dy = x_tip - x_from, y_tip - y_from
        n = math.hypot(dx, dy) or 1.0
        ux, uy = dx / n, dy / n
        bx, by = x_tip - ux * size, y_tip - uy * size
        hw = size * 0.38
        pts = [(x_tip, y_tip), (bx - uy * hw, by + ux * hw), (bx + uy * hw, by - ux * hw)]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(f'<polygon points="{d}" fill="{color}" stroke="none"/>')

    def line(self, x0, y0, x1, y1, color: str = INK, width: float = 0.9, dash: str | None = None,
             start: bool = False, end: bool = False, marker: str = "ar") -> None:
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{color}" '
                 f'stroke-width="{width}"{extra}/>')
        size = 12.0 if marker == "ap" else 9.0
        if start:
            self._head(x0, y0, x1, y1, color, size)
        if end:
            self._head(x1, y1, x0, y0, color, size)

    def text(self, x, y, s: str, size: int = 16, anchor: str = "start", weight: str = "600",
             color: str = INK, halo: bool = True) -> None:
        common = (f'x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
                  f'font-weight="{weight}"')
        if halo:
            self.add(f'<text {common} fill="#ffffff" stroke="#ffffff" stroke-width="4" '
                     f'stroke-linejoin="round">{escape(s)}</text>')
        self.add(f'<text {common} fill="{color}">{escape(s)}</text>')


def _label(sym: str, dims: dict, key: str) -> str:
    v = dims.get(key)
    return f"{sym} {v.split()[0]}" if v else sym  # nominal only; tolerances are in the legend


def _ring(svg: _Svg, cx: float, cy: float, rx: float, ry: float) -> None:
    svg.add(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{RING}" fill-opacity="0.35" '
            f'stroke="{RING}" stroke-width="2"/>')


def _spring_seal(svg: _Svg, x0: float, y0: float, x1: float, y1: float, open_left: bool) -> None:
    """U-shaped jacket (open towards the pressure side) with a coil spring inside."""
    tk = 0.16 * (y1 - y0)
    r = 0.22 * (y1 - y0)
    svg.add(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="{r:.1f}" fill="{RING}" '
            f'fill-opacity="0.35" stroke="{RING}" stroke-width="2"/>')
    # cavity open towards the pressure side: white fill over the jacket, outline on three sides
    yt, yb = y0 + tk, y1 - tk
    if open_left:
        xo, xc = x0 - 2, x1 - tk
    else:
        xo, xc = x1 + 2, x0 + tk
    svg.add(f'<rect x="{min(xo, xc):.1f}" y="{yt:.1f}" width="{abs(xc - xo):.1f}" height="{yb - yt:.1f}" '
            'fill="#ffffff" stroke="none"/>')
    svg.add(f'<polyline points="{xo:.1f},{yt:.1f} {xc:.1f},{yt:.1f} {xc:.1f},{yb:.1f} {xo:.1f},{yb:.1f}" '
            f'fill="none" stroke="{RING}" stroke-width="1.5"/>')
    sx = (x0 + x1) / 2 + (-tk / 2 if open_left else tk / 2)
    sr = (y1 - y0 - 2 * tk) / 2 * 0.78
    svg.add(f'<circle cx="{sx:.1f}" cy="{(y0 + y1) / 2:.1f}" r="{sr:.1f}" fill="none" stroke="{INK_2}" '
            'stroke-width="2.2" stroke-dasharray="4 2.5"/>')


def _seal(svg: _Svg, dims: dict, seal: str, gx0: float, gx1: float, y0: float, y1: float,
          align: str = "center", open_left: bool = True) -> None:
    """Seal in the groove spanning y0..y1 (contact to contact); label the cross-section."""
    gw = gx1 - gx0
    if seal == "spring":
        sw = gw * 0.82
    else:
        sw = gw * 0.86
    if align == "right":
        sx0 = gx1 - sw
    elif align == "left":
        sx0 = gx0
    else:
        sx0 = gx0 + (gw - sw) / 2
    cy = (y0 + y1) / 2
    if seal == "spring":
        _spring_seal(svg, sx0, y0, sx0 + sw, y1, open_left)
        lines = [_label(SYMBOL["seal_b"], dims, "seal_b"), _label(SYMBOL["seal_h"], dims, "seal_h")]
        svg.text(sx0 + sw / 2, y1 + 18, "   ".join(lines), size=14, anchor="middle")
    else:
        _ring(svg, sx0 + sw / 2, cy, sw / 2, (y1 - y0) / 2)
        svg.text(sx0 + sw / 2, cy + 5, _label(SYMBOL["cs"], dims, "cs"), size=15, anchor="middle")


def _diameter(svg: _Svg, x: float, y_axis: float, y_to: float, label: str, ty: float) -> None:
    """Diameter from the centre line (single arrow head, half-section convention)."""
    svg.line(x, y_axis, x, y_to, end=True)
    svg.text(x + 7, ty, label)


def _radius_leader(svg: _Svg, px: float, py: float, tx: float, ty: float, label: str, anchor="end") -> None:
    svg.line(tx + (4 if anchor == "end" else -4), ty - 4, px, py, width=0.8, end=True)
    svg.text(tx, ty, label, size=15, anchor=anchor)


def _seal_vertical(svg: _Svg, dims: dict, seal: str, g0: float, g1: float, xa: float, xb: float) -> None:
    """Seal in a radial groove drawn with a vertical axis: the groove spans g0..g1 axially (y),
    the seal is squeezed between xa and xb radially (x). Spring jacket opens upwards."""
    gw, d = g1 - g0, xb - xa
    cx, cy = (xa + xb) / 2, (g0 + g1) / 2
    if seal == "spring":
        sw = gw * 0.82
        u0 = (gw - sw) / 2
        inner = _Svg()
        _spring_seal(inner, u0, 0.0, u0 + sw, d, open_left=True)
        # local frame (u along the groove width, v across) -> page: x = xa + v, y = g0 + u
        svg.add(f'<g transform="matrix(0,1,1,0,{xa:.1f},{g0:.1f})">{"".join(inner.parts)}</g>')
        # b and h are listed in the legend (no room on the drawing next to the gap label)
    else:
        _ring(svg, cx, cy, d / 2, gw * 0.86 / 2)
        svg.text(cx, cy + 5, _label(SYMBOL["cs"], dims, "cs"), size=15, anchor="middle")


def _axis_vertical(svg: _Svg, ax: float) -> None:
    svg.line(ax, 14, ax, H - 6, color=INK_2, dash="14 4 3 4")
    svg.text(ax + 4, 12, "℄", size=13, weight="400", color=INK_2)


def _radial_dia(svg: _Svg, ax: float, y: float, x_to: float, label: str) -> None:
    """Diameter from the vertical centre line (single arrow head), label above the line."""
    svg.line(ax, y, x_to, y, end=True)
    svg.text(ax + 10, y - 7, label)


def _piston(svg: _Svg, dims: dict, seal: str) -> None:
    """Piston gland, axis vertical: piston on the left, cylinder wall on the right."""
    ax, x_gb, x_od, x_bore = 40, 310, 400, 414
    g0, g1, top, bot = 150, 270, 24, 344
    r = 9
    svg.poly([(ax, top), (x_od, top), (x_od, g0), (x_gb + r, g0), (x_gb, g0 + r), (x_gb, g1 - r),
              (x_gb + r, g1), (x_od, g1), (x_od, bot), (ax, bot)], "url(#hA)")  # piston
    svg.poly([(x_bore, top), (XR, top), (XR, bot), (x_bore, bot)], "url(#hB)")  # cylinder
    _seal_vertical(svg, dims, seal, g0, g1, x_gb, x_bore)
    _axis_vertical(svg, ax)
    if "bore" in dims:
        _radial_dia(svg, ax, 62, x_bore, _label("ØA", dims, "bore"))
    if "piston" in dims:
        _radial_dia(svg, ax, 104, x_od, _label("ØC", dims, "piston"))
    if "groove_d" in dims or "depth" in dims:
        svg.line(x_gb, g1, x_gb, 334, width=0.7)
    if "groove_d" in dims:
        _radial_dia(svg, ax, 326, x_gb, _label("ØB", dims, "groove_d"))
    if "depth" in dims:
        svg.line(x_gb, 298, x_bore, 298, start=True, end=True)
        svg.text(x_bore + 8, 303, _label("L", dims, "depth"))
    if "width" in dims:
        svg.line(x_gb, g0, 238, g0, width=0.7)
        svg.line(x_gb, g1, 238, g1, width=0.7)
        svg.line(246, g0, 246, g1, start=True, end=True)
        svg.text(238, (g0 + g1) / 2 + 5, _label("G", dims, "width"), anchor="end")
    if "gap" in dims:
        _radius_leader(svg, (x_od + x_bore) / 2, 128, x_bore + 30, 140, _label("E", dims, "gap"), anchor="start")
    if "radius" in dims:
        _radius_leader(svg, x_gb + 3, g1 - 3, 292, 288, _label("R", dims, "radius"))


def _rod(svg: _Svg, dims: dict, seal: str) -> None:
    """Rod gland, axis vertical: rod on the left, housing with the groove on the right."""
    ax, x_rod, x_thr, x_gb = 40, 290, 302, 406
    g0, g1, top, bot = 150, 270, 24, 344
    r = 9
    svg.poly([(ax, top), (x_rod, top), (x_rod, bot), (ax, bot)], "url(#hB)")  # rod
    svg.poly([(x_thr, top), (XR, top), (XR, bot), (x_thr, bot), (x_thr, g1), (x_gb - r, g1), (x_gb, g1 - r),
              (x_gb, g0 + r), (x_gb - r, g0), (x_thr, g0)], "url(#hA)")  # housing
    _seal_vertical(svg, dims, seal, g0, g1, x_rod, x_gb)
    _axis_vertical(svg, ax)
    if "rod" in dims:
        _radial_dia(svg, ax, 62, x_rod, _label("ØD", dims, "rod"))
    if "throat" in dims:
        _radial_dia(svg, ax, 104, x_thr, _label("ØT", dims, "throat"))
    if "groove_d" in dims or "depth" in dims:
        svg.line(x_gb, g1, x_gb, 334, width=0.7)
    if "groove_d" in dims:
        _radial_dia(svg, ax, 326, x_gb, _label(ROD_GROOVE, dims, "groove_d"))
    if "depth" in dims:
        svg.line(x_rod, 298, x_gb, 298, start=True, end=True)
        svg.text(x_gb + 8, 303, _label("L", dims, "depth"))
    if "width" in dims:
        svg.line(x_gb, g0, 450, g0, width=0.7)
        svg.line(x_gb, g1, 450, g1, width=0.7)
        svg.line(442, g0, 442, g1, start=True, end=True)
        svg.text(452, (g0 + g1) / 2 + 5, _label("G", dims, "width"))
    if "gap" in dims:
        _radius_leader(svg, (x_rod + x_thr) / 2, 128, 262, 118, _label("E", dims, "gap"))
    if "radius" in dims:
        _radius_leader(svg, x_gb - 3, g1 - 3, 452, 254, _label("R", dims, "radius"), anchor="start")


def _face(svg: _Svg, dims: dict, seal: str, direction: str) -> None:
    ax, y_face, y_gb = 40, 140, 225
    gx0, gx1 = 300, 420
    r = 9
    svg.poly([(ax, 40), (XR, 40), (XR, y_face), (ax, y_face)], "url(#hB)")  # cover
    svg.poly([(ax, y_face), (gx0, y_face), (gx0, y_gb - r), (gx0 + r, y_gb), (gx1 - r, y_gb), (gx1, y_gb - r),
              (gx1, y_face), (XR, y_face), (XR, 335), (ax, 335)], "url(#hA)")  # flange
    internal = direction == "internal"
    _seal(svg, dims, seal, gx0, gx1, y_face, y_gb, align="right" if internal else "left",
          open_left=internal)
    svg.line(ax, 20, ax, 345, color=INK_2, dash="14 4 3 4")
    svg.text(ax + 4, 16, "℄", size=13, weight="400", color=INK_2)
    # pressure
    if internal:
        svg.line(200, y_face, gx0 - 4, y_face, color=PRESSURE, width=2.2, end=True, marker="ap")
        svg.text(205, y_face - 8, t("schematic.pressure"), size=15, color=PRESSURE)
    else:
        svg.line(XR - 20, y_face, gx1 + 4, y_face, color=PRESSURE, width=2.2, end=True, marker="ap")
        svg.text(XR - 25, y_face - 8, t("schematic.pressure"), size=15, color=PRESSURE, anchor="end")
    if "groove_id" in dims:
        svg.line(gx0, y_gb, gx0, 286, width=0.7)
        svg.line(ax, 280, gx0, 280, end=True)
        svg.text(ax + 12, 274, _label(SYMBOL["groove_id"], dims, "groove_id"))
    if "groove_od" in dims:
        svg.line(gx1, y_gb, gx1, 318, width=0.7)
        svg.line(ax, 312, gx1, 312, end=True)
        svg.text(ax + 12, 306, _label(SYMBOL["groove_od"], dims, "groove_od"))
    if "depth" in dims:
        svg.line(gx1, y_gb, 495, y_gb, width=0.7)
        svg.line(480, y_gb, 480, y_face, start=True, end=True)
        svg.text(488, 190, _label("L", dims, "depth"))
    if "width" in dims:
        svg.line(gx0, y_face, gx0, 74, width=0.7)
        svg.line(gx1, y_face, gx1, 74, width=0.7)
        svg.line(gx0, 80, gx1, 80, start=True, end=True)
        svg.text((gx0 + gx1) / 2, 72, _label("G", dims, "width"), anchor="middle")
    if "radius" in dims:
        if internal:
            _radius_leader(svg, gx0 + 3, y_gb - 3, 288, 250, _label("R", dims, "radius"))
        else:
            _radius_leader(svg, gx1 - 3, y_gb - 3, 432, 250, _label("R", dims, "radius"), anchor="start")


def gland_schematic(kind: str, dims: dict[str, str | None], unit: str, direction: str = "internal",
                    seal: str = "oring", tiny: bool = False) -> str:
    """SVG text of the dimensioned schematic. ``dims`` values are already formatted (no unit)."""
    dims = {k: v for k, v in dims.items() if v is not None}
    svg = _Svg(tiny)
    if kind == "piston":
        _piston(svg, dims, seal)
    elif kind == "rod":
        _rod(svg, dims, seal)
    elif kind == "face":
        _face(svg, dims, seal, direction)
    else:
        raise ValueError(f"unknown gland kind {kind!r}")

    # legend (one row per dimension)
    rows = []
    for key, value in dims.items():
        sym = ROD_GROOVE if (kind == "rod" and key == "groove_d") else SYMBOL.get(key, "")
        rows.append((sym, t(f"schematic.{key}"), value))
    y0 = H + 12
    total_h = y0 + 26 * len(rows) + 30
    svg.line(20, H + 2, W - 20, H + 2, color="#e6e5e1", width=1)
    for i, (sym, name, value) in enumerate(rows):
        y = y0 + 20 + 26 * i
        svg.text(24, y, sym, size=16, halo=False)
        svg.text(80, y, name, size=16, weight="400", color=INK_2, halo=False)
        shown = f"{value} {unit}" if any(ch.isdigit() for ch in value) else value
        svg.text(W - 24, y, shown, size=16, anchor="end", halo=False)
    svg.text(W - 20, total_h - 8, t("schematic.not_to_scale"), size=13, anchor="end", weight="400",
             color=INK_2, halo=False)
    body = "".join(svg.parts)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {total_h}" width="100%" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif">'
            f'<rect width="{W}" height="{total_h}" fill="#ffffff"/>{_defs(tiny)}{body}</svg>')
