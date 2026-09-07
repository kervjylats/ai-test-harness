# AI Test Harness

Point any AI coding agent (opencode, a Groq-backed CLI, Hermes via Ollama,
whatever you pick up later) at a running app and have it click through a
checklist like a human tester would — then write back a findings report
in the same format every time, regardless of which agent or platform ran
it.

**Reusable across every project** — the checklist format, the report
format, and the driver (`testctl.py`) never change. Adding a new project
is just: write a checklist, add one small config file, done.

⚠️ **Nothing in this folder has been run yet.** It was written in a
sandboxed environment with no browser, no Android emulator, and no
Windows desktop — so treat everything here as a solid first draft to
smoke-test, not something already proven working. The smoke test below
is designed to catch problems cheaply before you point this at a real app.

---

## One-time setup

```bash
cd ai-test-harness
pip install playwright
python -m playwright install chromium
```

(Only need `pip install Appium-Python-Client` / `pip install pywinauto`
once you actually get to the Android or Windows adapters — skip for now.)

## Smoke test — do this FIRST, before pointing it at any real app

This confirms the plumbing itself (server, HTTP client, screenshot, find,
tap) actually works, using a trivial public page instead of your app, so
if something's broken you're not simultaneously debugging your Flutter
build too.

```bash
# create a throwaway config pointing at a real, simple website
echo '{"platform": "web", "url": "https://example.com", "headless": false}' > projects/smoketest.config.json

# terminal 1 — leave this running
python testctl.py --project smoketest serve

# terminal 2
python testctl.py --project smoketest launch
python testctl.py --project smoketest screenshot smoke.png
python testctl.py --project smoketest find "Example Domain"
python testctl.py --project smoketest close
```

You should see a `smoke.png` appear, and the `find` command should print
`{"ok": true, "result": {...}}`. If that all works, the harness itself is
sound — anything you hit after this point is specific to your app, not
the harness.

## Testing your actual project

1. `flutter run -d chrome` (or serve your `flutter build web` output) —
   get it running at some `localhost` URL first, same as always.
2. Copy `projects/PROJECT.config.example.json` → `projects/<name>.config.json`,
   fill in the `url`.
3. Write (or adapt) a checklist in `templates/CHECKLIST_TEMPLATE.md`'s
   format — for Personal Wellness Trainer, you already have one:
   `TESTING_CHECKLIST.md` in the project repo. An agent can read that
   directly; it doesn't strictly need to be rewritten into the template
   shape, the template's just there for *new* projects that don't have
   one yet.
4. Start the server: `python testctl.py --project <name> serve`
5. Point your agent at the checklist and tell it to work through it using
   `testctl.py` commands (see per-agent wiring below), writing results
   into `REPORT_TEMPLATE.md`'s format as it goes.

---

## Wiring this into each agent you mentioned

### opencode (easiest — native MCP support)

Two options, pick one:

**A. Plain shell (simplest, works immediately, no extra setup):**
Just tell opencode, in your prompt: *"You have a CLI tool at
`ai-test-harness/testctl.py`. Read `ai-test-harness/README.md` for usage.
Work through `TESTING_CHECKLIST.md` using it, and write your findings to
`report.md` using `ai-test-harness/templates/REPORT_TEMPLATE.md`'s
format."* opencode can already run shell commands — nothing to configure.

**B. MCP (nicer tool-call UX, a bit more setup):**
```bash
pip install mcp
```
Then add to opencode's MCP config (`opencode mcp add`, or edit its config
file directly):
```json
{
  "mcpServers": {
    "test-harness": {
      "command": "python",
      "args": ["/absolute/path/to/ai-test-harness/mcp_server.py"]
    }
  }
}
```
Either way, `python testctl.py --project <name> serve` still needs to be
running in its own terminal first — the MCP server is just a translator
on top, it doesn't launch the app itself.

### Groq-backed CLI

Depends entirely on which specific CLI you're using in front of Groq's
API — if you tell me which one, I can give exact wiring. Until then: the
plain-shell approach (option A above) works with essentially anything
that can execute a shell command, which covers the large majority of
these tools without any special setup.

### Hermes via Ollama

Ollama itself doesn't speak MCP natively — you'd need a separate bridge
tool (e.g. MCPHost) to get MCP working with it, which is an extra moving
part worth avoiding for now. Simplest path: whatever thin agent/script
you're using to drive Hermes, just give it shell access and the same
plain-shell instructions as above. If your Hermes setup already goes
through a framework that supports "tools"/"functions" generically, wire
those directly to `python testctl.py ...` calls the same way.

### Anything else you pick up later

If it can run a shell command at all, point it at `testctl.py` the same
way — that's the entire point of building the universal layer as a CLI
instead of betting on MCP support existing everywhere.

---

## Adapter status

| Platform | File | Status |
|---|---|---|
| Web (Flutter Web / any web app) | `adapters/web_playwright.py` | Fully built — start here |
| Android (emulator, incl. Expo/RN) | `adapters/android_appium.py` | Scaffolded — needs your Appium+emulator to finish/verify |
| Windows desktop | `adapters/windows_desktop.py` | Scaffolded — the roughest tier, build this last |

## Extending to a 4th platform later

Implement `adapters/base.py`'s 6 methods for whatever it is (iOS
simulator via Appium/XCUITest would follow the exact same shape as the
Android adapter, for instance), register it in `get_adapter()` inside
`testctl.py`, and every checklist/report/agent-wiring piece above keeps
working unchanged.
