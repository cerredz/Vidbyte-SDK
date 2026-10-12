# S1 spec author report: agent output connectors

- **Stage:** S1 spec author
- **Date:** 2026-10-11
- **Spec:** `docs/spec/agent-output-connectors/spec.md`, revision r3, `status: approved` (r1 at `6248fc96`, r2 at `7158ee2b`, r3 in the commit that adds the "Revision r3" section below)
- **Commit (r1):** `6248fc96`

The r1 run wrote and committed only `spec.md`; the orchestrator committed this report. The r2 run, at the end of this file, changed only `spec.md` and this report and committed both. It created no source, test, or stub files. It ran no gate and installed nothing.

## What I read

### Pipeline inputs (read in full)

- `docs/spec/agent-output-connectors/request.md`
- `context/code-map.md`
- `reports/S0-scout.md`
- the spec template
- `house-style.md`
- the orchestrator briefing

### Repo guidance

- `AGENTS.md`
- `REPO_MAP.md`, for these entries:
  - the `vidbyte/agents/` subtree
  - `vidbyte/lib/` and its subfolders
  - `vidbyte/providers/`
  - `vidbyte/lib/http/`
- folder READMEs:
  - `vidbyte/agents/README.md`
  - `vidbyte/agents/jev/README.md`
  - `vidbyte/lib/README.md`
  - `vidbyte/tools/builtins/operations/clients/README.md`

### Field guide (`field-guide/vidbyte-sdk/`)

- `comment-format.md`
- `class-bound-helpers.md`
- `strict-config-dataclasses.md`
- `provider-api-contracts.md`
- `blocking-lint-invariants.md`
- `jev-capability-layout.md`
- `prebuilt-agents.md`
- `local-ci-verification.md`
- `agents-md-map.md`
- `review-scope.md`

### Source (read in the sections cited by the spec)

**Agents**

- `vidbyte/agents/base.py`:
  - `__init__`
  - the runtime rejections at 128–162
  - `_generate_reply` at 896–934
  - `_assert_schema_satisfied` at 947–963
  - `_notify_session_exception`
  - `_drain_queued_prompts` at 1073–1107
  - `restore`
  - `run` and `arun`
- `vidbyte/agents/fork.py`: lines 53–81
- `vidbyte/agents/jev/settings.py` and `vidbyte/agents/jev/agent.py`: lines 90–102
- `vidbyte/agents/coding.py`
- `vidbyte/agents/runtime.py`: `_middleware_abort_result` and `_runtime_metadata`
- `vidbyte/agents/codex/agent.py`: lines 100–178
- `vidbyte/tools/agent_tool.py`: line 59

**Lib**

- `vidbyte/lib/http/transport.py`: `request`, and `_send_once` at 59–66
- `vidbyte/lib/errors/base.py` and `vidbyte/lib/errors/__init__.py`
- `vidbyte/lib/registries/models.py`: lines 151–161
- `vidbyte/lib/dataclasses/agents.py`: `AgentStopReason` and `AgentMessage`
- `vidbyte/lib/dataclasses/config.py`: lines 23–29
- `vidbyte/lib/enums/__init__.py`
- `vidbyte/lib/constants/speed.py`

**Other**

- `vidbyte/sessions/session.py`: `record_turn` at 182–188, and line 459
- `vidbyte/tools/builtins/operations/clients/_base.py` and `brave.py`
- `vidbyte/tools/builtins/operations/fetch.py`: line 223
- `.semgrep/typed-mapping-boundary-policy.yml`
- `pyproject.toml`

I re-verified every `path:line` reference in the spec against this worktree before committing.

### Platform research

Three parallel research agents ran on 2026-10-11:

- chat and messaging
- trackers, docs, and storage
- email, alerting, and automation

Their findings are cited row by row, with official URLs, in spec §9.2 tables (a) and (b). I spot-checked these myself:

- Notion's `markdown` parameter: `markdown_version` defaults to v1, and the parameter is mutually exclusive with children.
- Notion's page-parent shape.
- X `POST /2/tweets` and LinkedIn sharing are OAuth-only.
- The Gmail API needs OAuth.

## Approaches weighed

**Chosen: the contract plus one class per destination in a new `vidbyte/lib/outputs/`, with the linking dispatcher in `vidbyte/agents/output/` (D-1, D-2).**

The user placed "the abstraction" in `agents/output/` and the provider logic in lib or providers. Lint rule A006 forbids any lib or providers module from importing `vidbyte.agents`, and it counts function-local imports. So a connector in lib cannot subclass a base class that lives in `agents/output/`. Moving the contract down to lib is what AGENTS.md prescribes ("move the contract down"). It keeps each platform to one class. `agents/output/` keeps the part the user described as "linking the provider and agent logic": the dispatcher, plus the public re-export package.

