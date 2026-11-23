"""A module imported the first time it's used, not when its importer is.

`server` and `jobs` reach `downloader` through one: it brings yt-dlp in (~0.45 s
and 20 MB), which nothing needs before the server answers. main.py's JavaScript
runtime check (js_runtime.log_found, on its own thread) loads yt-dlp right after
the start, in the background, so the first download or ANALYZE rarely waits.
"""
from __future__ import annotations

import importlib
from types import ModuleType


class LazyModule:
    def __init__(self, name: str) -> None:
        self._name = name

    def _module(self) -> ModuleType:
        return importlib.import_module(self._name)

    def __getattr__(self, attr: str):
        # Looked up on the module every time (never cached here), so a test's
        # patch of `mellow.downloader.<name>` is what the caller gets
        return getattr(self._module(), attr)

    def __repr__(self) -> str:
        return f"<lazy module {self._name!r}>"
