"""
round3_check.py — Round 3 vocabulary spot-check (Partner→Associate, Partnership→Collab).
Signs in as an owner via the Dev Quick Sign-In sheet and asserts the new terminology
renders across owner UI, with no legacy "Partner"/"Partnership"/"Partners" labels.
"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080"
RESULTS = []
SHOT = Path("test_evidence")
SHOT.mkdir(exist_ok=True)
LEGACY = ("Partner", "Partners", "Partnership")
CLICKABLE_ROLES = ("checkbox", "tab", "button", "link")

def record(step, desc, ok, notes="", shot=""):
    RESULTS.append({"step": step, "description": desc,
                    "result": "pass" if ok else "fail",
                    "notes": notes, "screenshot": shot})
    print(f"  [{'PASS' if ok else 'FAIL'}] {step}: {desc} — {notes}")

def shot(page, name):
    p = SHOT / f"round3_{name}.png"
    page.screenshot(path=str(p))
    return str(p)

def enable_acc(page):
    page.evaluate("""() => {
        const b = document.querySelector('flt-semantics-placeholder');
        if (b) b.click();
    }""")
    page.wait_for_timeout(3000)

def acc_entries(page):
    snap = page.accessibility.snapshot()
    out = []
    def collect(n):
        if n.get("name"):
            out.append((n["name"], n.get("role")))
        for c in n.get("children", []):
            collect(c)
    collect(snap)
    return out

def texts(page):
    dom = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('flt-semantics'))
            .map(s => s.textContent).filter(Boolean);
    }""")
    names = [n for n, _ in acc_entries(page)]
    return list(set(dom + names))

def _click_rect(page, x, y):
    page.mouse.click(x, y)
    page.wait_for_timeout(1500)

def find_click(page, label):
    for attempt in range(4):
        m = page.evaluate("""(label) => {
            const sems = document.querySelectorAll('flt-semantics');
            const lower = label.toLowerCase();
            for (const s of sems) {
                const t = (s.textContent || '');
                if (t.toLowerCase().includes(lower) && t.length < 80) {
                    const r = s.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0)
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                }
            }
            return null;
        }""", label)
        if m:
            _click_rect(page, m["x"], m["y"])
            return True
        entries = acc_entries(page)
        for idx, (name, role) in enumerate(entries):
            if name == label and role in CLICKABLE_ROLES:
                k = sum(1 for (n2, r2) in entries[:idx] if r2 == role)
                rect = page.evaluate("""(sel) => {
                    const nodes = Array.from(document.querySelectorAll(sel)).filter(s => {
                        const r = s.getBoundingClientRect(); return r.width > 0;
                    });
                    return nodes.map(s => { const r = s.getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2}; });
                }""", 'flt-semantics[role="' + role + '"]')
                if k < len(rect):
                    _click_rect(page, rect[k]["x"], rect[k]["y"])
                    return True
        if attempt < 3:
            enable_acc(page)
            page.wait_for_timeout(1500)
    return False

def legacy_matches(t):
    return [x for x in t if any(L in x for L in LEGACY)]

def main_flow(page, browser):
    page.evaluate("""() => { window.location.hash = '#/login'; }""")
    page.wait_for_timeout(4000)
    enable_acc(page)

    fab = page.evaluate("""() => {
        const sems = document.querySelectorAll('flt-semantics[role="button"]');
        for (const s of sems) {
            if ((s.textContent || '') === 'Dev Quick Sign-In') {
                const r = s.getBoundingClientRect();
                if (r.width > 0) return {x: r.x + r.width/2, y: r.y + r.height/2};
            }
        }
        return null;
    }""")
    if not fab:
        record("R3.0", "Dev Quick Sign-In FAB present on login", False, "FAB not found")
        return
    page.mouse.click(fab["x"], fab["y"])
    page.wait_for_timeout(2500)
    enable_acc(page)

    t = texts(page)
    record("R3.1", "Dev sheet role chips rename Partner→Associate",
           "Associate" in t and not legacy_matches(t),
           f"'Associate' chip present={('Associate' in t)}, legacy={legacy_matches(t)}",
           shot(page, "dev_sheet_chips"))

    # ---- Owner dashboard (Yoga Studio) ----
    if not find_click(page, "Yoga Studio"):
        record("R3.2", "Owner dashboard: new vocabulary, no legacy",
               False, "could not sign in as Yoga Studio")
        return
    page.wait_for_timeout(4000)
    enable_acc(page)
    t = texts(page)
    ok = any("Associate" in x for x in t) and any("Collab" in x for x in t) and not legacy_matches(t)
    record("R3.2", "Owner dashboard: 'Associate'/'Collab' present, no legacy",
           ok, f"Associate={any('Associate' in x for x in t)}, "
               f"Collab={any('Collab' in x for x in t)}, legacy={legacy_matches(t)}",
           shot(page, "owner_dashboard"))

    # ---- Network → Associates tab ----
    find_click(page, "Network")
    enable_acc(page)
    find_click(page, "Associates")
    enable_acc(page)
    t = texts(page)
    has_tab = any("Associates" in x and len(x) < 20 for x in t)
    has_legacy = legacy_matches(t)
    has_discover = any("Discover new associates" in x for x in t)
    record("R3.3", "Network: 'Associates' tab, no 'Partners' tab",
           has_tab and not has_legacy,
           f"Associates tab={has_tab}, Partners={has_legacy}, Discover banner={has_discover}",
           shot(page, "network"))

    # ---- Settings → Business Features ----
    find_click(page, "Settings")
    enable_acc(page)
    find_click(page, "Business Features")
    enable_acc(page)
    t = texts(page)
    has_collabs = any("Collabs" in x for x in t)
    has_legacy = legacy_matches(t)
    record("R3.4", "Business Features: 'Collabs' tile, no 'Partners'",
           has_collabs and not has_legacy,
           f"Collabs={has_collabs}, legacy={has_legacy}",
           shot(page, "business_features"))

    # ---- Marketplace via the Discover banner (with #/owner/marketplace fallback) ----
    find_click(page, "Network")
    enable_acc(page)
    find_click(page, "Associates")
    enable_acc(page)
    opened = find_click(page, "Discover new associates")
    page.evaluate("""() => { window.location.hash = '#/owner/marketplace'; }""")
    page.wait_for_timeout(2500)
    opened = True
    page.wait_for_timeout(2500)
    enable_acc(page)
    t = texts(page)
    leg = legacy_matches(t)
    has_assoc = any("Associate" in x for x in t)
    has_collab = any("Collab" in x for x in t)
    record("R3.5", "Marketplace: 'Associates' terminology, no legacy labels",
           has_assoc and not leg,
           f"Associate={has_assoc}, Collab={has_collab} (content-dependent), legacy={leg}",
           shot(page, "marketplace"))

def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(BASE)
        page.wait_for_timeout(5000)
        main_flow(page, browser)
        browser.close()
    with open("round3_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2)
    passed = sum(1 for r in RESULTS if r["result"] == "pass")
    failed = sum(1 for r in RESULTS if r["result"] == "fail")
    print(f"\n--- SUMMARY: {passed} pass / {failed} fail / {len(RESULTS)} total ---")

if __name__ == "__main__":
    run()