**Rejected placements and shapes**

- **A `Protocol` in lib plus an abstract base in `agents/output/`.** Every platform would need two classes and the codebase would carry two contracts.
- **`vidbyte/providers/outputs/`.** REPO_MAP defines `providers/` as the model-vendor layer. Its `__init__` eagerly imports every model adapter, and its README covers model contracts only. The user allowed either folder, so purpose decided it.
- **A delivery loop inline in `BaseAgent`.** `base.py` is already 1,694 lines. This also contradicts the user's placement of the linking logic.
- **Smaller designs (§8.3):**
  - Slack plus a webhook only. This fails the user's request for a list of platforms.
  - One templated generic webhook. Mentions, caps, auth forms, and link extraction differ for every destination, so the templates would grow into a DSL.
  - No `OutputContent` record. That means 11 copies of the shaping rule.
  - Per-connector `*Settings` records. That means 10 one- to three-field records; the checks are already single-sourced in `OutputArguments`.

## Where I disagreed with the scout or the request (with evidence)

1. **Registry name.** The request names `ModelRegistry.resolve_api_key`, but the class is `ProviderModelRegistry` (`vidbyte/lib/registries/models.py:151-161`). The spec cites the real symbol.
2. **Forks versus `as_tool`.** The request says forks drop outputs and also that `as_tool` delivers on every call. Those contradict each other, because `AgentTool.execute` runs on `self._agent.fork()` (`vidbyte/tools/agent_tool.py:59`). I chose "forks never deliver" (D-7) and recorded the other option as Q-2, default no. Both lines were proposals by the assistant, not decisions by the user.
3. **Per-kind payload dataclasses.** The request's implementation hints suggested payloads per kind (chat, email, issue). Every one of the 11 destinations needs only a title and a body per reply. Labels are per-connector configuration in the approved snippet (`labels=("bug",)`). One `OutputContent` record replaces them (D-10), and the flip condition is recorded.
4. **JevAgent wiring.** The request said "bolt it on JevAgent". `tests/test_jev_agent.py:504-509` pins the constructor, and AGENTS.md routes new capabilities to `JevAgentSettings` fields. So outputs arrive as `JevAgentSettings.outputs` (D-8).
5. **Blank-content skip.** The request's skip rule covered only aborted replies. I added "blank content" as well: Slack answers 400 `no_text` and Discord rejects an empty `content`, so a blank reply would turn into false failures. This is guarded by INV-9. The assumption it rests on is A-12: valid structured replies always carry non-blank JSON content.
6. **Teams.** The conversation treated Teams like Slack. Two things change that. Office 365 connector webhooks stopped working in May 2026, and Workflows URLs accept only Adaptive Card envelopes. A 202 response means "accepted", not "posted" (A-2). Only "Anyone" flows avoid OAuth. All of this is recorded in EC-30 and catalog row a-3.
7. **Notion.** The conversation assumed block conversion would be needed. `POST /v1/pages` accepts a `markdown` body parameter, so no converter is required (D-18, A-6).
8. **Gmail.** Gmail has no separate connector. Without OAuth it is reachable only over SMTP with an app password. It is a configuration of `EmailOutput` (D-12). The Gmail API itself goes in table (b) as OAuth-only.
9. **Retries.** The request allowed full retries where a provider idempotency key exists. None of the 11 destinations offers a documented replay-safe key. Linear's `IssueCreateInput.id` rejects a duplicate rather than replaying it. So retries are 429-only (D-5).
10. **Lint result line.** The gates reference expects `AGENT-LINT: PASS`, but `lint/core/report.py:58` prints `SDK-LINT: PASS`. The spec uses the real line.
11. **Placement of the handoff sibling.** The S0 map treats the handoff as a post-reply sibling. In fact `_run_auto_handoff` runs *before* `_notify_session` and `_assert_schema_satisfied` (`base.py:920-931`). Delivery therefore follows the schema-check precedent instead, sitting between line 931 and the drain (D-3, INV-26).

## Assumptions I am least sure of

- **A-6, Notion `markdown`.** That Notion's `markdown` handles typical LLM markdown under `2026-03-11`. If it does not, the fallback is the block route, which is a larger change.
- **A-1, GitHub limits.** That GitHub's 65,536-character body limit and its title limit hold. Both were observed in practice and are not documented.
- **A-2 and A-3, Teams.** That Teams 202 semantics behave as described, and that a plain TextBlock cannot mention anyone. Both come from community reports and card docs, not a contract.
- **A-5, Google Chat mentions.** That only `<users/…>` mentions people in Google Chat webhook text.
- **A-7, Jira tokens.** That unscoped Jira API tokens over Basic auth keep working. Atlassian is pushing scoped tokens, which need the `api.atlassian.com` route (NG-12).
- **A-11, GitHub API version.** That GitHub API version `2026-03-10` keeps the create-issue fields unchanged.
- **A-13, runtime coverage.** That every `AgentRuntimeType` replies through `_generate_reply`. This is taken from code-map §4 and was not re-traced for the MCTS and actor runtimes.

