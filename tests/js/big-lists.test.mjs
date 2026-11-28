// node --test tests/js — long lists drawn in steps, and the date formatting a
// big folder calls 2,000 times (#127)
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { progressiveCount } from '../../gui/lib/hooks.js';
import { fmtDate } from '../../gui/lib/util.js';
import {
  PROGRESSIVE_FILES_FIRST, PROGRESSIVE_FILES_CHUNK, PROGRESSIVE_FOLDERS_FIRST, PROGRESSIVE_FOLDERS_CHUNK,
} from '../../gui/lib/constants.js';

test('a long list is drawn in steps that end on its length', () => {
  const steps = [];
  let count = PROGRESSIVE_FILES_FIRST;
  while (count < 2000) {
    count = progressiveCount(count, 2000, PROGRESSIVE_FILES_FIRST, PROGRESSIVE_FILES_CHUNK);
    steps.push(count);
  }
  assert.equal(steps.at(-1), 2000);
  assert.ok(steps.every((n, i) => i === 0 || n - steps[i - 1] <= PROGRESSIVE_FILES_CHUNK));
  assert.equal(steps.length, Math.ceil((2000 - PROGRESSIVE_FILES_FIRST) / PROGRESSIVE_FILES_CHUNK));
});

test('a short list, or one that shrank, is drawn whole at once', () => {
  assert.equal(progressiveCount(0, 30, PROGRESSIVE_FILES_FIRST, PROGRESSIVE_FILES_CHUNK), 30);
  assert.equal(progressiveCount(900, 10, PROGRESSIVE_FILES_FIRST, PROGRESSIVE_FILES_CHUNK), 10);
  assert.equal(progressiveCount(PROGRESSIVE_FOLDERS_FIRST, 500, PROGRESSIVE_FOLDERS_FIRST, PROGRESSIVE_FOLDERS_CHUNK),
    PROGRESSIVE_FOLDERS_FIRST + PROGRESSIVE_FOLDERS_CHUNK);
});

test('the first step holds more than a screen of cards', () => {
  // The smallest cards (SM, 130 px) on a 2560×1440 window: about 18 × 8
  assert.ok(PROGRESSIVE_FILES_FIRST >= 100);
  assert.ok(PROGRESSIVE_FOLDERS_FIRST >= 40);
});

test('fmtDate gives what toLocaleDateString gives', () => {
  for (const ts of [Date.UTC(2026, 0, 2, 3, 4, 5), 0.5, 1e12, Date.UTC(1999, 11, 31, 23, 59), 1764300000000]) {
    assert.equal(fmtDate(ts), new Date(ts).toLocaleDateString());
  }
  assert.equal(fmtDate(0), '—');
  assert.equal(fmtDate(null), '—');
  assert.equal(fmtDate('not a date'), 'Invalid Date');
});
