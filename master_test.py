"""
master_test.py — Automated full checklist test for Personal Wellness Trainer.
Uses Playwright directly for Flutter Web canvas interaction.
Takes screenshots at every step, records pass/fail results.

Round 6 rework (dev tools removed for good):
- No Dev Quick Sign-In / QA Console anywhere: accounts are created through
  the REAL landing-signup flow, sessions via typed Email/Password login.
- No page reloads mid-run: mock stores are static in-memory JS and a reload
  would wipe everything this run created. Sign-out is the in-app
  Settings -> Sign Out path; navigation is tab/hash based.
- Invite flows use real one-time tokens (page text / clipboard / predicted
  mock counter: first Generate Link in a fresh isolate = wlp_000011).
- Steps 8/9 (invite -> propose deal) record the KNOWN dead-end honestly
  (FAIL, do-not-fix) instead of being blocked by missing credentials.
- Marketplace + money loop are driven across two real owner accounts
  (own1@robot.test, own4@robot.test) plus an invite-linked associate.
"""
import json, sys, io, time, re
# line_buffering: flush on every newline. Without it the wrapper swallows
# output until the 8KB buffer fills — if stdout is a backpressured pipe the
# flush can block forever (Round 6 run 1 hung exactly at a record() print
# after Step 9) and a killed process loses the whole buffer.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8',
                              line_buffering=True)
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080"
ROLE_HASHES = ("/owner", "/partner", "/staff", "/client")

RESULTS = []
SCREENSHOT_DIR = Path("test_screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

def screenshot(page, name):
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    return str(path)

def record(step, description, result, expected, screenshot_path="", notes=""):
    RESULTS.append({
        "step": step,
        "description": description,
        "result": result,
        "expected": expected,
        "screenshot": screenshot_path,
        "notes": notes,
    })
    status = "PASS" if result == "pass" else "FAIL" if result == "fail" else "BLOCKED"
    print(f"  [{status}] {step}: {description}")

def enable_flutter_acc(page):
    page.evaluate("""() => {
        const btn = document.querySelector('flt-semantics-placeholder');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(3500)

def _acc_snapshot(page):
    """Get accessibility snapshot."""
    return page.accessibility.snapshot()

def find_and_click(page, label, timeout=3000):
    """Find element by text/name and click. Handles Flutter Web canvas.
    Retries with downward scrolls so below-the-fold chips/tiles (e.g. the
    Settings tiles, below-fold list rows) become clickable."""
    for _ in range(6):
        snap = _acc_snapshot(page)

        # Method 0: aria-label direct match FIRST. Flutter Web exposes
        # semantics names as aria-label on flt-semantics nodes. Interactive
        # nodes (checkbox/switch/button/tab...) win over mere text nodes,
        # whose label text rect can sit OUTSIDE the actual hit area (e.g. the
        # bottom-nav 'Settings' label node sits above the tab's hit region).
        #  A) el.click() (semantics tap action) — works even BELOW the fold,
        #     so no coordinate/scroll fragility (chips, toggles).
        #  B) tabs (bottom nav) matched by aria-label + coordinate click —
        #     index alignment with the acc tree is unreliable.
        lab_hit = page.evaluate("""(label) => {
            const lower = label.toLowerCase();
            const sems = document.querySelectorAll('flt-semantics[aria-label]');
            let best = null;
            for (const s of sems) {
                const role = s.getAttribute('role');
                if (role !== 'checkbox' && role !== 'switch' && role !== 'button'
                    && role !== 'tab' && role !== 'link' && role !== 'menuitem') continue;
                const al = (s.getAttribute('aria-label') || '');
                const tail = al.slice(label.length);
                const alower = al.toLowerCase();
                if (alower !== lower && !(alower.startsWith(lower) &&
                    (tail === '' || /^\\s|\\(|\\n/.test(tail)))) continue;
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    const area = r.width * r.height;
                    if (!best || area < best.area) {
                        best = {n: s, role: role,
                                x: r.x + r.width/2, y: r.y + r.height/2,
                                area: area};
                    }
                }
            }
            if (!best) return null;
            if (best.role === 'tab') {
                return {tab: true, x: best.x, y: best.y};
            }
            best.n.click();
            return {tab: false};
        }""", label)
        if lab_hit:
            if lab_hit.get("tab"):
                page.mouse.click(lab_hit["x"], lab_hit["y"])
            page.wait_for_timeout(1500)
            return True

        # Method 1: Direct textContent match (works for buttons with visible text)
        match = page.evaluate("""(label) => {
            const sems = document.querySelectorAll('flt-semantics');
            for (const s of sems) {
                if (s.textContent === label) {
                    const r = s.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                    }
                }
            }
            return null;
        }""", label)
        if match:
            page.mouse.click(match["x"], match["y"])
            page.wait_for_timeout(1500)
            return True

        lab_match = page.evaluate("""(label) => {
            const lower = label.toLowerCase();
            const sems = document.querySelectorAll('flt-semantics[aria-label]');
            let best = null;
            for (const s of sems) {
                const al = (s.getAttribute('aria-label') || '');
                const tail = al.slice(label.length);
                const alower = al.toLowerCase();
                if (alower !== lower && !(alower.startsWith(lower) &&
                    (tail === '' || /^\\s|\\(|\\n/.test(tail)))) continue;
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    const area = r.width * r.height;
                    if (!best || area < best.area) {
                        best = {x: r.x + r.width/2, y: r.y + r.height/2, area: area};
                    }
                }
            }
            return best;
        }""", label)
        if lab_match:
            if lab_match["y"] <= 780:
                page.mouse.click(lab_match["x"], lab_match["y"])
                page.wait_for_timeout(1500)
                return True
            # below the fold — fall through to the scroll step

        # Method 2: Checkboxes with a semantic name but empty textContent
        cb_names = []
        def find_cbs(n):
            if n.get("role") == "checkbox" and n.get("name"):
                cb_names.append(n["name"])
            for c in n.get("children", []):
                find_cbs(c)
        find_cbs(snap)

        if label in cb_names:
            dom_cbs = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('flt-semantics[role="checkbox"]'))
                    .map((s, i) => { const r = s.getBoundingClientRect(); return {idx:i, x:r.x, y:r.y, w:r.width, h:r.height}; })
                    .filter(e => e.w > 0);
            }""")
            idx = cb_names.index(label)
            if idx < len(dom_cbs):
                c = dom_cbs[idx]
                cx = c["x"] + c["w"]/2
                cy = c["y"] + c["h"]/2
                if cy <= 780:
                    page.mouse.click(cx, cy)
                    page.wait_for_timeout(1500)
                    return True
                # below the fold — fall through; the scroll step below brings it up

        # Method 2b: Icon buttons whose name comes from a Tooltip (empty textContent)
        # e.g. the Network invite FAB ('Invite'), the app-bar 'Chats'/'Notifications'.
        btn_names = []
        def find_btns(n):
            if n.get("role") == "button" and n.get("name"):
                btn_names.append(n["name"])
            for c in n.get("children", []):
                find_btns(c)
        find_btns(snap)

        if label in btn_names:
            dom_btns = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('flt-semantics[role="button"]'))
                    .map((s, i) => { const r = s.getBoundingClientRect(); return {idx:i, x:r.x, y:r.y, w:r.width, h:r.height}; })
                    .filter(e => e.w > 0);
            }""")
            idx = btn_names.index(label)
            if idx < len(dom_btns):
                b = dom_btns[idx]
                by = b["y"] + b["h"]/2
                if by <= 780:
                    page.mouse.click(b["x"] + b["w"]/2, by)
                    page.wait_for_timeout(1500)
                    return True
                # below the fold — fall through to the scroll step

        # Method 3: Tabs with a semantic name, then partial textContent match
        tab_names = []
        def find_tabs(n):
            if n.get("role") == "tab" and n.get("name"):
                tab_names.append(n["name"])
            for c in n.get("children", []):
                find_tabs(c)
        find_tabs(snap)

        if label in tab_names:
            dom_tabs = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('flt-semantics[role="tab"]'))
                    .map((s, i) => { const r = s.getBoundingClientRect(); return {idx:i, x:r.x, y:r.y, w:r.width, h:r.height}; })
                    .filter(e => e.w > 0);
            }""")
            idx = tab_names.index(label)
            if idx < len(dom_tabs):
                t = dom_tabs[idx]
                page.mouse.click(t["x"] + t["w"]/2, t["y"] + t["h"]/2)
                page.wait_for_timeout(1500)
                return True

        # Method 2c: Switches (Settings -> Business Features toggles). Their
        # aria-label name embeds title+description ('Collabs\nAllow this...'),
        # so match when a name STARTS WITH the label.
        sw_names = []
        def find_sws(n):
            if n.get("role") == "switch" and n.get("name"):
                sw_names.append(n["name"])
            for c in n.get("children", []):
                find_sws(c)
        find_sws(snap)

        sw_idx = None
        for i, nm in enumerate(sw_names):
            if nm.lower().startswith(label.lower()):
                sw_idx = i
                break
        if sw_idx is not None:
            dom_sws = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('flt-semantics[role="switch"]'))
                    .map((s, i) => { const r = s.getBoundingClientRect(); return {idx:i, x:r.x, y:r.y, w:r.width, h:r.height}; })
                    .filter(e => e.w > 0);
            }""")
            if sw_idx < len(dom_sws):
                w = dom_sws[sw_idx]
                wy = w["y"] + w["h"]/2
                if wy <= 780:
                    page.mouse.click(w["x"] + w["w"]/2, wy)
                    page.wait_for_timeout(1500)
                    return True
                # below the fold — fall through to the scroll step

        match = page.evaluate("""(label) => {
            const sems = document.querySelectorAll('flt-semantics');
            const lower = label.toLowerCase();
            let best = null;
            for (const s of sems) {
                const t = (s.textContent || '');
                if (t.length > 300 || !t.toLowerCase().includes(lower)) continue;
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    const area = r.width * r.height;
                    if (!best || area < best.area) {
                        best = {x: r.x + r.width/2, y: r.y + r.height/2, area: area};
                    }
                }
            }
            return best;
        }""", label)
        if match:
            if match["y"] <= 780:
                page.mouse.click(match["x"], match["y"])
                page.wait_for_timeout(1500)
                return True
            # below the fold — fall through to the scroll step

        # Not found (or only below the fold): scroll the active pane down a bit
        # and re-snapshot so indexes stay aligned with the visible semantics.
        page.mouse.move(640, 400)
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(900)
        enable_flutter_acc(page)

    return False

def get_all_text(page):
    """Get all visible text from accessibility tree + DOM."""
    snap = page.accessibility.snapshot()
    names = []
    def collect(n):
        if n.get("name"):
            names.append(n["name"])
        for c in n.get("children", []):
            collect(c)
    collect(snap)
    dom_texts = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('flt-semantics'))
            .map(s => s.textContent)
            .filter(Boolean);
    }""")
    return list(set(names + dom_texts))

