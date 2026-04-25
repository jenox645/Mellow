"""MellowDLP Flask backend v4."""
import os, sys, json, threading, time, subprocess, shutil, datetime, re
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory

if getattr(sys, 'frozen', False):
    BASE = Path(sys._MEIPASS)
else:
    BASE = Path(__file__).parent

STATIC = BASE / 'static'
app = Flask(__name__, static_folder=str(STATIC))

from downloader import Downloader
_dl = Downloader()
_events = []
_lock = threading.Lock()

CONFIG_FILE  = Path.home() / '.mellow_dlp.json'
HISTORY_FILE = Path.home() / '.mellow_dlp_history.json'
LIBRARY_FILE = Path.home() / '.mellow_dlp_library.json'

def load_config():
    d = {
        'download_dir': str(Path.home() / 'Downloads' / 'MellowDLP'),
        'cookies_file': '', 'cookies_from_browser': '',
        'rate_limit': '', 'concurrent': 4,
        'sponsorblock': False, 'proxy': '',
        'external_downloader': '', 'language': 'en',
    }
    if CONFIG_FILE.exists():
        try: d.update(json.loads(CONFIG_FILE.read_text()))
        except: pass
    os.makedirs(d['download_dir'], exist_ok=True)
    return d

def save_config(c): CONFIG_FILE.write_text(json.dumps(c, indent=2))

def load_history():
    if HISTORY_FILE.exists():
        try: return json.loads(HISTORY_FILE.read_text())
        except: pass
    return []

def load_library():
    if LIBRARY_FILE.exists():
        try: return json.loads(LIBRARY_FILE.read_text())
        except: pass
    return []

def save_library(lib): LIBRARY_FILE.write_text(json.dumps(lib, indent=2))

def push_event(d):
    with _lock:
        _events.append(d)
        if len(_events) > 300: _events.pop(0)

@app.route('/')
def index(): return send_from_directory(STATIC, 'index.html')

@app.route('/<path:p>')
def static_files(p): return send_from_directory(STATIC, p)

