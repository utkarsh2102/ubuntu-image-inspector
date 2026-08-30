"""Collection orchestration: discovery -> manifests -> emitted JSON."""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

from . import __version__
from .archive import build_pkgmeta
from .config import METRICS, PUBLISH_TYPES_WITH_MANIFEST
from .discovery import DiscoveredMilestone, collect_milestone, discover_milestones
from .emit import write_json
from .http import CachedSession
from .manifest import manifest_url_for, parse_manifest
from .model import Point
from .seriesmap import load_series
from .snapstore import fetch_snap_sizes

log = logging.getLogger(__name__)


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_points(
    session: CachedSession, dm: DiscoveredMilestone
) -> list[Point]:
    """Size, build date, and (where published) manifest contents for a milestone.

    Batched: one curl invocation for every HEAD and one for every manifest in
    the milestone, which is what keeps a full run in minutes rather than hours.
    """
    jobs = sorted(dm.files.items())
    points = [
        Point(
            milestone_id=dm.milestone.id,
            image_id=image_id,
            url=url,
            sha256=dm.checksums.get(image_id),
        )
        for image_id, url in jobs
    ]

    heads = session.head_many([p.url for p in points])
    for p in points:
        info = heads.get(p.url)
        if info:
            p.bytes = info.size
            p.built = info.last_modified
        else:
            p.flags.append("size-unknown")

    # netboot tarballs and ubuntu-base publish no manifest (verified 404). They
    # are tracked for size only and flagged so the UI never offers package views.
    wants: list[Point] = []
    for p in points:
        if p.image_id.split("/", 1)[0] in PUBLISH_TYPES_WITH_MANIFEST:
            wants.append(p)
        else:
            p.flags.append("size-only")

    if wants:
        urls = {p.url: manifest_url_for(p.url) for p in wants}
        texts = session.get_text_many(sorted(set(urls.values())))
        for p in wants:
            murl = urls[p.url]
            text = texts.get(murl)
            if text is None:
                p.flags.append("manifest-missing")
                continue
            p.manifest_url = murl
            p.packages, p.snaps = parse_manifest(text)

    return points


