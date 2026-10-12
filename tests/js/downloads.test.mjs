// node --test tests/js — the progress-event reducer (gui/lib/downloads.js)
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { applyEvent, downloadsReducer, initialDownloads } from '../../gui/lib/downloads.js';

const run = (events, state = initialDownloads()) =>
  events.reduce((s, data) => downloadsReducer(s, { type: 'event', data, now: 1000 }), state);
const types = s => s.effects.map(fx => fx.type);

test('a single download: progress, item, saved file, done', () => {
  const s = run([
    { status: 'starting', job_id: 'j1' },
    { status: 'downloading', job_id: 'j1', pct: 40, speed: 1e6, eta: 5, current_item_title: 'Song' },
    { status: 'item_done', job_id: 'j1', video_id: 'v1', title: 'Song' },
    { status: 'item_saved', job_id: 'j1', file_path: '/m/Song.mp3', file_size: 123 },
  ]);
  assert.equal(s.appState, 'downloading');
  assert.equal(s.primaryJob, 'j1');
  assert.equal(s.dlState.pct, 40);
  assert.deepEqual(s.activeJobs.j1.title, 'Song');
  assert.equal(s.speedHistory.at(-1), 1e6);
  assert.deepEqual(s.completedItems.map(i => [i.title, i.file_path, i.file_size]), [['Song', '/m/Song.mp3', 123]]);
  const done = run([{ status: 'complete', job_id: 'j1', title: 'Song', file_path: '/m/Song.mp3' }], s);
  assert.equal(done.appState, 'idle');
  assert.equal(done.dlState, null);
  assert.equal(done.primaryJob, null);
  assert.deepEqual(done.activeJobs, {});
  assert.deepEqual(types(done), ['chime', 'notify', 'desktop', 'refreshStats', 'refreshVault']);
  assert.equal(done.effects[1].title, 'Download Complete');
  assert.equal(done.effects[1].file, '/m/Song.mp3');
});

test('a playlist: items leave the pending list once, and the end is celebrated', () => {
  let s = downloadsReducer(initialDownloads(), { type: 'playlist_started', name: 'Mix', count: 3 });
  s = downloadsReducer(s, { type: 'set', key: 'playlistItems',
    value: [{ idx: 1, title: 'A' }, { idx: 2, title: 'B' }, { idx: 3, title: 'C' }] });
  s = run([
    { status: 'starting', job_id: 'p' },
    { status: 'item_done', job_id: 'p', video_id: 'b', playlist_index: 2, title: 'B' },
    { status: 'item_done', job_id: 'p', video_id: 'b', playlist_index: 2, title: 'B' },   // repeated
  ], s);
  assert.deepEqual(s.playlistItems.map(i => i.title), ['A', 'C']);
  assert.equal(s.playlistCompletedCount, 1);
  assert.equal(s.completedItems.length, 1);
  s = run([{ status: 'complete', job_id: 'p' }], s);
  assert.equal(s.playlistItems, null);
  assert.equal(s.playlistActive, false);
  assert.deepEqual(s.effects.at(-1), { type: 'victory', sync: false, name: 'Mix', count: 3 });
});

test('an item that matches nothing leaves the pending list alone', () => {
  const s = applyEvent({ ...initialDownloads(), playlistItems: [{ idx: 1, title: 'A' }] },
    { status: 'item_done', title: 'Unknown' });
  assert.deepEqual(s.playlistItems, [{ idx: 1, title: 'A' }]);
});

test('a background job finishing leaves the main panel to its own job', () => {
  const s = run([
    { status: 'starting', job_id: 'main' },
    { status: 'downloading', job_id: 'main', pct: 10 },
    { status: 'downloading', job_id: 'bg', pct: 90 },
    { status: 'complete', job_id: 'bg', title: 'Other' },
  ]);
  assert.equal(s.primaryJob, 'main');
  assert.equal(s.dlState.pct, 10);
  assert.equal(s.appState, 'downloading');
  assert.deepEqual(Object.keys(s.activeJobs), ['main']);
  assert.ok(types(s).includes('notify'));
});

test('errors: explained ones carry their fix, unexplained extraction errors offer an update', () => {
  const explained = run([{ status: 'starting', job_id: 'e' },
    { status: 'error', job_id: 'e', message: 'raw', title: 'Sign-in needed', hint: 'Use cookies', action: 'open_config' }]);
  assert.equal(explained.appState, 'error');
  assert.deepEqual(explained.effects[0],
    { type: 'notify', title: 'Sign-in needed', body: 'Use cookies', kind: 'error', action: 'open_config' });
  assert.equal(explained.failedItems[0].hint, 'Sign-in needed — Use cookies');
  const breakage = run([{ status: 'error', message: 'Unable to extract player response' }]);
  assert.equal(breakage.effects[0].action, 'update_ytdlp');
  const ffmpeg = run([{ status: 'error', message: 'Unable to extract x', code: 'ffmpeg_missing' }]);
  assert.equal(ffmpeg.effects[0].action, 'get_ffmpeg');
  assert.equal(ffmpeg.failedCount, 1);
});