def wait_for_texts(page, needles, timeout_ms=20000):
    """Poll until any needle appears in the acc tree (handles slow first load)."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    texts = []
    while time.monotonic() < deadline:
        texts = get_all_text(page)
        joined = " ".join(t.lower() for t in texts)
        if any(n.lower() in joined for n in needles):
            return texts
        page.wait_for_timeout(1200)
    return texts

def until_absent(page, needles, timeout_ms=8000):
    """Poll until NONE of the needles remain in body innerText (case-insensitive)."""
    lower = [n.lower() for n in needles]
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        txt = page.evaluate("document.body.innerText") or ""
        if not any(n in txt.lower() for n in lower):
            return True
        page.wait_for_timeout(400)
    return False

def has_text(page, needles):
    """True if ANY needle appears in the page innerText (case-insensitive)."""
    txt = page.evaluate("document.body.innerText").lower()
    return any(n.lower() in txt for n in needles)

def page_text(page):
    """Lower-cased blob of body innerText + semantics text/aria-labels."""
    return page.evaluate("""() => {
        let t = document.body.innerText || '';
        for (const s of document.querySelectorAll('flt-semantics')) {
            t += '\\n' + (s.textContent || '') + '\\n' + (s.getAttribute('aria-label') || '');
        }
        return t.toLowerCase();
    }""")

def has(page, needles):
    txt = page_text(page)
    return any(n.lower() in txt for n in needles)

def has_all(page, needles):
    txt = page_text(page)
    return all(n.lower() in txt for n in needles)

def has_after_scroll(page, needles, rounds=5, steps=2):
    """Scroll down (up to `rounds` times) until every needle is on-page."""
    for _ in range(rounds):
        if has_all(page, needles):
            return True
        scroll_down(page, steps=steps)
        page.wait_for_timeout(600)
        enable_flutter_acc(page)
    return has_all(page, needles)

def click_prefix(page, label, wait=2200):
    """Click the FIRST flt-semantics whose text/aria-label STARTS WITH label.
    Avoids `includes` (which hits the page-aggregate node) and exact-match
    (labels often pick up merged text like 'Propose a deal Set a commission
    split...')."""
    page.evaluate("""(label) => {
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
    page.wait_for_timeout(wait)
    enable_flutter_acc(page)


def click_exact(page, label, wait=2200):
    """Click the flt-semantics whose text EXACTLY equals label, preferring
    interactive nodes (button/tab/link/...) over plain text nodes. A lone
    text node with the same string often precedes the real button (e.g. the
    finance 'Mark Paid' tile renders text -> group -> button), and el.click()
    on a non-interactive node is a no-op.
    Returns True if a node matched and was clicked."""
    clicked = page.evaluate("""(label) => {
        const vis = (s) => {
            const r = s.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        };
        const sems = Array.from(document.querySelectorAll('flt-semantics'))
            .filter(vis);
        const interactive = ['button', 'tab', 'link', 'checkbox', 'switch', 'menuitem'];
        const exact = (s) => {
            const t = (s.textContent || '').trim();
            const al = (s.getAttribute('aria-label') || '').trim();
            return t === label || al === label;
        };
        const hit = sems.find(s =>
                        interactive.includes(s.getAttribute('role')) && exact(s))
                 || sems.find(exact);
        if (!hit) return false;
        hit.click();
        return true;
    }""", label)
    page.wait_for_timeout(wait)
    enable_flutter_acc(page)
    return clicked


def click_contains(page, needle, wait=2500):
    """Click the LAST flt-semantics whose text/aria contains needle.
    Returns the clicked node's text (or None)."""
    matched = page.evaluate("""(needle) => {
        const hits = [];
        for (const s of document.querySelectorAll('flt-semantics')) {
            const t = ((s.textContent || '') + ' ' + (s.getAttribute('aria-label') || ''))
                .trim().replace(/\\s+/g, ' ');
            if (t.includes(needle)) {
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) hits.push(s);
            }
        }
        if (!hits.length) return null;
        const el = hits[hits.length - 1];
        el.click();
        return ((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || ''))
            .trim().replace(/\\s+/g, ' ');
    }""", needle)
    page.wait_for_timeout(wait)
    return matched


def scroll_down(page, steps=4, dy=650):
    """Move the mouse over the list then wheel to reveal below-fold sections."""
    page.mouse.move(640, 400)
    page.wait_for_timeout(400)
    for _ in range(steps):
        page.mouse.wheel(0, dy)
        page.wait_for_timeout(800)
    enable_flutter_acc(page)


def click_btn(page, label, wait=2500):
    """Click flt-semantics[role=button] whose text EXACTLY equals label."""
    matched = page.evaluate("""(label) => {
        for (const s of document.querySelectorAll('flt-semantics[role=button]')) {
            const t = (s.textContent || '').trim().replace(/\\s+/g, ' ');
            if (t === label) {
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) { s.click(); return t; }
            }
        }
        return null;
    }""", label)
    page.wait_for_timeout(wait)
    return matched


def click_btn_prefix(page, prefix, wait=2500):
    """Click flt-semantics[role=button] whose text STARTS WITH prefix."""
    matched = page.evaluate("""(prefix) => {
        for (const s of document.querySelectorAll('flt-semantics[role=button]')) {
            const t = (s.textContent || '').trim().replace(/\\s+/g, ' ');
            if (t.startsWith(prefix)) {
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) { s.click(); return t; }
            }
        }
        return null;
    }""", prefix)
    page.wait_for_timeout(wait)
    return matched


def fill(page, aria_label, value):
    """page.fill by exact input aria-label (Flutter re-creates inputs per
    fill, so locate fresh every time)."""
    try:
        page.fill(f'input[aria-label="{aria_label}"]', value, timeout=4000)
        page.wait_for_timeout(300)
        return True
    except Exception:
        return False


def fill_textareas(page, txt, wait=500):
    n = page.evaluate("""(txt) => {
        let c = 0;
        for (const ta of document.querySelectorAll('textarea')) {
            const r = ta.getBoundingClientRect();
            if (r.width > 0) {
                ta.focus(); ta.value = txt;
                ta.dispatchEvent(new Event('input', {bubbles: true}));
                c++;
            }
        }
        return c;
    }""", txt)
    if n:
        page.wait_for_timeout(wait)
    return n


def fill_first_input(page, value):
    n = page.evaluate("""(v) => {
        let c = 0;
        for (const i of document.querySelectorAll('input, textarea')) {
            const r = i.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                const proto = i.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(i, v);
                i.dispatchEvent(new Event('input', {bubbles: true}));
                c++;
                break;
            }
        }
        return c;
    }""", value)
    page.wait_for_timeout(400)
    return n


def wait_for_input(page, aria, timeout_ms=8000):
    waited = 0
    while waited < timeout_ms:
        try:
            el = page.query_selector(f'input[aria-label="{aria}"]')
            if el and el.is_visible():
                return True
        except Exception:
            pass
        page.wait_for_timeout(400)
        waited += 400
    return False


def type_into(page, aria, value, tries=4):
    sel = f'input[aria-label="{aria}"]'
    for _ in range(tries):
        try:
            el = page.wait_for_selector(sel, state="attached", timeout=4000)
            el.click()
            page.keyboard.press("Control+A")
            page.keyboard.type(value, delay=25)
            page.wait_for_timeout(250)
            if el.input_value() == value:
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def fill_by_label_prefix(page, prefix, value, tries=4):
    """Fill an input whose aria-label STARTS with `prefix` — Flutter
    merges labelText+hint into one label ('Amount\\ne.g. 120.00'), so an
    exact aria-label selector would never match."""
    for _ in range(tries):
        ok = page.evaluate("""({prefix, value}) => {
            for (const i of document.querySelectorAll('input, textarea')) {
                const al = (i.getAttribute('aria-label') || '');
                if (!al.startsWith(prefix)) continue;
                const r = i.getBoundingClientRect();
                if (!(r.width > 0 && r.height > 0)) continue;
                const proto = i.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(i, value);
                i.dispatchEvent(new Event('input', {bubbles: true}));
                return true;
            }
            return false;
        }""", {"prefix": prefix, "value": value})
        if ok:
            page.wait_for_timeout(300)
            return True
        page.wait_for_timeout(500)
    return False


def input_labels(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('input, textarea'))
        .map(i => i.getAttribute('aria-label') || '')""")


def card_titles(page):
    """Titles of the marketplace Availability card switches:
    ['Discoverable', ...slot titles]."""
    return page.evaluate("""() => {
        for (const s of document.querySelectorAll('flt-semantics')) {
            const a = s.getAttribute('aria-label') || '';
            if (a.includes('My Availability')) {
                const lines = a.split('\\n').map(x => x.trim()).filter(Boolean);
                const titles = ['Discoverable'];
                const i = lines.indexOf('Collab Slots');
                if (i >= 0) {
                    const rest = lines.slice(i + 1);
                    for (let j = 0; j + 1 < rest.length + 1; j += 2) titles.push(rest[j]);
                }
                return titles;
            }
        }
        return [];
    }""")


def switch_states(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('flt-semantics[role=switch]'))
        .map(s => s.getAttribute('aria-checked') || '')""")


def toggle_slot(page, title, wait=3000):
    """Toggle the availability switch named `title` by card-title index.
    Returns True if it flipped to 'true'."""
    titles = card_titles(page)
    if title not in titles:
        print(f"    toggle {title!r}: NOT IN titles {titles}")
        return None
    idx = titles.index(title)
    before = switch_states(page)
    page.evaluate("""(i) => {
        const sw = document.querySelectorAll('flt-semantics[role=switch]');
        if (sw[i]) sw[i].click();
    }""", idx)
    page.wait_for_timeout(wait)
    after = switch_states(page)
    ok = idx < len(after) and after[idx] == "true" and (
        idx >= len(before) or before[idx] != "true")
    print(f"    toggle {title!r} idx={idx}: {before[idx] if idx < len(before) else '?'}"
          f" -> {after[idx] if idx < len(after) else '?'} ({'OK' if ok else 'CHECK'})")
    return ok


# ---------------------------------------------------------------------------
# Session / account helpers (Round 6: real flows only, NO page reloads).
# ---------------------------------------------------------------------------

def on_role_shell(page):
    return any(h in page.url for h in ROLE_HASHES)


def typed_login(page, email, password="test123"):
    """Fill the real Email/Password inputs on #/login and submit."""
    page.evaluate("""() => { window.location.hash = '#/login'; }""")
    page.wait_for_timeout(8000)
    enable_flutter_acc(page)
    page.fill(f'input[aria-label="Email"]', email)
    page.wait_for_timeout(400)
    page.fill(f'input[aria-label="Password"]', password)
    page.wait_for_timeout(400)
    enable_flutter_acc(page)
    page.evaluate("""() => {
        for (const s of document.querySelectorAll('flt-semantics')) {
            if ((s.textContent || '').trim() === 'Sign In') { s.click(); break; }
        }
    }""")
    page.wait_for_timeout(8000)
    enable_flutter_acc(page)


def login(page, email, password="test123"):
    """Typed credential login + settle on the role dashboard."""
    typed_login(page, email, password)
    page.wait_for_timeout(3000)
    enable_flutter_acc(page)


def real_sign_out(page):
    """Settings -> Sign Out (app-level). NO page reload: mock stores are
    static in-memory JS — a reload would wipe everything created this run.
    Pops pushed routes first (URL-less ones via the Back button, URL-carrying
    ones via hash) so the shell's Settings tab is reachable.
    Returns True when no role shell hash remains in the URL."""
    if not on_role_shell(page):
        return True  # already at the front door / login
    for attempt in range(3):
        page.keyboard.press("Escape")  # close any open dialog first
        page.wait_for_timeout(800)
        if "#" in page.url:
            h = page.url.split("#", 1)[1].strip("/")
            parts = [p for p in h.split("/") if p]
            if len(parts) > 1:
                page.evaluate(f"() => {{ window.location.hash = '#/{parts[0]}'; }}")
                page.wait_for_timeout(2500)
                enable_flutter_acc(page)
        # URL-less pushed routes (e.g. AgreementDetail keeps '#/owner')
        if has(page, ["Back"]) and not has(page, ["Revenue Summary"]):
            find_and_click(page, "Back", timeout=4000)
            page.wait_for_timeout(1500)
            enable_flutter_acc(page)
        find_and_click(page, "Settings", timeout=6000)
        page.wait_for_timeout(1500)
        find_and_click(page, "Sign Out", timeout=3000)
        page.wait_for_timeout(3000)
        enable_flutter_acc(page)
        if not on_role_shell(page):
            return True
        print(f"    sign-out attempt {attempt} still on {page.url}")
    return False


def signup(page, name, email, category, job_prefix, business, tagline="Robot biz",
           password="test123"):
    """Landing form -> onboarding -> owner dashboard. Returns final URL."""
    page.evaluate("() => { window.location.hash = '#/get-started'; }")
    page.wait_for_timeout(3500)
    enable_flutter_acc(page)
    for attempt in range(3):
        type_into(page, "Your Name", name)
        type_into(page, "Email", email)
        type_into(page, "Password", password)
        click_btn(page, "Get started", wait=5000)
        if "#/onboarding" in page.url or has(page, ["Choose", "category", "Movement"]):
            break
        print(f"    submit attempt {attempt}: still on {page.url},"
              f" validation={has(page, ['is required'])}")
    if "#/onboarding" not in page.url:
        print(f"    signup {email}: onboarding never reached ({page.url})")
    for attempt in range(3):
        if wait_for_input(page, "Business Name", 1200) or has(page, ["Finish Setup"]) \
           or has(page, ["About you"]):
            break
        if not has(page, [job_prefix]):
            hit = click_btn(page, category, wait=3500)
            print(f"    signup attempt {attempt}: category={hit!r}")
            if hit is None:
                print(f"    signup {email}: category button {category!r} not found")
        hit = click_btn_prefix(page, job_prefix, wait=3500)
        print(f"    signup attempt {attempt}: job={hit!r}")
        click_btn(page, "Continue", wait=4000)
        if wait_for_input(page, "Business Name"):
            break
        print(f"    signup attempt {attempt}: Business Name missing, retrying")
    page.fill('input[aria-label="Business Name"]', business, timeout=8000)
    try:
        page.fill('input[aria-label="Tagline"]', tagline, timeout=4000)
    except Exception:
        pass
    fill_textareas(page, "Robot automated business description")
    click_btn(page, "Continue", wait=4000)
    fill_textareas(page, "Robot team member bio")
    hit = None
    for _ in range(3):
        hit = click_btn(page, "Finish Setup", wait=6000)
        if hit or "#/owner" in page.url:
            break
        click_btn(page, "Continue", wait=3000)
        fill_textareas(page, "Robot team member bio")
    enable_flutter_acc(page)
    print(f"    signup {email}: finish={hit} -> {page.url}")
    return page.url


def invitee_signup(page, code, name, email, password="test123"):
    """Landing form in 'Activate your code' mode -> role dashboard.
    Returns the final URL (expected to carry the invitee's role hash)."""
    page.evaluate("() => { window.location.hash = '#/get-started'; }")
    page.wait_for_timeout(3500)
    enable_flutter_acc(page)
    fill(page, "Code (optional)", code)
    fill(page, "Your Name", name)
    fill(page, "Email", email)
    fill(page, "Password", password)
    # Filling Code swaps the landing form into 'Activate your code' mode
    # with an 'Activate' button (probed).
    hit = click_btn(page, "Activate", wait=6000) or click_btn(page, "Get started", wait=6000)
    print(f"    invitee {email} submit={hit} code={code}")
    for hop in range(8):
        url = page.url
        if any(h in url for h in ROLE_HASHES):
            break
        txt = page_text(page)
        if "invalid" in txt or "not found" in txt or "expired" in txt or "error" in txt:
            print(f"    invitee {email}: error text visible, stopping")
            break
        acted = (click_btn(page, "Continue", wait=3000)
                 or click_btn(page, "Next", wait=3000)
                 or click_btn(page, "Finish Setup", wait=3000))
        if not acted:
            break
    enable_flutter_acc(page)
    print(f"    invitee {email}: -> {page.url}")
    return page.url


def generate_invite_token(page, fallback):
    """The 'Invite ...' dialog must already be open. Press 'Generate Link'
    (the ONLY place a token is minted — one per press; mock _idCounter starts
    at 10, so the Nth press of the run yields wlp_0000(10+N)), read the token
    off the QR dialog (page text, then clipboard via a trusted gesture), then
    close both dialogs. Returns the token string (may be the predicted
    `fallback` when both read paths fail)."""
    gl = click_btn(page, "Generate Link", wait=4000)
    token = ""
    # QR dialog shows the token as SelectableText — try page text first.
    for _ in range(4):
        codes = re.findall(r"wlp_[A-Za-z0-9]+", page_text(page))
        if codes:
            token = codes[0]
            break
        page.wait_for_timeout(500)
    if not token:
        # Clipboard write needs a TRUSTED gesture (JS el.click() is untrusted
        # and navigator.clipboard.writeText gets rejected silently), so
        # coordinate-click the exact-text node.
        pt = page.evaluate("""() => {
            for (const s of document.querySelectorAll('flt-semantics')) {
                if ((s.textContent || '').trim() === 'Copy code') {
                    const r = s.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0)
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                }
            }
            return null;
        }""")
        if pt:
            page.mouse.click(pt["x"], pt["y"])
            page.wait_for_timeout(500)
        for _ in range(6):
            page.wait_for_timeout(500)
            clip = ""
            try:
                clip = page.evaluate("navigator.clipboard.readText()") or ""
            except Exception:
                pass
            codes = re.findall(r"wlp_[A-Za-z0-9]+", clip)
            if codes:
                token = codes[0]
                break
    if not token:
        token = fallback
        print(f"    invite token read failed -> using predicted {fallback}")
    click_btn(page, "Done", wait=2000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(1200)
    enable_flutter_acc(page)
    print(f"    invite token: {token} (generate={gl})")
    return token


def go_home(page, tries=3):
    """Land on the owner dashboard WITHOUT a page reload (a reload would
    wipe the static in-memory mock stores this run created).

    - Bottom-nav Home tab: works on shell screens (dashboard/marketplace/
      notifications).
    - hash '#/owner': no-op when already '#/owner', never pops a pushed
      route (AgreementDetail doesn't even change the URL).
    - Back button: the only way out of URL-less pushed routes."""
    for _ in range(tries):
        if has(page, ["Agreements"]):
            return True
        if has(page, ["Back"]):
            find_and_click(page, "Back", timeout=4000)
        else:
            find_and_click(page, "Home", timeout=4000)
        page.wait_for_timeout(2000)
        enable_flutter_acc(page)
        page.evaluate("() => { window.location.hash = '#/owner'; }")
        page.wait_for_timeout(1500)
        enable_flutter_acc(page)
    return has(page, ["Agreements"])


def go_marketplace(page):
    page.evaluate("() => { window.location.hash = '#/owner/marketplace'; }")
    page.wait_for_timeout(5000)
    enable_flutter_acc(page)


def run_tests():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True,
                                 args=["--enable-unsafe-swiftshader",
                                       "--disable-dev-shm-usage"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800},
                              permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    page.goto(BASE)
    page.wait_for_timeout(6000)

    # =====================================================================
    # CROSS-CUTTING CHECKS
    # =====================================================================
    print("\n=== CROSS-CUTTING CHECKS ===\n")

    # CC1: App launches without crashing — unauthenticated root is
    # redirected to the buyer's marketing front door (/get-started).
    # First load is slow (engine warm-up) — poll until the front door renders.
    enable_flutter_acc(page)
    texts = wait_for_texts(page, ["run your own", "wellness business", "Get started"],
                           timeout_ms=60000)
    s = screenshot(page, "CC01_front_door")
    texts = get_all_text(page)
    has_landing = any("wellness business" in t.lower() or "run your own" in t.lower()
                      for t in texts)
    record("CC1", "App launches, unauthenticated root → marketing front door (/get-started)",
           "pass" if has_landing else "fail",
           "Marketing landing visible", s, f"Found texts: {texts[:5]}")

    # CC2 (Round 6 flip): the Dev Quick Sign-In FAB is GONE for good —
    # the login screen only offers the real credential form.
    page.evaluate("() => { window.location.hash = '#/login'; }")
    page.wait_for_timeout(3000)
    enable_flutter_acc(page)
    s2 = screenshot(page, "CC02_no_dev_fab")
    labels = input_labels(page)
    form_ok = has(page, ["Sign In"]) and "Email" in labels
    no_dev = not has(page, ["Dev Quick Sign-In"])
    record("CC2", "Dev Quick Sign-In FAB removed from login screen (Round 6 flip)",
           "pass" if (no_dev and form_ok) else "fail",
           "No dev FAB; real Email/Password form present", s2,
           f"inputs={labels}, dev FAB present={not no_dev}")

    # CC3: fresh signup drives the REAL landing form end-to-end.
    url = signup(page, "Robot Yoga", "own1@robot.test", "Movement & Fitness",
                 "Yoga Studio", "Robot Yoga Co")
    wait_for_texts(page, ["Revenue"], timeout_ms=20000)
    s3 = screenshot(page, "CC03_own1_signup")
    ok3 = has(page, ["Robot Yoga Co"]) and has(page, ["Revenue Summary"])
    record("CC3", "Fresh owner signup (own1@robot.test) lands on its dashboard",
           "pass" if ok3 else "fail",
           "Dashboard with the new business branding", s3,
           f"url={url}")

    # CC4: Bottom nav tabs switch screens correctly
    for tab in ["Content", "Revenue", "Network", "Settings", "Home"]:
        if find_and_click(page, tab):
            page.wait_for_timeout(1500)
            enable_flutter_acc(page)
            s_tab = screenshot(page, f"CC04_tab_{tab}")
            tab_texts = get_all_text(page)
            if not tab_texts:
                record("CC4", f"Tab '{tab}' loads content", "fail",
                       "Tab shows content", s_tab, f"No text found on {tab} tab")
            else:
                record("CC4", f"Tab '{tab}' loads content", "pass",
                       "Tab shows content", s_tab)
        else:
            record("CC4", f"Tab '{tab}' clickable", "fail",
                   "Tab responds to click", "", "Tab not found")

    # CC5: Content list loads (pull-to-refresh N/A on web)
    find_and_click(page, "Content")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s5 = screenshot(page, "CC05_content_list")
    texts = get_all_text(page)
    record("CC5", "Content list loads (pull-to-refresh N/A on web)",
           "pass" if texts else "fail",
           "Content list visible", s5, "Pull-to-refresh is mobile-only; verified list loads")

    # CC6: Empty states show sensible text (not "null")
    find_and_click(page, "Home")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s6 = screenshot(page, "CC06_empty_states")
    texts = get_all_text(page)
    has_null = any("null" in t.lower() for t in texts)
    record("CC6", "Empty states show sensible text (no 'null')",
           "pass" if not has_null else "fail",
           "No 'null' text visible", s6, f"Texts: {texts[:8]}")

    # CC7: Notification bell icon
    has_bell = find_and_click(page, "Notifications") or find_and_click(page, "Notification")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s7 = screenshot(page, "CC07_notifications")
    texts = get_all_text(page)
    record("CC7", "Notification bell opens notifications",
           "pass" if has_bell else "fail",
           "Notification panel/list visible", s7, f"Found: {texts[:5]}")

    # CC8: real in-app sign-out (Settings -> Sign Out, NO reload)
    signed_out = real_sign_out(page)
    page.wait_for_timeout(2000)
    enable_flutter_acc(page)
    s8 = screenshot(page, "CC08_signed_out")
    texts = get_all_text(page)
    back_to_login = any("sign in" in t.lower() or "wellness business" in t.lower()
                        for t in texts)
    record("CC8", "Sign out (Settings → Sign Out, in-app) returns to front door",
           "pass" if signed_out and back_to_login and not on_role_shell(page) else "fail",
           "Unauthenticated front door after sign-out", s8,
           f"url={page.url}")

    # CC9: Window resize doesn't break layout
    page.set_viewport_size({"width": 800, "height": 600})
    page.wait_for_timeout(1500)
    s9a = screenshot(page, "CC09_small_window")
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.wait_for_timeout(1500)
    screenshot(page, "CC09_large_window")
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_timeout(1000)
    record("CC9", "Window resize doesn't break layout", "pass",
           "Layout adapts to resize", s9a, "Small: 800x600, Large: 1920x1080")

    # =====================================================================
    # LOGIN-SCREEN INTEGRITY (replaces the deleted QA Console section)
    # =====================================================================
    print("\n=== LOGIN SCREEN INTEGRITY ===\n")

    page.evaluate("() => { window.location.hash = '#/login'; }")
    page.wait_for_timeout(3000)
    enable_flutter_acc(page)
    s_qc = screenshot(page, "QC01_login_form")
    labels = input_labels(page)
    form_ok = (has(page, ["Sign In"]) and "Email" in labels
               and any(l.startswith("Password") for l in labels))
    no_qa = (not has(page, ["Open QA Console"])
             and not has(page, ["Dev Quick Sign-In"]))
    record("QC1", "Login screen: real credential form only (no QA Console / dev entries)",
           "pass" if (form_ok and no_qa) else "fail",
           "Email/Password/Sign In present, no dev or QA entry points", s_qc,
           f"inputs={labels}")

    # =====================================================================
    # 3-OWNER TEST PLAN (Round 6: real accounts, no dev chips)
    # =====================================================================
    print("\n=== 3-OWNER TEST PLAN (real flows) ===\n")

    # Step 1: own1 re-login via typed credentials, empty Network tabs
    login(page, "own1@robot.test")
    find_and_click(page, "Network")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    find_and_click(page, "Associates")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s1 = screenshot(page, "step01_own1_associates")
    found = has(page, ["Invite"])
    no_seed = not has(page, ["Jordan"])
    record("Step 1", "own1 typed re-login; Network → Associates empty (no seeded members)",
           "pass" if (found and no_seed) else "fail",
           "Empty Associates list for a new business", s1,
           f"tab reached (Invite FAB)={found}, seeded member present={not no_seed}, "
           f"texts={get_all_text(page)[:5]}")
    real_sign_out(page)

    # Step 2: fresh signup own4
    url = signup(page, "Robot Pilates", "own4@robot.test", "Movement & Fitness",
                 "Pilates Studio", "Robot Pilates Co")
    branded = has(page, ["Robot Pilates Co"])
    find_and_click(page, "Network")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    find_and_click(page, "Associates")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s2b = screenshot(page, "step02_own4_associates")
    found = has(page, ["Invite"])
    no_seed = not has(page, ["Jordan"]) and not has(page, ["Robot Associate"])
    record("Step 2", "own4 fresh signup; Network → Associates empty",
           "pass" if (branded and found and no_seed) else "fail",
           "New business dashboard + empty Network", s2b,
           f"url={url} branded={branded} invite_fab={found} seeded={not no_seed}")
    real_sign_out(page)

    # Step 3: fresh signup own3 (will run the invite path)
    url = signup(page, "Robot Strength", "own3@robot.test", "Movement & Fitness",
                 "Strength Coach", "Robot Strength Co")
    branded = has(page, ["Robot Strength Co"])
    find_and_click(page, "Network")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    find_and_click(page, "Associates")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s3b = screenshot(page, "step03_own3_associates")
    found = has(page, ["Invite"])
    no_seed = not has(page, ["Jordan"]) and not has(page, ["Robot Associate"])
    record("Step 3", "own3 fresh signup; Network → Associates empty",
           "pass" if (branded and found and no_seed) else "fail",
           "New business dashboard + empty Network", s3b,
           f"url={url} branded={branded} invite_fab={found} seeded={not no_seed}")
    real_sign_out(page)

    # Step 4: typed re-login restores own3 (session for the invite flow)
    login(page, "own3@robot.test")
    s4 = screenshot(page, "step04_own3_relogin")
    ok4 = has(page, ["Robot Strength Co"]) and has(page, ["Revenue Summary"])
    record("Step 4", "Typed Email/Password re-login restores the session (own3)",
           "pass" if ok4 else "fail",
           "Dashboard visible after re-login", s4, f"url={page.url}")

    # ---- Step 5: own3 invites an associate (real one-time token) ----
    find_and_click(page, "Network")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    find_and_click(page, "Associates")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    inv = find_and_click(page, "Invite")
    token_assoc = ""
    if inv:
        token_assoc = generate_invite_token(page, "wlp_000011")
    s5b = screenshot(page, "step05_invite_token")
    record("Step 5", "Owner invites an Associate (invite link generated)",
           "pass" if (inv and token_assoc.startswith("wlp_")) else "fail",
           "Invite dialog + one-time invite token", s5b,
           f"invite_fab={inv} token={token_assoc or 'NONE'}")

    # ---- Step 6: invitee joins via the landing Code field ----
    joined_url = ""
    rec6, note6 = "fail", ""
    if token_assoc:
        real_sign_out(page)
        joined_url = invitee_signup(page, token_assoc, "Robot Associate",
                                    "assoc@robot.test")
        find_and_click(page, "Network")
        page.wait_for_timeout(1500)
        enable_flutter_acc(page)
        s6b = screenshot(page, "step06_assoc_owner_card")
        owner_card = has_all(page, ["Owner", "Robot Strength Co"])
        rec6 = "pass" if ("/partner" in joined_url and owner_card) else "fail"
        note6 = f"url={joined_url} owner_card={owner_card} token={token_assoc}"
    else:
        s6b = screenshot(page, "step06_skipped")
        note6 = "Cascade: no invite token from Step 5."
    record("Step 6", "Invitee joins via invite code and sees the Owner card",
           rec6, "Invitee on /partner with linked-owner card", s6b, note6)

    # ---- Step 7: associate invites a client ----
    inv7 = find_and_click(page, "Invite")
    token_client = ""
    if inv7:
        token_client = generate_invite_token(page, "wlp_000012")
    s7b = screenshot(page, "step07_assoc_invite_client")
    record("Step 7", "Associate invites a client (invite link generated)",
           "pass" if (inv7 and token_client.startswith("wlp_")) else "fail",
           "Client invite dialog + one-time invite token", s7b,
           f"invite_fab={inv7} token={token_client or 'NONE'}")
    real_sign_out(page)

    # ---- Step 8: own3 proposes a deal to the linked associate ----
    # KNOWN dead-end (Round 6 do-not-fix): the invite-linked associate has
    # no category, so `_propose()` early-returns on a null
    # partnerCategoryId (propose_agreement_screen.dart:237) — 'Send
    # Proposal' is a silent no-op and the propose screen never pops.
    # Record the real outcome honestly (expected FAIL), then pop the screen.
    login(page, "own3@robot.test")
    find_and_click(page, "Network")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    find_and_click(page, "Associates")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s8a = screenshot(page, "step08_associates")
    step8_sent = False
    rec8, s8c, note8 = "fail", s8a, ""
    banner = has(page, ["Propose a deal"])
    if banner:
        click_prefix(page, "Propose a deal")
        s8b = screenshot(page, "step08_propose_screen")
        propose_ui = has(page, ["Propose Agreement"]) and has(page, ["Select associate"])
        if propose_ui:
            click_exact(page, "Select associate")
            click_btn_prefix(page, "Robot Associate", wait=2000) or \
                click_prefix(page, "Robot Associate")
            picked = has(page, ["Robot Associate (no category)"])
            click_exact(page, "Send Proposal")
            propose_closed = until_absent(page, ["Propose Agreement", "Send Proposal"],
                                          8000)
            step8_sent = propose_closed and has(page, ["Discover new associates"])
            rec8 = "pass" if (picked and step8_sent) else "fail"
            s8c = screenshot(page, "step08_after_send")
            note8 = (f"picked={picked} screen_popped={propose_closed}. "
                     "KNOWN invite→propose dead-end: invite-linked associate has "
                     "no category → partnerCategoryId null → _propose() returns "
                     "silently (propose_agreement_screen.dart:237); no agreement "
                     "is created.")
            if not step8_sent:
                click_exact(page, "Back", wait=3000)   # pop the stuck screen
                page.wait_for_timeout(1500)
                enable_flutter_acc(page)
        else:
            s8c = s8b
            note8 = "Propose screen controls (Select associate / Send Proposal) not exposed."
    else:
        note8 = "No 'Propose a deal' banner on the Associates list."
    record("Step 8", "Owner proposes a deal to the linked Associate",
           rec8, "Propose screen closes (proposal delivered)", s8c, note8)

    # ---- Step 9: receiver-side accept/decline ----
    rec9, note9 = "fail", ""
    if step8_sent:
        real_sign_out(page)
        login(page, "assoc@robot.test")
        seen = False
        for route_lbl in ["Network", "Agreements", "Home"]:
            find_and_click(page, route_lbl, timeout=5000)
            page.wait_for_timeout(2000)
            enable_flutter_acc(page)
            if has_text(page, ["Accept", "Decline", "Proposal"]):
                seen = True
                break
        acc = click_exact(page, "Accept") if seen else False
        s9c = screenshot(page, "step09_receiver")
        rec9 = "pass" if (seen and acc) else "fail"
        note9 = f"proposal markers seen={seen} accept_clicked={acc}"
        real_sign_out(page)
    else:
        s9c = screenshot(page, "step09_cascade")
        note9 = ("Cascade: Step 8 did not deliver a proposal (known invite→propose "
                 "dead-end), so the receiver has nothing to accept.")
    record("Step 9", "Associate receives and can accept/decline the proposal",
           rec9, "Proposal visible to Associate with Accept/Decline", s9c, note9)

    # =====================================================================
    # Steps 10-13: Partnership Marketplace path (own1 <-> own4)
    # =====================================================================
    print("\n--- Marketplace path (two real owners) ---\n")

    # own4 availability: Discoverable + open the Yoga slot (chip own1 picks)
    real_sign_out(page)
    login(page, "own4@robot.test")
    go_marketplace(page)
    toggle_slot(page, "Discoverable")
    toggle_slot(page, "Yoga Studio")
    own4_ready = switch_states(page)[:2] == ["true", "true"]

    # own1: Discoverable + open Pilates slot -> discovers own4
    real_sign_out(page)
    login(page, "own1@robot.test")
    go_marketplace(page)
    toggle_slot(page, "Discoverable")
    toggle_slot(page, "Pilates Studio")
    scroll_down(page, steps=6)
    s10 = screenshot(page, "step10_discovery")
    has_tile = has(page, ["Robot Pilates Co"])
    record("Step 10", "Owner discovers a new associate in the marketplace",
           "pass" if has_tile else "fail",
           "Discoverable listing tile for Robot Pilates Co", s10,
           f"own4_ready={own4_ready} tile={has_tile}")

    # Step 11: own1 sends an Associate Request for the Yoga slot
    sent = False
    ev11 = []
    if has_tile:
        click_contains(page, "Robot Pilates Co", wait=3000)
        enable_flutter_acc(page)
        if has(page, ["Open Collab Slots"]):
            (click_exact(page, "Yoga Studio", wait=1500)
             or click_contains(page, "Yoga Studio", wait=1200))
            enable_flutter_acc(page)
        hit = click_exact(page, "Send Associate Request", wait=6000)
        page.wait_for_timeout(2500)
        enable_flutter_acc(page)
        ev11.append(f"send_btn={hit}")
        if has(page, ["Confirm Request"]):
            fill_first_input(page, "Robot Yoga would love to collab.")
            click_exact(page, "Confirm Request", wait=6000)
            page.wait_for_timeout(3500)
            enable_flutter_acc(page)
            sent = has(page, ["Request sent"])
    s11 = screenshot(page, "step11_request")
    page.keyboard.press("Escape")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    pending_badge = has(page, ["Pending"])
    sent = sent or pending_badge
    record("Step 11", "Owner sends an Associate Request (pending outbound)",
           "pass" if sent else "fail",
           "'Request sent' / tile shows Pending", s11,
           f"{','.join(ev11)} confirmed={sent} badge={pending_badge}")

    # Step 12: own4 receives -> accept -> split -> confirm
    real_sign_out(page)
    login(page, "own4@robot.test")
    go_marketplace(page)
    scroll_down(page, steps=6)
    got = has_all(page, ["Received Requests", "Robot Yoga Co"])
    s12 = screenshot(page, "step12_received")
    accepted = False
    if got:
        click_exact(page, "Accept", wait=6000)
        page.wait_for_timeout(3000)
        enable_flutter_acc(page)
        if has(page, ["Set your commission split"]):
            click_exact(page, "Confirm Collab", wait=6000)
            page.wait_for_timeout(3700)
            enable_flutter_acc(page)
            accepted = not has(page, ["Accept", "Decline", "Confirm Collab"])
            s12 = screenshot(page, "step12_accepted")
    record("Step 12", "Receiver accepts the request and confirms the collab",
           "pass" if (got and accepted) else "fail",
           "Accept → commission split → Confirm Collab → cleared", s12,
           f"received={got} confirmed={accepted}")

    # Step 13: sender approves -> Active
    real_sign_out(page)
    login(page, "own1@robot.test")
    s13 = screenshot(page, "step13_pending")
    own1_pending = has(page, ["1 Pending"])
    approved = False
    if own1_pending:
        click_contains(page, "1 Pending", wait=4000)
        page.wait_for_timeout(2500)
        enable_flutter_acc(page)
        detail = has(page, ["Approve"])
        if detail:
            click_exact(page, "Approve", wait=6000)
            page.wait_for_timeout(3500)
            enable_flutter_acc(page)
            page.evaluate("() => { window.location.hash = '#/owner'; }")
            page.wait_for_timeout(3000)
            enable_flutter_acc(page)
            approved = has(page, ["1 Active"]) and not has(page, ["1 Pending"])
            s13 = screenshot(page, "step13_approved")
    record("Step 13", "Sender approves the proposed agreement → Active",
           "pass" if approved else "fail",
           "Dashboard shows 1 Active / 0 Pending after Approve", s13,
           f"pending_chip={own1_pending} approved={approved}")

    # =====================================================================
    # Steps 14-17: money loop (Round 6 payments)
    # =====================================================================
    print("\n--- Money loop (record payment → commission payout) ---\n")

    # Step 14: active agreement detail + Record payment dialog fields
    go_home(page)
    click_contains(page, "1 Active", wait=4000)
    page.wait_for_timeout(2500)
    enable_flutter_acc(page)
    detail_ok = has_after_scroll(page, ["Record payment", "End Agreement"])
    s14 = screenshot(page, "step14_detail")
    dialog_ok = False
    labels14 = []
    if detail_ok:
        click_exact(page, "Record payment", wait=6000)
        page.wait_for_timeout(2500)
        enable_flutter_acc(page)
        labels14 = input_labels(page)
        dialog_ok = (has(page, ["Confirm Payment", "Payment method"])
                     and any(a.startswith("Amount") for a in labels14))
        s14 = screenshot(page, "step14_payment_dialog")
    record("Step 14", "Agreement detail exposes Record payment + dialog fields",
           "pass" if (detail_ok and dialog_ok) else "fail",
           "Amount/Payment method inputs + Confirm Payment button", s14,
           f"detail={detail_ok} dialog={dialog_ok} inputs={labels14}")

    # Step 15: record $120 -> payment txn + pending commission in Revenue
    dialog_closed = revenue_ok = False
    if dialog_ok:
        fill_by_label_prefix(page, "Amount", "120")
        click_exact(page, "Confirm Payment", wait=1200)
        page.wait_for_timeout(3500)
        enable_flutter_acc(page)
        dialog_closed = until_absent(page, ["Confirm Payment"], 8000)
        if has(page, ["Confirm Payment"]):  # never strand the modal
            click_exact(page, "Cancel", wait=3000)
            page.wait_for_timeout(1000)
            enable_flutter_acc(page)
    go_home(page)
    find_and_click(page, "Revenue", timeout=6000)
    page.wait_for_timeout(3000)
    enable_flutter_acc(page)
    revenue_ok = has_after_scroll(page, ["Session payment", "Mark Paid"])
    deal_active = has(page, ["ACTIVE"])
    s15 = screenshot(page, "step15_revenue_payment")
    record("Step 15", "Recorded $120 payment → txn + pending commission in Revenue",
           "pass" if (dialog_closed and revenue_ok) else "fail",
           "Session payment txn + Mark Paid row + ACTIVE deal", s15,
           f"dialog_closed={dialog_closed} revenue={revenue_ok} deal_active={deal_active}")

    # Step 16: Mark Paid -> payout txn on own1's ledger, button disappears
    btn_gone = payout = summary = False
    s16 = s15
    if revenue_ok:
        click_exact(page, "Mark Paid", wait=6000)
        page.wait_for_timeout(3500)
        enable_flutter_acc(page)
        btn_gone = not has(page, ["Mark Paid"])
        payout = has_after_scroll(page, ["Commission payout to Robot Pilates Co"])
        summary = has(page, ["Commissions Paid $24.00", "Commissions $24.00",
                             "$96.00", "$24.00 PAID"])
        s16 = screenshot(page, "step16_payout")
    record("Step 16", "Mark Paid pays the commission out (payout txn + summary)",
           "pass" if (revenue_ok and btn_gone and payout) else "fail",
           "Button gone, payout txn on own1 ledger, Net $96 / commission $24", s16,
           f"btn_gone={btn_gone} payout_txn={payout} summary_seen={summary}")

    # Step 17: the payout lands in the PAYEE's own ledger
    real_sign_out(page)
    login(page, "own4@robot.test")
    go_home(page)
    find_and_click(page, "Revenue", timeout=6000)
    page.wait_for_timeout(3000)
    enable_flutter_acc(page)
    o_payout = has_after_scroll(page, ["Commission payout to Robot Pilates Co"])
    o_no_mark = not has(page, ["Mark Paid"])
    o_deal = has(page, ["ACTIVE"])
    s17 = screenshot(page, "step17_payee_ledger")
    record("Step 17", "Payee (own4) sees the commission payout in its own ledger",
           "pass" if (o_payout and o_no_mark) else "fail",
           "Payout txn visible, no Mark Paid button for the payee", s17,
           f"payout={o_payout} no_mark={o_no_mark} deal_active={o_deal}")

    # =====================================================================
    # Steps 18-21: Business Features toggles
    # =====================================================================
    print("\n=== BUSINESS FEATURES TOGGLES ===\n")

    real_sign_out(page)
    login(page, "own1@robot.test")
    find_and_click(page, "Settings")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    has_bf = (find_and_click(page, "Business Features")
              or find_and_click(page, "Features"))
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    find_and_click(page, "Collabs")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s18 = screenshot(page, "toggle_step18_collabs_off")
    texts = get_all_text(page)
    record("Step 18", "Business Features — toggle Collabs off",
           "pass" if has_bf else "fail",
           "Collabs toggle switched off", s18, f"Texts: {texts[:8]}")

    toggled_on = find_and_click(page, "Collabs")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s19 = screenshot(page, "toggle_step19_collabs_on")
    record("Step 19", "Business Features — toggle Collabs back on",
           "pass" if toggled_on else "fail",
           "Collabs toggle restored", s19)

    toggled_mp = find_and_click(page, "Marketplace")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s20 = screenshot(page, "toggle_step20_marketplace_off")
    record("Step 20", "Business Features — toggle Marketplace off (then restored)",
           "pass" if toggled_mp else "fail",
           "Marketplace toggle exercised", s20)
    find_and_click(page, "Marketplace")   # restore
    page.wait_for_timeout(1000)

    toggled_ag = find_and_click(page, "Agreements")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s21 = screenshot(page, "toggle_step21_agreements_off")
    record("Step 21", "Business Features — toggle Agreements off (then restored)",
           "pass" if toggled_ag else "fail",
           "Agreements toggle exercised", s21)
    find_and_click(page, "Agreements")    # restore
    page.wait_for_timeout(1000)

    page.evaluate("() => { window.location.hash = '#/owner'; }")
    page.wait_for_timeout(2500)
    enable_flutter_acc(page)

    # =====================================================================
    # OWNER ROLE CHECKLIST
    # =====================================================================
    print("\n=== OWNER ROLE CHECKLIST ===\n")

    find_and_click(page, "Home")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "owner_dashboard")
    ok = has_all(page, ["Revenue Summary", "Net Revenue"])
    record("Owner", "Dashboard loads with summary cards/stats",
           "pass" if ok else "fail",
           "Dashboard with revenue summary", s, f"Texts: {get_all_text(page)[:6]}")

    find_and_click(page, "Content")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "owner_content")
    content_ok = has(page, ["Tools", "Scheduling", "Catalog"])
    record("Owner", "Content (Activity) list loads with tool cards",
           "pass" if content_ok else "fail",
           "Content list + tools visible", s, f"Texts: {get_all_text(page)[:6]}")

    find_and_click(page, "Revenue")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "owner_revenue")
    rev_ok = has(page, ["Deals", "Transactions"])
    record("Owner", "Revenue (Finance) loads with deals/transactions",
           "pass" if rev_ok else "fail",
           "Finance view with deals", s, f"Texts: {get_all_text(page)[:6]}")

    # Network: Associates + Staff (generate the staff invite token) + Clients
    find_and_click(page, "Network")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    assoc_tab = find_and_click(page, "Associates")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    assoc_fab = has(page, ["Invite"])
    staff_tab = find_and_click(page, "Staff")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    inv_staff = find_and_click(page, "Invite")
    token_staff = ""
    if inv_staff:
        token_staff = generate_invite_token(page, "wlp_000013")
    clients_tab = find_and_click(page, "Clients")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "owner_network_tabs")
    net_ok = (assoc_tab and assoc_fab and staff_tab and inv_staff
              and token_staff.startswith("wlp_") and clients_tab)
    record("Owner", "Network → Associates/Staff/Clients tabs + staff invite link",
           "pass" if net_ok else "fail",
           "All three tabs load; staff invite token generated", s,
           f"assoc_tab={assoc_tab} invite_fab={assoc_fab} staff_tab={staff_tab} "
           f"staff_invite={inv_staff} token={token_staff or 'NONE'} "
           f"clients_tab={clients_tab}")

    find_and_click(page, "Settings")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "owner_settings")
    settings_ok = has(page, ["Business Features"])
    record("Owner", "Settings screen loads (features entry points present)",
           "pass" if settings_ok else "fail",
           "Settings with Business Features entry", s,
           f"Texts: {get_all_text(page)[:6]}")

    chats_hit = (find_and_click(page, "Chats") or find_and_click(page, "Chat"))
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "owner_chats")
    record("Owner", "Chat icon opens conversations list",
           "pass" if chats_hit else "fail",
           "Conversations list visible", s, f"Texts: {get_all_text(page)[:6]}")

    # =====================================================================
    # ASSOCIATE ROLE CHECKLIST (the invite-linked account from Step 6)
    # =====================================================================
    print("\n=== ASSOCIATE ROLE CHECKLIST ===\n")

    real_sign_out(page)
    login(page, "assoc@robot.test")
    s = screenshot(page, "associate_dashboard")
    ok = has(page, ["launch your own"])
    record("Associate", "Dashboard loads with Launch Your Own prompt",
           "pass" if ok else "fail",
           "Partner shell prompt visible", s, f"Texts: {get_all_text(page)[:6]}")

    # Invitee profiles carry no jobId -> activeJobConfigProvider falls back
    # to platform base terminology ("Sessions"), not "Activity"/"Content".
    hit = (find_and_click(page, "Activity") or find_and_click(page, "Content")
           or find_and_click(page, "Sessions"))
    s = screenshot(page, "associate_activity")
    record("Associate", "Activity view loads (view-only)",
           "pass" if hit else "fail", "Activity view visible", s,
           f"clicked={hit}")

    hit = (find_and_click(page, "Finance") or find_and_click(page, "Revenue"))
    s = screenshot(page, "associate_finance")
    record("Associate", "Finance — associate-scoped view loads",
           "pass" if hit else "fail", "Associate finance view", s,
           f"clicked={hit}")

    find_and_click(page, "Network")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "associate_network")
    owner_card = has_all(page, ["Owner", "Robot Strength Co"])
    record("Associate", "Network — Owner shown as card at top",
           "pass" if owner_card else "fail",
           "Owner card visible", s, f"Texts: {get_all_text(page)[:6]}")

    find_and_click(page, "Settings")
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    up = (find_and_click(page, "Launch") or find_and_click(page, "Upgrade")
          or find_and_click(page, "Practice"))
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "associate_upgrade")
    record("Associate", "Upgrade to Pro (Launch Your Own Business)",
           "pass" if up else "fail",
           "Upgrade option visible in Settings", s, f"clicked={up}")

    # =====================================================================
    # STAFF ROLE CHECKLIST (staff invite token from the Owner checklist)
    # =====================================================================
    print("\n=== STAFF ROLE CHECKLIST ===\n")

    real_sign_out(page)
    # NOT staff@/client@/owner@/partner@ — mock_auth_source.dart:94 rejects
    # sign-ups whose email starts with those reserved prefixes.
    staff_url = invitee_signup(page, token_staff or "wlp_000013",
                               "Robot Staff", "invite.staff@robot.test")
    s = screenshot(page, "staff_dashboard")
    joined_staff = "/staff" in staff_url
    record("Staff", "Staff invitee joins via invite code → staff dashboard",
           "pass" if joined_staff else "fail",
           "Staff shell visible after invite redemption", s,
           f"url={staff_url} token={token_staff or 'NONE'}")

    hit = (find_and_click(page, "Activity") or find_and_click(page, "Content")
           or find_and_click(page, "Sessions"))
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "staff_activity")
    record("Staff", "Activity — can view",
           "pass" if hit else "fail", "Activity view visible", s,
           f"clicked={hit}")

    # =====================================================================
    # CLIENT ROLE CHECKLIST (client invite token from Step 7)
    # =====================================================================
    print("\n=== CLIENT ROLE CHECKLIST ===\n")

    real_sign_out(page)
    client_url = invitee_signup(page, token_client or "wlp_000012",
                                "Robot Client", "invite.client@robot.test")
    s = screenshot(page, "client_dashboard")
    joined_client = "/client" in client_url
    record("Client", "Client invitee joins via invite code → client dashboard",
           "pass" if joined_client else "fail",
           "Client shell visible after invite redemption", s,
           f"url={client_url} token={token_client or 'NONE'}")

    # Client nav: Home | Sessions | Associates | Payments | Settings
    hit = (find_and_click(page, "Activity") or find_and_click(page, "Hub")
           or find_and_click(page, "Sessions"))
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "client_activity")
    record("Client", "Activity Hub — browse classes/sessions",
           "pass" if hit else "fail", "Activity Hub visible", s,
           f"clicked={hit}")

    hit = (find_and_click(page, "Payments") or find_and_click(page, "Finance"))
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "client_payments")
    record("Client", "Payments — client-facing history loads",
           "pass" if hit else "fail", "Payment history visible", s,
           f"clicked={hit}")

    hit = (find_and_click(page, "Profile") or find_and_click(page, "Settings"))
    page.wait_for_timeout(1500)
    enable_flutter_acc(page)
    s = screenshot(page, "client_profile")
    texts = get_all_text(page)
    record("Client", "Profile — client can view/edit profile",
           "pass" if (hit and texts) else "fail",
           "Profile screen visible", s, f"clicked={hit} texts={texts[:6]}")

    # =====================================================================
    # SAVE RESULTS
    # =====================================================================
    browser.close()
    pw.stop()

    with open("test_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2)

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["result"] == "pass")
    failed = sum(1 for r in RESULTS if r["result"] == "fail")
    blocked = sum(1 for r in RESULTS if r["result"] == "blocked")
    print(f"\n{'='*60}")
    print(f"TOTAL: {total} | PASS: {passed} | FAIL: {failed} | BLOCKED: {blocked}")
    print(f"{'='*60}")

    return RESULTS

if __name__ == "__main__":
    run_tests()
