// ANALYTICS page — KPI cards, charts, sync health, history browser.
'use strict';

import { API } from '../lib/api.js';
import {
  fmtBytes, fmtSpeed, fmtEta, fmtDate, fmtTimestamp, timeAgo, platformTagClass,
} from '../lib/util.js';
import { Ico } from '../components/icons.jsx';
import { EditableStat, LineChart, Modal } from '../components/common.jsx';
import { HISTORY_LIMIT, HISTORY_SEARCH_DEBOUNCE_MS } from '../lib/constants.js';

const MONTH_LABELS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

// Year-in-review card — one DuckDB query of pure novelty
function WrappedModal({ onClose }) {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = React.useState(currentYear);
  const [data, setData] = React.useState(null);

  React.useEffect(() => {
    setData(null);
    API.get('/api/analytics/wrapped?year=' + year).then(setData).catch(() => setData({ error: true }));
  }, [year]);

  const maxMonthly = data && data.monthly ? Math.max(...data.monthly, 1) : 1;

  return (
    <Modal title={'✦ MELLOW WRAPPED ' + year} onClose={onClose} footer={
      <>
        <button className="btn btn-secondary btn-sm" onClick={() => setYear(y => y - 1)}>‹ {year - 1}</button>
        {year < currentYear && (
          <button className="btn btn-secondary btn-sm" onClick={() => setYear(y => y + 1)}>{year + 1} ›</button>
        )}
        <button className="btn btn-primary btn-sm" onClick={onClose}>CLOSE</button>
      </>
    }>
      {!data ? (
        <div style={{ padding: 24, textAlign: 'center', fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t3)' }}>CRUNCHING THE NUMBERS...</div>
      ) : data.error || !data.total_downloads ? (
        <div style={{ padding: 24, textAlign: 'center', fontFamily: 'Share Tech Mono, monospace', fontSize: 10, color: 'var(--t3)' }}>
          NOTHING DOWNLOADED IN {year} — A QUIET YEAR.
        </div>
      ) : (
        <div style={{ fontFamily: 'Share Tech Mono, monospace' }}>
          <div className="g2" style={{ marginBottom: 10 }}>
            <div className="stat">
              <div className="stat-label">DOWNLOADS</div>
              <div className="stat-value cyan">{data.total_downloads.toLocaleString()}</div>
            </div>
            <div className="stat">
              <div className="stat-label">HOURS OF MEDIA</div>
              <div className="stat-value amber">{Math.round(data.total_duration_seconds / 3600).toLocaleString()}h</div>
            </div>
          </div>
          <div className="g2" style={{ marginBottom: 10 }}>
            <div className="stat">
              <div className="stat-label">STORAGE</div>
              <div className="stat-value green">{fmtBytes(data.total_size_bytes)}</div>
            </div>
            <div className="stat">
              <div className="stat-label">SUCCESS RATE</div>
              <div className="stat-value cyan">{data.success_rate !== null ? data.success_rate + '%' : '—'}</div>
            </div>
          </div>
          {(data.top_uploaders || []).length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 9, color: 'var(--amber)', letterSpacing: '0.1em', marginBottom: 4 }}>TOP CHANNELS</div>
              {data.top_uploaders.map((u, i) => (
                <div key={u.uploader} style={{ display: 'flex', gap: 8, fontSize: 10, padding: '2px 0' }}>
                  <span style={{ color: 'var(--t4)', minWidth: 18 }}>#{i + 1}</span>
                  <span style={{ flex: 1, color: i === 0 ? 'var(--cyan)' : 'var(--t2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.uploader}</span>
                  <span style={{ color: 'var(--t3)' }}>{u.count}</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 9, color: 'var(--amber)', letterSpacing: '0.1em', marginBottom: 4 }}>MONTH BY MONTH</div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 50 }}>
              {(data.monthly || []).map((v, i) => (
                <div key={i} style={{ flex: 1, textAlign: 'center' }} title={`${v} downloads`}>
                  <div style={{ height: Math.max(2, (v / maxMonthly) * 40), background: 'var(--cyan)', opacity: 0.35 + (v / maxMonthly) * 0.65 }} />
                  <div style={{ fontSize: 7, color: 'var(--t4)', marginTop: 2 }}>{MONTH_LABELS[i]}</div>
                </div>
              ))}
            </div>
          </div>
          {data.busiest_day && (
            <div style={{ fontSize: 9, color: 'var(--t3)' }}>
              Busiest day: <span style={{ color: 'var(--cyan)' }}>{data.busiest_day.day}</span> with {data.busiest_day.count} downloads
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

function HistoryPanel({ showNotif, refreshStats }) {
  const [rows, setRows] = React.useState([]);
  const [search, setSearch] = React.useState('');
  const [typeFilter, setTypeFilter] = React.useState('all');
  const [offset, setOffset] = React.useState(0);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ limit: HISTORY_LIMIT, offset, type: typeFilter });
    if (search.trim()) params.set('search', search.trim());
    API.get('/api/history?' + params.toString())
      .then(d => setRows(Array.isArray(d) ? d : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [search, typeFilter, offset]);

  React.useEffect(() => {
    const t = setTimeout(load, HISTORY_SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [load]);

  const redownload = (r) => {
    API.post('/api/download', { url: r.url, mode: r.format === 'audio' ? 'audio' : 'video', quality: r.quality || 'best' })
      .then(d => d.error ? showNotif('Error', d.error, 'error') : showNotif('Re-queued', r.title || r.url))
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const openFile = (r) => {
    API.post('/api/vault/open-file', { path: r.file_path }).catch(() => {});
  };

  const deleteRow = (r) => {
    API.del('/api/history', { ids: [r.id] })
      .then(() => { setRows(rs => rs.filter(x => x.id !== r.id)); refreshStats && refreshStats(); })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  return (
    <div className="chart-panel" style={{ marginTop: 16 }}>
      <div className="chart-title">History Browser</div>
      <div className="chart-sub">FULL DOWNLOAD HISTORY — SEARCH · REDOWNLOAD · OPEN</div>
      <div style={{ display: 'flex', gap: 8, margin: '8px 0', alignItems: 'center' }}>
        <input
          className="inp-sm" style={{ flex: 1, maxWidth: 320 }}
          placeholder="Search title / url / uploader..."
          value={search}
          onChange={e => { setSearch(e.target.value); setOffset(0); }}
        />
        <select className="sel" value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setOffset(0); }}>
          <option value="all">ALL TYPES</option>
          <option value="video">VIDEO</option>
          <option value="audio">AUDIO</option>
        </select>
        <span style={{ marginLeft: 'auto', fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)' }}>
          {offset + 1}–{offset + rows.length}
        </span>
        <button className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => setOffset(o => Math.max(0, o - HISTORY_LIMIT))}>‹ PREV</button>
        <button className="btn btn-secondary btn-sm" disabled={rows.length < HISTORY_LIMIT} onClick={() => setOffset(o => o + HISTORY_LIMIT)}>NEXT ›</button>
      </div>
      <table className="data-table">
        <thead>
          <tr><th>TITLE</th><th>TYPE</th><th>SIZE</th><th>DATE</th><th>STATUS</th><th style={{ textAlign: 'right' }}>ACTIONS</th></tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id}>
              <td style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.url}>
                {r.title || r.url || '—'}
              </td>
              <td className="mono">{(r.format || '—').toUpperCase()}</td>
              <td className="mono">{fmtBytes(r.file_size_bytes)}</td>
              <td className="mono">{fmtDate(r.timestamp)}</td>
              <td>
                <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 8, padding: '2px 6px', color: r.status === 'success' ? 'var(--green)' : 'var(--red)', border: '1px solid', borderColor: r.status === 'success' ? 'rgba(0,255,148,0.3)' : 'rgba(255,59,97,0.3)' }}
                  title={r.error_message || ''}>
                  {(r.status || '').toUpperCase()}
                </span>
              </td>
              <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                {r.url && <button className="btn btn-secondary btn-sm" style={{ padding: '2px 6px', fontSize: 8, marginRight: 4 }} title="Download again" onClick={() => redownload(r)}>↻ DL</button>}
                {r.file_path && <button className="btn btn-secondary btn-sm" style={{ padding: '2px 6px', fontSize: 8, marginRight: 4 }} title="Open file" onClick={() => openFile(r)}>▶ OPEN</button>}
                <button className="btn btn-danger btn-sm" style={{ padding: '2px 6px', fontSize: 8 }} title="Delete record" onClick={() => deleteRow(r)}>✕</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && !loading && (
        <div style={{ padding: '20px', textAlign: 'center', fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)' }}>
          NO MATCHING RECORDS
        </div>
      )}
    </div>
  );
}

export function AnalyticsPage({ stats, refreshStats, showNotif }) {
  const [range, setRange] = React.useState('30d');
  const [wrappedOpen, setWrappedOpen] = React.useState(false);
  const [localStats, setLocalStats] = React.useState(stats);
  const [overrides, setOverrides] = React.useState({});
  const trendRef = React.useRef(null);
  const platformRef = React.useRef(null);
  const donutRef = React.useRef(null);

  React.useEffect(() => {
    API.get('/api/stats?range=' + range)
      .then(setLocalStats)
      .catch(() => {});
  }, [range]);

  React.useEffect(() => {
    setLocalStats(s => ({ ...s, ...stats }));
  }, [stats]);

  React.useEffect(() => {
    API.get('/api/analytics/overrides').then(setOverrides).catch(() => {});
  }, []);

  const saveOverride = React.useCallback((key, val) => {
    const update = { [key]: val };
    setOverrides(o => ({ ...o, ...update }));
    API.post('/api/analytics/overrides', update).catch(() => {});
  }, []);

  // Use override value if present, else computed value
  const statVal = (key, computed) => (key in overrides && overrides[key] !== '' && overrides[key] !== null) ? overrides[key] : computed;

  // Draw trend chart
  React.useEffect(() => {
    const c = trendRef.current;
    if (!c || !localStats.by_day_last_30) return;
    const data = localStats.by_day_last_30;
    if (!data.length) return;
    const w = c.offsetWidth; c.width = w; c.height = 120;
    const ctx = c.getContext('2d');
    const pts = data.map(d => d.count);
    const labels = data.map(d => d.day.slice(5));
    const maxV = Math.max(...pts, 1);
    const pad = { l: 28, r: 8, t: 8, b: 22 };
    const cw = w - pad.l - pad.r, ch = 120 - pad.t - pad.b;
    ctx.clearRect(0, 0, w, 120);
    [0, 0.5, 1].forEach(f => {
      const y = pad.t + ch * (1 - f);
      ctx.strokeStyle = 'rgba(61,96,112,0.25)'; ctx.lineWidth = 0.5; ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + cw, y); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(61,96,112,0.6)'; ctx.font = '8px Share Tech Mono';
      ctx.fillText(Math.round(maxV * f), 0, y + 3);
    });
    const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + ch);
    grad.addColorStop(0, 'rgba(0,216,255,0.2)'); grad.addColorStop(1, 'rgba(0,216,255,0.01)');
    ctx.fillStyle = grad; ctx.beginPath();
    pts.forEach((v, i) => {
      const x = pad.l + i * (cw / (pts.length - 1));
      const y = pad.t + ch * (1 - v / maxV);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.lineTo(pad.l + cw, pad.t + ch); ctx.lineTo(pad.l, pad.t + ch); ctx.closePath(); ctx.fill();
    ctx.strokeStyle = 'rgba(0,216,255,0.85)'; ctx.lineWidth = 1.5; ctx.beginPath();
    pts.forEach((v, i) => {
      const x = pad.l + i * (cw / (pts.length - 1));
      const y = pad.t + ch * (1 - v / maxV);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = 'rgba(61,96,112,0.6)'; ctx.font = '7px Share Tech Mono'; ctx.textAlign = 'center';
    labels.forEach((l, i) => {
      if (i % Math.ceil(labels.length / 8) === 0) {
        const x = pad.l + i * (cw / (pts.length - 1));
        ctx.fillText(l, x, 120 - 5);
      }
    });
  }, [localStats.by_day_last_30]);

  // Draw platform bars
  React.useEffect(() => {
    const c = platformRef.current;
    if (!c || !localStats.by_platform) return;
    const data = localStats.by_platform.slice(0, 6);
    if (!data.length) return;
    const w = c.offsetWidth; c.width = w; c.height = Math.max(data.length * 22 + 16, 80);
    const ctx = c.getContext('2d');
    const maxV = Math.max(...data.map(d => d.count), 1);
    const pad = { l: 80, r: 40, t: 8, b: 8 };
    const cw = w - pad.l - pad.r;
    ctx.clearRect(0, 0, w, c.height);
    const colors = ['rgba(0,216,255,0.85)','rgba(249,169,0,0.85)','rgba(192,132,252,0.85)','rgba(0,255,148,0.7)','rgba(255,59,97,0.7)','rgba(61,96,112,0.7)'];
    data.forEach((p, i) => {
      const y = pad.t + i * 22;
      ctx.fillStyle = 'rgba(138,171,184,0.5)'; ctx.font = '9px Share Tech Mono'; ctx.textAlign = 'right';
      ctx.fillText(p.platform || '—', pad.l - 6, y + 12);
      const bw = (p.count / maxV) * cw;
      ctx.fillStyle = 'rgba(30,58,72,0.5)'; ctx.fillRect(pad.l, y, cw, 14);
      ctx.fillStyle = colors[i % colors.length]; ctx.fillRect(pad.l, y, bw, 14);
      ctx.fillStyle = 'rgba(216,236,245,0.8)'; ctx.textAlign = 'left'; ctx.font = '8px Share Tech Mono';
      ctx.fillText(p.count, pad.l + bw + 4, y + 11);
    });
  }, [localStats.by_platform]);

  // Draw donut
  React.useEffect(() => {
    const c = donutRef.current;
    if (!c || !localStats.storage_by_format) return;
    const data = localStats.storage_by_format.slice(0, 4);
    if (!data.length) return;
    c.width = 140; c.height = 140;
    const ctx = c.getContext('2d');
    const cx = 70, cy = 70, r = 52, ri = 34;
    const total = data.reduce((s, d) => s + d.bytes, 0) || 1;
    const colors = ['rgba(0,216,255,0.9)','rgba(249,169,0,0.9)','rgba(192,132,252,0.9)','rgba(0,255,148,0.7)'];
    let start = -Math.PI / 2;
    data.forEach((d, i) => {
      const sweep = (d.bytes / total) * Math.PI * 2;
      ctx.beginPath(); ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, r, start, start + sweep); ctx.closePath();
      ctx.fillStyle = colors[i]; ctx.fill();
      start += sweep;
    });
    ctx.beginPath(); ctx.arc(cx, cy, ri, 0, Math.PI * 2);
    ctx.fillStyle = 'var(--bg2)'; ctx.fill();
    ctx.fillStyle = 'rgba(0,216,255,0.9)'; ctx.font = 'bold 14px Oxanium'; ctx.textAlign = 'center';
    ctx.fillText(fmtBytes(total), cx, cy + 2);
    ctx.fillStyle = 'rgba(61,96,112,0.9)'; ctx.font = '8px Share Tech Mono';
    ctx.fillText('TOTAL', cx, cy + 14);
  }, [localStats.storage_by_format]);

  const hourly = localStats.hourly_activity || Array(24).fill(0);
  const maxHour = Math.max(...hourly, 1);

  const handleExport = () => {
    window.location.href = '/api/analytics/export';
  };

  return (
    <div className="content active">
      <div className="vhead">
        <div>
          <div className="vlabel">データレイク / DATA LAKE</div>
          <div className="vtitle"><span style={{ color: 'var(--t1)' }}>DATA</span> <span className="a">LAKE</span></div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <div className="range-tabs">
            {['7d','30d','all'].map(r => (
              <div key={r} className={'range-tab' + (range === r ? ' active' : '')} onClick={() => setRange(r)}>
                {r === 'all' ? 'ALL TIME' : r.toUpperCase()}
              </div>
            ))}
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => setWrappedOpen(true)} title="Year in review">
            ✦ WRAPPED
          </button>
          <button className="btn btn-amber btn-sm" onClick={handleExport}>
            <Ico name="download" /> EXPORT CSV
          </button>
        </div>
      </div>

      {wrappedOpen && <WrappedModal onClose={() => setWrappedOpen(false)} />}

      {/* KPI CARDS — click any value to edit/override */}
      <div className="g4" style={{ marginBottom: 16 }}>
        <div className="stat">
          <div className="stat-label">TOTAL DOWNLOADS</div>
          <EditableStat
            value={statVal('total_downloads', localStats.total_downloads || 0)}
            colorClass="cyan"
            format={v => Number(v).toLocaleString()}
            onSave={v => saveOverride('total_downloads', v)}
          />
          <div className="stat-sub">all time</div>
        </div>
        <div className="stat">
          <div className="stat-label">STORAGE USED</div>
          <EditableStat
            value={statVal('total_size_bytes', localStats.total_size_bytes || 0)}
            colorClass="amber"
            format={v => fmtBytes(Number(v))}
            onSave={v => saveOverride('total_size_bytes', v)}
          />
          <div className="stat-sub">disk usage</div>
        </div>
        <div className="stat">
          <div className="stat-label">PLATFORMS</div>
          <EditableStat
            value={statVal('platform_count', (localStats.by_platform || []).length)}
            colorClass="green"
            format={v => String(v)}
            onSave={v => saveOverride('platform_count', v)}
          />
          <div className="stat-sub">distinct sources</div>
        </div>
        <div className="stat">
          <div className="stat-label">AVG SPEED</div>
          <EditableStat
            value={statVal('avg_speed_bps', localStats.avg_speed_bps || 0)}
            colorClass="cyan"
            format={v => fmtSpeed(Number(v))}
            onSave={v => saveOverride('avg_speed_bps', v)}
          />
          <div className="stat-sub">bytes/sec</div>
        </div>
      </div>

      {/* HEALTH KPI ROW */}
      <div className="g4" style={{ marginBottom: 16 }}>
        <div className="stat">
          <div className="stat-label">SUCCESS RATE</div>
          <div className="stat-value green">
            {localStats.success_rate !== null && localStats.success_rate !== undefined ? localStats.success_rate + '%' : '—'}
          </div>
          <div className="stat-sub">of all attempts</div>
        </div>
        <div className="stat">
          <div className="stat-label">CONTENT DURATION</div>
          <div className="stat-value cyan">
            {Math.round((localStats.total_duration_seconds || 0) / 3600).toLocaleString()}h
          </div>
          <div className="stat-sub">hours of media</div>
        </div>
        <div className="stat">
          <div className="stat-label">FAILURES</div>
          <div className="stat-value red">{(localStats.status_counts || {}).error || 0}</div>
          <div className="stat-sub">errored downloads</div>
        </div>
        <div className="stat">
          <div className="stat-label">LAST SYNC</div>
          <div className="stat-value amber" style={{ fontSize: 16 }}>
            {(localStats.sync_runs || []).length ? timeAgo(localStats.sync_runs[0].synced_at) : 'NEVER'}
          </div>
          <div className="stat-sub">{(localStats.sync_runs || []).length} logged runs</div>
        </div>
      </div>

      {/* CHARTS ROW */}
      <div className="g2" style={{ marginBottom: 0 }}>
        <div className="chart-panel">
          <div className="chart-title">Download Trend</div>
          <div className="chart-sub">DOWNLOADS PER DAY — LAST {range.toUpperCase()}</div>
          <canvas ref={trendRef} className="chart" height={120} />
        </div>
        <div className="chart-panel">
          <div className="chart-title">Storage by Format</div>
          <div className="chart-sub">DISK USAGE BREAKDOWN</div>
          <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
            <canvas ref={donutRef} width={140} height={140} />
            <div style={{ flex: 1 }}>
              {(localStats.storage_by_format || []).slice(0, 4).map((f, i) => (
                <div key={f.format} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t2)' }}>
                  <span>{(f.format || '—').toUpperCase()}</span>
                  <span style={{ color: 'var(--cyan)' }}>{fmtBytes(f.bytes)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="g2">
        <div className="chart-panel">
          <div className="chart-title">Platform Breakdown</div>
          <div className="chart-sub">DOWNLOADS BY SOURCE</div>
          <canvas ref={platformRef} className="chart" />
        </div>
        <div className="chart-panel">
          <div className="chart-title">Activity Heatmap</div>
          <div className="chart-sub">DOWNLOADS BY HOUR OF DAY</div>
          <div className="heatmap">
            {hourly.map((v, i) => (
              <div
                key={i}
                className="hm-cell"
                title={`${String(i).padStart(2,'0')}:00 — ${v} downloads`}
                style={{ background: `rgba(0,216,255,${(0.06 + (v / maxHour) * 0.9).toFixed(2)})` }}
              />
            ))}
          </div>
          <div className="hm-labels">
            <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
          </div>
        </div>
      </div>

      {/* STORAGE GROWTH + SPEED TREND */}
      <div className="g2">
        <div className="chart-panel">
          <div className="chart-title">Storage Growth</div>
          <div className="chart-sub">CUMULATIVE DISK USAGE OVER TIME</div>
          <LineChart
            data={(localStats.storage_growth || []).map(d => ({ x: d.day, y: d.bytes }))}
            color="rgba(249,169,0,0.85)"
            yFormat={v => fmtBytes(v)}
          />
        </div>
        <div className="chart-panel">
          <div className="chart-title">Speed Trend</div>
          <div className="chart-sub">AVERAGE DOWNLOAD SPEED PER DAY</div>
          <LineChart
            data={(localStats.speed_by_day || []).map(d => ({ x: d.day, y: d.avg_bps }))}
            color="rgba(0,216,255,0.85)"
            yFormat={v => fmtSpeed(v)}
          />
        </div>
      </div>

      {/* FAILURES + WEEK HEATMAP */}
      <div className="g2">
        <div className="chart-panel">
          <div className="chart-title">Failures Over Time</div>
          <div className="chart-sub">ERRORED DOWNLOADS PER DAY</div>
          {(localStats.failures_by_day || []).length ? (
            <LineChart
              data={(localStats.failures_by_day || []).map(d => ({ x: d.day, y: d.count }))}
              color="rgba(255,59,97,0.85)"
            />
          ) : (
            <div style={{ padding: '30px 0', textAlign: 'center', fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)' }}>
              NO FAILURES IN RANGE
            </div>
          )}
        </div>
        <div className="chart-panel">
          <div className="chart-title">Week × Hour Heatmap</div>
          <div className="chart-sub">WHEN DO YOU DOWNLOAD — DAY OF WEEK × HOUR</div>
          {(() => {
            const grid = localStats.dow_hourly || [];
            const days = ['SUN','MON','TUE','WED','THU','FRI','SAT'];
            const maxC = Math.max(1, ...grid.flat());
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 6 }}>
                {days.map((d, di) => (
                  <div key={d} style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 7, color: 'var(--t4)', width: 24, flexShrink: 0 }}>{d}</span>
                    {Array.from({ length: 24 }, (_, h) => {
                      const v = (grid[di] || [])[h] || 0;
                      return (
                        <div key={h} title={`${d} ${String(h).padStart(2,'0')}:00 — ${v}`}
                          style={{ flex: 1, height: 12, background: `rgba(0,216,255,${(0.05 + (v / maxC) * 0.9).toFixed(2)})` }} />
                      );
                    })}
                  </div>
                ))}
                <div className="hm-labels" style={{ paddingLeft: 26 }}>
                  <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
                </div>
              </div>
            );
          })()}
        </div>
      </div>

      {/* SYNC HEALTH */}
      <div className="chart-panel" style={{ marginBottom: 16 }}>
        <div className="chart-title">Sync Health</div>
        <div className="chart-sub">LAST 10 LIBRARY / VAULT SYNC RUNS</div>
        {(localStats.sync_runs || []).length ? (
          <table className="data-table">
            <thead>
              <tr><th>WHEN</th><th>FOLDER</th><th>NEW</th><th>ERRORS</th><th>DURATION</th></tr>
            </thead>
            <tbody>
              {(localStats.sync_runs || []).map((s, i) => (
                <tr key={i}>
                  <td className="mono">{fmtTimestamp(s.synced_at)}</td>
                  <td>{s.name || '—'}</td>
                  <td className="mono" style={{ color: 'var(--green)' }}>{s.new_items ?? 0}</td>
                  <td className="mono" style={{ color: s.errors ? 'var(--red)' : 'var(--t4)' }}>{s.errors ?? 0}</td>
                  <td className="mono">{fmtEta(s.duration_seconds || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ padding: '20px', textAlign: 'center', fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)' }}>
            NO SYNC RUNS LOGGED YET — RUN A VAULT OR LIBRARY SYNC
          </div>
        )}
      </div>

      {/* RECENT DOWNLOADS TABLE */}
      <div className="chart-panel">
        <div className="chart-title">Recent Downloads</div>
        <div className="chart-sub">LAST 10 RECORDS FROM DUCKDB</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>TITLE</th>
              <th>PLATFORM</th>
              <th>FORMAT</th>
              <th>SIZE</th>
              <th>DATE</th>
              <th>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {(localStats.recent_records || []).map(r => (
              <tr key={r.id}>
                <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.title || r.url || '—'}
                </td>
                <td><span className={platformTagClass(r.platform)}>{r.platform || '—'}</span></td>
                <td className="mono">{r.format ? r.format.toUpperCase() : '—'}</td>
                <td className="mono">{fmtBytes(r.file_size_bytes)}</td>
                <td className="mono">{fmtDate(r.timestamp)}</td>
                <td>
                  <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 8, padding: '2px 6px', color: r.status === 'success' ? 'var(--green)' : 'var(--red)', border: '1px solid', borderColor: r.status === 'success' ? 'rgba(0,255,148,0.3)' : 'rgba(255,59,97,0.3)' }}>
                    {(r.status || '').toUpperCase()}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!(localStats.recent_records || []).length && (
          <div style={{ padding: '24px', textAlign: 'center', fontFamily: 'Share Tech Mono, monospace', fontSize: 9, color: 'var(--t4)' }}>
            NO RECORDS YET — START DOWNLOADING TO POPULATE THE DATA LAKE
          </div>
        )}
      </div>

      <HistoryPanel showNotif={showNotif} refreshStats={refreshStats} />
    </div>
  );
}
