"""Tolerance analysis: worst-case, RSS and Monte Carlo (SPEC §7).

Toleranced quantities are the dimensions of the design (gland dimensions, O-ring I.D. and
cross-section), each given as a nominal value with lower and upper deviations
(asymmetric allowed, e.g. +0.05/-0). All analyses are done at one thermal state (or a list
of states for worst-case) using the full single-point model (``checks.run_checks``).

Methods
-------
* Worst-case: every corner of the tolerance box (2^n combinations) plus the nominal point
  is evaluated; reported are the minimum and maximum of each output and the most severe
  status of each check family. Monotonic outputs reach their extremes at corners; for
  non-monotonic outputs this is an approximation.
* RSS: outputs are linearised at the mean point (the middle of each tolerance band) with
  central finite differences; with sigma_i = (upper - lower) / 6 (tolerance band = +/-3
  sigma) the output standard deviation is sqrt(sum((df/dx_i * sigma_i)^2)). The reported
  range is mean +/- 3 sigma. Linearisation is the stated simplification.
* Monte Carlo: N samples (default 20,000); each dimension is drawn independently from a
  normal distribution with mean at the middle of its band and sigma = band/6 (tolerance =
  +/-3 sigma), or uniformly over the band. The seed can be fixed for reproducibility.
  Output: per-sample values of each output, and per check family the fraction of samples
  that are PASS / WARN / FAIL.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

from .checks import CheckResult, Design, Status, run_checks
from .gland_types import ThermalState
from .loader import Dataset
from .sweep import check_family, severity_key

Distribution = Literal["normal", "uniform"]
DEFAULT_MC_SAMPLES = 20_000
MAX_WORST_CASE_PARAMS = 12
OUTPUTS = ("squeeze_min", "squeeze_max", "fill", "stretch", "max_extrusion_gap_m",
           "circumferential_compression")
_RANK = {Status.PASS: 0, Status.WARN: 1, Status.FAIL: 2}


@dataclass(frozen=True)
class Tolerance:
    """Deviation band around the nominal value: [nominal + lower_m, nominal + upper_m]."""

    lower_m: float
    upper_m: float

    def __post_init__(self) -> None:
        if self.lower_m > self.upper_m:
            raise ValueError("tolerance lower deviation exceeds upper deviation")

    @classmethod
    def symmetric(cls, tol_m: float) -> Tolerance:
        return cls(-abs(tol_m), abs(tol_m))

    @property
    def mid_m(self) -> float:
        return (self.lower_m + self.upper_m) / 2.0

    @property
    def sigma_m(self) -> float:
        return (self.upper_m - self.lower_m) / 6.0


# A parameter is addressed as "gland.<field>" or "oring.<field>".
Tolerances = dict[str, Tolerance]


def toleranceable_fields(design: Design) -> list[str]:
    """Dimension fields that can carry a tolerance for this design."""
    fields = [f"gland.{name}" for name, value in vars(design.gland).items()
              if name.endswith("_m") and name != "eccentricity_m" and isinstance(value, float)]
    return fields + ["oring.id_m", "oring.cs_m"]


def nominal_value(design: Design, path: str) -> float:
    obj, name = path.split(".")
    return getattr(getattr(design, obj), name)


def with_values(design: Design, values: dict[str, float]) -> Design:
    """Copy of ``design`` with the given absolute dimension values."""
    gland_kw = {p.split(".")[1]: v for p, v in values.items() if p.startswith("gland.")}
    ring_kw = {p.split(".")[1]: v for p, v in values.items() if p.startswith("oring.")}
    return replace(design, gland=replace(design.gland, **gland_kw),
                   oring=replace(design.oring, **ring_kw))


def _validate(design: Design, tols: Tolerances) -> None:
    allowed = set(toleranceable_fields(design))
    unknown = set(tols) - allowed
    if unknown:
        raise ValueError(f"unknown toleranced fields: {sorted(unknown)}")


def _outputs(design: Design, ds: Dataset, state: ThermalState) -> tuple[dict[str, float], list[CheckResult]]:
    gs, results = run_checks(design, ds, state)
    out = {k: getattr(gs, k) for k in OUTPUTS}
    out = {k: (math.nan if v is None else float(v)) for k, v in out.items()}
    return out, results


def _family_status(results: list[CheckResult]) -> dict[str, Status]:
    fam: dict[str, Status] = {}
    for r in results:
        f = check_family(r)
        if f not in fam or _RANK[r.status] > _RANK[fam[f]]:
            fam[f] = r.status
    return fam


# --------------------------------------------------------------------------- worst case


@dataclass(frozen=True)
class WorstCaseResult:
    table: pd.DataFrame  # one row per evaluated corner (and state)
    output_min: dict[str, float]
    output_max: dict[str, float]
    family_status: dict[str, Status]
    worst_results: dict[str, tuple[CheckResult, dict[str, float]]]  # family -> (result, corner)


def worst_case(design: Design, tols: Tolerances, ds: Dataset,
               states: list[ThermalState] | ThermalState = ThermalState()) -> WorstCaseResult:
    _validate(design, tols)
    if len(tols) > MAX_WORST_CASE_PARAMS:
        raise ValueError(f"worst-case limited to {MAX_WORST_CASE_PARAMS} toleranced parameters")
    states = [states] if isinstance(states, ThermalState) else list(states)
    names = list(tols)
    corners = [dict(zip(names, c)) for c in itertools.product(*[(0, 1)] * len(names))]
    rows, fam_status, worst_res = [], {}, {}
    for state in states:
        for corner in [None, *corners]:
            if corner is None:
                values = {n: nominal_value(design, n) for n in names}
                label = "nominal"
            else:
                values = {n: nominal_value(design, n) + (tols[n].upper_m if corner[n] else tols[n].lower_m)
                          for n in names}
                label = "".join("+" if corner[n] else "-" for n in names)
            out, results = _outputs(with_values(design, values), ds, state)
            row = {"corner": label, "T_seal_K": state.T_seal_K, "T_housing_K": state.T_housing_K,
                   **{f"x:{n}": v for n, v in values.items()}, **out}
            for r in results:
                f = check_family(r)
                if f not in worst_res or severity_key(r) > severity_key(worst_res[f][0]):
                    fam_status[f] = r.status
                    worst_res[f] = (r, values)
            rows.append(row)
    df = pd.DataFrame(rows)
    return WorstCaseResult(
        table=df,
        output_min={k: float(df[k].min()) for k in OUTPUTS},
        output_max={k: float(df[k].max()) for k in OUTPUTS},
        family_status=fam_status,
        worst_results=worst_res,
    )


# --------------------------------------------------------------------------- RSS


@dataclass(frozen=True)
class RssResult:
    mean: dict[str, float]
    sigma: dict[str, float]
    sensitivities: pd.DataFrame  # rows: outputs, columns: parameters (d output / d x)

    def low(self, key: str) -> float:
        return self.mean[key] - 3 * self.sigma[key]

    def high(self, key: str) -> float:
        return self.mean[key] + 3 * self.sigma[key]


def rss(design: Design, tols: Tolerances, ds: Dataset, state: ThermalState = ThermalState(),
        rel_step: float = 1e-6) -> RssResult:
    _validate(design, tols)
    mean_vals = {n: nominal_value(design, n) + t.mid_m for n, t in tols.items()}
    mean_out, _ = _outputs(with_values(design, mean_vals), ds, state)
    sens = {}
    for n in tols:
        h = max(abs(mean_vals[n]) * rel_step, 1e-12)
        up, _ = _outputs(with_values(design, {**mean_vals, n: mean_vals[n] + h}), ds, state)
        dn, _ = _outputs(with_values(design, {**mean_vals, n: mean_vals[n] - h}), ds, state)
        sens[n] = {k: (up[k] - dn[k]) / (2 * h) for k in OUTPUTS}
    sigma = {k: math.sqrt(sum((sens[n][k] * tols[n].sigma_m) ** 2 for n in tols)) for k in OUTPUTS}
    return RssResult(mean_out, sigma, pd.DataFrame(sens))


# --------------------------------------------------------------------------- Monte Carlo


@dataclass(frozen=True)
class MonteCarloResult:
    samples: pd.DataFrame  # inputs (x:<field>) and outputs per sample
    family_rates: pd.DataFrame  # index: family, columns: PASS, WARN, FAIL (fractions)
    overall_rates: dict[str, float]
    n: int
    distribution: str
    seed: int | None


def draw(tols: Tolerances, nominal: dict[str, float], n: int, distribution: Distribution,
         rng: np.random.Generator) -> dict[str, np.ndarray]:
    out = {}
    for name, t in tols.items():
        mu = nominal[name] + t.mid_m
        if distribution == "normal":
            out[name] = rng.normal(mu, t.sigma_m, n) if t.sigma_m > 0 else np.full(n, mu)
        elif distribution == "uniform":
            out[name] = rng.uniform(nominal[name] + t.lower_m, nominal[name] + t.upper_m, n)
        else:
            raise ValueError(f"unknown distribution {distribution}")
    return out


def monte_carlo(design: Design, tols: Tolerances, ds: Dataset,
                state: ThermalState = ThermalState(), n: int = DEFAULT_MC_SAMPLES,
                distribution: Distribution = "normal", seed: int | None = None) -> MonteCarloResult:
    _validate(design, tols)
    rng = np.random.default_rng(seed)
    nominal = {k: nominal_value(design, k) for k in tols}
    x = draw(tols, nominal, n, distribution, rng)
    rows, fam_rows, overall = [], [], []
    for i in range(n):
        values = {k: float(v[i]) for k, v in x.items()}
        out, results = _outputs(with_values(design, values), ds, state)
        rows.append({**{f"x:{k}": v for k, v in values.items()}, **out})
        fams = _family_status(results)
        fam_rows.append({f: s.value for f, s in fams.items()})
        overall.append(max(fams.values(), key=lambda s: _RANK[s]).value if fams else "PASS")
    fam_df = pd.DataFrame(fam_rows).fillna("PASS")  # family not triggered in a sample = PASS
    rates = pd.DataFrame(
        {s: (fam_df == s).sum() / n for s in ("PASS", "WARN", "FAIL")}
    ).fillna(0.0)
    ov = pd.Series(overall)
    return MonteCarloResult(
        samples=pd.DataFrame(rows),
        family_rates=rates,
        overall_rates={s: float((ov == s).mean()) for s in ("PASS", "WARN", "FAIL")},
        n=n,
        distribution=distribution,
        seed=seed,
    )
