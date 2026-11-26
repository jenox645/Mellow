// App chrome: sidebar navigation, top bar, bottom status bar.
'use strict';

import { fmtBytes, fmtEta, fmtSpeed, logScale, shortFolder, themeRgba } from '../lib/util.js';
import { DISK_RULER_MAX_BYTES, DISK_RULER_MIN_BYTES, STATUS_SPARK_SAMPLES } from '../lib/constants.js';
import { SVG } from './icons.jsx';
import { Mascot } from './common.jsx';
import {
  MASCOT_DJ, MASCOT_VIBING, MASCOT_CHILLING,
  MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE, MASCOT_TROUBLESHOOTING_SAFE,
} from '../lib/mascots.js';

export function Sidebar({ page, setPage, appState, stats, speedHistory, theme, sysInfo }) {
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
    ctx.strokeStyle = themeRgba('--accent-rgb', 0.6);   // a canvas can't resolve var()
    ctx.lineWidth = 1;
    ctx.beginPath();
    pts.forEach((v, i) => {
      const x = (i / (pts.length - 1)) * w;
      const y = h - (v / maxV) * h * 0.85 - h * 0.05;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  }, [speedHistory, theme]);   // the line's colour is the theme's

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
  const currentSpeed = speedHistory.length ? speedHistory[speedHistory.length - 1] : 0;

  return (
    <aside className="sidebar">
      <div className="logo-area">
        <div className="logo">
          <img src="assets/mellow.ico" className="logo-img" alt="M" onError={(e) => { e.target.style.display = 'none'; }} />
          <span className="logo-text">MELLOW</span>
        </div>
        <div className="logo-sub">SYSTEM // {sysInfo.app_version ? 'v' + sysInfo.app_version : '—'}</div>
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

      <div className={mascotAreaClass}>
        <Mascot key={page} src={mascotSrc} className="mascot-img" />
      </div>

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

const PAGE_META = {
  feed:      { path: 'COMMAND', ja: 'ダッシュボード', isLake: false },
  queue:     { path: 'QUEUE', ja: 'キュー管理', isLake: false },
  vault:     { path: 'VAULT', ja: 'メディアボールト', isLake: false },
  analytics: { path: 'ANALYTICS', ja: 'データレイク', isLake: true },
  signal:    { path: 'SIGNAL API', ja: 'APIシグナル', isLake: true },
  config:    { path: 'CONFIG', ja: 'システム設定', isLake: true },
};

export function TopBar({ page, onGuide }) {
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
      {onGuide && (
        <div className="topbar-guide" onClick={onGuide} title="What each part of this page does (G)">? GUIDE</div>
      )}
      <div className="topbar-time">{time}</div>
      <div className="topbar-tag">{date}</div>
      <div className="topbar-tag amber">ADMIN</div>
    </div>
  );
}

// ── Status bar ───────────────────────────────────────────────────────────────
// Says something only when it matters. Idle: one quiet line (the link lamp, the download folder, the
// free disk on a ruler, three marks for yt-dlp / FFmpeg / the JS runtime). Downloading: the live
// strip (what's downloading, items left, the speed as a scrolling trace, the ETA, a progress line
// along the window's bottom edge). Anything that needs the user (FFmpeg missing, a newer yt-dlp or
// MellowDLP, no JS runtime, a low disk) speaks up as its action, idle or not.

const SPARK_W = 150, SPARK_H = 18;

// A diamond lamp: hollow when idle, filled and pinging while receiving
function Lamp() {
  return (
    <svg className="sb-lamp" viewBox="0 0 9 9" aria-hidden="true">
      <path className="ping" d="M4.5 .5 8.5 4.5 4.5 8.5 .5 4.5Z" />
      <path className="core" d="M4.5 .5 8.5 4.5 4.5 8.5 .5 4.5Z" />
    </svg>
  );
}

// Hatching for an action (and the disk's low zone)
function Hatch() {
  return (
    <svg className="hatch" viewBox="0 0 10 16" preserveAspectRatio="none" aria-hidden="true">
      {[-12, -6, 0, 6, 12].map(x => <line key={x} x1={x} y1="16" x2={x + 10} y2="0" stroke="currentColor" strokeWidth="1.2" />)}
    </svg>
  );
}

// The speed: the last samples in a frame with corner marks. Each new sample scrolls the trace one
// step left (the group remounts with `seq`, starting one step to the right).
function SpeedTrace({ samples, seq }) {
  const pts = samples.slice(-STATUS_SPARK_SAMPLES);
  const max = Math.max(...pts, 1);
  const step = SPARK_W / (STATUS_SPARK_SAMPLES - 1);
  const x0 = SPARK_W - (pts.length - 1) * step;
  const xy = pts.map((v, i) => [x0 + i * step, SPARK_H - 2 - (v / max) * (SPARK_H - 5)]);
  const line = xy.map(([x, y]) => x.toFixed(1) + ',' + y.toFixed(1)).join(' ');
  const c = 3;   // corner mark length
  return (
    <svg className="sb-spark" viewBox={`0 0 ${SPARK_W} ${SPARK_H}`} aria-hidden="true">
      <path className="frame" d={`M0 ${c}V0H${c}M${SPARK_W - c} 0H${SPARK_W}V${c}M${SPARK_W} ${SPARK_H - c}V${SPARK_H}H${SPARK_W - c}M${c} ${SPARK_H}H0V${SPARK_H - c}`} />
      <line className="base" x1="0" x2={SPARK_W} y1={SPARK_H - 1.5} y2={SPARK_H - 1.5} />
      <svg x="0" y="0" width={SPARK_W} height={SPARK_H} overflow="hidden">
        <g className="run" key={seq} style={{ '--step': step + 'px' }}>
          <polygon className="area" points={`${xy[0][0]},${SPARK_H - 1.5} ${line} ${SPARK_W},${SPARK_H - 1.5}`} />
          <polyline className="trace" points={line} />
        </g>
      </svg>
    </svg>
  );
}

// Free disk on a log ruler: a tick per decade (0.1 · 1 · 10 · 100 GB · 1 TB) and a red mark where
// "low" starts; when it is low, the zone under the mark is hatched
function DiskRuler({ free, low, isLow }) {
  const W = 56, at = b => logScale(b, DISK_RULER_MIN_BYTES, DISK_RULER_MAX_BYTES) * W;
  const lowX = low ? at(low) : 0;
  return (
    <svg className="sb-ruler" viewBox={`0 0 ${W} 12`} aria-hidden="true">
      <defs>
        <pattern id="sb-hatch" className="hz" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="3" stroke="currentColor" strokeWidth="1.2" />
        </pattern>
      </defs>
      <rect className="trk" x="0" y="4" width={W} height="3" />
      <rect className="bar" x="0" y="4" width={W} height="3" style={{ '--v': at(free) / W }} />
      {[0, 1, 2, 3, 4].map(d => <line key={d} className="tk" x1={d * W / 4 || 0.5} x2={d * W / 4 || 0.5} y1="8" y2="12" />)}
      {lowX > 0 && <>{isLow && <rect className="low" x="0" y="3" width={lowX} height="5" />}
        <line className="lowmk" x1={lowX} x2={lowX} y1="1" y2="10" /></>}
    </svg>
  );
}

export function StatusBar({
  sysInfo, speedHistory, config, appUpdate, onAppUpdate, ffmpegInstall, onGetFfmpeg,
  appState, dlState, isPaused, activeJobs, playlistTotalCount, playlistCompletedCount,
  ytdlpUpdate, onUpdateYtdlp, onOpenFolder, onOpenConfig,
}) {
  // Count the samples, so the trace scrolls once per new one
  const seq = React.useRef(0);
  const lastSamples = React.useRef(speedHistory);
  if (lastSamples.current !== speedHistory) { lastSamples.current = speedHistory; seq.current += 1; }

  const live = (appState === 'downloading' || appState === 'processing') && !!dlState;
  const processing = live && (appState === 'processing' || dlState.status === 'processing');
  const paused = live && isPaused;
  const speed = live && !paused ? (dlState.speed || 0) : 0;
  const pct = live ? (processing ? 100 : Math.max(0, Math.min(100, dlState.pct || 0))) : 0;
  const jobs = Object.keys(activeJobs || {}).length;
  const total = playlistTotalCount || 0;
  const done = Math.min(playlistCompletedCount || 0, total);

  const home = config.output_dir || '';
  const folder = (live && dlState.job_folder) || home;
  const elsewhere = !!(live && dlState.job_folder && dlState.job_folder !== home);

  // What needs the user: each is its own action, the most urgent first
  const actions = [];
  if (ffmpegInstall) {
    actions.push({ key: 'ffmpeg', kind: 'warn', busy: true, pct: ffmpegInstall.stage === 'downloading' ? ffmpegInstall.pct || 0 : 100,
      text: 'FFMPEG ' + (ffmpegInstall.stage === 'downloading' ? (ffmpegInstall.pct || 0) + '%' : 'INSTALLING…'),
      title: 'Downloading and checking FFmpeg' });
  } else if (sysInfo.ffmpeg === false) {
    actions.push(sysInfo.ffmpeg_installable
      ? { key: 'ffmpeg', kind: 'err', text: 'FFMPEG MISSING — GET IT', onClick: onGetFfmpeg, cls: 'sb-ffmpeg-get',
        title: 'FFmpeg merges, converts and trims. Click to download it into MellowDLP (checked against its published checksum)' }
      : { key: 'ffmpeg', kind: 'err', text: 'FFMPEG MISSING', onClick: onOpenConfig,
        title: (sysInfo.ffmpeg_install_note || 'FFmpeg is needed to merge, convert and trim.') + ' Click for Config.' });
  }
  if (sysInfo.disk_low && sysInfo.disk_free_bytes != null && live) {
    actions.push({ key: 'disk', kind: 'err', text: 'DISK LOW — ' + fmtBytes(sysInfo.disk_free_bytes), onClick: () => onOpenFolder && onOpenFolder(folder),
      title: 'Little free space left on the download drive. Click to open the download folder' });
  }
  if (appUpdate) {
    actions.push({ key: 'app', kind: 'warn', text: '⬆ MELLOWDLP ' + appUpdate.latest + ' — ' + (appUpdate.can_install ? 'UPDATE' : 'GET IT'),
      onClick: onAppUpdate, title: appUpdate.can_install
        ? 'Download, check and install MellowDLP ' + appUpdate.latest + ', then restart'
        : (appUpdate.install_note || 'Open the release page') });
  }
  if (ytdlpUpdate) {
    actions.push({ key: 'ytdlp', kind: 'warn', text: 'YT-DLP ' + ytdlpUpdate.latest + ' — UPDATE', onClick: onUpdateYtdlp,
      title: 'yt-dlp ' + ytdlpUpdate.installed + ' → ' + ytdlpUpdate.latest + ': sites change, a newer yt-dlp keeps up' });
  }
  const js = sysInfo.js_runtime;
  const jsBad = 'js_runtime' in sysInfo && !(js && js.supported !== false);
  if (jsBad) {
    actions.push({ key: 'js', kind: 'warn', text: 'NO JS RUNTIME', onClick: onOpenConfig,
      title: 'YouTube needs a JavaScript runtime (Node.js, Deno…) to read some videos. Click for Config → JavaScript Runtime' });
  }

  const health = [
    ['yt-dlp', !!sysInfo.ytdlp_version, 'yt-dlp ' + (sysInfo.ytdlp_version || '—')],
    ['FFmpeg', sysInfo.ffmpeg !== false, 'FFmpeg ' + (sysInfo.ffmpeg ? (sysInfo.ffmpeg_path || 'found') : sysInfo.ffmpeg === false ? 'missing' : '—')],
    ['JS', !jsBad, 'JS runtime ' + (js ? js.name + (js.version ? ' ' + js.version : '') : jsBad ? 'missing' : '—')],
  ];
  const quietHealth = !actions.some(a => a.key === 'ffmpeg' || a.key === 'js');

  let i = 0;   // the cells' entrance stagger
  const cell = (cls, children, extra = {}) => (
    <div className={'sb-cell ' + cls} style={{ '--i': i++ }} {...extra}>{children}</div>
  );

  return (
    <div className={'statusbar sbc' + (live ? ' live' : '') + (processing ? ' processing' : '') + (paused ? ' paused' : '')}>
      <React.Fragment key={live ? 'live' : 'idle'}>
        {cell('sb-link' + (live ? (paused ? ' paused' : ' live') : ''), <>
          <Lamp />
          {!live ? 'IDLE' : paused ? 'PAUSED' : processing ? 'PROCESSING' : 'RECEIVING'}
          <span className="sb-ja">{!live ? '待機' : paused ? '一時停止' : processing ? '処理中' : '受信中'}</span>
        </>)}

        {live && total > 1 && done < total && cell('sb-items', <>
          <span className="sb-cap">ITEM</span>
          <span className="sb-num">{String(Math.min(done + 1, total)).padStart(String(total).length, '0')}</span>
          <span className="sb-cap">/ {total}</span>
        </>, { title: done + ' of ' + total + ' done' })}
        {live && cell('sb-pct', <span className="sb-num">{pct.toFixed(1)}%</span>)}
        {live && cell('sb-speed-cell', <>
          <SpeedTrace samples={speedHistory} seq={seq.current} />
          <span className="sb-speed"><span className="sb-num">{paused || processing ? '—' : fmtSpeed(speed).split(' ')[0]}</span>
            {!paused && !processing && <span className="sb-cap">{(fmtSpeed(speed).split(' ')[1] || '').toUpperCase()}</span>}</span>
        </>, { title: 'Download speed' })}
        {live && cell('sb-eta', <>
          <span className="sb-cap">ETA</span><span className="sb-num">{paused || processing ? '—' : fmtEta(dlState.eta)}</span>
        </>)}

        {live && cell('sb-title', <>
          <span title={dlState.current_item_title || ''}>{dlState.current_item_title || dlState.filename || 'Starting…'}</span>
          {jobs > 1 && <span className="sb-more" title={jobs + ' downloads running: the Queue lists them'}>+{jobs - 1} JOB{jobs > 2 ? 'S' : ''}</span>}
        </>)}
        {!live && <div className="sb-fill" />}

        {actions.map(a => (
          <button key={a.key} type="button" className={'sb-cell sb-act sb-update' + (a.kind === 'err' ? ' err' : '') + (a.busy ? ' busy' : '') + (a.cls ? ' ' + a.cls : '')}
            style={{ '--i': i++ }} title={a.title} onClick={a.onClick} disabled={a.busy}>
            <Hatch />{a.text}
            {a.busy && <span className="meter" style={{ '--p': a.pct }}><b /></span>}
          </button>
        ))}

        {!live && quietHealth && cell('sb-sys', <>
          <span className="sb-cap">SYS</span>
          {health.map(([k, ok]) => <span key={k} className={'mk' + (ok ? '' : ' bad')} />)}
        </>, { title: health.map(h => h[2]).join('\n'), 'aria-label': 'System: ' + health.map(h => h[2]).join(', ') })}

        {!live && sysInfo.disk_free_bytes != null && cell('sb-disk' + (sysInfo.disk_low ? ' low' : ''), <>
          <span className="sb-cap">{sysInfo.disk_low ? 'DISK LOW' : 'DISK'}</span>
          <DiskRuler free={sysInfo.disk_free_bytes} low={sysInfo.disk_low_bytes} isLow={sysInfo.disk_low} />
          <span className="sb-val">{fmtBytes(sysInfo.disk_free_bytes)}</span>
        </>, { title: 'Free space on the download drive (the ruler: 0.1 GB · 1 GB · 10 GB · 100 GB · 1 TB)' })}

        <button type="button" className={'sb-cell sb-out sb-path' + (elsewhere ? ' job' : '')} style={{ '--i': i++ }}
          title={folder} aria-label={'Open the download folder: ' + folder} onClick={() => folder && onOpenFolder && onOpenFolder(folder)}>
          <i aria-hidden="true" /><span className="sb-cap">OUT</span><span className="sb-val">{shortFolder(folder) || '—'}</span><i aria-hidden="true" />
        </button>
      </React.Fragment>

      {live && (
        <>
          <div className="sb-prog" style={{ '--p': pct }} aria-hidden="true">
            <div className="sb-prog-fill" />{processing && <div className="sb-prog-scan" />}
          </div>
          <div className="sb-head" style={{ '--p': pct }} aria-hidden="true" />
        </>
      )}
    </div>
  );
}
