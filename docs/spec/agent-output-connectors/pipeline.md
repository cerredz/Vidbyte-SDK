---
slug: agent-output-connectors
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-output-connectors
branch: feat/agent-output-connectors
base_commit: db3988ffdb4d580021ec4dae995281135f8f0a0f
pr: https://github.com/cerredz/Vidbyte-SDK/pull/882
until: none
started: 2026-10-11 17:36
---

# Pipeline: Agent output connectors

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-11 17:36 | 2026-10-11 17:52 | reports/S0-scout.md | base_commit db3988ff; code-map.md (4 sections, 477 lines) |
| S1 spec + review | done | 2026-10-11 17:55 | 2026-10-11 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-r2.md | spec r3 @1335db49 approved; r1 NEEDS REWORK (1B/5M/5m) → r2 SOUND WITH FIXES (0B/2M/5m), all 18 accepted |
| S2 tests | done | 2026-10-11 | 2026-10-11 | reports/S2-test-author.md | 86 tests / 313 cases in tests/features/agent_output_connectors/ (9 modules); red `21 failed, 292 errors`; test commit d90400d2; S2_HEAD 72fc2002; 7 spec defects → spec r4 @f3229734; status tests-written @5e79413f |
| S3 implement | done | 2026-10-11 | 2026-10-11 | reports/S3-implementer.md | S3_HEAD 9463c348; draft PR #882; 313/313 green (re-run by orchestrator); SDK-LINT PASS; run_ci source 3516 passed + full CI passed; budget 23/23 files, 26/26 classes, 0 deps; ci.yml 38194285572 in progress, static-policy 38194287162 success (both at fa430c8f; later commits docs-only) |
| S4 adversarial review | done | 2026-10-11 | 2026-10-11 | reports/S4-review-{conformance,conventions,engineering}.md, S4-findings-verifier.md | review.md: MERGEABLE AFTER FIXES; confirmed 1 Blocker (R-1 httpx INFO log leaks secret URLs) / 3 Major (R-2 str destination, R-3 SMTP thread holds sync run past deadline, R-4 duplicated email rule) / 11 Minor; 0 refuted (1 sub-claim) |
| S5 repair loop | done (converged at iteration 1) | 2026-10-11 | 2026-10-12 | reports/S5-repair-1.md, verify-log.md | merge ba83c953 (origin/main, no conflicts); 12 findings fixed one commit each; HEAD ed1dd67b; 340/340; SDK-LINT PASS; run_ci source 3743 passed; full run_ci CI passed (re-run by orchestrator at ed1dd67b); Semgrep 0; remote ci 38211917706 + static-policy 38211919803 success @1348b728; review.md 0 open |
| S5 re-review | done (round 1/2) | 2026-10-12 | 2026-10-12 | reports/S5-rereview.md | SOUND: 0 Blocker / 0 Major / 2 Minor (R-C1 Telegram ctor raise not recorded as deviation; R-C2 E302 blank line email.py:32); all 12 fixes hold; merge clean; §4 snippet byte-equal |
| S5 re-review | done (round 2/2) | 2026-10-12 | 2026-10-12 | reports/S5-rereview-2.md | SOUND: 0 Blocker / 0 Major / 2 Minor (R-C1 resend hint warns only about `network`, but EC-5 http_5xx-after-create and EC-24 smtp_recipients_refused can also already be delivered → following it duplicated a GitHub issue in a probe; R-C2 pr-body.md still calls S6-1/S6-2 "not fixed" + stale Telegram rationale); S6-1/S6-2 hold; merge clean; S008 10/9/50; AC-1/AC-15/contract hold; full pytest 3824 passed |
| S6 PR | body written; reopened S5 for 2 Minors | 2026-10-12 | | reports/S6-pr-author.md | PR #882 retitled (no [WIP]), draft, 1 mermaid, spec pr-open @ae6115f4; ci 38215600229 + static 38215602359 success @ae6115f4; AC-18/AC-24 proofs exist on branch |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 3/8 (iteration 2 = S6 follow-ups; iteration 3 = re-review-2 R-C1 wording) · S5 re-review rounds: 2/2

