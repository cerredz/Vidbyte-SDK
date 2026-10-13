---
slug: native-grok-opencode-meta-hosts
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-grok-opencode-meta-hosts
branch: feat/native-grok-opencode-meta-hosts
base_commit: aa8c380c4cd1d5791526dd545f5ef1020b28a5cc
pr:
until: none
started: 2026-10-13 01:30 UTC
---

# Pipeline: GrokHost, OpencodeHost, MuseHost (Meta Muse Code), and GLM / DeepSeek backend profiles, with exhaustive error handling

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-13 01:30 UTC | 2026-10-13 02:20 UTC | reports/S0-scout.md | base_commit aa8c380c; code-map.md, 4 sections, 21 notes |
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2
- S5 repair iterations: 0/8
- S5 re-review rounds: 0/2

## Decisions the orchestrator made

- **2026-10-13 01:30 — Scope is the catalog's ★ set for each target, plus `build_opencode_backend_provider`.**
  - Why: Prompt 2's "for now" applied the same way as the upstream Codex first PR. The added function is the only runnable GLM/DeepSeek route while ClaudeHost is unmerged.
  - Recorded as request.md Q-1, default ★ only.
- **2026-10-13 01:30 — GrokHost's ACP code is protocol-generic but not a public `AcpHost`.**
  - Why: Prompt 2 narrows to five targets, and the upstream ledger rejects a base class that has only one implementation.
- **2026-10-13 01:30 — This PR follows the codex-host/claude-host shared-file contract.**
  - `native/__init__.py` must have SHA-256 `0374a2c8…497a`.
  - Tests go only in host-named folders.
  - Export indexes are edited append-only.
  - `pyproject.toml` stays unchanged unless Q-2 is resolved with evidence.
  - Why: three PRs create `vidbyte/harnesses/native/` in parallel.
- **2026-10-13 02:20 — Muse transport wording.** request.md §C quotes the catalog verbatim, so it still says "Talks MSP through `muse-code-sdk`" (request.md:598). That line is the catalog's description, not a decision. Q-2 (default: no new dependency) governs how Muse is reached.
  - Why: the scout flagged the two lines as conflicting (code-map §4.11).

## User replies (verbatim)
(none during the run)

## Niche facts accumulated (carried into every later briefing)

### Lint and gates
- **S011 bans `import httpx`** outside `vidbyte/lib/http/transport.py` and `vidbyte/tools/mcp/transport.py` (baseline 0).
  - opencode must go through `HttpTransport.request` (`lib/http/transport.py:55`), or change that owner module.
  - `HttpTransport.request` has no SSE, no query params, and creates a new client per call. — *source:* S0 code-map §4.1
- **The full-lint pass line is `SDK-LINT: PASS`**, not `AGENT-LINT`. — *source:* S0
- **Semgrep is not part of `run_ci.py`.**
  - Static policy: `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, using semgrep 1.170.1 from the venv at `C:/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1`. — *source:* S0 code-map §1
- **Source and package stages need different `PYTHONPATH` settings.**
  - Source stage: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`.
  - Package stage and full gate: run with no `PYTHONPATH`. — *source:* S0 code-map §1
- **S039 bans `asyncio.Lock`.** The precedent is `asyncio.Semaphore(1)` at `vidbyte/agents/codex/agent.py:82-86`. — *source:* S0
- **S045 (ASYNC109) flags an async parameter named `timeout`.** Use `timeout_seconds`. — *source:* S0
- **S012 flags every `.request(` call without a timeout** (baseline 0). — *source:* S0
- **C012 requires `ProviderModelRegistry` proof for model fields.**
  - It applies to `model` / `*_model` str fields on `*Settings`, `*Config`, `*Spec` and `*Options` classes, and the registry is strict.
  - Vendor model strings (Grok, opencode `provider/model`, Muse, `glm-5.3[1m]`) are not in that registry.
  - Exemptions are rows inside the rule file; editing that file may count as weakening a rule. — *source:* S0 code-map §4.14

### Module layout and packaging
- **Don't copy the `builtins/sessions/` layout for headers or error handling.** It is baseline debt: a non-A001 header, raw exception text (S017), adjacent literals (S062), and a sync `_caught`.
  - Headers: copy `vidbyte/tools/toolsets/coding.py:1-12`.
  - Error translation: copy `vidbyte/agents/codex/transport.py`. — *source:* S0
- **`vidbyte/tools/mcp/transport.py` does not fit ACP or MSP as-is.**
  - It drops notifications (`:416-418`).
  - It can't answer server requests (`:419-450`).
  - `request()` has no timeout keyword (`:222-226`).
  - A006 does allow the `harnesses` → `tools.mcp` import. — *source:* S0 code-map §4.2
- **No process-tree kill exists in the SDK.** On Windows the SDK kills only the direct child (`bash.py:9`). The Muse `.cmd` shim routes arguments through `cmd.exe` `%*` parsing. — *source:* S0 code-map §4.9-10
- **Commit order for the public API.**
  - `scripts/generate-sdk-public-api.py` refuses to run while `vidbyte/__init__.py` has uncommitted changes.
  - So commit the export first, then regenerate `contracts/sdk-public-api.json`. — *source:* S0 code-map §4.16
- **C015 plus the frozen `pyproject.toml`:** no non-.py, non-README data files may live under `vidbyte/` (no vendored JSON schemas or fixtures). — *source:* S0 code-map §4.17

### Failure codes
- **`FailureCode` spans `vidbyte/lib/enums/failure.py:25-144`.**
  - The CODEX block is lines 35-46. Line 34 sits directly before it (Claude's suggested spot) and line 47 directly after it (Codex's spot).
  - Safe insertion spots for this PR: after 144, between 67 and 68, between 99 and 100, or between 129 and 130. — *source:* S0
- **Only `codex.*` codes need classification rows,** enforced by `tests/test_codex_failure_recovery.py:192-202`. No table exists for other prefixes. — *source:* S0

### Tool exposure
- **MCP runs tools without a permission check.** `mcp_server/handlers.py:84-88` calls `tool.execute` with no `PermissionPolicy`, no validation and no timeout.
  - The server is serial, so a blocking `wait_*` tool stalls every other call.
  - It serves only the tools passed to `McpStudioServer(tools=...)`. — *source:* S0 code-map §4.5, §4.7
- **Every public `BaseTool` exported from `vidbyte.tools.builtins` becomes YAML-declarable,** including WRITE tools (`lib/registries/components.py:101-124`). — *source:* S0 code-map §4.6
- **Dynamic tools inside a Codex agent are cancelled at 300 s** (`lib/constants/codex.py:193`). — *source:* S0 code-map §4.8
