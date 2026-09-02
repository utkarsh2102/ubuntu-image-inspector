/** Bootstrap: wires the store, the data layer and the views. */
import { createStore } from './state.js';
import * as router from './router.js';
import { loadIndex, loadMetrics, loadPair, loadPkgMeta } from './data/repo.js';
import { buildStyles, SORTS } from './data/model.js';
import { el, clear, option } from './util/dom.js';
import { shortDate } from './util/fmt.js';
import { summarise } from './diff/engine.js';
import { rankContributors, explainWhy } from './diff/attribution.js';
import { buildTrendData, renderTrend, renderLegend, resizeTrend } from './views/trend.js';
import { renderMovers } from './views/movers.js';
import { renderKpis, renderContributors, renderChangeLists, renderWhy } from './views/changed.js';

const $ = (id) => document.getElementById(id);

const store = createStore({
  view: 'overview',
  metric: 'bytes',
  xmode: 'ordinal',
  a: null,
  b: null,
  image: null,
  sort: 'bytes-desc',
  hidden: new Set(),
  index: null,
  metricsBySeries: {},
  styles: new Map(),
  moverRows: [],
  pair: null,
  pkgmeta: null,
  filter: '',
  ...router.decode(location.hash),
});

let llm = null; // lazily imported; the dashboard never depends on it

async function boot() {
  const index = await loadIndex();
  const styles = buildStyles(index);

  const metricsBySeries = {};
  await Promise.all(
    index.series.map(async (s) => {
      metricsBySeries[s.codename] = await loadMetrics(s.codename);
    })
  );

  const milestones = [];
  for (const s of index.series) {
    for (const m of s.milestones) {
      milestones.push({ ...m, codename: s.codename, version: s.version });
    }
  }

  const state = store.get();
  const defaults = {};
  if (!state.a || !state.b) {
    // Default to the most recent adjacent pair that actually has data.
    const last = milestones[milestones.length - 1];
    const prev = milestones[milestones.length - 2] || last;
    defaults.a = prev.id;
    defaults.b = last.id;
  }
  if (!state.image) defaults.image = 'live-server/amd64';

  store.set({ index, styles, metricsBySeries, milestones, ...defaults });

  buildControls();
  router.install(store);
  store.subscribe(render);
  render(store.get(), ['*']);
  await refreshComparison();
}

function buildControls() {
  const { index, milestones } = store.get();

  clear($('metric-select'));
  for (const m of index.metrics) {
    $('metric-select').append(option(m.id, m.label, m.id === store.get().metric));
  }
  $('metric-select').addEventListener('change', (e) => store.set({ metric: e.target.value }));

  $('xmode-select').value = store.get().xmode;
  $('xmode-select').addEventListener('change', (e) => store.set({ xmode: e.target.value }));

  for (const id of ['cmp-a', 'cmp-b']) {
    const sel = $(id);
    clear(sel);
    for (const m of milestones) {
      sel.append(
        option(m.id, `${m.version} — ${m.label}${m.date ? ` (${shortDate(m.date)})` : ''}`)
      );
    }
    sel.value = id === 'cmp-a' ? store.get().a : store.get().b;
    sel.addEventListener('change', (e) =>
      store.set(id === 'cmp-a' ? { a: e.target.value } : { b: e.target.value })
    );
  }

  clear($('sort-select'));
  for (const s of SORTS) $('sort-select').append(option(s.id, s.label, s.id === store.get().sort));
  $('sort-select').addEventListener('change', (e) => store.set({ sort: e.target.value }));

  clear($('wc-image'));
  for (const img of index.images) $('wc-image').append(option(img.id, img.label));
  $('wc-image').value = store.get().image;
  $('wc-image').addEventListener('change', (e) => store.set({ image: e.target.value }));

  $('wc-filter').addEventListener('input', (e) => store.set({ filter: e.target.value }));

  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => store.set({ view: tab.dataset.view }));
  }

  $('theme-toggle').addEventListener('click', () => {
    const root = document.documentElement;
    // With no attribute set the OS preference is in charge; the first click
    // flips away from whatever is currently showing.
    const dark =
      root.dataset.theme === 'dark' ||
      (!root.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    root.dataset.theme = dark ? 'light' : 'dark';
    try {
      localStorage.setItem('uii.theme', root.dataset.theme);
    } catch {
      /* storage blocked: the choice simply does not persist */
    }
    render(store.get(), ['theme']);
  });

  try {
    const saved = localStorage.getItem('uii.theme');
    if (saved) document.documentElement.dataset.theme = saved;
  } catch {
    /* ignore */
  }

  $('llm-settings').addEventListener('click', async () => {
    llm = llm || (await import('./llm/panel.js'));
    llm.renderSettings($('llm-panel'));
  });
  $('llm-copy').addEventListener('click', async () => {
    llm = llm || (await import('./llm/panel.js'));
    const pack = llm.currentPack();
    if (!pack) return;
    const text = JSON.stringify(pack, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      $('llm-panel').append(el('p', { class: 'note', text: 'Evidence pack copied to clipboard.' }));
    } catch {
      const ta = el('textarea', { style: { width: '100%', height: '160px' } });
      ta.value = text;
      clear($('llm-panel')).append(ta);
    }
  });
  $('llm-run').addEventListener('click', async () => {
    llm = llm || (await import('./llm/panel.js'));
    await llm.runAnalysis($('llm-panel'), highlightRef);
  });

  window.addEventListener('resize', () => resizeTrend($('chart')));
}

