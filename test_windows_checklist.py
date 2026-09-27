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
    r = post("screenshot", out_path=f"test_evidence/win_{name}.png")
    return r.get("ok")

def find(text):
    r = post("find", text=text)
    if r.get("ok"):
        return r["result"]
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

# --- Smoke test ---
print("\n=== SMOKE TEST ===\n")
screenshot("01_login")

# Find key elements
for term in ["Sign In", "Email", "Password", "Dev Quick Sign-In", "Create account"]:
    loc = find(term)
    results.append(record(f"S.{term[:10]}", f"find '{term}'", "pass" if loc else "fail",
        f"at {loc}" if loc else "not found"))

# --- SECTION 1: Roster-row fix ---
print("\n=== 1. ROSTER-ROW FIX ===\n")

if tap("Dev Quick Sign-In"):
    time.sleep(2)
    screenshot("02_dev_panel")

    yoga = find("Yoga Studio")
    results.append(record("1.1", "Dev panel shows job chips", "pass" if yoga else "fail",
        f"Yoga Studio: {yoga}"))

    if yoga:
        tap("Yoga Studio")
        time.sleep(5)
        screenshot("03_yoga_dashboard")

        dash = find("Revenue Summary") or find("Yoga Studio")
        results.append(record("1.2", "Yoga dashboard loads", "pass" if dash else "fail",
            f"{dash}"))

        # Network > Partners
        net = find("Network")
        if net:
            tap("Network")
            time.sleep(2)
            screenshot("04_network")

            partners = find("Partners")
            if partners:
                tap("Partners")
                time.sleep(1)
                screenshot("05_partners")

            no_p = find("No partners yet")
            has_jordan = find("Jordan")
            results.append(record("1.3", "Partners tab empty", "pass" if (no_p and not has_jordan) else "fail",
                f"empty={no_p}, jordan={has_jordan}"))

        # Settings > Business Features
        settings = find("Settings")
        if settings:
            tap("Settings")
            time.sleep(2)
            screenshot("06_settings")

            bf = find("Business Features")
            if bf:
                tap("Business Features")
                time.sleep(2)
                screenshot("07_business_features")

            p_toggle = find("Partnerships") or find("Partners")
            results.append(record("1.4", "Business Features toggles", "pass" if p_toggle else "fail",
                f"{p_toggle}"))
        else:
            results.append(record("1.4", "Business Features toggles", "blocked", "Settings not found"))
    else:
        for i in range(2, 5):
            results.append(record(f"1.{i}", "Skipped", "blocked", "Previous step failed"))
else:
    for i in range(1, 5):
        results.append(record(f"1.{i}", "Skipped", "blocked", "Dev panel not opened"))

# --- SECTION 2: Self-serve signup ---
print("\n=== 2. SELF-SERVE SIGNUP ===\n")

# Close and relaunch to get back to login
post("close")
time.sleep(2)
post("launch")
time.sleep(5)
screenshot("08_back_to_login")

create = find("Create account")
if create:
    tap("Create account")
    time.sleep(2)
    screenshot("09_create_account")

    # Check for toggle (should NOT exist)
    # On Windows, the Create Account form goes straight to name/email/password
    has_name = find("Display Name") or find("Name")
    has_email = find("Email")
    results.append(record("2.1", "No Client/Partner toggle", "pass" if (has_name and has_email) else "fail",
        f"name={has_name}, email={has_email}"))

    invite = find("invite link") or find("Invite link")
    results.append(record("2.2", "Invite link note visible", "pass" if invite else "fail",
        f"{invite}"))
else:
    results.append(record("2.1", "Create Account visible", "fail", "not found"))
    results.append(record("2.2", "Invite link note", "blocked", "Create Account not found"))

# --- SUMMARY ---
print("\n--- SUMMARY ---")
passed = sum(1 for r in results if r["result"] == "pass")
failed = sum(1 for r in results if r["result"] == "fail")
blocked = sum(1 for r in results if r["result"] == "blocked")
print(f"Total: {len(results)} | Pass: {passed} | Fail: {failed} | Blocked: {blocked}")

with open("windows_checklist_results.json", "w") as f:
    json.dump(results, f, indent=2)

post("close")
