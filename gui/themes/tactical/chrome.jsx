// Theme Tactical's window: a header strip with section tabs, an instrument rail on the right, a
// command bar and an annunciator row (gui/themes/tactical/DIRECTION.md). Registered in ../slots.jsx;
// each part gets exactly the props Classic's part gets (gui/components/chrome.jsx) and offers the same
// things. Styles: ../tactical.css.
'use strict';

import { fmtBytes, fmtSpeed, themeRgba } from '../../lib/util.js';
import { SVG } from '../../components/icons.jsx';
import {
  TACTICAL_GAUGE_SEGMENTS as GAUGE_SEGMENTS, TACTICAL_RAIL_GRAPH_BARS as RAIL_GRAPH_BARS,
  TACTICAL_RAIL_GRAPH_H as RAIL_GRAPH_H, TACTICAL_STATUS_GRAPH_H as STATUS_GRAPH_H,
} from '../../lib/constants.js';

// The six sections, in the order of the 1–6 keys. `role` is what the command bar calls the page.
const PAGES = [
  { id: 'feed', label: 'FEED', num: '01', icon: 'feed', path: 'COMMAND', role: 'INTAKE' },
  { id: 'queue', label: 'QUEUE', num: '02', icon: 'queue', path: 'QUEUE', role: 'JOB CONTROL' },
  { id: 'vault', label: 'VAULT', num: '03', icon: 'vault', path: 'VAULT', role: 'MEDIA STORAGE' },
  { id: 'analytics', label: 'ANALYTICS', num: '04', icon: 'analytics', path: 'ANALYTICS', role: 'TELEMETRY', lake: true },
  { id: 'signal', label: 'SIGNAL API', num: '05', icon: 'signal', path: 'SIGNAL API', role: 'DATA LINK', lake: true },
  { id: 'config', label: 'CONFIG', num: '06', icon: 'config', path: 'CONFIG', role: 'SYSTEM SETUP', lake: true },
];

// A canvas sized to its box, cleared, with the device's pixel ratio applied
function prepare(canvas, height) {
  const w = canvas.offsetWidth;
  if (!w) return null;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = w * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, height);
  return { ctx, w };
}

