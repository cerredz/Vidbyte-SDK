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
| S0 worktree + capture + recon | done | 2026-10-13 | 2026-10-13 | reports/S0-scout.md | base_commit 336d6c78 (merge of origin/main 8387d666 into 4ee040b7) |
| S1 spec + review | done | 2026-10-13 | 2026-10-14 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-2.md | r1 09f7c42d → review 1 (0B/3M/5m, 7c670413) → r2 0dca4e0c → review 2 (1B/2M/7m, c0b83578) → **r3 8cabad5e, status approved** (FR 35, NFR 10, AC 36, EC 46, D 26, INV 18, Q-1…Q-8 all default No; 7 new files) |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 (cap reached; r3 is the last revision, disputes become Q-n) · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-13 — Build on the existing PR #882 branch, not a new branch from main — the user said "implement these things on the pr" (request.md §A Prompt 10).
- 2026-10-13 — Local branch is `feat/output-connector-followups` tracking `origin/feat/agent-output-connectors`; every push is `git push origin HEAD:feat/agent-output-connectors` — another session's worktree (`C:/Users/422mi/vidbyte-repos/worktrees-sdk/feat/agent-output-connectors`, clean, at 4ee040b7) has the PR branch checked out, and git forbids one branch in two worktrees.
- 2026-10-13 — Merged origin/main (8387d666) into the branch at S0 as merge commit 336d6c78 (conflict-free; branch was 15 behind) — checklist §0 "merge main into the branch"; catch-up by merge, never rebase. This is BASE_COMMIT; reviewers diff `336d6c78..HEAD`.
- 2026-10-13 — Scope = every checkbox of request.md §B sections 0–5, EXCEPT: "Mark the PR ready" (user's call); "Next, if you want them"; "Linear and Jira versions, only if you ask"; the "Don't build" list; bot tokens (Q3 default no); HTML email (Q4 default no). INCLUDED: optional Telegram `topic_id=`; all five §4 connectors (user did not narrow "pick 3–5"); Google Chat Markdown only if official docs confirm the field on the webhook's create call.
- 2026-10-13 — New slug folder `docs/spec/output-connector-followups/` instead of revising the first batch's spec in place — keeps the closed run's review/verify-log intact; the first spec gets only its §9.2(b) corrections.
- 2026-10-14 — S1 author was stopped by a session restart before writing anything; resumed via SendMessage (not relaunched) to keep its vendor-doc research; it then wrote and committed r1 (09f7c42d). Its report was left uncommitted; orchestrator committed it (bb4491c3).
- 2026-10-14 — S1 reviewer round 1 hit a 429 usage limit after its report skeleton; resumed via SendMessage after the reset (not relaunched). Verdict SOUND WITH FIXES; all 8 findings forwarded; author applied all in r2 (0dca4e0c).
- 2026-10-14 — Ran a scoped round 2 (focus: r2 edits + dependents) because R-1/R-8 fixes changed §10 security controls and a public field (`signing_key` bounds). Verdict SOUND WITH FIXES, 1 Blocker / 2 Major / 7 Minor, none scope-adding; all 10 forwarded verbatim (report path) to the same author with instruction to freeze r3 as `status: approved` (the two review rounds are the approval; no user gate per skill rule 8).
- 2026-10-14 — S2 exception to the test-author template's hard rule 5 ("never modify an existing test's assertions"): the test author MAY update exactly the first-batch expectations listed in spec §13 (wire bodies, counts, ordered lists, env-var map, README date pin), each logged in test-plan.md with its spec ID; nothing else may change, nothing may be weakened, skipped, or deleted — the spec changes those default wire shapes on purpose, so the old pins assert superseded behavior. S3's no-test-edit check then runs against S2_HEAD.

## User replies (verbatim)
- 2026-10-13 — "great, implement these things on the pr"

## Niche facts accumulated (carried into every later briefing)
- Push with `git push origin HEAD:feat/agent-output-connectors` (local branch name differs from the PR branch) — *source:* orchestrator S0
- Anti-stall rules for every agent: give every subprocess a timeout and stdin from /dev/null; export `GIT_TERMINAL_PROMPT=0 GIT_EDITOR=true`; at most 2–4 throwaway experiments; write the report skeleton first — *source:* memory (2026-10-13 two-repo run)
- Merging main into a branch whose `vidbyte/__init__.py` exports changed can leave `contracts/sdk-public-api.json` `source.commit` stale; run `scripts/generate-sdk-public-api.py` and commit the regen separately if the C016/contract gate asks — *source:* memory
- At every S5 convergence check `gh pr view 882 --json mergeable,mergeStateStatus`; SDK main moves ~1 commit/10 min, so stop at MERGEABLE/BEHIND — *source:* memory
- vidbyte-cli draft PR #166 depends on `SlackOutput`, `GitHubIssueOutput`, `LinearIssueOutput` constructors and the root `OutputDispatcher` export (commit 4272c308): no breaking changes — *source:* memory
- No-test-edit check across merge commits: `git show --cc --format= <merge> -- tests/` is empty; plain diffs from BASE_COMMIT include only this run's work — *source:* memory
- The SDK lint pass line is `SDK-LINT: PASS` (lint/core/report.py:58), not `AGENT-LINT: PASS` — *source:* S0 scout
- `OutputHttp.post` is POST-only and returns only a receipt (no response JSON); `OutputRequest` has no method field and takes only a JSON-object body; `_link` walks dicts only and only prepends a prefix — *source:* S0 scout
- `HttpTransport._send_once` serializes `json_body` itself (transport.py:79); no raw-bytes parameter exists; `idempotency_key` is local only and PATCH needs one before it can be retried — *source:* S0 scout
- Changing default chat wire shapes (Slack, Teams, Telegram, Jira, Google Chat) breaks first-batch tests that pin exact bodies; five new connectors break the 18-name export count, the ordered destination list, the env-var map test, and the docs test requiring "2026-10-11" in every env-var row — *source:* S0 scout
- No Markdown, ADF, or HMAC helper exists in vidbyte/lib; the only S061-approved file writer is the synchronous `LocalFileSystemBackend.append_text` — *source:* S0 scout
- `OutputArguments.text/texts/matching/address/identifier` echo the bad value in errors — never pass secret header values or `secret=` through them; only `credential` and `https_url` hide values — *source:* S0 scout
- `OutputRequest.headers` rejects non-lowercase keys; S105 flags constants with `token`/`secret` name segments; A002 needs `# @intent` on functions mentioning secret/request/send/fetch — *source:* S0 scout
- Test fake `HttpScript` always returns `headers={}` (no Link pagination yet); every `_send_once` fake takes `**kwargs`; autouse `isolated_output_env` clears only the 11 output env vars (not GITHUB_STEP_SUMMARY); the layering test globs only direct children of vidbyte/lib/outputs/*.py — *source:* S0 scout
- Job-summary file write can trip S047 (blocking open in async), S061 (non-literal paths), S041 (explicit encoding); first batch forbade asyncio.to_thread for SMTP and used a dedicated executor — *source:* S0 scout
- Spec r1 design: 7 new files (adf.py, github_api.py, gitlab.py, github_job_summary.py, confluence.py, typefully.py, hubspot.py); `HttpTransport.request(content=)` for exact signed bytes; `OutputHttp.patch`/`.read` with `OutputRead`/`OutputMethod`; `OutputRequest.json_body` may be None plus a `content` field; GitHub `key=` drives sticky comment and one-issue-per-key via list endpoints, ≤ 10 pages; Google Chat Markdown NOT built (D-24, live check L-3) — *source:* S1 author r1
- Spec §13 lists the first-batch test expectations that must change (Slack ≤ 12,000 chars → `markdown` block; Telegram → `sendRichMessage` `rich_message.markdown`; Teams card two blocks; WIRE_ROWS/CAPPED, mention test, dispatch.py:125/148/315, acceptance.py:97, agent_wiring.py:62; ROOT_NAMES 18→24; LIB_OUTPUT_MODULES +7; README date pin 2026-10-11 vs new rows 2026-10-14; OUTPUT_ENV_VARS gains GITHUB_STEP_SUMMARY) — *source:* S1 author r1
- Notion append = PATCH `{"type":"insert_content","insert_content":{"content":...}}`, no `url` in response → SENT with url=None; Confluence create returns 200; GitLab MR note has no link; §9.2(b) SMS count is 8 (Telesign is form-encoded) — *source:* S1 author r1
- Never add an A001 header to `vidbyte/lib/http/transport.py` (predates this PR) — *source:* S1 author r1
- r2 design deltas: Telegram replaces every `<` with fullwidth `＜` before the cap (INV-18, EC-43/44); NFR-7 deadline is honest (one request can take ~31.5 s; a cut during the write is ambiguous, EC-45); webhook `signing_key` must decode to 24–64 bytes (`WEBHOOK_KEY_MIN_BYTES`/`MAX`); exact regexes in §12.3 row 3; Q-6 (Telegram skip_entity_detection), Q-7 (write-budget check), Q-8 (sticky-marker author filter) all default No — *source:* S1 author r2
- Lint is count-ratcheted: a plain `SDK-LINT: PASS` can hide new violations in rules with room. Check touched files with `python lint/run.py --rule <R> --all` for A002 (579/703), S061 (5/6), S001 (56/59), S017 (78/79), S025 (261/263), C011 (1/2), C012 (23/24). S054 is 3/3 (no room). S008 = Ruff C901/PLR0912/PLR0915 at 10/12/50; S024 max depth 3 — *source:* S1 reviewers r1+r2
- `OutputHttp.post` calls `_error_code` (delivery.py:85) and `_link` (:90) directly; a shared `_write` must not add a second hop in the same class (Style 1) — move the readers to a second class (R-9) — *source:* S1 reviewer r2
- Wire test asserts exact `json_body` equality (test_output_connectors_wire_contract.py:101); HubSpot `hs_timestamp` needs `unittest.mock.ANY`; Confluence `body.value` is a JSON string sensitive to key order — *source:* S1 reviewer r2
- Teams cap test sends `OutputContent("Load test", "x"*7000)` (body does not open with its title): title-line stripping must be conditional (R-11) — *source:* S1 reviewer r2
- Telegram Rich Markdown `![](https…)` posts media as the bot (R-10 → neutralize `![`); httpx 0.28.1 accepts port 99999 in a URL, only `urlsplit().port` raises (R-17) — *source:* S1 reviewer r2
- r3 design deltas: `_error_code`/`_link` move unchanged into a new static `OutputResponses` class in `delivery.py` (in its `__all__`, NOT re-exported from `vidbyte.lib.outputs`); Telegram makes exactly two length-preserving `str.replace` calls before the 32,768 cap (`<` → U+FF1C, `[` after `!` → U+FF3B, `TELEGRAM_MEDIA_*` constants); Teams drops the first body line only when `first_line(body) == title`; `ADF_BREAK_PATTERN = r"[ \t]*[-*_][-*_ \t]*"` checked before bullets, a lone `-` stays a paragraph (EC-14); GitLab port pattern `[1-9][0-9]{0,4}` then `urlsplit` range check (no numeric literal, A007); webhook header errors name only the position, non-mapping `headers` only the type name; AC-10 uses `S3CRET` inputs — *source:* S1 author r3
- Least-sure assumptions for live checks: A-1 (Slack webhook accepts `markdown` block; L-1 before ready), A-9 (GitHub auto-creates a missing label), A-13 (HubSpot v3 tasks without associations); L-2 decides the Telegram `<` rule — *source:* S1 author r3
- `test_output_connectors_agent_wiring.py:62` and `dispatch.py:315` pass unchanged (one-line replies); env-var test iterates `HTTP_DESTINATION_KEYS`, missing-credential test iterates `ALL_DESTINATION_KEYS`; `vidbyte/lib/outputs/README.md:140-148` Deadline footgun needs `file_error` — *source:* S1 reviewer r2

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
