VERDICT: SOUND WITH FIXES — r2 resolves 14 of the 15 round-1 findings and partly resolves the 15th, but the new skill read-back loop, built as §12.3 row 10 prescribes, is a new S064 lint finding and fails the gate; three smaller defects (ephemeral skill runs, a dead-end next step, a turn-only size bound) need text fixes before S2.

Reviewed: spec.md r2 (commit deeba11e, HEAD e5249ea6, base c181be65). Read-only. Lint checks were run against a scratchpad fixture, never against repository files.

## ROUND-1 RESOLUTION

- R-1 resolved. `thread_list` gains `limit: int | None = None` (§9.4 line 884, §12.3 row 8). `wire.py:267-287` drops falsy values, so existing callers send nothing new. §12.4 has an A007 line (line 1113). A fixture with the prescribed shapes produces no A007 finding.
- R-2 resolved. §13 authorizes `_valid_arguments` (`test_codex_host_tools.py:40`) and `_valid_kwargs` (`test_codex_host_records.py:108,312`) at lines 1183-1184. Every other changed pin is listed or derives from `TOOL_TABLE`/`TOOL_NAMES` (`WRITE_TOOLS` at tools:35, the `CodexHostOperation` expectation at records:61).
- R-3 resolved. `get_codex_goal` never resumes (INV-20, INV-33). Compact reads the goal before any resume and raises `codex.goal_unfinished` unless the goal is `complete` (INV-18, D-13, AC-38, EC-42). Residual risks are named (A-16, A-17, EC-43, EC-44). Local `~/.codex/goals_1.sqlite` evidence corroborates A-16 (see R-22).
- R-4 resolved. INV-18 last bullet, EC-41, the row 11 docstring, the tool description and `COMPACT_STARTED_TEXT`. Q-16 is `[scope-adding]` with default no.
- R-5 resolved as decided, with regressions. The read-back is built (INV-34, INV-35, D-17, AC-30, AC-39, AC-40, EC-45, EC-46). Its loop introduces R-16, and it ignores ephemeral threads (R-17).
- R-6 resolved. The §C expected-case table in §6.3 maps all six cases. D-9, D-14 and FR-15 say "deviates from request §C", and Q-11 and Q-14 point at them.
- R-7 resolved. `CodexSkillHost` Protocol (D-2, §8.5 line 662, row 10: "never imports `host.py`"). Lint A005, A006 and C011 accept or skip Protocols. The host satisfies it structurally, and the mypy line in §12.4 covers it.
- R-8 resolved for the four named rules. §12.4 now has A007, C008, S024 and S008 lines with their rule files and baselines. A fifth ratchet, S064, is tripped by r2's own new loop (R-16).
- R-9 partially resolved. D-25, AC-41 and EC-47 bound the default page at 3 turns. One turn is still unbounded in size, and pages come oldest first (R-19).
- R-10 resolved. Row 6 leaves `from_sdk` byte for byte (INV-32), and only new code calls `items()`.
- R-11 resolved. §11 line 910 and §12.2 line 1059 record the README as read. It is 51,754 characters, under its 65,000 A009 legacy ceiling.
- R-12 resolved. §4 line 118, AC-1 and EC-35 say 0.162.1 was probed and that older runtimes raise `protocol_mismatch`.
- R-13 resolved. A-18 states the assumed types and their source, and D-10 flips on A-18.
- R-14 resolved. NG-14 records the drift at `toolsets/__init__.py:11` (pinned at packaging:242), with Q-18 defaulting to no.
- R-15 resolved. The INV-16 last bullet and EC-14 match `_rpc_code` (`errors.py:97-107`).

## WHAT THE SPEC GETS RIGHT