## Self-check (Stage E)

- **Section headings** match the template exactly (verified with a diff).
- **IDs:** every referenced ID is defined, and none is duplicated. The counts:

  | ID | Count | ID | Count |
  |---|---|---|---|
  | G | 4 | D | 21 |
  | NG | 12 | W | 12 |
  | INV | 28 | T | 5 |
  | AC | 26 | A | 14 |
  | EC | 42 | Q | 7 (0 blocking) |
  | FR | 20 | | |
  | NFR | 8 | | |

- **Traceability:** every FR maps to an INV or AC, every AC appears in a W row, and every §12.3 row names a standard and what it serves.
- **File budget:** the §12.3 new-file count is 22, which equals the §8.4 budget.
- **Corrections during the check:**
  - The §8.4 class count was 25 and is now 24, across 18 modules.
  - One weighted-word quote lost its original double space; it is restored.
- **Verbatim text:** the Prompt 4 text in §0.1 is verbatim from request.md.
- **No test cases** appear anywhere in the spec.

## Revision r2 (S1 review round 1)

The review (`reports/S1-spec-review.md`, commit `a028eb6d`) returned NEEDS REWORK: 1 Blocker, 5 Major, 5 Minor. I read "WHAT THE SPEC GETS RIGHT" first and kept every item on it: the delivery point and metadata identity; lowercase headers, `retry_status_codes=(429,)`, `follow_redirects=False`, and `max_response_bytes`; the Jev settings field and CodingAgent `**kwargs`; forks with `outputs=()`; credential order and masking; the error-code grammar; and the 17 root exports.

### Dispositions

All eleven findings are **Accepted**. None was rejected or deferred.

| ID | Severity | Change |
|---|---|---|
| R-1 | Blocker | Re-cut at the provider boundary. `vidbyte/agents/output/` now holds the `OutputConnector` Protocol (`connector.py`), `OutputShaping` (skip rule and title/body shaping), and `OutputDispatcher` (render-or-shape, type check, `send`). `vidbyte/lib/outputs/` keeps provider work only. D-2 quotes all three Prompt 4 clauses and cites AGENTS.md Style 3, not A006. |
| R-2 | Major | INV-9 skips any `stop_reason` outside `OUTPUT_DELIVERABLE_STOP_REASONS` (`final_response`, `is_done`). Added D-22, AC-8 (c), EC-43, and A-15. |
| R-3 | Major | INV-16, D-7, NG-5, and EC-21 now cover only agents the SDK builds. Added EC-44 (Jev specialist, Aggregate proposer or aggregator) and EC-45 (pipeline, workflow, and MCP stages), plus README footguns. Q-8 is scope-adding and not built. |
| R-4 | Major | `single_line` is `" ".join(text.split())[:limit]`, with no marker and no call to `truncate`. |
| R-5 | Major | D-21 and row 7 order: parse, walk, non-blank str, prefix, then the `https://` check. |
| R-6 | Major | §11 typecheck is S009 (mypy, baseline 350). Added a §12.4 typing line; `render` is typed in §8.5. |
| R-7 | Minor | §12.4 A002 line now covers names used in the body, and lists the known sites. Added lines for S003 `zip(strict=True)`, S002 `raise … from`, and A007 no-literals. Added `JIRA_ADF_VERSION`. |
| R-8 | Minor | D-17 gains criterion (f), the cut. Table (b) rows are now "Qualifies; below the cut". |
| R-9 | Minor | The Notion body neutralizes `<mention-` (`NOTION_MENTION_TOKEN` and `_REPLACEMENT`). INV-12, AC-9 (b), EC-6, T-2, and A-6 updated. |
| R-10 | Minor | EC-28 reworded to cover every later checkpoint and `export_state()`. A-14 withdrawn. |
| R-11 | Minor | Docs only: a README footgun, catalog row a-6, NG-12, and EC-46. Q-9 is scope-adding and not built. |

### Symbols moved or renamed

Public names and the 17 root exports are unchanged. `vidbyte.agents.output` still exports 18 names.

