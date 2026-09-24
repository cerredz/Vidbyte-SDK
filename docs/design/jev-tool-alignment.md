# Jev Tool Alignment

## What and why

`JevAgentSettings(tool_align=JevToolAlignmentSettings(...))` lets a `JevAgent` attach tools that already exist in public tool catalogs, for one run, when the request needs something no configured tool does. Writing new tool code was rejected as too open-ended. Tools that other people publish, maintain, and run are a safer source.

The owner asked for all of the logic to live in helper methods on `JevAgentAlignment`, the self-alignment class from PR #445. This branch therefore contains #445's commits. #445 should merge first, and this PR targets `main`.

## How it works

`JevRuntime.arun` runs prompt alignment (when `self_align` is on), then tool alignment (when `tool_align` is set), then the inherited loop.

1. **Detect (Jev, one request).** The state is `{system_prompt, request, tools}`. It asks #445's `fit.task_in_scope` gate, unless prompt alignment already answered it, plus `tools.detect.outside_action`. If the request is out of scope, or needs no outside action, the run goes ahead with no further calls.
2. **Needs (scout, generative).** `JevAgentAlignment` builds one scout `BaseAgent` with a fixed prompt and four tools. In its first pass, the scout writes one to three needs as `{action, object, system}`. Code builds each need sentence.
3. **Coverage (Jev, one request per need).** The state is `{request, need, need_system, tool_1..tool_n}`. It asks one question per existing tool ("does `tool_k` perform `need`?"), `need.asks_change`, and `need.names_system`. A need is covered when any tool scores at least 0.6. If every need is covered, nothing is searched.
4. **Search (scout, generative).** The second pass handles the uncovered needs. `search_tool_catalogs` fans out to every enabled catalog provider. `describe_catalog_entry` fetches an entry's tool list. `propose_tool_candidates` shortlists tools, and may only use entry ids and tool names that search or describe returned.
5. **Facts (code).** Each proposal must have an allowed install kind (by default `remote_http` and `managed`), all the secrets it needs, and a pinned version for packages and containers (unless `allow_unpinned_packages`). Exposed names must not collide with an existing tool. A proposal that fails becomes a rejection. A missing secret or credential becomes an owner action.
6. **Open (code).** Remote and managed installs are connected before any judgment, and their live `tools/list` is what Jev judges. The same session is later bridged, so the description that was judged is the one that runs.
7. **Candidate (Jev).** There are two requests per candidate tool:
   - the request state `{request, need, need_system, candidate_name, candidate_description, candidate_inputs}` asks `performs_need`, `serves_request`, and `named_system`;
   - the description-only state `{candidate_description, candidate_inputs}` asks `describes_only` (a tool-poisoning screen) and `effect`, a choice of reads / writes / sends_or_deletes / unclear. These answers are cached by a hash of the description.
8. **Decide (code).** A tool attaches when `performs_need ≥ 0.7`, `serves_request ≥ 0.7`, `describes_only ≥ 0.85`, and `named_system ≥ 0.6` (the last only when the user named a system), and its effect is allowed:
   - reads are always allowed;
   - writes need `asks_change ≥ 0.5`;
   - sends/deletes and unclear effects need `asks_change ≥ 0.85` plus `allow_high_impact`.

   A server-declared destructive hint overrides Jev's effect answer. Candidates are ranked by verified status, remote install, pinned version, fewer secrets, and `performs_need`. One entry is attached per need, capped at `max_attached_tools`.
9. **Attach for this run.** Approved tools are bridged with a server prefix (`<entry>__<tool>`). They are added to this run-local runtime's tools and context, and closed when the run ends. Read-only tools get `ToolPermission.READ`; everything else gets `EXECUTE`, so the owner's `PermissionPolicy` still decides.
10. **Report.** `metadata["jev_tool_alignment"]` holds a `JevToolAlignmentResult`: status, needs, attached tools, rejected candidates with reasons, owner actions, provider errors, probabilities, and summed Jev usage. When `announce=True` and the run returns no structured output, code appends a footer listing the added tools.

