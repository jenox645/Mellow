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
  // 0 is a time ("0:00", a chapter's start); only a missing value is blank
  if (s === null || s === undefined || s === '' || isNaN(s)) return '';
  s = Math.floor(s);
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


// "90", "1:30" or "1:01:30" → seconds; null when unreadable
export function parseClock(s) {
  const t = String(s || '').trim();
  if (!t) return null;
  if (!/^\d+(\.\d+)?$|^\d+:\d{1,2}(\.\d+)?$|^\d+:\d{1,2}:\d{1,2}(\.\d+)?$/.test(t)) return null;
  return t.split(':').reduce((acc, part) => acc * 60 + parseFloat(part), 0);
}

// Rough output size of a single-video download, from /api/info's
// size_estimates (what yt-dlp would fetch). Converted audio is sized by its
// bitrate; lossless targets by their typical rate. Scaled down for a clip.
// null when the site gave nothing to go on.
export function estimateDownloadBytes(info, { mode, quality, audioFmt, audioQuality, startTime, endTime, chapters }) {
  const est = info && info.size_estimates;
  if (!est) return null;
  const duration = info.duration || 0;
  let bytes;
  if (mode === 'audio') {
    const kbps = audioFmt === 'wav' ? 1411 : audioFmt === 'flac' ? 900 : parseInt(audioQuality, 10);
    bytes = kbps && duration ? duration * kbps * 125 : est.audio;
  } else {
    bytes = est.video && est.video[quality];
  }
  if (!bytes) return null;
  if (duration && chapters && chapters.length) {
    // Only the chosen chapters are downloaded (clip start/end is ignored then)
    const span = chapters.reduce((t, c) => t + Math.max(0, c.end - c.start), 0);
    return span ? bytes * Math.min(span, duration) / duration : bytes;
  }
  const start = parseClock(startTime), end = parseClock(endTime);
  if (duration && (start !== null || end !== null)) {
    const span = Math.min(end !== null ? end : duration, duration) - Math.max(start || 0, 0);
    if (span > 0) bytes = bytes * span / duration;
  }
  return bytes;
}

// A canvas can't resolve CSS variables: read the current layout's value
export function cssVar(name, fallback) {
  const v = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

// Canvas font for a Classic pixel size (7–12 scale with the layout's --fs-*)
export function canvasFont(px, { weight = '', family = '--font-mono' } = {}) {
  const size = px >= 7 && px <= 12 ? cssVar('--fs-' + px, px + 'px') : px + 'px';
  return (weight ? weight + ' ' : '') + size + ' ' + cssVar(family, 'monospace');
}
