// Theme Archive's window: a lobby header with resource capsules, a dock of big buttons at the bottom,
// a title plate with a talking assistant, and a notice tray (gui/themes/archive/DIRECTION.md).
// Registered in ../slots.jsx; each part gets exactly the props Classic's part gets
// (gui/components/chrome.jsx) and offers the same things. Styles: ../archive.css.
'use strict';

import { fmtBytes, fmtSpeed, themeRgba } from '../../lib/util.js';
import { SVG } from '../../components/icons.jsx';
import { Mascot } from '../../components/common.jsx';
import {
  MASCOT_DJ, MASCOT_VIBING, MASCOT_CHILLING,
  MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE, MASCOT_TROUBLESHOOTING_SAFE,
} from '../../lib/mascots.js';
import {
  ARCHIVE_SPARK_POINTS as SPARK_POINTS, ARCHIVE_SPARK_H as SPARK_H, ARCHIVE_DATE_TICK_MS as DATE_TICK_MS,
} from '../../lib/constants.js';

// The six sections, in the order of the 1–6 keys; `line` is what the assistant says on that page
const PAGES = [
  { id: 'feed', label: 'Feed', jp: 'フィード', icon: 'feed', line: "Paste a link and I'll fetch it!" },
  { id: 'queue', label: 'Queue', jp: 'キュー', icon: 'queue', line: "Here's everything waiting its turn." },
  { id: 'vault', label: 'Vault', jp: 'ライブラリ', icon: 'vault', line: 'Your collection, all in one place.' },
  { id: 'analytics', label: 'Analytics', jp: 'データ', icon: 'analytics', line: "Let's see how you've been doing!", lake: true },
  { id: 'signal', label: 'Signal', jp: 'シグナル', icon: 'signal', line: 'Ask the database anything.', lake: true },
  { id: 'config', label: 'Config', jp: '設定', icon: 'config', line: 'Make it just the way you like.', lake: true },
];

const PAGE_MASCOT = {
  feed: MASCOT_VIBING,
  queue: MASCOT_DJ,
  vault: MASCOT_COMFY_SAFE || MASCOT_CHILLING,
  analytics: MASCOT_CHILLING,
  signal: MASCOT_SUCCESS_SAFE || MASCOT_VIBING,
  config: MASCOT_TROUBLESHOOTING_SAFE || MASCOT_VIBING,
};

// Small glyphs for the resource capsules (drawn in the capsule's colour)
const GLYPH = {
  speed: '<svg viewBox="0 0 24 24"><path d="M13.5 2 4.5 13.5h6.5L10 22l9.5-12.5H13z" fill="currentColor"/></svg>',
  records: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M5 6.5h14M5 12h14M5 17.5h9"/></svg>',
  size: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><ellipse cx="12" cy="6" rx="7.5" ry="3"/><path d="M4.5 6v12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3"/></svg>',
  library: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M9 17.5V5l10-2v12.5"/><circle cx="6.5" cy="17.5" r="2.5" fill="currentColor"/><circle cx="16.5" cy="15.5" r="2.5" fill="currentColor"/></svg>',
};

function Glyph({ name }) {
  return <i className="arc-glyph" aria-hidden="true" dangerouslySetInnerHTML={{ __html: GLYPH[name] }} />;
}

// One resource capsule: a round icon, a caption, the value. Keyed by its value outside, so a change pops
function Capsule({ glyph, cap, live, title, children }) {
  return (
    <div className={'arc-cap' + (live ? ' live' : '')} title={title}>
      <Glyph name={glyph} />
      <div className="arc-cap-text">
        <span className="arc-cap-label">{cap}</span>
        <span className="arc-cap-val">{children}</span>
      </div>
    </div>
  );
}

