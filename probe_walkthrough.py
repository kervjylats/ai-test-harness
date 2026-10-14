# probe_walkthrough.py — Phase D walkthrough mechanics probe (2026-10-12).
#
# Validates, in isolation, the exact click path the suite's
# PER-JOB MODULE WALKTHROUGH uses on the owner Activity hub:
# find_and_click on each Tools tile + the Homework chip, then
# go_home + real_sign_out. Run while the server on :9090 is up.
#
#   python -u probe_walkthrough.py

from playwright.sync_api import sync_playwright
import master_test as mt

BASE = "http://localhost:9090"


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE)
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)

    email = "probe.walk@robot.test"
    url = mt.signup(page, "Probe Owner", email, "Movement & Fitness",
                    "Yoga Studio", "Probe Yoga Co")
    print(f"signup -> {url}")

    mt.go_home(page)
    print(f"home -> {page.url}")

    hub = mt.find_and_click(page, "Content")
    page.wait_for_timeout(1500)
    mt.enable_flutter_acc(page)
    print(f"hub opened={hub} tools={mt.has(page, ['Tools'])}")

    tiles = [("Schedule", "schedule"), ("Catalog", "catalog"),
             ("Media", "media"), ("Reviews", "reviews")]
    for tile, path in tiles:
        opened = mt.find_and_click(page, tile)
        page.wait_for_timeout(1000)
        mt.enable_flutter_acc(page)
        body = " ".join(mt.get_all_text(page)).lower()
        print(f"tile {tile}: opened={opened} url={page.url} "
              f"path_ok={path in page.url.lower()} err={'could not load' in body}")
        mt.go_home(page)
        mt.find_and_click(page, "Content")
        page.wait_for_timeout(1200)
        mt.enable_flutter_acc(page)

    hw = mt.find_and_click(page, "Homework")
    page.wait_for_timeout(2000)
    mt.enable_flutter_acc(page)
    hw_texts = mt.get_all_text(page)
    print(f"homework: opened={hw} url={page.url}")
    print(f"  texts: {hw_texts[:10]}")
    print(f"  stub={'coming soon' in ' '.join(hw_texts).lower()}")

    back_home = mt.go_home(page)
    print(f"back home -> {page.url} (go_home={back_home})")

    so = mt.real_sign_out(page)
    print(f"sign out -> signed_out={so} url={page.url} "
          f"login_form={'Email' in mt.input_labels(page)}")

    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
