# MellowDLP's API for other programs

Scripts, launchers, browser helpers and home automation running on the same computer can add downloads
and follow them through `/api/v1`. Each program uses its own **API key**, which can do only what you
allowed when you made it.

## Make a key

1. In MellowDLP, open **Config → API ACCESS**.
2. Give the key a name (what will use it) and tick what it may do:

   | Scope | Allows |
   |---|---|
   | `downloads:create` | `POST /api/v1/downloads` |
   | `queue:read` | `GET /api/v1/queue` |
   | `events:read` | `GET /api/v1/events` |

   Any key may call `GET /api/v1/status`.
3. **MAKE KEY** shows the key once: copy it then. MellowDLP keeps only a fingerprint of it.
4. **REVOKE** stops a key at once.

MellowDLP listens on `127.0.0.1` only, on a port chosen at each start. So that a program always finds
it, set **Fixed Port** in the same panel (from the next start, when that port is free).

## Calls

Send the key with every request:

    Authorization: Bearer mlw_…

### `GET /api/v1/status`

```json
{"app_version": "2.13.0", "ytdlp_version": "2026.08.19", "queued": 1, "active": 0}
```

### `POST /api/v1/downloads` (`downloads:create`)

```sh
curl -X POST http://127.0.0.1:7337/api/v1/downloads \
  -H "Authorization: Bearer mlw_…" -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "mode": "audio", "audio_format": "mp3"}'
```

**Fields:**
- `url` is required: one `http` or `https` link.
- These are optional; anything you leave out takes your Config default:

  | Field | Values |
  |---|---|
  | `mode` | `video` / `audio` |
  | `quality` | `best`, `4k`, `1080p`, `720p`, `480p`, `360p` |
  | `container` | `mp4`, `mkv`, `webm` |
  | `audio_format` | `mp3`, `m4a`, `aac`, `flac`, `opus`, `wav` |
  | `audio_quality` | `best`, `320`, `256`, `192`, `128` |

- Any other field is refused (400). The download goes to your download folder, named by your Config
  template.

**Answer:** `201 {"job_id": "…", "status": "queued"}`.

### `GET /api/v1/queue` (`queue:read`)

Every job MellowDLP knows about, queued, running or recently finished. Each one has `id`, `type`, `label`,
`url`, `status`, `queue_position`, `not_before` and `counts`. Where files are saved is never included.

### `GET /api/v1/events` (`events:read`)

Download progress as server-sent events (`text/event-stream`, one JSON object per `data:` line). Each
event's `status` is one of:
- `starting`, `downloading`, `processing`;
- `item_done`, `item_failed`;
- `warning`;
- `complete`, `error`, `cancelled`;
- `paused`, `resumed`;
- `queue_done`;
- `ping` (a keep-alive, every 25 s).

Fields: `job_id`, `job_type`, `job_label`, `pct`, `speed`, `eta`, `title`, `current_item_title`,
`playlist_index`, `video_id`, `reason`, `code`, `hint`. File paths and raw error text are never sent.

## Answers to expect

| Status | Meaning |
|---|---|
| `401` | No key, an unknown key, or a revoked one |
| `403` | The key exists but may not do this (its scopes) |
| `400` | A field is missing, unknown or not one of the allowed values |

## Coming from MellowDLP 2.12 or earlier

Before 2.13, every route under `/api/` answered any program on the computer. Now only MellowDLP's own
window can use them: a program gets `401 Not signed in`. To move an integration over:

| Before | Now |
|---|---|
| `POST /api/download` | `POST /api/v1/downloads` with a `downloads:create` key, and only the fields above. A folder (`output_dir`), a name template or a custom format can't be set from outside |
| `GET /api/queue/status` | `GET /api/v1/queue` (`queue:read`) |
| `GET /api/progress` | `GET /api/v1/events` (`events:read`) |
| `GET /api/status` (listed, never there) | `GET /api/v1/status` |

Settings, history, the vault, backups and the SQL console have no `/api/v1` counterpart: they stay with
MellowDLP's window.
