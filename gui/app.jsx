/* @jsxRuntime classic */
/* @jsx React.createElement */
/* @jsxFrag React.Fragment */
/* global React, ReactDOM, MASCOT_DJ, MASCOT_VIBING, MASCOT_CHILLING, MASCOT_FRUSTRATED, MASCOT_TIRED, MASCOT_COMFY, MASCOT_SUCCESS, MASCOT_TROUBLESHOOTING, MASCOT_VICTORY */
'use strict';

// Safe refs for optional mascots (defined by build_setup.py; may be absent in dev)
const _g = typeof globalThis !== 'undefined' ? globalThis : window;
const _mc = (name) => (typeof _g[name] !== 'undefined' ? _g[name] : null);
const MASCOT_COMFY_SAFE          = _mc('MASCOT_COMFY');
const MASCOT_SUCCESS_SAFE        = _mc('MASCOT_SUCCESS');
const MASCOT_TROUBLESHOOTING_SAFE = _mc('MASCOT_TROUBLESHOOTING');
const MASCOT_VICTORY_SAFE        = _mc('MASCOT_VICTORY');

// ── Utilities ────────────────────────────────────────────────────────────────

function fmtBytes(b) {
  if (!b && b !== 0) return '—';
  if (b === 0) return '0 B';
  const k = 1024, sizes = ['B','KB','MB','GB','TB'];
  const i = Math.min(Math.floor(Math.log(Math.max(b,1)) / Math.log(k)), 4);
  return (b / Math.pow(k, i)).toFixed(i > 1 ? 1 : 0) + ' ' + sizes[i];
}

function fmtSpeed(bps) {
  if (!bps) return '0 B/s';
  return fmtBytes(bps) + '/s';
}

function fmtEta(s) {
  if (!s || s < 0) return '--';
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60), sec = s % 60;
  if (m < 60) return m + ':' + String(sec).padStart(2, '0');
  const h = Math.floor(m / 60);
  return h + ':' + String(m % 60).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
}

function fmtDuration(s) {
  if (!s) return '';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
  return m + ':' + String(sec).padStart(2, '0');
}

function fmtDate(ts) {
  if (!ts) return '—';
  try { return new Date(ts).toLocaleDateString(); } catch { return ts; }
}

function fmtTimestamp(ts) {
  if (!ts) return '—';
  try { return new Date(ts).toLocaleString(); } catch { return ts; }
}

function timeAgo(ts) {
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

function platformTagClass(platform) {
  if (!platform) return 'platform-tag default';
  const p = platform.toLowerCase();
  if (p.includes('youtube')) return 'platform-tag youtube';
  if (p.includes('soundcloud')) return 'platform-tag soundcloud';
  return 'platform-tag default';
}

// ── API ──────────────────────────────────────────────────────────────────────

const API = {
  get: (url) => fetch(url).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),
  post: (url, body) => fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(r => r.json()),
  put: (url, body) => fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(r => r.json()),
  del: (url, body) => fetch(url, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  }).then(r => r.json()),
};

// ── SVG Icons ────────────────────────────────────────────────────────────────

const SVG = {
  feed: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
  queue: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
  vault: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/></svg>',
  analytics: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  signal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15"><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/></svg>',
  config: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
  folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
  sync: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="11" height="11"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  chevron_down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><polyline points="6 9 12 15 18 9"/></svg>',
  chevron_right: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><polyline points="9 18 15 12 9 6"/></svg>',
  dots: '<svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  db: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
  external: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
};

function Ico({ name, size }) {
  const raw = SVG[name] || '';
  if (!raw) return null;
  const html = size
    ? raw.replace(/width="\d+"/, `width="${size}"`).replace(/height="\d+"/, `height="${size}"`)
    : raw;
  return (
    <span
      dangerouslySetInnerHTML={{ __html: html }}
      style={{ display: 'inline-flex', alignItems: 'center', lineHeight: 0 }}
    />
  );
}

// ── Toggle ────────────────────────────────────────────────────────────────────

function Toggle({ checked, onChange }) {
  return (
    <div
      className={'toggle' + (checked ? ' on' : '')}
      onClick={() => onChange(!checked)}
    />
  );
}

// ── Mascot ─────────────────────────────────────────────────────────────────────
// Handles both inline-SVG strings and data-URI PNGs from mascots.js

function Mascot({ src, className, style, wrapClass }) {
  if (src && typeof src === 'string' && src.trimStart().startsWith('<svg')) {
    return (
      <div
        className={'mascot-wrap ' + (wrapClass || className || '')}
        style={style}
        dangerouslySetInnerHTML={{ __html: src }}
      />
    );
  }
  return <img src={src} className={className || 'mascot-img'} style={style} alt="" />;
}

// ── EditableStat ──────────────────────────────────────────────────────────────

function EditableStat({ value, colorClass, format, onSave }) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState('');
  const inputRef = React.useRef(null);

  const startEdit = () => {
    setDraft(String(value));
    setEditing(true);
  };

  React.useEffect(() => {
    if (editing && inputRef.current) inputRef.current.select();
  }, [editing]);

  const commit = () => {
    setEditing(false);
    if (onSave && draft !== String(value)) onSave(draft);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="stat-value-input"
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false); }}
      />
    );
  }

  return (
    <div
      className={'stat-value editable ' + (colorClass || '')}
      onClick={startEdit}
      title="Click to edit"
    >
      {format ? format(value) : value}
    </div>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────────────

function Modal({ title, onClose, children, footer }) {
  React.useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box">
        <div className="modal-hud" /><div className="modal-hud-br" />
        <div className="modal-header">
          <div className="modal-title">{title}</div>
          <div className="modal-close" onClick={onClose}><Ico name="x" size={14} /></div>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

// ── Notification ──────────────────────────────────────────────────────────────

function Notif({ notif, dismiss }) {
  if (!notif) return null;
  return (
    <div className={'notif ' + (notif.type || '')} onClick={dismiss} style={{ cursor: 'pointer' }}>
      <div className="notif-title">{notif.title}</div>
      <div className="notif-body">{notif.body}</div>
    </div>
  );
}

// ── Loading Screen ────────────────────────────────────────────────────────────

const LOADING_MIN_MS = 4500;

const _SPLASH_POOL = [
  MASCOT_DJ, MASCOT_VIBING, MASCOT_CHILLING, MASCOT_TIRED,
  MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE, MASCOT_TROUBLESHOOTING_SAFE, MASCOT_VICTORY_SAFE,
].filter(Boolean);

function LoadingScreen({ onReady }) {
  const [text, setText] = React.useState('');
  const [attempts, setAttempts] = React.useState(0);
  const serverReadyRef = React.useRef(false);
  const minElapsedRef = React.useRef(false);
  const TARGET = 'WELCOME, ADMINISTRATOR';
  const splashMascot = React.useRef(_SPLASH_POOL[Math.floor(Math.random() * _SPLASH_POOL.length)]).current;
  const isSvgSplash = typeof splashMascot === 'string' && splashMascot.trimStart().startsWith('<svg');
  const splashStyle = isSvgSplash
    ? { filter: 'drop-shadow(0 0 24px rgba(0,216,255,0.35))' }
    : { filter: 'sepia(1) saturate(6.7) hue-rotate(151deg) brightness(0.87) drop-shadow(0 0 24px rgba(0,216,255,0.35))', mixBlendMode: 'screen' };

  const tryReady = React.useCallback(() => {
    if (serverReadyRef.current && minElapsedRef.current) onReady();
  }, [onReady]);

  React.useEffect(() => {
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setText(TARGET.slice(0, i));
      if (i >= TARGET.length) clearInterval(timer);
    }, 60);
    return () => clearInterval(timer);
  }, []);

  // Minimum display duration — ensures animation completes
  React.useEffect(() => {
    const t = setTimeout(() => {
      minElapsedRef.current = true;
      tryReady();
    }, LOADING_MIN_MS);
    return () => clearTimeout(t);
  }, [tryReady]);

  // Server readiness check
  React.useEffect(() => {
    const tryConnect = () => {
      fetch('/api/system')
        .then(r => r.json())
        .then(() => {
          serverReadyRef.current = true;
          tryReady();
        })
        .catch(() => {
          setAttempts(a => {
            const next = a + 1;
            if (next < 5) setTimeout(tryConnect, 1200);
            else {
              serverReadyRef.current = true;
              tryReady();
            }
            return next;
          });
        });
    };
    const t = setTimeout(tryConnect, 600);
    return () => clearTimeout(t);
  }, [tryReady]);

  return (
    <div className="loading-screen">
      <Mascot src={splashMascot} className="loading-mascot" wrapClass="loading-mascot" style={splashStyle} />
      <div className="loading-title">{text}<span style={{ opacity: 0.5, animation: 'pulse 1s infinite' }}>_</span></div>
      <div className="loading-sub">MELLOW // DATA LAKE COMMANDER v2.0.0</div>
      <div className="loading-bar"><div className="loading-bar-fill" /></div>
      {attempts > 0 && (
        <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: '9px', color: 'var(--t4)' }}>
          CONNECTING... ATTEMPT {attempts}/5
        </div>
      )}
    </div>
  );
}

// ── Pipeline Stages ───────────────────────────────────────────────────────────

function Pipeline({ stage }) {
  const stages = ['FETCH', 'META', 'DOWNLOAD', 'MERGE', 'INDEX', 'WRITE DB'];
  const idx = { starting: 0, processing: 3, indexing: 4, done: 5 }[stage] ?? 2;

  const items = [];
  stages.forEach((label, i) => {
    const isDone = i < idx;
    const isActive = i === idx;
    items.push(<div key={'d' + i} className={'pl-dot' + (isDone ? ' done' : isActive ? ' active' : '')} />);
    if (i < stages.length - 1) {
      items.push(<div key={'l' + i} className={'pl-line' + (isDone ? ' done' : '')} />);
    }
    items.push(<span key={'lb' + i} className={'pl-label' + (isDone ? ' done' : isActive ? ' active' : '')}>{label}</span>);
    if (i < stages.length - 1) {
      items.push(<div key={'l2' + i} className={'pl-line' + (isDone ? ' done' : '')} />);
    }
  });

  return <div className="pipeline">{items}</div>;
}

// ── Mini Speed Graph (canvas) ─────────────────────────────────────────────────

function MiniGraph({ data, color, height = 28 }) {
  const canvasRef = React.useRef(null);

  React.useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = c.offsetWidth * dpr;
    c.height = height * dpr;
    const ctx = c.getContext('2d');
    ctx.scale(dpr, dpr);
    const w = c.offsetWidth, h = height;
    ctx.clearRect(0, 0, w, h);
    const pts = data && data.length > 0 ? data : Array(20).fill(0.2 + Math.random() * 0.3);
    const maxV = Math.max(...pts, 1);
    ctx.strokeStyle = color || 'rgba(0,216,255,0.6)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    pts.forEach((v, i) => {
      const x = (i / (pts.length - 1)) * w;
      const y = h - (v / maxV) * h * 0.85 - h * 0.05;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  }, [data, color, height]);

  return <canvas ref={canvasRef} style={{ width: '100%', height: height + 'px', display: 'block' }} />;
}