- **The compact goal gate is the right control in the right place.** One raw `thread/goal/get` runs before any resume, and only `complete` is trusted (INV-18, D-13, INV-33). Codex stores goals by `thread_id` independently of load state, and it keeps a `thread_goal_continuation_deferrals` table, so an unchecked resume really could restart goal work. The gate closes that hole without forcing a paid turn.
- **The cycle is gone at the source.** `CodexSkillHost` lives beside its only user, and `skill_functions.py` never imports the host, not even under `TYPE_CHECKING`. This is the AGENTS Placement remedy, and no lint rule objects to it.
- **The error vocabulary fits every pin.** The 4 codes go after `CODEX_TURN_TIMED_OUT` (`failure.py:61`) and before `INPUT_EMPTY` (62), which keeps both the 15-code host slice (records:395-402) and #1036's 28-code tail after `RULE_EVALUATION_FAILED` (159). Each code has a classification row and a next step, so `CodexErrorMapper.error` (`errors.py:61`) can never raise `KeyError`.
- **The read-back looks in the right place.** `userMessage` is in `CODEX_SUPPORTED_ITEM_TYPES` (`constants/codex.py:84`), so `_item` keeps `content` as a list of `{type, name, path}` dicts (`result.py:81-95`, `by_alias`). The turn-id match uses `CodexTurnHandle.turn_id`. Local rollouts show that Codex persists skill entries in exactly that form (R-22).

## FINDINGS

R-16 [Blocker] [L8/L11] §12.3 row 10 / §12.4 / INV-34 / NFR-5 — The skill read-back loop as specified is a new S064 finding, so SDK-LINT fails
- Evidence:
  - What S064 counts. It treats a loop as a retry loop when the loop names a retry word (`_RETRY_WORDS = retr(y|ies|ied)|attempt|backoff`, case-insensitive, `lint/rules/s064_retry_overall_deadline.py:31`) and sleeps at its own level. Such a loop complies only through an ordered comparison against a clock value or an enclosing timeout scope (the file header).
  - Baseline. `lint/baseline.json:91` is `"S064": 4`, and the rule currently finds 4, so there is no slack.
  - What row 10 prescribes. Up to `CODEX_HOST_INPUT_CHECK_ATTEMPTS` calls "with `await asyncio.sleep(CODEX_HOST_INPUT_CHECK_INTERVAL_SECONDS)` between them", and no deadline.
  - Fixture result. A scratchpad fixture of exactly that shape, run through the rule, is reported as retry-without-deadline (words: `CODEX_HOST_INPUT_CHECK_ATTEMPTS`). The same loop inside `asyncio.timeout(...)` is not reported.
  - §12.4 lists A007, C008, S024 and S008, but has no S064 line.
  - NFR-5 says the read-back "waits at most ATTEMPTS × INTERVAL". In fact each round sends two requests (`thread/read`, then `thread/turns/list`), and each request is bounded only by `CODEX_HOST_REQUEST_TIMEOUT_SECONDS` = `CODEX_TOOL_CALL_TIMEOUT_SECONDS` = 300.0 (`constants/codex.py:291,327`). The real worst case is about 10 × 2 × 300 s. That is exactly the cumulative overrun S064 exists to prevent.
- Failure: an implementer who follows row 10 verbatim gets S064 found 5 against a baseline of 4. The rule reports REGRESSED and `scripts/run_ci.py` fails (NFR-4). The easy ways out, renaming the constant so it avoids "attempt" or raising the baseline, are rule-gaming that house style forbids. So S3 either stalls or cheats.
- Smallest fix:
  1. Add §9.3 `CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS`, for example `10.0`. It must not be derived from the interval: tests patch the interval to 0 in `skill_functions` (§13 line 1196), and a derived deadline would then be 0, which breaks AC-39's exact read count.
  2. In row 10 and INV-34, take `deadline = loop.time() + CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS` before the first read. Before each sleep, stop when `loop.time() + CODEX_HOST_INPUT_CHECK_INTERVAL_SECONDS >= deadline`. The precedent is `vidbyte/lib/http/vidbyte_gateway.py:196-209`. Do not wrap the loop in `asyncio.timeout`: it would cancel an in-flight read and turn a plain miss into a `TimeoutError` on the INV-35 re-raise path instead of `command_not_run`.
  3. Add to §12.4: "S064 (baseline 4) gains nothing. The read-back loop compares `loop.time()` with a deadline taken from the named constant (`s064_retry_overall_deadline.py`)." Add the read-back helper to the A002 line's list of expected `@intent` sites, because it names "attempt".
  4. In NFR-5, state both bounds: at most ATTEMPTS reads, and no new read after the deadline. Add the deadline constant to §13's constants-dict note.

