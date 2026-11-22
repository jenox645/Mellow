// Theme Tactical's splash: a console coming up (the LoadingScreen slot). What it waits for is
// Classic's (useSplash: the floor, click to skip, the server check, the 401 answer).
'use strict';

import { useSplash } from '../../components/loading.jsx';
import { Mascot } from '../../components/common.jsx';
import { MASCOT_VIBING, MASCOT_CHILLING, MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE } from '../../lib/mascots.js';
import { TACTICAL_SPLASH_SEGMENTS as BAR_SEGMENTS, TACTICAL_SPLASH_STEP_MS as BAR_STEP_MS } from '../../lib/constants.js';

const POOL = [MASCOT_VIBING, MASCOT_CHILLING, MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE].filter(Boolean);

function Reticle() {
  return (
    <svg className="tac-boot-reticle" viewBox="0 0 64 64" aria-hidden="true">
      <circle className="tac-boot-reticle-ring" cx="32" cy="32" r="22" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="3 5" />
      <path d="M32 2v12M32 50v12M2 32h12M50 32h12" stroke="currentColor" strokeWidth="1.5" />
      <path className="tac-boot-reticle-hot" d="M32 26v12M26 32h12" strokeWidth="1.5" />
    </svg>
  );
}

export function TacticalLoadingScreen({ onReady }) {
  const { attempts, appVersion, signedOut, skip } = useSplash(onReady);
  const mascot = React.useRef(POOL[Math.floor(Math.random() * POOL.length)]).current;

  if (signedOut) {
    return (
      <div className="tac-boot tac-boot-denied">
        <div className="tac-boot-box">
          <div className="tac-boot-top"><span>MELLOWDLP // OPS CONSOLE</span><span>NO SESSION</span></div>
          <div className="tac-boot-title">NOT SIGNED IN</div>
          <div className="tac-boot-msg">
            This page wasn't opened by MellowDLP, or MellowDLP has restarted since.
            Open MellowDLP from its icon: it opens a signed-in window.
          </div>
          {signedOut.download && (
            <div className="tac-boot-msg">
              Still not working? Get the latest MellowDLP:{' '}
              <a href={signedOut.download} target="_blank" rel="noreferrer">
                {signedOut.download.replace(/^https:\/\//, '')}
              </a>
            </div>
          )}
        </div>
      </div>
    );
  }

  const server = appVersion ? 'ONLINE' : attempts > 0 ? 'RETRY ' + attempts + '/5' : 'CONNECTING';

  return (
    <div className="tac-boot" onClick={skip} title="Click to skip">
      <div className="tac-boot-box">
        <div className="tac-boot-top">
          <span>MELLOWDLP // OPS CONSOLE</span>
          <span>{appVersion ? 'v' + appVersion : 'STARTING'}</span>
        </div>
        <div className="tac-boot-main">
          <div className="tac-boot-id">
            <Reticle />
            <div>
              <div className="tac-boot-title">MELLOW<span>DLP</span></div>
              <div className="tac-boot-sub">WELCOME, ADMINISTRATOR</div>
            </div>
          </div>
          {mascot && (
            <div className="tac-boot-portrait" aria-hidden="true">
              <Mascot src={mascot} className="tac-boot-art" />
            </div>
          )}
        </div>
        <div className="tac-boot-log">
          <div className="tac-boot-line"><span>01</span><span>INTERFACE</span><i /><b>LOADED</b></div>
          <div className={'tac-boot-line' + (appVersion ? '' : ' wait')}>
            <span>02</span><span>LOCAL SERVER</span><i /><b>{server}</b>
          </div>
          <div className={'tac-boot-line' + (appVersion ? '' : ' wait')}>
            <span>03</span><span>SESSION</span><i /><b>{appVersion ? 'SIGNED IN' : 'CHECKING'}</b>
          </div>
        </div>
        <div className="tac-boot-bar" aria-hidden="true">
          {Array.from({ length: BAR_SEGMENTS }, (_, i) => <i key={i} style={{ animationDelay: (i * BAR_STEP_MS) + 'ms' }} />)}
        </div>
        <div className="tac-boot-foot"><span>CLICK TO SKIP</span><span>LOCAL ONLY</span></div>
      </div>
    </div>
  );
}
