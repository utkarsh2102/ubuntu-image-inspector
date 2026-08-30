"""HTTP transport, built on curl.

Why curl and not urllib: against old-releases.ubuntu.com a single urllib HEAD
measured 30-60 s while curl consistently returned in under a second, and curl
can batch many transfers into one invocation with connection reuse -- six
parallel HEADs complete in ~1.3 s. Since the collector issues hundreds of HEADs,
that difference decides whether a run takes minutes or hours. curl is present on
the machine and on GitHub Actions runners.

Two rules govern this module:

1. Be a good citizen. Bounded parallelism, retries, an identifying User-Agent,
   and an on-disk cache so a re-run costs almost nothing.
2. Never let one bad URL kill a collection run. Callers get ``None`` and the
   failure is recorded, because a partial dataset that says so beats no dataset.
"""

from __future__ import annotations

import email.utils
import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

from .config import USER_AGENT

log = logging.getLogger(__name__)

# One line per transfer. %{url} is the URL as REQUESTED, not %{url_effective}:
# cdimage 301-redirects EOL GA artifacts to /ubuntu/releases/..., and keying
# results on the post-redirect URL silently orphans every redirected file.
_HEAD_FORMAT = (
    "%{url}\\t%{http_code}\\t%header{content-length}\\t%header{last-modified}\\n"
)


@dataclass
class HeadInfo:
    """What a HEAD tells us about a published artifact.

    Content-Length is the only exact image size available: directory listings
    round to "2.7G" and SHA256SUMS carries no size at all.
    """

    size: int | None
    last_modified: str | None  # ISO 8601 UTC


