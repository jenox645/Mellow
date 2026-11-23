// The Signal API page's logic: its state, effects, API calls and handlers, shared by every theme.
// useSignalPage(props) takes what the App hands the page and returns everything a view
// draws and every handler it calls (the view itself never calls the API).
'use strict';

import { API } from '../lib/api.js';
import { LIVE_EVENTS_KEEP } from '../lib/constants.js';

export const PRESET_QUERIES = [
  { label: 'Most downloaded channels', sql: "SELECT uploader, COUNT(*) as downloads, SUM(file_size_bytes) as total_bytes\nFROM downloads\nWHERE status='success' AND uploader IS NOT NULL\nGROUP BY uploader\nORDER BY downloads DESC\nLIMIT 15" },
  { label: 'Storage by format', sql: "SELECT format, COUNT(*) as count, SUM(file_size_bytes) as total_bytes, AVG(file_size_bytes) as avg_bytes\nFROM downloads\nWHERE status='success'\nGROUP BY format\nORDER BY total_bytes DESC" },
  { label: 'Downloads this week', sql: "SELECT strftime(timestamp, '%Y-%m-%d') as day, COUNT(*) as downloads\nFROM downloads\nWHERE status='success'\n  AND timestamp >= now() - INTERVAL '7 days'\nGROUP BY day\nORDER BY day DESC" },
  { label: 'Largest files', sql: "SELECT title, format, quality, file_size_bytes, timestamp\nFROM downloads\nWHERE status='success' AND file_size_bytes IS NOT NULL\nORDER BY file_size_bytes DESC\nLIMIT 10" },
  { label: 'Failed downloads', sql: "SELECT title, url, error_message, timestamp\nFROM downloads\nWHERE status='error'\nORDER BY timestamp DESC\nLIMIT 20" },
  { label: 'Downloads by hour', sql: "SELECT EXTRACT(hour FROM timestamp)::INTEGER as hour, COUNT(*) as count\nFROM downloads\nWHERE status='success'\nGROUP BY hour\nORDER BY hour" },
  { label: 'Platform breakdown', sql: "SELECT platform, COUNT(*) as downloads,\n  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as pct\nFROM downloads\nWHERE status='success'\nGROUP BY platform\nORDER BY downloads DESC" },
  { label: 'All downloads', sql: "SELECT id, title, platform, format, quality,\n  file_size_bytes, timestamp, status\nFROM downloads\nORDER BY timestamp DESC\nLIMIT 50" },
  { label: 'Library folders & linked playlists', sql: "SELECT l.name, l.folder, l.quality, l.mode,\n  l.embed_thumbnail, l.embed_subs, l.sponsorblock,\n  l.last_synced,\n  (SELECT COUNT(*) FROM sync_log sl WHERE sl.library_id = l.id) as total_syncs\nFROM library l\nORDER BY l.last_synced DESC NULLS LAST" },
  { label: 'Sync history (all runs)', sql: "SELECT l.name as folder, sl.synced_at, sl.new_items,\n  sl.skipped, sl.errors, sl.duration_seconds\nFROM sync_log sl\nJOIN library l ON l.id = sl.library_id\nORDER BY sl.synced_at DESC\nLIMIT 30" },
  { label: 'Downloads per library folder', sql: "-- An entry's files live in folder/folder_name when it uses a subfolder\nSELECT l.name as library, l.folder,\n  COUNT(d.id) as downloads,\n  SUM(d.file_size_bytes) as total_bytes,\n  MAX(d.timestamp) as last_download\nFROM library l\nLEFT JOIN downloads d\n  ON replace(d.file_path, '\\', '/') LIKE replace(l.folder, '\\', '/')\n     || CASE WHEN l.use_subfolder AND coalesce(l.folder_name, '') <> ''\n             THEN '/' || l.folder_name ELSE '' END || '/%'\n  AND d.status='success'\nGROUP BY l.id, l.name, l.folder\nORDER BY downloads DESC" },
  { label: 'Duplicates by title', sql: "-- wasted = every copy but the largest\nSELECT title, COUNT(*) as count,\n  SUM(file_size_bytes) - MAX(file_size_bytes) as wasted_bytes\nFROM downloads\nWHERE status='success' AND title IS NOT NULL\nGROUP BY title\nHAVING COUNT(*) > 1\nORDER BY wasted_bytes DESC\nLIMIT 20" },
  { label: 'Audio vs Video split', sql: "-- format is 'audio' or 'video'; container is the file type\nSELECT format as type, COUNT(*) as count,\n  SUM(file_size_bytes) as total_bytes,\n  string_agg(DISTINCT container, ', ') as containers\nFROM downloads\nWHERE status='success'\nGROUP BY format" },
  { label: 'Download speed stats', sql: "SELECT\n  DATE_TRUNC('day', timestamp) as day,\n  AVG(download_speed_avg_bps) / 1048576.0 as avg_mbps,\n  MAX(download_speed_avg_bps) / 1048576.0 as peak_mbps,\n  COUNT(*) as count\nFROM downloads\nWHERE status='success' AND download_speed_avg_bps IS NOT NULL\nGROUP BY day\nORDER BY day DESC\nLIMIT 14" },
  { label: 'Longest downloads (time)', sql: "SELECT title, platform, format, elapsed_seconds,\n  file_size_bytes, timestamp\nFROM downloads\nWHERE status='success' AND elapsed_seconds IS NOT NULL\nORDER BY elapsed_seconds DESC\nLIMIT 10" },
];

