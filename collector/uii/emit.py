"""Deterministic JSON emission.

Byte-identical output for unchanged input is a hard requirement, not a nicety:
without it every nightly run rewrites ~1800 files, the repository grows by
~150 MB per run, and "did anything actually change?" stops being answerable from
``git status``. Hence sorted keys, compact separators, and ``generatedAt``
appearing only in ``index.json``.
"""

from __future__ import annotations

import json
from pathlib import Path


def dumps(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def write_json(path: Path, obj: object) -> bool:
    """Write ``obj`` to ``path``. Returns True if the file changed on disk."""
    text = dumps(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return False
        except OSError:
            pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return True
