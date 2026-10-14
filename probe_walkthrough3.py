# probe_walkthrough3.py — step-accurate hub navigation probe (2026-10-12).
#
# Probes 1-2 showed: the Tools tile IS a role=button semantics node;
# find_and_click's el.click() reported success but the URL never changed;
# raw clicks at guessed coordinates missed (fresh-owner hub has a "No
# Class yet" banner shifting tiles down). This probe prints URL + text
# head after EVERY action, and clicks tiles via their OWN semantics rect.

from playwright.sync_api import sync_playwright
import master_test as mt

BASE = "http://localhost:9090"

FIND_NODE = """([needle, wantRole]) => {
    let best = null;
    for (const s of document.querySelectorAll('flt-semantics')) {
        const t = (s.textContent || '').trim().replace(/\\s+/g, ' ');
        const al = (s.getAttribute('aria-label') || '').trim();
        const role = s.getAttribute('role');
        const label = al || t;
        if (wantRole && role !== wantRole) continue;
        if (label.toLowerCase() !== needle &&
            !(label.toLowerCase().startsWith(needle) &&
              /^[\\s(]/.test(label.slice(needle.length) || ' '))) continue;
        const r = s.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        if (!best || r.width * r.height < best.w * best.h) {
            best = {x: r.x + r.width / 2, y: r.y + r.height / 2,
                    w: r.width, h: r.height, text: label.slice(0, 50), role};
        }
    }
    return best;
}"""


def state(page, tag):
    print(f"[{tag}] url={page.url}")
    print(f"    texts: {mt.get_all_text(page)[:6]}")


def rect_click(page, needle, role=None):
    n = page.evaluate(FIND_NODE, [needle, role])
    print(f"    node({needle!r}, role={role}): {n}")
    if not n:
        return False
    page.mouse.click(n["x"], n["y"])
    page.wait_for_timeout(2500)
    mt.enable_flutter_acc(page)
    return True


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE)
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)

    url = mt.signup(page, "Probe Three", "probe.three@robot.test",
                    "Movement & Fitness", "Yoga Studio", "Probe Three Yoga")
    print(f"signup -> {url}")

    # 1. dashboard state
    state(page, "after signup")

    # 2. Content tab -> hub
    rect_click(page, "Content", "tab")
    state(page, "hub")

    # 3. Schedule tile via its own semantics rect (role=button)
    rect_click(page, "Schedule", "button")
    state(page, "schedule tile clicked")

    # 4. back out
    rect_click(page, "Back", "button")
    state(page, "after back")
    rect_click(page, "Content", "tab")
    state(page, "hub again")

    # 5. Homework chip via rect
    rect_click(page, "Homework", None)
    state(page, "homework clicked")

    # 6. sign out from wherever we are
    so = mt.real_sign_out(page)
    print(f"sign out -> signed_out={so} url={page.url}")

    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
