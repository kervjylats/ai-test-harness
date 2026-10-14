# probe_walkthrough9.py — which Title-fill strategy does Flutter actually
# consume in the homework assign dialog? (2026-10-14)
#
# Run-2 evidence: fab/pick succeeded, Title field stayed EMPTY though the
# helper returned True. The app silently no-ops submit when title is empty
# (homework_list_screen.dart:95), so the probe verifies consumption via
# DOM input_value + semantics mirror, not via submit (fresh business has
# no clients to pick).
#
#   python -u probe_walkthrough9.py
from playwright.sync_api import sync_playwright
import master_test as mt


def dump_inputs(page, tag):
    rows = page.evaluate("""() => Array.from(
        document.querySelectorAll('input, textarea')).map(i => ({
            label: i.getAttribute('aria-label') || '',
            value: i.value || '',
            w: Math.round(i.getBoundingClientRect().width)}))""")
    print(f"[inputs {tag}]")
    for r in rows:
        print(f"    label={r['label'][:48]!r} value={r['value']!r} w={r['w']}")


def clear_title(page):
    idx = page.evaluate("""() => Array.from(
        document.querySelectorAll('input, textarea'))
        .findIndex(i => (i.getAttribute('aria-label') || '')
        .startsWith('Title'))""")
    if idx >= 0:
        page.locator("input, textarea").nth(idx).click()
        page.wait_for_timeout(300)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(300)


def fill_v2(page, prefix, value, tries=3):
    """Candidate fix: click to focus FIRST (attaches Flutter's editing
    session), then real trusted keystrokes, verified before returning."""
    for _ in range(tries):
        try:
            idx = page.evaluate("""(prefix) => Array.from(
                document.querySelectorAll('input, textarea'))
                .findIndex(i => {
                    const al = i.getAttribute('aria-label') || '';
                    const r = i.getBoundingClientRect();
                    return al.startsWith(prefix) && r.width > 0
                        && r.height > 0; })""", prefix)
            if idx < 0:
                continue
            el = page.locator("input, textarea").nth(idx)
            el.click()
            page.wait_for_timeout(400)
            page.keyboard.press("Control+A")
            page.keyboard.type(value, delay=15)
            page.wait_for_timeout(400)
            if el.input_value() == value:
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto("http://localhost:9090")
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)
    mt.signup(page, "Probe Nine", "probe.nine@robot.test",
              "Movement & Fitness", "Strength Coach", "Probe Nine Strength")
    mt.go_home(page)
    mt.find_and_click(page, "Content")
    mt.wait_for_texts(page, ["Tools"], timeout_ms=8000)
    mt.enable_flutter_acc(page)
    mt.find_and_click(page, "Homework")
    mt.wait_for_texts(page, ["Assign Homework", "No homework"],
                      timeout_ms=8000)
    mt.enable_flutter_acc(page)
    print(f"fab -> {mt.find_and_click(page, 'Assign Homework')}")
    mt.wait_for_texts(page, ["Title"], timeout_ms=6000)
    mt.enable_flutter_acc(page)
    dump_inputs(page, "dialog open")

    # Strategy A: current synthetic setter + input event.
    a = mt.fill_by_label_prefix(page, "Title", "STRAT_A_MARKER")
    mt.enable_flutter_acc(page)
    dump_inputs(page, "after strategy A")
    a_seen = mt.has(page, ["STRAT_A_MARKER"])
    print(f"strategy A (synthetic): returned={a} semantics_mirror={a_seen}")
    clear_title(page)

    # Strategy B: click-to-focus + trusted keystrokes + verify.
    b = fill_v2(page, "Title", "STRAT_B_MARKER")
    mt.enable_flutter_acc(page)
    dump_inputs(page, "after strategy B")
    b_seen = mt.has(page, ["STRAT_B_MARKER"])
    print(f"strategy B (focus+type): returned={b} semantics_mirror={b_seen}")

    print(f"VERDICT: {'B' if (b and b_seen) else ('A' if (a and a_seen) else 'NEITHER')}")
    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
