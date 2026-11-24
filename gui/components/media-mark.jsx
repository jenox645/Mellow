// What a vault file shows while it has no picture (no cover art inside, a video ffmpeg can't read, or the
// picture still loading): a drawn mark in the theme's ink, never an empty box. A disc for audio (its
// grooves, the label in the vault colour, the spindle) and a film frame for video (sprocket holes, a play
// mark). Thin lines at any size (non-scaling strokes); the picture, once loaded, lies over it.
'use strict';

const HOLES = [0, 1, 2, 3, 4, 5, 6];

export function MediaMark({ video, small }) {
  const cls = 'media-mark' + (small ? ' small' : '');
  if (video) {
    return (
      <svg className={cls} viewBox="0 0 64 40" aria-hidden="true" focusable="false">
        <rect x="4" y="3" width="56" height="34" />
        <line x1="4" y1="10" x2="60" y2="10" />
        <line x1="4" y1="30" x2="60" y2="30" />
        {!small && HOLES.map(i => <rect key={'t' + i} className="mm-hole" x={8.5 + i * 7.5} y="5.5" width="3" height="2" />)}
        {!small && HOLES.map(i => <rect key={'b' + i} className="mm-hole" x={8.5 + i * 7.5} y="32.5" width="3" height="2" />)}
        <path className="mm-hot" d="M28.5 14.5 L37.5 20 L28.5 25.5 Z" />
      </svg>
    );
  }
  return (
    <svg className={cls} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <circle cx="20" cy="20" r="17" />
      {!small && <circle className="mm-groove" cx="20" cy="20" r="13.5" />}
      {!small && <circle className="mm-groove" cx="20" cy="20" r="10.5" />}
      <circle className="mm-hot" cx="20" cy="20" r="6" />
      <circle className="mm-dot" cx="20" cy="20" r="1.3" />
    </svg>
  );
}