R-17 [Major] [L5] INV-6 / INV-34 / §6.3 — `run_codex_skill` on an ephemeral thread starts a paid turn, then always reports `command_not_run`
- Evidence:
  - Skill and docs runs accept `CodexThreadSettings.ephemeral` (`vidbyte/lib/dataclasses/codex.py:202`). Only the goal path refuses it (`codex_host.py:225-233`, "Codex keeps goals only on stored threads"). Tool calls can carry ephemeral `spawn_defaults`.
  - Generated schema: an ephemeral thread "should not be materialized on disk", and `itemsView: full` returns "every ThreadItem available from persisted app-server history".
  - INV-34, A-19 and A-20 all rely on recorded history. No EC, A or AC entry covers an ephemeral thread for the read-back or for `list_codex_turns`.
- Failure:
  - Input: `run_codex_skill("s", "do it", request=CodexSpawnRequest(thread=CodexThreadSettings(ephemeral=True)))`.
  - State: Codex persists no history for the thread, so `thread/turns/list` shows no `userMessage` on any of the 10 reads.
  - Wrong output: a turn that started correctly with the skill is interrupted. The caller gets `codex.command_not_run` saying the run "could not be confirmed". Every ephemeral skill or docs run spends money and then fails falsely.
  - The fake-based suite cannot detect this (NG-15).
- Smallest fix:
  - Add to INV-6: "a skill or docs run on an ephemeral thread" raises `ConfigurationError` before any request, with a message constant in `skill_functions` whose reason mirrors `_reject_bad_goal`'s.
  - Add an EC row and one more case to AC-28's style of AC.
  - Add A-21: "an ephemeral thread exposes no turns through `thread/turns/list`; if wrong, drop the refusal."
  - Add an EC row for `list_codex_turns` on an ephemeral thread (expected: an empty page, not an error).

R-18 [Major] [L1/L5] §9.2 error table — The `codex.goal_unfinished` next step offers two remedies, and both fail
- Evidence:
  - The next step (line 754) reads: "Wait for the thread's goal to finish, or pause it from a Codex client, then compact the thread again."
  - EC-42 and AC-38 refuse `paused`, and Q-17 keeps that refusal by default.
  - The gate fires only on `NOT_LOADED` threads, which run no turns, so their goals never finish by waiting.
  - Codex 0.162.1 has `thread/goal/clear` (`v2_all.py:9920`, method literal at 10652). A cleared goal reads back as None, which INV-18 lets through.
- Failure: a caller who pauses the goal and retries gets `goal_unfinished (status paused)` again. A caller who waits sees nothing change. FR-15's "next step" is present but leads nowhere, which defeats G-5 and §C's "extensively handle errors".
- Smallest fix: change the text to "Continue the thread with continue_codex_thread until its goal is complete, or clear the goal from a Codex client, then compact the thread again." This is optional: the row `("transient", "session", "warning", "route")` implies that retrying helps. `("terminal", "session", "warning", "raise")` is more honest, but only `vidbyte/agents/codex/failures.py` reads the row, so the change is cosmetic.

R-19 [Minor] [L6] D-25 / EC-47 — The tool default bounds turns, not size, and pages come oldest first
- Evidence:
  - INV-17 sends `itemsView: "full"` with `sortDirection: asc`.
  - `_item` keeps whole payloads, command output included, for supported types (`result.py:81-95`).
  - D-25 itself cites one probed turn with 89 items.
  - EC-47 promises "a bounded tool result".
