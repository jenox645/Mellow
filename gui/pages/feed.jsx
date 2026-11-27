// FEED page — URL ingest, options, active download, queue preview.
// The logic is useFeedPage (feed-logic.js); this file is Classic's view of it. A theme can
// register its own view of the Feed (gui/themes/slots.jsx, `pages: { feed: … }`).
'use strict';

import { fmtBytes, fmtCount, fmtDuration, fmtEta, fmtSpeed, isLinkLike, timeAgo } from '../lib/util.js';
import { SVG } from '../components/icons.jsx';
import { FileActions, FolderInput, FormatToggles, Mascot, Pipeline, SyncBanner } from '../components/common.jsx';
import { PendingList } from '../components/pending-list.jsx';
import { VaultLinkPromptModal } from '../components/vault-modals.jsx';
import { MASCOT_CHILLING } from '../lib/mascots.js';
import { AUDIO_FORMATS, AUDIO_QUALITIES, CONTAINERS, LOSSLESS_AUDIO, QUALITIES } from '../lib/constants.js';
import { useFeedPage } from './feed-logic.js';

// The Feed: its logic, drawn by the theme's view (Classic's unless the theme has one)
export function FeedPage({ View = ClassicFeedView, ...props }) {
  const feed = useFeedPage(props);
  return <View {...feed} />;
}