// The Sidebar slot: the lobby header (brand, resource capsules, status) and the dock
export function ArchiveSidebar({ page, setPage, appState, stats, speedHistory, theme, sysInfo }) {
  const sparkRef = React.useRef(null);

  // The speed sparkline in its capsule: a soft area under a round line, the newest point marked
  React.useEffect(() => {
    const c = sparkRef.current;
    if (!c || !c.offsetWidth) return;
    const w = c.offsetWidth;
    const dpr = window.devicePixelRatio || 1;
    c.width = w * dpr;
    c.height = SPARK_H * dpr;
    const ctx = c.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, SPARK_H);
    const pts = speedHistory.slice(-SPARK_POINTS);
    while (pts.length < SPARK_POINTS) pts.unshift(0);
    const maxV = Math.max(...pts, 1);
    const xy = pts.map((v, i) => [(i / (pts.length - 1)) * (w - 3) + 1.5, SPARK_H - 2 - (v / maxV) * (SPARK_H - 5)]);
    const fill = ctx.createLinearGradient(0, 0, 0, SPARK_H);
    fill.addColorStop(0, themeRgba('--accent-rgb', 0.32));   // a canvas can't resolve var()
    fill.addColorStop(1, themeRgba('--accent-rgb', 0));
    ctx.beginPath();
    xy.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.lineTo(xy[xy.length - 1][0], SPARK_H);
    ctx.lineTo(xy[0][0], SPARK_H);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.beginPath();
    xy.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.strokeStyle = themeRgba('--accent-rgb', 0.9);
    ctx.lineWidth = 1.6;
    ctx.lineJoin = 'round';
    ctx.stroke();
    const [lx, ly] = xy[xy.length - 1];
    ctx.beginPath();
    ctx.arc(lx, ly, 2, 0, Math.PI * 2);
    ctx.fillStyle = themeRgba('--accent-rgb', 1);
    ctx.fill();
  }, [speedHistory, theme]);   // the line's colour is the theme's

  const currentSpeed = speedHistory.length ? speedHistory[speedHistory.length - 1] : 0;
  const live = currentSpeed > 0;
  const [speedNum, speedUnit] = fmtSpeed(currentSpeed).split(' ');
  const [dbNum, dbUnit] = fmtBytes(stats.total_size_bytes || 0).split(' ');
  const trouble = !sysInfo.ffmpeg || appState === 'error';
  const statusText = !sysInfo.ffmpeg ? 'ffmpeg missing' : appState === 'error' ? 'Last download failed' : 'All good!';

  return (
    <>
      <header className={'arc-top' + (live ? ' live' : '')}>
        <div className="arc-brand">
          <i className="arc-brand-halo" aria-hidden="true" />
          <img src="assets/mellow.ico" className="arc-brand-img" alt="" onError={(e) => { e.target.style.display = 'none'; }} />
          <div className="arc-brand-text">
            <div className="arc-brand-name">Mellow<span>DLP</span></div>
            <div className="arc-brand-sub">メロウ · {sysInfo.app_version ? 'v' + sysInfo.app_version : '…'}</div>
          </div>
        </div>

        <div className="arc-caps">
          <Capsule glyph="speed" cap="Speed" live={live} title="Download speed right now">
            <b key={speedNum}>{speedNum}</b><small>{speedUnit}</small>
            <canvas ref={sparkRef} className="arc-spark" aria-hidden="true" />
          </Capsule>
          <Capsule glyph="records" cap="Records" title="Downloads recorded">
            <b key={stats.total_downloads || 0}>{(stats.total_downloads || 0).toLocaleString()}</b>
          </Capsule>
          <Capsule glyph="size" cap="Total" title="Size of everything recorded">
            <b key={dbNum + dbUnit}>{dbNum}</b><small>{dbUnit}</small>
          </Capsule>
          <Capsule glyph="library" cap="Library" title="Playlists the library tracks">
            <b key={stats.library_playlists || 0}>{stats.library_playlists || 0}</b>
          </Capsule>
          <div className={'arc-state' + (trouble ? ' warn' : '')} title={'System status: ' + statusText}>
            <i className="arc-state-dot" aria-hidden="true" />{statusText}
          </div>
        </div>
      </header>

      <nav className="arc-dock" aria-label="Sections">
        {PAGES.map((p, i) => (
          <button
            type="button"
            key={p.id}
            className={'arc-dock-btn nav-item' + (page === p.id ? ' on' : '') + (p.lake && !PAGES[i - 1].lake ? ' arc-dock-gap' : '')}
            aria-current={page === p.id ? 'page' : undefined}
            title={p.label + ' — key ' + (i + 1)}
            onClick={() => setPage(p.id)}
          >
            <span className="arc-dock-icon" dangerouslySetInnerHTML={{ __html: SVG[p.icon] }} />
            <span className="arc-dock-label">{p.label}</span>
            <span className="arc-dock-key" aria-hidden="true">{i + 1}</span>
          </button>
        ))}
      </nav>
    </>
  );
}

// The TopBar slot: the title plate, the assistant with its bubble, GUIDE and the date
export function ArchiveTopBar({ page, onGuide }) {
  const [date, setDate] = React.useState('');

  React.useEffect(() => {
    const update = () => setDate(new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }));
    update();
    const t = setInterval(update, DATE_TICK_MS);
    return () => clearInterval(t);
  }, []);

  const meta = PAGES.find(p => p.id === page) || PAGES[0];

  return (
    <div className="arc-bar">
      <div className="arc-plate" key={meta.id}>
        <span className="arc-plate-chev" aria-hidden="true" />
        <span className="arc-plate-title">{meta.label}</span>
        <span className="arc-plate-jp">{meta.jp}</span>
      </div>

      <div className="arc-assist" key={'assist-' + meta.id}>
        <div className="arc-bubble">{meta.line}</div>
        <div className="arc-assist-face">
          <Mascot src={PAGE_MASCOT[page] || MASCOT_VIBING} className="arc-assist-art" />
        </div>
      </div>

      {onGuide && (
        <button type="button" className="arc-guide topbar-guide" onClick={onGuide}
          title="What each part of this page does (G)">
          <span className="arc-guide-q" aria-hidden="true">?</span>Guide
        </button>
      )}
      <div className="arc-date">{date}</div>
    </div>
  );
}

