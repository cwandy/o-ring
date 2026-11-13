"""Phase 1 tests for data files, models and the DOĞRULANMALI list."""

import shutil

import pytest
import yaml
from pydantic import ValidationError

from oring_designer import verify
from oring_designer.loader import (
    DataError,
    format_verification_list,
    load_dataset,
    resolve_data_dir,
    verification_list,
)
from oring_designer.models import DataQuality, QualifiedValue

DS = load_dataset()


def test_all_spec_materials_present():
    assert set(DS.seal_materials) == {"nbr", "epdm", "fkm", "ffkm", "vmq", "pvmq", "ptfe", "pctfe"}
    assert set(DS.housing_materials) == {
        "al6061", "al7075", "al1100", "al3003", "ss304", "ss316",
        "ph17_4", "ph15_5", "ph17_7", "in718",
    }
    assert {"lox", "ln2", "lh2", "lch4", "ghe"} <= set(DS.fluids)


def test_groups():
    groups = {m.id: m.group for m in DS.seal_materials.values()}
    assert groups["ptfe"] == groups["pctfe"] == "thermoplastic"
    assert groups["nbr"] == "elastomer"


def test_17_7_ph_note():
    assert "17-5 PH" in DS.housing_materials["ph17_7"].notes


def test_tempers_selectable():
    tempers = [t.id for t in DS.housing_materials["ph17_4"].tempers]
    assert "H900" in tempers and "H1150" in tempers


def test_ph_steels_flag_cryo_toughness_without_invented_threshold():
    for mid in ("ph17_4", "ph15_5", "ph17_7"):
        tough = DS.housing_materials[mid].cryo_toughness
        assert tough.warning is True
        assert tough.threshold_K.value is None
        assert tough.threshold_K.data_quality is DataQuality.PLACEHOLDER


def test_fluid_compatibility_defaults_to_unknown():
    lox = DS.fluids["lox"]
    assert lox.compatibility_with("nbr").status == "not_ok"
    assert lox.compatibility_with("ptfe").status == "unknown"


def test_every_thermal_segment_has_source_and_quality():
    for m in [*DS.seal_materials.values(), *DS.housing_materials.values()]:
        for seg in m.thermal_strain.segments:
            assert seg.source in DS.references
            assert seg.data_quality is not None


def test_non_placeholder_requires_value_and_source():
    with pytest.raises(ValidationError):
        QualifiedValue(value=1.0, data_quality="literature")
    with pytest.raises(ValidationError):
        QualifiedValue(source="x", data_quality="literature")
    QualifiedValue(data_quality="placeholder")  # allowed


def test_unknown_source_id_rejected(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(DS.data_dir, data)
    path = data / "fluids.yaml"
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    content["fluids"][0]["boiling_point_K"]["source"] = "no_such_reference"
    path.write_text(yaml.safe_dump(content, allow_unicode=True), encoding="utf-8")
    with pytest.raises(DataError, match="no_such_reference"):
        load_dataset(data)


def test_data_dir_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ORING_DESIGNER_DATA", str(tmp_path))
    assert resolve_data_dir() == tmp_path
    monkeypatch.setenv("ORING_DESIGNER_DATA", str(tmp_path / "missing"))
    with pytest.raises(DataError):
        resolve_data_dir()


# --------------------------------------------------------------------------- DOĞRULANMALI


def test_verification_list_contents():
    items = verification_list(DS)
    explicit = [i for i in items if i.origin == "explicit"]
    auto = [i for i in items if i.origin == "auto"]
    files_with_explicit = {i.file for i in explicit}
    assert {"seal_materials.yaml", "housing_materials.yaml", "fluids.yaml",
            "design_rules.yaml", "extrusion_limits.yaml"} <= files_with_explicit
    locations = {i.location for i in auto}
    assert "materials[ph17_4].cryo_toughness.threshold_K" in locations
    assert "materials[ptfe].thermal_strain.segments[0]" in locations  # extrapolated < 80 K
    assert "materials[nbr].tg_K" in locations


def test_verification_list_output(capsys):
    text = format_verification_list(verification_list(DS))
    assert text.startswith("DOĞRULANMALI")
    assert verify.main([str(DS.data_dir)]) == 0
    out = capsys.readouterr().out
    assert "DOĞRULANMALI" in out and "ph17_4" in out


def test_verification_list_includes_standard_tables():
    items = [i for i in verification_list(DS) if i.file.startswith("standards/")]
    text = " ".join(str(i) for i in items)
    assert "as568.csv" in text and "iso3601_1.csv" in text
    assert "2-201" in text and "2-209" in text
