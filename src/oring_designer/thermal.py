"""Thermal strain lookup and dimension scaling.

Integrated thermal strain eps(T) = dL/L referenced to 293.15 K is interpolated
from tabulated data (PCHIP). No constant CTE is used.
Scaling: L(T) = L_ref * (1 + eps(T)) / (1 + eps(T_ref)).

Status: placeholder, implemented in phase 1.
"""
