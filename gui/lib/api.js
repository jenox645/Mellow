// Thin JSON fetch wrapper used by every page.
'use strict';

export const API = {
  get: (url) => fetch(url).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),
  post: (url, body) => fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(r => r.json()),
  put: (url, body) => fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(r => r.json()),
  del: (url, body) => fetch(url, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  }).then(r => r.json()),
};
