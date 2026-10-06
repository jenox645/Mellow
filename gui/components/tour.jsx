// GUIDE: walks through a page one part at a time. The spotlight glides to
// each part (scrolling to it, opening OPTIONS/ADVANCED when it sits inside),
// dims the rest of the window, and a card beside it says what it does.
'use strict';

import { placeCard } from '../lib/tours.js';
import { TOUR_PAD_PX, TOUR_REVEAL_WAIT_MS, TOUR_SCROLL_WAIT_MS } from '../lib/constants.js';

const find = name => document.querySelector('[data-tour="' + name + '"]');
const wait = ms => new Promise(r => setTimeout(r, ms));

// Collapsed panels (max-height 0) and absent ones don't count as on screen
function visibleEl(name) {
  const el = find(name);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return r.width > 4 && r.height > 4 ? el : null;
}

async function prepare(step) {
  for (const r of step.reveal || []) {
    if (!visibleEl(r.unless)) {
      const toggle = find(r.click);
      if (toggle) {
        toggle.click();
        await wait(TOUR_REVEAL_WAIT_MS);
      }
    }
  }
  const el = visibleEl(step.target);
  if (el) {
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    await wait(TOUR_SCROLL_WAIT_MS);
  }
  return el;
}

export function Tour({ name, steps, onClose }) {
  const [idx, setIdx] = React.useState(0);
  const [el, setEl] = React.useState(null);
  const [ready, setReady] = React.useState(false);
  const [rect, setRect] = React.useState(null);
  const [cardSize, setCardSize] = React.useState({ width: 340, height: 200 });
  const cardRef = React.useRef(null);
  const step = steps[idx];
  const last = idx === steps.length - 1;

  // Open/scroll to this step's part, then point at it
  React.useEffect(() => {
    let live = true;
    setReady(false);
    prepare(step).then(found => {
      if (!live) return;
      setEl(found);
      setReady(true);
    });
    return () => { live = false; };
  }, [step]);

  // Follow the part while the page moves (scrolling, panels opening)
  React.useEffect(() => {
    let frame;
    const tick = () => {
      if (el && el.isConnected) {
        const r = el.getBoundingClientRect();
        setRect(prev => (prev && Math.round(prev.left) === Math.round(r.left) && Math.round(prev.top) === Math.round(r.top)
          && Math.round(prev.width) === Math.round(r.width) && Math.round(prev.height) === Math.round(r.height))
          ? prev : { left: r.left, top: r.top, width: r.width, height: r.height });
      } else {
        setRect(null);
      }
      if (cardRef.current) {
        const c = cardRef.current.getBoundingClientRect();
        setCardSize(prev => (Math.round(prev.width) === Math.round(c.width) && Math.round(prev.height) === Math.round(c.height))
          ? prev : { width: c.width, height: c.height });
      }
      frame = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(frame);
  }, [el]);

  const go = React.useCallback(delta => {
    const next = idx + delta;
    if (next >= steps.length) onClose();
    else setIdx(Math.max(0, next));
  }, [idx, steps.length, onClose]);

  // ←/→/Enter step, Esc closes (so does a click outside the card or leaving the page)
  React.useEffect(() => {
    const onKey = e => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowRight' || e.key === 'Enter') go(1);
      else if (e.key === 'ArrowLeft') go(-1);
      else return;
      e.preventDefault();
      e.stopPropagation();
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [go, onClose]);

  const vw = window.innerWidth, vh = window.innerHeight;
  const spot = rect && ready ? {
    left: rect.left - TOUR_PAD_PX, top: rect.top - TOUR_PAD_PX,
    width: rect.width + TOUR_PAD_PX * 2, height: rect.height + TOUR_PAD_PX * 2,
  } : null;
  const pos = placeCard(spot, cardSize, { width: vw, height: vh });

  return (
    <div className="tour-root" role="dialog" aria-label={'Guide: ' + step.title}>
      <div className="tour-blocker" title="Close the guide" onClick={onClose} />
      <div className={'tour-spot' + (spot ? '' : ' none')}
        style={spot || { left: vw / 2, top: vh / 2, width: 0, height: 0 }} />
      <div ref={cardRef} className={'tour-card side-' + pos.side + (ready ? '' : ' moving')}
        style={{ left: pos.left, top: pos.top }}>
        <div className="modal-hud" /><div className="modal-hud-br" />
        <div className="tour-head">
          <span className="tour-tag">GUIDE · {name}</span>
          <span className="tour-count">{idx + 1} / {steps.length}</span>
          <span className="tour-x" title="Close (Esc)" onClick={onClose}>✕</span>
        </div>
        <div key={idx} className="tour-body">
          <div className="tour-title">{step.title}</div>
          {!spot && ready && step.missing && <div className="tour-missing">{step.missing}</div>}
          <div className="tour-text">{step.text}</div>
          {step.tip && <div className="tour-tip"><span>TIP</span>{step.tip}</div>}
        </div>
        <div className="tour-foot">
          <div className="tour-dots">
            {steps.map((s, i) => (
              <span key={i} className={'tour-dot' + (i === idx ? ' on' : i < idx ? ' seen' : '')}
                title={s.title} onClick={() => setIdx(i)} />
            ))}
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => go(-1)} disabled={idx === 0}>←</button>
          <button className="btn btn-primary btn-sm" onClick={() => go(1)}>{last ? 'DONE ✓' : 'NEXT →'}</button>
        </div>
      </div>
    </div>
  );
}
