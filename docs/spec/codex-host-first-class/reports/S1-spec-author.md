# S1 spec-author report: codex-host-first-class (slice 2)

| Field | Value |
|---|---|
| Stage | S1 spec author |
| Date | 2026-10-17 |
| Branch | `feat/codex-host-first-class` |
| Spec | `docs/spec/codex-host-first-class/spec.md`, r1 (1,832 lines), committed as `fde5a8b0` |
| Writes | spec.md and this report (both committed). Throwaway check scripts are in the session scratchpad only. No code, no tests, no installs, no `codex` binary, no push. |

## What I read
- **Rules and the request:**
  - the spec template and AGENTS.md;
  - request.md;
  - `pipeline.md` (the decisions of 22:40 and 23:05, and the niche facts);
  - the S0 scout's `context/code-map.md` (in full) and `reports/S0-scout.md`.
- **Host code, at the places the design touches:**
  - `host.py`: `_open`, spawn, continue, the private start helpers, `delete`, `get_codex_goal`;
  - `wire.py`: `final_answer`, `turn_start`, `pricing`;
  - `thread_helpers.py`: `compact`, `delete`, `goal`;
  - `preflight.py` signatures;
  - `codex_host_inputs.py` (lines 1-100 and 200-405);
  - the `codex_host.py` constant tables (lines 40-180) and the existing message texts;
  - `enums/__init__.py` and `enums/codex.py.__all__`;
  - `enums/process.py`;
  - `lib/process/{argv,runner,__init__}.py`;
  - `dataclasses/process.py` fields;
  - `native_threads.py` header and constants;
  - `tools/builtins/codex/{descriptions,_base,thread_helpers}.py` at the relevant lines.
- **Pins:**
  - the `test_harness_threads_surface.py` export and branch-scope tests;
  - `test_harness_threads_static_policy.py`, which skips codex;
  - the bodies of the superseded tests: hardening contract rows, packaging import probe, input boundary rows, the tool-count tests.
- **SDK 0.163.0, read with `V -I`:**
  - the `notification_registry` method names;
  - the model fields of every streamed notification and raw response;
  - which slice-2 responses have `v2_all` models: 9 have none, and 4 raw ones do;
  - the typed `CodexClient` goal and archive methods;
  - `_start_goal_operation` in full, because D-17 depends on it.
- **External evidence paths** (Codex TUI `side.rs`, `app_server_session.rs`, `session_queue_commands.rs`; the schemas) were checked to exist where §11 says.

## Approaches weighed
1. **Surface placement.**
   - Chosen: four SDK-free mixins over `CodexHostCore`, plus a `CodexTurnStarts` collaborator for the moved start helpers.
   - Rejected:
     - Growing `host.py` (937 lines today) would pass 1,300 lines and break the `vars(CodexHost)` helper-order pin.
     - Collaborators with forwarders would add about 250 lines back and break the same pin.
2. **The experimental wire.**
   - Chosen: the existing raw path with a passthrough response class, and `parse` run on the worker inside the call.
   - Rejected:
     - Hand-written pydantic models for the 9 unmodeled responses.
     - Fake stand-in model names: pydantic ignores extras, so non-empty answers would silently read as empty.
     - Parsing after the call: a malformed answer would then log as a successful call and escape as a raw `ConfigurationError`.
3. **Streaming.**
   - Chosen: a bounded, host-side event log fed by the existing watcher, with drop-oldest plus `GAP`.
   - Rejected: the SDK's private multi-consumer subscription, which is unbounded and needs a second reader thread per stream.
4. **Goal resume.**
   - Chosen: reserve, activate, a status-only set, then wait, under `connection.start`.
   - Rejected:
     - `start_goal_operation`, which always clears the goal and so loses budget and usage.
     - A bare typed set, which sends no `origin` and is untracked.
5. **The worktree.**
   - Chosen: a canonical `GitWorktrees.add` over `CliArgv` and `CliRunner`, under `~/.vidbyte/codex-worktrees/`.
   - Rejected: `codex exec --worktree`, which spends, and inline `subprocess`.

## Where I disagree with the scout or the request
- **Queue add/list/start is not built** (NG-1, blocking Q-1, default "not built"). The request and the 23:05 decision list it as P1. The evidence:
  - Codex's own CLI refuses to queue through a private embedded server;
  - CodexHost always runs one;
  - the TUI never calls `queue/start` or `queue/list`, so Codex drains the queue itself, which is an inference;
  - such turns would start untracked, which breaks slice-1 INV-11;
  - inside one private server, the queue duplicates `continue_codex_thread` after `wait_codex_turn`.

  This is the one place I overrode the request. The request allows it ("impossible or redundant become NG … with evidence").
