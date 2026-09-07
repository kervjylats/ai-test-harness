"""
adapters/base.py

The contract every platform adapter implements. testctl.py never talks to
Playwright/Appium/pywinauto directly — it only ever calls these 6 methods.
That's what makes the CLI (and every agent driving it) identical across
web/Android/Windows/whatever comes next: only the adapter underneath swaps.

Coordinates for tap() are (x, y) in the SCREENSHOT's pixel space, which
is why every adapter must return screenshots at a known, stable size —
see each adapter's own docstring for specifics.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class Adapter(ABC):
    @abstractmethod
    def launch(self, config: dict) -> None:
        """Start the app under test. `config` is the parsed project .json —
        each adapter reads whichever keys it needs (e.g. 'url' for web,
        'apk_path'/'package' for Android, 'exe_path' for Windows)."""

    @abstractmethod
    def screenshot(self, out_path: Path) -> Path:
        """Save a PNG screenshot to out_path, return the path. This is what
        the agent actually 'looks at' to decide pass/fail — keep it fast."""

    @abstractmethod
    def find_text(self, text: str) -> dict | None:
        """Search the current screen for `text`. Return
        {'x': int, 'y': int, 'matched': str} for the center point of the
        first match, or None if not found. Case-insensitive, substring
        match — matches how a human would describe 'the button that says
        Sign In', not an exact-string requirement."""

    @abstractmethod
    def tap(self, x: int, y: int) -> None:
        """Tap/click at a screenshot-space coordinate."""

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type into whatever currently has focus (tap a text field first)."""

    @abstractmethod
    def close(self) -> None:
        """Tear down the app/session cleanly."""
