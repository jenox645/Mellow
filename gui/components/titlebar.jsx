// The desktop app's title bar (src-tauri/: a frameless window on Windows).
// The band is the window's drag region (CSS app-region: native drag, snap,
// double-click to maximize, no IPC); its buttons go to the shell through the
// backend (/api/window). Its bottom rule draws on when the window opens and
// fills with the first download's progress; its mark is the mascot badge.
// A theme restyles it with the
// --titlebar-* tokens, or replaces it (slot TitleBar, gui/lib/slots.js).
'use strict';

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1 };

function useMaximized() {
  const check = () => window.outerWidth >= window.screen.availWidth - 2
    && window.outerHeight >= window.screen.availHeight - 2;
  const [maximized, setMaximized] = React.useState(check);
  React.useEffect(() => {
    const onResize = () => setMaximized(check());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  return maximized;
}

export function TitleBar({ progress, onWindowOp }) {
  const maximized = useMaximized();
  const pct = progress && typeof progress.pct === 'number' ? Math.max(0, Math.min(100, progress.pct)) : null;
  return (
    <div className="titlebar" data-tour="titlebar">
      <div className="titlebar-mark" aria-hidden="true">
        {/* Mellow's sheep-face badge, as on the tray and the taskbar (scripts/make_icons.py) */}
        <img src="/mellow-badge.png" srcSet="/mellow-badge.png 1x, /mellow-badge@2x.png 2x"
          width="18" height="18" alt="" draggable="false" />
      </div>
      <div className="titlebar-name"><b>MELLOWDLP</b><i>メロウ</i></div>
      <div className="titlebar-fill" />
      <button className="titlebar-btn" title="Minimize" onClick={() => onWindowOp('minimize')}>
        <svg viewBox="0 0 10 10" width="10" height="10"><path d="M0 5.5h10" {...stroke} /></svg>
      </button>
      <button className="titlebar-btn" title={maximized ? 'Restore' : 'Maximize'} onClick={() => onWindowOp('maximize')}>
        {maximized ? (
          <svg viewBox="0 0 10 10" width="10" height="10"><path d="M2.5 2.5V.5h7v7h-2M.5 2.5h7v7h-7z" {...stroke} /></svg>
        ) : (
          <svg viewBox="0 0 10 10" width="10" height="10"><path d="M.5.5h9v9h-9z" {...stroke} /></svg>
        )}
      </button>
      <button className="titlebar-btn titlebar-close" title="Close" onClick={() => onWindowOp('close')}>
        <svg viewBox="0 0 10 10" width="10" height="10"><path d="M.5.5l9 9M9.5.5l-9 9" {...stroke} /></svg>
      </button>
      <span className="titlebar-rule" />
      {pct !== null && (
        <span className={'titlebar-progress' + (progress.paused ? ' paused' : '')}
          style={{ transform: 'scaleX(' + (pct / 100) + ')' }} />
      )}
    </div>
  );
}
