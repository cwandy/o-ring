"""Seal compound datasheet values (data/seal_compounds.yaml) and the formula-based squeeze
band derived from them.

Minimum squeeze (material-based): a ring with compression set C keeps only (1 - C) of its
initial deflection. The squeeze that remains at the worst tolerance / temperature corner
must still give the minimum absolute squeeze of the rules (Parker 3.6, 0.007 in), so

    s_min = (x_abs_min / W) / (1 - C)

Maximum squeeze: the rule set's squeeze_max (elastomers, Parker 3.6: 30 %) or, where that
is undefined, the upper end of the recommended band. TR10 (if given) is the functional low
temperature: below it the ring no longer follows the contraction of the gland.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[2] / "data" / "seal_compounds.yaml"


@dataclass(frozen=True)
class Compound:
    id: str
    seal_material: str
    name: str
    compression_set: float | None
    compression_set_conditions: str
    hardness_shore_a: float | None
    tr10_K: float | None
    brittle_point_K: float | None
    service_K: tuple[float | None, float | None]
    source: str
    data_quality: str


@lru_cache(maxsize=1)
def compounds() -> dict[str, Compound]:
    raw = yaml.safe_load(DATA.read_text(encoding="utf-8"))["compounds"]
    out = {}
    for c in raw:
        cs = c.get("compression_set") or {}
        out[c["id"]] = Compound(
            c["id"], c["seal_material"], c["name"], cs.get("value"), cs.get("conditions", ""),
            c.get("hardness_shore_a"), c.get("tr10_K"), c.get("brittle_point_K"),
            tuple(c.get("service_K") or (None, None)), c["source"], c["data_quality"])
    return out


def for_material(seal_material: str) -> list[Compound]:
    return [c for c in compounds().values() if c.seal_material == seal_material]


def min_squeeze(cs_m: float, compression_set: float, min_abs_m: float) -> float:
    if not 0 <= compression_set < 1:
        raise ValueError("compression set must be in [0, 1)")
    return (min_abs_m / cs_m) / (1.0 - compression_set)
