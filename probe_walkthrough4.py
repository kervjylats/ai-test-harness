# probe_walkthrough4.py — text-accurate check of the suite's exact click path.
#
# Probe 3 never left the dashboard (role filter bug). This one uses the
# suite's own find_and_click/go_home helpers verbatim and prints the
# screen texts after every step, to see whether el.click() navigation
# actually changes the visible screen even when the URL does not.

from playwright.sync_api import sync_playwright
import master_test as mt

BASE = "http://localhost:9090"


def state(page, tag):
    print(f"[{tag}] url={page.url}")
    for t in mt.get_all_text(page)[:7]:
        print(f"    | {t[:90]}")


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE)
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)

    url = mt.signup(page, "Probe Four", "probe.four@robot.test",
                    "Movement & Fitness", "Yoga Studio", "Probe Four Yoga")
    print(f"signup -> {url}")

    mt.go_home(page)
    print(f"open hub: {mt.find_and_click(page, 'Content')}")
    page.wait_for_timeout(1500)
    mt.enable_flutter_acc(page)
    state(page, "hub")

    print(f"click Schedule: {mt.find_and_click(page, 'Schedule')}")
    state(page, "after Schedule")

    mt.go_home(page)
    print(f"re-open hub: {mt.find_and_click(page, 'Content')}")
    page.wait_for_timeout(1500)
    mt.enable_flutter_acc(page)
    print(f"click Homework: {mt.find_and_click(page, 'Homework')}")
    state(page, "after Homework")

    so = mt.real_sign_out(page)
    print(f"sign out -> signed_out={so} url={page.url}")

    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
