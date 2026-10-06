// node --test tests/js — the GUIDE tours (gui/lib/tours.js)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';

import { TOURS, placeCard, tourIdFor } from '../../gui/lib/tours.js';

const GUI = new URL('../../gui/', import.meta.url);
const source = ['pages', 'components']
  .flatMap(dir => readdirSync(new URL(dir + '/', GUI)).map(f => readFileSync(new URL(dir + '/' + f, GUI), 'utf8')))
  .join('\n');
const tagged = name => source.includes('data-tour="' + name + '"') || source.includes("'" + name + "'");

test('every page has a tour', () => {
  for (const page of ['feed', 'queue', 'vault', 'analytics', 'signal', 'config']) {
    assert.ok(TOURS[page] && TOURS[page].length, page);
  }
});

test('every step says something and points at an element the pages mark', () => {
  for (const [id, steps] of Object.entries(TOURS)) {
    const targets = steps.map(s => s.target).filter(Boolean);
    assert.equal(new Set(targets).size, targets.length, id + ': a target twice');
    for (const s of steps) {
      assert.ok(s.title && s.text, id + ': ' + s.target);
      // A step without a target explains an idea (add-only vs mirror, the archive file)
      assert.ok(s.target === null || tagged(s.target), id + ': nothing is marked data-tour="' + s.target + '"');
      for (const r of s.reveal || []) {
        assert.ok(tagged(r.click) && tagged(r.unless), id + ': reveal ' + JSON.stringify(r));
      }
    }
  }
});

test('examples are well formed', () => {
  const kinds = { rows: 'rows', file: 'lines', pairs: 'pairs' };
  for (const [id, steps] of Object.entries(TOURS)) {
    for (const s of steps.filter(st => st.example)) {
      const list = s.example[kinds[s.example.kind]];
      assert.ok(Array.isArray(list) && list.length, id + ': ' + s.title);
      if (s.example.kind === 'file') assert.ok(s.example.name, id + ': ' + s.title);
      if (s.example.kind === 'rows') assert.ok(list.every(r => r.text), id + ': ' + s.title);
      if (s.example.kind === 'pairs') assert.ok(list.every(pair => pair.length === 2), id + ': ' + s.title);
      assert.ok(!s.example.onlyMissing || s.target, id + ': onlyMissing needs a target');
    }
  }
});

test('most steps carry a tip or an example', () => {
  const steps = Object.values(TOURS).flat();
  const rich = steps.filter(s => s.tip || s.example).length;
  assert.ok(rich / steps.length >= 0.75, rich + ' of ' + steps.length);
});

test('the vault has a tour per view', () => {
  assert.equal(tourIdFor('vault', false), 'vault');
  assert.equal(tourIdFor('vault', true), 'vault_folder');
  assert.equal(tourIdFor('feed', true), 'feed');
  assert.equal(tourIdFor('nowhere', false), null);
});

const VIEW = { width: 1100, height: 780 };
const CARD = { width: 340, height: 200 };
const inside = p => p.left >= 0 && p.top >= 0 && p.left + CARD.width <= VIEW.width && p.top + CARD.height <= VIEW.height;

test('the card goes below the part, else above, else beside it', () => {
  const below = placeCard({ left: 100, top: 100, width: 300, height: 40 }, CARD, VIEW);
  assert.equal(below.side, 'below');
  assert.equal(below.top, 100 + 40 + 14);
  assert.equal(placeCard({ left: 100, top: 600, width: 300, height: 40 }, CARD, VIEW).side, 'above');
  assert.equal(placeCard({ left: 100, top: 150, width: 300, height: 500 }, CARD, VIEW).side, 'right');
  assert.equal(placeCard({ left: 700, top: 150, width: 380, height: 500 }, CARD, VIEW).side, 'left');
});

test('the card always stays inside the window', () => {
  const cases = [
    null,
    { left: 1000, top: 50, width: 90, height: 20 },          // near the right edge
    { left: 0, top: 0, width: 1100, height: 780 },           // as big as the window
    { left: -50, top: 700, width: 200, height: 60 },         // partly off screen
  ];
  for (const target of cases) {
    const p = placeCard(target, CARD, VIEW);
    assert.ok(inside(p), JSON.stringify({ target, p }));
  }
  assert.equal(placeCard(null, CARD, VIEW).side, 'center');
  assert.equal(placeCard({ left: 0, top: 0, width: 1100, height: 780 }, CARD, VIEW).side, 'over');
});
