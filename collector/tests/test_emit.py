"""Deterministic emission.

Without this, every nightly run rewrites every file and `git status` stops
being able to answer "did anything actually change?".
"""

import json

from uii.emit import dumps, write_json


def test_keys_are_sorted_and_output_is_compact():
    text = dumps({"b": 1, "a": {"z": 1, "y": 2}})
    assert text == '{"a":{"y":2,"z":1},"b":1}\n'


def test_write_reports_change_only_when_content_differs(tmp_path):
    p = tmp_path / "x.json"
    assert write_json(p, {"a": 1}) is True
    assert write_json(p, {"a": 1}) is False
    assert write_json(p, {"a": 2}) is True


def test_reordered_input_produces_identical_bytes(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    write_json(a, {"x": 1, "y": 2})
    write_json(b, {"y": 2, "x": 1})
    assert a.read_bytes() == b.read_bytes()


def test_round_trips(tmp_path):
    p = tmp_path / "r.json"
    obj = {"n": [1, 2, 3], "s": "ünïcodé", "nested": {"k": None}}
    write_json(p, obj)
    assert json.loads(p.read_text()) == obj
