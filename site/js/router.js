/**
 * Hash routing, so a view is shareable -- the whole point being that a link to
 * "26.10 snapshot 3 -> 4, Server amd64" can be pasted into a bug report.
 *
 * Hash routing (not paths) means GitHub Pages needs no 404 rewrite rules.
 */
const KEYS = ['view', 'metric', 'xmode', 'a', 'b', 'image', 'sort', 'hidden'];

export function encode(state) {
  const p = new URLSearchParams();
  for (const k of KEYS) {
    const v = state[k];
    if (v === null || v === undefined || v === '') continue;
    if (k === 'hidden') {
      if (v instanceof Set && v.size) p.set(k, [...v].join(','));
      continue;
    }
    p.set(k, v);
  }
  return '#' + p.toString();
}

export function decode(hash) {
  const p = new URLSearchParams((hash || '').replace(/^#/, ''));
  const out = {};
  for (const k of KEYS) {
    if (!p.has(k)) continue;
    out[k] = k === 'hidden' ? new Set(p.get(k).split(',').filter(Boolean)) : p.get(k);
  }
  return out;
}

let writing = false;

export function install(store) {
  store.subscribe((state) => {
    const next = encode(state);
    if (next === location.hash) return;
    writing = true;
    history.replaceState(null, '', next);
    writing = false;
  });

  window.addEventListener('hashchange', () => {
    if (writing) return;
    store.set(decode(location.hash));
  });
}
