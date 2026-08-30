"""Manifest parsing -- the authoritative inventory of what is in an image.

Format (tab separated), as emitted by livecd-rootfs
``live-build/snap-seed-parse.py`` and the dpkg query that precedes it::

    bash                5.2.37-2ubuntu5
    libsnappy1v5:amd64  1.2.2-1
    snap:core24         stable                  1196
    snap:firefox        stable/ubuntu-25.10     6966

Packages are ``<name>\\t<version>``; names may carry an ``:arch`` qualifier.
Snaps are ``snap:<name>\\t<channel>\\t<revision>``.

Note what a manifest does *not* contain: byte sizes and dependencies. Those are
joined in from the archive Packages index (see ``archive.py``); this module only
establishes inventory.
"""

from __future__ import annotations

from .model import PkgRef, SnapRef

SNAP_PREFIX = "snap:"


def parse_manifest(text: str) -> tuple[list[PkgRef], list[SnapRef]]:
    packages: list[PkgRef] = []
    snaps: list[SnapRef] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        fields = line.split("\t")
        # Tolerate whitespace-separated variants seen in older manifests.
        if len(fields) < 2:
            fields = line.split()
        if len(fields) < 2:
            continue

        head = fields[0].strip()
        if head.startswith(SNAP_PREFIX):
            name = head[len(SNAP_PREFIX) :].strip()
            channel = fields[1].strip()
            revision = _parse_revision(fields[2] if len(fields) > 2 else "")
            if name and revision is not None:
                snaps.append(SnapRef(name=name, channel=channel, revision=revision))
            continue

        version = fields[1].strip()
        if not head or not version:
            continue
        name, qualified = _strip_arch_qualifier(head)
        packages.append(PkgRef(name=name, version=version, qualified=qualified))

    packages.sort(key=lambda p: (p.name, p.version))
    snaps.sort(key=lambda s: s.name)
    return packages, snaps


def _strip_arch_qualifier(raw: str) -> tuple[str, str | None]:
    """``libsnappy1v5:amd64`` -> ``("libsnappy1v5", "libsnappy1v5:amd64")``.

    The raw form is retained so no information is lost; the stripped name is
    what joins against the archive index and against the other image's manifest.
    """
    if ":" in raw:
        name, _, arch = raw.partition(":")
        if name and arch:
            return name, raw
    return raw, None


def _parse_revision(raw: str) -> int | None:
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) if digits else None


def manifest_url_for(image_url: str) -> str:
    """Published manifests sit beside the artifact with the extension replaced.

    Verified for .iso, .wsl and .img.xz in 26.10 snapshot-4.
    """
    for ext in (".img.xz", ".tar.gz", ".iso", ".wsl", ".squashfs"):
        if image_url.endswith(ext):
            return image_url[: -len(ext)] + ".manifest"
    return image_url + ".manifest"
