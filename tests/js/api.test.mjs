// node --test tests/js — gui/lib/api.js: every API call carries this tab's sign-in token
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { API, authHeaders } from '../../gui/lib/api.js';

const withStorage = async (token, fn) => {
  globalThis.sessionStorage = { getItem: (key) => (key === 'mellow-token' ? token : null) };
  try { return await fn(); } finally { delete globalThis.sessionStorage; }
};

test('authHeaders is empty without a token (or without storage)', async () => {
  assert.deepEqual(authHeaders(), {});
  await withStorage(null, () => assert.deepEqual(authHeaders(), {}));
});

test('every API call sends the token, with or without a body', async () => {
  const sent = [];
  globalThis.fetch = async (url, init) => {
    sent.push(init);
    return { ok: true, json: async () => ({ ok: true }) };
  };
  try {
    await withStorage('tok123', async () => {
      await API.get('/api/config');
      await API.post('/api/download', { url: 'x' });
    });
  } finally {
    delete globalThis.fetch;
  }
  assert.equal(sent[0].headers['X-Mellow-Token'], 'tok123');
  assert.equal(sent[1].headers['X-Mellow-Token'], 'tok123');
  assert.equal(sent[1].headers['Content-Type'], 'application/json');
});

test('a 401 rejects with the server message and status', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 401, statusText: 'UNAUTHORIZED',
    json: async () => ({ error: 'Not signed in', signed_in: false }) });
  try {
    await assert.rejects(API.get('/api/config'), (err) => err.status === 401 && err.message === 'Not signed in');
  } finally {
    delete globalThis.fetch;
  }
});
