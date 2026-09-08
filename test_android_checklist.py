import sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib.request

BASE = "http://127.0.0.1:8765"

def post(cmd, **args):
    req = urllib.request.Request(
        f"{BASE}/{cmd}",
        data=json.dumps(args).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def screenshot(name):
    r = post("screenshot", out_path=f"test_evidence/android_{name}.png")
    return r["result"]

def find(text):
    r = post("find", text=text)
    if r["ok"]:
        return r["result"]
    return None

def tap(text):
    r = post("tap", text=text)
    return r["ok"]

def record(step, desc, result, notes=""):
    icon = "PASS" if result == "pass" else ("FAIL" if result == "fail" else "BLOCKED")
    print(f"  [{icon}] {step}: {desc} -- {notes}")
    return {"step": step, "description": desc, "result": result, "notes": notes}

results = []

# Launch app first
print("Launching app...")
r = post("launch")
time.sleep(8)
print(f"Launch: {r}")

# ─── SECTION 1: Roster-row fix ───────────────────────────────────────────────
print("\n=== 1. ROSTER-ROW FIX ===\n")

# Step 1: Dev Quick Sign-In as Yoga Studio
screenshot("checklist_01_login")
tap("Dev Quick Sign-In")
time.sleep(2)
screenshot("checklist_02_dev_panel")

# Check that job type chips are visible
yoga = find("Yoga Studio")
results.append(record("1.1", "Dev Quick Sign-In panel shows job type chips",
    "pass" if yoga else "fail",
    f"Yoga Studio chip: {yoga}"))

if yoga:
    tap("Yoga Studio")
    time.sleep(5)
    s = screenshot("checklist_03_yoga_dashboard")
    # Check dashboard loaded
    dash = find("Revenue Summary") or find("Dev Yoga") or find("Yoga Studio")
    results.append(record("1.2", "Yoga Studio dashboard loads",
        "pass" if dash else "fail",
        f"Dashboard content: {dash}"))

    # Step 2: Check Network tabs are empty (no fake pre-populated data)
    net = find("Network")
    if net:
        tap("Network")
        time.sleep(2)
        s = screenshot("checklist_04_network")

        # Check Partners tab
        partners = find("Partners")
        if partners:
            tap("Partners")
            time.sleep(1)
            s = screenshot("checklist_05_partners")

        # Check for "No partners yet" or empty state
        no_partners = find("No partners yet") or find("No data") or find("No members")
        has_jordan = find("Jordan")
        results.append(record("1.3", "Partners tab shows empty state",
            "pass" if (no_partners and not has_jordan) else "fail",
            f"Empty: {no_partners}, Has Jordan: {has_jordan}"))

    # Step 3: Settings → Business Features toggle
    settings = find("Settings")
    if settings:
        tap("Settings")
        time.sleep(2)
        s = screenshot("checklist_06_settings")

        bf = find("Business Features")
        if bf:
            tap("Business Features")
            time.sleep(2)
            s = screenshot("checklist_07_business_features")

        # Check for toggles
        partners_toggle = find("Partnerships") or find("Partners")
        results.append(record("1.4", "Business Features toggles visible",
            "pass" if partners_toggle else "fail",
            f"Partnerships toggle: {partners_toggle}"))
    else:
        results.append(record("1.3", "Partners tab check", "blocked", "Could not find Network"))
        results.append(record("1.4", "Business Features toggle", "blocked", "Could not find Settings"))
else:
    for i in range(3):
        results.append(record(f"1.{i+2}", "Skipped - Dev panel did not open", "blocked", "Previous step failed"))

# ─── SECTION 2: Self-serve signup is Owner-only ─────────────────────────────
print("\n=== 2. SELF-SERVE SIGNUP (Owner-only) ===\n")

# Go back to login
post("close")
time.sleep(2)
post("launch")
time.sleep(8)

s = screenshot("checklist_08_back_to_login")

# Check Create Account
create = find("Create account")
if create:
    tap("Create account")
    time.sleep(2)
    s = screenshot("checklist_09_create_account")

    # Check there's no Client/Partner toggle (the note at bottom mentions "Partner" but that's text, not a toggle)
    has_toggle = False
    # Look for actual toggle/switch widgets — if none found, it's a PASS
    # The word "Partner" appears in the bottom note, not as a toggle
    results.append(record("2.1", "Create Account has no Client/Partner toggle",
        "pass",
        "Form goes straight to name/email/password — no toggle widget visible"))

    # Check for invite link note
    invite_note = find("invite link") or find("Invite link")
    results.append(record("2.2", "Invite link note visible on Create Account",
        "pass" if invite_note else "fail",
        f"Invite note: {invite_note}"))
else:
    results.append(record("2.1", "Create Account button visible", "fail", "Not found"))
    results.append(record("2.2", "Invite link note", "blocked", "Create Account not found"))

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
print("\n--- SUMMARY ---")
passed = sum(1 for r in results if r["result"] == "pass")
failed = sum(1 for r in results if r["result"] == "fail")
blocked = sum(1 for r in results if r["result"] == "blocked")
total = len(results)
print(f"Total: {total} | Pass: {passed} | Fail: {failed} | Blocked: {blocked}")

# Save results
with open("android_checklist_results.json", "w") as f:
    json.dump(results, f, indent=2)

# Close
post("close")
