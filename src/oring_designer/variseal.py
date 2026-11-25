"""Turcon Variseal M2 groove dimensions from the Trelleborg catalogue (data/variseal_m2.yaml).

``groove(kind, d_m, pressure_Pa)`` returns the series and the installation dimensions for a
rod diameter (rod) or bore diameter (piston): groove diameter, groove width (+0.2/0), the
ISO 286 classes of the mating/groove diameters, the maximum radial clearance s_max for the
pressure and the maximum groove corner radius r1. The recommended (standard) range is used
first; otherwise the extended range ("on request" in the catalogue) is reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[2] / "data" / "variseal_m2.yaml"


class VarisealRangeError(ValueError):
    pass


@dataclass(frozen=True)
class VarisealGroove:
    series: str
    standard_range: bool  # False: extended range (catalogue: available on request)
    groove_diameter_m: float
    groove_width_m: float
    width_tol_m: float  # +tol / 0
    mating_class: str  # rod: h9 (rod), piston: H9 (bore)
    groove_class: str  # rod: H9 (groove D1), piston: h9 (groove d1)
    s_max_m: float | None  # None above 40 MPa (back-up ring required)
    r1_max_m: float
    backup_ring: bool
    source: str


@lru_cache(maxsize=1)
def _data() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class VarisealFace:
    series: str
    standard_range: bool
    depth_m: float
    depth_tol_m: float  # +tol / 0
    width_min_m: float
    r1_max_m: float
    s_max_m: float | None  # axial clearance; None above 40 MPa
    diameter_class: str  # internal: d7 H11 (groove O.D.), external: d8 h11 (groove I.D.)
    source: str


def face_groove(direction: str, d_m: float, pressure_Pa: float) -> VarisealFace:
    """Variseal HF: internal pressure -> groove outside diameter d7; external -> inside d8."""
    data = _data()
    rows = data["face"][direction]
    mm = d_m * 1e3
    row = next((r for r in rows if r["std"][0] <= mm <= r["std"][1]), None)
    standard = row is not None
    if row is None:
        row = next((r for r in rows if r["ext"][0] <= mm <= r["ext"][1]), None)
    if row is None:
        raise VarisealRangeError(f"{mm:.2f} mm outside the Variseal HF range")
    b4 = row["b4"]
    n = int(row["series"][-1])
    if mm > 700 and n in (3, 4):
        b4 = 8.0 if n == 3 else 11.0
    if mm > 1000 and n == 5:
        b4 = 18.0
    p = pressure_Pa / 1e6
    idx = next((i for i, b in enumerate(data["pressure_bounds_MPa"]) if p < b), None)
    return VarisealFace(row["series"], standard, row["h"] * 1e-3, row["h_tol"] * 1e-3, b4 * 1e-3,
                        row["r1"] * 1e-3, None if idx is None else row["s_max"][idx] * 1e-3,
                        "H11" if direction == "internal" else "h11", data["source_face"])


def groove(kind: str, d_m: float, pressure_Pa: float) -> VarisealGroove:
    if kind not in ("rod", "piston"):
        raise VarisealRangeError("Variseal M2 catalogue covers rod and piston glands only")
    data = _data()
    mm = d_m * 1e3
    rows = data[kind]
    row = next((r for r in rows if r["std"][0] <= mm <= r["std"][1]), None)
    standard = row is not None
    if row is None:
        row = next((r for r in rows if r["ext"][0] <= mm <= r["ext"][1]), None)
    if row is None:
        raise VarisealRangeError(f"{mm:.2f} mm outside the Variseal M2 {kind} range")
    p_MPa = pressure_Pa / 1e6
    idx = next((i for i, b in enumerate(data["pressure_bounds_MPa"]) if p_MPa < b), None)
    s_max = None if idx is None else row["s_max"][idx] * 1e-3
    gd = mm + row["offset"] if kind == "rod" else mm - row["offset"]
    series_no = int(row["series"][-1])
    return VarisealGroove(
        series=row["series"], standard_range=standard, groove_diameter_m=gd * 1e-3,
        groove_width_m=row["width"] * 1e-3, width_tol_m=0.2e-3,
        mating_class="h9" if kind == "rod" else "H9", groove_class="H9" if kind == "rod" else "h9",
        s_max_m=s_max, r1_max_m=data["r1_max_mm"][series_no] * 1e-3, backup_ring=idx is None,
        source=data[f"source_{kind}"])
