// Download state driven by the server's progress events (/api/progress).
//
// A pure reducer, so it runs (and is tested) without a browser. Anything
// that isn't state — toasts, the chime, refreshing stats, the victory
// overlay — is queued in `effects` for the App to carry out
// (effectsFromQueue), in the order the events arrived.
'use strict';

import { BREAKAGE_RE, COMPLETED_ITEMS_KEEP, FAILED_ITEMS_KEEP, SPEED_HISTORY_LEN } from './constants.js';

export function initialDownloads() {
  return {
    appState: 'idle',          // idle | downloading | processing | error
    dlState: null,             // the latest progress of the job on the main panel
    primaryJob: null,          // that job's id ('_single' for events without one)
    activeJobs: {},            // every running job: {pct, speed, eta, title, thumb, label, type}
    seenVideoIds: [],          // item_done already counted for the primary job
    isPaused: false,
    pausedCount: 0,
    speedHistory: Array(SPEED_HISTORY_LEN).fill(0),
    playlistItems: null,       // pending items of the playlist being downloaded
    completedItems: [],        // finished items, newest first
    failedItems: [],
    failedCount: 0,
    playlistTotalCount: 0,
    playlistCompletedCount: 0,
    playlistActive: false,     // a playlist download/sync is running: celebrate its end
    currentPlaylist: { name: '', count: 0 },
    syncJobLabel: null,
    fetchingPlaylistItems: false,
    appUpdate: null,           // MellowDLP updating itself: {stage, pct, version}
    effects: [],               // side effects waiting for the App (see applyEvent)
  };
}

export function downloadsReducer(state, action) {
  switch (action.type) {
    case 'event':
      return applyEvent(state, action.data, action.now);
    case 'set': {
      // setState-style: a value or an updater function, for one field
      const value = typeof action.value === 'function' ? action.value(state[action.key]) : action.value;
      return value === state[action.key] ? state : { ...state, [action.key]: value };
    }
    case 'playlist_started':
      return {
        ...state,
        playlistActive: true,
        currentPlaylist: { name: action.name || '', count: action.count || 0 },
        playlistTotalCount: action.count || 0,
        playlistCompletedCount: 0,
        failedCount: 0,
        failedItems: [],
        fetchingPlaylistItems: !!action.fetching,
      };
    case 'playlist_items':
      return {
        ...state,
        playlistItems: action.items.map(i => ({ ...i, selected: true })),
        fetchingPlaylistItems: false,
        playlistTotalCount: action.count,
        currentPlaylist: { name: action.name || '', count: action.count },
      };
    case 'effects_done':
      // Only the ones the App has run: more may have queued meanwhile
      return action.count ? { ...state, effects: state.effects.slice(action.count) } : state;
    default:
      return state;
  }
}

const withoutJob = (jobs, jobId) => {
  if (!jobId || !(jobId in jobs)) return jobs;
  const next = { ...jobs };
  delete next[jobId];
  return next;
};

// The main panel's job ended: back to idle
const endPrimary = (s, appState) => ({
  ...s, primaryJob: null, dlState: null, appState, isPaused: false,
});

function failure(data, jobId, now) {
  return {
    title: data.message || 'Download failed',
    reason: data.code || data.reason || 'error',
    hint: data.title ? data.title + ' — ' + data.hint : null,
    url: data.url || null,
    jobId,
    failedAt: now,
  };
}

// Pending items of the running playlist without the one that just finished:
// by video id, else playlist position, else title — never blindly the first
function withoutFinished(items, data) {
  if (!items) return items;
  const tries = [
    data.video_id && (x => x.video_id !== data.video_id),
    data.playlist_index != null && (x => x.idx !== data.playlist_index),
    data.title && (x => x.title !== data.title),
  ].filter(Boolean);
  for (const keep of tries) {
    const rest = items.filter(keep);
    if (rest.length < items.length) return rest;
  }
  return items;
}

