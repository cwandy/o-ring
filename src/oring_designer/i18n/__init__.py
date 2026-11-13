"""UI text lookup.

All user-facing strings live in one YAML dictionary per language (``tr.yaml``),
keyed by dotted codes. The calculation core never produces display text; it
returns message codes and parameters that are rendered here.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

DEFAULT_LANG = "tr"


@lru_cache(maxsize=None)
def _load(lang: str) -> dict[str, Any]:
    text = resources.files(__package__).joinpath(f"{lang}.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    return _flatten(data)


def _flatten(tree: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in tree.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, full + "."))
        else:
            flat[full] = value
    return flat


def t(key: str, lang: str = DEFAULT_LANG, **params: Any) -> str:
    """Return the text for ``key`` formatted with ``params``.

    Missing keys raise ``KeyError`` so that untranslated strings are caught by tests.
    """
    return str(_load(lang)[key]).format(**params)


def t_list(key: str, lang: str = DEFAULT_LANG) -> list[str]:
    """A list of texts (e.g. report assumptions)."""
    value = _load(lang)[key]
    if not isinstance(value, list):
        raise KeyError(f"{key} is not a list")
    return [str(v) for v in value]


def render_check(result: Any, lang: str = DEFAULT_LANG) -> str:
    """Display text for a ``checks.CheckResult`` (code + params)."""
    return t(f"checks.{result.code}", lang, **result.params)


def family_label(family: str, lang: str = DEFAULT_LANG) -> str:
    """Display name of a check family (falls back to the raw family code)."""
    try:
        return t(f"families.{family}", lang)
    except KeyError:
        return family
