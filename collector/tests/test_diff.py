"""Diff semantics, and the golden fixture the JS implementation must match."""

import json
from pathlib import Path

from uii.diff import diff_manifests
from uii.manifest import parse_manifest
from uii.model import PkgRef, SnapRef

FIXTURES = Path(__file__).parent / "fixtures"


def load_pair():
    a = parse_manifest((FIXTURES / "live-server-amd64.snapshot3.manifest").read_text())
    b = parse_manifest((FIXTURES / "live-server-amd64.snapshot4.manifest").read_text())
    return a, b


def test_real_snapshot_diff_detects_snap_revision_changes():
    (a_pkgs, a_snaps), (b_pkgs, b_snaps) = load_pair()
    d = diff_manifests(a_pkgs, a_snaps, b_pkgs, b_snaps)

    changed = {s["name"]: s for s in d["snapChanged"]}
    # Real revisions published in the 25.10 cycle.
    assert changed["snapd"]["fromRev"] == 24792
    assert changed["snapd"]["toRev"] == 25202
    assert changed["subiquity"]["fromRev"] == 6802
    assert changed["subiquity"]["toRev"] == 6830
    # core24 did not move between these two snapshots.
    assert "core24" not in changed


def test_classification_is_exclusive():
    a = [PkgRef("keep", "1"), PkgRef("gone", "1"), PkgRef("bump", "1")]
    b = [PkgRef("keep", "1"), PkgRef("new", "1"), PkgRef("bump", "2")]
    d = diff_manifests(a, [], b, [])
    assert [p["name"] for p in d["added"]] == ["new"]
    assert [p["name"] for p in d["removed"]] == ["gone"]
    assert [p["name"] for p in d["changed"]] == ["bump"]
    assert d["counts"] == {
        "added": 1,
        "removed": 1,
        "changed": 1,
        "snapAdded": 0,
        "snapRemoved": 0,
        "snapChanged": 0,
    }


def test_channel_change_alone_counts_as_a_snap_change():
    # edge -> stable at the same revision is a real, reportable change.
    a = [SnapRef("x", "edge", 5)]
    b = [SnapRef("x", "stable", 5)]
    d = diff_manifests([], a, [], b)
    assert d["counts"]["snapChanged"] == 1
    assert d["snapChanged"][0]["fromChannel"] == "edge"


def test_results_are_sorted_for_determinism():
    a = [PkgRef("b", "1")]
    b = [PkgRef("z", "1"), PkgRef("a", "1")]
    d = diff_manifests(a, [], b, [])
    assert [p["name"] for p in d["added"]] == ["a", "z"]


def test_golden_fixture_matches_committed_json():
    """The contract the JS engine is held to in site/tests/diff.parity.test.mjs.

    If this fails, the two implementations have diverged and the browser is
    showing something the collector would not.
    """
    (a_pkgs, a_snaps), (b_pkgs, b_snaps) = load_pair()
    got = diff_manifests(a_pkgs, a_snaps, b_pkgs, b_snaps)
    golden = json.loads((FIXTURES / "diff.golden.json").read_text())
    assert got == golden
