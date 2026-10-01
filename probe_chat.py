#!/usr/bin/env python
# probe_chat.py — diagnose the owner->associate DM open + message send.
# Dumps composer DOM/semantics after a TRUSTED coordinate click on the
# 'Message <name>' icon, then tries typing + Send via several strategies.
import json
import master_test as mt
from playwright.sync_api import sync_playwright

PASSWORD = "demo123"


def dump(page, tag):
    info = page.evaluate("""() => {
        const inputs = [...document.querySelectorAll('input, textarea')]
            .map(el => ({
                tag: el.tagName,
                aria: el.getAttribute('aria-label') || '',
                ph: el.getAttribute('placeholder') || '',
                cls: (el.className || '').toString().slice(0, 60),
                vis: (() => { const r = el.getBoundingClientRect();
                              return r.width > 0 && r.height > 0; })(),
            }));
        const sems = [...document.querySelectorAll('flt-semantics[aria-label]')]
            .map(s => ({
                al: s.getAttribute('aria-label'),
                role: s.getAttribute('role') || '',
            }))
            .filter(x => /send|message|attach|chat/i.test(x.al));
        return {url: location.href, inputs, sems};
    }""")
    print(f"[{tag}] {json.dumps(info, indent=1)}", flush=True)
    return info


def coord_click(page, aria):
    pt = page.evaluate("""(al) => {
        for (const s of document.querySelectorAll('flt-semantics[aria-label]')) {
            if ((s.getAttribute('aria-label') || '') === al) {
                const r = s.getBoundingClientRect();
                if (r.width > 0 && r.height > 0)
                    return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }
        }
        return null;
    }""", aria)
    if not pt:
        print(f"coord_click {aria!r}: NODE NOT FOUND", flush=True)
        return False
    page.mouse.click(pt["x"], pt["y"])
    print(f"coord_click {aria!r}: clicked {pt}", flush=True)
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
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append(f"console.{m.type}: {m.text}")
            if m.type in ("error", "warning") else None)
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

        # --- open the DM with a trusted coordinate click ---
        mt.find_and_click(page, "Network", timeout=6000)
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        mt.find_and_click(page, "Associates")
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        print("reliable el.click path:",
              mt.find_and_click(page, "Message Blake", timeout=4000),
              flush=True)
        page.wait_for_timeout(3000)
        mt.enable_flutter_acc(page)
        d = dump(page, "after-el-click")
        if "message" not in json.dumps(d).lower() or "send" not in json.dumps(d).lower():
            coord_click(page, "Message Blake")
            page.wait_for_timeout(3500)
            mt.enable_flutter_acc(page)
            d = dump(page, "after-coord-click")

        # --- type into the composer ---
        typed = False
        for sel in ['input[aria-label*="message" i]',
                    'textarea[aria-label*="message" i]',
                    'input[placeholder*="message" i]']:
            try:
                page.fill(sel, "PROBE: hello from the composer", timeout=3000)
                typed = True
                print(f"typed via {sel}", flush=True)
                break
            except Exception as e:
                print(f"fill {sel}: {type(e).__name__}", flush=True)
        if not typed:
            n = page.evaluate("""() => {
                const els = [...document.querySelectorAll('input, textarea')]
                    .filter(el => { const r = el.getBoundingClientRect();
                                    return r.width > 0 && r.height > 0; });
                if (!els.length) return 0;
                const el = els[els.length - 1];
                const proto = el.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                Object.getOwnPropertyDescriptor(proto, 'value')
                    .set.call(el, 'PROBE: hello from the composer');
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.focus();
                return els.length;
            }""")
            typed = n > 0
            print(f"typed via raw-last-input: {n} inputs", flush=True)

        # --- send: coordinate click on Send, else Enter ---
        coord_click(page, "Send")
        page.wait_for_timeout(2500)
        sent = "PROBE: hello from the composer" in " ".join(mt.get_all_text(page))
        print(f"sent (coord)={sent}", flush=True)
        if not sent:
            page.keyboard.press("Enter")
            page.wait_for_timeout(2500)
            sent = "PROBE: hello from the composer" in " ".join(mt.get_all_text(page))
            print(f"sent (enter)={sent}", flush=True)
        mt.screenshot(page, "probe_chat_room")
        dump(page, "final")
        print("PAGE EVENTS:", json.dumps(errs[-12:], indent=1), flush=True)
        print(f"FINAL sent={sent} url={page.url}", flush=True)
    finally:
        ctx.close()
        browser.close()
        pw.stop()


if __name__ == "__main__":
    run()
