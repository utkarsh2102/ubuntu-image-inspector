"""Snap sizes, including historical revisions.

The ``channel-map`` from ``/v2/snaps/info`` only describes what is *current* in
each channel, which is useless for a manifest that pins revision 1196 from a
year ago. The refresh endpoint resolves an exact revision instead, and a single
POST can carry many actions.

Verified: core24 revision 1196 on amd64 is 70045696 bytes.
"""

from __future__ import annotations

import logging

from .config import SNAP_REFRESH_URL
from .http import CachedSession

log = logging.getLogger(__name__)

BATCH = 30


def _headers(arch: str) -> dict[str, str]:
    # Both headers are required; omitting the architecture yields
    # "Snap-Device-Architecture header is required".
    return {"Snap-Device-Series": "16", "Snap-Device-Architecture": arch}


def _store_arch(arch: str) -> str:
    """Image architectures carry variant suffixes the store does not know."""
    base = arch.split("+", 1)[0]
    return {"amd64v3": "amd64"}.get(base, base)


def fetch_snap_sizes(
    session: CachedSession, arch: str, refs: list[tuple[str, int]]
) -> dict[tuple[str, int], dict]:
    """Resolve ``(name, revision)`` pairs to size/version/type metadata.

    A revision's size is immutable, so results cache permanently. Unresolvable
    revisions (very old ones can disappear) yield no entry; callers record that
    as ``bytes: null`` rather than zero.
    """
    out: dict[tuple[str, int], dict] = {}
    wanted = sorted(set(refs))
    if not wanted:
        return out

    store_arch = _store_arch(arch)

    for start in range(0, len(wanted), BATCH):
        chunk = wanted[start : start + BATCH]
        actions = [
            {
                "action": "install",
                "instance-key": f"k{i}",
                "name": name,
                "revision": revision,
            }
            for i, (name, revision) in enumerate(chunk)
        ]
        payload = {"context": [], "actions": actions}
        data = session.post_json(SNAP_REFRESH_URL, payload, _headers(store_arch))
        if not data:
            continue

        by_key = {}
        for result in data.get("results", []):
            key = result.get("instance-key")
            if key:
                by_key[key] = result

        for i, (name, revision) in enumerate(chunk):
            result = by_key.get(f"k{i}")
            if not result or result.get("result") not in ("install", "refresh", "download"):
                continue
            snap = result.get("snap") or {}
            download = snap.get("download") or {}
            size = download.get("size")
            if not isinstance(size, int):
                continue
            out[(name, revision)] = {
                "bytes": size,
                "version": snap.get("version"),
                "type": snap.get("type"),
            }

    return out
