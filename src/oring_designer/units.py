"""Unit conversion at the I/O boundary (pint).

The calculation core works with plain floats in SI units (m, K, Pa); names carry
the unit as a suffix (``depth_m``, ``T_seal_K``, ``p_Pa``). pint is used only
here, to convert user input/output (mm/in, degC/K/degF, bar/MPa/psi).

Status: placeholder, implemented in phase 1.
"""
