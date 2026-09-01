/**
 * The image-size-over-time chart.
 *
 * Design decisions worth knowing:
 *  - ONE y scale, always. Size and package count are different metrics with
 *    different units; they are switched between, never overlaid on twin axes.
 *  - ~23 images but only 8 validated categorical slots. Identity is composite:
 *    hue = image family, dash = architecture (see data/model.js). Generating 23
 *    hues would look decisive and be unreadable.
 *  - The x axis defaults to milestone sequence, because snapshot cadence is
 *    irregular and sequence is the only axis on which "26.10 snapshot 3" lines
 *    up with "25.10 snapshot 3". The axis says so, and every tooltip carries
 *    the real build date.
 */
import { cssVar } from '../data/model.js';
import { el, clear } from '../util/dom.js';
import { formatMetric, shortDate } from '../util/fmt.js';

let chart = null;
let lastKey = '';

export function buildTrendData(index, metricsBySeries, state) {
  const metric = state.metric || 'bytes';
  const xmode = state.xmode || 'ordinal';

  // Build the global milestone sequence across the selected series.
  const milestones = [];
  for (const s of index.series) {
    for (const m of s.milestones) {
      milestones.push({ ...m, codename: s.codename, version: s.version });
    }
  }
  milestones.sort((a, b) => {
    if (a.codename !== b.codename) {
      const ai = index.series.findIndex((s) => s.codename === a.codename);
      const bi = index.series.findIndex((s) => s.codename === b.codename);
      return ai - bi;
    }
    return a.order - b.order;
  });

  const xs =
    xmode === 'date'
      ? milestones.map((m) => (m.date ? Date.parse(m.date) / 1000 : null))
      : milestones.map((_, i) => i);

  // Drop milestones with no date in date mode, keeping the arrays aligned.
  const keep = xs.map((v) => v !== null);
  const xVals = xs.filter((_, i) => keep[i]);
  const keptMilestones = milestones.filter((_, i) => keep[i]);

  const lookup = new Map();
  for (const [codename, rows] of Object.entries(metricsBySeries)) {
    for (const r of rows) lookup.set(`${r.m}|${r.i}`, r);
  }

  const series = [];
  for (const img of index.images) {
    const values = keptMilestones.map((m) => {
      const row = lookup.get(`${m.id}|${img.id}`);
      if (!row) return null;
      const v = row[metric];
      return typeof v === 'number' ? v : null;
    });
    if (values.every((v) => v === null)) continue;
    series.push({ image: img, values });
  }

  return { milestones: keptMilestones, xVals, series, metric, xmode };
}

