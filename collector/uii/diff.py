"""Manifest diffing.

This algorithm is implemented twice -- here and in ``site/js/diff/engine.js`` --
because the browser computes arbitrary milestone pairs on demand while CI
precomputes adjacent steps. The duplication is only tolerable because
``site/tests/diff.parity.test.mjs`` asserts the two produce identical output
over golden fixtures.

Version comparison is by exact string. Debian version ordering is deliberately
not attempted: getting it subtly wrong in two languages is worse than reporting
"changed" and letting measured sizes imply direction.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .model import PkgRef, SnapRef


def _pkg_map(pkgs: Iterable[PkgRef]) -> dict[str, str]:
    return {p.name: p.version for p in pkgs}


def _snap_map(snaps: Iterable[SnapRef]) -> dict[str, SnapRef]:
    return {s.name: s for s in snaps}


def diff_manifests(
    a_pkgs: Iterable[PkgRef],
    a_snaps: Iterable[SnapRef],
    b_pkgs: Iterable[PkgRef],
    b_snaps: Iterable[SnapRef],
) -> dict:
    """Diff image A -> image B. Keys are sorted so output is deterministic."""
    a = _pkg_map(a_pkgs)
    b = _pkg_map(b_pkgs)

    added = [{"name": n, "version": b[n]} for n in sorted(b.keys() - a.keys())]
    removed = [{"name": n, "version": a[n]} for n in sorted(a.keys() - b.keys())]
    changed = [
        {"name": n, "from": a[n], "to": b[n]}
        for n in sorted(a.keys() & b.keys())
        if a[n] != b[n]
    ]

    sa = _snap_map(a_snaps)
    sb = _snap_map(b_snaps)

    snap_added = [
        {"name": n, "channel": sb[n].channel, "rev": sb[n].revision}
        for n in sorted(sb.keys() - sa.keys())
    ]
    snap_removed = [
        {"name": n, "channel": sa[n].channel, "rev": sa[n].revision}
        for n in sorted(sa.keys() - sb.keys())
    ]
    snap_changed = [
        {
            "name": n,
            "fromRev": sa[n].revision,
            "toRev": sb[n].revision,
            "fromChannel": sa[n].channel,
            "toChannel": sb[n].channel,
        }
        for n in sorted(sa.keys() & sb.keys())
        if sa[n].revision != sb[n].revision or sa[n].channel != sb[n].channel
    ]

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "snapAdded": snap_added,
        "snapRemoved": snap_removed,
        "snapChanged": snap_changed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "snapAdded": len(snap_added),
            "snapRemoved": len(snap_removed),
            "snapChanged": len(snap_changed),
        },
    }


def diff_from_detail(a: Mapping, b: Mapping) -> dict:
    """Diff two emitted detail documents (as the browser would)."""
    to_pkgs = lambda d: [PkgRef(name=n, version=v) for n, v in d.get("packages", [])]  # noqa: E731
    to_snaps = lambda d: [  # noqa: E731
        SnapRef(name=s["name"], channel=s.get("channel", ""), revision=s.get("rev", 0))
        for s in d.get("snaps", [])
    ]
    return diff_manifests(to_pkgs(a), to_snaps(a), to_pkgs(b), to_snaps(b))
