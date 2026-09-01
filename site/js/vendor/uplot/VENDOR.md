# Vendored: uPlot

- **Version:** 1.6.32
- **Source:** https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/
- **License:** MIT (Leon Sorokin) — https://github.com/leeoniya/uPlot/blob/master/LICENSE
- **Why vendored:** the site has no build step and no local npm. Vendoring keeps
  the deployed page same-origin, which also lets the CSP stay tight (no
  third-party `script-src`).

## SHA-256 (verified in CI)

```
19c8d4c6ad88929a79f4ae49d6f7161566dfd0ba3d15cc495e974f787eb78f1f  uPlot.iife.min.js
df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04  uPlot.min.css
```

`.github/workflows/ci.yml` re-downloads the upstream files and asserts these
digests, so the vendored copies cannot silently drift.
