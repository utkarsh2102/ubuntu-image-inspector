/**
 * The evidence pack.
 *
 * Assembled EXCLUSIVELY from values the deterministic layer already computed.
 * The model fetches nothing and calculates nothing; it receives facts and
 * returns interpretation. Anything the data cannot establish is stated as a
 * caveat rather than omitted, so the model is told what it does not know.
 */
import { bytes } from '../util/fmt.js';

export function buildEvidencePack({ index, aM, bM, image, summary, attribution, why, question }) {
  const snapContributors = attribution.snapRows.map((r, i) => ({
    ref: `s${i + 1}`,
    kind: 'snap',
    name: r.name,
    change: r.change,
    detail: r.detail,
    deltaBytesCompressed: r.bytes,
  }));

  const pkgContributors = attribution.pkgRows.map((r, i) => ({
    ref: `p${i + 1}`,
    kind: 'package',
    name: r.name,
    sourcePackage: r.source,
    change: r.change,
    detail: r.detail,
    deltaInstalledKB: r.kb,
  }));

  const sourceRollup = attribution.sourceRows.map((r, i) => ({
    ref: `r${i + 1}`,
    sourcePackage: r.source,
    binaries: r.count,
    deltaInstalledKB: r.kb,
  }));

  const caveats = [
    'UNITS: observed.bytesDelta is COMPRESSED image bytes from HTTP Content-Length. ' +
      'Package deltas are UNCOMPRESSED installed kilobytes from the archive Packages index. ' +
      'These are different units. Never add them together and never present an installed-size ' +
      'change as though it were the image size change.',
    'The image is squashfs-compressed. This dataset does not measure the compression ratio, so ' +
      'you cannot convert an installed-size change into an image-size change. Do not estimate one.',
    'Snap sizes are the snap store\'s reported download size for the exact revision pinned in ' +
      'the manifest, and are already compressed.',
  ];

  if (attribution.unresolvedPackages) {
    caveats.push(
      `${attribution.unresolvedPackages} changed packages could not be resolved in the archive ` +
        'index; their size is unknown, not zero. Do not guess it.'
    );
  }
  if (!attribution.havePkgMeta) {
    caveats.push(
      'No package metadata is available for this series/architecture, so no package has a known size.'
    );
  }
  if (!why) {
    caveats.push(
      'No dependency path was requested or found, so do not assert why any package is present.'
    );
  }

  return {
    schemaVersion: 2,
    question:
      question || 'Explain this image\'s change between the two milestones, with concrete evidence.',
    context: {
      image: { id: image.id, publishType: image.publishType, arch: image.arch },
      from: {
        milestone: aM.id,
        label: `${aM.version} ${aM.label}`,
        built: summary.builtA || aM.date,
        imageBytes: summary.bytesFrom,
        installedKB: attribution.installedFromTotal,
      },
      to: {
        milestone: bM.id,
        label: `${bM.version} ${bM.label}`,
        built: summary.builtB || bM.date,
        imageBytes: summary.bytesTo,
        installedKB: attribution.installedToTotal,
      },
    },
    observed: {
      imageBytesDelta: summary.bytesDelta,
      installedKBDelta: attribution.installedKBDelta,
      snapCompressedBytesDelta: attribution.snapDelta,
    },
    counts: {
      packagesAdded: summary.added,
      packagesRemoved: summary.removed,
      packagesChanged: summary.changed,
      snapsAdded: summary.snapAdded,
      snapsRemoved: summary.snapRemoved,
      snapsChanged: summary.snapChanged,
      packagesTotalFrom: summary.pkgFrom,
      packagesTotalTo: summary.pkgTo,
    },
    topPackageContributors: pkgContributors,
    topSnapContributors: snapContributors,
    sourcePackageRollup: sourceRollup,
    samplePackagesAdded: summary.diff.added.slice(0, 30).map((p) => `${p.name} ${p.version}`),
    samplePackagesRemoved: summary.diff.removed.slice(0, 30).map((p) => `${p.name} ${p.version}`),
    dependencyEvidence: why
      ? { package: why.package, path: why.chain, rootReason: why.rootReason }
      : null,
    caveats,
    provenance: {
      generatedAt: index.generatedAt,
      collector: index.collector?.version,
      sources: [
        'cdimage.ubuntu.com',
        'releases.ubuntu.com',
        'old-releases.ubuntu.com',
        'snapshot.ubuntu.com',
        'api.snapcraft.io',
      ],
    },
  };
}

/** Every numeric literal the pack contains, for the hallucination check. */
export function packNumbers(pack) {
  const nums = new Set();
  const walk = (v) => {
    if (typeof v === 'number' && isFinite(v)) {
      nums.add(Math.abs(v));
      return;
    }
    if (Array.isArray(v)) return v.forEach(walk);
    if (v && typeof v === 'object') return Object.values(v).forEach(walk);
    if (typeof v === 'string') {
      for (const m of v.matchAll(/\d[\d,.]*/g)) {
        const n = parseFloat(m[0].replace(/,/g, ''));
        if (isFinite(n)) nums.add(Math.abs(n));
      }
    }
  };
  walk(pack);
  return nums;
}
