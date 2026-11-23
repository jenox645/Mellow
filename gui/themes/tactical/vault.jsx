// Tactical's Vault: the STORAGE INDEX. The folders are numbered bays in an index that stays on the left
// (each with its share of the vault as a segment bar and a sync lamp); the right side is the vault's
// allocation until a bay is opened, then that bay's record: big name, readouts, its actions as a word
// menu, the sync report, and its files as a ruled table (☰ LIST) or framed covers (SM / MD / LG).
// It draws what useVaultPage returns (gui/pages/vault-logic.js); the dialogs are Classic's own
// (VaultRootDialogs / VaultFolderDialogs), so every action works the same.
'use strict';

import { fmtBytes, fmtDate, fmtWait, timeAgo } from '../../lib/util.js';
import { isVideoExt } from '../../pages/vault-logic.js';
import { SyncReport, VaultFolderDialogs, VaultRootDialogs } from '../../pages/vault.jsx';
import { Ico } from '../../components/icons.jsx';
import { Brackets, Caption, Hatch, LabelBlock, Node, Reg, SegBar } from './ornaments.jsx';
import { PageHead } from './feed.jsx';

const CARD_MIN = { sm: '130px', md: '175px', lg: '240px' };
const pad2 = n => String(n).padStart(2, '0');

function lampOf(folder) {
  if (folder.sync_failures > 0) return ['err', folder.sync_failures > 1 ? folder.sync_failures + ' FAILED' : 'FAILED'];
  if (folder.last_synced) return ['ok', 'SYNCED ' + timeAgo(folder.last_synced).toUpperCase().replace(' AGO', '')];
  if (folder.playlist_count > 0 || folder.library_id) return ['link', 'LINKED'];
  if (folder.watched) return ['', 'WATCHED'];
  return ['', 'LOCAL'];
}

