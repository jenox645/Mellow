// Bundled only by tests/browser/test_page_views.py: Classic gets a minimal view of every page, as a
// theme would register them (gui/themes/slots.jsx), drawn from what the pages' hooks return.
import { THEME_SLOTS } from '../../../gui/themes/slots.jsx';

function DummyFeedView(feed) {
  return (
    <div id="dummy-feed" data-keys={Object.keys(feed).sort().join(' ')}>
      <input id="dummy-url" value={feed.url} onChange={e => feed.setUrl(e.target.value)} />
      <button id="dummy-analyze" onClick={() => feed.handleAnalyze()}>ANALYZE</button>
      <div id="dummy-mode">{feed.mode} {feed.quality}</div>
      <div id="dummy-title">{feed.analyzing ? 'ANALYZING' : feed.info ? feed.info.title : 'NOTHING YET'}</div>
    </div>
  );
}

function DummyVaultView(vault) {
  return (
    <div id="dummy-vault" data-keys={Object.keys(vault).sort().join(' ')}>
      <button id="dummy-refresh" onClick={vault.refreshAll}>REFRESH</button>
      {vault.vaultFolders.map(f => (
        <button key={f.path} className="dummy-folder" onClick={() => vault.setSelectedFolder(f.path)}>{f.name}</button>
      ))}
      <div id="dummy-open">{vault.selectedFolder ? vault.folderName : 'ROOT'}</div>
      <ul>{vault.shownFiles.map(f => <li key={f.path} className="dummy-file">{f.name}</li>)}</ul>
    </div>
  );
}

function DummyQueueView(queue) {
  return (
    <div id="dummy-queue" data-keys={Object.keys(queue).sort().join(' ')}>
      <div id="dummy-counts">{queue.activeCount} active · {queue.queuedJobsCount} queued · tab {queue.qTab}</div>
      {queue.jobs.map(j => (
        <button key={j.id} className="dummy-job" onClick={() => queue.startJobNow(j)}>{j.label}</button>
      ))}
    </div>
  );
}

function DummyAnalyticsView(analytics) {
  return (
    <div id="dummy-analytics" data-keys={Object.keys(analytics).sort().join(' ')}>
      <button id="dummy-7d" onClick={() => analytics.setRange('7d')}>7D</button>
      <div id="dummy-range">{analytics.range} {analytics.localStats.total_downloads || 0}</div>
      <input id="dummy-history-search" value={analytics.historySearch}
        onChange={e => analytics.searchHistory(e.target.value)} />
      <ul>{analytics.historyRows.map(r => <li key={r.id} className="dummy-row">{r.title}</li>)}</ul>
    </div>
  );
}

function DummySignalView(signal) {
  return (
    <div id="dummy-signal" data-keys={Object.keys(signal).sort().join(' ')}>
      {signal.presets.map((p, i) => (
        <button key={i} className="dummy-preset" onClick={() => signal.pickPreset(i)}>{p.label}</button>
      ))}
      <button id="dummy-run" onClick={signal.runQuery}>RUN</button>
      <div id="dummy-result">{signal.running ? 'RUNNING' : signal.result ? signal.result.row_count + ' rows' : 'NO RESULT'}</div>
    </div>
  );
}

function DummyConfigView(cfg) {
  return (
    <div id="dummy-config" data-keys={Object.keys(cfg).sort().join(' ')}>
      <input id="dummy-template" value={cfg.local.filename_template || ''}
        onChange={e => cfg.set('filename_template', e.target.value)} />
      <div id="dummy-preview">{cfg.namePreview ? (cfg.namePreview.ok ? cfg.namePreview.example : 'BAD') : ''}</div>
      <button id="dummy-save" onClick={cfg.handleSave}>SAVE</button>
      <div id="dummy-theme">{cfg.currentTheme}</div>
    </div>
  );
}

THEME_SLOTS.classic = {
  pages: {
    feed: DummyFeedView, queue: DummyQueueView, vault: DummyVaultView, analytics: DummyAnalyticsView,
    signal: DummySignalView, config: DummyConfigView,
  },
};
