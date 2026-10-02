"""Diag: what does the marketplace DOM actually contain?"""
import json
from playwright.sync_api import sync_playwright

import master_test as mt

from server_control import BASE, ensure_server, stop_server


def run():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.goto(BASE)
    page.wait_for_timeout(7000)
    mt.enable_flutter_acc(page)

    # signup own1 with the proven onboarding walk
    import probe_marketplace as pm
    url = pm.signup(page, "Robot Yoga", "diag@robot.test", "Movement & Fitness",
                    "Yoga Studio", "Robot Yoga Co")
    print("signup ->", url)
    mt.enable_flutter_acc(page)

    page.evaluate("() => { window.location.hash = '#/owner/marketplace'; }")
    page.wait_for_timeout(6000)
    mt.enable_flutter_acc(page)
    page.wait_for_timeout(1500)

    out = page.evaluate("""() => {
        const sems = Array.from(document.querySelectorAll('flt-semantics'));
        const info = sems.slice(0, 80).map(s => {
            const r = s.getBoundingClientRect();
            return {role: s.getAttribute('role') || '',
                    cls: s.className || '',
                    txt: (s.textContent || '').trim().replace(/\\s+/g,' ').slice(0,90),
                    aria: s.getAttribute('aria-label') || '',
                    y: Math.round(r.y), x: Math.round(r.x),
                    w: Math.round(r.width), h: Math.round(r.height)};
        });
        const switches = sems.filter(s => s.getAttribute('role') === 'switch')
            .map((s, i) => { const r = s.getBoundingClientRect();
                return {i, y: Math.round(r.y), x: Math.round(r.x),
                        w: Math.round(r.width), h: Math.round(r.height),
                        checked: s.getAttribute('aria-checked') || ''}; });
        const others = Array.from(document.querySelectorAll(
            'flt-paragraph, flt-text, canvas, .flutter-view p, flutter-view'))
            .slice(0, 20).map(e => ({tag: e.tagName, cls: e.className,
                txt: (e.textContent||'').trim().slice(0,60)}));
        const host = document.querySelector('flt-semantics');
        return {count: sems.length, switches, others,
                hostParent: host && host.parentElement
                    ? host.parentElement.outerHTML.slice(0, 2500) : '',
                bodyClasses: document.body.className,
                fltTags: Array.from(new Set(Array.from(document.querySelectorAll('*'))
                    .map(e => e.tagName.toLowerCase()).filter(t => t.startsWith('flt-'))))};
    }""")
    print(json.dumps(out, indent=1)[:9000])

    browser.close()
    pw.stop()


if __name__ == "__main__":
    if ensure_server():
        try:
            run()
        finally:
            stop_server()
