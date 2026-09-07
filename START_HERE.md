# Start Here — Instructions for the AI Agent

You're running inside the `ai-test-harness` folder on the user's own PC.
**Your job: make this test harness actually work, fixing whatever is
broken along the way, then report back in plain language.**

## Context you need

This harness lets an AI agent (you) click through a real app's UI like a
human tester would, by driving it through `testctl.py`. It was written by
another AI in a sandboxed environment with no browser, no emulator, and
no real Windows desktop to test on — so **nothing in this folder has been
confirmed to actually run yet**. Treat every file as a first draft that
needs real-world debugging, not finished code. That debugging is your job.

Read `README.md` in this same folder for the full explanation of what
each piece does before you start.

---

## Step 1 — Install dependencies

```
pip install playwright
python -m playwright install chromium
```

If either of these fails, fix the environment first (missing Python,
permissions, PATH issues, etc.) — don't move on with a broken install.

## Step 2 — Run the smoke test and fix anything that breaks

`README.md` has a section called **"Smoke test"** — follow it exactly.
It points at a real, trivial public website instead of the user's actual
app, specifically so that if something fails, you know the problem is in
the harness itself, not in their app.

**If any step fails: don't just report it and stop.** Read the actual
error, open whichever file is responsible (`testctl.py`,
`adapters/web_playwright.py`, or `mcp_server.py`), find the real bug, and
fix it. Then re-run the smoke test from the top. Repeat until it fully
passes. This back-and-forth is expected — you're debugging a draft, not
running something already proven to work.

Things worth checking if something breaks:
- Port `8765` already in use on this PC → change `DEFAULT_PORT` near the
  top of `testctl.py`, or free the port
- Playwright's browser binary missing → re-run
  `python -m playwright install chromium`
- Any Python import error → `pip install` whatever it's complaining about
- Any logic bug you find in `testctl.py` or the adapter — just fix it
  directly, this code has not been tested by anyone yet

## Step 3 — Once the smoke test fully passes, test the real project

1. Ask the user where the actual Flutter project lives on this PC if you
   don't already know (it's the `personal-wellness-trainer` repo).
2. Get it running so it's actually serving somewhere
   (`flutter run -d chrome` from inside that project's folder). If
   Flutter itself won't run, that's a project/environment issue — flag it
   to the user rather than trying to fix Flutter's own setup yourself.
3. Confirm the URL it's running on matches what's in
   `projects/pwt.config.json` in this folder — update that file if not.
4. Start the harness server (leave it running):
   `python testctl.py --project pwt serve`
5. Open `TESTING_CHECKLIST.md` in the project's repo — that's the actual
   checklist to work through, item by item, using `testctl.py` commands
   (`launch`, `screenshot`, `find`, `tap`, `type`, `close`).
6. For every single item, actually confirm the expected result happened
   (via `find`/`screenshot`) before marking it passed — don't assume
   something worked just because no error was thrown.

## Step 4 — Write up what happened

Create a new file, `SETUP_REPORT.md`, in this same `ai-test-harness`
folder, using the shape in `templates/REPORT_TEMPLATE.md`, and make sure
it covers, in plain language:

1. **Did the harness itself work in the end?** (pass/fail on the smoke
   test, after your fixes)
2. **What did you have to fix to get there?** List every bug you found
   and changed, in plain English, not just a diff — this is going to a
   non-programmer.
3. **Full results of the real `TESTING_CHECKLIST.md` run** — every item,
   pass or fail, not just the failures.
4. **Anything you genuinely couldn't test and why** (e.g. no Android
   emulator available in this session, a Windows-only limitation, etc).

## Boundaries — please respect these

- **Don't modify the actual Flutter app's source code.** You're testing
  it, not changing it — if you find a real bug *in the app* (not in the
  harness), write it up in `SETUP_REPORT.md` under its own section
  instead of fixing it yourself. The user will decide what to do with it.
- Fixing the **harness code** (`testctl.py`, the adapters, `mcp_server.py`)
  is fully in-scope and expected — that code has no owner yet but you.
- If you get stuck on something that seems to need a real Android
  emulator or a Windows-desktop-specific fix and neither is set up yet,
  say so plainly in the report rather than spending excessive time
  guessing at code you can't actually verify.
