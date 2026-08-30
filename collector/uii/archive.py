"""Package sizes and dependencies from the Ubuntu archive.

Manifests establish *what* is in an image but carry only name and version. The
byte magnitudes behind "why did this image grow" come from the archive Packages
index, joined on the exact (name, version) each manifest records.

Point-in-time accuracy matters: a manifest pins the version that existed when
the image was built, and the current archive has long since moved on. So the
index is fetched from snapshot.ubuntu.com at each milestone's own build
timestamp. Measured against questing snapshot-3 live-server/amd64 this resolves
695 of 696 packages; the single miss lives outside main.

Units, stated once and carried through the UI: ``Installed-Size`` is
UNCOMPRESSED on-disk kilobytes. It is not an ISO byte count -- images are
squashfs-compressed -- and the two are never added together or presented as the
same quantity.
"""

from __future__ import annotations

import logging
import lzma
from collections import defaultdict

from .config import ARCHIVE_COMPONENTS, CURRENT_ARCHIVE, SNAPSHOT_ARCHIVE
from .http import CachedSession

log = logging.getLogger(__name__)

# Fields worth keeping. Everything else in a stanza is discarded during the
# streaming parse so peak memory stays small even on universe.
_WANTED = {
    "Package",
    "Version",
    "Installed-Size",
    "Size",
    "Source",
    "Section",
    "Priority",
    "Depends",
    "Pre-Depends",
    "Recommends",
    "Task",
    "Essential",
}


def _store_arch(arch: str) -> str:
    """Image architectures carry variant suffixes the archive does not have."""
    base = arch.split("+", 1)[0]
    return {"amd64v3": "amd64"}.get(base, base)


def _stamp(built: str) -> str:
    """'2025-07-28T13:46:38Z' -> '20250728T134638Z' (snapshot.ubuntu.com form)."""
    return built.replace("-", "").replace(":", "")


def parse_packages_index(raw: bytes, needed: set[str]) -> dict[str, dict[str, dict]]:
    """Stream an xz Packages index, keeping only stanzas we asked for."""
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    cur: dict[str, str] = {}

    def flush() -> None:
        name = cur.get("Package")
        version = cur.get("Version")
        if not name or not version or name not in needed:
            return
        installed = cur.get("Installed-Size", "")
        deb = cur.get("Size", "")
        entry = {
            "i": int(installed) if installed.isdigit() else None,
            "d": int(deb) if deb.isdigit() else None,
            "src": (cur.get("Source") or name).split(" ", 1)[0],
            "sec": cur.get("Section"),
            "pri": cur.get("Priority"),
        }
        deps = []
        for key in ("Pre-Depends", "Depends"):
            if cur.get(key):
                deps.extend(_dep_names(cur[key]))
        if deps:
            entry["dep"] = sorted(set(deps))
        if cur.get("Recommends"):
            entry["rec"] = sorted(set(_dep_names(cur["Recommends"])))
        if cur.get("Task"):
            entry["task"] = [t.strip() for t in cur["Task"].split(",") if t.strip()]
        if cur.get("Essential") == "yes":
            entry["ess"] = True
        out[name][version] = entry

    try:
        with lzma.open(raw, "rt", encoding="utf-8", errors="replace") as fh:  # type: ignore[arg-type]
            for line in fh:
                line = line.rstrip("\n")
                if not line:
                    flush()
                    cur = {}
                    continue
                if line[0] in " \t":
                    continue
                key, sep, value = line.partition(": ")
                if sep and key in _WANTED:
                    cur[key] = value
            flush()
    except lzma.LZMAError as exc:
        log.warning("bad Packages index: %s", exc)
    return dict(out)


def _dep_names(field: str) -> list[str]:
    """"libc6 (>= 2.38), foo | bar" -> ["libc6", "foo", "bar"]."""
    names = []
    for clause in field.split(","):
        for alt in clause.split("|"):
            token = alt.strip().split(" ", 1)[0].split(":", 1)[0]
            if token:
                names.append(token)
    return names


def build_pkgmeta(
    session: CachedSession,
    codename: str,
    arch: str,
    milestone_stamps: dict[str, str],
    needed: set[str],
) -> dict:
    """Resolve sizes/deps for every (name, version) an image of this arch uses.

    ``milestone_stamps`` maps milestone id -> the build timestamp to query the
    archive at. One index is fetched per (milestone, component); results merge
    into a single table because a given (name, version) has the same size
    whichever milestone referenced it.
    """
    store_arch = _store_arch(arch)
    merged: dict[str, dict[str, dict]] = defaultdict(dict)
    sources: dict[str, str] = {}

    for milestone_id, stamp in sorted(milestone_stamps.items()):
        # main and restricted cover almost everything on a Canonical image;
        # universe is only pulled in when names are still unresolved, which
        # keeps a full run from downloading tens of megabytes it never reads.
        for tier in (("main", "restricted"), ("universe", "multiverse")):
            urls = {}
            for component in tier:
                if component not in ARCHIVE_COMPONENTS:
                    continue
                urls[component] = SNAPSHOT_ARCHIVE.format(
                    stamp=stamp, codename=codename, component=component, arch=store_arch
                )

            bodies = session.get_many(list(urls.values()), optional=True)
            for component, url in urls.items():
                raw = bodies.get(url)
                if raw is None:
                    # Fall back to the live archive; only valid for a series
                    # that is still published there.
                    fallback = CURRENT_ARCHIVE.format(
                        codename=codename, component=component, arch=store_arch
                    )
                    raw = session.get(fallback, optional=True)
                    if raw is None:
                        continue
                    sources[f"{milestone_id}:{component}"] = "current"
                else:
                    sources[f"{milestone_id}:{component}"] = stamp

                import io

                parsed = parse_packages_index(io.BytesIO(raw), needed)
                for name, versions in parsed.items():
                    merged[name].update(versions)

            if tier == ("main", "restricted"):
                # Stop before universe if everything already resolved.
                if all(name in merged for name in needed):
                    break

    return {
        "schemaVersion": 1,
        "series": codename,
        "arch": arch,
        "pkgs": {k: merged[k] for k in sorted(merged)},
        "sources": sources,
    }
