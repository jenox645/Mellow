// The Analytics page's logic: its state, effects, API calls and handlers, shared by every theme.
// useAnalyticsPage(props) takes what the App hands the page and returns everything a view
// draws and every handler it calls (the view itself never calls the API).
'use strict';

import { API, download } from '../lib/api.js';
import { HISTORY_LIMIT, HISTORY_SEARCH_DEBOUNCE_MS } from '../lib/constants.js';

// Per-day counts with the days that had none filled in as 0. The query only
// returns active days, so a line through them drew 1 Jan next to 20 Jan.
export function dailySeries(rows, range) {
  if (!rows || !rows.length) return [];
  const counts = new Map(rows.map(r => [r.day, r.count]));
  const key = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const span = { '7d': 7, '30d': 30 }[range];
  const day = span ? new Date(today) : new Date(rows[0].day + 'T00:00:00');
  if (span) day.setDate(day.getDate() - (span - 1));
  const out = [];
  for (; day <= today; day.setDate(day.getDate() + 1)) {
    out.push({ x: key(day), y: counts.get(key(day)) || 0 });
  }
  return out.length ? out : rows.map(r => ({ x: r.day, y: r.count }));
}

// The History Browser: one page of the download history, searched and filtered
function useHistory({ showNotif, refreshStats }) {
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
      .then(() => showNotif('Re-queued', r.title || r.url))
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

  return {
    historyRows: rows, historyLoading: loading, historySearch: search, historyType: typeFilter,
    historyOffset: offset, historyHasPrev: offset > 0, historyHasNext: rows.length >= HISTORY_LIMIT,
    // A new search or type starts again from the first page
    searchHistory: text => { setSearch(text); setOffset(0); },
    filterHistoryType: type => { setTypeFilter(type); setOffset(0); },
    historyPrev: () => setOffset(o => Math.max(0, o - HISTORY_LIMIT)),
    historyNext: () => setOffset(o => o + HISTORY_LIMIT),
    redownloadHistoryRow: redownload, openHistoryFile: openFile, deleteHistoryRow: deleteRow,
  };
}

// ✦ WRAPPED: the year in review, one DuckDB query, read while the card is open
function useWrapped() {
  const [open, setOpen] = React.useState(false);
  const [year, setYear] = React.useState(() => new Date().getFullYear());
  const [data, setData] = React.useState(null);

  React.useEffect(() => {
    if (!open) return;
    setData(null);
    // The state outlives the card: an answer that comes back after the card closed or
    // moved to another year (close + reopen before it lands) is dropped, not shown
    let current = true;
    API.get('/api/analytics/wrapped?year=' + year)
      .then(d => { if (current) setData(d); })
      .catch(() => { if (current) setData({ error: true }); });
    return () => { current = false; };
  }, [open, year]);

  return {
    wrappedOpen: open, wrappedYear: year, wrappedData: data,
    // Opens on this year, as it always has
    openWrapped: () => { setYear(new Date().getFullYear()); setData(null); setOpen(true); },
    closeWrapped: () => setOpen(false),
    setWrappedYear: setYear,
  };
}

export function useAnalyticsPage(props) {
  const { stats, refreshStats, showNotif } = props;
  const [range, setRange] = React.useState('30d');
  const [localStats, setLocalStats] = React.useState(stats);
  const [overrides, setOverrides] = React.useState({});

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

  // A KPI card's value typed over the computed one (EditableStat)
  const saveOverride = React.useCallback((key, val) => {
    const update = { [key]: val };
    setOverrides(o => ({ ...o, ...update }));
    API.post('/api/analytics/overrides', update).catch(() => {});
  }, []);

  // Use override value if present, else computed value
  const statVal = (key, computed) => (key in overrides && overrides[key] !== '' && overrides[key] !== null) ? overrides[key] : computed;

  const handleExport = () => {
    download('/api/analytics/export').catch(e => showNotif('Export Failed', e.message, 'error'));
  };

  const history = useHistory({ showNotif, refreshStats });
  const wrapped = useWrapped();

  return {
    ...props,
    // the range (7d / 30d / all) and what /api/stats gave for it
    range, setRange, localStats,
    // the KPI cards
    statVal, saveOverride,
    // the charts' data
    hourly: localStats.hourly_activity || Array(24).fill(0),
    dailyTrend: dailySeries(localStats.by_day_last_30, range),
    dailyFailures: dailySeries(localStats.failures_by_day, range),
    // EXPORT CSV
    handleExport,
    ...wrapped,
    ...history,
  };
}
