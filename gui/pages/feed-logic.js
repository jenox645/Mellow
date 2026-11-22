// The Feed's logic: its state, effects, API calls and handlers, shared by every theme.
// useFeedPage(props) takes what the App hands the Feed and returns everything a view
// draws and every handler it calls (the view itself never calls the API).
'use strict';

import { API, cancelShownDownload } from '../lib/api.js';
import { estimateDownloadBytes, idxRanges, isLinkLike, videoInPlaylist } from '../lib/util.js';
import { defaultToggles, togglesFrom } from '../lib/formats.js';
import { hasSession, useSessionState } from '../lib/hooks.js';
import { ANALYZE_SLOW_MS } from '../lib/constants.js';

export function useFeedPage(props) {
  const { dlState, sysInfo, showNotif, config, setConfig, suggestedUrl, onSuggestedConsumed, onPlaylistDownload, playlistItems, setPlaylistItems, setPlaylistJobId, errorActions } = props;
  // Kept in sessionStorage: the Feed comes back as it was after switching pages
  const [url, setUrl] = useSessionState('feed_url', '');
  const [analyzing, setAnalyzing] = React.useState(false);
  // Analyze normally takes a few seconds; past ANALYZE_SLOW_MS say why it may hang
  const [analyzeSlow, setAnalyzeSlow] = React.useState(false);
  React.useEffect(() => {
    if (!analyzing) { setAnalyzeSlow(false); return undefined; }
    const t = setTimeout(() => setAnalyzeSlow(true), ANALYZE_SLOW_MS);
    return () => clearTimeout(t);
  }, [analyzing]);
  const [fetchingItems, setFetchingItems] = React.useState(false);
  const [info, setInfo] = useSessionState('feed_info', null);
  // Words instead of a link: a YouTube search ({query, items}); kept while
  // results are analyzed one by one
  const [searchResults, setSearchResults] = useSessionState('feed_search', null);
  const [optsOpen, setOptsOpen] = React.useState(false);
  const [advOpen, setAdvOpen] = React.useState(false);
  // Chapter picker: indexes of the chosen chapters of the analyzed video
  const [chaptersOpen, setChaptersOpen] = React.useState(false);
  const [chapterSel, setChapterSel] = React.useState(() => new Set());
  const videoChapters = (info && !info.is_playlist && info.chapters) || [];
  const chosenChapters = videoChapters.filter(c => chapterSel.has(c.index));
  const [mode, setMode] = useSessionState('feed_mode', 'video');
  const [quality, setQuality] = useSessionState('feed_quality', '1080p');
  const [container, setContainer] = useSessionState('feed_container', 'mp4');
  const [audioFmt, setAudioFmt] = useSessionState('feed_audioFmt', 'mp3');
  const [audioQuality, setAudioQuality] = useSessionState('feed_audioQuality', 'best');
  // The on/off options (FORMAT_TOGGLES) as one {key: bool}
  const [toggles, setToggles] = useSessionState('feed_toggles', defaultToggles());
  const setToggle = (key, value) => setToggles(t => ({ ...t, [key]: value }));
  const [startTime, setStartTime] = useSessionState('feed_startTime', '');
  const [endTime, setEndTime] = useSessionState('feed_endTime', '');
  const [customFmt, setCustomFmt] = useSessionState('feed_customFmt', '');
  const [downloadPath, setDownloadPath] = useSessionState('feed_downloadPath', '');
  // FILE NAME: this video's own file name (null = the one Config's template gives),
  // kept with the video it was typed for: another analysis starts from its own
  const [fileNameFor, setFileNameFor] = useSessionState('feed_fileName', { url: '', name: null });
  const fileName = info && fileNameFor.url === info.webpage_url ? fileNameFor.name : null;
  const setFileName = name => setFileNameFor({ url: info && info.webpage_url, name });
  // Sent only when it differs from the default (empty = the default)
  const customFileName = info && !info.is_playlist && fileName && fileName.trim() !== (info.file_name || '')
    ? fileName.trim() : '';
  const fileExt = mode === 'audio' ? (audioFmt === 'aac' ? 'm4a' : audioFmt) : container;

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
  // A list (playlist, picked results, imported links) was queued: the unticked
  // items leave the pending list, and ✕ skips in that job from now on
  const onListQueued = React.useCallback((d) => {
    setPlaylistItems && setPlaylistItems(prev => prev && prev.filter(i => i.selected !== false));
    if (d.job_id && setPlaylistJobId) setPlaylistJobId(d.job_id);
  }, [setPlaylistItems, setPlaylistJobId]);

  const onQueued = React.useCallback((d) => {
    if (d.status === 'scheduled') {
      setSubmitting(false);
      setScheduleLater(false);
      showNotif('Scheduled', 'Starts at ' + scheduleStart + ' — see the Queue page to start it sooner', 'success');
    }
    if (d.disk_warning) showNotif('Low Disk Space', d.disk_warning, 'warn');
    if (d.recent_output_dirs) setConfig(c => ({ ...c, recent_output_dirs: d.recent_output_dirs }));
  }, [scheduleStart, showNotif, setConfig]);
  React.useEffect(() => { setSubmitting(false); }, [dlState]);

  // explicitUrl lets callers analyze a URL the `url` state hasn't caught up
  // to yet (clipboard suggestion); plain onClick passes an event — ignored.
  // A video opened from a playlist or Mix is analyzed alone, with a link to
  // the whole list (wholePlaylist: true analyzes the link as it is).
  const handleAnalyze = React.useCallback((explicitUrl, wholePlaylist = false) => {
    let target = (typeof explicitUrl === 'string' ? explicitUrl : url).trim();
    if (!target) return;
    if (!isLinkLike(target)) {
      setAnalyzing(true);
      setInfo(null);
      setPlaylistItems && setPlaylistItems(null);
      API.post('/api/search', { query: target })
        .then(d => {
          setSearchResults({ query: d.query, items: d.items || [] });
          if (!(d.items || []).length) showNotif('No Results', 'Nothing found for "' + d.query + '"', 'warn');
        })
        .catch(e => {
          const d = e.data || {};
          showNotif(d.title || 'Search Failed', d.hint || e.message, 'error', errorActions && errorActions(d.action));
        })
        .finally(() => setAnalyzing(false));
      return;
    }
    const inList = !wholePlaylist && videoInPlaylist(target);
    if (inList) {
      target = inList.video;
      setUrl(target);   // what DOWNLOAD sends
    }
    setAnalyzing(true);
    setInfo(null);
    setPlaylistItems && setPlaylistItems(null);
    setPlaylistJobId && setPlaylistJobId(null);   // a new list: nothing of it is queued yet
    API.post('/api/info', { url: target })
      .then(data => {
        setInfo(inList && !data.is_playlist ? { ...data, from_list: { url: inList.playlist, mix: inList.mix } } : data);
        if (data.is_playlist && data.items && setPlaylistItems) {
          setPlaylistItems(data.items.map(item => ({ ...item, selected: true })));
        } else if (data.is_playlist) {
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
        showNotif(d.title || 'Error', d.hint || e.message, 'error', errorActions && errorActions(d.action));
      })
      .finally(() => setAnalyzing(false));
  }, [url, showNotif, setPlaylistItems, errorActions]);

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
    mode: hasSession('feed_mode'), quality: hasSession('feed_quality'),
    container: hasSession('feed_container'), audioFmt: hasSession('feed_audioFmt'),
    audioQuality: hasSession('feed_audioQuality'),
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
    mode, quality, container, audio_format: audioFmt, audio_quality: audioQuality, ...toggles,
  });

  const applyPreset = (p) => {
    const o = p.opts || {};
    if (o.mode) setMode(o.mode);
    if (o.quality) setQuality(o.quality);
    if (o.container) setContainer(o.container);
    if (o.audio_format) setAudioFmt(o.audio_format);
    if (o.audio_quality) setAudioQuality(o.audio_quality);
    setToggles(togglesFrom(o));
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
              setPlaylistJobId && setPlaylistJobId(null);
              setInfo({ is_playlist: true, is_imported: true, title: fname, playlist_count: urls.length });
              showNotif('Imported', urls.length + ' URLs from ' + fname + (isArchive ? ' (archive format)' : ''), 'success');
            }
          })
          .catch(e => showNotif('Error', e.message, 'error'));
      })
      .catch(() => {});
  }, [showNotif, setPlaylistItems]);

  // Several search results ticked: they become a list like imported links
  // (DOWNLOAD takes the ticked ones with the options below)
  const pickMany = React.useCallback((items) => {
    const query = (searchResults && searchResults.query) || '';
    setImportedUrls(items.map(i => i.url));
    setImportedFileName('"' + query + '"');
    setPlaylistItems && setPlaylistItems(items.map((it, n) => ({ ...it, idx: n + 1, selected: true })));
    setPlaylistJobId && setPlaylistJobId(null);
    setInfo({ is_playlist: true, is_imported: true, title: items.length + ' picked from "' + query + '"',
      playlist_count: items.length, thumbnail: items[0] && items[0].thumbnail });
  }, [searchResults, setPlaylistItems, setPlaylistJobId]);

  const startImportDownload = React.useCallback(() => {
    if (!importedUrls || !importedUrls.length) return;
    // Links removed from the pending list with ✕ stay out
    const urls = playlistItems
      ? importedUrls.filter(u => playlistItems.some(i => i.url === u && i.selected !== false))
      : importedUrls;
    if (!urls.length) {
      showNotif('Nothing To Download', 'Every imported link was removed', 'warn');
      return;
    }
    if (onPlaylistDownload) onPlaylistDownload(urls.length, importedFileName || 'Imported URLs');
    setSubmitting(true);
    API.post('/api/download', {
      url: urls[0],
      multi_urls: urls,
      mode,
      quality,
      container,
      audio_format: audioFmt,
      audio_quality: audioQuality,
      ...toggles,
      scheduled: scheduleLater,
      ...(downloadPath ? { output_dir: downloadPath } : {}),
    }).then(d => { onQueued(d); onListQueued(d); })
      .catch(e => { showNotif('Error', e.message, 'error'); setSubmitting(false); });
  }, [importedUrls, playlistItems, importedFileName, mode, quality, container, audioFmt, audioQuality, toggles, downloadPath, onPlaylistDownload, showNotif, scheduleLater, onQueued, onListQueued]);

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
      // Items removed with ✕ are gone from the list: compare with the whole playlist
      const selected = playlistItems.filter(i => i.selected !== false);
      const whole = Math.max(info.playlist_count || 0, ...playlistItems.map(i => i.idx));
      if (selected.length === 0) {
        showNotif('Nothing To Download', 'Every item of the playlist was removed', 'warn');
        setSubmitting(false);
        return;
      }
      if (selected.length < whole) playlistItemsParam = idxRanges(selected.map(i => i.idx));
    }
    API.post('/api/download', {
      url: url.trim(),
      mode,
      quality,
      container,
      audio_format: audioFmt,
      audio_quality: audioQuality,
      ...toggles,
      start_time: startTime,
      end_time: endTime,
      custom_format: customFmt,
      ...(downloadPath ? { output_dir: downloadPath } : {}),
      ...(playlistItemsParam ? { playlist_items: playlistItemsParam } : {}),
      ...(chosenChapters.length ? { chapters: chosenChapters } : {}),
      ...(customFileName ? { file_name: customFileName } : {}),
      scheduled: scheduleLater,
      ...extra,
    }).then(d => { onQueued(d); if (info && info.is_playlist) onListQueued(d); })
      .catch(e => { showNotif('Error', e.message, 'error'); setSubmitting(false); });
  }, [url, mode, quality, container, audioFmt, audioQuality, toggles, startTime, endTime, customFmt, downloadPath, playlistItems, info, showNotif, scheduleLater, onQueued, onListQueued, chosenChapters, customFileName]);

  // Keep ref in sync with latest startDownload (assigned during render, safe to read in callbacks)
  startDownloadRef.current = startDownload;

  const handleCancel = React.useCallback(() => {
    cancelShownDownload(dlState).catch(e => showNotif('Error', e.message, 'error'));
  }, [dlState, showNotif]);

  const estimatedBytes = info && !info.is_playlist
    ? estimateDownloadBytes(info, { mode, quality, audioFmt, audioQuality, startTime, endTime, chapters: chosenChapters })
    : null;
  const playlistTotalSecs = info && info.is_playlist && playlistItems
    ? playlistItems.reduce((s, i) => s + (i.duration || 0), 0) : 0;
  const diskFree = sysInfo && sysInfo.disk_free_bytes;
  const wontFit = !!(estimatedBytes && diskFree && estimatedBytes > diskFree);

  // A new analysis starts with no chapters chosen
  React.useEffect(() => { setChapterSel(new Set()); }, [info && info.webpage_url]);

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
  // What the view's own links and buttons do (Classic had these inline)
  const toggleChapter = React.useCallback((index) => setChapterSel(prev => {
    const next = new Set(prev);
    if (next.has(index)) next.delete(index); else next.add(index);
    return next;
  }), []);
  const chooseAllChapters = React.useCallback(() => setChapterSel(new Set(videoChapters.map(c => c.index))), [videoChapters]);
  const chooseNoChapters = React.useCallback(() => setChapterSel(new Set()), []);
  const cancelPreset = React.useCallback(() => { setSavingPreset(false); setPresetName(''); }, []);
  const openPreviousDownload = React.useCallback(() => {
    API.post('/api/vault/open-file', { path: info.previous_download.file_path }).catch(() => {});
  }, [info]);
  const showPreviousDownload = React.useCallback(() => {
    API.post('/api/open-folder', { path: info.previous_download.file_path }).catch(() => {});
  }, [info]);
  // A video opened from a playlist or Mix: analyze the whole list instead
  const analyzeWholeList = React.useCallback(() => {
    setUrl(info.from_list.url);
    handleAnalyze(info.from_list.url, true);
  }, [info, handleAnalyze]);
  const pickSearchResult = React.useCallback((item) => {
    setUrl(item.url);
    handleAnalyze(item.url);
  }, [handleAnalyze]);
  const clearSearch = React.useCallback(() => setSearchResults(null), []);
  // ↻ next to the queue: read the playlist's items again
  const refreshPlaylistItems = React.useCallback(() => {
    if (!url.trim()) return;
    API.post('/api/playlist-items', { url: url.trim() })
      .then(r => {
        if (r.items && setPlaylistItems) {
          setPlaylistItems(r.items.map(i => ({ ...i, selected: true })));
          setPlaylistJobId && setPlaylistJobId(null);
        }
      })
      .catch(() => {});
  }, [url, setPlaylistItems, setPlaylistJobId]);
  // The vault-link prompt shown for a playlist's DOWNLOAD
  const closeVaultLinkPrompt = React.useCallback(() => setVaultLinkPrompt(false), []);
  const promptJustDownload = React.useCallback(() => {
    setVaultLinkPrompt(false);
    if (startDownloadRef.current) startDownloadRef.current();
  }, []);
  const promptLinkAndDownload = React.useCallback((extra) => {
    setVaultLinkPrompt(false);
    if (startDownloadRef.current) startDownloadRef.current(extra);
  }, []);

  return {
    ...props,
    // the link box
    url, setUrl, handleUrlKeyDown, handleAnalyze, analyzing, analyzeSlow, handlePaste, handleImportFile,
    importedUrls, importedFileName,
    // SAVE TO
    downloadPath, setDownloadPath, browseDownloadPath,
    // OPTIONS
    optsOpen, setOptsOpen, advOpen, setAdvOpen,
    mode, setMode, quality, setQuality, container, setContainer, audioFmt, setAudioFmt, audioQuality, setAudioQuality,
    toggles, setToggle, startTime, setStartTime, endTime, setEndTime, customFmt, setCustomFmt,
    savingPreset, setSavingPreset, presetName, setPresetName, savePreset, cancelPreset, applyPreset, deletePreset,
    currentOpts,
    videoChapters, chaptersOpen, setChaptersOpen, chapterSel, chosenChapters, toggleChapter, chooseAllChapters,
    chooseNoChapters,
    // the analyzed link
    info, fetchingItems, fileName, setFileName, fileExt, estimatedBytes, wontFit, diskFree, playlistTotalSecs,
    openPreviousDownload, showPreviousDownload, analyzeWholeList, refreshPlaylistItems,
    // DOWNLOAD / ⏾ LATER / progress
    handleDownload, submitting, isDownloading, scheduleLater, setScheduleLater, scheduleStart, handleCancel,
    pipelineStage,
    // search results
    searchResults, pickSearchResult, pickMany, clearSearch,
    // the queue preview
    feedQTab, setFeedQTab,
    // the vault-link prompt (playlists)
    vaultLinkPrompt, closeVaultLinkPrompt, promptJustDownload, promptLinkAndDownload,
  };
}
