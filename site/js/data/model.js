/**
 * Derived views over the index: milestone ordering, image colour identity, and
 * the metric registry.
 */

/** Flat, ordered list of every milestone across every series. */
export function allMilestones(index) {
  const out = [];
  for (const s of index.series) {
    for (const m of s.milestones) {
      out.push({ ...m, codename: s.codename, version: s.version, seriesLabel: s.version });
    }
  }
  return out;
}

export function milestoneById(index, id) {
  return allMilestones(index).find((m) => m.id === id) || null;
}

/**
 * Colour identity.
 *
 * There are ~17 images but only 8 validated categorical slots, and generating
 * extra hues is exactly what makes a chart unreadable for colour-blind readers.
 * So identity is composite: hue encodes the image family (5 families, well
 * inside the validated set) and dash pattern encodes the architecture. Colour
 * is assigned from a stable sort of the FULL catalog, so filtering never
 * repaints the survivors.
 */
const FAMILY_ORDER = [
  'desktop',
  'live-server',
  'wsl',
  'preinstalled-server',
  'preinstalled-desktop',
  'netboot',
  'base',
];

const DASHES = [null, [6, 3], [2, 3], [10, 3, 2, 3], [1, 3]];

export function buildStyles(index) {
  const styles = new Map();
  const archesByFamily = new Map();

  for (const img of index.images) {
    if (!archesByFamily.has(img.publishType)) archesByFamily.set(img.publishType, []);
    archesByFamily.get(img.publishType).push(img.arch);
  }
  for (const list of archesByFamily.values()) list.sort();

  for (const img of index.images) {
    const famIdx = FAMILY_ORDER.indexOf(img.publishType);
    const slot = (famIdx < 0 ? FAMILY_ORDER.length : famIdx) % 8;
    const archIdx = archesByFamily.get(img.publishType).indexOf(img.arch);
    styles.set(img.id, {
      colorVar: `--series-${slot + 1}`,
      dash: DASHES[archIdx % DASHES.length],
      family: img.publishType,
    });
  }
  return styles;
}

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export const SORTS = [
  { id: 'bytes-desc', label: 'Largest size increase', metric: 'bytesDelta', dir: -1 },
  { id: 'bytes-asc', label: 'Largest size decrease', metric: 'bytesDelta', dir: 1 },
  { id: 'added-desc', label: 'Most packages added', metric: 'added', dir: -1 },
  { id: 'removed-desc', label: 'Most packages removed', metric: 'removed', dir: -1 },
  { id: 'changed-desc', label: 'Most packages changed', metric: 'changed', dir: -1 },
  { id: 'snapadd-desc', label: 'Most snaps added', metric: 'snapAdded', dir: -1 },
  { id: 'snaprm-desc', label: 'Most snaps removed', metric: 'snapRemoved', dir: -1 },
  { id: 'snapchg-desc', label: 'Most snap changes', metric: 'snapChanged', dir: -1 },
];
