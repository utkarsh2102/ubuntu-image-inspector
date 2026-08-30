"""Static configuration: URL templates, known publish types, and filters.

Everything here was verified against the live services. Where a value encodes a
convention (for example the ``snapshot-3`` directory holding ``snapshot3`` files),
the convention is documented next to it.
"""

from __future__ import annotations

USER_AGENT = "ubuntu-image-inspector/0.1 (+https://github.com/ubuntu/ubuntu-image-inspector)"

# --- Publishing roots -------------------------------------------------------
# In-development series publish milestones beneath releases/<version>/release/.
CDIMAGE_DEV_MILESTONES = "https://cdimage.ubuntu.com/ubuntu/releases/{version}/release/"
# EOL series are moved wholesale to old-releases, keyed by codename.
OLD_RELEASES_SERIES = "https://old-releases.ubuntu.com/releases/{codename}/"
# GA for amd64 lives on releases.ubuntu.com ...
RELEASES_GA = "https://releases.ubuntu.com/{codename}/"
# ... and the remaining architectures on cdimage.
CDIMAGE_GA = "https://cdimage.ubuntu.com/releases/{codename}/release/"

DISTRO_INFO_CSV = "https://debian.pages.debian.net/distro-info-data/ubuntu.csv"

SNAP_REFRESH_URL = "https://api.snapcraft.io/v2/snaps/refresh"

# Point-in-time archive; covers any timestamp at or after 2023-03-01.
SNAPSHOT_ARCHIVE = (
    "https://snapshot.ubuntu.com/ubuntu/{stamp}/dists/{codename}/{component}/binary-{arch}/Packages.xz"
)
CURRENT_ARCHIVE = (
    "http://archive.ubuntu.com/ubuntu/dists/{codename}/{component}/binary-{arch}/Packages.xz"
)
GERMINATE_ALL = "https://ubuntu-archive-team.ubuntu.com/germinate-output/platform.{codename}/all"

# --- Image taxonomy ---------------------------------------------------------
# Publish types that Canonical ships and that carry a .manifest. Verified against
# 26.10 snapshot-4: 17 of 21 published artifacts have one.
PUBLISH_TYPES_WITH_MANIFEST = (
    "desktop",
    "live-server",
    "wsl",
    "preinstalled-server",
    "preinstalled-desktop",
)

# Published, Canonical-shipped, but no .manifest exists (verified 404). These are
# tracked for size only and are flagged so the UI never offers package views.
PUBLISH_TYPES_SIZE_ONLY = ("netboot", "base")

PUBLISH_TYPES = PUBLISH_TYPES_WITH_MANIFEST + PUBLISH_TYPES_SIZE_ONLY

# Community flavors. Discovery never walks their trees, but validate.py asserts
# none leaked in. Source: ubuntu-cdimage lib/cdimage/test_observer.py
# OS_OWNER_MAPPING, where these map to their own release teams rather than a
# Canonical team.
EXCLUDED_FLAVORS = frozenset(
    {
        "kubuntu",
        "xubuntu",
        "lubuntu",
        "lubuntu-next",
        "edubuntu",
        "ubuntu-mate",
        "ubuntu-budgie",
        "ubuntu-unity",
        "ubuntucinnamon",
        "ubuntukylin",
        "ubuntustudio",
        "ubuntu-gnome",
    }
)

# Series in scope for the initial collection.
DEFAULT_SERIES = ("questing", "resolute", "stonking")

ARCHIVE_COMPONENTS = ("main", "restricted", "universe", "multiverse")

# Milestone phase ordering. This defines the time axis; see docs/SCHEMA.md.
PHASE_RANK = {"snapshot": 0, "alpha": 1, "beta": 2, "rc": 3, "ga": 4, "point": 5}

# Metric registry. Adding a metric here and in site/js/data/model.js is all that
# is required to expose a new series on the trend chart.
METRICS = (
    {"id": "bytes", "label": "Image size", "unit": "bytes", "field": "bytes"},
    {"id": "pkgs", "label": "Packages", "unit": "count", "field": "pkgs"},
    {"id": "snaps", "label": "Snaps", "unit": "count", "field": "snaps"},
)
