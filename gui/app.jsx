/* @jsxRuntime classic */
/* @jsx React.createElement */
/* @jsxFrag React.Fragment */
/* global React, ReactDOM */
// App root — page routing, SSE event hub, global state, cross-cutting UX
// (clipboard watcher, keyboard shortcuts, title progress, completion chime).
'use strict';

import { API } from './lib/api.js';
import {
  BREAKAGE_RE,
  CLIPBOARD_URL_RE,
  COMPLETED_ITEMS_KEEP,
  FAILED_ITEMS_KEEP,
  NOTIF_ACTION_TIMEOUT_MS,
  NOTIF_TIMEOUT_MS,
  PAGE_ORDER,
  SPEED_HISTORY_LEN,
  STATS_POLL_ACTIVE_MS,
  STATS_POLL_IDLE_MS,
  UPDATE_CHECK_EVERY_MS,
  UPDATE_CHECK_STORAGE_KEY,
  VICTORY_AUTO_DISMISS_MS,
  VICTORY_FADE_MS,
} from './lib/constants.js';
import { playCompletionChime } from './lib/sound.js';
import { MASCOT_VICTORY_SAFE } from './lib/mascots.js';
import { Modal, Notif, Mascot } from './components/common.jsx';
import { LoadingScreen } from './components/loading.jsx';
import { Sidebar, TopBar, StatusBar } from './components/chrome.jsx';
import { FeedPage } from './pages/feed.jsx';
import { QueuePage } from './pages/queue.jsx';
import { VaultPage } from './pages/vault.jsx';
import { AnalyticsPage } from './pages/analytics.jsx';
import { SignalApiPage } from './pages/signal.jsx';
import { ConfigPage } from './pages/config.jsx';
import { AddVaultModal } from './components/vault-modals.jsx';

const KEYBOARD_SHORTCUTS = [
  ['1 – 6', 'Jump to Feed / Queue / Vault / Analytics / Signal / Config'],
  ['?', 'Toggle this help'],
  ['Esc', 'Close dialogs'],
  ['Enter (Feed)', 'Paste → Analyze → Download'],
];

function ShortcutHelpOverlay({ onClose }) {
  return (
    <Modal title="KEYBOARD SHORTCUTS" onClose={onClose} footer={
      <button className="btn btn-secondary btn-sm" onClick={onClose}>CLOSE</button>
    }>
      <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 11 }}>
        {KEYBOARD_SHORTCUTS.map(([key, desc]) => (
          <div key={key} style={{ display: 'flex', gap: 14, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
            <span style={{ color: 'var(--cyan)', minWidth: 90 }}>{key}</span>
            <span style={{ color: 'var(--t2)' }}>{desc}</span>
          </div>
        ))}
      </div>
    </Modal>
  );
}

