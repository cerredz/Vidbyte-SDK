LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the placement, export and shared-file rules are followed exactly, but the new code breaks three binding conventions (72-column comments, one-level call chains, enums for closed sets) and hides seven A002 findings behind baseline slack; every fix is local and fits the budget.

Reviewed: `git diff origin/main...099fac83` (S3_HEAD; local HEAD 3ebefd11 adds only pipeline.md). All line numbers refer to 099fac83.

WHAT THE IMPLEMENTATION GETS RIGHT

- **Shared-file discipline holds byte for byte.** The REPO_MAP.md and `vidbyte/harnesses/README.md` insertions are request.md §C's fenced texts, at the named spots. The native `__init__` blob hashes to `0374a2c8…942f497a`. Export lists in `lib/enums/__init__.py`, `lib/enums/codex.py`, `lib/constants/codex.py` and `tools/builtins/__init__.py` keep main's order, with entries only inserted. Deletions occur in only two files: `agents/codex/tools.py` (the extraction) and `lib/errors/base.py` (the `next_step` signature, with the literal DIAGNOSTIC_FIELDS kept).
- **Placement follows AGENTS.md.** The 13 enums are in `lib/enums/codex.py`. The 15 frozen, slotted records are in the new `lib/dataclasses/codex_host.py`, with a sorted list-literal `__all__`. Constants are in `lib/constants/codex.py`, and the FailureCode block sits right after `CODEX_RUN_OPTION_UNSUPPORTED`. No `types.py`, `models.py` or `constants.py` was added beside the feature.
- **The model-facing vocabularies come from enums.** Tool names are `CodexHostOperation` values (readiness.py:24-26, live.py:34-38). Schema `enum` choices are built from the enum members (delegation.py:39-40), and `_resolve_choice` maps wire values back to members. Descriptions live in descriptions.py, and S025 passes. Raw calls go through `request_with_retry_on_overload`, so S012 holds.
- **Hygiene is clean.** Every new `.py` file has the A001 header, and `--all` lists none of them. `vidbyte/` has no `noqa`, `type: ignore` or `nosemgrep`. openai-codex is imported at runtime only in connection, wire, turns and `CodexErrorMapper.from_exception`; host and preflight import it under TYPE_CHECKING only. The 45 commits are one per §12.3 row, each cites its W-, FR- and AC- IDs, and each carries Co-Authored-By.

FINDINGS

R-V1 [Blocker] [comment format] vidbyte/lib/dataclasses/codex_host.py:66 — 172 of the 596 added comment lines are wider than 72 columns
  Evidence: `git diff origin/main...099fac83 -- vidbyte | grep -E '^\+\s*#' | awk 'length($0) > 73' | wc -l` prints 172 (596 added comment lines).
    - Widths: 148 lines are 73–76 columns, 18 are 77–88 and 6 are over 88.
    - Widest lines: codex_host.py:66 (119 cols, "# Accepts None or a finite number of seconds above the exclusive minimum; bool, NaN and infinity are refused first."), codex_host.py:209 (102), agents/codex/tools.py:70 (98, "# Checks every tool name against the app-server's naming rules and the MCP-reserved names."), codex_host.py:58 (97), :167 (94) and :158 (93).
    - Per file: host.py 41, wire.py 26, connection.py 26, errors.py 18, codex_host.py 17, turns.py 17, preflight.py 9, _base.py 6, threads.py 3, delegation.py 3, constants/codex.py 3, agents/codex/tools.py 3.
  Failure: field guide `comment-format.md` says "Wrap every comment line at 72 columns, counting the indent … A single-line comment that would pass 72 columns becomes a wrapped block too", and that awk command is its Check.
    - The owner rejected this on PR #690: "if a comment is a multi line comment, then format it correctly".
    - The spec repeats the rule at spec.md:1331 ("Multi-line comments wrap at 72 columns") and spec.md:1097.
    - Most blocks appear to be wrapped at 72 columns counted from the `#`, not from column 1.
    - A reviewer would write: "Rewrap these comments to 72 columns, counting the indent."
  Smallest fix: rewrap the 172 lines. Only comments change. Keep each `# @intent` line first and within A002's 20-line window. Then run the awk check again (it should print nothing) and run `lint/run.py --rule A002`.
  Spec IDs: spec.md:1331 checklist; field guide comment-format.