test('pause, resume and cancel', () => {
  let s = run([{ status: 'starting', job_id: 'c' }, { status: 'downloading', job_id: 'c', pct: 5 }, { status: 'paused' }]);
  assert.equal(s.isPaused, true);
  assert.equal(s.dlState.paused, true);
  s = run([{ status: 'resumed' }], s);
  assert.equal(s.isPaused, false);
  s = run([{ status: 'cancelled', job_id: 'c' }], s);
  assert.equal(s.appState, 'idle');
  assert.equal(s.dlState, null);
  assert.equal(s.effects.at(-1).title, 'Cancelled');
});

test('effects are handed over once, newer ones kept', () => {
  let s = run([{ status: 'warning', message: 'a' }, { status: 'warning', message: 'b' }]);
  assert.equal(s.effects.length, 2);
  s = downloadsReducer(s, { type: 'effects_done', count: 1 });
  assert.deepEqual(s.effects.map(fx => fx.body), ['b']);
  assert.equal(downloadsReducer(s, { type: 'effects_done', count: 0 }), s);
});

test('set works like setState, and unknown events change nothing', () => {
  let s = downloadsReducer(initialDownloads(), { type: 'set', key: 'failedCount', value: 2 });
  s = downloadsReducer(s, { type: 'set', key: 'failedCount', value: n => n + 1 });
  assert.equal(s.failedCount, 3);
  assert.equal(applyEvent(s, { status: 'something_new' }), s);
  assert.equal(applyEvent(s, { status: 'item_saved', job_id: 'none' }), s);
});

test('queue finished and yt-dlp update toasts', () => {
  assert.deepEqual(types(run([{ status: 'queue_done', count: 1 }])), ['desktop']);
  assert.equal(run([{ status: 'queue_done', count: 3 }]).effects[0].title, 'Queue Finished');
  assert.equal(run([{ status: 'ytdlp_updated', ok: true, restart_required: true }]).effects[0].title, 'Restart To Finish');
  assert.equal(run([{ status: 'ytdlp_updated', ok: false, message: 'x' }]).effects[0].kind, 'error');
  assert.equal(run([{ status: 'ytdlp_updated', ok: false, message: 'x' }]).effects[0].body, 'x');
});

test('MellowDLP updating itself: progress, then the restart or a failure', () => {
  let s = run([{ status: 'app_update', stage: 'downloading', pct: 0, version: '2.1.0' },
    { status: 'app_update', stage: 'downloading', pct: 42, version: '2.1.0' }]);
  assert.deepEqual(s.appUpdate, { stage: 'downloading', pct: 42, version: '2.1.0' });
  assert.equal(s.effects.length, 0);
  s = run([{ status: 'app_update', stage: 'restarting', version: '2.1.0' }], s);
  assert.equal(s.appUpdate.stage, 'restarting');
  s = run([{ status: 'app_update', stage: 'error', message: "doesn't match its published checksum" }], s);
  assert.equal(s.appUpdate, null);
  assert.deepEqual(s.effects.at(-1), { type: 'notify', title: 'Update Failed',
    body: "doesn't match its published checksum", kind: 'error', action: 'open_release' });
});

test('GET FFMPEG: progress, then done (refresh) or a failure with retry; warnings offer it', () => {
  let s = run([{ status: 'ffmpeg_install', stage: 'downloading', pct: 0, version: '9.0' },
    { status: 'ffmpeg_install', stage: 'downloading', pct: 63, version: '9.0' }]);
  assert.deepEqual(s.ffmpegInstall, { stage: 'downloading', pct: 63, version: '9.0' });
  s = run([{ status: 'ffmpeg_install', stage: 'installing', version: '9.0' }], s);
  assert.equal(s.ffmpegInstall.stage, 'installing');
  const done = run([{ status: 'ffmpeg_install', stage: 'done', version: '9.0', detail: 'ffmpeg version n9.0.2' }], s);
  assert.equal(done.ffmpegInstall, null);
  assert.deepEqual(types(done), ['notify', 'refreshStats']);
  assert.equal(done.effects[0].body, 'ffmpeg version n9.0.2');
  const failed = run([{ status: 'ffmpeg_install', stage: 'error', message: 'checksum' }], s);
  assert.equal(failed.ffmpegInstall, null);
  assert.equal(failed.effects[0].action, 'get_ffmpeg');
  assert.equal(run([{ status: 'warning', code: 'ffmpeg_missing', message: 'm' }]).effects[0].action, 'get_ffmpeg');
  assert.equal(run([{ status: 'warning', code: 'sponsorblock_skipped', message: 'm' }]).effects[0].action, null);
});

