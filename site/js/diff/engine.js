/**
 * Manifest diffing -- the browser half.
 *
 * This mirrors collector/uii/diff.py exactly. The duplication exists because CI
 * precomputes adjacent steps while the browser computes arbitrary pairs on
 * demand; site/tests/diff.parity.test.mjs asserts the two agree over golden
 * fixtures, which is the only thing making the duplication safe.
 *
 * Version comparison is by exact string. Debian version ordering is
 * deliberately not attempted here: getting it subtly wrong in two languages is
 * worse than reporting "changed" and letting measured sizes imply direction.
 */

function pkgMap(detail) {
  const m = new Map();
  for (const [name, version] of detail.packages || []) m.set(name, version);
  return m;
}

function snapMap(detail) {
  const m = new Map();
  for (const s of detail.snaps || []) m.set(s.name, s);
  return m;
}

export function diffManifests(a, b) {
  const A = pkgMap(a);
  const B = pkgMap(b);

  const added = [];
  const removed = [];
  const changed = [];

  for (const [name, version] of B) if (!A.has(name)) added.push({ name, version });
  for (const [name, version] of A) if (!B.has(name)) removed.push({ name, version });
  for (const [name, from] of A) {
    if (!B.has(name)) continue;
    const to = B.get(name);
    if (from !== to) changed.push({ name, from, to });
  }

  const SA = snapMap(a);
  const SB = snapMap(b);
  const snapAdded = [];
  const snapRemoved = [];
  const snapChanged = [];

  for (const [name, s] of SB) {
    if (!SA.has(name)) snapAdded.push({ name, channel: s.channel, rev: s.rev, bytes: s.bytes });
  }
  for (const [name, s] of SA) {
    if (!SB.has(name)) snapRemoved.push({ name, channel: s.channel, rev: s.rev, bytes: s.bytes });
  }
  for (const [name, sa] of SA) {
    if (!SB.has(name)) continue;
    const sb = SB.get(name);
    if (sa.rev !== sb.rev || sa.channel !== sb.channel) {
      snapChanged.push({
        name,
        fromRev: sa.rev,
        toRev: sb.rev,
        fromChannel: sa.channel,
        toChannel: sb.channel,
        fromBytes: sa.bytes ?? null,
        toBytes: sb.bytes ?? null,
        deltaBytes:
          typeof sa.bytes === 'number' && typeof sb.bytes === 'number' ? sb.bytes - sa.bytes : null,
      });
    }
  }

  const byName = (x, y) => (x.name < y.name ? -1 : x.name > y.name ? 1 : 0);
  added.sort(byName);
  removed.sort(byName);
  changed.sort(byName);
  snapAdded.sort(byName);
  snapRemoved.sort(byName);
  snapChanged.sort(byName);

  return {
    added,
    removed,
    changed,
    snapAdded,
    snapRemoved,
    snapChanged,
    counts: {
      added: added.length,
      removed: removed.length,
      changed: changed.length,
      snapAdded: snapAdded.length,
      snapRemoved: snapRemoved.length,
      snapChanged: snapChanged.length,
    },
  };
}

/** Deterministic facts about one image across a comparison. */
export function summarise(a, b) {
  const d = diffManifests(a, b);
  const bytesDelta =
    typeof a.bytes === 'number' && typeof b.bytes === 'number' ? b.bytes - a.bytes : null;
  const snapBytesA = a.totals?.snapBytes ?? null;
  const snapBytesB = b.totals?.snapBytes ?? null;
  return {
    ...d.counts,
    bytesDelta,
    bytesFrom: a.bytes ?? null,
    bytesTo: b.bytes ?? null,
    pkgFrom: a.totals?.pkgCount ?? (a.packages || []).length,
    pkgTo: b.totals?.pkgCount ?? (b.packages || []).length,
    snapFrom: a.totals?.snapCount ?? (a.snaps || []).length,
    snapTo: b.totals?.snapCount ?? (b.snaps || []).length,
    snapBytesDelta:
      typeof snapBytesA === 'number' && typeof snapBytesB === 'number'
        ? snapBytesB - snapBytesA
        : null,
    diff: d,
  };
}