R-V2 [Blocker] [call-chain depth] vidbyte/harnesses/native/codex/host.py:5 — the header says "a flat list of leaf helpers", but CodexHost helpers call helpers two and three levels deep
  Evidence: host.py:5 says "Each public method is one narrated main function over a flat list of leaf helpers". A scan of the direct self-calls finds these chains:
    - `start_codex_review` (:455) → `_accept_review` (:619) → `_read_back` (:629), `_stopped` (:629, :631) and `_stop` (:645) → `_spawn_task` (:698).
    - `spawn_codex_thread`, `continue_codex_thread` and `launch_codex_subagents` → `_accept` (:566) → `_stopped` (:572).
    - `launch_codex_subagents` (:425) → `_stop` → `_spawn_task`.
    - `spawn_codex_thread` (:243) → `_start_goal` (:536) → `_stopped` (:553).
    - `_complete_review` (:662) → `_read_back`.
    - `_read_back` (:653) repeats `CodexPreflight.require_thread`'s `thread/read` call (preflight.py:159).
    - Outside the host: wire.py `turn_snapshot`/`goal_snapshot` → `_snapshot` (:543) → `final_answer` (:129).
  Failure: AGENTS.md:21-25 (principle 1) says "a function may call another of its own functions, but that second function should not call a third … lift that call up into the main function".
    - The spec checklist says "Helpers call no helpers of their own" (spec.md:1331), and house style allows "at most one hop of same-class delegation".
    - The header claims the opposite of what the code does, so the next agent will rely on a false invariant.
    - A reviewer would write: "Keep call chains one level deep. The header is wrong."
  Smallest fix (in budget, no new class or file): the depth comes mostly from three shared leaves, and a call to another class does not count (AGENTS.md:23).
    - Move `_spawn_task` and its task set onto CodexConnection as `spawn(work)`. CodexConnection already owns the loop, `begin_close()` and `is_dead()`.
    - Replace `_stopped` with a `CodexConnection.stopped()` predicate. The failed-open path at host.py:130 must then also call `begin_close()`.
    - Replace `_read_back` with `self._preflight.require_thread(operation, thread_id, include_turns=True)` under `suppress(CodexAgentError)` in its two callers. This also removes the duplicate `thread/read` call.
    - Split `_accept_review` (see R-V7).
    - Then make line 5 true.
  Spec IDs: AGENTS.md principle 1; spec.md:1331.

R-V3 [Blocker] [enum typing] vidbyte/harnesses/native/codex/turns.py:197 — closed vocabularies are stored, passed and keyed as plain `str` although their enums exist
  Evidence: three vocabularies travel as strings.
    - **Goal status.** turns.py:197 sets `self.status = ""`, then :211 `self.status = payload.goal.status.value` and :212 `self.status != CodexGoalStatus.ACTIVE.value`. wire.py:536 and :539 compare `rule.status == CodexGoalStatus.COMPLETE.value`, and wire.py:519 rebuilds `CodexGoalStatus(rule.status)`. errors.py:148 declares `goal_problem(cls, status: str)` over errors.py:39-42 `GOAL_PROBLEM_CODES = {CodexGoalStatus.BUDGET_LIMITED.value: …}`. constants/codex.py:404-406 defines `CODEX_GOAL_TERMINAL_STATUSES = frozenset({"paused", "blocked", "usageLimited", "budgetLimited", "complete"})`, a literal set standing in for CodexGoalStatus (enums/codex.py:212-221).
    - **Sandbox readiness.** connection.py:187 and :192 return `-> str` (`""` at :199, `response.status.value` at :200), and preflight.py:129 returns `-> str` (`""` at :133). wire.py:370 `sandbox_problem(status: str)` and :378 `readiness(..., sandbox_status: str)` each rebuild `CodexSandboxReadiness(...)` (:373, :390). The `""` they pass is `CodexSandboxReadiness.NOT_CHECKED` (enums/codex.py:139).
    - **Approval mode.** wire.py:301 declares `_approvals(..., default_mode: str)`, fed by `CODEX_HOST_DEFAULT_APPROVAL_MODE = "auto_review"` (constants:352).
  Failure: AGENTS.md:63 is a Placement Rule, binding for all new code: "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`". AGENTS.md principle 4 says the same.
    - Field guide `model-facing-tool-contracts.md` ("Centralize categorical vocabularies") records that the owner has flagged literal sets standing in for a vocabulary twice.
    - A reviewer would write: "status is a CodexGoalStatus and the sandbox status is a CodexSandboxReadiness. Convert each once, at the wire."
  Smallest fix (in budget): every enum already exists, and constants/codex.py already imports from lib/enums/codex.
    - Convert once at the wire edge: `CodexGoalStatus(payload.goal.status.value)` at turns.py:211, and `CodexSandboxReadiness(response.status.value)` or `CodexSandboxReadiness.NOT_CHECKED` in connection.py and preflight.py.
    - Type with the enums: `CodexGoalFinishRule.status`, `goal_problem(status)`, `sandbox_status`, `sandbox_problem(status)`, `readiness(sandbox_status)` and `_approvals(default_mode)`.
    - Key GOAL_PROBLEM_CODES and CODEX_GOAL_TERMINAL_STATUSES by CodexGoalStatus members. `NONE` and `NOT_CHECKED` are both `""`, so the sentinels keep their values.
    - CODEX_APPROVAL_MODE_WIRE, CODEX_SANDBOX_THREAD_MODE and CODEX_SANDBOX_TURN_POLICY are also keyed by literal enum values (constants:368-383), while the same file keys CODEX_NEXT_STEPS by `FailureCode.X.value`. spec.md:1037-1040 fixes these values, and str-enum members keep both the values and equality. Re-keying them is therefore optional; leave it if the spec author reads the table as fixing the spelling.
  Spec IDs: AGENTS.md:63; spec.md:1037-1040 (values unchanged).

