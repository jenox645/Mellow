"""MellowDLP downloader v3 — library/playlist smart download support."""
import json, datetime
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

HISTORY_FILE = Path.home() / '.mellow_dlp_history.json'

QUALITY_MAP = {
    'best':  'bestvideo+bestaudio/best',
    '4k':    'bestvideo[height<=2160]+bestaudio/best[height<=2160]',
    '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
    '720p':  'bestvideo[height<=720]+bestaudio/best[height<=720]',
    '480p':  'bestvideo[height<=480]+bestaudio/best[height<=480]',
    '360p':  'bestvideo[height<=360]+bestaudio/best[height<=360]',
}

# Format sort strings — better than raw -f for compatibility
FORMAT_SORT_MAP = {
    '1080p': 'vcodec:h264,res:1080,acodec:aac',
    '720p':  'vcodec:h264,res:720,acodec:aac',
    '480p':  'vcodec:h264,res:480,acodec:aac',
    '4k':    'vcodec:h264,res:2160,acodec:aac',
    'best':  'vcodec:h264,acodec:aac',
}


class Downloader:
    def __init__(self):
        self._cancelled = False
        self._ydl = None

    def cancel(self):
        self._cancelled = True

    def download(self, opts: dict, progress_cb):
        if yt_dlp is None:
            progress_cb({'status':'error','message':'yt-dlp not installed'}); return

        self._cancelled = False
        url = opts.get('url','')
        fmt_type = opts.get('format_type','VIDEO')
        output_dir = opts.get('download_dir', str(Path.home()/'Downloads'/'MellowDLP'))
        filename_tpl = opts.get('filename_template','%(title)s.%(ext)s')
        use_sort = opts.get('use_format_sort', False)
        library_id = opts.get('library_id')

        # Output template
        if fmt_type == 'PLAYLIST' or library_id:
            outtmpl = f"{output_dir}/{filename_tpl}"
        else:
            outtmpl = f"{output_dir}/%(title)s.%(ext)s"

        # Format
        if opts.get('custom_format'):
            fmt_str = opts['custom_format']
            format_sort = None
        elif use_sort:
            q = opts.get('quality','1080p').lower()
            fmt_str = 'bv+ba/b'
            format_sort = FORMAT_SORT_MAP.get(q, FORMAT_SORT_MAP['best'])
        elif fmt_type == 'AUDIO':
            fmt_str = 'bestaudio/best'
            format_sort = None
        else:
            q = opts.get('quality','best').lower()
            fmt_str = QUALITY_MAP.get(q, QUALITY_MAP['best'])
            format_sort = None

        # Post-processors
        pps = []
        if fmt_type == 'AUDIO':
            pps.append({'key':'FFmpegExtractAudio','preferredcodec':opts.get('audio_format','mp3'),'preferredquality':'0'})
        else:
            pass  # merge handled by merge_output_format

        if opts.get('embed_thumbnail'):
            pps.append({'key':'EmbedThumbnail'})
        if opts.get('embed_metadata') or opts.get('embed_chapters'):
            pps.append({'key':'FFmpegMetadata','add_metadata':True,'add_chapters':bool(opts.get('embed_chapters'))})
        if opts.get('sponsorblock'):
            pps.append({'key':'SponsorBlock','categories':['sponsor','intro','outro','selfpromo']})
        if opts.get('split_chapters'):
            pps.append({'key':'FFmpegSplitChapters'})

        # Clip / trim
        download_ranges = None
        cs, ce = opts.get('clip_start','').strip(), opts.get('clip_end','').strip()
        if cs or ce:
            s = _parse_time(cs) if cs else 0
            e = _parse_time(ce) if ce else float('inf')
            download_ranges = yt_dlp.utils.download_range_func(None, [(s, e)])
            pps.append({'key':'FFmpegFixupStretch'})

        # Subs
        sub_opts = {}
        if opts.get('embed_subs'):
            langs = opts.get('sub_langs','en')
            sub_opts = {
                'writesubtitles': True,
                'writeautomaticsub': opts.get('auto_subs', False),
                'subtitleslangs': [l.strip() for l in langs.split(',')],
                'embedsubtitles': True,
            }

        ydl_opts = {
            'format': fmt_str,
            'outtmpl': outtmpl,
            'writethumbnail': bool(opts.get('embed_thumbnail')),
            'postprocessors': pps,
            'progress_hooks': [self._make_hook(progress_cb, library_id)],
            'noprogress': True,
            'quiet': True,
            'ignoreerrors': True,  # don't abort on single-video errors in playlists
            'retries': 5,
            'fragment_retries': 10,
            'continuedl': True,
            'concurrent_fragment_downloads': int(opts.get('concurrent', 4)),
            **sub_opts,
        }

        if format_sort:
            ydl_opts['format_sort'] = [format_sort]

        if fmt_type != 'AUDIO':
            ydl_opts['merge_output_format'] = opts.get('container','mp4')

        if download_ranges:
            ydl_opts['download_ranges'] = download_ranges
            ydl_opts['force_keyframes_at_cuts'] = True

        if opts.get('cookies_file') and Path(opts['cookies_file']).exists():
            ydl_opts['cookiefile'] = opts['cookies_file']
        elif opts.get('cookies_from_browser'):
            ydl_opts['cookiesfrombrowser'] = (opts['cookies_from_browser'],)

        if opts.get('rate_limit'): ydl_opts['ratelimit'] = opts['rate_limit']
        if opts.get('proxy'): ydl_opts['proxy'] = opts['proxy']
        if opts.get('external_dl'): ydl_opts['external_downloader'] = opts['external_dl']
        if opts.get('archive_file'): ydl_opts['download_archive'] = opts['archive_file']
        if opts.get('playlist_start'): ydl_opts['playliststart'] = int(opts['playlist_start'])
        if opts.get('playlist_end'): ydl_opts['playlistend'] = int(opts['playlist_end'])
        if opts.get('date_after'): ydl_opts['dateafter'] = opts['date_after'].replace('-','')
        if opts.get('date_before'): ydl_opts['datebefore'] = opts['date_before'].replace('-','')
        if opts.get('sleep_interval'):
            ydl_opts['sleep_interval'] = float(opts['sleep_interval'])
        if opts.get('max_sleep_interval'):
            ydl_opts['max_sleep_interval'] = float(opts['max_sleep_interval'])
        if opts.get('sleep_requests'):
            ydl_opts['sleep_requests'] = float(opts['sleep_requests'])

        try:
            progress_cb({'status':'starting','url':url,'library_id':library_id})
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self._ydl = ydl
                try:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', url) if info else url
                except Exception:
                    title = url
                if self._cancelled:
                    progress_cb({'status':'cancelled'}); return
                code = ydl.download([url])
            if self._cancelled:
                progress_cb({'status':'cancelled'})
            elif code == 0:
                progress_cb({'status':'complete','title':title,'library_id':library_id})
                _append_history(url, title, fmt_type, opts)
            else:
                progress_cb({'status':'error','message':f'Exit code {code}','library_id':library_id})
        except yt_dlp.utils.DownloadError as e:
            progress_cb({'status':'error','message':_friendly(str(e)),'library_id':library_id})
        except Exception as e:
            if 'cancelled' in str(e).lower():
                progress_cb({'status':'cancelled'})
            else:
                progress_cb({'status':'error','message':str(e)[:300],'library_id':library_id})
        finally:
            self._ydl = None

    def _make_hook(self, cb, library_id=None):
        def hook(d):
            if self._cancelled: raise Exception('cancelled')
            s = d.get('status')
            if s == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                done  = d.get('downloaded_bytes', 0)
                speed = d.get('speed') or 0
                eta   = d.get('eta') or 0
                cb({
                    'status':'downloading',
                    'pct': int(done/total*100) if total else 0,
                    'downloaded': done, 'total': total,
                    'speed': _fmt_speed(speed), 'eta': _fmt_eta(eta),
                    'filename': Path(d.get('filename','')).name,
                    'library_id': library_id,
                })
            elif s == 'finished':
                cb({'status':'processing','library_id':library_id})
        return hook


