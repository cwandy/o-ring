"""ISO 286 tolerance classes."""

from __future__ import annotations

import re

import pytest

from oring_designer.fits import FitRangeError, _table, classes, deviation, source
from oring_designer.loader import load_dataset


def test_known_values():
    # spot values well known from ISO 286-2
    assert deviation("H7", 25e-3).upper_m == pytest.approx(21e-6)
    assert deviation("H7", 25e-3).lower_m == 0
    assert deviation("f7", 60e-3).upper_m == pytest.approx(-30e-6)
    assert deviation("f7", 60e-3).lower_m == pytest.approx(-60e-6)
    assert deviation("h9", 40e-3).lower_m == pytest.approx(-62e-6)
    assert deviation("g6", 40e-3).upper_m == pytest.approx(-9e-6)


def test_range_boundaries_are_over_and_up_to_including():
    assert deviation("H7", 30e-3).upper_m == pytest.approx(21e-6)   # 18 < 30 <= 30
    assert deviation("H7", 30.001e-3).upper_m == pytest.approx(25e-6)
    with pytest.raises(FitRangeError):
        deviation("H7", 2e-3)
    with pytest.raises(FitRangeError):
        deviation("H7", 501e-3)
    with pytest.raises(FitRangeError):
        deviation("Q7", 20e-3)


def test_width_equals_IT_of_grade_for_every_class_and_range():
    """upper - lower must be the same IT for all letters of one grade (table consistency)."""
    tab = _table()["classes"]
    for cls, rows in tab.items():
        grade = re.sub(r"\D", "", cls)
        ref = tab.get(f"h{grade}") or tab.get(f"H{grade}")
        for row, r in zip(rows, ref):
            assert row[:2] == r[:2]
            assert row[2] - row[3] == r[2] - r[3], (cls, row)


def test_js_symmetric_and_class_lists():
    d = deviation("js7", 25e-3)
    assert d.upper_m == pytest.approx(10.5e-6) and d.lower_m == pytest.approx(-10.5e-6)
    assert "H7" in classes("hole") and "f7" in classes("shaft") and "JS7" in classes("hole")
    assert not set(classes("hole")) & set(classes("shaft"))


def test_source_is_a_known_reference():
    src, quality = source()
    assert src in load_dataset().references
    assert quality == "literature"
