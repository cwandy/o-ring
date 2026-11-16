"""Parse the ISO 286 / JIS B 0401-2 limit deviation tables (Miki Pulley excerpt) into data/iso286.yaml.

Source page (accessed 2026-11-16):
  https://www.mikipulley.co.jp/en/resources/standards-fitting-tolerances
  "List of Fit Tolerances (Excerpt from JIS B 0401)". JIS B 0401-2 gives the ISO 286-2 values.

Usage: python tools/derive_iso286.py <page-text.txt> [<isofits data.py for cross-check>]
The page text is the HTML with tags replaced by " | " cell separators (see the session notes).

js / JS classes are not parsed: ISO 286-1 defines them as +/- IT/2, derived in fits.py.
Cross-check: the independent transcription in the PyPI package ``isofits`` 1.0 (ISO 286, 3-400 mm)
is compared value by value.
"""

from __future__ import annotations

import ast
import re
import sys

HOLES = ["E7", "E8", "E9", "F6", "F7", "F8", "G6", "G7", "H5", "H6", "H7", "H8", "H9", "H10"]
SHAFTS = ["d8", "d9", "e7", "e8", "e9", "f6", "f7", "f8", "g5", "g6", "h5", "h6", "h7", "h8", "h9"]
BOUNDS = [3, 6, 10, 14, 18, 24, 30, 40, 50, 65, 80, 100, 120, 140, 160, 180, 200, 225, 250, 280, 315,
          355, 400, 450, 500]


def _pair(tok: str, cls: str) -> tuple[int, int]:
    tok = tok.strip().replace("–", "-").replace("−", "-").replace(" ", "")
    if cls.startswith("H"):  # lower deviation 0 printed right after the upper one: "+120" = +12 / 0
        assert tok.startswith("+") and tok.endswith("0"), tok
        return int(tok[1:-1]), 0
    m = re.fullmatch(r"([+-]?\d+)([+-]\d+)", tok)
    assert m, (tok, cls)
    return int(m.group(1)), int(m.group(2))


def parse(text: str, header_cls: list[str], start_marker: str) -> dict[str, list]:
    lines = text[text.index(start_marker):].splitlines()
    out: dict[str, list] = {c: [] for c in header_cls}
    last = None
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.split("|")][1:]
        if len(cells) < 2 or not cells[0].isdigit():
            if out[header_cls[0]] and len(out[header_cls[0]]) == len(BOUNDS) - 1:
                break
            continue
        lo, hi = int(cells[0]), int(cells[1])
        vals = cells[2:2 + len(header_cls)]
        if len(vals) == len(header_cls) and all(vals):
            last = [_pair(v, c) for v, c in zip(vals, header_cls)]
        assert last is not None
        for c, v in zip(header_cls, last):
            out[c].append((lo, hi, *v))
        if hi == 500:
            break
    return out


def main() -> None:
    text = open(sys.argv[1], encoding="utf-8").read()
    holes = parse(text, HOLES, "Hole tolerance classes E7 to H10")
    shafts = parse(text, SHAFTS, "Shaft tolerance classes d8 to h9")
    data = {**holes, **shafts}
    for c, rows in data.items():
        assert [r[0] for r in rows] == BOUNDS[:-1] and [r[1] for r in rows] == BOUNDS[1:], c
    if len(sys.argv) > 2:  # cross-check with isofits (3-400 mm)
        src = open(sys.argv[2], encoding="utf-8").read()
        ns = {}
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign):
                ns[node.targets[0].id] = ast.literal_eval(node.value)
        n = bad = 0
        for table in ("hole_data", "shaft_data"):
            t = ns[table]
            for c, col in t.items():
                if c not in data:
                    continue
                for i, cell in enumerate(col):
                    lo = int(t["over"][i])
                    up, low = (int(x) for x in cell.split("\n"))
                    row = next(r for r in data[c] if r[0] == lo)
                    n += 1
                    if (row[2], row[3]) != (up, low):
                        bad += 1
                        print("MISMATCH", c, lo, row, (up, low))
        print(f"cross-check isofits: {n} values compared, {bad} mismatches")
    print("# data/iso286.yaml classes body")
    for c, rows in data.items():
        print(f"  {c}: [" + ", ".join(f"[{a}, {b}, {u}, {l}]" for a, b, u, l in rows) + "]")


if __name__ == "__main__":
    main()
