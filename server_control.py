"""
server_control.py - shared, on-demand web server for the built Flutter bundle.

Why this exists
---------------
The app itself needs NO server (run it normally with `flutter run -d windows`
or `flutter run -d chrome`). This static file server exists ONLY so the
Playwright suite / game / probes have a stable URL to drive.

It runs on demand: started by ensure_server() when a harness script needs it,
and stop_server() tears it down afterwards so nothing lingers in the
background. There is deliberately no auto-restart anywhere.

Port history
------------
Was 8080 until Round 7. 8080 is the LocalAI hub's `big` slot port
(C:\\LocalAI\\hub_server.py SLOT_PORTS = {"big": 8080, ...}) - serving our
bundle there blocked seven of the hub's models from starting. New default is
9090 (verified free: hub owns 8080-8085+ growing from 8083, hub itself 5000,
adhd-pill dev server 4173, old harness scripts 8765).

Override with env var PWT_WEB_PORT if 9090 is ever taken.

Usage
-----
    python server_control.py status    # print state + exit 0 if up
    python server_control.py start     # start if not already up
    python server_control.py stop      # stop it (only ours - port 9090)

Programmatic:
    from server_control import BASE, ensure_server, stop_server
    ensure_server()   # safe to call repeatedly; no-op if already listening
    ...
    stop_server()     # call at end of a run when you started it
"""
import os
import socket
import subprocess
import sys
import time

PORT = int(os.environ.get("PWT_WEB_PORT", "9090"))
BASE = f"http://localhost:{PORT}"
WEB_DIR = r"C:\DEV\Projects\personal-wellness-trainer-main\build\web"

# The process WE started in this interpreter (None if server was already
# up, or we didn't start it). stop_server() only kills a listener on our
# dedicated port, so it can never touch an unrelated process.
_OUR_PROC = None


def is_up(port=PORT, timeout=0.4):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_server(web_dir=WEB_DIR, port=PORT):
    """Start the static server if nothing is listening yet. Idempotent."""
    global _OUR_PROC
    if is_up(port):
        return True
    _OUR_PROC = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--directory", web_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for the bind instead of a blind sleep - slow machines need longer.
    for _ in range(40):
        if is_up(port):
            return True
        time.sleep(0.25)
    print(f"FATAL: server did not come up on :{port}", file=sys.stderr)
    return False


def _listener_pid(port=PORT):
    """PID bound to our port via netstat (authoritative, no psutil dep)."""
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, creationflags=0x08000000,
        ).stdout
    except OSError:
        return None
    for line in out.splitlines():
        parts = line.split()
        # TCP   127.0.0.1:9090   ...   LISTENING   <pid>
        if len(parts) >= 5 and parts[3] == "LISTENING":
            local = parts[1]
            if local.endswith(f":{port}"):
                try:
                    return int(parts[4])
                except ValueError:
                    return None
    return None


def stop_server(port=PORT):
    """Stop the static server on OUR dedicated port. No-op if not listening.

    Only touches whatever is bound to the harness port - it can never kill an
    unrelated process. Returns True if a listener was stopped.
    """
    global _OUR_PROC
    if _OUR_PROC is not None and _OUR_PROC.poll() is None:
        _OUR_PROC.terminate()
        try:
            _OUR_PROC.wait(timeout=5)
        except Exception:
            _OUR_PROC.kill()
        _OUR_PROC = None
        return True

    # Started by an earlier process (or the CLI) - find it by port.
    pid = _listener_pid(port)
    if pid is None:
        return False
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, creationflags=0x08000000,
        )
    except OSError:
        return False
    return True


def _main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "status":
        up = is_up()
        print(f"port {PORT}: {'UP' if up else 'DOWN'} ({BASE})")
        return 0 if up else 1
    if cmd == "start":
        ok = ensure_server()
        print(f"port {PORT}: {'UP' if ok else 'FAILED'} ({BASE})")
        return 0 if ok else 1
    if cmd == "stop":
        stopped = stop_server()
        print(f"port {PORT}: {'stopped' if stopped else 'not running'}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))