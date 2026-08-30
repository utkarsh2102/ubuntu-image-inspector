"""Core entities.

Identity rules (these determine every file path and every chart key):

* Series   -- codename is the key; version is display only.
* Milestone-- ``<codename>:<slug>`` e.g. ``questing:snapshot-3``, ``questing:ga``.
* Image    -- ``<publish_type>/<arch>`` e.g. ``live-server/arm64+largemem``.
* Package  -- ``(name, version)``, arch qualifier stripped, raw form retained.
* Snap     -- ``(name, revision)``; revision is the immutable identity, channel is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import PHASE_RANK


@dataclass(frozen=True)
class Series:
    codename: str
    version: str
    lts: bool
    status: str  # "dev" | "supported" | "eol"
    created: str | None = None
    released: str | None = None
    eol: str | None = None


@dataclass(frozen=True)
class Milestone:
    """A published directory of images for one series."""

    codename: str
    kind: str  # snapshot | alpha | beta | rc | ga | point
    n: int | None  # snapshot/alpha/beta/rc number
    point: int  # LTS point release number; 0 for the initial GA
    base_url: str
    host: str  # cdimage | old-releases | releases

    @property
    def slug(self) -> str:
        if self.kind == "ga":
            return "ga" if self.point == 0 else f"ga.{self.point}"
        return f"{self.kind}-{self.n}" if self.n is not None else self.kind

    @property
    def id(self) -> str:
        return f"{self.codename}:{self.slug}"

    @property
    def label(self) -> str:
        if self.kind == "ga":
            return "GA" if self.point == 0 else f"GA point {self.point}"
        if self.n is None:
            return self.kind.upper() if self.kind == "rc" else self.kind.capitalize()
        return f"{self.kind.capitalize()} {self.n}"

    @property
    def sort_key(self) -> tuple[int, int, int]:
        return (PHASE_RANK[self.kind], self.n or 0, self.point)


@dataclass(frozen=True)
class ImageId:
    """A published artifact's logical identity, parsed from its filename."""

    publish_type: str
    arch: str
    ext: str

    @property
    def id(self) -> str:
        return f"{self.publish_type}/{self.arch}"

    @property
    def label(self) -> str:
        pretty = {
            "desktop": "Desktop",
            "live-server": "Server",
            "wsl": "WSL",
            "preinstalled-server": "Preinstalled Server",
            "preinstalled-desktop": "Preinstalled Desktop",
            "netboot": "Netboot",
            "base": "Base",
        }.get(self.publish_type, self.publish_type)
        return f"{pretty} ({self.arch})"


@dataclass(frozen=True)
class PkgRef:
    name: str  # arch qualifier stripped
    version: str
    qualified: str | None = None  # original form when it carried ":arch"


@dataclass(frozen=True)
class SnapRef:
    name: str
    channel: str
    revision: int


@dataclass
class Point:
    """One (milestone, image) datum -- a single row on the trend chart."""

    milestone_id: str
    image_id: str
    url: str
    bytes: int | None = None
    built: str | None = None
    sha256: str | None = None
    packages: list[PkgRef] = field(default_factory=list)
    snaps: list[SnapRef] = field(default_factory=list)
    manifest_url: str | None = None
    # (name, revision) -> {bytes, version, type}, resolved from the snap store
    snap_meta: dict = field(default_factory=dict)
    # (name, version) -> archive metadata (installed size, deps, section)
    pkg_meta: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
