"""
probe_deeplink.py - Round 7: prove a REAL shared invite link works in a browser.

Unit tests only proved the URL string round-trips. This proves the browser
agrees with the hash-router reality end to end:

  1. Owner generates an invite; the dialog DISPLAYS a shareable URL.
  2. That URL is hash-style (/#/accept-invitation?token=...) and points at
     the LIVE origin (the port we're actually serving on) - a path-style
     link would 404 on the static server and never load the app at all.
  3. Opening the URL in a FRESH tab (what a real recipient does) lands on
     the redemption screen and prefills the code from the link.
  4. A fresh browser validates + redeems an invite live. NOTE: the mock
     invite store is an in-process static, so a minted token cannot exist
     in another page load - that leg uses the SEEDED demo invite
     (wlp_000001) which every fresh mock load ships. (In mock mode the
     "shared server" only spans one page instance; Phase 10 Supabase will
     make minted links genuinely cross-browser.)
  5. The invitee completes signup straight from the link and reaches
     their role dashboard.

Results -> probe_deeplink_result.json + screenshots in test_screenshots/.
Exit code 0 = all steps pass.
"""
import json
import re

# NOTE: do not wrap sys.stdout here - master_test already installs a
# line-buffered wrapper at import time; wrapping the wrapper's buffer
# again means GC closes the shared buffer mid-run (I/O on closed file).
from playwright.sync_api import sync_playwright

import master_test as mt
from server_control import BASE, ensure_server, stop_server

PASSWORD = "demo123"
OWNER = dict(name="Linka", email="linka@robot.test",
             category="Movement & Fitness", job="Yoga Studio",
             business="Linka Yoga Co")
INVITEE = dict(name="Dee", email="dee@robot.test")
# Seeded client invite (MockInviteSource) - present in every page load,
# so a fresh browser context can validate it live.
SEEDED_TOKEN = "wlp_000001"

RESULTS = []


def check(step, desc, ok, note=""):
    RESULTS.append({"step": step, "desc": desc,
                    "result": "pass" if ok else "fail", "note": note})
    print(f"  [{'PASS' if ok else 'FAIL'}] {step}: {desc}"
          + (f" - {note}" if note else ""), flush=True)
    return ok


def wait_has(page, needle, timeout_ms=20000):
    """True only when the needle is actually visible (mt.wait_for_texts
    returns a text LIST - truthy even on timeout, so it can't be used
    as a boolean)."""
    deadline = timeout_ms
    waited = 0
    while waited <= deadline:
        if mt.has(page, [needle]):
            return True
        page.wait_for_timeout(800)
        waited += 800
    return mt.has(page, [needle])


def grab_url(page):
    """The shareable URL as DISPLAYED in the invite/QR dialog."""
    for _ in range(6):
        texts = "\n".join(mt.get_all_text(page))
        for cand in re.findall(r"https?://[^\s\"'<>]+", texts):
            if "accept-invitation" in cand:
                return cand, "displayed"
        page.wait_for_timeout(500)
    # Clipboard via the dialog's Copy (trusted coordinate click - JS .click()
    # is untrusted and clipboard.writeText gets rejected silently).
    for label in ("Copy", "Copy code", "Copy link"):
        pt = page.evaluate("""(label) => {
            for (const s of document.querySelectorAll('flt-semantics')) {
                if ((s.textContent || '').trim() === label) {
                    const r = s.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0)
                        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                }
            }
            return null;
        }""", label)
        if not pt:
            continue
        page.mouse.click(pt["x"], pt["y"])
        page.wait_for_timeout(700)
        for _ in range(4):
            clip = ""
            try:
                clip = page.evaluate("navigator.clipboard.readText()") or ""
            except Exception:
                pass
            for cand in re.findall(r"https?://[^\s\"'<>]+", clip):
                if "accept-invitation" in cand:
                    return cand, "clipboard"
            page.wait_for_timeout(500)
    return "", "not-found"


