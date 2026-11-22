// The Config page's logic: its state, effects, API calls and handlers, shared by every theme.
// useConfigPage(props) takes what the App hands the page and returns everything a view
// draws and every handler it calls (the view itself never calls the API).
'use strict';

import { API, authHeaders, download } from '../lib/api.js';
import { fmtBytes } from '../lib/util.js';
import { DEFAULT_THEME, TEMPLATE_PREVIEW_DEBOUNCE_MS, THEMES } from '../lib/constants.js';

export function useConfigPage(props) {
  const { config, setConfig, showNotif, onAppUpdateChecked, refreshStats } = props;
  const [local, setLocal] = React.useState({ ...config });
  const [updateInfo, setUpdateInfo] = React.useState(null);
  const [appUpdate, setAppUpdate] = React.useState(null);
  const [checkingApp, setCheckingApp] = React.useState(false);
  const [checking, setChecking] = React.useState(false);
  const [updating, setUpdating] = React.useState(false);
  const [vacuuming, setVacuuming] = React.useState(false);
  const [dangerModal, setDangerModal] = React.useState(null);

  // The form follows the saved config, but a change to one setting (picking a theme saves at once)
  // must not wipe what was typed here and not saved yet: an edited key stays unless that key changed
  const prevConfig = React.useRef(config);
  React.useEffect(() => {
    const prev = prevConfig.current;
    prevConfig.current = config;
    setLocal(l => {
      const next = { ...config };
      for (const k of Object.keys(l)) {
        if (l[k] !== prev[k] && config[k] === prev[k]) next[k] = l[k];
      }
      return next;
    });
  }, [config]);

  const set = (key, val) => setLocal(l => ({ ...l, [key]: val }));

  // Only the keys this page edits — sending the whole stale `local` copy
  // clobbered vault_playlists/webhooks changes made since the page mounted
  const CONFIG_PAGE_KEYS = [
    'output_dir', 'filename_template',
    'cookies_browser', 'cookies_browser_profile', 'cookies_file',
    'rate_limit', 'proxy', 'force_ipv4', 'external_downloader',
    'concurrent_fragments', 'sleep_interval', 'retries',
    'write_metadata', 'skip_shorts', 'skip_live', 'sub_langs', 'auto_subs', 'keep_sub_files',
    'ui_victory_animation', 'ui_victory_sync',
    'default_mode', 'default_quality', 'default_container', 'default_audio_format', 'default_audio_quality',
    'download_workers', 'schedule_start', 'on_queue_done', 'keep_awake', 'auto_sync_enabled', 'auto_sync_default_interval',
    'update_check_on_launch', 'clipboard_watch', 'completion_sound', 'desktop_notifications',
    'api_port',
  ];
  const NUMERIC_DEFAULTS = { concurrent_fragments: 4, sleep_interval: 0, retries: 3, download_workers: 1, api_port: 0 };

  const handleSave = () => {
    const toSave = {};
    CONFIG_PAGE_KEYS.forEach(k => {
      if (local[k] === undefined) return;
      let v = local[k];
      if (k in NUMERIC_DEFAULTS) {
        const n = parseInt(v, 10);
        v = Number.isFinite(n) ? n : NUMERIC_DEFAULTS[k];
      }
      toSave[k] = v;
    });
    API.post('/api/config', toSave)
      .then(() => { setConfig(c => ({ ...c, ...toSave })); showNotif('Saved', 'Configuration updated', 'success'); })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  // APPEARANCE: a theme applies and saves when picked (the App follows config.ui_theme), no SAVE needed
  const currentTheme = THEMES.some(t => t.id === config.ui_theme) ? config.ui_theme : DEFAULT_THEME;
  // Quick picks save one after another, in click order; `saved` is the last theme the server took
  const themeSaves = React.useRef({ chain: Promise.resolve(), pending: 0, last: 0, saved: null });
  const pickTheme = id => {
    if (id === currentTheme) return;
    const s = themeSaves.current;
    if (!s.pending) s.saved = currentTheme;   // nothing on its way: what's shown is what's saved
    s.pending++;
    const pick = ++s.last;
    setConfig(c => ({ ...c, ui_theme: id }));
    s.chain = s.chain
      .then(() => API.post('/api/config', { ui_theme: id }))
      .then(() => { s.saved = id; }, e => {
        // Not saved: if it's still the latest pick, back to the saved theme so the next launch doesn't disagree
        if (pick === s.last) setConfig(c => (c.ui_theme === id ? { ...c, ui_theme: s.saved } : c));
        showNotif('Error', e.message, 'error');
      })
      .finally(() => { s.pending--; });
  };

  // Every setting back to the server's defaults (a list kept here missed
  // most of them); vault playlists, schedules, budgets and presets stay
  const handleReset = () => {
    API.post('/api/config/reset', {})
      .then(c => { setLocal(c); setConfig(c); showNotif('Reset', 'Defaults restored', 'success'); })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const browseFolder = () => {
    API.post('/api/browse-folder', {}).then(d => {
      if (!d.path) return;
      set('output_dir', d.path);
      // Saved at once, so the rest of the app (status bar OUT, the Feed's default folder) follows now
      API.post('/api/config', { output_dir: d.path })
        .then(() => setConfig(c => ({ ...c, output_dir: d.path })))
        .catch(e => showNotif('Error', e.message, 'error'));
    }).catch(e => showNotif('Error', e.message, 'error'));
  };

  // What a download would be named with the template being typed
  const [namePreview, setNamePreview] = React.useState(null);
  React.useEffect(() => {
    const template = local.filename_template || '';
    const t = setTimeout(() => {
      API.post('/api/filename-preview', { template })
        .then(d => setNamePreview(d))
        .catch(e => setNamePreview({ ok: false, error: e.message }));
    }, TEMPLATE_PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [local.filename_template]);

  // Reads the cookies with the values on screen, before they are saved
  const [testingCookies, setTestingCookies] = React.useState(false);
  const testCookies = () => {
    setTestingCookies(true);
    API.post('/api/cookies/test', {
      cookies_browser: local.cookies_browser, cookies_browser_profile: local.cookies_browser_profile,
      cookies_file: local.cookies_file,
    })
      .then(d => {
        const yt = d.youtube_signed_in ? 'signed in to YouTube' : 'not signed in to YouTube';
        if (d.undecryptable) {
          showNotif('Cookies Partly Readable', `${d.count} cookies read, ${d.undecryptable} encrypted by the browser — ${yt}. Firefox or a cookies.txt avoids this.`, 'warn');
        } else if (!d.count) {
          showNotif('No Cookies', 'The source is readable but empty — sign in with that browser/profile first.', 'warn');
        } else {
          showNotif('Cookies OK', `${d.count} cookies read — ${yt}.`, d.youtube_signed_in ? 'success' : 'info');
        }
      })
      .catch(e => {
        const d = e.data || {};
        // The hint says what to do. yt-dlp's own words follow, except where the hint already
        // says it all (encrypted cookies: the raw text repeats a DPAPI error and an issue link)
        const body = !d.hint ? e.message : d.code === 'cookies_encrypted' ? d.hint : d.hint + ' (' + e.message + ')';
        showNotif(d.title || 'Cookies Not Readable', body, 'error');
      })
      .finally(() => setTestingCookies(false));
  };

  const browseCookies = () => {
    API.post('/api/browse-file', { filter: '.txt' }).then(d => { if (d.path) set('cookies_file', d.path); });
  };

  const checkUpdate = () => {
    setChecking(true);
    API.get('/api/check-ytdlp-update')
      .then(setUpdateInfo)
      .catch(e => setUpdateInfo({ error: e.message }))
      .finally(() => setChecking(false));
  };

  const checkAppUpdate = () => {
    setCheckingApp(true);
    API.get('/api/check-app-update')
      .then(u => { setAppUpdate(u); if (onAppUpdateChecked) onAppUpdateChecked(u); })
      .catch(e => setAppUpdate({ error: e.message }))
      .finally(() => setCheckingApp(false));
  };

  const doVacuum = () => {
    setVacuuming(true);
    API.post('/api/analytics/vacuum', {})
      .then(d => showNotif('Vacuum complete', 'DB size: ' + fmtBytes(d.db_size_bytes), 'success'))
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setVacuuming(false));
  };

  const doPurge = () => {
    API.del('/api/history', { all: true })
      .then(d => {
        showNotif('Purged', d.deleted + ' records deleted', 'success');
        setDangerModal(null);
        if (refreshStats) refreshStats();
        API.get('/api/config').then(c => { setLocal(c); setConfig(c); }).catch(() => {});
      })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  // ── Backup / restore ────────────────────────────────────────────────────────
  const restoreInputRef = React.useRef(null);
  const [restoring, setRestoring] = React.useState(false);

  const handleRestoreFile = (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    setRestoring(true);
    fetch('/api/backup/restore', { method: 'POST', body: form, headers: authHeaders() })
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          showNotif('Backup Restored', (d.restored || []).join(' + ') + ' — restart recommended', 'success');
          API.get('/api/config').then(c => { setLocal(c); setConfig(c); }).catch(() => {});
          refreshStats && refreshStats();
        } else {
          showNotif('Restore Failed', d.error || 'Unknown error', 'error');
        }
      })
      .catch(err => showNotif('Restore Failed', err.message, 'error'))
      .finally(() => setRestoring(false));
  };

  // Desktop Notifications: switching it on asks for the permission on this click (browsers only
  // prompt from a user action), and switches back off when it isn't given
  const setDesktopNotifications = v => {
    set('desktop_notifications', v);
    if (v && typeof Notification !== 'undefined' && Notification.permission === 'default') {
      Notification.requestPermission().then(p => {
        if (p !== 'granted') { set('desktop_notifications', false); showNotif('Notifications blocked', 'Allow notifications for this app to use this', 'warn'); }
      });
    }
  };

  // The buttons that only ask the server to do something
  const browseCookiesProfile = () => {
    API.post('/api/browse-folder', {}).then(d => { if (d.path) set('cookies_browser_profile', d.path); });
  };

  // Download Archive File: OPEN FOLDER opens the download folder typed here
  const openArchiveFolder = () => {
    const dir = local.output_dir;
    if (dir) API.post('/api/open-folder', { path: dir }).catch(() => {});
    else showNotif('No folder', 'Set a download path first', 'info');
  };

  const openLog = () => {
    API.post('/api/open-log', {})
      .catch(e => e.status === 404
        ? showNotif('No log yet', e.message, 'info')
        : showNotif('Error', e.message, 'error'));
  };

  const downloadBackup = () => {
    download('/api/backup').catch(e => showNotif('Backup Failed', e.message, 'error'));
  };

  // A page in the browser: 'repo' (GitHub), 'nodejs', or none (the latest release)
  const openReleasePage = page => {
    API.post('/api/open-release', page ? { page } : {}).catch(() => {});
  };

  const updateYtdlp = () => {
    setUpdating(true);
    API.post('/api/update-ytdlp', {})
      .then(() => showNotif('Updating', 'yt-dlp update started'))
      .catch(e => showNotif('Error', e.message, 'error'))
      .finally(() => setUpdating(false));
  };

  return {
    ...props,
    // the form: what's on screen (saved by SAVE CONFIG →), and one setting changed
    local, set, handleSave, handleReset,
    // STORAGE
    browseFolder, namePreview, openArchiveFolder,
    // BEHAVIOR
    setDesktopNotifications,
    // AUTH (cookies)
    browseCookiesProfile, browseCookies, testCookies, testingCookies,
    // DATABASE / backup
    vacuuming, doVacuum, openLog, downloadBackup, restoreInputRef, restoring, handleRestoreFile,
    // versions: MellowDLP, yt-dlp, the GitHub / Node.js pages
    appUpdate, checkingApp, checkAppUpdate, updateInfo, checking, checkUpdate, updating, updateYtdlp, openReleasePage,
    // APPEARANCE
    currentTheme, pickTheme,
    // DANGER ZONE
    dangerModal, setDangerModal, doPurge,
  };
}
