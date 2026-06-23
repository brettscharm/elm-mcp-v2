# elm-mcp v2 — Design & Research

> Goal: **significantly improve on IBM's Engineering AI Hub MCP**, while keeping
> the one thing we genuinely needed from it — **governed auth/access to ELM** —
> plus its correct, config-aware primitives and its SysML coverage.
>
> *"The hub is the reliable engine. elm-mcp v2 is the interface."*

Status: planning doc for the work after v0.3.1 (federation core + forwarding
fix). Items marked **⟂ verify-live** need a fresh hub token to confirm exact
I/O before implementation.

---

## 0. Approach (decided)

Two course-corrections that shape everything below:

**A. Supplement, don't replace.** The hub's core tools *work* — a model can drive
their discovery dance (proven in real use). So we do **not** hide/rewrap them
wholesale. Instead:
- **Keep the hub's core tools exposed** (passthrough; correct + working).
- **Supplement on their outputs** — a thin enrichment layer (links, dedup,
  formatting) and analysis tools that operate on the data the hub fetches.
- **Add a lot of net-new tools** the hub's MCP simply doesn't have.
- Add a clean **wrapper only where the hub has *no* tool at all** (a real
  "list modules", a deduped+linked search) — gap-filling, not replacing.

This is lower-risk than §3's original "wrap-and-hide" framing — read the wrapper
table there as *gap-fillers + optional niceties*, not "replace everything."

**B. Authoring & analysis, NOT code generation.** v1's identity was
`build_new_project` (idea → … → code). That's the wrong center of gravity — the
hub feels nicer precisely because it's about rich *interaction* with ELM data,
not writing code. v2's value, and the "ton more tools", are **engineering-
assistant capabilities**: understand / summarize / translate, quality
(lint·coach·score), review·coverage, traceability·impact, compliance, and
drafting clean requirements. Code-gen survives only as a minor bridge, never the
identity. **The identity is: make ELM data understandable, high-quality, and
traceable.**

---

## 1. What the official hub actually is

