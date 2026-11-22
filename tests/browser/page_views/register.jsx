// Bundled only by tests/browser/test_page_views.py: Classic gets two minimal page views, as a
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

THEME_SLOTS.classic = { pages: { feed: DummyFeedView, vault: DummyVaultView } };
