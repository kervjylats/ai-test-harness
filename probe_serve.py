"""Round 7 smoke: harness loads the release bundle on the new port 9090."""
from server_control import BASE, ensure_server, stop_server
from playwright.sync_api import sync_playwright

assert ensure_server(), "server failed to start"
print("BASE =", BASE)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True,
                               args=["--enable-unsafe-swiftshader",
                                     "--disable-dev-shm-usage"])
        pg = b.new_context(viewport={"width": 1280, "height": 800}).new_page()
        pg.goto(BASE, timeout=30000)
        pg.wait_for_timeout(6000)
        title = pg.title()
        has_canvas = pg.evaluate(
            "() => !!document.querySelector('flutter-view, flt-glass-pane, canvas')")
        text = pg.evaluate("() => (document.body.innerText || '').slice(0, 120)")
        print("title:", title)
        print("flutter canvas present:", has_canvas)
        print("body text head:", repr(text))
        b.close()
        assert has_canvas, "no flutter canvas"
        print("smoke OK")
finally:
    stop_server()
    print("server stopped; nothing lingering")