// The Sidebar slot: the header strip (brand, section tabs, system state) and the instrument rail
export function TacticalSidebar({ page, setPage, appState, stats, speedHistory, theme, sysInfo }) {
  const canvasRef = React.useRef(null);

  // Speed history as bars: the newest on the right, the last one in the accent
  React.useEffect(() => {
    const c = canvasRef.current;
    const box = c && prepare(c, RAIL_GRAPH_H);
    if (!box) return;
    const { ctx, w } = box;
    const pts = speedHistory.slice(-RAIL_GRAPH_BARS);
    while (pts.length < RAIL_GRAPH_BARS) pts.unshift(0);
    const maxV = Math.max(...pts, 1);
    const step = w / RAIL_GRAPH_BARS;
    pts.forEach((v, i) => {
      const h = Math.max(1, Math.round((v / maxV) * (RAIL_GRAPH_H - 2)));
      const live = i === pts.length - 1 && v > 0;
      ctx.fillStyle = live ? themeRgba('--accent-rgb', 1) : themeRgba('--t2-rgb', v > 0 ? 0.55 : 0.25);   // a canvas can't resolve var()
      ctx.fillRect(Math.round(i * step), RAIL_GRAPH_H - h, Math.max(1, Math.floor(step) - 1), h);
    });
  }, [speedHistory, theme]);   // the bars' colours are the theme's

  const currentSpeed = speedHistory.length ? speedHistory[speedHistory.length - 1] : 0;
  const peak = Math.max(...speedHistory, 1);
  const lit = currentSpeed > 0 ? Math.max(1, Math.round((currentSpeed / peak) * GAUGE_SEGMENTS)) : 0;
  const [speedNum, speedUnit] = fmtSpeed(currentSpeed).split(' ');
  const trouble = !sysInfo.ffmpeg || appState === 'error';
  const statusText = !sysInfo.ffmpeg ? 'FFMPEG MISSING' : appState === 'error' ? 'LAST DL FAILED' : 'ALL SYSTEMS NOMINAL';
  const [dbNum, dbUnit] = fmtBytes(stats.total_size_bytes || 0).split(' ');

  return (
    <>
      <header className={'tac-head' + (lit ? ' live' : '')}>
        <div className="tac-head-scan" aria-hidden="true" />
        <div className="tac-brand">
          <img src="assets/mellow.ico" className="tac-brand-img" alt="" onError={(e) => { e.target.style.display = 'none'; }} />
          <div className="tac-brand-text">
            <div className="tac-brand-name">MELLOW<span>DLP</span></div>
            <div className="tac-brand-sub">OPS CONSOLE // {sysInfo.app_version ? 'v' + sysInfo.app_version : '—'}</div>
          </div>
        </div>

        <nav className="tac-tabs" aria-label="Sections">
          {PAGES.map((p, i) => (
            <button
              type="button"
              key={p.id}
              className={'tac-tab nav-item' + (page === p.id ? ' on' : '') + (p.lake && !PAGES[i - 1].lake ? ' tac-tab-gap' : '')}
              aria-current={page === p.id ? 'page' : undefined}
              title={p.label + ' — key ' + (i + 1)}
              onClick={() => setPage(p.id)}
            >
              <span className="tac-tab-num">{p.num}</span>
              <span className="tac-tab-icon" dangerouslySetInnerHTML={{ __html: SVG[p.icon] }} />
              <span className="tac-tab-label">{p.label}</span>
            </button>
          ))}
        </nav>

        <div className={'tac-annun' + (trouble ? ' warn' : '')} title={'System status: ' + statusText}>
          <div className="tac-annun-cap">SYS STATUS</div>
          <div className="tac-annun-state"><i className="tac-lamp" /><span>{statusText}</span></div>
        </div>
      </header>

      <aside className="tac-rail" aria-label="Telemetry">
        <div className="tac-rail-cap">TLM</div>

        <div className={'tac-gauge' + (lit ? ' live' : '')} title="Download speed, against this session's peak">
          <div className="tac-rail-label">DL SPEED</div>
          <div className="tac-gauge-segs" aria-hidden="true">
            {Array.from({ length: GAUGE_SEGMENTS }, (_, i) => (
              <i key={i} className={'tac-seg' + (GAUGE_SEGMENTS - i <= lit ? ' on' : '')} />
            ))}
          </div>
          <div className="tac-gauge-val">{speedNum}<span>{speedUnit}</span></div>
        </div>

        <div className="tac-rail-graph" title="Download speed, last samples">
          <canvas ref={canvasRef} />
        </div>

        {/* keyed by their value: a readout that changes ticks (tactical.css tac-tick) */}
        <div className="tac-read" title="Downloads recorded">
          <div className="tac-rail-label">RECORDS</div>
          <div className="tac-read-val" key={stats.total_downloads || 0}>{(stats.total_downloads || 0).toLocaleString()}</div>
        </div>
        <div className="tac-read" title="Size of everything recorded">
          <div className="tac-rail-label">TOTAL DB</div>
          <div className="tac-read-val" key={dbNum + dbUnit}>{dbNum}<span>{dbUnit}</span></div>
        </div>
        <div className="tac-read" title="Playlists the library tracks">
          <div className="tac-rail-label">LIBRARY</div>
          <div className="tac-read-val" key={stats.library_playlists || 0}>{stats.library_playlists || 0}</div>
        </div>

        {/* The rail is 92 px wide: too narrow for a mascot to be seen (it was a 71 px box), so the
            scale runs to the bottom; Tactical's Mellow is on the splash */}
        <div className="tac-rail-fill" aria-hidden="true" />
      </aside>
    </>
  );
}

// The TopBar slot: the command bar under the header (where you are, GUIDE, the clock)
export function TacticalTopBar({ page, onGuide }) {
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

  const meta = PAGES.find(p => p.id === page) || PAGES[0];

  return (
    <div className="tac-cmd">
      <div className="tac-cmd-sec" key={meta.id}>SEC {meta.num}</div>
      <div className="tac-cmd-path">
        MELLOW <i>/</i> <b>{meta.path}</b> <i>/</i> {meta.role}
      </div>
      <div className="tac-cmd-ticks" aria-hidden="true" />
      <div className="tac-cmd-keys" title="Press ? for every shortcut">
        <kbd>1</kbd>–<kbd>6</kbd> SECTION <kbd>?</kbd> KEYS
      </div>
      {onGuide && (
        <button type="button" className="tac-cmd-guide topbar-guide" onClick={onGuide}
          title="What each part of this page does (G)">
          ? GUIDE <kbd>G</kbd>
        </button>
      )}
      <div className="tac-cmd-date">{date}</div>
      <div className="tac-cmd-time">{time}</div>
      <div className="tac-cmd-opr">ADMIN</div>
    </div>
  );
}

// The PageFrame slot: the page sits in a bracketed frame; a line sweeps it when the section changes
export function TacticalPageFrame({ page, children }) {
  return (
    <div className="tac-frame" data-page={page}>
      {children}
      <div className="tac-frame-sweep" key={page} aria-hidden="true" />
    </div>
  );
}

