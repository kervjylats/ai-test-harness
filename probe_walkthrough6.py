# probe_walkthrough6.py — timing probe for the Reviews/Homework chip (2026-10-12).
#
# Probe 5: find_and_click('Reviews') returned True but the screen only
# appeared AFTER its 8s wait window (observed in the suite run too),
# then the stale state poisoned the Homework step. This probe samples
# the page every 2s after each chip click to see when (and whether)
# navigation actually lands.
#
#   python -u probe_walkthrough6.py

from playwright.sync_api import sync_playwright
import master_test as mt

BASE = "http://localhost:9090"


def sample(page, label, probes, seconds=16):
    for i in range(1, seconds // 2 + 1):
        page.wait_for_timeout(2000)
        body = " ".join(t.lower() for t in mt.get_all_text(page))
        hits = [p for p in probes if p in body]
        back = "back" in body
        print(f"  t={i * 2:2d}s hits={hits} back={back} url={page.url.split('#')[-1]}")
        if hits:
            return True
    return False


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE)
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)

    mt.signup(page, "Probe Six", "probe.six@robot.test",
              "Movement & Fitness", "Yoga Studio", "Probe Six Yoga")
    mt.go_home(page)

    print("== Reviews chip ==")
    mt.find_and_click(page, "Content")
    mt.wait_for_texts(page, ["Tools"], timeout_ms=8000)
    opened = mt.find_and_click(page, "Reviews")
    print(f"  find_and_click -> {opened}")
    ok = sample(page, "reviews", ["no reviews yet"])
    print(f"  landed within 16s: {ok}")

    print("== back to hub ==")
    mt.go_home(page)
    mt.find_and_click(page, "Content")
    mt.wait_for_texts(page, ["Tools"], timeout_ms=8000)
    print(f"  hub restored: {mt.has(page, ['Tools'])}")

    print("== Homework chip ==")
    opened = mt.find_and_click(page, "Homework")
    print(f"  find_and_click -> {opened}")
    ok = sample(page, "homework", ["assign homework", "no homework"])
    print(f"  landed within 16s: {ok}")

    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
