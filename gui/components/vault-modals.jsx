// Vault dialogs: add/link/sync/rename playlists, duplicate finder.
'use strict';

import { API } from '../lib/api.js';
import { fmtBytes } from '../lib/util.js';
import { Modal } from './common.jsx';
import { SPONSORBLOCK_HINT } from '../lib/constants.js';

export function AddVaultModal({ onClose, onSaved, showNotif }) {
  const [name, setName] = React.useState('');
  const [urls, setUrls] = React.useState(['']);
  const [folder, setFolder] = React.useState('');
  const [mediaType, setMediaType] = React.useState('video');
  const [quality, setQuality] = React.useState('1080p');
  const [container, setContainer] = React.useState('mp4');
  const [audioFmt, setAudioFmt] = React.useState('mp3');
  const [mode, setMode] = React.useState('add');
  const [embedThumb, setEmbedThumb] = React.useState(true);
  const [embedChapters, setEmbedChapters] = React.useState(true);
  const [embedMeta, setEmbedMeta] = React.useState(true);
  const [embedSubs, setEmbedSubs] = React.useState(false);
  const [sponsorblock, setSponsorblock] = React.useState(false);
  const [saving, setSaving] = React.useState(false);

  const browseFolder = () => {
    API.post('/api/browse-folder', {}).then(d => { if (d.path) setFolder(d.path); });
  };

  const handleSave = () => {
    if (!name.trim()) { showNotif('Error', 'Name is required', 'error'); return; }
    const validUrls = urls.map(u => u.trim()).filter(Boolean);
    setSaving(true);
    // Save library entry with the first URL (primary), link all URLs to vault_playlists
    API.post('/api/library', {
      name: name.trim(),
      url: validUrls[0] || '',
      extra_urls: validUrls.slice(1),
      folder: folder,
      folder_name: name.trim(),
      use_subfolder: !!folder,
      quality: mediaType === 'audio' ? 'best' : quality,
      container,
      audio_format: audioFmt,
      mode: mediaType === 'audio' ? 'AUDIO' : 'VIDEO',
      sync_mode: mode,
      embed_thumbnail: embedThumb,
      embed_chapters: embedChapters,
      embed_metadata: embedMeta,
      embed_subs: embedSubs,
      sponsorblock,
    }).then(() => onSaved())
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setSaving(false));
  };

  return (
    <Modal
      title="ADD PLAYLIST TO VAULT"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary btn-sm" onClick={onClose}>CANCEL</button>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            {saving ? 'SAVING...' : 'ADD TO VAULT'}
          </button>
        </>
      }
    >
      <div className="form-row">
        <div className="form-label">PLAYLIST NAME</div>
        <input className="form-input" value={name} onChange={e => setName(e.target.value)} placeholder="My Playlist" />
      </div>
      <div className="form-row">
        <div className="form-label">PLAYLIST URL(S)</div>
        {urls.map((u, i) => (
          <div key={i} className="input-row" style={{ marginBottom: 4 }}>
            <input className="form-input" value={u}
              onChange={e => setUrls(prev => prev.map((x, j) => j === i ? e.target.value : x))}
              placeholder="https://youtube.com/playlist?list=..." />
            {urls.length > 1 && (
              <button className="btn btn-secondary btn-sm" style={{ flexShrink: 0 }}
                onClick={() => setUrls(prev => prev.filter((_, j) => j !== i))}>✕</button>
            )}
          </div>
        ))}
        <button className="btn btn-secondary btn-sm" style={{ marginTop: 4 }}
          onClick={() => setUrls(prev => [...prev, ''])}>+ ADD URL</button>
      </div>
      <div className="form-row">
        <div className="form-label">SAVE FOLDER</div>
        <div className="input-row">
          <input className="form-input" value={folder} onChange={e => setFolder(e.target.value)} placeholder="C:\Users\..." />
          <button className="btn btn-secondary btn-sm" onClick={browseFolder}>BROWSE</button>
        </div>
      </div>
      <div className="form-row">
        <div className="form-label">MEDIA TYPE</div>
        <div className="opts-tabs" style={{ marginTop: 0 }}>
          <div className={'opts-tab' + (mediaType === 'video' ? ' active' : '')} onClick={() => setMediaType('video')}>VIDEO</div>
          <div className={'opts-tab' + (mediaType === 'audio' ? ' active' : '')} onClick={() => setMediaType('audio')}>AUDIO ONLY</div>
        </div>
      </div>
      {mediaType === 'video' ? (
        <>
          <div className="form-row">
            <div className="form-label">QUALITY</div>
            <div className="pills">
              {['best','1080p','720p','480p'].map(q => (
                <div key={q} className={'pill' + (quality === q ? ' active' : '')} onClick={() => setQuality(q)}>{q.toUpperCase()}</div>
              ))}
            </div>
          </div>
          <div className="form-row">
            <div className="form-label">CONTAINER</div>
            <div className="pills">
              {['mp4','mkv','webm'].map(c => (
                <div key={c} className={'pill' + (container === c ? ' active' : '')} onClick={() => setContainer(c)}>{c.toUpperCase()}</div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="form-row">
          <div className="form-label">FORMAT</div>
          <div className="pills">
            {['mp3','aac','flac','m4a','opus','wav'].map(f => (
              <div key={f} className={'pill' + (audioFmt === f ? ' active' : '')} onClick={() => setAudioFmt(f)}>{f.toUpperCase()}</div>
            ))}
          </div>
        </div>
      )}
      <div className="form-row">
        <div className="form-label">SYNC MODE</div>
        <div className="pills">
          <div className={'pill' + (mode === 'add' ? ' active' : '')} onClick={() => setMode('add')}>ADD ONLY</div>
          <div className={'pill' + (mode === 'mirror' ? ' active' : '')} onClick={() => setMode('mirror')}>
            MIRROR <span style={{ color: 'var(--amber)', fontSize: 8 }}> DESTRUCTIVE</span>
          </div>
        </div>
      </div>
      <div className="form-row">
        <div className="form-label">OPTIONS</div>
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
      </div>
    </Modal>
  );
}

export function LinkPlaylistModal({ folder, onClose, showNotif }) {
  const [playlists, setPlaylists] = React.useState([]);
  const [newUrl, setNewUrl] = React.useState('');
  const [saving, setSaving] = React.useState(false);
  const [importing, setImporting] = React.useState(false);

  React.useEffect(() => {
    API.get('/api/vault/playlists?path=' + encodeURIComponent(folder.path))
      .then(d => setPlaylists(d.playlists || []))
      .catch(() => {});
  }, [folder.path]);

  const handleAdd = () => {
    const u = newUrl.trim();
    if (!u) return;
    setSaving(true);
    API.post('/api/vault/playlists', { path: folder.path, url: u })
      .then(d => { setPlaylists(d.playlists || []); setNewUrl(''); })
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setSaving(false));
  };

  const handleUnlink = (url) => {
    API.del('/api/vault/playlists', { path: folder.path, url })
      .then(() => setPlaylists(pl => pl.filter(p => p !== url)))
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const handleImportFile = () => {
    setImporting(true);
    API.post('/api/browse-file', { filter: '.txt' })
      .then(d => {
        if (!d.path) { setImporting(false); return; }
        return API.post('/api/read-url-file', { path: d.path })
          .then(r => {
            const urls = r.urls || [];
            if (!urls.length) { showNotif('No URLs', 'No valid URLs found in file (format: http... or "youtube VIDEO_ID")', 'error'); setImporting(false); return; }
            const fmt = r.format === 'archive' ? 'archive' : 'URL list';
            return urls.reduce((chain, url) =>
              chain.then(() => API.post('/api/vault/playlists', { path: folder.path, url }))
            , Promise.resolve())
              .then(() => API.get('/api/vault/playlists?path=' + encodeURIComponent(folder.path)))
              .then(d2 => { setPlaylists(d2.playlists || []); showNotif('Imported', urls.length + ' URL(s) from ' + fmt, 'success'); });
          });
      })
      .catch(e => showNotif('Error', e.message || 'Import failed', 'error'))
      .finally(() => setImporting(false));
  };

  return (
    <Modal title={'LINK PLAYLIST — ' + folder.name.toUpperCase()} onClose={onClose} footer={
      <button className="btn btn-secondary btn-sm" onClick={onClose}>CLOSE</button>
    }>
      <div className="form-row">
        <div className="form-label">PLAYLIST URL</div>
        <div className="input-row">
          <input className="form-input" value={newUrl} onChange={e => setNewUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            placeholder="https://youtube.com/playlist?list=..." />
          <button className="btn btn-primary btn-sm" onClick={handleAdd} disabled={saving || !newUrl.trim()}>LINK</button>
          <button className="btn btn-secondary btn-sm" onClick={handleImportFile} disabled={importing} title="Import URLs from .txt file (one URL per line)">
            {importing ? '...' : 'FROM FILE'}
          </button>
        </div>
      </div>
      {playlists.length > 0 && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {playlists.map(pl => (
            <div key={pl} style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bg3)', padding: '6px 10px' }}>
              <span style={{ flex: 1, fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{pl}</span>
              <span style={{ cursor: 'pointer', color: 'var(--red)', fontSize: 12, flexShrink: 0 }} onClick={() => handleUnlink(pl)}>✕</span>
            </div>
          ))}
        </div>
      )}
      {playlists.length === 0 && (
        <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)', textAlign: 'center', padding: '12px 0' }}>NO PLAYLISTS LINKED YET</div>
      )}
    </Modal>
  );
}

export function SyncPlaylistModal({ folder, onClose, showNotif, onRefreshVault, isDownloading, onSyncStart, onSyncItems }) {
  const [playlists, setPlaylists] = React.useState(null);
  const [selectedPlaylists, setSelectedPlaylists] = React.useState(null);
  const [syncMode, setSyncMode] = React.useState('add');
  const [syncMediaType, setSyncMediaType] = React.useState('video');
  const [syncQuality, setSyncQuality] = React.useState('1080p');
  const [syncContainer, setSyncContainer] = React.useState('mp4');
  const [syncAudioFmt, setSyncAudioFmt] = React.useState('mp3');
  const [syncEmbedThumb, setSyncEmbedThumb] = React.useState(true);
  const [syncEmbedSubs, setSyncEmbedSubs] = React.useState(false);
  const [syncEmbedChapters, setSyncEmbedChapters] = React.useState(true);
  const [syncEmbedMeta, setSyncEmbedMeta] = React.useState(true);
  const [syncSponsorblock, setSyncSponsorblock] = React.useState(false);
  const [syncing, setSyncing] = React.useState(false);
  const [mirrorPreview, setMirrorPreview] = React.useState(null);
  const [previewing, setPreviewing] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [conflictDialog, setConflictDialog] = React.useState(false);

  // Auto-sync schedule for this folder ('inherit' follows the Config default)
  const [schedule, setSchedule] = React.useState(null);
  const [scheduleMap, setScheduleMap] = React.useState({});
  const [autoSyncEnabled, setAutoSyncEnabled] = React.useState(false);

  React.useEffect(() => {
    API.get('/api/vault/playlists?path=' + encodeURIComponent(folder.path))
      .then(d => {
        const pls = d.playlists || [];
        setPlaylists(pls);
        setSelectedPlaylists(new Set(pls));
      })
      .catch(() => { setPlaylists([]); setSelectedPlaylists(new Set()); });
    API.get('/api/config').then(c => {
      const map = c.vault_sync_schedule || {};
      setScheduleMap(map);
      setSchedule(map[folder.path] || 'default');
      setAutoSyncEnabled(c.auto_sync_enabled === true);
    }).catch(() => {});
  }, [folder.path]);

  const updateSchedule = (val) => {
    setSchedule(val);
    const next = { ...scheduleMap };
    if (val === 'default') delete next[folder.path];
    else next[folder.path] = val;
    setScheduleMap(next);
    API.post('/api/config', { vault_sync_schedule: next })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const buildFmtOpts = () => ({
    // sync_audio sent explicitly both ways — the backend otherwise falls
    // back to the library entry's saved mode
    ...(syncMediaType === 'audio'
      ? { sync_audio: true, audio_format: syncAudioFmt }
      : { sync_audio: false, quality: syncQuality, container: syncContainer }),
    embed_thumbnail: syncEmbedThumb,
    embed_subs: syncEmbedSubs,
    embed_chapters: syncEmbedChapters,
    embed_metadata: syncEmbedMeta,
    sponsorblock: syncSponsorblock,
  });

  const doSync = (fmtOpts) => {
    const activePlaylists = playlists.filter(p => !selectedPlaylists || selectedPlaylists.has(p));
    if (!activePlaylists.length) { showNotif('No Playlists', 'Select at least one playlist', 'error'); return; }
    setSyncing(true);
    API.post('/api/vault/sync', { path: folder.path, mode: syncMode, playlist_urls: activePlaylists, ...fmtOpts })
      .then(() => {
        const label = folder.name + ' — ' + activePlaylists.length + ' playlist(s)';
        showNotif('Sync Queued', label, 'success');
        onSyncStart && onSyncStart(label);
        if (onSyncItems) {
          onSyncItems(null, 0, folder.name);
          Promise.all(
            activePlaylists.map(url =>
              API.post('/api/playlist-items', { url }).then(r => r.items || []).catch(() => [])
            )
          ).then(results => {
            const allItems = results.flat();
            onSyncItems(allItems, allItems.length, folder.name + ' sync');
          });
        }
        onRefreshVault && onRefreshVault();
        onClose();
      })
      .catch(e => showNotif('Error', e.message || 'Sync failed', 'error'))
      .finally(() => setSyncing(false));
  };

  const handleSync = () => {
    const fmtOpts = buildFmtOpts();
    if (syncMode === 'mirror') {
      setPreviewing(true);
      API.post('/api/vault/mirror-preview', { path: folder.path })
        .then(d => { setMirrorPreview({ ...d, fmtOpts }); setPreviewing(false); })
        .catch(e => { showNotif('Error', e.message || 'Preview failed', 'error'); setPreviewing(false); });
      return;
    }
    if (isDownloading) {
      setConflictDialog(true);
      return;
    }
    doSync(fmtOpts);
  };

  const handleMirrorConfirm = () => {
    setConfirming(true);
    const pathsToDelete = (mirrorPreview?.to_delete || []).map(f => f.path);
    const fmtOpts = mirrorPreview?.fmtOpts || buildFmtOpts();
    const activePlaylists = playlists ? playlists.filter(p => !selectedPlaylists || selectedPlaylists.has(p)) : [];
    API.post('/api/vault/mirror-confirm', { path: folder.path, paths: pathsToDelete })
      .then(() => API.post('/api/vault/sync', { path: folder.path, mode: 'add', playlist_urls: activePlaylists.length ? activePlaylists : undefined, ...fmtOpts }))
      .then(() => {
        const label = folder.name + ' — mirror sync';
        showNotif('Mirror Done', 'Deleted ' + pathsToDelete.length + ' file(s), syncing new items', 'success');
        onSyncStart && onSyncStart(label);
        if (onSyncItems && activePlaylists.length) {
          onSyncItems(null, 0, folder.name);
          Promise.all(
            activePlaylists.map(url =>
              API.post('/api/playlist-items', { url }).then(r => r.items || []).catch(() => [])
            )
          ).then(results => {
            const allItems = results.flat();
            onSyncItems(allItems, allItems.length, folder.name + ' sync');
          });
        }
        onRefreshVault && onRefreshVault();
        onClose();
      })
      .catch(e => showNotif('Error', e.message || 'Mirror failed', 'error'))
      .finally(() => setConfirming(false));
  };

  const hasPlaylist = playlists && playlists.length > 0;

  // Mirror confirm step
  if (mirrorPreview) {
    const toDelete = mirrorPreview.to_delete || [];
    const toAddCount = mirrorPreview.to_add_count || 0;
    const unchangedCount = mirrorPreview.unchanged_count || 0;
    return (
      <Modal title={'MIRROR DIFF — ' + folder.name.toUpperCase()} onClose={onClose} footer={
        <>
          <button className="btn btn-secondary btn-sm" onClick={() => setMirrorPreview(null)}>BACK</button>
          <button className="btn btn-danger btn-sm" onClick={handleMirrorConfirm} disabled={confirming}>
            {confirming ? 'APPLYING...' : 'APPLY MIRROR'}
          </button>
        </>
      }>
        <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, padding: '6px 0', borderBottom: '1px solid var(--border)', marginBottom: 8 }}>
          {toAddCount > 0 && <div style={{ color: 'var(--cyan)' }}>+ {toAddCount} new item(s) will be downloaded</div>}
          {toDelete.length > 0 && <div style={{ color: 'var(--red)' }}>− {toDelete.length} item(s) will be deleted (not in any playlist)</div>}
          {unchangedCount > 0 && <div style={{ color: 'var(--t4)' }}>= {unchangedCount} item(s) unchanged</div>}
          {toAddCount === 0 && toDelete.length === 0 && <div style={{ color: 'var(--t3)' }}>No changes — folder matches all linked playlists.</div>}
        </div>
        {toDelete.length > 0 && (
          <div style={{ maxHeight: 180, overflow: 'auto' }}>
            {toDelete.map((f, i) => (
              <div key={i} style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--red)', padding: '2px 0', borderBottom: '1px solid var(--border)' }}>
                {f.name} <span style={{ color: 'var(--t4)' }}>({fmtBytes(f.size)})</span>
              </div>
            ))}
          </div>
        )}
      </Modal>
    );
  }

  return (
    <Modal title={'SYNC — ' + folder.name.toUpperCase()} onClose={onClose} footer={
      hasPlaylist ? (
        <>
          <button className="btn btn-secondary btn-sm" onClick={onClose}>CANCEL</button>
          <button className="btn btn-primary btn-sm" onClick={handleSync} disabled={syncing || previewing}>
            {previewing ? 'CHECKING...' : syncing ? 'SYNCING...' : syncMode === 'mirror' ? 'PREVIEW MIRROR' : 'SYNC NOW'}
          </button>
        </>
      ) : (
        <button className="btn btn-secondary btn-sm" onClick={onClose}>CLOSE</button>
      )
    }>
      {playlists === null ? (
        <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)', textAlign: 'center', padding: '12px 0' }}>LOADING...</div>
      ) : !hasPlaylist ? (
        <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t3)', textAlign: 'center', padding: '12px 0' }}>
          No playlist linked. Use ⋮ → Link Playlist first.
        </div>
      ) : (
        <>
          <div className="form-row">
            <div className="form-label">LINKED PLAYLISTS ({playlists.length})</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '4px 0' }}>
              {playlists.map((pl, i) => {
                const checked = !selectedPlaylists || selectedPlaylists.has(pl);
                return (
                  <label key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input type="checkbox" checked={checked} onChange={e => {
                      setSelectedPlaylists(prev => {
                        const next = new Set(prev);
                        e.target.checked ? next.add(pl) : next.delete(pl);
                        return next;
                      });
                    }} />
                    <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: checked ? 'var(--cyan)' : 'var(--t4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{pl}</span>
                  </label>
                );
              })}
            </div>
          </div>
          <div className="form-row">
            <div className="form-label">MEDIA TYPE</div>
            <div className="opts-tabs" style={{ marginTop: 0 }}>
              <div className={'opts-tab' + (syncMediaType === 'video' ? ' active' : '')} onClick={() => setSyncMediaType('video')}>VIDEO</div>
              <div className={'opts-tab' + (syncMediaType === 'audio' ? ' active' : '')} onClick={() => setSyncMediaType('audio')}>AUDIO ONLY</div>
            </div>
          </div>
          {syncMediaType === 'video' ? (
            <>
              <div className="form-row">
                <div className="form-label">QUALITY</div>
                <div className="pills">
                  {['best','1080p','720p','480p'].map(q => (
                    <div key={q} className={'pill' + (syncQuality === q ? ' active' : '')} onClick={() => setSyncQuality(q)}>{q.toUpperCase()}</div>
                  ))}
                </div>
              </div>
              <div className="form-row">
                <div className="form-label">CONTAINER</div>
                <div className="pills">
                  {['mp4','mkv','webm'].map(c => (
                    <div key={c} className={'pill' + (syncContainer === c ? ' active' : '')} onClick={() => setSyncContainer(c)}>{c.toUpperCase()}</div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="form-row">
              <div className="form-label">FORMAT</div>
              <div className="pills">
                {['mp3','aac','flac','m4a','opus','wav'].map(f => (
                  <div key={f} className={'pill' + (syncAudioFmt === f ? ' active' : '')} onClick={() => setSyncAudioFmt(f)}>{f.toUpperCase()}</div>
                ))}
              </div>
            </div>
          )}
          <div className="form-row">
            <div className="form-label">SYNC MODE</div>
            <div className="pills">
              <div className={'pill' + (syncMode === 'add' ? ' active' : '')} onClick={() => setSyncMode('add')}>ADD ONLY</div>
              <div className={'pill' + (syncMode === 'mirror' ? ' active' : '')} onClick={() => setSyncMode('mirror')}>
                MIRROR <span style={{ color: 'var(--amber)', fontSize: 8 }}> DESTRUCTIVE</span>
              </div>
            </div>
          </div>
          <div className="form-row">
            <div className="form-label">AUTO-SYNC SCHEDULE</div>
            <div className="pills">
              {[['default', 'DEFAULT'], ['off', 'OFF'], ['6h', 'EVERY 6H'], ['daily', 'DAILY'], ['weekly', 'WEEKLY']].map(([val, label]) => (
                <div key={val} className={'pill' + (schedule === val ? ' active' : '')} onClick={() => updateSchedule(val)}>{label}</div>
              ))}
            </div>
            {!autoSyncEnabled && schedule !== null && (
              <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 8, color: 'var(--amber)', marginTop: 4 }}>
                Auto-sync is OFF globally — enable it in CONFIG → BEHAVIOR for schedules to run.
              </div>
            )}
          </div>
          <div className="form-row">
            <div className="form-label">OPTIONS</div>
            <div className="opts-toggles">
              {[
                { label: 'Embed Thumbnail', val: syncEmbedThumb, set: setSyncEmbedThumb },
                { label: 'Subtitles', val: syncEmbedSubs, set: setSyncEmbedSubs },
                { label: 'Chapters', val: syncEmbedChapters, set: setSyncEmbedChapters },
                { label: 'Metadata', val: syncEmbedMeta, set: setSyncEmbedMeta },
                { label: 'SponsorBlock', val: syncSponsorblock, set: setSyncSponsorblock, hint: SPONSORBLOCK_HINT },
              ].map(item => (
                <label key={item.label} className="opts-toggle-item" title={item.hint}>
                  <input type="checkbox" checked={item.val} onChange={e => item.set(e.target.checked)} />
                  {item.label}
                </label>
              ))}
            </div>
          </div>
        </>
      )}
      {conflictDialog && (
        <div style={{ marginTop: 12, padding: '10px 12px', background: 'var(--bg3)', border: '1px solid var(--amber)', borderRadius: 4 }}>
          <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--amber)', marginBottom: 8 }}>
            ⚠ A download is in progress. Sync will be queued after it completes.
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary btn-sm" onClick={() => { setConflictDialog(false); doSync(buildFmtOpts()); }}>
              QUEUE SYNC
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => setConflictDialog(false)}>
              CANCEL
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

