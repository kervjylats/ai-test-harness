# probe_walkthrough10.py — decisive Title-fill test with a REAL client and
# REAL submit (2026-10-14). Probe9 proved both strategies set the DOM value
# but page-text can't observe input.value, so only submit discriminates.
#
# Flow: owner signup -> invite client -> client joins -> owner re-login ->
# homework dialog -> Strategy A fill + pick + Assign -> listed?
# -> (if still open) Strategy B fill + Assign -> listed?
#
#   python -u probe_walkthrough10.py
from playwright.sync_api import sync_playwright
import master_test as mt


def open_assign_dialog(page):
    mt.go_home(page)
    mt.find_and_click(page, "Content")
    mt.wait_for_texts(page, ["Tools"], timeout_ms=8000)
    mt.enable_flutter_acc(page)
    mt.find_and_click(page, "Homework")
    mt.wait_for_texts(page, ["Assign Homework", "No homework"],
                      timeout_ms=8000)
    mt.enable_flutter_acc(page)
    if not mt.find_and_click(page, "Assign Homework"):
        return False
    mt.wait_for_texts(page, ["Title"], timeout_ms=6000)
    mt.enable_flutter_acc(page)
    return True


def pick_client(page):
    if not mt.find_and_click(page, "Client"):
        return False
    page.wait_for_timeout(1000)
    return mt.find_and_click(page, "Robot Client")


def try_submit(page, marker):
    mt.click_btn(page, "Assign")
    texts = mt.wait_for_texts(page, [marker], timeout_ms=8000)
    mt.enable_flutter_acc(page)
    listed = mt.has_all(page, [marker, "Robot Client"])
    print(f"    marker={marker} listed={listed}")
    return listed


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto("http://localhost:9090")
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)

    mt.signup(page, "Probe Ten", "probe.ten@robot.test",
              "Movement & Fitness", "Strength Coach", "Probe Ten Strength")
    mt.go_home(page)
    mt.find_and_click(page, "Network")
    page.wait_for_timeout(1500)
    mt.enable_flutter_acc(page)
    mt.find_and_click(page, "Associates")
    page.wait_for_timeout(1500)
    mt.enable_flutter_acc(page)
    token_assoc = ""
    if mt.find_and_click(page, "Invite"):
        token_assoc = mt.generate_invite_token(page, "wlp_000011")
    print(f"assoc token: {token_assoc}")
    mt.real_sign_out(page)
    aurl = mt.invitee_signup(page, token_assoc, "Robot Associate",
                             "probe.assoc@robot.test")
    print(f"assoc joined: {'/partner' in aurl}")
    # The ASSOCIATE invites the client (suite Step 7 pattern).
    mt.find_and_click(page, "Network")
    page.wait_for_timeout(1500)
    mt.enable_flutter_acc(page)
    token_client = ""
    if mt.find_and_click(page, "Invite"):
        token_client = mt.generate_invite_token(page, "wlp_000012")
    print(f"client token: {token_client}")
    mt.real_sign_out(page)
    curl = mt.invitee_signup(page, token_client, "Robot Client",
                             "probe.client@robot.test")
    print(f"client joined: {'/client' in curl}")
    mt.real_sign_out(page)
    print(f"owner relogin: {mt.login(page, 'probe.ten@robot.test')}")

    print(f"dialog open: {open_assign_dialog(page)}")
    print(f"client picked: {pick_client(page)}")
    page.wait_for_timeout(1000)

    print("Strategy A (synthetic setter + input event):")
    fa = mt.fill_by_label_prefix(page, "Title", "WEEK_A_ITEM")
    print(f"    fill returned={fa}")
    a_ok = try_submit(page, "WEEK_A_ITEM")

    b_ok = False
    if not a_ok:
        print("Strategy B (click-to-focus + trusted keystrokes):")
        idx = page.evaluate("""() => Array.from(
            document.querySelectorAll('input, textarea'))
            .findIndex(i => (i.getAttribute('aria-label') || '')
            .startsWith('Title'))""")
        el = page.locator("input, textarea").nth(idx)
        el.click()
        page.wait_for_timeout(400)
        page.keyboard.press("Control+A")
        page.keyboard.type("WEEK_B_ITEM", delay=15)
        page.wait_for_timeout(400)
        fb = (el.input_value() == "WEEK_B_ITEM")
        print(f"    fill verified={fb}")
        b_ok = try_submit(page, "WEEK_B_ITEM")

    print(f"VERDICT: {'A' if a_ok else ('B' if b_ok else 'NEITHER')}")
    mt.screenshot(page, "probe10_final")
    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
