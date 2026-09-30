// VAULT page — folder grid, folder view, file actions.
'use strict';

import { API } from '../lib/api.js';
import { fmtBytes, fmtDate, timeAgo } from '../lib/util.js';
import { Ico } from '../components/icons.jsx';
import { Modal, Mascot } from '../components/common.jsx';
import {
  MASCOT_CHILLING, MASCOT_TIRED, MASCOT_FRUSTRATED, MASCOT_COMFY_SAFE,
} from '../lib/mascots.js';
import {
  LinkPlaylistModal, SyncPlaylistModal,
  RenameVaultModal, DuplicatesModal,
} from '../components/vault-modals.jsx';

const BYTES_PER_GB = 1024 ** 3;
const VIDEO_PREVIEW_EXTS = ['mp4', 'webm', 'mkv', 'avi', 'mov'];

// In-app preview — streams through /api/vault/stream (Range-aware, seekable)
function MediaPreviewModal({ file, onClose }) {
  const src = '/api/vault/stream?path=' + encodeURIComponent(file.path);
  const isVideo = VIDEO_PREVIEW_EXTS.includes((file.ext || '').toLowerCase());
  return (
    <Modal title={'PREVIEW — ' + file.name.toUpperCase().slice(0, 40)} onClose={onClose} footer={
      <button className="btn btn-secondary btn-sm" onClick={onClose}>CLOSE</button>
    }>
      {isVideo ? (
        <video src={src} controls autoPlay style={{ width: '100%', maxHeight: 380, background: '#000' }} />
      ) : (
        <audio src={src} controls autoPlay style={{ width: '100%' }} />
      )}
    </Modal>
  );
}

