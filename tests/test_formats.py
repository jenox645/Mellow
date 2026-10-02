"""The on/off download options, defined once (mellow/formats.py)."""
import re
from pathlib import Path

import duckdb

from mellow import analytics, formats, library, vault


def test_toggles_fill_defaults_and_treat_null_as_unset():
    t = formats.toggles({'embed_thumbnail': None, 'sponsorblock': 1, 'embed_subs': ''})
    assert t == {**formats.TOGGLES, 'sponsorblock': True}
    assert all(isinstance(v, bool) for v in t.values())
    # request first, then the fallback (a folder's remembered format), then the default
    assert formats.toggles({}, {'normalize_audio': True})['normalize_audio'] is True
    assert formats.toggles({'normalize_audio': False}, {'normalize_audio': True})['normalize_audio'] is False


def test_the_frontend_lists_the_same_toggles_with_the_same_defaults():
    js = (Path(__file__).resolve().parent.parent / 'gui' / 'lib' / 'constants.js').read_text(encoding='utf-8')
    block = js[js.index('export const FORMAT_TOGGLES'):]
    block = block[:block.index('];')]
    found = {k: d == 'true' for k, d in re.findall(r"key: '(\w+)'.*?def: (true|false)", block)}
    assert found == formats.TOGGLES


def test_every_toggle_reaches_downloads_syncs_and_library_entries(client, tmp_dir):
    on = {k: not d for k, d in formats.TOGGLES.items()}     # each one flipped from its default
    sync = vault.build_sync_opts(on, None, {}, tmp_dir)
    assert {k: sync[k] for k in formats.TOGGLES} == on
    assert set(vault.SYNC_FORMAT_KEYS) >= set(formats.TOGGLES)
    entry = library.build_entry({'name': 'L', 'url': 'https://x/pl', 'folder': tmp_dir, **on}, 'e9', '2026-01-01')
    analytics.upsert_library_entry(entry)
    stored = analytics.get_library_entry('e9')
    assert {k: stored[k] for k in formats.TOGGLES} == on
    opts, _ = library.build_sync_opts(stored, {}, 'add')
    assert {k: opts[k] for k in formats.TOGGLES} == on


def test_an_old_library_table_gains_the_toggle_columns(tmp_path, monkeypatch):
    db = tmp_path / 'old.duckdb'
    con = duckdb.connect(str(db))
    con.execute("""CREATE TABLE library (id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
        folder TEXT, folder_name TEXT, use_subfolder BOOLEAN DEFAULT true, quality TEXT DEFAULT '1080p',
        mode TEXT DEFAULT 'VIDEO', embed_thumbnail BOOLEAN DEFAULT true, embed_chapters BOOLEAN DEFAULT true,
        embed_metadata BOOLEAN DEFAULT true, embed_subs BOOLEAN DEFAULT false, sub_langs TEXT DEFAULT 'en',
        sponsorblock BOOLEAN DEFAULT false, filename_template TEXT DEFAULT '', sync_mode TEXT DEFAULT 'add',
        last_synced TIMESTAMP, created_at TIMESTAMP DEFAULT now())""")
    con.execute("INSERT INTO library (id, name, url, sponsorblock) VALUES ('old', 'Old', 'https://x/o', true)")
    con.close()
    monkeypatch.setattr(analytics, 'DB_PATH', db)
    analytics.reset_connections()
    analytics.init_db()
    old = analytics.get_library_entry('old')
    assert old['sponsorblock'] is True and old['normalize_audio'] is False
    assert old['container'] == 'mp4' and old['audio_format'] == 'mp3'