export function renderTrend(root, noteEl, data, styles, state, onHover) {
  const { milestones, xVals, series, metric, xmode } = data;
  const hidden = state.hidden || new Set();

  const visible = series.filter((s) => !hidden.has(s.image.id));
  const uplotData = [xVals, ...visible.map((s) => s.values)];

  const metricLabel =
    (state.index?.metrics || []).find((m) => m.id === metric)?.label || metric;

  noteEl.textContent =
    xmode === 'ordinal'
      ? 'X axis is milestone sequence, not to scale in time — build dates are in the tooltip.'
      : 'X axis is real build date.';

  const opts = {
    width: root.clientWidth || 900,
    height: 400,
    padding: [12, 16, 4, 8],
    scales: { x: { time: xmode === 'date' }, y: { auto: true } },
    legend: { show: false },
    cursor: {
      y: false,
      points: { size: 7 },
      focus: { prox: 24 },
    },
    axes: [
      {
        stroke: cssVar('--text-muted'),
        grid: { stroke: cssVar('--hairline'), width: 1 },
        ticks: { stroke: cssVar('--hairline'), width: 1 },
        font: '11px system-ui, sans-serif',
        values:
          xmode === 'date'
            ? null
            : (_u, splits) =>
                splits.map((i) => {
                  const m = milestones[i];
                  if (!m) return '';
                  return `${m.version} ${m.label}`;
                }),
        rotate: xmode === 'ordinal' ? -30 : 0,
        size: xmode === 'ordinal' ? 78 : 40,
        label: xmode === 'ordinal' ? 'Milestone sequence (not to scale in time)' : 'Build date',
        labelSize: 22,
        labelFont: '11px system-ui, sans-serif',
      },
      {
        stroke: cssVar('--text-muted'),
        grid: { stroke: cssVar('--hairline'), width: 1 },
        ticks: { stroke: cssVar('--hairline'), width: 1 },
        font: '11px system-ui, sans-serif',
        size: 68,
        label: metricLabel,
        labelSize: 22,
        labelFont: '11px system-ui, sans-serif',
        values: (_u, splits) => splits.map((v) => formatMetric(metric, v)),
      },
    ],
    series: [
      {
        value: (_u, i) => {
          const m = milestones[i];
          return m ? `${m.version} ${m.label} · ${shortDate(m.date)}` : '—';
        },
      },
      ...visible.map((s) => {
        const st = styles.get(s.image.id) || {};
        return {
          label: s.image.label,
          stroke: cssVar(st.colorVar || '--series-1'),
          width: 2,
          dash: st.dash || undefined,
          points: { show: false },
          spanGaps: false,
          value: (_u, v) => formatMetric(metric, v),
        };
      }),
    ],
    hooks: {
      setCursor: [
        (u) => {
          if (onHover) onHover(u.cursor.idx, visible, milestones, metric);
        },
      ],
    },
  };

  const key = JSON.stringify([
    metric,
    xmode,
    visible.map((s) => s.image.id),
    xVals.length,
    document.documentElement.dataset.theme,
  ]);

  clear(root);
  if (chart) {
    chart.destroy();
    chart = null;
  }
  lastKey = key;
  if (!visible.length) {
    root.append(el('div', { class: 'empty', text: 'No images selected.' }));
    return;
  }
  chart = new uPlot(opts, uplotData, root);
}

export function resizeTrend(root) {
  if (chart) chart.setSize({ width: root.clientWidth, height: 400 });
}

/** Grouped legend: family label, then one toggle per architecture. */
export function renderLegend(root, data, styles, state, onToggle, onBulk) {
  clear(root);
  const hidden = state.hidden || new Set();

  const groups = new Map();
  for (const s of data.series) {
    const fam = s.image.publishType;
    if (!groups.has(fam)) groups.set(fam, []);
    groups.get(fam).push(s.image);
  }

  for (const [fam, images] of groups) {
    const g = el('div', { class: 'legend__group' });
    g.append(el('span', { class: 'legend__glabel', text: fam }));
    for (const img of images) {
      const st = styles.get(img.id) || {};
      const on = !hidden.has(img.id);
      const swatch = el('span', { class: 'legend__swatch' });
      swatch.style.background = cssVar(st.colorVar || '--series-1');
      if (st.dash) {
        swatch.style.background = `repeating-linear-gradient(90deg, ${cssVar(
          st.colorVar || '--series-1'
        )} 0 ${st.dash[0]}px, transparent ${st.dash[0]}px ${st.dash[0] + st.dash[1]}px)`;
      }
      g.append(
        el(
          'button',
          {
            class: 'legend__item',
            type: 'button',
            'aria-pressed': String(on),
            title: `${img.label} — click to ${on ? 'hide' : 'show'}`,
            onclick: () => onToggle(img.id),
          },
          [swatch, el('span', { text: img.arch })]
        )
      );
    }
    root.append(g);
  }

  root.append(
    el('div', { class: 'legend__actions' }, [
      el('button', { class: 'btn', type: 'button', text: 'Select all', onclick: () => onBulk('all') }),
      el('button', { class: 'btn', type: 'button', text: 'Clear', onclick: () => onBulk('none') }),
    ])
  );
}