- **`personality` and `multiAgentMode` on settings update.** The scout notes the gap report omits them. I keep them out on purpose: the schema marks both deprecated (NG-7).
- **Paths outside §11 and §12.** The template itself asks for `path:symbol` in §8.2, for paths in the must-not-regress INVs and in §13. I kept paths there. Everywhere else in §1–§10, repo paths became module or symbol names. External evidence is cited by short file name, and §11 maps each name to its full path.
- **`GitFlag` placement.** The `native_threads` constants header says vendor flags live in `enums/native_threads.py`. I put `GitFlag` in `enums/process.py`, beside `CliOptionStyle`, because it is a process-helper flag (§11 Conflicts 2).
- **`vidbyte.lib.process` exports.** Its header says to export new helpers, but the harness-threads pin fixes `__all__` at three names. `GitWorktrees` is therefore imported from its own module, and the header gains a note.

## Assumptions I am least sure of
1. **A-1:** a status-only `thread/goal/set {status: active}` starts a goal turn. If it is false, `resume_codex_goal` always times out in its start window. It is the riskiest P1 behaviour, and the fake cannot prove it.
2. **A-13:** `thread/resume` on a paused, blocked or usage-limited goal does not auto-start it. If it does, resume could start an untracked turn before the tracked set.
3. **A-14:** the `thread/inject_items` item shape used for the side-chat boundary (a Responses-API user message).
4. **A-11:** a collaboration mode persists to later turns. §4 sidesteps this by passing `DEFAULT` explicitly.
5. **A-2:** an omitted `developer_instructions` behaves as `null`. It is a one-line flip if wrong.
6. **Ceilings.** `wire.py` ≤ 840 is my estimate, about 820 after the edits. A tighter real count could force a BLOCKED report.

## Addendum r2 (S1 review round 1, 2026-10-17)

**Input.** `reports/S1-spec-review.md` (verdict SOUND WITH FIXES: 1 Blocker, 6 Major, 6 Minor). All 13 findings were accepted; §16 has one row each.

**Re-checked before applying, independently of the reviewer:**
- `ThreadSearchParams.json:85-86`, which defaults to interactive sources;
- `task_mentions.rs:80` and `tui/src/lib.rs:779-784`, which define interactive as CLI and VS Code;
- `goal_menu.rs:44-58,110-115,133-143`, the resume set and the edit that sets budget-limited back to active;
- the `ThreadForkResponse` reviewer fields (`V -I`);
- the fake's `source` default and its fork copying the reviewer (`codex_host_fakes.py:161,857`);
- `side.rs:426-446` and `methods.txt:14`;
- that no test calls `over_cap`.

**Where I chose differently from the reviewer's smallest fix:**
- **R-6.** The reviewer suggested releasing the handler after a later check in the mixin. I put the check inside `CodexThreadHelpers.fork(..., starts_turn=True)`, right after `thread/fork` and before the handler is shared, so nothing needs releasing. `fork_codex_thread` keeps `starts_turn=False` and is unchanged.
- **R-2.** I took the reviewer's first option: an allow-list `CODEX_HOST_LOAD_SAFE_GOAL_STATUSES` that refuses only `ACTIVE`. That is consistent with A-13, which `resume_codex_goal` already relied on. Compact's complete-only set is unchanged.
- **R-3.** Beyond adding `BUDGET_LIMITED`, resume refuses a spent budget locally (`tokens_used` ≥ `token_budget`), with its own message, cause and next step. Otherwise that case waits out the 30-second start window and ends in a vague `codex.api_error`.
- **R-1.** I chose `CODEX_HOST_HELPER_SOURCE_KINDS`, not every kind. Search then matches `list_codex_threads`, and sub-agent internals stay out (D-35).
- **R-7.** The cursor exists from the generator's first step to its `finally`, held weakly, and the start is fixed at the call. So AC-14 now has the subscriber take one event first, and AC-43 covers a subscription that is never iterated. The usage delta is computed once in `on_event`, so `over_cap` takes it as an argument.
- **R-4 and R-5.** I took the orchestrator's direction: no clean tool, and narrowed claims. The scope-adding halves are the optional Q-10 and Q-11, default not built.

