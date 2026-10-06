// The GUIDE: a step-by-step tour of each page. A step points at an element
// marked data-tour="<target>"; the Tour component lights it up and explains
// it. `reveal` opens what the target sits in first: each {click, unless}
// clicks `click` when `unless` is collapsed (OPTIONS, ADVANCED). A step whose
// target isn't on screen is shown in the middle, with `missing` saying when
// it appears.
'use strict';

export const TOURS = {
  feed: [
    {
      target: 'feed-url', title: 'Paste a link',
      text: 'A video, a playlist or a channel, from YouTube, SoundCloud or any of the 1000+ sites yt-dlp knows. '
        + 'ANALYZE reads it first. Type words instead of a link and it searches YouTube.',
      tip: 'Ctrl+V or dropping a link anywhere in the window does the same. Enter goes paste → analyze → download.',
    },
    {
      target: 'feed-import', title: 'Many links at once',
      text: 'IMPORT FILE takes a .txt with one link per line, or a mellow_archive.txt from another computer to download the same library again.',
    },
    {
      target: 'feed-save-to', title: 'SAVE TO',
      text: 'Where this download goes. Leave it empty for your default folder (Config → Download Path), or BROWSE for another one.',
      tip: '↑ / ↓ step through the folders you used before, like a terminal. Typing narrows the list.',
    },
    {
      target: 'feed-options', reveal: [{ click: 'feed-options-btn', unless: 'feed-options' }], title: 'Format and quality',
      text: 'VIDEO or AUDIO ONLY, then the quality and container, or the audio format and bitrate. '
        + 'Your choices stay when you paste the next link.',
      tip: 'PRESETS → + SAVE CURRENT keeps the whole set under a name, for one click next time.',
    },
    {
      target: 'feed-toggles', reveal: [{ click: 'feed-options-btn', unless: 'feed-options' }], title: 'Extras',
      text: 'Cover art, chapters and title/artist written into the file. Subtitles for videos. '
        + 'SponsorBlock cuts sponsor segments out (YouTube). Normalize Volume evens out loudness (audio).',
      tip: 'Hover a checkbox to see exactly what it does.',
    },
    {
      target: 'feed-advanced',
      reveal: [{ click: 'feed-options-btn', unless: 'feed-options' }, { click: 'feed-advanced-toggle', unless: 'feed-advanced-body' }], title: 'Only part of a video',
      text: 'CLIP START / END keeps just that stretch. A video with chapters also shows a CHAPTERS list: '
        + 'tick the ones you want, each becomes its own file.',
    },
    {
      target: 'feed-info', title: 'Before you download',
      missing: 'Shows up after ANALYZE.',
      text: 'Title, length and an estimated size, in red when it won\'t fit the drive. If you already have the video, '
        + 'it says so, with OPEN and SHOW IN FOLDER.',
      tip: 'DOWNLOAD starts now. ⏾ LATER waits for the night (Config → "Later" Downloads Start At).',
    },
    {
      target: 'feed-progress', title: 'Live progress',
      missing: 'Shows up while something downloads.',
      text: 'Speed, time left and every playlist item as it finishes. The Queue page has the full list.',
    },
  ],

  queue: [
    {
      target: 'queue-stats', title: 'At a glance',
      text: 'What is downloading, waiting, paused and failed right now.',
    },
    {
      target: 'queue-jobs', title: 'Jobs',
      missing: 'Shows up when downloads or syncs are waiting.',
      text: 'Every download and sync waits its turn here. ▲ ▼ change the order, ✕ cancels, ↻ RETRY runs a failed job again '
        + 'with the same options, ▶ START NOW skips a ⏾ LATER wait.',
      tip: 'Unfinished jobs survive a restart. Run up to 3 at once: Config → Concurrent Downloads.',
    },
    {
      target: 'queue-active', title: 'Now downloading',
      missing: 'Shows up while something downloads.',
      text: '⏸ pauses every running download where it is, ▶ carries on, ✕ cancels this one.',
    },
    {
      target: 'queue-playlist', title: 'Playlist items',
      missing: 'Shows up while a playlist downloads.',
      text: 'PENDING, COMPLETED and FAILED items of the playlist being downloaded. A failed item says why, '
        + 'and ↻ RETRY (or RETRY ALL) downloads it again with the same options.',
    },
  ],

  vault: [
    {
      target: 'vault-folders', title: 'Your library',
      text: 'Every folder MellowDLP downloads into, with thumbnails, item count and size. Click one to open it.',
      tip: 'SM / MD / LG at the top change the card size.',
    },
    {
      target: 'vault-add', title: 'Keep a playlist in sync',
      text: 'ADD PLAYLIST links a folder to a playlist or channel: it downloads everything, and each sync brings in what\'s new.',
    },
    {
      target: 'vault-watch', title: 'Folders you already have',
      text: 'WATCH FOLDER shows any folder on your computer here, even ones MellowDLP didn\'t fill.',
    },
    {
      target: 'vault-sync-all', title: 'Sync everything',
      missing: 'Shows up once a folder is linked to a playlist.',
      text: 'SYNC ALL queues a sync of every linked folder. Config → Auto-Sync Vault Folders does it on a schedule.',
    },
    {
      target: 'vault-dupes', title: 'Duplicates',
      text: 'FIND DUPES looks for the same video saved in more than one folder.',
    },
    {
      target: 'vault-card-menu', title: 'Folder menu',
      missing: 'Each folder card has a ⋮ menu in its corner.',
      text: '⋮ on a card: Stats & Budget (a size limit, with cleanup suggestions), Link Playlist, Sync, Rename, '
        + 'Generate Archive File (the list that stops anything downloading twice), Remove from Vault.',
    },
  ],

  vault_folder: [
    {
      target: 'vault-sync', title: 'Sync this folder',
      missing: 'Shows up when the folder is linked to a playlist.',
      text: 'SYNC NOW downloads what the playlist gained since last time. SYNC OPTIONS picks the format, '
        + 'and add-only or mirror (mirror also removes files gone from the playlist, after showing you the list).',
    },
    {
      target: 'vault-report', title: 'Sync report',
      missing: 'Shows up after this folder\'s first sync.',
      text: 'What the last syncs brought in, skipped (and why) and failed, with a retry for each failed item.',
    },
    {
      target: 'vault-tools', title: 'Find and pick',
      text: 'Search and sort the files. RANDOMIZE picks some at random to play; SELECT lets you play or delete several at once.',
    },
    {
      target: 'vault-files', title: 'Your files',
      text: 'Click to play in your player. ⋮ on a file: preview it in the app, show it in its folder, or delete it '
        + '(its thumbnail, subtitles and history go with it).',
    },
    {
      target: 'vault-back', title: 'Back',
      text: 'VAULT ROOT returns to all folders.',
    },
  ],

  analytics: [
    {
      target: 'analytics-range', title: 'Time range',
      text: 'Every number and chart below covers this period.',
    },
    {
      target: 'analytics-stats', title: 'Your numbers',
      text: 'Downloads, disk space, sites, speed, success rate and total duration, read from your download history.',
    },
    {
      target: 'analytics-wrapped', title: 'Wrapped',
      text: 'Your year in review: top uploaders, month by month, your busiest day, hours of content.',
    },
    {
      target: 'analytics-export', title: 'Export',
      text: 'EXPORT CSV saves the whole history as a spreadsheet.',
    },
    {
      target: 'analytics-charts', title: 'Charts',
      text: 'Sites, the hours you download at, storage growth, speed, failures and the health of your syncs.',
    },
  ],

  signal: [
    {
      target: 'signal-presets', title: 'Quick queries',
      text: 'Ready-made questions about your download history. Click one to load it.',
    },
    {
      target: 'signal-query', title: 'Ask anything',
      text: 'Write your own SQL (SELECT only, nothing can be changed) and EXECUTE. Results can be exported as CSV.',
    },
    {
      target: 'signal-schema', title: 'Tables and columns',
      text: 'SCHEMA REFERENCE lists what you can query: your downloads, your library and the sync log.',
    },
    {
      target: 'signal-api', title: 'Local API',
      text: 'API REFERENCE: the HTTP endpoints scripts and other apps can call to start downloads, read the queue or your history.',
      tip: 'Everything stays on this computer: the server only answers 127.0.0.1.',
    },
    {
      target: 'signal-webhooks', title: 'Webhooks',
      text: 'MellowDLP POSTs JSON to the URLs you add here when a download finishes or fails: a phone notification, a home server…',
    },
    {
      target: 'signal-events', title: 'Live events',
      text: 'LIVE EVENT STREAM shows every progress event as it happens, the same ones the app and the API see.',
    },
  ],

  config: [
    {
      target: 'config-save', title: 'Save your changes',
      text: 'Changes here apply when you click SAVE CONFIG. RESET DEFAULTS goes back to the original settings '
        + '(your presets, recent folders and history stay).',
    },
    {
      target: 'config-storage', title: 'Where files go',
      text: 'The default download folder, how files are named (with a live preview) and the archive file that stops anything downloading twice.',
    },
    {
      target: 'config-defaults', title: 'Download defaults',
      text: 'What the Feed starts with: video or audio, quality, formats. Subtitle languages, and skipping Shorts and live streams in playlists.',
    },
    {
      target: 'config-auth', title: 'Age-restricted and members-only videos',
      text: 'Lend MellowDLP the cookies of a browser where you\'re signed in, then TEST.',
    },
    {
      target: 'config-network', title: 'Network',
      text: 'Proxy, speed limit, retries, and Force IPv4 for connections where downloads hang.',
    },
    {
      target: 'config-behavior', title: 'Behavior',
      text: 'Downloads at once, the ⏾ LATER start time, what happens when the queue finishes, auto-sync, '
        + 'the copied-link suggestion, notifications, update checks and the completion sound.',
    },
    {
      target: 'config-backup', title: 'Backup',
      text: 'BACKUP saves your settings and history as one zip; RESTORE brings them back, here or on another computer.',
    },
    {
      target: 'config-ffmpeg', title: 'FFmpeg',
      text: 'The tool that merges, converts and trims. Missing? GET FFMPEG downloads and checks it for you.',
    },
    {
      target: 'config-versions', title: 'Updates',
      text: 'CHECK for a new MellowDLP and install it with one click. WHAT\'S NEW lists every release.',
    },
    {
      target: 'config-ytdlp', title: 'yt-dlp',
      text: 'The engine that talks to the sites. When downloads start failing (HTTP 403, "Sign in to confirm"), UPDATE it and restart.',
    },
  ],
};