export function ClassicFeedView({
  url, setUrl, handleUrlKeyDown, handleAnalyze, analyzing, analyzeSlow, handlePaste, handleImportFile, importedUrls,
  importedFileName, downloadPath, setDownloadPath, browseDownloadPath, config, optsOpen, setOptsOpen, advOpen,
  setAdvOpen, mode, setMode, quality, setQuality, container, setContainer, audioFmt, setAudioFmt, audioQuality,
  setAudioQuality, toggles, setToggle, startTime, setStartTime, endTime, setEndTime, customFmt, setCustomFmt,
  savingPreset, setSavingPreset, presetName, setPresetName, savePreset, cancelPreset, applyPreset, deletePreset,
  currentOpts, videoChapters, chaptersOpen, setChaptersOpen, chapterSel, chosenChapters, toggleChapter,
  chooseAllChapters, chooseNoChapters, info, fetchingItems, fileName, setFileName, fileExt, estimatedBytes, wontFit,
  diskFree, playlistTotalSecs, openPreviousDownload, showPreviousDownload, analyzeWholeList, refreshPlaylistItems,
  handleDownload, submitting, isDownloading, scheduleLater, setScheduleLater, scheduleStart, handleCancel,
  pipelineStage, searchResults, pickSearchResult, pickMany, clearSearch, feedQTab, setFeedQTab, vaultLinkPrompt,
  closeVaultLinkPrompt, promptJustDownload, promptLinkAndDownload, dlState, stats, switchPage, showNotif,
  playlistItems, setPlaylistItems, completedItems, playlistTotalCount, playlistCompletedCount, isPaused, syncJobLabel,
  syncPlan, playlistJobId, onPause, onResume, onClearCompleted,
}) {
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
        <div className="url-row" data-tour="feed-url">
          <div className="url-input-wrap">
            <input
              className="url-input"
              type="text"
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={handleUrlKeyDown}
              placeholder="Paste a link (YouTube or any supported site) — or type words to search YouTube"
            />
          </div>
          <button
            className={'btn btn-secondary btn-sm' + (optsOpen ? ' active-btn' : '')}
            data-tour="feed-options-btn"
            onClick={() => setOptsOpen(o => !o)}
          >
            OPTIONS
          </button>
          {!info && (
            <button className="btn btn-primary" onClick={handleAnalyze} disabled={analyzing}>
              {isLinkLike(url) || !url.trim()
                ? (analyzing ? 'ANALYZING...' : 'ANALYZE →')
                : (analyzing ? 'SEARCHING...' : 'SEARCH →')}
            </button>
          )}
          <button className="btn btn-secondary btn-sm" data-tour="feed-paste" onClick={handlePaste}>PASTE</button>
          <button className="btn btn-secondary btn-sm" data-tour="feed-import" onClick={handleImportFile} title="Import URLs from .txt file">IMPORT FILE</button>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t4)', padding: '0 18px 8px', marginTop: -10 }}>
          ENTER: {!url.trim() ? 'paste' : !info && !analyzing ? (isLinkLike(url) ? 'analyze' : 'search') : 'download'}
          {importedFileName && <span style={{ color: 'var(--accent)', marginLeft: 10 }}>↑ {importedFileName} ({importedUrls ? importedUrls.length : 0} URLs)</span>}
          {analyzeSlow && (
            <span style={{ color: 'var(--warn)', marginLeft: 10 }}>
              STILL ANALYZING — big playlists take a while. If it never finishes, try Config → Network → Force IPv4.
            </span>
          )}
        </div>

        {/* SAVE TO — this download's folder; ↑/↓ recall the ones used before */}
        <div className="save-to-row" data-tour="feed-save-to">
          <span className="opts-label">SAVE TO</span>
          <FolderInput
            value={downloadPath}
            onChange={setDownloadPath}
            recent={config.recent_output_dirs}
            placeholder={'Default — ' + (config.output_dir || 'set in Config') + ((config.recent_output_dirs || []).length ? '   (↑ recent folders)' : '')}
            onBrowse={browseDownloadPath}
          />
        </div>

        {/* OPTIONS PANEL */}
        <div className={'opts-panel' + (optsOpen ? ' open' : '')} data-tour="feed-options">
          <div className="opts-inner">
            {/* PRESETS — one-click saved option bundles */}
            <div className="opts-row" data-tour="feed-presets">
              <span className="opts-label">PRESETS</span>
              <div className="pills" style={{ alignItems: 'center' }}>
                {(config.download_presets || []).map(p => (
                  <div key={p.name} className="pill" title={'Apply "' + p.name + '"'} onClick={() => applyPreset(p)}>
                    {p.name.toUpperCase()}
                    <span
                      style={{ marginLeft: 6, color: 'var(--danger)' }}
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
                      if (e.key === 'Escape') cancelPreset();
                    }}
                    onBlur={cancelPreset}
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

            <div data-tour="feed-toggles">
            <FormatToggles values={toggles} onChange={setToggle} media={mode} hints={{
              embed_subs: 'Embedded in the video — languages: ' + (config.sub_langs || 'en')
                + (config.keep_sub_files ? ', also kept as .srt files' : '') + ' (Config → Download Defaults)',
            }} />
            </div>

            {videoChapters.length > 0 && (
              <div className="opts-advanced">
                <div className="opts-adv-toggle" onClick={() => setChaptersOpen(o => !o)}>
                  <span dangerouslySetInnerHTML={{ __html: chaptersOpen ? SVG.chevron_down : SVG.chevron_right }} />
                  CHAPTERS · {videoChapters.length}
                  {chosenChapters.length > 0 && <span style={{ color: 'var(--accent)', marginLeft: 8 }}>{chosenChapters.length} CHOSEN</span>}
                </div>
                <div className={'opts-adv-body' + (chaptersOpen ? ' open' : '')}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t3)', margin: '4px 0 6px', display: 'flex', gap: 12 }}>
                    <span>Each chosen chapter is saved as its own file (clip start/end is ignored).</span>
                    <span style={{ cursor: 'pointer', color: 'var(--accent)' }} onClick={chooseAllChapters}>ALL</span>
                    <span style={{ cursor: 'pointer', color: 'var(--accent)' }} onClick={chooseNoChapters}>NONE</span>
                  </div>
                  <div style={{ maxHeight: 220, overflowY: 'auto' }}>
                    {videoChapters.map(c => (
                      <label key={c.index} className="opts-toggle-item" style={{ display: 'flex', gap: 8, padding: '2px 0' }}>
                        <input type="checkbox" checked={chapterSel.has(c.index)} onChange={() => toggleChapter(c.index)} />
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--t4)', minWidth: 90 }}>
                          {fmtDuration(c.start)} – {fmtDuration(c.end)}
                        </span>
                        {c.title}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div className="opts-advanced" data-tour="feed-advanced">
              <div className="opts-adv-toggle" data-tour="feed-advanced-toggle" onClick={() => setAdvOpen(o => !o)}>
                <span dangerouslySetInnerHTML={{ __html: advOpen ? SVG.chevron_down : SVG.chevron_right }} />
                ADVANCED OPTIONS
              </div>
              <div className={'opts-adv-body' + (advOpen ? ' open' : '')} data-tour="feed-advanced-body">
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
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* INFO CARD */}
        <div className={'info-card' + (info ? ' open' : '')} data-tour="feed-info">
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
                {!info.is_playlist && info.file_name ? (
                  // The title is the file's name: click it and type (no box, the title's own font).
                  // The hidden copy in data-value sizes the field to its text, so the extension follows it
                  <div className="info-title info-title-edit" data-tour="feed-file-name"
                    title={'Click to rename the file before DOWNLOAD (video: ' + (info.title || '') + ')'}>
                    <span className="info-title-field" data-value={(fileName ?? info.file_name) || info.file_name}>
                      <input className="info-title-input" aria-label="File name" spellCheck={false} size={1}
                        value={fileName ?? info.file_name} placeholder={info.file_name}
                        onChange={e => setFileName(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') e.currentTarget.blur();
                          if (e.key === 'Escape') { setFileName(null); e.currentTarget.blur(); }
                        }} />
                    </span>
                    <span className="info-filename-ext">{chosenChapters.length ? ' - 01 …' : ''}.{fileExt}</span>
                    {fileName !== null && fileName !== info.file_name ? (
                      <button className="info-filename-reset" title="Back to the name Config's file name template gives"
                        onClick={() => setFileName(null)}>↺</button>
                    ) : <span className="info-title-pen" aria-hidden="true">✎</span>}
                  </div>
                ) : (
                  <div className="info-title">{info.title || 'Unknown Title'}</div>
                )}
                <div className="info-meta">
                  {[info.uploader, info.platform, info.is_playlist ? (info.playlist_count + ' items') : null].filter(Boolean).join(' · ')}
                </div>
                {info.previous_download && (
                  <div className="info-prev" title={info.previous_download.file_path || ''}>
                    <span className="tag green">✓ ALREADY DOWNLOADED {timeAgo(info.previous_download.timestamp).toUpperCase()}</span>
                    {info.previous_download.exists ? (
                      <>
                        <span className="info-prev-link" onClick={openPreviousDownload}>OPEN</span>
                        <span className="info-prev-link" onClick={showPreviousDownload}>SHOW IN FOLDER</span>
                      </>
                    ) : (
                      <span style={{ color: 'var(--t4)' }}>file moved or deleted since</span>
                    )}
                  </div>
                )}
                {info.from_list && (
                  <div className="info-prev" data-tour="feed-from-list" title={info.from_list.url}>
                    <span className="tag amber">{info.from_list.mix ? 'FROM A YOUTUBE MIX' : 'FROM A PLAYLIST'}</span>
                    <span style={{ color: 'var(--t4)' }}>just this video</span>
                    <span className="info-prev-link" onClick={analyzeWholeList}>
                      {info.from_list.mix ? 'THE WHOLE MIX' : 'THE WHOLE PLAYLIST'}
                    </span>
                  </div>
                )}
                <div className="info-tags">
                  <span className="tag cyan">{info.platform || 'URL'}</span>
                  {info.is_playlist && (
                    <span className="tag amber" title="Items left to download, and their total length (where the site says)">
                      PLAYLIST · {playlistItems ? playlistItems.length : info.playlist_count}
                      {playlistTotalSecs > 0 && ' · ' + fmtDuration(playlistTotalSecs)}
                    </span>
                  )}
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

      {searchResults && (
        <SearchResults results={searchResults} info={info} onClear={clearSearch}
          onPick={pickSearchResult}
          onPickMany={pickMany} />
      )}

      {/* SYNC IN PROGRESS BANNER */}
      {isDownloading && dlState && dlState.library_id && info && (
        <div className="sync-banner">⚠ SYNC IN PROGRESS — Your previous analysis is on standby</div>
      )}

      {/* ACTIVE DOWNLOAD PANEL */}
      <div className={'dl-panel panel' + (isDownloading ? ' open' : '')} style={{ marginBottom: 16 }} data-tour="feed-progress">
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
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t-muted)', marginBottom: 3, letterSpacing: '0.1em' }}>
                      FROM: {(info.title || '').toUpperCase().slice(0, 32)}
                    </div>
                  )}
                  <div className="dl-title">{dlState.current_item_title || (info && info.title) || dlState.filename || 'Downloading...'}</div>
                  <div className="dl-ch">{[info && info.uploader, info && info.platform, info && info.duration ? fmtDuration(info.duration) : null].filter(Boolean).join(' · ')}</div>
                  <div className="dl-tags">
                    <span className="tag cyan">{mode === 'audio' ? audioFmt.toUpperCase() : container.toUpperCase()}</span>
                    {mode !== 'audio' && <span className="tag">{quality.toUpperCase()}</span>}
                    {toggles.sponsorblock && <span className="tag green">SPONSORBLOCK</span>}
                  </div>
                  <div className="prog-row">
                    <div className="prog-bar">
                      <div className="prog-bar-fill" style={{ width: (dlState.pct || 0) + '%', background: isPaused ? 'var(--warn)' : undefined }} />
                    </div>
                    <span className="prog-pct" style={{ color: isPaused ? 'var(--warn)' : undefined }}>
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
            {url && <span style={{ marginLeft: 'auto', cursor: 'pointer', color: 'var(--t3)', fontSize: 13, padding: '0 4px' }} title="Refresh queue" onClick={refreshPlaylistItems}>↻</span>}
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
                <span style={{ marginLeft: 'auto', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--danger)', padding: '0 10px' }} onClick={onClearCompleted}>CLEAR ✕</span>
              )}
            </div>
          )}
          {feedQTab === 'pending' ? (
            playlistItems && playlistItems.length > 0 ? (
              <div>
                <SyncBanner plan={syncPlan} label={syncJobLabel} />
                <PendingList items={playlistItems} setItems={setPlaylistItems} jobId={playlistJobId}
                  showNotif={showNotif} maxHeight={300}
                  skipHint={syncPlan ? '✕ SKIPS THIS TIME (THE NEXT SYNC TRIES AGAIN)' : null} />
              </div>
            ) : (syncPlan || syncJobLabel) ? (
              <SyncBanner plan={syncPlan} label={syncJobLabel} />
            ) : fetchingItems ? (
              <div style={{ padding: '20px', fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t3)', textAlign: 'center' }}>
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
                    ? <img src={item.thumbnail} loading="lazy" decoding="async" style={{ width: 64, height: 36, objectFit: 'cover', flexShrink: 0, borderRadius: 2 }} alt="" onError={e => { e.target.style.display='none'; }} />
                    : <div className="q-comp-thumb-ph">✓</div>}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="q-comp-title">{item.title || 'Unknown'}</div>
                    <div className="q-comp-meta">
                      <span className="q-st-badge completed">DONE</span>
                      {' '}{item.file_size ? fmtBytes(item.file_size) + ' · ' : ''}
                      {timeAgo(item.completedAt)}
                    </div>
                  </div>
                  <FileActions path={item.file_path} />
                </div>
              ))}
              {(!completedItems || completedItems.length === 0) && (
                <div style={{ padding: '20px', fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t4)', textAlign: 'center' }}>NO COMPLETED ITEMS YET</div>
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
          onClose={closeVaultLinkPrompt}
          onJustDownload={promptJustDownload}
          onLinkAndDownload={promptLinkAndDownload}
          showNotif={showNotif}
        />
      )}
    </div>
  );
}

