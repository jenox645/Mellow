// node --test tests/js — explorer-style selection (gui/lib/selection.js)
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { clickSelect, hitKeys, intersects, rectFrom } from '../../gui/lib/selection.js';

const box = (key, left, top, w = 100, h = 100) => ({ key, left, top, right: left + w, bottom: top + h });
// A 3 × 2 grid of 100px cards, 10px apart
const GRID = ['a', 'b', 'c', 'd', 'e', 'f'].map((k, i) => box(k, (i % 3) * 110, Math.floor(i / 3) * 110));

test('a rectangle is the same whichever way it is dragged', () => {
  const down = rectFrom({ x: 10, y: 20 }, { x: 50, y: 80 });
  assert.deepEqual(down, { left: 10, top: 20, right: 50, bottom: 80 });
  assert.deepEqual(rectFrom({ x: 50, y: 80 }, { x: 10, y: 20 }), down);
});

test('cards the rectangle touches are hit, in list order', () => {
  // From inside "b" down and left into "d" and "e"
  assert.deepEqual(hitKeys(rectFrom({ x: 150, y: 50 }, { x: 60, y: 150 }), GRID), ['a', 'b', 'd', 'e']);
  // The gap between cards hits nothing
  assert.deepEqual(hitKeys(rectFrom({ x: 102, y: 0 }, { x: 108, y: 210 }), GRID), []);
  assert.ok(!intersects({ left: 100, top: 0, right: 110, bottom: 10 }, box('x', 110, 0)));   // edges only touch
});

test('a click toggles one file and makes it the anchor', () => {
  let r = clickSelect(new Set(), ['a', 'b', 'c'], 'b');
  assert.deepEqual([...r.selected], ['b']);
  assert.equal(r.anchor, 'b');
  r = clickSelect(r.selected, ['a', 'b', 'c'], 'c', {}, r.anchor);
  assert.deepEqual([...r.selected].sort(), ['b', 'c']);
  r = clickSelect(r.selected, ['a', 'b', 'c'], 'b', {}, r.anchor);
  assert.deepEqual([...r.selected], ['c']);
});

test('shift-click takes the range from the anchor, either way', () => {
  const keys = ['a', 'b', 'c', 'd', 'e'];
  let r = clickSelect(new Set(['b']), keys, 'd', { shift: true }, 'b');
  assert.deepEqual([...r.selected], ['b', 'c', 'd']);
  assert.equal(r.anchor, 'b');                                  // the range can still change
  r = clickSelect(r.selected, keys, 'a', { shift: true }, r.anchor);
  assert.deepEqual([...r.selected], ['a', 'b']);
});

test('ctrl+shift adds the range to what was selected', () => {
  const r = clickSelect(new Set(['e']), ['a', 'b', 'c', 'd', 'e'], 'c', { shift: true, add: true }, 'a');
  assert.deepEqual([...r.selected].sort(), ['a', 'b', 'c', 'e']);
});

test('shift without an anchor (or one no longer shown) is a plain click', () => {
  assert.deepEqual([...clickSelect(new Set(), ['a', 'b'], 'b', { shift: true }).selected], ['b']);
  assert.deepEqual([...clickSelect(new Set(), ['a', 'b'], 'b', { shift: true }, 'gone').selected], ['b']);
});