// The PageFrame slot: a sky backdrop with two slow halo rings; each page slides up into it
export function ArchivePageFrame({ page, children }) {
  return (
    <div className="arc-frame" data-page={page}>
      <div className="arc-backdrop" aria-hidden="true">
        <i className="arc-halo" />
        <i className="arc-halo arc-halo-2" />
      </div>
      <div className="arc-page" key={page}>{children}</div>
    </div>
  );
}

// One chip of the notice tray. Clickable ones are buttons (keyboard too)
function Chip({ cap, tone, className, onClick, children, ...rest }) {
  const cls = 'sb-seg arc-chip' + (tone ? ' ' + tone : '') + (className ? ' ' + className : '');
  const inner = (
    <>
      <i className="arc-chip-dot" aria-hidden="true" />
      {cap && <span className="arc-chip-cap">{cap}</span>}
      <span className="arc-chip-val">{children}</span>
    </>
  );
  return onClick
    ? <button type="button" className={cls} onClick={onClick} {...rest}>{inner}</button>
    : <div className={cls} {...rest}>{inner}</div>;
}

// The StatusBar slot: the notice tray (link, yt-dlp, ffmpeg, disk | the update offer, the folder);
// the dock floats in its middle
export function ArchiveStatusBar({ sysInfo, speedHistory, config, appUpdate, onAppUpdate, ffmpegInstall, onGetFfmpeg }) {
  const currentSpeed = speedHistory.length ? speedHistory[speedHistory.length - 1] : 0;
  const isActive = currentSpeed > 0;

  return (
    <div className="statusbar arc-tray">
      <div className="arc-tray-side">
        <Chip cap="Link" tone={isActive ? 'live' : 'idle'}>{isActive ? 'Downloading' : 'Idle'}</Chip>
        <Chip cap="yt-dlp" tone="info">{sysInfo.ytdlp_version || '—'}</Chip>
        {ffmpegInstall ? (
          <Chip cap="ffmpeg" tone="warn" className="sb-update" title="Downloading and checking ffmpeg">
            {ffmpegInstall.stage === 'downloading' ? ffmpegInstall.pct + '%' : 'Installing…'}
          </Chip>
        ) : !sysInfo.ffmpeg && sysInfo.ffmpeg_installable ? (
          <Chip tone="err" className="sb-update sb-ffmpeg-get" onClick={onGetFfmpeg}
            title="ffmpeg merges, converts and trims. Click to download it into MellowDLP (checked against its published checksum)">
            ffmpeg missing — get it
          </Chip>
        ) : (
          <Chip cap="ffmpeg" tone={sysInfo.ffmpeg ? 'ok' : 'err'} title={sysInfo.ffmpeg
            ? (sysInfo.ffmpeg_path || 'ffmpeg found')
            : (sysInfo.ffmpeg_install_note || 'ffmpeg is needed to merge, convert and trim.')}>
            {sysInfo.ffmpeg ? 'OK' : 'Missing'}
          </Chip>
        )}
        {sysInfo.disk_free_bytes != null && (
          <Chip cap={sysInfo.disk_low ? 'Disk low' : 'Disk'} tone={sysInfo.disk_low ? 'err' : 'ok'}
            title="Free space on the download drive">
            {fmtBytes(sysInfo.disk_free_bytes)} free
          </Chip>
        )}
      </div>
      <div className="arc-tray-dock" aria-hidden="true" />
      <div className="arc-tray-side arc-tray-right">
        {appUpdate && (
          <Chip tone="new" className="sb-update" onClick={onAppUpdate}
            title={appUpdate.can_install
              ? 'Download, check and install MellowDLP ' + appUpdate.latest + ', then restart'
              : (appUpdate.install_note || 'Open the release page')}>
            New! MellowDLP {appUpdate.latest} — {appUpdate.can_install ? 'update' : 'get it'}
          </Chip>
        )}
        <Chip cap="Saves to" tone="info" className="sb-path" title={config.output_dir || undefined}>
          {config.output_dir || '—'}
        </Chip>
      </div>
    </div>
  );
}
