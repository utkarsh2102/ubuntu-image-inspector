/**
 * The only module that knows the on-disk layout of site/data.
 *
 * Everything else asks for entities, never paths -- so a schema change is a
 * one-file change here.
 */
import { dataUrl, imageSlug, splitMilestone } from './paths.js';
import { fetchJson } from './loader.js';

let indexDoc = null;

export async function loadIndex() {
  if (!indexDoc) indexDoc = await fetchJson(dataUrl('index.json'));
  return indexDoc;
}

/** Rehydrate the row-as-array metrics encoding into objects, once. */
export async function loadMetrics(codename) {
  const doc = await fetchJson(dataUrl('metrics', `${codename}.json`));
  const f = doc.fields;
  return doc.points.map((row) => {
    const o = {};
    for (let i = 0; i < f.length; i++) o[f[i]] = row[i];
    return o;
  });
}

export async function loadDetail(milestoneId, imageId) {
  const [codename, slug] = splitMilestone(milestoneId);
  return fetchJson(dataUrl('detail', codename, slug, `${imageSlug(imageId)}.json`));
}

/**
 * Package sizes and dependencies for one (series, architecture).
 * ~150 KB gzipped, so it is fetched only when a comparison is actually opened.
 */
export async function loadPkgMeta(codename, arch) {
  return fetchJson(dataUrl('pkgmeta', `${codename}-${arch}.json`));
}

/** Detail for one image at both ends of a comparison; null where absent. */
export async function loadPair(aId, bId, imageId) {
  const [a, b] = await Promise.all([
    loadDetail(aId, imageId).catch(() => null),
    loadDetail(bId, imageId).catch(() => null),
  ]);
  return { a, b };
}
