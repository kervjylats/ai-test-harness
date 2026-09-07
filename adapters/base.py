"""
adapters/base.py

The contract every platform adapter implements. testctl.py never talks to
Playwright/Appium/pywinauto directly — it only ever calls these methods.
That's what makes the CLI (and every agent driving it) identical across
web/Android/Windows/whatever comes next: only the adapter underneath swaps.

Coordinates for tap() are (x, y) in the SCREENSHOT's pixel space, which
is why every adapter must return screenshots at a known, stable size —
see each adapter's own docstring for specifics.

Optional methods (find_in_region, tap_in_region): adapters that support
multi-panel or region-constrained search implement these. Adapters that
don't (Android, Windows) leave the defaults and callers get
NotImplementedError.
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

    # ── Optional: multi-panel / region-constrained search ──────────────────

    def find_in_region(self, text: str, region: dict) -> dict | None:
        """Search for `text` only within a bounding box.
        region = {"x1": int, "y1": int, "x2": int, "y2": int}
        Return {'x': int, 'y': int, 'matched': str} or None.

        Adapters that don't support region-constrained search leave this
        as the default — callers get NotImplementedError."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support find_in_region"
        )

    def tap_in_region(self, text: str, region: dict) -> dict | None:
        """Find `text` within a region, then tap it. Returns the match
        dict if found and tapped, or None."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support tap_in_region"
        )
