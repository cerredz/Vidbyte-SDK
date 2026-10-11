---
slug: agent-output-connectors
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-output-connectors
branch: feat/agent-output-connectors
base_commit: db3988ffdb4d580021ec4dae995281135f8f0a0f
pr:
until: none
started: 2026-10-11 17:36
---

# Pipeline: Agent output connectors

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-11 17:36 | 2026-10-11 17:52 | reports/S0-scout.md | base_commit db3988ff; code-map.md (4 sections, 477 lines) |
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-11 17:36 — Slug `agent-output-connectors`, branch `feat/agent-output-connectors`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-output-connectors` — pipeline defaults; SDK AGENTS.md defines no override.
- 2026-10-11 17:52 — `CodexHarnessAgent` is NOT given the parameter by default — Prompt 4 names only BaseAgent, JevAgent, CodingAgent, and the scout found `CodingAgent(BaseAgent)` (coding.py:27), so the earlier ledger's CodexHarnessAgent mention is superseded; carried as an optional Q-n (default: not included).
- 2026-10-11 17:52 — "forks do not inherit outputs" vs "as_tool delivers on every call" contradiction (AgentTool.execute runs on a fork, tools/agent_tool.py:59): not a user decision (both lines were assistant-proposed consequences); the spec author resolves it from the code and records a D-n.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- The credential sibling is `ProviderModelRegistry.resolve_api_key` (vidbyte/lib/registries/models.py:151-161); `ModelRegistry` does not exist — *source:* S0 scout
- `CodingAgent(BaseAgent)` (vidbyte/agents/coding.py:27) forwards `**kwargs`, so it may need no edit to accept `outputs`; `CodingAgent.restore` raises TypeError for the missing root_dir (coding.py header) — *source:* S0 scout
- `JevAgent.__init__(settings, runtime_settings)` is pinned by tests/test_jev_agent.py:504-509; AGENTS.md: a new JevAgent capability is a named validated field on `JevAgentSettings`; JevAgent passes no middleware/output_schema/handoff to BaseAgent today (jev/agent.py:90-102) — *source:* S0 scout
- Session records the turn (base.py:928) before the schema check (base.py:931); `SessionSerializer._safe` stores a non-pydantic dataclass in metadata as `{"__dropped__": ...}` — *source:* S0 scout
- Middleware abort = `reply.metadata["stop_reason"] == "middleware_abort"`; the abort content is NOT empty — *source:* S0 scout
- HttpTransport: JSON bodies only (no form encoding), ignores Retry-After, retries 5xx by default (pass `retry_status_codes=(429,)`), idempotency_key is a local guard never sent — *source:* S0 scout
- Lint: A001 full header on every new tracked .py file incl. tests (the "Context Protocol Header" style does NOT pass); A006 bans lib/ and providers/ importing vidbyte.agents even inside a function; A007 named constants for timeouts/status codes; A002 `@intent` comment on send/request/transport functions; A003 DIAGNOSTIC_FIELDS on any new error; S063 applies to gather; S052 flags blocking smtplib in async; lint pass line is `SDK-LINT: PASS`; new files are not linted until git-added — *source:* S0 scout
- C016: regenerate the public API contract only after the root `__init__` change is committed; Semgrep runs only in static-policy.yml, not run_ci.py — *source:* S0 scout
- providers/ is the model-adapter layer (counts as lower layer for A006); precedent for credentialed non-model HTTP clients is vidbyte/tools/builtins/operations/clients/ — *source:* S0 scout
- YAML `AgentSettings` deliberately excludes non-serializable inputs (lib/dataclasses/config.py:25-28); `_ALLOWED_FIELDS` rejects unknown keys; no parity test — *source:* S0 scout
- run_ci package stage must run with PYTHONPATH unset; Semgrep (`semgrep==1.170.1`) needs its own venv because the SDK pulls mcp 2.x — *source:* memory / S0 scout
- SDK CI workflows are dispatch-only: after pushing, `gh workflow run ci.yml --ref <branch>` and `gh workflow run static-policy.yml --ref <branch>`; read results via `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs` — *source:* memory