def collect(
    out_dir: Path,
    cache_dir: Path,
    codenames: tuple[str, ...],
    concurrency: int = 8,
    with_snap_sizes: bool = True,
    with_pkg_meta: bool = True,
) -> dict:
    session = CachedSession(cache_dir, concurrency=concurrency)
    series_map = load_series(session, codenames)

    all_series: list[dict] = []
    all_images: dict[str, dict] = {}
    availability: dict[str, dict[str, list[int]]] = {}
    unparsed: list[str] = []
    points_by_series: dict[str, list[Point]] = {}
    pkgmeta_docs: dict[str, dict[str, dict]] = {}
    collected_ledger: dict[str, dict] = {}

    for codename in codenames:
        series = series_map[codename]
        log.info("series %s (%s, %s)", codename, series.version, series.status)

        milestones = discover_milestones(session, series)
        if not milestones:
            log.warning("no milestones discovered for %s", codename)
            continue

        discovered: list[DiscoveredMilestone] = []
        for milestone in milestones:
            dm = collect_milestone(session, series, milestone)
            if dm.files:
                discovered.append(dm)
                unparsed.extend(dm.unparsed)
            else:
                log.info("  %s: no images", milestone.id)

        # Order defines the x axis; emit it so the client never re-derives it.
        order_of = {dm.milestone.id: i for i, dm in enumerate(discovered)}

        series_points: list[Point] = []
        for dm in discovered:
            results = _fetch_points(session, dm)
            series_points.extend(results)
            log.info("  %s: %d images", dm.milestone.id, len(results))
            collected_ledger[dm.milestone.id] = {
                "fileCount": len(dm.files),
                "images": sorted(dm.files.keys()),
            }

        if with_snap_sizes:
            _attach_snap_sizes(session, series_points)

        if with_pkg_meta:
            pkgmeta_docs[codename] = _build_pkgmeta_for_series(
                session, codename, series_points
            )

        points_by_series[codename] = series_points

        avail: dict[str, list[int]] = {}
        for p in series_points:
            avail.setdefault(p.image_id, []).append(order_of[p.milestone_id])
        for k in avail:
            avail[k] = sorted(set(avail[k]))
        availability[codename] = avail

        for p in series_points:
            if p.image_id not in all_images:
                publish_type, arch = p.image_id.split("/", 1)
                all_images[p.image_id] = {
                    "id": p.image_id,
                    "publishType": publish_type,
                    "arch": arch,
                    "label": _image_label(publish_type, arch),
                    "hasManifest": publish_type in PUBLISH_TYPES_WITH_MANIFEST,
                }

        all_series.append(
            {
                "codename": series.codename,
                "version": series.version,
                "lts": series.lts,
                "status": series.status,
                "created": series.created,
                "released": series.released,
                "eol": series.eol,
                "milestones": [
                    {
                        "id": dm.milestone.id,
                        "kind": dm.milestone.kind,
                        "n": dm.milestone.n,
                        "point": dm.milestone.point,
                        "order": order_of[dm.milestone.id],
                        "label": dm.milestone.label,
                        "host": dm.milestone.host,
                        "baseUrl": dm.milestone.base_url,
                        "date": _milestone_date(series_points, dm.milestone.id),
                    }
                    for dm in discovered
                ],
            }
        )

    index = {
        "schemaVersion": 1,
        "generatedAt": _now(),
        "collector": {"version": __version__},
        "metrics": list(METRICS),
        "series": all_series,
        "images": [all_images[k] for k in sorted(all_images)],
        "availability": availability,
    }

    changed = 0
    changed += int(write_json(out_dir / "index.json", index))

    for codename, points in points_by_series.items():
        changed += int(
            write_json(out_dir / "metrics" / f"{codename}.json", _metrics_doc(codename, points))
        )
        for p in points:
            changed += int(write_json(_detail_path(out_dir, p), _detail_doc(p)))

    for codename, by_arch in pkgmeta_docs.items():
        for arch, doc in by_arch.items():
            changed += int(
                write_json(out_dir / "pkgmeta" / f"{codename}-{arch}.json", doc)
            )

    write_json(out_dir / "_state" / "collected.json", collected_ledger)
    write_json(
        out_dir / "_state" / "unparsed.json",
        {"count": len(unparsed), "urls": sorted(unparsed)},
    )
    write_json(
        out_dir / "_state" / "errors.json",
        {"count": len(session.errors), "errors": session.errors[:200]},
    )

    return {
        "series": len(all_series),
        "images": len(all_images),
        "points": sum(len(v) for v in points_by_series.values()),
        "filesChanged": changed,
        "http": dict(session.stats),
        "unparsed": len(unparsed),
        "errors": len(session.errors),
    }


def _image_label(publish_type: str, arch: str) -> str:
    pretty = {
        "desktop": "Desktop",
        "live-server": "Server",
        "wsl": "WSL",
        "preinstalled-server": "Preinstalled Server",
        "preinstalled-desktop": "Preinstalled Desktop",
        "netboot": "Netboot",
        "base": "Base",
    }.get(publish_type, publish_type)
    return f"{pretty} ({arch})"


def _milestone_date(points: list[Point], milestone_id: str) -> str | None:
    """Milestone date = earliest image build time within it."""
    dates = [p.built for p in points if p.milestone_id == milestone_id and p.built]
    return min(dates) if dates else None


def _attach_snap_sizes(session: CachedSession, points: list[Point]) -> None:
    by_arch: dict[str, set[tuple[str, int]]] = {}
    for p in points:
        if not p.snaps:
            continue
        arch = p.image_id.split("/", 1)[1]
        by_arch.setdefault(arch, set()).update((s.name, s.revision) for s in p.snaps)

    resolved: dict[str, dict[tuple[str, int], dict]] = {}
    for arch, refs in by_arch.items():
        resolved[arch] = fetch_snap_sizes(session, arch, sorted(refs))

    for p in points:
        if not p.snaps:
            continue
        arch = p.image_id.split("/", 1)[1]
        table = resolved.get(arch, {})
        p.snap_meta = {
            (s.name, s.revision): table[(s.name, s.revision)]
            for s in p.snaps
            if (s.name, s.revision) in table
        }
        if any((s.name, s.revision) not in table for s in p.snaps):
            # Old revisions can vanish from the store. Record the gap rather
            # than letting a missing size read as zero.
            p.flags.append("snap-size-incomplete")


def _snap_entries(point: Point) -> list[dict]:
    out = []
    for s in point.snaps:
        meta = point.snap_meta.get((s.name, s.revision), {})
        out.append(
            {
                "name": s.name,
                "channel": s.channel,
                "rev": s.revision,
                "bytes": meta.get("bytes"),
                "version": meta.get("version"),
                "type": meta.get("type"),
            }
        )
    return out