export function DuplicatesModal({ onClose, showNotif, onRefreshVault }) {
  const [data, setData] = React.useState(null);
  const [deleting, setDeleting] = React.useState(false);

  const load = React.useCallback(() => {
    setData(null);
    API.get('/api/vault/duplicates')
      .then(setData)
      .catch(e => { showNotif('Error', e.message, 'error'); setData({ groups: [] }); });
  }, [showNotif]);

  React.useEffect(() => { load(); }, [load]);

  // Each group is sorted largest-first by the server; keep the largest copy
  const deleteSmaller = (groups) => {
    const targets = groups.flatMap(g => g.copies.slice(1));
    if (!targets.length) return;
    setDeleting(true);
    Promise.all(targets.map(c => API.del('/api/vault/file', { path: c.path }).catch(() => null)))
      .then(() => {
        showNotif('Deduplicated', targets.length + ' smaller cop' + (targets.length === 1 ? 'y' : 'ies') + ' deleted', 'success');
        onRefreshVault && onRefreshVault();
        load();
      })
      .finally(() => setDeleting(false));
  };

  const groups = (data && data.groups) || [];

  return (
    <Modal title="DUPLICATE FINDER" onClose={onClose} footer={
      <>
        <button className="btn btn-secondary btn-sm" onClick={onClose}>CLOSE</button>
        {groups.length > 0 && (
          <button className="btn btn-danger btn-sm" disabled={deleting} onClick={() => deleteSmaller(groups)}>
            {deleting ? 'DELETING...' : 'DELETE ALL SMALLER COPIES (' + fmtBytes(data.total_wasted_bytes) + ')'}
          </button>
        )}
      </>
    }>
      {data === null ? (
        <div style={{ padding: 24, textAlign: 'center', fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t3)' }}>
          SCANNING VAULT FOLDERS...
        </div>
      ) : groups.length === 0 ? (
        <div style={{ padding: 24, textAlign: 'center', fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t3)' }}>
          NO DUPLICATES FOUND — every [videoID] appears only once.
        </div>
      ) : (
        <div style={{ maxHeight: 320, overflow: 'auto' }}>
          <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--amber)', marginBottom: 8 }}>
            {groups.length} duplicated video(s) · {fmtBytes(data.total_wasted_bytes)} reclaimable
          </div>
          {groups.map(g => (
            <div key={g.video_id} style={{ marginBottom: 10, borderBottom: '1px solid var(--border)', paddingBottom: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--cyan)' }}>[{g.video_id}]</span>
                <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 8, color: 'var(--t4)' }}>{g.copies.length} copies · {fmtBytes(g.wasted_bytes)} wasted</span>
                <button className="btn btn-danger btn-sm" style={{ marginLeft: 'auto', padding: '2px 6px', fontSize: 8 }} disabled={deleting}
                  onClick={() => deleteSmaller([g])}>DELETE SMALLER</button>
              </div>
              {g.copies.map((c, i) => (
                <div key={c.path} style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 8, color: i === 0 ? 'var(--green)' : 'var(--t3)', padding: '2px 0 0 12px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.path}>
                  {i === 0 ? '✓ KEEP ' : '✕ DEL  '}{c.name} · {fmtBytes(c.size)} · {c.folder}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

export function RenameVaultModal({ folder, initialName, onClose, onSave }) {
  const [name, setName] = React.useState(initialName || '');
  return (
    <Modal title={'RENAME — ' + (folder.name || '').toUpperCase()} onClose={onClose} footer={
      <>
        <button className="btn btn-secondary btn-sm" onClick={onClose}>CANCEL</button>
        <button className="btn btn-primary btn-sm" onClick={() => { if (name.trim()) onSave(name.trim()); }}>SAVE</button>
      </>
    }>
      <div className="form-row">
        <div className="form-label">DISPLAY NAME</div>
        <input className="form-input" value={name} onChange={e => setName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && name.trim() && onSave(name.trim())}
          autoFocus />
      </div>
    </Modal>
  );
}
