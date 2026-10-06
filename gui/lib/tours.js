// The GUIDE: a step-by-step tour of each page. A step points at an element
// marked data-tour="<target>"; the Tour component lights it up and explains
// it. `reveal` opens what the target sits in first: each {click, unless}
// clicks `click` when `unless` is collapsed (OPTIONS, ADVANCED). A step
// without a target explains an idea rather than a part of the page. A step
// whose part isn't on screen is shown in the middle, with `missing` saying
// when it appears.
//
// `example` shows a made-up sample inside the card:
//   {kind: 'rows', rows: [{text, sub, badge, tone}]}   a list, like the real one
//   {kind: 'file', name, lines: []}                     a text file's content
//   {kind: 'pairs', pairs: [[left, right]]}             what turns into what
// `onlyMissing: true` shows it only while the real part isn't on screen.
'use strict';

const OPTIONS = { click: 'feed-options-btn', unless: 'feed-options' };

export const TOURS = {
  feed: [
    {
      target: 'feed-url', title: 'Paste a link',
      text: 'A video, a whole playlist or a channel, from YouTube, SoundCloud, Bandcamp, Twitch, Vimeo or any of the '
        + '1000+ sites yt-dlp knows. ANALYZE reads it first and shows what you\'ll get. Type words instead of a link '
        + 'and it searches YouTube: pick a result and it is analyzed.',
      tip: 'Ctrl+V or dropping a link anywhere in the window does the same. Enter goes paste → analyze → download.',
      example: { kind: 'pairs', pairs: [
        ['youtube.com/watch?v=…', 'one video'],
        ['youtube.com/playlist?list=…', 'every video of the playlist'],
        ['youtube.com/@channel', 'the whole channel'],
        ['lofi hip hop', 'YouTube search results'],
      ] },
    },
    {
      target: 'feed-paste', title: 'PASTE',
      text: 'Puts whatever link you copied into the box. Copied a link before switching to MellowDLP? '
        + 'It offers to analyze it as soon as the window comes back to the front.',
      tip: 'That suggestion can be turned off: Config → Clipboard Watcher.',
    },
    {
      target: 'feed-import', title: 'Many links at once',
      text: 'IMPORT FILE reads a .txt with one link per line and queues them all as one download. It also reads a '
        + 'mellow_archive.txt from another computer, which turns back into the links of everything in that folder.',
      tip: 'Moving to a new PC? Import each folder\'s mellow_archive.txt and the same library downloads again.',
      example: { kind: 'file', name: 'links.txt', lines: [
        'https://youtu.be/dQw4w9WgXcQ',
        'https://soundcloud.com/artist/track',
        'https://youtube.com/playlist?list=PL…',
      ] },
    },
    {
      target: 'feed-save-to', title: 'SAVE TO',
      text: 'Where this download goes. Leave it empty for your default folder (Config → Download Path), type a path, '
        + 'or BROWSE for one. A folder that doesn\'t exist yet is created.',
      tip: '↑ / ↓ step through the folders you used before, like a terminal. Typing narrows the list to the matching ones.',
      example: { kind: 'rows', rows: [
        { text: 'D:/Music/Lofi', badge: '↑ 1' },
        { text: 'D:/Videos/Courses', badge: '↑ 2' },
        { text: 'C:/Users/you/Downloads/MellowDLP', badge: '↑ 3' },
      ] },
    },
    {
      target: 'feed-options', reveal: [OPTIONS], title: 'Format and quality',
      text: 'VIDEO or AUDIO ONLY. For video: the quality (BEST takes the highest the site has) and the container — '
        + 'MP4 plays everywhere, MKV holds anything, WebM is smaller. For audio: MP3 for any player, M4A/AAC/Opus are '
        + 'smaller at the same quality, FLAC/WAV are lossless.',
      tip: 'These choices stay when you paste the next link, and survive switching pages.',
    },
    {
      target: 'feed-presets', reveal: [OPTIONS], title: 'Presets',
      text: '+ SAVE CURRENT keeps every option you set (format, quality, extras) under a name. One click on it '
        + 'sets them all again. ✕ deletes one.',
      tip: 'Make one per habit: "Music" (MP3 320, cover art, normalized) and "Lectures" (720p, subtitles, SponsorBlock).',
      example: { kind: 'rows', rows: [
        { text: 'MUSIC', sub: 'MP3 · 320k · cover art · normalize volume' },
        { text: 'LECTURES', sub: 'MP4 · 720p · subtitles · SponsorBlock' },
      ] },
    },
    {
      target: 'feed-toggles', reveal: [OPTIONS], title: 'Extras',
      text: 'Embed Thumbnail puts the cover art into the file. Chapters and Metadata (title, artist, date) are written '
        + 'in too. Subtitles (video) embeds them. SponsorBlock cuts sponsor segments, intros and "like and subscribe" '
        + 'reminders out of YouTube videos. Normalize Volume (audio) evens out loudness from one track to the next.',
      tip: 'Hover a checkbox to see exactly what it does. Subtitle languages: Config → Subtitle Languages.',
    },
    {
      target: 'feed-advanced', reveal: [OPTIONS, { click: 'feed-advanced-toggle', unless: 'feed-advanced-body' }],
      title: 'Only part of a video',
      text: 'CLIP START / END keeps just that stretch. A video with chapters also shows a CHAPTERS list above: tick '
        + 'the ones you want and each becomes its own file. CUSTOM FORMAT STRING is a yt-dlp format for experts.',
      example: { kind: 'pairs', pairs: [
        ['CLIP 00:01:30 → 00:03:00', 'just those 90 seconds'],
        ['CHAPTERS: 2, 5', 'Mix - 02 Intro.mp3, Mix - 05 Outro.mp3'],
      ] },
    },
    {
      target: 'feed-info', title: 'Before you download',
      missing: 'Shows up after ANALYZE.',
      text: 'Title, length, the site and an estimated size, in red when it won\'t fit the drive. If you already '
        + 'downloaded this video, it says when, with OPEN and SHOW IN FOLDER.',
      tip: 'DOWNLOAD starts now. ⏾ LATER queues it for a set time, like the night (Config → "Later" Downloads Start At). '
        + '↺ RESCAN reads the link again.',
      example: { onlyMissing: true, kind: 'rows', rows: [
        { text: 'Lofi Girl — beats to relax/study to', sub: 'Lofi Girl · YouTube · 1:02:13' },
        { text: '≈ 84 MB', badge: '1080P', tone: 'cyan' },
        { text: '✓ ALREADY DOWNLOADED 3 DAYS AGO', badge: 'OPEN', tone: 'green' },
      ] },
    },
    {
      target: 'feed-progress', title: 'Live progress',
      missing: 'Shows up while something downloads.',
      text: 'Speed, time left, and every playlist item as it finishes, fails or waits. ⏸ PAUSE stops every download '
        + 'where it is; CANCEL stops this one.',
      tip: 'You can keep browsing other pages: the window title shows the progress, and a chime plays at the end.',
      example: { onlyMissing: true, kind: 'rows', rows: [
        { text: '3 / 12 — Track three', sub: '4.2 MB/s · 0:12 left', badge: '62%', tone: 'cyan' },
        { text: 'Track two', badge: 'DONE', tone: 'green' },
        { text: 'Track one', badge: 'DONE', tone: 'green' },
      ] },
    },
  ],

  queue: [
    {
      target: 'queue-stats', title: 'At a glance',
      text: 'What is downloading, waiting, paused and failed right now.',
      tip: 'Keys 1 to 6 jump between pages: 2 brings you here from anywhere.',
    },
    {
      target: 'queue-jobs', title: 'Jobs',
      missing: 'Shows up when downloads or syncs are waiting.',
      text: 'Every download and vault sync waits its turn here. ▲ ▼ change the order, ✕ cancels or removes, '
        + '↻ RETRY runs a failed job again with the same options, ▶ START NOW skips a ⏾ LATER wait.',
      tip: 'Unfinished jobs survive closing the app: you\'re asked to resume them at the next start. '
        + 'Run up to 3 at once with Config → Concurrent Downloads.',
      example: { onlyMissing: true, kind: 'rows', rows: [
        { text: 'FEED  Lofi Girl — beats to relax', sub: '62% · 4.2 MB/s', badge: 'ACTIVE', tone: 'cyan' },
        { text: 'SYNC  Music/Chill', badge: 'QUEUED' },
        { text: 'FEED  Conference talk', badge: '⏾ 02:00', tone: 'purple' },
        { text: 'FEED  Old upload', sub: 'Private video', badge: '↻ RETRY', tone: 'red' },
      ] },
    },
    {
      target: 'queue-active', title: 'Now downloading',
      missing: 'Shows up while something downloads.',
      text: '⏸ pauses every running download where it is, ▶ carries on, ✕ cancels this one. A paused download '
        + 'keeps what it already has.',
      tip: 'Pause before a video call or a game: nothing is lost.',
    },
    {
      target: 'queue-playlist', title: 'Playlist items',
      text: 'The items of the playlist being downloaded, in three tabs: PENDING, COMPLETED and FAILED. A failed '
        + 'item says why; ↻ RETRY downloads it again with the same options, RETRY ALL does every one.',
      tip: '✕ on a pending item skips it. CLEAR ✕ empties a tab.',
      example: { kind: 'rows', rows: [
        { text: 'Track four', badge: 'PENDING' },
        { text: 'Track two', sub: 'Not available in your country', badge: '↻ RETRY', tone: 'red' },
      ] },
    },
  ],

  vault: [
    {
      target: 'vault-folders', title: 'Your library',
      text: 'Every folder MellowDLP downloads into, with a mosaic of what\'s inside, the number of files and their '
        + 'size. Click one to open it. ↻ on a linked card opens its sync; a red OVER BUDGET badge means it grew past its limit.',
      tip: 'SM / MD / LG at the top change the card size; ↻ REFRESH rescans the disk.',
      example: { onlyMissing: true, kind: 'rows', rows: [
        { text: 'Chill', sub: '214 MEDIA · 1.8 GB', badge: '↻ SYNCED', tone: 'cyan' },
        { text: 'Courses', sub: '36 MEDIA · 9.2 GB', badge: 'OVER BUDGET', tone: 'red' },
      ] },
    },
    {
      target: 'vault-add', title: 'Keep a playlist in sync',
      text: 'ADD PLAYLIST links a folder to a playlist or channel. The first sync downloads everything; each sync '
        + 'after that only brings in what was added since. Pick the format once, it\'s remembered for that folder.',
      tip: 'A private playlist (like your Liked videos) needs Config → Browser Cookies from a signed-in browser.',
      example: { kind: 'pairs', pairs: [
        ['Playlist "Chill" (214 videos)', 'folder Chill/'],
        ['+ 3 new videos tomorrow', 'next sync downloads just those 3'],
      ] },
    },
    {
      target: null, title: 'Add-only or mirror',
      text: 'Each linked folder syncs one of two ways. ADD ONLY never deletes anything: videos removed from the '
        + 'playlist stay on your disk. MIRROR makes the folder match the playlist exactly, so a video removed from the '
        + 'playlist is deleted here too — after it shows you the list and you confirm.',
      tip: 'Choose it in SYNC OPTIONS (the ⋮ menu → Sync). Not sure? ADD ONLY.',
      example: { kind: 'rows', rows: [
        { text: 'video removed from the playlist', badge: 'ADD ONLY: kept', tone: 'green' },
        { text: 'video removed from the playlist', badge: 'MIRROR: deleted', tone: 'red' },
      ] },
    },
    {
      target: null, title: 'The archive file',
      text: 'Each folder holds a mellow_archive.txt: one line per video already in it (site + video id). Before '
        + 'downloading, yt-dlp checks it, so nothing ever downloads twice, even when you rename or move the files. '
        + 'MellowDLP keeps it up to date when you download, sync and delete.',
      tip: 'It doubles as a backup of your library: import it in the Feed (IMPORT FILE) on another computer and '
        + 'everything in it downloads again. ⋮ → Generate Archive File creates one for a folder that has none.',
      example: { kind: 'file', name: 'Chill/mellow_archive.txt', lines: [
        'youtube dQw4w9WgXcQ',
        'youtube 5qap5aO4i9A',
        'soundcloud 1873462291',
      ] },
    },
    {
      target: 'vault-watch', title: 'Folders you already have',
      text: 'WATCH FOLDER shows any folder on your computer here, even ones MellowDLP didn\'t fill, so you can browse, '
        + 'play and clean it up like the others. It gets a WATCHED badge.',
      tip: 'A watched folder can be linked to a playlist later (⋮ → Link Playlist).',
    },
    {
      target: 'vault-sync-all', title: 'Sync everything',
      missing: 'Shows up once a folder is linked to a playlist.',
      text: 'SYNC ALL queues a sync of every linked folder, each in its own format.',
      tip: 'Or let it happen by itself: Config → Auto-Sync Vault Folders, then each folder\'s schedule (every 6 h, '
        + 'daily, weekly) in its sync options.',
    },
    {
      target: 'vault-dupes', title: 'Duplicates',
      text: 'FIND DUPES looks for the same video saved in more than one folder and can delete the smaller copies.',
      tip: 'Handy after importing old downloads with WATCH FOLDER.',
    },
    {
      target: 'vault-card-menu', title: 'Folder menu',
      missing: 'Each folder card has a ⋮ menu in its corner.',
      text: '⋮ on a card: Stats & Budget, Link Playlist, Sync, Open in Explorer, Rename, Generate Archive File, '
        + 'Remove from Vault (which only forgets the folder: your files stay).',
      tip: 'Stats & Budget sets a size limit. Past it, the card says OVER BUDGET and suggests which files to remove, '
        + 'oldest first.',
      example: { kind: 'pairs', pairs: [
        ['Budget 5 GB, folder 6.3 GB', 'OVER BUDGET'],
        ['Suggested', '4 oldest files · frees 1.4 GB'],
      ] },
    },
  ],

  vault_folder: [
    {
      target: 'vault-sync', title: 'Sync this folder',
      missing: 'Shows up when the folder is linked to a playlist.',
      text: 'SYNC NOW downloads what the playlist gained since the last sync, in the folder\'s format.',
      tip: 'A private playlist needs Config → Browser Cookies from the account that owns it, or the sync fails '
        + 'with "playlist does not exist".',
    },
    {
      target: 'vault-sync-options', title: 'Sync options',
      missing: 'Shows up when the folder is linked to a playlist.',
      text: 'The format and extras for this folder, ADD ONLY or MIRROR, and its auto-sync schedule: off, every 6 h, '
        + 'daily or weekly. MIRROR previews what it would delete before you confirm.',
      example: { kind: 'rows', rows: [
        { text: 'SYNC MODE', badge: 'ADD ONLY', tone: 'cyan' },
        { text: 'AUTO-SYNC', badge: 'DAILY', tone: 'cyan' },
        { text: 'FORMAT', badge: 'MP3 · 320K' },
      ] },
    },
    {
      target: 'vault-report', title: 'Sync report',
      missing: 'Shows up after this folder\'s first sync.',
      text: 'What the last syncs did: what came in, what was skipped and why (already there, a Short, a live '
        + 'stream), and what failed, with ↻ RETRY for each failed item.',
      example: { kind: 'rows', rows: [
        { text: 'Today 09:14 — 3 new · 211 already there', badge: 'OK', tone: 'green' },
        { text: 'Old upload', sub: 'Private video', badge: '↻ RETRY', tone: 'red' },
      ] },
    },
    {
      target: 'vault-tools', title: 'Search and sort',
      text: 'Find a file by name, and sort by name, size or date.',
      tip: 'TOTAL shows how many files match the search.',
    },
    {
      target: 'vault-random', title: 'Randomize',
      text: 'Pick a number, PICK, and MellowDLP chooses that many files at random; ▶ PLAY opens them in your player '
        + 'as a playlist.',
      tip: 'Can\'t decide what to watch tonight? Pick 3.',
    },
    {
      target: 'vault-select', title: 'Several at once',
      text: 'SELECT, then click files to tick them: ▶ PLAY plays them together, DELETE removes them all.',
    },
    {
      target: 'vault-files', title: 'Your files',
      text: 'Click a file to play it in your usual player. ⋮ on a file: Preview in App, Open in Explorer, or Delete '
        + '(its thumbnail, subtitles and history line go with it).',
      tip: 'A deleted file stays listed in the archive file, so the next sync won\'t download it again.',
    },
    {
      target: 'vault-open', title: 'The real folder',
      text: 'OPEN IN EXPLORER shows this folder on your disk. ↻ REFRESH rescans it after you add or remove files '
        + 'outside MellowDLP.',
    },
    {
      target: 'vault-back', title: 'Back',
      text: 'VAULT ROOT returns to all folders.',
      tip: 'Press G again there for the folder list\'s own guide.',
    },
  ],

  analytics: [
    {
      target: 'analytics-range', title: 'Time range',
      text: 'Every number and chart below covers this period: the last 7 days, 30 days, or all time.',
    },
    {
      target: 'analytics-stats', title: 'Your numbers',
      text: 'Downloads, disk space, sites and average speed, read from your download history.',
      tip: 'Click a number to set it yourself, for example to count downloads from before MellowDLP. '
        + 'Empty it to go back to the real count.',
    },
    {
      target: 'analytics-wrapped', title: 'Wrapped',
      text: 'Your year in review: top uploaders, month by month, your busiest day, hours of content and how you '
        + 'split video and audio.',
    },
    {
      target: 'analytics-export', title: 'Export',
      text: 'EXPORT CSV saves the whole download history as a spreadsheet: titles, links, sizes, dates, formats.',
    },
    {
      target: 'analytics-charts', title: 'Charts',
      text: 'Which sites you download from, the hours you download at, storage growing over time, speed per day, '
        + 'failures per day, and a day × hour heatmap.',
      tip: 'Many failures on one day usually means yt-dlp needed an update that day.',
    },
    {
      target: 'analytics-sync-health', title: 'Sync health',
      text: 'The last 10 vault syncs: how many new files each brought, what it skipped, its errors and how long it took.',
    },
    {
      target: 'analytics-recent', title: 'Recent downloads',
      text: 'The last 10 downloads, newest first.',
    },
  ],

  signal: [
    {
      target: 'signal-presets', title: 'Quick queries',
      text: 'Ready-made questions about your history: most downloaded channels, storage by format, largest files, '
        + 'failed downloads, sync history… Click one to load it, then EXECUTE.',
    },
    {
      target: 'signal-query', title: 'Ask anything',
      text: 'Write your own SQL and EXECUTE. Only SELECT works, so nothing can be changed or deleted. Results can be '
        + 'exported as CSV.',
      example: { kind: 'file', name: 'example query', lines: [
        'SELECT uploader, COUNT(*) AS videos',
        'FROM downloads',
        "WHERE platform = 'youtube'",
        'GROUP BY uploader ORDER BY videos DESC',
      ] },
    },
    {
      target: 'signal-schema', title: 'Tables and columns',
      text: 'SCHEMA REFERENCE lists what you can query: your downloads, your library and the sync log.',
      tip: 'Every download is one row of downloads, with its title, url, uploader, platform, format, size and status.',
    },
    {
      target: 'signal-api', title: 'Local API',
      text: 'API REFERENCE: the HTTP endpoints scripts and other apps can call to start downloads, read the queue or '
        + 'your history.',
      tip: 'Everything stays on this computer: the server only answers 127.0.0.1.',
      example: { kind: 'file', name: 'from a script', lines: [
        'POST /api/download',
        '{"url": "https://youtu.be/dQw4w9WgXcQ", "mode": "audio"}',
      ] },
    },
    {
      target: 'signal-webhooks', title: 'Webhooks',
      text: 'MellowDLP sends a JSON message to each URL you add here when a download finishes or fails: '
        + 'a phone notification service, a home server, a Discord channel…',
      example: { kind: 'file', name: 'what your URL receives', lines: [
        '{"status": "complete",',
        ' "title": "Lofi beats",',
        ' "file_path": "D:/Music/Lofi beats.mp3",',
        ' "file_size": 8421376}',
      ] },
    },
    {
      target: 'signal-events', title: 'Live events',
      text: 'LIVE EVENT STREAM shows every progress event as it happens, the same ones the app and the API see.',
      tip: 'Useful to see exactly what goes wrong in a download.',
    },
  ],

  config: [
    {
      target: 'config-save', title: 'Save your changes',
      text: 'Changes on this page apply when you click SAVE CONFIG. RESET DEFAULTS goes back to the original '
        + 'settings; your presets, recent folders, budgets and history stay.',
    },
    {
      target: 'config-storage', title: 'Where files go',
      text: 'Download Path is the default folder (the Feed\'s SAVE TO can pick another each time).',
    },
    {
      target: 'config-template', title: 'File names',
      text: 'How downloaded files are named, with yt-dlp fields. A "/" makes subfolders. The line under it names a '
        + 'sample video with your template.',
      example: { kind: 'pairs', pairs: [
        ['%(title)s.%(ext)s', 'Never Gonna Give You Up.mp4'],
        ['%(uploader)s/%(title)s.%(ext)s', 'Rick Astley/Never Gonna Give You Up.mp4'],
        ['%(playlist_index)03d - %(title)s.%(ext)s', '003 - Never Gonna Give You Up.mp4'],
      ] },
    },
    {
      target: 'config-archive', title: 'Archive file',
      text: 'Every download folder keeps a mellow_archive.txt of what it holds, so nothing downloads twice, and the '
        + 'file can rebuild the library on another computer. OPEN FOLDER shows where it is.',
      tip: 'The Vault\'s GUIDE explains it in detail.',
      example: { kind: 'file', name: 'mellow_archive.txt', lines: ['youtube dQw4w9WgXcQ', 'youtube 5qap5aO4i9A'] },
    },
    {
      target: 'config-defaults', title: 'Download defaults',
      text: 'What the Feed starts with: video or audio, quality, container, audio format and bitrate. Subtitle '
        + 'languages, automatic captions and keeping .srt files. Skipping Shorts and live streams in playlists.',
      tip: 'Subtitle languages: "en", "en,fr", "en.*" (every English variant) or "all".',
    },
    {
      target: 'config-auth', title: 'Private playlists, age-restricted and members-only videos',
      text: 'MellowDLP can borrow the sign-in of a browser where you\'re logged in to YouTube. Pick it under Browser '
        + 'Cookies, then TEST: it says how many cookies it read and whether you\'re signed in.',
      tip: 'On Windows, Chrome, Edge and Brave lock their cookies away ("cookies are encrypted"). Use Firefox, or '
        + 'export a cookies.txt with the "Get cookies.txt LOCALLY" extension, set Browser Cookies to Disabled and '
        + 'choose the file under Cookies File.',
      example: { kind: 'rows', rows: [
        { text: 'Private playlist, "does not exist"', badge: 'needs cookies', tone: 'amber' },
        { text: '"Sign in to confirm you\'re not a bot"', badge: 'needs cookies', tone: 'amber' },
        { text: 'Firefox → TEST', badge: 'Cookies OK', tone: 'green' },
      ] },
    },
    {
      target: 'config-network', title: 'Network',
      text: 'Proxy (to reach videos blocked in your country), a speed limit so downloads don\'t take all your '
        + 'bandwidth, retries, a pause between playlist items, and more parallel pieces for faster downloads.',
      tip: 'Analyze or downloads hang for minutes? Turn on Force IPv4.',
      example: { kind: 'pairs', pairs: [['Rate Limit 5M', 'at most 5 MB/s'], ['Proxy socks5://host:1080', 'through that server']] },
    },
    {
      target: 'config-behavior', title: 'Behavior',
      text: 'How many downloads run at once, the ⏾ LATER start time, what happens when the queue finishes (open the '
        + 'folder), auto-sync of vault folders, the copied-link suggestion, notifications, update checks and the '
        + 'completion sound.',
      tip: 'Auto-Sync Vault Folders must be on for the folders\' sync schedules to run.',
    },
    {
      target: 'config-backup', title: 'Backup',
      text: '⬇ BACKUP saves your settings and download history as one zip; ⬆ RESTORE brings them back, here or on '
        + 'another computer. The current ones are kept as .pre-restore copies.',
      tip: 'Your media files aren\'t in the zip; the archive files in each folder are their backup.',
    },
    {
      target: 'config-ffmpeg', title: 'FFmpeg',
      text: 'The tool that merges video and audio, converts to MP3 and others, trims clips and embeds cover art. '
        + 'Missing? GET FFMPEG downloads it, checks it and uses it right away.',
    },
    {
      target: 'config-versions', title: 'Updates',
      text: 'CHECK looks for a new MellowDLP; UPDATE installs it and restarts, no browser needed. It also checks at '
        + 'every start and every 6 hours. WHAT\'S NEW lists every release.',
    },
    {
      target: 'config-ytdlp', title: 'yt-dlp',
      text: 'The engine that talks to the sites. Sites change often, so when downloads start failing (HTTP 403, '
        + '"Sign in to confirm", "Unable to extract"), CHECK, UPDATE and restart MellowDLP.',
    },
    {
      target: 'config-log', title: 'Log file',
      text: 'What MellowDLP did, step by step. OPEN LOG shows it: useful when something fails without a clear reason, '
        + 'or to attach to a bug report.',
    },
    {
      target: 'config-danger', title: 'Danger zone',
      text: 'PURGE deletes the whole download history (the analytics and the "already downloaded" notes). '
        + 'Your files stay on disk.',
      tip: 'Make a BACKUP first if you might want it back.',
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
