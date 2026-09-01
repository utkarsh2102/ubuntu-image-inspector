/**
 * The ONLY place a data URL is constructed.
 *
 * Resolving from import.meta.url rather than an absolute "/data/..." path is
 * what makes the site work both at http://localhost:8000/ and at a GitHub Pages
 * project path like https://<org>.github.io/ubuntu-image-inspector/.
 */
export const DATA_ROOT = new URL('../../data/', import.meta.url);

export function dataUrl(...parts) {
  return new URL(parts.join('/'), DATA_ROOT).href;
}

/** Milestone id "questing:snapshot-3" -> ["questing", "snapshot-3"]. */
export function splitMilestone(id) {
  const i = id.indexOf(':');
  return [id.slice(0, i), id.slice(i + 1)];
}

/** Image id "live-server/arm64+largemem" -> "live-server-arm64+largemem". */
export function imageSlug(imageId) {
  return imageId.replace('/', '-');
}
