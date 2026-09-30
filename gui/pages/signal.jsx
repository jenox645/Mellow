// SIGNAL API page — SQL terminal, schema/API reference, webhooks, live events.
'use strict';

import { API } from '../lib/api.js';
import { SVG } from '../components/icons.jsx';
import { Mascot } from '../components/common.jsx';
import {
  MASCOT_FRUSTRATED, MASCOT_TROUBLESHOOTING_SAFE, MASCOT_VIBING,
} from '../lib/mascots.js';
import { LIVE_EVENTS_KEEP } from '../lib/constants.js';

const PRESET_QUERIES = [
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
  { label: 'Downloads per library folder', sql: "SELECT l.name as library, l.folder,\n  COUNT(d.id) as downloads,\n  SUM(d.file_size_bytes) as total_bytes,\n  MAX(d.timestamp) as last_download\nFROM library l\nLEFT JOIN downloads d ON d.file_path LIKE l.folder || '%'\n  AND d.status='success'\nGROUP BY l.id, l.name, l.folder\nORDER BY downloads DESC" },
  { label: 'Duplicates by title', sql: "SELECT title, COUNT(*) as count, SUM(file_size_bytes) as wasted_bytes\nFROM downloads\nWHERE status='success' AND title IS NOT NULL\nGROUP BY title\nHAVING COUNT(*) > 1\nORDER BY wasted_bytes DESC\nLIMIT 20" },
  { label: 'Audio vs Video split', sql: "SELECT\n  CASE WHEN format IN ('mp3','aac','flac','m4a','opus','wav') THEN 'audio' ELSE 'video' END as type,\n  COUNT(*) as count,\n  SUM(file_size_bytes) as total_bytes\nFROM downloads\nWHERE status='success'\nGROUP BY type" },
  { label: 'Download speed stats', sql: "SELECT\n  DATE_TRUNC('day', timestamp) as day,\n  AVG(download_speed_avg_bps) / 1048576.0 as avg_mbps,\n  MAX(download_speed_avg_bps) / 1048576.0 as peak_mbps,\n  COUNT(*) as count\nFROM downloads\nWHERE status='success' AND download_speed_avg_bps IS NOT NULL\nGROUP BY day\nORDER BY day DESC\nLIMIT 14" },
  { label: 'Longest downloads (time)', sql: "SELECT title, platform, format, elapsed_seconds,\n  file_size_bytes, timestamp\nFROM downloads\nWHERE status='success' AND elapsed_seconds IS NOT NULL\nORDER BY elapsed_seconds DESC\nLIMIT 10" },
];

