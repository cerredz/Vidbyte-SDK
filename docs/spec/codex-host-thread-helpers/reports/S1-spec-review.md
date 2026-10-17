VERDICT: SOUND WITH FIXES

Reviewer: S1 spec reviewer (staff engineer), round 1 of 2, full review of spec r1 (`5a1c754c`, 1,193 lines).
Count: 2 Blocker, 7 Major, 6 Minor.

## WHAT THE SPEC GETS RIGHT

- **The collaborator split works.** `CodexThreadHelpers` and `CodexSkillFunctions` are built in `_open()`, as `CodexPreflight` is, and every host method is a guard plus one delegation. That keeps `host.py` (771 lines today) under the 900 budget and keeps call chains one level deep. Reusing `spawn_codex_thread` gives one goal path, as request §C asks.
- **The failure codes fit both pins.** The three new codes come right after `CODEX_TURN_TIMED_OUT`, with classification rows and next steps beside its row (`constants/codex.py` 266 and 435). The 15-code slice test and `assertEqual(dict(CODEX_NEXT_STEPS), NEXT_STEPS)` can both still pass, and `test_codex_failure_recovery.py:193-203` gets its rows.
- **Not-found mapping without touching `errors.py`.** `_rpc_code` (`errors.py:97-107`) already maps any JSON-RPC error on `thread/read` to `session_not_found`, so one existence read gives a precise code. Per-method overrides would have mislabeled busy refusals as not-found.
- **The fake's gaps and the bundled skills are reported accurately.** The §13 list of fake gaps is true: there are no handlers for the five methods, and `_thread_list` ignores its params and never ends. The ✗ verdicts on the bundled skills match code-map §4.c (imagegen and skill-creator ask the user; skill-installer ends with a question; review-agent has `allow_implicit_invocation: false`).

## FINDINGS

R-1 [Blocker] [L8] §8.5 / §9.4 / §12.3 row 8 — `thread_list(..., limit: int = 0)` adds an A007 finding, so SDK-LINT fails
- Evidence: spec lines 626, 827 and row 8 (line 1002) say "gains a trailing `limit: int = 0`, sent … only when > 0". `lint/rules/a007_*.py:117-135` (`_parameter_defaults`) flags every numeric default on a parameter whose name contains the token `limit` (`OPERATIONAL_TOKENS`, line 33). `_numeric` (65-67) does not exempt 0. The baseline is `"A007": 255`. Lint is a count ratchet.
- Failure: one new A007 finding means A007 is REGRESSED and `python scripts/run_ci.py` fails. §12.4 has no A007 line, so the implementer is not warned. The `> 0` comparison may add a second finding (a literal near `limit`).
- Smallest fix: change it to `limit: int | None = None`, sent only when it is not None. INV-17 already uses this for `turns_page`. Add an A007 line to §12.4: "no numeric default or bare numeric literal on any timeout/limit/budget/depth name; use None or a named constant".

R-2 [Blocker] [L8/L10] §13 "Existing pins the new surface necessarily changes" — misses the `_valid_arguments` and `_valid_kwargs` pins
- Evidence: `tests/features/codex_host/test_codex_host_tools.py:40` `_valid_arguments(handle)` returns one argument dict per tool, 15 keys. `test_every_tool_turns_host_errors_into_error_results` (170-183) loops over `TOOL_NAMES` and indexes `_valid_arguments(handle)[name]`. `test_codex_host_records.py:312` asserts `set(_valid_kwargs()) == set(RECORD_NAMES)`. §13 authorizes `TOOL_TABLE`, `len(tools)`, `RECORD_NAMES` and others, but neither helper. `grep _valid_arguments spec.md` finds nothing.
- Failure: once `TOOL_NAMES` gains 11 rows, the loop raises `KeyError` for each new name, and once `RECORD_NAMES` grows the records equality fails. S2 may update "only" the pins §13 lists (§13, §14 "Ask first"), so the pack is red with no authorized way to fix it, or S2 stalls as BLOCKED.
- Smallest fix: add both to the §13 authorized list: "`_valid_arguments` (`test_codex_host_tools.py:40`) gains one valid argument dict per new tool; `_valid_kwargs` (`test_codex_host_records.py:108`) gains a baseline per new record".

