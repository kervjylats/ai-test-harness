"""
adapters/windows_desktop.py

Drives a Flutter Windows desktop build (the actual .exe) via pywinauto,
which talks to Windows' own UI Automation accessibility layer.

⚠️ STATUS: scaffolded, not verified — I have no Windows desktop available
in the sandbox this was written in, and this is genuinely the roughest of
the three adapters in practice (Flutter's Windows accessibility-tree
support is less mature than its Android/Web output). Budget real
debugging time here — this is why the earlier recommendation was to
build this one last, after Web and Android prove the harness works.

One-time setup on YOUR machine:
    pip install pywinauto

Project config keys this adapter reads:
    "exe_path":    path to the built .exe
                   (flutter build windows, then find it under
                   build/windows/x64/runner/Release/)
    "window_title": the window's title bar text — used to find/attach
                   to the right window once launched
"""

import subprocess
import time
from pathlib import Path

from pywinauto import Application
from pywinauto.keyboard import send_keys

from .base import Adapter


class WindowsDesktopAdapter(Adapter):
    def __init__(self):
        self._app = None
        self._window = None

    def launch(self, config: dict) -> None:
        self._app = Application(backend="uia").start(config["exe_path"])
        time.sleep(2)  # let the window actually appear before connecting
        self._window = self._app.window(title_re=f".*{config['window_title']}.*")
        self._window.wait("visible", timeout=15)

    def screenshot(self, out_path: Path) -> Path:
        self._window.capture_as_image().save(str(out_path))
        return out_path

    def find_text(self, text: str) -> dict | None:
        # Walks the UI Automation tree looking for any control whose
        # visible text contains `text`. Flutter's Windows accessibility
        # output can be sparse for custom-painted widgets — if this
        # keeps missing things that are clearly on screen, that's the
        # known rough edge mentioned above, not a bug in this script.
        try:
            el = self._window.child_window(title_re=f".*{text}.*")
            rect = el.rectangle()
        except Exception:
            return None
        return {
            "x": (rect.left + rect.right) // 2,
            "y": (rect.top + rect.bottom) // 2,
            "matched": text,
        }

    def tap(self, x: int, y: int) -> None:
        from pywinauto.mouse import click
        click(coords=(x, y))
        time.sleep(0.4)

    def type_text(self, text: str) -> None:
        send_keys(text, with_spaces=True)

    def close(self) -> None:
        if self._app:
            self._app.kill()
