// FEED page — URL ingest, options, active download, queue preview.
'use strict';

import { API, cancelShownDownload } from '../lib/api.js';
import { estimateDownloadBytes, fmtBytes, fmtSpeed, fmtEta, fmtDuration, timeAgo } from '../lib/util.js';
import { SVG, Ico } from '../components/icons.jsx';
import { Modal, Mascot, Pipeline } from '../components/common.jsx';
import { MASCOT_CHILLING } from '../lib/mascots.js';
import {
  ANALYZE_SLOW_MS, AUDIO_FORMATS, AUDIO_QUALITIES, CONTAINERS, LOSSLESS_AUDIO, QUALITIES,
  SPONSORBLOCK_HINT,
} from '../lib/constants.js';

export function FeedPage({ dlState, setDlState, setAppState, stats, sysInfo, refreshStats, showNotif, switchPage, config, setConfig, suggestedUrl, onSuggestedConsumed, onPlaylistDownload, playlistItems, setPlaylistItems, completedItems, failedItems, playlistTotalCount, playlistCompletedCount, isPaused, syncJobLabel, fetchingPlaylistItems, onPause, onResume, onClearCompleted }) {
  const ss = (k, fb) => { try { const v = sessionStorage.getItem(k); return v !== null ? v : fb; } catch { return fb; } };
  const ssJ = (k, fb) => { try { const v = sessionStorage.getItem(k); return v ? JSON.parse(v) : fb; } catch { return fb; } };
  const hasSS = (k) => { try { return sessionStorage.getItem(k) !== null; } catch { return false; } };

  const [url, setUrl] = React.useState(() => ss('feed_url', ''));
  const [analyzing, setAnalyzing] = React.useState(false);
  // Analyze normally takes a few seconds; past ANALYZE_SLOW_MS say why it may hang
  const [analyzeSlow, setAnalyzeSlow] = React.useState(false);
  React.useEffect(() => {
    if (!analyzing) { setAnalyzeSlow(false); return undefined; }
    const t = setTimeout(() => setAnalyzeSlow(true), ANALYZE_SLOW_MS);
    return () => clearTimeout(t);
  }, [analyzing]);
  const [fetchingItems, setFetchingItems] = React.useState(false);
  const [info, setInfo] = React.useState(() => ssJ('feed_info', null));
  const [optsOpen, setOptsOpen] = React.useState(false);
  const [advOpen, setAdvOpen] = React.useState(false);
  const [mode, setMode] = React.useState(() => ss('feed_mode', 'video'));
  const [quality, setQuality] = React.useState(() => ss('feed_quality', '1080p'));
  const [container, setContainer] = React.useState(() => ss('feed_container', 'mp4'));
  const [audioFmt, setAudioFmt] = React.useState(() => ss('feed_audioFmt', 'mp3'));
  const [audioQuality, setAudioQuality] = React.useState(() => ss('feed_audioQuality', 'best'));
  const [embedThumb, setEmbedThumb] = React.useState(() => ssJ('feed_embedThumb', true));
  const [embedSubs, setEmbedSubs] = React.useState(() => ssJ('feed_embedSubs', false));
  const [embedChapters, setEmbedChapters] = React.useState(() => ssJ('feed_embedChapters', true));
  const [embedMeta, setEmbedMeta] = React.useState(() => ssJ('feed_embedMeta', true));
  const [sponsorblock, setSponsorblock] = React.useState(() => ssJ('feed_sponsorblock', false));
  const [startTime, setStartTime] = React.useState(() => ss('feed_startTime', ''));
  const [endTime, setEndTime] = React.useState(() => ss('feed_endTime', ''));
  const [customFmt, setCustomFmt] = React.useState(() => ss('feed_customFmt', ''));
  const [downloadPath, setDownloadPath] = React.useState(() => ss('feed_downloadPath', ''));

  React.useEffect(() => { try { sessionStorage.setItem('feed_url', url); } catch {} }, [url]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_mode', mode); } catch {} }, [mode]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_quality', quality); } catch {} }, [quality]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_container', container); } catch {} }, [container]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_audioFmt', audioFmt); } catch {} }, [audioFmt]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_audioQuality', audioQuality); } catch {} }, [audioQuality]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_embedThumb', JSON.stringify(embedThumb)); } catch {} }, [embedThumb]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_embedSubs', JSON.stringify(embedSubs)); } catch {} }, [embedSubs]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_embedChapters', JSON.stringify(embedChapters)); } catch {} }, [embedChapters]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_embedMeta', JSON.stringify(embedMeta)); } catch {} }, [embedMeta]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_sponsorblock', JSON.stringify(sponsorblock)); } catch {} }, [sponsorblock]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_startTime', startTime); } catch {} }, [startTime]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_endTime', endTime); } catch {} }, [endTime]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_customFmt', customFmt); } catch {} }, [customFmt]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_downloadPath', downloadPath); } catch {} }, [downloadPath]);
  React.useEffect(() => { try { sessionStorage.setItem('feed_info', info ? JSON.stringify(info) : ''); } catch {} }, [info]);

  const prevUrl = React.useRef(url);
  React.useEffect(() => {
    if (prevUrl.current !== url) {
      prevUrl.current = url;
      setInfo(null);
      setPlaylistItems && setPlaylistItems(null);
      setImportedUrls(null);
      setImportedFileName('');
    }
  }, [url, setPlaylistItems]);

  const [vaultLinkPrompt, setVaultLinkPrompt] = React.useState(false);
  const [feedQTab, setFeedQTab] = React.useState('pending');
  const [removingFeedItems, setRemovingFeedItems] = React.useState(new Set());
  const [importedUrls, setImportedUrls] = React.useState(null);
  const [importedFileName, setImportedFileName] = React.useState('');

  // Ref to always call the latest startDownload (avoids stale closure in handleDownload)
  const startDownloadRef = React.useRef(null);

  const isDownloading = dlState && dlState.status !== 'complete' && dlState.status !== 'error';

  // Between POST /api/download and the first 'starting' SSE event isDownloading
  // is still false — block the window so rapid clicks can't enqueue duplicates
  const [submitting, setSubmitting] = React.useState(false);
  // ⏾ LATER: the next download waits for the Config start time
  const [scheduleLater, setScheduleLater] = React.useState(false);
  const scheduleStart = config.schedule_start || '02:00';
  const onQueued = React.useCallback((d) => {
    if (d.status === 'scheduled') {
      setSubmitting(false);
      setScheduleLater(false);
      showNotif('Scheduled', 'Starts at ' + scheduleStart + ' — see the Queue page to start it sooner', 'success');
    }
    if (d.disk_warning) showNotif('Low Disk Space', d.disk_warning, 'warn');
  }, [scheduleStart, showNotif]);
  React.useEffect(() => { setSubmitting(false); }, [dlState]);

  // explicitUrl lets callers analyze a URL the `url` state hasn't caught up
  // to yet (clipboard suggestion); plain onClick passes an event — ignored.
  const handleAnalyze = React.useCallback((explicitUrl) => {
    const target = (typeof explicitUrl === 'string' ? explicitUrl : url).trim();
    if (!target) return;
    setAnalyzing(true);
    setInfo(null);
    setPlaylistItems && setPlaylistItems(null);
    API.post('/api/info', { url: target })
      .then(data => {
        setInfo(data);
        if (data.is_playlist) {
          setFetchingItems(true);
          API.post('/api/playlist-items', { url: target })
            .then(r => {
              if (r.items && setPlaylistItems) {
                setPlaylistItems(r.items.map(item => ({ ...item, selected: true })));
              }
            })
            .catch(() => {})
            .finally(() => setFetchingItems(false));
        }
      })
      .catch(e => {
        // Explained when the backend recognises it; the raw text otherwise
        const d = e.data || {};
        showNotif(d.title || 'Error', d.hint || e.message, 'error');
      })
      .finally(() => setAnalyzing(false));
  }, [url, showNotif, setPlaylistItems]);

  // Clipboard watcher accepted: load the detected URL and analyze right away
  React.useEffect(() => {
    if (!suggestedUrl || !suggestedUrl.url) return;
    setUrl(suggestedUrl.url);
    handleAnalyze(suggestedUrl.url);
    onSuggestedConsumed && onSuggestedConsumed();
    // handleAnalyze/onSuggestedConsumed intentionally omitted: run only on a new suggestion
  }, [suggestedUrl]);

  // Apply Config-page download defaults when no session state exists yet
  const sessionHadRef = React.useRef({
    mode: hasSS('feed_mode'), quality: hasSS('feed_quality'),
    container: hasSS('feed_container'), audioFmt: hasSS('feed_audioFmt'),
    audioQuality: hasSS('feed_audioQuality'),
  });
  React.useEffect(() => {
    const had = sessionHadRef.current;
    if (!had.mode && config.default_mode) setMode(config.default_mode);
    if (!had.quality && config.default_quality) setQuality(config.default_quality);
    if (!had.container && config.default_container) setContainer(config.default_container);
    if (!had.audioFmt && config.default_audio_format) setAudioFmt(config.default_audio_format);
    if (!had.audioQuality && config.default_audio_quality) setAudioQuality(config.default_audio_quality);
  }, [config.default_mode, config.default_quality, config.default_container, config.default_audio_format, config.default_audio_quality]);

  // ── Format presets — named option bundles stored in config ────────────────
  const [savingPreset, setSavingPreset] = React.useState(false);
  const [presetName, setPresetName] = React.useState('');

  const currentOpts = () => ({
    mode, quality, container, audio_format: audioFmt, audio_quality: audioQuality,
    embed_thumbnail: embedThumb, embed_subs: embedSubs,
    embed_chapters: embedChapters, embed_metadata: embedMeta,
    sponsorblock,
  });

  const applyPreset = (p) => {
    const o = p.opts || {};
    if (o.mode) setMode(o.mode);
    if (o.quality) setQuality(o.quality);
    if (o.container) setContainer(o.container);
    if (o.audio_format) setAudioFmt(o.audio_format);
    if (o.audio_quality) setAudioQuality(o.audio_quality);
    setEmbedThumb(o.embed_thumbnail !== false);
    setEmbedSubs(!!o.embed_subs);
    setEmbedChapters(o.embed_chapters !== false);
    setEmbedMeta(o.embed_metadata !== false);
    setSponsorblock(!!o.sponsorblock);
    showNotif('Preset Applied', p.name, 'success');
  };

  const persistPresets = (presets) => {
    API.post('/api/config', { download_presets: presets })
      .then(() => setConfig && setConfig(c => ({ ...c, download_presets: presets })))
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const savePreset = () => {
    const name = presetName.trim();
    if (!name) return;
    const presets = (config.download_presets || []).filter(p => p.name !== name)
      .concat([{ name, opts: currentOpts() }]);
    persistPresets(presets);
    setSavingPreset(false);
    setPresetName('');
    showNotif('Preset Saved', name, 'success');
  };

  const deletePreset = (name) => {
    persistPresets((config.download_presets || []).filter(p => p.name !== name));
  };

  const handleImportFile = React.useCallback(() => {
    API.post('/api/browse-file', { filter: '.txt' })
      .then(d => {
        if (!d.path) return;
        API.post('/api/read-url-file', { path: d.path })
          .then(r => {
            const urls = r.urls || [];
            const fname = d.path.split(/[\\/]/).pop();
            const isArchive = r.format === 'archive';
            if (!urls.length) {
              showNotif('No URLs', fname + ' contains no valid URLs or archive entries', 'error');
              return;
            }
            if (urls.length === 1) {
              setUrl(urls[0]);
              setImportedUrls(null);
              setImportedFileName('');
              if (isArchive) showNotif('Archive imported', '1 URL from ' + fname, 'success');
            } else {
              setImportedUrls(urls);
              setImportedFileName(fname);
              const fakeItems = urls.map((u, i) => ({ idx: i + 1, title: u, url: u, selected: true }));
              setPlaylistItems && setPlaylistItems(fakeItems);
              setInfo({ is_playlist: true, is_imported: true, title: fname, playlist_count: urls.length });
              showNotif('Imported', urls.length + ' URLs from ' + fname + (isArchive ? ' (archive format)' : ''), 'success');
            }
          })
          .catch(e => showNotif('Error', e.message, 'error'));
      })
      .catch(() => {});
  }, [showNotif, setPlaylistItems]);

  const startImportDownload = React.useCallback(() => {
    if (!importedUrls || !importedUrls.length) return;
    if (onPlaylistDownload) onPlaylistDownload(importedUrls.length, importedFileName || 'Imported URLs');
    setSubmitting(true);
    API.post('/api/download', {
      url: importedUrls[0],
      multi_urls: importedUrls,
      mode,
      quality,
      container,
      audio_format: audioFmt,
      audio_quality: audioQuality,
      embed_thumbnail: embedThumb,
      embed_chapters: embedChapters,
      embed_metadata: embedMeta,
      embed_subs: embedSubs,
      sponsorblock,
      scheduled: scheduleLater,
      ...(downloadPath ? { output_dir: downloadPath } : {}),
    }).then(onQueued).catch(e => { showNotif('Error', e.message, 'error'); setSubmitting(false); });
  }, [importedUrls, importedFileName, mode, quality, container, audioFmt, audioQuality, embedThumb, embedChapters, embedMeta, embedSubs, sponsorblock, downloadPath, onPlaylistDownload, showNotif, scheduleLater, onQueued]);

  // Ref so handleDownload/handleUrlKeyDown can call latest startImportDownload without stale closure
  const startImportDownloadRef = React.useRef(null);
  startImportDownloadRef.current = startImportDownload;

  // handleDownload uses a ref so it always calls the latest startDownload without stale closure
  const handleDownload = React.useCallback(() => {
    if (!url.trim() && !importedUrls) return;
    if (info && info.is_imported && importedUrls) {
      startImportDownloadRef.current && startImportDownloadRef.current();
      return;
    }
    if (info && info.is_playlist) {
      if (onPlaylistDownload) onPlaylistDownload(info.playlist_count || 0, info.title || '');
      setVaultLinkPrompt(true);
      return;
    }
    if (startDownloadRef.current) startDownloadRef.current();
  }, [url, info, importedUrls, onPlaylistDownload]);

  const browseDownloadPath = React.useCallback(() => {
    API.post('/api/browse-folder', {}).then(d => { if (d.path) setDownloadPath(d.path); }).catch(() => {});
  }, []);

  const startDownload = React.useCallback((extra) => {
    setSubmitting(true);
    let playlistItemsParam = undefined;
    if (playlistItems && info && info.is_playlist) {
      const selected = playlistItems.filter(i => i.selected !== false);
      if (selected.length > 0 && selected.length < playlistItems.length) {
        playlistItemsParam = selected.map(i => i.idx).join(',');
      }
    }
    API.post('/api/download', {
      url: url.trim(),
      mode,
      quality,
      container,
      audio_format: audioFmt,
      audio_quality: audioQuality,
      embed_thumbnail: embedThumb,
      embed_chapters: embedChapters,
      embed_metadata: embedMeta,
      embed_subs: embedSubs,
      sponsorblock,
      start_time: startTime,
      end_time: endTime,
      custom_format: customFmt,
      ...(downloadPath ? { output_dir: downloadPath } : {}),
      ...(playlistItemsParam ? { playlist_items: playlistItemsParam } : {}),
      scheduled: scheduleLater,
      ...extra,
    }).then(onQueued).catch(e => { showNotif('Error', e.message, 'error'); setSubmitting(false); });
  }, [url, mode, quality, container, audioFmt, audioQuality, embedThumb, embedChapters, embedMeta, embedSubs, sponsorblock, startTime, endTime, customFmt, downloadPath, playlistItems, info, showNotif, scheduleLater, onQueued]);

  // Keep ref in sync with latest startDownload (assigned during render, safe to read in callbacks)
  startDownloadRef.current = startDownload;

  const handleCancel = React.useCallback(() => {
    cancelShownDownload(dlState).catch(e => showNotif('Error', e.message, 'error'));
  }, [dlState, showNotif]);

  const estimatedBytes = info && !info.is_playlist
    ? estimateDownloadBytes(info, { mode, quality, audioFmt, audioQuality, startTime, endTime })
    : null;
  const diskFree = sysInfo && sysInfo.disk_free_bytes;
  const wontFit = !!(estimatedBytes && diskFree && estimatedBytes > diskFree);

  const handlePaste = React.useCallback(() => {
    API.get('/api/clipboard').then(d => {
      if (d.text) setUrl(d.text);
    }).catch(() => {});
  }, []);

  const handleUrlKeyDown = React.useCallback((e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (!url.trim()) {
      API.get('/api/clipboard').then(d => { if (d.text) setUrl(d.text); }).catch(() => {});
    } else if (!info && !analyzing) {
      handleAnalyze();
    } else if (info && !isDownloading) {
      if (info.is_imported && importedUrls) {
        startImportDownloadRef.current && startImportDownloadRef.current();
      } else {
        handleDownload();
      }
    }
  }, [url, info, analyzing, isDownloading, importedUrls, handleAnalyze, handleDownload]);

  const pipelineStage = dlState
    ? dlState.status === 'processing' ? 'processing' : 'downloading'
    : 'done';

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
              onKeyDown={handleUrlKeyDown}
              placeholder="https://www.youtube.com/watch?v=... or any supported platform URL"
            />
          </div>
          <button
            className={'btn btn-secondary btn-sm' + (optsOpen ? ' active-btn' : '')}
            onClick={() => setOptsOpen(o => !o)}
          >
            OPTIONS
          </button>
          {!info && (
            <button className="btn btn-primary" onClick={handleAnalyze} disabled={analyzing}>
              {analyzing ? 'ANALYZING...' : 'ANALYZE →'}
            </button>
          )}
          <button className="btn btn-secondary btn-sm" onClick={handlePaste}>PASTE</button>
          <button className="btn btn-secondary btn-sm" onClick={handleImportFile} title="Import URLs from .txt file">IMPORT FILE</button>
        </div>
        <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)', paddingTop: 3 }}>
          ENTER: {!url.trim() ? 'paste' : !info && !analyzing ? 'analyze' : 'download'}
          {importedFileName && <span style={{ color: 'var(--cyan)', marginLeft: 10 }}>↑ {importedFileName} ({importedUrls ? importedUrls.length : 0} URLs)</span>}
          {analyzeSlow && (
            <span style={{ color: 'var(--amber)', marginLeft: 10 }}>
              STILL ANALYZING — big playlists take a while. If it never finishes, try Config → Network → Force IPv4.
            </span>
          )}
        </div>

        {/* OPTIONS PANEL */}
        <div className={'opts-panel' + (optsOpen ? ' open' : '')}>
          <div className="opts-inner">
            {/* PRESETS — one-click saved option bundles */}
            <div className="opts-row">
              <span className="opts-label">PRESETS</span>
              <div className="pills" style={{ alignItems: 'center' }}>
                {(config.download_presets || []).map(p => (
                  <div key={p.name} className="pill" title={'Apply "' + p.name + '"'} onClick={() => applyPreset(p)}>
                    {p.name.toUpperCase()}
                    <span
                      style={{ marginLeft: 6, color: 'var(--red)' }}
                      title="Delete preset"
                      onClick={e => { e.stopPropagation(); deletePreset(p.name); }}
                    >✕</span>
                  </div>
                ))}
                {savingPreset ? (
                  <input
                    className="inp-sm"
                    style={{ width: 130 }}
                    autoFocus
                    placeholder="Preset name…"
                    value={presetName}
                    onChange={e => setPresetName(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') savePreset();
                      if (e.key === 'Escape') { setSavingPreset(false); setPresetName(''); }
                    }}
                    onBlur={() => { setSavingPreset(false); setPresetName(''); }}
                  />
                ) : (
                  <div className="pill" title="Save current options as a preset" onClick={() => setSavingPreset(true)}>
                    + SAVE CURRENT
                  </div>
                )}
              </div>
            </div>

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
              <>
                <div className="opts-row">
                  <span className="opts-label">FORMAT</span>
                  <div className="pills">
                    {AUDIO_FORMATS.map(f => (
                      <div key={f} className={'pill' + (audioFmt === f ? ' active' : '')} onClick={() => setAudioFmt(f)}>
                        {f.toUpperCase()}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="opts-row" title={LOSSLESS_AUDIO.includes(audioFmt) ? audioFmt.toUpperCase() + ' is lossless: bitrate does not apply' : 'Target bitrate of the converted file'}>
                  <span className="opts-label">BITRATE</span>
                  <div className="pills" style={LOSSLESS_AUDIO.includes(audioFmt) ? { opacity: 0.4, pointerEvents: 'none' } : undefined}>
                    {AUDIO_QUALITIES.map(([v, label]) => (
                      <div key={v} className={'pill' + (audioQuality === v ? ' active' : '')} onClick={() => setAudioQuality(v)}>
                        {label}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            <div className="opts-toggles">
              {[
                { label: 'Embed Thumbnail', val: embedThumb, set: setEmbedThumb },
                { label: 'Subtitles', val: embedSubs, set: setEmbedSubs },
                { label: 'Chapters', val: embedChapters, set: setEmbedChapters },
                { label: 'Metadata', val: embedMeta, set: setEmbedMeta },
                { label: 'SponsorBlock', val: sponsorblock, set: setSponsorblock, hint: SPONSORBLOCK_HINT },
              ].map(item => (
                <label key={item.label} className="opts-toggle-item" title={item.hint}>
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
              {/* LEFT: thumbnail block — fixed 160×90, no border-radius */}
              <div className="info-thumb-block">
                {info.thumbnail
                  ? <img src={info.thumbnail} className="info-thumb-img" alt="" />
                  : <div className="info-thumb-img-ph">▶</div>
                }
                {info.duration && (
                  <span className="info-thumb-dur">{fmtDuration(info.duration)}</span>
                )}
                <span className={'info-thumb-fmt ' + (mode === 'audio' ? 'fmt-audio' : 'fmt-video')}>
                  {mode === 'audio' ? audioFmt.toUpperCase() : container.toUpperCase()}
                </span>
              </div>
              {/* CENTER: metadata */}
              <div className="info-details">
                <div className="info-title">{info.title || 'Unknown Title'}</div>
                <div className="info-meta">
                  {[info.uploader, info.platform, info.is_playlist ? (info.playlist_count + ' items') : null].filter(Boolean).join(' · ')}
                </div>
                {info.previous_download && (
                  <div className="info-prev" title={info.previous_download.file_path || ''}>
                    <span className="tag green">✓ ALREADY DOWNLOADED {timeAgo(info.previous_download.timestamp).toUpperCase()}</span>
                    {info.previous_download.exists ? (
                      <>
                        <span className="info-prev-link" onClick={() => API.post('/api/vault/open-file', { path: info.previous_download.file_path }).catch(() => {})}>OPEN</span>
                        <span className="info-prev-link" onClick={() => API.post('/api/open-folder', { path: info.previous_download.file_path }).catch(() => {})}>SHOW IN FOLDER</span>
                      </>
                    ) : (
                      <span style={{ color: 'var(--t4)' }}>file moved or deleted since</span>
                    )}
                  </div>
                )}
                <div className="info-tags">
                  <span className="tag cyan">{info.platform || 'URL'}</span>
                  {info.is_playlist && <span className="tag amber">PLAYLIST · {info.playlist_count}</span>}
                  {mode === 'video' ? <span className="tag">{quality.toUpperCase()}</span> : <span className="tag amber">{audioFmt.toUpperCase()}</span>}
                  {estimatedBytes && (
                    <span className={'tag' + (wontFit ? ' red' : '')}
                      title={wontFit ? 'Only ' + fmtBytes(diskFree) + ' free on the download drive'
                        : 'Estimated from the formats the site offers'}>
                      ≈ {fmtBytes(estimatedBytes)}{wontFit ? ' · WON\'T FIT' : ''}
                    </span>
                  )}
                </div>
              </div>
              {/* RIGHT: action area */}
              <div className="info-actions">
                <button className="btn btn-primary btn-sm" onClick={handleDownload}
                  disabled={(isDownloading && !scheduleLater) || submitting} style={{ width: '100%' }}>
                  {submitting ? 'STARTING...' : scheduleLater ? '⏾ AT ' + scheduleStart
                    : isDownloading ? 'ACTIVE...' : 'DOWNLOAD'}
                </button>
                <button className={'btn btn-sm ' + (scheduleLater ? 'btn-amber' : 'btn-secondary')} style={{ width: '100%' }}
                  title={'Queue it to start at ' + scheduleStart + ' (Config → Behavior)'}
                  onClick={() => setScheduleLater(v => !v)}>
                  ⏾ LATER{scheduleLater ? ' ✓' : ''}
                </button>
                <button className="btn btn-secondary btn-sm" onClick={handleAnalyze} disabled={analyzing || isDownloading} style={{ width: '100%' }} title="Re-analyze URL">
                  ↺ RESCAN
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* SYNC IN PROGRESS BANNER */}
      {isDownloading && dlState && dlState.library_id && info && (
        <div className="sync-banner">⚠ SYNC IN PROGRESS — Your previous analysis is on standby</div>
      )}

      {/* ACTIVE DOWNLOAD PANEL */}
      <div className={'dl-panel panel' + (isDownloading ? ' open' : '')} style={{ marginBottom: 16 }}>
        <div className="panel-hud" /><div className="panel-hud-br" />
        <div className="ph">
          <span className="ptag">ACTIVE</span>
          <span className="ptitle">NOW PROCESSING — 処理中</span>
          <span className="psub">
            {playlistTotalCount > 1
              ? `${playlistCompletedCount + 1} / ${playlistTotalCount} ACTIVE`
              : isDownloading ? 'DOWNLOADING' : 'WAITING'}
          </span>
        </div>
        {dlState && (
          <>
            <div className="dl-card">
              <div className="dl-inner">
                {(dlState.current_item_thumb || (info && info.thumbnail))
                  ? <img src={dlState.current_item_thumb || info.thumbnail} className="dl-thumb" alt="" onError={e => { e.target.style.display = 'none'; }} />
                  : <div className="dl-thumb-ph">▶</div>
                }
                <div className="dl-info">
                  {info && info.is_playlist && dlState.current_item_title && (
                    <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: '#8899aa', marginBottom: 3, letterSpacing: '0.1em' }}>
                      FROM: {(info.title || '').toUpperCase().slice(0, 32)}
                    </div>
                  )}
                  <div className="dl-title">{dlState.current_item_title || (info && info.title) || dlState.filename || 'Downloading...'}</div>
                  <div className="dl-ch">{[info && info.uploader, info && info.platform, info && info.duration ? fmtDuration(info.duration) : null].filter(Boolean).join(' · ')}</div>
                  <div className="dl-tags">
                    <span className="tag cyan">{mode === 'audio' ? audioFmt.toUpperCase() : container.toUpperCase()}</span>
                    {mode !== 'audio' && <span className="tag">{quality.toUpperCase()}</span>}
                    {sponsorblock && <span className="tag green">SPONSORBLOCK</span>}
                  </div>
                  <div className="prog-row">
                    <div className="prog-bar">
                      <div className="prog-bar-fill" style={{ width: (dlState.pct || 0) + '%', background: isPaused ? 'var(--amber)' : undefined }} />
                    </div>
                    <span className="prog-pct" style={{ color: isPaused ? 'var(--amber)' : undefined }}>
                      {isPaused ? 'PAUSED' : (dlState.pct || 0).toFixed(1) + '%'}
                    </span>
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
                  <div className="dl-kv"><span className="k">QUALITY</span><span className="v">{mode === 'audio' ? (LOSSLESS_AUDIO.includes(audioFmt) ? 'LOSSLESS' : (AUDIO_QUALITIES.find(q => q[0] === audioQuality) || ['', 'BEST'])[1]) : quality.toUpperCase()}</span></div>
                  <div className="dl-kv"><span className="k">PLATFORM</span><span className="v">{info && info.platform || '—'}</span></div>
                  <div className="dl-kv"><span className="k">SIZE</span><span className="v">{fmtBytes(dlState.total)}</span></div>
                  <div style={{ marginTop: 10, display: 'flex', gap: 6 }}>
                    {isPaused
                      ? <button className="btn btn-amber btn-sm" style={{ flex: 1 }} onClick={onResume}>▶ RESUME</button>
                      : <button className="btn btn-secondary btn-sm" style={{ flex: 1 }} onClick={onPause}>⏸ PAUSE</button>}
                    <button className="btn btn-danger btn-sm" style={{ flex: 1 }} onClick={handleCancel}>CANCEL</button>
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
            <span className="psub">{feedQTab === 'pending' ? (playlistItems ? playlistItems.length : 0) + ' ITEMS' : (completedItems ? completedItems.length : 0) + ' DONE'}</span>
            {url && <span style={{ marginLeft: 'auto', cursor: 'pointer', color: 'var(--t3)', fontSize: 13, padding: '0 4px' }} title="Refresh queue" onClick={() => { if (url.trim()) { API.post('/api/playlist-items', { url: url.trim() }).then(r => { if (r.items && setPlaylistItems) setPlaylistItems(r.items.map(i => ({ ...i, selected: true }))); }).catch(() => {}); } }}>↻</span>}
          </div>
          {((playlistItems && playlistItems.length > 0) || (completedItems && completedItems.length > 0)) && (
            <div className="q-tabs" style={{ display: 'flex', alignItems: 'center' }}>
              <div className={'q-tab' + (feedQTab === 'pending' ? ' active' : '')} onClick={() => setFeedQTab('pending')}>
                PENDING ({playlistItems ? playlistItems.length : 0})
              </div>
              <div className={'q-tab' + (feedQTab === 'completed' ? ' active' : '')} onClick={() => setFeedQTab('completed')}>
                COMPLETED ({completedItems ? completedItems.length : 0})
              </div>
              {feedQTab === 'completed' && completedItems && completedItems.length > 0 && onClearCompleted && (
                <span style={{ marginLeft: 'auto', cursor: 'pointer', fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--red)', padding: '0 10px' }} onClick={onClearCompleted}>CLEAR ✕</span>
              )}
            </div>
          )}
          {feedQTab === 'pending' ? (
            playlistItems && playlistItems.length > 0 ? (
              <div>
                <div className="queue-list-header">
                  <span className="qlh-left">PENDING ITEMS — 待機中</span>
                  <span className="qlh-right">{playlistItems.length} TRACKS · CLICK ✕ TO REMOVE</span>
                </div>
                {syncJobLabel && (
                  <div style={{ padding: '6px 14px', background: 'var(--bg3)', borderBottom: '1px solid var(--border)', fontFamily: 'Share Tech Mono', fontSize: 9, color: 'var(--cyan)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>⟳</span>
                    SYNC QUEUED: {syncJobLabel}
                  </div>
                )}
                <div className="pl-queue-list" style={{ maxHeight: 216 }}>
                  {playlistItems.slice(0, 12).map(item => (
                    <div
                      key={item.idx}
                      className={'pl-queue-item' + (removingFeedItems.has(item.idx) ? ' completing' : '')}
                      onAnimationEnd={removingFeedItems.has(item.idx) ? () => {
                        setPlaylistItems(prev => prev ? prev.filter(x => x.idx !== item.idx) : prev);
                        setRemovingFeedItems(prev => { const n = new Set(prev); n.delete(item.idx); return n; });
                      } : undefined}
                    >
                      <span className="pl-queue-drag">⠿</span>
                      <span className="pl-queue-idx">{item.idx}</span>
                      {item.thumbnail
                        ? <img src={item.thumbnail} className="pl-queue-thumb" alt="" onError={e => { e.target.style.display = 'none'; }} />
                        : <div className="pl-queue-thumb-ph">▶</div>
                      }
                      <div className="pl-queue-info">
                        <div className="pl-queue-title">{item.title || 'Unknown'}</div>
                        {item.uploader && <div className="pl-queue-sub">{item.uploader}</div>}
                      </div>
                      <span className="pl-queue-dur">{item.duration ? fmtDuration(item.duration) : '—'}</span>
                      <div className="pl-queue-st"><span className="q-st-badge queued">QUEUED</span></div>
                      <div className="pl-queue-remove" onClick={() => {
                        setRemovingFeedItems(prev => new Set([...prev, item.idx]));
                      }}>
                        <Ico name="x" size={10} />
                      </div>
                    </div>
                  ))}
                  {playlistItems.length > 12 && (
                    <div style={{ padding: '6px 14px', fontFamily: 'Share Tech Mono', fontSize: 9, color: 'var(--t4)', textAlign: 'center' }}>
                      +{playlistItems.length - 12} more ·{' '}
                      <span style={{ color: 'var(--cyan)', cursor: 'pointer' }} onClick={() => switchPage('queue')}>VIEW ALL →</span>
                    </div>
                  )}
                </div>
              </div>
            ) : (fetchingItems || fetchingPlaylistItems) ? (
              <div style={{ padding: '20px', fontFamily: 'Share Tech Mono', fontSize: 9, color: 'var(--t3)', textAlign: 'center' }}>
                FETCHING PLAYLIST ITEMS...
              </div>
            ) : (
              <div className="empty-state" style={{ padding: '24px' }}>
                <Mascot src={MASCOT_CHILLING} className="empty-mascot" wrapClass="empty-mascot-wrap" />
                <div className="empty-title">QUEUE EMPTY</div>
                <div className="empty-sub" onClick={() => switchPage('queue')}>VIEW QUEUE →</div>
              </div>
            )
          ) : (
            <div className="pl-queue-list" style={{ maxHeight: 216 }}>
              {(completedItems || []).slice(0, 12).map((item, i) => (
                <div key={i} className="q-completed-item">
                  {item.thumbnail
                    ? <img src={item.thumbnail} style={{ width: 64, height: 36, objectFit: 'cover', flexShrink: 0, borderRadius: 2 }} alt="" onError={e => { e.target.style.display='none'; }} />
                    : <div className="q-comp-thumb-ph">✓</div>}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="q-comp-title">{item.title || 'Unknown'}</div>
                    <div className="q-comp-meta">
                      <span className="q-st-badge completed">DONE</span>
                      {' '}{item.file_size ? fmtBytes(item.file_size) : ''}
                      {' · '}{timeAgo(item.completedAt)}
                    </div>
                  </div>
                </div>
              ))}
              {(!completedItems || completedItems.length === 0) && (
                <div style={{ padding: '20px', fontFamily: 'Share Tech Mono', fontSize: 9, color: 'var(--t4)', textAlign: 'center' }}>NO COMPLETED ITEMS YET</div>
              )}
            </div>
          )}
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

      {/* VAULT LINK PROMPT MODAL — shown for playlist downloads */}
      {vaultLinkPrompt && (
        <VaultLinkPromptModal
          info={info}
          url={url}
          config={config}
          opts={currentOpts()}
          onClose={() => setVaultLinkPrompt(false)}
          onJustDownload={() => { setVaultLinkPrompt(false); if (startDownloadRef.current) startDownloadRef.current(); }}
          onLinkAndDownload={(extra) => { setVaultLinkPrompt(false); if (startDownloadRef.current) startDownloadRef.current(extra); }}
          showNotif={showNotif}
        />
      )}
    </div>
  );
}

function VaultLinkPromptModal({ info, url, config, opts, onClose, onJustDownload, onLinkAndDownload, showNotif }) {
  const isAudio = opts.mode === 'audio';
  // What future syncs of the folder should download: the options chosen now
  const syncFormat = {
    sync_audio: isAudio, audio_format: opts.audio_format, audio_quality: opts.audio_quality,
    quality: opts.quality, container: opts.container,
    embed_thumbnail: opts.embed_thumbnail, embed_subs: opts.embed_subs,
    embed_chapters: opts.embed_chapters, embed_metadata: opts.embed_metadata,
    sponsorblock: opts.sponsorblock,
  };
  // Library mode keeps mellow_archive.txt, so items already in the folder are
  // skipped now and on every later sync
  const downloadInto = (folderPath) => onLinkAndDownload({ output_dir: folderPath, mode: 'library', sync_audio: isAudio });
  const [step, setStep] = React.useState('choose'); // 'choose' | 'link-existing' | 'create-new'
  const [vaultFolders, setVaultFolders] = React.useState([]);
  const [selectedFolder, setSelectedFolder] = React.useState('');
  const [newName, setNewName] = React.useState((info && info.title) ? info.title.slice(0, 40) : '');
  const [newFolder, setNewFolder] = React.useState('');
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (step === 'link-existing') {
      API.get('/api/vault').then(d => setVaultFolders(d.folders || [])).catch(() => {});
    }
  }, [step]);

  const browseNewFolder = () => {
    API.post('/api/browse-folder', {}).then(d => { if (d.path) setNewFolder(d.path); }).catch(() => {});
  };

  const handleLinkExisting = () => {
    if (!selectedFolder) return;
    setSaving(true);
    // Actually link the playlist, so the folder's Sync picks it up later
    API.post('/api/vault/playlists', { path: selectedFolder, url: url.trim(), sync_format: syncFormat })
      .then(() => {
        showNotif('Linked', 'Playlist linked to ' + selectedFolder.split(/[\\/]/).pop(), 'success');
        downloadInto(selectedFolder);
      })
      .catch(e => { showNotif('Error', e.message, 'error'); setSaving(false); });
  };

  const handleCreateNew = () => {
    const name = newName.trim();
    if (!name) { showNotif('Error', 'Name required', 'error'); return; }
    setSaving(true);
    API.post('/api/library', {
      name, url: url.trim(),
      // A picked folder is used as-is; otherwise a subfolder of the download folder
      folder: newFolder || config.output_dir || '',
      folder_name: name, use_subfolder: !newFolder,
      mode: isAudio ? 'AUDIO' : 'VIDEO', quality: opts.quality, container: opts.container,
      audio_format: opts.audio_format, sync_mode: 'add',
      embed_thumbnail: opts.embed_thumbnail, embed_chapters: opts.embed_chapters,
      embed_metadata: opts.embed_metadata, embed_subs: opts.embed_subs,
      sponsorblock: opts.sponsorblock,
    }).then(entry => {
      // Also remember the full format (incl. bitrate, which library entries
      // don't store) for the folder's future syncs
      return API.post('/api/vault/playlists', { path: entry.folder_path, url: url.trim(), sync_format: syncFormat })
        .then(() => entry);
    }).then(entry => {
      showNotif('Added to VAULT', name + ' saved to library', 'success');
      downloadInto(entry.folder_path);
    }).catch(e => { showNotif('Error', e.message, 'error'); setSaving(false); });
  };

  return (
    <Modal title="SAVE TO VAULT?" onClose={onClose} footer={null}>
      {step === 'choose' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t3)', textAlign: 'center', marginBottom: 6 }}>
            This is a playlist. Would you like to save it to the Vault?
          </div>
          <button className="btn btn-secondary btn-sm" style={{ width: '100%' }} onClick={() => setStep('link-existing')}>LINK TO EXISTING VAULT FOLDER</button>
          <button className="btn btn-secondary btn-sm" style={{ width: '100%' }} onClick={() => setStep('create-new')}>CREATE NEW VAULT ENTRY</button>
          <button className="btn btn-primary btn-sm" style={{ width: '100%' }} onClick={onJustDownload}>JUST DOWNLOAD</button>
        </div>
      )}
      {step === 'link-existing' && (
        <div>
          <div className="form-row">
            <div className="form-label">SELECT VAULT FOLDER</div>
            <select className="sel" style={{ width: '100%' }} value={selectedFolder} onChange={e => setSelectedFolder(e.target.value)}>
              <option value="">— Select folder —</option>
              {vaultFolders.map(f => <option key={f.path} value={f.path}>{f.name}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => setStep('choose')}>BACK</button>
            <button className="btn btn-primary btn-sm" onClick={handleLinkExisting} disabled={!selectedFolder || saving}>
              {saving ? 'LINKING...' : 'LINK AND DOWNLOAD'}
            </button>
          </div>
        </div>
      )}
      {step === 'create-new' && (
        <div>
          <div className="form-row">
            <div className="form-label">VAULT ENTRY NAME</div>
            <input className="form-input" value={newName} onChange={e => setNewName(e.target.value)} placeholder="My Playlist" />
          </div>
          <div className="form-row">
            <div className="form-label">SAVE FOLDER (OPTIONAL)</div>
            <div className="input-row">
              <input className="form-input" value={newFolder} onChange={e => setNewFolder(e.target.value)} placeholder="Uses Config default if empty" />
              <button className="btn btn-secondary btn-sm" onClick={browseNewFolder}>BROWSE</button>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => setStep('choose')}>BACK</button>
            <button className="btn btn-primary btn-sm" onClick={handleCreateNew} disabled={saving || !newName.trim()}>
              {saving ? 'SAVING...' : 'CREATE AND DOWNLOAD'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
