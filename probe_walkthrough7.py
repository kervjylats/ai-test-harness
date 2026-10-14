# probe_walkthrough7.py — dump hub chip semantics after the Semantics() fix.
#
# Verifies whether the Round 8-style Semantics(button, container) wrap on
# _CompactEngagementChip produced standalone aria-label nodes for
# 'Homework'/'Reviews', and whether find_and_click can activate them.
#
#   python -u probe_walkthrough7.py

from playwright.sync_api import sync_playwright
import master_test as mt

BASE = "http://localhost:9090"

DUMP = """(needle) => {
    const out = [];
    for (const s of document.querySelectorAll('flt-semantics')) {
        const t = (s.textContent || '').trim().replace(/\\s+/g, ' ');
        const al = (s.getAttribute('aria-label') || '').trim();
        const role = s.getAttribute('role');
        if ((t + ' ' + al).toLowerCase().includes(needle)) {
            const r = s.getBoundingClientRect();
            out.push({text: t.slice(0, 46), aria: al.slice(0, 46), role,
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

    mt.signup(page, "Probe Seven", "probe.seven@robot.test",
              "Movement & Fitness", "Yoga Studio", "Probe Seven Yoga")
    mt.go_home(page)
    mt.find_and_click(page, "Content")
    found = mt.wait_for_texts(page, ["Tools"], timeout_ms=8000)
    print(f"hub has Tools: {mt.has(page, ['Tools'])}")
    print(f"hub has Engagement: {mt.has(page, ['Engagement'])}")

    for needle in ("homework", "reviews"):
        print(f"--- nodes matching {needle!r} ---")
        for n in page.evaluate(DUMP, needle):
            print("   ", n)

    print("--- find_and_click Homework ---")
    print("  ->", mt.find_and_click(page, "Homework"))
    texts = mt.wait_for_texts(page, ["assign homework", "no homework"],
                              timeout_ms=8000)
    body = " ".join(t.lower() for t in texts)
    print(f"  coach view: {any(k in body for k in ('assign homework', 'no homework'))}")
    print(f"  body head: {body[:140]}")

    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