- Failure: on a thread whose early turns ran large commands, `list_codex_turns(thread_id)` returns the 3 oldest turns in full, which can be hundreds of items with no byte bound. A model that wants the latest work has to page through the whole thread from the start.
- Smallest fix: EC-47 and the `limit` description should say "bounded in turns, not in size; pages are oldest first". Optional Q-19 `[scope-adding]`, default not built: a byte cap on the tool result, or a newest-first option for the tool.

R-20 [Minor] [L9] §8.4 / §17 — The budget says 19 classes but lists 20
- Evidence: line 600 itemizes 2 collaborators, 1 Protocol, 11 tools, 5 records and 1 enum, which is 20. The r2 row of §17 (line 1302) repeats "19". Line 606 says that exceeding the budget means stopping and reporting BLOCKED.
- Failure: an implementer who builds exactly the listed classes exceeds the stated count. They either stop as BLOCKED or are flagged for a budget breach that is not real.
- Smallest fix: change "19" to "20" at lines 600 and 1302.

R-21 [Minor] [L9] A-11 / §12.3 rows 5 and 16 — Three texts stay stale after r2
- Evidence:
  - A-11 (line 1239) still says "compact or goal-read could change stored thread settings", but INV-33 says goal-read never resumes.
  - `codex_host.py:4` "(the fifteen tools)" is in neither row 5 (which edits only line 3) nor §12.5.
  - `tools/builtins/codex/__init__.py:3` "one per CodexHost function" becomes untrue, because delete has no tool. The packaging test pins only `__all__` there (packaging:212), not the header. Row 16 changes only the count.
- Failure: two A001 headers are untrue after the PR (code-map §4.e), and A-11 misleads the reader about which functions resume.
- Smallest fix:
  - A-11: "compact could change stored thread settings".
  - Row 5: also change line 4 from "fifteen tools" to "twenty-six tools".
  - Row 16: "one per CodexHost function except delete_codex_thread".

R-22 [Minor] [L10] §15 A-7 / A-16 / A-19 / A-20 — Local evidence already backs the read-back's key assumptions, and the spec does not cite it
- Evidence: read-only, counts-only scans of `~/.codex/sessions` rollouts and `~/.codex/goals_1.sqlite`:
  - From Codex 0.147, each turn's input is persisted as a completed `UserMessage` item whose `content` keeps `{type: "skill", name, path}` entries. There are 244 such entries in 183 files (0.147-0.160).
  - Entry order is text then skill in 230 messages, and text, skill, skill in 7. That is the spec's order, which bears on A-7.
  - In 0.16x rollouts, the `UserMessage` is the first item completed after `task_started` in 280 of 280 turns, which bears on A-19's ordering though not its timing.
  - The `thread_goals` table keys goals by `thread_id` and holds 69 rows: complete 52, blocked 6, usage_limited 6, paused 4, active 1. That bears on A-15 and A-16.
- Failure: no wrong behavior. But A-20 ("the probe saw only text entries") and A-7 ("order unverified") invite a later reviewer to reopen D-17 or demand a paid probe that is not needed. A-19's timing does stay unverified, because rollouts are written when an item completes.
- Smallest fix: cite this evidence in A-7, A-16, A-19 (ordering only) and A-20. Add one sentence to D-17: the check proves that Codex recorded the skill input, not that the model used the skill.

## VERIFIED CLAIMS

