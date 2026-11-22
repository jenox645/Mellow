// Config → IN THE BACKGROUND: the daily sync's time, and in the desktop app
// (src-tauri/, sysInfo.shell === 'tauri') the tray: run in the background,
// start with the system, notify from the tray (mellow/shell.py, scheduler.py).
'use strict';

import { Toggle } from './common.jsx';

const systemName = () => {
  const p = (typeof navigator !== 'undefined' && navigator.platform) || '';
  if (/Win/i.test(p)) return 'Windows';
  if (/Mac/i.test(p)) return 'macOS';
  return '';
};

function Row({ name, sub, children }) {
  return (
    <div className="settings-row">
      <div className="settings-label">
        <div className="sl-name">{name}</div>
        <div className="sl-sub">{sub}</div>
      </div>
      <div className="settings-ctrl">{children}</div>
    </div>
  );
}

export function DesktopAppPanel({ local, set, sysInfo }) {
  const tray = sysInfo && sysInfo.shell === 'tauri';
  const system = systemName();
  return (
    <div className="cfg-panel" data-tour="config-background">
      <div className="cfg-ph">
        <span className="ptag">AUTO</span>
        <span className="ptitle">IN THE BACKGROUND</span>
      </div>
      <div className="cfg-body">
        {tray && (
          <Row name="Run in the Background"
            sub="Closing the window keeps MellowDLP in the tray while downloads run or wait for their time, or folders sync by themselves. Off: closing quits">
            <Toggle checked={local.run_in_background !== false} onChange={v => set('run_in_background', v)} />
          </Row>
        )}
        {tray && (
          <Row name={system ? 'Start with ' + system : 'Start When You Log In'}
            sub="Starts in the tray when you log in, so the daily sync and downloads for later run without opening MellowDLP">
            <Toggle checked={local.start_with_system === true} onChange={v => set('start_with_system', v)} />
          </Row>
        )}
        <Row name="Daily Sync Time"
          sub="Folders on Daily sync at this time, or as soon as MellowDLP runs after it (it never wakes a sleeping computer)">
          <input type="time" className="inp-sm" style={{ width: 110 }} value={local.auto_sync_time || '03:00'}
            onChange={e => set('auto_sync_time', e.target.value)} />
        </Row>
        {tray && (
          <Row name="Notify from the Tray"
            sub="With no window open: a sync that found something new, finished downloads, a failure">
            <Toggle checked={local.background_notifications !== false} onChange={v => set('background_notifications', v)} />
          </Row>
        )}
      </div>
    </div>
  );
}
