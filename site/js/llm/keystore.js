/**
 * API key handling for a site with no backend.
 *
 * sessionStorage by default so the key dies with the tab; localStorage only on
 * explicit opt-in. Never in the URL, never in the hash, never logged.
 */
const KEY = 'uii.llm.config';

export function loadConfig() {
  for (const store of [sessionStorage, localStorage]) {
    try {
      const raw = store.getItem(KEY);
      if (raw) return JSON.parse(raw);
    } catch {
      /* private mode, blocked storage: fall through to defaults */
    }
  }
  return { provider: 'anthropic', model: '', baseUrl: '', apiKey: '', remember: false };
}

export function saveConfig(cfg) {
  const target = cfg.remember ? localStorage : sessionStorage;
  const other = cfg.remember ? sessionStorage : localStorage;
  try {
    target.setItem(KEY, JSON.stringify(cfg));
    other.removeItem(KEY);
  } catch {
    /* storage unavailable: the config simply does not persist */
  }
}

export function clearConfig() {
  for (const store of [sessionStorage, localStorage]) {
    try {
      store.removeItem(KEY);
    } catch {
      /* ignore */
    }
  }
}
