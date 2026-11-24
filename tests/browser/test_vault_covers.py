"""#109: a folder of FLACs copied in from elsewhere (no sidecar thumbnails) shows their covers, read from
the files themselves, and a song with no cover shows the drawn mark instead of an empty box."""
import shutil
import subprocess

import pytest

from tests.test_vault_thumbs import _audio, _with_cover

pytestmark = pytest.mark.browser

LOADED = "img => img.complete && img.naturalWidth > 0 && getComputedStyle(img).display !== 'none'"


def test_a_folder_of_flacs_shows_their_covers(page, downloads, tmp_path):
    expect = pytest.importorskip("playwright.sync_api").expect
    cover = tmp_path / "cover.jpg"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=200x200",
                    "-frames:v", "1", str(cover)], check=True)
    folder = downloads / "Copied FLACs"
    for name in ("01 First", "02 Second", "03 Third"):
        _with_cover(_audio(folder / f"{name}.flac"), cover.read_bytes())
    _audio(folder / "04 No Cover.flac")
    page.locator(".nav-item", has_text="VAULT").click()
    page.get_by_title("Refresh vault").click()
    card = page.locator(".vault-folder-card", has_text="Copied FLACs")
    # The folder's card: a mosaic of the covers inside its files
    expect(card.locator(".vfc-mosaic-cell")).to_have_count(3)
    page.wait_for_function(f"() => [...document.querySelectorAll('.vfc-mosaic-cell')].every({LOADED})")
    card.click()
    expect(page.locator(".lib-card")).to_have_count(4)
    page.wait_for_function(
        f"() => [...document.querySelectorAll('.lib-card')].filter(c => /First|Second|Third/.test(c.textContent))"
        f".every(c => {{ const img = c.querySelector('.lib-thumb img'); return img && ({LOADED})(img); }})")
    # No cover: the drawn disc shows, and no picture lies over it
    plain = page.locator(".lib-card", has_text="No Cover")
    expect(plain.locator(".media-mark")).to_be_visible()
    expect(plain.locator(".lib-thumb img")).to_be_hidden()
    # Nothing was written into the music folder
    assert sorted(p.name for p in folder.iterdir()) == ["01 First.flac", "02 Second.flac", "03 Third.flac",
                                                        "04 No Cover.flac"]
