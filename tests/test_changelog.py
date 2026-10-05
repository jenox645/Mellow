"""What's new: CHANGELOG.md, shipped with the app and shown after an update."""
from unittest.mock import patch

from mellow import changelog, config
from mellow.version import APP_VERSION

SAMPLE = """# Changelog

Intro text that isn't a release.

## 2.5.0
- **Faster**: everything is faster.
- **Wrapped item**: the text goes on
  on the next line.
- A line without a title.

## 2.4.0
- **GET FFMPEG**: one click.

## v2.3.0
- **SAVE TO**: folders.
"""


def test_this_version_has_release_notes():
    # Merging a version bump publishes it; the release workflow refuses one without notes
    assert changelog.section(APP_VERSION), f"CHANGELOG.md needs a '## {APP_VERSION}' section"
    shipped = [e["version"] for e in changelog.load()]
    assert shipped[0] == APP_VERSION, "the newest CHANGELOG.md section must be the current version"


def test_parse():
    entries = changelog.parse(SAMPLE)
    assert [e["version"] for e in entries] == ["2.5.0", "2.4.0", "2.3.0"]
    assert entries[0]["items"] == [
        {"title": "Faster", "text": "everything is faster."},
        {"title": "Wrapped item", "text": "the text goes on on the next line."},
        {"title": None, "text": "A line without a title."},
    ]


def test_section_is_the_raw_markdown_of_one_release(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(SAMPLE, encoding="utf-8")
    with patch.object(changelog, "CHANGELOG_PATH", path):
        assert changelog.section("2.4.0") == "- **GET FFMPEG**: one click."
        assert changelog.section("2.3.0") == "- **SAVE TO**: folders."
        assert changelog.section("1.0.0") is None


def _whats_new(path, last_seen, current="2.5.0", config_exists=True):
    if config_exists:
        config.update_config(lambda c: c.update(last_seen_version=last_seen))
    with patch.object(changelog, "CHANGELOG_PATH", path), patch.object(changelog, "APP_VERSION", current):
        return changelog.whats_new()


def test_whats_new_after_updating_lists_every_version_since(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(SAMPLE, encoding="utf-8")
    got = _whats_new(path, "2.3.0")
    assert got["show"] and [e["version"] for e in got["entries"]] == ["2.5.0", "2.4.0"]
    assert not _whats_new(path, "2.5.0")["show"]                  # already seen
    assert [e["version"] for e in _whats_new(path, "2.4.0", current="2.4.0")["entries"]] == []


def test_updated_from_before_whats_new_existed_shows_this_version(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(SAMPLE, encoding="utf-8")
    got = _whats_new(path, "")                                    # config exists, never seen
    assert [e["version"] for e in got["entries"]] == ["2.5.0"]


def test_a_fresh_install_starts_quiet(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(SAMPLE, encoding="utf-8")
    assert not config.CONFIG_PATH.exists()
    got = _whats_new(path, None, config_exists=False)
    assert got == {"current": "2.5.0", "show": False, "entries": []}
    assert config.load_config()["last_seen_version"] == "2.5.0"


def test_api_marks_seen_and_reset_keeps_it(client):
    config.update_config(lambda c: c.update(last_seen_version="0.0.1"))
    got = client.get("/api/whats-new").get_json()
    assert got["show"] and got["entries"][0]["version"] == APP_VERSION
    assert client.post("/api/whats-new/seen", json={}).status_code == 200
    assert client.get("/api/whats-new").get_json()["show"] is False
    every = client.get("/api/whats-new?all=1").get_json()["entries"]
    assert len(every) == len(changelog.load()) > 1
    config.reset_settings()
    assert client.get("/api/whats-new").get_json()["show"] is False
