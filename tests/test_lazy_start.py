"""Starting the app doesn't wait for yt-dlp (mellow/lazy.py).

Checked in a fresh process: in this one conftest and other tests have long
imported mellow.downloader, and yt-dlp with it.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

START = textwrap.dedent("""
    import sys
    from mellow.server import init_app
    init_app()
    assert "yt_dlp" not in sys.modules, "importing the server or init_app() imported yt_dlp"
    assert "mellow.downloader" not in sys.modules, "importing the server or init_app() imported the downloader"
    from mellow import jobs, server
    assert server.downloader.QUALITY_MAP
    assert callable(jobs.downloader.download_video)
    assert "mellow.downloader" in sys.modules and "yt_dlp" in sys.modules, "the first use didn't load them"
    print("started without yt_dlp; the first use loaded it")
""")


def test_the_server_starts_without_yt_dlp_and_loads_it_on_first_use(tmp_path):
    home = tmp_path / "home"
    for sub in ("AppData/Local", "AppData/Roaming", ".local/share"):
        (home / sub).mkdir(parents=True)
    # This account's files (config, database, queue, data folder) all in the throwaway home
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MELLOW_")}
    env.update(HOME=str(home), USERPROFILE=str(home), LOCALAPPDATA=str(home / "AppData" / "Local"),
               APPDATA=str(home / "AppData" / "Roaming"), XDG_DATA_HOME=str(home / ".local" / "share"))
    result = subprocess.run([sys.executable, "-c", START], cwd=ROOT, env=env, capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "started without yt_dlp" in result.stdout
    assert (home / ".mellow_dlp.duckdb").exists()        # init_app ran in the throwaway home
