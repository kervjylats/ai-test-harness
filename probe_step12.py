"""Probe: replay suite Steps 10-12 only, with timed diagnostics at Step 12.

Question: own4's Received Requests check failed (received=False) after a
successful Step 11 send. Is the request genuinely absent (data), or does the
section simply appear later than the suite's single check (timing)?

Prints, at 0/5/10/15s after landing on own4's marketplace:
  - presence of "Received Requests" and "Robot Yoga Co"
  - a text sample of the page
"""
import sys, time

# master_test wraps sys.stdout itself (line-buffered) — wrapping again here
# would let GC close the shared buffer out from under it.
import master_test as mt
from server_control import ensure_server, stop_server
from playwright.sync_api import sync_playwright


def probe(page):
    # ---- signup both owners (fresh mock state) ----
    mt.signup(page, "Robot Yoga", "own1@robot.test", "Movement & Fitness",
              "Yoga Studio", "Robot Yoga Co")
    mt.wait_for_texts(page, ["Revenue"], timeout_ms=20000)
    print(f"signup own1 done url={page.url}")
    mt.real_sign_out(page)

    mt.signup(page, "Robot Pilates", "own4@robot.test", "Movement & Fitness",
              "Pilates Studio", "Robot Pilates Co")
    print(f"signup own4 done url={page.url}")
    mt.real_sign_out(page)

    # ---- own4 availability ----
    mt.login(page, "own4@robot.test")
    mt.go_marketplace(page)
    mt.toggle_slot(page, "Discoverable")
    mt.toggle_slot(page, "Yoga Studio")
    own4_ready = all(
        (mt.switch_state(page, t) or {}).get("checked") == "true"
        for t in ("Discoverable", "Yoga Studio"))
    print(f"own4_ready={own4_ready}")
    mt.real_sign_out(page)

    # ---- own1 availability + discovery ----
    mt.login(page, "own1@robot.test")
    mt.go_marketplace(page)
    mt.toggle_slot(page, "Discoverable")
    mt.toggle_slot(page, "Pilates Studio")
    mt.scroll_down(page, steps=6)
    has_tile = mt.has(page, ["Robot Pilates Co"])
    print(f"step10 tile={has_tile}")

    sent, ev11 = False, []
    if has_tile:
        mt.click_contains(page, "Robot Pilates Co", wait=3000)
        mt.enable_flutter_acc(page)
        if mt.has(page, ["Open Collab Slots"]):
            (mt.click_exact(page, "Yoga Studio", wait=1500)
             or mt.click_contains(page, "Yoga Studio", wait=1200))
            mt.enable_flutter_acc(page)
        hit = mt.click_exact(page, "Send Associate Request", wait=6000)
        page.wait_for_timeout(2500)
        mt.enable_flutter_acc(page)
        ev11.append(f"send_btn={hit}")
        if mt.has(page, ["Confirm Request"]):
            mt.fill_first_input(page, "Robot Yoga would love to collab.")
            mt.click_exact(page, "Confirm Request", wait=6000)
            page.wait_for_timeout(3500)
            mt.enable_flutter_acc(page)
            sent = mt.has(page, ["Request sent"])
    page.keyboard.press("Escape")
    page.wait_for_timeout(1500)
    mt.enable_flutter_acc(page)
    pending = mt.has(page, ["Pending"])
    sent = sent or pending
    print(f"step11 {','.join(ev11)} confirmed={sent} badge={pending}")
    if not sent:
        print("PROBE ABORT: request never sent")
        return

    # ---- Step 12: replicate the suite's EXACT check, then diagnose ----
    mt.real_sign_out(page)
    mt.login(page, "own4@robot.test")
    print(f"after login url={page.url} "
          f"own4_brand={mt.has(page, ['Robot Pilates Co'])}")
    mt.go_marketplace(page)
    print(f"marketplace url={page.url}")

    # 1) exact suite sequence: scroll_down(6) then has_all
    mt.scroll_down(page, steps=6)
    recv = mt.has(page, ["Received Requests"])
    name = mt.has(page, ["Robot Yoga Co"])
    print(f"SUITE-EXACT scroll_down(6): has_all="
          f"{mt.has_all(page, ['Received Requests', 'Robot Yoga Co'])} "
          f"(recv={recv} tile={name})")
    print(f"    text sample: {' | '.join(mt.get_all_text(page)[:40])[:500]}")
    mt.screenshot(page, "probe12_scrolldown6")

    # 2) recover: scroll back up to the top sections
    mt.scroll_up(page, steps=8)
    recv2 = mt.has(page, ["Received Requests"])
    name2 = mt.has(page, ["Robot Yoga Co"])
    print(f"AFTER scroll_up(8): has_all="
          f"{mt.has_all(page, ['Received Requests', 'Robot Yoga Co'])} "
          f"(recv={recv2} tile={name2})")
    print(f"    text sample: {' | '.join(mt.get_all_text(page)[:40])[:500]}")
    mt.screenshot(page, "probe12_scrollup")

    if recv2 and name2:
        hit = mt.click_exact(page, "Accept", wait=6000)
        page.wait_for_timeout(3000)
        mt.enable_flutter_acc(page)
        print(f"accept_clicked={hit} "
              f"split_dialog={mt.has(page, ['Set your commission split'])}")
        if hit:
            mt.click_exact(page, "Confirm Collab", wait=6000)
            page.wait_for_timeout(3700)
            mt.enable_flutter_acc(page)
            cleared = not mt.has(page, ["Accept", "Decline", "Confirm Collab"])
            print(f"confirm_cleared={cleared}")
    else:
        print("SECTION NEVER PRESENT - data problem, not scroll")


def main():
    if not ensure_server():
        print("server failed to start")
        return 1
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(
            headless=True,
            args=["--enable-unsafe-swiftshader", "--disable-dev-shm-usage"])
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        page.goto(mt.BASE)
        page.wait_for_timeout(6000)
        mt.enable_flutter_acc(page)
        mt.wait_for_texts(page, ["run your own", "wellness business",
                                 "Get started"], timeout_ms=60000)
        probe(page)
        browser.close()
    finally:
        pw.stop()
        stop_server()
    return 0


if __name__ == "__main__":
    sys.exit(main())