**Found by me while checking R-5 and R-6.** A side-chat fork of a parent with an active goal may carry the goal. Codex's `/side` forks with continuation "start if idle" (`app_server_session.rs:1001-1019`), and the schema says a fork carries the goal unless `deferGoalContinuation` is set. I recorded it as EC-61 and A-20, the same acceptance slice-1 EC-28 gave `fork_codex_thread`. I did not build a refusal, because that needs a user decision.

**Correction to this report's r1 text.** Under "Approaches weighed", item 1, forwarders do not "break the `vars(CodexHost)` helper-order pin": the pin takes only a slice after `start_codex_review` (R-12). The size argument stands alone.

**Sections changed, for a round-2 reviewer:**
- §8.1: D-1, D-10, D-14, D-21, D-22, D-23, D-34, and the new D-35…D-38;
- §8.3 and §8.4: 69 classes, 44 config keys, 42 endpoints;
- §8.5: `fork(starts_turn)`, `CodexPreflight.reject_routed_reviewer`, `routes_to_user`, `CodexLiveTurn.over_cap(delta)`, the `subscribe` semantics, the `GitWorktreeSpec` comments;
- §9.1: the `GitWorktreeSpec` checks and both lifecycles;
- §9.2: the normative sequences, the search params, 16 tools and the messages;
- §9.3: the resume set and `CODEX_HOST_LOAD_SAFE_GOAL_STATUSES`;
- §9.4;
- §10: T-1 and T-2;
- §12.3 rows 16, 18–20, 23, 24, 28, 29, 32, 34 and 37–39. The shape of §12 is unchanged: still 39 rows and 13 new files.

**Least-sure assumptions now:**
- A-1 and A-19: a status-only active set starts a goal turn;
- A-13: loading a non-active goal does not restart it, which the new load guard now depends on as well;
- A-20: no goal continuation on a side fork;
- A-14: the inject item shape.

## Addendum r3 (S1 review round 2, final, 2026-10-17)

**Input.** `reports/S1-spec-review-r2.md` (verdict SOUND WITH FIXES: 3 Major, 2 Minor; 11 round-1 fixes held, R-5 and R-7 held partly). All five findings were accepted, and §16 has one row each (r2-1…r2-5), plus r2-6 for the review's verified-claims notes. The spec is now `status: approved`, `revision: 3`. This was the last round, and no finding was disputed, so no new Q-n was needed.

**Re-checked before applying, independently of the reviewer:**
- `wire.py` `_approvals`, `thread_fork` and `turn_start`: `turn_start` passes an empty explicit map, so only the turn's `approval_mode` reaches `turn/start`;
- `CODEX_APPROVAL_MODE_WIRE` (`deny_all` → `("never", "")`), and openai-codex's `ApprovalMode.deny_all`, which maps to `never` with no reviewer (`_approval_mode.py:13-16,34-35`);
- `codex_host.py:220-231`: explicit fields together with a mode raise `ConfigurationError`;
- `connection.py:293-294`: one approval router serves every thread;
- the 0.163.0 `ApprovalsReviewer` text, which names sandbox escapes;
- `_base.py` `_json` and `_model_json`, and `live.py`'s two `without_items=True` callers;
- `test_codex_host_packaging.py:249-255`, the pinned bullet;
- `connection.py:521-532` and `host.py:923-934`, close versus death;
- `thread_goal_actions.rs:78-84` and `:353-366`;
- that `CodexGoalTurn` calls `super().__init__(handle, request, pricing, loop)`, and that only the registry builds live turns (`turns.py:363,369`).

**Where I chose differently from the reviewer's smallest fix:**
- **R-14.** The reviewer proposed an explicit `approval_policy=NEVER` with both modes reset. `turn_start` never sends the explicit fields, so `never` would reach `thread/fork` only, and AC-36's own assertion on `turn/start` would fail. I set `thread.approval_mode` and `turn.approval_mode` to `DENY_ALL` instead, with both explicit fields at `PROVIDER_DEFAULT`. That sends `approvalPolicy: "never"` and no reviewer on both requests, passes the record's no-mixing check, and only narrows. A-21 records the one unverified link: that `never` denies escalations without asking anyone.
- **R-15, the host-wide bound.** The reviewer's smallest fix covered only the cursor. The orchestrator also asked for an enforced, named host-wide bound, so I added D-39:
  - `CodexTurnRegistry` keeps two integer totals;
  - `charge_stream(chars, events)` is passed to each log by `_add`, through `CodexTurnEventLog.attach`;
  - a log past `CODEX_HOST_STREAM_HOST_EVENT_LIMIT` (65,536) or `CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS` (32,000,000) drops its own oldest events, then the new one;
  - `ENDED` is never counted, so ended turns cannot fill the pool.
  
  This needs no 70th class, and `CodexGoalTurn` stays unchanged, because `_add` serves every turn kind. Config keys go from 44 to 46.

