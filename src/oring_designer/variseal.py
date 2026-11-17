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
