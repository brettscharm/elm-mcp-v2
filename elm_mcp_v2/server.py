"""elm-mcp v2 — the aggregating facade MCP server.

The host (Bob / Claude / Cursor) connects to THIS one server. It:
  1. opens an MCP client session to IBM's engineering-ai-hub (if configured),
  2. re-exposes the hub's tools (curated) so they're callable through us,
  3. adds elm-mcp's own authoring / orchestration tools on top.

=> one install, one login (the hub token lives in our config), one unified
toolset. If the hub isn't configured/reachable, we run STANDALONE with only
our own tools.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from . import __version__
from .hub import HubSession, hub_config
from . import lint as _lint

logging.basicConfig(
    stream=sys.stderr, level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S",
)
logger = logging.getLogger("elm-mcp-v2")

from mcp.server import Server
from mcp.types import Tool, ToolAnnotations, TextContent
import mcp.server.stdio

# Live hub session (set in main()); None => standalone mode.
_HUB: HubSession | None = None

# Hub tools we deliberately DO NOT re-expose (curation). Empty for v0.1.0 —
# everything the hub offers is passed through. As we add native authoring
# tools that supersede a hub primitive, add the hub tool name here.
_HIDE_HUB_TOOLS: set[str] = set()

_SERVER_INSTRUCTIONS = """\
elm-mcp v2 is an authoring + orchestration layer for IBM Engineering Lifecycle \
Management. It FEDERATES IBM's official engineering-ai-hub MCP server: the hub's \
tools (correct, config-aware reads/writes, linking, and SysML) are available \
through this same server, and elm-mcp adds its own authoring/workflow tools on \
top. You only connect to this one server.

Division of labour:
- Reading, searching, the raw commit (create/update/link), config management, \
and SysML → use the HUB tools (e.g. get_requirement, search_requirement, \
create_requirement, link_*). They are correct and config-aware.
- Drafting, quality-checking, and orchestration → use elm-mcp's own tools \
(prefix `elm_`). Flow: draft → `elm_lint_requirement` → commit via the hub's \
`create_requirement`.