// ── Sidebar ────────────────────────────────────────────────────────────────────

function Sidebar({ page, setPage, appState, stats, speedHistory, sysInfo, vaultFolders, selectedVaultFolder, setSelectedVaultFolder, onAddVault }) {
  const canvasRef = React.useRef(null);

  React.useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    c.width = c.offsetWidth * (window.devicePixelRatio || 1);
    c.height = 28 * (window.devicePixelRatio || 1);
    const ctx = c.getContext('2d');
    const w = c.offsetWidth, h = 28;
    ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
    const pts = speedHistory.length ? speedHistory.slice(-20) : Array(20).fill(0);
    const maxV = Math.max(...pts, 1);
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = 'rgba(0,216,255,0.6)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    pts.forEach((v, i) => {
      const x = (i / (pts.length - 1)) * w;
      const y = h - (v / maxV) * h * 0.85 - h * 0.05;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  }, [speedHistory]);

  const CORE_PAGES = [
    { id: 'feed', label: 'FEED', num: '01', icon: 'feed' },
    { id: 'queue', label: 'QUEUE', num: '02', icon: 'queue' },
    { id: 'vault', label: 'VAULT', num: '03', icon: 'vault' },
  ];
  const LAKE_PAGES = [
    { id: 'analytics', label: 'ANALYTICS', num: '04', icon: 'analytics' },
    { id: 'signal', label: 'SIGNAL API', num: '05', icon: 'signal' },
    { id: 'config', label: 'CONFIG', num: '06', icon: 'config' },
  ];

  const PAGE_MASCOT = {
    feed:      MASCOT_VIBING,
    queue:     MASCOT_DJ,
    vault:     MASCOT_COMFY_SAFE || MASCOT_CHILLING,
    analytics: MASCOT_CHILLING,
    signal:    MASCOT_SUCCESS_SAFE || MASCOT_VIBING,
    config:    MASCOT_TROUBLESHOOTING_SAFE || MASCOT_VIBING,
  };
  const mascotSrc = PAGE_MASCOT[page] || MASCOT_VIBING;

  const LAKE_IDS = ['analytics', 'signal', 'config'];
  const isLakePage = LAKE_IDS.includes(page);
  const mascotAreaClass = 'mascot-area' + (isLakePage ? ' lake-color' : ' core-color');
  const hideMascot = page === 'vault' && vaultFolders.length > 3;

  const currentSpeed = speedHistory.length ? speedHistory[speedHistory.length - 1] : 0;

  return (
    <aside className="sidebar">
      <div className="logo-area">
        <div className="logo">
          <img src="assets/mellow.ico" className="logo-img" alt="M" onError={(e) => { e.target.style.display = 'none'; }} />
          <span className="logo-text">MELLOW</span>
        </div>
        <div className="logo-sub">SYSTEM // v1.0.0</div>
      </div>

      <nav className="nav">
        <div className="nav-section">CORE</div>
        {CORE_PAGES.map(p => (
          <div
            key={p.id}
            className={'nav-item' + (page === p.id ? ' active-core' : '')}
            onClick={() => setPage(p.id)}
          >
            <span className="nav-icon" dangerouslySetInnerHTML={{ __html: SVG[p.icon] }} />
            {p.label}
            <span className="nnum">{p.num}</span>
          </div>
        ))}
        <div className="nav-section">DATA LAKE</div>
        {LAKE_PAGES.map(p => (
          <div
            key={p.id}
            className={'nav-item' + (page === p.id ? ' active-lake' : '')}
            onClick={() => setPage(p.id)}
          >
            <span className="nav-icon" dangerouslySetInnerHTML={{ __html: SVG[p.icon] }} />
            {p.label}
            <span className="nnum">{p.num}</span>
          </div>
        ))}
      </nav>

      {page === 'vault' ? (
        <div className="vault-tree">
          <div className="vt-header">VAULT FOLDERS</div>
          {vaultFolders.map(f => (
            <div
              key={f.path}
              className={'vt-item' + (selectedVaultFolder === f.path ? ' active' : '')}
              onClick={() => setSelectedVaultFolder(f.path)}
            >
              <Ico name="folder" />
              <span className="vt-item-name">{f.name}</span>
              {f.watched && <span className="vt-watched">WATCH</span>}
              <span className="vt-badge">{f.item_count}</span>
            </div>
          ))}
          <div className="vt-add" onClick={onAddVault}>
            <Ico name="plus" /> Add Playlist...
          </div>
        </div>
      ) : (
        <div className={mascotAreaClass + (hideMascot ? ' hidden' : '')}>
          <Mascot key={page} src={mascotSrc} className="mascot-img" />
        </div>
      )}

      <div className="sys-panel">
        <div className="sys-title">SYS STATUS</div>
        <div className="sys-stat"><span>DL SPEED</span><span>{fmtSpeed(currentSpeed)}</span></div>
        <div className="sys-stat"><span>RECORDS</span><span>{(stats.total_downloads || 0).toLocaleString()}</span></div>
        <div className="sys-stat"><span>TOTAL DB</span><span>{fmtBytes(stats.total_size_bytes || 0)}</span></div>
        <div className="sys-stat"><span>LIBRARY</span><span>{stats.library_playlists || 0}</span></div>
        <div className="sys-online">
          <div className={'sdot' + (!sysInfo.ffmpeg ? ' warn' : appState === 'error' ? ' warn' : '')} />
          <div className="stext">
            {!sysInfo.ffmpeg ? 'FFMPEG MISSING' : appState === 'error' ? 'LAST DL FAILED' : 'ALL SYSTEMS NOMINAL'}
          </div>
        </div>
        <div className="mini-graph">
          <canvas ref={canvasRef} style={{ width: '100%', height: '28px' }} />
        </div>
      </div>
    </aside>
  );
}

// ── TopBar ────────────────────────────────────────────────────────────────────

const PAGE_META = {
  feed:      { path: 'COMMAND', ja: 'ダッシュボード', isLake: false },
  queue:     { path: 'QUEUE', ja: 'キュー管理', isLake: false },
  vault:     { path: 'VAULT', ja: 'メディアボールト', isLake: false },
  analytics: { path: 'ANALYTICS', ja: 'データレイク', isLake: true },
  signal:    { path: 'SIGNAL API', ja: 'APIシグナル', isLake: true },
  config:    { path: 'CONFIG', ja: 'システム設定', isLake: true },
};

function TopBar({ page }) {
  const [time, setTime] = React.useState('');
  const [date, setDate] = React.useState('');

  React.useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString('en-US', { hour12: false }));
      setDate(now.toLocaleDateString('en-CA'));
    };
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, []);

  const meta = PAGE_META[page] || PAGE_META.feed;
  const accClass = meta.isLake ? 'acc-a' : 'acc';

  return (
    <div className="topbar">
      <div className="topbar-path">
        MELLOW · <span className={accClass}>{meta.path}</span> · {meta.ja}
      </div>
      <div className="topbar-spacer" />
      <div className="topbar-time">{time}</div>
      <div className="topbar-tag">{date}</div>
      <div className="topbar-tag amber">ADMIN</div>
    </div>
  );
}

// ── Status Bar ────────────────────────────────────────────────────────────────

function StatusBar({ sysInfo, speedHistory, config }) {
  const canvasRef = React.useRef(null);

  React.useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const w = c.offsetWidth;
    if (!w) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = w * dpr;
    c.height = 16 * dpr;
    const ctx = c.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, 16);
    const pts = speedHistory.length ? speedHistory : Array(60).fill(0);
    const maxV = Math.max(...pts, 1);
    ctx.strokeStyle = 'rgba(249,169,0,0.7)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    pts.forEach((v, i) => {
      const x = (i / (pts.length - 1)) * w;
      const y = 16 - (v / maxV) * 14 - 1;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  }, [speedHistory]);

  const currentSpeed = speedHistory.length ? speedHistory[speedHistory.length - 1] : 0;
  const isActive = currentSpeed > 0;

  return (
    <div className="statusbar">
      <div className="sb-seg">
        <div className={'sb-dot' + (isActive ? ' ok' : ' warn')} />
        {isActive ? 'DOWNLOADING' : 'IDLE'}
      </div>
      <div className="sb-seg">
        yt-dlp {sysInfo.ytdlp_version || '—'}
      </div>
      <div className="sb-seg">
        <div className={'sb-dot' + (sysInfo.ffmpeg ? ' ok' : ' err')} />
        FFmpeg {sysInfo.ffmpeg ? 'OK' : 'MISSING'}
      </div>
      <div className="sb-graph">
        <canvas ref={canvasRef} />
      </div>
      <div className="sb-seg sb-path">
        {config.output_dir || '—'}
      </div>
    </div>
  );
}

// ── FEED Page ─────────────────────────────────────────────────────────────────

