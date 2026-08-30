# Ubuntu Image Inspector

A static dashboard for how Ubuntu images change across the monthly snapshot
cadence and the six-month releases. It collects published image manifests and
metadata, computes deterministic diffs and size attribution, and offers an
optional LLM inspector that *interprets* those facts without ever becoming the
source of them.

No backend. The collector runs in GitHub Actions and commits JSON; GitHub Pages
serves it.

## What it answers

- Is this image getting larger, and which images are growing or stable?
- What changed between snapshot 3 and snapshot 4, or between 25.10 GA and
  26.04 LTS GA?
- Which images moved most, ranked by size, packages or snaps?
- For one image: exactly which packages and snaps were added, removed or
  upgraded, and which contributed most to the size change.
- Why is a given package in the image at all?

## Quick start

```bash
# Collect (first run downloads a few hundred MB; afterwards it is cached)
cd collector
python3 -m uii collect --series questing,resolute,stonking --verbose

# Serve
python3 -m http.server -d ../site 8000
```

Then open <http://127.0.0.1:8000/>.

The collector is Python 3.11+ with **no third-party dependencies**; it shells
out to `curl`, which must be on `PATH`. The site has **no build step** — it is
vanilla ES modules plus a vendored copy of uPlot.

## Where the data comes from

Everything is derived from what Canonical already publishes. Nothing is
estimated or invented.

| Fact | Source |
|---|---|
| Which milestones exist | Directory listings on `cdimage.ubuntu.com`, `releases.ubuntu.com`, `old-releases.ubuntu.com` |
| Which images exist | Each milestone's `SHA256SUMS` |
| Image size, build date | HTTP `Content-Length` and `Last-Modified` |
| Packages and versions | The published `<image>.manifest` |
| Snaps, channels, revisions | `snap:` lines in the same manifest |
| Snap download size | `api.snapcraft.io` `/v2/snaps/refresh`, resolved at the exact pinned revision |
| Package installed size, dependencies | Archive `Packages` index via `snapshot.ubuntu.com`, queried at each image's own build timestamp |

Milestones are permanently published directories, so history is real rather
than reconstructed:

```
cdimage.ubuntu.com/ubuntu/releases/26.10/release/snapshot-4/   # in development
old-releases.ubuntu.com/releases/questing/snapshot-3/          # archived
releases.ubuntu.com/questing/                                  # GA (amd64)
cdimage.ubuntu.com/releases/questing/release/                  # GA (other arches)
```

Daily builds are deliberately not used: `daily-live/<YYYYMMDD>/` is pruned after
about five days and cannot support a time series.

### Scope

Canonical-shipped Ubuntu images only — Desktop, Server, WSL and the preinstalled
images, across every published architecture. Community flavours (Kubuntu,
Xubuntu, Lubuntu, …) are excluded; the split follows the ownership mapping in
`ubuntu-cdimage`'s `lib/cdimage/test_observer.py`. Netboot tarballs and
`ubuntu-base` publish no manifest, so they are tracked for size only and
flagged.

## Units, and what is *not* claimed

This is the part worth reading carefully, because it is where a dashboard like
this usually starts lying.

Three measured quantities are reported, and they are **never added together**:

| Quantity | Unit | Source |
|---|---|---|
| Image size change | compressed bytes | `Content-Length` of the published artifact |
| Snap contribution | compressed bytes | snap store download size for that revision |
| Package contribution | **uncompressed** kilobytes | `Installed-Size` from the archive index |

Images are squashfs-compressed, so a package's installed size does not transfer
1:1 to the ISO. **This project does not measure the compression ratio and
therefore does not claim one.** You get the observed image delta, the installed
size delta, and the snap delta, each labelled — not a fabricated attribution
that adds to a tidy total.

Likewise, where a package version cannot be resolved in the archive index, its
size is reported as *unknown*, never as zero.

## Layout

```
collector/            Python collector (stdlib only; curl for transport)
  uii/
    discovery.py      Finds milestones and parses published filenames
    manifest.py       Parses <image>.manifest (packages + snap: lines)
    archive.py        Joins the archive Packages index for sizes and deps
    snapstore.py      Resolves historical snap revisions to sizes
    diff.py           Manifest diffing (mirrored in JS)
    emit.py           Deterministic JSON writer
  validate_data.py    Invariant + regression checks over an emitted tree
site/                 The entire GitHub Pages artifact
  js/data/repo.js     The only module that knows the data layout
  js/diff/            Diff engine and size attribution
  js/views/           Trend chart, top movers, what-changed
  js/llm/             Provider-agnostic LLM layer (lazily imported)
  data/               Generated, committed
docs/SCHEMA.md        The JSON contract
```

## The LLM inspector

Optional, provider-agnostic, and structurally separated from the facts.

Supported out of the box: **Claude** (Anthropic API, default
`claude-opus-5`), **OpenRouter**, **DeepSeek**, and any OpenAI-compatible
endpoint. Adding another is one entry in `site/js/llm/provider.js`.

Two ways to use it, because a static site has no backend to hold a key:

1. **Bring your own key.** Entered in the panel, kept in `sessionStorage`
   unless you opt into `localStorage`, and sent directly from your browser to
   the provider. The page has no server that could receive it.
2. **Copy the evidence pack.** One button puts the structured facts on your
   clipboard to paste into Claude Code or any chat. No key, no network call
   from the page.

The model receives only values the deterministic layer already computed, plus
explicit caveats naming what the data cannot establish. Three guards keep
interpretation tethered to evidence:

- every claim carries evidence refs that scroll to the measured row it came
  from;
- any number in the generated prose that does not appear in the evidence pack
  is underlined as unverified;
- generated text lives in its own visually distinct container, collapsed by
  default, and the dashboard is fully usable without ever opening it.

The whole `js/llm/` tree is dynamically imported, so the deterministic analysis
has no code path into it.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install pytest ruff

.venv/bin/python -m pytest collector/tests -q   # collector tests
.venv/bin/ruff check collector/                 # lint
python3 collector/validate_data.py site/data    # data invariants + regressions
node --test site/tests/                         # JS/Python diff parity
```

No Node available? Serve the repository root and open
`/site/tests/parity.browser.html` — it runs the same parity assertions in a
browser.

### Adding a metric

Add it to `METRICS` in `collector/uii/config.py`, emit the field in
`_metrics_doc`, and it appears in the chart's metric selector. Nothing else
needs to change.

## Deployment

`.github/workflows/collect.yml` runs nightly: collect → validate → commit
`site/data` only if it changed → deploy Pages. Published milestones are
immutable and recorded in a ledger, so a steady-state run makes only a few
dozen requests.

Enable Pages for the repository with **Source: GitHub Actions**.
