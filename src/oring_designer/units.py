"""Unit conversion at the I/O boundary (pint), decision K10.

The calculation core works with plain floats in SI units (m, K, Pa); names carry the
unit as a suffix (``depth_m``, ``T_seal_K``, ``p_Pa``). pint is used only here, to convert
user input/output: length mm/in, temperature degC/K/degF, pressure bar/MPa/psi.
"""

from __future__ import annotations

from functools import lru_cache

import pint

LENGTH_UNITS = ("mm", "in")
TEMPERATURE_UNITS = ("degC", "K", "degF")
PRESSURE_UNITS = ("bar", "MPa", "psi")


@lru_cache(maxsize=1)
def ureg() -> pint.UnitRegistry:
    return pint.UnitRegistry()


def _convert(value: float, from_unit: str, to_unit: str) -> float:
    reg = ureg()
    return float(reg.Quantity(value, from_unit).to(to_unit).magnitude)


def length_to_m(value: float, unit: str) -> float:
    return _convert(value, unit, "m")


def length_from_m(value_m: float, unit: str) -> float:
    return _convert(value_m, "m", unit)


def temperature_to_K(value: float, unit: str) -> float:
    return _convert(value, unit, "K")


def temperature_from_K(value_K: float, unit: str) -> float:
    return _convert(value_K, "K", unit)


def pressure_to_Pa(value: float, unit: str) -> float:
    return _convert(value, unit, "Pa")


def pressure_from_Pa(value_Pa: float, unit: str) -> float:
    return _convert(value_Pa, "Pa", unit)
