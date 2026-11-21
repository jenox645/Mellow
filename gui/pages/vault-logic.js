// The Vault's logic: its state, effects, API calls and handlers, shared by every theme.
// useVaultPage(props) takes what the App hands the Vault and returns everything a view
// draws (the folder cards and, once one is open, its files) and every handler it calls;
// the view itself never calls the API.
'use strict';

import { API } from '../lib/api.js';
import { fmtBytes } from '../lib/util.js';
import { TAGGABLE_AUDIO } from '../lib/constants.js';
import { useFitInWindow } from '../components/common.jsx';
import { useMarquee } from '../components/marquee.jsx';
import { clickSelect } from '../lib/selection.js';

export const BYTES_PER_GB = 1024 ** 3;
const VIDEO_PREVIEW_EXTS = ['mp4', 'webm', 'mkv', 'avi', 'mov'];

export const isVideoExt = (ext) => VIDEO_PREVIEW_EXTS.includes((ext || '').toLowerCase());
// In-app preview: streams through /api/vault/stream (Range-aware, seekable)
export const mediaStreamUrl = (path) => '/api/vault/stream?path=' + encodeURIComponent(path);

export function useVaultPage(props) {
  const { vaultFolders, selectedFolder, setSelectedFolder, config, setConfig, showNotif, onRefreshVault, isDownloading } = props;
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
  const ctxMenuRef = useFitInWindow(ctxMenu);
  const cardMenuRef = useFitInWindow(cardMenuData);
  const [linkPlModal, setLinkPlModal] = React.useState(null);
  const [renameModal, setRenameModal] = React.useState(null);
  const [moveModal, setMoveModal] = React.useState(null);   // {folder, into, moving}
  const [syncModal, setSyncModal] = React.useState(null);
  const [retagOpen, setRetagOpen] = React.useState(false);
  const [retagging, setRetagging] = React.useState(false);
  const [folderStatsModal, setFolderStatsModal] = React.useState(null); // folder stats modal
  const [folderStatsData, setFolderStatsData] = React.useState(null);
  // path → thumbnail URL for the open folder; null until known, so a card
  // doesn't fetch a guessed URL first and the right one after
  const [fileThumbs, setFileThumbs] = React.useState(null);
  const [vaultScale, setVaultScale] = React.useState(() => { try { return localStorage.getItem('vault_scale') || 'md'; } catch { return 'md'; } });
  const [selectedFiles, setSelectedFiles] = React.useState(new Set());
  const [selectionMode, setSelectionMode] = React.useState(false);
  const [deleteManyConfirm, setDeleteManyConfirm] = React.useState(false);
  const selectAnchor = React.useRef(null);     // where a Shift-click range starts
  const filesBoxRef = React.useRef(null);
  const marquee = useMarquee(filesBoxRef, selectedFiles, setSelectedFiles);
  // LIST is for an open folder; the folder cards use SM there
  const gridScale = vaultScale === 'list' ? 'sm' : vaultScale;
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

  const loadFolder = React.useCallback((folder) => {
    setLoading(true);
    setFileThumbs(null);
    API.get('/api/vault/folder?path=' + encodeURIComponent(folder))
      .then(d => {
        const loaded = d.files || [];
        setFiles(loaded);
        if (!loaded.length) { setFileThumbs({}); return; }
        API.post('/api/vault/file-thumbs', { paths: loaded.map(f => f.path) })
          .then(r => setFileThumbs(r.thumbs || {}))
          .catch(() => setFileThumbs({}));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Reloaded when the folder changes on disk too: a sync (or a move) that
  // finished while it was open refreshes the vault, and its counts with it
  const openFolderMeta = vaultFolders.find(f => f.path === selectedFolder);
  const openFolderStamp = openFolderMeta ? [openFolderMeta.item_count, openFolderMeta.size_bytes, openFolderMeta.modified_at].join('|') : '';
  React.useEffect(() => {
    if (selectedFolder) loadFolder(selectedFolder);
  }, [selectedFolder, loadFolder, openFolderStamp]);

  // A selection belongs to its folder: kept, DELETE in the next folder would
  // remove files of the one before
  React.useEffect(() => {
    setSelectedFiles(new Set());
    selectAnchor.current = null;
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
  // The server links a folder to its library entry (library_id); matching on
  // the folder name here attached "My Music" to an entry called "Music"
  const libEntry = selectedFolderMeta && selectedFolderMeta.library_id
    ? libraryEntries.find(e => e.id === selectedFolderMeta.library_id)
    : null;

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
      .catch(e => {
        if (!libEntry || e.status !== 400) throw e;
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
  // A folder with linked playlists can sync before its first sync, too
  const canSync = !!(libEntry || (selectedFolderMeta && selectedFolderMeta.playlist_count > 0));
  const taggableCount = files.filter(f => TAGGABLE_AUDIO.includes((f.ext || '').toLowerCase())).length;

  // RE-TAG: album, track numbers (the linked playlist's current order) and
  // artists for the audio files already here, as a download now writes them
  const handleRetag = React.useCallback(() => {
    if (!selectedFolder) return;
    setRetagging(true);
    API.post('/api/vault/retag', { path: selectedFolder })
      .then(r => {
        setRetagOpen(false);
        const numbered = r.numbered ? `, numbered in playlist order (${r.numbered})` : '';
        showNotif('Tags Updated', `${r.tagged} file${r.tagged === 1 ? '' : 's'} tagged as the album "${r.album}"${numbered}`
          + (r.unchanged ? ` · ${r.unchanged} already right` : '') + (r.failed ? ` · ${r.failed} couldn't be written` : ''),
          r.failed ? 'warn' : 'success');
      })
      .catch(e => showNotif('Re-tag Failed', e.message, 'error'))
      .finally(() => setRetagging(false));
  }, [selectedFolder, showNotif]);

  // What the folder's last sync did; refetched when a sync finishes (lastSynced moves)
  const [syncReport, setSyncReport] = React.useState(null);
  React.useEffect(() => {
    setSyncReport(null);
    if (!selectedFolder) return;
    API.get('/api/vault/sync-report?path=' + encodeURIComponent(selectedFolder))
      .then(d => setSyncReport(d.report))
      .catch(() => {});
  }, [selectedFolder, lastSynced, vaultFolders]);

  const handleRandomize = React.useCallback(() => {
    // The folder listing holds media files only
    if (!files.length) { showNotif('No media', 'No media files in this folder', 'error'); return; }
    // Fisher–Yates: sort() with a random comparator favours some orders
    const shuffled = [...files];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    setRandomizedFiles(shuffled.slice(0, Math.min(Number(randomizerCount) || 1, shuffled.length)));
    setSelectedFiles(new Set());
    setSelectionMode(true);
  }, [files, randomizerCount, showNotif]);

  // The open folder's files as shown: searched, then sorted
  const shownFiles = React.useMemo(() => files
    .filter(f => !vaultSearch || f.name.toLowerCase().includes(vaultSearch.toLowerCase()))
    .sort((a, b) => {
      if (vaultSort === 'size') return (b.size_bytes || 0) - (a.size_bytes || 0);
      if (vaultSort === 'date') return (b.created || 0) - (a.created || 0);
      return a.name.localeCompare(b.name);
    }), [files, vaultSearch, vaultSort]);

  // Keys in an open folder, as in a file explorer: Ctrl/⌘+A selects every file
  // shown, Esc clears the selection, Delete asks to delete the selected files
  React.useEffect(() => {
    if (!selectedFolder) return undefined;
    const onKey = (e) => {
      if (e.target.closest && e.target.closest('input, textarea, select, [contenteditable]')) return;
      if (document.querySelector('.modal-box')) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a' && shownFiles.length) {
        e.preventDefault();
        setSelectedFiles(new Set(shownFiles.map(f => f.path)));
      } else if (e.key === 'Escape' && selectedFiles.size) {
        setSelectedFiles(new Set());
      } else if (e.key === 'Delete' && selectedFiles.size) {
        setDeleteManyConfirm(true);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [selectedFolder, shownFiles, selectedFiles]);

  const handlePlayAll = React.useCallback(() => {
    const paths = shownFiles.map(f => f.path);
    if (!paths.length) return;
    API.post('/api/vault/play-files', { paths })
      .then(() => showNotif('Playing', paths.length + ' files opened in player', 'success'))
      .catch(e => showNotif('Error', e.message, 'error'));
  }, [shownFiles, showNotif]);

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
    Promise.all(paths.map(p => API.del('/api/vault/file', { path: p }).then(() => p, () => null)))
      .then(results => {
        const deleted = new Set(results.filter(Boolean));
        setFiles(f => f.filter(x => !deleted.has(x.path)));
        const failed = paths.length - deleted.size;
        if (deleted.size) showNotif('Deleted', deleted.size + ' file(s)');
        if (failed) showNotif('Not Deleted', failed + ' file(s) could not be deleted (in use or read-only?)', 'error');
        setSelectedFiles(new Set());
        setSelectionMode(false);
        setDeleteManyConfirm(false);
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

  // Move a folder elsewhere (the wrong one was picked): choose where, then confirm
  const pickMoveTarget = React.useCallback((folder) => {
    setCardMenuData(null);
    const parent = folder.path.replace(/[\\/][^\\/]+[\\/]?$/, '');
    API.post('/api/browse-folder', { initial: parent })
      .then(d => { if (d.path) setMoveModal({ folder, into: d.path }); })
      .catch(() => {});
  }, []);

  const handleMove = React.useCallback(() => {
    const { folder, into } = moveModal;
    setMoveModal(m => ({ ...m, moving: true }));
    API.post('/api/vault/move', { path: folder.path, into })
      .then(d => {
        showNotif('Folder Moved', folder.name + ' → ' + d.path, 'success');
        setFolderMosaics(prev => { const next = { ...prev }; delete next[folder.path]; return next; });
        if (selectedFolder === folder.path) setSelectedFolder(d.path);
        onRefreshVault && onRefreshVault();
        refreshLibraryEntries();
        setMoveModal(null);
      })
      .catch(e => { showNotif('Not Moved', e.message, 'error'); setMoveModal(m => m && { ...m, moving: false }); });
  }, [moveModal, showNotif, selectedFolder, setSelectedFolder, onRefreshVault, refreshLibraryEntries]);


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

  // A file's thumbnail: the one the folder listing found, the server's frame grab otherwise
  const fileThumbUrl = (file) => fileThumbs[file.path] || '/api/vault/thumb?path=' + encodeURIComponent(file.path);

  // A click opens the file; with SELECT on, Ctrl/⌘ or Shift it selects instead
  // (Shift: the range from the last file clicked), like a file explorer
  const onFileClick = (e, file) => {
    if (marquee.consumeClick()) return;
    const add = e.ctrlKey || e.metaKey;
    if (!(selectionMode || add || e.shiftKey)) { handleOpenFile(file.path); return; }
    const r = clickSelect(selectedFiles, shownFiles.map(f => f.path), file.path,
      { add: add || selectionMode, shift: e.shiftKey }, selectAnchor.current);
    selectAnchor.current = r.anchor;
    setSelectedFiles(r.selected);
  };
  const showChecks = selectionMode || selectedFiles.size > 0;
  const folderName = selectedFolder ? selectedFolder.split(/[\\/]/).pop() : '';

  // SM / MD / LG / ☰ LIST, remembered in this browser
  const setScale = React.useCallback((s) => {
    setVaultScale(s);
    try { localStorage.setItem('vault_scale', s); } catch { /* storage blocked: this session only */ }
  }, []);

  const refreshAll = React.useCallback(() => {
    onRefreshVault && onRefreshVault();
    refreshLibraryEntries();
  }, [onRefreshVault, refreshLibraryEntries]);

  const syncAll = React.useCallback(() => {
    API.post('/api/vault/sync-all', {})
      .then(d => showNotif('Sync All Queued', d.count + ' folder(s) queued', 'success'))
      .catch(e => showNotif('Sync Error', e.message, 'error'));
  }, [showNotif]);

  // Stats & Budget of a folder card: the dialog opens, its numbers follow
  const openFolderStats = React.useCallback((f) => {
    setCardMenuData(null);
    setFolderStatsData(null);
    setCleanupData(null);
    setBudgetInput(budgets[f.path] ? String(budgets[f.path] / BYTES_PER_GB) : '');
    setFolderStatsModal(f);
    API.get('/api/vault/folder-stats?path=' + encodeURIComponent(f.path)).then(setFolderStatsData).catch(() => {});
  }, [budgets]);

  const generateArchive = React.useCallback((f) => {
    setCardMenuData(null);
    API.post('/api/vault/archive-generate', { path: f.path })
      .then(d => showNotif('Archive Ready', d.migrated ? 'Migrated old archive → mellow_archive.txt' : 'mellow_archive.txt ready in ' + f.name, 'success'))
      .catch(e => showNotif('Error', e.message, 'error'));
  }, [showNotif]);

  // One of the cleanup candidates (oldest files of a folder over its budget)
  const deleteCleanupCandidate = React.useCallback((f) => {
    API.del('/api/vault/file', { path: f.path })
      .then(() => { showNotif('Deleted', f.name); loadCleanupCandidates(folderStatsModal.path); onRefreshVault && onRefreshVault(); })
      .catch(e => showNotif('Error', e.message, 'error'));
  }, [showNotif, loadCleanupCandidates, folderStatsModal, onRefreshVault]);

  // A failed item of the last sync, into this folder in the format it syncs with
  const retrySyncItem = React.useCallback((url) => API.post('/api/vault/retry-item', { path: selectedFolder, url })
    .then(() => showNotif('Re-queued', url))
    .catch(e => showNotif('Error', e.message, 'error')), [selectedFolder, showNotif]);

  return {
    ...props,
    budgets,
    // the folder cards
    folderMosaics, gridScale, vaultScale, setScale, refreshAll, syncAll,
    cardMenuData, setCardMenuData, cardMenuRef,
    openFolderStats, generateArchive, handleVaultRemove, handleVaultRename, pickMoveTarget,
    handleWatchFolder, confirmWatchFolder, watchArchivePrompt, setWatchArchivePrompt,
    dragOver, handleDragOver, handleDragLeave, handleDrop, dropModal, setDropModal,
    // dialogs
    linkPlModal, setLinkPlModal, syncModal, setSyncModal, renameModal, setRenameModal, dupModal, setDupModal,
    moveModal, setMoveModal, handleMove,
    folderStatsModal, setFolderStatsModal, folderStatsData, budgetInput, setBudgetInput, handleSetBudget,
    cleanupData, loadCleanupCandidates, deleteCleanupCandidate,
    // the open folder
    folderName, selectedFolderMeta, libEntry, lastSynced, canSync, syncingId, handleSync, syncReport, retrySyncItem,
    taggableCount, retagOpen, setRetagOpen, retagging, handleRetag,
    files, shownFiles, loading, loadFolder, fileThumbs, fileThumbUrl, vaultSearch, setVaultSearch, vaultSort, setVaultSort,
    handleOpenFile, handleOpenFolder, handleDeleteFile, deleteConfirm, setDeleteConfirm, confirmDelete,
    ctxMenu, setCtxMenu, ctxMenuRef, previewFile, setPreviewFile,
    // RANDOMIZE / PLAY ALL
    randomizerCount, setRandomizerCount, randomizedFiles, setRandomizedFiles, handleRandomize, handlePlayAll,
    handlePlayRandom,
    // selecting files (click, Ctrl/⌘, Shift, the rectangle)
    filesBoxRef, marquee, onFileClick, selectedFiles, setSelectedFiles, selectionMode, setSelectionMode, showChecks,
    handlePlaySelected, deleteManyConfirm, setDeleteManyConfirm, handleDeleteSelected,
  };
}
