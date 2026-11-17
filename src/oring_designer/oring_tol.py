"""Automatic O-ring I.D. and cross-section tolerances.

Elastomers: from the standard size tables (data/standards): AS568 by default (SAE AS568
tolerance of the size with the nearest cross-section and, within it, the nearest I.D.), or
ISO 3601-1 when the standard is chosen. Thermoplastic (PTFE / PCTFE) rings are machined to
order: default +/-0.1 mm on both, editable by the user.
"""

from __future__ import annotations

from dataclasses import dataclass

from .loader import load_standard_sizes

THERMOPLASTIC_DEFAULT_TOL_M = 0.1e-3


@dataclass(frozen=True)
class RingTolerance:
    id_tol_m: float
    cs_tol_m: float
    size: str | None  # matching standard size (nearest)


def standard_tolerance(id_m: float, cs_m: float, standard: str = "AS568") -> RingTolerance:
    sizes = load_standard_sizes()
    s = sizes[sizes.standard.str.startswith(standard)]
    cs_near = s.iloc[(s.cs_m - cs_m).abs().argsort()].cs_m.iloc[0]
    same_cs = s[(s.cs_m - cs_near).abs() < 1e-9]
    row = same_cs.iloc[(same_cs.id_m - id_m).abs().argsort()].iloc[0]
    return RingTolerance(float(row.id_tol_m), float(row.cs_tol_m), str(row["size"]))
