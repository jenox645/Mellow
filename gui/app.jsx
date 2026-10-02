/* @jsxRuntime classic */
/* @jsx React.createElement */
/* @jsxFrag React.Fragment */
/* global React, ReactDOM */
// App root — page routing, SSE event hub, global state, cross-cutting UX
// (clipboard watcher, keyboard shortcuts, title progress, completion chime).
'use strict';

import { API } from './lib/api.js';
import {
  CLIPBOARD_URL_RE,
  NOTIF_ACTION_TIMEOUT_MS,
  NOTIF_TIMEOUT_MS,
  PAGE_ORDER,
  STATS_POLL_ACTIVE_MS,
  STATS_POLL_IDLE_MS,
  APP_UPDATE_CHECK_STORAGE_KEY,
  UPDATE_CHECK_EVERY_MS,
  UPDATE_CHECK_STORAGE_KEY,
  VICTORY_AUTO_DISMISS_MS,
  VICTORY_FADE_MS,
} from './lib/constants.js';
import { playCompletionChime } from './lib/sound.js';
import { downloadsReducer, initialDownloads } from './lib/downloads.js';
import { MASCOT_VICTORY_SAFE } from './lib/mascots.js';
import { Modal, Notif, Mascot, AppUpdateOverlay } from './components/common.jsx';
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
  ['Ctrl+V / drop a link', 'Anywhere outside a text field: analyze it on the Feed'],
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

// OPEN FILE / FOLDER buttons for a "Download Complete" toast
function fileActions(path) {
  return [
    { label: 'OPEN FILE', primary: true, onClick: () => API.post('/api/vault/open-file', { path }).catch(() => {}) },
    { label: 'FOLDER', onClick: () => API.post('/api/open-folder', { path }).catch(() => {}) },
  ];
}

