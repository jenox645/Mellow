// Frontend tuning knobs — every timing/limit lives here, not inline.
'use strict';

// Splash
export const LOADING_MIN_MS = 1000;            // click-to-skip floor

// Toasts
export const NOTIF_TIMEOUT_MS = 6000;
export const NOTIF_ACTION_TIMEOUT_MS = 12000;  // toasts with buttons linger

// Analyze
export const ANALYZE_SLOW_MS = 15000;          // show the "still analyzing" hint after this

// Polling
export const STATS_POLL_ACTIVE_MS = 3000;      // while downloading
export const STATS_POLL_IDLE_MS = 30000;
export const QUEUE_POLL_MS = 4000;             // jobs list on the Queue page

// Victory overlay
export const VICTORY_AUTO_DISMISS_MS = 5000;
export const VICTORY_FADE_MS = 800;

// Buffers
export const SPEED_HISTORY_LEN = 60;
export const COMPLETED_ITEMS_KEEP = 200;
export const FAILED_ITEMS_KEEP = 100;
export const LIVE_EVENTS_KEEP = 50;

// History browser
export const HISTORY_LIMIT = 25;
export const HISTORY_SEARCH_DEBOUNCE_MS = 250;
export const TEMPLATE_PREVIEW_DEBOUNCE_MS = 300;  // Config filename template → example name

// yt-dlp update check on launch
export const UPDATE_CHECK_EVERY_MS = 24 * 60 * 60 * 1000;
export const UPDATE_CHECK_STORAGE_KEY = 'mellow_ytdlp_check_ts';
// A new MellowDLP is looked for at every launch, then this often while it runs
export const APP_UPDATE_POLL_MS = 6 * 60 * 60 * 1000;

// Clipboard watcher
export const CLIPBOARD_URL_RE = /^https?:\/\/\S+$/;

// Keyboard navigation — keys 1..N jump to these pages
export const PAGE_ORDER = ['feed', 'queue', 'vault', 'analytics', 'signal', 'config'];

// Tooltip of the SponsorBlock option (feed and library entries)
// Tooltip of the Normalize Volume option (audio downloads)
export const NORMALIZE_HINT = 'Even out loudness across tracks (EBU R128, -14 LUFS, as streaming services play them). Re-encodes the audio';

export const SPONSORBLOCK_HINT = 'Cut sponsor, intro, outro and self-promo segments out of YouTube downloads';

// The on/off download options — mirrors mellow/formats.py TOGGLES (a test
// keeps the keys and defaults in step). `only`: shown for that media alone.
export const FORMAT_TOGGLES = [
  { key: 'embed_thumbnail', label: 'Embed Thumbnail', def: true },
  { key: 'embed_subs', label: 'Subtitles', def: false, only: 'video' },
  { key: 'normalize_audio', label: 'Normalize Volume', def: false, only: 'audio', hint: NORMALIZE_HINT },
  { key: 'embed_chapters', label: 'Chapters', def: true },
  { key: 'embed_metadata', label: 'Metadata', def: true },
  { key: 'sponsorblock', label: 'SponsorBlock', def: false, hint: SPONSORBLOCK_HINT },
];

// Download choices — one list for the Feed, the vault dialogs and Config, so
// they can't drift apart (the vault dialog used to lack 4K and 360P)
export const QUALITIES = ['best', '4k', '1080p', '720p', '480p', '360p'];
export const CONTAINERS = ['mp4', 'mkv', 'webm'];
export const AUDIO_FORMATS = ['mp3', 'aac', 'flac', 'm4a', 'opus', 'wav'];
export const LOSSLESS_AUDIO = ['flac', 'wav'];
// [value, label]; 'best' = highest-quality VBR
export const AUDIO_QUALITIES = [['best', 'BEST'], ['320', '320K'], ['256', '256K'], ['192', '192K'], ['128', '128K']];

// Error patterns that usually mean yt-dlp is outdated
export const BREAKAGE_RE = /unable to extract|unsupported url|extractor|sign in to confirm|http error 403/i;

// GUIDE (components/tour.jsx)
export const TOUR_PAD_PX = 6;               // spotlight margin around the part it explains
export const TOUR_REVEAL_WAIT_MS = 380;     // after opening OPTIONS/ADVANCED (their CSS transition is 0.3s)
export const TOUR_SCROLL_WAIT_MS = 320;     // smooth scroll to the part before pointing at it