**IBM Engineering AI Hub** (currently 1.3) is a governed-AI add-on to IBM ELM.
It ships a **managed MCP endpoint** for "lifecycle-aware access to ELM data" —
a trusted/governed context layer. Sources:
- [Engineering AI Hub 1.3 announcement](https://www.ibm.com/new/announcements/ibm-engineering-ai-hub-1-3-helps-engineering-teams-scale-governed-agentic-ai-across-the-lifecycle)
- [Engineering AI Hub docs (1.0)](https://www.ibm.com/docs/en/engineering-ai-hub/1.0.0?topic=agents-getting-started)
- [DOORS Next AI & automation](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors-next/7.2.0?topic=overview-ai-automation)

Crucial distinction we confirmed by probing the live endpoint (46 tools):

- The **MCP endpoint exposes PRIMITIVES** — data access (`get_requirement`,
  `search_requirement`, `create_requirement`, components/config, links, SysML).
- The Hub's **smart agents** (requirements-quality analysis, the conversational
  Engineering Assistant, work-item synopsis, MBSE discovery) live in the **Hub
  product UI** — they are **not** on the MCP endpoint.

**Implication:** our authoring/analysis tools (lint, review, draft, coverage,
compliance) are **not redundant** with the MCP we federate. We're bringing
agent-grade help *to the MCP layer*, which the Hub itself only offers inside its
own UI. And the governed auth — the thing that finally got us cleanly into ELM —
is exactly what we keep.

### What we KEEP from the hub
1. **Auth / governed access** — the gateway token. The single hardest problem we
   had (self-signed certs, jazzop form login, token chaos) — solved by them.
2. **Config-management correctness** — `configuration_url`, changesets,
   components, streams. The GC project v1 couldn't see is fully visible here.
3. **SysML v2** — 18 model/branch/diagram tools. Entirely unique; we wrap nothing
   here, we pass it through.

### What we REPLACE (the interface)
Everything in §3.

---

## 2. The 46 hub tools (catalog)

| Group | Tools | Disposition in v2 |
|---|---|---|
| Identity | `get_project_area`, `get_user`, `list_project_areas` | wrap → `elm_projects`, `elm_user` |
| DNG reqs | `get_requirement`, `search_requirement`, `create_requirement`, `get_project_components`, `get_project_component_configuration`, `get_project_component_types`, `get_project_component_folders`, `create_requirement_change_set`, `deliver_requirement_change_set` | wrap → clean `elm_*` (hide raw) |
| EWM | `get_workitem`, `search_workitems`, `add_comment_to_workitem`, `get_workitem_schema`, `list_workitem_categories`, `list_workitem_releases`, `get_scm_artifact` | wrap → `elm_workitems`, `elm_get`, `elm_comment` |
| ETM | `get_testartifact`, `search_testartifact`, `get_testartifact_schema`, `add_comment_to_testartifact` | wrap → `elm_tests`, `elm_get` |
| Linking | `link_workitem_and_requirement`, `link_testartifact_and_requirement`, `link_workitem_and_testartifact`, `list_linked_requirements`, `list_linked_testartifacts`, `list_linked_workitems` | wrap → `elm_link`, `elm_links` |
| **SysML** | 18 model/element/branch/diagram tools | **pass through** (don't wrap) |

### Observed UX failures (the improvement targets)
Every one of these is a thing we hit in real use:

1. **UUID soup.** Reads/writes require `project_area_uuid`, `component_id`,
   **`configuration_url`**, `artifact_type_url`. You cannot use a project *name*.
2. **No "list modules."** You must: get components → search reqs → re-search for
   `MD_`-prefixed artifacts. (Live transcript proof.)
3. **No clickable links.** Results give ID + title, not the DNG web URL — losing
   the click-through v1 always provided.
4. **Dirty search.** Caps at 50; returns each requirement **twice** (TX/BI
   resource variants); no clean pagination.
5. **Mandatory discovery dance** before any real call ("read `ccm://docs/...`
   first").
6. **7-param creates**; cryptic `Missing required argument` validation errors that
   read like connection failures to the calling model.
7. **Split auth even internally** — Bearer for RM/CCM/QM, `rse-access-token` for
   SysML. A health check must probe the *requirements* backend to be meaningful.

---

## 3. The v2 improvement: a clean tool layer

**Design principle for every native tool: _name in → links out, one call,
deduped, good errors._** The AI talks to our `elm_*` tools; the hub's UUID-soup
stays under the hood. This also *eliminates* the validation errors — the model
never calls the param-heavy hub tools directly.

### 3a. Core engine (the part that makes it all possible)
Internal infrastructure, not tools:

- **Resolver** — `name → project_area_uuid`; `project → component_id +
  configuration_url`; `module name/id → module artifact`. The discovery dance,
  done **once and cached**. Every clean tool calls it. **⟂ verify-live** the
  exact calls + response shapes.
- **Link builder** — artifact id / OSLC resource URL → clickable DNG **web** URL
  (`…/rm/resources/<id>` or module web URL). **⟂ verify-live** whether hub
  results carry the full resource URL (derive from it) or only a numeric id
  (then we need the server base — likely from the resource URL on a `get_*`).
- **Dedup** — collapse TX/BI variants by base resource id so a list of 50 hits
  isn't 25 duplicated.
- **Cache** — project areas / components / configs change rarely; cache them
  (TTL) so the resolver is cheap. (Proxy best-practice: cache read-only
  idempotent backend calls.)

### 3b. Read tools
| v2 tool | Wraps | Improvement |
|---|---|---|
| `elm_projects(domain?, filter?)` | `list_project_areas` | optional domain (all 3 at once), name filter, returns name+uuid+link |
| `elm_modules(project)` | components + config + `MD_` search | **one call**, name-based, deduped, **with links** |
| `elm_requirements(project, module?/filter?, page?)` | `search_requirement` / module read | **deduped**, **paginated past 50**, attribute filters, **with links** |
| `elm_search(project, text, domain?)` | `search_requirement`/`search_workitems`/`search_testartifact` | name-based, resolves UUIDs, spans domains, deduped, **linked** |
| `elm_get(project, id)` | `get_requirement` / `get_workitem` / `get_testartifact` | id/name in, full detail + link, auto-routes by artifact type |
| `elm_links(artifact)` | `list_linked_*` | one call, both directions, with links |

### 3c. Write tools (preview-first)
| v2 tool | Wraps | Improvement |
|---|---|---|
| `elm_create_requirement(project, module, title, text, attrs?)` | `create_requirement` + `create/deliver_requirement_change_set` | name-based; resolves the 7 URLs + runs the changeset flow internally; **preview before commit** |
| `elm_link(source, target, type)` | `link_*` | name/id in, validates the link type |
| `elm_comment(artifact, text)` | `add_comment_to_*` | one call across artifact types |

### 3d. Authoring / analysis (no hub-MCP equivalent — the real value)
| v2 tool | Purpose |
|---|---|
| `elm_lint_requirement` *(shipped)* | quality gate before commit |
| `elm_review(project, module)` | the ELM analog of code review — findings: quality, coverage gaps, orphans, untraced changes (read-only first; `--fix` drafts closing items later) |
| `elm_coverage(project, module)` | reqs→tests/code coverage scorecard |
| `elm_draft(source: idea/PDF/Jira)` | draft → lint → structured, ready to commit via `elm_create_requirement` |
| `elm_compliance_packet(project, framework)` | framework-control coverage (port from v1) |
| `elm_traceability(project)` / `elm_change_impact(artifact)` | port from v1, on hub reads |

**Net surface the AI sees:** ~15 clean `elm_*` tools + ~18 SysML passthrough ≈
**33**, vs. the 48 raw federated tools today — fewer, cleaner, no UUID soup.

---

## 4. Architecture

```
Host ──► elm-mcp v2 ──────────────────────────────┐
          • elm_* clean tools (we implement)       │ resolver+cache+linkbuilder
          • SysML hub tools (passthrough)          │
          • [hidden] raw hub primitives            │  MCP client → Engineering AI Hub ──► ELM
          • retrieve_tools (escape hatch)          ┘
```

Decisions, several confirmed by the proxy-pattern research
([gateway patterns](https://chatforest.com/guides/mcp-gateway-proxy-patterns/),
[aggregation state-of-ecosystem](https://www.heyitworks.tech/blog/mcp-aggregation-gateway-proxy-tools-q1-2026)):

1. **Supplement, don't hide (by default).** Per §0A: `list_tools` exposes the
   hub's working tools (passthrough) **plus** our `elm_*` supplements + SysML.
   Add to `_HIDE_HUB_TOOLS` only when a hub tool is *genuinely* superseded by a
   cleaner gap-filler (e.g. once `elm_modules` exists, hide the raw module-hunt
   path) — not as a blanket policy. Keeps the surface manageable without
   rebuilding what already works.
2. **Escape hatch.** Keep a `retrieve_tools(query)` / `elm_raw_call(tool, args)`
   so nothing is *lost* — power users / coverage gaps can still reach any hub
   tool. (Mirrors the `retrieve_tools` discovery pattern.)
3. **Forward full `CallToolResult`** for any passthrough (fixed in v0.3.1 — keeps
   structuredContent, avoids the output-schema re-validation bug).
4. **Namespacing** only if a hub tool name ever collides with an `elm_*` name
   (none today; our prefix `elm_` keeps us clear).
5. **Read caching** for resolver lookups (project/component/config).
6. **Per-user token.** `ELM_HUB_TOKEN` is each user's own short-lived token, never
   shared (attribution + security). v2 holds no central credential. Fail with a
   clear "set your own token" message when missing/expired (we now detect expiry
   in `elm_health`).

---

## 5. Open questions — need a fresh hub token to settle (⟂ verify-live)
1. Exact response shape of `search_requirement` / module artifacts → the **link
   field** and the **TX/BI dedup key**.
2. The precise resolver chain for `create_requirement` (which call yields
   `artifact_type_url`, `configuration_url` for a named module).
3. Whether `get_project_components` + a module search is the cheapest "list
   modules", or there's a better artifact-type query.
4. Pagination mechanism past the 50-result cap (offset? page token?).
5. SysML auth (`rse-access-token`) — is it a separate token or derived from the
   same gateway login?

---

## 6. Roadmap
- **M1 — resolver + links + dedup + cache** (the engine). Then `elm_projects`,
  `elm_modules`, `elm_get` (read, name-in, links-out). *First visible "this is
  better."*
- **M2 — `elm_search` + `elm_requirements`** (deduped, paginated, linked) and
  curate `_HIDE_HUB_TOOLS`.
- **M3 — writes:** `elm_create_requirement` (preview-first, changeset flow),
  `elm_link`, `elm_comment`.
- **M4 — authoring:** `elm_review`/`elm_coverage`, `elm_draft`; port compliance /
  traceability / change-impact.
- **M5 — v2 Bob modes** tuned for the federated toolset (distinct slugs, clean
  names) + `elm_install_modes`.
- **Cross-cutting:** CI (build + connect-to-hub smoke + routing eval), the
  air-gapped bundled-deps build.

---

## 7. Positioning, in one line
**IBM's Engineering AI Hub governs the door and keeps the data correct; elm-mcp
v2 makes that data usable — name-based, link-rich, one-call, and with the
authoring intelligence the Hub only exposes inside its own UI.**
