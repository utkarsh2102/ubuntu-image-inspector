/**
 * Ranked size contributors.
 *
 * Two measured quantities live here and they are deliberately never added
 * together, because they are not the same unit:
 *
 *   - Snap deltas are COMPRESSED bytes. The snap store reports the exact
 *     download size of the revision the manifest pins, and a seeded snap lands
 *     on the image essentially 1:1.
 *   - Package deltas are UNCOMPRESSED on-disk kilobytes (`Installed-Size` from
 *     the archive Packages index). The image is squashfs-compressed, so a
 *     package's contribution to the ISO is smaller than its installed size --
 *     by a ratio this project does not measure and therefore does not claim.
 *
 * Both are facts. Neither is "the ISO delta". The observed ISO delta is
 * reported separately, from Content-Length, and the gap is shown as a residual
 * rather than papered over with an estimate.
 */

function installedKB(detail, pkgmeta) {
  const table = pkgmeta?.pkgs || {};
  const out = new Map();
  for (const [name, version] of detail.packages || []) {
    const entry = table[name]?.[version];
    if (entry && typeof entry.i === 'number') out.set(name, entry.i);
  }
  return out;
}

export function rankContributors(summary, a, b, pkgmeta, limit = 20) {
  // ---- snaps: measured, compressed bytes -------------------------------
  const snapRows = [];
  for (const s of summary.diff.snapAdded) {
    snapRows.push({
      ref: `s+${s.name}`,
      kind: 'snap',
      name: s.name,
      change: 'added',
      detail: `${s.channel} r${s.rev}`,
      bytes: typeof s.bytes === 'number' ? s.bytes : null,
    });
  }
  for (const s of summary.diff.snapRemoved) {
    snapRows.push({
      ref: `s-${s.name}`,
      kind: 'snap',
      name: s.name,
      change: 'removed',
      detail: `${s.channel} r${s.rev}`,
      bytes: typeof s.bytes === 'number' ? -s.bytes : null,
    });
  }
  for (const s of summary.diff.snapChanged) {
    snapRows.push({
      ref: `s~${s.name}`,
      kind: 'snap',
      name: s.name,
      change: 'changed',
      detail: `r${s.fromRev} → r${s.toRev}`,
      bytes: s.deltaBytes,
    });
  }
  const snapKnown = snapRows.filter((r) => typeof r.bytes === 'number' && r.bytes !== 0);
  snapKnown.sort((x, y) => Math.abs(y.bytes) - Math.abs(x.bytes));

  // ---- packages: measured, uncompressed KB ------------------------------
  const pkgRows = [];
  let unresolved = 0;

  if (pkgmeta) {
    const A = installedKB(a, pkgmeta);
    const B = installedKB(b, pkgmeta);
    const table = pkgmeta.pkgs || {};

    const record = (name, kb, change, detail) => {
      pkgRows.push({
        ref: `p${change[0]}${name}`,
        kind: 'pkg',
        name,
        change,
        detail,
        kb,
        source: sourceOf(table, name),
      });
    };

    for (const p of summary.diff.added) {
      const kb = B.get(p.name);
      if (typeof kb === 'number') record(p.name, kb, 'added', p.version);
      else unresolved++;
    }
    for (const p of summary.diff.removed) {
      const kb = A.get(p.name);
      if (typeof kb === 'number') record(p.name, -kb, 'removed', p.version);
      else unresolved++;
    }
    for (const p of summary.diff.changed) {
      const from = A.get(p.name);
      const to = B.get(p.name);
      if (typeof from === 'number' && typeof to === 'number') {
        if (to - from !== 0) record(p.name, to - from, 'changed', `${p.from} → ${p.to}`);
      } else {
        unresolved++;
      }
    }
  } else {
    unresolved = summary.added + summary.removed + summary.changed;
  }

  pkgRows.sort((x, y) => Math.abs(y.kb) - Math.abs(x.kb));

  // Roll individual binaries up to their source package, so twelve libfoo*
  // rows read as one "foo" line.
  const bySource = new Map();
  for (const r of pkgRows) {
    const key = r.source || r.name;
    const cur = bySource.get(key) || { source: key, kb: 0, count: 0 };
    cur.kb += r.kb;
    cur.count += 1;
    bySource.set(key, cur);
  }
  const sourceRows = [...bySource.values()]
    .filter((r) => r.kb !== 0)
    .sort((x, y) => Math.abs(y.kb) - Math.abs(x.kb))
    .slice(0, limit);

  const snapDelta = snapKnown.reduce((acc, r) => acc + r.bytes, 0);
  const installedDelta = pkgRows.reduce((acc, r) => acc + r.kb, 0);

  return {
    snapRows: snapKnown.slice(0, limit),
    pkgRows: pkgRows.slice(0, limit),
    sourceRows,
    snapDelta,
    installedKBDelta: installedDelta,
    installedFromTotal: a.totals?.installedKB ?? null,
    installedToTotal: b.totals?.installedKB ?? null,
    observed: summary.bytesDelta,
    unresolvedPackages: unresolved,
    havePkgMeta: Boolean(pkgmeta),
    coverage: {
      a: a.coverage || null,
      b: b.coverage || null,
    },
  };
}

