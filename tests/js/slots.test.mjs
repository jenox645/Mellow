import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SLOT_NAMES, resolveSlots, registryProblems } from '../../gui/lib/slots.js';

const defaults = Object.fromEntries(SLOT_NAMES.map(n => [n, 'classic-' + n]));

test('a theme without its own components gets every Classic one', () => {
  assert.deepEqual(resolveSlots(defaults, {}, 'tactical'), defaults);
  assert.deepEqual(resolveSlots(defaults, undefined, 'classic'), defaults);
});

test('a theme replaces only the slots it registered', () => {
  const slots = resolveSlots(defaults, { tactical: { Sidebar: 'own' } }, 'tactical');
  assert.equal(slots.Sidebar, 'own');
  assert.equal(slots.TopBar, 'classic-TopBar');
  assert.deepEqual(resolveSlots(defaults, { tactical: { Sidebar: 'own' } }, 'archive'), defaults);
});

test('unknown slot names never reach the App', () => {
  const slots = resolveSlots(defaults, { tactical: { Sidbar: 'typo' } }, 'tactical');
  assert.deepEqual(Object.keys(slots), SLOT_NAMES);
});

test('registryProblems names unknown themes and slots', () => {
  assert.deepEqual(registryProblems({}, ['classic']), []);
  assert.deepEqual(registryProblems({ tactical: { Sidebar: 1 } }, ['classic', 'tactical']), []);
  assert.deepEqual(registryProblems({ nope: {}, tactical: { Sidbar: 1 } }, ['tactical']),
    ['unknown theme "nope"', 'tactical: unknown slot "Sidbar"']);
});
