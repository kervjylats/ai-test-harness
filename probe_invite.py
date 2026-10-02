"""Round 6 probe: invite flow â€” owner invites associate, invitee joins via
landing Code field, then propose-deal both sides. One browser session,
NO page reloads (in-app sign-out only) so static mock stores survive."""
import json
import re
from playwright.sync_api import sync_playwright

import master_test as mt

from server_control import BASE, ensure_server, stop_server

LOG = []


def enable(page):
    mt.enable_flutter_acc(page)


def dump(page, step):
    enable(page)
    page.wait_for_timeout(600)
    texts = page.evaluate("""() => Array.from(document.querySelectorAll('flt-semantics'))
        .map(s => ({t: (s.textContent || '').trim().replace(/\\s+/g, ' '),
                    r: s.getAttribute('role') || '',
                    al: s.getAttribute('aria-label') || ''}))
        .filter(x => x.t)""")
    inputs = page.evaluate("""() => Array.from(document.querySelectorAll('input'))
        .map(i => (i.getAttribute('aria-label') || ''))""")
    LOG.append({"step": step, "url": page.url, "texts": texts, "inputs": inputs})
    print(f"\n=== STEP: {step}  url={page.url}")
    print(f"    inputs: {inputs}")
    for i, x in enumerate(texts):
        print(f"    [{i}] ({x['r'] or '-'}) {x['t'][:150]}")


def click_btn(page, label, wait=2500):
    matched = page.evaluate("""(label) => {
        for (const s of document.querySelectorAll('flt-semantics[role=button]')) {
            const t = (s.textContent || '').trim().replace(/\\s+/g, ' ');
            if (t === label) {
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) { s.click(); return t; }
            }
        }
        return null;
    }""", label)
    page.wait_for_timeout(wait)
    return matched


def click_btn_prefix(page, prefix, wait=2500):
    matched = page.evaluate("""(prefix) => {
        for (const s of document.querySelectorAll('flt-semantics[role=button]')) {
            const t = (s.textContent || '').trim().replace(/\\s+/g, ' ');
            if (t.startsWith(prefix)) {
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) { s.click(); return t; }
            }
        }
        return null;
    }""", prefix)
    page.wait_for_timeout(wait)
    return matched


def fill(page, aria_label, value):
    try:
        page.fill(f'input[aria-label="{aria_label}"]', value, timeout=4000)
        page.wait_for_timeout(300)
        return True
    except Exception:
        return False


def fill_textareas(page, txt, wait=500):
    n = page.evaluate("""(txt) => {
        let c = 0;
        for (const ta of document.querySelectorAll('textarea')) {
            const r = ta.getBoundingClientRect();
            if (r.width > 0) {
                ta.focus(); ta.value = txt;
                ta.dispatchEvent(new Event('input', {bubbles: true}));
                c++;
            }
        }
        return c;
    }""", txt)
    if n:
        page.wait_for_timeout(wait)
    return n


def blob(step_index=-1):
    return " | ".join(x["t"] for x in LOG[step_index]["texts"])


def signup(page, name, email, category, job_prefix, business, tagline="Robot biz"):
    """Landing form -> onboarding -> dashboard. Returns final url."""
    page.evaluate("() => { window.location.hash = '#/get-started'; }")
    page.wait_for_timeout(3500)
    enable(page)
    fill(page, "Your Name", name)
    fill(page, "Email", email)
    fill(page, "Password", "test123")
    click_btn(page, "Get started", wait=5000)
    # onboarding: category -> job -> Continue -> about -> Continue -> Finish
    click_btn(page, category, wait=3500)
    click_btn_prefix(page, job_prefix, wait=3500)
    click_btn(page, "Continue", wait=4000)
    fill(page, "Business Name", business)
    fill(page, "Tagline", tagline)
    fill_textareas(page, "Robot automated business description")
    click_btn(page, "Continue", wait=4000)
    fill_textareas(page, "Robot team member bio")
    hit = click_btn(page, "Finish Setup", wait=6000)
    enable(page)
    print(f"    signup {email}: finish={hit} -> {page.url}")
    return page.url