def run():
    if not ensure_server():
        print("FATAL: could not start server", flush=True)
        return 1
    invite_url, via = "", "unreached"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--enable-unsafe-swiftshader", "--disable-dev-shm-usage"])
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 800},
                permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            page.goto(BASE, timeout=30000)
            page.wait_for_timeout(6000)
            mt.enable_flutter_acc(page)
            mt.wait_for_texts(page, ["run your own", "wellness business",
                                     "Get started"], timeout_ms=60000)

            # 1. Owner signs up (fresh mock stores -> fresh invite counter).
            url = mt.signup(page, OWNER["name"], OWNER["email"],
                            OWNER["category"], OWNER["job"], OWNER["business"],
                            tagline="Links that work", password=PASSWORD)
            check(1, "Owner signup lands on dashboard", "#/owner" in url,
                  f"url={url}")

            # 2. Network -> Associates -> Invite -> Generate Link.
            mt.find_and_click(page, "Network", timeout=6000)
            page.wait_for_timeout(1500)
            mt.enable_flutter_acc(page)
            mt.find_and_click(page, "Associates")
            page.wait_for_timeout(1500)
            mt.enable_flutter_acc(page)
            inv = mt.find_and_click(page, "Invite")
            gl = mt.click_btn(page, "Generate Link", wait=4000)
            check(2, "Invite dialog mints a link", bool(inv and gl),
                  f"invite_btn={bool(inv)} generate={gl}")
            mt.screenshot(page, "deeplink_02_generated")

            invite_url, via = grab_url(page)
            # Close whichever dialogs are open.
            mt.click_btn(page, "Close", wait=1500)
            mt.click_btn(page, "Done", wait=1200)
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

            # 3. URL shape: live origin + hash route + real token.
            token_m = re.search(r"wlp_[A-Za-z0-9]+", invite_url or "")
            token = token_m.group(0) if token_m else ""
            shape_ok = bool(
                invite_url
                and invite_url.startswith(BASE)
                and "#/accept-invitation?token=" in invite_url
                and token.startswith("wlp_"))
            if not shape_ok and token:
                # Last resort: construct what the dialog should have shown -
                # still exercises the browser half (load + prefill + redeem),
                # but records that the displayed URL was unusable.
                invite_url = f"{BASE}/#/accept-invitation?token={token}"
                via = "constructed(display-read-failed)"
            check(3, "Displayed invite URL is hash-style, live origin, "
                     "carries the token",
                  shape_ok or via.startswith("constructed"),
                  f"via={via} url={invite_url or 'NONE'}")
            check(3.1, "Read the URL straight off the dialog (not faked)",
                  via in ("displayed", "clipboard"), f"via={via}")

            # 4. Fresh CONTEXT = what a real recipient actually is: a different
            # browser profile with no session. (A page in the owner's own
            # context inherits the owner's localStorage session and the
            # router bounces it to #/owner - correct for a logged-in user,
            # useless as a test of the invitee's experience.)
            rctx = browser.new_context(
                viewport={"width": 1280, "height": 800})
            p2 = rctx.new_page()
            p2.goto(invite_url, timeout=30000)
            p2.wait_for_timeout(6500)
            mt.enable_flutter_acc(p2)
            loaded = "accept-invitation" in p2.url
            check(4, "Shared link routes straight to the redemption screen "
                     "(fresh browser, no bounce, no 404)", loaded,
                  f"url={p2.url} title={p2.title()[:60]}")

            mt.screenshot(p2, "deeplink_04_minted")
            # The prefilled value itself is canvas-rendered and never
            # exposed in the DOM/acc tree - the state text is what the
            # screen shows, and step 8 signs up WITHOUT typing the code,
            # which is the functional proof the value landed.
            check(4.1, "Minted link drives the prefilled-code state "
                       "('Your invite code is already filled in')",
                  mt.has(p2, ["Your invite code is already filled in"]),
                  f"token={token}")

            # Live validation + invited heading: seeded invite that exists
            # in every fresh load (mock store is per-page - doc header).
            # goto() with only a hash difference is same-document: no
            # reload means the old page's statics + mounted form survive,
            # so force a real load.
            p2.goto(f"{BASE}/#/accept-invitation?token={SEEDED_TOKEN}",
                    timeout=30000)
            p2.reload(timeout=30000)
            p2.wait_for_timeout(5000)
            mt.enable_flutter_acc(p2)
            recognised = wait_has(p2, "Invite code recognised",
                                  timeout_ms=20000)
            invited = wait_has(p2, "You've been invited", timeout_ms=10000)
            mt.screenshot(p2, "deeplink_04_invited")
            check(5, "Redemption screen shows the invited state",
                  bool(invited), f"url={p2.url}")
            check(6, "Code validated live from the URL "
                     "('Invite code recognised')", bool(recognised))
            check(7, "Code field prefilled from the link (no retyping)",
                  mt.has(p2, ["Your invite code is already filled in"]),
                  "value is canvas-only; step 8 completes signup without "
                  "ever typing it")

            # 5. Redeem: fill the rest and submit whichever surface we're
            # on (accept screen = Continue, landing activation = Activate).
            mt.fill(p2, "Your Name", INVITEE["name"])
            mt.fill(p2, "Email", INVITEE["email"])
            mt.fill(p2, "Password", PASSWORD)
            submitted = (mt.click_btn(p2, "Continue", wait=6000)
                         or mt.click_btn(p2, "Activate", wait=6000)
                         or mt.click_btn(p2, "Get started", wait=6000))
            accepted = wait_has(p2, "You're all set!", timeout_ms=12000)
            if accepted:
                mt.screenshot(p2, "deeplink_05_accepted")
                mt.click_btn(p2, "Go to Dashboard", wait=6000)
                p2.wait_for_timeout(2500)
            else:
                # Landing activation path hops through setup screens
                # (same as mt.invitee_signup).
                for _ in range(8):
                    if any(h in p2.url
                           for h in ("/partner", "/staff", "/client")):
                        break
                    acted = (mt.click_btn(p2, "Continue", wait=3000)
                             or mt.click_btn(p2, "Next", wait=3000)
                             or mt.click_btn(p2, "Finish Setup", wait=3000))
                    p2.wait_for_timeout(1200)
                    if not acted:
                        break
                mt.screenshot(p2, "deeplink_05_accepted")
            final = p2.url
            check(8, "Invitee completes signup from the shared link",
                  bool(submitted) and (accepted or any(
                      h in final for h in ("/partner", "/staff", "/client"))),
                  f"submitted={bool(submitted)} accepted={bool(accepted)}")

            final = p2.url
            check(9, "Invitee lands on their role dashboard",
                  any(h in final for h in ("/partner", "/staff", "/client")),
                  f"url={final}")
            rctx.close()

            browser.close()
    except Exception as exc:
        check("x", "probe aborted", False, f"abort={exc!r}")
    finally:
        stop_server()

    failed = sum(1 for r in RESULTS if r["result"] == "fail")
    with open("probe_deeplink_result.json", "w", encoding="utf-8") as fh:
        json.dump({"base": BASE, "invite_url": invite_url, "via": via,
                   "results": RESULTS}, fh, indent=2)
    print(f"\n{'=' * 60}\nDEEP-LINK PROBE: {len(RESULTS) - failed} pass / "
          f"{failed} fail (of {len(RESULTS)})\n{'=' * 60}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run())