export function TacticalVaultView(v) {
  const {
    vaultFolders, selectedFolder, setSelectedFolder, onAddVault, budgets, refreshAll, syncAll, cardMenuData,
    setCardMenuData, handleWatchFolder, dragOver, handleDragOver, handleDragLeave, handleDrop, setSyncModal,
    setDupModal, isDownloading,
  } = v;
  const total = vaultFolders.reduce((s, f) => s + (f.size_bytes || 0), 0);
  const files = vaultFolders.reduce((s, f) => s + (f.item_count || 0), 0);
  const largest = Math.max(1, ...vaultFolders.map(f => f.size_bytes || 0));
  const [totNum, totUnit] = fmtBytes(total).split(' ');
  const open = !!selectedFolder;

  return (
    <div className={'content active' + (dragOver ? ' drag-over' : '')}
      onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>
      <div className="tx-page">
        <PageHead num="03" kicker="SECTION 03 // MEDIA" title="STORAGE" jp="保管庫">
          <button type="button" className="tx-btn go" data-tour="vault-add" onClick={onAddVault}>+ Add playlist</button>
        </PageHead>

        <div className={'tv' + (dragOver ? ' drag-over' : '')}>
          {/* A — the index of bays */}
          <div className="tx-block tv-index">
            <div className="tv-index-head">
              <Caption num="A" title="Index" jp="索引"><span className="tx-micro">{pad2(vaultFolders.length)} BAYS</span></Caption>
              <div className="tv-total">
                <span className="tv-total-num">{totNum}<small>{totUnit}</small></span>
                <span className="tx-micro">ACROSS {files.toLocaleString()} FILES</span>
              </div>
              <div className="tv-share" aria-hidden="true">
                {vaultFolders.map((f, i) => (
                  <i key={f.path} className={f.path === selectedFolder ? 'on' : ''}
                    style={{ flex: Math.max((f.size_bytes || 0) / Math.max(total, 1), 0.012), '--i': i }} />
                ))}
              </div>
              <div className="tx-menu">
                <button type="button" onClick={refreshAll} title="Read every folder again">Refresh</button>
                <button type="button" data-tour="vault-sync-all" onClick={syncAll} disabled={isDownloading}
                  title="Sync every folder linked to a playlist">↻ Sync all</button>
                <button type="button" data-tour="vault-dupes" onClick={() => setDupModal(true)} title="Find duplicate files across folders">Dupes</button>
                <button type="button" data-tour="vault-watch" onClick={handleWatchFolder} title="Watch a folder of your own: it shows here like the others">+ Watch</button>
              </div>
            </div>

            {vaultFolders.length === 0 ? (
              <div className="tv-empty" data-tour="vault-folders">
                <div className="tf-sleep" role="img" aria-label="Mellow, asleep: the vault is empty" />
                <span>VAULT EMPTY</span>
                <button type="button" className="tx-btn" onClick={onAddVault}>Add a playlist or watch a folder</button>
              </div>
            ) : (
              <div className="tv-bays" data-tour="vault-folders" role="list">
                {vaultFolders.map((folder, i) => {
                  const [lamp, lampText] = lampOf(folder);
                  const over = budgets[folder.path] && folder.size_bytes > budgets[folder.path];
                  const on = folder.path === selectedFolder;
                  return (
                    <div key={folder.path} role="listitem" className={'tv-bay' + (on ? ' on' : '')} style={{ '--i': i }}
                      data-folder-name={folder.name} title={folder.path}
                      onClick={() => setSelectedFolder(folder.path)}>
                      <LabelBlock value={pad2(i + 1)} />
                      <div className="tv-bay-name">{folder.name}</div>
                      <div className="tv-bay-meta">
                        <span>{folder.item_count || 0} MEDIA · {fmtBytes(folder.size_bytes)}{budgets[folder.path] ? ' / ' + fmtBytes(budgets[folder.path]) : ''}</span>
                        <SegBar value={(folder.size_bytes || 0) / largest} segments={12} className={on ? 'hot' : over ? 'err' : ''} />
                      </div>
                      <div className="tv-bay-side">
                        <span className={'tv-lamp ' + lamp}
                          title={folder.sync_failures > 0 && folder.sync_retry_in > 0 ? 'Retry in ' + fmtWait(folder.sync_retry_in) : undefined}>
                          <i aria-hidden="true" />{over ? 'OVER BUDGET' : lampText}
                        </span>
                        <span className="tv-bay-tools">
                          {(folder.playlist_count > 0 || folder.library_id) && (
                            <button type="button" title="Sync" aria-label={'Sync ' + folder.name}
                              onClick={e => { e.stopPropagation(); setSyncModal(folder); }}>↻</button>
                          )}
                          {!open && (
                            <button type="button" data-tour={i === 0 ? 'vault-card-menu' : undefined} title="Folder menu"
                              aria-label={'Menu for ' + folder.name}
                              onClick={e => {
                                e.stopPropagation();
                                if (cardMenuData && cardMenuData.folder.path === folder.path) { setCardMenuData(null); return; }
                                const rect = e.currentTarget.getBoundingClientRect();
                                setCardMenuData({ folder, top: rect.bottom + 4, right: window.innerWidth - rect.right });
                              }}>⋮</button>
                          )}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="tv-detail">
            {open ? <FolderRecord v={v} /> : (
              <Allocation folders={vaultFolders} total={total} onOpen={setSelectedFolder} />
            )}
          </div>
        </div>
      </div>

      {open ? <VaultFolderDialogs {...v} /> : <VaultRootDialogs {...v} />}
    </div>
  );
}

// The vault before a bay is opened: where the space goes, biggest first
function Allocation({ folders, total, onOpen }) {
  const rows = folders.map((f, i) => ({ f, n: i + 1 })).sort((a, b) => (b.f.size_bytes || 0) - (a.f.size_bytes || 0));
  return (
    <div className="tx-block tv-overview tx-bracketed">
      <Brackets />
      <div style={{ gridColumn: '1 / -1' }}><Caption num="B" title="Allocation" jp="配分" /></div>
      <div className="tv-legend" style={{ gridColumn: '1 / -1' }}>
        {rows.length === 0 && <div className="tv-hint"><Reg />NOTHING STORED YET</div>}
        {rows.map(({ f, n }) => {
          const share = (f.size_bytes || 0) / Math.max(total, 1);
          return (
            <div key={f.path} className="tv-legend-row" onClick={() => onOpen(f.path)} title={'Open ' + f.name}>
              <span>{pad2(n)}</span>
              <span className="nm">{f.name}</span>
              <span className="r">{fmtBytes(f.size_bytes)}</span>
              <span className="r">{(share * 100).toFixed(share < 0.1 ? 1 : 0)}%</span>
              <span style={{ gridColumn: '2 / -1' }}><SegBar value={share} segments={60} /></span>
            </div>
          );
        })}
      </div>
      <div className="tv-hint" style={{ gridColumn: '1 / -1' }}><Node kind="triangle" />SELECT A BAY TO OPEN ITS RECORD</div>
    </div>
  );
}

// One bay opened: its record and its files
function FolderRecord({ v }) {
  const {
    vaultFolders, selectedFolder, setSelectedFolder, folderName, selectedFolderMeta, libEntry, lastSynced, canSync,
    syncingId, handleSync, syncReport, retrySyncItem, taggableCount, setRetagOpen, loadFolder, handleOpenFolder,
    pickMoveTarget, setSyncModal, vaultScale, setScale, files, shownFiles, loading, fileThumbs, fileThumbUrl,
    vaultSearch, setVaultSearch, vaultSort, setVaultSort, randomizerCount, setRandomizerCount, randomizedFiles,
    setRandomizedFiles, handleRandomize, handlePlayAll, handlePlayRandom, filesBoxRef, marquee, onFileClick,
    selectedFiles, setSelectedFiles, selectionMode, setSelectionMode, showChecks, handlePlaySelected,
    setDeleteManyConfirm, setCtxMenu,
  } = v;
  const bay = Math.max(0, vaultFolders.findIndex(f => f.path === selectedFolder)) + 1;
  const size = selectedFolderMeta ? fmtBytes(selectedFolderMeta.size_bytes).split(' ') : ['—', ''];
  const picks = randomizedFiles ? new Set([...randomizedFiles.map(f => f.path), ...selectedFiles]).size : 0;
  const report = syncReport;
  const failed = report && report.failed ? (Array.isArray(report.failed) ? report.failed.length : report.failed) : 0;

  const marks = (file) => {
    const picked = selectedFiles.has(file.path);
    const rand = randomizedFiles && randomizedFiles.some(f => f.path === file.path);
    return (rand && !picked ? ' rand-selected' : '') + (picked ? ' file-selected' : '');
  };
  const menu = (file) => (
    <div className="lib-menu" title="File menu" onClick={(e) => {
      e.stopPropagation();
      const rect = e.currentTarget.getBoundingClientRect();
      setCtxMenu({ file, x: rect.right, y: rect.bottom });
    }}><Ico name="dots" /></div>
  );
  const thumb = (file, framed) => (
    <span className="tv-thumb">
      {isVideoExt(file.ext) ? '▶' : '♫'}
      {fileThumbs && <img src={fileThumbUrl(file)} loading="lazy" decoding="async" draggable={false} alt=""
        onError={e => { e.target.style.display = 'none'; }} onLoad={e => { e.target.style.display = ''; }} />}
      {framed && <Brackets size={7} inset={3} />}
      {showChecks && <span className={'tv-check' + (selectedFiles.has(file.path) ? ' on' : '')}>{selectedFiles.has(file.path) && '✓'}</span>}
    </span>
  );

  return (
    <>
      <div className="tx-block tv-folder-head tx-bracketed">
        <Brackets />
        <div className="tv-crumb" data-tour="vault-back">
          <button type="button" onClick={() => setSelectedFolder(null)}>◂ INDEX</button>
          <span title={selectedFolder}>{selectedFolder}</span>
          {libEntry && <span className="tx-micro" style={{ marginLeft: 'auto', flexShrink: 0 }}>PLAYLIST · {libEntry.name}</span>}
        </div>
        <div className="tv-fname">
          <LabelBlock value={pad2(bay)} caption="BAY" />
          <h2 title={folderName}>{folderName}</h2>
        </div>
        <div className="tv-readouts" data-tour="vault-report">
          <LabelBlock className="dark" value={files.length} caption="MEDIA" />
          <LabelBlock className="dark" value={size[0]} caption={size[1] || 'SIZE'} />
          <LabelBlock className="dark" value={lastSynced ? timeAgo(lastSynced).replace(' ago', '').toUpperCase() : '—'}
            caption={lastSynced ? 'LAST SYNC' : (libEntry || canSync) ? 'NEVER SYNCED' : 'NOT LINKED'} />
          {failed > 0 && <Hatch>{failed} FAILED LAST SYNC</Hatch>}
        </div>
        {report && <div className="tv-report"><SyncReport report={report} onRetry={retrySyncItem} /></div>}
        <div className="tv-actions">
          {canSync && (
            <button type="button" className="tx-btn amber" data-tour="vault-sync" onClick={handleSync} disabled={!!syncingId}>
              {syncingId ? 'Syncing…' : '↻ Sync now'}
            </button>
          )}
          <div className="tx-menu">
            {canSync && selectedFolderMeta && (
              <button type="button" data-tour="vault-sync-options" title="Sync options / selective playlist sync"
                onClick={() => setSyncModal(selectedFolderMeta)}>Sync options</button>
            )}
            {taggableCount > 0 && (
              <button type="button" data-tour="vault-retag" onClick={() => setRetagOpen(true)}
                title="Album, track numbers and artists for the songs in this folder">♪ Re-tag</button>
            )}
            <button type="button" onClick={() => loadFolder(selectedFolder)}>Refresh</button>
            <button type="button" data-tour="vault-open" onClick={() => handleOpenFolder(selectedFolder)}>Open in explorer</button>
            <button type="button" data-tour="vault-move" title="Move this folder somewhere else; its playlists, sync settings and history follow"
              onClick={() => pickMoveTarget(selectedFolderMeta || { path: selectedFolder, name: folderName })}>⇄ Move</button>
          </div>
          <div className="tx-segsel" data-tour="vault-view" role="radiogroup" aria-label="How files are shown">
            {['list', 'sm', 'md', 'lg'].map(s => (
              <button key={s} type="button" role="radio" aria-checked={vaultScale === s} className={vaultScale === s ? 'on' : ''}
                title={s === 'list' ? 'One line per file: name, type, size, date' : 'Covers, ' + { sm: 'small', md: 'medium', lg: 'large' }[s]}
                onClick={() => setScale(s)}>{s === 'list' ? '☰ LIST' : s.toUpperCase()}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="tx-block">
        <div ref={filesBoxRef} className="vault-files-area" onMouseDown={marquee.onMouseDown}>
          {!loading && files.length > 0 && (
            <>
              <div className="tv-tools" data-tour="vault-tools">
                <label className="tv-search">
                  <span className="tx-micro">FIND</span>
                  <input placeholder="title, in this folder — ライブラリを検索" value={vaultSearch} onChange={e => setVaultSearch(e.target.value)} />
                </label>
                <select className="tv-sort" value={vaultSort} onChange={e => setVaultSort(e.target.value)} aria-label="Sort by">
                  <option value="name">SORT · NAME</option>
                  <option value="size">SORT · SIZE</option>
                  <option value="date">SORT · DATE</option>
                </select>
                <span className="tv-randgrp" data-tour="vault-random">
                  <span className="tx-micro">RANDOM</span>
                  <span className="tv-rand">
                    <button type="button" aria-label="One fewer" onClick={() => setRandomizerCount(c => Math.max(1, (Number(c) || 1) - 1))}>−</button>
                    <input type="number" inputMode="numeric" min={1} max={Math.max(1, files.length)} aria-label="How many files to pick"
                      value={randomizerCount} onFocus={e => e.target.select()}
                      onChange={e => setRandomizerCount(e.target.value === '' ? ''
                        : Math.max(1, Math.min(Math.max(1, files.length), parseInt(e.target.value, 10) || 1)))}
                      onBlur={() => setRandomizerCount(c => Number(c) || 1)}
                      onKeyDown={e => { if (e.key === 'Enter') handleRandomize(); }} />
                    <button type="button" aria-label="One more" onClick={() => setRandomizerCount(c => Math.min(files.length || 99, (Number(c) || 0) + 1))}>+</button>
                  </span>
                  <button type="button" className="tx-btn" onClick={handleRandomize}>Pick</button>
                </span>
                <button type="button" className="tx-btn go" data-tour="vault-play-all" onClick={handlePlayAll}
                  disabled={!shownFiles.length} title="Play every file shown here, in this order">▶ Play all {shownFiles.length}</button>
                <button type="button" className={'tx-btn' + (selectionMode ? ' on' : '')} data-tour="vault-select"
                  onClick={() => { setSelectionMode(s => !s); setSelectedFiles(new Set()); }}>
                  {selectionMode ? 'Exit select' : 'Select'}
                </button>
              </div>
              <div className="tv-sel">
                {randomizedFiles ? (
                  <>
                    <b>{picks} PICKED</b>
                    <button type="button" className="tx-btn go" onClick={handlePlayRandom}>▶ Play {picks}</button>
                    <button type="button" className="tx-btn" onClick={() => { setRandomizedFiles(null); setSelectedFiles(new Set()); setSelectionMode(false); }}>✕ Clear</button>
                  </>
                ) : selectedFiles.size > 0 ? (
                  <>
                    <b>{selectedFiles.size} SELECTED</b>
                    <div className="tx-menu">
                      <button type="button" onClick={() => setSelectedFiles(new Set(shownFiles.map(f => f.path)))}>All</button>
                      <button type="button" onClick={() => setSelectedFiles(new Set())}>None</button>
                    </div>
                    <button type="button" className="tx-btn go" onClick={handlePlaySelected}>▶ Play {selectedFiles.size}</button>
                    <button type="button" className="tx-btn danger" onClick={() => setDeleteManyConfirm(true)}>Delete {selectedFiles.size}</button>
                  </>
                ) : (
                  <span>{shownFiles.length} OF {files.length} SHOWN · drag over files · Ctrl+click · Shift+click a range</span>
                )}
              </div>
            </>
          )}

          {loading ? (
            <div className="tv-empty"><Reg size={13} />READING THE FOLDER…</div>
          ) : files.length === 0 ? (
            <div className="tv-empty">
              <div className="tf-sleep" role="img" aria-label="Mellow, asleep: no media in this folder" />
              <span>NO MEDIA HERE</span>
              <span style={{ color: 'var(--t4)' }}>DOWNLOAD SOMETHING TO THIS FOLDER</span>
            </div>
          ) : (
            <div className="tv-files vault-files" data-tour="vault-files">
              {vaultScale === 'list' ? (
                <div className="tv-table" role="list">
                  {shownFiles.map((file, i) => (
                    <div key={file.path} role="listitem" data-select-key={file.path} style={{ '--i': i }}
                      className={'tv-row' + marks(file)} onClick={e => onFileClick(e, file)}>
                      <span className="n">{pad2(i + 1)}</span>
                      {thumb(file, false)}
                      <span className="nm" title={file.name}>{file.name.replace(/\.[^.]+$/, '')}</span>
                      <span className={'x ' + (isVideoExt(file.ext) ? 'v' : 'a')}>{file.ext.toUpperCase()}</span>
                      <span className="sz">{fmtBytes(file.size_bytes)}</span>
                      <span className="dt">{file.created ? fmtDate(file.created * 1000) : ''}</span>
                      {menu(file)}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="tv-grid" style={{ '--tv-card-min': CARD_MIN[vaultScale] || CARD_MIN.md }}>
                  {shownFiles.map((file, i) => (
                    <div key={file.path} data-select-key={file.path} style={{ '--i': i }}
                      className={'tv-card tx-bracketed' + marks(file)} onClick={e => onFileClick(e, file)}>
                      {thumb(file, true)}
                      <span className="tv-fmt">{file.ext.toUpperCase()}</span>
                      <div className="tv-card-body">
                        <span className="nm" title={file.name}>{file.name.replace(/\.[^.]+$/, '')}</span>
                        <span className="m">{fmtBytes(file.size_bytes)}</span>
                        <span className="m">{file.created ? fmtDate(file.created * 1000) : ''}</span>
                      </div>
                      {menu(file)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {marquee.overlay}
        </div>
      </div>
    </>
  );
}