## Decisions the orchestrator made
- 2026-10-11 17:36 — Slug `agent-output-connectors`, branch `feat/agent-output-connectors`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-output-connectors` — pipeline defaults; SDK AGENTS.md defines no override.
- 2026-10-11 17:52 — `CodexHarnessAgent` is NOT given the parameter by default — Prompt 4 names only BaseAgent, JevAgent, CodingAgent, and the scout found `CodingAgent(BaseAgent)` (coding.py:27), so the earlier ledger's CodexHarnessAgent mention is superseded; carried as an optional Q-n (default: not included).
- 2026-10-11 17:52 — "forks do not inherit outputs" vs "as_tool delivers on every call" contradiction (AgentTool.execute runs on a fork, tools/agent_tool.py:59): not a user decision (both lines were assistant-proposed consequences); the spec author resolves it from the code and records a D-n.

- 2026-10-11 — Committed the S1 author's report (Stage F only stages spec.md) — keeps reports on the branch.

- 2026-10-11 — Q-1..Q-10 take their stated defaults (all "No"/"Not built"): no CodexHarnessAgent outputs; as_tool/sub-agents (forks) do not deliver; no HMAC webhook; no Session.resume outputs=; render cannot return None; receipts not persisted; no YAML; Q-8/Q-9/Q-10 scope-adding not built — S1 summary printed, no user reply.
- 2026-10-11 — Pointed the author at the reviewer report by path rather than pasting the findings block, to keep orchestrator context lean; one-line summaries of every finding were included in the message.

- 2026-10-11 — S2 spot-check passed: tree clean, vidbyte/ untouched, all 26 AC in test-plan, re-ran acceptance (2F/4E) and dispatch (42E) red for missing modules; spec diff = Proof cells only.
- 2026-10-11 — Sent S2's 7 spec defects (AC-18 vacuous, AC-19 wall clock, §13 seam reach, AC-4 re-prompt, AC-12 named agent, AC-23 split, AC-20 single-connector) to the S1 author (resumed, revision mode) → r4 @f3229734; not counted as a review round. Checks (a)–(h) of test-bound details: none conflicted; (e)(f)(h) added to spec. Verified r4 left tests/, test-plan.md and Proof cells unchanged.
- 2026-10-11 — S2_HEAD = 72fc2002 (test tree baseline for S3/S5/S6 diffs; tests last changed in d90400d2).
- 2026-10-11 — S2 built a throwaway prototype in its scratchpad (outside repo, never committed) to mutation-test the suite (71/72 caught); accepted, since nothing under vidbyte/ changed.

- 2026-10-11 — S3 BLOCKED at row 27: S008 (C901 ≤10 / PLR0915 ≤50, baseline 19) — `_generate_reply` is 10/50 on base; inline block → 12/57 REGRESSED. Decided myself (not product intent): baseline raise forbidden (hard rule); move delivery to `_deliver_outputs` + gate-forced `_record_last_trace` extraction; two-hop chain accepted because S008 is an enforced gate and Style 1 is "shape to aim for", with repo precedent `_assert_schema_satisfied` → `_notify_session_exception` (base.py:962). Reverses R-13. Spec r5 @c29fabf4 (S3-1), plus lint-forced renames `*_MENTION_TOKEN`→`*_MENTION_PREFIX`, new `OUTPUT_ERROR_TOKEN_MAX_CHARS` (S3-2).
- 2026-10-11 — Accepted r5's guarded form (`if self.outputs: await self._deliver_outputs(...)` in `_generate_reply`, measured 10/9/50 = base, no new S008 finding) over the unguarded 9/8/49, because it keeps INV-22 ("adds no await" without outputs) as written.
- 2026-10-11 — CONFLICT `OutputArguments.optional_callable(value: object, ...)` (spec §8.5:595) vs S3's `Callable[[AgentMessage], OutputContent] | None` annotation (mypy `disallow_any_generics`, runtime check unchanged): accepted as an S3 implementation deviation recorded under spec §17, no spec edit.

- 2026-10-11 — S3 spot-check passed: tree clean, test diff vs 72fc2002 empty, all non-docs commits cite IDs, local HEAD == origin, PR #882 draft `[WIP]` MERGEABLE, spec `status: implemented`, `pr:` set.

- 2026-10-11 — S4 spot-check passed: review.md confirmed rows each carry path:line + verifier's own evidence; refuted sub-claim (R-V1 https drift) cites D-19/§9.1/D-21.
- 2026-10-11 — S5 prep ordering: findings need three owners (spec-author: R-5, R-3/R-11 wording, R-13 [scope-adding] → Q-n; test-author: R-1, R-2, R-3, R-12, R-14, R-15 tests; repair: all source). Run sequentially (spec r6 → test additions, red → repair iteration 1) because spec author and test author both edit spec.md. Test additions come from the S2 test author only (pipeline rule); repair agents get no test diff.

- 2026-10-11 — Spec r6 @a270e6ed (spec-author aligned S4 findings: R-1 httpx log filter, R-2, R-3 dedicated SMTP executor, R-4/R-9 constants, R-5 INV-2, R-11 resend caution, R-12 EC-48, R-13 → Q-11 not built + EC-49, R-15). Verified spec+report only, Proof cells unchanged.
- 2026-10-11 — S2 test author added S4 tests @45ba29cc (+27 cases → 340; red `16 failed, 324 passed`, re-run by orchestrator; vidbyte/ untouched; no existing assertion removed; httpx_destination fixture moved to conftest). New test-tree baseline S2_HEAD_2 = 7f3bb7ff; S5/S6 diff tests against it.
- 2026-10-11 — ci.yml 38194285572 at fa430c8f (S3 code) completed success (Source 3.11, 3.12, Package).

- 2026-10-12 — Session restarted mid repair-1; the agent had made no commits (tree clean at 78321115). Resumed the same agent. origin/main moved 25 commits (#759, #768-#772, #769, #873-#886); overlap with our diff: vidbyte/agents/README.md, vidbyte/agents/fork.py, vidbyte/lib/enums/__init__.py; base.py not touched by main. Added step 0 to iteration 1: `git merge origin/main` (never rebase), resolve, regenerate the public-API contract if needed, then fix findings on the merged base.

- 2026-10-12 — Repair-1 spot-check passed: tree clean; pack test diff vs 7f3bb7ff empty; non-pack test diffs vs merge-base empty (only main's); every repair commit cites R-n; HEAD == origin; remote green. R-5/R-13/R-14 statuses closed by the repair agent at my request (resolved outside repair: spec r6 / Q-11 / test author). Orchestrator full `python scripts/run_ci.py` at ed1dd67b: `CI passed.`
- 2026-10-12 — main 5 commits ahead again (#767, #888, #887, #746, #763), no overlap with our files → PR still mergeable; no second catch-up merge needed before S6 unless GitHub reports a conflict.

- 2026-10-12 — Re-review SOUND → loop converged. Applied the two trivial Minors anyway (one blank line; one §17 deviation bullet) by resuming the repair-1 agent instead of a fresh iteration: both are mechanical, no finding needs verification, and a fresh agent's orientation would cost more than the fix. Logged as a polish pass, not counted as iteration 2.

- 2026-10-12 — Polish pass done @12729d09 (R-C2 blank line ad4ed50a; R-C1 §17 deviation 0ca19568); 340 passed, SDK-LINT PASS, run_ci source 3743 passed; remote ci 38214072413 + static-policy 38214075610 success @12729d09. Test-tree check corrected: pack diff vs 7f3bb7ff empty, `git diff ba83c953..HEAD -- tests/` empty (non-pack differences vs 7f3bb7ff are main's, via the merge). Spec status → verified.

- 2026-10-12 — S6 spot-check passed. S6 OPEN ITEMS name two Minor code defects: (a) `EmailOutput(to=[])` error names `recipients` not `to` (email.py:50, dataclasses/outputs.py:112-113; AC-20 says name the parameter); (b) `OutputDeliveryError` repair hint (errors/base.py:215) says `deliver(failed, …)` but `err.failed` is receipts → `unexpected:AttributeError` when followed. Per skill, code defects found at S6 go back to S5: test author adds the AC-20 `to=[]` case (red) → fresh repair agent iteration 2 (catch-up merge of origin/main, 7 commits incl. #885 coding.py, #889 runtime.py; fix a + b) → resume S6 author to refresh the body.

- 2026-10-12 — Test author added AC-20 `email-empty-to` @4b063c28 (red for the right reason). Repair-2 (fresh agent) @81f9cba0: merge d4100704 (8 main commits, no conflicts; INV-9 allowlist still matches runtime after #889/#887; #888 header behaviour fine), S6-1 5b437f24 (`OutputArguments.non_empty`, names `to`), S6-2 2334385b (hint = zip recipe). Spot-check: 341 passed (re-run by me), pack diff vs d87fcbaf empty, tests/base.py/lint unchanged since merge, review.md 0 open, ci 38217869950 + static 38217872582 success @81f9cba0.
- 2026-10-12 — Stop chasing main: #891/#856 landed during repair-2; merge-tree clean, PR mergeable; a further catch-up is left to the user at merge time (re-measure S008 if #891's base.py change is merged).
- 2026-10-12 — Spending re-review round 2/2 (focused on ed1dd67b..HEAD: merge + S6-1 + S6-2) in parallel with spec r7 (name `OutputArguments.non_empty` in §8.5, row 13, §17) — the change set re-entered repair after the SOUND re-review, and the user is comparing quality.

- 2026-10-12 — Spec r7 @5bd94199 (docs only: §8.5, rows 5/13/25, §16 S6-1/S6-2, Telegram §17 bullet); verified by `git show --stat` (spec.md + S1 report only), status pr-open, pushed.
- 2026-10-12 — Re-review 2 SOUND with 2 Minors. Fixing RR2 R-C1 anyway in repair iteration 3 (fresh agent), scoped to wording only: the SDK's own error advice contradicts request.md §C ("the first post may have landed") and EC-5's "at most one issue exists", and a user following it double-posts — a real behavior change for callers, not cosmetics. No re-review rounds remain, so I verify iteration 3 myself (file list, gates, pack diff). Then spec r8 aligns §9.2/AC-24/EC-42 to the new literal, then the S6 author refreshes pr-body.md (covers RR2 R-C2).

- 2026-10-12 — Repair-3 spot-check passed @9dadba0a: code commit 563efc51 touches only errors/base.py (1 line) + 2 READMEs; lint/ unchanged; pack diff vs d87fcbaf and tests/ diff vs d4100704 both 0 lines; 341 passed (re-run by me); ci 38220771957 + static 38220773950 success on 9dadba0a (checked via gh run view). Caution now names network, invalid_response, smtp_error, smtp_recipients_refused, and codes starting http_5 — wider than the reviewer's list, each derived from the code that builds it (invalid_response only after a 2xx; smtp_error covers a reply timeout after DATA). Accepted: all five can follow a stored post.
- 2026-10-12 — Spec r8 next: align §9.2, AC-24, EC-42, row 25 with the final literal, and correct EC-46 (`port=2465` yields `smtp_error`, not `network` — code is right, the spec mis-predicted; no test pins it). Then S6 refresh (RR2-C2 + final verification table).

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
