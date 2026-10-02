// The on/off download options (FORMAT_TOGGLES), as one object {key: bool}.
'use strict';

import { FORMAT_TOGGLES } from './constants.js';

export function defaultToggles() {
  return Object.fromEntries(FORMAT_TOGGLES.map(t => [t.key, t.def]));
}

// Each toggle from `source` (a preset, a saved sync format), its default when unset
export function togglesFrom(source) {
  return Object.fromEntries(FORMAT_TOGGLES.map(t => {
    const v = source ? source[t.key] : undefined;
    return [t.key, v === undefined || v === null || v === '' ? t.def : !!v];
  }));
}

// The toggles that apply to a video or an audio download
export function togglesFor(media) {
  return FORMAT_TOGGLES.filter(t => !t.only || t.only === media);
}
