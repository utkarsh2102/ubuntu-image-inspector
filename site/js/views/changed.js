/**
 * "What Changed?" -- one image, one comparison, in full detail.
 *
 * The contract with the reader: everything in this view is computed from the
 * published manifests and HTTP metadata. Where a magnitude is genuinely not
 * available (package byte sizes need the archive index, which is phase 2), the
 * UI says "not available" rather than showing a zero that looks like a fact.
 */
import { el, clear } from '../util/dom.js';
import { bytes, deltaBytes, deltaNum, num, pct, shortDate } from '../util/fmt.js';

/** Installed-Size is in KB; render it in the same human units as bytes. */
const deltaKB = (kb) => (typeof kb === 'number' ? deltaBytes(kb * 1024) : '—');
const bytesFromKB = (kb) => (typeof kb === 'number' ? bytes(kb * 1024) : '—');

export function renderKpis(root, s, aM, bM) {
  clear(root);
  if (!s) {
    root.append(el('div', { class: 'empty', text: 'Select an image to compare.' }));
    return;
  }

  const pctChange =
    typeof s.bytesDelta === 'number' && s.bytesFrom ? s.bytesDelta / s.bytesFrom : null;

  const tiles = [
    {
      label: 'Image size',
      value: deltaBytes(s.bytesDelta),
      sub: `${bytes(s.bytesFrom)} → ${bytes(s.bytesTo)}  (${pct(pctChange)})`,
      tone: s.bytesDelta > 0 ? 'pos' : s.bytesDelta < 0 ? 'neg' : '',
    },
    { label: 'Packages added', value: deltaNum(s.added), sub: `${num(s.pkgFrom)} → ${num(s.pkgTo)} total` },
    { label: 'Packages removed', value: s.removed ? `−${s.removed}` : '0', sub: 'present in A, absent in B' },
    { label: 'Packages changed', value: num(s.changed), sub: 'version differs' },
    {
      label: 'Snaps',
      value: deltaNum(s.snapAdded - s.snapRemoved),
      sub: `${num(s.snapFrom)} → ${num(s.snapTo)} · ${num(s.snapChanged)} revision changes`,
    },
    {
      label: 'Seeded snap bytes',
      value: deltaBytes(s.snapBytesDelta),
      sub: 'measured from the snap store',
      tone: s.snapBytesDelta > 0 ? 'pos' : s.snapBytesDelta < 0 ? 'neg' : '',
    },
  ];

  for (const t of tiles) {
    root.append(
      el('div', { class: `kpi ${t.tone ? 'kpi--' + t.tone : ''}` }, [
        el('div', { class: 'kpi__label', text: t.label }),
        el('div', { class: 'kpi__value', text: t.value }),
        el('div', { class: 'kpi__sub', text: t.sub }),
      ])
    );
  }
}

export function renderContributors(root, at, onWhy) {
  clear(root);
  if (!at) return;

  // Measured ISO delta first -- it is the ground truth everything else is
  // compared against.
  root.append(el('h4', { text: 'Size contributors' }));
  root.append(
    el('p', { class: 'note' }, [
      'Observed image size change: ',
      el('strong', { text: deltaBytes(at.observed) }),
      ' (measured from Content-Length). The two breakdowns below are measured in ',
      el('em', { text: 'different units' }),
      ' and are never summed.',
    ])
  );

  // ---- snaps: compressed bytes ----------------------------------------
  const snapBox = el('div', { class: 'contrib__block' });
  snapBox.append(
    el('h5', {}, [
      'Seeded snaps',
      el('span', { class: 'pill', text: 'compressed bytes · measured' }),
      el('span', { class: 'pill', text: deltaBytes(at.snapDelta) }),
    ])
  );
  if (at.snapRows.length) {
    snapBox.append(barTable(at.snapRows, (r) => r.bytes, (r) => deltaBytes(r.bytes)));
  } else {
    snapBox.append(el('p', { class: 'note', text: 'No snap size changes in this comparison.' }));
  }
  root.append(snapBox);

  // ---- packages: uncompressed installed size ---------------------------
  const pkgBox = el('div', { class: 'contrib__block' });
  pkgBox.append(
    el('h5', {}, [
      'Packages',
      el('span', { class: 'pill', text: 'uncompressed installed size · measured' }),
      el('span', { class: 'pill', text: deltaKB(at.installedKBDelta) }),
    ])
  );

  if (!at.havePkgMeta) {
    pkgBox.append(
      el('p', {
        class: 'warn',
        text: 'Package metadata is not available for this series/architecture, so per-package sizes are unknown (not zero).',
      })
    );
  } else {
    pkgBox.append(
      barTable(
        at.pkgRows,
        (r) => r.kb,
        (r) => deltaKB(r.kb),
        onWhy
      )
    );
    if (at.sourceRows.length) {
      pkgBox.append(el('h5', { text: 'Rolled up by source package' }));
      pkgBox.append(
        barTable(
          at.sourceRows.map((r) => ({
            ref: `src:${r.source}`,
            name: r.source,
            kind: 'source',
            change: `${r.count} binar${r.count === 1 ? 'y' : 'ies'}`,
            detail: '',
            kb: r.kb,
          })),
          (r) => r.kb,
          (r) => deltaKB(r.kb)
        )
      );
    }
    if (at.unresolvedPackages) {
      pkgBox.append(
        el('p', {
          class: 'note',
          text: `${num(at.unresolvedPackages)} changed packages could not be resolved in the archive index; their size is unknown rather than zero.`,
        })
      );
    }
  }
  root.append(pkgBox);

  // ---- the honest gap ---------------------------------------------------
  root.append(
    el('p', { class: 'note', style: { marginTop: '10px' } }, [
      `Totals: installed size ${bytesFromKB(at.installedFromTotal)} → ${bytesFromKB(at.installedToTotal)} uncompressed; ` +
        `seeded snaps ${deltaBytes(at.snapDelta)} compressed. ` +
        'The image is squashfs-compressed, so an installed-size change does not transfer 1:1 to the ISO. ' +
        'This project measures the compression ratio nowhere, so it does not claim one.',
    ])
  );
}

