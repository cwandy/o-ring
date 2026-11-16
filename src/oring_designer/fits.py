"""ISO 286 tolerance classes (H7, f7, ...) -> limit deviations for a nominal size.

Values are the ISO 286-2 tables (data/iso286.yaml, source ``miki_jis_b0401``). js / JS classes
are +/- IT/2 by the ISO 286-1 definition, with IT taken from the h / H column of the same
grade. Upper-case = hole (internal feature), lower-case = shaft (external feature).
Only 3 mm < size <= 500 mm is tabulated; outside that range ``FitRangeError`` is raised and
the user enters the deviations by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[2] / "data" / "iso286.yaml"


class FitRangeError(ValueError):
    """Nominal size outside the tabulated range or unknown class."""


@dataclass(frozen=True)
class Deviation:
    upper_m: float
    lower_m: float

    @property
    def width_m(self) -> float:
        return self.upper_m - self.lower_m


@lru_cache(maxsize=None)
def _table() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


def _rows(cls: str) -> list:
    tab = _table()["classes"]
    if cls in tab:
        return tab[cls]
    m = re.fullmatch(r"(js|JS|Js)(\d+)", cls)
    if m:
        base = ("h" if m.group(1) == "js" else "H") + m.group(2)
        if base in tab:
            out = []
            for lo, hi, up, low in tab[base]:
                it = up - low
                out.append([lo, hi, it / 2, -it / 2])
            return out
    raise FitRangeError(f"unknown tolerance class {cls!r}")


def classes(kind: str | None = None) -> list[str]:
    """Available classes; ``kind`` = "hole", "shaft" or None (both)."""
    tab = _table()["classes"]
    holes = [c for c in tab if c[0].isupper()]
    shafts = [c for c in tab if c[0].islower()]
    holes += [f"JS{g}" for g in (6, 7, 8) if f"H{g}" in tab]
    shafts += [f"js{g}" for g in (5, 6, 7, 8) if f"h{g}" in tab]
    if kind == "hole":
        return holes
    if kind == "shaft":
        return shafts
    return holes + shafts


def deviation(cls: str, size_m: float) -> Deviation:
    """Upper and lower deviation (m) of class ``cls`` at nominal size ``size_m``."""
    mm = size_m * 1e3
    for lo, hi, up, low in _rows(cls):
        if lo < mm <= hi:
            return Deviation(up * 1e-6, low * 1e-6)
    raise FitRangeError(f"{cls}: {mm:.3f} mm outside the ISO 286 table (3-500 mm)")


def source() -> tuple[str, str]:
    t = _table()
    return t["source"], t["data_quality"]
