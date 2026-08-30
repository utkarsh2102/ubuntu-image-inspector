"""Find published milestones and the images inside them.

Nothing here hardcodes a catalog of releases or images. Milestones are found by
listing the publishing roots; images are found by parsing each milestone's
``SHA256SUMS`` (one request yields the exact published filename set plus a
checksum, which the HTML index cannot).

Filename convention, verified live: the directory ``snapshot-3/`` contains files
tagged ``snapshot3`` -- no dash. GA files carry no tag at all, and an LTS point
release encodes itself in the version token (``26.04.1``).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from .config import (
    CDIMAGE_DEV_MILESTONES,
    CDIMAGE_GA,
    OLD_RELEASES_SERIES,
    PUBLISH_TYPES,
    RELEASES_GA,
)
from .http import CachedSession
from .model import ImageId, Milestone, Series

log = logging.getLogger(__name__)

_HREF = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_MILESTONE_DIR = re.compile(r"^(snapshot)-(\d+)/$|^(beta|rc)(\d*)/$", re.IGNORECASE)

# Publish types are alternated longest-first so "preinstalled-server" wins over
# "server" and "live-server" is never split.
_PUBLISH_ALT = "|".join(sorted((re.escape(p) for p in PUBLISH_TYPES), key=len, reverse=True))

_FILENAME = re.compile(
    r"^(?P<proj>ubuntu(?:-base)?)"
    r"-(?P<ver>\d+\.\d+(?:\.\d+)?)"
    r"(?:-(?P<tag>snapshot\d+|beta\d*|rc\d*|alpha-?\d*))?"
    r"-(?P<publish>" + _PUBLISH_ALT + r")"
    r"-(?P<arch>[a-z0-9]+(?:\+[a-z0-9]+)?)"
    r"\.(?P<ext>iso|img\.xz|tar\.gz|wsl|squashfs)$"
)

_SHA256SUMS_LINE = re.compile(r"^(?P<sha>[0-9a-f]{64})\s+\*?(?P<name>\S.*)$")


@dataclass
class DiscoveredMilestone:
    milestone: Milestone
    # image id -> absolute URL of the artifact
    files: dict[str, str] = field(default_factory=dict)
    # image id -> sha256 of the artifact, where published
    checksums: dict[str, str] = field(default_factory=dict)
    # filenames we could not parse, kept so drift is visible rather than silent
    unparsed: list[str] = field(default_factory=list)


def parse_image_filename(name: str) -> tuple[ImageId, str | None, int] | None:
    """``name`` -> (image, milestone tag, point-release number).

    Returns ``None`` for anything that is not a recognised published artifact
    (checksum files, torrents, zsync metafiles, HTML).
    """
    m = _FILENAME.match(name)
    if not m:
        return None
    ver = m.group("ver")
    point = 0
    parts = ver.split(".")
    if len(parts) == 3 and parts[2].isdigit():
        point = int(parts[2])
    return (
        ImageId(publish_type=m.group("publish"), arch=m.group("arch"), ext=m.group("ext")),
        m.group("tag"),
        point,
    )


def _list_dir(
    session: CachedSession, url: str, no_cache: bool = False, optional: bool = False
) -> list[str]:
    html = session.get_text(url, no_cache=no_cache, optional=optional)
    if not html:
        return []
    return [h for h in _HREF.findall(html)]


def discover_milestones(session: CachedSession, series: Series) -> list[Milestone]:
    """Milestones for one series, ordered along the time axis."""
    found: list[Milestone] = []

    # Snapshot/beta/rc directories. Which root holds them depends on whether the
    # series has been archived yet.
    if series.status == "eol":
        roots = [(OLD_RELEASES_SERIES.format(codename=series.codename), "old-releases")]
    else:
        roots = [(CDIMAGE_DEV_MILESTONES.format(version=series.version), "cdimage")]

    for root, host in roots:
        # The in-development series keeps publishing, so never serve its listing
        # from cache.
        for href in _list_dir(session, root, no_cache=(series.status != "eol")):
            match = _MILESTONE_DIR.match(href)
            if not match:
                continue
            if match.group(1):
                kind, n = "snapshot", int(match.group(2))
            else:
                kind = match.group(3).lower()
                n = int(match.group(4)) if match.group(4) else None
            found.append(
                Milestone(
                    codename=series.codename,
                    kind=kind,
                    n=n,
                    point=0,
                    base_url=urljoin(root, href),
                    host=host,
                )
            )

    found.extend(_discover_ga(session, series))
    found.sort(key=lambda m: m.sort_key)
    return found


def _discover_ga(session: CachedSession, series: Series) -> list[Milestone]:
    """GA and any LTS point releases.

    GA is split across two hosts -- releases.ubuntu.com carries amd64 and cdimage
    carries the other architectures -- so both are probed and merged later by
    ``collect_milestone``. EOL series have everything under old-releases.
    """
    # Verified: old-releases.ubuntu.com/releases/questing/ holds only the
    # snapshot and beta subdirectories -- questing's GA images are still served
    # from releases.ubuntu.com. So GA is probed on all three hosts regardless of
    # series status, and whichever answers first wins per image.
    hosts = [
        (RELEASES_GA.format(codename=series.codename), "releases"),
        (CDIMAGE_GA.format(codename=series.codename), "cdimage"),
        (OLD_RELEASES_SERIES.format(codename=series.codename), "old-releases"),
    ]

    points: set[int] = set()
    for url, _host in hosts:
        for href in _list_dir(
            session, url, no_cache=(series.status == "dev"), optional=True
        ):
            parsed = parse_image_filename(href.rsplit("/", 1)[-1])
            if parsed and parsed[1] is None:
                points.add(parsed[2])

    if not points:
        return []

    primary_url, primary_host = hosts[0]
    return [
        Milestone(
            codename=series.codename,
            kind="ga",
            n=None,
            point=p,
            base_url=primary_url,
            host=primary_host,
        )
        for p in sorted(points)
    ]


def _expected_tag(milestone: Milestone) -> str | None:
    """Directory ``snapshot-3`` -> filename tag ``snapshot3``."""
    if milestone.kind == "ga":
        return None
    if milestone.n is None:
        return milestone.kind
    return f"{milestone.kind}{milestone.n}"


def collect_milestone(
    session: CachedSession, series: Series, milestone: Milestone
) -> DiscoveredMilestone:
    """List one milestone's published artifacts via SHA256SUMS."""
    out = DiscoveredMilestone(milestone=milestone)

    # GA spans several hosts (amd64 on releases.ubuntu.com, other arches on
    # cdimage, archived series on old-releases); snapshots live in one directory.
    if milestone.kind == "ga":
        sources = [
            RELEASES_GA.format(codename=series.codename),
            CDIMAGE_GA.format(codename=series.codename),
            OLD_RELEASES_SERIES.format(codename=series.codename),
        ]
    else:
        sources = [milestone.base_url]

    want_tag = _expected_tag(milestone)

    for source in sources:
        names: dict[str, str] = {}
        sums = session.get_text(
            urljoin(source, "SHA256SUMS"),
            no_cache=(series.status == "dev"),
            optional=True,
        )
        if sums:
            for line in sums.splitlines():
                m = _SHA256SUMS_LINE.match(line.strip())
                if m:
                    names[m.group("name").strip()] = m.group("sha")
        else:
            # Fall back to the HTML index if SHA256SUMS is absent.
            for href in _list_dir(session, source, optional=True):
                leaf = href.rsplit("/", 1)[-1]
                if leaf:
                    names.setdefault(leaf, "")

        for name, sha in sorted(names.items()):
            parsed = parse_image_filename(name)
            if parsed is None:
                if _looks_like_artifact(name):
                    out.unparsed.append(urljoin(source, name))
                continue
            image, tag, point = parsed
            if tag != want_tag:
                continue
            if milestone.kind == "ga" and point != milestone.point:
                continue
            # First host wins; releases.ubuntu.com is probed before cdimage.
            out.files.setdefault(image.id, urljoin(source, name))
            if sha:
                out.checksums.setdefault(image.id, sha)

    return out


def _looks_like_artifact(name: str) -> bool:
    """Only flag things that plausibly should have parsed, to keep noise down."""
    return name.endswith((".iso", ".img.xz", ".wsl", ".tar.gz", ".squashfs"))
