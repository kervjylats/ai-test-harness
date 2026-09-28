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

    # ── Battle-tested Flutter Web helpers (ported from the PWT harness) ────
    #
    # These were validated against a live Flutter Web CanvasKit build:
    #   * Session persists across reload when signing in via the real
    #     Email/Password form -> typed_logout() must clear localStorage.
    #   * Flutter re-creates the Email/Password <input>s after each fill, so
    #     inputs are re-located by aria-label every time, with a settle gap.
    #   * Switch toggles carry no aria-label in the DOM (their names live in
    #     the accessibility tree), so they're toggled by DOM index instead.
    #   * Long scrollable pages (ListView) build children lazily: sections
    #     below the fold are only present after scroll_down().
    #   * Headless Chromium needs --enable-unsafe-swiftshader for a reliable
    #     Flutter boot; set it via config["launch_args"].

    def _launch_args(self, config: dict) -> list:
        return config.get("launch_args", []) or []

    def launch(self, config: dict) -> None:
        url = config["url"]
        headless = config.get("headless", False)
        self._is_flutter = config.get("flutter", True)  # default True for this project

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=headless, args=self._launch_args(config))
        self._page = self._browser.new_page(viewport={"width": 1280, "height": 800})
        self._page.goto(url)
        # Flutter Web boots into an empty canvas for a moment — give it
        # room to actually paint before the first screenshot/find_text.
        self._page.wait_for_timeout(3000)

        if self._is_flutter:
            self._enable_flutter_accessibility()

    def enable_semantics(self, wait_ms: int = 700) -> None:
        """Re-activate (or refresh) the Flutter semantics tree after heavy UI
        changes. Cheap to call liberally between steps."""
        self._page.evaluate("""() => {
            const btn = document.querySelector('flt-semantics-placeholder');
            if (btn) btn.click();
        }""")
        self._page.wait_for_timeout(wait_ms)

    def inner_text(self) -> str:
        """Full visible page text (Flutter semantics expose it as innerText)."""
        return self._page.evaluate("document.body.innerText")

    def wait_for_texts(self, needles: list[str], timeout_ms: int = 20000) -> bool:
        """Poll innerText until ANY needle appears (case-insensitive).
        Returns True on match, False on timeout."""
        import time
        lower = [n.lower() for n in needles]
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            txt = self.inner_text().lower()
            if any(n in txt for n in lower):
                return True
            self._page.wait_for_timeout(500)
        return False

    def hash_navigate(self, hash_path: str, wait_ms: int = 5000) -> None:
        """Client-side hash navigation (e.g. '#/owner/marketplace')."""
        self._page.evaluate(f"""() => {{ window.location.hash = '{hash_path}'; }}""")
        self._page.wait_for_timeout(wait_ms)
        self.enable_semantics()

    def smart_find_click(self, label: str, wait_ms: int = 2200) -> bool:
        """Click the FIRST flt-semantics whose text/aria-label starts with
        `label`. Prefix matching avoids both `includes` (which hits the big
        page-aggregate node) and exact-match (labels often carry merged text
        like 'Propose a deal Set a commission split...'). Returns True when a
        node was clicked."""
        clicked = self._page.evaluate("""(label) => {
            for (const s of document.querySelectorAll('flt-semantics')) {
                const t = (s.textContent || '').trim();
                const al = (s.getAttribute('aria-label') || '').trim();
                if (t.startsWith(label) || al.startsWith(label)) {
                    const r = s.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) { s.click(); return true; }
                }
            }
            return false;
        }""", label)
        self._page.wait_for_timeout(wait_ms)
        self.enable_semantics(wait_ms=600)
        return clicked

    def click_exact(self, label: str, wait_ms: int = 2200) -> bool:
        """Click the FIRST flt-semantics whose text exactly equals `label`
        (stable for discrete buttons like 'Send Proposal' / 'Confirm Collab')."""
        clicked = self._page.evaluate("""(label) => {
            for (const s of document.querySelectorAll('flt-semantics')) {
                if ((s.textContent || '').trim() === label) {
                    const r = s.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) { s.click(); return true; }
                }
            }
            return false;
        }""", label)
        self._page.wait_for_timeout(wait_ms)
        self.enable_semantics(wait_ms=600)
        return clicked

    def switch_toggle(self, index: int, wait_ms: int = 2000) -> bool:
        """Toggle a role=switch node by DOM index (0 = first switch). Switch
        nodes carry no aria-label in Flutter's HTML renderer, so index
        matching (sidebar order) is the reliable route."""
        clicked = self._page.evaluate("""(i) => {
            const sems = document.querySelectorAll('flt-semantics[role=switch]');
            if (sems.length > i) { sems[i].click(); return true; }
            return false;
        }""", index)
        self._page.wait_for_timeout(wait_ms)
        self.enable_semantics(wait_ms=600)
        return clicked

    def scroll_down(self, steps: int = 4, dy: int = 650) -> None:
        """Move the mouse over the scrollable list then wheel, so lazy
        ListView children below the fold get built and exposed to semantics."""
        self._page.mouse.move(640, 400)
        self._page.wait_for_timeout(400)
        for _ in range(steps):
            self._page.mouse.wheel(0, dy)
            self._page.wait_for_timeout(800)
        self.enable_semantics(wait_ms=600)

    def typed_login(self, email: str, password: str = "test123",
                    settle_ms: int = 8000) -> None:
        """Sign in through the REAL Email/Password form (not dev identities).
        Flutter recreates the <input>s after each fill, so both are targeted
        by aria-label and allowed to settle (400ms) before proceeding."""
        self.hash_navigate("#/login", wait_ms=settle_ms)
        self._page.fill('input[aria-label="Email"]', email)
        self._page.wait_for_timeout(400)
        self._page.fill('input[aria-label="Password"]', password)
        self._page.wait_for_timeout(400)
        self.enable_semantics()
        self._page.evaluate("""() => {
            for (const s of document.querySelectorAll('flt-semantics')) {
                if ((s.textContent || '').trim() === 'Sign In') { s.click(); break; }
            }
        }""")
        self._page.wait_for_timeout(settle_ms)
        self.enable_semantics()

    def typed_logout(self) -> None:
        """Clear the persisted session (SharedPreferences-backed on web) and
        return to the unauthenticated front door."""
        self._page.evaluate("""() => {
            try { localStorage.clear(); } catch (e) {}
            try { sessionStorage.clear(); } catch (e) {}
        }""")
        self._page.goto(self._page.url.split('#')[0])
        self._page.wait_for_timeout(6000)
        self.enable_semantics(wait_ms=600)

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

    def navigate(self, path: str) -> None:
        """Navigate to a path relative to the app's base URL."""
        base = self._page.url.rstrip('/')
        self._page.goto(f'{base}{path}')
        self._page.wait_for_timeout(1000)
        if self._is_flutter:
            self._enable_flutter_accessibility()

    def js_eval(self, script: str) -> any:
        """Evaluate JavaScript in the page context and return the result."""
        return self._page.evaluate(script)

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
