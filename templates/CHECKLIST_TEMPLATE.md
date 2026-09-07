# <Project Name> — Agent Test Checklist

Instructions for the agent running this checklist:
- The app is already launched (or launch it first with the `app_launch` /
  `python testctl.py --project <name> launch` action).
- For each numbered step: perform the action, then use `app_screenshot` /
  `find` to confirm the expected result actually happened before moving on.
- Do not guess — if `find` comes back false for something a step expects
  to see, that is a FAIL, not a reason to assume it's fine and continue.
- Write every result (pass or fail) to the report using REPORT_TEMPLATE.md's
  format, one entry per step. Don't skip logging passes — a checklist with
  only failures listed can't be told apart from one that wasn't run.
- If a step's precondition (something an earlier step should have set up)
  isn't met, mark it FAIL with "blocked by step N" rather than skipping
  silently.

---

## Section: <e.g. "Sign up & onboarding">

1. [ ] <Action> — Expected: <what should be true after>
2. [ ] <Action> — Expected: <what should be true after>

## Section: <e.g. "Role X">

3. [ ] ...

---

## Notes for whoever wrote this checklist

- List anything here that's known to NOT be testable by an automated
  agent (e.g. "actually clicking a real invite link across two devices,"
  "real payment processing") — same idea as the "what won't be effective
  to test" section in TESTING_CHECKLIST.md. Saves the agent from filing a
  false failure for something that was never expected to work this way.
