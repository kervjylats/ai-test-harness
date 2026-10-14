# probe_walkthrough2.py — isolate HOW to open the hub Tools tiles (2026-10-12).
#
# Probe 1 showed find_and_click's el.click() on the merged tile node
# reports success but never navigates. This probe dumps the semantics
# nodes around 'Schedule' and tries raw coordinate clicks at the tile's
# visual center, then verifies the Homework chip + sign-out path.

from playwright.sync_api import sync_playwright
import master_test as mt

BASE = "http://localhost:9090"

DUMP_NODES = """(needle) => {
    const out = [];
    for (const s of document.querySelectorAll('flt-semantics')) {
        const t = (s.textContent || '').trim().replace(/\\s+/g, ' ');
        const al = (s.getAttribute('aria-label') || '').trim();
        if ((t + ' ' + al).toLowerCase().includes(needle)) {
            const r = s.getBoundingClientRect();
            out.push({text: t.slice(0, 60), aria: al.slice(0, 60),
                      role: s.getAttribute('role'),
                      x: Math.round(r.x), y: Math.round(r.y),
                      w: Math.round(r.width), h: Math.round(r.height)});
        }
    }
    return out;
}"""


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE)
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)

    url = mt.signup(page, "Probe Two", "probe.two@robot.test",
                    "Movement & Fitness", "Yoga Studio", "Probe Two Yoga")
    print(f"signup -> {url}")
    mt.go_home(page)
    mt.find_and_click(page, "Content")
    page.wait_for_timeout(1500)
    mt.enable_flutter_acc(page)

    print("--- nodes matching 'schedule' ---")
    for n in page.evaluate(DUMP_NODES, "schedule"):
        print("  ", n)

    # Raw coordinate click at the visual tile center (tile 1 of Tools;
    # from the hub screenshot the card spans y~157-227, full width).
    page.mouse.click(640, 192)
    page.wait_for_timeout(2500)
    mt.enable_flutter_acc(page)
    print(f"raw center click -> url={page.url}")
    print(f"  texts: {mt.get_all_text(page)[:8]}")

    back = mt.go_home(page)
    print(f"back home -> {page.url} ok={back}")
    mt.find_and_click(page, "Content")
    page.wait_for_timeout(1500)
    mt.enable_flutter_acc(page)

    print("--- nodes matching 'homework' ---")
    for n in page.evaluate(DUMP_NODES, "homework"):
        print("  ", n)
    hw = mt.find_and_click(page, "Homework")
    page.wait_for_timeout(2000)
    mt.enable_flutter_acc(page)
    print(f"homework chip -> opened={hw} url={page.url}")
    print(f"  texts: {mt.get_all_text(page)[:8]}")

    back = mt.go_home(page)
    print(f"back home -> {page.url} ok={back}")
    so = mt.real_sign_out(page)
    print(f"sign out -> signed_out={so} url={page.url}")

    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
