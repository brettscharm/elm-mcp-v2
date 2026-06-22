# elm-mcp v2 — one MCP server, the hub's correctness + our authoring brain

> ⚠️ Personal passion project. **NOT** an official IBM product. Use at your own risk.

**elm-mcp v2 is a single MCP server you install once.** Behind the scenes it is
itself a *client* of IBM's official **engineering-ai-hub** MCP server — it
re-exposes the hub's tools (correct, config-aware reads/writes, OSLC linking,
and SysML) *and* adds elm-mcp's own authoring / orchestration tools on top.

So your AI host (Bob, Claude, Cursor) connects to **one** server and sees the
whole toolset.

```
            ┌──────────── 1 install ────────────┐
 Bob ─────► │  elm-mcp v2  (this server)         │
            │   • elm_*  authoring/orchestration │
            │   • the hub's tools (federated)    │
            └───────────────┬───────────────────┘
                            │  hub token (configured once)
                            ▼
                  engineering-ai-hub  ──►  IBM ELM
```

## Why

| | The hub | elm-mcp v2 adds |
|---|---|---|
| Reads / search / schemas | ✅ correct, config-aware | — (we defer to it) |
| Create / update / link / changesets | ✅ correct | — (we defer to it) |
| SysML v2 models | ✅ (its big strength) | — |
| Login | ✅ gateway token | reused (one login) |
| Drafting · quality lint · interviews | — | ✅ `elm_lint_requirement`, … |
| Build orchestration, compliance, gap/impact reports, exports | — | ✅ (rolling in) |

**The hub is the reliable scribe; elm-mcp is the opinionated author.** We don't
re-implement the primitives the hub already does correctly — we orchestrate them
and add the authoring intelligence on top.

## Two modes

- **Federated (preferred):** set `ELM_HUB_URL` + `ELM_HUB_TOKEN` and the hub's
  tools light up alongside ours.
- **Standalone:** no hub configured → only elm-mcp's own tools (degraded but
  functional). The single install works either way.

> The hub is IBM-hosted and must be provisioned for you (that's where the token
> comes from). v2 can't bundle it — it federates it.

## Install

Add one server to your AI host's MCP config:

```json
{
  "mcpServers": {
    "elm-mcp-v2": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/brettscharm/elm-mcp-v2", "elm-mcp-v2"],
      "env": {
        "ELM_HUB_URL": "https://your-hub-host/mcp/",
        "ELM_HUB_TOKEN": "your-hub-bearer-token"
      }
    }
  }
}
```

(`uv` provisions Python + deps automatically. No clone, no pip.) Then fully
quit and reopen your host. Ask **"run elm_health"** to confirm federation.

Local dev:

```bash
git clone https://github.com/brettscharm/elm-mcp-v2 && cd elm-mcp-v2
pip install -e .
ELM_HUB_URL=… ELM_HUB_TOKEN=… elm-mcp-v2     # speaks MCP over stdio
```

### Config (env)

| var | meaning |
|---|---|
| `ELM_HUB_URL` | the hub's `/mcp/` endpoint |
| `ELM_HUB_TOKEN` | bearer token for the hub gateway |
| `ELM_HUB_VERIFY_SSL` | `1` to verify TLS (default `0` — test hubs use self-signed certs) |

> Never commit the token. Keep it in your host's MCP `env` block (or a local
> `.env`, which is gitignored).

## How it works

- On startup the server opens **one** streamable-HTTP MCP session to the hub and
  holds it open ([`elm_mcp_v2/hub.py`](elm_mcp_v2/hub.py)).
- `list_tools` returns **our tools + the hub's** (curated by `_HIDE_HUB_TOOLS`).
- `call_tool` runs our `elm_*` tools locally and **forwards** everything else to
  the hub, streaming its content back unchanged
  ([`elm_mcp_v2/server.py`](elm_mcp_v2/server.py)).

## Status — v0.1.0 (foundation)

What's here:
- ✅ The federation core (connect → mirror tools → forward calls).
- ✅ `elm_health` (federation status) and `elm_lint_requirement` (quality gate)
  as the first native tools.
- ✅ Standalone fallback.

Roadmap (porting elm-mcp's authoring value on top of the hub):
- [ ] `elm_draft_requirements` / Plan-Mode deep-drill → structured draft
- [ ] commit orchestration (drive the hub's `create_requirement` + changeset flow)
- [ ] `elm_find_similar` (semantic dedup over hub reads)
- [ ] `elm_compliance_packet`, `elm_traceability_gaps`, `elm_change_impact`
- [ ] `export_module_to_xlsx`, charts, trace/audit reports
- [ ] Jira import, PDF intake, team-activity log
- [ ] Bob modes / NL concierge tuned for the federated toolset
- [ ] tool-name curation (hide hub primitives we supersede)
- [ ] CI: build + connect-to-hub smoke test + routing eval

(elm-mcp v1, the standalone server, lives at
[github.com/brettscharm/elm-mcp](https://github.com/brettscharm/elm-mcp).)
