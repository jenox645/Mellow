// Splash screen — short floor, click to skip, waits for the server.
'use strict';

import { authHeaders } from '../lib/api.js';
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
  const [signedOut, setSignedOut] = React.useState(null);   // the 401 answer, once refused
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
      fetch('/api/system', { headers: authHeaders() })
        .then(r => {
          // Not a window MellowDLP opened (or the app restarted since): no point retrying
          if (r.status === 401) {
            r.json().catch(() => ({})).then(d => setSignedOut(d || {}));
            return Promise.reject(null);
          }
          return r.json();
        })
        .then(d => {
          if (d && d.app_version) setAppVersion(d.app_version);
          serverReadyRef.current = true;
          tryReady();
        })
        .catch((e) => {
          if (e === null) return;
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
    // Ask at once: the server is usually up before the splash has drawn
    const t = setTimeout(tryConnect, 0);
    return () => clearTimeout(t);
  }, [tryReady]);

  const skip = React.useCallback(() => {
    minElapsedRef.current = true;
    tryReady();
  }, [tryReady]);

  if (signedOut) {
    return (
      <div className="loading-screen">
        <div className="loading-title">NOT SIGNED IN</div>
        <div className="loading-sub" style={{ maxWidth: 520, textAlign: 'center', lineHeight: 1.8 }}>
          This page wasn't opened by MellowDLP, or MellowDLP has restarted since.
          Open MellowDLP from its icon: it opens a signed-in window.
        </div>
        {signedOut.download && (
          <div className="loading-sub" style={{ maxWidth: 520, textAlign: 'center', lineHeight: 1.8 }}>
            Still not working? Get the latest MellowDLP:{' '}
            <a href={signedOut.download} target="_blank" rel="noreferrer" style={{ color: 'var(--cyan)' }}>
              {signedOut.download.replace(/^https:\/\//, '')}
            </a>
          </div>
        )}
      </div>
    );
  }

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
        <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: '9px', color: 'var(--t4)' }}>
          CONNECTING... ATTEMPT {attempts}/5
        </div>
      )}
    </div>
  );
}

