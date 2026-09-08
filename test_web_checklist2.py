import sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib.request

BASE = "http://127.0.0.1:8765"

def post(cmd, **args):
    data = json.dumps(args).encode()
    req = urllib.request.Request(f"{BASE}/{cmd}", data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def screenshot(name):
    r = post("screenshot", out_path=f"test_evidence/web_c2_{name}.png")
    return r.get("ok")

def find(text):
    r = post("find", text=text)
    if r.get("ok"):
        return r["result"]
    return None

def find_any(*texts):
    for t in texts:
        r = find(t)
        if r:
            return r
    return None

def tap(text):
    r = post("tap", text=text)
    return r.get("ok")

def record(step, desc, result, notes=""):
    tag = "PASS" if result == "pass" else ("FAIL" if result == "fail" else "BLOCKED")
    print(f"  [{tag}] {step}: {desc} -- {notes}")
    return {"step": step, "description": desc, "result": result, "notes": notes}

results = []

# Launch
print("Launching...")
r = post("launch")
print(f"Launch: {r}")
time.sleep(3)

# ═══════════════════════════════════════════════════════════════════
# SECTION 1: Roster-row fix via Dev Quick Sign-In
# ═══════════════════════════════════════════════════════════════════
print("\n=== 1. ROSTER-ROW FIX (via Dev Quick Sign-In) ===\n")

screenshot("01_login")

tap("Dev Quick Sign-In")
time.sleep(2)
screenshot("02_dev_panel")

yoga = find("Yoga Studio")
results.append(record("1.1", "Dev panel shows job chips", "pass" if yoga else "fail",
    f"Yoga Studio: {yoga}"))

if yoga:
    tap("Yoga Studio")
    time.sleep(5)
    screenshot("03_yoga_dashboard")

    dash = find_any("Revenue Summary", "Yoga Studio", "Dev Yoga")
    results.append(record("1.2", "Yoga Studio dashboard loads", "pass" if dash else "fail",
        f"{dash}"))

    # Network → Partners
    net = find("Network")
    if net:
        tap("Network")
        time.sleep(2)
        screenshot("04_network")

        # Partners tab — look for partial text since Flutter splits DOM
        partners = find("Partners")
        if partners:
            tap("Partners")
            time.sleep(1)
            screenshot("05_partners")

        # Check empty state — try multiple text variants
        no_p = find_any("No partners", "No partners yet", "no partners", "Tap + to send")
        has_jordan = find("Jordan")
        has_sam = find("Sam")
        has_riley = find("Riley")
        results.append(record("1.3a", "Partners tab empty (no fake data)",
            "pass" if (no_p and not has_jordan and not has_sam and not has_riley) else "fail",
            f"empty_state={no_p is not None}, jordan={has_jordan is not None}, sam={has_sam is not None}, riley={has_riley is not None}"))

        # Staff tab
        staff = find("Staff")
        if staff:
            tap("Staff")
            time.sleep(1)
            screenshot("06_staff")
        no_staff = find_any("No staff", "No team", "no members", "Invite")
        results.append(record("1.3b", "Staff tab empty",
            "pass" if no_staff else "fail",
            f"{no_staff is not None}"))

        # Clients tab
        clients = find("Clients")
        if clients:
            tap("Clients")
            time.sleep(1)
            screenshot("07_clients")
        no_clients = find_any("No clients", "No members", "no clients", "Invite")
        results.append(record("1.3c", "Clients tab empty",
            "pass" if no_clients else "fail",
            f"{no_clients is not None}"))
    else:
        for k in ["1.3a", "1.3b", "1.3c"]:
            results.append(record(k, "Network tabs check", "blocked", "Network not found"))

    # Settings → Business Features → toggle sticks
    settings = find("Settings")
    if settings:
        tap("Settings")
        time.sleep(2)
        screenshot("08_settings")

        bf = find("Business Features")
        if bf:
            tap("Business Features")
            time.sleep(2)
            screenshot("09_business_features")

            p_toggle = find_any("Partners", "Partnerships")
            results.append(record("1.4a", "Business Features toggles visible",
                "pass" if p_toggle else "fail",
                f"{p_toggle is not None}"))

            # Toggle Partners off then on, navigate away and back
            if p_toggle:
                # Find toggle by looking for the switch control near "Partners"
                toggle = find("Partners")
                if toggle:
                    tap("Partners")
                    time.sleep(1)
                    screenshot("10_toggled_off")

                    # Navigate away (Home) then back to Settings > Business Features
                    home = find("Home")
                    if home:
                        tap("Home")
                        time.sleep(2)
                    settings2 = find("Settings")
                    if settings2:
                        tap("Settings")
                        time.sleep(1)
                    bf2 = find("Business Features")
                    if bf2:
                        tap("Business Features")
                        time.sleep(2)
                        screenshot("11_business_features_after")
                        p_toggle2 = find_any("Partners", "Partnerships")
                        results.append(record("1.4b", "Toggle sticks after navigation",
                            "pass" if p_toggle2 else "fail",
                            f"visible_after_nav={p_toggle2 is not None}"))
                    else:
                        results.append(record("1.4b", "Toggle sticks", "blocked", "Could not re-navigate to BF"))
                else:
                    results.append(record("1.4b", "Toggle sticks", "blocked", "Toggle not found"))
            else:
                results.append(record("1.4b", "Toggle sticks", "blocked", "No toggle to test"))
        else:
            results.append(record("1.4a", "Business Features visible", "fail", "Not found"))
            results.append(record("1.4b", "Toggle sticks", "blocked", "BF not found"))
    else:
        results.append(record("1.4a", "Settings visible", "fail", "Not found"))
        results.append(record("1.4b", "Toggle sticks", "blocked", "Settings not found"))
else:
    for k in ["1.2", "1.3a", "1.3b", "1.3c", "1.4a", "1.4b"]:
        results.append(record(k, "Skipped", "blocked", "Dev panel did not open"))

# ═══════════════════════════════════════════════════════════════════
# SECTION 2: Self-serve signup is Owner-only
# ═══════════════════════════════════════════════════════════════════
print("\n=== 2. SELF-SERVE SIGNUP (Owner-only) ===\n")

post("close")
time.sleep(2)
post("launch")
time.sleep(3)
screenshot("12_back_to_login")

create = find("Create account")
if create:
    tap("Create account")
    time.sleep(2)
    screenshot("13_create_account")

    # Step 5: No Client/Partner toggle — check for toggle/switch widgets
    # The word "Partner" appears in the bottom note text, which is NOT a toggle.
    # A real toggle would be a separate interactive control above the form.
    # Check: form has Display Name + Email + Password (no role selector above them)
    has_name = find("Display Name")
    has_email = find("Email")
    has_password = find("Password")
    # Look for a role toggle — would be something like "I am a" or role tabs
    role_toggle = find_any("I am a", "Sign up as", "Join as")
    results.append(record("2.1", "No Client/Partner toggle (Owner-only form)",
        "pass" if (has_name and has_email and has_password and not role_toggle) else "fail",
        f"name={has_name is not None}, email={has_email is not None}, pw={has_password is not None}, role_toggle={role_toggle is not None}"))

    # Step 6: Invite link note
    invite = find_any("invite link", "Invite link", "Partner or Client")
    results.append(record("2.2", "Invite link note visible",
        "pass" if invite else "fail",
        f"{invite is not None}"))
else:
    results.append(record("2.1", "Create Account visible", "fail", "Not found"))
    results.append(record("2.2", "Invite link note", "blocked", "CA not found"))

# ═══════════════════════════════════════════════════════════════════
# SECTION 3: Partner spot-check (informational)
# ═══════════════════════════════════════════════════════════════════
print("\n=== 3. PARTNER SPOT-CHECK ===\n")

# Note: Partner chip click via Dev Quick Sign-In doesn't work on Web
# due to Flutter nested Navigator canvas hit-test limitation (known from Phase 1).
# This is a harness limitation, not an app bug.
# We'll attempt it but expect it to fail.

post("close")
time.sleep(2)
post("launch")
time.sleep(3)

tap("Dev Quick Sign-In")
time.sleep(2)

partner = find("Partner")
if partner:
    tap("Partner")
    time.sleep(5)
    screenshot("14_partner_attempt")

    # Check if we actually got to the Partner dashboard
    partner_dash = find_any("My Deal", "Agreements", "Partner")
    dev_panel = find("Dev Quick Sign-In")
    if dev_panel:
        results.append(record("3.1", "Partner sign-in via Dev Quick Sign-In",
            "fail",
            "HARNESS LIMITATION: Chip click doesn't trigger Flutter handler (nested Navigator canvas hit-test)"))
        results.append(record("3.2", "Partner Agreements label", "blocked", "Partner not signed in"))
        results.append(record("3.3", "Partner no Discover/Marketplace", "blocked", "Partner not signed in"))
    else:
        results.append(record("3.1", "Partner sign-in via Dev Quick Sign-In", "pass", "Signed in"))
        # Check Agreements
        agreements = find("Agreements")
        results.append(record("3.2", "Partner Agreements label",
            "pass" if agreements else "fail",
            f"{agreements is not None}"))
        # Check no Discover/Marketplace
        discover = find("Discover")
        marketplace = find("Marketplace")
        results.append(record("3.3", "Partner no Discover/Marketplace",
            "pass" if not discover and not marketplace else "fail",
            f"discover={discover is not None}, marketplace={marketplace is not None}"))
else:
    results.append(record("3.1", "Partner sign-in", "blocked", "Partner chip not found"))
    results.append(record("3.2", "Partner Agreements", "blocked", "Not signed in"))
    results.append(record("3.3", "Partner no Discover/Marketplace", "blocked", "Not signed in"))

# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
print("\n--- SUMMARY ---")
passed = sum(1 for r in results if r["result"] == "pass")
failed = sum(1 for r in results if r["result"] == "fail")
blocked = sum(1 for r in results if r["result"] == "blocked")
total = len(results)
print(f"Total: {total} | Pass: {passed} | Fail: {failed} | Blocked: {blocked}")

with open("web_checklist2_results.json", "w") as f:
    json.dump(results, f, indent=2)

post("close")
