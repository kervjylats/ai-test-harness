#!/usr/bin/env python
# game_driver.py — Round 6 turn-based co-op game driver.
#
# A human and this script share one browser session and take turns:
#   the script plays the SETUP scenes, then hands you a decision gate
#   ("I propose in chat, you accept/edit"), swaps identity LIVE, plays
#   out your decision in the app, and continues. At the end an
#   after-action recap file is written next to this script.
#
# Personas (shared password, `name@demo.test` emails):
#   avery   owner        Avery Yoga Co        fresh signup
#   blake   associate    joined via avery's invite link (chat deal)
#   casey   marketplace  Casey Pilates Co     fresh signup, collab via marketplace
#   dana    staff        joined via avery's staff invite
#   erin    client       joined via blake's client invite (invites both ways)
#
# Usage:
#   python game_driver.py                 # headed, interactive gates
#   python game_driver.py --auto          # unattended: gates auto-accept
#   python game_driver.py --no-prologue   # skip the opening scene text
#
# Depends on master_test.py helpers (same repo); run against the RELEASE
# web build served by server_control.py on http://localhost:9090 (Round 7:
# was 8080, which is the LocalAI hub's `big` slot port). The server is
# started on demand and stopped when this script exits - nothing lingers.

import argparse
import datetime
import sys

from playwright.sync_api import sync_playwright

import master_test as mt
from server_control import BASE, ensure_server, stop_server

PASSWORD = "demo123"

OWNER = dict(role="owner", name="Avery", email="avery@demo.test",
             business="Avery Yoga Co", job="Yoga Studio",
             category="Movement & Fitness")
MARKET = dict(role="marketplace", name="Casey", email="casey@demo.test",
              business="Casey Pilates Co", job="Pilates Studio",
              category="Movement & Fitness")
ASSOC = dict(role="associate", name="Blake", email="blake@demo.test")
STAFF = dict(role="staff", name="Dana", email="dana@demo.test")
CLIENT = dict(role="client", name="Erin", email="erin@demo.test")

PROPOSAL = ("Propose: you take every Saturday client, 70/30 split in "
            "your favour on what you bring, one review each month. "
            "Accept or edit.")

SCENES = []      # {n, title, status: pass|fail|skip, note, shot}
DECISIONS = []   # {gate, persona, prompt, decision}
_STATE = {"auto": False, "n": 0}


def banner(text):
    print(f"\n{'=' * 60}\n {text}\n{'=' * 60}", flush=True)


def shot(page, name):
    return mt.screenshot(page, f"game_{name}")


def scene(page, title, ok, note="", screenshot=None):
    _STATE["n"] += 1
    status = "pass" if ok else "fail"
    SCENES.append({"n": _STATE["n"], "title": title, "status": status,
                   "note": note, "shot": screenshot or ""})
    print(f"  [{status.upper()}] {_STATE['n']}. {title}"
          + (f" — {note}" if note else ""), flush=True)
    return ok


def skip_scene(title, note):
    _STATE["n"] += 1
    SCENES.append({"n": _STATE["n"], "title": title, "status": "skip",
                   "note": note, "shot": ""})
    print(f"  [SKIP] {_STATE['n']}. {title} — {note}", flush=True)


def gate(page, gate_id, persona, prompt, options, default="accept",
         screenshot=None):
    """Live decision gate. Returns the human's raw decision string."""
    banner(f"GATE {gate_id} — you now play {persona['name']} "
           f"({persona['role']})")
    print(prompt, flush=True)
    print("Options: " + " | ".join(options), flush=True)
    if screenshot:
        shot(page, f"gate{gate_id}_{persona['role']}")
    if _STATE["auto"]:
        decision = default
        print(f"(auto) decision: {decision}", flush=True)
    else:
        try:
            decision = input("Your move> ").strip()
        except EOFError:
            decision = default
            print(f"(stdin closed) decision: {decision}", flush=True)
        if not decision:
            decision = default
    DECISIONS.append({"gate": gate_id, "persona": persona["email"],
                      "prompt": prompt, "decision": decision})
    print(f"-> {persona['name']} decides: {decision}\n", flush=True)
    return decision


def wait_composer(page, timeout_ms=6000):
    """Chat room = a textarea with aria-label 'Type a message…' present.
    (The thread is pushed as a URL-less route, so the URL never changes.)"""
    waited = 0
    while waited < timeout_ms:
        try:
            el = page.query_selector('textarea[aria-label*="message" i]')
            if el and el.is_visible():
                return True
        except Exception:
            pass
        page.wait_for_timeout(400)
        waited += 400
    return False


