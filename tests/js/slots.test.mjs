import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PAGE_NAMES, SLOT_NAMES, resolveSlots, registryProblems } from '../../gui/lib/slots.js';

const defaults = {
  ...Object.fromEntries(SLOT_NAMES.map(n => [n, 'classic-' + n])),
  pages: Object.fromEntries(PAGE_NAMES.map(n => [n, 'classic-' + n + '-view'])),
};

test('a theme without its own components gets every Classic one', () => {
  assert.deepEqual(resolveSlots(defaults, {}, 'tactical'), defaults);
  assert.deepEqual(resolveSlots(defaults, undefined, 'classic'), defaults);
});

test('a theme replaces only the slots it registered', () => {
  const slots = resolveSlots(defaults, { tactical: { Sidebar: 'own' } }, 'tactical');
  assert.equal(slots.Sidebar, 'own');
  assert.equal(slots.TopBar, 'classic-TopBar');
  assert.deepEqual(slots.pages, defaults.pages);
  assert.deepEqual(resolveSlots(defaults, { tactical: { Sidebar: 'own' } }, 'archive'), defaults);
});

test('a theme replaces only the page views it registered', () => {
  const registry = { tactical: { pages: { feed: 'own-feed' } } };
  const slots = resolveSlots(defaults, registry, 'tactical');
  assert.equal(slots.pages.feed, 'own-feed');
  assert.equal(slots.pages.vault, 'classic-vault-view');
  assert.equal(slots.Sidebar, 'classic-Sidebar');
  assert.deepEqual(resolveSlots(defaults, registry, 'classic').pages, defaults.pages);
});

test('unknown slot and page names never reach the App', () => {
  const slots = resolveSlots(defaults, { tactical: { Sidbar: 'typo', pages: { fed: 'typo' } } }, 'tactical');
  assert.deepEqual(Object.keys(slots), [...SLOT_NAMES, 'pages']);
  assert.deepEqual(Object.keys(slots.pages), PAGE_NAMES);
  assert.deepEqual(slots.pages, defaults.pages);
});

test('registryProblems names unknown themes, slots and pages', () => {
  assert.deepEqual(registryProblems({}, ['classic']), []);
  assert.deepEqual(registryProblems({ tactical: { Sidebar: 1 } }, ['classic', 'tactical']), []);
  assert.deepEqual(registryProblems({ tactical: { pages: { feed: 1, vault: 1 } } }, ['tactical']), []);
  assert.deepEqual(registryProblems({ nope: {}, tactical: { Sidbar: 1 } }, ['tactical']),
    ['unknown theme "nope"', 'tactical: unknown slot "Sidbar"']);
  assert.deepEqual(registryProblems({ tactical: { pages: { fed: 1 } } }, ['tactical']),
    ['tactical: unknown page "fed"']);
});

// Each page: Classic's view and the page's logic (its hook)
const PAGE_FILES = {
  feed: ['feed.jsx', 'feed-logic.js'], queue: ['queue.jsx', 'queue-logic.js'], vault: ['vault.jsx', 'vault-logic.js'],
  analytics: ['analytics.jsx', 'analytics-logic.js'], signal: ['signal.jsx', 'signal-logic.js'],
  config: ['config.jsx', 'config-logic.js'],
};

test('every page is split into logic and a view', () => {
  assert.deepEqual(Object.keys(PAGE_FILES).sort(), [...PAGE_NAMES].sort());
});

test('page views draw and call handlers: the API stays in the pages\' logic', async () => {
  const { readFile } = await import('node:fs/promises');
  for (const [view, logic] of Object.values(PAGE_FILES)) {
    const viewSrc = await readFile(new URL('../../gui/pages/' + view, import.meta.url), 'utf8');
    assert.doesNotMatch(viewSrc, /lib\/api\.js|\bAPI\.|\bfetch\(|new EventSource/, view + ' calls the API itself');
    const logicSrc = await readFile(new URL('../../gui/pages/' + logic, import.meta.url), 'utf8');
    assert.match(logicSrc, /lib\/api\.js/, logic);
  }
});

test('the App draws every page with the theme\'s view of it', async () => {
  const { readFile } = await import('node:fs/promises');
  const app = await readFile(new URL('../../gui/app.jsx', import.meta.url), 'utf8');
  for (const name of PAGE_NAMES) assert.match(app, new RegExp('View=\\{S\\.pages\\.' + name + '\\}'), name);
});