R-V4 [Major] [hardcoded strings] vidbyte/harnesses/native/codex/host.py:509 — 16 JSON-RPC method names are inline literals, and the existing CODEX_THREAD_START_METHOD is ignored
  Evidence: host.py:509 calls `connection.call(operation, "thread/start", ...)`, although `CODEX_THREAD_START_METHOD = "thread/start"` already exists on main (constants/codex.py:282, used at agents/codex/tools.py:115).
    - Other literals: host.py:208 "account/read", :268 "thread/resume", :301 "thread/fork", :308 and :516 "thread/name/set", :326 "thread/list", :374 "turn/steer", :533 "turn/start", :560 "cancel_goal_operation", :653 "thread/read"; preflight.py:97 "account/read" and :159 "thread/read"; connection.py:153 "initialize", :261 "cancel_goal_operation" and :263 "turn/interrupt".
    - The same PR adds CODEX_RATE_LIMITS_READ_METHOD, CODEX_REVIEW_START_METHOD, CODEX_GOAL_SET_METHOD, CODEX_MODEL_LIST_METHOD and CODEX_SANDBOX_READINESS_METHOD (constants:354-358) and uses them (host.py:217, :449-451, :554-555). Two conventions now sit side by side.
    - errors.py:29-32 keeps private copies (`THREAD_READ_METHOD = "thread/read"`, `THREAD_FORK_METHOD = "thread/fork"`). `_rpc_code` (errors.py:97-100) picks session_not_found or fork_failed only when the literal passed at host.py:301, host.py:653 or preflight.py:159 is spelled identically.
  Failure: house style says "No hardcoded meaningful strings", and this repo has already chosen a constant for this exact name. AGENTS.md principle 5 asks for one source per shared fact.
    - A typo at one call site would silently turn `codex.session_not_found` into `codex.api_error` (D-13).
    - A reviewer would write: "Use the constants. CODEX_THREAD_START_METHOD already exists."
  Smallest fix: add the missing method names to `lib/constants/codex.py`, beside CODEX_REVIEW_START_METHOD. These are constants only, with insert-only `__all__` additions; no file, class or record is added. Use them at all 16 sites, reuse CODEX_THREAD_START_METHOD, and import them in errors.py in place of its local copies.
  Spec IDs: D-13.

