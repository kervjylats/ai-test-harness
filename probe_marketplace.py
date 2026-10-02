"""Round 6 probe v3: two FRESH owners discover/link via the Marketplace,
then run the mock money loop end-to-end (Round 6 payments).
Session: own1 (Yoga) + own4 (Pilates), in-app sign-out only, no reloads.

Known mechanics (from source):
- Availability card = one semantics group, labels only in aria-label.
- switches DOM order == title order: [Discoverable, ...categories minus own].
- own4: Discoverable + open 'Yoga Studio' slot (chip own1 will pick).
- own1: Discoverable + open 'Pilates Studio' slot -> discovers own4.
- tile tap -> bottom sheet: chip -> 'Send Associate Request' -> message
  field -> 'Confirm Request'.
- receiver: marketplace Received Requests -> Accept -> 'Confirm Collab'.
- sender side gets a PROPOSED agreement; dashboard pending chip opens
  AgreementDetailScreen -> Approve.
- money loop: detail 'Record payment' -> 'Confirm Payment' dialog ->
  payment txn + pending commission in owner Revenue -> 'Mark Paid' ->
  payout txn -> payee (own4) sees it in their own ledger.
  Split on own1's copy = owner 80 / partner 20 => $24 on a $120 charge.
"""
import json
from playwright.sync_api import sync_playwright

import master_test as mt

# Round 7: shared on-demand server (was a private copy hardcoded to 8080 -
# the LocalAI hub's `big` slot port). Same start-if-needed semantics, new
# port 9090, single source of truth in server_control.py.
from server_control import BASE, PORT, ensure_server, stop_server

LOG = []
CONSOLE_LOG = []

import time


def enable(page):
    mt.enable_flutter_acc(page)


def print_console(tag, last=25):
    keys = ("failed", "Mutual", "createMutual", "Uncaught", "exception",
            "Could not", "error", "pageerror")
    hits = [l for l in CONSOLE_LOG
            if any(k.lower() in l.lower() for k in keys)]
    print(f"    >>> console[{tag}] {len(hits)}/{len(CONSOLE_LOG)} interesting:")
    for h in hits[-last:]:
        print(f"        {h[:300]}")


def dump(page, step):
    enable(page)
    page.wait_for_timeout(600)
    texts = page.evaluate("""() => Array.from(document.querySelectorAll('flt-semantics'))
        .map(s => ({t: (s.textContent || '').trim().replace(/\\s+/g, ' '),
                    a: (s.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' '),
                    r: s.getAttribute('role') || ''}))
        .filter(x => x.t || x.a)""")
    inputs = page.evaluate("""() => Array.from(document.querySelectorAll('input, textarea'))
        .map(i => (i.getAttribute('aria-label') || i.getAttribute('placeholder') || '?'))""")
    LOG.append({"step": step, "url": page.url, "texts": texts, "inputs": inputs})
    print(f"\n=== STEP: {step}  url={page.url}")
    print(f"    inputs: {inputs}")
    for i, x in enumerate(texts):
        body = x["t"] or x["a"]
        print(f"    [{i}] ({x['r'] or '-'}) {body[:150]}")


def card_titles(page):
    return page.evaluate("""() => {
        for (const s of document.querySelectorAll('flt-semantics')) {
            const a = s.getAttribute('aria-label') || '';
            if (a.includes('My Availability')) {
                const lines = a.split('\\n').map(x => x.trim()).filter(Boolean);
                const titles = ['Discoverable'];
                const i = lines.indexOf('Collab Slots');
                if (i >= 0) {
                    const rest = lines.slice(i + 1);
                    for (let j = 0; j + 1 < rest.length + 1; j += 2) titles.push(rest[j]);
                }
                return titles;
            }
        }
        return [];
    }""")


