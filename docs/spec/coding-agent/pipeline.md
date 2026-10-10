---
slug: coding-agent
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-coding-agent
branch: feat/coding-agent
base_commit: 8f23fd676d60f413e0353281dd73e60dc719407a
pr:
until: none
started: 2026-10-10 00:51
---

# Pipeline: CodingAgent — a minimal BaseAgent with seven file-system and web tools

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-10 00:51 | 2026-10-10 01:08 | reports/S0-scout.md | base_commit 8f23fd67; code-map.md (4 sections, 329 lines) |
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
- 2026-10-10 00:51 — Unset the branch upstream (`git branch --unset-upstream`) — `git worktree add -b … origin/main` made `feat/coding-agent` track `origin/main`; pushes must use `git push -u origin feat/coding-agent`.
- 2026-10-10 00:51 — Recorded the unanswered Edit-tool choice as an open question with default `ReplaceTextTool` (the assistant's recommendation in the conversation) — the user replied to the other four decisions but not this one.
- 2026-10-10 00:51 — Recorded "tool names I dont care" as: keep existing model-facing names, build no renaming layer — smallest reading; rule 11.

## User replies (verbatim)
- (none yet during the run)

## Niche facts accumulated (carried into every later briefing)
- Keyed fetch tools (Firecrawl, Browserbase, Parallel, Tavily) return only "N. url (len chars)" to the model (`fetch.py:39-42`); page bodies live in `metadata["operation_payload"]`. Only `direct_http_fetch` returns the body as output, and it is unbounded (`sources/fetches/http.py:44-49`). — *source:* S0 scout
- `LinkupFetchTool` is always a stub and there is no Linkup client; working keyed providers are Firecrawl, Browserbase, Parallel, Tavily, each client needs only `api_key`. — *source:* S0 scout
- Duplicate tool names raise `ToolRegistrationError` at BaseAgent construction; `_catalog_from_agent_tools` catches only TypeError (`base.py:1288`). — *source:* S0 scout
- `BaseAgent.restore` and `from_run_id` call `cls(...)` with only BaseAgent's kwargs (`base.py:479`, `:270`); a subclass constructor must cope. Forks are always plain `BaseAgent` (`fork.py:43`). — *source:* S0 scout
- Writes are double-gated: default policy SAFE+READ (`base.py:185`, `security.py:33`) and `FileSystemToolConfig.allow_write` (`filesystem.py:31`). A denied call becomes a DENIED tool result; nothing raises. `PatchTool` has no `allow_write`. — *source:* S0 scout
- Subprocess lint rules: S052, S055 (no `shell=True`, no `create_subprocess_shell`), S019, S006, S039 (`asyncio.Lock` banned), A002 (token "subprocess" needs an `@intent` comment), A007 (timeout/byte numbers must be named constants), S025 (model-facing descriptions need 4+ sentences). S012/S013 do NOT match subprocess calls. The only subprocess precedent in `vidbyte/` is `vidbyte/tools/mcp/transport.py:168` (`asyncio.create_subprocess_exec`). — *source:* S0 scout
- A001 header: copy the `FILE:/PURPOSE:/ROLE IN CODEBASE:/…` format of `vidbyte/agents/jev/agent.py`; the "Context Protocol Header" style in `base.py`, `handoff.py`, `continual_trace.py` is non-compliant. Lint counts only git-tracked files: `git add` new files before running `python lint/run.py`. — *source:* S0 scout
- Semgrep is NOT in `run_ci.py`; it runs only in `.github/workflows/static-policy.yml` (dispatch only, `semgrep==1.170.1`). All CI is manual dispatch on ubuntu-latest (Python 3.11 and 3.12); Windows bash behaviour is never exercised by CI. — *source:* S0 scout
- Workspace gotchas: run `scripts/run_ci.py` with `PYTHONPATH` unset (it breaks the package smoke step); Semgrep needs its own venv/pipx because the SDK pulls `mcp` 2.x; dispatch CI with `gh workflow run ci.yml --ref feat/coding-agent` or PR checks never appear. — *source:* orchestrator memory of earlier runs
- Unverified (S0): which `bash` Python's subprocess resolves on Windows (Git Bash, WSL launcher, and WindowsApps bash are all on PATH); whether importing `vidbyte.tools.builtins` from `vidbyte/agents/__init__.py` cycles (`tools/builtins/fork/fork.py` imports `vidbyte.agents`). — *source:* S0 scout