R-V5 [Major] [lint evasion] vidbyte/harnesses/native/codex/host.py:346 — two argument checks are reshaped so that C002 cannot see them
  Evidence: host.py:344-349 has the comment "# A wait takes exactly the timeouts a turn does, so the spawn request's own seconds rule checks it." and then `try: CodexSpawnRequest(timeout_seconds=timeout_seconds) except ConfigurationError: raise ConfigurationError(BAD_TIMEOUT_MESSAGE) from None`.
    - host.py:495 checks `limit is not None and (type(limit) is not int or limit < CODEX_HOST_MIN_LIVE_TURNS)`.
    - S3-implementer.md:87-89 and spec.md §17 "Implementation deviations (S3)" say both shapes exist to avoid C002. S3 added that spec text in commit 79eadcf4, so it is not an S1 decision.
  Failure: field guide `blocking-lint-invariants.md` (C002 entry) says "Never add a second isinstance(x, bool) guard for a field name that is already guarded".
    - `type(limit) is not int` is that second guard with the detector's pattern taken out. C002's own header says it "Enforces one validation owner".
    - House style forbids adding a suppression to get green, and reshaping code to dodge a rule works as one.
    - Building a whole CodexSpawnRequest to borrow one field rule hides the rule from the reader. The `from None` also drops which check failed.
    - A reviewer would write: "Don't shape the code around the linter. Call the validator that already owns the rule."
  Smallest fix (in budget): call the two validators that already own these rules in `lib/dataclasses/codex_host.py`.
    - Use `_reject_bad_seconds("wait_codex_turn", "timeout_seconds", timeout_seconds)` (:65) and `_reject_small_int("launch_codex_subagents", "limit", limit, CODEX_HOST_MIN_LIVE_TURNS)` (:57). This is the same private-import pattern spec row 6 set for `_require_text` (spec.md:1250).
    - Their guard identity is the generic `value`, which C002 skips, so no new C002 finding appears.
    - Drop BAD_TIMEOUT_MESSAGE and LAUNCH_LIMIT_MESSAGE (host.py:92, :94). The tests assert only the ConfigurationError type (test_codex_host_turns.py:215-218; test_codex_host_threads.py:135-136).
    - Then run `lint/run.py --rule C002`.
    - A public shared validator in C008's named home, `vidbyte/lib/dataclasses/validation.py`, would be a 19th file and needs the spec author.
  Spec IDs: spec.md §17 deviations (S3); field guide C002 lesson.

R-V6 [Major] [lint ratchet] vidbyte/harnesses/native/codex/host.py:311 — seven new A002 findings in new files pass only because A002's baseline has 96 findings of slack
  Evidence: `lint/run.py --all --format json`, filtered to this PR's files, shows A002 (`categories: external boundaries`) at:
    - host.py:311 `list_codex_threads`
    - oneshot.py:70 `list_codex_threads`
    - preflight.py:163 `reject_unusable_fields`
    - lib/dataclasses/codex_host.py:384 `__post_init__`
    - tools/builtins/codex/threads.py:107 `_perform`, :202 `_continue_defaults` and :277 `_perform`
    - The gate's summary line reads "A002 intent-comments 607 703 IMPROVED". S3-implementer.md:79 claims "The `@intent` lines satisfy A002".
  Failure: the spec.md:1297 checklist requires that every function whose identifiers contain request (and the other tokens) carries `# @intent <name>`.
    - The ratchet is meant to hold new code to the rule even where old code is baselined (field guide blocking-lint-invariants, A003 entry).
    - Once someone lowers the baseline, as the gate itself suggests ("Lower it with: … --update-baseline"), these seven become permanent debt.
    - A reviewer would write: "Your new functions are missing their intent markers."
  Smallest fix: add a real `# @intent <name>` block, stating the why rather than narrating the code, within 20 lines of each of the seven `def`s. Afterwards `lint/run.py --rule A002 --all` should list nothing under `native/codex/`, `builtins/codex/` or `codex_host.py`.
  Spec IDs: spec.md:1297; S3 claim (did not hold).

