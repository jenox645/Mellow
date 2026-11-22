// CONFIG page — storage, auth, network, database, behavior, danger zone.
// The logic is useConfigPage (config-logic.js); this file is Classic's view of it. A theme can
// register its own view of the page (gui/themes/slots.jsx, `pages: { config: … }`).
'use strict';

import { fmtBytes, themeCards } from '../lib/util.js';
import { Toggle, Modal, Mascot } from '../components/common.jsx';
import { ApiAccessPanel } from '../components/api-access.jsx';
import { MASCOT_FRUSTRATED } from '../lib/mascots.js';
import { AUDIO_FORMATS, AUDIO_QUALITIES, CONTAINERS, QUALITIES } from '../lib/constants.js';
import { useConfigPage } from './config-logic.js';

// The Config page: its logic, drawn by the theme's view (Classic's unless the theme has one)
export function ConfigPage({ View = ClassicConfigView, ...props }) {
  const cfg = useConfigPage(props);
  return <View {...cfg} />;
}

export function ClassicConfigView({
  showNotif, installAppUpdate, installFfmpeg, ffmpegInstall, showWhatsNew, sysInfo, local, set, handleSave,
  handleReset, browseFolder, namePreview, openArchiveFolder, browseCookiesProfile, browseCookies, testCookies,
  testingCookies, vacuuming, doVacuum, openLog, downloadBackup, restoreInputRef, restoring, handleRestoreFile,
  appUpdate, checkingApp, checkAppUpdate, updateInfo, checking, checkUpdate, updating, updateYtdlp, openReleasePage,
  currentTheme, pickTheme, dangerModal, setDangerModal, doPurge, setDesktopNotifications,
}) {
  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">システム設定 / SYSTEM CONFIG</div>
          <div className="vtitle"><span style={{ color: 'var(--t1)' }}>SYS</span> <span className="a">CONFIG</span></div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }} data-tour="config-save">
          <button className="btn btn-secondary btn-sm" onClick={handleReset}>RESET DEFAULTS</button>
          <button className="btn btn-primary btn-sm" onClick={handleSave}>SAVE CONFIG →</button>
        </div>
      </div>

      <div className="cfg-layout">
        {/* LEFT COLUMN */}
        <div>
          {/* STORAGE */}
          <div className="cfg-panel" data-tour="config-storage">
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
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t3)' }}>~/.mellow_dlp.duckdb</span>
                </div>
              </div>
              <div className="settings-row" data-tour="config-template">
                <div className="settings-label">
                  <div className="sl-name">Filename Template</div>
                  <div className="sl-sub">yt-dlp output template — a "/" makes subfolders</div>
                  {namePreview && (
                    <div className="sl-sub" title="A sample video, named with this template"
                      style={{ color: namePreview.ok ? 'var(--accent)' : 'var(--danger)', wordBreak: 'break-all' }}>
                      {namePreview.ok ? '→ ' + namePreview.example : '✕ ' + namePreview.error}
                    </div>
                  )}
                </div>
                <div className="settings-ctrl">
                  <input className="inp-sm" style={{ width: 220, borderColor: namePreview && !namePreview.ok ? 'var(--danger)' : undefined }}
                    value={local.filename_template || ''} onChange={e => set('filename_template', e.target.value)} placeholder="%(title)s [%(id)s].%(ext)s" />
                </div>
              </div>
              <div className="settings-row" data-tour="config-archive">
                <div className="settings-label">
                  <div className="sl-name">Download Archive File</div>
                  <div className="sl-sub">mellow_archive.txt — tracks downloaded items, import as URL list</div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t3)' }}>
                    {local.output_dir ? (local.output_dir.replace(/\\/g, '/').split('/').pop() || local.output_dir) + '/mellow_archive.txt' : 'mellow_archive.txt (in download folder)'}
                  </span>
                  <button className="btn btn-secondary btn-sm" onClick={openArchiveFolder}>OPEN FOLDER</button>
                </div>
              </div>
            </div>
          </div>

          {/* DOWNLOAD DEFAULTS */}
          <div className="cfg-panel" data-tour="config-defaults">
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
                    {QUALITIES.map(q => (
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
                    {CONTAINERS.map(c => <option key={c} value={c}>{c.toUpperCase()}</option>)}
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
                    {AUDIO_FORMATS.map(f => <option key={f} value={f}>{f.toUpperCase()}</option>)}
                  </select>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Default Audio Bitrate</div>
                  <div className="sl-sub">For MP3 / AAC / M4A / OPUS (FLAC and WAV are lossless)</div>
                </div>
                <div className="settings-ctrl">
                  <select className="sel" value={local.default_audio_quality || 'best'} onChange={e => set('default_audio_quality', e.target.value)}>
                    {AUDIO_QUALITIES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                  </select>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Subtitle Languages</div>
                  <div className="sl-sub">For the Subtitles option — "en,de", "en.*" (every English variant) or "all"</div>
                </div>
                <div className="settings-ctrl">
                  <input className="inp-sm" style={{ width: 160 }} value={local.sub_langs || ''} placeholder="en"
                    onChange={e => set('sub_langs', e.target.value)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Auto-Generated Subtitles</div>
                  <div className="sl-sub">Use YouTube's automatic captions when a video has none written for that language</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.auto_subs === true} onChange={v => set('auto_subs', v)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Keep Subtitle Files</div>
                  <div className="sl-sub">Also save them next to the video ("Title.en.srt"), for players and TVs that don't read embedded ones</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.keep_sub_files === true} onChange={v => set('keep_sub_files', v)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Skip YouTube Shorts</div>
                  <div className="sl-sub">In playlists, channels and vault syncs — a single pasted link still downloads</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.skip_shorts === true} onChange={v => set('skip_shorts', v)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Skip Live Streams</div>
                  <div className="sl-sub">Streams that are live or not started yet would record until they end, holding up a sync. Recordings of finished streams still download.</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.skip_live !== false} onChange={v => set('skip_live', v)} />
                </div>
              </div>
            </div>
          </div>

          {/* AUTHENTICATION */}
          <div className="cfg-panel" data-tour="config-auth">
            <div className="cfg-ph">
              <span className="ptag">AUTH</span>
              <span className="ptitle">AUTHENTICATION</span>
            </div>
            <div className="cfg-body">
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Browser Cookies</div>
                  <div className="sl-sub">
                    Uses your browser login session — <span style={{ color: 'var(--warn)' }}>close browser before use if locked</span>
                  </div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <select className="sel" value={local.cookies_browser || 'none'} onChange={e => set('cookies_browser', e.target.value)}>
                    {['none','chrome','firefox','edge','brave','safari'].map(b => (
                      <option key={b} value={b}>{b === 'none' ? 'Disabled' : b.charAt(0).toUpperCase() + b.slice(1)}</option>
                    ))}
                  </select>
                  {local.cookies_browser && local.cookies_browser !== 'none' && (
                    <span style={{ fontSize: 10.5, color: 'var(--success)', fontFamily: 'var(--font-mono)' }}>● ACTIVE</span>
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
                  <button className="btn btn-secondary btn-sm" onClick={browseCookiesProfile}>BROWSE</button>
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
                <div className="settings-ctrl" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  {(local.cookies_browser && local.cookies_browser !== 'none')
                    ? <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--success)' }}>Browser cookies ({local.cookies_browser}){local.cookies_browser_profile ? ' · custom profile' : ''}</span>
                    : local.cookies_file
                    ? <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--accent)' }}>Cookies file active</span>
                    : <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t4)' }}>No auth — public videos only</span>
                  }
                  {((local.cookies_browser && local.cookies_browser !== 'none') || local.cookies_file) && (
                    <button className="btn btn-secondary btn-sm" onClick={testCookies} disabled={testingCookies}
                      title="Load the cookies the way a download would (unsaved changes included)">
                      {testingCookies ? 'TESTING...' : 'TEST'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div>
          {/* NETWORK */}
          <div className="cfg-panel" data-tour="config-network">
            <div className="cfg-ph">
              <span className="ptag">NETWORK</span>
              <span className="ptitle">NETWORK SETTINGS</span>
            </div>
            <div className="cfg-body">
              {[
                { key: 'concurrent_fragments', label: 'Concurrent Fragments', sub: 'Parallel fragment downloads', type: 'number', min: 1, max: 16 },
                { key: 'rate_limit', label: 'Rate Limit', sub: 'All downloads together · 5M = 5MB/s · empty = unlimited', type: 'text', placeholder: '5M' },
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
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Force IPv4</div>
                  <div className="sl-sub">Turn on if Analyze or downloads hang for minutes (broken IPv6 connection)</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.force_ipv4 === true} onChange={v => set('force_ipv4', v)} />
                </div>
              </div>
            </div>
          </div>

          {/* BEHAVIOR */}
          <div className="cfg-panel" data-tour="config-behavior">
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
                  <div className="sl-name">"Later" Downloads Start At</div>
                  <div className="sl-sub">Time of day a download queued with ⏾ LATER starts (the app must be running)</div>
                </div>
                <div className="settings-ctrl">
                  <input type="time" className="inp-sm" style={{ width: 110 }} value={local.schedule_start || '02:00'}
                    onChange={e => set('schedule_start', e.target.value)} />
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">When the Queue Finishes</div>
                  <div className="sl-sub">Once nothing is left to download (after at least one new file)</div>
                </div>
                <div className="settings-ctrl">
                  <select className="sel" value={local.on_queue_done || 'nothing'} onChange={e => set('on_queue_done', e.target.value)}>
                    <option value="nothing">Do nothing</option>
                    <option value="open_folder">Open the download folder</option>
                  </select>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Keep the Computer Awake</div>
                  <div className="sl-sub">No sleep while downloads run or wait for their time (the screen can still turn off)</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.keep_awake !== false} onChange={v => set('keep_awake', v)} />
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
                  <div className="sl-name">Desktop Notifications</div>
                  <div className="sl-sub">System notification when a download finishes or fails while the window is in the background</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.desktop_notifications === true} onChange={setDesktopNotifications} />
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
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--accent-2)' }}>DuckDB (analytical)</span>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">DB Size</div>
                  <div className="sl-sub">Current database file size</div>
                </div>
                <div className="settings-ctrl">
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)' }}>{fmtBytes(sysInfo.db_size_bytes || 0)}</span>
                </div>
              </div>
              <div className="settings-row" data-tour="config-log">
                <div className="settings-label">
                  <div className="sl-name">Log File</div>
                  <div className="sl-sub">{sysInfo.log_path || 'What happened, for troubleshooting or a bug report'}</div>
                </div>
                <div className="settings-ctrl">
                  <button className="btn btn-secondary btn-sm" onClick={openLog}>OPEN LOG</button>
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
              <div className="settings-row" data-tour="config-backup">
                <div className="settings-label">
                  <div className="sl-name">Backup &amp; Restore</div>
                  <div className="sl-sub">Zip of config + analytics DB; restore keeps .pre-restore copies</div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-secondary btn-sm" onClick={downloadBackup}>
                    ⬇ BACKUP
                  </button>
                  <button className="btn btn-secondary btn-sm" disabled={restoring}
                    onClick={() => restoreInputRef.current && restoreInputRef.current.click()}>
                    {restoring ? 'RESTORING...' : '⬆ RESTORE'}
                  </button>
                  <input ref={restoreInputRef} type="file" accept=".zip" style={{ display: 'none' }} onChange={handleRestoreFile} />
                </div>
              </div>
              <div className="settings-row" data-tour="config-ffmpeg">
                <div className="settings-label">
                  <div className="sl-name">FFmpeg</div>
                  <div className="sl-sub" title={sysInfo.ffmpeg_path || ''}>
                    {ffmpegInstall
                      ? <span style={{ color: 'var(--warn)' }}>
                          {ffmpegInstall.stage === 'downloading' ? 'Downloading ' + ffmpegInstall.pct + '%' : 'Installing…'}
                        </span>
                      : sysInfo.ffmpeg
                      ? <span style={{ color: 'var(--success)' }}>
                          {sysInfo.ffmpeg_installed_by_app ? 'Installed by MellowDLP' : 'Found'} — {sysInfo.ffmpeg_path}
                        </span>
                      : <span style={{ color: 'var(--danger)' }}>
                          Missing — needed to merge, convert and trim{sysInfo.ffmpeg_installable ? '' : '. ' + (sysInfo.ffmpeg_install_note || '')}
                        </span>}
                  </div>
                </div>
                <div className="settings-ctrl">
                  {!sysInfo.ffmpeg && sysInfo.ffmpeg_installable && (
                    <button className="btn btn-amber btn-sm" onClick={installFfmpeg} disabled={!!ffmpegInstall}>
                      {ffmpegInstall ? '...' : 'GET FFMPEG'}
                    </button>
                  )}
                </div>
              </div>
              <div className="settings-row" data-tour="config-versions">
                <div className="settings-label">
                  <div className="sl-name">MellowDLP Version</div>
                  <div className="sl-sub">
                    {'v' + (sysInfo.app_version || '?') + ' — '}
                    {appUpdate && appUpdate.error ? <span style={{ color: 'var(--danger)' }}>Check failed: {appUpdate.error}</span>
                      : appUpdate && appUpdate.update_available ? <span style={{ color: 'var(--warn)' }}>
                          v{appUpdate.latest} is available{!appUpdate.can_install && appUpdate.install_note ? ' — ' + appUpdate.install_note : ''}
                        </span>
                      : appUpdate && appUpdate.message ? appUpdate.message
                      : appUpdate ? <span style={{ color: 'var(--success)' }}>Up to date</span>
                      : 'new versions are published on GitHub'}
                  </div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-secondary btn-sm" onClick={showWhatsNew}>WHAT'S NEW</button>
                  <button className="btn btn-secondary btn-sm" title="The project on GitHub: releases, source and issues (opens in your browser)"
                    onClick={() => openReleasePage('repo')}>GITHUB</button>
                  <button className="btn btn-secondary btn-sm" onClick={checkAppUpdate} disabled={checkingApp}>{checkingApp ? '...' : 'CHECK'}</button>
                  {appUpdate && appUpdate.update_available && (appUpdate.can_install
                    ? <button className="btn btn-amber btn-sm" onClick={() => installAppUpdate()}
                        title={appUpdate.download_size ? fmtBytes(appUpdate.download_size) + ', checked against its published checksum' : undefined}>
                        UPDATE TO v{appUpdate.latest}
                      </button>
                    : <button className="btn btn-amber btn-sm" onClick={() => openReleasePage()}>GET v{appUpdate.latest}</button>
                  )}
                </div>
              </div>
              <div className="settings-row" data-tour="config-js">
                <div className="settings-label">
                  <div className="sl-name">JavaScript Runtime</div>
                  <div className="sl-sub" title={sysInfo.js_runtime ? sysInfo.js_runtime.path : ''}>
                    {!sysInfo.js_runtime
                      ? <span style={{ color: 'var(--warn)' }}>None found — YouTube may offer fewer formats. yt-dlp uses Node.js, Deno, QuickJS or Bun</span>
                      : !sysInfo.js_runtime.supported
                      ? <span style={{ color: 'var(--warn)' }}>
                          {sysInfo.js_runtime.name} {sysInfo.js_runtime.version} is too old for yt-dlp (Node.js 22 or newer works)
                        </span>
                      : <span style={{ color: 'var(--success)' }}>
                          {sysInfo.js_runtime.name} {sysInfo.js_runtime.version} — solves YouTube's player challenges
                        </span>}
                  </div>
                </div>
                <div className="settings-ctrl">
                  {!(sysInfo.js_runtime && sysInfo.js_runtime.supported) && (
                    <button className="btn btn-secondary btn-sm" title="Opens nodejs.org in your browser. Once it is installed, restart MellowDLP: it finds Node.js by itself"
                      onClick={() => openReleasePage('nodejs')}>GET NODE.JS</button>
                  )}
                </div>
              </div>
              <div className="settings-row" data-tour="config-ytdlp">
                <div className="settings-label">
                  <div className="sl-name">yt-dlp Version</div>
                  <div className="sl-sub">
                    {updateInfo && updateInfo.pending_restart
                      ? <span style={{ color: 'var(--warn)' }}>{updateInfo.pending_restart} downloaded — restart MellowDLP to use it</span>
                      : updateInfo && !updateInfo.error && updateInfo.update_available
                      ? <span style={{ color: 'var(--warn)' }}>Update available: {updateInfo.latest} (running {updateInfo.installed})</span>
                      : updateInfo && !updateInfo.error ? <span style={{ color: 'var(--success)' }}>Up to date ({updateInfo.installed})</span>
                      : 'Check for updates below'
                    }
                  </div>
                </div>
                <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-secondary btn-sm" onClick={checkUpdate} disabled={checking}>{checking ? '...' : 'CHECK'}</button>
                  {updateInfo && updateInfo.update_available && (
                    <button className="btn btn-amber btn-sm" disabled={updating} onClick={updateYtdlp}>{updating ? 'UPDATING...' : 'UPDATE'}</button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* APPEARANCE */}
          <div className="cfg-panel" data-tour="config-appearance">
            <div className="cfg-ph">
              <span className="ptag" style={{ background: 'var(--accent-3)' }}>UI</span>
              <span className="ptitle">APPEARANCE</span>
            </div>
            <div className="cfg-body">
              <div className="theme-grid">
                {themeCards(currentTheme).map(t => {
                  const on = t.id === currentTheme;
                  const swatches = (
                    <div className="theme-swatches" aria-hidden="true">
                      {t.swatches.map((colour, i) => <span key={i} className="theme-swatch" style={{ background: colour }} />)}
                    </div>
                  );
                  if (!t.pair) return (
                    <div key={t.id} className={'theme-card' + (on ? ' on' : '')}
                      role="button" tabIndex={0} aria-pressed={on}
                      aria-label={'Theme: ' + t.name}
                      onClick={() => pickTheme(t.id)}
                      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pickTheme(t.id); } }}>
                      {swatches}
                      <div className="theme-name">{t.name}</div>
                      <div className="theme-current">{on ? '● CURRENT' : ''}</div>
                    </div>
                  );
                  // Two versions, one card: a click picks the version shown; the keyboard uses the switch
                  return (
                    <div key={t.pair.dark} className={'theme-card' + (on ? ' on' : '')}
                      role="group" aria-label={'Theme: ' + t.name}
                      onClick={() => pickTheme(t.id)}>
                      {swatches}
                      <div className="theme-name">{t.name}</div>
                      <div className="theme-mode">
                        {[['dark', 'DARK'], ['light', 'LIGHT']].map(([version, label]) => {
                          const id = t.pair[version];
                          const pressed = id === currentTheme;
                          return (
                            <button key={version} type="button" className={'theme-mode-btn' + (pressed ? ' on' : '')}
                              aria-pressed={pressed} aria-label={t.name + ' ' + version}
                              onClick={e => { e.stopPropagation(); pickTheme(id); }}>{label}</button>
                          );
                        })}
                      </div>
                      <div className="theme-current">{on ? '● CURRENT' : ''}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* UI PREFERENCES */}
          <div className="cfg-panel">
            <div className="cfg-ph">
              <span className="ptag" style={{ background: 'var(--accent-3)' }}>UI</span>
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
                  <div className="sl-sub">Show the celebration when a vault sync brought new files</div>
                </div>
                <div className="settings-ctrl">
                  <Toggle checked={local.ui_victory_sync !== false} onChange={v => set('ui_victory_sync', v)} />
                </div>
              </div>
            </div>
          </div>

          <ApiAccessPanel local={local} set={set} showNotif={showNotif} />

          {/* DANGER ZONE */}
          <div className="cfg-panel cfg-danger" data-tour="config-danger">
            <div className="cfg-ph">
              <span className="ptag red">DANGER</span>
              <span className="ptitle" style={{ color: 'var(--danger)' }}>DANGER ZONE</span>
            </div>
            <div className="cfg-body">
              <div className="settings-row">
                <div className="settings-label">
                  <div className="sl-name">Purge Download History</div>
                  <div className="sl-sub">Delete every download record and the stats built on them; the library stays</div>
                </div>
                <div className="settings-ctrl">
                  <button className="btn btn-danger btn-sm" onClick={() => setDangerModal('purge')}>PURGE HISTORY</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {dangerModal === 'purge' && (
        <Modal
          title="PURGE DOWNLOAD HISTORY"
          onClose={() => setDangerModal(null)}
          footer={
            <>
              <button className="btn btn-secondary btn-sm" onClick={() => setDangerModal(null)}>CANCEL</button>
              <button className="btn btn-danger btn-sm" onClick={doPurge}>PURGE HISTORY</button>
            </>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}>
            <Mascot src={MASCOT_FRUSTRATED} className="error-mascot" wrapClass="error-mascot" style={{ width: 80 }} />
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--t2)', textAlign: 'center', lineHeight: 1.8 }}>
              This permanently deletes every download record: the History list, the Analytics numbers and
              the "already downloaded" notes.<br />
              Your files, vault folders, linked playlists and their sync settings stay as they are.<br />
              <span style={{ color: 'var(--danger)' }}>This cannot be undone.</span>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