def _installed_kb(point: Point) -> int | None:
    """Total uncompressed on-disk size, in KB, for packages we could resolve.

    None when nothing resolved; a partial total is reported alongside a
    coverage count so the UI can say how complete it is rather than implying
    the number is the whole story.
    """
    vals = [point.pkg_meta[(p.name, p.version)]["i"] for p in point.packages
            if (p.name, p.version) in point.pkg_meta
            and point.pkg_meta[(p.name, p.version)].get("i") is not None]
    return sum(vals) if vals else None


def _pkg_meta_known(point: Point) -> int:
    return sum(1 for p in point.packages if (p.name, p.version) in point.pkg_meta)


def _snap_bytes(point: Point) -> int | None:
    vals = [
        point.snap_meta[(s.name, s.revision)]["bytes"]
        for s in point.snaps
        if (s.name, s.revision) in point.snap_meta
    ]
    return sum(vals) if vals else (0 if not point.snaps else None)


def _detail_path(out_dir: Path, point: Point) -> Path:
    codename, slug = point.milestone_id.split(":", 1)
    publish_type, arch = point.image_id.split("/", 1)
    return out_dir / "detail" / codename / slug / f"{publish_type}-{arch}.json"


def _detail_doc(point: Point) -> dict:
    return {
        "schemaVersion": 1,
        "milestone": point.milestone_id,
        "image": point.image_id,
        "bytes": point.bytes,
        "built": point.built,
        "sha256": point.sha256,
        "url": point.url,
        "manifestUrl": point.manifest_url,
        "packages": [[p.name, p.version] for p in point.packages],
        "snaps": _snap_entries(point),
        "totals": {
            "pkgCount": len(point.packages),
            "snapCount": len(point.snaps),
            "snapBytes": _snap_bytes(point),
            "installedKB": _installed_kb(point),
        },
        "coverage": {
            "pkgMetaKnown": _pkg_meta_known(point),
            "pkgMetaTotal": len(point.packages),
            "snapSizeKnown": len(point.snap_meta),
            "snapTotal": len(point.snaps),
        },
        "flags": sorted(set(point.flags)),
    }


def _metrics_doc(codename: str, points: list[Point]) -> dict:
    """Row-as-array encoding; this single file powers the whole trend chart."""
    fields = ["m", "i", "bytes", "built", "pkgs", "snaps", "snapBytes", "installedKB", "flags"]
    rows = [
        [
            p.milestone_id,
            p.image_id,
            p.bytes,
            p.built,
            len(p.packages),
            len(p.snaps),
            _snap_bytes(p),
            _installed_kb(p),
            sorted(set(p.flags)),
        ]
        for p in sorted(points, key=lambda x: (x.milestone_id, x.image_id))
    ]
    return {"schemaVersion": 1, "series": codename, "fields": fields, "points": rows}


def _build_pkgmeta_for_series(
    session: CachedSession, codename: str, points: list[Point]
) -> dict[str, dict]:
    """Resolve package sizes/deps per architecture and attach them to points."""
    from .archive import _stamp

    by_arch: dict[str, dict] = {}
    arch_points: dict[str, list[Point]] = {}
    for p in points:
        if not p.packages:
            continue
        arch_points.setdefault(p.image_id.split("/", 1)[1], []).append(p)

    for arch, group in sorted(arch_points.items()):
        needed = {pkg.name for p in group for pkg in p.packages}
        # One archive timestamp per milestone: the latest build in it, so the
        # index is guaranteed to be at or after every image it must explain.
        stamps: dict[str, str] = {}
        for p in group:
            if not p.built:
                continue
            prev = stamps.get(p.milestone_id)
            if prev is None or p.built > prev:
                stamps[p.milestone_id] = p.built
        stamps = {k: _stamp(v) for k, v in stamps.items()}
        if not stamps:
            continue

        doc = build_pkgmeta(session, codename, arch, stamps, needed)
        by_arch[arch] = doc

        table = doc["pkgs"]
        for p in group:
            p.pkg_meta = {
                (pkg.name, pkg.version): table[pkg.name][pkg.version]
                for pkg in p.packages
                if pkg.name in table and pkg.version in table[pkg.name]
            }
            if len(p.pkg_meta) < len(p.packages):
                p.flags.append("pkg-meta-incomplete")
        log.info(
            "  pkgmeta %s/%s: %d names resolved", codename, arch, len(table)
        )

    return by_arch
