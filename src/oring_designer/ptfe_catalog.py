"""PTFE O-ring groove dimensions from the Trelleborg catalogue (data/trelleborg_ptfe_oring.yaml).

Exact cross-sections are taken from the table; cross-sections between two rows are linearly
interpolated (flagged); outside 1.50-8.40 mm no catalogue value is returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

DATA = Path(__file__).resolve().parents[2] / "data" / "trelleborg_ptfe_oring.yaml"


@dataclass(frozen=True)
class PtfeGroove:
    depth_m: float
    width_m: float
    radius_m: float
    depth_tol_m: tuple[float, float]  # (lower, upper) deviation
    width_tol_m: tuple[float, float]
    interpolated: bool
    source: str


@lru_cache(maxsize=1)
def _data() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


def groove(cs_m: float) -> PtfeGroove | None:
    d = _data()
    rows = np.array(d["rows"], float)
    mm = cs_m * 1e3
    if not rows[0, 0] - 0.005 <= mm <= rows[-1, 0] + 0.005:
        return None
    exact = np.isclose(rows[:, 0], mm, atol=0.005)
    if exact.any():
        h, b, r = (float(v) for v in rows[exact][0, 1:])
        interp = False
    else:
        h, b, r = (float(np.interp(mm, rows[:, 0], rows[:, i])) for i in (1, 2, 3))
        interp = True
    dt, wt = d["depth_tol_mm"], d["width_tol_mm"]
    return PtfeGroove(h * 1e-3, b * 1e-3, r * 1e-3, (dt[0] * 1e-3, dt[1] * 1e-3),
                      (wt[0] * 1e-3, wt[1] * 1e-3), interp, d["source"])
