// Thin JSON fetch wrapper used by every page.
'use strict';

// Resolves with the JSON body. A failed request (4xx/5xx) rejects with an
// Error carrying the server's message, the full body as `data` and `status`.
// Resolving on those made every caller without its own `d.error` check report
// success for a request the server had refused.
const request = (method, url, body) => fetch(url, body === undefined ? { method } : {
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}).then(async r => {
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const err = new Error((data && data.error) || r.statusText || ('HTTP ' + r.status));
    err.data = data;
    err.status = r.status;
    throw err;
  }
  return data;
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
