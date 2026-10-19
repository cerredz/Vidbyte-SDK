LENS: conventions

VERDICT: MERGEABLE AFTER FIXES — The slice follows #1178's grain closely and every gate is green, but it still writes fixed values in native-host function bodies, adds six comment lines one column past the field guide's 72, and leaves one input refusal that does not name the method; all of these are small, local fixes.

Target: `git diff origin/ai/resolve-pr-1055-comments...c9150d63` (HEAD `e7fd9289` differs from `c9150d63` only in `docs/spec/codex-host-hardening/pipeline.md`, so the working tree's source is the reviewed source).

## WHAT THE IMPLEMENTATION GETS RIGHT

- **#1178's three conventions are applied almost everywhere.**
  - Every new host error goes through `CodexErrorMapper.error`, `process_exited` or `relabel`. The only non-mapper raises are input `ConfigurationError`s that name `"<method> <field>"`.
  - Every new public input is a field on a `codex_host_inputs.py` record, built right after `_guard`, and the constructor builds `CodexHostSetup` first.
  - The 12 new messages, the tables and the bounds are in `vidbyte/lib/constants/codex_host.py`, in its sorted `__all__`.
- **Placement and layering are correct.**
  - The six new records are `@dataclass(frozen=True, slots=True)` in `lib/dataclasses/codex_host.py`.
  - The three new enums are in `lib/enums/codex.py` and exported alphabetically from `lib/enums/__init__.py`.
  - `ExceptionOrigin` is a static-method class in `lib/util/`, re-exported and named in the `vidbyte/lib/README.md` util bullet.
  - `lib` imports nothing upward (A006 34/34), and `retryable`'s import is function-level, as §12.4 asks.
- **Structure follows AGENTS.md §1–§3.**
  - The review and turn-event code moved into `reviews.py` and `turn_events.py`, so `host.py` ends at 923 lines (919 at base) despite the new surface.
  - Every new module has the full FILE header, including FUNCTION INVENTORY and WHAT NOT TO DO.
  - The main functions are narrated step by step, for example `CodexThreadHelpers.fork` Steps 2–8 and `_end_lost_turn` (a)–(d).
  - Among the changed modules, only one function is over 50 lines (R-V6).
- **Gates and hygiene are clean.**
  - `SDK-LINT: PASS`, with no ratcheted finding in any changed file except pre-existing ones in `lib/errors/base.py` and `lib/dataclasses/codex.py`.
  - Ruff, including I001, is clean on the 23 changed files, and semgrep-core reports 0 results.
  - Tests: 320 passed, 1 skipped, and only the inherited `harness_threads` `:193` failure.
  - The commits use conventional subjects that cite spec row IDs.
  - The diff contains no generated files, and `harnesses/README.md:178`, `REPO_MAP.md` and `native/codex/__init__.py` are untouched.

## FINDINGS (ranked, max 15)

R-V1 [Blocker] [field-guide C021 / INV-47] vidbyte/harnesses/native/codex/preflight.py:205 — Two new fixed values live in native-host function bodies, where C021 cannot see them

  Evidence:
  - `preflight.py:205`: `named = CODEX_HOST_LIST_SEPARATOR.join(sorted(names)) if names else "any model"`. This is message text: it fills the `{models}` slot of `CODEX_HOST_UNKNOWN_TIER_MESSAGE` (spec.md:1027).
  - `host.py:744`: `for name, value in (("before_turn_id", forking.before_turn_id), ("defer_goal_continuation", forking.defer_goal_continuation)):`. This is a field-rule table written inline. The equivalent goal rule went to lib as `CODEX_HOST_GOAL_REJECTED_FIELDS` (`codex_host.py:156`), and #1178's rule is `CODEX_HOST_REJECTED_FIELDS`.
  - S3's deviation records the first as deliberate (spec.md:1621: "a call-site literal in preflight.py … no constant was added").
  - #1178's native modules carry no message or field-rule literals of this kind. At base, the only such strings in `host.py`, `preflight.py`, `thread_helpers.py`, `errors.py` and `skill_functions.py` are `require_*` field labels and wire keys.

  Failure:
  - INV-47 (spec.md:466) is titled "No fixed value lives in the native host", and requires that "Every new table, bound, field rule and message text lives in `vidbyte.lib.constants.codex_host`."
  - The field guide's C021 entry (`field-guide/vidbyte-sdk/blocking-lint-invariants.md:68`) covers exactly "a table, bound, field rule or message text" in any `native/` module.
  - The user rejected this placement three times ("wrong file location, put inside of lib").
  - C021 sees only top-level bindings, so the lint gate cannot catch either value. AC-40's test checks top-level names only.

  Smallest fix:
  - Add `CODEX_HOST_ANY_MODEL = "any model"` and `CODEX_HOST_FORK_EXPERIMENTAL_FIELDS = ("before_turn_id", "defer_goal_continuation")` to `vidbyte/lib/constants/codex_host.py` and its sorted `__all__`.
  - Use `CODEX_HOST_ANY_MODEL` in `_tier_problem`.
  - In `_reject_experimental_fork_fields`, loop `for name in CODEX_HOST_FORK_EXPERIMENTAL_FIELDS: if getattr(forking, name): raise …`.
  - No test changes: the tier tests check by keyword, and the constants test (`test_codex_host_hardening_contract.py:383-396`) checks a subset and the sort order.

  Spec IDs: INV-47, D-31, AC-40, NFR-11, §12.4 line 1 (spec.md:1315)

R-V2 [Blocker] [field-guide comment-format] vidbyte/harnesses/native/codex/host.py:767 — Six new comment lines exceed the 72-column limit

  Evidence: The field guide's Check (`field-guide/vidbyte-sdk/comment-format.md`, "Check:"), run over the diff's added lines only, prints six lines, each 73 columns:
  - `host.py:767`: `# pricing names the model Codex resolved and its provider (D-19).`
  - `thread_helpers.py:324`
  - `turn_events.py:132`
  - `lib/dataclasses/codex_host.py:249`
  - `lib/dataclasses/codex_host.py:795`
  - `lib/errors/base.py:199`

  At base, #1178's codex files had 0 comment lines over 72 (`host.py`, `thread_helpers.py`, `turns.py`, `connection.py`, `wire.py`, `preflight.py`, `dataclasses/codex_host.py` and `codex_host_inputs.py` were each counted).

  Failure:
  - The entry's rule is "Wrap every comment line at 72 columns, counting the indent", and its Check must print nothing for the files you touched. It is the owner's stated preference (PR #690).
  - §12.4 (spec.md:1323) repeats it: "comments wrap at 72 columns".
  - No lint rule enforces it, so only review catches it.

  Smallest fix: Re-wrap the six blocks so each line is at most 72 columns. Keep each `# @intent` line first, and still within 20 lines of its `def` (A002).

  Spec IDs: §12.4 (spec.md:1323), A002

R-V3 [Major] [AGENTS.md placement: closed sets are enums / D-31] vidbyte/harnesses/native/codex/connection.py:140 — Three closed vocabularies of the router are bare string literals in native code

  Evidence: INV-8 (spec.md, INV-8 block) defines each of these as a fixed set:
  - `handled_by`: `"tool"`, `"default"`, `"handler"` (`connection.py:140`, `:149`, `:171`, `:192`).
  - Fallback reasons: `"closing"`, `"answer_invalid"`, `"parse_failed"`, `"handler_timed_out"`, `"handler_failed"` (`:164`, `:173`, `:241-248`). `_reason(...) -> str` returns one of these five values.
  - Answer labels: `"success"`, `"failure"`, `"answers"`, `"no_permissions"`, `"current_time"`, `"empty"` (`_label`, `:255-264`).

  `handled_by` also drives control flow (`if handled_by == "tool"`, `:149`, `:192`). At base, the router read its one decision value from lib (`CODEX_APPROVAL_ACCEPT_DECISION`).

  Failure:
  - AGENTS.md §"Enums go in `vidbyte/lib/enums/`" says: "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum."
  - D-31 and the `codex_host` module header make lib "the home of every fixed value CodexHost and its collaborators use".
  - The field guide's "Centralize categorical vocabularies" entry (`model-facing-tool-contracts.md:10`) asks for `str, Enum` values rather than scattered literals.
  - D-12 makes log format strings call-site literals, but these values are not format strings. They are a vocabulary that the tests and log readers depend on, so a typo in one branch would silently create a new reason.

  Smallest fix:
  - Add `CodexServerRequestHandler` (tool, default, handler) and `CodexServerRequestFallback` (the five reasons) to `lib/enums/codex.py`, export them, and have `_reason` return the enum. Log `.value` so the INV-8 strings stay byte-identical.
  - The answer labels can be a third enum, or `CODEX_HOST_*` constants.
  - S2 must add the two names to `ENUMS_CODEX_ORDER` (`test_codex_host_packaging.py:79`, pinned at `:242`).
  - If that pin must not move in this slice, `CODEX_HOST_SERVER_REQUEST_*` constants in `lib/constants/codex_host.py` still satisfy D-31 and need no test change.

  Spec IDs: INV-8, INV-47, D-31, D-12, NFR-11

R-V4 [Major] [field-guide strict-config-dataclasses / INV-48] vidbyte/lib/dataclasses/codex_host_inputs.py:364 — run_codex_goal's turn-field refusal does not name run_codex_goal

  Evidence:
  - `CodexGoalRunRequest.__post_init__` calls `_reject_goal_fields(self.request)` (`:364`), which raises `CODEX_HOST_GOAL_FIELD_MESSAGE.format(name=name)` (`lib/dataclasses/codex_host.py:285`).
  - A caller of `run_codex_goal(objective, request=CodexSpawnRequest(turn=…))` therefore reads "Codex spawn request goal does not use the field turn, …". That request has no goal of its own, and `CodexGoalRunRequest` refuses one.
  - The record module's own header (`codex_host_inputs.py:5`) says "A field name in a message starts with the function the caller called."
  - Spec §8.5 had `_reject_goal_fields(owner: str, request)` (spec.md:795). S3 dropped `owner` because the §9.3 text has only a `{name}` slot (spec.md:1620, 1026).

  Failure:
  - INV-48 (spec.md:475) says "A refusal names `"<method> <field>"`".
  - The field guide (`strict-config-dataclasses.md:75`) says "field names in messages written as `"<method> <field>"`".
  - The spec contradicts itself: the §9.3 message text against INV-48. The implementation resolved this toward the text and against the invariant, and against its own header.
  - This is rated Major, not Blocker, because the §9.3 text is spec-fixed and S2's tests pin it (`codex_host_support.py:246`, `test_codex_host_hardening_contract.py:286`, `test_codex_host_turn_settings.py:59`).

  Smallest fix:
  - Restore spec §8.5's `owner` argument and give the message an `{owner}` slot. `CodexSpawnRequest` passes "Codex spawn request goal"; `CodexGoalRunRequest` passes "run_codex_goal request".
  - S1 amends spec.md:1026, and S2 updates `GOAL_FIELD_MESSAGE`. The tool tests check with `assertIn` and keep passing if the tail is unchanged.

  Spec IDs: INV-48, INV-34, §8.5, §9.3, D-33

R-V5 [Minor] [house style: enums and config over literals] vidbyte/lib/constants/codex_host.py:82 — The default-answer table mixes enum values with bare literals

  Evidence:
  - The three routed keys use `CodexServerRequestKind.X.value`, but their decision is the literal `"decline"`, while `CodexApprovalDecision.DECLINE` exists and the router uses it (`connection.py:226`).
  - The other four method keys (`"item/permissions/requestApproval"`, `"mcpServer/elicitation/request"`, `"applyPatchApproval"`, `"execCommandApproval"`) and `"denied"` are bare strings. Every other wire method in lib is a named `CODEX_*_METHOD` constant.

  Failure:
  - Mainly readability: a reader cannot tell which values are tied to a vocabulary.
  - A rename of the `CodexApprovalDecision.DECLINE` value would not reach this table.

  Smallest fix: Write `CodexApprovalDecision.DECLINE.value` in the two routed rows. The values are unchanged, so the AC-40 dict comparison still passes.

  Spec IDs: D-3, D-31, INV-15

R-V6 [Minor] [house style: about 40–50 lines; obvious over clever] vidbyte/harnesses/native/codex/connection.py:132 — The router's handle is 63 lines, and its locked section is a chain of ternaries shaped by lint

  Evidence:
  - It is the only function over 50 lines in the changed modules (AST scan).
  - `:160-163` chains four conditional expressions (`handler = None if self._closed else …`, `request = None if handler is None else …`, `coroutine = None if handler is None or request is None else cast(…)`, `future = None if coroutine is None else …`). `request is None` cannot hold once `handler` is set, because `from_params` returns a record or raises.
  - S3 records that this shape was chosen to bring S008 and S024 back to baseline (commit `2f31b1fc`).

  Failure: Readability only. A reader has to evaluate four nested conditions to learn "if open, parse then schedule". This is the router that runs on openai-codex's only reader thread, so it is the code most worth reading easily.

  Smallest fix: Under the lock, use one `if not self._closed and self._approval_handler is not None:` block holding three plain statements. Alternatively, move the parse and schedule into one `_start_handler(kind, params) -> tuple[...]` leaf, which keeps S008 and S024 within bounds and keeps the one `try`.

  Spec IDs: INV-17, D-2, §12.4 (spec.md:1324)

R-V7 [Minor] [AGENTS.md §4 / function design] vidbyte/harnesses/native/codex/wire.py:224 — Changed functions grow long positional lists and flag parameters instead of taking the record

  Evidence:
  - `thread_fork(thread_id, last_turn_id, exclude_turns, request, before_turn_id, defer_goal_continuation)` grows from 4 to 6 parameters, two of them booleans.
  - `thread_list(...)` (`wire.py:308`) now takes 8 positional primitives, while `CodexThreadListRequest` holds exactly those fields.
  - `CodexConnection._log_call(operation, method, thread_id, started, exc=None, error=None)` (`connection.py:413`) switches between the success and failure logs on whether two optional arguments are present.

  Failure:
  - AGENTS.md §4 says logic functions take a dataclass "rather than … long lists of primitive arguments", and it applies to "code you change".
  - The house style's function-design rule asks for no boolean or mode-switch flags.
  - This follows #1178's grain (it had 4 and 7 parameters) and spec row 13's prescribed signatures, so it is Minor.

  Smallest fix:
  - Pass `CodexForkRequest` to `thread_fork`, or make the two new parameters keyword-only.
  - Split `_log_call` into `_log_success` and `_log_failure`.
  - Leave `thread_list` for #1178's owner.

  Spec IDs: §12.3 rows 12–13, D-33

R-V8 [Minor] [INV-47 letter] vidbyte/lib/dataclasses/codex_host.py:839 — Nine new refusal texts are inline literals in the record module, and none sets `details["field"]`

  Evidence:
  - `:733`, `:745`, `:753`, `:779`, `:788`, `:797`, `:801`, `:839` and `:841` each write a new message inline, for example "Codex server answer answers go only with the ACCEPT decision.", and pass no `details`.
  - The two `CodexServerAnswer` texts (`:839`, `:841`) reach developers writing an `approval_handler`.
  - The record module had 20 inline messages at base, through its own helpers, so the inline form itself follows its grain.

  Failure:
  - INV-47 places "every new … message text" in `lib.constants.codex_host`.
  - A handler author cannot read the offending field from `details`.
  - Low impact: the router answers a misfit with the default answer anyway (INV-18).

  Smallest fix: Add `details={"field": "answers"}` and `details={"field": "decision"}` to the two `CodexServerAnswer` raises. Move texts into `codex_host.py` constants only if S1 wants INV-47 read literally for lib records.

  Spec IDs: INV-47, INV-18, §9.1 (spec.md:922-925)

## VERIFIED CLAIMS

1. **Lint gate.**
   - The full lint loop ends with `SDK-LINT: PASS`.
   - C021 is CLEAN at 0/0, S008 is RATCHETED at 19/19 and S024 at 25/25. No baseline file is in the diff (no `lint/` path changed).
   - The baseline counts per rule, so I ran `--rule X --all` for 29 ratcheted rules and filtered for the changed files. Only pre-existing findings appear: A001, A003 and A006 on `lib/errors/base.py`, and C006 and C008 on `lib/dataclasses/codex.py`, a file whose only change is one value.
   - No A007, S008, S016, S017, S019, S020 or S024 finding lands in a changed file.
2. **File sizes.**
   - `host.py`: 923 (919 at base). `dataclasses/codex_host.py`: 871 (616 at base). `wire.py`: 797 (705). `connection.py`: 556 (344). `constants/codex_host.py`: 459 (342).
   - `dataclasses/codex.py` is unchanged at 1205, as the "does not grow" rule requires.
   - Every changed test file is at most 817 lines.
3. **Imports and semgrep.**
   - Ruff I001 and the full ruff run over the 23 changed `vidbyte` files: "All checks passed!".
   - Over the whole tree, I001 reports 223 findings. These are pre-existing: the S051 ratchet holds 259, and none is in a changed file.
   - `ruff format --check` would reformat 19 files, but `scripts/run_ci.py` does not run it. It is not a gate.
   - The bundled semgrep-core with `typed-mapping-boundary-policy.yml` reports 0 results and 0 errors on `dataclasses/codex_host.py`, `dataclasses/codex_host_inputs.py`, `constants/codex_host.py`, `connection.py` and `wire.py`.
4. **Tests.**
   - `tests/features/codex_host`: 320 passed, 1 skipped.
   - `test_harness_threads_static_policy.py` passes (the INV-15 and INV-20 field-guide check).
   - `test_harness_threads_surface.py` fails only at `:193` (167 != 120), the inherited failure.
5. **Export lists.**
   - `__all__` is sorted in `constants/codex_host.py` (110 names), `dataclasses/codex_host.py` (26) and `codex_host_inputs.py` (17).
   - In `enums/codex.py`, the disorder (`CodexFailureClass` first) is #1178's, and the three new names are inserted in alphabetical position.
   - `enums/__init__.py:46,50,62,213,217,229` imports and exports all three.
6. **Error construction.**
   - Every new `raise` in `native/` is a `CodexErrorMapper` result, `raise error from None` after mapping, or an input `ConfigurationError` worded `"fork_codex_thread <field> …"` with `details["field"]` (grep of the added lines).
   - Every new `except BaseException` re-raises after cleanup: `host.py` spawn and launch, `thread_helpers.fork` step 8, and the moved `reviews._accept`.
7. **Records, headers and indexes.**
   - The six new records each carry `@dataclass(frozen=True, slots=True)` (`codex_host.py:396`, `:661`, `:673`, `:695`, `:813`, `:825`).
   - The three new source files and the eleven new test files open with a FILE header.
   - `tests/features/codex_host/README.md` indexes every tracked test file.
   - No `__pycache__`, `.pyc` or log file is in the diff.
8. **Call depth.**
   - `CodexTurnEvents.on_event` schedules `complete_review` as its own task (`spawn_task`), so the review completion is an independently scheduled main whose single helper is `_fail`. I accepted it under AGENTS.md §1.
   - `preflight.run`, `fork`, `_end_lost_turn` and `reviews.start` each call only one level of their own helpers.
9. **Commits.**
   - Every commit has a conventional `type(scope):` subject, and the code commits cite §12.3 row IDs and INV/AC IDs.
   - All commits except the first pipeline commit `70c76342` carry the Co-Authored-By trailer.
   - The spec docs under `docs/spec/` have precedent: #1055 (`6f5a7310`) merged its own spec folder.

## COMMANDS RUN

```
V=".../scratchpad/venv-codex163/Scripts/python.exe"
git rev-parse HEAD; git log --oneline c9150d63..HEAD; git diff --stat c9150d63 HEAD
git diff --stat|--name-only origin/ai/resolve-pr-1055-comments...c9150d63
git diff origin/ai/resolve-pr-1055-comments...c9150d63 -- <each source file>
git show origin/ai/resolve-pr-1055-comments:<file> | wc -l      # base sizes
"$V" lint/run.py                                    # -> SDK-LINT: PASS
"$V" lint/run.py --rule <A001..S064> --all | grep <changed files>   # 29 rules
"$V" lint/run.py --rule S020 --all
"$V" -m ruff check <23 changed vidbyte files> --config lint/ruff.toml --select I001 --no-cache   # All checks passed!
"$V" -m ruff check <same> --config lint/ruff.toml --no-cache                                  # All checks passed!
"$V" -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache                   # 223, pre-existing
"$V" -m ruff format --check <same> --config lint/ruff.toml --no-cache                         # informational
git diff -U0 ... | awk '<added comment lines longer than 72>'     # comment-format.md Check
git show origin/...:<file> | awk 'length>72 && /^\s*#/' | wc -l  # base comparison
semgrep-core.exe -rules .semgrep/typed-mapping-boundary-policy.yml -lang python -json <file>   # x5
PYTHONPATH=$(pwd) "$V" -m pytest -q -p no:cacheprovider tests/features/codex_host            # 320 passed, 1 skipped
PYTHONPATH=$(pwd) "$V" -m pytest -q -p no:cacheprovider tests/features/harness_threads/test_harness_threads_static_policy.py tests/features/harness_threads/test_harness_threads_surface.py   # 1 inherited failure
"$V" -I -c '<ast scan: functions over 50 lines>' <11 changed modules>
git log --format='%h %s%n%b' origin/ai/resolve-pr-1055-comments..c9150d63; git log --oneline origin/main -12
```

Field-guide entries read: `comment-format.md`, `blocking-lint-invariants.md` (§61, §68), `strict-config-dataclasses.md` (§32, §61, §75), `diagnostic-context.md`, `class-bound-helpers.md` (§3, §38–§59), `provider-api-contracts.md`, `model-facing-tool-contracts.md` (§10), `review-scope.md`, `agents-md-map.md`.

The only scratch output outside the worktree was `/tmp/x_all.txt` and `scratchpad/sg_out.json`. Nothing in the worktree was changed except this report.
