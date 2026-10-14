# probe_walkthrough5.py — validate the FIXED walkthrough assertions (2026-10-12).
#
# Replicates the exact per-tile logic now in master_test.py's
# PER-JOB MODULE WALKTHROUGH: find_and_click -> wait_for_texts(probe)
# with lowercase, job-agnostic substring probes (yoga maps Catalog ->
# 'Shop', Media -> 'Content'), then homework chip -> coach view, then
# sign-out. Run while the server on :9090 is up.
#
#   python -u probe_walkthrough5.py

from playwright.sync_api import sync_playwright
import master_test as mt

BASE = "http://localhost:9090"

OWNER_TOOLS = [("Schedule", "add slot"), ("Catalog", "is empty"),
               ("Media", "items yet"), ("Reviews", "no reviews yet")]


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE)
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)

    url = mt.signup(page, "Probe Five", "probe.five@robot.test",
                    "Movement & Fitness", "Yoga Studio", "Probe Five Yoga")
    print(f"signup -> {url}")

    mt.go_home(page)
    hub_clicked = mt.find_and_click(page, "Content")
    mt.wait_for_texts(page, ["Tools"], timeout_ms=8000)
    print(f"hub: clicked={hub_clicked} tools={mt.has(page, ['Tools'])}")

    fails = 0
    for tile, probe in OWNER_TOOLS:
        opened = mt.find_and_click(page, tile)
        texts = mt.wait_for_texts(page, [probe], timeout_ms=8000)
        body = " ".join(t.lower() for t in texts)
        ok = opened and probe in body and "could not load" not in body
        fails += 0 if ok else 1
        print(f"tile {tile}: opened={opened} probe={probe!r} ok={ok}")
        if not ok:
            print(f"   body head: {body[:160]}")
        mt.go_home(page)
        mt.find_and_click(page, "Content")
        mt.wait_for_texts(page, ["Tools"], timeout_ms=8000)
        mt.enable_flutter_acc(page)

    hw_open = mt.find_and_click(page, "Homework")
    hw_texts = mt.wait_for_texts(
        page, ["assign homework", "no homework", "delete homework"],
        timeout_ms=8000)
    hw_body = " ".join(t.lower() for t in hw_texts)
    coach_ok = any(k in hw_body for k in
                   ("assign homework", "no homework", "delete homework"))
    stub = "coming soon" in hw_body
    ok = hw_open and coach_ok and not stub
    fails += 0 if ok else 1
    print(f"homework: opened={hw_open} coach_ok={coach_ok} stub={stub} ok={ok}")
    if not ok:
        print(f"   body head: {hw_body[:160]}")

    mt.go_home(page)
    so = mt.real_sign_out(page)
    print(f"sign out -> signed_out={so} url={page.url}")
    print(f"RESULT: {'PASS' if fails == 0 else f'{fails} FAIL'}")

    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
