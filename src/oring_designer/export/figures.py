"""Matplotlib figures for the design report (PNG) and the desktop UI (Qt canvas).

Every chart has a ``*_fig`` function returning a ``matplotlib.figure.Figure`` (no pyplot, so
no global backend state) and, where the report needs it, a ``*_png`` wrapper. Same encodings
as the plotly charts of the browser UI. Fonts: matplotlib's bundled DejaVu Sans (covers
Turkish characters).
"""

from __future__ import annotations

import io
import math

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Polygon, Rectangle
from matplotlib.ticker import PercentFormatter

from ..gland_types import GlandState
from ..i18n import t
from ..viz.style import (GRID, LENGTH_SCALE, PART_GROOVE, PART_MATING, SERIES, TEMP_UNIT_LABEL, TEXT, TEXT_2,
                         compressed_stadium, temp_from_K)

BAND = (42 / 255, 120 / 255, 214 / 255, 0.12)
NODATA = (82 / 255, 81 / 255, 78 / 255, 0.18)
RING = (42 / 255, 120 / 255, 214 / 255, 0.35)


def _png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    return buf.getvalue()


def _new(figsize: tuple[float, float]) -> Figure:
    return Figure(figsize=figsize, layout="constrained", facecolor="white")


def _style(ax):
    ax.grid(True, color=GRID, linewidth=0.8)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=TEXT_2, labelsize=8)


def _shade_missing(ax, x, missing):
    i = 0
    while i < len(missing):
        if missing[i]:
            j = i
            while j + 1 < len(missing) and missing[j + 1]:
                j += 1
            ax.axvspan(x[max(i - 1, 0)], x[min(j + 1, len(x) - 1)], color=NODATA, lw=0)
            i = j + 1
        else:
            i += 1


def _T_label(temp_unit: str, key: str = "plots.T_housing") -> str:
    return f"{t(key)} [{TEMP_UNIT_LABEL[temp_unit]}]"


def _legend_below(fig: Figure, axes, ncol: int = 3) -> None:
    handles, labels = [], []
    for a in axes:
        h, lab = a.get_legend_handles_labels()
        handles += h
        labels += lab
    if handles:
        fig.legend(handles, labels, loc="outside lower center", ncol=ncol, fontsize=7, frameon=False)


# --------------------------------------------------------------------------- squeeze / fill sweep
def squeeze_fill_fig(df: pd.DataFrame, temp_unit: str, squeeze_band=None, squeeze_max=None,
                     fill_band=None, fill_hard_max=None, low_temp_limit_K=None,
                     low_temp_band_K=None, seal_offset_K: float = 0.0) -> Figure:
    x = np.asarray(temp_from_K(df["T_housing_K"], temp_unit))
    fig = _new((7.2, 5.6))
    a1, a2 = fig.subplots(2, 1, sharex=True)
    if squeeze_band:
        a1.axhspan(*squeeze_band, color=BAND, lw=0, label=t("plots.recommended_band"))
    if squeeze_max is not None:
        a1.axhline(squeeze_max, color=TEXT_2, lw=1, ls="--")
    a1.plot(x, df["squeeze_max"], color=SERIES[1], lw=2, label=t("plots.squeeze_max"))
    a1.plot(x, df["squeeze_nominal"], color=SERIES[0], lw=2, ls=":", label=t("plots.squeeze_nominal"))
    a1.plot(x, df["squeeze_min"], color=SERIES[0], lw=2, label=t("plots.squeeze_min"))
    if fill_band:
        a2.axhspan(*fill_band, color=BAND, lw=0)
    if fill_hard_max is not None:
        a2.axhline(fill_hard_max, color=TEXT_2, lw=1, ls="--")
    a2.plot(x, df["fill"], color=SERIES[2], lw=2, label=t("plots.fill"))
    for T_lim, ls, lab in ((low_temp_limit_K, "--", t("plots.low_temp_limit")),
                           (None if low_temp_limit_K is None or low_temp_band_K is None
                            else low_temp_limit_K + low_temp_band_K, ":", t("plots.low_temp_band"))):
        if T_lim is not None:
            xv = float(temp_from_K(T_lim - seal_offset_K, temp_unit))
            if x.min() <= xv <= x.max():
                for a in (a1, a2):
                    a.axvline(xv, color=TEXT, lw=1, ls=ls)
                a2.text(xv, a2.get_ylim()[0], " " + lab, rotation=90, va="bottom", fontsize=7, color=TEXT_2)
    missing = df["squeeze_min"].isna().to_numpy()
    for a in (a1, a2):
        _shade_missing(a, x, missing)
        a.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        _style(a)
    a1.set_title(t("plots.squeeze_title"), fontsize=10)
    a2.set_title(t("plots.fill_title"), fontsize=10)
    a2.set_xlabel(_T_label(temp_unit), fontsize=9)
    _legend_below(fig, (a1, a2))
    return fig


