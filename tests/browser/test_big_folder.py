"""A vault folder of thousands of files (#127): drawn a block per frame instead of
in one task that froze the window, with selecting and opening unchanged."""
import re

import pytest

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api").expect

N = 700
FIRST = 120            # gui/lib/constants.js PROGRESSIVE_FILES_FIRST


def _constant(name):
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "gui" / "lib" / "constants.js").read_text()
    return int(re.search(rf"export const {name} = (\d+);", text).group(1))


def _big_folder(downloads, name="Crate", n=N):
    folder = downloads / name
    folder.mkdir()
    for i in range(n):
        (folder / f"song {i:04d}.mp3").write_bytes(b"\0" * 16)
    return folder


def _open(page, name):
    page.locator(".nav-item", has_text="VAULT").click()
    page.get_by_title("Refresh vault").click()
    page.locator(".vault-folder-card", has_text=name).click()


def _first_paint_count(page, selector, action):
    """How many cards matching `selector` the first frame after `action` that has
    any shows (watched from before the action, frame by frame)."""
    page.evaluate("""(sel) => {
        window.__firstCount = 0;
        const look = () => {
            const n = document.querySelectorAll(sel).length;
            if (n) window.__firstCount = n; else requestAnimationFrame(look);
        };
        requestAnimationFrame(look);
    }""", selector)
    action()
    page.wait_for_function("window.__firstCount > 0", timeout=15_000)
    return page.evaluate("window.__firstCount")


@pytest.mark.parametrize("scale, card", [("md", ".lib-card"), ("list", ".lib-row")])
def test_a_big_folder_is_drawn_in_steps_and_ends_whole(page, downloads, scale, card):
    assert FIRST == _constant("PROGRESSIVE_FILES_FIRST")
    _big_folder(downloads)
    if scale == "list":
        _open(page, "Crate")
        page.locator(".lib-card").first.wait_for()
        # Another card size starts again from the first step too
        first = _first_paint_count(page, f"{card}[data-select-key]",
                                   lambda: page.locator(".pill", has_text="LIST").click())
    else:
        first = _first_paint_count(page, f"{card}[data-select-key]", lambda: _open(page, "Crate"))
    assert 0 < first <= FIRST, first
    expect(page.locator(f"{card}[data-select-key]")).to_have_count(N, timeout=15_000)
    names = page.locator(f"{card}[data-select-key]").evaluate_all(
        "els => els.map(e => e.getAttribute('data-select-key').split(/[\\\\/]/).pop())")
    assert names == [f"song {i:04d}.mp3" for i in range(N)]       # in order, none twice


def test_selecting_in_a_big_folder_sees_every_file(page, downloads):
    _big_folder(downloads)
    _open(page, "Crate")
    # Ctrl+A while the last blocks are still to come: every file, not the ones drawn
    page.locator(".vault-breadcrumb").wait_for()
    page.locator(".lib-card").first.wait_for()
    page.keyboard.press("Control+a")
    expect(page.locator(".vault-sel-count")).to_have_text(f"{N} SELECTED")
    expect(page.locator(".lib-card.file-selected")).to_have_count(N, timeout=15_000)
    page.keyboard.press("Escape")
    expect(page.locator(".lib-card.file-selected")).to_have_count(0)

    # A card of the first block, clicked after the others appeared, acts on the
    # selection as it is now (its block wasn't redrawn in between)
    cards = {i: page.locator(f".lib-card[data-select-key$='song {i:04d}.mp3']") for i in (3, 5, 650)}
    cards[650].click(modifiers=["Control"])
    cards[3].click(modifiers=["Control"])
    cards[5].click(modifiers=["Shift"])
    selected = page.locator(".lib-card.file-selected").evaluate_all(
        "els => els.map(e => e.getAttribute('data-select-key').split(/[\\\\/]/).pop())")
    assert selected == ["song 0003.mp3", "song 0004.mp3", "song 0005.mp3"], selected


def test_another_folder_starts_again_from_the_first_step(page, downloads):
    _big_folder(downloads, "Crate")
    _big_folder(downloads, "Shelf", 300)
    _open(page, "Crate")
    expect(page.locator(".lib-card[data-select-key]")).to_have_count(N, timeout=15_000)
    page.locator(".vbc-root").click()
    first = _first_paint_count(page, ".lib-card[data-select-key*='Shelf']",
                               lambda: page.locator(".vault-folder-card", has_text="Shelf").click())
    assert 0 < first <= FIRST, first
    expect(page.locator(".lib-card[data-select-key]")).to_have_count(300, timeout=15_000)
