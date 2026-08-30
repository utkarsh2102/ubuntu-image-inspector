"""uii -- Ubuntu Image Inspector collector CLI."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .collect import collect
from .config import DEFAULT_SERIES

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="uii", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="collect image data into site/data")
    c.add_argument("--out", type=Path, default=REPO_ROOT / "site" / "data")
    c.add_argument("--cache", type=Path, default=REPO_ROOT / ".cache" / "http")
    c.add_argument("--series", default=",".join(DEFAULT_SERIES),
                   help="comma-separated codenames")
    c.add_argument("--concurrency", type=int, default=8)
    c.add_argument("--no-snap-sizes", action="store_true",
                   help="skip snap store lookups (faster, leaves snapBytes null)")
    c.add_argument("--no-pkg-meta", action="store_true",
                   help="skip archive Packages join (faster, leaves installedKB null)")
    c.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
        format="%(message)s",
        stream=sys.stderr,
    )

    if args.cmd == "collect":
        codenames = tuple(s.strip() for s in args.series.split(",") if s.strip())
        summary = collect(
            out_dir=args.out,
            cache_dir=args.cache,
            codenames=codenames,
            concurrency=args.concurrency,
            with_snap_sizes=not args.no_snap_sizes,
            with_pkg_meta=not args.no_pkg_meta,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
