// Shared React hooks.
'use strict';

// sessionStorage: survives switching pages and reloading, not a restart
export function readSession(key, fallback) {
  try {
    const v = sessionStorage.getItem(key);
    return v === null || v === '' ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}

export function hasSession(key) {
  try { return sessionStorage.getItem(key) !== null; } catch { return false; }
}

// useState that is kept in sessionStorage under `key` (JSON)
export function useSessionState(key, initial) {
  const [value, setValue] = React.useState(() => readSession(key, initial));
  React.useEffect(() => {
    try { sessionStorage.setItem(key, JSON.stringify(value)); } catch {}
  }, [key, value]);
  return [value, setValue];
}

// How many of a list to draw now: `first`, then `chunk` more per step, never
// past `total`. A list of thousands is drawn over a few frames instead of in
// one task that blocks the window (#127).
export function progressiveCount(count, total, first, chunk) {
  return Math.min(total, Math.max(first, count + chunk));
}

// The first items of `items` to draw: `first` at once, `chunk` more each frame
// until all are there. A new `resetKey` (another folder, sort, search or card
// size) starts again from `first`; the same list grown or changed (a sync added
// a file) keeps what it already draws, so nothing flickers.
export function useProgressiveList(items, resetKey, first, chunk) {
  const [state, setState] = React.useState(() => ({ key: resetKey, count: first }));
  let count = state.count;
  if (state.key !== resetKey) {
    count = first;
    setState({ key: resetKey, count: first });    // React re-renders at once, before painting
  }
  const total = items.length;
  React.useEffect(() => {
    if (count >= total) return undefined;
    let timer = 0;
    // After this frame is painted: one chunk per frame, the window stays responsive
    const frame = requestAnimationFrame(() => {
      timer = setTimeout(() => setState(s => (s.key === resetKey
        ? { key: s.key, count: progressiveCount(s.count, total, first, chunk) } : s)), 0);
    });
    return () => { cancelAnimationFrame(frame); clearTimeout(timer); };
  }, [count, total, resetKey, first, chunk]);
  return count >= total ? items : items.slice(0, count);
}

// `items` cut into the blocks useProgressiveBlocks draws: `first` items, then
// `chunk` at a time. Pure, so the same items give the same blocks
export function listBlocks(items, first, chunk) {
  if (!items.length) return [];
  const blocks = [items.slice(0, first)];
  for (let i = first; i < items.length; i += chunk) blocks.push(items.slice(i, i + chunk));
  return blocks;
}

// useProgressiveList for a list of thousands: the same steps, as blocks whose
// arrays keep their identity while `items` doesn't change, so a view drawing each
// block with a memoized component (common.jsx ListBlock) redraws only the new
// one. With one flat list React went over every card already drawn at each step:
// 65 ms a step late in a folder of 2,000 files
export function useProgressiveBlocks(items, resetKey, first, chunk) {
  const blocks = React.useMemo(() => listBlocks(items, first, chunk), [items, first, chunk]);
  const [state, setState] = React.useState(() => ({ key: resetKey, shown: 1 }));
  let shown = state.shown;
  // Another list (resetKey), or none for now (a folder loading): from the first block again
  if (state.key !== resetKey || (!blocks.length && state.shown !== 1)) {
    shown = 1;
    setState({ key: resetKey, shown: 1 });
  }
  React.useEffect(() => {
    if (shown >= blocks.length) return undefined;
    let timer = 0;
    const frame = requestAnimationFrame(() => {
      timer = setTimeout(() => setState(s => (s.key === resetKey ? { key: s.key, shown: s.shown + 1 } : s)), 0);
    });
    return () => { cancelAnimationFrame(frame); clearTimeout(timer); };
  }, [shown, blocks.length, resetKey]);
  return shown >= blocks.length ? blocks : blocks.slice(0, shown);
}