def squeeze_fill_png(*args, **kwargs) -> bytes:
    return _png(squeeze_fill_fig(*args, **kwargs))


# --------------------------------------------------------------------------- clearance
def clearance_fig(df: pd.DataFrame, temp_unit: str, length_unit: str) -> Figure:
    x = np.asarray(temp_from_K(df["T_housing_K"], temp_unit))
    k = LENGTH_SCALE[length_unit]
    fig = _new((7.2, 3.0))
    ax = fig.subplots()
    ax.plot(x, df["diametral_clearance_m"] * k, color=SERIES[0], lw=2, label=t("plots.diametral_clearance"))
    ax.plot(x, df["max_extrusion_gap_m"] * k, color=SERIES[1], lw=2, label=t("plots.max_gap"))
    if df["allowed_gap_m"].notna().any():
        ax.plot(x, df["allowed_gap_m"] * k, color=TEXT_2, lw=1.5, ls="--", label=t("plots.allowed_gap"))
    ax.set_ylim(bottom=0)
    ax.set_ylabel(f"[{length_unit}]", fontsize=9)
    ax.set_xlabel(_T_label(temp_unit), fontsize=9)
    ax.set_title(t("plots.clearance_title"), fontsize=10)
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    _style(ax)
    return fig


def clearance_png(*args, **kwargs) -> bytes:
    return _png(clearance_fig(*args, **kwargs))


