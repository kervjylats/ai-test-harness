"""
adapters/web_playwright.py

Drives a Flutter Web build (or any web app) via Playwright.

For Flutter Web apps (CanvasKit renderer), text is rendered on a <canvas>
element and NOT exposed as DOM text nodes — standard Playwright text
locators (get_by_text) won't find anything. This adapter solves that by:

  1. Enabling Flutter's accessibility/semantics tree on page load (clicks
     the flt-semantics-placeholder via JS).
  2. Searching flt-semantics[aria-label] elements for text matches, with
     bounding boxes from the real DOM elements Flutter creates.

For regular HTML pages (non-Flutter), the standard get_by_text approach
works as before.

Setup (one-time):
    pip install playwright
    python -m playwright install chromium

Project config keys:
    "url":       the local URL your app serves on
    "headless":  true/false (default false)
    "flutter":   true/false — if true or auto-detected, enables the
                 Flutter accessibility workaround automatically.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

from .base import Adapter


class WebPlaywrightAdapter(Adapter):
    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None
        self._is_flutter = False

    def launch(self, config: dict) -> None:
        url = config["url"]
        headless = config.get("headless", False)
        self._is_flutter = config.get("flutter", True)  # default True for this project

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._page = self._browser.new_page(viewport={"width": 1280, "height": 800})
        self._page.goto(url)
        # Flutter Web boots into an empty canvas for a moment — give it
        # room to actually paint before the first screenshot/find_text.
        self._page.wait_for_timeout(3000)

        if self._is_flutter:
            self._enable_flutter_accessibility()

    def _enable_flutter_accessibility(self) -> None:
        """Click Flutter's hidden semantics-placeholder button to activate
        the full accessibility tree, making all rendered text available as
        flt-semantics DOM elements with aria-labels and bounding boxes."""
        self._page.evaluate("""() => {
            const btn = document.querySelector('flt-semantics-placeholder');
            if (btn) btn.click();
        }""")
        self._page.wait_for_timeout(2000)

    def screenshot(self, out_path: Path) -> Path:
        self._page.screenshot(path=str(out_path))
        return out_path

    def find_text(self, text: str) -> dict | None:
        # 1. Try standard DOM text search (works for HTML pages)
        locator = self._page.get_by_text(text, exact=False)
        if locator.count() > 0:
            box = locator.first.bounding_box()
            if box is not None:
                return {
                    "x": int(box["x"] + box["width"] / 2),
                    "y": int(box["y"] + box["height"] / 2),
                    "matched": text,
                }

        # 2. Flutter fallback: search flt-semantics by textContent
        if self._is_flutter:
            match = self._page.evaluate("""(text) => {
                const sems = document.querySelectorAll('flt-semantics');
                const lower = text.toLowerCase();
                for (const s of sems) {
                    const t = (s.textContent || '');
                    if (t.toLowerCase().includes(lower) && t.length < text.length * 3) {
                        const r = s.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            return {x: r.x + r.width/2, y: r.y + r.height/2, matched: t};
                        }
                    }
                }
                return null;
            }""", text)
            if match:
                return {
                    "x": int(match["x"]),
                    "y": int(match["y"]),
                    "matched": match["matched"],
                }

        return None

    def tap(self, x: int, y: int) -> None:
        self._page.mouse.click(x, y)
        self._page.wait_for_timeout(400)  # let Flutter's animation settle

    def type_text(self, text: str) -> None:
        self._page.keyboard.type(text, delay=20)

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