export function VaultPage({ vaultFolders, selectedFolder, setSelectedFolder, config, setConfig, showNotif, onAddVault, onRefreshVault, isDownloading, onSyncStart, onSyncItems }) {
  const [files, setFiles] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [ctxMenu, setCtxMenu] = React.useState(null);
  const [libraryEntries, setLibraryEntries] = React.useState([]);
  const [syncingId, setSyncingId] = React.useState(null);
  const [deleteConfirm, setDeleteConfirm] = React.useState(null);
  const [dragOver, setDragOver] = React.useState(false);
  const [dropModal, setDropModal] = React.useState(null);
  const [vaultSearch, setVaultSearch] = React.useState('');
  const [vaultSort, setVaultSort] = React.useState('name');
  const [folderMosaics, setFolderMosaics] = React.useState({});
  const [cardMenuData, setCardMenuData] = React.useState(null); // { folder, top, right }
  const [linkPlModal, setLinkPlModal] = React.useState(null);
  const [renameModal, setRenameModal] = React.useState(null);
  const [syncModal, setSyncModal] = React.useState(null);
  const [folderStatsModal, setFolderStatsModal] = React.useState(null); // folder stats modal
  const [folderStatsData, setFolderStatsData] = React.useState(null);
  const [fileThumbs, setFileThumbs] = React.useState({});
  const [vaultScale, setVaultScale] = React.useState(() => { try { return localStorage.getItem('vault_scale') || 'md'; } catch { return 'md'; } });
  const [selectedFiles, setSelectedFiles] = React.useState(new Set());
  const [selectionMode, setSelectionMode] = React.useState(false);
  const [randomizerCount, setRandomizerCount] = React.useState(5);
  const [randomizedFiles, setRandomizedFiles] = React.useState(null);
  const [watchArchivePrompt, setWatchArchivePrompt] = React.useState(null); // { path }
  const [dupModal, setDupModal] = React.useState(false);
  const [previewFile, setPreviewFile] = React.useState(null);
  const [budgetInput, setBudgetInput] = React.useState('');
  const [cleanupData, setCleanupData] = React.useState(null);

  const budgets = config.vault_budgets || {};

  const handleSetBudget = React.useCallback((folderPath, gb) => {
    const bytes = gb ? Math.round(parseFloat(gb) * BYTES_PER_GB) : null;
    if (gb && (!Number.isFinite(parseFloat(gb)) || parseFloat(gb) <= 0)) {
      showNotif('Invalid budget', 'Enter a size in GB (e.g. 25)', 'error');
      return;
    }
    API.post('/api/vault/budget', { path: folderPath, budget_bytes: bytes })
      .then(d => {
        setConfig && setConfig(c => ({ ...c, vault_budgets: d.budgets }));
        const folderName = folderPath.split(/[\\/]/).pop();
        showNotif(bytes ? 'Budget Set' : 'Budget Cleared',
          bytes ? fmtBytes(bytes) + ' for ' + folderName : folderName, 'success');
        setCleanupData(null);
      })
      .catch(e => showNotif('Error', e.message, 'error'));
  }, [setConfig, showNotif]);

  const loadCleanupCandidates = React.useCallback((folderPath) => {
    setCleanupData('loading');
    API.get('/api/vault/cleanup-candidates?path=' + encodeURIComponent(folderPath))
      .then(setCleanupData)
      .catch(e => { showNotif('Error', e.message, 'error'); setCleanupData(null); });
  }, [showNotif]);

  const refreshLibraryEntries = React.useCallback(() => {
    API.get('/api/library').then(setLibraryEntries).catch(() => {});
  }, []);

  React.useEffect(() => {
    refreshLibraryEntries();
  }, []);

  React.useEffect(() => {
    if (!selectedFolder) return;
    setLoading(true);
    API.get('/api/vault/folder?path=' + encodeURIComponent(selectedFolder))
      .then(d => {
        const loaded = d.files || [];
        setFiles(loaded);
        if (loaded.length > 0) {
          const paths = loaded.map(f => f.path);
          API.post('/api/vault/file-thumbs', { paths })
            .then(r => setFileThumbs(r.thumbs || {}))
            .catch(() => {});
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedFolder]);

  // Load thumbnail mosaics for all vault folder cards
  React.useEffect(() => {
    if (!vaultFolders.length) return;
    vaultFolders.forEach(folder => {
      if (folderMosaics[folder.path] !== undefined) return;
      API.get('/api/vault/folder-previews?path=' + encodeURIComponent(folder.path))
        .then(d => setFolderMosaics(prev => ({ ...prev, [folder.path]: d.thumbs || [] })))
        .catch(() => setFolderMosaics(prev => ({ ...prev, [folder.path]: [] })));
    });
  }, [vaultFolders]);

  const selectedFolderMeta = vaultFolders.find(f => f.path === selectedFolder);
  const libEntry = selectedFolderMeta && selectedFolderMeta.library_id
    ? libraryEntries.find(e => e.id === selectedFolderMeta.library_id)
    : libraryEntries.find(e => e.folder_name && selectedFolder && selectedFolder.endsWith(e.folder_name));

  // Same sync as the folder card: every linked playlist, in the format the
  // folder remembers. (It used to sync only the library entry's first URL,
  // with the entry's settings.) Library sync is the fallback for entries
  // made before playlists were linked to folders.
  const handleSync = React.useCallback(() => {
    if (!selectedFolder) return;
    if (isDownloading) showNotif('Note', 'Sync will queue after current download', 'info');
    setSyncingId(selectedFolder);
    const label = libEntry ? libEntry.name : selectedFolder.split(/[\\/]/).pop();
    API.post('/api/vault/sync', { path: selectedFolder })
      .then(d => {
        if (!d.error) return d;
        if (!libEntry) throw new Error(d.error);
        return API.post('/api/library/' + libEntry.id + '/sync', { mode: libEntry.sync_mode || 'add' });
      })
      .then(() => showNotif('Sync started', label))
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setSyncingId(null));
  }, [selectedFolder, libEntry, isDownloading, showNotif]);

  // The card and this view read different stamps; show whichever is newer
  const lastSynced = [libEntry && libEntry.last_synced, selectedFolderMeta && selectedFolderMeta.last_synced]
    .filter(Boolean)
    .sort((a, b) => new Date(b) - new Date(a))[0] || null;
  const canSync = !!(libEntry || (selectedFolderMeta && selectedFolderMeta.last_synced));

  const handleRandomize = React.useCallback(() => {
    const mediaFiles = files.filter(f => /\.(mp4|mkv|webm|mp3|m4a|flac|wav|aac|avi|mov|opus)$/i.test(f.name));
    if (!mediaFiles.length) { showNotif('No media', 'No media files in this folder', 'error'); return; }
    const count = Math.min(randomizerCount, mediaFiles.length);
    const shuffled = [...mediaFiles].sort(() => Math.random() - 0.5).slice(0, count);
    setRandomizedFiles(shuffled);
    setSelectedFiles(new Set());
    setSelectionMode(true);
  }, [files, randomizerCount, showNotif]);

  const handlePlayRandom = React.useCallback(() => {
    const randPaths = (randomizedFiles || []).map(f => f.path);
    const manualPaths = files.filter(f => selectedFiles.has(f.path)).map(f => f.path);
    const paths = [...new Set([...randPaths, ...manualPaths])];
    if (!paths.length) return;
    API.post('/api/vault/play-files', { paths })
      .then(() => showNotif('Playing', paths.length + ' files opened in player', 'success'))
      .catch(e => showNotif('Error', e.message, 'error'));
  }, [randomizedFiles, selectedFiles, files, showNotif]);

  const handlePlaySelected = React.useCallback(() => {
    if (!selectedFiles.size) return;
    const paths = files.filter(f => selectedFiles.has(f.path)).map(f => f.path);
    API.post('/api/vault/play-files', { paths })
      .then(() => showNotif('Playing', paths.length + ' files opened in player', 'success'))
      .catch(e => showNotif('Error', e.message, 'error'));
  }, [selectedFiles, files, showNotif]);

  const handleDeleteSelected = React.useCallback(() => {
    if (!selectedFiles.size) return;
    const paths = [...selectedFiles];
    Promise.all(paths.map(p => API.del('/api/vault/file', { path: p }).catch(() => null)))
      .then(() => {
        setFiles(f => f.filter(x => !selectedFiles.has(x.path)));
        showNotif('Deleted', paths.length + ' file(s)');
        setSelectedFiles(new Set());
        setSelectionMode(false);
      });
  }, [selectedFiles, showNotif]);

  const handleOpenFile = React.useCallback((path) => {
    API.post('/api/vault/open-file', { path }).catch(() => {});
  }, []);

  const handleOpenFolder = React.useCallback((path) => {
    API.post('/api/open-folder', { path }).catch(() => {});
  }, []);

  const handleDeleteFile = React.useCallback((file) => {
    setDeleteConfirm(file);
    setCtxMenu(null);
  }, []);

  const confirmDelete = React.useCallback(() => {
    if (!deleteConfirm) return;
    API.del('/api/vault/file', { path: deleteConfirm.path })
      .then(() => {
        setFiles(f => f.filter(x => x.path !== deleteConfirm.path));
        showNotif('Deleted', deleteConfirm.name);
      })
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setDeleteConfirm(null));
  }, [deleteConfirm, showNotif]);

  const isVideoExt = (ext) => ['mp4','mkv','webm','avi','mov'].includes(ext);

  React.useEffect(() => {
    const close = () => { setCtxMenu(null); setCardMenuData(null); };
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, []);

  const handleVaultRemove = React.useCallback((folder) => {
    API.post('/api/vault/remove', { path: folder.path })
      .then(() => {
        showNotif('Removed', folder.name);
        if (selectedFolder === folder.path) setSelectedFolder(null);
        setFolderMosaics(prev => { const next = { ...prev }; delete next[folder.path]; return next; });
        onRefreshVault && onRefreshVault();
        refreshLibraryEntries();
      })
      .catch(e => showNotif('Error', e.message, 'error'));
    setCardMenuData(null);
  }, [showNotif, onRefreshVault, selectedFolder, setSelectedFolder, refreshLibraryEntries]);

  const handleVaultRename = React.useCallback((folder, name) => {
    API.post('/api/vault/rename', { path: folder.path, name })
      .then(() => {
        setFolderMosaics(prev => { const next = { ...prev }; delete next[folder.path]; return next; });
        onRefreshVault && onRefreshVault();
        refreshLibraryEntries();
      })
      .catch(e => showNotif('Error', e.message, 'error'));
    setRenameModal(null);
  }, [showNotif, onRefreshVault, refreshLibraryEntries]);

  const handleWatchFolder = React.useCallback(() => {
    API.post('/api/browse-folder', {}).then(d => {
      if (!d.path) return;
      setWatchArchivePrompt({ path: d.path });
    }).catch(() => {});
  }, []);

  const confirmWatchFolder = React.useCallback((folderPath, createArchive) => {
    setWatchArchivePrompt(null);
    API.post('/api/vault/watch', { path: folderPath, create_archive: createArchive })
      .then(() => {
        showNotif('Watch Folder Added', folderPath.split(/[\\/]/).pop() + (createArchive ? ' · mellow_archive.txt created' : ''), 'success');
        onRefreshVault && onRefreshVault();
      })
      .catch(e => showNotif('Error', e.message, 'error'));
  }, [showNotif, onRefreshVault]);

  const handleDragOver = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setDragOver(false); };
  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation(); setDragOver(false);
    const droppedFiles = Array.from(e.dataTransfer.files || []);
    if (droppedFiles.length > 0) {
      const first = droppedFiles[0];
      setDropModal({ name: first.name });
    }
  };

  // ── ROOT VIEW — folder grid ──────────────────────────────────────────────────
  if (!selectedFolder) {
    return (
      <div
        className={'content active' + (dragOver ? ' drag-over' : '')}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="vhead">
          <div>
            <div className="vlabel">メディアボールト / MEDIA VAULT</div>
            <div className="vtitle">VAULT <span className="c">BROWSER</span></div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div className="pills" style={{ marginBottom: 0 }}>
              {['sm','md','lg'].map(s => (
                <div key={s} className={'pill' + (vaultScale === s ? ' active' : '')}
                  onClick={() => { setVaultScale(s); try { localStorage.setItem('vault_scale', s); } catch {} }}>
                  {s.toUpperCase()}
                </div>
              ))}
            </div>
            <button className="btn btn-secondary btn-sm" onClick={() => { onRefreshVault && onRefreshVault(); refreshLibraryEntries(); }} title="Refresh vault">↻ REFRESH</button>
            {vaultFolders.some(f => f.last_synced !== undefined || f.library_id) && (
              <button className="btn btn-secondary btn-sm" title="Sync all linked folders"
                onClick={() => {
                  const linked = vaultFolders.filter(f => f.library_id || f.last_synced);
                  if (!linked.length) { showNotif('Nothing to sync', 'No linked folders found', 'info'); return; }
                  API.post('/api/vault/sync-all', {})
                    .then(d => showNotif('Sync All Queued', d.count + ' folder(s) queued', 'success'))
                    .catch(e => showNotif('Sync Error', e.message, 'error'));
                }}>↻ SYNC ALL</button>
            )}
            <button className="btn btn-secondary btn-sm" onClick={() => setDupModal(true)} title="Find duplicate files across folders">⧉ FIND DUPES</button>
            <button className="btn btn-secondary btn-sm" onClick={handleWatchFolder}>
              <Ico name="folder" /> WATCH FOLDER
            </button>
            <button className="btn btn-primary btn-sm" onClick={onAddVault}>ADD PLAYLIST</button>
          </div>
        </div>

        {vaultFolders.length === 0 ? (
          <div className="empty-state">
            <Mascot src={MASCOT_COMFY_SAFE || MASCOT_CHILLING} className="empty-mascot" wrapClass="empty-mascot-wrap" />
            <div className="empty-title">VAULT EMPTY</div>
            <div className="empty-sub" onClick={onAddVault}>Add a playlist or watch folder to get started</div>
          </div>
        ) : (
          <div className="vault-folder-grid" style={{ '--vault-card-width': vaultScale === 'sm' ? '160px' : vaultScale === 'lg' ? '280px' : '200px' }}>
            {vaultFolders.map(folder => {
              const thumbs = folderMosaics[folder.path] || [];
              const showMosaic = thumbs.length > 0;
              return (
                <div key={folder.path} className="vault-folder-card" onClick={() => setSelectedFolder(folder.path)}>
                  {/* Thumbnail mosaic or folder icon */}
                  {showMosaic ? (
                    thumbs.length === 1 ? (
                      <img src={thumbs[0]} style={{width:'100%',height:'100%',objectFit:'cover',display:'block'}} alt=""
                        onError={e => { e.target.style.display='none'; }} />
                    ) : (
                      <div className="vfc-mosaic">
                        {[0,1,2,3].map((i) => {
                          const t = thumbs[i] || null;
                          return t
                            ? <img key={i} src={t} className="vfc-mosaic-cell" alt="" onError={e => { e.target.style.display='none'; }} />
                            : <div key={i} className="vfc-mosaic-ph" />;
                        })}
                      </div>
                    )
                  ) : (
                    <div className="vfc-icon">
                      <svg className="vfc-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" width="48" height="48">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                      </svg>
                    </div>
                  )}

                  {/* Three-dot menu button */}
                  <div className="vfc-menu-btn" onClick={e => {
                    e.stopPropagation();
                    if (cardMenuData && cardMenuData.folder.path === folder.path) {
                      setCardMenuData(null);
                      return;
                    }
                    const rect = e.currentTarget.getBoundingClientRect();
                    setCardMenuData({ folder, top: rect.bottom + 4, right: window.innerWidth - rect.right });
                  }}>⋮</div>

                  {/* Quick sync button — only shows when folder has a linked playlist */}
                  {folder.library_id && (
                    <div className="vfc-sync-btn" title="Sync" onClick={e => { e.stopPropagation(); setSyncModal(folder); }}>↻</div>
                  )}

                  {folder.watched && <span className="vfc-watched-badge">WATCHED</span>}
                  {budgets[folder.path] && folder.size_bytes > budgets[folder.path] && (
                    <span className="vfc-watched-badge" style={{ background: 'var(--red)', top: 6, left: 6, right: 'auto' }} title={'Over the ' + fmtBytes(budgets[folder.path]) + ' budget'}>
                      OVER BUDGET
                    </span>
                  )}
                  <div className="vfc-bottom">
                    <div className="vfc-name">{folder.name}</div>
                    <div className="vfc-meta-text">
                      {folder.item_count || 0} MEDIA · {fmtBytes(folder.size_bytes)}
                      {budgets[folder.path] ? ' / ' + fmtBytes(budgets[folder.path]) : ''}
                    </div>
                    {folder.library_name && (
                      <div className="vfc-lib-tag"><Ico name="sync" size={9} />{folder.library_name}</div>
                    )}
                    {folder.last_synced && (
                      <div className="vfc-synced">SYNCED {timeAgo(folder.last_synced)}</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Fixed-position folder card menu (renders above overflow:hidden) */}
        {cardMenuData && (
          <div
            className="vfc-menu-popup"
            style={{ top: cardMenuData.top, right: cardMenuData.right }}
            onClick={e => e.stopPropagation()}
          >
            <div className="vfc-menu-item" onClick={() => {
              const f = cardMenuData.folder;
              setCardMenuData(null);
              setFolderStatsData(null);
              setCleanupData(null);
              setBudgetInput(budgets[f.path] ? String(budgets[f.path] / BYTES_PER_GB) : '');
              setFolderStatsModal(f);
              API.get('/api/vault/folder-stats?path=' + encodeURIComponent(f.path)).then(setFolderStatsData).catch(() => {});
            }}>Stats &amp; Budget</div>
            <div className="vfc-menu-item" onClick={() => { setCardMenuData(null); setLinkPlModal(cardMenuData.folder); }}>Link Playlist</div>
            <div className="vfc-menu-item" onClick={() => { setCardMenuData(null); setSyncModal(cardMenuData.folder); }}>Sync</div>
            <div className="vfc-menu-item" onClick={() => { setCardMenuData(null); API.post('/api/open-folder', { path: cardMenuData.folder.path }).catch(() => {}); }}>Open in Explorer</div>
            <div className="vfc-menu-item" onClick={() => { setCardMenuData(null); setRenameModal({ folder: cardMenuData.folder, name: cardMenuData.folder.name }); }}>Rename</div>
            <div className="vfc-menu-item" onClick={() => {
              const f = cardMenuData.folder;
              setCardMenuData(null);
              API.post('/api/vault/archive-generate', { path: f.path })
                .then(d => showNotif('Archive Ready', d.migrated ? 'Migrated old archive → mellow_archive.txt' : 'mellow_archive.txt ready in ' + f.name, 'success'))
                .catch(e => showNotif('Error', e.message, 'error'));
            }}>Generate Archive File</div>
            <div className="vfc-menu-item danger" onClick={() => handleVaultRemove(cardMenuData.folder)}>Remove from Vault</div>
          </div>
        )}

        {dropModal && (
          <Modal title="DROP DETECTED" onClose={() => setDropModal(null)}
            footer={
              <>
                <button className="btn btn-secondary btn-sm" onClick={() => setDropModal(null)}>CANCEL</button>
                <button className="btn btn-secondary btn-sm" onClick={() => { setDropModal(null); handleWatchFolder(); }}>WATCH FOLDER</button>
                <button className="btn btn-primary btn-sm" onClick={() => { setDropModal(null); onAddVault && onAddVault(); }}>LINK PLAYLIST</button>
              </>
            }
          >
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t2)', textAlign: 'center', lineHeight: 2 }}>
              Dropped: <span style={{ color: 'var(--cyan)' }}>{dropModal.name}</span><br />
              <span style={{ color: 'var(--t4)', fontSize: 9 }}>What would you like to do?</span>
            </div>
          </Modal>
        )}

        {linkPlModal && <LinkPlaylistModal folder={linkPlModal} onClose={() => setLinkPlModal(null)} showNotif={showNotif} />}

        {dupModal && <DuplicatesModal onClose={() => setDupModal(false)} showNotif={showNotif} onRefreshVault={onRefreshVault} />}

        {syncModal && <SyncPlaylistModal folder={syncModal} onClose={() => setSyncModal(null)} showNotif={showNotif} onRefreshVault={onRefreshVault} isDownloading={isDownloading} onSyncStart={onSyncStart} onSyncItems={onSyncItems} />}

        {renameModal && (
          <RenameVaultModal
            folder={renameModal.folder}
            initialName={renameModal.name}
            onClose={() => setRenameModal(null)}
            onSave={(name) => handleVaultRename(renameModal.folder, name)}
          />
        )}

        {watchArchivePrompt && (
          <Modal title="WATCH FOLDER — ARCHIVE FILE" onClose={() => setWatchArchivePrompt(null)}
            footer={
              <>
                <button className="btn btn-secondary btn-sm" onClick={() => setWatchArchivePrompt(null)}>CANCEL</button>
                <button className="btn btn-secondary btn-sm" onClick={() => confirmWatchFolder(watchArchivePrompt.path, false)}>NO ARCHIVE</button>
                <button className="btn btn-primary btn-sm" onClick={() => confirmWatchFolder(watchArchivePrompt.path, true)}>YES, CREATE FILE</button>
              </>
            }
          >
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t2)', lineHeight: 2 }}>
              <div style={{ color: 'var(--cyan)', marginBottom: 6 }}>{watchArchivePrompt.path}</div>
              <div>Create a <span style={{ color: 'var(--amber)' }}>mellow_archive.txt</span> in this folder?</div>
              <div style={{ color: 'var(--t4)', fontSize: 9, marginTop: 4 }}>
                This file tracks downloaded items so syncs skip duplicates,<br />
                and can be imported as a URL list in the Feed section.
              </div>
            </div>
          </Modal>
        )}

        {folderStatsModal && (
          <Modal title={'STATS — ' + folderStatsModal.name.toUpperCase()} onClose={() => setFolderStatsModal(null)}>
            {!folderStatsData ? (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--t3)', fontFamily: 'Share Tech Mono, monospace', fontSize: 11 }}>Loading...</div>
            ) : folderStatsData.error ? (
              <div style={{ padding: 24, color: 'var(--red)', fontFamily: 'Share Tech Mono, monospace', fontSize: 11 }}>{folderStatsData.error}</div>
            ) : (
              <div style={{ padding: '8px 0', fontFamily: 'Share Tech Mono, monospace', fontSize: 11 }}>
                {(() => {
                  const s = folderStatsData;
                  const rows = [
                    ['Path', s.path],
                    ['Media Files', (s.media_count || 0) + ' items  (' + (s.audio_count || 0) + ' audio · ' + (s.video_count || 0) + ' video)'],
                    ['Total Size', fmtBytes(s.total_size_bytes)],
                    ['Avg File Size', fmtBytes(s.avg_size_bytes)],
                    ['Linked Playlists', (s.linked_playlists || 0) + ' playlist(s)'],
                    ['Formats', Object.entries(s.formats || {}).sort((a,b)=>b[1]-a[1]).map(([ext,n])=>ext.toUpperCase()+'('+n+')').join('  ')],
                    ['Largest File', s.largest_file ? s.largest_file.name + '  · ' + fmtBytes(s.largest_file.size) : '—'],
                    ['Smallest File', s.smallest_file ? s.smallest_file.name + '  · ' + fmtBytes(s.smallest_file.size) : '—'],
                    ['Newest File', s.newest_file ? s.newest_file.name + '  · ' + timeAgo(s.newest_file.ts * 1000) : '—'],
                    ['Oldest File', s.oldest_file ? s.oldest_file.name + '  · ' + timeAgo(s.oldest_file.ts * 1000) : '—'],
                  ];
                  return rows.map(([label, val]) => (
                    <div key={label} style={{ display: 'flex', gap: 12, padding: '5px 0', borderBottom: '1px solid var(--border)' }}>
                      <span style={{ color: 'var(--t3)', minWidth: 120, flexShrink: 0 }}>{label}</span>
                      <span style={{ color: 'var(--cyan)', wordBreak: 'break-all', fontSize: 10 }}>{val || '—'}</span>
                    </div>
                  ));
                })()}
                {/* STORAGE BUDGET */}
                <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
                  <div style={{ color: 'var(--amber)', fontSize: 9, letterSpacing: '0.1em', marginBottom: 6 }}>STORAGE BUDGET</div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input
                      className="inp-sm" type="number" min="0" step="0.5" style={{ width: 90 }}
                      placeholder="GB" value={budgetInput}
                      onChange={e => setBudgetInput(e.target.value)}
                    />
                    <span style={{ color: 'var(--t4)', fontSize: 9 }}>GB</span>
                    <button className="btn btn-primary btn-sm" onClick={() => handleSetBudget(folderStatsModal.path, budgetInput)}>SET</button>
                    {budgets[folderStatsModal.path] && (
                      <button className="btn btn-secondary btn-sm" onClick={() => { setBudgetInput(''); handleSetBudget(folderStatsModal.path, null); }}>CLEAR</button>
                    )}
                  </div>
                  {budgets[folderStatsModal.path] && folderStatsData.total_size_bytes > budgets[folderStatsModal.path] && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ color: 'var(--red)', fontSize: 10 }}>
                        ⚠ {fmtBytes(folderStatsData.total_size_bytes - budgets[folderStatsModal.path])} over budget
                      </div>
                      <button className="btn btn-secondary btn-sm" style={{ marginTop: 6 }}
                        onClick={() => loadCleanupCandidates(folderStatsModal.path)}>
                        VIEW CLEANUP CANDIDATES
                      </button>
                    </div>
                  )}
                  {cleanupData === 'loading' && (
                    <div style={{ color: 'var(--t4)', fontSize: 9, marginTop: 6 }}>SCANNING...</div>
                  )}
                  {cleanupData && cleanupData !== 'loading' && (cleanupData.candidates || []).length > 0 && (
                    <div style={{ maxHeight: 140, overflow: 'auto', marginTop: 8 }}>
                      <div style={{ color: 'var(--t3)', fontSize: 9, marginBottom: 4 }}>
                        Oldest files to free {fmtBytes(cleanupData.over_bytes)} (nothing is deleted automatically):
                      </div>
                      {cleanupData.candidates.map(f => (
                        <div key={f.path} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 9, padding: '2px 0', borderBottom: '1px solid var(--border)' }}>
                          <span style={{ flex: 1, color: 'var(--t2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                          <span style={{ color: 'var(--t4)', flexShrink: 0 }}>{fmtBytes(f.size)} · {fmtDate(f.mtime * 1000)}</span>
                          <button className="btn btn-danger btn-sm" style={{ padding: '1px 6px', fontSize: 8, flexShrink: 0 }}
                            onClick={() => {
                              API.del('/api/vault/file', { path: f.path })
                                .then(() => { showNotif('Deleted', f.name); loadCleanupCandidates(folderStatsModal.path); onRefreshVault && onRefreshVault(); })
                                .catch(e => showNotif('Error', e.message, 'error'));
                            }}>✕</button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                  <button className="btn btn-secondary btn-sm" onClick={() => { setFolderStatsModal(null); API.post('/api/open-folder', { path: folderStatsModal.path }).catch(() => {}); }}>OPEN IN EXPLORER</button>
                </div>
              </div>
            )}
          </Modal>
        )}
      </div>
    );
  }

  // ── FOLDER VIEW ──────────────────────────────────────────────────────────────
  const folderName = selectedFolder.split(/[\\/]/).pop();

  return (
    <div
      className={'content active' + (dragOver ? ' drag-over' : '')}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="vhead">
        <div>
          <div className="vlabel">メディアボールト / MEDIA VAULT</div>
          <div className="vtitle">VAULT <span className="c">{folderName.toUpperCase().slice(0, 16)}</span></div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="pills" style={{ marginBottom: 0 }}>
            {['sm','md','lg'].map(s => (
              <div key={s} className={'pill' + (vaultScale === s ? ' active' : '')}
                onClick={() => { setVaultScale(s); try { localStorage.setItem('vault_scale', s); } catch {} }}>
                {s.toUpperCase()}
              </div>
            ))}
          </div>
          {canSync && (
            <button className="btn btn-amber btn-sm" onClick={handleSync} disabled={!!syncingId}>
              {syncingId ? 'SYNCING...' : (<><Ico name="sync" /> SYNC NOW</>)}
            </button>
          )}
          {canSync && selectedFolderMeta && (
            <button className="btn btn-secondary btn-sm" title="Sync options / selective playlist sync"
              onClick={() => setSyncModal(selectedFolderMeta)}>SYNC OPTIONS</button>
          )}
          <button className="btn btn-secondary btn-sm" onClick={() => {
            setLoading(true);
            API.get('/api/vault/folder?path=' + encodeURIComponent(selectedFolder))
              .then(d => {
                const loaded = d.files || [];
                setFiles(loaded);
                if (loaded.length > 0) {
                  API.post('/api/vault/file-thumbs', { paths: loaded.map(f => f.path) })
                    .then(r => setFileThumbs(r.thumbs || {})).catch(() => {});
                }
              }).catch(() => {}).finally(() => setLoading(false));
          }}>↻ REFRESH</button>
          <button className="btn btn-secondary btn-sm" onClick={() => handleOpenFolder(selectedFolder)}>
            OPEN IN EXPLORER
          </button>
        </div>
      </div>

      {/* BREADCRUMB */}
      <div className="vault-breadcrumb">
        <span className="vbc-root" onClick={() => setSelectedFolder(null)}>VAULT ROOT</span>
        <span className="vbc-sep">›</span>
        <span className="vbc-current">{folderName.toUpperCase()}</span>
      </div>

      {libEntry && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="ph">
            <span className="ptag cyan">SYNCED</span>
            <span className="ptitle">{libEntry.name}</span>
            <span className="psub">
              {lastSynced ? 'Last sync: ' + timeAgo(lastSynced) : 'Never synced'}
            </span>
          </div>
        </div>
      )}

      {!loading && files.length > 0 && (
        <>
          <div className="vault-lib-controls">
            <div className="vault-lib-search-wrap">
              <span className="vault-lib-search-icon"><Ico name="signal" size={12} /></span>
              <input
                className="vault-lib-search"
                placeholder="SEARCH IN LIBRARY — ライブラリを検索"
                value={vaultSearch}
                onChange={e => setVaultSearch(e.target.value)}
              />
            </div>
            <select className="vault-lib-sort" value={vaultSort} onChange={e => setVaultSort(e.target.value)}>
              <option value="name">SORT BY: NAME</option>
              <option value="size">SORT BY: SIZE</option>
              <option value="date">SORT BY: DATE</option>
            </select>
          </div>
          <div className="vault-lib-count">TOTAL: <span>{files.filter(f => !vaultSearch || f.name.toLowerCase().includes(vaultSearch.toLowerCase())).length} ITEMS</span></div>
          <div className="randomizer-bar">
            <span className="opts-label">RANDOMIZE</span>
            <div className="rand-stepper">
              <button className="rand-step-btn" onClick={() => setRandomizerCount(c => Math.max(1, c - 1))}>−</button>
              <span className="rand-step-val">{randomizerCount}</span>
              <button className="rand-step-btn" onClick={() => setRandomizerCount(c => Math.min(files.length || 99, c + 1))}>+</button>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={handleRandomize}>PICK</button>
            {randomizedFiles && (
              <>
                <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--cyan)' }}>
                  {new Set([...randomizedFiles.map(f => f.path), ...selectedFiles]).size} selected
                </span>
                <button className="btn btn-primary btn-sm" onClick={handlePlayRandom}>
                  ▶ PLAY ({new Set([...randomizedFiles.map(f => f.path), ...selectedFiles]).size})
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => { setRandomizedFiles(null); setSelectedFiles(new Set()); setSelectionMode(false); }}>✕</button>
              </>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 4 }}>
            <button className={'btn btn-sm ' + (selectionMode ? 'btn-primary' : 'btn-secondary')}
              onClick={() => { setSelectionMode(s => !s); setSelectedFiles(new Set()); }}>
              {selectionMode ? 'EXIT SELECT' : 'SELECT'}
            </button>
            {selectionMode && selectedFiles.size > 0 && (
              <>
                <button className="btn btn-secondary btn-sm" onClick={() => setSelectedFiles(new Set(files.map(f => f.path)))}>ALL</button>
                <button className="btn btn-secondary btn-sm" onClick={() => setSelectedFiles(new Set())}>NONE</button>
                <button className="btn btn-primary btn-sm" onClick={handlePlaySelected}>▶ PLAY ({selectedFiles.size})</button>
                <button className="btn btn-danger btn-sm" onClick={handleDeleteSelected}>DELETE ({selectedFiles.size})</button>
              </>
            )}
          </div>
        </>
      )}

      {loading ? (
        <div className="empty-state">
          <Mascot src={MASCOT_CHILLING} className="empty-mascot" wrapClass="empty-mascot-wrap" />
          <div className="empty-title">LOADING...</div>
        </div>
      ) : files.length === 0 ? (
        <div className="empty-state">
          <Mascot src={MASCOT_TIRED} className="empty-mascot" wrapClass="empty-mascot-wrap" />
          <div className="empty-title">NO MEDIA HERE</div>
          <div className="empty-sub">Download something to this folder</div>
        </div>
      ) : (
        <div className="lib-grid" style={{ '--lib-card-min': vaultScale === 'sm' ? '130px' : vaultScale === 'lg' ? '240px' : '175px' }}>
          {files
            .filter(f => !vaultSearch || f.name.toLowerCase().includes(vaultSearch.toLowerCase()))
            .sort((a, b) => {
              if (vaultSort === 'size') return (b.size_bytes || 0) - (a.size_bytes || 0);
              if (vaultSort === 'date') return (b.created || 0) - (a.created || 0);
              return a.name.localeCompare(b.name);
            })
            .map(file => {
              const isRandSelected = randomizedFiles && randomizedFiles.some(f => f.path === file.path);
              const isFileSelected = selectedFiles.has(file.path);
              return (
            <div key={file.path}
              className={'lib-card' + (isRandSelected && !isFileSelected ? ' rand-selected' : '') + (isFileSelected ? ' file-selected' : '')}
              onClick={() => {
                if (selectionMode) {
                  setSelectedFiles(prev => { const next = new Set(prev); next.has(file.path) ? next.delete(file.path) : next.add(file.path); return next; });
                } else {
                  handleOpenFile(file.path);
                }
              }}>
              <div style={{ position: 'relative', width: '100%', height: 100, overflow: 'hidden', background: 'linear-gradient(135deg,var(--bg3),var(--bg2))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 32, color: 'var(--t4)' }}>
                <span style={{ position: 'relative', zIndex: 0 }}>{isVideoExt(file.ext) ? '▶' : '♫'}</span>
                {(fileThumbs[file.path] || '/api/vault/thumb?path=' + encodeURIComponent(file.path)) && (
                  <img
                    src={fileThumbs[file.path] || '/api/vault/thumb?path=' + encodeURIComponent(file.path)}
                    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', zIndex: 1 }}
                    alt=""
                    onError={e => { e.target.style.display = 'none'; }}
                    onLoad={e => { e.target.style.display = ''; }}
                  />
                )}
                <div className={'lib-fmt ' + (isVideoExt(file.ext) ? 'video' : 'audio')} style={{ position: 'absolute', top: 6, left: 6, zIndex: 2, margin: 0 }}>
                  {file.ext.toUpperCase()}
                </div>
                {selectionMode && (
                  <div style={{ position: 'absolute', top: 6, right: 6, zIndex: 3, width: 16, height: 16, borderRadius: 3, border: '2px solid var(--cyan)', background: isFileSelected ? 'var(--cyan)' : 'var(--bg1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--bg1)' }}>
                    {isFileSelected && '✓'}
                  </div>
                )}
              </div>
              <div className="lib-body">
                <div className="lib-title">{file.name.replace(/\.[^.]+$/, '')}</div>
                <div className="lib-meta">{fmtBytes(file.size_bytes)}</div>
                {file.created && (
                  <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 8, color: 'var(--t4)', marginTop: 2 }}>{fmtDate(file.created * 1000)}</div>
                )}
              </div>
              <div
                className="lib-menu"
                onClick={(e) => {
                  e.stopPropagation();
                  const rect = e.currentTarget.getBoundingClientRect();
                  setCtxMenu({ file, x: rect.right, y: rect.bottom });
                }}
              >
                <Ico name="dots" />
              </div>
            </div>
              );
            })}
        </div>
      )}

      {ctxMenu && (
        <div className="ctx-menu" style={{ left: ctxMenu.x, top: ctxMenu.y }} onClick={e => e.stopPropagation()}>
          <div className="ctx-item" onClick={() => { setPreviewFile(ctxMenu.file); setCtxMenu(null); }}>
            <Ico name="play" /> Preview in App
          </div>
          <div className="ctx-item" onClick={() => { handleOpenFile(ctxMenu.file.path); setCtxMenu(null); }}>
            <Ico name="external" /> Open in Player
          </div>
          <div className="ctx-item" onClick={() => { handleOpenFolder(ctxMenu.file.path); setCtxMenu(null); }}>
            <Ico name="folder" /> Open in Explorer
          </div>
          <div className="ctx-item danger" onClick={() => handleDeleteFile(ctxMenu.file)}>
            <Ico name="trash" /> Delete
          </div>
        </div>
      )}

      {deleteConfirm && (
        <Modal title="CONFIRM DELETE" onClose={() => setDeleteConfirm(null)}
          footer={
            <>
              <button className="btn btn-secondary btn-sm" onClick={() => setDeleteConfirm(null)}>CANCEL</button>
              <button className="btn btn-danger btn-sm" onClick={confirmDelete}>DELETE PERMANENTLY</button>
            </>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}>
            <Mascot src={MASCOT_FRUSTRATED} className="error-mascot" wrapClass="error-mascot" style={{ width: 80 }} />
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 11, color: 'var(--t2)', textAlign: 'center' }}>
              Delete <span style={{ color: 'var(--red)' }}>{deleteConfirm.name}</span>?<br />
              <span style={{ color: 'var(--t4)', fontSize: 9 }}>This cannot be undone.</span>
            </div>
          </div>
        </Modal>
      )}

      {dropModal && (
        <Modal title="DROP DETECTED" onClose={() => setDropModal(null)}
          footer={
            <>
              <button className="btn btn-secondary btn-sm" onClick={() => setDropModal(null)}>CANCEL</button>
              <button className="btn btn-secondary btn-sm" onClick={() => { setDropModal(null); handleOpenFolder(selectedFolder); }}>OPEN FOLDER</button>
            </>
          }
        >
          <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t2)', textAlign: 'center', lineHeight: 2 }}>
            Dropped: <span style={{ color: 'var(--cyan)' }}>{dropModal.name}</span><br />
            <span style={{ color: 'var(--t4)', fontSize: 9 }}>Open the folder to manage files directly.</span>
          </div>
        </Modal>
      )}

      {previewFile && <MediaPreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />}

      {/* Opened by SYNC OPTIONS; it was only mounted in the grid view, so the
          button in this view did nothing */}
      {syncModal && <SyncPlaylistModal folder={syncModal} onClose={() => setSyncModal(null)} showNotif={showNotif} onRefreshVault={onRefreshVault} isDownloading={isDownloading} onSyncStart={onSyncStart} onSyncItems={onSyncItems} />}
    </div>
  );
}
