# Phase 2 — Finish the Android and Windows Adapters

You already got the Web adapter working in Phase 1 (see `SETUP_REPORT.md`
for that history). This phase is the same kind of work, applied to the
two adapters that were only ever scaffolded, never run:
`adapters/android_appium.py` and `adapters/windows_desktop.py`.

Do Android first, all the way through. Only move to Windows once Android
is genuinely working — Windows is the rougher of the two (Flutter's
Windows accessibility-tree output is less mature), so don't split effort
across both at once.

---

## Android

### Setup

```
npm install -g appium
appium driver install uiautomator2
pip install Appium-Python-Client
```

You'll need:
- An Android emulator already running (Android Studio's Device Manager,
  or `emulator -avd <name>` from the command line) — the user has one set
  up already, ask them which AVD to use if it's not obvious.
- The Appium server running in its own terminal: `appium`
- A debug build of the Flutter app:
  ```
  cd <path to personal-wellness-trainer>
  flutter build apk --debug
  ```
  The APK lands under `build/app/outputs/flutter-apk/app-debug.apk`.

### Config

Create `projects/pwt-android.config.json`:
```json
{
  "platform": "android",
  "apk_path": "<full path to app-debug.apk>",
  "app_package": "<check android/app/src/main/AndroidManifest.xml for this>",
  "app_activity": ".MainActivity",
  "device_name": "<from `adb devices`, e.g. emulator-5554>"
}
```

### Verify, the same way Phase 1 did

```
python testctl.py --project pwt-android serve      # terminal 1
python testctl.py --project pwt-android launch      # terminal 2
python testctl.py --project pwt-android screenshot android_smoke.png
python testctl.py --project pwt-android find "Sign"  # or whatever text should be on the login screen
python testctl.py --project pwt-android close
```

**If any step fails: debug and fix `adapters/android_appium.py` directly,
the same way you fixed `web_playwright.py` in Phase 1.** Its docstring
already flags the parts most likely to need adjustment — start there.
Known rough edges to expect:
- `find_text`'s `UiSelector().textContains(...)` approach may need
  tuning depending on how Flutter's semantics tree actually renders on
  this specific Android/Flutter version combo — if it's not finding text
  you can see in a screenshot, that's the first thing to investigate.
- Timing: emulators are slower than a desktop Chrome instance: launch
  needs a real pause before the widget tree is ready. Increase
  `new_command_timeout` or add explicit waits if you see race conditions.

Once `find`/`tap`/`screenshot` work reliably against the login screen,
confirm the interface's optional `find_in_region`/`tap_in_region`
methods (added in the last Web round, for multi-panel pages like the QA
Console) — implement them for Android too if you get this far, following
the same pattern as `web_playwright.py`'s versions.

### Then run the real checklist

Once the adapter itself is solid, work through
`TESTING_CHECKLIST_2.md` (or whichever is the latest checklist in the
`personal-wellness-trainer` repo) against the Android build, the same
way Phase 1 did for Web — screenshots, pass/fail per step, written up.

---

## Windows (only after Android is done)

### Setup
```
pip install pywinauto
```

```
cd <path to personal-wellness-trainer>
flutter build windows
```
The `.exe` lands under `build/windows/x64/runner/Release/`.

### Config

Create `projects/pwt-windows.config.json`:
```json
{
  "platform": "windows",
  "exe_path": "<full path to the .exe>",
  "window_title": "<whatever the window's title bar actually says>"
}
```

### Verify

Same pattern as Android above — `serve`/`launch`/`screenshot`/`find`/
`close`, fix `adapters/windows_desktop.py` directly when something
breaks. Its docstring already warns this is the roughest tier — budget
real debugging time, and it's fine if this one ends up needing more
back-and-forth than Web or Android did.

---

## Write it up

Append a new section to `SETUP_REPORT.md` (don't overwrite the existing
Phase 1 history) covering:
1. What you had to fix in each adapter, in plain language
2. Whether each platform's smoke-equivalent ultimately passed
3. Full results of running the real checklist against each platform, once
   the adapter itself was solid enough to attempt it
4. Anything you got stuck on and couldn't resolve — say so plainly rather
   than reporting a false pass