function sourceOf(table, name) {
  const versions = table[name];
  if (!versions) return null;
  const first = Object.values(versions)[0];
  return first?.src || null;
}

/**
 * "Why is this package here?"
 *
 * Walks the reverse-dependency graph restricted to packages actually present
 * in the image, from the target back to a package the archive marks as a task
 * member or required/important priority -- i.e. something the image seeds
 * directly. Returns the shortest such chain.
 *
 * This is dependency evidence from the archive index, not germinate seed
 * output, so the UI labels it accordingly: it shows *a* path that explains the
 * presence, not necessarily the reason the archive team would give.
 */
export function explainWhy(target, detail, pkgmeta, maxDepth = 8) {
  if (!pkgmeta) return null;
  const table = pkgmeta.pkgs || {};

  const present = new Map();
  for (const [name, version] of detail.packages || []) present.set(name, version);
  if (!present.has(target)) return null;

  const entryFor = (name) => table[name]?.[present.get(name)] || null;

  // Reverse edges among packages present in this image.
  const parents = new Map();
  for (const [name] of present) {
    const e = entryFor(name);
    if (!e) continue;
    for (const dep of [...(e.dep || []), ...(e.rec || [])]) {
      if (!present.has(dep)) continue;
      if (!parents.has(dep)) parents.set(dep, []);
      parents.get(dep).push(name);
    }
  }

  /**
   * A package terminates the chain when it explains itself: the archive marks
   * it as a task member, essential, or required/important priority -- or
   * nothing else in this image depends on it, which means the image seeded it
   * directly. That last case matters in practice: kernel metapackages such as
   * linux-image-generic-hwe-24.04 are optional priority with no Task field,
   * so without it every kernel chain dead-ends.
   */
  const rootReason = (name) => {
    const e = entryFor(name);
    if (!e) return null;
    if (e.task?.length) return `task: ${e.task.join(', ')}`;
    if (e.ess) return 'marked Essential';
    if (e.pri === 'required' || e.pri === 'important') return `priority: ${e.pri}`;
    if (!(parents.get(name) || []).length) {
      return 'seeded directly (nothing else in this image depends on it)';
    }
    return null;
  };

  // BFS outward from the target to the nearest root.
  const seen = new Set([target]);
  let frontier = [[target]];
  for (let depth = 0; depth < maxDepth; depth++) {
    const next = [];
    for (const path of frontier) {
      const head = path[path.length - 1];
      for (const parent of parents.get(head) || []) {
        if (seen.has(parent)) continue;
        seen.add(parent);
        const extended = [...path, parent];
        const reason = rootReason(parent);
        if (reason) return { chain: extended.slice().reverse(), rootReason: reason };
        next.push(extended);
      }
    }
    if (!next.length) break;
    frontier = next;
  }

  const selfReason = rootReason(target);
  if (selfReason) return { chain: [target], rootReason: selfReason };
  return null;
}