export const SCHEMA_TEXT = `-- downloads
  id INTEGER PK, url TEXT, title TEXT, uploader TEXT,
  platform TEXT, duration_seconds INTEGER,
  file_size_bytes BIGINT, format TEXT, quality TEXT,
  container TEXT, file_path TEXT,
  timestamp TIMESTAMP, status TEXT,
  error_message TEXT, download_speed_avg_bps BIGINT,
  elapsed_seconds INTEGER, thumbnail_url TEXT,
  video_id TEXT  -- the site's id of the item (from 2.10.0)

-- library
  id TEXT PK, name TEXT, url TEXT,
  folder TEXT, folder_name TEXT, use_subfolder BOOLEAN,
  quality TEXT, mode TEXT, embed_thumbnail BOOLEAN,
  embed_chapters BOOLEAN, embed_metadata BOOLEAN,
  embed_subs BOOLEAN, sub_langs TEXT,
  sponsorblock BOOLEAN, filename_template TEXT,
  sync_mode TEXT, last_synced TIMESTAMP, created_at TIMESTAMP,
  container TEXT, audio_format TEXT

-- sync_log
  id INTEGER PK, library_id TEXT FK,
  synced_at TIMESTAMP, new_items INTEGER,
  skipped INTEGER, errors INTEGER, duration_seconds INTEGER`;

export function useSignalPage(props) {
  const [sql, setSql] = React.useState(PRESET_QUERIES[0].sql);
  const [activePreset, setActivePreset] = React.useState(0);
  const [result, setResult] = React.useState(null);
  const [running, setRunning] = React.useState(false);
  const [schemaOpen, setSchemaOpen] = React.useState(false);
  const [docsOpen, setDocsOpen] = React.useState(false);
  const [webhooksOpen, setWebhooksOpen] = React.useState(false);
  const [eventsOpen, setEventsOpen] = React.useState(false);
  const [webhooks, setWebhooks] = React.useState({ complete: [], error: [] });
  const [whCompleteUrl, setWhCompleteUrl] = React.useState('');
  const [whErrorUrl, setWhErrorUrl] = React.useState('');
  const [whSaving, setWhSaving] = React.useState(false);
  const [liveEvents, setLiveEvents] = React.useState([]);
  const liveEsRef = React.useRef(null);

  React.useEffect(() => {
    API.get('/api/webhooks').then(setWebhooks).catch(() => {});
  }, []);

  React.useEffect(() => {
    if (!eventsOpen) {
      if (liveEsRef.current) { liveEsRef.current.close(); liveEsRef.current = null; }
      return;
    }
    const es = new EventSource('/api/progress');
    liveEsRef.current = es;
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d.status === 'ping') return;
        setLiveEvents(prev => {
          const entry = { ts: new Date().toLocaleTimeString(), ...d };
          return [entry, ...prev].slice(0, LIVE_EVENTS_KEEP);
        });
      } catch {}
    };
    return () => { es.close(); liveEsRef.current = null; };
  }, [eventsOpen]);

  const saveWebhooks = () => {
    // Append the typed URL — replacing the whole list made multiple webhooks
    // per event impossible despite the list UI
    const appendTo = (list, url) => {
      const u = url.trim();
      return u && !list.includes(u) ? [...list, u] : list;
    };
    const updated = {
      complete: appendTo(webhooks.complete || [], whCompleteUrl),
      error: appendTo(webhooks.error || [], whErrorUrl),
    };
    setWhSaving(true);
    API.post('/api/webhooks', updated)
      .then(() => { setWebhooks(updated); setWhCompleteUrl(''); setWhErrorUrl(''); })
      .catch(() => {})
      .finally(() => setWhSaving(false));
  };

  const removeWebhook = (type, url) => {
    const updated = { ...webhooks, [type]: webhooks[type].filter(u => u !== url) };
    API.post('/api/webhooks', updated).then(() => setWebhooks(updated)).catch(() => {});
  };

  const runQuery = React.useCallback(() => {
    if (!sql.trim()) return;
    setRunning(true);
    setResult(null);
    API.post('/api/analytics/query', { sql })
      .then(setResult)
      .catch(e => setResult({ error: e.message, columns: [], rows: [] }))
      .finally(() => setRunning(false));
  }, [sql]);

  const handleExportResult = React.useCallback(() => {
    if (!result || !result.columns) return;
    const rows = [result.columns.join(','), ...result.rows.map(r => r.map(c => JSON.stringify(c ?? '')).join(','))];
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'query_result.csv'; a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  // A preset fills the editor; typing makes it the user's own query
  const pickPreset = i => { setActivePreset(i); setSql(PRESET_QUERIES[i].sql); };
  const editSql = text => { setSql(text); setActivePreset(-1); };

  // API REFERENCE: the address other programs use, and its COPY
  const baseUrl = window.location.origin;
  const copyBaseUrl = () => navigator.clipboard.writeText(baseUrl).catch(() => {});

  return {
    ...props,
    // the SQL terminal
    presets: PRESET_QUERIES, activePreset, pickPreset, sql, editSql, runQuery, running, result, handleExportResult,
    // the folding sections
    schemaOpen, setSchemaOpen, schemaText: SCHEMA_TEXT, docsOpen, setDocsOpen, webhooksOpen, setWebhooksOpen,
    eventsOpen, setEventsOpen,
    // API REFERENCE
    baseUrl, copyBaseUrl,
    // OUTBOUND WEBHOOKS
    webhooks, whCompleteUrl, setWhCompleteUrl, whErrorUrl, setWhErrorUrl, whSaving, saveWebhooks, removeWebhook,
    // LIVE EVENT STREAM (open while its section is)
    liveEvents, clearLiveEvents: () => setLiveEvents([]),
  };
}