function FeedPage({ dlState, setDlState, setAppState, stats, refreshStats, showNotif, switchPage, config, onPlaylistDownload }) {
  const [url, setUrl] = React.useState(() => sessionStorage.getItem('feed_url') || '');
  const [analyzing, setAnalyzing] = React.useState(false);
  const [info, setInfo] = React.useState(null);
  const [optsOpen, setOptsOpen] = React.useState(false);
  const [advOpen, setAdvOpen] = React.useState(false);
  const [mode, setMode] = React.useState(() => sessionStorage.getItem('feed_mode') || 'video');
  const [quality, setQuality] = React.useState(() => sessionStorage.getItem('feed_quality') || '1080p');
  const [container, setContainer] = React.useState(() => sessionStorage.getItem('feed_container') || 'mp4');
  const [audioFmt, setAudioFmt] = React.useState('mp3');
  const [embedThumb, setEmbedThumb] = React.useState(true);
  const [embedSubs, setEmbedSubs] = React.useState(false);
  const [embedChapters, setEmbedChapters] = React.useState(true);
  const [embedMeta, setEmbedMeta] = React.useState(true);
  const [sponsorblock, setSponsorblock] = React.useState(false);
  const [startTime, setStartTime] = React.useState('');
  const [endTime, setEndTime] = React.useState('');
  const [customFmt, setCustomFmt] = React.useState('');
  const [downloadPath, setDownloadPath] = React.useState(() => sessionStorage.getItem('feed_downloadPath') || '');
  const [vaultModal, setVaultModal] = React.useState(false);

  React.useEffect(() => { sessionStorage.setItem('feed_url', url); }, [url]);
  React.useEffect(() => { sessionStorage.setItem('feed_mode', mode); }, [mode]);
  React.useEffect(() => { sessionStorage.setItem('feed_quality', quality); }, [quality]);
  React.useEffect(() => { sessionStorage.setItem('feed_container', container); }, [container]);
  React.useEffect(() => { sessionStorage.setItem('feed_downloadPath', downloadPath); }, [downloadPath]);
  const [vaultName, setVaultName] = React.useState('');
  const [vaultFolder, setVaultFolder] = React.useState('');

  const isDownloading = dlState && dlState.status !== 'complete' && dlState.status !== 'error';

  const handleAnalyze = React.useCallback(() => {
    if (!url.trim()) return;
    setAnalyzing(true);
    setInfo(null);
    API.post('/api/info', { url: url.trim() })
      .then(data => {
        if (data.error) { showNotif('Error', data.error, 'error'); return; }
        setInfo(data);
        if (data.is_playlist) { setMode('video'); }
      })
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setAnalyzing(false));
  }, [url, showNotif]);

  const handleDownload = React.useCallback(() => {
    if (!url.trim()) return;
    if (info && info.is_playlist && onPlaylistDownload) onPlaylistDownload();
    startDownload();
  }, [url, info, onPlaylistDownload, startDownload]);

  const browseDownloadPath = React.useCallback(() => {
    API.post('/api/browse-folder', {}).then(d => { if (d.path) setDownloadPath(d.path); }).catch(() => {});
  }, []);

  const startDownload = React.useCallback((extra) => {
    setVaultModal(false);
    API.post('/api/download', {
      url: url.trim(),
      mode,
      quality,
      container,
      audio_format: audioFmt,
      embed_thumbnail: embedThumb,
      embed_chapters: embedChapters,
      embed_metadata: embedMeta,
      embed_subs: embedSubs,
      sponsorblock,
      start_time: startTime,
      end_time: endTime,
      custom_format: customFmt,
      ...(downloadPath ? { output_dir: downloadPath } : {}),
      ...extra,
    }).then(d => {
      if (d.error) showNotif('Error', d.error, 'error');
    }).catch(e => showNotif('Error', e.message, 'error'));
  }, [url, mode, quality, container, audioFmt, embedThumb, embedChapters, embedMeta, embedSubs, sponsorblock, startTime, endTime, customFmt, downloadPath, showNotif]);

  const handleCancel = React.useCallback(() => {
    API.post('/api/cancel', {}).then(() => showNotif('Cancelled', 'Download cancelled'));
  }, [showNotif]);

  const handlePaste = React.useCallback(() => {
    API.get('/api/clipboard').then(d => {
      if (d.text) setUrl(d.text);
    }).catch(() => {});
  }, []);

  const browseVaultFolder = React.useCallback(() => {
    API.post('/api/browse-folder', {}).then(d => {
      if (d.path) setVaultFolder(d.path);
    }).catch(() => {});
  }, []);

  const confirmVaultDownload = React.useCallback(() => {
    if (vaultFolder && vaultName) {
      API.post('/api/library', {
        name: vaultName,
        url: url.trim(),
        folder: vaultFolder,
        folder_name: vaultName,
        quality,
        mode: mode.toUpperCase(),
        embed_thumbnail: embedThumb,
        embed_chapters: embedChapters,
        embed_metadata: embedMeta,
        embed_subs: embedSubs,
        sponsorblock,
      }).then(() => {
        startDownload({ mode: 'library' });
        showNotif('Added to VAULT', vaultName + ' saved to library');
      }).catch(() => startDownload());
    } else {
      startDownload();
    }
  }, [vaultFolder, vaultName, url, quality, mode, embedThumb, embedChapters, embedMeta, embedSubs, sponsorblock, startDownload, showNotif]);

  const pipelineStage = dlState
    ? dlState.status === 'processing' ? 'processing' : 'downloading'
    : 'done';

  const QUALITIES = ['best','4k','1080p','720p','480p','360p'];
  const CONTAINERS = ['mp4','mkv','webm'];
  const AUDIO_FMTS = ['mp3','aac','flac','m4a','opus','wav'];

  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">ダッシュボード / COMMAND FEED</div>
          <div className="vtitle"><span className="c">FEED</span> COMMAND</div>
        </div>
        <div className="vright">
          <div>USER // <span className="acc">ADMIN</span></div>
          <div>{new Date().toLocaleDateString()}</div>
        </div>
      </div>

      {/* URL INGEST PANEL */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-hud" /><div className="panel-hud-br" />
        <div className="ph">
          <span className="ptag">INGEST</span>
          <span className="ptitle">URL PASTE — URLを貼り付け</span>
          <span className="psub">PASTE URL HERE</span>
        </div>
        <div className="url-row">
          <div className="url-input-wrap">
            <input
              className="url-input"
              type="text"
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
              placeholder="https://www.youtube.com/watch?v=... or any supported platform URL"
            />
          </div>
          <button
            className={'btn btn-secondary btn-sm' + (optsOpen ? ' active-btn' : '')}
            onClick={() => setOptsOpen(o => !o)}
          >
            OPTIONS
          </button>
          {info ? (
            <button className="btn btn-primary" onClick={handleDownload} disabled={isDownloading}>
              {isDownloading ? 'ACTIVE...' : 'DOWNLOAD'}
            </button>
          ) : (
            <button className="btn btn-primary" onClick={handleAnalyze} disabled={analyzing}>
              {analyzing ? 'ANALYZING...' : 'ANALYZE →'}
            </button>
          )}
          <button className="btn btn-secondary btn-sm" onClick={handlePaste}>PASTE</button>
        </div>

        {/* OPTIONS PANEL */}
        <div className={'opts-panel' + (optsOpen ? ' open' : '')}>
          <div className="opts-inner">
            <div className="opts-tabs">
              <div className={'opts-tab' + (mode === 'video' ? ' active' : '')} onClick={() => setMode('video')}>VIDEO</div>
              <div className={'opts-tab' + (mode === 'audio' ? ' active' : '')} onClick={() => setMode('audio')}>AUDIO ONLY</div>
            </div>

            {mode === 'video' ? (
              <>
                <div className="opts-row">
                  <span className="opts-label">QUALITY</span>
                  <div className="pills">
                    {QUALITIES.map(q => (
                      <div key={q} className={'pill' + (quality === q ? ' active' : '')} onClick={() => setQuality(q)}>
                        {q.toUpperCase()}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="opts-row">
                  <span className="opts-label">CONTAINER</span>
                  <div className="pills">
                    {CONTAINERS.map(c => (
                      <div key={c} className={'pill' + (container === c ? ' active' : '')} onClick={() => setContainer(c)}>
                        {c.toUpperCase()}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="opts-row">
                <span className="opts-label">FORMAT</span>
                <div className="pills">
                  {AUDIO_FMTS.map(f => (
                    <div key={f} className={'pill' + (audioFmt === f ? ' active' : '')} onClick={() => setAudioFmt(f)}>
                      {f.toUpperCase()}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="opts-toggles">
              {[
                { label: 'Embed Thumbnail', val: embedThumb, set: setEmbedThumb },
                { label: 'Subtitles', val: embedSubs, set: setEmbedSubs },
                { label: 'Chapters', val: embedChapters, set: setEmbedChapters },
                { label: 'Metadata', val: embedMeta, set: setEmbedMeta },
                { label: 'SponsorBlock', val: sponsorblock, set: setSponsorblock },
              ].map(item => (
                <label key={item.label} className="opts-toggle-item">
                  <input type="checkbox" checked={item.val} onChange={e => item.set(e.target.checked)} />
                  {item.label}
                </label>
              ))}
            </div>

            <div className="opts-advanced">
              <div className="opts-adv-toggle" onClick={() => setAdvOpen(o => !o)}>
                <span dangerouslySetInnerHTML={{ __html: advOpen ? SVG.chevron_down : SVG.chevron_right }} />
                ADVANCED OPTIONS
              </div>
              <div className={'opts-adv-body' + (advOpen ? ' open' : '')}>
                <div className="opts-adv-grid">
                  <div>
                    <div className="inp-label">CLIP START (HH:MM:SS)</div>
                    <input className="inp-sm" value={startTime} onChange={e => setStartTime(e.target.value)} placeholder="00:01:30" />
                  </div>
                  <div>
                    <div className="inp-label">CLIP END (HH:MM:SS)</div>
                    <input className="inp-sm" value={endTime} onChange={e => setEndTime(e.target.value)} placeholder="00:03:00" />
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <div className="inp-label">CUSTOM FORMAT STRING</div>
                    <input className="inp-sm" value={customFmt} onChange={e => setCustomFmt(e.target.value)} placeholder="bv[height<=1080]+ba/best" />
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <div className="inp-label">TARGET FOLDER <span style={{ color: 'var(--t4)', fontSize: 7 }}>(OVERRIDE — empty uses Config default)</span></div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <input className="inp-sm" style={{ flex: 1 }} value={downloadPath} onChange={e => setDownloadPath(e.target.value)} placeholder={config.output_dir || 'Default from Config'} />
                      <button className="btn btn-secondary btn-sm" onClick={browseDownloadPath}>BROWSE</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* INFO CARD */}
        <div className={'info-card' + (info ? ' open' : '')}>
          {info && (
            <div className="info-inner">
              {info.thumbnail
                ? <img src={info.thumbnail} className="info-thumb" alt="" />
                : <div className="info-thumb-ph">▶</div>
              }
              <div className="info-details">
                <div className="info-title">{info.title || 'Unknown Title'}</div>
                <div className="info-meta">
                  {info.uploader && <span>{info.uploader}</span>}
                  {info.platform && <span>{info.platform}</span>}
                  {info.duration && <span>{fmtDuration(info.duration)}</span>}
                  {info.is_playlist && <span>{info.playlist_count} items</span>}
                </div>
                <div className="info-tags">
                  <span className="tag cyan">{info.platform || 'URL'}</span>
                  {info.is_playlist && <span className="tag amber">PLAYLIST</span>}
                  {mode === 'video' ? <span className="tag">{quality.toUpperCase()}</span> : <span className="tag amber">{audioFmt.toUpperCase()}</span>}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ACTIVE DOWNLOAD PANEL */}
      <div className={'dl-panel panel' + (isDownloading ? ' open' : '')} style={{ marginBottom: 16 }}>
        <div className="panel-hud" /><div className="panel-hud-br" />
        <div className="ph">
          <span className="ptag">ACTIVE</span>
          <span className="ptitle">NOW PROCESSING — 処理中</span>
          <span className="psub">1 / 1 ACTIVE</span>
        </div>
        {dlState && (
          <>
            <div className="dl-card">
              <div className="dl-inner">
                {info && info.thumbnail
                  ? <img src={info.thumbnail} className="dl-thumb" alt="" />
                  : <div className="dl-thumb-ph">▶</div>
                }
                <div className="dl-info">
                  <div className="dl-title">{info && info.title || dlState.filename || 'Downloading...'}</div>
                  <div className="dl-ch">{[info && info.uploader, info && info.platform, info && info.duration ? fmtDuration(info.duration) : null].filter(Boolean).join(' · ')}</div>
                  <div className="dl-tags">
                    <span className="tag cyan">{mode === 'audio' ? audioFmt.toUpperCase() : container.toUpperCase()}</span>
                    {mode !== 'audio' && <span className="tag">{quality.toUpperCase()}</span>}
                    {sponsorblock && <span className="tag green">SPONSORBLOCK</span>}
                  </div>
                  <div className="prog-row">
                    <div className="prog-bar">
                      <div className="prog-bar-fill" style={{ width: (dlState.pct || 0) + '%' }} />
                    </div>
                    <span className="prog-pct">{(dlState.pct || 0).toFixed(1)}%</span>
                  </div>
                  <div className="dl-meta">
                    <span>{fmtBytes(dlState.downloaded)} / <span className="acc">{fmtBytes(dlState.total)}</span></span>
                    <span>↓ <span className="acc">{fmtSpeed(dlState.speed)}</span></span>
                    <span>ETA <span className="acc">{fmtEta(dlState.eta)}</span></span>
                  </div>
                </div>
                <div className="dl-side">
                  <div className="dl-side-title">DETAILS — 詳細</div>
                  <div className="dl-kv"><span className="k">FORMAT</span><span className="v">{mode === 'audio' ? audioFmt.toUpperCase() : container.toUpperCase()}</span></div>
                  <div className="dl-kv"><span className="k">QUALITY</span><span className="v">{quality.toUpperCase()}</span></div>
                  <div className="dl-kv"><span className="k">PLATFORM</span><span className="v">{info && info.platform || '—'}</span></div>
                  <div className="dl-kv"><span className="k">SIZE</span><span className="v">{fmtBytes(dlState.total)}</span></div>
                  <div style={{ marginTop: 10, display: 'flex', gap: 6 }}>
                    <button className="btn btn-danger btn-sm" style={{ flex: 1 }} onClick={handleCancel}>
                      CANCEL
                    </button>
                  </div>
                </div>
              </div>
            </div>
            <Pipeline stage={pipelineStage} />
          </>
        )}
      </div>

      {/* QUEUE PREVIEW + STATS */}
      <div className="g2">
        <div className="panel">
          <div className="panel-hud" /><div className="panel-hud-br" />
          <div className="ph">
            <span className="ptag">QUEUE</span>
            <span className="ptitle">WAITING — 待機中</span>
            <span className="psub">EMPTY</span>
          </div>
          <div className="empty-state" style={{ padding: '24px' }}>
            <Mascot src={MASCOT_CHILLING} className="empty-mascot" wrapClass="empty-mascot-wrap" />
            <div className="empty-title">QUEUE EMPTY</div>
            <div className="empty-sub" onClick={() => switchPage('queue')}>VIEW QUEUE →</div>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="g2" style={{ marginBottom: 0 }}>
            <div className="stat">
              <div className="stat-label">TOTAL RECORDS</div>
              <div className="stat-value cyan">{(stats.total_downloads || 0).toLocaleString()}</div>
              <div className="stat-sub">all time</div>
            </div>
            <div className="stat">
              <div className="stat-label">STORAGE USED</div>
              <div className="stat-value amber">{fmtBytes(stats.total_size_bytes || 0)}</div>
              <div className="stat-sub">total size</div>
            </div>
          </div>
          <div className="g2" style={{ marginBottom: 0 }}>
            <div className="stat">
              <div className="stat-label">PLATFORMS</div>
              <div className="stat-value green">{(stats.by_platform || []).length}</div>
              <div className="stat-sub">distinct sources</div>
            </div>
            <div className="stat">
              <div className="stat-label">LIBRARY</div>
              <div className="stat-value cyan">{stats.library_playlists || 0}</div>
              <div className="stat-sub">playlists tracked</div>
            </div>
          </div>
        </div>
      </div>

      {/* VAULT MODAL */}
      {vaultModal && (
        <Modal
          title="ADD TO VAULT"
          onClose={() => setVaultModal(false)}
          footer={
            <>
              <button className="btn btn-secondary btn-sm" onClick={() => { setVaultModal(false); startDownload(); }}>JUST DOWNLOAD ONCE</button>
              <button className="btn btn-primary btn-sm" onClick={confirmVaultDownload}>SAVE TO VAULT AND DOWNLOAD</button>
            </>
          }
        >
          <div className="form-row">
            <div className="form-label">PLAYLIST NAME</div>
            <input className="form-input" value={vaultName} onChange={e => setVaultName(e.target.value)} />
          </div>
          <div className="form-row">
            <div className="form-label">SAVE FOLDER</div>
            <div className="input-row">
              <input className="form-input" value={vaultFolder} onChange={e => setVaultFolder(e.target.value)} placeholder="C:\Users\..." />
              <button className="btn btn-secondary btn-sm" onClick={browseVaultFolder}>BROWSE</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── QUEUE Page ────────────────────────────────────────────────────────────────

function QueuePage({ dlState, showNotif }) {
  const isDownloading = dlState && dlState.pct !== undefined;

  const handleCancel = () => {
    API.post('/api/cancel', {}).then(() => showNotif('Cancelled', 'Download stopped'));
  };

  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">キュー / DOWNLOAD QUEUE</div>
          <div className="vtitle">QUEUE <span className="c">CONTROL</span></div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <button className="btn btn-secondary btn-sm">IMPORT BATCH</button>
        </div>
      </div>

      <div className="g4" style={{ marginBottom: 16 }}>
        <div className="stat"><div className="stat-label">ACTIVE</div><div className="stat-value amber">{isDownloading ? 1 : 0}</div></div>
        <div className="stat"><div className="stat-label">QUEUED</div><div className="stat-value cyan">0</div></div>
        <div className="stat"><div className="stat-label">PAUSED</div><div className="stat-value" style={{ color: 'var(--purple)' }}>0</div></div>
        <div className="stat"><div className="stat-label">FAILED</div><div className="stat-value red">0</div></div>
      </div>

      {isDownloading ? (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="panel-hud" /><div className="panel-hud-br" />
          <div className="ph">
            <span className="ptag">ACTIVE</span>
            <span className="ptitle">NOW DOWNLOADING</span>
            <span className="psub" style={{ color: 'var(--cyan)' }}>{(dlState.pct || 0).toFixed(1)}% COMPLETE</span>
          </div>
          <div className="q-item row-active">
            <span className="q-drag">⋮⋮</span>
            <div className="q-thumb-ph">▶</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="q-name" style={{ marginBottom: 4 }}>{dlState.filename || 'Downloading...'}</div>
              <div className="prog-bar" style={{ height: 4 }}>
                <div className="prog-bar-fill" style={{ width: (dlState.pct || 0) + '%' }} />
              </div>
            </div>
            <span className="q-size">{fmtBytes(dlState.total)}</span>
            <div className="q-status"><span className="q-st-badge downloading">ACTIVE</span></div>
            <div className="q-del" onClick={handleCancel}>
              <Ico name="x" />
            </div>
          </div>
          <div style={{ padding: '8px 14px', borderTop: '1px solid var(--border)', display: 'flex', gap: 12, fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t3)' }}>
            <span>↓ <span style={{ color: 'var(--cyan)' }}>{fmtSpeed(dlState.speed)}</span></span>
            <span>ETA <span style={{ color: 'var(--cyan)' }}>{fmtEta(dlState.eta)}</span></span>
            <span>{fmtBytes(dlState.downloaded)} / {fmtBytes(dlState.total)}</span>
          </div>
        </div>
      ) : null}

      <div className="panel">
        <div className="panel-hud" /><div className="panel-hud-br" />
        <div className="ph">
          <span className="ptag">QUEUE</span>
          <span className="ptitle">PENDING DOWNLOADS — 待機中</span>
        </div>
        <div className="empty-state">
          <Mascot src={MASCOT_VIBING} className="empty-mascot" wrapClass="empty-mascot-wrap" />
          <div className="empty-title">QUEUE EMPTY</div>
          <div className="empty-sub">Paste a URL in FEED to start downloading</div>
        </div>
      </div>
    </div>
  );
}

// ── VAULT Page ────────────────────────────────────────────────────────────────

function VaultPage({ vaultFolders, selectedFolder, setSelectedFolder, config, showNotif, onAddVault, onRefreshVault }) {
  const [files, setFiles] = React.useState([]);
  const [folderInfo, setFolderInfo] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [ctxMenu, setCtxMenu] = React.useState(null);
  const [libraryEntries, setLibraryEntries] = React.useState([]);
  const [syncingId, setSyncingId] = React.useState(null);
  const [deleteConfirm, setDeleteConfirm] = React.useState(null);

  React.useEffect(() => {
    API.get('/api/library').then(setLibraryEntries).catch(() => {});
  }, []);

  React.useEffect(() => {
    if (!selectedFolder) return;
    setLoading(true);
    API.get('/api/vault/folder?path=' + encodeURIComponent(selectedFolder))
      .then(d => { setFiles(d.files || []); setFolderInfo(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedFolder]);

  const folderEntry = libraryEntries.find(e => e.folder_name && selectedFolder && selectedFolder.endsWith(e.folder_name));

  const handleSync = React.useCallback(() => {
    if (!folderEntry) return;
    setSyncingId(folderEntry.id);
    API.post('/api/library/' + folderEntry.id + '/sync', { mode: folderEntry.sync_mode || 'add' })
      .then(() => showNotif('Sync started', folderEntry.name))
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setSyncingId(null));
  }, [folderEntry, showNotif]);

  const handleOpenFile = React.useCallback((path) => {
    API.post('/api/vault/open-file', { path }).catch(() => {});
  }, []);

  const handleOpenFolder = React.useCallback((path) => {
    API.post('/api/open-folder', { path }).catch(() => {});
  }, []);

  const handleDeleteFile = React.useCallback((file) => {
    setDeleteConfirm(file);
    setCtxMenu(null);
  }, []);

  const confirmDelete = React.useCallback(() => {
    if (!deleteConfirm) return;
    API.del('/api/vault/file', { path: deleteConfirm.path })
      .then(() => {
        setFiles(f => f.filter(x => x.path !== deleteConfirm.path));
        showNotif('Deleted', deleteConfirm.name);
      })
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setDeleteConfirm(null));
  }, [deleteConfirm, showNotif]);

  const isVideoExt = (ext) => ['mp4','mkv','webm','avi','mov'].includes(ext);

  React.useEffect(() => {
    const close = () => setCtxMenu(null);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, []);

  const handleWatchFolder = React.useCallback(() => {
    API.post('/api/browse-folder', {}).then(d => {
      if (!d.path) return;
      API.post('/api/vault/watch', { path: d.path })
        .then(() => {
          showNotif('Watch Folder Added', d.path.split(/[\\/]/).pop(), 'success');
          onRefreshVault && onRefreshVault();
        })
        .catch(e => showNotif('Error', e.message, 'error'));
    }).catch(() => {});
  }, [showNotif, onRefreshVault]);

  const handleUnwatchFolder = React.useCallback((folderPath) => {
    API.del('/api/vault/watch', { path: folderPath })
      .then(() => { onRefreshVault && onRefreshVault(); })
      .catch(() => {});
  }, [onRefreshVault]);

  if (!selectedFolder) {
    return (
      <div className="content active">
        <div className="vhead">
          <div>
            <div className="vlabel">メディアボールト / MEDIA VAULT</div>
            <div className="vtitle">VAULT <span className="c">BROWSER</span></div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <button className="btn btn-secondary btn-sm" onClick={handleWatchFolder}>
              <Ico name="folder" /> WATCH FOLDER
            </button>
            <button className="btn btn-primary btn-sm" onClick={onAddVault}>ADD PLAYLIST</button>
          </div>
        </div>
        <div className="empty-state">
          <Mascot src={MASCOT_COMFY_SAFE || MASCOT_CHILLING} className="empty-mascot" wrapClass="empty-mascot-wrap" />
          <div className="empty-title">SELECT A FOLDER</div>
          <div className="empty-sub">Choose a folder from the sidebar tree or add one above</div>
        </div>
      </div>
    );
  }

  const folderName = selectedFolder.split(/[\\/]/).pop();

  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">メディアボールト / {folderName.toUpperCase()}</div>
          <div className="vtitle">VAULT <span className="c">{folderName.toUpperCase().slice(0, 16)}</span></div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          {folderEntry && (
            <button
              className="btn btn-amber btn-sm"
              onClick={handleSync}
              disabled={!!syncingId}
            >
              {syncingId ? 'SYNCING...' : (
                <><Ico name="sync" /> SYNC NOW</>
              )}
            </button>
          )}
          <button className="btn btn-secondary btn-sm" onClick={handleWatchFolder} title="Add a local folder to vault">
            <Ico name="folder" /> WATCH FOLDER
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => handleOpenFolder(selectedFolder)}>
            OPEN IN EXPLORER
          </button>
        </div>
      </div>

      {folderEntry && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="ph">
            <span className="ptag cyan">SYNCED</span>
            <span className="ptitle">{folderEntry.name}</span>
            <span className="psub">
              {folderEntry.last_synced ? 'Last sync: ' + timeAgo(folderEntry.last_synced) : 'Never synced'}
            </span>
          </div>
        </div>
      )}

      {loading ? (
        <div className="empty-state">
          <Mascot src={MASCOT_CHILLING} className="empty-mascot" wrapClass="empty-mascot-wrap" />
          <div className="empty-title">LOADING...</div>
        </div>
      ) : files.length === 0 ? (
        <div className="empty-state">
          <Mascot src={MASCOT_TIRED} className="empty-mascot" wrapClass="empty-mascot-wrap" />
          <div className="empty-title">NO MEDIA HERE</div>
          <div className="empty-sub">Download something to this folder</div>
        </div>
      ) : (
        <div className="lib-grid">
          {files.map(file => (
            <div key={file.path} className="lib-card" onDoubleClick={() => handleOpenFile(file.path)}>
              <div className="lib-thumb-ph">
                {isVideoExt(file.ext) ? '▶' : '♫'}
              </div>
              <div className={'lib-fmt ' + (isVideoExt(file.ext) ? 'video' : 'audio')}>
                {file.ext.toUpperCase()}
              </div>
              <div className="lib-body">
                <div className="lib-title">{file.name.replace(/\.[^.]+$/, '')}</div>
                <div className="lib-meta">{fmtBytes(file.size_bytes)}</div>
              </div>
              <div
                className="lib-menu"
                onClick={(e) => {
                  e.stopPropagation();
                  const rect = e.currentTarget.getBoundingClientRect();
                  setCtxMenu({ file, x: rect.right, y: rect.bottom });
                }}
              >
                <Ico name="dots" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* CONTEXT MENU */}
      {ctxMenu && (
        <div className="ctx-menu" style={{ left: ctxMenu.x, top: ctxMenu.y }} onClick={e => e.stopPropagation()}>
          <div className="ctx-item" onClick={() => { handleOpenFile(ctxMenu.file.path); setCtxMenu(null); }}>
            <Ico name="play" /> Open in Player
          </div>
          <div className="ctx-item" onClick={() => { handleOpenFolder(ctxMenu.file.path); setCtxMenu(null); }}>
            <Ico name="folder" /> Open in Explorer
          </div>
          <div className="ctx-item danger" onClick={() => handleDeleteFile(ctxMenu.file)}>
            <Ico name="trash" /> Delete
          </div>
        </div>
      )}

      {/* DELETE CONFIRM */}
      {deleteConfirm && (
        <Modal
          title="CONFIRM DELETE"
          onClose={() => setDeleteConfirm(null)}
          footer={
            <>
              <button className="btn btn-secondary btn-sm" onClick={() => setDeleteConfirm(null)}>CANCEL</button>
              <button className="btn btn-danger btn-sm" onClick={confirmDelete}>DELETE PERMANENTLY</button>
            </>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}>
            <Mascot src={MASCOT_FRUSTRATED} className="error-mascot" wrapClass="error-mascot" style={{ width: 80 }} />
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 11, color: 'var(--t2)', textAlign: 'center' }}>
              Delete <span style={{ color: 'var(--red)' }}>{deleteConfirm.name}</span>?<br />
              <span style={{ color: 'var(--t4)', fontSize: 9 }}>This cannot be undone.</span>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── ANALYTICS Page ────────────────────────────────────────────────────────────

function AnalyticsPage({ stats, refreshStats }) {
  const [range, setRange] = React.useState('30d');
  const [localStats, setLocalStats] = React.useState(stats);
  const [overrides, setOverrides] = React.useState({});
  const trendRef = React.useRef(null);
  const platformRef = React.useRef(null);
  const donutRef = React.useRef(null);

  React.useEffect(() => {
    API.get('/api/stats?range=' + range)
      .then(setLocalStats)
      .catch(() => {});
  }, [range]);

  React.useEffect(() => {
    setLocalStats(s => ({ ...s, ...stats }));
  }, [stats]);

  React.useEffect(() => {
    API.get('/api/analytics/overrides').then(setOverrides).catch(() => {});
  }, []);

  const saveOverride = React.useCallback((key, val) => {
    const update = { [key]: val };
    setOverrides(o => ({ ...o, ...update }));
    API.post('/api/analytics/overrides', update).catch(() => {});
  }, []);

  // Use override value if present, else computed value
  const statVal = (key, computed) => (key in overrides && overrides[key] !== '' && overrides[key] !== null) ? overrides[key] : computed;

  // Draw trend chart
  React.useEffect(() => {
    const c = trendRef.current;
    if (!c || !localStats.by_day_last_30) return;
    const data = localStats.by_day_last_30;
    if (!data.length) return;
    const w = c.offsetWidth; c.width = w; c.height = 120;
    const ctx = c.getContext('2d');
    const pts = data.map(d => d.count);
    const labels = data.map(d => d.day.slice(5));
    const maxV = Math.max(...pts, 1);
    const pad = { l: 28, r: 8, t: 8, b: 22 };
    const cw = w - pad.l - pad.r, ch = 120 - pad.t - pad.b;
    ctx.clearRect(0, 0, w, 120);
    [0, 0.5, 1].forEach(f => {
      const y = pad.t + ch * (1 - f);
      ctx.strokeStyle = 'rgba(61,96,112,0.25)'; ctx.lineWidth = 0.5; ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + cw, y); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(61,96,112,0.6)'; ctx.font = '8px Share Tech Mono';
      ctx.fillText(Math.round(maxV * f), 0, y + 3);
    });
    const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + ch);
    grad.addColorStop(0, 'rgba(0,216,255,0.2)'); grad.addColorStop(1, 'rgba(0,216,255,0.01)');
    ctx.fillStyle = grad; ctx.beginPath();
    pts.forEach((v, i) => {
      const x = pad.l + i * (cw / (pts.length - 1));
      const y = pad.t + ch * (1 - v / maxV);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.lineTo(pad.l + cw, pad.t + ch); ctx.lineTo(pad.l, pad.t + ch); ctx.closePath(); ctx.fill();
    ctx.strokeStyle = 'rgba(0,216,255,0.85)'; ctx.lineWidth = 1.5; ctx.beginPath();
    pts.forEach((v, i) => {
      const x = pad.l + i * (cw / (pts.length - 1));
      const y = pad.t + ch * (1 - v / maxV);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = 'rgba(61,96,112,0.6)'; ctx.font = '7px Share Tech Mono'; ctx.textAlign = 'center';
    labels.forEach((l, i) => {
      if (i % Math.ceil(labels.length / 8) === 0) {
        const x = pad.l + i * (cw / (pts.length - 1));
        ctx.fillText(l, x, 120 - 5);
      }
    });
  }, [localStats.by_day_last_30]);

  // Draw platform bars
  React.useEffect(() => {
    const c = platformRef.current;
    if (!c || !localStats.by_platform) return;
    const data = localStats.by_platform.slice(0, 6);
    if (!data.length) return;
    const w = c.offsetWidth; c.width = w; c.height = Math.max(data.length * 22 + 16, 80);
    const ctx = c.getContext('2d');
    const maxV = Math.max(...data.map(d => d.count), 1);
    const pad = { l: 80, r: 40, t: 8, b: 8 };
    const cw = w - pad.l - pad.r;
    ctx.clearRect(0, 0, w, c.height);
    const colors = ['rgba(0,216,255,0.85)','rgba(249,169,0,0.85)','rgba(192,132,252,0.85)','rgba(0,255,148,0.7)','rgba(255,59,97,0.7)','rgba(61,96,112,0.7)'];
    data.forEach((p, i) => {
      const y = pad.t + i * 22;
      ctx.fillStyle = 'rgba(138,171,184,0.5)'; ctx.font = '9px Share Tech Mono'; ctx.textAlign = 'right';
      ctx.fillText(p.platform || '—', pad.l - 6, y + 12);
      const bw = (p.count / maxV) * cw;
      ctx.fillStyle = 'rgba(30,58,72,0.5)'; ctx.fillRect(pad.l, y, cw, 14);
      ctx.fillStyle = colors[i % colors.length]; ctx.fillRect(pad.l, y, bw, 14);
      ctx.fillStyle = 'rgba(216,236,245,0.8)'; ctx.textAlign = 'left'; ctx.font = '8px Share Tech Mono';
      ctx.fillText(p.count, pad.l + bw + 4, y + 11);
    });
  }, [localStats.by_platform]);

  // Draw donut
  React.useEffect(() => {
    const c = donutRef.current;
    if (!c || !localStats.storage_by_format) return;
    const data = localStats.storage_by_format.slice(0, 4);
    if (!data.length) return;
    c.width = 140; c.height = 140;
    const ctx = c.getContext('2d');
    const cx = 70, cy = 70, r = 52, ri = 34;
    const total = data.reduce((s, d) => s + d.bytes, 0) || 1;
    const colors = ['rgba(0,216,255,0.9)','rgba(249,169,0,0.9)','rgba(192,132,252,0.9)','rgba(0,255,148,0.7)'];
    let start = -Math.PI / 2;
    data.forEach((d, i) => {
      const sweep = (d.bytes / total) * Math.PI * 2;
      ctx.beginPath(); ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, r, start, start + sweep); ctx.closePath();
      ctx.fillStyle = colors[i]; ctx.fill();
      start += sweep;
    });
    ctx.beginPath(); ctx.arc(cx, cy, ri, 0, Math.PI * 2);
    ctx.fillStyle = 'var(--bg2)'; ctx.fill();
    ctx.fillStyle = 'rgba(0,216,255,0.9)'; ctx.font = 'bold 14px Oxanium'; ctx.textAlign = 'center';
    ctx.fillText(fmtBytes(total), cx, cy + 2);
    ctx.fillStyle = 'rgba(61,96,112,0.9)'; ctx.font = '8px Share Tech Mono';
    ctx.fillText('TOTAL', cx, cy + 14);
  }, [localStats.storage_by_format]);

  const hourly = localStats.hourly_activity || Array(24).fill(0);
  const maxHour = Math.max(...hourly, 1);

  const handleExport = () => {
    window.location.href = '/api/analytics/export';
  };

  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">データレイク / DATA LAKE</div>
          <div className="vtitle"><span style={{ color: 'var(--t1)' }}>DATA</span> <span className="a">LAKE</span></div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <div className="range-tabs">
            {['7d','30d','all'].map(r => (
              <div key={r} className={'range-tab' + (range === r ? ' active' : '')} onClick={() => setRange(r)}>
                {r === 'all' ? 'ALL TIME' : r.toUpperCase()}
              </div>
            ))}
          </div>
          <button className="btn btn-amber btn-sm" onClick={handleExport}>
            <Ico name="download" /> EXPORT CSV
          </button>
        </div>
      </div>

      {/* KPI CARDS — click any value to edit/override */}
      <div className="g4" style={{ marginBottom: 16 }}>
        <div className="stat">
          <div className="stat-label">TOTAL DOWNLOADS</div>
          <EditableStat
            value={statVal('total_downloads', localStats.total_downloads || 0)}
            colorClass="cyan"
            format={v => Number(v).toLocaleString()}
            onSave={v => saveOverride('total_downloads', v)}
          />
          <div className="stat-sub">all time</div>
        </div>
        <div className="stat">
          <div className="stat-label">STORAGE USED</div>
          <EditableStat
            value={statVal('total_size_bytes', localStats.total_size_bytes || 0)}
            colorClass="amber"
            format={v => fmtBytes(Number(v))}
            onSave={v => saveOverride('total_size_bytes', v)}
          />
          <div className="stat-sub">disk usage</div>
        </div>
        <div className="stat">
          <div className="stat-label">PLATFORMS</div>
          <EditableStat
            value={statVal('platform_count', (localStats.by_platform || []).length)}
            colorClass="green"
            format={v => String(v)}
            onSave={v => saveOverride('platform_count', v)}
          />
          <div className="stat-sub">distinct sources</div>
        </div>
        <div className="stat">
          <div className="stat-label">AVG SPEED</div>
          <EditableStat
            value={statVal('avg_speed_bps', localStats.avg_speed_bps || 0)}
            colorClass="cyan"
            format={v => fmtSpeed(Number(v))}
            onSave={v => saveOverride('avg_speed_bps', v)}
          />
          <div className="stat-sub">bytes/sec</div>
        </div>
      </div>

      {/* CHARTS ROW */}
      <div className="g2" style={{ marginBottom: 0 }}>
        <div className="chart-panel">
          <div className="chart-title">Download Trend</div>
          <div className="chart-sub">DOWNLOADS PER DAY — LAST {range.toUpperCase()}</div>
          <canvas ref={trendRef} className="chart" height={120} />
        </div>
        <div className="chart-panel">
          <div className="chart-title">Storage by Format</div>
          <div className="chart-sub">DISK USAGE BREAKDOWN</div>
          <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
            <canvas ref={donutRef} width={140} height={140} />
            <div style={{ flex: 1 }}>
              {(localStats.storage_by_format || []).slice(0, 4).map((f, i) => (
                <div key={f.format} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t2)' }}>
                  <span>{(f.format || '—').toUpperCase()}</span>
                  <span style={{ color: 'var(--cyan)' }}>{fmtBytes(f.bytes)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="g2">
        <div className="chart-panel">
          <div className="chart-title">Platform Breakdown</div>
          <div className="chart-sub">DOWNLOADS BY SOURCE</div>
          <canvas ref={platformRef} className="chart" />
        </div>
        <div className="chart-panel">
          <div className="chart-title">Activity Heatmap</div>
          <div className="chart-sub">DOWNLOADS BY HOUR OF DAY</div>
          <div className="heatmap">
            {hourly.map((v, i) => (
              <div
                key={i}
                className="hm-cell"
                title={`${String(i).padStart(2,'0')}:00 — ${v} downloads`}
                style={{ background: `rgba(0,216,255,${(0.06 + (v / maxHour) * 0.9).toFixed(2)})` }}
              />
            ))}
          </div>
          <div className="hm-labels">
            <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
          </div>
        </div>
      </div>

      {/* RECENT DOWNLOADS TABLE */}
      <div className="chart-panel">
        <div className="chart-title">Recent Downloads</div>
        <div className="chart-sub">LAST 10 RECORDS FROM DUCKDB</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>TITLE</th>
              <th>PLATFORM</th>
              <th>FORMAT</th>
              <th>SIZE</th>
              <th>DATE</th>
              <th>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {(localStats.recent_records || []).map(r => (
              <tr key={r.id}>
                <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.title || r.url || '—'}
                </td>
                <td><span className={platformTagClass(r.platform)}>{r.platform || '—'}</span></td>
                <td className="mono">{r.format ? r.format.toUpperCase() : '—'}</td>
                <td className="mono">{fmtBytes(r.file_size_bytes)}</td>
                <td className="mono">{fmtDate(r.timestamp)}</td>
                <td>
                  <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 8, padding: '2px 6px', color: r.status === 'success' ? 'var(--green)' : 'var(--red)', border: '1px solid', borderColor: r.status === 'success' ? 'rgba(0,255,148,0.3)' : 'rgba(255,59,97,0.3)' }}>
                    {(r.status || '').toUpperCase()}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!(localStats.recent_records || []).length && (
          <div style={{ padding: '24px', textAlign: 'center', fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)' }}>
            NO RECORDS YET — START DOWNLOADING TO POPULATE THE DATA LAKE
          </div>
        )}
      </div>
    </div>
  );
}

// ── SIGNAL API Page ───────────────────────────────────────────────────────────

const PRESET_QUERIES = [
  { label: 'Most downloaded channels', sql: "SELECT uploader, COUNT(*) as downloads, SUM(file_size_bytes) as total_bytes\nFROM downloads\nWHERE status='success' AND uploader IS NOT NULL\nGROUP BY uploader\nORDER BY downloads DESC\nLIMIT 15" },
  { label: 'Storage by format', sql: "SELECT format, COUNT(*) as count, SUM(file_size_bytes) as total_bytes, AVG(file_size_bytes) as avg_bytes\nFROM downloads\nWHERE status='success'\nGROUP BY format\nORDER BY total_bytes DESC" },
  { label: 'Downloads this week', sql: "SELECT strftime(timestamp, '%Y-%m-%d') as day, COUNT(*) as downloads\nFROM downloads\nWHERE status='success'\n  AND timestamp >= now() - INTERVAL '7 days'\nGROUP BY day\nORDER BY day DESC" },
  { label: 'Largest files', sql: "SELECT title, format, quality, file_size_bytes, timestamp\nFROM downloads\nWHERE status='success' AND file_size_bytes IS NOT NULL\nORDER BY file_size_bytes DESC\nLIMIT 10" },
  { label: 'Failed downloads', sql: "SELECT title, url, error_message, timestamp\nFROM downloads\nWHERE status='error'\nORDER BY timestamp DESC\nLIMIT 20" },
  { label: 'Downloads by hour', sql: "SELECT EXTRACT(hour FROM timestamp)::INTEGER as hour, COUNT(*) as count\nFROM downloads\nWHERE status='success'\nGROUP BY hour\nORDER BY hour" },
  { label: 'Platform breakdown', sql: "SELECT platform, COUNT(*) as downloads,\n  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as pct\nFROM downloads\nWHERE status='success'\nGROUP BY platform\nORDER BY downloads DESC" },
  { label: 'All downloads', sql: "SELECT id, title, platform, format, quality,\n  file_size_bytes, timestamp, status\nFROM downloads\nORDER BY timestamp DESC\nLIMIT 50" },
];

const SCHEMA_TEXT = `-- downloads
  id INTEGER PK, url TEXT, title TEXT, uploader TEXT,
  platform TEXT, duration_seconds INTEGER,
  file_size_bytes BIGINT, format TEXT, quality TEXT,
  container TEXT, file_path TEXT,
  timestamp TIMESTAMP, status TEXT,
  error_message TEXT, download_speed_avg_bps BIGINT,
  elapsed_seconds INTEGER

-- library
  id TEXT PK, name TEXT, url TEXT,
  folder TEXT, folder_name TEXT, use_subfolder BOOLEAN,
  quality TEXT, mode TEXT, embed_thumbnail BOOLEAN,
  embed_chapters BOOLEAN, embed_metadata BOOLEAN,
  embed_subs BOOLEAN, sub_langs TEXT,
  sponsorblock BOOLEAN, filename_template TEXT,
  sync_mode TEXT, last_synced TIMESTAMP, created_at TIMESTAMP

-- sync_log
  id INTEGER PK, library_id TEXT FK,
  synced_at TIMESTAMP, new_items INTEGER,
  skipped INTEGER, errors INTEGER, duration_seconds INTEGER`;

function SignalApiPage() {
  const [sql, setSql] = React.useState(PRESET_QUERIES[0].sql);
  const [activePreset, setActivePreset] = React.useState(0);
  const [result, setResult] = React.useState(null);
  const [running, setRunning] = React.useState(false);
  const [schemaOpen, setSchemaOpen] = React.useState(false);

  const runQuery = React.useCallback(() => {
    if (!sql.trim()) return;
    setRunning(true);
    setResult(null);
    API.post('/api/analytics/query', { sql })
      .then(setResult)
      .catch(e => setResult({ error: e.message, columns: [], rows: [] }))
      .finally(() => setRunning(false));
  }, [sql]);

  const handleExportResult = React.useCallback(() => {
    if (!result || !result.columns) return;
    const rows = [result.columns.join(','), ...result.rows.map(r => r.map(c => JSON.stringify(c ?? '')).join(','))];
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'query_result.csv'; a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">APIシグナル / SIGNAL API</div>
          <div className="vtitle"><span style={{ color: 'var(--t1)' }}>SIGNAL</span> <span className="a">API</span></div>
        </div>
        <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)', textAlign: 'right' }}>
          LIVE QUERY TERMINAL<br />
          <span style={{ color: 'var(--amber)' }}>LOCAL DATA LAKE ONLY</span>
        </div>
      </div>

      <div className="terminal-layout">
        {/* PRESET LIST */}
        <div className="preset-panel">
          <div className="ph">
            <span className="ptag amber">PRESETS</span>
            <span className="ptitle">QUICK QUERIES</span>
          </div>
          {PRESET_QUERIES.map((p, i) => (
            <div
              key={i}
              className={'preset-item' + (activePreset === i ? ' active' : '')}
              onClick={() => { setActivePreset(i); setSql(p.sql); }}
            >
              {p.label}
            </div>
          ))}
        </div>

        {/* QUERY PANEL */}
        <div className="query-panel">
          <div className="query-area">
            <div className="inp-label" style={{ marginBottom: 6 }}>SQL QUERY (SELECT ONLY)</div>
            <textarea
              className="query-textarea"
              value={sql}
              onChange={e => { setSql(e.target.value); setActivePreset(-1); }}
              spellCheck={false}
            />
          </div>
          <div className="query-footer">
            <button className="btn btn-primary btn-sm" onClick={runQuery} disabled={running}>
              {running ? 'EXECUTING...' : 'EXECUTE'}
            </button>
            {result && !result.error && (
              <>
                <div className="query-time">
                  {result.row_count} rows · {result.time_ms}ms
                </div>
                <button className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto' }} onClick={handleExportResult}>
                  EXPORT RESULT
                </button>
              </>
            )}
          </div>

          <div className="results-area">
            {result && result.error ? (
              <div className="error-state">
                <img src={MASCOT_FRUSTRATED} className="error-mascot" alt="" />
                <div className="error-msg">{result.error}</div>
              </div>
            ) : result && result.columns && result.columns.length > 0 ? (
              <table className="data-table" style={{ minWidth: '100%' }}>
                <thead>
                  <tr>{result.columns.map(c => <th key={c}>{c.toUpperCase()}</th>)}</tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td key={j} className="mono">
                          {cell === null ? <span style={{ color: 'var(--t4)' }}>NULL</span>
                            : typeof cell === 'number' ? cell.toLocaleString()
                            : String(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : !running ? (
              <div className="error-state">
                <Mascot src={MASCOT_TROUBLESHOOTING_SAFE || MASCOT_VIBING} className="error-mascot" wrapClass="error-mascot" style={{ width: 80 }} />
                <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t3)', textAlign: 'center' }}>
                  SELECT A PRESET OR WRITE A QUERY
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {/* SCHEMA */}
      <div style={{ marginTop: 16 }}>
        <div
          className="opts-adv-toggle"
          style={{ padding: '10px 0', borderTop: '1px solid var(--border)' }}
          onClick={() => setSchemaOpen(o => !o)}
        >
          <span dangerouslySetInnerHTML={{ __html: schemaOpen ? SVG.chevron_down : SVG.chevron_right }} />
          SCHEMA REFERENCE
        </div>
        {schemaOpen && (
          <div className="schema-block">{SCHEMA_TEXT}</div>
        )}
      </div>
    </div>
  );
}

// ── CONFIG Page ───────────────────────────────────────────────────────────────

function ConfigPage({ config, setConfig, showNotif, sysInfo, refreshStats }) {
  const [local, setLocal] = React.useState({ ...config });
  const [updateInfo, setUpdateInfo] = React.useState(null);
  const [checking, setChecking] = React.useState(false);
  const [updating, setUpdating] = React.useState(false);
  const [vacuuming, setVacuuming] = React.useState(false);
  const [dangerModal, setDangerModal] = React.useState(null);

  React.useEffect(() => {
    setLocal({ ...config });
  }, [config]);

  const set = (key, val) => setLocal(l => ({ ...l, [key]: val }));

  const handleSave = () => {
    API.post('/api/config', local)
      .then(() => { setConfig(local); showNotif('Saved', 'Configuration updated', 'success'); })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const handleReset = () => {
    API.post('/api/config', {
      output_dir: '', cookies_browser: 'none', cookies_file: '',
      rate_limit: '', proxy: '', external_downloader: '',
      concurrent_fragments: 4, sleep_interval: 1, retries: 3,
      write_metadata: true, extract_chapters: true, filename_template: '',
    }).then(() => API.get('/api/config').then(c => { setLocal(c); setConfig(c); showNotif('Reset', 'Defaults restored', 'success'); }));
  };

  const browseFolder = () => {
    API.post('/api/browse-folder', {}).then(d => { if (d.path) set('output_dir', d.path); });
  };

  const browseCookies = () => {
    API.post('/api/browse-file', { filter: '.txt' }).then(d => { if (d.path) set('cookies_file', d.path); });
  };

  const checkUpdate = () => {
    setChecking(true);
    API.get('/api/check-ytdlp-update')
      .then(setUpdateInfo)
      .catch(e => setUpdateInfo({ error: e.message }))
      .finally(() => setChecking(false));
  };

  const doVacuum = () => {
    setVacuuming(true);
    API.post('/api/analytics/vacuum', {})
      .then(d => showNotif('Vacuum complete', 'DB size: ' + fmtBytes(d.db_size_bytes), 'success'))
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setVacuuming(false));
  };

  const doPurge = () => {
    API.del('/api/history', { all: true })
      .then(d => {
        showNotif('Purged', d.deleted + ' records deleted', 'success');
        setDangerModal(null);
        if (refreshStats) refreshStats();
        API.get('/api/config').then(c => { setLocal(c); setConfig(c); }).catch(() => {});
      })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">システム設定 / SYSTEM CONFIG</div>
          <div className="vtitle"><span style={{ color: 'var(--t1)' }}>SYS</span> <span className="a">CONFIG</span></div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <button className="btn btn-secondary btn-sm" onClick={handleReset}>RESET DEFAULTS</button>
          <button className="btn btn-primary btn-sm" onClick={handleSave}>SAVE CONFIG →</button>
        </div>
      </div>

      <div className="cfg-layout">
        {/* LEFT COLUMN */}
        <div>
          {/* STORAGE */}
          <div className="cfg-panel">
            <div className="cfg-ph">
              <span className="ptag">STORAGE</span>
              <span className="ptitle">FILE OUTPUT</span>
            </div>
            <div className="cfg-body">
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Download Path</div>
                  <div className="sl-sub">Where files are saved by default</div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <input className="inp-sm" style={{ width: 180 }} value={local.output_dir || ''} onChange={e => set('output_dir', e.target.value)} />
                  <button className="btn btn-secondary btn-sm" onClick={browseFolder}>BROWSE</button>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Database Path</div>
                  <div className="sl-sub">DuckDB analytical database location</div>
                </div>
                <div className="settings-ctrl">
                  <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t3)' }}>~/.mellow_dlp.duckdb</span>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Filename Template</div>
                  <div className="sl-sub">yt-dlp output template</div>
                </div>
                <div className="settings-ctrl">
                  <input className="inp-sm" style={{ width: 220 }} value={local.filename_template || ''} onChange={e => set('filename_template', e.target.value)} placeholder="%(title)s [%(id)s].%(ext)s" />
                </div>
              </div>
            </div>
          </div>

          {/* AUTHENTICATION */}
          <div className="cfg-panel">
            <div className="cfg-ph">
              <span className="ptag">AUTH</span>
              <span className="ptitle">AUTHENTICATION</span>
            </div>
            <div className="cfg-body">
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Browser Cookies</div>
                  <div className="sl-sub">Uses your current browser login session</div>
                </div>
                <div className="settings-ctrl">
                  <select className="sel" value={local.cookies_browser || 'none'} onChange={e => set('cookies_browser', e.target.value)}>
                    {['none','chrome','firefox','edge','brave','safari'].map(b => (
                      <option key={b} value={b}>{b === 'none' ? 'Disabled' : b.charAt(0).toUpperCase() + b.slice(1)}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Cookies File</div>
                  <div className="sl-sub">Export via "Get cookies.txt LOCALLY" extension</div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <input className="inp-sm" style={{ width: 160 }} value={local.cookies_file || ''} onChange={e => set('cookies_file', e.target.value)} placeholder="cookies.txt" />
                  <button className="btn btn-secondary btn-sm" onClick={browseCookies}>BROWSE</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div>
          {/* NETWORK */}
          <div className="cfg-panel">
            <div className="cfg-ph">
              <span className="ptag">NETWORK</span>
              <span className="ptitle">NETWORK SETTINGS</span>
            </div>
            <div className="cfg-body">
              {[
                { key: 'concurrent_fragments', label: 'Concurrent Fragments', sub: 'Parallel fragment downloads', type: 'number', min: 1, max: 16 },
                { key: 'rate_limit', label: 'Rate Limit', sub: '5M = 5MB/s · empty = unlimited', type: 'text', placeholder: '5M' },
                { key: 'proxy', label: 'Proxy', sub: 'http://host:port or socks5://host:port', type: 'text', placeholder: 'http://...' },
                { key: 'external_downloader', label: 'External Downloader', sub: 'aria2c for parallel (must be installed)', type: 'text', placeholder: 'aria2c' },
                { key: 'sleep_interval', label: 'Sleep Interval (s)', sub: 'Delay between playlist items', type: 'number', min: 0, max: 60 },
                { key: 'retries', label: 'Retries', sub: 'Auto-retry count on failure', type: 'number', min: 0, max: 10 },
              ].map(f => (
                <div key={f.key} className="settings-row">
                  <div className="settings-label">
                    <div className="sl-name">{f.label}</div>
                    <div className="sl-sub">{f.sub}</div>
                  </div>
                  <div className="settings-ctrl">
                    <input
                      className="inp-sm"
                      style={{ width: 110 }}
                      type={f.type}
                      min={f.min}
                      max={f.max}
                      value={local[f.key] !== undefined ? local[f.key] : ''}
                      placeholder={f.placeholder || ''}
                      onChange={e => set(f.key, f.type === 'number' ? (parseInt(e.target.value) || 0) : e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* DATABASE */}
          <div className="cfg-panel">
            <div className="cfg-ph">
              <span className="ptag amber">DB</span>
              <span className="ptitle">DATABASE</span>
            </div>
            <div className="cfg-body">
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Write Metadata to DB</div>
                  <div className="sl-sub">Log every download to DuckDB analytics</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.write_metadata !== false} onChange={v => set('write_metadata', v)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">DB Engine</div>
                  <div className="sl-sub">Analytical columnar database</div>
                </div>
                <div className="settings-ctrl">
                  <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--amber)' }}>DuckDB (analytical)</span>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">DB Size</div>
                  <div className="sl-sub">Current database file size</div>
                </div>
                <div className="settings-ctrl">
                  <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--cyan)' }}>{fmtBytes(sysInfo.db_size_bytes || 0)}</span>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Vacuum Database</div>
                  <div className="sl-sub">Reclaim unused space</div>
                </div>
                <div className="settings-ctrl">
                  <button className="btn btn-secondary btn-sm" onClick={doVacuum} disabled={vacuuming}>
                    {vacuuming ? 'VACUUMING...' : 'VACUUM DB'}
                  </button>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">yt-dlp Version</div>
                  <div className="sl-sub">
                    {updateInfo && !updateInfo.error && updateInfo.update_available
                      ? <span style={{ color: 'var(--amber)' }}>Update available: {updateInfo.latest}</span>
                      : updateInfo && !updateInfo.error ? <span style={{ color: 'var(--green)' }}>Up to date</span>
                      : 'Check for updates below'
                    }
                  </div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-secondary btn-sm" onClick={checkUpdate} disabled={checking}>{checking ? '...' : 'CHECK'}</button>
                  {updateInfo && updateInfo.update_available && (
                    <button className="btn btn-amber btn-sm" disabled={updating} onClick={() => {
                      setUpdating(true);
                      API.post('/api/update-ytdlp', {})
                        .then(() => showNotif('Updating', 'yt-dlp update started'))
                        .catch(e => showNotif('Error', e.message, 'error'))
                        .finally(() => setUpdating(false));
                    }}>{updating ? 'UPDATING...' : 'UPDATE'}</button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* DANGER ZONE */}
          <div className="cfg-panel cfg-danger">
            <div className="cfg-ph">
              <span className="ptag red">DANGER</span>
              <span className="ptitle" style={{ color: 'var(--red)' }}>DANGER ZONE</span>
            </div>
            <div className="cfg-body">
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Purge Database Records</div>
                  <div className="sl-sub">Delete all download history from DuckDB</div>
                </div>
                <div className="settings-ctrl">
                  <button className="btn btn-danger btn-sm" onClick={() => setDangerModal('purge')}>PURGE RECORDS</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {dangerModal === 'purge' && (
        <Modal
          title="PURGE DATABASE RECORDS"
          onClose={() => setDangerModal(null)}
          footer={
            <>
              <button className="btn btn-secondary btn-sm" onClick={() => setDangerModal(null)}>CANCEL</button>
              <button className="btn btn-danger btn-sm" onClick={doPurge}>PURGE ALL RECORDS</button>
            </>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}>
            <Mascot src={MASCOT_FRUSTRATED} className="error-mascot" wrapClass="error-mascot" style={{ width: 80 }} />
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t2)', textAlign: 'center', lineHeight: 1.8 }}>
              This will permanently delete all download records from DuckDB.<br />
              <span style={{ color: 'var(--red)' }}>This action cannot be undone.</span>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── App Root ──────────────────────────────────────────────────────────────────

function App() {
  const [loading, setLoading] = React.useState(true);
  const [page, setPage] = React.useState('feed');
  const [appState, setAppState] = React.useState('idle');
  const [dlState, setDlState] = React.useState(null);
  const [stats, setStats] = React.useState({});
  const [sysInfo, setSysInfo] = React.useState({});
  const [config, setConfig] = React.useState({});
  const [notif, setNotif] = React.useState(null);
  const [speedHistory, setSpeedHistory] = React.useState(Array(60).fill(0));
  const [vaultFolders, setVaultFolders] = React.useState([]);
  const [selectedVaultFolder, setSelectedVaultFolder] = React.useState(null);
  const [addVaultModal, setAddVaultModal] = React.useState(false);
  const [showVictory, setShowVictory] = React.useState(false);
  const playlistActiveRef = React.useRef(false);
  const notifTimer = React.useRef(null);
  const victoryTimer = React.useRef(null);

  const showNotif = React.useCallback((title, body, type = 'info') => {
    setNotif({ title, body, type });
    if (notifTimer.current) clearTimeout(notifTimer.current);
    notifTimer.current = setTimeout(() => setNotif(null), 6000);
  }, []);

  const refreshStats = React.useCallback(() => {
    API.get('/api/stats').then(setStats).catch(() => {});
    API.get('/api/system').then(setSysInfo).catch(() => {});
  }, []);

  const refreshVault = React.useCallback((basePath) => {
    const path = basePath || config.output_dir;
    if (!path) return;
    API.get('/api/vault?path=' + encodeURIComponent(path))
      .then(d => setVaultFolders(d.folders || []))
      .catch(() => {});
  }, [config.output_dir]);

  React.useEffect(() => {
    refreshStats();
    API.get('/api/config').then(c => {
      setConfig(c);
      if (c.output_dir) {
        API.get('/api/vault?path=' + encodeURIComponent(c.output_dir))
          .then(d => setVaultFolders(d.folders || []))
          .catch(() => {});
      }
    }).catch(() => {});
  }, []);

  React.useEffect(() => {
    const es = new EventSource('/api/progress');
    es.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }
      if (data.status === 'ping') return;
      if (data.status === 'starting') {
        setAppState('downloading');
        setDlState({ status: 'starting', pct: 0 });
      } else if (data.status === 'downloading') {
        setAppState('downloading');
        setDlState(data);
        setSpeedHistory(h => [...h.slice(1), data.speed || 0]);
      } else if (data.status === 'processing') {
        setAppState('processing');
        setDlState(prev => prev ? { ...prev, status: 'processing' } : { status: 'processing', pct: 100 });
      } else if (data.status === 'complete') {
        setDlState(null);
        setAppState('idle');
        setSpeedHistory(h => [...h.slice(1), 0]);
        showNotif('Download Complete', data.title || 'File saved successfully', 'success');
        refreshStats();
        refreshVault();
        if (playlistActiveRef.current && MASCOT_VICTORY_SAFE) {
          playlistActiveRef.current = false;
          setShowVictory(true);
          if (victoryTimer.current) clearTimeout(victoryTimer.current);
          victoryTimer.current = setTimeout(() => setShowVictory(false), 4500);
        }
      } else if (data.status === 'error') {
        setDlState(null);
        setAppState('error');
        showNotif('Error', data.message || 'Download failed', 'error');
        refreshStats();
      } else if (data.status === 'cancelled') {
        setDlState(null);
        setAppState('idle');
        showNotif('Cancelled', 'Download stopped');
      } else if (data.status === 'ytdlp_updated') {
        if (data.ok) showNotif('Updated', 'yt-dlp updated successfully', 'success');
        else showNotif('Update failed', data.error || '', 'error');
        refreshStats();
      }
    };
    es.onerror = () => {};
    return () => es.close();
  }, [showNotif, refreshStats, refreshVault]);

  const switchPage = React.useCallback((p) => setPage(p), []);

  if (loading) {
    return <LoadingScreen onReady={() => setLoading(false)} />;
  }

  return (
    <div className="app">
      <Sidebar
        page={page}
        setPage={setPage}
        appState={appState}
        stats={stats}
        speedHistory={speedHistory}
        sysInfo={sysInfo}
        vaultFolders={vaultFolders}
        selectedVaultFolder={selectedVaultFolder}
        setSelectedVaultFolder={(folder) => {
          setSelectedVaultFolder(folder);
          setPage('vault');
        }}
        onAddVault={() => setAddVaultModal(true)}
      />

      <div className="main">
        <TopBar page={page} />

        {page === 'feed' && (
          <FeedPage
            dlState={dlState}
            setDlState={setDlState}
            setAppState={setAppState}
            stats={stats}
            refreshStats={refreshStats}
            showNotif={showNotif}
            switchPage={switchPage}
            config={config}
            onPlaylistDownload={() => { playlistActiveRef.current = true; }}
          />
        )}
        {page === 'queue' && (
          <QueuePage dlState={dlState} showNotif={showNotif} />
        )}
        {page === 'vault' && (
          <VaultPage
            vaultFolders={vaultFolders}
            selectedFolder={selectedVaultFolder}
            setSelectedFolder={setSelectedVaultFolder}
            config={config}
            showNotif={showNotif}
            onAddVault={() => setAddVaultModal(true)}
            onRefreshVault={refreshVault}
          />
        )}
        {page === 'analytics' && (
          <AnalyticsPage stats={stats} refreshStats={refreshStats} />
        )}
        {page === 'signal' && <SignalApiPage />}
        {page === 'config' && (
          <ConfigPage
            config={config}
            setConfig={setConfig}
            showNotif={showNotif}
            sysInfo={sysInfo}
            refreshStats={refreshStats}
          />
        )}

        <StatusBar sysInfo={sysInfo} speedHistory={speedHistory} config={config} />
      </div>

      <Notif notif={notif} dismiss={() => setNotif(null)} />

      {showVictory && MASCOT_VICTORY_SAFE && (
        <div className="victory-overlay" onClick={() => setShowVictory(false)}>
          <Mascot src={MASCOT_VICTORY_SAFE} className="victory-mascot" wrapClass="victory-mascot" />
          <div className="victory-text">PLAYLIST COMPLETE!</div>
        </div>
      )}

      {addVaultModal && (
        <AddVaultModal
          onClose={() => setAddVaultModal(false)}
          onSaved={() => { setAddVaultModal(false); refreshVault(); showNotif('Added to VAULT', 'Playlist saved', 'success'); }}
          showNotif={showNotif}
        />
      )}
    </div>
  );
}

// ── Add Vault Modal ───────────────────────────────────────────────────────────

function AddVaultModal({ onClose, onSaved, showNotif }) {
  const [name, setName] = React.useState('');
  const [url, setUrl] = React.useState('');
  const [folder, setFolder] = React.useState('');
  const [quality, setQuality] = React.useState('1080p');
  const [mode, setMode] = React.useState('add');
  const [saving, setSaving] = React.useState(false);

  const browseFolder = () => {
    API.post('/api/browse-folder', {}).then(d => { if (d.path) setFolder(d.path); });
  };

  const handleSave = () => {
    if (!name.trim()) { showNotif('Error', 'Name is required', 'error'); return; }
    setSaving(true);
    API.post('/api/library', {
      name: name.trim(),
      url: url.trim(),
      folder: folder,
      folder_name: name.trim(),
      use_subfolder: !!folder,
      quality,
      mode: 'VIDEO',
      sync_mode: mode,
      embed_thumbnail: true, embed_chapters: true, embed_metadata: true,
    }).then(() => onSaved())
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setSaving(false));
  };

  return (
    <Modal
      title="ADD PLAYLIST TO VAULT"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary btn-sm" onClick={onClose}>CANCEL</button>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            {saving ? 'SAVING...' : 'ADD TO VAULT'}
          </button>
        </>
      }
    >
      <div className="form-row">
        <div className="form-label">PLAYLIST NAME</div>
        <input className="form-input" value={name} onChange={e => setName(e.target.value)} placeholder="My Playlist" />
      </div>
      <div className="form-row">
        <div className="form-label">YOUTUBE / SOURCE URL</div>
        <input className="form-input" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://youtube.com/playlist?list=..." />
      </div>
      <div className="form-row">
        <div className="form-label">SAVE FOLDER</div>
        <div className="input-row">
          <input className="form-input" value={folder} onChange={e => setFolder(e.target.value)} placeholder="C:\Users\..." />
          <button className="btn btn-secondary btn-sm" onClick={browseFolder}>BROWSE</button>
        </div>
      </div>
      <div className="form-row">
        <div className="form-label">QUALITY</div>
        <select className="sel" value={quality} onChange={e => setQuality(e.target.value)}>
          {['best','4k','1080p','720p','480p','360p'].map(q => (
            <option key={q} value={q}>{q.toUpperCase()}</option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <div className="form-label">SYNC MODE</div>
        <div className="pills">
          <div className={'pill' + (mode === 'add' ? ' active' : '')} onClick={() => setMode('add')}>ADD ONLY</div>
          <div className={'pill' + (mode === 'mirror' ? ' active' : '')} onClick={() => setMode('mirror')}>
            MIRROR <span style={{ color: 'var(--amber)', fontSize: 8 }}> DESTRUCTIVE</span>
          </div>
        </div>
      </div>
    </Modal>
  );
}

// ── Mount ─────────────────────────────────────────────────────────────────────

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(App));