def _parse_time(s):
    parts = s.strip().split(':')
    try:
        if len(parts)==3: return int(parts[0])*3600+int(parts[1])*60+float(parts[2])
        if len(parts)==2: return int(parts[0])*60+float(parts[1])
        return float(s)
    except: return 0.0

def _fmt_speed(b):
    if not b: return '—'
    return f'{b/1e6:.1f} MB/s' if b>1e6 else f'{b/1e3:.0f} KB/s'

def _fmt_eta(s):
    if not s: return '—'
    m,s=divmod(s,60); h,m=divmod(m,60)
    if h: return f'{h}h {m}m'
    if m: return f'{m}m {s}s'
    return f'{s}s'

def _friendly(msg):
    m = msg.lower()
    if 'sign in' in m or 'age' in m: return 'Age-restricted — add cookies in Settings.'
    if '403' in m: return 'HTTP 403 rate-limited — add cookies or set a rate limit.'
    if 'private' in m or 'unavailable' in m: return 'Video is private or unavailable.'
    if 'ffmpeg' in m: return 'FFmpeg not found — install it and restart.'
    return msg[:200]

def _append_history(url, title, fmt_type, opts):
    try:
        hist = []
        if HISTORY_FILE.exists(): hist = json.loads(HISTORY_FILE.read_text())
        hist.insert(0, {'url':url,'title':title,'type':fmt_type.lower(),
                        'date':datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                        'quality':opts.get('quality',''),'container':opts.get('container','')})
        HISTORY_FILE.write_text(json.dumps(hist[:100], indent=2))
    except: pass
