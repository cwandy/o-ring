"""Plotly charts: squeeze/fill vs temperature, clearance vs temperature, dL/L curves.

Design notes (dataviz method): one y-axis per chart (squeeze and fill are separate
stacked panels sharing the temperature axis), categorical colours in fixed order from the
validated default palette, 2 px lines, recessive grid, x-unified hover, legend always
shown for >= 2 series. Allowed bands are neutral grey fills; status colours are not used
for series. Regions without thermal data are shaded and labelled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..i18n import t

SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e6e5e1"
BAND = "rgba(42, 120, 214, 0.12)"
NODATA = "rgba(82, 81, 78, 0.18)"

TEMP_UNIT_LABEL = {"K": "K", "degC": "°C", "degF": "°F"}
LENGTH_SCALE = {"mm": 1e3, "in": 1 / 0.0254}


def temp_from_K(T_K, unit: str):
    T = np.asarray(T_K, dtype=float)
    if unit == "K":
        return T
    if unit == "degC":
        return T - 273.15
    if unit == "degF":
        return (T - 273.15) * 9 / 5 + 32
    raise ValueError(unit)


def _layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(color=TEXT, size=13),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="left", x=0,
                    font=dict(color=TEXT_2)),
        margin=dict(l=60, r=20, t=100, b=50),
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID,
                     tickfont=dict(color=TEXT_2))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID,
                     tickfont=dict(color=TEXT_2))
    return fig


def _line(x, y, name, color, dash=None, row=None, col=None, fig=None, fmt=".1%"):
    trace = go.Scatter(x=x, y=y, name=name, mode="lines", connectgaps=False,
                       line=dict(color=color, width=2, dash=dash),
                       hovertemplate=f"%{{y:{fmt}}}")
    if fig is not None:
        fig.add_trace(trace, row=row, col=col)
    return trace


def _no_data_regions(x: np.ndarray, missing: np.ndarray) -> list[tuple[float, float]]:
    regions, start = [], None
    for i, m in enumerate(missing):
        if m and start is None:
            start = i
        if (not m or i == len(missing) - 1) and start is not None:
            end = i if m else i - 1
            lo = x[max(start - 1, 0)] if start > 0 else x[start]
            hi = x[min(end + 1, len(x) - 1)] if end < len(x) - 1 else x[end]
            regions.append((float(lo), float(hi)))
            start = None
    return regions


def _shade_no_data(fig, x, missing, rows):
    for lo, hi in _no_data_regions(x, missing):
        for r in rows:
            fig.add_vrect(exclude_empty_subplots=False, x0=lo, x1=hi, fillcolor=NODATA, line_width=0, layer="below", row=r, col=1)
        fig.add_annotation(x=(lo + hi) / 2, y=1.0, yref="paper", text=t("plots.no_data"),
                           showarrow=False, font=dict(color=TEXT_2, size=11), yanchor="bottom")


def _range(values: pd.DataFrame, refs: list[float], pad: float = 0.03) -> list[float] | None:
    """Y range covering the data and the reference lines/bands, so limits stay in view."""
    data = values.to_numpy(dtype=float)
    data = data[np.isfinite(data)]
    if data.size == 0 and not refs:
        return None
    lo = min([*data.tolist(), *refs])
    hi = max([*data.tolist(), *refs])
    return [lo - pad, hi + pad]


def squeeze_fill_figure(
    df: pd.DataFrame,
    temp_unit: str = "K",
    x_column: str = "T_housing_K",
    squeeze_band: tuple[float, float] | None = None,
    squeeze_max: float | None = None,
    fill_band: tuple[float, float] | None = None,
    fill_hard_max: float | None = None,
    low_temp_limit_K: float | None = None,
    low_temp_band_K: float | None = None,
    seal_offset_K: float = 0.0,
) -> go.Figure:
    """Squeeze (min/max around the circumference) and gland fill vs temperature.

    ``seal_offset_K`` = T_seal - T(x): vertical seal-temperature lines are drawn at the x
    position where the seal reaches the limit (lag mode).
    """
    x = temp_from_K(df[x_column], temp_unit)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=(t("plots.squeeze_title"), t("plots.fill_title")))
    if squeeze_band:
        fig.add_hrect(exclude_empty_subplots=False, y0=squeeze_band[0], y1=squeeze_band[1], fillcolor=BAND, line_width=0,
                      layer="below", row=1, col=1)
        fig.add_annotation(x=x.max(), y=squeeze_band[1], text=t("plots.recommended_band"),
                           showarrow=False, xanchor="right", yanchor="bottom",
                           font=dict(color=TEXT_2, size=11), row=1, col=1)
    if squeeze_max is not None:
        fig.add_hline(exclude_empty_subplots=False, y=squeeze_max, line=dict(color=TEXT_2, width=1, dash="dash"), row=1, col=1)
    _line(x, df["squeeze_max"], t("plots.squeeze_max"), SERIES[1], fig=fig, row=1, col=1)
    _line(x, df["squeeze_nominal"], t("plots.squeeze_nominal"), SERIES[0], dash="dot", fig=fig, row=1, col=1)
    _line(x, df["squeeze_min"], t("plots.squeeze_min"), SERIES[0], fig=fig, row=1, col=1)

    if fill_band:
        fig.add_hrect(exclude_empty_subplots=False, y0=fill_band[0], y1=fill_band[1], fillcolor=BAND, line_width=0,
                      layer="below", row=2, col=1)
    if fill_hard_max is not None:
        fig.add_hline(exclude_empty_subplots=False, y=fill_hard_max, line=dict(color=TEXT_2, width=1, dash="dash"), row=2, col=1)
    _line(x, df["fill"], t("plots.fill"), SERIES[2], fig=fig, row=2, col=1)

    for T_lim, label, dash in (
        (low_temp_limit_K, t("plots.low_temp_limit"), "dash"),
        (None if low_temp_limit_K is None or low_temp_band_K is None
         else low_temp_limit_K + low_temp_band_K, t("plots.low_temp_band"), "dot"),
    ):
        if T_lim is None:
            continue
        xv = float(temp_from_K(T_lim - seal_offset_K, temp_unit))
        if x.min() <= xv <= x.max():
            fig.add_vline(exclude_empty_subplots=False, x=xv, line=dict(color=TEXT, width=1, dash=dash))
            fig.add_annotation(x=xv, y=0, yref="paper", text=label, showarrow=False,
                               xanchor="left", yanchor="bottom", textangle=-90,
                               font=dict(color=TEXT_2, size=11))

    _shade_no_data(fig, np.asarray(x), df["squeeze_min"].isna().to_numpy(), rows=(1, 2))
    sq_refs = [v for v in (*(squeeze_band or ()), squeeze_max) if v is not None]
    fill_refs = [v for v in (*(fill_band or ()), fill_hard_max) if v is not None]
    fig.update_yaxes(tickformat=".0%", range=_range(df[["squeeze_min", "squeeze_max"]], sq_refs),
                     row=1, col=1)
    fig.update_yaxes(tickformat=".0%", range=_range(df[["fill"]], fill_refs), row=2, col=1)
    xlabel = t("plots.T_housing") if x_column == "T_housing_K" else t("plots.T_seal")
    fig.update_xaxes(title_text=f"{xlabel} [{TEMP_UNIT_LABEL[temp_unit]}]", row=2, col=1)
    return _layout(fig, 620)


def clearance_figure(df: pd.DataFrame, temp_unit: str = "K", length_unit: str = "mm",
                     x_column: str = "T_housing_K") -> go.Figure:
    """Diametral clearance, worst-case one-sided extrusion gap and allowed gap vs temperature."""
    x = temp_from_K(df[x_column], temp_unit)
    k = LENGTH_SCALE[length_unit]
    fmt = ".3f" if length_unit == "mm" else ".4f"
    fig = go.Figure()
    _line(x, df["diametral_clearance_m"] * k, t("plots.diametral_clearance"), SERIES[0], fig=fig, fmt=fmt)
    _line(x, df["max_extrusion_gap_m"] * k, t("plots.max_gap"), SERIES[1], fig=fig, fmt=fmt)
    if df["allowed_gap_m"].notna().any():
        _line(x, df["allowed_gap_m"] * k, t("plots.allowed_gap"), TEXT_2, dash="dash", fig=fig, fmt=fmt)
    fig.update_layout(title=t("plots.clearance_title"))
    fig.update_yaxes(title_text=f"[{length_unit}]", rangemode="tozero")
    xlabel = t("plots.T_housing") if x_column == "T_housing_K" else t("plots.T_seal")
    fig.update_xaxes(title_text=f"{xlabel} [{TEMP_UNIT_LABEL[temp_unit]}]")
    missing = df["diametral_clearance_m"].isna().to_numpy() & df["squeeze_min"].isna().to_numpy()
    for lo, hi in _no_data_regions(np.asarray(x), missing):
        fig.add_vrect(exclude_empty_subplots=False, x0=lo, x1=hi, fillcolor=NODATA, line_width=0, layer="below")
    return _layout(fig, 380)


def thermal_strain_figure(curves: dict, temp_unit: str = "K") -> go.Figure:
    """dL/L (relative to 293.15 K) of the given curves over their data ranges.

    ``curves``: display name -> ThermalStrainCurve (curves without data are skipped).
    """
    fig = go.Figure()
    for i, (name, c) in enumerate(curves.items()):
        if not c.has_data:
            continue
        T = np.linspace(c.T_min_K, c.T_max_K, 400)
        _line(temp_from_K(T, temp_unit), c.eps(T) * 100, name, SERIES[i % len(SERIES)], fig=fig,
              fmt=".3f")
    fig.update_layout(title=t("plots.strain_title"))
    fig.update_yaxes(title_text="ΔL/L [%]")
    fig.update_xaxes(title_text=f"{t('plots.temperature')} [{TEMP_UNIT_LABEL[temp_unit]}]")
    return _layout(fig, 420)


def mc_histogram(
    values: pd.Series,
    title: str,
    limits: list[tuple[float, str]] | None = None,
    ranges: list[tuple[float, float, str]] | None = None,
    scale: float = 1.0,
    fmt: str = ".1%",
    unit: str = "",
) -> go.Figure:
    """Monte Carlo histogram of one output with limit lines (dashed) and comparison ranges.

    ``limits``: (value, label) vertical lines, e.g. allowed limits.
    ``ranges``: (low, high, label) intervals drawn as dotted lines, e.g. worst-case / RSS.
    Line styles are explained in the legend (no labels drawn over the bars).
    """
    v = values.dropna().to_numpy() * scale
    fig = go.Figure(go.Histogram(x=v, nbinsx=60, name=t("plots.monte_carlo"),
                                 marker=dict(color=SERIES[0]),
                                 marker_line=dict(color=SURFACE, width=1),
                                 hovertemplate=f"%{{x:{fmt}}}<br>n = %{{y}}<extra></extra>"))

    def legend_entry(name: str, color: str, dash: str) -> None:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name=name,
                                 line=dict(color=color, width=1.5, dash=dash)))

    seen: set[str] = set()
    for value, label in limits or []:
        fig.add_vline(x=value * scale, line=dict(color=TEXT, width=1.5, dash="dash"))
        if label not in seen:
            legend_entry(label, TEXT, "dash")
            seen.add(label)
    for i, (lo, hi, label) in enumerate(ranges or []):
        color = SERIES[1 + i]
        for x in (lo, hi):
            fig.add_vline(x=x * scale, line=dict(color=color, width=1.5, dash="dot"))
        legend_entry(label, color, "dot")
    fig.update_xaxes(tickformat=fmt, title_text=unit)
    fig.update_yaxes(title_text=t("plots.count"))
    fig.update_layout(title=dict(text=title), bargap=0.02)
    _layout(fig, 400)
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.28, xanchor="left", x=0),
                      margin=dict(t=50, b=120))
    return fig


def se_figure(df: pd.DataFrame, temp_unit: str = "K", length_unit: str = "mm",
              compression_limits: tuple[float | None, float | None] = (None, None),
              gap_max: float | None = None) -> go.Figure:
    """Spring-energized seal: compression (wide / tight side) and gaps vs housing temperature."""
    x = temp_from_K(df["T_housing_K"], temp_unit)
    k = LENGTH_SCALE[length_unit]
    fmt = ".3f" if length_unit == "mm" else ".4f"
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=(t("plots.se_compression"), t("plots.se_gaps")))
    lo, hi = compression_limits
    if lo is not None and hi is not None:
        fig.add_hrect(exclude_empty_subplots=False, y0=lo * k, y1=hi * k, fillcolor=BAND,
                      line_width=0, layer="below", row=1, col=1)
    for v in (lo, hi):
        if v is not None:
            fig.add_hline(exclude_empty_subplots=False, y=v * k,
                          line=dict(color=TEXT_2, width=1, dash="dash"), row=1, col=1)
    _line(x, df["compression_max_m"] * k, t("plots.se_comp_max"), SERIES[1], fig=fig, row=1, col=1, fmt=fmt)
    _line(x, df["compression_min_m"] * k, t("plots.se_comp_min"), SERIES[0], fig=fig, row=1, col=1, fmt=fmt)
    if df["max_extrusion_gap_m"].notna().any():
        _line(x, df["max_extrusion_gap_m"] * k, t("plots.max_gap"), SERIES[2], fig=fig, row=2, col=1, fmt=fmt)
        if gap_max is not None:
            fig.add_hline(exclude_empty_subplots=False, y=gap_max * k,
                          line=dict(color=TEXT_2, width=1, dash="dash"), row=2, col=1)
    _line(x, df["axial_clearance_m"] * k, t("plots.se_axial"), SERIES[6], fig=fig, row=2, col=1, fmt=fmt)
    _shade_no_data(fig, np.asarray(x), df["compression_min_m"].isna().to_numpy(), rows=(1, 2))
    fig.update_yaxes(title_text=f"[{length_unit}]", row=1, col=1)
    fig.update_yaxes(title_text=f"[{length_unit}]", rangemode="tozero", row=2, col=1)
    fig.update_xaxes(title_text=f"{t('plots.T_housing')} [{TEMP_UNIT_LABEL[temp_unit]}]", row=2, col=1)
    return _layout(fig, 560)
