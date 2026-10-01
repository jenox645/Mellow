// Which layout the UI renders: "classic" (the HUD look) or "studio".
// Pages read it with useLayout(); CSS keys off <html data-layout="…">.
'use strict';

import { LAYOUTS, LAYOUT_STORAGE_KEY } from './constants.js';

export const LayoutContext = React.createContext('classic');

export function useLayout() {
  return React.useContext(LayoutContext);
}

export function normalizeLayout(name) {
  return LAYOUTS.includes(name) ? name : 'classic';
}

export function currentLayout() {
  return normalizeLayout(document.documentElement.getAttribute('data-layout'));
}

export function applyLayout(name) {
  const layout = normalizeLayout(name);
  document.documentElement.setAttribute('data-layout', layout);
  try { localStorage.setItem(LAYOUT_STORAGE_KEY, layout); } catch {}
  return layout;
}
