// Thin JSON fetch wrapper used by every page.
'use strict';

// The token /launch gave this tab (mellow/session.py). Every API call sends it:
// pages other programs serve on this machine share the session cookie, never
// this tab's sessionStorage.
const TOKEN_KEY = 'mellow-token';
export const authHeaders = () => {
  let token = null;
  try { token = sessionStorage.getItem(TOKEN_KEY); } catch { /* no storage (tests, blocked) */ }
  return token ? { 'X-Mellow-Token': token } : {};
};

const failure = async (r) => {
  const data = await r.json().catch(() => null);
  const err = new Error((data && data.error) || r.statusText || ('HTTP ' + r.status));
  err.data = data;
  err.status = r.status;
  return err;
};

// Resolves with the JSON body. A failed request (4xx/5xx) rejects with an
// Error carrying the server's message, the full body as `data` and `status`.
// Resolving on those made every caller without its own `d.error` check report
// success for a request the server had refused.
const request = (method, url, body) => fetch(url, body === undefined ? { method, headers: authHeaders() } : {
  method,
  headers: { 'Content-Type': 'application/json', ...authHeaders() },
  body: JSON.stringify(body),
}).then(async r => {
  if (!r.ok) throw await failure(r);
  return r.json().catch(() => null);
});

// A file the server sends (backup, CSV export): fetched with the token, then
// saved under the name the server gives it. A plain link can't send the token.
export const download = (url) => fetch(url, { headers: authHeaders() }).then(async r => {
  if (!r.ok) throw await failure(r);
  const named = /filename="?([^";]+)"?/.exec(r.headers.get('Content-Disposition') || '');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(await r.blob());
  link.download = named ? named[1] : 'download';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 60000);
});

export const API = {
  get: (url) => request('GET', url),
  post: (url, body) => request('POST', url, body),
  put: (url, body) => request('PUT', url, body),
  del: (url, body) => request('DELETE', url, body),
};

// Stop the download a progress panel shows (its latest event carries the
// job id). With several downloads running, /api/cancel stopped all of them.
// The resulting `cancelled` event is what tells the user it stopped.
export const cancelShownDownload = (dlState) => (dlState && dlState.job_id
  ? API.del('/api/queue/' + encodeURIComponent(dlState.job_id))
  : API.post('/api/cancel', {}));
