// Tactical's Feed: the INTAKE console. A command line takes the target, the loadout is always on the
// table (mode plates, a quality ruler, extras as lamp switches), the analyzed target is a dossier with
// a fact grid, and the right column is one transfer instrument (ring gauge, readouts, speed trace,
// pipeline nodes, the destination disk) that stands by with Mellow asleep. It draws what useFeedPage
// returns (gui/pages/feed-logic.js) and calls only its handlers; no API here.
'use strict';

import { fmtBytes, fmtDuration, fmtEta, fmtSpeed, isLinkLike, timeAgo } from '../../lib/util.js';
import { togglesFor } from '../../lib/formats.js';
import {
  AUDIO_FORMATS, AUDIO_QUALITIES, CONTAINERS, LOSSLESS_AUDIO, QUALITIES, TACTICAL_SPEED_TRACE_SAMPLES as SPEED_SAMPLES,
} from '../../lib/constants.js';
import { FileActions, FolderInput, SyncBanner } from '../../components/common.jsx';
import { PendingList } from '../../components/pending-list.jsx';
import { VaultLinkPromptModal } from '../../components/vault-modals.jsx';
import { SearchResults } from '../../pages/feed.jsx';
import { Brackets, Caption, Hatch, LabelBlock, Node, Reg, RingGauge, Ruler, ScanLine, Spark } from './ornaments.jsx';

const STEPS = ['FETCH', 'META', 'DL', 'MERGE', 'INDEX', 'DB'];
const QUALITY_STOPS = QUALITIES.slice().reverse().map(q => ({ key: q, label: q }));
const BITRATE_STOPS = AUDIO_QUALITIES.slice().reverse().map(([key, label]) => ({ key, label }));

// The page head every Tactical page shares: an outlined index numeral, the section's name, a rule
export function PageHead({ num, kicker, title, jp, children }) {
  return (
    <div className="tx-head">
      <span className="tx-head-num" aria-hidden="true">{num}</span>
      <div className="tx-head-sub">
        <span className="tx-micro">{kicker}</span>
        <span className="tx-head-title">{title}</span>
      </div>
      {jp && <span className="tx-head-jp">{jp}</span>}
      <svg className="tx-head-rule" aria-hidden="true" preserveAspectRatio="none">
        <line className="tx-draw" x1="0" y1="11.5" x2="100%" y2="11.5" pathLength="1" />
      </svg>
      <div className="tx-head-side">{children}</div>
    </div>
  );
}

// The last samples of the download's speed: the trace the transfer column draws
function useSpeedTrace(dlState, live) {
  const [samples, setSamples] = React.useState([]);
  React.useEffect(() => {
    if (!live) return;
    const v = (dlState && dlState.speed) || 0;
    setSamples(s => s.concat(v).slice(-SPEED_SAMPLES));
  }, [dlState, live]);
  return live ? samples : [];
}

