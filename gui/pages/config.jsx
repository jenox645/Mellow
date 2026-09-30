// CONFIG page — storage, auth, network, database, behavior, danger zone.
'use strict';

import { API } from '../lib/api.js';
import { fmtBytes } from '../lib/util.js';
import { Toggle, Modal, Mascot } from '../components/common.jsx';
import { MASCOT_FRUSTRATED } from '../lib/mascots.js';

export function ConfigPage({ config, setConfig, showNotif, sysInfo, refreshStats }) {
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

  // Only the keys this page edits — sending the whole stale `local` copy
  // clobbered vault_playlists/webhooks changes made since the page mounted
  const CONFIG_PAGE_KEYS = [
    'output_dir', 'filename_template',
    'cookies_browser', 'cookies_browser_profile', 'cookies_file',
    'rate_limit', 'proxy', 'external_downloader',
    'concurrent_fragments', 'sleep_interval', 'retries',
    'write_metadata', 'extract_chapters',
    'ui_victory_animation', 'ui_victory_sync',
    'default_mode', 'default_quality', 'default_container', 'default_audio_format',
    'download_workers', 'auto_sync_enabled', 'auto_sync_default_interval',
    'update_check_on_launch', 'clipboard_watch', 'completion_sound',
  ];
  const NUMERIC_DEFAULTS = { concurrent_fragments: 4, sleep_interval: 0, retries: 3, download_workers: 1 };

  const handleSave = () => {
    const toSave = {};
    CONFIG_PAGE_KEYS.forEach(k => {
      if (local[k] === undefined) return;
      let v = local[k];
      if (k in NUMERIC_DEFAULTS) {
        const n = parseInt(v, 10);
        v = Number.isFinite(n) ? n : NUMERIC_DEFAULTS[k];
      }
      toSave[k] = v;
    });
    API.post('/api/config', toSave)
      .then(() => { setConfig(c => ({ ...c, ...toSave })); showNotif('Saved', 'Configuration updated', 'success'); })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const handleReset = () => {
    API.post('/api/config', {
      output_dir: '', cookies_browser: 'none', cookies_file: '', cookies_browser_profile: '',
      rate_limit: '', proxy: '', external_downloader: '',
      concurrent_fragments: 4, sleep_interval: 0, retries: 3,
      write_metadata: true, extract_chapters: true, filename_template: '',
    }).then(() => API.get('/api/config').then(c => { setLocal(c); setConfig(c); showNotif('Reset', 'Defaults restored', 'success'); }));
  };

  const browseFolder = () => {
    API.post('/api/browse-folder', {}).then(d => {
      if (!d.path) return;
      set('output_dir', d.path);
      API.post('/api/config', { output_dir: d.path }).catch(() => {});
    });
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

  // ── Backup / restore ────────────────────────────────────────────────────────
  const restoreInputRef = React.useRef(null);
  const [restoring, setRestoring] = React.useState(false);

  const handleRestoreFile = (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    setRestoring(true);
    fetch('/api/backup/restore', { method: 'POST', body: form })
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          showNotif('Backup Restored', (d.restored || []).join(' + ') + ' — restart recommended', 'success');
          API.get('/api/config').then(c => { setLocal(c); setConfig(c); }).catch(() => {});
          refreshStats && refreshStats();
        } else {
          showNotif('Restore Failed', d.error || 'Unknown error', 'error');
        }
      })
      .catch(err => showNotif('Restore Failed', err.message, 'error'))
      .finally(() => setRestoring(false));
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
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Download Archive File</div>
                  <div className="sl-sub">mellow_archive.txt — tracks downloaded items, import as URL list</div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t3)' }}>
                    {local.output_dir ? (local.output_dir.replace(/\\/g, '/').split('/').pop() || local.output_dir) + '/mellow_archive.txt' : 'mellow_archive.txt (in download folder)'}
                  </span>
                  <button className="btn btn-secondary btn-sm" onClick={() => {
                    const dir = local.output_dir;
                    if (dir) API.post('/api/open-folder', { path: dir }).catch(() => {});
                    else showNotif('No folder', 'Set a download path first', 'info');
                  }}>OPEN FOLDER</button>
                </div>
              </div>
            </div>
          </div>

          {/* DOWNLOAD DEFAULTS */}
          <div className="cfg-panel">
            <div className="cfg-ph">
              <span className="ptag">DEFAULTS</span>
              <span className="ptitle">DOWNLOAD DEFAULTS</span>
            </div>
            <div className="cfg-body">
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Default Mode</div>
                  <div className="sl-sub">Initial mode on the Feed page</div>
                </div>
                <div className="settings-ctrl">
                  <select className="sel" value={local.default_mode || 'video'} onChange={e => set('default_mode', e.target.value)}>
                    <option value="video">Video</option>
                    <option value="audio">Audio only</option>
                  </select>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Default Quality</div>
                  <div className="sl-sub">Preselected video quality</div>
                </div>
                <div className="settings-ctrl">
                  <select className="sel" value={local.default_quality || '1080p'} onChange={e => set('default_quality', e.target.value)}>
                    {['best', '4k', '1080p', '720p', '480p', '360p'].map(q => (
                      <option key={q} value={q}>{q.toUpperCase()}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Default Container</div>
                  <div className="sl-sub">Preselected video container</div>
                </div>
                <div className="settings-ctrl">
                  <select className="sel" value={local.default_container || 'mp4'} onChange={e => set('default_container', e.target.value)}>
                    {['mp4', 'mkv', 'webm'].map(c => <option key={c} value={c}>{c.toUpperCase()}</option>)}
                  </select>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Default Audio Format</div>
                  <div className="sl-sub">Preselected format for AUDIO ONLY</div>
                </div>
                <div className="settings-ctrl">
                  <select className="sel" value={local.default_audio_format || 'mp3'} onChange={e => set('default_audio_format', e.target.value)}>
                    {['mp3', 'aac', 'flac', 'm4a', 'opus', 'wav'].map(f => <option key={f} value={f}>{f.toUpperCase()}</option>)}
                  </select>
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
                  <div className="sl-sub">
                    Uses your browser login session — <span style={{ color: 'var(--amber)' }}>close browser before use if locked</span>
                  </div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <select className="sel" value={local.cookies_browser || 'none'} onChange={e => set('cookies_browser', e.target.value)}>
                    {['none','chrome','firefox','edge','brave','safari'].map(b => (
                      <option key={b} value={b}>{b === 'none' ? 'Disabled' : b.charAt(0).toUpperCase() + b.slice(1)}</option>
                    ))}
                  </select>
                  {local.cookies_browser && local.cookies_browser !== 'none' && (
                    <span style={{ fontSize: 9, color: 'var(--green)', fontFamily: 'Share Tech Mono, monospace' }}>● ACTIVE</span>
                  )}
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Browser Profile Path</div>
                  <div className="sl-sub">Optional: path to profile folder (e.g. …\Brave-Browser\User Data\Default)</div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <input className="inp-sm" style={{ width: 200 }} value={local.cookies_browser_profile || ''} onChange={e => set('cookies_browser_profile', e.target.value)} placeholder="Leave empty for auto-detect" />
                  <button className="btn btn-secondary btn-sm" onClick={() => API.post('/api/browse-folder', {}).then(d => { if (d.path) set('cookies_browser_profile', d.path); })}>BROWSE</button>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Cookies File</div>
                  <div className="sl-sub">Export via "Get cookies.txt LOCALLY" extension — used when Browser is Disabled</div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <input className="inp-sm" style={{ width: 160 }} value={local.cookies_file || ''} onChange={e => set('cookies_file', e.target.value)} placeholder="cookies.txt" />
                  <button className="btn btn-secondary btn-sm" onClick={browseCookies}>BROWSE</button>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Auth Status</div>
                  <div className="sl-sub">Current authentication method active</div>
                </div>
                <div className="settings-ctrl">
                  {(local.cookies_browser && local.cookies_browser !== 'none')
                    ? <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--green)' }}>Browser cookies ({local.cookies_browser}){local.cookies_browser_profile ? ' · custom profile' : ''}</span>
                    : local.cookies_file
                    ? <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--cyan)' }}>Cookies file active</span>
                    : <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)' }}>No auth — public videos only</span>
                  }
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
                      onChange={e => set(f.key, e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* BEHAVIOR */}
          <div className="cfg-panel">
            <div className="cfg-ph">
              <span className="ptag">BEHAVIOR</span>
              <span className="ptitle">APP BEHAVIOR</span>
            </div>
            <div className="cfg-body">
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Concurrent Downloads</div>
                  <div className="sl-sub">Jobs running at once — 1 is gentlest on rate limits</div>
                </div>
                <div className="settings-ctrl">
                  <select className="sel" value={local.download_workers || 1} onChange={e => set('download_workers', parseInt(e.target.value, 10))}>
                    {[1, 2, 3].map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Auto-Sync Vault Folders</div>
                  <div className="sl-sub">Periodically sync linked folders in the background</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.auto_sync_enabled === true} onChange={v => set('auto_sync_enabled', v)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Auto-Sync Interval</div>
                  <div className="sl-sub">Default cadence — folders can override it in their sync options</div>
                </div>
                <div className="settings-ctrl">
                  <select className="sel" value={local.auto_sync_default_interval || 'daily'} onChange={e => set('auto_sync_default_interval', e.target.value)}>
                    <option value="6h">Every 6 hours</option>
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                  </select>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Clipboard Watcher</div>
                  <div className="sl-sub">Suggest analyzing URLs you copied when the window regains focus</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.clipboard_watch !== false} onChange={v => set('clipboard_watch', v)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Update Check on Launch</div>
                  <div className="sl-sub">Once a day, warn when yt-dlp is outdated</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.update_check_on_launch !== false} onChange={v => set('update_check_on_launch', v)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Completion Sound</div>
                  <div className="sl-sub">Soft chime when a download finishes</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.completion_sound === true} onChange={v => set('completion_sound', v)} />
                </div>
              </div>
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
                  <div className="sl-name">Backup &amp; Restore</div>
                  <div className="sl-sub">Zip of config + analytics DB; restore keeps .pre-restore copies</div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-secondary btn-sm" onClick={() => { window.location.href = '/api/backup'; }}>
                    ⬇ BACKUP
                  </button>
                  <button className="btn btn-secondary btn-sm" disabled={restoring}
                    onClick={() => restoreInputRef.current && restoreInputRef.current.click()}>
                    {restoring ? 'RESTORING...' : '⬆ RESTORE'}
                  </button>
                  <input ref={restoreInputRef} type="file" accept=".zip" style={{ display: 'none' }} onChange={handleRestoreFile} />
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

          {/* UI PREFERENCES */}
          <div className="cfg-panel">
            <div className="cfg-ph">
              <span className="ptag" style={{ background: 'var(--purple)' }}>UI</span>
              <span className="ptitle">UI PREFERENCES</span>
            </div>
            <div className="cfg-body">
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Playlist Completion Animation</div>
                  <div className="sl-sub">Show victory overlay when a feed playlist finishes</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.ui_victory_animation !== false} onChange={v => set('ui_victory_animation', v)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Sync Completion Animation</div>
                  <div className="sl-sub">Show victory overlay when a vault sync finishes</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.ui_victory_sync !== false} onChange={v => set('ui_victory_sync', v)} />
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
