"""Derivation of thermal-strain points added on 2026-11-13 (traceability).

Prints the YAML segments inserted into data/housing_materials.yaml and
data/seal_materials.yaml. All inputs are quoted from the sources; the arithmetic is here.

Sources
-------
* Bal Seal TR-18 (Rev. 01, 2021): mean CTE from room temperature (RT) to T. Verified:
  304 SS at -73 C: 14.8e-6 * (-73 - 21.1) = -1.393e-3, NIST TRC fit -1.392e-3.
* Sandia SAND80-2302 (Rack, 1981), Table 2: measured dL/L of cast 17-4 PH relative to
  298 K (agrees with wrought data per the report).
* NIST TRC 9 % Ni steel (Fe-9.0Ni) linear expansion fit, 4-300 K (equation range 4-265 K):
  martensitic/ferritic reference shape for the PH steels below 200 K.
* Clark, A.F., NBS (AEC-NASA Tech Brief B69-10707, Cryogenics 8 (1968) 282): RT expansion
  coefficient is a good indicator of total contraction to low temperature; heat treatment
  has little effect unless the structure changes -> scale a reference curve of similar
  structure (used for PH steels below 200 K and 7075 below 116 K; marked extrapolated).
* Parker ORD 5700 Table 2-5: contraction 24 -> -54 C and expansion 24 -> 191 C (in./ft.).
* NBS Monograph 29 (7075-T6 at 116 K) + NIST TRC Al 6061 fit: 7075 below 116 K.

Bal Seal Table 4.1 has merged cells (checked on the rendered page): 304 SS 16.9 spans
205-316 C; 17-7 PH H900 11.0 is the 0 C value and 11.5 spans 93-316 C; 15-5 / 17-4 H900
10.8 is the 0 C and 93 C value. Table 4.2 (aluminium) cells are offset half a column; only
the 20 -> 100 C value (23.6) is used.
"""

from __future__ import annotations

F_TO_K = 1.8  # 1 /F = 1.8 /K

# NIST Fe-9Ni fit (1e-5 units, relative to 293 K)
NI9 = [-2.104e2, -5.699e-2, 5.072e-3, -1.381e-5, 1.897e-8]


def ni9(T: float) -> float:
    return sum(c * T**i for i, c in enumerate(NI9)) * 1e-5


def ni9_rel_29315(T: float) -> float:
    return (1 + ni9(T)) / (1 + ni9(293.15)) - 1


def balseal_point(alpha_um_per_m_C: float, T_C: float, T_rt_C: float = 21.1) -> tuple[float, float]:
    """(T_K, dL/L relative to RT) from a Bal Seal mean coefficient (um/m/C)."""
    return T_C + 273.15, alpha_um_per_m_C * 1e-6 * (T_C - T_rt_C)


def ph_steel(name: str, anchor: tuple[float, float] | None, scale_override: float | None,
             above: list[tuple[float, float]]) -> None:
    """Proxy segment (9Ni shape scaled) 20..190 K + sourced points."""
    if anchor is not None:
        s = anchor[1] / ni9_rel_29315(anchor[0])
    else:
        s = scale_override
    print(f"# {name}: scale on 9Ni = {s:.4f}")
    pts = [(T, round(s * ni9_rel_29315(T), 7)) for T in range(20, 200, 10)]
    print("proxy", pts)
    print("sourced", ([anchor] if anchor else []) + [(293.15, 0.0)] + above)
    return s


if __name__ == "__main__":
    # 17-4 PH (H900 row; Condition A identical at 0-93 C): -73 C 10.4, 93 C 10.8
    a = balseal_point(10.4, -73.0)
    b = balseal_point(10.8, 93.0)
    s174 = ph_steel("17-4 PH", (a[0], a[1]), None, [b])
    # Sandia cast 17-4: 474 K 0.194 %, 568 K 0.313 % relative to 298 K -> relative to 293.15 K
    e298 = 10.8e-6 * (298.0 - 293.15)
    print("sandia", [(474.0, round((1 + 0.00194) * (1 + e298) - 1, 6)),
                     (568.0, round((1 + 0.00313) * (1 + e298) - 1, 6))])
    # 15-5 PH: -73 C 10.4, 0 C 10.8, 93 C 10.8
    ph_steel("15-5 PH", balseal_point(10.4, -73.0), None, [balseal_point(10.8, 93.0)])
    # 17-7 PH hardened (Bal Seal "17-7 PH Condition H900"): 11.0 near RT; no -73 C value:
    # scale = 17-4 scale * 11.0 / 10.8 (Clark: proportional to RT coefficient)
    ph_steel("17-7 PH", None, s174 * 11.0 / 10.8,
             [balseal_point(11.0, 0.0), balseal_point(11.5, 93.0), balseal_point(11.5, 205.0),
              balseal_point(11.5, 316.0)])
    print("17-4/15-5 0 C", balseal_point(10.8, 0.0))
    # Aluminium (Bal Seal table 4.2, RT = 20 C): 6061 and 7075 at 100 C: 23.6
    print("Al 100 C", balseal_point(23.6, 100.0, 20.0))
    # 304 SS at 93 C: 16.6
    print("304", [balseal_point(16.6, 93.0), balseal_point(16.9, 205.0), balseal_point(16.9, 316.0)])
    # 7075 below 116 K: NIST 6061 shape (relative to 293 K) scaled to Monograph 29 -314e-5 at 116 K
    al = [-4.1277e2, -3.0389e-1, 8.7696e-3, -9.9821e-6, 0.0]

    def al6061(T: float) -> float:
        T = max(T, 18.0)
        return sum(c * T**i for i, c in enumerate(al)) * 1e-5

    k = -314e-5 / al6061(116.0)
    print(f"7075 scale {k:.4f}", [(T, round(k * al6061(T), 7)) for T in range(20, 120, 10)])
    # VMQ: Parker silicone 24 -> 191 C 0.360 in./ft., re-referenced with Monograph eps(297.15)
    e297 = 119e-5 * (297.15 - 293.0) / 7.0
    print("VMQ 464.15", round((1 + 0.360 / 12) * (1 + e297) - 1, 6))
    # Parker Table 2-5 (in./ft. -> /12); reference 24 C = 297.15 K
    for name, c, e in [("NBR", .108, .224), ("FKM", .156, .324), ("EPDM", .155, .320),
                       ("Silicone", .174, .360), ("Low-temperature silicone", .193, .396)]:
        print(name, [(219.15, round(-c / 12, 6)), (297.15, 0.0), (464.15, round(e / 12, 6))])
    # Parofluor (FFKM): coefficient only, 1.8e-4 /F
    a_ffkm = 1.8e-4 * F_TO_K
    print("FFKM", [(255.15, round(a_ffkm * (255.15 - 297.15), 6)), (297.15, 0.0),
                   (593.15, round(a_ffkm * (593.15 - 297.15), 6))])
