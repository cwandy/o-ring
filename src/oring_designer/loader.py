"""Loading and validation of the YAML data files.

The data directory is resolved from an explicit argument, then the
``ORING_DESIGNER_DATA`` environment variable, then ``<repo>/data`` (K18).

Each YAML file may carry a top-level ``DOGRULANMALI`` list (items to verify, written by
hand). :func:`verification_list` merges these with every entry whose ``data_quality`` is
``placeholder`` or ``extrapolated``, found by scanning the files.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import (
    DataQuality,
    CommonRules,
    ExtrusionLimits,
    Fluid,
    HousingMaterial,
    Reference,
    RuleSet,
    SealMaterial,
)

ENV_VAR = "ORING_DESIGNER_DATA"
VERIFY_KEY = "DOGRULANMALI"

FILES = {
    "references": "references.yaml",
    "seal_materials": "seal_materials.yaml",
    "housing_materials": "housing_materials.yaml",
    "fluids": "fluids.yaml",
    "design_rules": "design_rules.yaml",
    "extrusion_limits": "extrusion_limits.yaml",
}


class DataError(ValueError):
    """Raised when a data file is missing or inconsistent."""


def resolve_data_dir(data_dir: str | os.PathLike | None = None) -> Path:
    if data_dir is not None:
        path = Path(data_dir)
    elif os.environ.get(ENV_VAR):
        path = Path(os.environ[ENV_VAR])
    else:
        path = Path(__file__).resolve().parents[2] / "data"
    if not path.is_dir():
        raise DataError(f"data directory not found: {path}")
    return path


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DataError(f"data file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _by_id(items: list, kind: str) -> dict:
    out: dict = {}
    for item in items:
        if item.id in out:
            raise DataError(f"duplicate {kind} id: {item.id}")
        out[item.id] = item
    return out


@dataclass(frozen=True)
class Dataset:
    data_dir: Path
    references: dict[str, Reference]
    seal_materials: dict[str, SealMaterial]
    housing_materials: dict[str, HousingMaterial]
    fluids: dict[str, Fluid]
    rule_sets: list[RuleSet]
    common_rules: CommonRules
    extrusion_limits: ExtrusionLimits
    raw: dict[str, dict[str, Any]] = field(repr=False)
    _curves: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def curve(self, material_id: str):
        """Thermal strain curve of a seal or housing material (built once, cached)."""
        if material_id not in self._curves:
            from .thermal import build_curve

            m = self.seal_materials.get(material_id) or self.housing_materials[material_id]
            self._curves[material_id] = build_curve(m.thermal_strain, material_id)
        return self._curves[material_id]

    def rule_set(self, material_group: str, gland_type: str) -> RuleSet:
        for rs in self.rule_sets:
            if rs.material_group == material_group and rs.gland_type == gland_type:
                return rs
        raise KeyError(f"no rule set for {material_group}/{gland_type}")


def load_dataset(data_dir: str | os.PathLike | None = None) -> Dataset:
    """Load and validate every data file, including cross-references to ``references.yaml``."""
    root = resolve_data_dir(data_dir)
    raw = {key: _read(root / name) for key, name in FILES.items()}

    references = _by_id(
        [Reference.model_validate(r) for r in raw["references"].get("references", [])], "reference"
    )
    seals = _by_id(
        [SealMaterial.model_validate(m) for m in raw["seal_materials"].get("materials", [])],
        "seal material",
    )
    housings = _by_id(
        [HousingMaterial.model_validate(m) for m in raw["housing_materials"].get("materials", [])],
        "housing material",
    )
    fluids = _by_id([Fluid.model_validate(f) for f in raw["fluids"].get("fluids", [])], "fluid")
    rule_sets = [RuleSet.model_validate(r) for r in raw["design_rules"].get("rule_sets", [])]
    common_rules = CommonRules.model_validate(raw["design_rules"].get("common", {}))
    extrusion = ExtrusionLimits.model_validate(
        {k: v for k, v in raw["extrusion_limits"].items() if k != VERIFY_KEY}
    )

    unknown = sorted(
        {s for key, data in raw.items() if key != "references" for s in _iter_sources(data)}
        - set(references)
    )
    if unknown:
        raise DataError(f"source ids not defined in references.yaml: {unknown}")
    for fluid in fluids.values():
        bad = set(fluid.compatibility) - set(seals)
        if bad:
            raise DataError(f"fluid {fluid.id}: compatibility for unknown seal materials {sorted(bad)}")

    return Dataset(
        root, references, seals, housings, fluids, rule_sets, common_rules, extrusion, raw
    )


def _iter_sources(node: Any):
    if isinstance(node, dict):
        src = node.get("source")
        if isinstance(src, str):
            yield src
        for value in node.values():
            yield from _iter_sources(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_sources(value)


# --------------------------------------------------------------------------- verification list


@dataclass(frozen=True)
class VerificationItem:
    file: str
    location: str
    message: str
    origin: str  # "explicit" (hand-written DOGRULANMALI entry) or "auto" (quality scan)

    def __str__(self) -> str:
        where = f"{self.file}" + (f" :: {self.location}" if self.location else "")
        return f"[{where}] {self.message}"


_FLAGGED = {DataQuality.PLACEHOLDER.value, DataQuality.EXTRAPOLATED.value}


def _scan(node: Any, path: str, out: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        quality = node.get("data_quality")
        if quality in _FLAGGED:
            out.append((path, quality))
        for key, value in node.items():
            if key == VERIFY_KEY:
                continue
            _scan(value, f"{path}.{key}" if path else str(key), out)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            label = value.get("id") if isinstance(value, dict) and "id" in value else i
            _scan(value, f"{path}[{label}]", out)


def verification_list(dataset: Dataset | None = None) -> list[VerificationItem]:
    """All items still to be verified ("DOĞRULANMALI"), explicit entries first."""
    ds = dataset or load_dataset()
    items: list[VerificationItem] = []
    for key, name in FILES.items():
        for text in ds.raw[key].get(VERIFY_KEY, []) or []:
            items.append(VerificationItem(name, "", str(text), "explicit"))
    for csv_name in STANDARD_FILES.values():
        path = ds.data_dir / "standards" / csv_name
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if line.startswith("#") and "DOĞRULANMALI" in line:
                items.append(VerificationItem(f"standards/{csv_name}", "", line.lstrip("# "), "explicit"))
        for row in csv.DictReader(line for line in lines if not line.startswith("#")):
            if row.get("notes"):
                label = row.get("parker_size") or row.get("dash") or ""
                items.append(VerificationItem(f"standards/{csv_name}", label, row["notes"], "explicit"))
    for key, name in FILES.items():
        found: list[tuple[str, str]] = []
        _scan(ds.raw[key], "", found)
        for location, quality in found:
            items.append(VerificationItem(name, location, quality, "auto"))
    return items


def format_verification_list(items: list[VerificationItem]) -> str:
    lines = ["DOĞRULANMALI", "============", ""]
    explicit = [i for i in items if i.origin == "explicit"]
    auto = [i for i in items if i.origin == "auto"]
    lines += [f"- {i}" for i in explicit]
    lines += ["", f"placeholder / extrapolated veri ({len(auto)} kayıt):"]
    lines += [f"- {i}" for i in auto]
    return "\n".join(lines)


# --------------------------------------------------------------------------- standard sizes

STANDARD_FILES = {"AS568": "as568.csv", "ISO3601-1": "iso3601_1.csv"}
INCH = 0.0254


def load_standard_sizes(data_dir: str | os.PathLike | None = None):
    """All standard O-ring sizes as one table (SI units).

    Columns: standard ("AS568", "ISO3601-1 A", "ISO3601-1 G"), size, id_m, id_tol_m, cs_m,
    cs_tol_m, data_quality, notes. AS568 uses the inch columns (primary in the source).
    """
    import pandas as pd

    root = resolve_data_dir(data_dir) / "standards"
    as568 = pd.read_csv(root / STANDARD_FILES["AS568"], comment="#", dtype={"dash": str})
    a = pd.DataFrame({
        "standard": "AS568",
        "size": "AS568-" + as568["dash"],
        "id_m": as568["id_in"] * INCH, "id_tol_m": as568["id_tol_in"] * INCH,
        "cs_m": as568["cs_in"] * INCH, "cs_tol_m": as568["cs_tol_in"] * INCH,
        "data_quality": as568["data_quality"], "notes": as568["notes"].fillna(""),
    })
    iso = pd.read_csv(root / STANDARD_FILES["ISO3601-1"], comment="#")
    b = pd.DataFrame({
        "standard": "ISO3601-1 " + iso["series"],
        "size": iso.apply(lambda r: f"{r.d1_mm:g} x {r.d2_mm:.2f} {r.series}", axis=1),
        "id_m": iso["d1_mm"] * 1e-3, "id_tol_m": iso["d1_tol_mm"] * 1e-3,
        "cs_m": iso["d2_mm"] * 1e-3, "cs_tol_m": iso["d2_tol_mm"] * 1e-3,
        "data_quality": iso["data_quality"], "notes": "",
    })
    return pd.concat([a, b], ignore_index=True)
