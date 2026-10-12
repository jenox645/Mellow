// The pending items of an analyzed playlist, picked search results, imported
// links or a running sync — one list for the Feed and the Queue.
//
// Before the download starts (no jobId) each item has a checkbox: the
// download takes the ticked ones. Once its job is queued or running, ✕ skips
// an item for real (POST /api/queue/<job>/skip); one already downloading
// finishes.
'use strict';

import { API } from '../lib/api.js';
import { fmtDuration } from '../lib/util.js';
import { PENDING_LIST_RENDER_MAX } from '../lib/constants.js';
import { Ico } from './icons.jsx';

const keyOf = (item, i) => item.id || item.url || ('#' + item.idx + ':' + i);

export function PendingList({ items, setItems, jobId, showNotif, maxHeight, skipHint }) {
  const [leaving, setLeaving] = React.useState(() => new Set());
  if (!items) return null;
  const picking = !jobId;
  const chosen = picking ? items.filter(i => i.selected !== false) : items;
  const secs = chosen.reduce((s, i) => s + (i.duration || 0), 0);
  const shown = items.slice(0, PENDING_LIST_RENDER_MAX);

  const setAll = pick => setItems(prev => prev && prev.map(i => ({ ...i, selected: pick(i) })));
  const toggle = key => setItems(prev => prev && prev.map((i, n) => (keyOf(i, n) === key ? { ...i, selected: i.selected === false } : i)));
  const forget = key => setLeaving(prev => { const next = new Set(prev); next.delete(key); return next; });
  const skip = (item, key) => {
    setLeaving(prev => new Set([...prev, key]));
    API.post('/api/queue/' + encodeURIComponent(jobId) + '/skip', { items: [item.id, item.url].filter(Boolean) })
      .catch(e => { forget(key); showNotif && showNotif('Not Removed', e.message, 'error'); });
  };

  return (
    <div className="pending-list" data-tour="pending-list">
      <div className="queue-list-header">
        {picking ? (
          <>
            <span className="qlh-left">{chosen.length} OF {items.length} SELECTED{secs ? ' · ' + fmtDuration(secs) : ''}</span>
            <span className="qlh-right pending-picks">
              <span onClick={() => setAll(() => true)}>ALL</span>
              <span onClick={() => setAll(() => false)}>NONE</span>
              <span onClick={() => setAll(i => i.selected === false)}>INVERT</span>
            </span>
          </>
        ) : (
          <>
            <span className="qlh-left">{items.length} TO GO{secs ? ' · ' + fmtDuration(secs) : ''}</span>
            <span className="qlh-right">{skipHint || '✕ SKIPS AN ITEM'}</span>
          </>
        )}
      </div>
      <div className="pl-queue-list" style={maxHeight ? { maxHeight } : undefined}>
        {shown.map((item, n) => {
          const key = keyOf(item, n);
          const off = picking && item.selected === false;
          return (
            <div key={key}
              className={'pl-queue-item' + (off ? ' pl-queue-off' : '') + (leaving.has(key) ? ' completing' : '')}
              onClick={picking ? () => toggle(key) : undefined}
              style={picking ? { cursor: 'pointer' } : undefined}
              onAnimationEnd={leaving.has(key) ? () => {
                setItems(prev => prev && prev.filter((i, m) => keyOf(i, m) !== key));
                forget(key);
              } : undefined}>
              {picking
                ? <span className={'pl-queue-check' + (off ? '' : ' on')} role="checkbox" aria-checked={!off}>{off ? '' : '✓'}</span>
                : <span className="pl-queue-idx">{item.idx}</span>}
              {item.thumbnail
                ? <img src={item.thumbnail} className="pl-queue-thumb" alt="" onError={e => { e.target.style.display = 'none'; }} />
                : <div className="pl-queue-thumb-ph">▶</div>}
              <div className="pl-queue-info">
                <div className="pl-queue-title">{item.title || item.url || 'Unknown'}</div>
                {item.uploader && <div className="pl-queue-sub">{item.uploader}</div>}
              </div>
              <span className="pl-queue-dur">{item.duration ? fmtDuration(item.duration) : '—'}</span>
              <div className="pl-queue-st">
                <span className={'q-st-badge ' + (off ? 'skipped' : 'queued')}>{off ? 'SKIP' : 'QUEUED'}</span>
              </div>
              {!picking && (
                <div className="pl-queue-remove" title={skipHint ? 'Skip this one' : 'Skip this one: it won\'t be downloaded'}
                  onClick={() => skip(item, key)}>
                  <Ico name="x" size={10} />
                </div>
              )}
            </div>
          );
        })}
        {items.length > shown.length && (
          <div className="pending-more">+{items.length - shown.length} more</div>
        )}
      </div>
    </div>
  );
}
