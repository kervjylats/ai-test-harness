#!/usr/bin/env python3
"""
mcp_server.py — thin MCP wrapper around testctl's server, for agents that
prefer structured MCP tool calls over shelling out (opencode, Claude Code,
etc). This is a BONUS layer, not a requirement — every agent can already
drive the app via plain `python testctl.py ...` shell calls regardless of
whether it has this wired up. Skip this file entirely for Hermes/Ollama or
a Groq-backed CLI unless you've specifically set up an MCP bridge for them
(e.g. MCPHost) — plain shell access to testctl.py works for those too and
is simpler to get running first.

Setup:
    pip install mcp

Then point opencode (or Claude Code, etc) at this the normal way MCP
servers are configured for that tool — see README.md for the exact config
snippet.

This assumes `python testctl.py --project <name> serve` is ALREADY running
in another terminal — this file is just a translator, it doesn't launch
the app itself.
"""

import sys
from mcp.server.fastmcp import FastMCP

# Reuse testctl's own client function so there's exactly one place that
# knows how to talk to the running server — no duplicated HTTP logic.
from pathlib import Path

# Reuse testctl's own client function so there's exactly one place that
# knows how to talk to the running server — no duplicated HTTP logic.
# (Path-based so this works on Windows backslash paths as well as POSIX.)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from testctl import _post, DEFAULT_PORT  # noqa: E402

mcp = FastMCP("test-harness")

PORT = DEFAULT_PORT  # override below if you run testctl on a different port


@mcp.tool()
def app_launch() -> dict:
    """Launch the app under test (must call this before anything else)."""
    return _post(PORT, "launch")


@mcp.tool()
def app_screenshot(out_path: str) -> dict:
    """Save a screenshot of the current app state to out_path (PNG)."""
    return _post(PORT, "screenshot", out_path=out_path)


@mcp.tool()
def app_find(text: str) -> dict:
    """Check whether `text` is visible anywhere on the current screen."""
    return _post(PORT, "find", text=text)


@mcp.tool()
def app_tap(text: str) -> dict:
    """Find `text` on screen and tap its center."""
    return _post(PORT, "tap", text=text)


@mcp.tool()
def app_type(text: str) -> dict:
    """Type text into whatever currently has focus (tap a field first)."""
    return _post(PORT, "type", text=text)


@mcp.tool()
def app_close() -> dict:
    """Close the app under test and end the session."""
    return _post(PORT, "close")


if __name__ == "__main__":
    mcp.run()