def switch_states(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('flt-semantics[role=switch]'))
        .map(s => s.getAttribute('aria-checked') || '')""")


def toggle_slot(page, title, wait=3000):
    titles = card_titles(page)
    if title not in titles:
        print(f"    toggle {title!r}: NOT IN titles {titles}")
        return None
    idx = titles.index(title)
    before = switch_states(page)
    page.evaluate("""(i) => {
        const sw = document.querySelectorAll('flt-semantics[role=switch]');
        if (sw[i]) sw[i].click();
    }""", idx)
    page.wait_for_timeout(wait)
    after = switch_states(page)
    ok = idx < len(after) and after[idx] == "true" and (
        idx >= len(before) or before[idx] != "true")
    print(f"    toggle {title!r} idx={idx}: {before[idx] if idx < len(before) else '?'}"
          f" -> {after[idx] if idx < len(after) else '?'} ({'OK' if ok else 'CHECK'})")
    return ok


def page_text(page):
    return page.evaluate("""() => {
        let t = document.body.innerText || '';
        for (const s of document.querySelectorAll('flt-semantics')) {
            t += '\\n' + (s.textContent || '') + '\\n' + (s.getAttribute('aria-label') || '');
        }
        return t.toLowerCase();
    }""")


def has(page, needles):
    txt = page_text(page)
    return any(n.lower() in txt for n in needles)


def has_all(page, needles):
    txt = page_text(page)
    return all(n.lower() in txt for n in needles)


def has_after_scroll(page, needles, rounds=5, steps=2):
    """Scroll down (up to `rounds` times) until every needle is on-page."""
    for _ in range(rounds):
        if has_all(page, needles):
            return True
        mt.scroll_down(page, steps=steps)
        page.wait_for_timeout(600)
        enable(page)
    return has_all(page, needles)


def go_home(page, tries=3):
    """Land on the owner dashboard for sure.

    - Bottom-nav Home tab: works on shell screens (dashboard/marketplace/
      notifications â€” marketplace has its own hash too).
    - hash '#/owner': no-op when already '#/owner', and it NEVER pops a
      pushed route (AgreementDetail doesn't even change the URL).
    - Back button: the only way out of pushed routes like AgreementDetail
      (URL stays '#/owner' while a route sits on top of the shell)."""
    for _ in range(tries):
        if has(page, ["Agreements"]):
            return True
        mt.find_and_click(page, "Home", timeout=4000)
        page.wait_for_timeout(2000)
        enable(page)
        if has(page, ["Agreements"]):
            return True
        page.evaluate("() => { window.location.hash = '#/owner'; }")
        page.wait_for_timeout(2000)
        enable(page)
        if has(page, ["Agreements"]):
            return True
        if has(page, ["Back"]):
            mt.find_and_click(page, "Back", timeout=4000)
            page.wait_for_timeout(2000)
            enable(page)
    if has(page, ["Agreements"]):
        return True
    # Last resort: a full reload resets the pushed-route stack (mock stores
    # are static in-memory â€” they survive; session/prefs come from
    # localStorage). The dashboard always carries the 'Agreements' card.
    page.goto(f"{BASE}/#/owner")
    page.wait_for_timeout(6000)
    enable(page)
    return has(page, ["Agreements"])


def click_contains(page, needle, wait=2500):
    matched = page.evaluate("""(needle) => {
        const hits = [];
        for (const s of document.querySelectorAll('flt-semantics')) {
            const t = ((s.textContent || '') + ' ' + (s.getAttribute('aria-label') || ''))
                .trim().replace(/\\s+/g, ' ');
            if (t.includes(needle)) {
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) hits.push(s);
            }
        }
        if (!hits.length) return null;
        const el = hits[hits.length - 1];
        el.click();
        return ((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || ''))
            .trim().replace(/\\s+/g, ' ');
    }""", needle)
    page.wait_for_timeout(wait)
    return matched


def click(page, label, wait=2500):
    r = mt.click_exact(page, label, wait=wait)
    page.wait_for_timeout(wait)
    return r


def fill_first_input(page, value):
    n = page.evaluate("""(v) => {
        let c = 0;
        for (const i of document.querySelectorAll('input, textarea')) {
            const r = i.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                const proto = i.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(i, v);
                i.dispatchEvent(new Event('input', {bubbles: true}));
                c++;
                break;
            }
        }
        return c;
    }""", value)
    page.wait_for_timeout(400)
    return n


def wait_for_input(page, aria, timeout_ms=8000):
    waited = 0
    while waited < timeout_ms:
        try:
            el = page.query_selector(f'input[aria-label="{aria}"]')
            if el and el.is_visible():
                return True
        except Exception:
            pass
        page.wait_for_timeout(400)
        waited += 400
    return False


def type_into(page, aria, value, tries=4):
    sel = f'input[aria-label="{aria}"]'
    for _ in range(tries):
        try:
            el = page.wait_for_selector(sel, state="attached", timeout=4000)
            el.click()
            page.keyboard.press("Control+A")
            page.keyboard.type(value, delay=25)
            page.wait_for_timeout(250)
            if el.input_value() == value:
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def fill_by_label_prefix(page, prefix, value, tries=4):
    """Fill an input whose aria-label STARTS with `prefix` â€” Flutter
    merges labelText+hint into one label ('Amount\\ne.g. 120.00'), so an
    exact aria-label selector would never match."""
    for _ in range(tries):
        ok = page.evaluate("""({prefix, value}) => {
            for (const i of document.querySelectorAll('input, textarea')) {
                const al = (i.getAttribute('aria-label') || '');
                if (!al.startsWith(prefix)) continue;
                const r = i.getBoundingClientRect();
                if (!(r.width > 0 && r.height > 0)) continue;
                const proto = i.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(i, value);
                i.dispatchEvent(new Event('input', {bubbles: true}));
                return true;
            }
            return false;
        }""", {"prefix": prefix, "value": value})
        if ok:
            page.wait_for_timeout(300)
            return True
        page.wait_for_timeout(500)
    return False


def input_labels(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('input, textarea'))
        .map(i => i.getAttribute('aria-label') || '')""")


