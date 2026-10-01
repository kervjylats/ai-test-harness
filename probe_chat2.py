#!/usr/bin/env python
# probe_chat2.py — stage-by-stage DM diagnosis:
# dump semantics BEFORE click, trusted coordinate click on the Message
# icon, poll URL/semantics for 6s, fall back to opening the member row
# (profile) and finding a Message action there, then composer send.
import json
import master_test as mt
from playwright.sync_api import sync_playwright

PASSWORD = "demo123"


def state(page, tag):
    info = page.evaluate("""() => {
        const ph = document.querySelector('flt-semantics-placeholder');
        const all = document.querySelectorAll('flt-semantics');
        const labels = [...document.querySelectorAll('flt-semantics[aria-label]')]
            .map(s => (s.getAttribute('role') || '?') + ':' +
                      s.getAttribute('aria-label'));
        const inputs = [...document.querySelectorAll('input, textarea')]
            .filter(el => { const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0; })
            .map(el => el.tagName + '[' +
                (el.getAttribute('aria-label') || '') + '][' +
                (el.getAttribute('placeholder') || '') + ']');
        return {url: location.hash, ph: !!ph, nSem: all.length,
                nLabels: labels.length, labels: labels.slice(0, 40), inputs};
    }""")
    print(f"[{tag}] {json.dumps(info)}", flush=True)
    return info


def coord(page, aria, exact=True):
    pt = page.evaluate("""([al, exact]) => {
        for (const s of document.querySelectorAll('flt-semantics[aria-label]')) {
            const v = (s.getAttribute('aria-label') || '');
            const m = exact ? v === al : v.toLowerCase().includes(al.toLowerCase());
            if (!m) continue;
            const r = s.getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {x: r.x + r.width / 2, y: r.y + r.height / 2, v};
        }
        return null;
    }""", [aria, exact])
    if not pt:
        print(f"  coord({aria!r}) NOT FOUND", flush=True)
        return False
    page.mouse.click(pt["x"], pt["y"])
    print(f"  coord({aria!r}) clicked {pt}", flush=True)
    return True


def run():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True,
                                 args=["--enable-unsafe-swiftshader",
                                       "--disable-dev-shm-usage"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800},
                              permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    page.on("console", lambda m: errs.append(f"{m.type}: {m.text[:200]}")
            if m.type == "error" else None)
    try:
        page.goto(mt.BASE, timeout=30000)
        page.wait_for_timeout(6000)
        mt.enable_flutter_acc(page)
        mt.wait_for_texts(page, ["run your own", "wellness business",
                                 "Get started"], timeout_ms=60000)

        mt.signup(page, "Avery", "avery@demo.test", "Movement & Fitness",
                  "Yoga Studio", "Avery Yoga Co", password=PASSWORD)
        mt.find_and_click(page, "Network", timeout=6000)
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        mt.find_and_click(page, "Associates")
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        mt.find_and_click(page, "Invite")
        token = mt.generate_invite_token(page, "wlp_000011")
        print(f"token={token}", flush=True)
        mt.real_sign_out(page)
        mt.invitee_signup(page, token, "Blake", "blake@demo.test",
                          password=PASSWORD)
        mt.real_sign_out(page)
        mt.login(page, "avery@demo.test", PASSWORD)

        mt.find_and_click(page, "Network", timeout=6000)
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        mt.find_and_click(page, "Associates")
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        state(page, "A: on Associates, semantics should be on")

        print("STAGE 1: trusted coordinate click on 'Message Blake'",
              flush=True)
        coord(page, "Message Blake")
        for i in range(6):
            page.wait_for_timeout(1000)
            s = state(page, f"S1+{i}s")
            if "message-thread" in s["url"]:
                break

        if "message-thread" not in page.url:
            print("STAGE 2: click the member ROW instead", flush=True)
            mt.enable_flutter_acc(page)
            state(page, "B: after re-enable")
            # tile row: click on the 'Blake' text node area
            coord(page, "Blake", exact=True) or mt.click_contains(page, "Blake")
            page.wait_for_timeout(2500)
            mt.enable_flutter_acc(page)
            state(page, "C: after row click")
            # look for a Message action on whatever opened
            if coord(page, "Message Blake"):
                pass
            else:
                coord(page, "Message", exact=False)
            for i in range(5):
                page.wait_for_timeout(1000)
                s = state(page, f"S2+{i}s")
                if "message-thread" in s["url"]:
                    break

        if "message-thread" in page.url:
            page.wait_for_timeout(2000)
            mt.enable_flutter_acc(page)
            state(page, "D: in chat room")
            typed = False
            for sel in ['input[aria-label*="message" i]',
                        'textarea[aria-label*="message" i]',
                        'input[placeholder*="message" i]']:
                try:
                    page.fill(sel, "PROBE TWO hello", timeout=2500)
                    typed = True
                    print(f"typed via {sel}", flush=True)
                    break
                except Exception:
                    pass
            if not typed:
                n = page.evaluate("""() => {
                    const els = [...document.querySelectorAll('input, textarea')]
                        .filter(el => { const r = el.getBoundingClientRect();
                                        return r.width > 0 && r.height > 0; });
                    if (!els.length) return 0;
                    const el = els[0];
                    const proto = el.tagName === 'TEXTAREA'
                        ? window.HTMLTextAreaElement.prototype
                        : window.HTMLInputElement.prototype;
                    Object.getOwnPropertyDescriptor(proto, 'value')
                        .set.call(el, 'PROBE TWO hello');
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    return els.length;
                }""")
                typed = n > 0
                print(f"typed via raw input[0]: {n}", flush=True)
            sent = coord(page, "Send")
            page.wait_for_timeout(2500)
            ok = "PROBE TWO hello" in " ".join(mt.get_all_text(page))
            if not ok:
                page.keyboard.press("Enter")
                page.wait_for_timeout(2500)
                ok = "PROBE TWO hello" in " ".join(mt.get_all_text(page))
            print(f"SENT={ok}", flush=True)
            mt.screenshot(page, "probe2_chat_room")
        else:
            print("NEVER REACHED THE CHAT ROOM", flush=True)
            mt.screenshot(page, "probe2_stuck")

        print("ERRORS:", json.dumps(errs[-15:], indent=1), flush=True)
    finally:
        ctx.close()
        browser.close()
        pw.stop()


if __name__ == "__main__":
    run()