- **Failure-code placement holds.** `failure.py:61` is `CODEX_TURN_TIMED_OUT`, 62 is `INPUT_EMPTY` and 159 is `RULE_EVALUATION_FAILED`. Row 1's placement keeps the 15-code slice test (records:395-402) and #1036's 28-code tail. The inherited test still fails at `len(main_members)==120`, for its existing reason.
- **Row 4's import claim is true.** `CodexGoalStatus` is already imported at `constants/codex.py:19`. The existing `CODEX_GOAL_TERMINAL_STATUSES` (line 410, used by `turns.py:248`) differs from the new `CODEX_HOST_RESUMABLE_GOAL_STATUSES`, so there is no duplication.
- **Errors map as the spec says.**
  - `CodexErrorMapper.error(code, message, operation, thread_id="")` indexes `CODEX_NEXT_STEPS[code.value]` (`errors.py:61`).
  - `_rpc_code` maps every `thread/read` JSON-RPC error to `session_not_found` (97-107).
  - Classification rows are read only by `vidbyte/agents/codex/failures.py`. `tests/test_codex_failure_recovery.py:190-203` requires a row for every code.
- **The SDK surface matches the spec.**
  - `client.thread_compact(thread_id)` (client.py:534) and `request_with_retry_on_overload(method, params, *, response_model, max_attempts=3)` (731) exist.
  - In `v2_all.py`: `SkillUserInput(name, path, type)` (6491), `UserMessageThreadItem.content: list[UserInput]` (9968-9975), and the `ThreadDeleteResponse`, `ThreadGoalGetResponse`, `SkillsListResponse` and `ThreadTurnsListResponse` models.
  - `thread/goal/clear` exists (9920, 10652).
  - `ThreadTurnsListParams.limit` is a uint32 with a minimum of 0, and `sortDirection` defaults to desc, which is why the spec sends asc explicitly.
- **Host-side reuse is real.**
  - `_reject_small_int` is at `codex_host.py:57` and is already imported by `host.py` (59, 528).
  - `CodexTurnHandle` carries `thread_id` and `turn_id`.
  - `interrupt_codex_turn` (host.py:400) sends nothing for a finished turn, so the single interrupt after a miss is harmless.
  - The cancel-then-re-raise precedent is at host.py:592-602, and the error rebuild at 458-460.
  - `_resolve_count` returns None for an omitted argument, so the tool's `limit or CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT` works (D-25, AC-41).
- **Lint scope is as the spec assumes.**
  - S060 covers only `vidbyte/sessions/` and `vidbyte/lib/dataclasses/`.
  - S012 flags `.request(` calls that lack a timeout. The spec's "no method named request" is stricter and harmless.
  - The C008 verb list has no "reject", so `_reject_*` names pass.
  - S013 excludes the codex builtins, and S020 does not apply because the new folders have no README.
  - C019 has no near miss for the new codes. A005, A006 and C011 accept Protocols.
  - A002 reads Name and Attribute identifiers but not `ast.arg`, so the Protocol stubs' `request` parameter is not flagged.
  - Baselines: A002 703, A007 255, C008 45, S008 19, S024 25, S064 4 (found 4).
- **Tests pin what §13 says.**
  - `_valid_arguments` (tools:40) is indexed at 170-183, `len(tools)==15` is at 141, and the probe `(15, "check_codex_ready")` is at packaging:165.
  - `RECORD_EXPORTS` has 15 entries and `ENUMS_CODEX_ORDER` 22.
  - `CALL_LIST` checks parameter names (`test_codex_host_sdk_contract.py:22-46`).
  - No test enumerates `CodexHost`'s public methods, so the 12 new methods need no extra pin.
  - `test_harness_threads_static_policy.py` exempts the codex subpackage.
- **Header counts.** `vidbyte/agents/codex/README.md` is 51,754 characters, under its 65,000 ceiling. "fifteen" appears at `toolsets/codex.py:3,5,78`, `builtins/codex/__init__.py:3`, `_base.py:3`, `descriptions.py:3` and `codex_host.py:3,4`. All but `codex_host.py:4` are in §12.3 or §12.5 (R-21).
- **Local Codex state, read-only and counts only.** See R-22. No codex or app-server process was run, and no file other than this report was written to the repository.