def send_chat(page, text):
    """Type into the composer and click Send (positional: the Send button
    sits at the composer's right edge, ~32px from the screen edge — the
    'Send' tooltip is never exposed as a semantics aria-label in this
    build, and the composer's own aria-label empties while typing).
    Returns True when the message bubble shows up in the thread."""
    for attempt in range(3):
        ok = False
        for sel in ('textarea[aria-label*="message" i]', 'textarea'):
            try:
                page.fill(sel, text, timeout=3000)
                ok = True
                break
            except Exception:
                continue
        if not ok:
            n = page.evaluate("""(v) => {
                const el = document.querySelector('textarea');
                if (!el) return 0;
                Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype, 'value'
                ).set.call(el, v);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                return 1;
            }""", text)
            ok = n > 0
        if not ok:
            print(f"    send: attempt {attempt} — composer not fillable",
                  flush=True)
            page.wait_for_timeout(1500)
            continue
        cur = page.evaluate(
            "() => (document.querySelector('textarea') || {}).value || ''")
        if text not in cur:
            page.wait_for_timeout(600)
            cur = page.evaluate(
                "() => (document.querySelector('textarea') || {}).value || ''")
        if text not in cur:
            print(f"    send: attempt {attempt} — value not set", flush=True)
            page.wait_for_timeout(1500)
            continue
        # Positional Send click (probe-verified: w-32, composer mid-row).
        rect = page.evaluate("""() => {
            const el = document.querySelector('textarea');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return null;
            return {y: r.y + r.height / 2, w: window.innerWidth};
        }""")
        if not rect:
            print(f"    send: attempt {attempt} — no composer rect", flush=True)
            page.wait_for_timeout(1500)
            continue
        page.mouse.click(rect["w"] - 32, rect["y"])
        page.wait_for_timeout(2200)
        if text[:24] in " ".join(mt.get_all_text(page)):
            return True
        print(f"    send: attempt {attempt} — clicked, no bubble yet",
              flush=True)
        page.wait_for_timeout(800)
    print("    send: FAILED after 3 attempts", flush=True)
    return False


def open_dm(page, member, owner_side=False):
    """Network tab -> member row/icon -> chat room. Owner-side member
    tiles open the DM on tap (URL-less push); the partner-side owner card
    needs its 'Message <name>' icon (semantics node or icon slot)."""
    mt.find_and_click(page, "Network", timeout=6000)
    page.wait_for_timeout(1800)
    mt.enable_flutter_acc(page)
    if owner_side:
        mt.find_and_click(page, "Associates")
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
    # 1) tap the member tile (owner Associates list) — proven to push the
    #    chat room.
    mt.click_contains(page, member, wait=2500)
    if wait_composer(page, 5000):
        return True
    # 2) explicit 'Message <name>' icon button (partner owner card keeps
    #    its own semantics node).
    if mt.find_and_click(page, f"Message {member}", timeout=3500):
        if wait_composer(page, 5000):
            return True
    # 3) trusted coordinate click on the icon's slot: trailing edge of the
    #    row/card (chat icon sits ~58px from the right edge).
    pt = page.evaluate("""(name) => {
        for (const s of document.querySelectorAll('flt-semantics')) {
            const t = ((s.textContent || '') + ' ' +
                       (s.getAttribute('aria-label') || ''));
            if (!t.includes(name)) continue;
            const r = s.getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {x: r.right - 58, y: r.y + r.height / 2};
        }
        return null;
    }""", member)
    if pt:
        page.mouse.click(pt["x"], pt["y"])
        print(f"    open_dm: icon-slot click at {pt}", flush=True)
        if wait_composer(page, 5000):
            return True
    return False