def _parse_http_date(raw: str | None) -> str | None:
    if not raw or raw == "(nil)":
        return None
    try:
        dt = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class CachedSession:
    def __init__(
        self,
        cache_dir: Path,
        concurrency: int = 8,
        timeout: int = 90,
        retries: int = 3,
    ) -> None:
        if not shutil.which("curl"):
            raise RuntimeError("curl is required but was not found on PATH")
        self.cache_dir = cache_dir
        self.concurrency = max(1, concurrency)
        self.timeout = timeout
        self.retries = retries
        self.stats = {"hit": 0, "miss": 0, "error": 0}
        self.errors: list[dict[str, str]] = []
        cache_dir.mkdir(parents=True, exist_ok=True)

    # -- cache -------------------------------------------------------------
    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / digest[:2] / digest

    def _read_cache(self, key: str) -> bytes | None:
        p = self._path_for(key)
        if p.is_file():
            try:
                return p.read_bytes()
            except OSError:
                return None
        return None

    def _write_cache(self, key: str, body: bytes) -> None:
        p = self._path_for(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        try:
            tmp.write_bytes(body)
            tmp.replace(p)
        except OSError as exc:  # pragma: no cover
            log.warning("cache write failed: %s", exc)

    def _record_error(self, url: str, reason: str) -> None:
        self.stats["error"] += 1
        self.errors.append({"url": url, "error": reason})

    def _base_args(self) -> list[str]:
        return [
            "curl",
            "--silent",
            "--show-error",
            "--location",
            "--fail",
            "--retry",
            str(self.retries),
            "--retry-delay",
            "1",
            "--max-time",
            str(self.timeout),
            "--connect-timeout",
            "20",
            "--user-agent",
            USER_AGENT,
            "--parallel",
            "--parallel-max",
            str(self.concurrency),
        ]

    # -- HEAD --------------------------------------------------------------
    def head_many(self, urls: list[str]) -> dict[str, HeadInfo]:
        """Size and build date for many artifacts, in one curl invocation."""
        out: dict[str, HeadInfo] = {}
        pending: list[str] = []

        for url in urls:
            cached = self._read_cache(f"HEAD {url}")
            if cached is not None:
                self.stats["hit"] += 1
                try:
                    d = json.loads(cached)
                    out[url] = HeadInfo(d.get("size"), d.get("last_modified"))
                    continue
                except ValueError:
                    pass
            pending.append(url)

        if not pending:
            return out

        # --head writes headers to stdout, which would interleave with the -w
        # records; -D /dev/null discards them while -w still resolves %header{}.
        args = self._base_args() + [
            "--head",
            "-D",
            "/dev/null",
            "-o",
            "/dev/null",
            "-w",
            _HEAD_FORMAT,
            "--config",
            "-",
        ]
        config = "\n".join(f"url = {_quote(u)}" for u in pending) + "\n"
        proc = subprocess.run(args, input=config, capture_output=True, text=True)

        seen: set[str] = set()
        for line in proc.stdout.splitlines():
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            url, code, length, modified = parts[0], parts[1], parts[2], parts[3]
            if code != "200":
                continue
            info = HeadInfo(
                size=int(length) if length.isdigit() else None,
                last_modified=_parse_http_date(modified),
            )
            out[url] = info
            seen.add(url)
            self.stats["miss"] += 1
            self._write_cache(
                f"HEAD {url}",
                json.dumps({"size": info.size, "last_modified": info.last_modified}).encode(),
            )

        for url in pending:
            if url not in seen:
                self._record_error(url, (proc.stderr or "HEAD failed").strip()[:200])

        return out

    def head(self, url: str) -> HeadInfo | None:
        return self.head_many([url]).get(url)

    # -- GET ---------------------------------------------------------------
    def get_many(
        self, urls: list[str], no_cache: bool = False, optional: bool = False
    ) -> dict[str, bytes]:
        """Fetch many URLs in one curl invocation."""
        out: dict[str, bytes] = {}
        pending: list[str] = []

        for url in urls:
            if not no_cache:
                cached = self._read_cache(f"GET {url}")
                if cached is not None:
                    self.stats["hit"] += 1
                    out[url] = cached
                    continue
            pending.append(url)

        if not pending:
            return out

        with tempfile.TemporaryDirectory(prefix="uii-get-") as tmpdir:
            tmp = Path(tmpdir)
            lines = []
            targets: dict[str, Path] = {}
            for i, url in enumerate(pending):
                dest = tmp / f"r{i}"
                targets[url] = dest
                lines.append(f"url = {_quote(url)}")
                lines.append(f"output = {_quote(str(dest))}")
            args = self._base_args() + ["--config", "-"]
            proc = subprocess.run(
                args, input="\n".join(lines) + "\n", capture_output=True, text=True
            )

            for url, dest in targets.items():
                if dest.is_file() and dest.stat().st_size >= 0:
                    body = dest.read_bytes()
                    out[url] = body
                    self.stats["miss"] += 1
                    if not no_cache:
                        self._write_cache(f"GET {url}", body)
                elif not optional:
                    # Some probes are expected to miss (a directory with no
                    # SHA256SUMS); those are not collection errors.
                    self._record_error(url, (proc.stderr or "GET failed").strip()[:200])

        return out

    def get(self, url: str, no_cache: bool = False, optional: bool = False) -> bytes | None:
        return self.get_many([url], no_cache=no_cache, optional=optional).get(url)

    def get_text(self, url: str, no_cache: bool = False, optional: bool = False) -> str | None:
        raw = self.get(url, no_cache=no_cache, optional=optional)
        return None if raw is None else raw.decode("utf-8", errors="replace")

    def get_text_many(self, urls: list[str], no_cache: bool = False) -> dict[str, str]:
        return {
            u: b.decode("utf-8", errors="replace")
            for u, b in self.get_many(urls, no_cache=no_cache).items()
        }

    # -- POST --------------------------------------------------------------
    def post_json(self, url: str, payload: dict, headers: dict[str, str]) -> dict | None:
        body = json.dumps(payload)
        key = "POST " + url + " " + hashlib.sha256(body.encode()).hexdigest()
        cached = self._read_cache(key)
        if cached is not None:
            self.stats["hit"] += 1
            try:
                return json.loads(cached)
            except ValueError:
                pass

        # Strip the parallel flags and, crucially, the value that follows
        # --parallel-max; leaving it behind makes curl treat "8" as a URL.
        cleaned: list[str] = []
        skip = False
        for a in self._base_args():
            if skip:
                skip = False
                continue
            if a == "--parallel-max":
                skip = True
                continue
            if a == "--parallel":
                continue
            cleaned.append(a)

        cleaned += [
            "--request",
            "POST",
            "--data-binary",
            "@-",
            "--header",
            "Content-Type: application/json",
        ]
        for k, v in headers.items():
            cleaned += ["--header", f"{k}: {v}"]
        cleaned.append(url)

        proc = subprocess.run(cleaned, input=body, capture_output=True, text=True)
        if proc.returncode != 0 or not proc.stdout:
            self._record_error(url, (proc.stderr or "POST failed").strip()[:200])
            return None
        try:
            data = json.loads(proc.stdout)
        except ValueError as exc:
            self._record_error(url, f"bad JSON: {exc}")
            return None
        self.stats["miss"] += 1
        self._write_cache(key, proc.stdout.encode())
        return data
