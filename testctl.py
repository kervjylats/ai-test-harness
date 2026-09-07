#!/usr/bin/env python3
"""
testctl.py — the universal driver. Any agent that can run a shell command
can drive an app through this, regardless of whether it speaks MCP.

WHY THIS RUNS AS A SERVER (not "one CLI call per action" directly):
Playwright/Appium/pywinauto handles wrap live OS-level connections (a
browser pipe, a device socket, a window handle) that cannot be saved to
disk and reloaded in a new process — there's no way around that. So
testctl runs as a small local HTTP server that holds the live adapter in
memory; the CLI commands you actually call are lightweight requests to
that server. This is the same pattern Appium and opencode itself use
(`appium` runs as a server; `opencode serve` + `opencode attach` is the
same split for exactly this reason).

Usage — two terminals:

  Terminal 1 (leave running):
      python testctl.py --project pwt serve

  Terminal 2 (or: what an agent actually calls, one line per action):
      python testctl.py --project pwt launch
      python testctl.py --project pwt screenshot out.png
      python testctl.py --project pwt find "Sign In"
      python testctl.py --project pwt tap "Sign In"
      python testctl.py --project pwt type "hello@example.com"
      python testctl.py --project pwt close

Every client command prints ONE line of JSON to stdout — that's the
contract an agent should parse:
    {"ok": true, "result": {"x": 640, "y": 220, "matched": "Sign In"}}
    {"ok": false, "error": "text not found: 'Sign In'"}
"""

import argparse
import json
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HARNESS_DIR = Path(__file__).parent
DEFAULT_PORT = 8765


def load_config(project: str) -> dict:
    path = HARNESS_DIR / "projects" / f"{project}.config.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No config at {path}. Copy templates/PROJECT.config.example.json "
            f"there and fill it in for this project."
        )
    return json.loads(path.read_text())


def get_adapter(config: dict):
    platform = config["platform"]
    if platform == "web":
        from adapters.web_playwright import WebPlaywrightAdapter
        return WebPlaywrightAdapter()
    if platform == "android":
        from adapters.android_appium import AndroidAppiumAdapter
        return AndroidAppiumAdapter()
    if platform == "windows":
        from adapters.windows_desktop import WindowsDesktopAdapter
        return WindowsDesktopAdapter()
    raise ValueError(f"Unknown platform '{platform}' in project config.")


# ── Server mode: holds the one live adapter instance ─────────────────────────

class _State:
    adapter = None
    config = None


def _make_handler():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # keep stdout clean — only the client side should print JSON

        def _reply(self, payload: dict, status: int = 200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            args = json.loads(self.rfile.read(length) or b"{}")
            command = self.path.strip("/")

            try:
                if command == "launch":
                    if _State.adapter is not None:
                        try:
                            _State.adapter.close()
                        except Exception:
                            pass
                    _State.adapter = get_adapter(_State.config)
                    _State.adapter.launch(_State.config)
                    self._reply({"ok": True, "result": "launched"})
                    return

                if _State.adapter is None:
                    self._reply(
                        {"ok": False, "error": "not launched — call 'launch' first"},
                        400,
                    )
                    return

                if command == "screenshot":
                    out = _State.adapter.screenshot(Path(args["out_path"]))
                    self._reply({"ok": True, "result": str(out)})

                elif command == "find":
                    result = _State.adapter.find_text(args["text"])
                    self._reply({"ok": result is not None, "result": result})

                elif command == "tap":
                    found = _State.adapter.find_text(args["text"])
                    if found is None:
                        self._reply({"ok": False, "error": f"text not found: '{args['text']}'"})
                        return
                    _State.adapter.tap(found["x"], found["y"])
                    self._reply({"ok": True, "result": found})

                elif command == "type":
                    _State.adapter.type_text(args["text"])
                    self._reply({"ok": True, "result": "typed"})

                elif command == "close":
                    _State.adapter.close()
                    _State.adapter = None
                    self._reply({"ok": True, "result": "closed"})

                else:
                    self._reply({"ok": False, "error": f"unknown command '{command}'"}, 404)

            except Exception as e:
                self._reply({"ok": False, "error": str(e)}, 500)

    return Handler


def run_server(project: str, port: int):
    _State.config = load_config(project)
    server = HTTPServer(("127.0.0.1", port), _make_handler())
    print(json.dumps({"ok": True, "result": f"serving project '{project}' on port {port}"}))
    sys.stdout.flush()
    server.serve_forever()


# ── Client mode: what an agent actually calls per action ─────────────────────

def _post(port: int, command: str, **args) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/{command}",
        data=json.dumps(args).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as e:
        return {
            "ok": False,
            "error": f"{e} — is the server running? "
                     f"(python testctl.py --project <name> serve)",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve")
    sub.add_parser("launch")
    p_screenshot = sub.add_parser("screenshot")
    p_screenshot.add_argument("out_path")
    p_find = sub.add_parser("find")
    p_find.add_argument("text")
    p_tap = sub.add_parser("tap")
    p_tap.add_argument("text", help="Finds this text on screen, then taps its center.")
    p_type = sub.add_parser("type")
    p_type.add_argument("text")
    sub.add_parser("close")

    args = parser.parse_args()

    if args.command == "serve":
        run_server(args.project, args.port)
        return

    if args.command == "screenshot":
        result = _post(args.port, "screenshot", out_path=args.out_path)
    elif args.command == "find":
        result = _post(args.port, "find", text=args.text)
    elif args.command == "tap":
        result = _post(args.port, "tap", text=args.text)
    elif args.command == "type":
        result = _post(args.port, "type", text=args.text)
    else:
        result = _post(args.port, args.command)

    print(json.dumps(result))
    if not result.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
