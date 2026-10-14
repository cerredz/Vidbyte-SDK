---
slug: output-connector-followups
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-output-connector-followups
branch: feat/output-connector-followups (local name) → pushes to origin feat/agent-output-connectors (PR #882)
base_commit: 336d6c78bd5c4e2bef31d4182c96a21bb57e0e8b
pr: https://github.com/cerredz/Vidbyte-SDK/pull/882
until: none
started: 2026-10-13
---

# Pipeline: Output connector follow-ups on PR #882

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | running | 2026-10-13 | | reports/S0-scout.md | base_commit 336d6c78 (merge of origin/main 8387d666 into 4ee040b7) |
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
- 2026-10-13 — Build on the existing PR #882 branch, not a new branch from main — the user said "implement these things on the pr" (request.md §A Prompt 10).
- 2026-10-13 — Local branch is `feat/output-connector-followups` tracking `origin/feat/agent-output-connectors`; every push is `git push origin HEAD:feat/agent-output-connectors` — another session's worktree (`C:/Users/422mi/vidbyte-repos/worktrees-sdk/feat/agent-output-connectors`, clean, at 4ee040b7) has the PR branch checked out, and git forbids one branch in two worktrees.
- 2026-10-13 — Merged origin/main (8387d666) into the branch at S0 as merge commit 336d6c78 (conflict-free; branch was 15 behind) — checklist §0 "merge main into the branch"; catch-up by merge, never rebase. This is BASE_COMMIT; reviewers diff `336d6c78..HEAD`.
- 2026-10-13 — Scope = every checkbox of request.md §B sections 0–5, EXCEPT: "Mark the PR ready" (user's call); "Next, if you want them"; "Linear and Jira versions, only if you ask"; the "Don't build" list; bot tokens (Q3 default no); HTML email (Q4 default no). INCLUDED: optional Telegram `topic_id=`; all five §4 connectors (user did not narrow "pick 3–5"); Google Chat Markdown only if official docs confirm the field on the webhook's create call.
- 2026-10-13 — New slug folder `docs/spec/output-connector-followups/` instead of revising the first batch's spec in place — keeps the closed run's review/verify-log intact; the first spec gets only its §9.2(b) corrections.

## User replies (verbatim)
- 2026-10-13 — "great, implement these things on the pr"

## Niche facts accumulated (carried into every later briefing)
- Push with `git push origin HEAD:feat/agent-output-connectors` (local branch name differs from the PR branch) — *source:* orchestrator S0
- Anti-stall rules for every agent: give every subprocess a timeout and stdin from /dev/null; export `GIT_TERMINAL_PROMPT=0 GIT_EDITOR=true`; at most 2–4 throwaway experiments; write the report skeleton first — *source:* memory (2026-10-13 two-repo run)
- Merging main into a branch whose `vidbyte/__init__.py` exports changed can leave `contracts/sdk-public-api.json` `source.commit` stale; run `scripts/generate-sdk-public-api.py` and commit the regen separately if the C016/contract gate asks — *source:* memory
- At every S5 convergence check `gh pr view 882 --json mergeable,mergeStateStatus`; SDK main moves ~1 commit/10 min, so stop at MERGEABLE/BEHIND — *source:* memory
- vidbyte-cli draft PR #166 depends on `SlackOutput`, `GitHubIssueOutput`, `LinearIssueOutput` constructors and the root `OutputDispatcher` export (commit 4272c308): no breaking changes — *source:* memory
- No-test-edit check across merge commits: `git show --cc --format= <merge> -- tests/` is empty; plain diffs from BASE_COMMIT include only this run's work — *source:* memory

### Carried from the first batch (docs/spec/agent-output-connectors/pipeline.md)
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
- Contract names (spec §8.5): OutputConnector.deliver/_send, OutputArguments, OutputText, OutputHttp, OutputSmtp, OutputDispatcher.connectors/.deliver, records OutputContent/DeliveryReceipt/OutputRequest/SmtpSettings, enums OutputDestination/DeliveryStatus, OutputDeliveryError — *source:* S1 author r1
- Test seams: patch HttpTransport._send_once + transport.asyncio.sleep; patch smtplib.SMTP/SMTP_SSL as seen by vidbyte/lib/outputs/delivery.py; monkeypatch.setenv for credentials — *source:* S1 author r1
- Header keys passed to HttpTransport must be lowercase (else duplicate content-type); lib/errors/base.py may import AgentMessage/DeliveryReceipt only under TYPE_CHECKING; agents/output/dispatcher.py must not import from vidbyte.agents (base.py imports it → cycle); S012 flags a helper named `request` — *source:* S1 author r1
- r3 contract additions: OutputConnector is a runtime_checkable Protocol in vidbyte/agents/output/connector.py (declare `destination` as a plain annotation, not ClassVar — mypy); OutputShaping + OutputDispatcher(.connectors/.deliver/._deliver_one) in agents/output; BaseOutput + 11 connectors with public `send(reply, content)` + OutputArguments(.matching/.address/.optional_callable) + OutputText + OutputHttp + OutputSmtp in vidbyte/lib/outputs/; delivery is an inline try/except in BaseAgent._generate_reply (no _deliver_outputs) — *source:* S1 author r3
- isinstance(SomeOutputClass, OutputConnector) is True for the class object; OutputDispatcher.connectors checks isinstance(item, type) first — *source:* S1 review r2
- S009 runs `python -m mypy --config-file lint/mypy.ini vidbyte` inside lint (baseline 350); S051 I001 import order already fails on base (base.py has 3 unsorted blocks; baseline 259) — never re-sort base.py or run `ruff --fix` on it — *source:* S1 review r2 / author r3
- A002 matches tokens in function bodies (names/attributes), not just def names: `_link` and `_deliver_one` need `# @intent` — *source:* S1 review r1/r2
- Skip rule: deliver only when stop_reason absent, `final_response`, or `is_done`; budget stops come from runtime.py `_stopped_result` (~1882/1911) — *source:* S1 review r1
- `_deliver_one` wraps `connector.send` in `asyncio.wait_for(..., OUTPUT_DELIVERY_DEADLINE_SECONDS)` (35 s); tests can shorten it by setting the attribute on the dispatcher module — *source:* S1 author r3
- HTTP tests fake `HttpTransport._send_once` (header names must be lowercase); redirect + size-ceiling tests replace `transport_module.httpx.AsyncClient` with `httpx.MockTransport`, so keep `follow_redirects=False` and `max_response_bytes=OUTPUT_MAX_RESPONSE_BYTES` — *source:* S2
- `delivery.py` must `import smtplib` (module import) and use the client as a context manager; fakes replace `delivery.smtplib.SMTP`/`SMTP_SSL` — *source:* S2 / spec r4 row 7
- Dispatcher reads `OUTPUT_DELIVERY_DEADLINE_SECONDS` as a module global at call time (tests monkeypatch `dispatcher_module.OUTPUT_DELIVERY_DEADLINE_SECONDS`), never a default arg — *source:* S2 / spec r4 row 22
- Inline `except BaseException` must `self._queued_prompts.clear()` on every exception (inside a run `_queued_prompts` returns the claimed list via a context var) — *source:* S2 / spec r4 INV-7
- Exact strings asserted: `Missing credential for {dest} output. Pass {param} or set {ENV}.`; `{n} of {m} outputs failed: dest (code), ...`; `ClassName(credential='***')` — *source:* S2
- Slack escapes after truncation; Jira paragraphs = non-blank lines of the truncated body — *source:* S2
- Layering test parses real imports: agents/output may import stdlib, vidbyte.lib, vidbyte.agents.output only; lib/outputs must not import httpx/requests/aiohttp/http.client/urllib.request — *source:* S2 / spec r4 §12.2
- Run new tests: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors` (no global `pip install -e`; deps present in global Python 3.11) — *source:* S2
- S008 headroom on `_generate_reply` is zero (10/9/50 with the guarded `_deliver_outputs` call); add nothing else to it — *source:* S3 / spec r5
- Comments must fit 72 columns incl. indentation; S054/S105 flags string constants with a `_TOKEN_` name segment; only run `ruff check --select I001 --fix` on newly created files — *source:* S3
- `fork.py` and `jev/agent.py` changes can't land before row 27 (forks raise TypeError otherwise) — *source:* S3
- Semgrep: global install broken by mcp 2.x; use a venv with semgrep==1.170.1 and put its Scripts first on PATH (semgrep.exe launches pysemgrep from PATH) — *source:* S3
- Pre-existing, not ours: scripts/test-github-content-readmes.py 110/114 (4 failures in vidbyte/harnesses/README.md), not part of run_ci — *source:* S3
- R-1 test sets INFO on the ROOT logger and requires the caller's own httpx request to still log — fix must not touch httpx level/disabled/propagate and must reset `_OUTPUT_POST_ACTIVE` — *source:* S2 S4-follow-up
- R-3 test fails (10 s backstop, no hang) with `asyncio.to_thread` or `run_in_executor(None, …)`; needs module `_SMTP_EXECUTOR` — *source:* S2 S4-follow-up
- R-12: suppress `smtplib.SMTPException`/`OSError` around QUIT only, after `send_message` returns — *source:* S2 S4-follow-up
- Semgrep in Git Bash: put the semgrep venv on PATH via `cygpath -u` (a `C:/…` entry splits on the colon and the broken global pysemgrep runs) — *source:* S5 repair-1
- S009 reads 350/350 after the merge because main added the finding; identical finding sets at ba83c953 and HEAD — *source:* S5 repair-1
- Test-baseline check after the catch-up merge: `git diff 7f3bb7ff..HEAD -- tests/features/agent_output_connectors` plus `git diff ba83c953..HEAD -- tests/`; a plain `7f3bb7ff..HEAD -- tests/` includes main's test files — *source:* S5 polish
- Prior-art tests: tests/test_web_operation_client_retry.py (patch HttpTransport._send_once + transport_module.asyncio.sleep), tests/test_restore_output_schema.py, tests/agent_test_support.py (build_test_agent, bind_test_runner, OfflineTestAgent); test header exemplar tests/features/coding_agent/conftest.py — *source:* spec §13
- RR2 R-C1 repro: script `HttpTransport._send_once` so GitHub stores the issue then answers 502, apply the hint's two expressions → 2 issues; the fix is the hint literal (one line, S062) + agents/output/README.md:98-99 + lib/outputs/README.md:145-146 (+ spec §9.2/AC-24/EC-42 by the spec author) — *source:* S5 re-review 2
- The adjacent string literals at errors/base.py:486-497 are main's pre-existing code; do not copy them (S062) — *source:* S5 re-review 2
- `smtplib.SMTPServerDisconnected` is both SMTPException and OSError; any read timeout after TCP connect is `smtp_error`, only connect/TLS-handshake OSError is `network` — *source:* S5 repair-3
- Git Bash: `semgrep --test … > /dev/null` exits 2 despite passing; read the exit code unredirected — *source:* S5 repair-3
