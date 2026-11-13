"""Static matplotlib figures for the design report (same encodings as the plotly charts).

Returns PNG bytes. Fonts: matplotlib's bundled DejaVu Sans (covers Turkish characters).
"""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402

from ..gland_types import GlandState  # noqa: E402
from ..i18n import t  # noqa: E402
from ..viz.plots import SERIES, TEMP_UNIT_LABEL, TEXT, TEXT_2, temp_from_K  # noqa: E402
from ..viz.section import PART_GROOVE, PART_MATING, compressed_stadium  # noqa: E402

GRID = "#e6e5e1"
BAND = (42 / 255, 120 / 255, 214 / 255, 0.12)
NODATA = (82 / 255, 81 / 255, 78 / 255, 0.18)
LENGTH_SCALE = {"mm": 1e3, "in": 1 / 0.0254}


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


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


def squeeze_fill_png(df: pd.DataFrame, temp_unit: str, squeeze_band=None, squeeze_max=None,
                     fill_band=None, fill_hard_max=None, low_temp_limit_K=None,
                     low_temp_band_K=None, seal_offset_K: float = 0.0) -> bytes:
    x = np.asarray(temp_from_K(df["T_housing_K"], temp_unit))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 5.6), sharex=True)
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
        a.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        _style(a)
    a1.set_title(t("plots.squeeze_title"), fontsize=10)
    a2.set_title(t("plots.fill_title"), fontsize=10)
    a2.set_xlabel(f"{t('plots.T_housing')} [{TEMP_UNIT_LABEL[temp_unit]}]", fontsize=9)
    h1, l1 = a1.get_legend_handles_labels()
    h2, l2 = a2.get_legend_handles_labels()
    fig.legend(h1 + h2, l1 + l2, loc="lower center", ncol=3, fontsize=7, frameon=False,
               bbox_to_anchor=(0.5, -0.06))
    fig.tight_layout()
    return _png(fig)


def clearance_png(df: pd.DataFrame, temp_unit: str, length_unit: str) -> bytes:
    x = np.asarray(temp_from_K(df["T_housing_K"], temp_unit))
    k = LENGTH_SCALE[length_unit]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.plot(x, df["diametral_clearance_m"] * k, color=SERIES[0], lw=2, label=t("plots.diametral_clearance"))
    ax.plot(x, df["max_extrusion_gap_m"] * k, color=SERIES[1], lw=2, label=t("plots.max_gap"))
    if df["allowed_gap_m"].notna().any():
        ax.plot(x, df["allowed_gap_m"] * k, color=TEXT_2, lw=1.5, ls="--", label=t("plots.allowed_gap"))
    ax.set_ylim(bottom=0)
    ax.set_ylabel(f"[{length_unit}]", fontsize=9)
    ax.set_xlabel(f"{t('plots.T_housing')} [{TEMP_UNIT_LABEL[temp_unit]}]", fontsize=9)
    ax.set_title(t("plots.clearance_title"), fontsize=10)
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    _style(ax)
    fig.tight_layout()
    return _png(fig)


def section_png(panels: list[tuple[str, GlandState | None]], kind: str, side: str = "nominal",
                length_unit: str = "mm", pressure_direction: str = "internal",
                corner_radius_m: float = 0.0) -> bytes:
    """Static version of ``viz.section.section_figure`` (same geometry, see its docstring;
    groove corner radii are not drawn here)."""
    k = LENGTH_SCALE[length_unit]
    nd = 3 if length_unit == "mm" else 4
    valid = [s for _, s in panels if s is not None]
    Gmax = max(s.gland_width_m for s in valid) * k if valid else 1.0
    Ymax = max(max(s.depth_max_m, s.cs_eff_m) for s in valid) * k if valid else 1.0
    m = 0.55 * Gmax
    fig, axs = plt.subplots(1, len(panels), figsize=(3.0 * len(panels), 2.9))
    axs = np.atleast_1d(axs)
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
            ax.add_patch(Polygon(right + left, closed=True, facecolor=(42 / 255, 120 / 255, 214 / 255, 0.35),
                                 edgecolor=SERIES[0], lw=1.5))
        sq = (W - L) / W
        ax.text(G / 2, 1.28 * Ymax, f"{t('plots.label_squeeze')} {sq:.1%} · {t('plots.label_fill')} {st.fill:.1%}",
                ha="center", fontsize=7, color=TEXT)
        ax.annotate("", (-0.3 * m, 0), (-0.3 * m, L), arrowprops=dict(arrowstyle="<->", lw=0.8))
        ax.text(-0.35 * m, L / 2, f"L {L:.{nd}f}", ha="right", va="center", fontsize=7)
        ax.annotate("", (0, -0.15 * Ymax), (G, -0.15 * Ymax), arrowprops=dict(arrowstyle="<->", lw=0.8))
        ax.text(G / 2, -0.3 * Ymax, f"G {G:.{nd}f}", ha="center", fontsize=7)
    fig.suptitle(f"{t('plots.section_title')} [{length_unit}] — {t('plots.section_note')}", fontsize=8,
                 color=TEXT_2, y=0.02)
    fig.tight_layout()
    return _png(fig)
