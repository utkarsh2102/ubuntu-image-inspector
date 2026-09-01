/**
 * Top Movers: every image ranked across one comparison.
 *
 * The size column is a diverging bar centred on zero -- growth and shrink are
 * opposite directions, not "bad" and "good", so it uses the diverging pair
 * rather than the status palette.
 */
import { el, clear } from '../util/dom.js';
import { bytes, deltaBytes, deltaNum, num } from '../util/fmt.js';

export function renderMovers(root, rows, sortId, sorts, onPick) {
  clear(root);

  if (!rows.length) {
    root.append(
      el('div', {
        class: 'empty',
        text: 'No images are present in both selected milestones.',
      })
    );
    return;
  }

  const sort = sorts.find((s) => s.id === sortId) || sorts[0];
  const sorted = [...rows].sort((a, b) => {
    const av = a[sort.metric];
    const bv = b[sort.metric];
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return sort.dir === -1 ? bv - av : av - bv;
  });

  const maxAbs = Math.max(
    1,
    ...sorted.map((r) => (typeof r.bytesDelta === 'number' ? Math.abs(r.bytesDelta) : 0))
  );

  const table = el('table', { class: 'data' });
  table.append(
    el('thead', {}, [
      el('tr', {}, [
        el('th', { text: 'Image' }),
        el('th', { class: 'num', text: 'Size Δ' }),
        el('th', { text: '', style: { width: '180px' } }),
        el('th', { class: 'num', text: 'Size' }),
        el('th', { class: 'num', text: 'Pkg +' }),
        el('th', { class: 'num', text: 'Pkg −' }),
        el('th', { class: 'num', text: 'Pkg Δ' }),
        el('th', { class: 'num', text: 'Snap +' }),
        el('th', { class: 'num', text: 'Snap −' }),
        el('th', { class: 'num', text: 'Snap Δ' }),
      ]),
    ])
  );

  const tbody = el('tbody');
  for (const r of sorted) {
    const d = r.bytesDelta;
    const frac = typeof d === 'number' ? Math.abs(d) / maxAbs : 0;
    const bar = el('div', { class: 'dbar' });
    bar.append(el('div', { class: 'dbar__zero', style: { left: '50%' } }));
    if (typeof d === 'number' && d !== 0) {
      const fill = el('div', {
        class: `dbar__fill dbar__fill--${d > 0 ? 'pos' : 'neg'}`,
      });
      const w = (frac * 50).toFixed(2) + '%';
      fill.style.width = w;
      if (d > 0) fill.style.left = '50%';
      else fill.style.right = '50%';
      bar.append(fill);
    }

    const tr = el('tr', { dataset: { image: r.imageId } }, [
      el('td', {}, [
        el('button', {
          class: 'row-btn',
          type: 'button',
          text: r.label,
          title: 'Open in What Changed?',
          onclick: () => onPick(r.imageId),
        }),
      ]),
      el('td', { class: 'num', text: deltaBytes(d) }),
      el('td', {}, [bar]),
      el('td', { class: 'num', text: bytes(r.bytesTo) }),
      el('td', { class: 'num', text: num(r.added) }),
      el('td', { class: 'num', text: num(r.removed) }),
      el('td', { class: 'num', text: num(r.changed) }),
      el('td', { class: 'num', text: num(r.snapAdded) }),
      el('td', { class: 'num', text: num(r.snapRemoved) }),
      el('td', { class: 'num', text: num(r.snapChanged) }),
    ]);
    tbody.append(tr);
  }
  table.append(tbody);

  root.append(table);
  root.append(
    el('p', {
      class: 'note',
      text: `${sorted.length} images compared. Size deltas are measured from each artifact's Content-Length.`,
    })
  );
}
