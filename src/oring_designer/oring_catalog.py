"""Trelleborg elastomer O-ring housing dimensions and radial clearance
(data/trelleborg_oring_housing.yaml: Tables 23 and 17, B.2.4 initial compression)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

DATA = Path(__file__).resolve().parents[2] / "data" / "trelleborg_oring_housing.yaml"


@dataclass(frozen=True)
class Housing:
    depth_m: float | None  # radial: housing depth t (dynamic or static); face: groove depth h
    width_m: float  # radial b1 / axial b4
    radius_m: float
    width_tol_m: float  # +tol / 0
    depth_dev_m: tuple[float, float] | None  # face: (0, +0.1); radial: None (diameters H8/f7)
    interpolated: bool
    source: str


@lru_cache(maxsize=1)
def _data() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


def housing(cs_m: float, gland: str, dynamic: bool = False) -> Housing | None:
    """gland: "face" (axial static) or "radial". None outside the table."""
    d = _data()
    rows = np.array([[np.nan if v is None else v for v in r] for r in d["housing"]], float)
    mm = cs_m * 1e3
    if not rows[0, 0] - 0.005 <= mm <= rows[-1, 0] + 0.005:
        return None
    col_depth = 4 if gland == "face" else (1 if dynamic else 2)
    col_width = 5 if gland == "face" else 3
    exact = np.isclose(rows[:, 0], mm, atol=0.005)

    def val(c):
        if exact.any():
            return float(rows[exact][0, c])
        ok = ~np.isnan(rows[:, c])
        return float(np.interp(mm, rows[ok, 0], rows[ok, c]))

    depth = val(col_depth)
    tol = d["tolerances_mm"]
    wkey = "b4" if gland == "face" else "b1"
    return Housing(None if math.isnan(depth) else depth * 1e-3, val(col_width) * 1e-3, val(6) * 1e-3,
                   tol[wkey][1] * 1e-3,
                   (tol["h"][0] * 1e-3, tol["h"][1] * 1e-3) if gland == "face" else None,
                   not exact.any(), d["source"])


def initial_compression(kind: str) -> tuple[float, float]:
    """kind: radial_dynamic | radial_static | axial_static (approximate, B.2.4)."""
    lo, hi = _data()["initial_compression"][kind]
    return float(lo), float(hi)


def _row_value(table: list, p_MPa: float, i_bin: int) -> float | None:
    for p_max, vals in table:
        if p_MPa <= p_max + 1e-9:
            return vals[i_bin]
    return None


def radial_clearance(cs_m: float, pressure_Pa: float, hardness: float) -> float | None:
    """Maximum permissible radial clearance S (m), Table 17; None above the table pressure
    (back-up ring). Between 70 and 90 Shore A linear; below 70 the 70 values, above 90 the 90."""
    d = _data()["clearance"]
    mm = cs_m * 1e3
    i = next(k for k, b in enumerate(d["cs_bins"]) if mm <= float(b))
    p = pressure_Pa / 1e6
    s70, s90 = _row_value(d["70"], p, i), _row_value(d["90"], p, i)
    if hardness <= 70:
        s = s70
    elif hardness >= 90:
        s = s90
    elif s70 is None or s90 is None:
        s = None
    else:
        s = s70 + (s90 - s70) * (hardness - 70) / 20
    return None if s is None else s * 1e-3


def clearance_table_pressure_Pa(hardness: float) -> float:
    """Highest pressure covered by Table 17 for this hardness (the 70 rows below 90 Shore A)."""
    d = _data()["clearance"]
    return float(d["90" if hardness >= 90 else "70"][-1][0]) * 1e6


# --------------------------------------------------------------------------- back-up rings
BU_DATA = Path(__file__).resolve().parents[2] / "data" / "trelleborg_backup_ring.yaml"


@dataclass(frozen=True)
class BackupRing:
    n: int  # 1 or 2
    ring_width_m: float  # radial height W
    ring_thickness_m: float  # T
    housing_depth_m: float  # radial depth = d3 offset / 2
    groove_width_m: float  # b2 (one ring) or b3 (two rings)
    width_tol_m: float  # +0.25
    radius_m: float
    interpolated: bool
    source: str


@lru_cache(maxsize=1)
def _bu() -> dict:
    return yaml.safe_load(BU_DATA.read_text(encoding="utf-8"))


def backup_ring(cs_m: float, n: int, dynamic: bool = False) -> BackupRing | None:
    """Table 72 (external sealing / piston). None outside 1.50-8.40 mm."""
    d = _bu()
    rows = np.array(d["rows"], float)
    mm = cs_m * 1e3
    if not rows[0, 0] - 0.005 <= mm <= rows[-1, 0] + 0.005:
        return None
    exact = np.isclose(rows[:, 0], mm, atol=0.005)

    def val(c):
        return float(rows[exact][0, c]) if exact.any() else float(np.interp(mm, rows[:, 0], rows[:, c]))

    W = val(1 if dynamic else 2)
    off = val(4 if dynamic else 5)
    return BackupRing(n, W * 1e-3, val(3) * 1e-3, off / 2 * 1e-3, val(6 if n == 1 else 7) * 1e-3, 0.25e-3,
                      val(8) * 1e-3, not exact.any(), d["source"])
