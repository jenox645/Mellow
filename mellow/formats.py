"""The on/off options a download can ask for, defined once.

A Feed download, a folder's remembered sync format, a library entry and its
syncs all carry these; each used to list them itself, so a new option had to
be added in a dozen places (and one missed was silently off). The frontend's
FORMAT_TOGGLES in gui/lib/constants.js mirrors this table (a test keeps them
in step), and library entries get one DB column per toggle automatically.
"""
from __future__ import annotations

# key → default when the request (or the stored entry) doesn't say
TOGGLES: dict[str, bool] = {
    "embed_thumbnail": True,
    "embed_chapters": True,
    "embed_metadata": True,
    "embed_subs": False,       # video only
    "sponsorblock": False,
    "normalize_audio": False,  # audio only
}

# The format choices that go with them in a remembered sync format
CHOICES: tuple[str, ...] = ("sync_audio", "audio_format", "audio_quality", "quality", "container")


def toggles(source: dict | None, fallback: dict | None = None) -> dict[str, bool]:
    """Every toggle as a bool: from `source`, else `fallback`, else its default.

    A missing, null or empty value counts as unset (a JSON null from an old
    client used to switch a default-on option off).
    """
    def given(d: dict | None, key: str):
        value = (d or {}).get(key)
        return None if value is None or value == "" else value

    out = {}
    for key, default in TOGGLES.items():
        value = given(source, key)
        if value is None:
            value = given(fallback, key)
        out[key] = default if value is None else bool(value)
    return out