# --------------------------------------------------------------------------- scaled section
def section_fig(panels: list[tuple[str, GlandState | None]], kind: str, side: str = "nominal",
                length_unit: str = "mm", pressure_direction: str = "internal",
                corner_radius_m: float = 0.0) -> Figure:
    """Static version of ``viz.section.section_figure`` (same geometry, see its docstring;
    groove corner radii are not drawn here)."""
    k = LENGTH_SCALE[length_unit]
    nd = 3 if length_unit == "mm" else 4
    valid = [s for _, s in panels if s is not None]
    Gmax = max(s.gland_width_m for s in valid) * k if valid else 1.0
    Ymax = max(max(s.depth_max_m, s.cs_eff_m) for s in valid) * k if valid else 1.0
    m = 0.55 * Gmax
    fig = _new((3.0 * len(panels), 2.9))
    axs = np.atleast_1d(fig.subplots(1, len(panels)))
    for ax, (title, st) in zip(axs, panels):
        ax.set_xlim(-m, Gmax + m)
        ax.set_ylim(-0.35 * Ymax, 1.45 * Ymax)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(title, fontsize=9)
        if st is None:
            ax.text(Gmax / 2, Ymax / 2, t("plots.no_data"), ha="center", color=TEXT_2, fontsize=8)
            continue
        G, W = st.gland_width_m * k, st.cs_eff_m * k
        if kind == "face":
            L = F = st.depth_nominal_m * k
        else:
            F = st.depth_nominal_m * k - (st.diametral_clearance_m or 0) / 2 * k
            L = {"nominal": st.depth_nominal_m, "tight": st.depth_min_m, "wide": st.depth_max_m}[side] * k
        x0, x1, y0, y1 = -m, Gmax + m, -0.35 * Ymax, 1.45 * Ymax
        ax.add_patch(Polygon([(x0, F), (0, F), (0, 0), (G, 0), (G, F), (x1, F), (x1, y0), (x0, y0)],
                             closed=True, color=PART_GROOVE, lw=0))
        ax.add_patch(Rectangle((x0, L), x1 - x0, y1 - L, color=PART_MATING, lw=0))
        cx = (G - W / 2 if pressure_direction == "internal" else W / 2) if kind == "face" else G / 2
        ax.add_patch(Circle((cx, W / 2), W / 2, fill=False, ls="--", color=TEXT_2, lw=1))
        if L < W:
            s = compressed_stadium(W, L, G)
            sx0 = (G - s.width if pressure_direction == "internal" else 0.0) if kind == "face" else (G - s.width) / 2
            r = s.height / 2
            th = np.linspace(-math.pi / 2, math.pi / 2, 41)
            right = [(sx0 + s.width - r + r * math.cos(a), r + r * math.sin(a)) for a in th]
            left = [(sx0 + r - r * math.cos(a), r - r * math.sin(a)) for a in th]
            ax.add_patch(Polygon(right + left, closed=True, facecolor=RING, edgecolor=SERIES[0], lw=1.5))
        sq = (W - L) / W
        ax.text(G / 2, 1.28 * Ymax, f"{t('plots.label_squeeze')} {sq:.1%} · {t('plots.label_fill')} {st.fill:.1%}",
                ha="center", fontsize=7, color=TEXT)
        ax.annotate("", (-0.3 * m, 0), (-0.3 * m, L), arrowprops=dict(arrowstyle="<->", lw=0.8))
        ax.text(-0.35 * m, L / 2, f"L {L:.{nd}f}", ha="right", va="center", fontsize=7)
        ax.annotate("", (0, -0.15 * Ymax), (G, -0.15 * Ymax), arrowprops=dict(arrowstyle="<->", lw=0.8))
        ax.text(G / 2, -0.3 * Ymax, f"G {G:.{nd}f}", ha="center", fontsize=7)
    fig.suptitle(f"{t('plots.section_title')} [{length_unit}] — {t('plots.section_note')}", fontsize=8,
                 color=TEXT_2, y=0.02)
    return fig


def section_png(*args, **kwargs) -> bytes:
    return _png(section_fig(*args, **kwargs))


# --------------------------------------------------------------------------- groove calculator envelope
def envelope_fig(per_T: pd.DataFrame, temp_unit: str, target: tuple[float, float], fill_limit: float,
                 fill_hard: float | None = None) -> Figure:
    """Squeeze and fill vs temperature: tolerance envelope (shaded), nominal, target band, limits."""
    x = np.asarray(temp_from_K(per_T["T_K"], temp_unit))
    fig = _new((7.2, 5.6))
    a1, a2 = fig.subplots(2, 1, sharex=True)
    a1.axhspan(*target, color=(82 / 255, 81 / 255, 78 / 255, 0.12), lw=0, label=t("plots.gc_target"))
    a1.fill_between(x, per_T["squeeze_lo"], per_T["squeeze_hi"], color=(42 / 255, 120 / 255, 214 / 255, 0.30),
                    lw=0, label=t("plots.gc_envelope"))
    a1.plot(x, per_T["squeeze_lo"], color=SERIES[0], lw=2, label=t("plots.squeeze_min"))
    a1.plot(x, per_T["squeeze_hi"], color=SERIES[1], lw=2, label=t("plots.squeeze_max"))
    a1.plot(x, per_T["squeeze_nominal"], color=TEXT, lw=1.5, ls=":", label=t("plots.squeeze_nominal"))
    a2.axhline(fill_limit, color=TEXT_2, lw=1, ls="--", label=t("plots.gc_fill_limit", v=fill_limit))
    if fill_hard is not None:
        a2.axhline(fill_hard, color=TEXT, lw=1, ls="--", label=t("plots.gc_fill_hard", v=fill_hard))
    a2.plot(x, per_T["fill_max"], color=SERIES[2], lw=2, label=t("plots.gc_fill_max"))
    a2.plot(x, per_T["fill_nominal"], color=SERIES[2], lw=1.5, ls=":", label=t("plots.gc_fill_nominal"))
    for a, title in ((a1, "plots.gc_squeeze"), (a2, "plots.gc_fill")):
        a.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        a.set_title(t(title), fontsize=10)
        _style(a)
    a2.set_xlabel(_T_label(temp_unit, "plots.temperature"), fontsize=9)
    _legend_below(fig, (a1, a2), ncol=4)
    return fig


