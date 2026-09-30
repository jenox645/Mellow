// Shared formatting helpers.
'use strict';

export function fmtBytes(b) {
  if (!b && b !== 0) return '—';
  if (b === 0) return '0 B';
  const k = 1024, sizes = ['B','KB','MB','GB','TB'];
  const i = Math.min(Math.floor(Math.log(Math.max(b,1)) / Math.log(k)), 4);
  return (b / Math.pow(k, i)).toFixed(i > 1 ? 1 : 0) + ' ' + sizes[i];
}

export function fmtSpeed(bps) {
  if (!bps) return '0 B/s';
  return fmtBytes(bps) + '/s';
}

export function fmtEta(s) {
  if (!s || s < 0) return '--';
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60), sec = s % 60;
  if (m < 60) return m + ':' + String(sec).padStart(2, '0');
  const h = Math.floor(m / 60);
  return h + ':' + String(m % 60).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
}

export function fmtDuration(s) {
  if (!s) return '';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
  return m + ':' + String(sec).padStart(2, '0');
}

export function fmtDate(ts) {
  if (!ts) return '—';
  try { return new Date(ts).toLocaleDateString(); } catch { return ts; }
}

export function fmtTimestamp(ts) {
  if (!ts) return '—';
  try { return new Date(ts).toLocaleString(); } catch { return ts; }
}

export function timeAgo(ts) {
  if (!ts) return '';
  try {
    const diff = Date.now() - new Date(ts).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return m + 'm ago';
    const h = Math.floor(m / 60);
    if (h < 24) return h + 'h ago';
    return Math.floor(h / 24) + 'd ago';
  } catch { return ''; }
}

export function platformTagClass(platform) {
  if (!platform) return 'platform-tag default';
  const p = platform.toLowerCase();
  if (p.includes('youtube')) return 'platform-tag youtube';
  if (p.includes('soundcloud')) return 'platform-tag soundcloud';
  return 'platform-tag default';
}

