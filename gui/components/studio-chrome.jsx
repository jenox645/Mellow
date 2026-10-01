// Studio layout chrome: one sidebar with the navigation, what is downloading
// right now (from any page), system health and the switch back to Classic.
'use strict';

import { fmtBytes, fmtEta, fmtSpeed } from '../lib/util.js';
import { Ico } from './icons.jsx';
import { Mascot } from './common.jsx';
import {
  MASCOT_DJ, MASCOT_VIBING, MASCOT_CHILLING, MASCOT_TIRED,
  MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE, MASCOT_TROUBLESHOOTING_SAFE,
} from '../lib/mascots.js';

const NAV_GROUPS = [
  { label: 'Library', items: [
    { id: 'feed', label: 'Feed', icon: 'arrow_down' },
    { id: 'queue', label: 'Queue', icon: 'list' },
    { id: 'vault', label: 'Vault', icon: 'archive' },
  ] },
  { label: 'Insights', items: [
    { id: 'analytics', label: 'Analytics', icon: 'bars' },
    { id: 'signal', label: 'Signal API', icon: 'terminal' },
    { id: 'config', label: 'Config', icon: 'sliders' },
  ] },
];

const PAGE_MASCOT = {
  feed: MASCOT_VIBING,
  queue: MASCOT_CHILLING,
  vault: MASCOT_COMFY_SAFE || MASCOT_CHILLING,
  analytics: MASCOT_CHILLING,
  signal: MASCOT_SUCCESS_SAFE || MASCOT_VIBING,
  config: MASCOT_TROUBLESHOOTING_SAFE || MASCOT_VIBING,
};

// What is running now. Click it to open the Queue.
function NowCard({ page, activeJobs, isPaused, stats, onOpen, onPause, onResume }) {
  const jobs = Object.values(activeJobs || {});
  const job = jobs[0];
  const pct = job ? Math.max(0, Math.min(100, job.pct || 0)) : 0;
  const mascot = job ? (isPaused ? (MASCOT_TIRED || MASCOT_CHILLING) : MASCOT_DJ) : PAGE_MASCOT[page] || MASCOT_VIBING;
  const toggle = (e) => { e.stopPropagation(); if (isPaused) onResume(); else onPause(); };

  return (
    <div className={'s-now' + (job ? ' busy' : '') + (isPaused ? ' paused' : '')} onClick={onOpen}
      title={job ? 'Open the Queue' : undefined}>
      <div className="s-now-mascot"><Mascot key={page + (job ? '-busy' : '')} src={mascot} className="s-now-img" wrapClass="s-now-svg" /></div>
      {job ? (
        <>
          <div className="s-now-state">
            {isPaused ? 'Paused' : 'Downloading'}
            {jobs.length > 1 && <span className="s-now-more"> · {jobs.length} running</span>}
          </div>
          <div className="s-now-title" title={job.title || job.label || ''}>{job.title || job.label || 'Starting…'}</div>
          <div className="s-bar"><div className="s-bar-fill" style={{ width: pct + '%' }} /></div>
          <div className="s-now-meta">
            <span>{pct.toFixed(0)}%</span>
            {!isPaused && job.speed > 0 && <span>{fmtSpeed(job.speed)}</span>}
            {!isPaused && job.eta > 0 && <span>{fmtEta(job.eta)}</span>}
            <button className="s-icon-btn" onClick={toggle} title={isPaused ? 'Resume' : 'Pause all'}>
              <Ico name={isPaused ? 'play_fill' : 'pause'} />
            </button>
          </div>
          <div className="s-now-pct">{pct.toFixed(0)}%</div>
        </>
      ) : (
        <>
          <div className="s-now-state">All quiet</div>
          <div className="s-now-sub">
            {(stats.total_downloads || 0).toLocaleString()} downloads · {fmtBytes(stats.total_size_bytes || 0)}
          </div>
        </>
      )}
    </div>
  );
}

export function StudioSidebar({
  page, setPage, activeJobs, isPaused, stats, sysInfo, onPause, onResume, onSwitchLayout,
}) {
  const running = Object.keys(activeJobs || {}).length;
  return (
    <aside className="s-side">
      <div className="s-brand">
        <span className="s-brand-mark"><Ico name="arrow_down" size={16} /></span>
        <span className="s-brand-name">Mellow</span>
        {sysInfo.app_version && <span className="s-brand-ver">v{sysInfo.app_version}</span>}
      </div>

      <nav className="s-nav">
        {NAV_GROUPS.map((g, gi) => (
          <div key={g.label} className="s-nav-group">
            <div className="s-nav-label">{g.label}</div>
            {g.items.map((it, i) => (
              <button
                key={it.id}
                className={'s-nav-item' + (page === it.id ? ' active' : '')}
                onClick={() => setPage(it.id)}
                title={it.label + '  (' + (gi * 3 + i + 1) + ')'}
              >
                <Ico name={it.icon} size={18} />
                <span className="s-nav-text">{it.label}</span>
                {it.id === 'queue' && running > 0 && <span className="s-nav-badge">{running}</span>}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="s-side-spacer" />

      <NowCard page={page} activeJobs={activeJobs} isPaused={isPaused} stats={stats}
        onOpen={() => setPage('queue')} onPause={onPause} onResume={onResume} />

      <div className="s-health">
        <div className="s-health-row" title={'yt-dlp ' + (sysInfo.ytdlp_version || '')}>
          <span className="s-dot ok" /><span className="s-health-text">yt-dlp {sysInfo.ytdlp_version || '—'}</span>
        </div>
        <div className={'s-health-row' + (sysInfo.ffmpeg ? '' : ' warn')}
          title={sysInfo.ffmpeg ? (sysInfo.ffmpeg_path || 'ffmpeg found')
            : 'ffmpeg is needed to merge, convert and trim. Windows: winget install Gyan.FFmpeg'}
          onClick={sysInfo.ffmpeg ? undefined : () => setPage('config')}>
          <span className={'s-dot ' + (sysInfo.ffmpeg ? 'ok' : 'err')} />
          <span className="s-health-text">{sysInfo.ffmpeg ? 'FFmpeg ready' : 'FFmpeg missing'}</span>
        </div>
        {sysInfo.disk_free_bytes != null && (
          <div className={'s-health-row' + (sysInfo.disk_low ? ' warn' : '')} title="Free space on the download drive">
            <span className={'s-dot ' + (sysInfo.disk_low ? 'err' : 'ok')} />
            <span className="s-health-text">{fmtBytes(sysInfo.disk_free_bytes)} free</span>
          </div>
        )}
      </div>

      <button className="s-layout-switch" onClick={() => onSwitchLayout('classic')} title="Switch to the Classic layout (L)">
        <Ico name="layout" /> <span className="s-nav-text">Classic layout</span>
      </button>
    </aside>
  );
}