- **`OutputConnector`:** was an ABC in `lib/outputs/base.py`. It is now a `@runtime_checkable` Protocol in `agents/output/connector.py`.
- **`OutputConnector.deliver`:** removed. Its steps now run in `OutputDispatcher.deliver` and `OutputDispatcher._deliver_one`.
- **`_send`:** renamed to the public `send` on every connector, declared abstract on the new `BaseOutput` in `lib/outputs/base.py`.
- **`OutputText.is_deliverable`, `.content`, `.structured_field`:** moved to `OutputShaping` in `agents/output/connector.py`.
- **`OutputText.structured_json`:** moved to `WebhookOutput._structured_json`.
- **`lib/outputs/content.py`:** renamed to `lib/outputs/text.py`.
- **New names:**
  - `OutputArguments.optional_callable`;
  - the constants `OUTPUT_DELIVERABLE_STOP_REASONS`, `JIRA_ADF_VERSION`, `NOTION_MENTION_TOKEN`, and `NOTION_MENTION_REPLACEMENT`.
- **§12.3 rows:** a new row 21 (`connector.py`) means the old rows 20–35 are now 20–36.

### Budget after the re-cut

- **Files:** 23 new (21 `.py` and 2 READMEs) and 13 modified. §8.4 equals §12.3 rows 1–23.
- **Classes:** 26, in 19 modules (18 new, plus `lib/errors/base.py`).
- **The one added layer piece is `BaseOutput`.** It is there so eleven connectors do not each re-implement the masked repr and render storage, which would put INV-4 at risk. It holds no agent logic.

### Facts verified for r2 (beyond the review's list)