def signup(page, name, email, category, job_prefix, business, tagline="Robot biz"):
    page.evaluate("() => { window.location.hash = '#/get-started'; }")
    page.wait_for_timeout(3500)
    enable(page)
    for attempt in range(3):
        type_into(page, "Your Name", name)
        type_into(page, "Email", email)
        type_into(page, "Password", "test123")
        click_btn(page, "Get started", wait=5000)
        if "#/onboarding" in page.url or has(page, ["Choose", "category", "Movement"]):
            break
        print(f"    submit attempt {attempt}: still on {page.url},"
              f" validation={has(page, ['is required'])}")
    if "#/onboarding" not in page.url:
        dump(page, "S_onboarding_never_reached")
    for attempt in range(3):
        if wait_for_input(page, "Business Name", 1200) or has(page, ["Finish Setup"]) or has(page, ["About you"]):
            break
        if not has(page, [job_prefix]):
            hit = click_btn(page, category, wait=3500)
            print(f"    signup attempt {attempt}: category={hit!r}")
            if hit is None and attempt == 0:
                dump(page, "S_category_failed")
        hit = click_btn_prefix(page, job_prefix, wait=3500)
        print(f"    signup attempt {attempt}: job={hit!r}")
        click_btn(page, "Continue", wait=4000)
        if wait_for_input(page, "Business Name"):
            break
        print(f"    signup attempt {attempt}: Business Name missing, retrying")
    page.fill('input[aria-label="Business Name"]', business, timeout=8000)
    try:
        page.fill('input[aria-label="Tagline"]', tagline, timeout=4000)
    except Exception:
        pass
    fill_textareas(page, "Robot automated business description")
    click_btn(page, "Continue", wait=4000)
    fill_textareas(page, "Robot team member bio")
    hit = None
    for _ in range(3):
        hit = click_btn(page, "Finish Setup", wait=6000)
        if hit or "#/owner" in page.url:
            break
        click_btn(page, "Continue", wait=3000)
        fill_textareas(page, "Robot team member bio")
    enable(page)
    print(f"    signup {email}: finish={hit} -> {page.url}")
    return page.url


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


def real_sign_out(page):
    for attempt in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
        if "#" in page.url:
            h = page.url.split("#", 1)[1].strip("/")
            parts = [p for p in h.split("/") if p]
            if len(parts) > 1:
                page.evaluate(f"() => {{ window.location.hash = '#/{parts[0]}'; }}")
                page.wait_for_timeout(2500)
                enable(page)
        mt.find_and_click(page, "Settings", timeout=6000)
        page.wait_for_timeout(1500)
        mt.find_and_click(page, "Sign Out", timeout=3000)
        page.wait_for_timeout(3000)
        enable(page)
        url = page.url
        if "/owner" not in url and "/partner" not in url:
            return True
        print(f"    sign-out attempt {attempt} still on {url}")
    return False


