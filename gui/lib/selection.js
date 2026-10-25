// Selecting files the way a file explorer does: drag a rectangle, Ctrl/⌘-click
// one more, Shift-click a range. Pure helpers (node-tested); the drag itself is
// useMarquee in components/marquee.jsx.
'use strict';

/** The rectangle between two corners, as {left, top, right, bottom}. */
export function rectFrom(a, b) {
  return {
    left: Math.min(a.x, b.x), top: Math.min(a.y, b.y),
    right: Math.max(a.x, b.x), bottom: Math.max(a.y, b.y),
  };
}

/** Whether two rectangles overlap (touching edges don't count). */
export function intersects(r, box) {
  return r.left < box.right && r.right > box.left && r.top < box.bottom && r.bottom > box.top;
}

/** Keys of the boxes ({key, left, top, right, bottom}) the rectangle touches, in their order. */
export function hitKeys(rect, boxes) {
  return boxes.filter(b => intersects(rect, b)).map(b => b.key);
}

/**
 * A click on `key` in a list shown as `keys`:
 * - shift: the range from the anchor to `key` (added to what was selected
 *   when `add` is set too); the anchor stays, so the range can be changed;
 * - otherwise toggles `key` and makes it the anchor.
 * Returns {selected: Set, anchor}.
 */
export function clickSelect(selected, keys, key, { add = false, shift = false } = {}, anchor = null) {
  const from = anchor == null ? -1 : keys.indexOf(anchor);
  const to = keys.indexOf(key);
  if (shift && from >= 0 && to >= 0) {
    const range = keys.slice(Math.min(from, to), Math.max(from, to) + 1);
    return { selected: new Set([...(add ? selected : []), ...range]), anchor };
  }
  const next = new Set(selected);
  if (next.has(key)) next.delete(key); else next.add(key);
  return { selected: next, anchor: key };
}