`elm_health` shows whether the hub is federated and how many tools are live.\
"""

app = Server("elm-mcp-v2", version=__version__, instructions=_SERVER_INSTRUCTIONS)


# ── Our native tools ──────────────────────────────────────────
_OUR_TOOLS: list[Tool] = [
    Tool(
        name="elm_health",
        description=(
            "Show elm-mcp v2 status: version, whether the official "
            "engineering-ai-hub is federated, the hub's name/version, and how "
            "many tools are live (hub + ours). Use when the user asks 'are you "
            "connected', 'is the hub working', 'what version', or 'what can you do'."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
    ),
    Tool(
        name="elm_update",
        description=(
            "Update elm-mcp v2 in place to the latest GitHub release. Works for "
            "the download / point-at-a-file install — it fetches the latest "
            "version and replaces the files in the folder your host points at "
            "(no git needed). Use when the user says 'update yourself', 'update "
            "elm mcp', 'pull the latest', or 'are you up to date'. Tell the user "
            "to fully restart their host afterward. (For a pip/uvx install it "
            "instead tells you the uvx/pip command to run.)"
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    ),
    Tool(
        name="elm_lint_requirement",
        description=(
            "Check the quality of a requirement statement BEFORE writing it to "
            "ELM — flags vague/un-testable wording, missing 'shall', compound "
            "requirements, passive voice, and missing measurable criteria, with "
            "a 0-100 score and concrete suggestions. Runs with no ELM access. "
            "Use this between drafting a requirement and committing it via the "
            "hub's create_requirement. Pass `text` (one requirement)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The requirement statement to lint."}
            },
            "required": ["text"],
        },
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    ),
]
_OUR_TOOL_NAMES = {t.name for t in _OUR_TOOLS}


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Our tools + the (curated) hub tools, presented as one catalog."""
    tools = list(_OUR_TOOLS)
    if _HUB is not None and _HUB.connected:
        for t in await _HUB.list_tools():
            if t.name in _HIDE_HUB_TOOLS or t.name in _OUR_TOOL_NAMES:
                continue
            tools.append(t)
    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    arguments = arguments or {}

    # --- our native tools ---
    if name == "elm_health":
        if _HUB is not None and _HUB.connected:
            n_hub = len(await _HUB.list_tools())
            # A successful MCP handshake does NOT mean the hub token still works
            # — tokens expire. Do a live, no-arg probe call so a stale token is
            # reported clearly instead of a misleading "healthy".
            # Probe the requirements (RM) backend — that's the auth that matters
            # for ELM work, and it returns a clean 401 when the token is stale.
            auth, detail = "unknown", ""
            try:
                probe = await _HUB.call_tool("list_project_areas", {"app_type": "RM"})
                ptxt = " ".join(getattr(c, "text", "") for c in probe.content)
                if probe.isError or "401" in ptxt or "Invalid access token" in ptxt:
                    auth, detail = "bad", ptxt[:200]
                else:
                    auth = "ok"
            except Exception as e:  # noqa: BLE001
                auth, detail = "probe-failed", f"{type(e).__name__}: {e}"

            if auth == "ok":
                status = (f"🟢 **Federated & authenticated** — hub `{_HUB.server_name}` "
                          f"v{_HUB.server_version}; a live data call succeeded.\n"
                          f"- Hub tools: **{n_hub}** · elm-mcp tools: **{len(_OUR_TOOLS)}** "
                          f"· total **{n_hub + len(_OUR_TOOLS)}**")
            elif auth == "bad":
                status = (f"🟠 **Hub reachable, but the token is REJECTED.** The MCP "
                          f"handshake works, but live data calls return 401 — your "
                          f"`ELM_HUB_TOKEN` has expired or been revoked. **Refresh the "
                          f"token and restart.**\n> {detail}")
            else:
                status = (f"🟠 **Hub connected, but a live probe call failed** — tools "
                          f"are listed but data calls may not work.\n> {detail}")
        else:
            status = ("🟠 **Standalone** — the engineering-ai-hub is not configured/"
                      "reachable, so only elm-mcp's own tools are available.\n"
                      "Set `ELM_HUB_URL` + `ELM_HUB_TOKEN` to federate the hub.\n"
                      f"- elm-mcp tools: **{len(_OUR_TOOLS)}**")
        return [TextContent(type="text", text=f"# elm-mcp v2 — v{__version__}\n\n{status}")]

    if name == "elm_lint_requirement":
        text = arguments.get("text", "")
        rep = _lint.lint_requirement(text)
        return [TextContent(type="text", text=_lint.format_report(text, rep))]

    if name == "elm_update":
        from . import update as _update
        res = _update.self_update()
        prefix = "✓ " if res.get("updated") else ""
        return [TextContent(type="text", text=f"{prefix}{res['message']}")]

    # --- federated hub tools: forward the FULL CallToolResult straight through ---
    # Returning the hub's CallToolResult verbatim preserves its content +
    # structuredContent + isError, and the low-level server returns it as-is
    # (so we don't re-validate the hub's outputSchema and trip "outputSchema
    # defined but no structured output returned"). It also lets the hub's real
    # responses — 401s, missing-arg validation, actual data — reach the host
    # instead of being masked by our wrapper.
    if _HUB is not None and _HUB.connected:
        try:
            return await _HUB.call_tool(name, arguments)
        except Exception as e:  # noqa: BLE001
            return [TextContent(type="text", text=(
                f"Error calling hub tool `{name}`: {type(e).__name__}: {e}"
            ))]

    return [TextContent(type="text", text=(
        f"Unknown tool `{name}`. The engineering-ai-hub isn't federated "
        f"(standalone mode), so only elm-mcp's own tools are available. "
        f"Set ELM_HUB_URL + ELM_HUB_TOKEN to enable the hub's tools."
    ))]


async def _run_stdio() -> None:
    n_ours = len(_OUR_TOOLS)
    mode = "federating hub" if (_HUB and _HUB.connected) else "STANDALONE"
    logger.info("elm-mcp v2 v%s starting (%s, %d native tools)", __version__, mode, n_ours)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


async def main() -> None:
    global _HUB
    cfg = hub_config()
    if cfg is None:
        logger.info("No hub configured (ELM_HUB_URL/ELM_HUB_TOKEN unset) — standalone mode.")
        await _run_stdio()
        return
    async with HubSession(cfg) as hub:
        _HUB = hub
        await _run_stdio()


def cli() -> None:
    """Console-script entry point (`elm-mcp-v2`)."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
