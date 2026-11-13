"""O-ring compression force and the clamp load needed to keep a face joint closed.

Compression load per unit length (Parker ORD 5700 Figures 2-4 to 2-8, ``data/
compression_force.yaml``): for a cross-section, percent compression and hardness the charts
give a range [min, max] in lbf per inch of seal. Interpolation: log(load) linear in percent
compression between the tabulated levels (5, 10, 20, 30, 40 %), linear in hardness between
50..90 Shore A, log-log in cross-section between the five chart cross-sections. Outside
5..40 % compression or 50..90 Shore A, or outside .070..275 in cross-section, no value is
returned (no extrapolation). Parker Table 2-3 gives the applicable part of the bar
(``typical``): normal hardness tolerance and ring I.D. < 25.4 mm -> middle third,
> 25.4 mm -> lower half.

Face joint clamp load (internal pressure): the joint stays closed (metal-to-metal contact)
if the clamp force exceeds the ring compression force plus the pressure end load acting
inside the sealing diameter::

    F_clamp,min = q_max * pi * D_mean + p * pi * D_seal^2 / 4

with q_max the upper compression load per length at the maximum squeeze, D_mean = ring I.D.
+ W and D_seal = groove O.D. (the ring bears on the O.D. wall under internal pressure; the
full groove O.D. area is a conservative choice). For external pressure the pressure pushes
the parts together and only the compression force remains. No safety factor is included.
Room-temperature data: elastomers harden when cold, increasing the force.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import yaml

from .loader import Dataset

LBF_PER_IN_TO_N_PER_M = 4.4482216152605 / 0.0254
LEVELS = (5, 10, 20, 30, 40)
HARDNESS = (50, 60, 70, 80, 90)


@lru_cache(maxsize=4)
def _table(data_dir: str):
    with open(f"{data_dir}/compression_force.yaml", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    cs = np.array([r["cs_nominal_in"] for r in raw["cross_sections"]])
    arr = np.zeros((len(cs), len(LEVELS), len(HARDNESS), 2))
    for i, r in enumerate(raw["cross_sections"]):
        for j, lvl in enumerate(LEVELS):
            for k, h in enumerate(HARDNESS):
                arr[i, j, k] = r["load"][lvl][h]
    return cs, arr


@dataclass(frozen=True)
class LoadRange:
    min_N_per_m: float
    max_N_per_m: float
    typical_min_N_per_m: float
    typical_max_N_per_m: float


def load_per_length(ds: Dataset, cs_m: float, squeeze: float, hardness: float,
                    ring_id_m: float | None = None) -> LoadRange | None:
    """Compression load per unit length (N/m) or None outside the chart ranges."""
    cs_tab, arr = _table(str(ds.data_dir))
    pct, cs_in = squeeze * 100, cs_m / 0.0254
    if not (LEVELS[0] <= pct <= LEVELS[-1] and HARDNESS[0] <= hardness <= HARDNESS[-1]
            and cs_tab[0] - 0.002 <= cs_in <= cs_tab[-1] + 0.002):
        return None
    log = np.log(arr)  # (cs, level, hardness, bound)
    # hardness (linear) and level (log-load linear in percent)
    by_h = np.array([[[np.interp(hardness, HARDNESS, log[i, j, :, b]) for b in (0, 1)]
                      for j in range(len(LEVELS))] for i in range(len(cs_tab))])
    by_l = np.array([[np.interp(pct, LEVELS, by_h[i, :, b]) for b in (0, 1)] for i in range(len(cs_tab))])
    lo, hi = (np.exp(np.interp(math.log(cs_in), np.log(cs_tab), by_l[:, b])) for b in (0, 1))
    lo, hi = min(lo, hi), max(lo, hi)
    if ring_id_m is not None and ring_id_m > 0.0254:
        t_lo, t_hi = lo, lo + (hi - lo) / 2  # lower half
    else:
        t_lo, t_hi = lo + (hi - lo) / 3, lo + 2 * (hi - lo) / 3  # middle third
    k = LBF_PER_IN_TO_N_PER_M
    return LoadRange(lo * k, hi * k, t_lo * k, t_hi * k)


@dataclass(frozen=True)
class FaceClampLoad:
    compression_N: tuple[float, float]  # (typical max, chart max) at the maximum squeeze
    pressure_N: float
    clamp_min_N: float  # chart max compression + pressure load (conservative)
    clamp_typical_N: float  # typical max compression + pressure load


def face_clamp_load(load_at_max_squeeze: LoadRange, ring_id_m: float, cs_m: float,
                    seal_diameter_m: float, pressure_Pa: float,
                    direction: str = "internal") -> FaceClampLoad:
    circumference = math.pi * (ring_id_m + cs_m)
    comp_typ = load_at_max_squeeze.typical_max_N_per_m * circumference
    comp_max = load_at_max_squeeze.max_N_per_m * circumference
    p_load = pressure_Pa * math.pi * seal_diameter_m**2 / 4 if direction == "internal" else 0.0
    return FaceClampLoad((comp_typ, comp_max), p_load, comp_max + p_load, comp_typ + p_load)