function barTable(rows, valueOf, formatOf, onWhy) {
  const table = el('table', { class: 'data' });
  table.append(
    el('thead', {}, [
      el('tr', {}, [
        el('th', { text: 'Contributor' }),
        el('th', { text: 'Change' }),
        el('th', { class: 'num', text: 'Delta' }),
        el('th', { text: '', style: { width: '170px' } }),
      ]),
    ])
  );
  const maxAbs = Math.max(...rows.map((r) => Math.abs(valueOf(r))), 1);
  const tb = el('tbody');
  for (const r of rows) {
    const v = valueOf(r);
    const bar = el('div', { class: 'dbar' });
    bar.append(el('div', { class: 'dbar__zero', style: { left: '50%' } }));
    const fill = el('div', { class: `dbar__fill dbar__fill--${v > 0 ? 'pos' : 'neg'}` });
    fill.style.width = ((Math.abs(v) / maxAbs) * 50).toFixed(2) + '%';
    if (v > 0) fill.style.left = '50%';
    else fill.style.right = '50%';
    bar.append(fill);

    const nameCell = el('td');
    if (onWhy && r.kind === 'pkg') {
      nameCell.append(
        el('button', {
          class: 'row-btn',
          type: 'button',
          text: r.name,
          title: 'Why is this package in the image?',
          onclick: () => onWhy(r.name),
        })
      );
    } else {
      nameCell.append(el('strong', { text: r.name }));
    }
    if (r.kind) nameCell.append(el('span', { class: 'pill', text: r.kind }));

    tb.append(
      el('tr', { dataset: { ref: r.ref } }, [
        nameCell,
        el('td', { text: [r.change, r.detail].filter(Boolean).join(' · ') }),
        el('td', { class: 'num', text: formatOf(r) }),
        el('td', {}, [bar]),
      ])
    );
  }
  table.append(tb);
  return table;
}

/** Render a dependency path explaining why a package is present. */
export function renderWhy(root, name, why) {
  clear(root);
  if (!why) {
    root.append(
      el('p', {
        class: 'note',
        text: `No dependency path to a seeded package was found for ${name} in this image. The data does not establish why it is present.`,
      })
    );
    return;
  }
  root.append(el('h5', { text: `Why is ${name} in this image?` }));
  const chain = el('div', { class: 'why' });
  why.chain.forEach((node, i) => {
    if (i) chain.append(el('span', { class: 'why__arrow', text: '↓' }));
    chain.append(el('code', { class: 'why__node', text: node }));
  });
  root.append(chain);
  root.append(
    el('p', {
      class: 'note',
      text: `Root (${why.chain[0]}) is seeded by ${why.rootReason}. Path derived from Depends/Recommends in the archive index, restricted to packages present in this image.`,
    })
  );
}

function list(title, items, render, filter) {
  const filtered = filter
    ? items.filter((i) => i.name.toLowerCase().includes(filter))
    : items;
  const box = el('div', { class: 'changelist' });
  box.append(
    el('h4', {}, [title, el('span', { class: 'pill', text: String(filtered.length) })])
  );
  if (!filtered.length) {
    box.append(el('div', { class: 'note', text: '—' }));
    return box;
  }
  const scroller = el('div', { class: 'scroller' });
  const table = el('table', { class: 'data' });
  const tb = el('tbody');
  for (const item of filtered.slice(0, 500)) tb.append(render(item));
  table.append(tb);
  scroller.append(table);
  box.append(scroller);
  if (filtered.length > 500) {
    box.append(el('div', { class: 'note', text: `showing first 500 of ${filtered.length}` }));
  }
  return box;
}

export function renderChangeLists(root, s, filter) {
  clear(root);
  if (!s) return;
  const f = (filter || '').trim().toLowerCase();
  const d = s.diff;

  root.append(
    list('Packages added', d.added, (i) =>
      el('tr', {}, [el('td', { text: i.name }), el('td', { class: 'num', text: i.version })]), f)
  );
  root.append(
    list('Packages removed', d.removed, (i) =>
      el('tr', {}, [el('td', { text: i.name }), el('td', { class: 'num', text: i.version })]), f)
  );
  root.append(
    list('Packages changed', d.changed, (i) =>
      el('tr', {}, [
        el('td', { text: i.name }),
        el('td', { class: 'num', text: `${i.from} → ${i.to}` }),
      ]), f)
  );
  root.append(
    list('Snaps added', d.snapAdded, (i) =>
      el('tr', {}, [
        el('td', { text: i.name }),
        el('td', { class: 'num', text: `${i.channel} r${i.rev}` }),
        el('td', { class: 'num', text: bytes(i.bytes) }),
      ]), f)
  );
  root.append(
    list('Snaps removed', d.snapRemoved, (i) =>
      el('tr', {}, [
        el('td', { text: i.name }),
        el('td', { class: 'num', text: `${i.channel} r${i.rev}` }),
        el('td', { class: 'num', text: bytes(i.bytes) }),
      ]), f)
  );
  root.append(
    list('Snaps changed', d.snapChanged, (i) =>
      el('tr', {}, [
        el('td', { text: i.name }),
        el('td', { class: 'num', text: `r${i.fromRev} → r${i.toRev}` }),
        el('td', { class: 'num', text: deltaBytes(i.deltaBytes) }),
      ]), f)
  );
}
