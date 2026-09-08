"""
adapters/windows_desktop.py

Drives a Flutter Windows desktop build (the actual .exe) via pywinauto,
which talks to Windows' own UI Automation accessibility layer.

Flutter's Windows accessibility tree exposes text as `name` on controls
(Button, Text, Edit, etc.).  The `title_re` / `name` search works well
for standard controls.  Custom-painted widgets (e.g. canvas) may not
appear — that's a Flutter limitation, not a bug here.

One-time setup on YOUR machine:
    pip install pywinauto

Project config keys this adapter reads:
    "exe_path":      path to the built .exe
    "window_title":  substring of the window's title bar text
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
        self._last_element = None

    def launch(self, config: dict) -> None:
        if self._app is not None:
            try:
                self._app.kill()
            except Exception:
                pass
        self._config = config
        self._app = Application(backend="uia").start(config["exe_path"])
        time.sleep(5)
        self._window = self._app.window(
            title_re=f".*{config['window_title']}.*"
        )
        self._window.wait("visible", timeout=20)
        self._set_focus()

    def _set_focus(self):
        """Bring the Flutter window to the foreground."""
        try:
            import win32gui
            import win32con
            hwnd = self._window.handle
            # Restore if minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            # Trick: attach to foreground thread first, then set focus
            fg_hwnd = win32gui.GetForegroundWindow()
            fg_tid = win32gui.GetWindowThreadProcessId(fg_hwnd)[0]
            import ctypes
            my_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            ctypes.windll.user32.AttachThreadInput(my_tid, fg_tid, True)
            win32gui.SetForegroundWindow(hwnd)
            ctypes.windll.user32.AttachThreadInput(my_tid, fg_tid, False)
            time.sleep(0.3)
        except Exception:
            try:
                self._window.set_focus()
                time.sleep(0.3)
            except Exception:
                pass

    def screenshot(self, out_path: Path) -> Path:
        self._ensure_window()
        self._set_focus()
        self._window.capture_as_image().save(str(out_path))
        return out_path

    def _ensure_window(self):
        """Reconnect to the window if the reference went stale."""
        try:
            # Test if current reference still works
            self._window.window_text()
            return
        except Exception:
            pass
        # Reconnect
        try:
            self._window = self._app.window(
                title_re=f".*{self._config.get('window_title', '')}.*"
            )
            self._window.wait("visible", timeout=10)
        except Exception:
            pass

    def find_text(self, text: str) -> dict | None:
        self._ensure_window()
        # Strategy 1: child_window(title_re) — fast, works for most controls
        try:
            el = self._window.child_window(title_re=f".*{text}.*")
            el.wait("visible", timeout=5)
            rect = el.rectangle()
            self._last_element = el
            return {
                "x": (rect.left + rect.right) // 2,
                "y": (rect.top + rect.bottom) // 2,
                "matched": text,
            }
        except Exception:
            pass
        # Strategy 2: manual walk
        el = self._walk_find(self._window, text)
        if el:
            self._last_element = el
            rect = el.rectangle()
            return {
                "x": (rect.left + rect.right) // 2,
                "y": (rect.top + rect.bottom) // 2,
                "matched": text,
            }
        return None

    def _walk_find(self, root, text: str, depth=0):
        if depth > 20:
            return None
        try:
            name = root.element_info.name or ""
            if text.lower() in name.lower():
                return root
        except Exception:
            pass
        try:
            for child in root.children():
                result = self._walk_find(child, text, depth + 1)
                if result:
                    return result
        except Exception:
            pass
        return None

    def tap(self, x: int, y: int) -> None:
        # Flutter Windows doesn't respond to SetCursorPos-based clicks.
        # Use click_input() on the deepest element at (x, y).
        self._set_focus()
        target = self._find_element_at(self._window, x, y)
        if target:
            try:
                target.click_input()
                time.sleep(0.5)
                return
            except Exception:
                pass
        # Fallback
        from pywinauto.mouse import click as mouse_click
        mouse_click(coords=(x, y))
        time.sleep(0.5)

    def tap_element(self, find_result: dict) -> None:
        """Tap using the element stored by find_text (preferred over coordinate tap)."""
        if self._last_element:
            try:
                self._set_focus()
                self._last_element.click_input()
                time.sleep(0.5)
                self._last_element = None
                return
            except Exception:
                pass
        self.tap(find_result["x"], find_result["y"])

    def _find_element_at(self, root, x, y, depth=0):
        if depth > 25:
            return None
        try:
            rect = root.rectangle()
            if not (rect.left <= x <= rect.right and rect.top <= y <= rect.bottom):
                return None
        except Exception:
            return None
        # Try children first (deeper = more specific target)
        best = None
        try:
            for child in root.children():
                result = self._find_element_at(child, x, y, depth + 1)
                if result:
                    best = result  # keep going deeper
        except Exception:
            pass
        return best if best else root

    def type_text(self, text: str) -> None:
        self._set_focus()
        send_keys(text, with_spaces=True)

    def close(self) -> None:
        if self._app:
            try:
                self._app.kill()
            except Exception:
                pass
            self._app = None
            self._window = None
