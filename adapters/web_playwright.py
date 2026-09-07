"""
adapters/web_playwright.py

Drives a Flutter Web build (or any web app) via Playwright.

For Flutter Web apps (CanvasKit renderer), text is rendered on a <canvas>
element and NOT exposed as DOM text nodes — standard Playwright text
locators (get_by_text) won't find anything. This adapter solves that by:

  1. Enabling Flutter's accessibility/semantics tree on page load (clicks
     the flt-semantics-placeholder via JS).
  2. Searching flt-semantics elements for text matches via textContent.
  3. For elements with empty textContent (checkboxes, tabs), using
     role-based mapping: collecting accessibility tree names in order,
     then mapping to DOM elements by their flt-semantics[role] index.

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

# Viewport height — elements below this are considered off-screen.
_VIEWPORT_HEIGHT = 800


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
        flt-semantics DOM elements with bounding boxes."""
        self._page.evaluate("""() => {
            const btn = document.querySelector('flt-semantics-placeholder');
            if (btn) btn.click();
        }""")
        self._page.wait_for_timeout(3500)

    def screenshot(self, out_path: Path) -> Path:
        self._page.screenshot(path=str(out_path))
        return out_path

    # ── Text finding ─────────────────────────────────────────────────────

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

        if not self._is_flutter:
            return None

        # 2. Flutter: search flt-semantics by textContent (buttons, labels)
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

        # 3. Role-based mapping for elements with empty textContent
        #    (checkboxes, tabs — their names live in the accessibility tree,
        #     not in the DOM textContent)
        for role in ("checkbox", "tab"):
            result = self._role_based_find(text, role)
            if result is not None:
                return result

        return None

    def _role_based_find(self, label: str, role: str) -> dict | None:
        """Find an element by its accessibility-tree name and role.

        Flutter renders some elements (checkboxes, tabs) with empty
        textContent in the DOM.  Their *names* exist only in the
        accessibility tree.  This method:
          1. Gets the accessibility snapshot.
          2. Collects all nodes with the given role, in tree order.
          3. Finds the index of `label` in that ordered list.
          4. Maps that index to the Nth flt-semantics[role="..."] DOM
             element (which does have a bounding box).
          5. Scrolls into view if off-screen, then returns coordinates.
        """
        snap = self._page.accessibility.snapshot()
        if snap is None:
            return None

        # Collect named nodes of this role in tree order
        role_names = []
        def _walk(node):
            if node.get("role") == role and node.get("name"):
                role_names.append(node["name"])
            for child in node.get("children", []):
                _walk(child)
        _walk(snap)

        if label not in role_names:
            return None

        idx = role_names.index(label)

        # Get DOM elements with this role and their bounding boxes
        dom_els = self._page.evaluate(f"""() => {{
            return Array.from(document.querySelectorAll('flt-semantics[role="{role}"]'))
                .map((s, i) => {{
                    const r = s.getBoundingClientRect();
                    return {{idx: i, x: r.x, y: r.y, w: r.width, h: r.height}};
                }})
                .filter(e => e.w > 0);
        }}""")

        if idx >= len(dom_els):
            return None

        el = dom_els[idx]
        cx = el["x"] + el["w"] / 2
        cy = el["y"] + el["h"] / 2

        # Scroll into view if off-screen
        if cy > _VIEWPORT_HEIGHT - 20:
            self._page.mouse.wheel(0, 300)
            self._page.wait_for_timeout(1000)
            self._enable_flutter_accessibility()
            # Re-query positions after scroll
            dom_els = self._page.evaluate(f"""() => {{
                return Array.from(document.querySelectorAll('flt-semantics[role="{role}"]'))
                    .map((s, i) => {{
                        const r = s.getBoundingClientRect();
                        return {{idx: i, x: r.x, y: r.y, w: r.width, h: r.height}};
                    }})
                    .filter(e => e.w > 0);
            }}""")
            if idx < len(dom_els):
                el = dom_els[idx]
                cx = el["x"] + el["w"] / 2
                cy = el["y"] + el["h"] / 2

        return {"x": int(cx), "y": int(cy), "matched": label}

    # ── Region-based finding (for QA Console, multi-panel pages) ──────────

    def find_in_region(self, text: str, region: dict) -> dict | None:
        """Like find_text, but only considers elements within a bounding box.

        region = {"x1": int, "y1": int, "x2": int, "y2": int}
        """
        # Try DOM text first
        locator = self._page.get_by_text(text, exact=False)
        for i in range(locator.count()):
            box = locator.nth(i).bounding_box()
            if box is None:
                continue
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            if (region["x1"] <= cx <= region["x2"] and
                    region["y1"] <= cy <= region["y2"]):
                return {"x": int(cx), "y": int(cy), "matched": text}

        if not self._is_flutter:
            return None

        # Flutter textContent match within region
        match = self._page.evaluate("""(args) => {
            const [text, x1, y1, x2, y2] = [args.text, args.x1, args.y1, args.x2, args.y2];
            const sems = document.querySelectorAll('flt-semantics');
            const lower = text.toLowerCase();
            for (const s of sems) {
                const t = (s.textContent || '');
                if (t.toLowerCase().includes(lower) && t.length < text.length * 3) {
                    const r = s.getBoundingClientRect();
                    const cx = r.x + r.width/2, cy = r.y + r.height/2;
                    if (r.width > 0 && r.height > 0 &&
                        cx >= x1 && cx <= x2 && cy >= y1 && cy <= y2) {
                        return {x: cx, y: cy, matched: t};
                    }
                }
            }
            return null;
        }""", {"text": text, "x1": region["x1"], "y1": region["y1"],
               "x2": region["x2"], "y2": region["y2"]})
        if match:
            return {"x": int(match["x"]), "y": int(match["y"]),
                    "matched": match["matched"]}

        return None

    def tap_in_region(self, text: str, region: dict) -> dict | None:
        """Find text within a region and tap it. Returns coordinates or None."""
        result = self.find_in_region(text, region)
        if result:
            self.tap(result["x"], result["y"])
        return result

    # ── Low-level actions ────────────────────────────────────────────────

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