# --------------------------------------------------------------------------- Monte Carlo histogram
def histogram_fig(values: pd.Series, title: str, limits=None, ranges=None, scale: float = 1.0,
                  percent: bool = True, unit: str = "") -> Figure:
    """Monte Carlo histogram with limit lines (dashed) and worst-case / RSS ranges (dotted)."""
    v = values.dropna().to_numpy() * scale
    fig = _new((4.6, 3.0))
    ax = fig.subplots()
    ax.hist(v, bins=60, color=SERIES[0], edgecolor="white", linewidth=0.4, label=t("plots.monte_carlo"))
    seen = set()
    for value, label in limits or []:
        ax.axvline(value * scale, color=TEXT, lw=1.3, ls="--", label=None if label in seen else label)
        seen.add(label)
    for i, (lo, hi, label) in enumerate(ranges or []):
        for j, xv in enumerate((lo, hi)):
            ax.axvline(xv * scale, color=SERIES[1 + i], lw=1.3, ls=":", label=label if j == 0 else None)
    if percent:
        ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=1))
    ax.set_xlabel(unit, fontsize=8)
    ax.set_ylabel(t("plots.count"), fontsize=8)
    ax.set_title(title, fontsize=9)
    _style(ax)
    _legend_below(fig, (ax,), ncol=2)
    return fig


# --------------------------------------------------------------------------- spring-energised seal
def se_fig(df: pd.DataFrame, temp_unit: str = "K", length_unit: str = "mm",
           compression_limits: tuple[float | None, float | None] = (None, None),
           gap_max: float | None = None) -> Figure:
    x = np.asarray(temp_from_K(df["T_housing_K"], temp_unit))
    k = LENGTH_SCALE[length_unit]
    fig = _new((7.2, 5.6))
    a1, a2 = fig.subplots(2, 1, sharex=True)
    lo, hi = compression_limits
    if lo is not None and hi is not None:
        a1.axhspan(lo * k, hi * k, color=BAND, lw=0)
    for v in (lo, hi):
        if v is not None:
            a1.axhline(v * k, color=TEXT_2, lw=1, ls="--")
    a1.plot(x, df["compression_max_m"] * k, color=SERIES[1], lw=2, label=t("plots.se_comp_max"))
    a1.plot(x, df["compression_min_m"] * k, color=SERIES[0], lw=2, label=t("plots.se_comp_min"))
    if df["max_extrusion_gap_m"].notna().any():
        a2.plot(x, df["max_extrusion_gap_m"] * k, color=SERIES[2], lw=2, label=t("plots.max_gap"))
        if gap_max is not None:
            a2.axhline(gap_max * k, color=TEXT_2, lw=1, ls="--")
    a2.plot(x, df["axial_clearance_m"] * k, color=SERIES[6], lw=2, label=t("plots.se_axial"))
    a2.set_ylim(bottom=0)
    missing = df["compression_min_m"].isna().to_numpy()
    for a, title in ((a1, "plots.se_compression"), (a2, "plots.se_gaps")):
        _shade_missing(a, x, missing)
        a.set_ylabel(f"[{length_unit}]", fontsize=9)
        a.set_title(t(title), fontsize=10)
        _style(a)
    a2.set_xlabel(_T_label(temp_unit), fontsize=9)
    _legend_below(fig, (a1, a2), ncol=4)
    return fig