function App() {
  const [loading, setLoading] = React.useState(true);
  const [page, setPage] = React.useState('feed');
  const [appState, setAppState] = React.useState('idle');
  const [dlState, setDlState] = React.useState(null);
  const [activeJobs, setActiveJobs] = React.useState({});
  const [stats, setStats] = React.useState({});
  const [sysInfo, setSysInfo] = React.useState({});
  const [config, setConfig] = React.useState({});
  const [notif, setNotif] = React.useState(null);
  const [speedHistory, setSpeedHistory] = React.useState(Array(SPEED_HISTORY_LEN).fill(0));
  const [vaultFolders, setVaultFolders] = React.useState([]);
  const [selectedVaultFolder, setSelectedVaultFolder] = React.useState(null);
  const [addVaultModal, setAddVaultModal] = React.useState(false);
  const [showVictory, setShowVictory] = React.useState(false);
  const [victoryDismissing, setVictoryDismissing] = React.useState(false);
  const [victoryData, setVictoryData] = React.useState(null);
  const [playlistItems, setPlaylistItems] = React.useState(null);
  const [completedItems, setCompletedItems] = React.useState([]);
  const [failedItems, setFailedItems] = React.useState([]);
  const [playlistTotalCount, setPlaylistTotalCount] = React.useState(0);
  const [playlistCompletedCount, setPlaylistCompletedCount] = React.useState(0);
  const [failedCount, setFailedCount] = React.useState(0);
  const [isPaused, setIsPaused] = React.useState(false);
  const [pausedCount, setPausedCount] = React.useState(0);
  const [syncJobLabel, setSyncJobLabel] = React.useState(null);
  const [fetchingPlaylistItems, setFetchingPlaylistItems] = React.useState(false);
  const [restorableJobs, setRestorableJobs] = React.useState(null);
  const [clipboardSuggestion, setClipboardSuggestion] = React.useState(null);
  const [shortcutHelp, setShortcutHelp] = React.useState(false);
  const playlistActiveRef = React.useRef(false);
  const currentPlaylistRef = React.useRef({ name: '', count: 0 });
  const configRef = React.useRef(config);
  const notifTimer = React.useRef(null);
  const victoryTimer = React.useRef(null);
  const processedCompletions = React.useRef(new Set());
  // Job whose events drive the main progress panel (others run in background
  // when download_workers > 1 and are tracked in activeJobs)
  const primaryJobRef = React.useRef(null);
  const lastClipboardRef = React.useRef('');

  React.useEffect(() => { configRef.current = config; }, [config]);

  const showNotif = React.useCallback((title, body, type = 'info', actions = null) => {
    setNotif({ title, body, type, actions });
    if (notifTimer.current) clearTimeout(notifTimer.current);
    notifTimer.current = setTimeout(
      () => setNotif(null),
      actions ? NOTIF_ACTION_TIMEOUT_MS : NOTIF_TIMEOUT_MS
    );
  }, []);

  const refreshStats = React.useCallback(() => {
    API.get('/api/stats').then(setStats).catch(() => {});
    API.get('/api/system').then(setSysInfo).catch(() => {});
  }, []);

  const refreshVault = React.useCallback((basePath) => {
    const path = basePath || config.output_dir;
    const url = path ? '/api/vault?path=' + encodeURIComponent(path) : '/api/vault';
    API.get(url)
      .then(d => setVaultFolders(d.folders || []))
      .catch(() => {});
  }, [config.output_dir]);

  // Jobs that were still queued when the app last exited
  React.useEffect(() => {
    API.get('/api/queue/restorable')
      .then(d => { if (d.jobs && d.jobs.length) setRestorableJobs(d.jobs); })
      .catch(() => {});
  }, []);

  // Initial load: stats, config, vault — then the once-a-day yt-dlp check
  React.useEffect(() => {
    refreshStats();
    API.get('/api/config').then(c => {
      setConfig(c);
      if (c.output_dir) {
        API.get('/api/vault?path=' + encodeURIComponent(c.output_dir))
          .then(d => setVaultFolders(d.folders || []))
          .catch(() => {});
      }
      if (c.update_check_on_launch !== false) {
        let last = 0;
        try { last = parseInt(localStorage.getItem(UPDATE_CHECK_STORAGE_KEY) || '0', 10) || 0; } catch {}
        if (Date.now() - last > UPDATE_CHECK_EVERY_MS) {
          try { localStorage.setItem(UPDATE_CHECK_STORAGE_KEY, String(Date.now())); } catch {}
          API.get('/api/check-ytdlp-update').then(u => {
            if (u && u.update_available) {
              showNotif('yt-dlp Update Available', `${u.installed} → ${u.latest}`, 'info', [{
                label: 'UPDATE NOW', primary: true,
                onClick: () => API.post('/api/update-ytdlp', {}).catch(() => {}),
              }]);
            }
          }).catch(() => {});
        }
      }
    }).catch(() => {});
  }, [refreshStats, showNotif]);

  React.useEffect(() => {
    const iv = setInterval(
      refreshStats,
      (appState === 'downloading' || appState === 'processing') ? STATS_POLL_ACTIVE_MS : STATS_POLL_IDLE_MS
    );
    return () => clearInterval(iv);
  }, [appState, refreshStats]);

  // Clipboard watcher: on window focus, suggest analyzing a copied media URL
  React.useEffect(() => {
    const check = () => {
      if (configRef.current.clipboard_watch === false) return;
      API.get('/api/clipboard').then(d => {
        const text = (d.text || '').trim();
        if (!text || text === lastClipboardRef.current) return;
        lastClipboardRef.current = text;
        if (!CLIPBOARD_URL_RE.test(text)) return;
        try { if (sessionStorage.getItem('feed_url') === text) return; } catch {}
        showNotif('URL Detected in Clipboard', text, 'info', [{
          label: 'ANALYZE', primary: true,
          onClick: () => {
            setClipboardSuggestion({ url: text, ts: Date.now() });
            setPage('feed');
          },
        }]);
      }).catch(() => {});
    };
    window.addEventListener('focus', check);
    return () => window.removeEventListener('focus', check);
  }, [showNotif]);

  // Keyboard shortcuts (ignored while typing in a field)
  React.useEffect(() => {
    const handler = (e) => {
      const tag = ((e.target && e.target.tagName) || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || (e.target && e.target.isContentEditable)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= PAGE_ORDER.length) {
        setPage(PAGE_ORDER[num - 1]);
      } else if (e.key === '?') {
        setShortcutHelp(s => !s);
      } else if (e.key === 'Escape') {
        setShortcutHelp(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Live progress in the window title
  React.useEffect(() => {
    if (appState === 'downloading' && dlState && dlState.pct !== undefined) {
      document.title = `▼ ${(dlState.pct || 0).toFixed(0)}% — MellowDLP`;
    } else if (appState === 'processing') {
      document.title = '⚙ processing — MellowDLP';
    } else {
      document.title = 'MellowDLP';
    }
  }, [appState, dlState]);

  // ── SSE event hub ────────────────────────────────────────────────────────────
  React.useEffect(() => {
    const es = new EventSource('/api/progress');
    es.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }
      if (data.status === 'ping') return;
      const jobId = data.job_id || null;
      const isPrimary = primaryJobRef.current === null || jobId === null || jobId === primaryJobRef.current;

      if (data.status === 'starting') {
        if (primaryJobRef.current === null) {
          primaryJobRef.current = jobId || '_single';
          processedCompletions.current.clear();
          setDlState({ status: 'starting', pct: 0 });
        }
        setAppState('downloading');
      } else if (data.status === 'downloading') {
        setAppState('downloading');
        if (jobId) {
          setActiveJobs(prev => ({ ...prev, [jobId]: {
            pct: data.pct, speed: data.speed, eta: data.eta,
            title: data.current_item_title || data.filename,
            thumb: data.current_item_thumb,
            label: data.job_label, type: data.job_type,
          } }));
        }
        if (primaryJobRef.current === null && jobId) primaryJobRef.current = jobId;
        if (isPrimary) setDlState(data);
        setSpeedHistory(h => [...h.slice(1), data.speed || 0]);
        if (data.current_item_title) {
          setPlaylistItems(prev => {
            if (!prev || !prev.length) return prev;
            const first = prev[0];
            if (first.url && first.title === first.url) {
              return [{ ...first, title: data.current_item_title, thumbnail: data.current_item_thumb || first.thumbnail }, ...prev.slice(1)];
            }
            return prev;
          });
        }
      } else if (data.status === 'processing') {
        if (isPrimary) {
          setAppState('processing');
          setDlState(prev => prev ? { ...prev, status: 'processing' } : { status: 'processing', pct: 100 });
        }
      } else if (data.status === 'item_done') {
        if (data.video_id && processedCompletions.current.has(data.video_id)) return;
        if (data.video_id) processedCompletions.current.add(data.video_id);
        const idx = data.playlist_index;
        const vid = data.video_id;
        const title = data.title;
        setPlaylistItems(prev => {
          if (!prev) return prev;
          // Try most specific match first, then fall back
          if (vid) {
            const byId = prev.filter(x => x.video_id !== vid);
            if (byId.length < prev.length) return byId;
          }
          if (idx !== undefined && idx !== null) {
            const byIdx = prev.filter(x => x.idx !== idx);
            if (byIdx.length < prev.length) return byIdx;
          }
          if (title) {
            const byTitle = prev.filter(x => x.title !== title);
            if (byTitle.length < prev.length) return byTitle;
          }
          // No match: leave the list alone — blindly dropping the head
          // removed the wrong pending item
          return prev;
        });
        setCompletedItems(prev => {
          if (data.video_id && prev.some(x => x.video_id === data.video_id)) return prev;
          return [{
            video_id: data.video_id,
            title: data.title,
            thumbnail: data.thumbnail,
            completedAt: Date.now(),
          }, ...prev].slice(0, COMPLETED_ITEMS_KEEP);
        });
        setPlaylistCompletedCount(c => c + 1);
      } else if (data.status === 'paused') {
        setIsPaused(true);
        setPausedCount(1);
        setDlState(prev => prev ? { ...prev, paused: true } : prev);
      } else if (data.status === 'resumed') {
        setIsPaused(false);
        setPausedCount(0);
        setDlState(prev => prev ? { ...prev, paused: false } : prev);
      } else if (data.status === 'item_failed') {
        setFailedCount(c => c + 1);
        setFailedItems(prev => [{
          title: data.message || 'Unknown item',
          reason: data.reason || 'error',
          url: data.url || null,
          failedAt: Date.now(),
        }, ...prev].slice(0, FAILED_ITEMS_KEEP));
      } else if (data.status === 'complete') {
        if (jobId) setActiveJobs(prev => { const next = { ...prev }; delete next[jobId]; return next; });
        if (configRef.current.completion_sound) playCompletionChime();
        const fileActions = data.file_path ? [
          { label: 'OPEN FILE', primary: true, onClick: () => API.post('/api/vault/open-file', { path: data.file_path }).catch(() => {}) },
          { label: 'FOLDER', onClick: () => API.post('/api/open-folder', { path: data.file_path }).catch(() => {}) },
        ] : null;
        showNotif('Download Complete', data.title || 'File saved successfully', 'success', fileActions);
        refreshStats();
        refreshVault();
        if (!isPrimary) return;  // a background job finished; main panel stays
        primaryJobRef.current = null;
        setDlState(null);
        setAppState('idle');
        setIsPaused(false);
        setPausedCount(0);
        setSyncJobLabel(null);
        setSpeedHistory(h => [...h.slice(1), 0]);
        setPlaylistItems(null);
        setFetchingPlaylistItems(false);
        if (playlistActiveRef.current) {
          playlistActiveRef.current = false;
          const isSyncCompletion = !!data.library_id;
          const victoryEnabled = isSyncCompletion
            ? configRef.current.ui_victory_sync !== false
            : configRef.current.ui_victory_animation !== false;
          if (victoryEnabled && MASCOT_VICTORY_SAFE) {
            setVictoryData({
              playlistName: currentPlaylistRef.current.name,
              itemCount: currentPlaylistRef.current.count,
            });
            setVictoryDismissing(false);
            setShowVictory(true);
            if (victoryTimer.current) clearTimeout(victoryTimer.current);
            victoryTimer.current = setTimeout(() => {
              setVictoryDismissing(true);
              setTimeout(() => { setShowVictory(false); setVictoryDismissing(false); }, VICTORY_FADE_MS);
            }, VICTORY_AUTO_DISMISS_MS);
          }
        }
      } else if (data.status === 'error') {
        if (jobId) setActiveJobs(prev => { const next = { ...prev }; delete next[jobId]; return next; });
        const msg = data.message || 'Download failed';
        setFailedItems(prev => [{
          title: msg, reason: 'error', url: data.url || null, failedAt: Date.now(),
        }, ...prev].slice(0, FAILED_ITEMS_KEEP));
        setFailedCount(c => c + 1);
        // Extraction failures usually mean yt-dlp is outdated — offer the fix
        const looksLikeBreakage = BREAKAGE_RE.test(msg);
        const errActions = looksLikeBreakage ? [{
          label: 'UPDATE YT-DLP', primary: true,
          onClick: () => API.post('/api/update-ytdlp', {}).catch(() => {}),
        }] : null;
        showNotif('Error', looksLikeBreakage ? msg + ' — this often means yt-dlp is outdated.' : msg, 'error', errActions);
        refreshStats();
        if (!isPrimary) return;
        primaryJobRef.current = null;
        setDlState(null);
        setAppState('error');
        setIsPaused(false);
      } else if (data.status === 'cancelled') {
        if (jobId) setActiveJobs(prev => { const next = { ...prev }; delete next[jobId]; return next; });
        showNotif('Cancelled', 'Download stopped');
        if (!isPrimary) return;
        primaryJobRef.current = null;
        setDlState(null);
        setAppState('idle');
        setIsPaused(false);
        setPausedCount(0);
      } else if (data.status === 'ytdlp_updated') {
        if (data.ok) showNotif('Updated', 'yt-dlp updated successfully', 'success');
        else showNotif('Update failed', data.error || '', 'error');
        refreshStats();
      }
    };
    es.onerror = () => {};
    return () => es.close();
  }, [showNotif, refreshStats, refreshVault]);

  const switchPage = React.useCallback((p) => setPage(p), []);

  if (loading) {
    return <LoadingScreen onReady={() => setLoading(false)} />;
  }

  return (
    <div className="app">
      <Sidebar
        page={page}
        setPage={setPage}
        appState={appState}
        stats={stats}
        speedHistory={speedHistory}
        sysInfo={sysInfo}
      />

      <div className="main">
        <TopBar page={page} />

        {page === 'feed' && (
          <FeedPage
            dlState={dlState}
            setDlState={setDlState}
            setAppState={setAppState}
            stats={stats}
            refreshStats={refreshStats}
            showNotif={showNotif}
            switchPage={switchPage}
            config={config}
            setConfig={setConfig}
            suggestedUrl={clipboardSuggestion}
            onSuggestedConsumed={() => setClipboardSuggestion(null)}
            onPlaylistDownload={(count, name) => {
              playlistActiveRef.current = true;
              currentPlaylistRef.current = { name: name || '', count: count || 0 };
              setPlaylistTotalCount(count || 0);
              setPlaylistCompletedCount(0);
              setFailedCount(0);
              setFailedItems([]);
            }}
            playlistItems={playlistItems}
            setPlaylistItems={setPlaylistItems}
            completedItems={completedItems}
            failedItems={failedItems}
            playlistTotalCount={playlistTotalCount}
            playlistCompletedCount={playlistCompletedCount}
            isPaused={isPaused}
            syncJobLabel={syncJobLabel}
            fetchingPlaylistItems={fetchingPlaylistItems}
            onPause={() => API.post('/api/download/pause', {}).catch(() => {})}
            onResume={() => API.post('/api/download/resume', {}).catch(() => {})}
            onClearCompleted={() => setCompletedItems([])}
          />
        )}
        {page === 'queue' && (
          <QueuePage
            dlState={dlState}
            showNotif={showNotif}
            activeJobs={activeJobs}
            playlistItems={playlistItems}
            setPlaylistItems={setPlaylistItems}
            completedItems={completedItems}
            failedItems={failedItems}
            playlistTotalCount={playlistTotalCount}
            playlistCompletedCount={playlistCompletedCount}
            isPaused={isPaused}
            pausedCount={pausedCount}
            failedCount={failedCount}
            syncJobLabel={syncJobLabel}
            fetchingPlaylistItems={fetchingPlaylistItems}
            onPause={() => API.post('/api/download/pause', {}).catch(() => {})}
            onResume={() => API.post('/api/download/resume', {}).catch(() => {})}
            onClearCompleted={() => setCompletedItems([])}
            onClearFailed={() => { setFailedItems([]); setFailedCount(0); }}
          />
        )}
        {page === 'vault' && (
          <VaultPage
            vaultFolders={vaultFolders}
            selectedFolder={selectedVaultFolder}
            setSelectedFolder={setSelectedVaultFolder}
            config={config}
            setConfig={setConfig}
            showNotif={showNotif}
            onAddVault={() => setAddVaultModal(true)}
            onRefreshVault={refreshVault}
            isDownloading={!!(dlState && dlState.status !== 'complete' && dlState.status !== 'error')}
            onSyncStart={setSyncJobLabel}
            onSyncItems={(items, count, name) => {
              if (items === null) {
                setFetchingPlaylistItems(true);
                playlistActiveRef.current = true;
                currentPlaylistRef.current = { name: name || '', count: 0 };
                setPlaylistTotalCount(0);
                setPlaylistCompletedCount(0);
                setFailedCount(0);
                setFailedItems([]);
              } else {
                setPlaylistItems(items.map(i => ({ ...i, selected: true })));
                setFetchingPlaylistItems(false);
                setPlaylistTotalCount(count);
                currentPlaylistRef.current = { name: name || '', count };
              }
            }}
          />
        )}
        {page === 'analytics' && (
          <AnalyticsPage stats={stats} refreshStats={refreshStats} showNotif={showNotif} />
        )}
        {page === 'signal' && <SignalApiPage />}
        {page === 'config' && (
          <ConfigPage
            config={config}
            setConfig={setConfig}
            showNotif={showNotif}
            sysInfo={sysInfo}
            refreshStats={refreshStats}
          />
        )}

        <StatusBar sysInfo={sysInfo} speedHistory={speedHistory} config={config} />
      </div>

      <Notif notif={notif} dismiss={() => setNotif(null)} />

      {showVictory && MASCOT_VICTORY_SAFE && (
        <div className={'victory-overlay' + (victoryDismissing ? ' dismissing' : '')} onClick={() => {
          if (victoryTimer.current) clearTimeout(victoryTimer.current);
          setVictoryDismissing(true);
          setTimeout(() => { setShowVictory(false); setVictoryDismissing(false); }, VICTORY_FADE_MS);
        }}>
          {[
            { delay: '0s',    tx: '80px',   ty: '-60px'  },
            { delay: '0.1s',  tx: '-70px',  ty: '-80px'  },
            { delay: '0.15s', tx: '100px',  ty: '20px'   },
            { delay: '0.2s',  tx: '-90px',  ty: '30px'   },
            { delay: '0.05s', tx: '40px',   ty: '100px'  },
            { delay: '0.25s', tx: '-40px',  ty: '90px'   },
            { delay: '0.3s',  tx: '120px',  ty: '-30px'  },
            { delay: '0.12s', tx: '-110px', ty: '-20px'  },
            { delay: '0.18s', tx: '60px',   ty: '-110px' },
            { delay: '0.22s', tx: '-60px',  ty: '-100px' },
            { delay: '0.08s', tx: '90px',   ty: '80px'   },
            { delay: '0.35s', tx: '-80px',  ty: '70px'   },
          ].map((s, i) => (
            <div key={i} className="victory-sparkle" style={{ '--delay': s.delay, '--tx': s.tx, '--ty': s.ty, top: '50%', left: '50%' }} />
          ))}
          <Mascot src={MASCOT_VICTORY_SAFE} className="victory-mascot" wrapClass="victory-mascot" />
          <div className="victory-text">✦ PLAYLIST COMPLETE ✦</div>
          {victoryData && victoryData.playlistName && (
            <div style={{ fontFamily: "'Exo 2', sans-serif", fontSize: 16, color: '#e0e8f0', fontStyle: 'italic', textAlign: 'center', maxWidth: 400 }}>
              "{victoryData.playlistName}"
            </div>
          )}
          {victoryData && (victoryData.itemCount > 0) && (
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 13, color: '#8899aa', letterSpacing: '0.1em' }}>
              {victoryData.itemCount} ITEMS DOWNLOADED
            </div>
          )}
          <div className="victory-dismiss">click anywhere or wait 5s to dismiss</div>
        </div>
      )}

      {addVaultModal && (
        <AddVaultModal
          onClose={() => setAddVaultModal(false)}
          onSaved={() => { setAddVaultModal(false); refreshVault(); showNotif('Added to VAULT', 'Playlist saved', 'success'); }}
          showNotif={showNotif}
        />
      )}

      {shortcutHelp && <ShortcutHelpOverlay onClose={() => setShortcutHelp(false)} />}

      {restorableJobs && (
        <Modal
          title="RESUME PENDING DOWNLOADS?"
          onClose={() => setRestorableJobs(null)}
          footer={
            <>
              <button className="btn btn-secondary btn-sm" onClick={() => {
                API.del('/api/queue/restorable').catch(() => {});
                setRestorableJobs(null);
              }}>DISCARD</button>
              <button className="btn btn-primary btn-sm" onClick={() => {
                API.post('/api/queue/restore', {})
                  .then(d => showNotif('Queue Restored', (d.restored || 0) + ' job(s) re-queued', 'success'))
                  .catch(e => showNotif('Error', e.message, 'error'));
                setRestorableJobs(null);
              }}>RESUME ALL</button>
            </>
          }
        >
          <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t2)' }}>
            <div style={{ marginBottom: 8, color: 'var(--t3)' }}>
              {restorableJobs.length} download(s) were still queued when the app last closed:
            </div>
            {restorableJobs.slice(0, 8).map(j => (
              <div key={j.id} style={{ padding: '3px 0', borderBottom: '1px solid var(--border)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                <span style={{ color: 'var(--amber)', marginRight: 8 }}>{(j.type || 'feed').toUpperCase()}</span>
                <span style={{ color: 'var(--cyan)' }}>{j.label || j.url}</span>
              </div>
            ))}
            {restorableJobs.length > 8 && (
              <div style={{ padding: '4px 0', color: 'var(--t4)' }}>+{restorableJobs.length - 8} more</div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── Mount ─────────────────────────────────────────────────────────────────────

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(App));
