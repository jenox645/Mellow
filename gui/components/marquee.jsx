// Drag a rectangle over files to select them, as in a file explorer.
//
// Press anywhere in the container (on a file too) and move: every item the
// rectangle touches is selected; with Ctrl/⌘ held they're added to the
// selection. A press that doesn't move is an ordinary click. Dragging near
// the top or bottom of the scrolling area scrolls it.
'use strict';

import { hitKeys, rectFrom } from '../lib/selection.js';
import {
  MARQUEE_EDGE_PX, MARQUEE_SCROLL_MS, MARQUEE_SCROLL_PX, MARQUEE_START_PX,
} from '../lib/constants.js';

const ITEM = '[data-select-key]';
const NOT_A_DRAG = 'button, input, select, textarea, a, .lib-menu';

function scrollParent(el) {
  for (let p = el && el.parentElement; p; p = p.parentElement) {
    const y = window.getComputedStyle(p).overflowY;
    if ((y === 'auto' || y === 'scroll') && p.scrollHeight > p.clientHeight) return p;
  }
  return document.scrollingElement || document.documentElement;
}

/**
 * Returns {onMouseDown, overlay, consumeClick}: put onMouseDown on the
 * container (position: relative) and render overlay inside it; an item's
 * onClick calls consumeClick() first and ignores the click when it's true
 * (the end of a drag). Items carry data-select-key.
 */
export function useMarquee(containerRef, selected, setSelected) {
  const [box, setBox] = React.useState(null);
  const dragged = React.useRef(false);
  const selectedRef = React.useRef(selected);
  selectedRef.current = selected;

  const onMouseDown = React.useCallback((e) => {
    const container = containerRef.current;
    if (e.button !== 0 || !container || e.target.closest(NOT_A_DRAG)) return;
    e.preventDefault();                       // no text selection, no image dragging
    // …which also keeps focus where it was: leave the search box, so keys
    // (Ctrl+A, Delete, Esc) go to the files
    if (document.activeElement && document.activeElement.matches('input, textarea')) document.activeElement.blur();
    const origin = () => container.getBoundingClientRect();
    // In the container's own coordinates: they hold while the page scrolls
    const start = { x: e.clientX - origin().left, y: e.clientY - origin().top };
    const base = e.ctrlKey || e.metaKey ? [...selectedRef.current] : [];
    const onItem = !!e.target.closest(ITEM);
    const scroller = scrollParent(container);
    let pointer = { x: e.clientX, y: e.clientY };
    let active = false;
    let timer = null;

    const update = () => {
      const o = origin();
      const at = { x: pointer.x - o.left, y: pointer.y - o.top };
      if (!active && Math.hypot(at.x - start.x, at.y - start.y) < MARQUEE_START_PX) return;
      active = true;
      const rect = rectFrom(start, at);
      setBox(rect);
      const boxes = [...container.querySelectorAll(ITEM)].map(el => {
        const r = el.getBoundingClientRect();
        return { key: el.dataset.selectKey, left: r.left - o.left, top: r.top - o.top,
                 right: r.right - o.left, bottom: r.bottom - o.top };
      });
      setSelected(new Set([...base, ...hitKeys(rect, boxes)]));
    };
    const autoScroll = () => {
      if (!active) return;
      const view = scroller === document.scrollingElement || scroller === document.documentElement
        ? { top: 0, bottom: window.innerHeight } : scroller.getBoundingClientRect();
      const step = pointer.y < view.top + MARQUEE_EDGE_PX ? -MARQUEE_SCROLL_PX
        : pointer.y > view.bottom - MARQUEE_EDGE_PX ? MARQUEE_SCROLL_PX : 0;
      if (step) { scroller.scrollTop += step; update(); }
    };
    const onMove = (ev) => { pointer = { x: ev.clientX, y: ev.clientY }; update(); };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      clearInterval(timer);
      if (active) {
        setBox(null);
        dragged.current = true;               // the click that follows ends the drag
        setTimeout(() => { dragged.current = false; }, 0);
      } else if (!onItem && !base.length) {
        setSelected(new Set());               // a click on empty space clears the selection
      }
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    timer = setInterval(autoScroll, MARQUEE_SCROLL_MS);
  }, [containerRef, setSelected]);

  const consumeClick = React.useCallback(() => dragged.current, []);
  const overlay = box && (
    <div className="marquee" style={{ left: box.left, top: box.top, width: box.right - box.left, height: box.bottom - box.top }} />
  );
  return { onMouseDown, overlay, consumeClick };
}
