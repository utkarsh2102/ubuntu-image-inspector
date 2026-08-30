"""Series metadata from distro-info-data, not a hardcoded table."""

from __future__ import annotations

import csv
import datetime as dt
import io

from .config import DISTRO_INFO_CSV
from .http import CachedSession
from .model import Series

# Used only if distro-info-data is unreachable. Values are checked against the
# CSV when it is available.
FALLBACK = {
    "questing": ("25.10", False),
    "resolute": ("26.04", True),
    "stonking": ("26.10", False),
}


def _today() -> dt.date:
    return dt.date.today()


def _parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw.strip())
    except ValueError:
        return None


def load_series(session: CachedSession, codenames: tuple[str, ...]) -> dict[str, Series]:
    text = session.get_text(DISTRO_INFO_CSV)
    rows: dict[str, dict[str, str]] = {}
    if text:
        for row in csv.DictReader(io.StringIO(text)):
            series = (row.get("series") or "").strip()
            if series:
                rows[series] = row

    out: dict[str, Series] = {}
    today = _today()
    for codename in codenames:
        row = rows.get(codename)
        if row:
            version = (row.get("version") or "").replace(" LTS", "").strip()
            lts = "LTS" in (row.get("version") or "")
            created = row.get("created") or None
            released = row.get("release") or None
            eol = row.get("eol") or None
        else:
            version, lts = FALLBACK.get(codename, (codename, False))
            created = released = eol = None

        released_d = _parse_date(released)
        eol_d = _parse_date(eol)
        if eol_d and eol_d <= today:
            status = "eol"
        elif released_d and released_d <= today:
            status = "supported"
        else:
            status = "dev"

        out[codename] = Series(
            codename=codename,
            version=version,
            lts=lts,
            status=status,
            created=created,
            released=released,
            eol=eol,
        )
    return out
