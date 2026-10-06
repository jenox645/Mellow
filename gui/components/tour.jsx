// GUIDE: walks through a page one part at a time. The spotlight glides to
// each part (scrolling to it, opening OPTIONS/ADVANCED when it sits inside),
// dims the rest of the window, and a card beside it says what it does.
'use strict';

import { placeCard } from '../lib/tours.js';
import {
  TOUR_CARD_SIZE, TOUR_FOLLOW_MS, TOUR_MIN_VISIBLE_PX, TOUR_PAD_PX, TOUR_REVEAL_WAIT_MS, TOUR_SCROLL_WAIT_MS,
} from '../lib/constants.js';

const find = name => document.querySelector('[data-tour="' + name + '"]');
const wait = ms => new Promise(r => setTimeout(r, ms));

// Collapsed panels (max-height 0) and absent ones don't count as on screen
function visibleEl(name) {
  const el = find(name);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return r.width > TOUR_MIN_VISIBLE_PX && r.height > TOUR_MIN_VISIBLE_PX ? el : null;
}

// Open, or opening: the panel's class flips at the click, its height follows
// during the CSS transition. Clicking again then would close it.
function isOpen(name) {
  const el = find(name);
  return !!el && (el.classList.contains('open') || !!visibleEl(name));
}

// Open what the step's part sits in and scroll to it. Stops as soon as the
// step is no longer current (live() false): no clicks or scrolling after
// the user moved on or closed the guide. `opened` collects what it opened.
async function prepare(step, live, opened) {
  for (const r of step.reveal || []) {
    if (!live()) return null;
    if (!isOpen(r.unless)) {
      const toggle = find(r.click);
      if (toggle) {
        toggle.click();
        opened.push(r);
        await wait(TOUR_REVEAL_WAIT_MS);
      }
    }
  }
  if (!live()) return null;
  const el = step.target ? visibleEl(step.target) : null;
  if (el) {
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    await wait(TOUR_SCROLL_WAIT_MS);
  }
  return el;
}

// A made-up sample of what a part shows (tours.js `example`)
function TourExample({ example }) {
  if (example.kind === 'file') {
    return (
      <div className="tour-ex">
        <div className="tour-ex-head">📄 {example.name}</div>
        <pre className="tour-ex-file">{example.lines.join('\n')}</pre>
      </div>
    );
  }
  if (example.kind === 'pairs') {
    return (
      <div className="tour-ex">
        <div className="tour-ex-head">EXAMPLE</div>
        {example.pairs.map(([a, b], i) => (
          <div key={i} className="tour-ex-pair"><span>{a}</span><span className="tour-ex-arrow">→</span><span>{b}</span></div>
        ))}
      </div>
    );
  }
  return (
    <div className="tour-ex">
      <div className="tour-ex-head">EXAMPLE</div>
      {example.rows.map((r, i) => (
        <div key={i} className="tour-ex-row">
          <div className="tour-ex-main">
            <div className="tour-ex-text">{r.text}</div>
            {r.sub && <div className="tour-ex-sub">{r.sub}</div>}
          </div>
          {r.badge && <span className={'tour-ex-badge ' + (r.tone || '')}>{r.badge}</span>}
        </div>
      ))}
    </div>
  );
}

export function Tour({ name, steps, onClose }) {
  const [idx, setIdx] = React.useState(0);
  const [el, setEl] = React.useState(null);
  const [ready, setReady] = React.useState(false);
  const [rect, setRect] = React.useState(null);
  const [cardSize, setCardSize] = React.useState(TOUR_CARD_SIZE);
  const cardRef = React.useRef(null);
  const opened = React.useRef([]);
  const step = steps[idx];
  const last = idx === steps.length - 1;

  // Open/scroll to this step's part, then point at it
  React.useEffect(() => {
    let live = true;
    setReady(false);
    prepare(step, () => live, opened.current).then(found => {
      if (!live) return;
      setEl(found);
      setReady(true);
    });
    return () => { live = false; };
  }, [step]);

  // Leave the page as it was: close the panels the guide opened
  React.useEffect(() => () => {
    for (const r of opened.current.slice().reverse()) {
      if (isOpen(r.unless)) {
        const toggle = find(r.click);
        if (toggle) toggle.click();
      }
    }
  }, []);

  // Follow the part and the card: every frame while they settle after a
  // step change (scrolling, panels opening), then whenever the page scrolls
  // or something changes size
  React.useEffect(() => {
    const measure = () => {
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
    };
    let frame = 0;
    const until = Date.now() + TOUR_FOLLOW_MS;
    const settle = () => {
      measure();
      if (Date.now() < until) frame = requestAnimationFrame(settle);
    };
    settle();
    const onChange = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    window.addEventListener('scroll', onChange, true);
    window.addEventListener('resize', onChange);
    const resized = new ResizeObserver(onChange);
    if (el) resized.observe(el);
    if (cardRef.current) resized.observe(cardRef.current);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onChange, true);
      window.removeEventListener('resize', onChange);
      resized.disconnect();
    };
  }, [el, idx]);

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
          {!step.target && <div className="tour-concept">HOW IT WORKS</div>}
          {step.target && !spot && ready && step.missing && <div className="tour-missing">{step.missing}</div>}
          <div className="tour-text">{step.text}</div>
          {step.example && (!step.example.onlyMissing || (ready && !spot)) && <TourExample example={step.example} />}
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
