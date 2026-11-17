"""Themes: one list of ids for the backend, the frontend and the page's early
script, and the `ui_theme` setting (Config → APPEARANCE)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from mellow import config, constants
from tests.test_tester_feedback import _contrast

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


# ── The theme files (gui/themes/<id>.css) ─────────────────────────────────────

OTHER_THEMES = [t for t in constants.UI_THEMES if t != "classic"]


def _css(theme: str) -> str:
    """A theme file without its comments."""
    return re.sub(r"/\*.*?\*/", "", (GUI / "themes" / f"{theme}.css").read_text(encoding="utf-8"), flags=re.S)


def _rules(css: str) -> list[tuple[str, str]]:
    """(selector list, declarations) of every style rule; @media and @supports are opened, @font-face is skipped."""
    rules, pos = [], 0
    while (brace := css.find("{", pos)) >= 0:
        prelude = css[pos:brace].strip()
        depth, end = 1, brace + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[end], 0)
            end += 1
        body = css[brace + 1:end - 1]
        if prelude.startswith(("@media", "@supports")):
            rules += _rules(body)
        elif not prelude.startswith("@"):
            rules.append((prelude, body))
        pos = end
    return rules


def _classic_tokens() -> dict[str, str]:
    html = (GUI / "index.html").read_text(encoding="utf-8")
    root = html[html.index(":root{"):]
    root = re.sub(r"/\*.*?\*/", "", root[:root.index("\n    }")], flags=re.S)
    return dict(re.findall(r"(--[\w-]+):([^;]+);", root))


def test_classic_is_the_page_itself():
    """Classic has no file: its tokens are index.html's :root, which no theme attribute narrows."""
    assert not (GUI / "themes" / "classic.css").exists()
    html = (GUI / "index.html").read_text(encoding="utf-8")
    assert 'data-theme="classic"' not in html
    for theme in OTHER_THEMES:
        assert html.index(f'href="themes/{theme}.css"') > html.index("</style>"), "after the page's own rules"


@pytest.mark.parametrize("theme", OTHER_THEMES)
def test_a_theme_file_only_styles_its_own_theme(theme):
    rules = _rules(_css(theme))
    assert rules
    scope = f':root[data-theme="{theme}"]'
    for selectors, _ in rules:
        for selector in selectors.split(","):
            assert selector.strip().startswith(scope), f"{theme}.css: {selector.strip()!r} reaches other themes"


@pytest.mark.parametrize("theme", OTHER_THEMES)
def test_a_theme_redefines_every_colour_font_and_glow(theme):
    """A token left out would show Classic's cyan or its glow in the middle of another theme."""
    classic = _classic_tokens()
    literal = re.compile(r"(?<!url\()#[0-9A-Fa-f]{3,8}\b|rgba?\(\d")
    needed = {name for name, value in classic.items()
              if literal.search(value) or name.endswith("-rgb") or name.startswith(("--glow-", "--canvas-", "--font-"))}
    needed -= {"--canvas-grid-size"}
    assert {"--bg", "--accent", "--accent-rgb", "--glow-text", "--font-mono", "--on-accent", "--scrim"} <= needed
    mine = dict(re.findall(r"(--[\w-]+):([^;]+);", _css(theme)))
    assert not needed - set(mine), f"{theme}.css leaves Classic's {sorted(needed - set(mine))}"
    assert not set(mine) - set(classic), f"{theme}.css sets tokens the page doesn't have: {sorted(set(mine) - set(classic))}"
    glows = [n for n in mine if n.startswith("--glow-")]
    assert glows and all(mine[n] == "none" for n in glows)
    assert mine["--canvas-scanlines"] == "none"


@pytest.mark.parametrize("theme", OTHER_THEMES)
def test_a_themes_text_is_readable_on_its_backgrounds(theme):
    """As for Classic (test_tester_feedback): 4.5:1 for every text level on every background."""
    tokens = dict(re.findall(r"--(bg\d?|t\d):(#[0-9A-Fa-f]{6});", _css(theme)))
    assert set(tokens) == {"bg", "bg1", "bg2", "bg3", "t1", "t2", "t3", "t4"}, "opaque #rrggbb, all eight"
    for text in ("t1", "t2", "t3", "t4"):
        worst = min(_contrast(tokens[text], tokens[bg]) for bg in ("bg", "bg1", "bg2", "bg3"))
        assert worst >= 4.5, f"{theme}: --{text} {tokens[text]} is {worst:.2f}:1 on one background"
    on = tokens["bg2"]
    steps = [_contrast(tokens[t], on) for t in ("t1", "t2", "t3", "t4")]
    assert steps == sorted(steps, reverse=True), f"{theme}: the text levels step down"