def write_recap(mode, prologue_shown):
    ts = datetime.datetime.now()
    path = f"game_recap_{ts.strftime('%Y%m%d_%H%M%S')}.md"
    lines = [
        "# Game Recap — After-Action Report",
        "",
        f"- Run: {ts.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Mode: {mode}",
        f"- Prologue: {'shown' if prologue_shown else 'skipped'}",
        f"- Shared password: `{PASSWORD}` (emails `name@demo.test`)",
        "",
        "## Decision gates",
        "",
    ]
    if DECISIONS:
        for d in DECISIONS:
            lines.append(f"- **Gate {d['gate']}** ({d['persona']}): "
                         f"`{d['decision']}`")
    else:
        lines.append("- none reached")
    lines += ["", "## Scenes", "",
              "| # | Scene | Result | Note | Screenshot |",
              "|---|-------|--------|------|------------|"]
    for s in SCENES:
        lines.append(f"| {s['n']} | {s['title']} | {s['status'].upper()} "
                     f"| {s['note']} | {s['shot']} |")
    passed = sum(1 for s in SCENES if s["status"] == "pass")
    failed = sum(1 for s in SCENES if s["status"] == "fail")
    skipped = sum(1 for s in SCENES if s["status"] == "skip")
    lines += ["", "## Totals", "",
              f"- pass {passed} / fail {failed} / skip {skipped} "
              f"(of {len(SCENES)})",
              ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\nRecap written: {path}", flush=True)
    return path, failed


def run(args):
    _STATE["auto"] = args.auto
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=args.headless,
        args=["--enable-unsafe-swiftshader", "--disable-dev-shm-usage"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800},
                              permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    failed = 1
    prologue_shown = not args.no_prologue
    try:
        page.goto(BASE, timeout=30000)
        page.wait_for_timeout(6000)
        mt.enable_flutter_acc(page)
        # First load is slow (engine warm-up) — poll the front door like
        # the suite's CC1 before touching the signup form.
        mt.wait_for_texts(page, ["run your own", "wellness business",
                                 "Get started"], timeout_ms=60000)

        # ---------------------------------------------------------------
        # PROLOGUE (optional)
        # ---------------------------------------------------------------
        if prologue_shown:
            banner("PROLOGUE")
            print("Avery is opening a yoga studio and needs a team.\n"
                  "Blake, a fellow wellness pro, was invited to join.\n"
                  "Casey runs a pilates studio across town — the marketplace\n"
                  "may turn them into collaborators. Staff and clients will\n"
                  "follow. You decide the deals; the driver runs the app.",
                  flush=True)

        # ---------------------------------------------------------------
        # SCENE 1 — owner boots up
        # ---------------------------------------------------------------
        banner("SCENE 1 — Avery opens the studio")
        url = mt.signup(page, OWNER["name"], OWNER["email"],
                        OWNER["category"], OWNER["job"], OWNER["business"],
                        tagline="Yoga for real life", password=PASSWORD)
        s = shot(page, "01_owner_dashboard")
        scene(page, "Owner Avery signs up and lands on the dashboard",
              "#/owner" in url, f"url={url}", s)

        # ---------------------------------------------------------------
        # SCENE 2 — invite the associate (invite direction 1)
        # ---------------------------------------------------------------
        banner("SCENE 2 — Avery invites Blake (associate)")
        mt.find_and_click(page, "Network", timeout=6000)
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        mt.find_and_click(page, "Associates")
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        inv = mt.find_and_click(page, "Invite")
        token_assoc = mt.generate_invite_token(page, "wlp_000011") if inv else ""
        s = shot(page, "02_invite_associate")
        scene(page, "Invite link generated for the associate",
              token_assoc.startswith("wlp_"), f"token={token_assoc or 'NONE'}", s)
        mt.real_sign_out(page)
        joined = mt.invitee_signup(page, token_assoc, ASSOC["name"],
                                   ASSOC["email"], password=PASSWORD)
        s = shot(page, "02b_blake_partner_shell")
        scene(page, "Blake joins via invite code -> partner shell",
              "/partner" in joined, f"url={joined} token={token_assoc}", s)

        # ---------------------------------------------------------------
        # SCENE 3 — GATE A: propose in chat, human accepts/edits
        # ---------------------------------------------------------------
        banner("SCENE 3 — the chat proposal (live role swap)")
        mt.real_sign_out(page)
        mt.login(page, OWNER["email"], PASSWORD)
        dm = open_dm(page, ASSOC["name"], owner_side=True)
        s = shot(page, "03_owner_dm_open")
        sent = send_chat(page, PROPOSAL) if dm else False
        scene(page, "Avery opens the DM with Blake and posts the proposal",
              dm and sent, f"dm={dm} sent={sent}", s)
        decision = gate(
            page, "A", ASSOC,
            f"Avery proposes in chat:\n  \"{PROPOSAL}\"\n"
            "In the browser you can read it (Network -> chat with Avery).\n"
            "Your move as Blake:",
            ["accept", "edit <your reply text>"], default="accept")
        mt.real_sign_out(page)
        mt.login(page, ASSOC["email"], PASSWORD)
        dm2 = open_dm(page, OWNER["name"])
        reply = ("Agreed — accepted, let's run Saturdays."
                 if decision.lower().startswith(("accept", "y", "agree"))
                 else decision[4:].strip() if decision.lower().startswith("edit")
                 else decision)
        s = shot(page, "03b_blake_reply")
        replied = send_chat(page, reply) if dm2 else False
        scene(page, f"Blake replies in chat: \"{reply[:40]}\"",
              dm2 and replied, f"dm={dm2} sent={replied}", s)

        # ---------------------------------------------------------------
        # SCENE 4 — marketplace persona (Casey) sets up
        # ---------------------------------------------------------------
        banner("SCENE 4 — Casey's studio joins the marketplace")
        mt.real_sign_out(page)
        url = mt.signup(page, MARKET["name"], MARKET["email"],
                        MARKET["category"], MARKET["job"], MARKET["business"],
                        tagline="Pilates with purpose", password=PASSWORD)
        s = shot(page, "04_casey_dashboard")
        scene(page, "Casey signs up (second real business)",
              "#/owner" in url, f"url={url}", s)
        mt.go_marketplace(page)
        t1 = mt.toggle_slot(page, "Discoverable")
        t2 = mt.toggle_slot(page, "Yoga Studio")
        s = shot(page, "04b_casey_marketplace_slots")
        scene(page, "Casey goes discoverable and opens the Yoga slot",
              bool(t1 and t2), f"discoverable={bool(t1)} yoga_slot={bool(t2)}", s)

        # ---------------------------------------------------------------
        # SCENE 5 — Avery discovers Casey, sends the request
        # ---------------------------------------------------------------
        banner("SCENE 5 — Avery discovers Casey in the marketplace")
        mt.real_sign_out(page)
        mt.login(page, OWNER["email"], PASSWORD)
        mt.go_marketplace(page)
        mt.toggle_slot(page, "Discoverable")
        mt.toggle_slot(page, "Pilates Studio")
        mt.scroll_down(page, steps=6)
        has_tile = mt.has(page, [MARKET["business"]])
        s = shot(page, "05_discovery_tile")
        scene(page, f"Tile for {MARKET['business']} is discoverable",
              has_tile, f"tile={has_tile}", s)
        sent_req = False
        if has_tile:
            mt.click_contains(page, MARKET["business"], wait=3000)
            mt.enable_flutter_acc(page)
            if mt.has(page, ["Open Collab Slots"]):
                (mt.click_exact(page, "Yoga Studio", wait=1500)
                 or mt.click_contains(page, "Yoga Studio", wait=1200))
                mt.enable_flutter_acc(page)
            hit = mt.click_exact(page, "Send Associate Request", wait=6000)
            page.wait_for_timeout(2500)
            mt.enable_flutter_acc(page)
            if mt.has(page, ["Confirm Request"]):
                mt.fill_first_input(page, "Avery Yoga would love to collab.")
                mt.click_exact(page, "Confirm Request", wait=6000)
                page.wait_for_timeout(3500)
                mt.enable_flutter_acc(page)
                sent_req = mt.has(page, ["Request sent"])
            sent_req = sent_req or hit and mt.has(page, ["Pending"])
        s = shot(page, "05b_request_sent")
        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
        scene(page, "Associate Request sent to Casey (pending outbound)",
              sent_req, f"sent={sent_req}", s)

        # ---------------------------------------------------------------
        # SCENE 6 — GATE B: Casey's live accept/decline
        # ---------------------------------------------------------------
        decision_b = gate(
            page, "B", MARKET,
            "Avery sent an Associate Request to Casey's studio.\n"
            "In the browser: Marketplace -> Received Requests shows it.\n"
            "Your move as Casey:",
            ["accept", "decline"], default="accept")
        declined = decision_b.lower().startswith("decl")
        if declined:
            skip_scene("Casey accepts the collab request",
                       f"Gate B decision: {decision_b}")
            skip_scene("Avery approves -> agreement Active",
                       "cascade: request declined at Gate B")
            skip_scene("Money loop (record payment -> commission payout)",
                       "cascade: no active agreement")
            skip_scene("Casey's ledger shows the commission payout",
                       "cascade: no active agreement")
        else:
            # Casey accepts + confirms the split
            mt.real_sign_out(page)
            mt.login(page, MARKET["email"], PASSWORD)
            mt.go_marketplace(page)
            mt.scroll_down(page, steps=6)
            got = mt.has_all(page, ["Received Requests", OWNER["business"]])
            accepted = False
            s = shot(page, "06_received_request")
            if got:
                mt.click_exact(page, "Accept", wait=6000)
                page.wait_for_timeout(3000)
                mt.enable_flutter_acc(page)
                if mt.has(page, ["Set your commission split"]):
                    mt.click_exact(page, "Confirm Collab", wait=6000)
                    page.wait_for_timeout(3700)
                    mt.enable_flutter_acc(page)
                    accepted = not mt.has(page, ["Accept", "Decline",
                                                 "Confirm Collab"])
                    s = shot(page, "06b_collab_confirmed")
            scene(page, "Casey accepts and confirms the collab",
                  got and accepted, f"received={got} confirmed={accepted}", s)

            # Avery approves -> Active
            mt.real_sign_out(page)
            mt.login(page, OWNER["email"], PASSWORD)
            s = shot(page, "06c_pending_chip")
            pending = mt.has(page, ["1 Pending"])
            approved = False
            if pending:
                mt.click_contains(page, "1 Pending", wait=4000)
                page.wait_for_timeout(2500)
                mt.enable_flutter_acc(page)
                if mt.has(page, ["Approve"]):
                    mt.click_exact(page, "Approve", wait=6000)
                    page.wait_for_timeout(3500)
                    mt.enable_flutter_acc(page)
                    page.evaluate("() => { window.location.hash = '#/owner'; }")
                    page.wait_for_timeout(3000)
                    mt.enable_flutter_acc(page)
                    approved = (mt.has(page, ["1 Active"])
                                and not mt.has(page, ["1 Pending"]))
                    s = shot(page, "06d_agreement_active")
            scene(page, "Avery approves -> agreement Active",
                  pending and approved,
                  f"pending_chip={pending} approved={approved}", s)

            # -------------------------------------------------------------
            # SCENE 7 — money loop (proven suite path)
            # -------------------------------------------------------------
            banner("SCENE 7 — money loop (payment -> commission payout)")
            mt.go_home(page)
            mt.click_contains(page, "1 Active", wait=4000)
            page.wait_for_timeout(2500)
            mt.enable_flutter_acc(page)
            detail = mt.has_after_scroll(page, ["Record payment",
                                                "End Agreement"])
            dialog_ok = False
            if detail:
                mt.click_exact(page, "Record payment", wait=6000)
                page.wait_for_timeout(2500)
                mt.enable_flutter_acc(page)
                labels = mt.input_labels(page)
                dialog_ok = (mt.has(page, ["Confirm Payment",
                                           "Payment method"])
                             and any(a.startswith("Amount") for a in labels))
            s = shot(page, "07_payment_dialog")
            closed = False
            if dialog_ok:
                mt.fill_by_label_prefix(page, "Amount", "120")
                mt.click_exact(page, "Confirm Payment", wait=1200)
                page.wait_for_timeout(3500)
                mt.enable_flutter_acc(page)
                closed = mt.until_absent(page, ["Confirm Payment"], 8000)
                if mt.has(page, ["Confirm Payment"]):
                    mt.click_exact(page, "Cancel", wait=3000)
            scene(page, "$120 payment recorded on the active agreement",
                  detail and dialog_ok and closed,
                  f"detail={detail} dialog={dialog_ok} closed={closed}", s)

            mt.go_home(page)
            mt.find_and_click(page, "Revenue", timeout=6000)
            page.wait_for_timeout(3000)
            mt.enable_flutter_acc(page)
            revenue_ok = mt.has_after_scroll(page, ["Session payment",
                                                    "Mark Paid"])
            btn_gone = payout = False
            s = shot(page, "07b_revenue_mark_paid")
            if revenue_ok:
                mt.click_exact(page, "Mark Paid", wait=6000)
                page.wait_for_timeout(3500)
                mt.enable_flutter_acc(page)
                btn_gone = not mt.has(page, ["Mark Paid"])
                payout = mt.has_after_scroll(
                    page, [f"Commission payout to {MARKET['business']}"])
                s = shot(page, "07c_payout_done")
            scene(page, "Mark Paid pays the commission out (payout txn)",
                  revenue_ok and btn_gone and payout,
                  f"revenue={revenue_ok} btn_gone={btn_gone} "
                  f"payout={payout}", s)

            # payee side
            mt.real_sign_out(page)
            mt.login(page, MARKET["email"], PASSWORD)
            mt.go_home(page)
            mt.find_and_click(page, "Revenue", timeout=6000)
            page.wait_for_timeout(3000)
            mt.enable_flutter_acc(page)
            payee = mt.has_after_scroll(
                page, [f"Commission payout to {MARKET['business']}"])
            no_mark = not mt.has(page, ["Mark Paid"])
            s = shot(page, "07d_payee_ledger")
            scene(page, "Casey's own ledger shows the commission payout",
                  payee and no_mark, f"payout={payee} no_mark={no_mark}", s)

        # ---------------------------------------------------------------
        # SCENE 8 — staff invite (owner -> staff)
        # ---------------------------------------------------------------
        banner("SCENE 8 — Avery invites Dana (staff)")
        mt.real_sign_out(page)
        mt.login(page, OWNER["email"], PASSWORD)
        mt.find_and_click(page, "Network", timeout=6000)
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        mt.find_and_click(page, "Staff")
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        inv = mt.find_and_click(page, "Invite")
        token_staff = (mt.generate_invite_token(page, "wlp_000012")
                       if inv else "")
        s = shot(page, "08_staff_invite")
        scene(page, "Staff invite link generated",
              token_staff.startswith("wlp_"),
              f"token={token_staff or 'NONE'}", s)
        mt.real_sign_out(page)
        joined = mt.invitee_signup(page, token_staff, STAFF["name"],
                                   STAFF["email"], password=PASSWORD)
        s = shot(page, "08b_dana_staff_shell")
        scene(page, "Dana joins via invite code -> staff shell",
              "/staff" in joined, f"url={joined}", s)

        # ---------------------------------------------------------------
        # SCENE 9 — client invite by the associate (invite direction 2)
        # ---------------------------------------------------------------
        banner("SCENE 9 — Blake invites Erin (client): invites both ways")
        mt.real_sign_out(page)
        mt.login(page, ASSOC["email"], PASSWORD)
        mt.find_and_click(page, "Network", timeout=6000)
        page.wait_for_timeout(1500)
        mt.enable_flutter_acc(page)
        inv = mt.find_and_click(page, "Invite")   # 'Invite a client' FAB
        token_client = (mt.generate_invite_token(page, "wlp_000013")
                        if inv else "")
        s = shot(page, "09_client_invite")
        scene(page, "Associate-generated client invite link",
              token_client.startswith("wlp_"),
              f"token={token_client or 'NONE'}", s)
        mt.real_sign_out(page)
        joined = mt.invitee_signup(page, token_client, CLIENT["name"],
                                   CLIENT["email"], password=PASSWORD)
        s = shot(page, "09b_erin_client_shell")
        scene(page, "Erin joins via invite code -> client shell",
              "/client" in joined, f"url={joined}", s)

        failed = 0
    except Exception as exc:
        print(f"\n!! game aborted: {exc!r}", flush=True)
        try:
            scene(page, "Driver completed the arc", False, f"abort={exc!r}",
                  shot(page, "abort"))
        except Exception:
            SCENES.append({"n": _STATE["n"] + 1,
                           "title": "Driver completed the arc",
                           "status": "fail", "note": f"abort={exc!r}",
                           "shot": ""})
        failed = 1
    finally:
        try:
            path, recap_failed = write_recap(
                "auto" if args.auto else "interactive",
                prologue_shown)
            failed = failed or recap_failed
        except Exception as exc:
            print(f"!! recap failed: {exc!r}", flush=True)
        ctx.close()
        browser.close()
        pw.stop()
    return failed


def main():
    ap = argparse.ArgumentParser(description="Round 6 co-op game driver")
    ap.add_argument("--auto", action="store_true",
                    help="unattended mode: gates take their default choice")
    ap.add_argument("--headless", action="store_true",
                    help="run without a visible browser window")
    ap.add_argument("--no-prologue", action="store_true",
                    help="skip the opening scene text")
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    if ensure_server():
        try:
            sys.exit(main())
        finally:
            stop_server()