R-3 [Major] [L5/L7] INV-18 / INV-20 / D-13 / D-15 / A-4 — resuming a `NOT_LOADED` thread inside a READ tool can restart paid goal turns
- Evidence: `get_codex_goal` is a READ tool (§9.2) and resumes a `NOT_LOADED` thread first (INV-20, D-15). The vendor's `_start_goal_operation` waits for a "runtime-generated first turn", so an active goal drives turns by itself. The host's goal interrupt (`connection.py:271-289`) goes through `cancel_goal_operation`, which pauses the goal *before* interrupting, so an unpaused active goal keeps going. `turns.py` tracks only turns this host started. A-4 itself is only inferred from error-message wording.
- Failure: reading the goal of a stored thread whose goal is still `active` may load it and let Codex continue the goal. Those are untracked, uncapped paid turns, started by a tool marked READ, and nothing stops them when the host closes. Compact has the same exposure, though there it sits inside a WRITE tool.
- Smallest fix: settle A-4 and A-5 before S2, using the author's own non-spending probe on a real `notLoaded` thread id from `thread/list` (`thread/goal/get`, `thread/turns/list` and `thread/read`, with no resume). If goal/get answers, drop the resume (D-15 flip). If it does not, add an A-16 ("resume may restart an active goal"), and have `get_codex_goal` never resume: it raises `codex.session_not_found`-class guidance ("continue the thread first") instead.

R-4 [Major] [L5] INV-18 / NG-12 / EC-20 — a compaction is lost if the host closes right after `compact` returns
- Evidence: INV-18 returns `None` "once Codex accepts", and the tool returns `COMPACT_STARTED_TEXT`. NG-12 leaves the compaction turn untracked. Closing the host (`_open`/close in `host.py:146-185`) ends the `codex app-server` child that runs the compaction. EC-20 covers only a following continue.
- Failure: the natural `async with CodexHost() as h: await h.compact_codex_thread(t)` exits right after the call returns. The compaction is cut off and may already have been paid for. The caller saw no error, and no EC names this case.
- Smallest fix: add an EC row and a sentence in INV-18, the method docstring and the tool description: "the compaction finishes only while this host stays open". Optional [scope-adding] Q-16: wait for the compaction turn's completion, bounded by a named constant.

R-5 [Major] [L1] D-17 / INV-25 / A-7 — skill runs skip the §C "check that the command actually ran" rule with no question raised
- Evidence: request §C: "a skill/goal wrapper verifies in the thread that the feature took (for goal: thread/goal/get) and raises a specific error if not". D-17: "There is no read-back after the turn starts". A-7 admits that neither the item order nor whether Codex honours the item could be verified. No Q-n covers this.
- Failure: if Codex silently drops the skill item (wrong order, or an unsupported position), `run_codex_skill` and `run_codex_openai_docs` return a handle as success. The run is a plain prompt that the caller believes used the skill, which is exactly the outcome §C asked to rule out.
- Smallest fix: either build the read-back §C asks for or ask the owner. To build it: after the turn starts, read the newest turn (`thread/turns/list`, limit 1, newest first) and check that its userMessage holds a `skill` item with the sent name. If it does not, interrupt once and raise `codex.command_not_run`, as INV-22 does. Add an A- entry for when the item is persisted. To ask instead: keep D-17, cite §C as a deviation, and add Q-16.

R-6 [Major] [L1] D-9 / D-14 / FR-15 / Q-11 / Q-14 — the spec departs from two §C expected error cases without citing §C
- Evidence: request §C lists "empty since-window" and "delete of a loaded thread" among expected *error* cases. D-9 returns `()`, and D-14 deletes an idle loaded thread. Neither row cites the §C sentence; only the author's report (S1-spec-author.md:69-70) calls them disagreements.
- Failure: the reasons are defensible, but at approval the owner cannot see that two named expected cases were changed. Q-11 and Q-14 read as optional extras rather than as deviations from the request.
- Smallest fix: add one table that maps each §C expected case (unknown thread id, unknown skill, thread busy, compact on a running turn, delete of a loaded thread, empty since-window) to its INV/EC and outcome. Mark D-9 and D-14 "deviates from §C", and point Q-11 and Q-14 at them. Neither decision needs to be reversed.

