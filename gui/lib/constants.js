// Frontend tuning knobs — every timing/limit lives here, not inline.
'use strict';

// Splash
export const LOADING_MIN_MS = 1000;            // click-to-skip floor

// Toasts
export const NOTIF_TIMEOUT_MS = 6000;
export const NOTIF_ACTION_TIMEOUT_MS = 12000;  // toasts with buttons linger

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

// yt-dlp update check on launch
export const UPDATE_CHECK_EVERY_MS = 24 * 60 * 60 * 1000;
export const UPDATE_CHECK_STORAGE_KEY = 'mellow_ytdlp_check_ts';

// Clipboard watcher
export const CLIPBOARD_URL_RE = /^https?:\/\/\S+$/;

// Keyboard navigation — keys 1..N jump to these pages
export const PAGE_ORDER = ['feed', 'queue', 'vault', 'analytics', 'signal', 'config'];

// Tooltip of the SponsorBlock option (feed and library entries)
export const SPONSORBLOCK_HINT = 'Cut sponsor, intro, outro and self-promo segments out of YouTube downloads';

// Error patterns that usually mean yt-dlp is outdated
export const BREAKAGE_RE = /unable to extract|unsupported url|extractor|sign in to confirm|http error 403/i;