**Rejected while designing D-39:**
- Passing the bound to `CodexLiveTurn.__init__`: `CodexGoalTurn`'s `super()` call would have to change, against INV-51.
- Typing the log against the registry: `turn_stream` would then import `turns`, a cycle.
- A cap on live turns: it refuses valid paid work.
- Eviction from the largest log: a scan of every turn per event.

**Sections changed, for the record:**
- **Frontmatter:** status and revision.
- **§6:** INV-20 (per-turn and per-host bounds, what is dropped, `ENDED` uncounted), INV-21 (the integer count, finalization, `aclosing`), INV-22 (positions), INV-27 step 4 (the tool never reaches the reviewer refusal), INV-43 (the side chat's posture); AC-26, AC-36, AC-37, the new AC-44; EC-17, EC-18, EC-59, EC-60, the new EC-62.
- **§7:** NFR-3.
- **§8.1:** D-14, D-22, D-37, the new D-39.
- **§8.4:** 46 config keys.
- **§8.5:** `attach`, `close`, `subscribe`, and `CodexTurnRegistry.charge_stream`.
- **§9.1:** the log lifecycle and the volume bullet.
- **§9.2:** tool 34, the tool rules (four `_json` exceptions, `TURN_SETTINGS_STATUS_TEXT`, multi-wait without items, the side-chat description) and the not-resumable next step.
- **§9.3:** two host limits.
- **§10:** T-2.
- **§11:** the source index (`_approval_mode.py`, `thread_goal_actions.rs`).
- **§12:** W-5, W-10, and §12.3 rows 18, 19, 31, 32, 33, 35 and 38. There are still 39 rows and 13 new files.
- **§13:** four patchable stream limits, the fake's `approvalPolicy` override, and the pinned builtins bullet.
- **§15:** A-13 (citation; an "If wrong" path that no longer loops), A-20 (citation), and the new A-21.
- **§16 and §17.**

**Final counts:**
- **IDs:** G 6, NG 19, INV 55, AC 44, EC 62, FR 36, NFR 12, D 39, T 8, W 19, A 21, Q 11. None duplicated, none missing, none undefined (`ids.py`); every table well formed (`tables.py`).
- **Budget:** 13 new files, 69 classes, 0 dependencies, 46 config keys, 0 tables, 42 endpoints.

**Least-sure assumptions now:** A-1 and A-19 (a status-only active set starts a goal turn), A-13, A-20 and A-21 (`never` asks no one). The binary is never run here, so all four rest on source and schema reading.

## r4 addendum (S2 findings, 2026-10-18)

**Input.** `test-plan.md` § "Spec defects and ambiguities" (8 items) and the coordinator's r4 request. This is an amendment, not a review round, so the status stays `approved`. §16 has rows S2-1…S2-8, and §17 has r4.

**Defects:**
- **S2-1, §13.** I added `test_codex_host_lifecycle.py::CodexHostSnippetTests::test_the_section_4_snippet_prints_its_three_lines` (`:101`, `"26 check_codex_ready"` → `"42 check_codex_ready"`) and `test_codex_host_helper_lifecycle.py::CodexHelperSnippetTests::test_the_section_4_snippet_prints_its_seven_lines` (`:109`, `"26 False"` → `"42 False"`). Both print `len(tools)`. My r1 sweep looked for `len(tools) == 26` and missed two that print the count instead.
- **S2-2.** The new message is now `CODEX_HOST_NO_STORED_GOAL_MESSAGE`, with the same text. The existing `CODEX_HOST_NO_GOAL_MESSAGE` (`codex_host.py:312`, `skill_functions.py:217`, pinned at `test_codex_host_helper_surface.py:94`) is untouched. `_CAUSE` and `_NEXT_STEP` keep their names.

**Sweep for other catalog or operation counts:**
- **Searched:** `grep -rn "26"` over `tests/features/codex_host`, `tests/features/harness_threads` and `tests/test_codex_*.py`, each hit read by eye. I also searched for `len(tools|TOOL_TABLE|TOOL_NAMES|CodexHostOperation)`, printed counts, the `TOOL_TABLE[`/`names()[` slices, loops over the whole catalog, and the operation-order pins.
- **Count pins:** none besides the two above. The other "26" hits are spec IDs, rows already superseded and rewritten by S2, or test names.
- **Operation-order pins:** `helper_surface.py:245-251` and `hardening_records.py:108-115` still hold, because the 25 new members go in before `LAUNCH_CODEX_SUBAGENTS`, which comes before `START_CODEX_REVIEW`.
- **No operation-count literal:** no test asserts `len(CodexHostOperation)`.
- **Prose drift, not asserted:** `tests/features/codex_host/FEATURE.md:190,207` and `README.md:51` still say "26-tool".

**Clarifications chosen (each within S2's accepted set):**
- **(3)** All 15 method constants named in §9.3. They follow the two pinned names (`CODEX_THREAD_SETTINGS_UPDATE_METHOD`, `CODEX_THREAD_SEARCH_METHOD`) and the module's existing `CODEX_GOAL_SET_METHOD` style. So they are `CODEX_<...>_METHOD`, not `CODEX_HOST_<...>_METHOD`: the request's pattern contradicts the two pinned names it says to follow.
- **(4)** `reasoning_effort`, the `CodexCollaborationMode` field the sentence names as its subject.
- **(5)** `.name`, not the recommended `.value`: `PROVIDER_DEFAULT`'s value is `""`, and network access with the default sandbox is exactly a case this message refuses.
- **(6)** Required, as in §8.5 and the wire schema.
- **(7)** Yes, through `handle.thread_id`, as slice 1's `steer_codex_turn` does.
- **(8)** Omitted, because the schema treats false and null alike.

**Counts:** unchanged. IDs: G6 NG19 INV55 AC44 EC62 FR36 NFR12 D39 T8 W19 A21 Q11. Budget: 13 / 69 / 0 / 46 / 0 / 42.

## r5 addendum (S3 findings, 2026-10-18)

**Input.** The coordinator's r5 request (A1 and A2) and `reports/S3-implementer.md` (S3 labels them B-1 and B-5). This is an amendment, not a review round, so the status stays `approved`. The spec is committed at 5f6c4fc4 (revision 5). §16 has rows S3-1 and S3-2, and §17 has r5.

**A1 (S3-1).** §13 now supersedes `test_codex_host_hardening_records.py::CodexSpawnRequestHardeningTests::test_the_new_fields_default_to_unset_and_build_with_the_sandbox_they_need` (`:356`). The tail after `name` gains `"collaboration_mode"`, as D-5 and row 7 require.

**Sweep.** I grepped `turn_service_tier`, `writable_roots`, `network_access` and `dataclasses.fields(` across `tests/features/codex_host` and `tests/features/harness_threads`, and read every hit. No other test pins `CodexSpawnRequest`'s field list or order:
- **Already superseded and rewritten by S2:** the fork-row tail (`hardening_contract.py:548`), `GOAL_REJECTED_FIELDS` (`codex_host_support.py:284`, `hardening_records.py:438`) and `GOAL_REFUSED`.
- **Computed from the fields, so they follow automatically:** the review row (`hardening_contract.py:543-544`) and `feature_constants.py:209`.
- **About other records:** `CodexForkRequest`'s last two fields, `CodexThreadListRequest`'s last field, `CodexThreadInfo`'s tier fields, and the helper records' `RECORD_FIELDS`.
- **Not order pins:** first-field-only frozen checks, and `FORBIDDEN_PARAMETERS`, which lists tool parameter names, not record fields.
- **Elsewhere:** no test outside `tests/features/codex_host` names `CodexSpawnRequest`.

My r1 and r4 sweeps looked for counts of tools and operations. They missed this order pin because it asserts the exact tail list rather than a count.

**A2 (S3-2).**
- **Renamed** `CodexMcpAuthStatus.BEARER_TOKEN` → `BEARER` in §8.5 (the only spec line that named the member), keeping `"bearerToken"`.
- **Rationale** is D-40: lint S054 (ruff S105, allowance 3) flags the name alone, the baseline may not be raised for a new violation, and §14 forbids suppressions.
- **§13:** the `EXPECTED_ENUMS` row (`test_codex_host_records.py:83`) now notes the member name, and a new row covers `test_codex_host_mcp_memory.py:83`. S2 updates both.
- **No other mentions:** §9.1 lists no members.

**Cited only:** S3's B-2, B-3 and B-4 are test defects with no spec change.

**Counts:** D-40 added, so D goes to 40. Every other ID count and the §8.4 budget are unchanged (13 / 69 / 0 / 46 / 0 / 42). `ids.py` and `tables.py` are clean.