@app.route('/api/progress')
def progress_stream():
    def gen():
        last = 0
        while True:
            with _lock:
                new = _events[last:]; last = len(_events)
            for e in new: yield f'data: {json.dumps(e)}\n\n'
            time.sleep(0.1)
    return Response(gen(), mimetype='text/event-stream',
                    headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.route('/api/clipboard', methods=['GET'])
def read_clipboard():
    """Read clipboard server-side to avoid browser permission popup."""
    try:
        import subprocess as sp
        if sys.platform == 'win32':
            r = sp.run(['powershell','-command','Get-Clipboard'], capture_output=True, text=True, timeout=3)
            return jsonify({'text': r.stdout.strip()})
        elif sys.platform == 'darwin':
            r = sp.run(['pbpaste'], capture_output=True, text=True, timeout=3)
            return jsonify({'text': r.stdout.strip()})
        else:
            r = sp.run(['xclip','-selection','clipboard','-o'], capture_output=True, text=True, timeout=3)
            return jsonify({'text': r.stdout.strip()})
    except Exception as e:
        return jsonify({'text': '', 'error': str(e)})

@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    """Open a folder in Windows Explorer."""
    path = (request.json or {}).get('path', '')
    if not path: return jsonify({'error': 'No path'}), 400
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == 'win32':
            subprocess.Popen(['explorer', str(p)])
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(p)])
        else:
            subprocess.Popen(['xdg-open', str(p)])
        return jsonify({'status': 'opened'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def start_download():
    body = request.json or {}
    cfg = load_config()
    opts = {**cfg, **body}
    if not opts.get('url'): return jsonify({'error': 'No URL'}), 400
    threading.Thread(target=_dl.download, kwargs={'opts':opts,'progress_cb':push_event}, daemon=True).start()
    return jsonify({'status': 'started'})

@app.route('/api/cancel', methods=['POST'])
def cancel():
    _dl.cancel(); push_event({'status':'cancelled'})
    return jsonify({'status':'cancelled'})

@app.route('/api/info', methods=['POST'])
def get_info():
    url = (request.json or {}).get('url','')
    if not url: return jsonify({'error':'No URL'}), 400
    try:
        import yt_dlp
        cfg = load_config()
        opts = {'quiet':True,'no_warnings':True}
        if cfg.get('cookies_file') and Path(cfg['cookies_file']).exists():
            opts['cookiefile'] = cfg['cookies_file']
        if cfg.get('cookies_from_browser'):
            opts['cookiesfrombrowser'] = (cfg['cookies_from_browser'],)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        thumb = info.get('thumbnail','')
        for t in sorted(info.get('thumbnails',[]), key=lambda x: x.get('width',0), reverse=True):
            if t.get('width',9999) <= 640: thumb = t.get('url',thumb); break
        return jsonify({
            'title': info.get('title','Unknown'),
            'uploader': info.get('uploader',''),
            'duration': info.get('duration',0),
            'thumbnail': thumb,
            'platform': info.get('extractor_key',''),
            'is_playlist': info.get('_type') == 'playlist',
            'playlist_count': info.get('playlist_count'),
        })
    except Exception as e: return jsonify({'error':str(e)[:300]}), 500

@app.route('/api/config', methods=['GET'])
def get_config(): return jsonify(load_config())

@app.route('/api/config', methods=['POST'])
def post_config():
    cfg = load_config(); cfg.update(request.json or {}); save_config(cfg)
    return jsonify({'status':'saved'})

@app.route('/api/history', methods=['GET'])
def get_history(): return jsonify(load_history())

@app.route('/api/history', methods=['DELETE'])
def delete_history():
    body = request.json or {}
    hist = load_history()
    if 'ids' in body:
        ids = set(body['ids']); hist = [h for i,h in enumerate(hist) if i not in ids]
    elif 'older_than_days' in body:
        cut = datetime.datetime.now() - datetime.timedelta(days=body['older_than_days'])
        hist = [h for h in hist if datetime.datetime.strptime(h.get('date','1970-01-01 00:00'),'%Y-%m-%d %H:%M') > cut]
    else: hist = []
    HISTORY_FILE.write_text(json.dumps(hist, indent=2))
    return jsonify({'remaining':len(hist)})

@app.route('/api/library', methods=['GET'])
def get_library(): return jsonify(load_library())

@app.route('/api/library', methods=['POST'])
def add_library():
    body = request.json or {}
    lib = load_library()
    entry = {
        'id': str(int(time.time()*1000)),
        'name': body.get('name','Untitled'),
        'url': body.get('url',''),
        'folder': body.get('folder',''),
        'folder_name': body.get('folder_name',''),
        'use_subfolder': body.get('use_subfolder', True),
        'quality': body.get('quality','1080p'),
        'mode': body.get('mode','VIDEO'),
        'embed_thumbnail': body.get('embed_thumbnail', True),
        'embed_chapters': body.get('embed_chapters', True),
        'embed_metadata': body.get('embed_metadata', True),
        'embed_subs': body.get('embed_subs', False),
        'sub_langs': body.get('sub_langs','en'),
        'sponsorblock': body.get('sponsorblock', False),
        'filename_template': body.get('filename_template',''),
        'last_updated': None,
        'status': 'idle',
    }
    lib.append(entry); save_library(lib)
    return jsonify(entry)

@app.route('/api/library/<lid>', methods=['PUT'])
def update_library(lid):
    lib = load_library()
    for i,e in enumerate(lib):
        if e['id']==lid: lib[i].update(request.json or {}); lib[i]['id']=lid; save_library(lib); return jsonify(lib[i])
    return jsonify({'error':'Not found'}), 404

@app.route('/api/library/<lid>', methods=['DELETE'])
def delete_library(lid):
    save_library([e for e in load_library() if e['id']!=lid])
    return jsonify({'status':'deleted'})

@app.route('/api/library/<lid>/sync', methods=['POST'])
def sync_library(lid):
    body = request.json or {}
    sync_mode = body.get('mode','add')
    lib = load_library()
    entry = next((e for e in lib if e['id']==lid), None)
    if not entry: return jsonify({'error':'Not found'}), 404

    cfg = load_config()
    base_folder = entry.get('folder') or cfg['download_dir']
    if entry.get('use_subfolder'):
        folder_name = entry.get('folder_name') or entry.get('name') or 'Playlist'
        output_dir = str(Path(base_folder) / folder_name)
    else:
        output_dir = base_folder

    archive = str(Path(output_dir) / f'.mellow_archive_{lid}.txt')
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    opts = {
        **cfg,
        'url': entry['url'],
        'format_type': entry.get('mode','VIDEO'),
        'quality': entry.get('quality','1080p'),
        'container': 'mp4',
        'audio_format': 'mp3',
        'embed_thumbnail': entry.get('embed_thumbnail', True),
        'embed_subs': entry.get('embed_subs', False),
        'sub_langs': entry.get('sub_langs','en'),
        'embed_chapters': entry.get('embed_chapters', True),
        'embed_metadata': entry.get('embed_metadata', True),
        'sponsorblock': entry.get('sponsorblock', False),
        'archive_file': archive,
        'download_dir': output_dir,
        'filename_template': entry.get('filename_template') or '%(title)s [%(id)s].%(ext)s',
        'sleep_interval': 1.5,
        'max_sleep_interval': 5,
        'use_format_sort': True,
        'library_id': lid,
        'sync_mode': sync_mode,
    }

    def run():
        lib2 = load_library()
        for e in lib2:
            if e['id']==lid: e['status']='syncing'
        save_library(lib2)
        push_event({'status':'library_start','library_id':lid})

        if sync_mode == 'mirror':
            # For mirror mode: get current playlist IDs, compare with archive
            # This is handled in the downloader
            opts['mirror_mode'] = True

        _dl.download(opts=opts, progress_cb=push_event)

        lib3 = load_library()
        for e in lib3:
            if e['id']==lid:
                e['status']='idle'
                e['last_updated']=datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        save_library(lib3)
        push_event({'status':'library_done','library_id':lid})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'status':'started'})

@app.route('/api/check-ytdlp-update', methods=['GET'])
def check_update():
    """Check if a newer yt-dlp is available without installing it."""
    try:
        import yt_dlp
        current = yt_dlp.version.__version__
        # Check PyPI for latest
        r = subprocess.run(
            [sys.executable,'-m','pip','index','versions','yt-dlp'],
            capture_output=True, text=True, timeout=15
        )
        latest = current
        if r.returncode == 0:
            m = re.search(r'Available versions: ([^\n]+)', r.stdout)
            if m:
                versions = [v.strip() for v in m.group(1).split(',')]
                if versions: latest = versions[0]
        return jsonify({'current': current==latest, 'version': current, 'latest': latest})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/update-ytdlp', methods=['POST'])
def update_ytdlp():
    try:
        subprocess.run([sys.executable,'-m','pip','install','--upgrade','yt-dlp'],
                       capture_output=True, timeout=120)
        import importlib, yt_dlp; importlib.reload(yt_dlp)
        return jsonify({'version': yt_dlp.version.__version__})
    except Exception as e: return jsonify({'error':str(e)}), 500

@app.route('/api/system', methods=['GET'])
def system_info():
    ffmpeg = shutil.which('ffmpeg') is not None
    try:
        import yt_dlp; ver = yt_dlp.version.__version__
    except: ver = 'unknown'
    return jsonify({'ffmpeg':ffmpeg,'ytdlp_version':ver})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
