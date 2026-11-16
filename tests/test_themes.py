"""Themes: one list of ids for the backend, the frontend and the page's early
script, and the `ui_theme` setting (Config → APPEARANCE)."""
from __future__ import annotations

import re
from pathlib import Path

from mellow import config, constants

GUI = Path(__file__).resolve().parents[1] / "gui"


def _frontend_ids() -> list[str]:
    js = (GUI / "lib" / "constants.js").read_text(encoding="utf-8")
    block = js[js.index("export const THEMES"):]
    return re.findall(r"\{ id: '(\w+)'", block[:block.index("];")])


def test_the_frontend_lists_the_backends_themes():
    assert _frontend_ids() == list(constants.UI_THEMES)
    js = (GUI / "lib" / "constants.js").read_text(encoding="utf-8")
    assert re.search(r"DEFAULT_THEME = '(\w+)'", js).group(1) == config._DEFAULTS["ui_theme"]


def test_the_early_script_knows_the_same_themes():
    """index.html applies the remembered theme before the bundle loads, from its own copy of the list."""
    html = (GUI / "index.html").read_text(encoding="utf-8")
    listed = re.search(r"THEME_IDS = \[(.*?)\]", html).group(1)
    assert re.findall(r"'(\w+)'", listed) == list(constants.UI_THEMES)
    key = re.search(r"THEME_STORAGE_KEY = '([\w-]+)'", (GUI / "lib" / "constants.js").read_text(encoding="utf-8"))
    assert f"localStorage.getItem('{key.group(1)}')" in html


def test_every_theme_has_a_name_and_five_swatches():
    js = (GUI / "lib" / "constants.js").read_text(encoding="utf-8")
    block = js[js.index("export const THEMES"):]
    rows = re.findall(r"\{ id: '\w+', name: '([^']+)', swatches: \[(.*?)\] \}", block[:block.index("];")])
    assert len(rows) == len(constants.UI_THEMES)
    for name, swatches in rows:
        assert name
        assert len(re.findall(r"'#[0-9A-Fa-f]{6}'", swatches)) == 5, name


def test_the_theme_is_classic_until_one_is_picked():
    assert constants.UI_THEMES[0] == "classic"
    assert config.load_config()["ui_theme"] == "classic"


def test_picking_a_theme_saves_it(client):
    assert client.post("/api/config", json={"ui_theme": "archive"}).status_code == 200
    assert client.get("/api/config").get_json()["ui_theme"] == "archive"


def test_an_unknown_theme_is_refused_and_nothing_is_saved(client):
    client.post("/api/config", json={"ui_theme": "tactical"})
    r = client.post("/api/config", json={"ui_theme": "neon", "sleep_interval": 9})
    assert r.status_code == 400
    assert "ui_theme must be one of: classic, whitetech, archive, tactical" in r.get_json()["error"]
    saved = config.load_config()
    assert saved["ui_theme"] == "tactical"
    assert saved["sleep_interval"] != 9
    for bad in (None, 3, ["archive"], ""):
        assert client.post("/api/config", json={"ui_theme": bad}).status_code == 400, bad


def test_reset_defaults_goes_back_to_classic(client):
    client.post("/api/config", json={"ui_theme": "whitetech"})
    r = client.post("/api/config/reset", json={})
    assert r.get_json()["ui_theme"] == "classic"
    assert config.load_config()["ui_theme"] == "classic"