R-7 [Major] [L4] D-2 / §12.3 row 10 — `skill_functions` ↔ `host` is a module cycle under AGENTS §3
- Evidence: `host.py` imports `skill_functions` at runtime to build `CodexSkillFunctions` in `_open()`. `skill_functions.py` imports `CodexHost` under `TYPE_CHECKING` (D-2). AGENTS §3 says "no two modules depend on each other in a cycle". D-2 relies on A006 skipping `TYPE_CHECKING` edges, which makes the lint silent but leaves the cycle in place. The existing precedent, `launch_codex_subagents` (`host.py:428-461`), has no back-reference.
- Failure: a placement or cycle review flags the dependency in both directions, and mypy needs the real host type only to call four methods.
- Smallest fix: define a small `Protocol` in `skill_functions.py` with `spawn_codex_thread`, `list_codex_skills`, `get_codex_goal` and `interrupt_codex_turn`, and type the field with it. `skill_functions` then never imports `host`. AGENTS Placement endorses "a `Protocol`" for this.

R-8 [Major] [L8] §12.4 — the checklist leaves out four ratcheted lint rules the new code is likely to trip
- Evidence: `lint/baseline.json` counts: C008 45, S024 25, S008 19, A007 255. All are ratchets, so any new finding fails. C008 (`c008_*.py:25-27`) flags validator definitions named with a verb (`require`, `validate`, `ensure`, `check`, `resolve`, `normalize`, `coerce`, `is`) followed by a primitive (`limit`, `positive`, `int`, `budget`, `bool`, `timeout`) outside `vidbyte/lib/dataclasses/validation.py`. The new records validate `limit`, depth and `token_budget`. S024 caps nesting at 3. S008 runs ruff C901/PLR0912/PLR0915, and the lineage walk and the goal check have several exits.
- Failure: an implementer who follows §12.4 exactly can still write `_require_positive_limit` or a 4-deep loop in the lineage walk, and SDK-LINT then fails.
- Smallest fix: add four lines to §12.4. Reuse the existing record validators or name new ones `_reject_*`, and never define a new `require/validate/check` + primitive helper. Keep nesting at 3 or less and branches under the ruff limits by splitting flat helpers. Put no numeric literal next to a limit/depth/budget name.

R-9 [Major] [L6] §9.2 tool 20 / INV-17 — `list_codex_turns` returns the full transcript, with no limit, to the model
- Evidence: §9.2 row 20 makes `limit` optional. INV-17 sends `limit` "only when not None" with `itemsView: "full"`. codex-host INV-35 strips items from wait/get tool output for the same size reason.
- Failure: when the model omits `limit`, a long thread returns every item of every turn in one tool result. That can flood the calling agent's context window, which a model-facing tool contract should prevent.
- Smallest fix: the tool, but not the host method, applies a named constant (for example `CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT`) when `limit` is absent, and its description says to page with `cursor`.

R-10 [Minor] [L4] §12.3 row 6 — `from_sdk → items → _item` is a three-level chain
- Evidence: row 6: "`from_sdk` uses `items=cls.items(result.items)`", and `items` calls `cls._item`. AGENTS §1 applies to code the change touches.
- Failure: a changed main function gains a helper that itself calls a helper. INV-32 still holds.
- Smallest fix: leave `from_sdk` byte-for-byte unchanged. Only the new collaborator calls `CodexResultSerializer.items`, which is a call into another class and so does not count.

R-11 [Minor] [L9] §11 / §12.4 / §8 folders table — the spec overlooks `vidbyte/agents/codex/README.md`
- Evidence: the README exists (about 51,754 characters, with a File Index and Non-Goals) and governs `result.py`, which row 6 changes. Spec lines 852 and 1047 say "no folder README exists in the touched folders".
- Failure: AGENTS says to read a folder's README to the end before changing anything in the folder. The spec's statement is false for one touched folder.
- Smallest fix: list the README as read, and state that no File Index change is needed because no file is added there.

R-12 [Minor] [L9] §4 (line 118) / AC-1 — "codex 0.151.0 or newer" is unverified for the five new methods
- Evidence: the author probed only 0.162.1 (S1-spec-author.md:39), and EC-35 says "older than the probed 0.162.1".
- Failure: manual QA on 0.151 to 0.161 may hit -32601 even though AC-1 promises it works.
- Smallest fix: state "0.162.1 (probed); older runtimes raise `codex.protocol_mismatch` (EC-35)".

