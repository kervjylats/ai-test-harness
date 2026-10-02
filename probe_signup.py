"""Round 6 probe v3: landing signup -> onboarding walk -> sign-out -> relogin."""
import json
from playwright.sync_api import sync_playwright

from server_control import BASE, ensure_server, stop_server

LOG = []


def enable_flutter_acc(page):
    page.evaluate("""() => {
        const btn = document.querySelector('flt-semantics-placeholder');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(3500)


def dump(page, step):
    enable_flutter_acc(page)
    page.wait_for_timeout(600)
    texts = page.evaluate("""() => Array.from(document.querySelectorAll('flt-semantics'))
        .map(s => ({t: (s.textContent || '').trim().replace(/\\s+/g, ' '),
                    r: s.getAttribute('role') || ''}))
        .filter(x => x.t)""")
    inputs = page.evaluate("""() => Array.from(document.querySelectorAll('input'))
        .map(i => (i.getAttribute('aria-label') || ''))""")
    LOG.append({"step": step, "url": page.url, "texts": texts, "inputs": inputs})
    print(f"\n=== STEP: {step}  url={page.url}")
    print(f"    inputs: {inputs}")
    for i, x in enumerate(texts):
        print(f"    [{i}] ({x['r'] or '-'}) {x['t'][:140]}")


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
    """Click first role=button whose text STARTS WITH prefix (merged
    title+description buttons like 'Yoga Studio Offer yoga classes...')."""
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


def blob_of(i=-1):
    return " | ".join(x["t"] for x in LOG[i]["texts"])


def run():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
    page = browser.new_page(viewport={"width": 1280, "height": 800})

    # signup
    page.goto(BASE)
    page.wait_for_timeout(7000)
    enable_flutter_acc(page)
    email = "probe.owner1@robot.test"
    print(f"    fill name={fill(page, 'Your Name', 'Probe Owner One')} "
          f"email={fill(page, 'Email', email)} pw={fill(page, 'Password', 'test123')}")
    vals = page.evaluate("""() => Array.from(document.querySelectorAll('input'))
        .map(i => ({al: i.getAttribute('aria-label') || '', v: i.value || ''}))""")
    print(f"    input values after fill: {vals}")
    hit = click_btn(page, "Get started", wait=6000)
    print(f"    signup submit hit: {hit}")
    dump(page, "S1_onboarding_start")

    # onboarding walk: category -> job -> about -> rest
    plan = ["Movement & Fitness", "Yoga Studio"]
    for pi, target in enumerate(plan):
        hit = click_btn(page, target, wait=3500) or click_btn_prefix(page, target, wait=3500)
        print(f"    plan[{pi}] {target!r} -> {hit}")
        dump(page, f"S2_plan{pi}_{target.split()[0]}")
    hit = click_btn(page, "Continue", wait=4000)
    print(f"    continue after job select -> {hit}")
    dump(page, "S2b_after_continue")

    FIELD_MAP = {
        "Business Name": "Probe Yoga Co", "Business name": "Probe Yoga Co",
        "Tagline": "Move well, feel good",
        "Your Name": "Probe Owner One", "Email": "probe.owner1@robot.test",
        "Phone": "5550001111",
    }

    def inputs_now():
        return page.evaluate("""() => Array.from(document.querySelectorAll('input'))
            .map(i => (i.getAttribute('aria-label') || ''))""")

    def fill_textareas(txt):
        n = page.evaluate("""(txt) => {
            let c = 0;
            for (const ta of document.querySelectorAll('textarea')) {
                const r = ta.getBoundingClientRect();
                if (r.width > 0) {
                    ta.focus();
                    ta.value = txt;
                    ta.dispatchEvent(new Event('input', {bubbles: true}));
                    c++;
                }
            }
            return c;
        }""", txt)
        if n:
            page.wait_for_timeout(400)
        return n

    for hop in range(14):
        b = blob_of().lower()
        if "revenue" in b and "home" in b:
            print("    >>> DASHBOARD reached")
            break
        filled_any = False
        for lbl in inputs_now():
            if lbl in FIELD_MAP:
                if fill(page, lbl, FIELD_MAP[lbl]):
                    filled_any = True
        if fill_textareas("Robot probe business description") > 0:
            filled_any = True
        if filled_any:
            print(f"    hop {hop}: filled fields")
            dump(page, f"S3_hop{hop}_filled")
        before = blob_of()
        acted = None
        for cand in ["Finish Setup", "Continue", "Next", "Finish", "Start my business", "Create business",
                     "Get started", "Save", "Complete", "Launch"]:
            acted = click_btn(page, cand, wait=3500)
            if acted:
                break
        print(f"    hop {hop}: acted={acted}")
        dump(page, f"S3_hop{hop}")
        if blob_of() == before:
            print("    >>> screen unchanged after action â€” stuck")
            break

    dump(page, "S4_final_state")

    # sign-out discovery via bottom-nav Settings tab (master_test helper)
    import master_test as mt
    hit = mt.find_and_click(page, "Settings", timeout=6000)
    print(f"    settings tab -> {hit}")
    dump(page, "O_settings_tab")
    found_out = False
    for lbl in ["Sign Out", "Sign out", "Log out", "Logout"]:
        h = mt.find_and_click(page, lbl, timeout=3000)
        if h:
            print(f"    >>> sign-out clicked: {lbl}")
            found_out = True
            break
    if found_out:
        page.wait_for_timeout(3000)
        dump(page, "O_after_signout")

    # relogin
    page.evaluate("() => { window.location.hash = '#/login'; }")
    page.wait_for_timeout(4000)
    dump(page, "L0_login")
    if LOG[-1]["inputs"]:
        fill(page, "Email", email)
        fill(page, "Password", "test123")
        hit = click_btn(page, "Sign In", wait=6000)
        print(f"    relogin submit: {hit}")
        dump(page, "L1_after_relogin")
        print(f"    >>> final url: {LOG[-1]['url']}")

    browser.close()
    pw.stop()
    with open("probe_onboarding_out.json", "w") as f:
        json.dump(LOG, f, indent=1)
    print(f"\nWROTE probe_onboarding_out.json ({len(LOG)} steps)")


if __name__ == "__main__":
    if ensure_server():
        try:
            run()
        finally:
            stop_server()
