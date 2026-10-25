// Config → API ACCESS: keys for other programs (/api/v1), and a fixed port
// so they can find the app (mellow/api_keys.py, server.py /api/keys).
'use strict';

import { API } from '../lib/api.js';
import { Modal } from './common.jsx';
import { timeAgo } from '../lib/util.js';

const when = (secs) => (secs ? timeAgo(secs * 1000) : 'never');

export function ApiAccessPanel({ local, set, showNotif }) {
  const [keys, setKeys] = React.useState([]);
  const [scopes, setScopes] = React.useState({});
  const [name, setName] = React.useState('');
  const [chosen, setChosen] = React.useState({ 'downloads:create': true });
  const [made, setMade] = React.useState(null);   // the new key, shown this once
  const base = window.location.origin;

  const refresh = React.useCallback(() => {
    API.get('/api/keys')
      .then(d => { setKeys(d.keys || []); setScopes(d.scopes || {}); })
      .catch(e => showNotif('Error', e.message, 'error'));
  }, [showNotif]);
  React.useEffect(() => { refresh(); }, [refresh]);

  const create = () => {
    const wanted = Object.keys(chosen).filter(s => chosen[s]);
    API.post('/api/keys', { name, scopes: wanted })
      .then(d => { setMade(d); setName(''); refresh(); })
      .catch(e => showNotif('Key Not Made', e.message, 'error'));
  };
  const revoke = (key) => {
    API.del('/api/keys/' + encodeURIComponent(key.id))
      .then(() => { showNotif('Key Revoked', key.name, 'info'); refresh(); })
      .catch(e => showNotif('Error', e.message, 'error'));
  };
  const copy = (text) => navigator.clipboard.writeText(text)
    .then(() => showNotif('Copied', '', 'success'))
    .catch(() => {});

  const example = made && `curl -X POST ${base}/api/v1/downloads \\\n  -H "Authorization: Bearer ${made.key}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"url": "https://www.youtube.com/watch?v=…"}'`;

  return (
    <div className="cfg-panel" data-tour="config-api">
      <div className="cfg-ph">
        <span className="ptag">API</span>
        <span className="ptitle">API ACCESS</span>
      </div>
      <div className="cfg-body">
        <div className="settings-row">
          <div className="settings-label">
            <div className="sl-name">Address</div>
            <div className="sl-sub">Programs on this computer reach MellowDLP at {base}/api/v1 with a key</div>
          </div>
          <div className="settings-ctrl">
            <button className="btn btn-secondary btn-sm" onClick={() => copy(base + '/api/v1')}>COPY</button>
          </div>
        </div>
        <div className="settings-row">
          <div className="settings-label">
            <div className="sl-name">Fixed Port</div>
            <div className="sl-sub">Empty = a free port each start. Set one (1024–65535) so programs always find
              MellowDLP; used from the next start, when it is free</div>
          </div>
          <div className="settings-ctrl">
            <input className="inp-sm" style={{ width: 90 }} inputMode="numeric" placeholder="auto"
              value={local.api_port ? String(local.api_port) : ''}
              onChange={e => set('api_port', e.target.value.replace(/\D/g, '').slice(0, 5))} />
          </div>
        </div>

        {keys.map(k => (
          <div className="settings-row" key={k.id}>
            <div className="settings-label">
              <div className="sl-name">{k.name}</div>
              <div className="sl-sub">
                {(k.scopes || []).map(s => scopes[s] || s).join(' · ')} — last used {when(k.last_used)}
              </div>
            </div>
            <div className="settings-ctrl">
              <button className="btn btn-danger btn-sm" onClick={() => revoke(k)}>REVOKE</button>
            </div>
          </div>
        ))}

        <div className="settings-row">
          <div className="settings-label">
            <div className="sl-name">New Key</div>
            <div className="sl-sub" style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 4 }}>
              {Object.entries(scopes).map(([scope, label]) => (
                <label key={scope} style={{ display: 'flex', gap: 4, alignItems: 'center', cursor: 'pointer' }}>
                  <input type="checkbox" checked={!!chosen[scope]}
                    onChange={e => setChosen(c => ({ ...c, [scope]: e.target.checked }))} />
                  {label}
                </label>
              ))}
            </div>
          </div>
          <div className="settings-ctrl" style={{ display: 'flex', gap: 6 }}>
            <input className="inp-sm" style={{ width: 150 }} placeholder="What will use it" value={name}
              maxLength={60} onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && name.trim()) create(); }} />
            <button className="btn btn-secondary btn-sm" disabled={!name.trim()} onClick={create}>MAKE KEY</button>
          </div>
        </div>
      </div>

      {made && (
        <Modal title={'API KEY — ' + made.name.toUpperCase()} onClose={() => setMade(null)} footer={
          <button className="btn btn-primary btn-sm" onClick={() => setMade(null)}>DONE</button>
        }>
          <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 11, lineHeight: 1.8 }}>
            <div style={{ color: 'var(--amber)', marginBottom: 8 }}>
              Copy it now: MellowDLP keeps only a fingerprint of it and can't show it again.
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
              <code style={{ wordBreak: 'break-all', color: 'var(--cyan)' }} data-testid="new-api-key">{made.key}</code>
              <button className="btn btn-secondary btn-sm" onClick={() => copy(made.key)}>COPY</button>
            </div>
            <div style={{ color: 'var(--t3)' }}>For example:</div>
            <pre style={{ whiteSpace: 'pre-wrap', color: 'var(--t2)', margin: '4px 0 0' }}>{example}</pre>
          </div>
        </Modal>
      )}
    </div>
  );
}