R-13 [Minor] [L1] FR-13 / D-10 / G-4 — the mirrored field types of `NativeThreadSummary` are not pinned
- Evidence: FR-13 names the seven fields, but nothing pins `updated_at` as int seconds versus float or datetime, or `model` as `""` versus None. The model is on the sibling branch, which this review must not read.
- Failure: the later cross-harness merge (G-4) is no longer mechanical if the types differ.
- Smallest fix: add an A- entry that states the assumed types and their source, plus a D-10 flip: "if the sibling's types differ, align them before the merge".

R-14 [Minor] [L9] NG-14 — one pinned toolsets line stops being exactly true
- Evidence: `vidbyte/tools/toolsets/__init__.py:11` "- CodexHostTools: One tool per CodexHost function over one host." is pinned at `test_codex_host_packaging.py:242`. With `delete_codex_thread`, the host has 27 functions and 26 tools.
- Failure: NG-14's claim that "their generic text stays true" is no longer exact.
- Smallest fix: acknowledge this in NG-14 as known drift that is not edited because the line is pinned. Optionally list it under Q-n for a follow-up.

R-15 [Minor] [L5] INV-16 — "any other failure while reading an ancestor propagates" cannot happen as written
- Evidence: `_rpc_code` maps *every* JSON-RPC error on `thread/read` to `session_not_found` (`errors.py:101-102`). Only timeouts, transport death and cancellation reach the "other failure" branch.
- Failure: a refused parent read (permission, malformed id) silently ends the walk with an incomplete chain instead of raising. The behavior is acceptable, but the spec text does not describe it.
- Smallest fix: reword INV-16: "any JSON-RPC error on a parent read ends the walk as not found; a timeout, a dead server or a cancellation propagates".

## VERIFIED CLAIMS

1. `host.py` is 771 lines. `launch_codex_subagents` (428-461) re-sequences private spawn helpers and re-raises with a message suffix (452-460), which is the precedent D-2 cites. **True.**
2. In `constants/codex.py` (543 lines), `CODEX_FAILURE_CLASSIFICATION` starts at 99 with the `TURN_TIMED_OUT` row at 266. `CODEX_NEXT_STEPS` starts at 420 with `TURN_TIMED_OUT` at 435, and `__all__` is at 460. The row 4 placement and the 15-code slice claim hold. **True.**
3. `errors.py:97-107` `_rpc_code` maps `thread/read` errors to `session_not_found`, so `errors.py` can stay unchanged. **True**, with the caveat in R-15.
4. `test_codex_host_records.py:61` derives the `CodexHostOperation` expectation from `TOOL_NAMES`, so `DELETE_CODEX_THREAD` needs an explicit extra, which §13 lists. **True.** `_valid_kwargs` (108, 312) is not listed (R-2).
5. `test_codex_failure_recovery.py:193-203` requires a classification row for every `codex.*` code, and `test_session_failures.py:143` requires a dot. **True.**
6. `test_codex_output_contracts.py:322` calls `CodexResultSerializer._item(...)` directly, so INV-32 must keep `_item`. **True.**
7. The pins exist as stated: `len(tools) == 15` at `test_codex_host_tools.py:141`, the probe `(15, "check_codex_ready")` at `test_codex_host_packaging.py:165`, and the toolsets docstring at `:242`. **True.** `_valid_arguments` at `:40` is missing from §13 (R-2).
8. `wire.py` `thread_list` drops falsy params, and `thread_resume` sends approvals only when set. `RAW_RESPONSES` (`connection.py:67-73`) has 5 rows, and row 7 adds 4. **True.**
9. `preflight.py` `require_idle` is at 162-167 and `require_thread` at 169-173. `turns.py` counts reserved threads as busy, so compact's reserve blocks this host's own continue (D-13). **True.**
10. The headless ✗ reasons for the bundled skills match code-map §4.c. The spec's §9.2 paraphrases instead of quoting SKILL.md text and uses `$CODEX_HOME` instead of a real home path. **True.**
11. Lint baselines: A007 255, C008 45, S008 19, S024 25. A007 flags a numeric default of 0 on a `limit`-named parameter (`_numeric` exempts only bools). **True**, which is the basis of R-1.
