"""Shared chart style and small geometry helpers (no plotting library imported here).

Used by the plotly charts (browser UI), the matplotlib figures (report and desktop UI) and
the section drawings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e6e5e1"
PART_GROOVE = "#c9c8c3"
PART_MATING = "#a3a29c"
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
