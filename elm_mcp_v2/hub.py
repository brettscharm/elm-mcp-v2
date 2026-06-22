"""Client side of the facade: a thin, resilient wrapper around an MCP
*client* session to IBM's engineering-ai-hub.

This is what makes elm-mcp v2 "build on top of" the official server. We open a
single streamable-HTTP MCP session to the hub at startup and hold it for the
life of the process; `list_tools()` mirrors the hub's tool catalog and
`call_tool()` forwards a call straight through. If the hub is unreachable or
unconfigured, the facade degrades to standalone mode (our own tools only).

Config (env):
  ELM_HUB_URL        full URL of the hub's /mcp/ endpoint
  ELM_HUB_TOKEN      bearer token for the hub gateway
  ELM_HUB_VERIFY_SSL "1" to verify TLS (default "0" — hub test instances use
                     self-signed certs)
"""
from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack
from typing import Any, Optional

import httpx

logger = logging.getLogger("elm-mcp-v2.hub")


def hub_config() -> Optional[dict]:
    """Return {url, token, verify} if the hub is configured, else None."""
    url = os.environ.get("ELM_HUB_URL", "").strip()
    token = os.environ.get("ELM_HUB_TOKEN", "").strip()
    if not url or not token:
        return None
    verify = os.environ.get("ELM_HUB_VERIFY_SSL", "0") == "1"
    return {"url": url, "token": token, "verify": verify}


def _httpx_factory(verify: bool):
    def factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(
            headers=headers,
            timeout=timeout or httpx.Timeout(30.0),
            auth=auth,
            verify=verify,
            follow_redirects=True,
        )
    return factory


class HubSession:
    """Holds a live MCP client session to the hub. Use as an async context
    manager around the whole server run so the session stays open for every
    tool call. `connected` tells the facade whether to federate or run
    standalone."""

    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._stack: Optional[AsyncExitStack] = None
        self.session = None              # mcp.ClientSession when connected
        self.connected = False
        self.server_name = ""
        self.server_version = ""
        self.tools_cache: list = []      # mirrored hub Tool objects

    async def __aenter__(self) -> "HubSession":
        # Imported lazily so the package imports even if mcp isn't present yet
        # (self-heal / early startup) — and so standalone mode has no hard dep
        # on the client transport.
        from mcp.client.streamable_http import streamablehttp_client
        from mcp import ClientSession

        self._stack = AsyncExitStack()
        try:
            read, write, _ = await self._stack.enter_async_context(
                streamablehttp_client(
                    self._cfg["url"],
                    headers={"Authorization": f"Bearer {self._cfg['token']}"},
                    httpx_client_factory=_httpx_factory(self._cfg["verify"]),
                )
            )
            session = await self._stack.enter_async_context(ClientSession(read, write))
            init = await session.initialize()
            self.session = session
            self.connected = True
            si = init.serverInfo
            self.server_name = getattr(si, "name", "hub")
            self.server_version = getattr(si, "version", "?")
            self.tools_cache = list((await session.list_tools()).tools)
            logger.info(
                "Federating hub '%s' v%s — %d tools",
                self.server_name, self.server_version, len(self.tools_cache),
            )
        except Exception as e:  # noqa: BLE001 — any failure → standalone
            logger.warning(
                "Could not connect to the hub (%s). Running STANDALONE — "
                "only elm-mcp v2's own tools will be available.",
                type(e).__name__,
            )
            await self._stack.aclose()
            self._stack = None
            self.connected = False
        return self

    async def __aexit__(self, *exc) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self.connected = False

    async def list_tools(self) -> list:
        """Current hub tool catalog (refreshed best-effort, cache fallback)."""
        if not self.connected or self.session is None:
            return []
        try:
            self.tools_cache = list((await self.session.list_tools()).tools)
        except Exception as e:  # noqa: BLE001
            logger.warning("hub list_tools refresh failed (%s) — using cache", type(e).__name__)
        return self.tools_cache

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        """Forward a tool call to the hub and return its FULL CallToolResult.

        Returning the whole result (not just .content) preserves
        structuredContent + isError, and — because the low-level server passes
        a CallToolResult through verbatim — avoids re-validating the hub's
        outputSchema on our side (which would otherwise fail with
        "outputSchema defined but no structured output returned")."""
        if not self.connected or self.session is None:
            raise RuntimeError("hub not connected")
        return await self.session.call_tool(name, arguments or {})