function highlightRef(ref) {
  const row = document.querySelector(`#wc-contrib tr[data-ref="${CSS.escape(ref)}"]`);
  if (!row) return;
  for (const r of document.querySelectorAll('#wc-contrib tr')) r.classList.remove('is-selected');
  row.classList.add('is-selected');
  row.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function render(state, changed) {
  const needsComparison = ['a', 'b', 'image'].some((k) => changed.includes(k));

  document.querySelectorAll('.tab').forEach((t) => {
    t.setAttribute('aria-selected', String(t.dataset.view === state.view));
  });
  $('view-overview').hidden = state.view !== 'overview';
  $('view-changed').hidden = state.view === 'overview';

  if (!state.index) return;

  const data = buildTrendData(state.index, state.metricsBySeries, state);
  renderTrend($('chart'), $('chart-note'), data, state.styles, state, null);
  renderLegend($('legend'), data, state.styles, state, toggleImage, bulkToggle);

  renderMovers($('movers'), state.moverRows, state.sort, SORTS, (imageId) =>
    store.set({ image: imageId, view: 'changed' })
  );

  renderComparisonPanels(state);

  const prov = state.index.generatedAt
    ? `Data generated ${shortDate(state.index.generatedAt)} · collector ${state.index.collector?.version || '—'}`
    : '';
  $('prov').textContent = prov;

  if (needsComparison) refreshComparison();
}

function renderComparisonPanels(state) {
  const { pair, index } = state;
  const img = index.images.find((i) => i.id === state.image);
  const aM = state.milestones.find((m) => m.id === state.a);
  const bM = state.milestones.find((m) => m.id === state.b);

  $('wc-title').textContent = img ? img.label : 'Select an image';
  $('wc-sub').textContent =
    aM && bM ? `${aM.version} ${aM.label} → ${bM.version} ${bM.label}` : '';

  clear($('wc-why'));

  if (!pair || !pair.a || !pair.b) {
    clear($('wc-kpis')).append(
      el('div', {
        class: 'empty',
        text: 'This image is not published in both selected milestones.',
      })
    );
    clear($('wc-contrib'));
    clear($('wc-lists'));
    return;
  }

  const s = summarise(pair.a, pair.b);
  s.builtA = pair.a.built;
  s.builtB = pair.b.built;
  const attribution = rankContributors(s, pair.a, pair.b, state.pkgmeta);

  renderKpis($('wc-kpis'), s, aM, bM);
  renderContributors($('wc-contrib'), attribution, (name) => {
    const why = explainWhy(name, pair.b, state.pkgmeta);
    renderWhy($('wc-why'), name, why);
    $('wc-why').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
  renderChangeLists($('wc-lists'), s, state.filter);

  if (llm) {
    llm.preparePack({ index, aM, bM, image: img, summary: s, attribution });
  } else {
    // Keep the pack ready without loading the panel: import on first need only.
    import('./llm/panel.js').then((mod) => {
      llm = mod;
      mod.preparePack({ index, aM, bM, image: img, summary: s, attribution });
    });
  }
}

function toggleImage(id) {
  const hidden = new Set(store.get().hidden);
  if (hidden.has(id)) hidden.delete(id);
  else hidden.add(id);
  store.set({ hidden });
}

function bulkToggle(mode) {
  const { index } = store.get();
  store.set({ hidden: mode === 'all' ? new Set() : new Set(index.images.map((i) => i.id)) });
}

/** Recompute Top Movers and the per-image pair for the current comparison. */
async function refreshComparison() {
  const state = store.get();
  if (!state.index || !state.a || !state.b) return;

  const candidates = state.index.images.filter((i) => i.hasManifest);
  const results = await Promise.all(
    candidates.map(async (img) => {
      const { a, b } = await loadPair(state.a, state.b, img.id);
      if (!a || !b) return null;
      const s = summarise(a, b);
      return { imageId: img.id, label: img.label, ...s };
    })
  );

  const rows = results.filter(Boolean);
  const pair = await loadPair(state.a, state.b, state.image);

  // Package sizes live per (series, arch) and are only needed once a specific
  // image comparison is open, so they are fetched here rather than at boot.
  let pkgmeta = null;
  if (pair.b) {
    const [, arch] = state.image.split('/');
    const codename = state.b.split(':')[0];
    pkgmeta = await loadPkgMeta(codename, arch).catch(() => null);
  }

  store.set({ moverRows: rows, pair, pkgmeta });
}

boot().catch((err) => {
  document.getElementById('main').prepend(
    el('div', { class: 'panel' }, [
      el('h3', { text: 'Could not load data' }),
      el('p', { class: 'warn', text: String(err.message || err) }),
    ])
  );
});