Failure policy: the run fails open (any Jev, scout, or catalog failure, or the time budget running out, means the original tools are used) and attaching fails closed (an unverified tool never attaches). Every opened session is closed.

## Catalog provider layer

`vidbyte/providers/tool_catalogs/` has one adapter per catalog behind `ToolCatalogProvider`. Each adapter normalizes results into `ToolCatalogEntry` records (`vidbyte/lib/dataclasses/tool_catalogs.py`). All of them use `HttpTransport` with timeouts and byte ceilings.

| Catalog | Search | Install produced |
|---|---|---|
| Official MCP Registry | `GET /v0.1/servers?search=&version=latest` | remotes, plus npm/pypi/oci packages |
| GitHub MCP Registry | same API at `api.mcp.github.com` | same |
| Smithery | `GET /servers?q=` + `GET /servers/{name}` | remote `deploymentUrl`, with config from `x-from` |
| Glama | `GET /v1/connectors?query=` (key) | remote connector URL |
| Docker MCP Catalog | cached `catalog.yaml`, searched locally | remote, or container image@digest |
| ToolSDK | cached `packages-list.json`, searched locally + package file | remote, or unpinned npm (rejected) |
| Composio | `GET /api/v3.1/tools?query=` (key) | managed: a tool-router session MCP URL |
| Pipedream | `GET /v1/connect/apps?q=` (OAuth client) | managed: `remote.mcp.pipedream.net/v3` + headers |
| Arcade | `GET /v1/tools?search=` (key) | managed: direct `POST /v1/tools/execute` |
| APIs.guru | cached `list.json` | OpenAPI (discovery only, reported, never attached) |

The official registry, GitHub's registry, Docker, Smithery, and ToolSDK are on by default. APIs.guru is keyless but must be listed explicitly. Keyed catalogs must be listed together with their credentials, and managed platforms also need `user_id`; settings validation refuses anything missing.

## Other changes

- `vidbyte/tools/mcp/`:
  - new `McpStreamableHttpTransport` (JSON or SSE replies, `Mcp-Session-Id`, `MCP-Protocol-Version`, the `notifications/initialized` notification, and DELETE on close);
  - `McpServerConfig` accepts `url` + `headers` (with secrets hidden from repr), `tool_allowlist`, and `tool_prefix`;
  - tool definitions keep their MCP `annotations`.
- `SearchMcpServersTool` stops deriving `npx -y <qualifiedName>`, which ran unrelated npm packages. It now returns Smithery's remote URL, and `AttachMcpServerTool` accepts a `url`.

## Files

- New: `vidbyte/lib/{enums,constants,dataclasses}/tool_catalogs.py`, `vidbyte/providers/tool_catalogs/*`, `vidbyte/prompts/prompts/jev_alignment/tool_scout_system_prompt.md`, `tests/test_tool_catalogs.py`, `tests/test_mcp_http_transport.py`, `tests/test_jev_tool_alignment.py`, `scripts/test-jev-tool-alignment.py`.
- Modified: `vidbyte/agents/jev/{settings,agent,runtime}.py` and `alignment/{agent,questions,tool,draft,result,__init__}.py`; the MCP files above plus `vidbyte/agents/mixins.py` (`url`/`headers` on `attach_mcp_server`); `vidbyte/tools/builtins/mcp/{search,attach_tool}.py` and their tests; the prompt manifest and enum; exports; `scripts/test-jev-agent-scaffold.py`; `skills/jev-agent/SKILL.md`; and the providers, MCP, and jev READMEs.

## Risks and open questions

- The thresholds are starting points and still need a labeled set.
- Smithery's hosted `run.tools` servers may require OAuth; connection failures are reported as `connect_failed`.
- Composio, Pipedream, and Arcade need `user_id`, the end-user identity, set in settings.
- Container and package installs are opt-in. When allowed, the pinned process is started to read its live tool list before Jev judges the tools, so allowing those kinds means trusting the pinned image or package to start. No tool is called or exposed until Jev approves it.

## Verification

- Deterministic tests for each provider parser, the HTTP transport, and every tool-alignment status and rejection reason.
- `python lint/run.py`, `python scripts/run_ci.py --stage source`, `python scripts/run_ci.py`.
