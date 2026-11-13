"""Print the "DOĞRULANMALI" (to-verify) list: ``python -m oring_designer.verify [data_dir]``."""

from __future__ import annotations

import sys

from .loader import format_verification_list, load_dataset, verification_list


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    ds = load_dataset(args[0] if args else None)
    print(format_verification_list(verification_list(ds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
