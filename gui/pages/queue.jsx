// QUEUE page — server job queue, active download, playlist tabs.
'use strict';

import { API, cancelShownDownload } from '../lib/api.js';
import { fmtBytes, fmtSpeed, fmtEta, fmtDuration, timeAgo } from '../lib/util.js';
import { Ico } from '../components/icons.jsx';
import { Mascot, PageHead } from '../components/common.jsx';
import { MASCOT_TIRED } from '../lib/mascots.js';
import { QUEUE_POLL_MS } from '../lib/constants.js';

export function QueuePage({ dlState, showNotif, activeJobs, playlistItems, setPlaylistItems, completedItems, failedItems, playlistTotalCount, playlistCompletedCount, isPaused, pausedCount, failedCount, syncJobLabel, fetchingPlaylistItems, onPause, onResume, onClearCompleted, onClearFailed }) {
  const isDownloading = dlState && dlState.pct !== undefined;
  const queueCount = playlistItems ? playlistItems.length : 0;
  const [qTab, setQTab] = React.useState('pending');
  const [removingItems, setRemovingItems] = React.useState(new Set());
  const [jobs, setJobs] = React.useState([]);

  const loadJobs = React.useCallback(() => {
    API.get('/api/queue/status').then(d => setJobs(d.jobs || [])).catch(() => {});
  }, []);

  // The backend job queue (queued vault syncs, second URLs) — distinct from
  // the playlist items of the active job shown below
  React.useEffect(() => {
    loadJobs();
    const iv = setInterval(loadJobs, QUEUE_POLL_MS);
    return () => clearInterval(iv);
  }, [loadJobs]);

  const handleCancel = () => {
    cancelShownDownload(dlState).catch(e => showNotif('Error', e.message, 'error'));
  };

  const handleCancelJob = (job) => {
    API.del('/api/queue/' + job.id)
      .then(() => {
        showNotif(job.status === 'active' ? 'Cancelling' : 'Removed', job.label || job.url);
        setJobs(js => js.map(j => j.id === job.id ? { ...j, status: 'cancelled' } : j));
      })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  // Same options and folder as the job it failed in (a plain /api/download
  // used the Feed defaults: an MP3 playlist's item came back as video)
  const retryItem = (item) => (item.jobId
    ? API.post('/api/queue/' + encodeURIComponent(item.jobId) + '/retry', { url: item.url })
      .catch(e => { if (e.status === 404) return API.post('/api/download', { url: item.url }); throw e; })
    : API.post('/api/download', { url: item.url }));

  const handleRetryFailed = (item) => {
    if (!item.url) return;
    retryItem(item)
      .then(() => showNotif('Re-queued', item.url))
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const handleRetryAll = () => {
    const items = (failedItems || []).filter(i => i.url);
    const seen = new Set();
    const unique = items.filter(i => !seen.has(i.url) && seen.add(i.url));
    Promise.all(unique.map(i => retryItem(i).then(() => true, () => false)))
      .then(results => {
        const ok = results.filter(Boolean).length;
        showNotif('Re-queued', ok + ' of ' + unique.length + ' failed item(s)', ok === unique.length ? 'success' : 'warn');
      });
  };

  const handleReorder = (job, delta) => {
    const target = (job.queue_position || 0) + delta;
    if (target < 0) return;
    API.post('/api/queue/' + job.id + '/reorder', { index: target })
      .then(loadJobs)
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const JOB_BADGE = { queued: 'queued', active: 'downloading', complete: 'completed', failed: 'failed', cancelled: 'queued' };
  const JOB_COLOR = { queued: 'var(--cyan)', active: 'var(--amber)', complete: 'var(--green)', failed: 'var(--red)', cancelled: 'var(--t4)' };
  const queuedJobsCount = jobs.filter(j => j.status === 'queued').length;

  const handleRemove = (idx) => {
    setRemovingItems(prev => new Set([...prev, idx]));
    // Actual removal from state happens in onAnimationEnd
  };

  return (
    <div className="content active">
      <PageHead
        label="キュー / DOWNLOAD QUEUE"
        title={<>QUEUE <span className="c">CONTROL</span></>}
        name="Queue"
        sub="What's downloading, waiting, finished or failed"
        actions={<>
          {playlistItems && playlistItems.length > 0 && (
            <button className="btn btn-danger btn-sm" onClick={() => setPlaylistItems && setPlaylistItems(null)}>
              CLEAR QUEUE
            </button>
          )}
        </>}
      />

      <div className="g4" style={{ marginBottom: 16 }}>
        <div className="stat"><div className="stat-label">ACTIVE</div><div className="stat-value amber">{isDownloading ? 1 : 0}</div></div>
        <div className="stat"><div className="stat-label">QUEUED</div><div className="stat-value cyan">{queueCount}</div></div>
        <div className="stat"><div className="stat-label">PAUSED</div><div className="stat-value" style={{ color: 'var(--amber)' }}>{pausedCount || 0}</div></div>
        <div className="stat"><div className="stat-label">FAILED</div><div className="stat-value red">{failedCount || 0}</div></div>
      </div>

      {/* BACKEND JOB QUEUE — queued syncs / extra URLs invisible until now */}
      {jobs.length > 0 && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="panel-hud" /><div className="panel-hud-br" />
          <div className="ph">
            <span className="ptag amber">JOBS</span>
            <span className="ptitle">SERVER JOB QUEUE</span>
            <span className="psub">{jobs.filter(j => j.status === 'queued').length} QUEUED · {jobs.filter(j => j.status === 'active').length} ACTIVE</span>
          </div>
          {jobs.map(job => {
            const live = activeJobs && activeJobs[job.id];
            return (
              <div key={job.id} className="q-item" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 14px', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-8)', color: 'var(--t4)', minWidth: 36 }}>{(job.type || 'feed').toUpperCase()}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-10)', color: 'var(--t2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {job.label || job.url}
                  </div>
                  {/* Live per-job progress — visible when downloads run concurrently */}
                  {job.status === 'active' && live && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 3 }}>
                      <div className="prog-bar" style={{ height: 3, flex: 1 }}>
                        <div className="prog-bar-fill" style={{ width: (live.pct || 0) + '%' }} />
                      </div>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-8)', color: 'var(--cyan)', flexShrink: 0 }}>
                        {(live.pct || 0).toFixed(0)}% · {fmtSpeed(live.speed)}
                      </span>
                    </div>
                  )}
                </div>
                {job.error && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-8)', color: 'var(--red)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={job.error}>{job.error}</span>}
                {job.status === 'queued' && job.not_before && job.not_before * 1000 > Date.now() ? (
                  <>
                    <span className="q-st-badge queued" style={{ color: 'var(--purple)' }}
                      title={'Starts ' + new Date(job.not_before * 1000).toLocaleString()}>
                      ⏾ {new Date(job.not_before * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <button className="btn btn-secondary btn-sm" style={{ padding: '3px 8px', fontSize: 'var(--fs-8)' }}
                      onClick={() => API.post('/api/queue/' + encodeURIComponent(job.id) + '/start-now', {})
                        .then(loadJobs).catch(e => showNotif('Error', e.message, 'error'))}>▶ START NOW</button>
                  </>
                ) : (
                  <span className={'q-st-badge ' + (JOB_BADGE[job.status] || 'queued')} style={{ color: JOB_COLOR[job.status] }}>{(job.status || '').toUpperCase()}</span>
                )}
                {job.status === 'queued' && queuedJobsCount > 1 && (
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <button className="rand-step-btn" title="Run earlier" style={{ padding: '0 5px', fontSize: 'var(--fs-8)' }}
                      disabled={(job.queue_position || 0) === 0}
                      onClick={() => handleReorder(job, -1)}>▲</button>
                    <button className="rand-step-btn" title="Run later" style={{ padding: '0 5px', fontSize: 'var(--fs-8)' }}
                      disabled={(job.queue_position || 0) >= queuedJobsCount - 1}
                      onClick={() => handleReorder(job, 1)}>▼</button>
                  </span>
                )}
                {(job.status === 'queued' || job.status === 'active') && (
                  <div className="q-del" title={job.status === 'active' ? 'Cancel this job' : 'Remove from queue'} onClick={() => handleCancelJob(job)}><Ico name="x" /></div>
                )}
                {(job.status === 'failed' || job.status === 'cancelled') && (
                  <button className="btn btn-secondary btn-sm" style={{ padding: '3px 8px', fontSize: 'var(--fs-8)' }}
                    title="Run this job again, with the same options"
                    onClick={() => API.post('/api/queue/' + encodeURIComponent(job.id) + '/retry', {})
                      .then(() => { showNotif('Re-queued', job.label || job.url); loadJobs(); })
                      .catch(e => showNotif('Error', e.message, 'error'))}>↻ RETRY</button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {isDownloading && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="panel-hud" /><div className="panel-hud-br" />
          <div className="ph">
            <span className="ptag">ACTIVE</span>
            <span className="ptitle">NOW DOWNLOADING</span>
            <span className="psub" style={{ color: 'var(--cyan)' }}>
            {playlistTotalCount > 1
              ? `${playlistCompletedCount + 1} / ${playlistTotalCount} — ${(dlState.pct || 0).toFixed(1)}%`
              : `${(dlState.pct || 0).toFixed(1)}% COMPLETE`}
          </span>
          </div>
          <div className="q-item row-active">
            <span className="q-drag">⋮⋮</span>
            {dlState.current_item_thumb
              ? <img src={dlState.current_item_thumb} style={{ width: 64, height: 36, objectFit: 'cover', display: 'block', borderRadius: 0, flexShrink: 0 }} onError={e => { e.target.style.display = 'none'; }} />
              : <div className="q-thumb-ph">▶</div>}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="q-name" style={{ marginBottom: 4 }}>{dlState.current_item_title || dlState.filename || 'Downloading...'}</div>
              <div className="prog-bar" style={{ height: 4 }}>
                <div className="prog-bar-fill" style={{ width: (dlState.pct || 0) + '%', background: isPaused ? 'var(--amber)' : undefined }} />
              </div>
            </div>
            <span className="q-size">{fmtBytes(dlState.total)}</span>
            <div className="q-status"><span className={'q-st-badge ' + (isPaused ? 'queued' : 'downloading')}>{isPaused ? 'PAUSED' : 'ACTIVE'}</span></div>
            {isPaused
              ? <button className="btn btn-amber btn-sm" style={{ padding: '4px 8px', fontSize: 'var(--fs-9)' }} onClick={onResume}>▶</button>
              : <button className="btn btn-secondary btn-sm" style={{ padding: '4px 8px', fontSize: 'var(--fs-9)' }} onClick={onPause}>⏸</button>}
            <div className="q-del" onClick={handleCancel}><Ico name="x" /></div>
          </div>
          <div style={{ padding: '8px 14px', borderTop: '1px solid var(--border)', display: 'flex', gap: 12, fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-9)', color: 'var(--t3)' }}>
            <span>↓ <span style={{ color: 'var(--cyan)' }}>{fmtSpeed(dlState.speed)}</span></span>
            <span>ETA <span style={{ color: 'var(--cyan)' }}>{fmtEta(dlState.eta)}</span></span>
            <span>{fmtBytes(dlState.downloaded)} / {fmtBytes(dlState.total)}</span>
          </div>
        </div>
      )}

      {(playlistItems && playlistItems.length > 0) || (completedItems && completedItems.length > 0) || (failedItems && failedItems.length > 0) ? (
        <div className="panel">
          <div className="panel-hud" /><div className="panel-hud-br" />
          <div className="ph">
            <span className="ptag">PLAYLIST</span>
            <span className="ptitle">DOWNLOAD QUEUE</span>
            <span className="psub">
              {qTab === 'pending' ? (playlistItems ? playlistItems.length : 0) + ' PENDING'
                : qTab === 'completed' ? (completedItems ? completedItems.length : 0) + ' DONE'
                : (failedItems ? failedItems.length : 0) + ' FAILED'}
            </span>
          </div>
          <div className="q-tabs" style={{ display: 'flex', alignItems: 'center' }}>
            <div className={'q-tab' + (qTab === 'pending' ? ' active' : '')} onClick={() => setQTab('pending')}>PENDING</div>
            <div className={'q-tab' + (qTab === 'completed' ? ' active' : '')} onClick={() => setQTab('completed')}>COMPLETED</div>
            <div className={'q-tab' + (qTab === 'failed' ? ' active' : '')} onClick={() => setQTab('failed')} style={failedItems && failedItems.length ? { color: 'var(--red)' } : undefined}>
              FAILED{failedItems && failedItems.length ? ' (' + failedItems.length + ')' : ''}
            </div>
            {qTab === 'completed' && completedItems && completedItems.length > 0 && onClearCompleted && (
              <span style={{ marginLeft: 'auto', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-9)', color: 'var(--red)', padding: '0 10px' }} onClick={onClearCompleted}>CLEAR ✕</span>
            )}
            {qTab === 'failed' && failedItems && failedItems.filter(i => i.url).length > 1 && (
              <span style={{ marginLeft: 'auto', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-9)', color: 'var(--cyan)', padding: '0 10px' }}
                title="Download every failed item again, with the options of the job it failed in"
                onClick={handleRetryAll}>↻ RETRY ALL</span>
            )}
            {qTab === 'failed' && failedItems && failedItems.length > 0 && onClearFailed && (
              <span style={{ marginLeft: failedItems.filter(i => i.url).length > 1 ? 0 : 'auto', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-9)', color: 'var(--red)', padding: '0 10px' }} onClick={onClearFailed}>CLEAR ✕</span>
            )}
          </div>
          {qTab === 'failed' ? (
            <div className="pl-queue-list">
              {(failedItems || []).map((item, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 14px', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-8)', color: item.reason === 'geo_blocked' ? 'var(--amber)' : 'var(--red)', minWidth: 70 }}>
                    {(item.reason || 'error').toUpperCase()}
                  </span>
                  <span style={{ flex: 1, minWidth: 0, fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-9)', color: 'var(--t2)' }} title={item.title}>
                    {item.hint && <div style={{ color: 'var(--t1)', marginBottom: 2 }}>{item.hint}</div>}
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: item.hint ? 'var(--t4)' : undefined }}>{item.title}</div>
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-8)', color: 'var(--t4)' }}>{timeAgo(item.failedAt)}</span>
                  {item.url && (
                    <button className="btn btn-secondary btn-sm" style={{ padding: '3px 8px', fontSize: 'var(--fs-8)' }} onClick={() => handleRetryFailed(item)}>↻ RETRY</button>
                  )}
                </div>
              ))}
              {(!failedItems || failedItems.length === 0) && (
                <div style={{ padding: '20px', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-9)', color: 'var(--t4)', textAlign: 'center' }}>NO FAILURES — ALL CLEAR</div>
              )}
            </div>
          ) : qTab === 'pending' ? (
            <>
              <div className="queue-list-header">
                <span className="qlh-left">PENDING ITEMS<span className="ja"> — 待機中</span></span>
                <span className="qlh-right">{(playlistItems ? playlistItems.length : 0)} TRACKS · CLICK ✕ TO REMOVE</span>
              </div>
              {syncJobLabel && (
                <div style={{ padding: '6px 14px', background: 'var(--bg3)', borderBottom: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-9)', color: 'var(--cyan)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>⟳</span>
                  SYNC QUEUED: {syncJobLabel}
                </div>
              )}
              <div className="pl-queue-list">
                {(playlistItems || []).map(item => (
                  <div
                    key={item.idx}
                    className={'pl-queue-item' + (removingItems.has(item.idx) ? ' completing' : '')}
                    onAnimationEnd={removingItems.has(item.idx) ? () => {
                      setPlaylistItems(prev => prev ? prev.filter(x => x.idx !== item.idx) : prev);
                      setRemovingItems(prev => { const n = new Set(prev); n.delete(item.idx); return n; });
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
                    <div className="pl-queue-remove" onClick={() => handleRemove(item.idx)}>
                      <Ico name="x" size={10} />
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="pl-queue-list">
              {(completedItems || []).map((item, i) => (
                <div key={i} className="q-completed-item">
                  {item.thumbnail
                    ? <img src={item.thumbnail} style={{ width: 64, height: 36, objectFit: 'cover', flexShrink: 0, borderRadius: 2 }} alt="" onError={e => { e.target.style.display='none'; }} />
                    : <div className="q-comp-thumb-ph">✓</div>}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="q-comp-title">{item.title || 'Unknown'}</div>
                    <div className="q-comp-meta">
                      <span className="q-st-badge completed">DONE</span>
                      {' '}
                      {item.file_size ? fmtBytes(item.file_size) : ''}
                      {' · '}
                      {timeAgo(item.completedAt)}
                    </div>
                  </div>
                </div>
              ))}
              {(!completedItems || completedItems.length === 0) && (
                <div style={{ padding: '20px', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-9)', color: 'var(--t4)', textAlign: 'center' }}>NO COMPLETED ITEMS YET</div>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="panel">
          <div className="panel-hud" /><div className="panel-hud-br" />
          <div className="ph">
            <span className="ptag">QUEUE</span>
            <span className="ptitle">PENDING DOWNLOADS<span className="ja"> — 待機中</span></span>
          </div>
          {fetchingPlaylistItems ? (
            <div style={{ padding: '20px', fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-9)', color: 'var(--t3)', textAlign: 'center' }}>
              FETCHING PLAYLIST ITEMS...
            </div>
          ) : (
            <div className="empty-state">
              <Mascot src={MASCOT_TIRED} className="empty-mascot tint-cyan" wrapClass="empty-mascot-wrap" style={{ width: 180 }} />
              <div className="empty-title">QUEUE EMPTY</div>
              <div className="empty-sub">PASTE A URL IN FEED TO START DOWNLOADING</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
