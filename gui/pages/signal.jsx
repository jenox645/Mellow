// SIGNAL API page — SQL terminal, schema/API reference, webhooks, live events.
// The logic is useSignalPage (signal-logic.js); this file is Classic's view of it. A theme can
// register its own view of the page (gui/themes/slots.jsx, `pages: { signal: … }`).
'use strict';

import { SVG } from '../components/icons.jsx';
import { Mascot } from '../components/common.jsx';
import {
  MASCOT_FRUSTRATED, MASCOT_TROUBLESHOOTING_SAFE, MASCOT_VIBING,
} from '../lib/mascots.js';
import { useSignalPage } from './signal-logic.js';

// The Signal API page: its logic, drawn by the theme's view (Classic's unless the theme has one)
export function SignalApiPage({ View = ClassicSignalView, ...props }) {
  const signal = useSignalPage(props);
  return <View {...signal} />;
}

export function ClassicSignalView({
  presets, activePreset, pickPreset, sql, editSql, runQuery, running, result, handleExportResult, schemaOpen,
  setSchemaOpen, schemaText, docsOpen, setDocsOpen, webhooksOpen, setWebhooksOpen, eventsOpen, setEventsOpen, baseUrl,
  copyBaseUrl, webhooks, whCompleteUrl, setWhCompleteUrl, whErrorUrl, setWhErrorUrl, whSaving, saveWebhooks,
  removeWebhook, liveEvents, clearLiveEvents,
}) {
  const liveEventsRef = React.useRef(null);

  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">APIシグナル / SIGNAL API</div>
          <div className="vtitle"><span style={{ color: 'var(--t1)' }}>SIGNAL</span> <span className="a">API</span></div>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--t4)', textAlign: 'right' }}>
          LIVE QUERY TERMINAL<br />
          <span style={{ color: 'var(--accent-2)' }}>LOCAL DATA LAKE ONLY</span>
        </div>
      </div>

      <div className="terminal-layout">
        {/* PRESET LIST */}
        <div className="preset-panel" data-tour="signal-presets">
          <div className="ph">
            <span className="ptag amber">PRESETS</span>
            <span className="ptitle">QUICK QUERIES</span>
          </div>
          {presets.map((p, i) => (
            <div
              key={i}
              className={'preset-item' + (activePreset === i ? ' active' : '')}
              onClick={() => pickPreset(i)}
            >
              {p.label}
            </div>
          ))}
        </div>

        {/* QUERY PANEL */}
        <div className="query-panel" data-tour="signal-query">
          <div className="query-area">
            <div className="inp-label" style={{ marginBottom: 6 }}>SQL QUERY (SELECT ONLY)</div>
            <textarea
              className="query-textarea"
              value={sql}
              onChange={e => editSql(e.target.value)}
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
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--t3)', textAlign: 'center' }}>
                  SELECT A PRESET OR WRITE A QUERY
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {/* SCHEMA */}
      <div data-tour="signal-schema" style={{ marginTop: 16 }}>
        <div className="opts-adv-toggle" style={{ padding: '10px 0', borderTop: '1px solid var(--border)' }}
          onClick={() => setSchemaOpen(o => !o)}>
          <span dangerouslySetInnerHTML={{ __html: schemaOpen ? SVG.chevron_down : SVG.chevron_right }} />
          SCHEMA REFERENCE
        </div>
        {schemaOpen && <div className="schema-block">{schemaText}</div>}
      </div>

      {/* REST API DOCS */}
      <div data-tour="signal-api" style={{ marginTop: 4 }}>
        <div className="opts-adv-toggle" style={{ padding: '10px 0', borderTop: '1px solid var(--border)' }}
          onClick={() => setDocsOpen(o => !o)}>
          <span dangerouslySetInnerHTML={{ __html: docsOpen ? SVG.chevron_down : SVG.chevron_right }} />
          API REFERENCE
        </div>
        {docsOpen && (
          <div className="schema-block" style={{ fontSize: 11, lineHeight: 1.8 }}>
            <div style={{ color: 'var(--t3)', marginBottom: 6 }}>
              For programs on this computer. Every request sends <span style={{ color: 'var(--t1)' }}>Authorization: Bearer &lt;key&gt;</span>;
              make a key, and choose what it may do, in Config → API ACCESS.
            </div>
            {[
              ['GET',  '/api/v1/status',    'any key',          'App and yt-dlp versions, queued and active downloads'],
              ['POST', '/api/v1/downloads', 'downloads:create', 'Queue a download  {url, mode?, quality?, container?, audio_format?, audio_quality?}'],
              ['GET',  '/api/v1/queue',     'queue:read',       'The queue: each job\'s link, label and status'],
              ['GET',  '/api/v1/events',    'events:read',      'Progress as server-sent events (text/event-stream)'],
            ].map(([method, path, scope, desc]) => (
              <div key={path} style={{ display: 'flex', gap: 8, padding: '2px 0' }}>
                <span style={{ color: method === 'GET' ? 'var(--accent)' : 'var(--accent-2)', minWidth: 36 }}>{method}</span>
                <span style={{ color: 'var(--t1)', minWidth: 150 }}>{path}</span>
                <span style={{ color: 'var(--accent-3)', minWidth: 110 }}>{scope}</span>
                <span style={{ color: 'var(--t4)' }}>{desc}</span>
              </div>
            ))}
            <div style={{ marginTop: 6, color: 'var(--t4)' }}>
              Downloads go to the download folder with your Config defaults. Settings, files, history and
              backups are for MellowDLP's own window only.
            </div>
            <div style={{ marginTop: 8, color: 'var(--t3)' }}>
              Base URL: <span style={{ color: 'var(--accent)' }}>{baseUrl}</span>
              <button className="btn btn-secondary btn-sm" style={{ marginLeft: 12 }}
                onClick={copyBaseUrl}>
                COPY
              </button>
            </div>
          </div>
        )}
      </div>

      {/* OUTBOUND WEBHOOKS */}
      <div data-tour="signal-webhooks" style={{ marginTop: 4 }}>
        <div className="opts-adv-toggle" style={{ padding: '10px 0', borderTop: '1px solid var(--border)' }}
          onClick={() => setWebhooksOpen(o => !o)}>
          <span dangerouslySetInnerHTML={{ __html: webhooksOpen ? SVG.chevron_down : SVG.chevron_right }} />
          OUTBOUND WEBHOOKS
        </div>
        {webhooksOpen && (
          <div style={{ padding: '8px 0', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
            <div style={{ color: 'var(--t4)', marginBottom: 8 }}>POST JSON to external URLs on download events</div>
            {[['complete', whCompleteUrl, setWhCompleteUrl], ['error', whErrorUrl, setWhErrorUrl]].map(([evt, val, setVal]) => (
              <div key={evt} style={{ marginBottom: 12 }}>
                <div style={{ color: 'var(--t3)', marginBottom: 4 }}>ON {evt.toUpperCase()}</div>
                {(webhooks[evt] || []).map(url => (
                  <div key={url} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ flex: 1, color: 'var(--accent)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{url}</span>
                    <span style={{ cursor: 'pointer', color: 'var(--danger)' }} onClick={() => removeWebhook(evt, url)}>✕</span>
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
      <div data-tour="signal-events" style={{ marginTop: 4 }}>
        <div className="opts-adv-toggle" style={{ padding: '10px 0', borderTop: '1px solid var(--border)' }}
          onClick={() => setEventsOpen(o => !o)}>
          <span dangerouslySetInnerHTML={{ __html: eventsOpen ? SVG.chevron_down : SVG.chevron_right }} />
          LIVE EVENT STREAM {eventsOpen && <span style={{ color: 'var(--accent)', fontSize: 10.5, marginLeft: 8 }}>● CONNECTED</span>}
        </div>
        {eventsOpen && (
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', padding: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
              <button className="btn btn-secondary btn-sm" onClick={clearLiveEvents}>CLEAR</button>
            </div>
            <div ref={liveEventsRef} style={{ maxHeight: 220, overflow: 'auto', fontFamily: 'var(--font-mono)', fontSize: 10.5 }}>
              {liveEvents.length === 0
                ? <div style={{ color: 'var(--t4)', textAlign: 'center', padding: 12 }}>Waiting for events...</div>
                : liveEvents.map((ev, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, padding: '2px 0', borderBottom: '1px solid var(--border)' }}>
                    <span style={{ color: 'var(--t4)', flexShrink: 0 }}>{ev.ts}</span>
                    <span style={{ color: 'var(--accent-2)', flexShrink: 0, minWidth: 80 }}>{ev.status}</span>
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