export function applyEvent(state, data, now = Date.now()) {
  const jobId = data.job_id || null;
  const isPrimary = state.primaryJob === null || jobId === null || jobId === state.primaryJob;
  const fx = [];
  let s = state;

  switch (data.status) {
    case 'starting':
      if (s.primaryJob === null) {
        s = { ...s, primaryJob: jobId || '_single', seenVideoIds: [], dlState: { status: 'starting', pct: 0 } };
      }
      s = { ...s, appState: 'downloading' };
      break;

    case 'downloading': {
      s = { ...s, appState: 'downloading', speedHistory: [...s.speedHistory.slice(1), data.speed || 0] };
      if (jobId) {
        s.activeJobs = { ...s.activeJobs, [jobId]: {
          pct: data.pct, speed: data.speed, eta: data.eta,
          title: data.current_item_title || data.filename,
          thumb: data.current_item_thumb,
          label: data.job_label, type: data.job_type,
        } };
      }
      if (s.primaryJob === null && jobId) s.primaryJob = jobId;
      if (isPrimary) s.dlState = data;
      // An imported link shows as its URL until the download names it
      const first = s.playlistItems && s.playlistItems[0];
      if (data.current_item_title && first && first.url && first.title === first.url) {
        s.playlistItems = [{ ...first, title: data.current_item_title, thumbnail: data.current_item_thumb || first.thumbnail },
          ...s.playlistItems.slice(1)];
      }
      break;
    }

    case 'processing':
      if (isPrimary) {
        s = { ...s, appState: 'processing',
          dlState: s.dlState ? { ...s.dlState, status: 'processing' } : { status: 'processing', pct: 100 } };
      }
      break;

    case 'item_done': {
      const vid = data.video_id;
      if (vid && s.seenVideoIds.includes(vid)) return state;
      s = { ...s, playlistItems: withoutFinished(s.playlistItems, data),
        playlistCompletedCount: s.playlistCompletedCount + 1 };
      if (vid) s.seenVideoIds = [...s.seenVideoIds, vid];
      if (!(vid && s.completedItems.some(x => x.video_id === vid))) {
        s.completedItems = [{ video_id: vid, title: data.title, thumbnail: data.thumbnail, jobId, completedAt: now },
          ...s.completedItems].slice(0, COMPLETED_ITEMS_KEEP);
      }
      break;
    }

    case 'item_saved': {
      // The file an item ended up as (after conversion): the job's newest
      // finished item that has none yet
      const i = s.completedItems.findIndex(x => x.jobId === jobId && !x.file_path);
      if (i < 0) return state;
      const completedItems = s.completedItems.slice();
      completedItems[i] = { ...completedItems[i], file_path: data.file_path, file_size: data.file_size };
      s = { ...s, completedItems };
      break;
    }

    case 'paused':
      s = { ...s, isPaused: true, pausedCount: 1, dlState: s.dlState && { ...s.dlState, paused: true } };
      break;

    case 'resumed':
      s = { ...s, isPaused: false, pausedCount: 0, dlState: s.dlState && { ...s.dlState, paused: false } };
      break;

    case 'item_failed':
      s = { ...s, failedCount: s.failedCount + 1,
        failedItems: [{ ...failure(data, jobId, now), title: data.message || 'Unknown item' },
          ...s.failedItems].slice(0, FAILED_ITEMS_KEEP) };
      break;

    case 'complete':
      s = { ...s, activeJobs: withoutJob(s.activeJobs, jobId) };
      fx.push({ type: 'chime' });
      fx.push(data.warning
        // Saved, but not the way it was asked for (e.g. no ffmpeg to convert)
        ? { type: 'notify', title: 'Downloaded With Limits', body: data.warning, kind: 'warn', file: data.file_path }
        : { type: 'notify', title: 'Download Complete', body: data.title || 'File saved successfully', kind: 'success', file: data.file_path });
      fx.push({ type: 'desktop', title: 'Download complete', body: data.title || '' });
      fx.push({ type: 'refreshStats' }, { type: 'refreshVault' });
      if (isPrimary) {   // a background job finishing leaves the main panel alone
        s = { ...endPrimary(s, 'idle'), pausedCount: 0, syncJobLabel: null,
          speedHistory: [...s.speedHistory.slice(1), 0], playlistItems: null, fetchingPlaylistItems: false };
        if (s.playlistActive) {
          s.playlistActive = false;
          fx.push({ type: 'victory', sync: !!data.library_id,
            name: s.currentPlaylist.name, count: s.currentPlaylist.count });
        }
      }
      break;

    case 'error': {
      const item = failure(data, jobId, now);
      s = { ...s, activeJobs: withoutJob(s.activeJobs, jobId), failedCount: s.failedCount + 1,
        failedItems: [item, ...s.failedItems].slice(0, FAILED_ITEMS_KEEP) };
      if (data.title) {
        // The backend recognised the error: plain words and the fix
        fx.push({ type: 'notify', title: data.title, body: data.hint, kind: 'error', action: data.action });
      } else {
        // Extraction failures usually mean yt-dlp is outdated — offer the fix
        // (unless the backend already pinned it on the missing ffmpeg)
        const breakage = data.code !== 'ffmpeg_missing' && BREAKAGE_RE.test(item.title);
        fx.push({ type: 'notify', title: 'Error', kind: 'error',
          body: breakage ? item.title + ' — this often means yt-dlp is outdated.' : item.title,
          action: breakage ? 'update_ytdlp' : null });
      }
      fx.push({ type: 'desktop', title: data.title || 'Download failed', body: data.hint || item.title });
      fx.push({ type: 'refreshStats' });
      if (isPrimary) s = endPrimary(s, 'error');
      break;
    }

    case 'cancelled':
      s = { ...s, activeJobs: withoutJob(s.activeJobs, jobId) };
      fx.push({ type: 'notify', title: 'Cancelled', body: 'Download stopped', kind: 'info' });
      if (isPrimary) s = { ...endPrimary(s, 'idle'), pausedCount: 0 };
      break;

    case 'queue_done':
      // The last one finished: its own "Download Complete" already said so
      if (data.count > 1) fx.push({ type: 'notify', title: 'Queue Finished', body: data.count + ' downloads done', kind: 'success' });
      fx.push({ type: 'desktop', title: 'All downloads finished', body: data.count + ' download(s) done' });
      break;

    case 'warning':
      fx.push({ type: 'notify', title: 'Heads Up', body: data.message || '', kind: 'warn' });
      break;

    case 'app_update':
      // downloading (pct) → installing → restarting; the app then closes
      if (data.stage === 'error') {
        s = { ...s, appUpdate: null };
        fx.push({ type: 'notify', title: 'Update Failed', body: data.message || '', kind: 'error', action: 'open_release' });
      } else {
        s = { ...s, appUpdate: { stage: data.stage, pct: data.pct || 0, version: data.version || '' } };
      }
      break;

    case 'ytdlp_updated':
      fx.push(data.ok
        ? { type: 'notify', title: data.restart_required ? 'Restart To Finish' : 'Updated',
          body: data.message || 'yt-dlp updated successfully', kind: 'success' }
        : { type: 'notify', title: 'Update failed', body: data.error || '', kind: 'error' });
      fx.push({ type: 'refreshStats' });
      break;

    default:
      return state;
  }
  return fx.length ? { ...s, effects: [...s.effects, ...fx] } : s;
}
