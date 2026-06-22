#!/usr/bin/env python3
"""Zero-install launcher for elm-mcp v2 — point your MCP host straight at THIS file.

For locked-down machines where you can't run terminal/pip commands yourself:

    1. Download the repo ZIP, extract it.
    2. Set your host's MCP command to your Python + the path to this file:
         "command": "python3",
         "args": ["/path/to/elm-mcp-v2-main/run_server.py"]
    3. (Done — no pip, no `cd`, no install command.)

On first launch this script:
  • checks Python is 3.10+,
  • makes sure its dependencies (mcp, httpx) are importable — installing them
    into the SAME interpreter your host launched, then re-execing — so the
    install happens INSIDE the process your host spawns, not as a command you
    have to type, and
  • adds this folder to the import path so the `elm_mcp_v2` package runs
    straight from the extracted ZIP with no `pip install` of the package.

Network note: the one-time dependency install needs to reach PyPI. That works
on machines that merely restrict YOU from running commands. On a fully
air-gapped box (no PyPI at all), use the bundled-deps variant instead (see
README) — there's no way to fetch packages with no network.
"""
import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Runtime dependencies (keep in sync with pyproject `dependencies`).
_DEPS = ["mcp>=1.0.0", "httpx>=0.27"]
_IMPORT_NAMES = ["mcp", "httpx"]


def _ensure_deps() -> None:
    if sys.version_info < (3, 10):
        sys.stderr.write(
            f"[elm-mcp-v2] Python 3.10+ is required — this interpreter is "
            f"{sys.version.split()[0]} ({sys.executable}). Point your host at a "
            f"newer Python.\n")
        sys.stderr.flush()
        sys.exit(1)

    missing = [m for m in _IMPORT_NAMES if importlib.util.find_spec(m) is None]
    if not missing:
        return

    if os.environ.get("ELM_MCP_V2_HEALED") == "1":
        # Installed once and still missing — don't loop. Likely pip put them in
        # a site that isn't on this interpreter's path, or install was blocked.
        sys.stderr.write(
            f"[elm-mcp-v2] Dependencies still missing after auto-install: "
            f"{', '.join(missing)}.\n[elm-mcp-v2] Install by hand with this exact "
            f"Python:\n    {sys.executable} -m pip install {' '.join(_DEPS)}\n")
        sys.stderr.flush()
        sys.exit(1)

    sys.stderr.write(
        f"[elm-mcp-v2] Missing dependencies {missing} — installing into "
        f"{sys.executable} (one-time, ~15-30s)...\n")
    sys.stderr.flush()

    base = [sys.executable, "-m", "pip", "install", *_DEPS,
            "--disable-pip-version-check", "-q"]
    ok = False
    for cmd in (base, base + ["--user"]):  # retry into user site if blocked
        try:
            subprocess.run(cmd, check=True, timeout=300)
            ok = True
            break
        except Exception:
            continue
    if not ok:
        sys.stderr.write(
            f"[elm-mcp-v2] Auto-install failed (offline, or PyPI blocked).\n"
            f"[elm-mcp-v2] Run manually: {sys.executable} -m pip install "
            f"{' '.join(_DEPS)}\n")
        sys.stderr.flush()
        sys.exit(1)

    sys.stderr.write("[elm-mcp-v2] Dependencies installed — restarting.\n")
    sys.stderr.flush()
    os.environ["ELM_MCP_V2_HEALED"] = "1"
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])


_ensure_deps()

# Run the package straight from the extracted folder — no `pip install` of the
# package itself needed.
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from elm_mcp_v2.server import cli  # noqa: E402

if __name__ == "__main__":
    cli()
