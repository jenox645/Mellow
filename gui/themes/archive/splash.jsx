// Theme Archive's splash: a game's title screen (the LoadingScreen slot). What it waits for is
// Classic's (useSplash: the floor, click to skip, the server check, the 401 answer).
'use strict';

import { useSplash } from '../../components/loading.jsx';
import { Mascot } from '../../components/common.jsx';
import { MASCOT_VIBING, MASCOT_CHILLING, MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE } from '../../lib/mascots.js';

const POOL = [MASCOT_VIBING, MASCOT_CHILLING, MASCOT_COMFY_SAFE, MASCOT_SUCCESS_SAFE].filter(Boolean);

function Sky() {
  return (
    <div className="arc-title-sky" aria-hidden="true">
      <i className="arc-title-ring" />
      <i className="arc-title-ring arc-title-ring-2" />
      <i className="arc-title-cloud" />
      <i className="arc-title-cloud arc-title-cloud-2" />
    </div>
  );
}

export function ArchiveLoadingScreen({ onReady }) {
  const { attempts, appVersion, signedOut, skip } = useSplash(onReady);
  const mascot = React.useRef(POOL[Math.floor(Math.random() * POOL.length)]).current;

  if (signedOut) {
    return (
      <div className="arc-title arc-title-denied">
        <Sky />
        <div className="arc-title-card">
          <div className="arc-title-card-head">Not signed in</div>
          <p>
            This page wasn't opened by MellowDLP, or MellowDLP has restarted since.
            Open MellowDLP from its icon: it opens a signed-in window.
          </p>
          {signedOut.download && (
            <p>
              Still not working? Get the latest MellowDLP:{' '}
              <a href={signedOut.download} target="_blank" rel="noreferrer">
                {signedOut.download.replace(/^https:\/\//, '')}
              </a>
            </p>
          )}
        </div>
      </div>
    );
  }

  const state = appVersion ? 'Ready!' : attempts > 0 ? 'Retrying… ' + attempts + '/5' : 'Connecting…';

  return (
    <div className="arc-title" onClick={skip} title="Click to skip">
      <Sky />
      {mascot && (
        <div className="arc-title-hero" aria-hidden="true">
          <Mascot src={mascot} className="arc-title-art" />
        </div>
      )}
      <div className="arc-title-logo">Mellow<span>DLP</span></div>
      <div className="arc-title-sub">メロウ · your video archive{appVersion ? ' · v' + appVersion : ''}</div>
      <div className={'arc-title-state' + (appVersion ? ' ok' : '')}><i aria-hidden="true" />{state}</div>
      <div className="arc-title-touch">TOUCH TO START</div>
    </div>
  );
}
