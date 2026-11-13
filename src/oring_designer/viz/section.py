"""Scaled cross-section drawing of gland and O-ring (SPEC §9).

Coordinates of one panel (lengths in the display unit):
  x: across the groove (axial direction for radial glands, radial direction for face glands),
     0 = groove wall on the left, G = groove width.
  y: depth direction, 0 = groove bottom, F = groove-part surface, L = mating surface.

Radial glands: the groove-part surface is at F = L - c/2 (c = diametral clearance), so the
extrusion gap L - F is visible between the parts. The panel shows one circumferential
position: nominal (concentric), the tight side (L - e) or the wide side (L + e).
Face glands: metal-to-metal contact, F = L; the ring is drawn against the low-pressure
groove wall it bears on (O.D. wall for internal pressure, I.D. wall for external).

Simplifications (stated in the figure): the free ring is a circle of the stretched
cross-section W_eff resting on the groove bottom; the compressed ring is a stadium
(rectangle with semicircular ends) of height L and the same area pi W_eff^2 / 4. It is
capped at the groove width (marked "does not fit").
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..gland_types import GlandState
from ..i18n import t
from .plots import SERIES, SURFACE, TEXT, TEXT_2, _layout

PART_GROOVE = "#c9c8c3"
PART_MATING = "#a3a29c"
RING_FILL = "rgba(42, 120, 214, 0.35)"
LENGTH_SCALE = {"mm": 1e3, "in": 1 / 0.0254}


@dataclass(frozen=True)
class Stadium:
    width: float
    height: float
    capped: bool  # True if the area-preserving width exceeded the available width

    @property
    def area(self) -> float:
        r = self.height / 2
        return self.width * self.height - (4 - math.pi) * r**2


def compressed_stadium(cs_eff: float, height: float, max_width: float | None = None) -> Stadium:
    """Stadium of the given height with the area of a circle of diameter ``cs_eff``.

    w * h - (4 - pi) (h/2)^2 = pi cs^2 / 4  ->  w = (pi cs^2/4 + (4 - pi) h^2/4) / h.
    If ``height >= cs_eff`` the ring is not compressed and a circle (w = h = cs) is returned.
    """
    if height >= cs_eff:
        return Stadium(cs_eff, cs_eff, False)
    area = math.pi * cs_eff**2 / 4
    w = (area + (4 - math.pi) * height**2 / 4) / height
    if max_width is not None and w > max_width:
        return Stadium(max_width, height, True)
    return Stadium(w, height, False)


def _stadium_xy(x0: float, w: float, h: float, n: int = 41):  # odd: includes the extreme points
    r = h / 2
    xs, ys = [], []
    for a in np.linspace(-math.pi / 2, math.pi / 2, n):  # right cap
        xs.append(x0 + w - r + r * math.cos(a)); ys.append(r + r * math.sin(a))
    for a in np.linspace(math.pi / 2, 3 * math.pi / 2, n):  # left cap
        xs.append(x0 + r + r * math.cos(a)); ys.append(r + r * math.sin(a))
    xs.append(xs[0]); ys.append(ys[0])
    return xs, ys


def _circle_xy(cx: float, cy: float, d: float, n: int = 80):
    a = np.linspace(0, 2 * math.pi, n)
    return (cx + d / 2 * np.cos(a)).tolist(), (cy + d / 2 * np.sin(a)).tolist()


def _poly(fig, xs, ys, color, name, col, show, line=None):
    fig.add_trace(go.Scatter(x=xs, y=ys, fill="toself", fillcolor=color, mode="lines",
                             line=line or dict(color=color, width=0.5), name=name,
                             legendgroup=name, showlegend=show, hoverinfo="skip"), row=1, col=col)


def _dim(fig, col, x0, y0, x1, y1, text, offset=(0, 0)):
    """Two-headed dimension arrow from (x0, y0) to (x1, y1) with a label."""
    xref, yref = ("x", "y") if col == 1 else (f"x{col}", f"y{col}")
    for (a, b), (c, d) in (((x1, y1), (x0, y0)), ((x0, y0), (x1, y1))):
        fig.add_annotation(x=a, y=b, ax=c, ay=d, xref=xref, yref=yref, axref=xref, ayref=yref,
                           showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1,
                           arrowcolor=TEXT, text="")
    fig.add_annotation(x=(x0 + x1) / 2 + offset[0], y=(y0 + y1) / 2 + offset[1], xref=xref,
                       yref=yref, text=text, showarrow=False, font=dict(size=11, color=TEXT),
                       bgcolor="rgba(252,252,251,0.85)")


def section_figure(
    panels: list[tuple[str, GlandState | None]],
    kind: str,
    side: str = "nominal",
    length_unit: str = "mm",
    pressure_direction: str = "internal",
    corner_radius_m: float = 0.0,
) -> go.Figure:
    """One panel per (title, state); ``None`` state = no thermal data at that temperature."""
    k = LENGTH_SCALE[length_unit]
    nd = 3 if length_unit == "mm" else 4
    fig = make_subplots(rows=1, cols=len(panels), subplot_titles=[p[0] for p in panels],
                        horizontal_spacing=0.04)
    valid = [s for _, s in panels if s is not None]
    if valid:
        Gmax = max(s.gland_width_m for s in valid) * k
        Ymax = max(max(s.depth_max_m, s.cs_eff_m) for s in valid) * k
    else:
        Gmax = Ymax = 1.0
    margin = 0.55 * Gmax
    x_range = [-margin, Gmax + margin]
    y_range = [-0.35 * Ymax, 1.45 * Ymax]

    for col, (title, st) in enumerate(panels, start=1):
        show = col == 1
        if st is None:
            fig.add_annotation(x=Gmax / 2, y=Ymax / 2, text=t("plots.no_data"), showarrow=False,
                               xref="x" if col == 1 else f"x{col}", yref="y" if col == 1 else f"y{col}",
                               font=dict(color=TEXT_2))
            continue
        G = st.gland_width_m * k
        W = st.cs_eff_m * k
        if kind == "face":
            L = st.depth_nominal_m * k
            F = L
        else:
            c_half = (st.diametral_clearance_m or 0.0) / 2 * k
            F = st.depth_nominal_m * k - c_half
            L = {"nominal": st.depth_nominal_m, "tight": st.depth_min_m,
                 "wide": st.depth_max_m}[side] * k
        x0, x1 = x_range
        # groove part (U-shaped body around the groove)
        r = min(corner_radius_m * k, G / 2, F)
        groove_x = [x0, 0, 0]
        groove_y = [F, F, r]
        if r > 0:
            for a in np.linspace(math.pi, 1.5 * math.pi, 8):
                groove_x.append(r + r * math.cos(a)); groove_y.append(r + r * math.sin(a))
            for a in np.linspace(1.5 * math.pi, 2 * math.pi, 8):
                groove_x.append(G - r + r * math.cos(a)); groove_y.append(r + r * math.sin(a))
        else:
            groove_x += [0, G]; groove_y += [0, 0]
        groove_x += [G, G, x1, x1, x0, x0]
        groove_y += [r, F, F, y_range[0], y_range[0], F]
        _poly(fig, groove_x, groove_y, PART_GROOVE, t("plots.groove_part"), col, show)
        # mating part
        _poly(fig, [x0, x1, x1, x0, x0], [L, L, y_range[1], y_range[1], L], PART_MATING,
              t("plots.mating_part"), col, show)

        # free ring: circle on the groove bottom
        if kind == "face":
            cx = G - W / 2 if pressure_direction == "internal" else W / 2
        else:
            cx = G / 2
        fx, fy = _circle_xy(cx, W / 2, W)
        fig.add_trace(go.Scatter(x=fx, y=fy, mode="lines", name=t("plots.free_ring"),
                                 legendgroup="free", showlegend=show, hoverinfo="skip",
                                 line=dict(color=TEXT_2, width=1.5, dash="dash")), row=1, col=col)
        # compressed ring
        stad = compressed_stadium(W, L, G)
        if kind == "face":
            sx0 = G - stad.width if pressure_direction == "internal" else 0.0
        else:
            sx0 = (G - stad.width) / 2
        if L < W:
            xs, ys = _stadium_xy(sx0, stad.width, stad.height)
            fig.add_trace(go.Scatter(x=xs, y=ys, fill="toself", fillcolor=RING_FILL, mode="lines",
                                     line=dict(color=SERIES[0], width=2),
                                     name=t("plots.compressed_ring"), legendgroup="comp",
                                     showlegend=show, hoverinfo="skip"), row=1, col=col)

        # dimensions
        sq = (W - L) / W
        _dim(fig, col, -0.3 * margin, 0, -0.3 * margin, L, f"{t('plots.dim_L')} {L:.{nd}f}",
             offset=(-0.32 * margin, 0))
        _dim(fig, col, 0, -0.15 * Ymax, G, -0.15 * Ymax, f"{t('plots.dim_W')} {G:.{nd}f}",
             offset=(0, -0.1 * Ymax))
        _dim(fig, col, cx, 0, cx, W, f"{t('plots.dim_cs')} {W:.{nd}f}", offset=(0.22 * Gmax, 0.05 * Ymax))
        if kind != "face" and L - F > 1e-4 * W:
            _dim(fig, col, G + 0.35 * margin, F, G + 0.35 * margin, L,
                 f"{t('plots.dim_gap')} {L - F:.{nd}f}", offset=(0.35 * margin, 0.12 * Ymax))
        label = f"{t('plots.label_squeeze')} {sq:.1%} · {t('plots.label_fill')} {st.fill:.1%}"
        if L >= W:
            label += f" · {t('plots.no_contact')}"
        if stad.capped:
            label += f" · {t('plots.overfilled')}"
        fig.add_annotation(x=G / 2, y=1.3 * Ymax, text=label, showarrow=False,
                           xref="x" if col == 1 else f"x{col}", yref="y" if col == 1 else f"y{col}",
                           font=dict(size=12, color=TEXT))

    for col in range(1, len(panels) + 1):
        fig.update_xaxes(range=x_range, visible=False, row=1, col=col)
        fig.update_yaxes(range=y_range, visible=False, scaleanchor=f"x{'' if col == 1 else col}",
                         scaleratio=1, row=1, col=col)
    fig.update_layout(title=dict(text=f"{t('plots.section_title')} [{length_unit}]"))
    fig.add_annotation(x=0, y=-0.22, xref="paper", yref="paper", text=t("plots.section_note"),
                       showarrow=False, xanchor="left", font=dict(size=11, color=TEXT_2))
    _layout(fig, 360)
    fig.update_layout(hovermode=False, plot_bgcolor=SURFACE, margin=dict(t=70, b=90),
                      legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="left", x=0))
    return fig