- `AgentStopReason` has 17 members (`vidbyte/lib/dataclasses/agents.py:51-70`). INV-9 names the rejected-answer stops too: `contract_unsatisfied`, `finish_review_rejected`, `tool_settings_denied`, and `error`.
- The precedent `NORMAL_STOP_REASONS` is at `vidbyte/evals/behavior/stop.py:32`.
- Reflexion forwards the inner run's stop reason, defaulting to `final_response` (`vidbyte/context/algorithms/reflexion.py:125-131`).
- There is no `stop_reason` under `vidbyte/agents/jev/` or `vidbyte/lib/jev/`. _(Corrected in r3: the literal string is absent, but normal Jev replies still carry it, because `JevRuntime` subclasses `AgentRuntime` and `JevResponse.delegated` copies the specialist's metadata. Only `JevResponse.stopped` has none. See R-15.)_
- A002 splits identifiers on `_` and `.` and matches whole words (`lint/rules/a002_intent_comments.py:69-75`). So `OutputSmtp._client` needs no `# @intent`, and r1's listing of it was dropped. `_link` (which reads `request`) and `_deliver_one` (which calls `send`) do need one.
- A006 excludes `__init__.py` files from its graph (`a006_directed_dependency_graph.py:65-67`).
- The Protocol precedent is `vidbyte/sessions/store.py:29-30`.
- A `runtime_checkable` `isinstance` check passes for a connector *class* as well as an instance. That is why `OutputDispatcher.connectors` rejects `isinstance(item, type)` first (INV-21, AC-20).

### New and least-sure assumptions after r2

- **A-15 (new).** That no runtime marks a finished answer with a stop reason other than `final_response` or `is_done`. If one does, its replies are SKIPPED: visible in the receipts, with nothing posted.
- **A-6 (extended).** That every Notion mention tag starts with `<mention-`.
- The earlier least-sure list (A-1, A-2, A-3, A-5, A-7, A-11, A-13) stands.

### Self-check (r2)

- **Section headings** match r1 and the template. The diff shows only Python comment lines inside §8.5's code block.
- **IDs:** no duplicates, no undefined references, and no gaps. The counts:

  | ID | Count | ID | Count |
  |---|---|---|---|
  | G | 4 | D | 22 |
  | NG | 12 | W | 12 |
  | INV | 28 | T | 5 |
  | AC | 26 | A | 15 (A-14 withdrawn) |
  | EC | 46 | Q | 9 (0 blocking) |
  | FR | 20 | | |
  | NFR | 8 | | |

- **Traceability:** every FR is traced, and every AC appears in a W row.
- **Names:** they agree across §4, §8.5, §9.2, §12.3, and §16. r1 symbols appear only in the §16 rename table.
- **Status:** `status: draft`, `revision: 2`, not approved (that comes after round 2).
- **No test cases** appear anywhere in the spec.

## Revision r3 (S1 review round 2, final; approved)

The review (`reports/S1-spec-review-r2.md`, commit `81f9ae35`) returned SOUND WITH FIXES: 0 Blocker, 2 Major, 5 Minor. It found the r2 layout correct and cycle-free, and I left it unchanged. The 23 files, 26 classes, 17 root exports, Protocol plus `BaseOutput`, and every R-1 to R-11 fix are all as they were.

The spec frontmatter now reads `status: approved` and `revision: 3`. The two review rounds are the approval.

### Dispositions

All seven findings are **Accepted**. None is disputed, so no new open question replaces a fix.

| ID | Severity | Change |
|---|---|---|
| R-12 | Major | Added `OutputArguments.matching(value, pattern, *, parameter)` and `OutputArguments.address(value, *, parameter)`, plus the constants `GITHUB_REPO_PATTERN` and `JIRA_SITE_PATTERN`. Rows 13, 14, and 16 call them with `to`, `sender`, `repo`, `site`, and `email`, so every AC-20 error names the constructor parameter. AC-20 adds `email="jira-bot"`. |
| R-13 | Major | Removed `BaseAgent._deliver_outputs`. Delivery is now an inline `try` / `except BaseException` block in `_generate_reply`, mirroring `base.py:920-927`. |
| R-14 | Minor | INV-12 and FR-13 now cover channel-wide and mass mentions only. GitHub `@user` / `@org/team` and Telegram `@username` are an accepted limitation (T-2, EC-6, row 19). Q-10 is scope-adding and not built. |
| R-15 | Minor | INV-9 and EC-38 now cite `JevResponse.stopped`. EC-44 adds (b) a delegated reply copies the specialist's `deliveries` and (c) a proposer whose delivery fails is a failed proposer. AC-21's Given now excludes sub-agents with outputs. Rows 19, 23, and 34 are updated. |
| R-16 | Minor | D-1 now weighs `vidbyte/providers/tracing/` as the runner-up's precedent. It decides on `lib/http/` adjacency and the model-vendor namespace, and the false README claim is gone. The choice is unchanged. |
| R-17 | Minor | §12.4: S051 must not be REGRESSED (baseline 259), and the I001 output filtered to touched paths must be empty. `base.py` imports are added without re-sorting the block. §11 lists S051 259. |
| R-18 | Minor | I took option (a), because the conversation set the latency bound. `_deliver_one` wraps `send` in `asyncio.wait_for(..., OUTPUT_DELIVERY_DEADLINE_SECONDS)` (35 s). The wait's `TimeoutError` becomes FAILED `network`. The precedent is `aggregation.py:114`. This adds EC-47, A-16, and AC-6 (e). |

### Symbols moved or renamed in r3

- **`BaseAgent._deliver_outputs`:** removed, replaced by the inline block in `_generate_reply`.
- **`JIRA_SITE_SUFFIX`:** renamed to `JIRA_SITE_PATTERN`.
- **New:**
  - `OutputArguments.matching` and `OutputArguments.address`;
  - the constants `GITHUB_REPO_PATTERN` and `OUTPUT_DELIVERY_DEADLINE_SECONDS`.
- **Unchanged:** public names, root exports, the file budget, and the class count.

### Facts checked for r3

- `vidbyte/providers/README.md:46` lists `tracing/`. `TracerBase` is at `vidbyte/lib/tracing/base.py:16`. LangSmith reads `LANGSMITH_API_KEY` from the environment (`langsmith.py:38`).
- In `vidbyte/agents/jev/response.py`:
  - `JevResponse.delegated` (128-132) passes `metadata=reply.metadata`;
  - `stopped` (134-137) builds a result with no `stop_reason`.
- In `aggregation.py`:
  - proposers run under `gather(return_exceptions=True)` at line 89;
  - each proposer is bounded by `asyncio.wait_for` at line 114;
  - `_collect_candidates` raises `AggregateExecutionError` below `min_successful` (116-132).
- `lint/baseline.json` has S051 at 259.

### New assumption

- **A-16.** That a healthy destination finishes within 35 s, including the 429 path. If it does not, the receipt reads FAILED `network` while the post may still land. The fix is to raise the constant.

### Self-check (r3)

- **Section headings** are identical to r2 and the template.
- **IDs:** no duplicates, no undefined references, and no gaps. The counts:

  | ID | Count | ID | Count |
  |---|---|---|---|
  | G | 4 | D | 22 |
  | NG | 12 | W | 12 |
  | INV | 28 | T | 5 |
  | AC | 26 | A | 16 (A-14 withdrawn) |
  | EC | 47 | Q | 10 (0 blocking) |
  | FR | 20 | | |
  | NFR | 8 | | |

- **Traceability:** every AC still appears in a W row.
- **Budget:** §8.4 still equals §12.3 rows 1–23. There are 14 config keys; the deadline is an operational constant, not a user knob.
- **Stale symbols:** `_deliver_outputs` and `JIRA_SITE_SUFFIX` appear only in §16.
- **§14** now forbids building Q-8, Q-9, or Q-10.

## Revision r4 (S2 test-author feedback)

The coordinator asked me to align the spec with seven defects found by the S2 test author (`reports/S2-test-author.md`, "Spec defects found"; `test-plan.md`, "Notes for the implementer"). This is not a review round. I changed nothing under `tests/`, nothing in `test-plan.md`, and nothing in the §6.2 Proof column (checked by diffing that column before and after). No contract name, feature, field, or control changed, and `status: approved` stays.

All seven defects are Accepted and logged in §16 as S2-1 to S2-7:

- **S2-1:** AC-18 and INV-7 now say that the queued-prompt list the run claimed at its start is cleared (`base.py:392-395`, `792-795`), on every exception the inline block catches.
- **S2-2:** AC-19 is now event-gated: concurrent sends, and receipts in configured order. The wall-clock bound is gone.
- **S2-3:** §13 now explains where `follow_redirects`, the retry arguments, `idempotency_key`, and the size ceiling are applied. It also says AC-25 and EC-34 use `httpx.MockTransport` through `transport_module.httpx.AsyncClient`.
- **S2-4:** AC-4's scripted model returns the same invalid answer on every call, because the runtime re-prompts.
- **S2-5:** AC-12 uses a named agent (`AgentMetadata(name=...)`).
- **S2-6:** AC-23 is split into (a) `session.run` and (b) a direct `agent.run` on a session-bound agent.
- **S2-7:** row 22 drops the dedicated single-connector check, and AC-20 says that the not-iterable check covers it.

I confirmed the eight structural items the test author asserts:

| Item | What is asserted | Where it is stated |
|---|---|---|
| (a) | the missing-credential message | row 5 |
| (b) | the failure summary message | row 22 |
| (c) | the masked repr | §8.5 and row 5 |
| (d) | `follow_redirects=False` and `max_response_bytes` | row 7 and §9.2 |
| (e) | `import smtplib` as a module, and the SMTP client used as a context manager | row 7 already said `with`; I added the module import to row 7 |
| (f) | the deadline read as a module global | added to row 22 |
| (g) | Slack escapes after truncation; Jira paragraphs come from the non-blank lines of the truncated body | §9.2 |
| (h) | layering | §12.2, NFR-7, and §12.4 now allow `vidbyte/agents/output/` to import its own modules, and the forbidden HTTP client list adds `aiohttp` |

Items (a) to (d) and (g) were already stated where shown. Item (h) needed a wording fix. The old text said "`vidbyte.lib.*` and the standard library only", which would have forbidden `dispatcher.py` from importing `connector.py`. The design itself is unchanged.

None of the eight items contradicts the spec, so there are no CONFLICT items.

Self-check (r4):
- **Section headings** are unchanged.
- **IDs:** no duplicates, no undefined references, and no gaps. The counts are unchanged from r3.
- **Frontmatter:** `revision: 4`, `updated: 2026-10-11`, `status: approved`.

## Revision r5 (S3 blocker, orchestrator decision)

S3 stopped at §12.3 row 27 (`reports/S3-implementer.md`, "Blocker"). Lint rule S008 (Ruff C901 ≤ 10, PLR0912 ≤ 12, PLR0915 ≤ 50; ratcheted at 19) leaves `BaseAgent._generate_reply` no headroom: the base commit is already at complexity 10 and 50 statements. The inline block from R-13 pushes it to 12 and 57.

The orchestrator decided to reverse R-13. r5 applies that decision and the lint-forced renames. Status stays `tests-written`. Nothing under `tests/` or `vidbyte/`, nothing in `test-plan.md`, and nothing in the §6.2 Proof column changed. I diffed the Proof column to confirm.

Changes:
- **S3-1, the reversal of R-13.** Delivery moves into a private `BaseAgent._deliver_outputs(reply, metadata)`, which holds the `try` / `except BaseException` block.
  - The block clears the claimed queue, notifies the session, and re-raises.
  - The three existing last-trace lines move, with unchanged behavior, into `_record_last_trace(metadata)`.
  - These edits are in §2, §5, INV-7 (only the location of the block), AC-23's Then cell, D-3, D-4, §8.5, §11 (S008 19 added to the baselines), W-9, row 27, and §12.4. §12.4 also gets a new S008 line.
  - The base.py budget goes from 25 to 35 added lines (row 27, NFR-3, NG-11, and §11 conflict 1). It now counts the moved trace lines.
  - The R-13 row in §16 is marked "reversed in r5 (S3-1)". A new S3-1 row records the evidence.
- **Placement of the guard (my call, measured).** `_generate_reply` keeps `if self.outputs:` before `await self._deliver_outputs(...)`. Without it, `_generate_reply` would add an await for agents without outputs, and INV-22 says it "adds no await" and must hold as written.
  - I measured with Ruff on a copy of base.py in the scratchpad; the repo was not touched.
  - Guarded: complexity 10, branches 9, statements 50. These equal the base commit, so there is no S008 finding at the real limits.
  - Unguarded call: 9 / 8 / 49. That matches the orchestrator's measurement, but it breaks INV-22's wording.
- **S3-2, lint-forced renames.**
  - `GOOGLE_CHAT_MENTION_TOKEN` became `GOOGLE_CHAT_MENTION_PREFIX`, and `NOTION_MENTION_TOKEN` became `NOTION_MENTION_PREFIX`. They are renamed in row 2, the §9.2 helper lines, and A-6.
  - `OUTPUT_ERROR_TOKEN_PATTERN` is now built from the new `OUTPUT_ERROR_TOKEN_MAX_CHARS = 64`, which row 2 names. The pattern's value is unchanged.
  - Row 2 now cites S054 / S105.
- **The other S3 deviations.**
  - The canonical lowercase UUID from `identifier()`, the shaping fallback when the first line is blank, and the lowercase header-key check are all consistent with §8.5, INV-13, and §9.1, so I left them in S3's list.
  - Deviation 2, typing `optional_callable`'s `value` as `Callable[...] | None`, differs from the §8.5 signature `value: object`. I report it as a CONFLICT for the orchestrator and did not edit it.

Self-check (r5):
- **Section headings** are unchanged.
- **IDs:** no duplicates, no undefined references, and no gaps. The counts are unchanged from r4.
- **Stale wording:** "inline" and `*_MENTION_TOKEN` now appear only in the §16 and §17 history and the r5 rename table.
- **Frontmatter:** `revision: 5`, `updated: 2026-10-11`, `status: tests-written`.

## Revision r6 (S4 verified review, orchestrator-directed alignment)

The orchestrator directed this alignment with `review.md` (S4 verified review, verdict MERGEABLE AFTER FIXES) before repair starts. It is not a review round. Status stays `reviewed`. Nothing under `tests/` or `vidbyte/` changed, and neither did `test-plan.md`, `review.md`, or the §6.2 Proof column; I diffed the Proof column to confirm. Each item is recorded in §16 as S4-R<n>.

Changes, one per item:
- **S4-R1 (Blocker), the httpx log leak.** Row 7 now specifies the log guard. A module-level `_OUTPUT_POST_ACTIVE: ContextVar[bool]` in `delivery.py` (precedent `vidbyte/lib/usage_ledger.py:39`) is set around `HttpTransport().request` in `OutputHttp.post` and reset in `finally`. `OutputHttp._keep_log_record` is added once at import to `logging.getLogger("httpx")` and drops `HTTP Request:` records while the flag is set. The user's own httpx requests are still logged. There is no `import httpx`, no `transport.py` edit, and no level change. INV-4 (new bullet for log records), EC-41, T-1, §8.2, §12.4 (a new Credentials line and the httpx-import line), and §13 (a Logs seam) are updated.
- **S4-R2 (Major).** A non-`OutputDestination` `destination` is rejected in `connectors()`, with a message containing `outputs` (INV-21, AC-20 Given, EC-14, row 22). A `send` that returns a non-`DeliveryReceipt` is FAILED `unexpected:ConfigurationError`, mirroring the render check (AC-11 (f), EC-16, §8.5 `_deliver_one` step 5, row 22).
- **S4-R3 (Major).** SMTP runs on a module-level `_SMTP_EXECUTOR = ThreadPoolExecutor()` in `email.py`, through `loop.run_in_executor`. Updated: INV-19, FR-17, NFR-1 (`concurrent.futures`), NFR-2, §5 node L, §8.2, the §8.5 sketch comment and narration, rows 7 and 13, §12.4, §13, and EC-47. INV-19 and EC-47 state that a timed-out email may still be delivered later, which is already accepted under EC-19 and EC-47.
- **S4-R4 (Major).** Row 2 adds `OUTPUT_EMAIL_ADDRESS_PATTERN = r"[^\s,]*@[^\s,]*"`, and rows 3 and 5 and the §8.5 sketch say both `_is_address` and `OutputArguments.address` `re.fullmatch` it. The optional `OUTPUT_HTTPS_PREFIX` is added, and the https checks stay different (D-19 vs §9.1 and D-21).
- **S4-R5.** INV-2 is reworded so that a `render` that raises or returns a non-`OutputContent` makes zero sends, and its receipt is FAILED.
- **S4-R9.** `JIRA_ISSUE_PATH` and `JIRA_BROWSE_PATH` are named in row 2 and used in row 16 and the §9.2 Jira row.
- **S4-R11 (wording only).** A one-sentence resend caution is added in §9.2, AC-24 (Then), and EC-42.
- **S4-R12.** New EC-48 covers a non-221 QUIT after acceptance: the receipt is unchanged. Row 7 decides the receipt once `send_message` returns and closes under `contextlib.suppress(smtplib.SMTPException, OSError)`.
- **S4-R13 [scope-adding].** Not specified (rule 9). It is optional Q-11, default No, not built. New EC-49 states the limitation.
- **S4-R15.** `https_url` reads `urlsplit(value).port` in a `try` and re-raises `ValueError` as `ConfigurationError` `from None` (row 5, INV-21, AC-20 Given, EC-13, and the §12.4 S002 sites).
- **S4-R6, R7, R8, R10, R14** need no spec change and are left to the repair agent and the test author. They are recorded in one §16 row.

New IDs: EC-48, EC-49, and Q-11, plus case (f) in AC-11. There are no new AC or INV IDs.

Facts I checked for r6:
- `vidbyte/` has no `ThreadPoolExecutor`, `run_in_executor`, `addFilter`, or `logging.Filter` (Grep). §8.2 says so and cites the standard-library APIs.
- I read Python 3.11.0's `asyncio.runners.Runner.close`. It calls `loop.shutdown_default_executor()` with no timeout. `concurrent.futures.thread` registers `threading._register_atexit(_python_exit)`, so interpreter exit still joins a dedicated executor's workers. INV-19 states this.
- The `vidbyte/lib/usage_ledger.py:39` precedent is `_ACTIVE_LEDGER: ContextVar[UsageLedger | None]`.
- A002 policy tokens (`lint/rules/a002_intent_comments.py:25-48`) do not force `# @intent` on `_keep_log_record`. Row 7 asks for one anyway, because it is the redaction policy.
- I probed httpx: a non-ASCII header value raises `UnicodeEncodeError`. With `MockTransport`, a CR/LF or control character in a header is sent without error, but I did not check the real h11 path. So EC-49 covers only the verified non-ASCII header case, and Q-11 asks about both kinds of character, as directed.

Self-check (r6):
- **Section headings:** unchanged.
- **IDs:** no duplicates, no undefined references, and no gaps. EC now runs to 49 and Q to 11. The never-referenced list only shrank: EC-13, EC-16, and EC-41 are now cited.
- **Proof column:** identical to r5.
- **`asyncio.to_thread`:** it now appears only as "never `to_thread`", the `fetch.py` precedent, or history (§16, the r6 symbol table).
- **Frontmatter:** `revision: 6`, `updated: 2026-10-11`, `status: reviewed`.

## Revision r7 (S6 follow-ups, orchestrator-directed alignment)

This revision brings the spec in line with repair iteration 2 (`reports/S5-repair-2.md`, review.md rows S6-1 and S6-2). Status stays `pr-open`, and the `pr:` line is unchanged. Nothing under `tests/` or `vidbyte/` changed, and neither did `test-plan.md`, `review.md`, or the §6.2 Proof column (I diffed it).

Changes:
- **§8.5:** adds `OutputArguments.non_empty(values: tuple[str, ...], *, parameter: str) -> tuple[str, ...]`. I read the signature from `vidbyte/lib/outputs/base.py:74` at 7fb2ac75.
- **§12.3 row 5:** lists `non_empty` with the other static methods and gives its rule and message, `"{parameter} must list at least one value."`. `texts` still accepts an empty sequence, because GitHub's `labels=()` default goes through it.
- **§12.3 row 13:** the `to` path is now `texts`, then `non_empty`, then `address`, so an empty list names `to` (the caller is `email.py:50`).
- **§17 deviations:** the TelegramOutput bullet no longer claims there are only eight methods. `non_empty` exists because its caller needs the caller's parameter name. Telegram's int-or-string check stays a one-caller inline exception.
- **S6-2:** row 25 paraphrased the old `repair_approaches` hint, `deliver(failed, …)`. It now gives the §9.2 / AC-24 zip recipe, with `failed_connectors`, a "not `err.failed`" note, and the network caution. §9.2, AC-24, and EC-42 already gave the working recipe, so they are unchanged.
- **§16:** adds rows S6-1 and S6-2 (Minor, fixed in code, spec aligned in r7). §17 gets an r7 row.

Self-check (r7):
- Headings are unchanged.
- The IDs have no duplicates, gaps, or undefined references, and the counts are unchanged.
- The Proof column is identical.
- No stale "ninth method" claim or old hint paraphrase remains.
- Frontmatter: `revision: 7`, `updated: 2026-10-12`, `status: pr-open`.
