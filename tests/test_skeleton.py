"""Phase 0 smoke tests: package imports, i18n lookup, Streamlit page renders."""

import importlib
from pathlib import Path

import pytest

MODULES = [
    "oring_designer",
    "oring_designer.models",
    "oring_designer.loader",
    "oring_designer.units",
    "oring_designer.thermal",
    "oring_designer.geometry",
    "oring_designer.gland_types",
    "oring_designer.checks",
    "oring_designer.sweep",
    "oring_designer.tolerance",
    "oring_designer.selector",
    "oring_designer.viz.section",
    "oring_designer.viz.plots",
]

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(name)


def test_core_has_no_streamlit_dependency():
    """Importing the whole package must not pull in streamlit (run in a fresh process)."""
    import subprocess
    import sys

    code = "import importlib, sys\n"
    code += "".join(f"importlib.import_module({m!r})\n" for m in MODULES)
    code += "assert 'streamlit' not in sys.modules, 'core imports streamlit'\n"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_i18n_lookup_and_formatting():
    from oring_designer.i18n import t

    assert t("app.title")
    assert "1.2.3" in t("app.version", version="1.2.3")
    with pytest.raises(KeyError):
        t("does.not.exist")


def test_streamlit_hello_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP)).run(timeout=30)
    assert not at.exception
    assert "Yuva Hesaplayıcı" in at.title[0].value
