// App chrome: sidebar navigation, top bar, bottom status bar.
'use strict';

import { fmtBytes, fmtSpeed } from '../lib/util.js';
import { SVG } from './icons.jsx';
import { Mascot } from './common.jsx';
import {
  MASCOT_DJ, MASCOT_VIBING, MASCOT_CHILLING,
  MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE, MASCOT_TROUBLESHOOTING_SAFE,
} from '../lib/mascots.js';

export function Sidebar({ page, setPage, appState, stats, speedHistory, sysInfo }) {
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

export function TopBar({ page }) {
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

export function StatusBar({ sysInfo, speedHistory, config, onSwitchLayout }) {
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
      <div className="sb-seg" title={sysInfo.ffmpeg
        ? (sysInfo.ffmpeg_path || 'ffmpeg found')
        : 'ffmpeg is needed to merge, convert and trim. Windows: winget install Gyan.FFmpeg'}>
        <div className={'sb-dot' + (sysInfo.ffmpeg ? ' ok' : ' err')} />
        FFmpeg {sysInfo.ffmpeg ? 'OK' : 'MISSING'}
      </div>
      {sysInfo.disk_free_bytes != null && (
        <div className="sb-seg" title="Free space on the download drive"
          style={sysInfo.disk_low ? { color: 'var(--red)' } : undefined}>
          <div className={'sb-dot' + (sysInfo.disk_low ? ' err' : ' ok')} />
          {sysInfo.disk_low ? 'DISK LOW ' : 'DISK '}{fmtBytes(sysInfo.disk_free_bytes)} FREE
        </div>
      )}
      <div className="sb-graph">
        <canvas ref={canvasRef} />
      </div>
      {onSwitchLayout && (
        <div className="sb-seg sb-layout" title="Switch to the Studio layout (L)" onClick={() => onSwitchLayout('studio')}>
          ⇄ STUDIO LAYOUT
        </div>
      )}
      <div className="sb-seg sb-path">
        {config.output_dir || '—'}
      </div>
    </div>
  );
}