const SCHEMA_TEXT = `-- downloads
  id INTEGER PK, url TEXT, title TEXT, uploader TEXT,
  platform TEXT, duration_seconds INTEGER,
  file_size_bytes BIGINT, format TEXT, quality TEXT,
  container TEXT, file_path TEXT,
  timestamp TIMESTAMP, status TEXT,
  error_message TEXT, download_speed_avg_bps BIGINT,
  elapsed_seconds INTEGER

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

export function SignalApiPage() {
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
  const liveEventsRef = React.useRef(null);
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

  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">APIシグナル / SIGNAL API</div>
          <div className="vtitle"><span style={{ color: 'var(--t1)' }}>SIGNAL</span> <span className="a">API</span></div>
        </div>
        <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)', textAlign: 'right' }}>
          LIVE QUERY TERMINAL<br />
          <span style={{ color: 'var(--amber)' }}>LOCAL DATA LAKE ONLY</span>
        </div>
      </div>

      <div className="terminal-layout">
        {/* PRESET LIST */}
        <div className="preset-panel">
          <div className="ph">
            <span className="ptag amber">PRESETS</span>
            <span className="ptitle">QUICK QUERIES</span>
          </div>
          {PRESET_QUERIES.map((p, i) => (
            <div
              key={i}
              className={'preset-item' + (activePreset === i ? ' active' : '')}
              onClick={() => { setActivePreset(i); setSql(p.sql); }}
            >
              {p.label}
            </div>
          ))}
        </div>

        {/* QUERY PANEL */}
        <div className="query-panel">
          <div className="query-area">
            <div className="inp-label" style={{ marginBottom: 6 }}>SQL QUERY (SELECT ONLY)</div>
            <textarea
              className="query-textarea"
              value={sql}
              onChange={e => { setSql(e.target.value); setActivePreset(-1); }}
              spellCheck={false}
            />
          </div>
          <div className="query-footer">
            <button className="btn btn-primary btn-sm" onClick={runQuery} disabled={running}>
              {running ? 'EXECUTING...' : 'EXECUTE'}
            </button>
            {result && !result.error && (
              <>
                <div className="query-time">
                  {result.row_count} rows · {result.time_ms}ms
                </div>
                <button className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto' }} onClick={handleExportResult}>
                  EXPORT RESULT
                </button>
              </>
            )}
          </div>

          <div className="results-area">
            {result && result.error ? (
              <div className="error-state">
                <img src={MASCOT_FRUSTRATED} className="error-mascot" alt="" />
                <div className="error-msg">{result.error}</div>
              </div>
            ) : result && result.columns && result.columns.length > 0 ? (
              <table className="data-table" style={{ minWidth: '100%' }}>
                <thead>
                  <tr>{result.columns.map(c => <th key={c}>{c.toUpperCase()}</th>)}</tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td key={j} className="mono">
                          {cell === null ? <span style={{ color: 'var(--t4)' }}>NULL</span>
                            : typeof cell === 'number' ? cell.toLocaleString()
                            : String(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : !running ? (
              <div className="error-state">
                <Mascot src={MASCOT_TROUBLESHOOTING_SAFE || MASCOT_VIBING} className="error-mascot" wrapClass="error-mascot" style={{ width: 80 }} />
                <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t3)', textAlign: 'center' }}>
                  SELECT A PRESET OR WRITE A QUERY
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {/* SCHEMA */}
      <div style={{ marginTop: 16 }}>
        <div className="opts-adv-toggle" style={{ padding: '10px 0', borderTop: '1px solid var(--border)' }}
          onClick={() => setSchemaOpen(o => !o)}>
          <span dangerouslySetInnerHTML={{ __html: schemaOpen ? SVG.chevron_down : SVG.chevron_right }} />
          SCHEMA REFERENCE
        </div>
        {schemaOpen && <div className="schema-block">{SCHEMA_TEXT}</div>}
      </div>

      {/* REST API DOCS */}
      <div style={{ marginTop: 4 }}>
        <div className="opts-adv-toggle" style={{ padding: '10px 0', borderTop: '1px solid var(--border)' }}
          onClick={() => setDocsOpen(o => !o)}>
          <span dangerouslySetInnerHTML={{ __html: docsOpen ? SVG.chevron_down : SVG.chevron_right }} />
          API REFERENCE
        </div>
        {docsOpen && (
          <div className="schema-block" style={{ fontSize: 10, lineHeight: 1.8 }}>
            {[
              ['GET',  '/api/status',        'System status + yt-dlp version'],
              ['GET',  '/api/stats',          'Download statistics'],
              ['GET',  '/api/queue/status',   'Current job queue'],
              ['POST', '/api/download',       'Start download  {url, mode, quality, container, audio_format, ...}'],
              ['POST', '/api/cancel',         'Cancel active download'],
              ['POST', '/api/download/pause', 'Pause active download'],
              ['POST', '/api/download/resume','Resume paused download'],
              ['GET',  '/api/vault',          'Vault folder list'],
              ['POST', '/api/vault/sync',     'Sync vault folder  {path, quality, container, sync_audio, audio_format}'],
              ['GET',  '/api/history',        'Download history  ?limit=50&offset=0&search='],
              ['GET',  '/api/progress',       'SSE event stream (text/event-stream)'],
              ['POST', '/api/queue/{id}/reorder', 'Move a queued job  {index}'],
              ['GET',  '/api/vault/stream',   'Range-aware media streaming  ?path='],
              ['GET',  '/api/vault/duplicates', 'Cross-folder duplicate scan'],
              ['GET',  '/api/analytics/wrapped', 'Year in review  ?year=2026'],
              ['GET',  '/api/backup',         'Download config+DB backup zip'],
              ['POST', '/api/backup/restore', 'Restore from a backup zip (multipart)'],
            ].map(([method, path, desc]) => (
              <div key={path} style={{ display: 'flex', gap: 8, padding: '2px 0' }}>
                <span style={{ color: method === 'GET' ? 'var(--cyan)' : 'var(--amber)', minWidth: 36 }}>{method}</span>
                <span style={{ color: 'var(--t1)', minWidth: 220 }}>{path}</span>
                <span style={{ color: 'var(--t4)' }}>{desc}</span>
              </div>
            ))}
            <div style={{ marginTop: 8, color: 'var(--t3)' }}>
              Base URL: <span style={{ color: 'var(--cyan)' }}>{window.location.origin}</span>
              <button className="btn btn-secondary btn-sm" style={{ marginLeft: 12 }}
                onClick={() => navigator.clipboard.writeText(window.location.origin).catch(() => {})}>
                COPY
              </button>
            </div>
          </div>
        )}
      </div>

      {/* OUTBOUND WEBHOOKS */}
      <div style={{ marginTop: 4 }}>
        <div className="opts-adv-toggle" style={{ padding: '10px 0', borderTop: '1px solid var(--border)' }}
          onClick={() => setWebhooksOpen(o => !o)}>
          <span dangerouslySetInnerHTML={{ __html: webhooksOpen ? SVG.chevron_down : SVG.chevron_right }} />
          OUTBOUND WEBHOOKS
        </div>
        {webhooksOpen && (
          <div style={{ padding: '8px 0', fontFamily: 'Share Tech Mono, monospace', fontSize: 10 }}>
            <div style={{ color: 'var(--t4)', marginBottom: 8 }}>POST JSON to external URLs on download events</div>
            {[['complete', whCompleteUrl, setWhCompleteUrl], ['error', whErrorUrl, setWhErrorUrl]].map(([evt, val, setVal]) => (
              <div key={evt} style={{ marginBottom: 12 }}>
                <div style={{ color: 'var(--t3)', marginBottom: 4 }}>ON {evt.toUpperCase()}</div>
                {(webhooks[evt] || []).map(url => (
                  <div key={url} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ flex: 1, color: 'var(--cyan)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{url}</span>
                    <span style={{ cursor: 'pointer', color: 'var(--red)' }} onClick={() => removeWebhook(evt, url)}>✕</span>
                  </div>
                ))}
                <div style={{ display: 'flex', gap: 6 }}>
                  <input className="form-input" style={{ flex: 1 }} value={val}
                    onChange={e => setVal(e.target.value)} placeholder="https://hooks.example.com/..." />
                </div>
              </div>
            ))}
            <button className="btn btn-primary btn-sm" onClick={saveWebhooks} disabled={whSaving}>
              {whSaving ? 'SAVING...' : 'SAVE WEBHOOKS'}
            </button>
          </div>
        )}
      </div>

      {/* LIVE EVENT STREAM */}
      <div style={{ marginTop: 4 }}>
        <div className="opts-adv-toggle" style={{ padding: '10px 0', borderTop: '1px solid var(--border)' }}
          onClick={() => setEventsOpen(o => !o)}>
          <span dangerouslySetInnerHTML={{ __html: eventsOpen ? SVG.chevron_down : SVG.chevron_right }} />
          LIVE EVENT STREAM {eventsOpen && <span style={{ color: 'var(--cyan)', fontSize: 9, marginLeft: 8 }}>● CONNECTED</span>}
        </div>
        {eventsOpen && (
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', padding: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
              <button className="btn btn-secondary btn-sm" onClick={() => setLiveEvents([])}>CLEAR</button>
            </div>
            <div ref={liveEventsRef} style={{ maxHeight: 220, overflow: 'auto', fontFamily: 'Share Tech Mono, monospace', fontSize: 9 }}>
              {liveEvents.length === 0
                ? <div style={{ color: 'var(--t4)', textAlign: 'center', padding: 12 }}>Waiting for events...</div>
                : liveEvents.map((ev, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, padding: '2px 0', borderBottom: '1px solid var(--border)' }}>
                    <span style={{ color: 'var(--t4)', flexShrink: 0 }}>{ev.ts}</span>
                    <span style={{ color: 'var(--amber)', flexShrink: 0, minWidth: 80 }}>{ev.status}</span>
                    <span style={{ color: 'var(--t2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {ev.title || ev.message || ev.current_item_title || (ev.pct !== undefined ? ev.pct + '%' : '')}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
