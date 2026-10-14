# probe_walkthrough8.py — replicate the suite E2E step-for-step with state
# dumps (2026-10-12). The 70/72 run's E2E ended on the Reviews screen
# though nothing in the E2E clicks Reviews; this probe prints URL + text
# head after EVERY action to find the divergence.
#
#   python -u probe_walkthrough8.py

from playwright.sync_api import sync_playwright
import master_test as mt

BASE = "http://localhost:9090"


def state(page, tag):
    print(f"[{tag}] url={page.url.split('#')[-1]}")
    print(f"    texts: {mt.get_all_text(page)[:5]}")


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE)
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)

    mt.signup(page, "Probe Eight", "probe.eight@robot.test",
              "Movement & Fitness", "Yoga Studio", "Probe Eight Yoga")

    # Mirror the E2E prologue: go_home, Content tab, Homework chip.
    print(f"go_home -> {mt.go_home(page)}")
    state(page, "dashboard")
    print(f"content -> {mt.find_and_click(page, 'Content')}")
    mt.wait_for_texts(page, ["Tools"], timeout_ms=8000)
    state(page, "hub")
    hw = mt.find_and_click(page, "Homework")
    print(f"homework chip -> {hw}")
    mt.wait_for_texts(page, ["Assign Homework"], timeout_ms=8000)
    mt.enable_flutter_acc(page)
    state(page, "homework screen?")

    fab = mt.find_and_click(page, "Assign Homework")
    print(f"fab -> {fab}")
    mt.wait_for_texts(page, ["Title"], timeout_ms=6000)
    mt.enable_flutter_acc(page)
    state(page, "assign dialog?")

    dd = mt.find_and_click(page, "Client")
    print(f"dropdown open -> {dd}")
    state(page, "dropdown open?")

    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