// YouTube search results: click one to analyze it (the list stays for the
// next pick), or tick several and download them together
function SearchResults({ results, info, onPick, onPickMany, onClear }) {
  const [ticked, setTicked] = React.useState(() => new Set());
  React.useEffect(() => { setTicked(new Set()); }, [results]);
  const tick = (e, key) => {
    e.stopPropagation();
    setTicked(prev => { const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  };
  const chosen = results.items.filter(i => ticked.has(i.url));
  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-hud" /><div className="panel-hud-br" />
      <div className="ph">
        <span className="ptag">SEARCH</span>
        <span className="ptitle" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          "{results.query}"
        </span>
        <span className="psub">{chosen.length ? chosen.length + ' TICKED' : results.items.length + ' RESULTS'}</span>
        {chosen.length > 0 && (
          <button className="btn btn-primary btn-sm" style={{ marginLeft: 10, padding: '4px 10px', fontSize: 10.5 }}
            data-tour="search-pick-many" title="Put the ticked videos in one list, then DOWNLOAD them with the options below"
            onClick={() => onPickMany(chosen)}>LIST {chosen.length} →</button>
        )}
        <span style={{ cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t3)', paddingLeft: 10 }}
          title="Close the results" onClick={onClear}>CLEAR ✕</span>
      </div>
      <div className="pl-queue-list" style={{ maxHeight: 360 }}>
        {results.items.map(item => {
          const picked = info && (info.webpage_url === item.url || info.id === item.id);
          return (
            <div key={item.url || item.idx} className={'pl-queue-item search-result' + (picked ? ' picked' : '')}
              title="Analyze this one" style={{ cursor: 'pointer' }}
              onClick={() => onPick(item)}>
              <span className={'pl-queue-check search-check' + (ticked.has(item.url) ? ' on' : '')} role="checkbox"
                aria-checked={ticked.has(item.url)} title="Tick to download several" onClick={e => tick(e, item.url)}>
                {ticked.has(item.url) ? '✓' : ''}
              </span>
              {item.thumbnail
                ? <img src={item.thumbnail} loading="lazy" decoding="async" className="pl-queue-thumb" alt="" onError={e => { e.target.style.display = 'none'; }} />
                : <div className="pl-queue-thumb-ph">▶</div>}
              <div className="pl-queue-info">
                <div className="pl-queue-title">{item.title || item.url}</div>
                <div className="pl-queue-sub">
                  {[item.uploader, item.view_count != null ? fmtCount(item.view_count) + ' views' : null].filter(Boolean).join(' · ')}
                </div>
              </div>
              <span className="pl-queue-dur">{item.duration ? fmtDuration(item.duration) : '—'}</span>
              <div className="pl-queue-st">
                <span className={'q-st-badge ' + (picked ? 'completed' : 'queued')}>{picked ? 'PICKED' : 'ANALYZE'}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