// Which tour the GUIDE button starts: the vault has one for the folder list
// and one for an open folder.
export function tourIdFor(page, vaultFolderOpen) {
  if (page === 'vault' && vaultFolderOpen) return 'vault_folder';
  return TOURS[page] ? page : null;
}

// Where the explanation card goes: below the target if it fits, else above,
// else beside it; always inside the window. Rects are {left, top, width, height}.
export function placeCard(target, card, viewport, gap = 14, margin = 12) {
  const clampX = x => Math.max(margin, Math.min(x, viewport.width - card.width - margin));
  const clampY = y => Math.max(margin, Math.min(y, viewport.height - card.height - margin));
  if (!target) {
    return { side: 'center', left: clampX((viewport.width - card.width) / 2), top: clampY((viewport.height - card.height) / 2) };
  }
  const below = target.top + target.height + gap;
  if (below + card.height + margin <= viewport.height) {
    return { side: 'below', left: clampX(target.left), top: below };
  }
  const above = target.top - gap - card.height;
  if (above >= margin) {
    return { side: 'above', left: clampX(target.left), top: above };
  }
  const right = target.left + target.width + gap;
  if (right + card.width + margin <= viewport.width) {
    return { side: 'right', left: right, top: clampY(target.top) };
  }
  const left = target.left - gap - card.width;
  if (left >= margin) {
    return { side: 'left', left, top: clampY(target.top) };
  }
  // A target as big as the window: the card sits over its lower part
  return { side: 'over', left: clampX(target.left + 16), top: clampY(viewport.height - card.height - margin) };
}
