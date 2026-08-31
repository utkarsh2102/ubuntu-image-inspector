#!/usr/bin/env python3
"""Validate an emitted site/data tree.

Checks the invariants the dashboard relies on, plus a regression assertion
against image sizes verified by hand against the live services. If Ubuntu
republishes an artifact at a different size, this is what notices.

Usage: python collector/validate_data.py site/data
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Verified by hand from Content-Length on old-releases/releases.ubuntu.com.
KNOWN_SIZES = {
    ("questing", "live-server/amd64"): {
        "questing:snapshot-1": 2034323456,
        "questing:snapshot-2": 2065596416,
        "questing:snapshot-3": 2134083584,
        "questing:snapshot-4": 2433372160,
        "questing:ga": 2283360256,
    }
}

FLAVORS = {
    "kubuntu", "xubuntu", "lubuntu", "edubuntu", "ubuntu-mate",
    "ubuntu-budgie", "ubuntu-unity", "ubuntucinnamon", "ubuntukylin",
    "ubuntustudio",
}


def fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def main(root: Path) -> int:
    errors: list[str] = []

    index_path = root / "index.json"
    if not index_path.is_file():
        print(f"missing {index_path}", file=sys.stderr)
        return 1
    index = json.loads(index_path.read_text())

    if index.get("schemaVersion") != 1:
        fail(errors, f"unexpected schemaVersion {index.get('schemaVersion')}")

    image_ids = {i["id"] for i in index["images"]}
    if not image_ids:
        fail(errors, "no images in index")

    # No community flavor may have leaked into a Canonical-only dataset.
    for img in index["images"]:
        if img["publishType"] in FLAVORS or img["id"].split("/")[0] in FLAVORS:
            fail(errors, f"flavor image present: {img['id']}")

    for series in index["series"]:
        codename = series["codename"]

        orders = [m["order"] for m in series["milestones"]]
        if orders != sorted(orders):
            fail(errors, f"{codename}: milestone order is not monotonic")
        if len(set(orders)) != len(orders):
            fail(errors, f"{codename}: duplicate milestone order values")

        metrics_path = root / "metrics" / f"{codename}.json"
        if not metrics_path.is_file():
            fail(errors, f"{codename}: metrics file missing")
            continue
        metrics = json.loads(metrics_path.read_text())
        fields = metrics["fields"]
        idx = {k: i for i, k in enumerate(fields)}

        milestone_ids = {m["id"] for m in series["milestones"]}
        seen: set[tuple[str, str]] = set()

        for row in metrics["points"]:
            mid, iid = row[idx["m"]], row[idx["i"]]
            if mid not in milestone_ids:
                fail(errors, f"{codename}: metrics reference unknown milestone {mid}")
            if iid not in image_ids:
                fail(errors, f"{codename}: metrics reference unknown image {iid}")
            key = (mid, iid)
            if key in seen:
                fail(errors, f"{codename}: duplicate point {mid} {iid}")
            seen.add(key)

            size = row[idx["bytes"]]
            if size is not None and size <= 0:
                fail(errors, f"{codename}: non-positive size for {mid} {iid}")

            slug = mid.split(":", 1)[1]
            detail = root / "detail" / codename / slug / f"{iid.replace('/', '-')}.json"
            if not detail.is_file():
                fail(errors, f"missing detail file for {mid} {iid}")

        expected = KNOWN_SIZES.get((codename, "live-server/amd64"))
        if expected:
            actual = {
                row[idx["m"]]: row[idx["bytes"]]
                for row in metrics["points"]
                if row[idx["i"]] == "live-server/amd64"
            }
            for mid, want in expected.items():
                got = actual.get(mid)
                if got != want:
                    fail(errors, f"regression: {mid} live-server/amd64 is {got}, expected {want}")

    state = root / "_state" / "unparsed.json"
    if state.is_file():
        unparsed = json.loads(state.read_text())
        if unparsed.get("count"):
            fail(errors, f"{unparsed['count']} unparsed artifacts; review _state/unparsed.json")

    if errors:
        print(f"FAILED ({len(errors)} problems):", file=sys.stderr)
        for e in errors[:40]:
            print(f"  - {e}", file=sys.stderr)
        return 1

    n_points = sum(
        len(json.loads((root / "metrics" / f"{s['codename']}.json").read_text())["points"])
        for s in index["series"]
    )
    print(
        f"OK: {len(index['series'])} series, {len(image_ids)} images, {n_points} points"
    )
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("site/data")
    raise SystemExit(main(target))
