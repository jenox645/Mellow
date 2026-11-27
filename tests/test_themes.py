"""Themes: one list of ids for the backend, the frontend and the page's early
script, and the `ui_theme` setting (Config → APPEARANCE)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mellow import config, constants
from tests.test_tester_feedback import _contrast

GUI = Path(__file__).resolve().parents[1] / "gui"


def _frontend_ids() -> list[str]:
    js = (GUI / "lib" / "constants.js").read_text(encoding="utf-8")
    block = js[js.index("export const THEMES"):]
    return re.findall(r"\{ id: '([\w-]+)'", block[:block.index("];")])


def test_the_frontend_lists_the_backends_themes():
    assert _frontend_ids() == list(constants.UI_THEMES)
    js = (GUI / "lib" / "constants.js").read_text(encoding="utf-8")
    assert re.search(r"DEFAULT_THEME = '(\w+)'", js).group(1) == config._DEFAULTS["ui_theme"]


def test_the_early_script_knows_the_same_themes():
    """index.html applies the remembered theme before the bundle loads, from its own copy of the list."""
    html = (GUI / "index.html").read_text(encoding="utf-8")
    listed = re.search(r"THEME_IDS = \[(.*?)\]", html).group(1)
    assert re.findall(r"'([\w-]+)'", listed) == list(constants.UI_THEMES)
    key = re.search(r"THEME_STORAGE_KEY = '([\w-]+)'", (GUI / "lib" / "constants.js").read_text(encoding="utf-8"))
    assert f"localStorage.getItem('{key.group(1)}')" in html


def test_every_theme_has_a_name_and_five_swatches():
    js = (GUI / "lib" / "constants.js").read_text(encoding="utf-8")
    block = js[js.index("export const THEMES"):]
    rows = re.findall(r"\{ id: '[\w-]+', name: '([^']+)', swatches: \[(.*?)\] \}", block[:block.index("];")])
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
    assert "ui_theme must be one of: classic, classic-light, archive, tactical" in r.get_json()["error"]
    saved = config.load_config()
    assert saved["ui_theme"] == "tactical"
    assert saved["sleep_interval"] != 9
    for bad in (None, 3, ["archive"], ""):
        assert client.post("/api/config", json={"ui_theme": bad}).status_code == 400, bad


def test_reset_defaults_goes_back_to_classic(client):
    client.post("/api/config", json={"ui_theme": "classic-light"})
    r = client.post("/api/config/reset", json={})
    assert r.get_json()["ui_theme"] == "classic"
    assert config.load_config()["ui_theme"] == "classic"


def test_a_renamed_theme_loads_as_the_theme_it_became(client):
    """White Tech (picked in a build of the theme foundation) is Classic Light now."""
    assert constants.UI_THEME_RENAMED == {"whitetech": "classic-light"}
    assert not set(constants.UI_THEME_RENAMED) & set(constants.UI_THEMES)
    assert set(constants.UI_THEME_RENAMED.values()) <= set(constants.UI_THEMES)
    config.save_config({**config.load_config(), "ui_theme": "whitetech"})
    assert config.load_config()["ui_theme"] == "classic-light"
    assert client.get("/api/config").get_json()["ui_theme"] == "classic-light"
    # the next save writes the new id
    config.update_config(lambda c: c.update(sleep_interval=3))
    assert json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))["ui_theme"] == "classic-light"
    # a broken value is left to the server's check, not turned into an error here
    config.save_config({**config.load_config(), "ui_theme": ["whitetech"]})
    assert config.load_config()["ui_theme"] == ["whitetech"]


def test_the_early_script_knows_the_renamed_themes():
    html = (GUI / "index.html").read_text(encoding="utf-8")
    renamed = re.search(r"RENAMED = \{(.*?)\}", html).group(1)
    assert dict(re.findall(r"([\w-]+): '([\w-]+)'", renamed)) == constants.UI_THEME_RENAMED


def test_classic_and_classic_light_share_one_card():
    js = (GUI / "lib" / "constants.js").read_text(encoding="utf-8")
    pairs = re.search(r"THEME_PAIRS = \[(.*?)\];", js).group(1)
    assert re.findall(r"dark: '([\w-]+)', light: '([\w-]+)'", pairs) == [("classic", "classic-light")]


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
def test_a_theme_declares_its_colour_scheme(theme):
    """WebKitGTK (the Tauri window on Linux) draws checkboxes, number fields and scrollbars in the
    declared scheme; index.html gives that engine Classic's dark one, which a light theme that
    declared none would keep (#117)."""
    scheme = re.compile(r"(^|;)\s*color-scheme:\s*(light|dark)\s*(;|$)")
    assert any(selectors.strip() == f':root[data-theme="{theme}"]' and scheme.search(body)
               for selectors, body in _rules(_css(theme))), f"{theme}.css: no color-scheme"


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


@pytest.mark.parametrize("theme", constants.UI_THEMES)
def test_the_file_menu_chip_shows_its_dots(theme):
    """The vault's ⋯ chip (.lib-menu) draws --t2 dots on --scrim-menu over a thumbnail of any colour:
    composited over black and over white, the dots keep 3:1 (an icon, WCAG 1.4.11)."""
    css = (GUI / "index.html").read_text(encoding="utf-8") if theme == "classic" else _css(theme)
    tokens = dict(re.findall(r"--(t2|scrim-menu):([^;]+);", css))
    r, g, b, a = (float(x) for x in re.fullmatch(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)", tokens["scrim-menu"].strip()).groups())
    for under in (0, 255):
        chip = "#" + "".join(f"{round(c * a + under * (1 - a)):02x}" for c in (r, g, b))
        assert _contrast(tokens["t2"], chip) >= 3, f"{theme}: ⋯ dots {tokens['t2']} on {chip}"


def test_classic_lights_colours_are_readable_as_text():
    """Classic Light writes its accents as text too (links, tags, ERROR / DONE words, the vault's amber):
    4.5:1 on every background, --danger included."""
    css = _css("classic-light")
    tokens = dict(re.findall(r"--([\w-]+):(#[0-9A-Fa-f]{6});", css))
    for colour in ("accent", "accent-hover", "accent-2", "accent-3", "warn", "danger", "success"):
        worst = min(_contrast(tokens[colour], tokens[bg]) for bg in ("bg", "bg1", "bg2", "bg3"))
        assert worst >= 4.5, f"--{colour} {tokens[colour]} is {worst:.2f}:1 on one background"
    # and the text on an accent-filled button / pill
    for fill in ("accent", "danger", "success"):
        assert _contrast(tokens["on-accent"], tokens[fill]) >= 4.5, fill


def test_classic_light_is_classic_in_structure():
    """Only colours and drawn-over details: Classic's fonts, and no rule that sizes or places a part."""
    css = _css("classic-light")
    classic = _classic_tokens()
    mine = dict(re.findall(r"(--[\w-]+):([^;]+);", css))
    for font in ("--font-display", "--font-body", "--font-mono"):
        assert mine[font] == classic[font]
    for token in mine:
        assert not token.startswith(("--radius", "--title-", "--label-", "--logo-", "--ptitle-", "--dur-", "--btn-clip", "--panel-clip")), token
    layout = re.compile(r"(?<![\w-])(width|height|min-width|min-height|max-width|max-height|margin[\w-]*|padding[\w-]*|"
                        r"font-size|line-height|gap|flex[\w-]*|grid[\w-]*|display|position|top|left|right|bottom|inset)\s*:")
    for selectors, body in _rules(css):
        if "::before" in selectors or "::after" in selectors:
            continue   # drawn-over pieces place themselves
        if selectors.strip() == ':root[data-theme="classic-light"]':
            continue
        assert not layout.search(body), f"{selectors} changes the layout: {body}"