export function TacticalFeedView({
  url, setUrl, handleUrlKeyDown, handleAnalyze, analyzing, analyzeSlow, handlePaste, handleImportFile, importedUrls,
  importedFileName, downloadPath, setDownloadPath, browseDownloadPath, config, advOpen, setAdvOpen, mode, setMode,
  quality, setQuality, container, setContainer, audioFmt, setAudioFmt, audioQuality, setAudioQuality, toggles,
  setToggle, startTime, setStartTime, endTime, setEndTime, customFmt, setCustomFmt, savingPreset, setSavingPreset,
  presetName, setPresetName, savePreset, cancelPreset, applyPreset, deletePreset, currentOpts, videoChapters,
  chaptersOpen, setChaptersOpen, chapterSel, chosenChapters, toggleChapter, chooseAllChapters, chooseNoChapters,
  info, fetchingItems, fileName, setFileName, fileExt, estimatedBytes, wontFit, diskFree, playlistTotalSecs,
  openPreviousDownload, showPreviousDownload, analyzeWholeList, refreshPlaylistItems, handleDownload, submitting,
  isDownloading, scheduleLater, setScheduleLater, scheduleStart, handleCancel, pipelineStage, searchResults,
  pickSearchResult, pickMany, clearSearch, feedQTab, setFeedQTab, vaultLinkPrompt, closeVaultLinkPrompt,
  promptJustDownload, promptLinkAndDownload, dlState, stats, showNotif, playlistItems, setPlaylistItems,
  completedItems, playlistTotalCount, playlistCompletedCount, isPaused, syncJobLabel, syncPlan, playlistJobId,
  onPause, onResume, onClearCompleted,
}) {
  const live = !!(isDownloading && dlState);
  const trace = useSpeedTrace(dlState, live && !isPaused);
  const lossless = LOSSLESS_AUDIO.includes(audioFmt);
  const fmtLabel = mode === 'audio' ? audioFmt.toUpperCase() : container.toUpperCase();
  const pending = playlistItems ? playlistItems.length : 0;
  const done = completedItems ? completedItems.length : 0;
  const hasRoster = pending > 0 || done > 0 || !!syncPlan || !!syncJobLabel || fetchingItems;
  const enterDoes = !url.trim() ? 'PASTE' : !info && !analyzing ? (isLinkLike(url) ? 'ANALYZE' : 'SEARCH') : 'DOWNLOAD';

  return (
    <div className="content active">
      <div className="tx-page">
        <PageHead num="01" kicker="SECTION 01 // COMMAND" title="INTAKE" jp="取り込み">
          <span className="tx-micro">RECORDS {(stats.total_downloads || 0).toLocaleString()}</span>
          <Reg />
          <span className="tx-micro">QUEUE {pending}</span>
        </PageHead>

        <div className="tf">
          <div className="tf-main">
            {/* A — the target: one command line */}
            <div className="tx-block tf-target tx-bracketed">
              <Brackets />
              <Caption num="A" title="Target" jp="対象">
                <div className="tx-menu">
                  <button type="button" data-tour="feed-paste" onClick={handlePaste}>Paste</button>
                  <button type="button" data-tour="feed-import" onClick={handleImportFile} title="Import URLs from a .txt file">Import .txt</button>
                </div>
              </Caption>
              <div className="tf-cmdline" data-tour="feed-url">
                <span className="tf-prompt" aria-hidden="true">&gt;</span>
                <input className="tf-url" type="text" value={url} spellCheck={false}
                  aria-label="Link or search words"
                  onChange={e => setUrl(e.target.value)} onKeyDown={handleUrlKeyDown}
                  placeholder="Paste a link (YouTube or any supported site) — or type words to search YouTube" />
                {!info ? (
                  <button type="button" className="tx-btn go" onClick={handleAnalyze} disabled={analyzing}>
                    {isLinkLike(url) || !url.trim()
                      ? (analyzing ? 'Analyzing…' : 'Analyze →')
                      : (analyzing ? 'Searching…' : 'Search →')}
                  </button>
                ) : (
                  <button type="button" className="tx-btn" onClick={handleAnalyze} disabled={analyzing || isDownloading} title="Re-analyze the link">
                    ↺ Rescan
                  </button>
                )}
              </div>
              <div className="tf-hint">
                <span className="tx-micro">↵ {enterDoes}</span>
                <span className="tx-micro">WORDS SEARCH YOUTUBE</span>
                {importedFileName && <span className="tx-micro hot">↑ {importedFileName} · {importedUrls ? importedUrls.length : 0} URLS</span>}
                {analyzeSlow && (
                  <span className="tx-micro warn">STILL ANALYZING — big playlists take a while. If it never finishes: Config → Network → Force IPv4</span>
                )}
              </div>
              <div className="tf-dest" data-tour="feed-save-to">
                <span className="tx-micro">DEST</span>
                <FolderInput value={downloadPath} onChange={setDownloadPath} recent={config.recent_output_dirs}
                  placeholder={'Default — ' + (config.output_dir || 'set in Config') + ((config.recent_output_dirs || []).length ? '   (↑ recent folders)' : '')}
                  onBrowse={browseDownloadPath} />
              </div>
            </div>

            {/* B — the loadout, always on the table */}
            <div className="tx-block tf-load" data-tour="feed-options">
              <Caption num="B" title="Loadout" jp="装備" />
              <div className="tf-modes" role="radiogroup" aria-label="What to download">
                {[['video', 'VID', 'VIDEO'], ['audio', 'AUD', 'AUDIO ONLY']].map(([m, big, cap]) => (
                  <button key={m} type="button" role="radio" aria-checked={mode === m}
                    className={'tf-mode' + (mode === m ? ' on' : '')} onClick={() => setMode(m)}>
                    <b>{big}</b><span>{cap}</span>
                  </button>
                ))}
              </div>
              {mode === 'video' ? (
                <>
                  <div className="tf-scale">
                    <span className="tx-micro">QUALITY</span>
                    <Ruler stops={QUALITY_STOPS} value={quality} onPick={setQuality} label="Quality" />
                  </div>
                  <div className="tf-pick">
                    <span className="tx-micro">CONTAINER</span>
                    <div className="tx-segsel" role="radiogroup" aria-label="Container">
                      {CONTAINERS.map(c => (
                        <button key={c} type="button" role="radio" aria-checked={container === c}
                          className={container === c ? 'on' : ''} onClick={() => setContainer(c)}>{c}</button>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="tf-scale" title={lossless ? audioFmt.toUpperCase() + ' is lossless: bitrate does not apply' : 'Target bitrate of the converted file'}>
                    <span className="tx-micro">BITRATE{lossless ? ' — LOSSLESS' : ''}</span>
                    <Ruler stops={BITRATE_STOPS} value={audioQuality} onPick={setAudioQuality} disabled={lossless} label="Bitrate" />
                  </div>
                  <div className="tf-pick">
                    <span className="tx-micro">FORMAT</span>
                    <div className="tx-segsel" role="radiogroup" aria-label="Audio format">
                      {AUDIO_FORMATS.map(f => (
                        <button key={f} type="button" role="radio" aria-checked={audioFmt === f}
                          className={audioFmt === f ? 'on' : ''} onClick={() => setAudioFmt(f)}>{f}</button>
                      ))}
                    </div>
                  </div>
                </>
              )}

              <div className="tf-toggles" data-tour="feed-toggles">
                {togglesFor(mode).map(t => {
                  const on = !!toggles[t.key];
                  const hint = t.key === 'embed_subs'
                    ? 'Embedded in the video — languages: ' + (config.sub_langs || 'en')
                      + (config.keep_sub_files ? ', also kept as .srt files' : '') + ' (Config → Download Defaults)'
                    : t.hint;
                  return (
                    <button key={t.key} type="button" role="switch" aria-checked={on} title={hint}
                      className={'tf-tog' + (on ? ' on' : '')} onClick={() => setToggle(t.key, !on)}>
                      <i aria-hidden="true" />{t.label}
                    </button>
                  );
                })}
              </div>

              <div className="tf-more" data-tour="feed-presets">
                <span className="tx-micro">PRESETS</span>
                {(config.download_presets || []).map(p => (
                  <span key={p.name} className="tf-preset">
                    <button type="button" title={'Apply "' + p.name + '"'} onClick={() => applyPreset(p)}>{p.name.toUpperCase()}</button>
                    <button type="button" title="Delete preset" aria-label={'Delete preset ' + p.name} onClick={() => deletePreset(p.name)}>✕</button>
                  </span>
                ))}
                {savingPreset ? (
                  <input className="tf-input" style={{ width: 150 }} autoFocus placeholder="Preset name…" value={presetName}
                    onChange={e => setPresetName(e.target.value)} onBlur={cancelPreset}
                    onKeyDown={e => { if (e.key === 'Enter') savePreset(); if (e.key === 'Escape') cancelPreset(); }} />
                ) : (
                  <span className="tf-preset"><button type="button" title="Save the current options as a preset" onClick={() => setSavingPreset(true)}>+ SAVE CURRENT</button></span>
                )}
                <div className="tx-menu" style={{ marginLeft: 'auto' }}>
                  {videoChapters.length > 0 && (
                    <button type="button" className={chosenChapters.length ? 'hot' : ''} onClick={() => setChaptersOpen(o => !o)}>
                      Chapters {videoChapters.length}{chosenChapters.length ? ' · ' + chosenChapters.length + ' chosen' : ''} {chaptersOpen ? '▾' : '▸'}
                    </button>
                  )}
                  <button type="button" data-tour="feed-advanced-toggle" onClick={() => setAdvOpen(o => !o)}>
                    Extended {advOpen ? '▾' : '▸'}
                  </button>
                </div>
              </div>

              {videoChapters.length > 0 && (
                <div className={'tf-drawer' + (chaptersOpen ? ' open' : '')}>
                  <div className="tf-hint" style={{ marginTop: 0 }}>
                    <span className="tx-micro">EACH CHOSEN CHAPTER IS SAVED AS ITS OWN FILE (CLIP START/END IS IGNORED)</span>
                    <div className="tx-menu" style={{ marginLeft: 'auto' }}>
                      <button type="button" onClick={chooseAllChapters}>All</button>
                      <button type="button" onClick={chooseNoChapters}>None</button>
                    </div>
                  </div>
                  <div className="tf-chapters">
                    {videoChapters.map(c => (
                      <label key={c.index} className="tf-chap">
                        <input type="checkbox" checked={chapterSel.has(c.index)} onChange={() => toggleChapter(c.index)} />
                        <span className="t">{fmtDuration(c.start)} – {fmtDuration(c.end)}</span>
                        <span>{c.title}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
              <div className={'tf-drawer' + (advOpen ? ' open' : '')} data-tour="feed-advanced">
                <div className={'tf-adv' + (advOpen ? ' open' : '')} data-tour="feed-advanced-body">
                  <label><span className="tx-micro">CLIP START (HH:MM:SS)</span>
                    <input className="tf-input" value={startTime} onChange={e => setStartTime(e.target.value)} placeholder="00:01:30" /></label>
                  <label><span className="tx-micro">CLIP END (HH:MM:SS)</span>
                    <input className="tf-input" value={endTime} onChange={e => setEndTime(e.target.value)} placeholder="00:03:00" /></label>
                  <label><span className="tx-micro">CUSTOM FORMAT STRING</span>
                    <input className="tf-input" value={customFmt} onChange={e => setCustomFmt(e.target.value)} placeholder="bv[height<=1080]+ba/best" /></label>
                </div>
              </div>
            </div>

            {/* C — the analyzed target */}
            {info ? (
              <div className="tx-block tf-dossier" data-tour="feed-info">
                <div className="tf-thumb tx-bracketed">
                  <Brackets size={9} inset={-5} />
                  {info.thumbnail && <img src={info.thumbnail} alt="" onError={e => { e.target.style.display = 'none'; }} />}
                  <svg className="tf-cross" viewBox="0 0 256 144" preserveAspectRatio="none" aria-hidden="true">
                    <path d="M128 64v16M120 72h16" stroke="currentColor" strokeWidth="1" fill="none" />
                  </svg>
                  <span className="tf-fmt">{fmtLabel}</span>
                  {(info.duration || playlistTotalSecs > 0) && (
                    <LabelBlock className="dark sm" value={fmtDuration(info.duration || playlistTotalSecs)}
                      caption={info.is_playlist ? (playlistItems ? playlistItems.length : info.playlist_count) + ' ITEMS' : 'LENGTH'} />
                  )}
                </div>

                <div className="tf-dbody">
                  {!info.is_playlist && info.file_name ? (
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
                  <dl className="tf-facts">
                    <div><dt>SOURCE</dt><dd>{info.platform || 'URL'}</dd></div>
                    <div><dt>CHANNEL</dt><dd title={info.uploader || ''}>{info.uploader || '—'}</dd></div>
                    {info.is_playlist
                      ? <div><dt>ITEMS</dt><dd>{playlistItems ? playlistItems.length : info.playlist_count} LEFT</dd></div>
                      : <div><dt>{mode === 'audio' ? 'FORMAT' : 'QUALITY'}</dt><dd>{mode === 'audio' ? audioFmt.toUpperCase() : quality.toUpperCase()}</dd></div>}
                    <div title={wontFit ? 'Only ' + fmtBytes(diskFree) + ' free on the download drive' : 'Estimated from the formats the site offers'}>
                      <dt>{wontFit ? 'WON\'T FIT' : 'EST SIZE'}</dt>
                      <dd className={wontFit ? 'err' : ''}>{estimatedBytes ? '≈ ' + fmtBytes(estimatedBytes) : '—'}</dd>
                    </div>
                  </dl>
                  {info.previous_download && (
                    <div className="tf-note" title={info.previous_download.file_path || ''}>
                      <span className="ok">✓ ALREADY DOWNLOADED {timeAgo(info.previous_download.timestamp).toUpperCase()}</span>
                      {info.previous_download.exists ? (
                        <>
                          <span className="lnk" onClick={openPreviousDownload}>OPEN</span>
                          <span className="lnk" onClick={showPreviousDownload}>SHOW IN FOLDER</span>
                        </>
                      ) : <span>file moved or deleted since</span>}
                    </div>
                  )}
                  {info.from_list && (
                    <div className="tf-note" data-tour="feed-from-list" title={info.from_list.url}>
                      <span className="amber">{info.from_list.mix ? 'FROM A YOUTUBE MIX' : 'FROM A PLAYLIST'}</span>
                      <span>just this video</span>
                      <span className="lnk" onClick={analyzeWholeList}>{info.from_list.mix ? 'THE WHOLE MIX' : 'THE WHOLE PLAYLIST'}</span>
                    </div>
                  )}
                  {info.is_playlist && !info.from_list && (
                    <div className="tf-note"><span className="amber">PLAYLIST</span> each item is saved as it finishes</div>
                  )}
                </div>

                <div className="tf-acts">
                  <button type="button" className="tx-btn go tf-go" onClick={handleDownload}
                    disabled={(isDownloading && !scheduleLater) || submitting}>
                    {submitting ? 'Starting…' : scheduleLater ? '⏾ At ' + scheduleStart : isDownloading ? 'Active' : 'Download'}
                    <small>{isDownloading && playlistTotalCount > 1 ? (playlistCompletedCount + 1) + ' / ' + playlistTotalCount
                      : estimatedBytes ? '≈ ' + fmtBytes(estimatedBytes) : fmtLabel}</small>
                  </button>
                  <button type="button" className={'tx-btn' + (scheduleLater ? ' amber' : '')}
                    title={'Queue it to start at ' + scheduleStart + ' (Config → Behavior)'} onClick={() => setScheduleLater(v => !v)}>
                    ⏾ Later{scheduleLater ? ' ✓' : ''}
                  </button>
                </div>
              </div>
            ) : !searchResults && (
              <div className="tx-block tf-empty">
                <div className="tf-empty-grid tx-bracketed" aria-hidden="true"><Brackets size={8} inset={-3} /><Reg size={13} /></div>
                <p><b>No target.</b> Paste a link from YouTube or any site yt-dlp knows, or type words to search YouTube.
                  The loadout above is what the download gets.</p>
              </div>
            )}

            {searchResults && (
              <SearchResults results={searchResults} info={info} onClear={clearSearch} onPick={pickSearchResult} onPickMany={pickMany} />
            )}
            {isDownloading && dlState && dlState.library_id && info && (
              <Hatch className="warn">SYNC IN PROGRESS — YOUR ANALYSIS IS ON STANDBY</Hatch>
            )}

            {/* D — the roster: what's left, what's done */}
            {hasRoster && (
              <div className="tx-block tf-roster">
                <div className="tf-roster-head">
                  <Caption num="C" title="Roster" jp="名簿" />
                  {url && <div className="tx-menu"><button type="button" onClick={refreshPlaylistItems} title="Read the list again">↻ Reload</button></div>}
                  <div className="tx-tabs" role="tablist">
                    <button type="button" role="tab" aria-selected={feedQTab === 'pending'} className={feedQTab === 'pending' ? 'on' : ''}
                      onClick={() => setFeedQTab('pending')}>Pending {pending}</button>
                    <button type="button" role="tab" aria-selected={feedQTab === 'completed'} className={feedQTab === 'completed' ? 'on' : ''}
                      onClick={() => setFeedQTab('completed')}>Done {done}</button>
                  </div>
                  {feedQTab === 'completed' && done > 0 && onClearCompleted && (
                    <div className="tx-menu"><button type="button" onClick={onClearCompleted}>Clear ✕</button></div>
                  )}
                </div>
                {feedQTab === 'pending' ? (
                  pending > 0 ? (
                    <div>
                      <SyncBanner plan={syncPlan} label={syncJobLabel} />
                      <PendingList items={playlistItems} setItems={setPlaylistItems} jobId={playlistJobId}
                        showNotif={showNotif} maxHeight={340}
                        skipHint={syncPlan ? '✕ SKIPS THIS TIME (THE NEXT SYNC TRIES AGAIN)' : null} />
                    </div>
                  ) : (syncPlan || syncJobLabel) ? <SyncBanner plan={syncPlan} label={syncJobLabel} />
                    : <div className="tf-roster-empty tx-micro"><Node kind="diamond" />{fetchingItems ? 'READING THE LIST…' : 'NOTHING LEFT TO DOWNLOAD'}</div>
                ) : done > 0 ? (
                  <div className="pl-queue-list" style={{ maxHeight: 340 }}>
                    {completedItems.slice(0, 40).map((item, i) => (
                      <div key={i} className="tf-done">
                        <span className="n">{String(i + 1).padStart(2, '0')}</span>
                        {item.thumbnail
                          ? <img src={item.thumbnail} alt="" onError={e => { e.target.style.visibility = 'hidden'; }} />
                          : <span className="ph" />}
                        <div style={{ minWidth: 0 }}>
                          <div className="t">{item.title || 'Unknown'}</div>
                          <div className="m"><b>DONE</b> · {item.file_size ? fmtBytes(item.file_size) + ' · ' : ''}{timeAgo(item.completedAt)}</div>
                        </div>
                        <FileActions path={item.file_path} />
                      </div>
                    ))}
                  </div>
                ) : <div className="tf-roster-empty tx-micro"><Node kind="diamond" />NOTHING FINISHED YET</div>}
              </div>
            )}
          </div>

          {/* The transfer instrument */}
          <Transfer live={live} dlState={dlState} isPaused={isPaused} trace={trace} pipelineStage={pipelineStage}
            info={info} playlistTotalCount={playlistTotalCount} playlistCompletedCount={playlistCompletedCount}
            onPause={onPause} onResume={onResume} handleCancel={handleCancel}
            diskFree={diskFree} estimatedBytes={estimatedBytes} wontFit={wontFit} />
        </div>
      </div>

      {vaultLinkPrompt && (
        <VaultLinkPromptModal info={info} url={url} config={config} opts={currentOpts()} onClose={closeVaultLinkPrompt}
          onJustDownload={promptJustDownload} onLinkAndDownload={promptLinkAndDownload} showNotif={showNotif} />
      )}
    </div>
  );
}

function Transfer({ live, dlState, isPaused, trace, pipelineStage, info, playlistTotalCount, playlistCompletedCount,
  onPause, onResume, handleCancel, diskFree, estimatedBytes, wontFit }) {
  const pct = live ? (dlState.pct || 0) : 0;
  const processing = live && (pipelineStage === 'processing' || pipelineStage === 'indexing');
  const state = !live ? 'STANDBY' : isPaused ? 'PAUSED' : processing ? 'PROCESSING' : 'RECEIVING';
  const multi = playlistTotalCount > 1;
  const item = String(Math.min(playlistCompletedCount + 1, playlistTotalCount)).padStart(2, '0');
  const stepAt = { starting: 0, processing: 3, indexing: 4, done: 5 }[pipelineStage] ?? 2;
  const [speedNum, speedUnit] = live ? fmtSpeed(dlState.speed).split(' ') : ['—', 'SPEED'];
  const thumb = live && (dlState.current_item_thumb || (info && info.thumbnail));
  const share = estimatedBytes && diskFree ? Math.min(1, estimatedBytes / diskFree) : 0;
  const got = live && dlState.downloaded ? fmtBytes(dlState.downloaded).split(' ') : ['—'];

  return (
    <div className={'tx-block tf-xfer tx-bracketed' + (live ? ' live' : '') + (isPaused ? ' paused' : '')} data-tour="feed-progress">
      <Brackets />
      <Caption num="D" title="Transfer" jp="転送" />
      <div className="tf-xfer-state">
        <b><i aria-hidden="true" />{state}</b>
        <span>{multi && live ? 'ITEM ' + item + ' / ' + String(playlistTotalCount).padStart(2, '0') : live ? 'SINGLE' : 'NO JOB'}</span>
      </div>

      <div className="tf-ringwrap">
        <RingGauge value={pct / 100} size={236} live={live && !isPaused} warn={isPaused}>
          {live ? (
            <>
              <div className="tf-pct" key={Math.floor(pct)}>{Math.floor(pct)}<small>%</small></div>
              <div className="tf-pct-cap">{isPaused ? 'PAUSED' : multi ? <>ITEM <b>{item}</b> OF {String(playlistTotalCount).padStart(2, '0')}</> : fmtBytes(dlState.downloaded) + ' / ' + fmtBytes(dlState.total)}</div>
            </>
          ) : (
            <>
              <div className="tf-sleep" role="img" aria-label="Mellow, asleep: nothing is downloading" />
              <div className="tf-pct-cap">STANDING BY</div>
            </>
          )}
        </RingGauge>
      </div>

      <div className="tf-readouts">
        <LabelBlock className="dark" value={speedNum} caption={speedUnit.toUpperCase()} />
        <LabelBlock className="dark" value={live ? fmtEta(dlState.eta) : '—'} caption="ETA" />
        <LabelBlock className="dark" value={got[0]} caption={got[1] ? got[1].toUpperCase() + ' DONE' : 'RECEIVED'} />
      </div>

      <Spark samples={trace} className={live && !isPaused ? 'live' : ''} label={live ? 'SPEED TRACE' : 'SPEED TRACE · IDLE'} />

      {live && (
        <div className="tf-now">
          {thumb ? <img src={thumb} alt="" onError={e => { e.target.style.visibility = 'hidden'; }} /> : <span className="ph" />}
          <div style={{ minWidth: 0 }}>
            <div className="s">NOW{info && info.is_playlist ? ' · ' + (info.title || '').toUpperCase().slice(0, 28) : ''}</div>
            <div className="t">{dlState.current_item_title || (info && info.title) || dlState.filename || 'Downloading…'}</div>
          </div>
          <ScanLine active={!isPaused} />
        </div>
      )}

      <div className="tf-steps" aria-label="Pipeline">
        {STEPS.map((s, i) => {
          const cls = !live ? '' : i < stepAt ? 'done' : i === stepAt ? 'now' : '';
          return <div key={s} className={'tf-step ' + cls}><Node kind="diamond" size={9} filled={cls === 'done'} />{s}</div>;
        })}
      </div>

      <div className="tf-ctl">
        {isPaused
          ? <button type="button" className="tx-btn amber" onClick={onResume} disabled={!live}>▶ Resume</button>
          : <button type="button" className="tx-btn" onClick={onPause} disabled={!live}>❚❚ Pause</button>}
        <button type="button" className="tx-btn danger" onClick={handleCancel} disabled={!live}>Cancel</button>
      </div>

      <div className="tf-disk" title="Free space on the download drive, and the share this download needs">
        <div className="tf-disk-row">
          <span className="tx-micro">DEST DISK</span>
          <b className={wontFit ? 'err' : ''}>{diskFree ? fmtBytes(diskFree) + ' FREE' : '—'}</b>
        </div>
        <div className="tf-disk-bar">
          <span className={'tf-disk-fill' + (wontFit ? ' err' : '')} style={{ transform: `scaleX(${estimatedBytes ? Math.max(share, 0.01) : 1})` }} />
        </div>
        <div className="tf-disk-scale">
          <span>0</span>
          <span>{estimatedBytes ? (wontFit ? 'WON\'T FIT · ' : 'THIS DOWNLOAD ≈ ') + fmtBytes(estimatedBytes) : 'NO ESTIMATE'}</span>
        </div>
      </div>
    </div>
  );
}
