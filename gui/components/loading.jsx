// Splash screen — short floor, click to skip, waits for the server.
'use strict';

import { LOADING_MIN_MS } from '../lib/constants.js';
import {
  MASCOT_DJ, MASCOT_VIBING, MASCOT_CHILLING, MASCOT_TIRED,
  MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE, MASCOT_TROUBLESHOOTING_SAFE, MASCOT_VICTORY_SAFE,
} from '../lib/mascots.js';

const _SPLASH_POOL = [
  MASCOT_DJ, MASCOT_VIBING, MASCOT_CHILLING, MASCOT_TIRED,
  MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE, MASCOT_TROUBLESHOOTING_SAFE, MASCOT_VICTORY_SAFE,
].filter(Boolean);

export function LoadingScreen({ onReady }) {
  const [text, setText] = React.useState('');
  const [attempts, setAttempts] = React.useState(0);
  const [appVersion, setAppVersion] = React.useState('');
  const serverReadyRef = React.useRef(false);
  const minElapsedRef = React.useRef(false);
  const TARGET = 'WELCOME, ADMINISTRATOR';
  const splashMascot = React.useRef(_SPLASH_POOL[Math.floor(Math.random() * _SPLASH_POOL.length)]).current;
  const splashIsSvg = typeof splashMascot === 'string' && (splashMascot.trimStart().startsWith('<svg') || splashMascot.trimStart().startsWith('<?xml'));
  const splashSvgHtml = splashIsSvg ? splashMascot.replace(/^<\?xml[^?]*\?>\s*/i, '') : null;

  const tryReady = React.useCallback(() => {
    if (serverReadyRef.current && minElapsedRef.current) onReady();
  }, [onReady]);

  React.useEffect(() => {
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setText(TARGET.slice(0, i));
      if (i >= TARGET.length) clearInterval(timer);
    }, 60);
    return () => clearInterval(timer);
  }, []);

  // Minimum display duration — ensures animation completes
  React.useEffect(() => {
    const t = setTimeout(() => {
      minElapsedRef.current = true;
      tryReady();
    }, LOADING_MIN_MS);
    return () => clearTimeout(t);
  }, [tryReady]);

  // Server readiness check
  React.useEffect(() => {
    const tryConnect = () => {
      fetch('/api/system')
        .then(r => r.json())
        .then(d => {
          if (d && d.app_version) setAppVersion(d.app_version);
          serverReadyRef.current = true;
          tryReady();
        })
        .catch(() => {
          setAttempts(a => {
            const next = a + 1;
            if (next < 5) setTimeout(tryConnect, 1200);
            else {
              serverReadyRef.current = true;
              tryReady();
            }
            return next;
          });
        });
    };
    const t = setTimeout(tryConnect, 600);
    return () => clearTimeout(t);
  }, [tryReady]);

  const skip = React.useCallback(() => {
    minElapsedRef.current = true;
    tryReady();
  }, [tryReady]);

  return (
    <div className="loading-screen" onClick={skip} style={{ cursor: 'pointer' }} title="Click to skip">
      {splashIsSvg ? (
        <div className="loading-mascot" style={{ filter: 'drop-shadow(0 0 24px rgba(0,216,255,0.35))' }} dangerouslySetInnerHTML={{ __html: splashSvgHtml }} />
      ) : splashMascot ? (
        <img src={splashMascot} className="loading-mascot" style={{ filter: 'sepia(1) saturate(6.7) hue-rotate(151deg) brightness(0.87) drop-shadow(0 0 24px rgba(0,216,255,0.35))', mixBlendMode: 'screen' }} alt="" />
      ) : null}
      <div className="loading-title">{text}<span style={{ opacity: 0.5, animation: 'pulse 1s infinite' }}>_</span></div>
      <div className="loading-sub">MELLOW // DATA LAKE COMMANDER{appVersion ? ' v' + appVersion : ''}</div>
      <div className="loading-bar"><div className="loading-bar-fill" /></div>
      {attempts > 0 && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--t4)' }}>
          CONNECTING... ATTEMPT {attempts}/5
        </div>
      )}
    </div>
  );
}

