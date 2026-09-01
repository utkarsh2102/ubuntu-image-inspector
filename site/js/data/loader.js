/** Fetch with in-flight dedupe and a memory cache. Data files are immutable. */
const cache = new Map();
const inflight = new Map();

export async function fetchJson(url) {
  if (cache.has(url)) return cache.get(url);
  if (inflight.has(url)) return inflight.get(url);

  const p = fetch(url, { credentials: 'omit' })
    .then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${url}`);
      return r.json();
    })
    .then((data) => {
      cache.set(url, data);
      inflight.delete(url);
      return data;
    })
    .catch((err) => {
      inflight.delete(url);
      throw err;
    });

  inflight.set(url, p);
  return p;
}

export function peek(url) {
  return cache.get(url);
}
