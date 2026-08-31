"""Filename and milestone parsing.

These are the rules most likely to drift as Ubuntu publishes new image
variants, so every case here is a filename observed on cdimage or
old-releases.
"""

from pathlib import Path

import pytest

from uii.discovery import parse_image_filename
from uii.model import Milestone

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "name,image_id,tag,point",
    [
        ("ubuntu-25.10-snapshot3-live-server-amd64.iso", "live-server/amd64", "snapshot3", 0),
        ("ubuntu-25.10-live-server-amd64.iso", "live-server/amd64", None, 0),
        ("ubuntu-26.04.1-live-server-arm64.iso", "live-server/arm64", None, 1),
        ("ubuntu-26.10-snapshot4-desktop-amd64v3.iso", "desktop/amd64v3", "snapshot4", 0),
        (
            "ubuntu-26.10-snapshot4-live-server-arm64+largemem.iso",
            "live-server/arm64+largemem",
            "snapshot4",
            0,
        ),
        (
            "ubuntu-25.10-preinstalled-desktop-arm64+raspi.img.xz",
            "preinstalled-desktop/arm64+raspi",
            None,
            0,
        ),
        ("ubuntu-25.10-wsl-amd64.wsl", "wsl/amd64", None, 0),
        ("ubuntu-base-26.04-base-amd64.tar.gz", "base/amd64", None, 0),
    ],
)
def test_parses_published_filenames(name, image_id, tag, point):
    parsed = parse_image_filename(name)
    assert parsed is not None, name
    image, got_tag, got_point = parsed
    assert image.id == image_id
    assert got_tag == tag
    assert got_point == point


@pytest.mark.parametrize(
    "name",
    [
        "SHA256SUMS",
        "ubuntu-25.10-live-server-amd64.iso.torrent",
        "ubuntu-25.10-live-server-amd64.iso.zsync",
        "ubuntu-25.10-snapshot3-desktop-amd64.manifest",
        "HEADER.html",
        "",
    ],
)
def test_rejects_non_artifacts(name):
    assert parse_image_filename(name) is None


def test_milestone_identity_and_ordering():
    def m(kind, n=None, point=0):
        return Milestone(
            codename="questing", kind=kind, n=n, point=point, base_url="", host="x"
        )

    assert m("snapshot", 3).id == "questing:snapshot-3"
    assert m("ga").id == "questing:ga"
    assert m("ga", point=1).id == "questing:ga.1"
    assert m("beta").id == "questing:beta"

    ordered = sorted(
        [m("ga"), m("snapshot", 2), m("beta"), m("snapshot", 10), m("ga", point=1)],
        key=lambda x: x.sort_key,
    )
    assert [x.slug for x in ordered] == [
        "snapshot-2",
        "snapshot-10",
        "beta",
        "ga",
        "ga.1",
    ]