// One cell of the annunciator row: a caption over... beside its value
function Cell({ cap, lamp, className, children, ...rest }) {
  return (
    <div className={'sb-seg tac-cell' + (className ? ' ' + className : '')} {...rest}>
      {lamp && <i className={'tac-lamp ' + lamp} />}
      {cap && <span className="tac-cell-cap">{cap}</span>}
      <span className="tac-cell-val">{children}</span>
    </div>
  );
}

// The StatusBar slot: an annunciator row (link, yt-dlp, ffmpeg, disk, the update offer, speed, folder)
export function TacticalStatusBar({ sysInfo, speedHistory, theme, config, appUpdate, onAppUpdate, ffmpegInstall, onGetFfmpeg }) {
  const canvasRef = React.useRef(null);

  // Speed history as a stepped line (a strip chart)
  React.useEffect(() => {
    const c = canvasRef.current;
    const box = c && prepare(c, STATUS_GRAPH_H);
    if (!box) return;
    const { ctx, w } = box;
    const pts = speedHistory.length ? speedHistory : Array(60).fill(0);
    const maxV = Math.max(...pts, 1);
    const step = w / pts.length;
    ctx.strokeStyle = themeRgba('--t2-rgb', 0.8);
    ctx.lineWidth = 1;
    ctx.beginPath();
    pts.forEach((v, i) => {
      const y = Math.round(STATUS_GRAPH_H - 1 - (v / maxV) * (STATUS_GRAPH_H - 2)) + 0.5;
      if (i === 0) ctx.moveTo(0, y);
      else ctx.lineTo(i * step, y);
      ctx.lineTo((i + 1) * step, y);
    });
    ctx.stroke();
  }, [speedHistory, theme]);   // the line's colour is the theme's

  const currentSpeed = speedHistory.length ? speedHistory[speedHistory.length - 1] : 0;
  const isActive = currentSpeed > 0;

  return (
    <div className="statusbar tac-status">
      <Cell cap="LINK" lamp={isActive ? 'live' : 'idle'} className={isActive ? 'tac-cell-live' : ''}>
        {isActive ? 'DOWNLOADING' : 'IDLE'}
      </Cell>
      <Cell cap="YT-DLP">{sysInfo.ytdlp_version || '—'}</Cell>
      {ffmpegInstall ? (
        <Cell cap="FFMPEG" lamp="warn" className="sb-update" title="Downloading and checking ffmpeg">
          {ffmpegInstall.stage === 'downloading' ? ffmpegInstall.pct + '%' : 'INSTALLING…'}
        </Cell>
      ) : !sysInfo.ffmpeg && sysInfo.ffmpeg_installable ? (
        <Cell lamp="err" className="sb-update sb-ffmpeg-get" onClick={onGetFfmpeg}
          title="ffmpeg merges, converts and trims. Click to download it into MellowDLP (checked against its published checksum)">
          FFMPEG MISSING — GET IT
        </Cell>
      ) : (
        <Cell cap="FFMPEG" lamp={sysInfo.ffmpeg ? 'ok' : 'err'} title={sysInfo.ffmpeg
          ? (sysInfo.ffmpeg_path || 'ffmpeg found')
          : (sysInfo.ffmpeg_install_note || 'ffmpeg is needed to merge, convert and trim.')}>
          {sysInfo.ffmpeg ? 'OK' : 'MISSING'}
        </Cell>
      )}
      {sysInfo.disk_free_bytes != null && (
        <Cell cap={sysInfo.disk_low ? 'DISK LOW' : 'DISK'} lamp={sysInfo.disk_low ? 'err' : 'ok'}
          className={sysInfo.disk_low ? 'tac-cell-err' : ''} title="Free space on the download drive">
          {fmtBytes(sysInfo.disk_free_bytes)} FREE
        </Cell>
      )}
      {appUpdate && (
        <Cell className="sb-update" onClick={onAppUpdate}
          title={appUpdate.can_install
            ? 'Download, check and install MellowDLP ' + appUpdate.latest + ', then restart'
            : (appUpdate.install_note || 'Open the release page')}>
          ⬆ MELLOWDLP {appUpdate.latest} — {appUpdate.can_install ? 'UPDATE' : 'GET IT'}
        </Cell>
      )}
      <div className="sb-graph tac-status-graph" title="Download speed">
        <canvas ref={canvasRef} />
      </div>
      <Cell cap="OUT" className="sb-path" title={config.output_dir || undefined}>
        {config.output_dir || '—'}
      </Cell>
    </div>
  );
}