def real_sign_out(page):
    for attempt in range(2):
        page.keyboard.press("Escape")   # close any open dialog first
        page.wait_for_timeout(1200)
        mt.find_and_click(page, "Settings", timeout=6000)
        page.wait_for_timeout(1500)
        mt.find_and_click(page, "Sign Out", timeout=3000)
        page.wait_for_timeout(3000)
        enable(page)
        url = page.url
        if "#/owner" not in url and "#/associate" not in url and "#/staff" not in url \
           and "#/client" not in url:
            return True
        print(f"    sign-out attempt {attempt} still on {url}")
    return False


def run():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800},
                              permissions=["clipboard-read"])
    page = ctx.new_page()
    page.goto(BASE)
    page.wait_for_timeout(7000)
    enable(page)

    # ---- A: signup the ASSOCIATE-INVITER (owner3, Strength Coach) ----
    url = signup(page, "Robot Strength", "own3@robot.test",
                 "Movement & Fitness", "Strength Coach", "Robot Strength Co")
    print(f"    A done: {url}")
    dump(page, "A_dashboard")

    # ---- B: Network -> Associates -> Invite ----
    mt.find_and_click(page, "Network", timeout=6000)
    page.wait_for_timeout(1500)
    enable(page)
    mt.find_and_click(page, "Associates", timeout=4000)
    page.wait_for_timeout(1500)
    enable(page)
    dump(page, "B_associates")
    inv = mt.find_and_click(page, "Invite", timeout=4000)
    print(f"    invite click: {inv}")
    dump(page, "B_invite_dialog")
    # dialog: 'Invite Associate' -> 'Generate Link' -> QR dialog with
    # 'Copy code' (token goes to CLIPBOARD, never enters semantics).
    gl = click_btn(page, "Generate Link", wait=4000)
    print(f"    generate link: {gl}")
    dump(page, "B_after_actions")
    # Copy code needs a TRUSTED user gesture (JS s.click() is untrusted ->
    # navigator.clipboard.writeText is rejected silently). find_and_click
    # uses page.mouse.click (trusted) for exact text matches.
    copied = mt.find_and_click(page, "Copy code", timeout=3000)
    print(f"    copy click: {copied}")
    token = ""
    for _ in range(6):
        page.wait_for_timeout(500)
        try:
            token = page.evaluate("navigator.clipboard.readText()") or ""
        except Exception as e:
            print(f"    clipboard read failed: {e}")
        if token:
            break
    print(f"    >>> clipboard token: {token!r}")
    codes = re.findall(r"wlp_[A-Za-z0-9]+", token) or ([token] if token else [])
    # Deterministic mock token: _idCounter starts at 10 and increments
    # BEFORE first use -> first Generate Link in a fresh isolate is
    # always wlp_000011 (clipboard is unreliable headless â€” this is the
    # source of truth; clipboard stays as bonus verification).
    if not codes:
        codes = ["wlp_000011"]
        print("    >>> using predicted token wlp_000011 (counter=10+1)")
    click_btn(page, "Done", wait=2000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(1200)
    enable(page)
    dump(page, "B_post_done_associates")
    if not codes:
        found = re.findall(r"wlp_[A-Za-z0-9]+", blob())
        print(f"    >>> wlp on associates screen: {found}")
        codes = found

    # ---- C: sign out -> signup invitee WITH code ----
    if not codes:
        print("    !!! no invite code extracted â€” skipping invitee phases")
        browser.close()
        pw.stop()
        with open("probe_invite_out.json", "w") as f:
            json.dump(LOG, f, indent=1)
        return
    out1 = real_sign_out(page)
    print(f"    C sign out: {out1} -> {page.url}")
    code = codes[0]
    page.evaluate("() => { window.location.hash = '#/get-started'; }")
    page.wait_for_timeout(3000)
    enable(page)
    fill(page, "Code (optional)", code)
    print(f"    filled code {code}")
    enable(page)
    dump(page, "C_code_filled_form")
    fill(page, "Your Name", "Robot Associate")
    fill(page, "Email", "assoc@robot.test")
    fill(page, "Password", "test123")
    # Filling Code swaps the landing form into 'Activate your code' mode
    # with an 'Activate' button (probed).
    hit = click_btn(page, "Activate", wait=6000) or click_btn(page, "Get started", wait=6000)
    print(f"    invitee submit: {hit}")
    dump(page, "C_invitee_after_submit")
    # invitee may land on a dashboard, an onboarding, or bounce with an error
    for hop in range(8):
        b = blob().lower()
        url = page.url
        if any(f"#{p}" in url for p in ("/owner", "/associate", "/staff", "/client")):
            print(f"    invitee dashboard reached: {url}")
            break
        if "invalid" in b or "not found" in b or "expired" in b or "error" in b:
            print(f"    >>> invitee error visible: {[t['t'] for t in LOG[-1]['texts'] if 'nvalid' in t['t'] or 'rror' in t['t']][:3]}")
            break
        acted = (click_btn(page, "Continue", wait=3000) or click_btn(page, "Next", wait=3000)
                 or click_btn(page, "Finish Setup", wait=3000))
        print(f"    C hop {hop}: {acted}")
        if not acted:
            break
        dump(page, f"C_hop{hop}")
    dump(page, "C_final")

    # ---- D: invitee Network -> Owner card? ----
    mt.find_and_click(page, "Network", timeout=6000)
    page.wait_for_timeout(1500)
    enable(page)
    dump(page, "D_invitee_network")

    # ---- E: sign out -> owner3 typed login -> propose deal ----
    out_e = real_sign_out(page)
    print(f"    E sign out: {out_e} -> {page.url}")
    mt.typed_login(page, "own3@robot.test")
    page.wait_for_timeout(2000)
    enable(page)
    dump(page, "E_owner_relogin")
    mt.find_and_click(page, "Network", timeout=6000)
    page.wait_for_timeout(1500)
    enable(page)
    mt.find_and_click(page, "Associates", timeout=4000)
    page.wait_for_timeout(1500)
    enable(page)
    dump(page, "E_associates")
    mt.click_prefix(page, "Propose a deal")
    page.wait_for_timeout(2500)
    enable(page)
    dump(page, "E_propose_screen")
    mt.click_exact(page, "Select associate")
    page.wait_for_timeout(2000)
    enable(page)
    dump(page, "E_dropdown")
    # pick first option that looks like a person (prefix click on 'Robot' or any non-placeholder)
    picked = (click_btn_prefix(page, "Robot Associate", wait=2000)
              or mt.click_prefix(page, "Robot"))
    print(f"    picked option: {picked}")
    dump(page, "E_picked")
    sent = mt.click_exact(page, "Send Proposal")
    page.wait_for_timeout(3000)
    enable(page)
    dump(page, "E_after_send")

    # ---- F: invitee sees proposal -> Accept ----
    out_f = real_sign_out(page)
    print(f"    F sign out: {out_f} -> {page.url}")
    mt.typed_login(page, "assoc@robot.test")
    page.wait_for_timeout(2500)
    enable(page)
    dump(page, "F_assoc_relogin")
    # proposals may live on dashboard, agreements, or network
    for route_lbl in ["Network", "Agreements", "Home"]:
        mt.find_and_click(page, route_lbl, timeout=5000)
        page.wait_for_timeout(2000)
        enable(page)
        dump(page, f"F_{route_lbl}")
        if mt.has_text(page, ["Accept", "Decline", "Proposal", "Propose"]):
            print(f"    >>> proposal markers on {route_lbl}")
            break
    acc = mt.click_exact(page, "Accept")
    print(f"    accept click: {acc}")
    page.wait_for_timeout(3000)
    enable(page)
    dump(page, "F_after_accept")

    browser.close()
    pw.stop()
    with open("probe_invite_out.json", "w") as f:
        json.dump(LOG, f, indent=1)
    print(f"\nWROTE probe_invite_out.json ({len(LOG)} steps)")


if __name__ == "__main__":
    if ensure_server():
        try:
            run()
        finally:
            stop_server()
