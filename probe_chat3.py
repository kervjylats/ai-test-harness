#!/usr/bin/env python
# probe_chat3.py — hyper-instrumented composer diagnosis: dump state at
# every step (fill -> value -> semantics -> send click -> bubble).
import json
import master_test as mt
from playwright.sync_api import sync_playwright

PASSWORD = "demo123"
MSG = "PROBE THREE hello world"


def dump(page, tag):
    info = page.evaluate("""() => {
        const ta = document.querySelector('textarea');
        const ph = document.querySelector('flt-semantics-placeholder');
        const labels = [...document.querySelectorAll('flt-semantics[aria-label]')]
            .map(s => (s.getAttribute('role') || '?') + ':' +
                      s.getAttribute('aria-label'));
        return {
            hash: location.hash,
            ta: ta ? {aria: ta.getAttribute('aria-label') || '',
                      val: ta.value,
                      vis: (() => { const r = ta.getBoundingClientRect();
                                    return [r.x, r.y, r.width, r.height]; })()}
                 : null,
            ph: !!ph,
            nSem: document.querySelectorAll('flt-semantics').length,
            labels: labels.slice(0, 30),
            hasMsg: (document.body.innerText || '').includes('PROBE THREE'),
        };
    }""")
    print(f"[{tag}] {json.dumps(info)}", flush=True)
    return info


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
    page.on("console", lambda m: errs.append(f"{m.type}: {m.text[:300]}")
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
        mt.click_contains(page, "Blake", wait=2500)
        page.wait_for_timeout(2500)
        dump(page, "A: after tile click")

        # ---- FILL attempts ----
        sel = 'textarea[aria-label*="message" i]'
        try:
            page.fill(sel, MSG, timeout=3000)
            print("fill(page.fill): OK", flush=True)
        except Exception as e:
            print(f"fill(page.fill): {e!r}", flush=True)
        dump(page, "B: after page.fill")
        cur = page.evaluate(
            "() => (document.querySelector('textarea') || {}).value || ''")
        if MSG not in cur:
            n = page.evaluate("""(v) => {
                const els = [...document.querySelectorAll('textarea, input')]
                    .filter(el => { const r = el.getBoundingClientRect();
                                    return r.width > 0 && r.height > 0; });
                if (!els.length) return 0;
                const el = els[0];
                const proto = el.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                Object.getOwnPropertyDescriptor(proto, 'value')
                    .set.call(el, v);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                return els.length;
            }""", MSG)
            print(f"native set: {n} candidates", flush=True)
        dump(page, "C: after native set")

        # ---- SEND: node coord first, positional second ----
        mt.enable_flutter_acc(page)
        page.wait_for_timeout(2500)
        d = dump(page, "D: after enable")
        pt = None
        for s in d["labels"]:
            if s.endswith(":Send") or s == "button:Send":
                print(f"Send label found in dump: {s}", flush=True)
        pt = page.evaluate("""() => {
            for (const s of document.querySelectorAll('flt-semantics[aria-label]')) {
                if ((s.getAttribute('aria-label') || '') === 'Send') {
                    const r = s.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0)
                        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                }
            }
            return null;
        }""")
        if pt:
            page.mouse.click(pt["x"], pt["y"])
            print(f"clicked Send node {pt}", flush=True)
        else:
            rect = page.evaluate("""() => {
                const el = document.querySelector('textarea');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {y: r.y + r.height / 2, w: window.innerWidth};
            }""")
            print(f"positional rect={rect}", flush=True)
            if rect:
                page.mouse.click(rect["w"] - 32, rect["y"])
                print("clicked positional (w-32)", flush=True)
        page.wait_for_timeout(2500)
        dump(page, "E: after send click")
        if not d0_has(page, MSG):
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)
            dump(page, "F: after Enter")
        print("FINAL hasMsg=", page.evaluate(
            "(m) => document.body.innerText.includes(m)", MSG), flush=True)
        print("ERRORS:", json.dumps(errs[-12:], indent=1), flush=True)
    finally:
        ctx.close()
        browser.close()
        pw.stop()


def d0_has(page, msg):
    return page.evaluate("(m) => document.body.innerText.includes(m)", msg)


if __name__ == "__main__":
    run()
