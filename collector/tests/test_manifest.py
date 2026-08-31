"""Manifest parsing, against real published manifest content."""

from pathlib import Path

from uii.manifest import manifest_url_for, parse_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parses_packages_and_snaps():
    pkgs, snaps = parse_manifest(load("live-server-amd64.snapshot3.manifest"))
    assert len(pkgs) == 40
    assert {s.name for s in snaps} == {"core24", "snapd", "subiquity"}

    by_name = {s.name: s for s in snaps}
    assert by_name["core24"].channel == "stable"
    assert by_name["core24"].revision == 1055
    assert by_name["subiquity"].channel == "25.10/stable"


def test_strips_arch_qualifier_but_keeps_raw():
    pkgs, _ = parse_manifest("libsnappy1v5:amd64\t1.2.2-1\nbash\t5.2\n")
    by_name = {p.name: p for p in pkgs}
    assert by_name["libsnappy1v5"].qualified == "libsnappy1v5:amd64"
    assert by_name["bash"].qualified is None


def test_ignores_blank_and_malformed_lines():
    pkgs, snaps = parse_manifest("\n\nbash\t5.2\ngarbage-no-version\n\n")
    assert [p.name for p in pkgs] == ["bash"]
    assert snaps == []


def test_snap_without_revision_is_dropped_not_zeroed():
    # A revision we cannot read must not silently become revision 0, which
    # would diff as a real change against a genuine revision.
    _, snaps = parse_manifest("snap:foo\tstable\t\n")
    assert snaps == []


def test_output_is_sorted_for_determinism():
    pkgs, _ = parse_manifest("zlib\t1\nalpha\t2\n")
    assert [p.name for p in pkgs] == ["alpha", "zlib"]


def test_manifest_url_for_each_published_extension():
    cases = {
        "https://x/ubuntu-25.10-live-server-amd64.iso": "https://x/ubuntu-25.10-live-server-amd64.manifest",
        "https://x/ubuntu-25.10-wsl-amd64.wsl": "https://x/ubuntu-25.10-wsl-amd64.manifest",
        "https://x/ubuntu-26.10-preinstalled-server-amd64.img.xz": "https://x/ubuntu-26.10-preinstalled-server-amd64.manifest",
    }
    for src, want in cases.items():
        assert manifest_url_for(src) == want
