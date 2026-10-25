"""YouTube's player challenges: every yt-dlp call may use any JavaScript
runtime yt-dlp supports (it used to look for Deno only), with yt-dlp-ejs'
solver scripts at the version yt-dlp takes (mellow/js_runtime.py)."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yt_dlp
from yt_dlp.globals import supported_js_runtimes

from mellow import downloader, js_runtime
from mellow.constants import NODEJS_DOWNLOAD_PAGE

ROOT = Path(__file__).resolve().parents[1]


# ── Every engine, in every yt-dlp call ────────────────────────────────────────

def test_every_engine_yt_dlp_supports_is_enabled():
    assert set(js_runtime.ytdlp_opts()) == set(supported_js_runtimes.value)
    assert js_runtime.ytdlp_opts() is not js_runtime.ytdlp_opts()     # yt-dlp edits it


def test_the_network_options_enable_them_and_yt_dlp_takes_them():
    opts: dict = {}
    downloader._apply_network_opts(opts, {})
    with yt_dlp.YoutubeDL({**opts, "quiet": True}) as ydl:
        # Before: yt-dlp's default, {"deno": {}}: Node, QuickJS and Bun never tried
        assert set(ydl.params["js_runtimes"]) == {"deno", "node", "quickjs", "bun"}
        assert set(ydl._js_runtimes) == {"deno", "node", "quickjs", "bun"}


def test_a_downloads_own_yt_dlp_options_get_them(tmp_path, monkeypatch):
    seen = {}

    class FakeYDL:
        def __init__(self, params):
            seen.update(params)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            return 0

        def add_post_processor(self, *a, **kw):
            pass

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)
    downloader.download_video("https://example.com/v", str(tmp_path), {"format": "video", "quality": "best"},
                              lambda e: None)
    assert set(seen["js_runtimes"]) == set(js_runtime.ENGINES)


# ── The solver scripts ────────────────────────────────────────────────────────

def test_the_solver_scripts_are_the_ones_this_yt_dlp_accepts():
    """yt-dlp checks the scripts' version and hash and skips any other: Node and
    QuickJS have no solver without them (only Deno and Bun can fetch theirs)."""
    import yt_dlp_ejs
    import yt_dlp_ejs.yt.solver as solver
    from yt_dlp.extractor.youtube.jsc._builtin import vendor
    assert yt_dlp_ejs.version.split(".")[:2] == vendor.VERSION.split(".")[:2]
    for name, code in (("yt.solver.lib.min.js", solver.lib()), ("yt.solver.core.min.js", solver.core())):
        assert hashlib.sha3_512(code.encode()).hexdigest() == vendor.HASHES[name], name


# ── Which one is installed ────────────────────────────────────────────────────

class _Info:
    def __init__(self, name, version, supported=True):
        self.name, self.version, self.supported = name, version, supported
        self.path = f"/usr/bin/{name}"


def _engines(monkeypatch, **installed):
    """Fake runtime classes: name → _Info (installed), Exception (lookup fails)."""
    calls = []

    def make(name):
        class Fake:
            def __init__(self, path=None):
                pass

            @property
            def info(self):
                calls.append(name)
                found = installed.get(name)
                if isinstance(found, Exception):
                    raise found
                return found
        return Fake

    monkeypatch.setattr(supported_js_runtimes, "value", {n: make(n) for n in js_runtime.ENGINES})
    js_runtime._cache = None
    return calls


@pytest.fixture(autouse=True)
def _fresh_cache():
    js_runtime._cache = None
    yield
    js_runtime._cache = None


def test_node_alone_is_found(monkeypatch):
    _engines(monkeypatch, node=_Info("node", "22.11.0"))
    assert js_runtime.found() == {"name": "node", "version": "22.11.0", "path": "/usr/bin/node",
                                  "supported": True}


def test_the_one_yt_dlp_prefers_is_named(monkeypatch):
    _engines(monkeypatch, bun=_Info("bun", "1.3.0"), node=_Info("node", "24.0.0"), deno=_Info("deno", "2.5.0"))
    assert js_runtime.found()["name"] == "deno"


def test_a_too_old_one_is_named_but_not_supported(monkeypatch):
    _engines(monkeypatch, node=_Info("node", "20.11.0", supported=False))
    assert js_runtime.found() == {"name": "node", "version": "20.11.0", "path": "/usr/bin/node",
                                  "supported": False}


def test_a_supported_one_wins_over_a_too_old_one(monkeypatch):
    _engines(monkeypatch, deno=_Info("deno", "1.46.0", supported=False), bun=_Info("bun", "1.3.0"))
    assert js_runtime.found()["name"] == "bun"


def test_nothing_installed_or_a_lookup_that_fails(monkeypatch):
    _engines(monkeypatch, node=OSError("permission denied"))
    assert js_runtime.found() is None
    assert "no JavaScript runtime" in js_runtime.describe(None)


def test_the_lookup_is_kept_for_a_while(monkeypatch):
    calls = _engines(monkeypatch, node=_Info("node", "22.11.0"))
    js_runtime.found()
    js_runtime.found()
    assert calls.count("node") == 1
    js_runtime.found(refresh=True)
    assert calls.count("node") == 2


def test_config_shows_it(client, monkeypatch):
    _engines(monkeypatch, node=_Info("node", "22.11.0"))
    assert client.get("/api/system").get_json()["js_runtime"]["name"] == "node"


def test_get_node_opens_its_download_page(client):
    with patch("mellow.desktop.open_url") as open_url:
        assert client.post("/api/open-release", json={"page": "nodejs"}).status_code == 200
        for _ in range(50):
            if open_url.called:
                break
            time.sleep(0.02)
    open_url.assert_called_once_with(NODEJS_DOWNLOAD_PAGE)


def test_the_log_names_it(monkeypatch, caplog):
    _engines(monkeypatch)
    with caplog.at_level("INFO", logger="mellow.js_runtime"):
        t = threading.Thread(target=js_runtime.log_found)
        t.start()
        t.join(5)
    assert "no JavaScript runtime found" in caplog.text


# ── An updated yt-dlp brings its own solver scripts ───────────────────────────

def _zipapp(path, version, ejs_version=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("__main__.py", "import yt_dlp")
        zf.writestr("yt_dlp/__init__.py", "from . import version\n")
        zf.writestr("yt_dlp/version.py", f"__version__ = '{version}'\n")
        if ejs_version:
            zf.writestr("yt_dlp_ejs/__init__.py", f"version = '{ejs_version}'\n")
            zf.writestr("yt_dlp_ejs/yt/__init__.py", "")
            zf.writestr("yt_dlp_ejs/yt/solver/__init__.py", "MARKER = 'overlay'\n")


_RUN = """
import sys
from pathlib import Path
from mellow import ytdlp_update
ytdlp_update.OVERLAY_PATH = Path(sys.argv[1])
ytdlp_update.bundled_version = lambda: '2026.08.19'
print(ytdlp_update.activate_overlay())
import yt_dlp_ejs, yt_dlp_ejs.yt.solver
print(yt_dlp_ejs.version, getattr(yt_dlp_ejs.yt.solver, 'MARKER', 'bundled'))
"""


def _run(zip_path):
    out = subprocess.run([sys.executable, "-c", _RUN, str(zip_path)], cwd=ROOT,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def test_the_downloaded_yt_dlp_uses_the_solver_scripts_it_came_with(tmp_path):
    """yt-dlp's release zipapp carries yt_dlp_ejs; the app's own copy is the
    version the bundled yt-dlp takes, which a newer yt-dlp may refuse."""
    _zipapp(tmp_path / "o.zip", "2099.01.01", ejs_version="9.9.0")
    assert _run(tmp_path / "o.zip") == ["2099.01.01", "9.9.0", "overlay"]


def test_a_download_without_them_keeps_the_apps_own(tmp_path):
    import yt_dlp_ejs
    _zipapp(tmp_path / "o.zip", "2099.01.01")
    assert _run(tmp_path / "o.zip") == ["2099.01.01", yt_dlp_ejs.version, "bundled"]