def login(page, email):
    mt.typed_login(page, email)
    page.wait_for_timeout(3000)
    enable(page)


def go_marketplace(page):
    page.evaluate("() => { window.location.hash = '#/owner/marketplace'; }")
    page.wait_for_timeout(5000)
    enable(page)


def run():
    if not ensure_server():
        print(f"FATAL: could not start http server on :{PORT}")
        return
    pw = sync_playwright().start()
    last = None
    for attempt in range(3):
        try:
            run_once(pw)
            pw.stop()
            return
        except Exception as e:
            last = e
            print(f"RETRY {attempt}: {e!r}")
            print_console(f"attempt{attempt}-failed", last=40)
            time.sleep(3)
            ensure_server()
    pw.stop()
    raise last


def run_once(pw):
    browser = pw.chromium.launch(headless=True, args=[
        "--enable-unsafe-swiftshader", "--disable-dev-shm-usage"])
    try:
        run_journey(browser)
    finally:
        try:
            browser.close()
        except Exception:
            pass


def run_journey(browser):
    LOG.clear()
    CONSOLE_LOG.clear()
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.on("console", lambda m: CONSOLE_LOG.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: CONSOLE_LOG.append(f"[pageerror] {e}"))
    page.goto(BASE)
    page.wait_for_timeout(7000)
    enable(page)

    # A: own1 = Yoga owner
    signup(page, "Robot Yoga", "own1@robot.test", "Movement & Fitness",
           "Yoga Studio", "Robot Yoga Co")
    dump(page, "A_own1_dashboard")

    # B: own4 = Pilates owner
    assert real_sign_out(page), "sign-out before own4 failed"
    signup(page, "Robot Pilates", "own4@robot.test", "Movement & Fitness",
           "Pilates Studio", "Robot Pilates Co")
    dump(page, "B_own4_dashboard")

    # C: own4 availability: Discoverable + open Yoga slot (chip own1 picks)
    go_marketplace(page)
    dump(page, "C_own4_card")
    toggle_slot(page, "Discoverable")
    toggle_slot(page, "Yoga Studio")
    dump(page, "C_own4_after")
    own4_ready = switch_states(page)[:2] == ["true", "true"]
    print(f"    >>> own4 ready (disc+slot): {own4_ready}")

    # D: own1 browses -> Pilates slot -> discovers own4 -> request
    assert real_sign_out(page), "sign-out before own1 login failed"
    login(page, "own1@robot.test")
    go_marketplace(page)
    dump(page, "D_own1_card")
    toggle_slot(page, "Discoverable")
    toggle_slot(page, "Pilates Studio")
    dump(page, "D_own1_slots")
    mt.scroll_down(page, steps=6)
    dump(page, "D_discovery")
    has_tile = has(page, ["Robot Pilates Co"])
    print(f"    >>> discovery shows own4: {has_tile}")
    sent = False
    if has_tile:
        click_contains(page, "Robot Pilates Co", wait=3000)
        enable(page)
        dump(page, "D_profile_sheet")
        if has(page, ["Open Collab Slots"]):
            (mt.click_exact(page, "Yoga Studio", wait=1500) or click_contains(page, "Yoga Studio", wait=1200))
            enable(page)
            dump(page, "D_chip_picked")
        hit = mt.click_exact(page, "Send Associate Request", wait=6000)
        page.wait_for_timeout(2500)
        enable(page)
        dump(page, "D_message_field")
        if has(page, ["Confirm Request"]):
            fill_first_input(page, "Robot Yoga would love to collab.")
            mt.click_exact(page, "Confirm Request", wait=6000)
            page.wait_for_timeout(3500)
            enable(page)
            dump(page, "D_after_confirm")
            sent = has(page, ["Request sent"])
    page.keyboard.press("Escape")
    page.wait_for_timeout(1500)
    enable(page)
    dump(page, "D_tile_pending")
    pending_badge = has(page, ["Pending"])
    sent = sent or pending_badge
    print(f"    >>> request sent: {sent} (badge={pending_badge})")

    # E: own4 receives -> accept -> split -> confirm
    assert real_sign_out(page), "sign-out before own4 login failed"
    login(page, "own4@robot.test")
    go_marketplace(page)
    mt.scroll_down(page, steps=6)
    dump(page, "E_received")
    got = has_all(page, ["Received Requests", "Robot Yoga Co"])
    print(f"    >>> received section: {got}")
    accepted = False
    if got:
        mt.click_exact(page, "Accept", wait=6000)
        page.wait_for_timeout(3000)
        enable(page)
        dump(page, "E_split_dialog")
        if has(page, ["Set your commission split"]):
            mt.click_exact(page, "Confirm Collab", wait=6000)
            page.wait_for_timeout(1200)
            enable(page)
            dump(page, "E_snack_early")
            page.wait_for_timeout(2500)
            enable(page)
            dump(page, "E_after_confirm")
            accepted = not has(page, ["Accept", "Decline", "Confirm Collab"])
    print(f"    >>> accepted+confirmed: {accepted}")
    print_console("post-confirm")

    # F0: own4's dashboard â€” did the mutual agreement actually finalize?
    page.evaluate("() => { window.location.hash = '#/owner'; }")
    page.wait_for_timeout(3000)
    enable(page)
    dump(page, "F0_own4_dashboard")
    own4_active = has(page, ["1 Active"])
    print(f"    >>> own4 dashboard shows 1 Active: {own4_active}")

    # F: own1 side after linking â€” where does the sender approve?
    assert real_sign_out(page), "sign-out before own1 relogin failed"
    login(page, "own1@robot.test")
    dump(page, "F_own1_dashboard")
    own1_pending = has(page, ["1 Pending"])
    print(f"    >>> own1 dashboard shows 1 Pending: {own1_pending}")

    # F1: sender-side approval via the dashboard pending chip
    # (non-empty counts open AgreementDetailScreen â€” the only Approve UI)
    sender_detail = sender_approved = False
    if own1_pending:
        click_contains(page, "1 Pending", wait=4000)
        page.wait_for_timeout(2500)
        enable(page)
        dump(page, "F1_own1_detail")
        sender_detail = has(page, ["Approve", "Decline"])
        print(f"    >>> sender detail w/ Approve: {sender_detail}")
        if sender_detail:
            mt.click_exact(page, "Approve", wait=6000)
            page.wait_for_timeout(3500)
            enable(page)
            dump(page, "F1_own1_after_approve")
            page.evaluate("() => { window.location.hash = '#/owner'; }")
            page.wait_for_timeout(3000)
            enable(page)
            dump(page, "F1_own1_dashboard_after")
            sender_approved = has(page, ["1 Active"]) and not has(page, ["1 Pending"])
            print(f"    >>> sender approved -> 1 Active, 0 Pending: {sender_approved}")
    # F2: bell notifications
    mt.find_and_click(page, "Notifications", timeout=6000)
    page.wait_for_timeout(2500)
    enable(page)
    dump(page, "F_notifications")
    page.evaluate("() => { window.location.hash = '#/owner'; }")
    page.wait_for_timeout(2500)
    enable(page)
    # F3: revenue/finance deals
    mt.find_and_click(page, "Revenue", timeout=6000)
    page.wait_for_timeout(3000)
    enable(page)
    mt.scroll_down(page, steps=3)
    dump(page, "F_finance_deals")
    # F4: marketplace sent state
    go_marketplace(page)
    mt.scroll_down(page, steps=6)
    dump(page, "F_own1_marketplace_after")
    # F5: network screen state
    page.evaluate("() => { window.location.hash = '#/owner'; }")
    page.wait_for_timeout(2500)
    enable(page)
    mt.find_and_click(page, "Network", timeout=6000)
    page.wait_for_timeout(2500)
    enable(page)
    dump(page, "F_network_after")

    # â”€â”€ G: money loop (Round 6 mock payments) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # G1: own1's ACTIVE agreement detail â€” the Record payment entry point
    home_ok = go_home(page)
    print(f"    >>> G0 go_home: {home_ok}")
    click_contains(page, "1 Active", wait=4000)
    page.wait_for_timeout(2500)
    enable(page)
    has_payment_btn = has_after_scroll(page, ["Record payment", "End Agreement"])
    dump(page, "G1_own1_detail")
    print(f"    >>> G1 active detail w/ Record payment: {has_payment_btn}")

    # G2: record a $120 card payment (defaults: Session payment / Client / Card)
    paid = False
    if has_payment_btn:
        mt.click_exact(page, "Record payment", wait=6000)
        page.wait_for_timeout(2500)
        enable(page)
        dump(page, "G2_payment_dialog")
        # TextField labels are INPUT aria-labels ('Amount\ne.g. 120.00'),
        # NOT flt-semantics text â€” check inputs + visible button text.
        labels = input_labels(page)
        dialog_ok = has(page, ["Confirm Payment", "Payment method"]) and \
            any(a.startswith("Amount") for a in labels)
        print(f"    >>> G2 payment dialog fields: {dialog_ok} inputs={labels}")
        if dialog_ok:
            filled = fill_by_label_prefix(page, "Amount", "120")
            print(f"    >>> G2 amount filled: {filled}")
            # Snackbar fires only after the awaited record + two network
            # delays (~1.5-3s) and lives ~4s â€” check at ~4.7s post-click.
            mt.click_exact(page, "Confirm Payment", wait=1200)
            page.wait_for_timeout(3500)
            enable(page)
            paid = has(page, ["Payment recorded"])
            dump(page, "G2_after_confirm")
            print(f"    >>> G2 payment recorded snackbar: {paid}")
        # Never strand the modal â€” it blocks navigation and sign-out.
        if has(page, ["Confirm Payment"]):
            print("    >>> G2 dialog still open -> cancelling")
            mt.click_exact(page, "Cancel", wait=3000)
            page.wait_for_timeout(1000)
            enable(page)

    # G3: own1's Revenue â€” payment txn + pending commission w/ Mark Paid
    #     (split on own1's copy = owner 80 / partner 20 -> $24 owed)
    home_ok = go_home(page)  # from detail: hash fallback (no bottom nav)
    print(f"    >>> G3 go_home: {home_ok}")
    mt.find_and_click(page, "Revenue", timeout=6000)
    page.wait_for_timeout(3000)
    enable(page)
    revenue_ok = has_after_scroll(page, ["Session payment", "Mark Paid"])
    dump(page, "G3_own1_revenue")
    print(f"    >>> G3 revenue shows payment + pending commission: {revenue_ok}")

    # G4: Mark Paid -> payout txn on own1's ledger, button disappears
    payout_btn_gone = own1_payout = False
    if revenue_ok:
        mt.click_exact(page, "Mark Paid", wait=6000)
        page.wait_for_timeout(3500)
        enable(page)
        payout_btn_gone = not has(page, ["Mark Paid"])
        own1_payout = has_after_scroll(
            page, ["Commission payout to Robot Pilates Co"])
        dump(page, "G4_own1_after_mark_paid")
        print(f"    >>> G4 Mark Paid: btn gone={payout_btn_gone}, "
              f"payout txn={own1_payout}")

    # G5: own4's side â€” the payout lands in the PAYEE's own ledger
    #     (owner-role payee visibility: merged user-keyed txns + commissions)
    assert go_home(page), "could not get home before sign-out"
    assert real_sign_out(page), "sign-out before own4 finance check failed"
    login(page, "own4@robot.test")
    go_home(page)
    mt.find_and_click(page, "Revenue", timeout=6000)
    page.wait_for_timeout(3000)
    enable(page)
    own4_payout = has_after_scroll(
        page, ["Commission payout to Robot Pilates Co"])
    own4_no_mark = not has(page, ["Mark Paid"])  # payee row: not ours to close
    own4_deal = has(page, ["Deals"])
    dump(page, "G5_own4_revenue")
    print(f"    >>> G5 own4 sees payout txn: {own4_payout} "
          f"(no Mark Paid btn: {own4_no_mark}, Deals: {own4_deal})")

    # `paid` (snackbar sighting) is best-effort; revenue_ok â€” the actual
    # payment txn + pending commission row â€” is the real proof.
    money_loop_ok = all([revenue_ok, payout_btn_gone,
                         own1_payout, own4_payout, own4_no_mark])
    print(f"    >>> MONEY LOOP OK: {money_loop_ok} (snackbar seen: {paid})")

    print_console("final")

    with open("probe_marketplace_out.json", "w") as f:
        json.dump(LOG, f, indent=1)
    print(f"\nWROTE probe_marketplace_out.json ({len(LOG)} steps)")


if __name__ == "__main__":
    if ensure_server():
        try:
            run()
        finally:
            stop_server()
