// node --test tests/js — frontend helpers (gui/lib/util.js, formats.js)
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  estimateDownloadBytes, fmtBytes, fmtCount, fmtDuration, idxRanges, isLinkLike, parseClock,
} from '../../gui/lib/util.js';
import { defaultToggles, togglesFor, togglesFrom } from '../../gui/lib/formats.js';

test('idxRanges compresses playlist positions', () => {
  assert.equal(idxRanges([9, 1, 2, 3, 5, 8, 3]), '1-3,5,8-9');
  assert.equal(idxRanges([4]), '4');
  assert.equal(idxRanges([]), '');
});

test('isLinkLike tells links from search words', () => {
  for (const link of ['https://youtu.be/x', 'youtube.com/watch?v=abc', 'www.example.org', 'ytsearch5:lofi']) {
    assert.ok(isLinkLike(link), link);
  }
  for (const words of ['lofi beats', 'daft punk - one more time', 'music.mp3 remix', '']) {
    assert.ok(!isLinkLike(words), words);
  }
});

test('formatting', () => {
  assert.equal(fmtDuration(0), '0:00');
  assert.equal(fmtDuration(3725.9), '1:02:05');
  assert.equal(fmtDuration(null), '');
  assert.equal(fmtCount(1500), '1.5K');
  assert.equal(fmtCount(2300000), '2.3M');
  assert.equal(fmtCount(1000000), '1M');
  assert.equal(fmtCount(null), '');
  assert.equal(fmtBytes(1536), '2 KB');
  assert.equal(fmtBytes(31 * 1024 * 1024), '31.0 MB');
  assert.equal(fmtBytes(0), '0 B');
  assert.equal(fmtBytes(null), '—');
});

test('parseClock', () => {
  assert.equal(parseClock('90'), 90);
  assert.equal(parseClock('1:30'), 90);
  assert.equal(parseClock('1:01:30'), 3690);
  assert.equal(parseClock('1:3x'), null);
  assert.equal(parseClock(''), null);
});

test('estimateDownloadBytes follows quality, bitrate, clip and chapters', () => {
  const info = { duration: 100, size_estimates: { video: { '1080p': 1000, '720p': 400 }, audio: 50 } };
  const base = { mode: 'video', quality: '1080p', audioFmt: 'mp3', audioQuality: 'best', startTime: '', endTime: '' };
  assert.equal(estimateDownloadBytes(info, base), 1000);
  assert.equal(estimateDownloadBytes(info, { ...base, quality: '720p' }), 400);
  assert.equal(estimateDownloadBytes(info, { ...base, startTime: '0:10', endTime: '0:60' }), 500);
  assert.equal(estimateDownloadBytes(info, { ...base, chapters: [{ start: 0, end: 25 }] }), 250);
  assert.equal(estimateDownloadBytes(info, { ...base, mode: 'audio', audioQuality: '128' }), 100 * 128 * 125);
  assert.equal(estimateDownloadBytes(info, { ...base, mode: 'audio' }), 50);  // "best": the stream itself
  assert.equal(estimateDownloadBytes({ duration: 5 }, base), null);
});

test('toggles: defaults, values from a preset, per media', () => {
  const d = defaultToggles();
  assert.equal(d.embed_thumbnail, true);
  assert.equal(d.sponsorblock, false);
  assert.deepEqual(togglesFrom({ sponsorblock: 1, embed_thumbnail: null }), { ...d, sponsorblock: true });
  const video = togglesFor('video').map(t => t.key);
  const audio = togglesFor('audio').map(t => t.key);
  assert.ok(video.includes('embed_subs') && !video.includes('normalize_audio'));
  assert.ok(audio.includes('normalize_audio') && !audio.includes('embed_subs'));
});