R-V7 [Minor] [function design] vidbyte/harnesses/native/codex/host.py:619 — internal boolean flags switch behavior inside a single function
  Evidence:
    - host.py:619 `_accept_review(..., *, late: bool)` returns instead of raising (:634-636) and adds a stop (:644-645).
    - connection.py:246-259 `interrupt(..., cleanup: bool = False, quiet: bool = False)` uses `with suppress(*((CodexAgentError,) if quiet else ())):`.
    - Other internal flags: host.py:457 `_guard(operation, *, talks: bool)`, errors.py:94 `_rpc_code(method, *, malformed: bool, refused: bool)`, preflight.py:91 `run(..., check_model: bool)`, turns.py:236 `CodexTurnWatcher(..., until_completed: bool)` and _base.py:201 `_json(record, *, without_items: bool)`.
    - host.py:653 passes a bare positional `True` (`connection.client.thread_read, handle.thread_id, True`).
  Failure: the function_design deep-dive says "Do not use boolean or string flag arguments to switch between two behaviors inside one function", and the house-style table says "no boolean flags". The public §8.5 flags (`include_hidden`, `archived`, `include_turns`, `exclude_turns`) are settled and excluded here.
  Smallest fix: split the two flags that change control flow.
    - Split `_accept_review` into an accept path and a late-adopt path.
    - Split `interrupt` into a raising call and a quiet one, or let `_stop` wrap the call in `suppress`.
    - Name the positional `True` with a module constant, because `CodexConnection.call` forwards only positional arguments.
    - Leave the remaining flags as follow-ups.
  Spec IDs: n/a.

R-V8 [Minor] [intent comments] vidbyte/harnesses/native/codex/wire.py:429 — several `# @intent` tags name no rule and explain no why
  Evidence:
    - wire.py:429-431 reads "# @intent thread-records-name-the-codex-provider" / "# A thread and the turns Codex included, each summarized by its" / "# status, final answer and error message.", and the body never mentions the provider.
    - wire.py:284 puts "@intent one-settings-record-per-request" on a one-to-one settings mapper.
    - wire.py:296-297 reads "@intent explicit-approvals-are-sent-as-given" / "The caller's explicit approval fields, by wire field name.".
    - _base.py:202 puts "@intent tool-output-is-the-record-json" on a serializer.
    - host.py:249-250 reads "@intent continue-only-an-idle-thread-that-exists" / "Start one more turn on an existing thread, by id.".
  Failure: the intent_based_commenting deep-dive says "Do not tag … one-to-one data mappers", "Do not write vague intent" and "Do not write comments that merely narrate the implementation". A002's own header rejects "empty intent markers". These read as tags written to satisfy A002's tokens (request, provider).
  Smallest fix: keep each tag, since A002 requires it on these functions, and give it its why in a sentence or two. For example, wire.py:429 carries the provider because D-19 refuses to price a non-OpenAI provider at OpenAI rates.
  Spec IDs: D-19 (for wire.py:429).

R-V9 [Minor] [shared logic] vidbyte/lib/dataclasses/codex_host.py:163 — the rule that a prompt carries no context is written twice, with two different messages
  Evidence: codex_host.py:163-164 checks `if self.prompt.context_items or self.prompt.context_manager is not None or self.prompt.context_placements:` and raises "Codex spawn request prompt cannot carry context_items, a context_manager or context_placements.". wire.py:239-240 runs the same three-field test and raises "A Codex prompt must be a str or a CodexRunInput without context_items, a context_manager or context_placements.".
  Failure: AGENTS.md principle 5 says to "write the logic once … have every caller use that helper". A fourth context field added to CodexRunInput would have to be remembered in both places.
  Smallest fix: add one `_reject_*` module function in codex_host.py, named per spec §9.1. Call it from `CodexSpawnRequest`'s prompt check and from `CodexParamsTranslator.input_items`.
  Spec IDs: spec §9.1 (helper naming).

R-V10 [Minor] [readability] vidbyte/harnesses/native/codex/turns.py:352 — records are built from unlabeled positional arguments, and one key is picked by a chained conditional
  Evidence:
    - turns.py:352 builds `CodexRunResult(thread_id, turn.handle.turn_id, snapshot.status.value, None, None, delta, (), last_usage=delta, usage_available=True)`.
    - host.py:447 calls `self._responses.pricing(thread.model or "", thread.model_provider, "")`.
    - errors.py:159 sets `key = info if isinstance(info, str) else next(iter(info), "") if isinstance(info, dict) else ""`.
  Failure: house style says "Optimize for reading. Obvious over clever", and the function_design deep-dive allows at most three positional arguments. A reader cannot tell what the two `None`s, the `()` and the trailing `""` mean.
  Smallest fix: use keyword arguments at turns.py:352 and host.py:447, and split errors.py:159 into an `if`/`elif`.
  Spec IDs: n/a.

