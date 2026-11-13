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
def _load(lang: str) -> dict[str, str]:
    text = resources.files(__package__).joinpath(f"{lang}.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    return _flatten(data)


def _flatten(tree: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in tree.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, full + "."))
        else:
            flat[full] = str(value)
    return flat


def t(key: str, lang: str = DEFAULT_LANG, **params: Any) -> str:
    """Return the text for ``key`` formatted with ``params``.

    Missing keys raise ``KeyError`` so that untranslated strings are caught by tests.
    """
    return _load(lang)[key].format(**params)