function App() {
  const [loading, setLoading] = React.useState(true);
  const [page, setPage] = React.useState('feed');
  // Everything the server's progress events drive (gui/lib/downloads.js)
  const [dl, dispatch] = React.useReducer(downloadsReducer, undefined, initialDownloads);
  const {
    appState, dlState, activeJobs, speedHistory, playlistItems, completedItems, failedItems,
    playlistTotalCount, playlistCompletedCount, failedCount, isPaused, pausedCount, syncJobLabel,
    fetchingPlaylistItems, appUpdate,
  } = dl;
  // setState-style setters for the pages (stable: dispatch never changes)
  const setters = React.useMemo(() => {
    const set = key => value => dispatch({ type: 'set', key, value });
    return {
      setPlaylistItems: set('playlistItems'), setCompletedItems: set('completedItems'),
      setFailedItems: set('failedItems'), setFailedCount: set('failedCount'),
      setSyncJobLabel: set('syncJobLabel'),
    };
  }, []);
  const { setPlaylistItems, setCompletedItems, setFailedItems, setFailedCount, setSyncJobLabel } = setters;
  const [stats, setStats] = React.useState({});
  const [sysInfo, setSysInfo] = React.useState({});
  const [config, setConfig] = React.useState({});
  const [notif, setNotif] = React.useState(null);
  const [vaultFolders, setVaultFolders] = React.useState([]);
  const [selectedVaultFolder, setSelectedVaultFolder] = React.useState(null);
  const [addVaultModal, setAddVaultModal] = React.useState(false);
  const [showVictory, setShowVictory] = React.useState(false);
  const [victoryDismissing, setVictoryDismissing] = React.useState(false);
  const [victoryData, setVictoryData] = React.useState(null);
  const [restorableJobs, setRestorableJobs] = React.useState(null);
  const [clipboardSuggestion, setClipboardSuggestion] = React.useState(null);
  const [shortcutHelp, setShortcutHelp] = React.useState(false);
  const configRef = React.useRef(config);
  const notifTimer = React.useRef(null);
  const victoryTimer = React.useRef(null);
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

  // Buttons for the fixes the backend can name (errors.py actions)
  const errorActions = React.useCallback((action) => {
    if (action === 'update_ytdlp') return [{
      label: 'UPDATE YT-DLP', primary: true,
      onClick: () => API.post('/api/update-ytdlp', {}).catch(() => {}),
    }];
    if (action === 'open_config') return [{ label: 'OPEN CONFIG', primary: true, onClick: () => setPage('config') }];
    if (action === 'open_release') return [{
      label: 'RELEASE PAGE', primary: true,
      onClick: () => API.post('/api/open-release', {}).catch(() => {}),
    }];
    return null;
  }, []);

  // Install the latest MellowDLP and restart (progress: app_update events).
  // Running downloads are saved and offered again, but ask first.
  const installAppUpdate = React.useCallback((force = false) => {
    API.post('/api/app-update/install', { force }).catch(err => {
      if (err.data && err.data.running) {
        showNotif('Downloads Running', err.data.running + ' download(s) will stop for the update and be offered again after the restart.', 'warn', [
          { label: 'UPDATE NOW', primary: true, onClick: () => installAppUpdate(true) },
          { label: 'LATER', onClick: () => {} },
        ]);
      } else {
        showNotif('Update Failed', err.message, 'error');
      }
    });
  }, [showNotif]);

  // System notification when the window is in the background (opt-in in Config)
  const desktopNotify = React.useCallback((title, body) => {
    if (!configRef.current.desktop_notifications) return;
    if (document.hasFocus() || typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    try { new Notification(title, { body: body || '' }); } catch {}
  }, []);

  // Paste or drop a link anywhere: jump to the Feed and analyze it
  React.useEffect(() => {
    const isTyping = (el) => {
      const tag = ((el && el.tagName) || '').toLowerCase();
      return tag === 'input' || tag === 'textarea' || tag === 'select' || (el && el.isContentEditable);
    };
    const offer = (text) => {
      const u = (text || '').trim().split(/\s+/)[0];
      if (!CLIPBOARD_URL_RE.test(u)) return false;
      lastClipboardRef.current = u;
      setClipboardSuggestion({ url: u, ts: Date.now() });
      setPage('feed');
      return true;
    };
    const onPaste = (e) => {
      if (isTyping(e.target)) return;
      if (offer(e.clipboardData && e.clipboardData.getData('text'))) e.preventDefault();
    };
    const hasLink = (e) => {
      const types = Array.from((e.dataTransfer && e.dataTransfer.types) || []);
      return !types.includes('Files') && (types.includes('text/uri-list') || types.includes('text/plain'));
    };
    const onDragOver = (e) => { if (hasLink(e)) e.preventDefault(); };
    const onDrop = (e) => {
      if (!hasLink(e)) return;
      const dt = e.dataTransfer;
      if (offer(dt.getData('text/uri-list') || dt.getData('text/plain'))) e.preventDefault();
    };
    window.addEventListener('paste', onPaste);
    window.addEventListener('dragover', onDragOver);
    window.addEventListener('drop', onDrop);
    return () => {
      window.removeEventListener('paste', onPaste);
      window.removeEventListener('dragover', onDragOver);
      window.removeEventListener('drop', onDrop);
    };
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

  // Jobs that were running or queued when the app last exited
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
        // Once a day: is there a newer MellowDLP?
        let lastApp = 0;
        try { lastApp = parseInt(localStorage.getItem(APP_UPDATE_CHECK_STORAGE_KEY) || '0', 10) || 0; } catch {}
        if (Date.now() - lastApp > UPDATE_CHECK_EVERY_MS) {
          try { localStorage.setItem(APP_UPDATE_CHECK_STORAGE_KEY, String(Date.now())); } catch {}
          API.get('/api/check-app-update').then(u => {
            if (u && u.update_available) {
              showNotif('MellowDLP ' + u.latest + ' Available', 'You have ' + u.current + '.', 'info', [u.can_install
                ? { label: 'UPDATE & RESTART', primary: true, onClick: () => installAppUpdate() }
                : { label: 'GET IT', primary: true, onClick: () => API.post('/api/open-release', {}).catch(() => {}) }]);
            }
          }).catch(() => {});
        }
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
      if (data.status !== 'ping') dispatch({ type: 'event', data, now: Date.now() });
    };
    es.onerror = () => {};
    return () => es.close();
  }, []);

  // Run what the events asked for (toasts, chime, refreshes, celebration)
  const celebrate = React.useCallback((fx) => {
    const enabled = fx.sync ? configRef.current.ui_victory_sync !== false
      : configRef.current.ui_victory_animation !== false;
    if (!enabled || !MASCOT_VICTORY_SAFE) return;
    setVictoryData({ playlistName: fx.name, itemCount: fx.count });
    setVictoryDismissing(false);
    setShowVictory(true);
    if (victoryTimer.current) clearTimeout(victoryTimer.current);
    victoryTimer.current = setTimeout(() => {
      setVictoryDismissing(true);
      setTimeout(() => { setShowVictory(false); setVictoryDismissing(false); }, VICTORY_FADE_MS);
    }, VICTORY_AUTO_DISMISS_MS);
  }, []);

  React.useEffect(() => {
    const effects = dl.effects;
    if (!effects.length) return;
    for (const fx of effects) {
      if (fx.type === 'notify') {
        showNotif(fx.title, fx.body, fx.kind, fx.file ? fileActions(fx.file) : errorActions(fx.action));
      } else if (fx.type === 'desktop') {
        desktopNotify(fx.title, fx.body);
      } else if (fx.type === 'chime') {
        if (configRef.current.completion_sound) playCompletionChime();
      } else if (fx.type === 'refreshStats') {
        refreshStats();
      } else if (fx.type === 'refreshVault') {
        refreshVault();
      } else if (fx.type === 'victory') {
        celebrate(fx);
      }
    }
    dispatch({ type: 'effects_done', count: effects.length });
  }, [dl.effects, showNotif, errorActions, desktopNotify, refreshStats, refreshVault, celebrate]);

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
            stats={stats}
            sysInfo={sysInfo}
            refreshStats={refreshStats}
            showNotif={showNotif}
            switchPage={switchPage}
            config={config}
            setConfig={setConfig}
            suggestedUrl={clipboardSuggestion}
            onSuggestedConsumed={() => setClipboardSuggestion(null)}
            onPlaylistDownload={(count, name) => dispatch({ type: 'playlist_started', name, count })}
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
            onSyncItems={(items, count, name) => dispatch(items === null
              ? { type: 'playlist_started', name, count: 0, fetching: true }
              : { type: 'playlist_items', items, count, name })}
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
            installAppUpdate={installAppUpdate}
            sysInfo={sysInfo}
            refreshStats={refreshStats}
          />
        )}

        <StatusBar sysInfo={sysInfo} speedHistory={speedHistory} config={config} />
      </div>

      <Notif notif={notif} dismiss={() => setNotif(null)} />

      {appUpdate && <AppUpdateOverlay update={appUpdate} />}

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
              {restorableJobs.length} download(s) hadn't finished when the app last closed:
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