VERIFIED CLAIMS

- Held: the gate passes (`lint/run.py` ends `SDK-LINT: PASS`).
- Did not hold: S3-implementer.md:79, "The `@intent` lines satisfy A002". `--all` lists seven A002 findings in new files (R-V6).
- Did not hold: host.py:5, "Each public method is one narrated main function over a flat list of leaf helpers" (R-V2).
- Held: every new `.py` file has the seven-field A001 header. A001 `--all` lists only the pre-existing `tools/builtins/__init__.py` and `tools/toolsets/__init__.py`.
- Held: the native `__init__` blob SHA-256 is `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
- Held: the REPO_MAP.md and harnesses README texts equal request.md §C's fenced blocks, byte for byte. They sit after "…both build against.\n\n", before "##### `vidbyte/harnesses/stores/`", and after the `serialization.py` bullet.
- Held: export lists changed by insertion only. Main's order is kept in all four unsorted lists, and `git diff --numstat` shows deletions only in agents/codex/tools.py (2) and lib/errors/base.py (2).
- Held: openai-codex is imported at runtime only in connection, wire, turns and `errors.from_exception` (errors.py:69); host.py:65-71 and preflight.py:30 import it under TYPE_CHECKING.
- Held: `vidbyte/` has no `# noqa`, `type: ignore` or `nosemgrep`. The test fakes have two coded ignores (codex_host_fakes.py:343, :500).
- Held: the largest file is host.py at 733 lines, and no function exceeds 40 lines.
- Held: 101 of 101 codex_host tests pass, and semgrep reports 0 findings.
- New finding the gate does not show: C011 counts 2 against a baseline of 2, and one of the two is new, at turns.py:320 `CodexTurnRegistry._add:UsageTracker()` (kind `usage-orphan-tracker`). It follows from D-19 ("A UsageTracker per thread"), a settled decision, so it is not raised as a finding, but C011 now has no slack. The S062 hit at agents/codex/tools.py:74 is pre-existing code that moved (main:68).
- Did not hold: the briefing lists a field-guide entry "codex-harness-agent", but `field-guide/vidbyte-sdk/` has no such file.

COMMANDS RUN

- `git status --short` (clean); `git log --oneline -3` shows 3ebefd11, 099fac83, 79eadcf4.
- `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py` ends with:
  ```
  A002 IMPROVED 703 -> 607 … S025 IMPROVED 263 -> 261
  SDK-LINT: PASS
  ```
- `… lint/run.py --all --format json` (output in the scratchpad, filtered by path) shows A002 with 7 hits in new files, C011 with 1 hit at turns.py:320, A001 with 0 new-file hits, and S062 with 1 moved line. `exit_code: 0`.
- `git diff origin/main...099fac83 -- vidbyte | grep -E '^\+\s*#' | awk 'length($0) > 73' | wc -l` prints `172`, out of 596 added comment lines.
- `PATH="/c/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1/Scripts:$PATH" semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` prints `Ran 1 rule on 911 files: 0 findings.` The first try used a `C:/` PATH entry, which resolved to the global Python311 semgrep; that crashed with `No module named 'mcp.server.fastmcp'` (mcp 2.x).
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/codex_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` prints `101 passed in 7.51s`.
- `git show 099fac83:vidbyte/harnesses/native/__init__.py | sha256sum` prints `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
- `git diff --numstat origin/main...099fac83 -- vidbyte REPO_MAP.md | awk '$2>0'` prints `14 2 vidbyte/agents/codex/tools.py` and `3 2 vidbyte/lib/errors/base.py`.
- Inline-Python AST scans (via `git show`) found the self-call chains in R-V2, the flags in R-V7, function lengths (none over 40) and `__all__` order (old order kept). An inline-Python byte comparison checked request.md §C against REPO_MAP.md and the harnesses README (True / True).
- `git log --format='%h %an | %s' origin/main..099fac83` shows 45 commits, one per row with IDs cited; `grep -c Co-Authored-By` prints 45.
- `git grep -n -E "\((D|INV|EC)-[0-9]+" origin/main -- vidbyte` found 1 hit (bash.py). Spec-ID references in source headers already have precedent on main, so they are not raised.
