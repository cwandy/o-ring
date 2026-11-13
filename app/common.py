"""Shared Streamlit helpers (sidebar units, data banner, status table)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from oring_designer.checks import CheckResult, Status
from oring_designer.i18n import render_check, t
from oring_designer.loader import Dataset, load_dataset

STATUS_STYLE = {  # dataviz status palette; always shown with icon + label
    "PASS": ("✅", "rgba(12, 163, 12, 0.18)"),
    "WARN": ("⚠️", "rgba(250, 178, 25, 0.30)"),
    "FAIL": ("❌", "rgba(208, 59, 59, 0.22)"),
}


@st.cache_resource
def dataset() -> Dataset:
    return load_dataset()


def sidebar_units() -> dict[str, str]:
    st.sidebar.header(t("ui.units"))
    length = st.sidebar.radio(t("ui.length_unit"), ["mm", "in"], horizontal=True)
    temp = st.sidebar.radio(t("ui.temp_unit"), ["degC", "K", "degF"], horizontal=True,
                            format_func=lambda u: {"degC": "°C", "K": "K", "degF": "°F"}[u])
    pressure = st.sidebar.radio(t("ui.pressure_unit"), ["bar", "MPa", "psi"], horizontal=True)
    return {"length": length, "temp": temp, "pressure": pressure}


def status_label(status: Status | str) -> str:
    s = status.value if isinstance(status, Status) else status
    return f"{STATUS_STYLE[s][0]} {t('status.' + s)}"


def status_table(rows: list[tuple[Status, str, str | None]]) -> None:
    """rows: (status, message, optional temperature text)."""
    has_T = any(r[2] for r in rows)
    data = {
        t("ui.col_status"): [status_label(r[0]) for r in rows],
        t("ui.col_check"): [r[1] for r in rows],
    }
    if has_T:
        data[t("ui.col_T")] = [r[2] or "" for r in rows]
    df = pd.DataFrame(data)
    colors = [STATUS_STYLE[r[0].value][1] for r in rows]

    def _style(col):
        if col.name == t("ui.col_status"):
            return [f"background-color: {c}" for c in colors]
        return ["" for _ in col]

    st.table(df.style.apply(_style).hide(axis="index"))  # st.table wraps long messages


def result_rows(results: list[CheckResult]) -> list[tuple[Status, str, None]]:
    order = {Status.FAIL: 0, Status.WARN: 1, Status.PASS: 2}
    return [(r.status, render_check(r), None) for r in sorted(results, key=lambda r: order[r.status])]


def data_banner(needs: bool) -> None:
    if needs:
        st.warning(t("ui.data_banner"), icon="⚠️")


def section_view(design, ds, states: list[tuple[str, "ThermalState"]], kind: str, length_unit: str,
                 key: str) -> None:
    """Scaled cross-section panels for the given thermal states (None where data are missing)."""
    from oring_designer.checks import run_checks
    from oring_designer.thermal import ThermalDataError
    from oring_designer.viz.section import section_figure

    side = "nominal"
    if kind != "face":
        side = st.radio(t("ui.section_side"), ["nominal", "tight", "wide"], horizontal=True,
                        format_func=lambda k: t(f"plots.side_{k}"), key=key)
    panels = []
    for label, state in states:
        try:
            panels.append((label, run_checks(design, ds, state)[0]))
        except ThermalDataError:
            panels.append((label, None))
    gl = design.gland
    fig = section_figure(panels, kind, side, length_unit,
                         getattr(gl, "pressure_direction", "internal"), gl.corner_radius_m)
    st.plotly_chart(fig, use_container_width=True, theme=None)
