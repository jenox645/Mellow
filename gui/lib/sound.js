// Tiny WebAudio chime for download completion — no asset files needed.
'use strict';

const CHIME_NOTES_HZ = [659.25, 880];  // E5 → A5
const NOTE_LENGTH_S = 0.18;
const NOTE_GAP_S = 0.12;
const CHIME_GAIN = 0.08;

let _ctx = null;

export function playCompletionChime() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    if (!_ctx) _ctx = new AudioCtx();
    const now = _ctx.currentTime;
    CHIME_NOTES_HZ.forEach((freq, i) => {
      const osc = _ctx.createOscillator();
      const gain = _ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      const start = now + i * NOTE_GAP_S;
      gain.gain.setValueAtTime(CHIME_GAIN, start);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + NOTE_LENGTH_S);
      osc.connect(gain).connect(_ctx.destination);
      osc.start(start);
      osc.stop(start + NOTE_LENGTH_S);
    });
  } catch {
    // Audio is best-effort; never let it break the UI
  }
}