test('a vault sync that brought new songs is celebrated, an up-to-date one is not', () => {
  const sync = (id, items) => [
    { status: 'starting', job_id: id, job_type: 'sync', job_label: 'Sync — Lofi Beats (1 playlist(s))' },
    ...items.map(v => ({ status: 'item_done', job_id: id, job_type: 'sync', video_id: v, title: v })),
    { status: 'complete', job_id: id, job_type: 'sync', job_label: 'Sync — Lofi Beats (1 playlist(s))' },
  ];
  // Started from the Vault or by auto-sync: the Feed never said a playlist started
  let s = run(sync('s1', ['a', 'b', 'c']));
  assert.deepEqual(s.effects.at(-1), { type: 'victory', sync: true, name: 'Lofi Beats', count: 3 });
  s = run(sync('s2', []));
  assert.ok(!types(s).includes('victory'));
  // A library sync's label, and a sync finishing behind another download
  s = run([
    { status: 'starting', job_id: 'main' },
    { status: 'starting', job_id: 'lib', job_type: 'sync', job_label: 'Library sync — Chill Mix' },
    { status: 'item_done', job_id: 'lib', job_type: 'sync', video_id: 'x' },
    { status: 'complete', job_id: 'lib', job_type: 'sync', job_label: 'Library sync — Chill Mix' },
  ]);
  assert.deepEqual(s.effects.at(-1), { type: 'victory', sync: true, name: 'Chill Mix', count: 1 });
  assert.deepEqual(s.jobItemsDone, {});
});

test('a sync lists what it will download and what the folder has, then says how it went', () => {
  const label = 'Sync — Lofi Beats (1 playlist(s))';
  const ev = (status, extra = {}) => ({ status, job_id: 's', job_type: 'sync', job_label: label, ...extra });
  let s = run([
    ev('sync_plan', { total: 4, have: 2, new: 2, failed_playlists: [],
      items: [{ idx: 2, id: 'b', title: 'B' }, { idx: 4, id: 'd', title: 'D' }],
      have_items: [{ idx: 1, id: 'a', title: 'A' }, { idx: 3, id: 'c', title: 'C' }] }),
    ev('starting'),
  ]);
  // Only what will be downloaded is pending; the rest is listed as in the folder
  assert.deepEqual(s.playlistItems.map(i => i.title), ['B', 'D']);
  assert.deepEqual({ ...s.syncPlan, haveItems: s.syncPlan.haveItems.map(i => i.title) },
    { jobId: 's', name: 'Lofi Beats', total: 4, have: 2, new: 2, haveItems: ['A', 'C'], failed: 0 });
  s = run([ev('item_done', { video_id: 'b', title: 'B' })], s);
  assert.deepEqual(s.playlistItems.map(i => i.title), ['D']);
  s = run([ev('item_done', { video_id: 'd', title: 'D' }),
    ev('complete', { sync_summary: { new: 2, already: 2, failed: 0 } })], s);
  assert.equal(s.syncPlan, null);
  assert.equal(s.playlistItems, null);
  const toast = s.effects.find(fx => fx.type === 'notify');
  assert.deepEqual([toast.title, toast.body], ['Sync Complete', 'Lofi Beats: 2 new · 2 already in the folder']);
  assert.deepEqual(s.effects.at(-1), { type: 'victory', sync: true, name: 'Lofi Beats', count: 2 });

  // Up to date (a periodic sync, say): a quiet toast, no sound, no desktop notification, no celebration
  s = run([ev('sync_plan', { total: 3, have: 3, new: 0, items: [], have_items: [] }),
    ev('complete', { sync_summary: { new: 0, already: 3, failed: 0 } })]);
  assert.deepEqual(types(s), ['notify', 'refreshStats', 'refreshVault']);
  assert.equal(s.effects[0].title, 'Sync: Up To Date');
  assert.equal(s.effects[0].body, 'Lofi Beats: up to date, nothing new (3 already in the folder)');
});

test("a sync plan doesn't take the list from a Feed playlist or another job's panel", () => {
  const plan = { status: 'sync_plan', job_id: 's', job_type: 'sync', total: 1, have: 0, new: 1,
    items: [{ idx: 1, id: 'x', title: 'X' }], have_items: [] };
  let s = downloadsReducer(initialDownloads(), { type: 'playlist_started', name: 'Mix', count: 2 });
  s = run([plan], s);
  assert.equal(s.syncPlan, null);
  s = run([{ status: 'starting', job_id: 'feed' }, plan]);
  assert.equal(s.syncPlan, null);
  // A failed or cancelled sync takes its plan along
  s = run([plan, { status: 'cancelled', job_id: 's', job_type: 'sync' }]);
  assert.equal(s.syncPlan, null);
  assert.equal(s.playlistItems, null);
});
