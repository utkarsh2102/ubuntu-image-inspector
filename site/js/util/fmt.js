/** Formatting helpers. All output is inserted via textContent, never innerHTML. */

export function bytes(n) {
  if (typeof n !== 'number' || !isFinite(n)) return '—';
  const neg = n < 0;
  let v = Math.abs(n);
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  const s = v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1);
  return `${neg ? '-' : ''}${s} ${units[i]}`;
}

export function deltaBytes(n) {
  if (typeof n !== 'number' || !isFinite(n)) return '—';
  return (n > 0 ? '+' : '') + bytes(n);
}

export function deltaNum(n) {
  if (typeof n !== 'number' || !isFinite(n)) return '—';
  return (n > 0 ? '+' : '') + n.toLocaleString();
}

export function num(n) {
  return typeof n === 'number' && isFinite(n) ? n.toLocaleString() : '—';
}

export function pct(n) {
  if (typeof n !== 'number' || !isFinite(n)) return '—';
  return `${n > 0 ? '+' : ''}${(n * 100).toFixed(1)}%`;
}

export function shortDate(iso) {
  if (!iso) return '—';
  return iso.slice(0, 10);
}

export function metricValue(metricId, row) {
  switch (metricId) {
    case 'bytes':
      return row.bytes;
    case 'pkgs':
      return row.pkgs;
    case 'snaps':
      return row.snaps;
    case 'snapBytes':
      return row.snapBytes;
    default:
      return row[metricId];
  }
}

export function formatMetric(metricId, v) {
  if (v === null || v === undefined) return '—';
  return metricId === 'bytes' || metricId === 'snapBytes' ? bytes(v) : num(v);
}
