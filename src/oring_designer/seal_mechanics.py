"""O-ring compression load and contact pressure from material properties (Lindley 1966).

Toroidal rubber ring of cross-section d compressed by x between flat plates (Lindley,
J. Strain Analysis 1 (1966) 190, equation (8)); per unit length of ring::

    f = d E (alpha_T + k beta_T),          x = d (1 - cos t)
    alpha_T = 4/3 ln(sec t + tan t) - 4/3 sin t
    beta_T  = -1/2 ln(sec t + tan t) + 1/3 sin t + 1/6 sec t tan t

E and k from the paper's Appendix 1 (vs hardness, data/lindley1966.yaml). The load is
carried by the rectangle of breadth b = d sin t (Fig. 3), so the mean contact pressure on
the sealing face is p_c = f / b. Sealing criterion (literature, e.g. FE studies of O-ring
seals): contact pressure must exceed the fluid pressure; the required squeeze is the one at
which p_c = p (margin 1.0, no value found in the sources).

Limits: strain-independent modulus (no temperature dependence: no sourced data); valid for
elastomers; the paper reports good agreement up to ~30 % compression and under-estimation
above. Hardness outside 35-75 IRHD is extrapolated (log E linear, k held) and flagged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

DATA = Path(__file__).resolve().parents[2] / "data" / "lindley1966.yaml"
KGF_CM2 = 0.0980665e6  # Pa


@dataclass(frozen=True)
class RubberModulus:
    E_Pa: float
    k: float
    extrapolated: bool


@lru_cache(maxsize=1)
def _table():
    d = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    return (np.array(d["hardness_IRHD"], float), np.log(np.array(d["E_kgf_cm2"], float) * KGF_CM2),
            np.array(d["k"], float))


def modulus(hardness: float) -> RubberModulus:
    H, logE, k = _table()
    if H[0] <= hardness <= H[-1]:
        return RubberModulus(float(math.exp(np.interp(hardness, H, logE))), float(np.interp(hardness, H, k)), False)
    i = (0, 1) if hardness < H[0] else (-2, -1)
    slope = (logE[i[1]] - logE[i[0]]) / (H[i[1]] - H[i[0]])
    E = math.exp(logE[i[0]] + slope * (hardness - H[i[0]]))
    return RubberModulus(E, float(k[0] if hardness < H[0] else k[-1]), True)


def _theta(squeeze: float) -> float:
    if not 0 < squeeze < 1:
        raise ValueError("squeeze must be between 0 and 1")
    return math.acos(1.0 - squeeze)


def alpha_beta(squeeze: float) -> tuple[float, float]:
    t = _theta(squeeze)
    L = math.log(1 / math.cos(t) + math.tan(t))
    s, st = math.sin(t), math.tan(t) / math.cos(t)
    return 4 / 3 * L - 4 / 3 * s, -0.5 * L + s / 3 + st / 6


def load_per_length(cs_m: float, squeeze: float, hardness: float) -> float:
    """Compression load per unit length of ring, N/m."""
    m = modulus(hardness)
    a, b = alpha_beta(squeeze)
    return cs_m * m.E_Pa * (a + m.k * b)


def contact_pressure(cs_m: float, squeeze: float, hardness: float) -> float:
    """Mean contact pressure on the sealing face, Pa (load / contact breadth d sin t)."""
    return load_per_length(cs_m, squeeze, hardness) / (cs_m * math.sin(_theta(squeeze)))


def required_squeeze(pressure_Pa: float, hardness: float, cs_m: float = 1e-3, margin: float = 1.0) -> float:
    """Smallest squeeze with contact pressure >= margin * pressure (independent of cs)."""
    target = margin * pressure_Pa
    lo, hi = 1e-4, 0.5
    if contact_pressure(cs_m, hi, hardness) < target:
        return float("inf")
    if contact_pressure(cs_m, lo, hardness) >= target:
        return lo
    for _ in range(80):
        mid = (lo + hi) / 2
        if contact_pressure(cs_m, mid, hardness) >= target:
            hi = mid
        else:
            lo = mid
    return hi
