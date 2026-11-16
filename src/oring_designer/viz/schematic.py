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


def _defs() -> str:
    return (
        '<defs>'
        '<pattern id="hA" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<rect width="7" height="7" fill="#dddcd6"/><line x1="0" y1="0" x2="0" y2="7" stroke="#b9b8b1" '
        'stroke-width="1.3"/></pattern>'
        '<pattern id="hB" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">'
        '<rect width="7" height="7" fill="#c7c6bf"/><line x1="0" y1="0" x2="0" y2="7" stroke="#a3a29b" '
        'stroke-width="1.3"/></pattern>'
        f'<marker id="ar" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="9" markerHeight="9" '
        f'markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0,1.5 L10,5 L0,8.5 z" fill="{INK}"/>'
        '</marker>'
        f'<marker id="ap" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="12" markerHeight="12" '
        f'markerUnits="userSpaceOnUse" orient="auto"><path d="M0,1 L10,5 L0,9 z" fill="{PRESSURE}"/></marker>'
        '</defs>'
    )


class _Svg:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, s: str) -> None:
        self.parts.append(s)

    def poly(self, pts, fill: str, stroke: str = INK, width: float = 1.4) -> None:
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" '
                 'stroke-linejoin="round"/>')

    def line(self, x0, y0, x1, y1, color: str = INK, width: float = 0.9, dash: str | None = None,
             start: bool = False, end: bool = False, marker: str = "ar") -> None:
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        if start:
            extra += f' marker-start="url(#{marker})"'
        if end:
            extra += f' marker-end="url(#{marker})"'
        self.add(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{color}" '
                 f'stroke-width="{width}"{extra}/>')

    def text(self, x, y, s: str, size: int = 16, anchor: str = "start", weight: str = "600",
             color: str = INK, halo: bool = True) -> None:
        h = ' paint-order="stroke" stroke="#ffffff" stroke-width="4" stroke-linejoin="round"' if halo else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
                 f'font-weight="{weight}" fill="{color}"{h}>{escape(s)}</text>')


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


def _piston(svg: _Svg, dims: dict, seal: str) -> None:
    cl, y_bore, y_od, y_gb = 320, 100, 114, 200
    gx0, gx1 = 240, 360
    svg.poly([(20, 28), (XR, 28), (XR, y_bore), (20, y_bore)], "url(#hB)")  # cylinder
    r = 9
    svg.poly([(20, y_od), (gx0, y_od), (gx0, y_gb - r), (gx0 + r, y_gb), (gx1 - r, y_gb), (gx1, y_gb - r),
              (gx1, y_od), (XR, y_od), (XR, cl), (20, cl)], "url(#hA)")  # piston
    _seal(svg, dims, seal, gx0, gx1, y_bore, y_gb)
    svg.line(10, cl, XR + 10, cl, color=INK_2, dash="14 4 3 4")
    svg.text(16, cl - 6, "℄", size=13, weight="400", color=INK_2)
    if "bore" in dims:
        _diameter(svg, 60, cl, y_bore, _label("ØA", dims, "bore"), 190)
    if "piston" in dims:
        _diameter(svg, 165, cl, y_od, _label("ØC", dims, "piston"), 280)
    if "groove_d" in dims:
        svg.line(gx1, y_gb, 425, y_gb, width=0.7)
        _diameter(svg, 412, cl, y_gb, _label("ØB", dims, "groove_d"), 285)
    if "depth" in dims:
        svg.line(gx1, y_gb, 495, y_gb, width=0.7)
        svg.line(480, y_gb, 480, y_bore, start=True, end=True)
        svg.text(488, 160, _label("L", dims, "depth"))
    if "width" in dims:
        svg.line(gx0, y_gb, gx0, y_gb + 42, width=0.7)
        svg.line(gx1, y_gb, gx1, y_gb + 42, width=0.7)
        svg.line(gx0, y_gb + 36, gx1, y_gb + 36, start=True, end=True)
        svg.text((gx0 + gx1) / 2, y_gb + 54, _label("G", dims, "width"), anchor="middle")
    if "gap" in dims:
        _radius_leader(svg, 112, (y_bore + y_od) / 2, 108, 150, _label("E", dims, "gap"), anchor="start")
    if "radius" in dims:
        _radius_leader(svg, gx0 + 3, y_gb - 3, 228, 178, _label("R", dims, "radius"))


def _rod(svg: _Svg, dims: dict, seal: str) -> None:
    cl, y_rod, y_thr, y_gb = 320, 220, 206, 120
    gx0, gx1 = 240, 360
    r = 9
    svg.poly([(20, 28), (XR, 28), (XR, y_thr), (gx1, y_thr), (gx1, y_gb + r), (gx1 - r, y_gb),
              (gx0 + r, y_gb), (gx0, y_gb + r), (gx0, y_thr), (20, y_thr)], "url(#hA)")  # housing
    svg.poly([(20, y_rod), (XR, y_rod), (XR, cl), (20, cl)], "url(#hB)")  # rod
    _seal(svg, dims, seal, gx0, gx1, y_gb, y_rod)
    svg.line(10, cl, XR + 10, cl, color=INK_2, dash="14 4 3 4")
    svg.text(16, cl - 6, "℄", size=13, weight="400", color=INK_2)
    if "rod" in dims:
        _diameter(svg, 60, cl, y_rod, _label("ØD", dims, "rod"), 290)
    if "throat" in dims:
        _diameter(svg, 165, cl, y_thr, _label("ØT", dims, "throat"), 262)
    if "groove_d" in dims:
        svg.line(gx1, y_gb, 425, y_gb, width=0.7)
        _diameter(svg, 412, cl, y_gb, _label(ROD_GROOVE, dims, "groove_d"), 290)
    if "depth" in dims:
        svg.line(gx1, y_gb, 495, y_gb, width=0.7)
        svg.line(480, y_gb, 480, y_rod, start=True, end=True)
        svg.text(488, 178, _label("L", dims, "depth"))
    if "width" in dims:
        svg.line(gx0, y_gb, gx0, y_gb - 28, width=0.7)
        svg.line(gx1, y_gb, gx1, y_gb - 28, width=0.7)
        svg.line(gx0, y_gb - 22, gx1, y_gb - 22, start=True, end=True)
        svg.text((gx0 + gx1) / 2, y_gb - 30, _label("G", dims, "width"), anchor="middle")
    if "gap" in dims:
        _radius_leader(svg, 112, (y_rod + y_thr) / 2, 108, 182, _label("E", dims, "gap"), anchor="start")
    if "radius" in dims:
        _radius_leader(svg, gx0 + 3, y_gb + 3, 228, 150, _label("R", dims, "radius"))


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
                    seal: str = "oring") -> str:
    """SVG text of the dimensioned schematic. ``dims`` values are already formatted (no unit)."""
    dims = {k: v for k, v in dims.items() if v is not None}
    svg = _Svg()
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
            f'<rect width="{W}" height="{total_h}" fill="#ffffff"/>{_defs()}{body}</svg>')
