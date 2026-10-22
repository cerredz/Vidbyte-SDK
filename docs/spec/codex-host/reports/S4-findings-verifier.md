# S4 · Findings verifier report — codex-host

Stage: S4 findings verifier · Diff: `git diff origin/main...099fac83` · Local HEAD 3ebefd11 (adds only `pipeline.md`; `git diff --quiet 099fac83 HEAD -- vidbyte tests` exits 0) · Output: `docs/spec/codex-host/review.md` · No commits, no source edits, no live `codex`.

Environment for every command below:

```
W=C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host
PY=C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host/Scripts/python.exe   # Python 3.11, openai-codex 0.162.1
```

Probes are inline `PYTHONPATH=$W $PY -P - <<'EOF' … EOF` heredocs. Each subclasses `tests.features.codex_host.codex_host_support.HostTestCase` over the in-memory fake and runs with `unittest.main(argv=["x"], exit=False)`. Nothing is written to disk.

## 1. Merge map

| Original ID(s) | Lens | Merged ID | Severity (proposed → final) | Disposition |
|---|---|---|---|---|
| R-E1 | engineering | R-1 | Blocker → Blocker | CONFIRMED |
| R-E2 | engineering | R-2 | Blocker → Blocker | CONFIRMED |
| R-V3 | conventions | R-3 | Blocker → Blocker | CONFIRMED (the wire-table re-keying is trimmed as optional) |
| R-V2 | conventions | R-4 | Blocker → Blocker | CONFIRMED (the wire.py module-function chain is trimmed; the fix is extended to move `_stop`) |
| R-V1 | conventions | R-5 | Blocker → Blocker | CONFIRMED |
| R-C1 + R-E3 | conformance + engineering | R-6 | Major + Major → Major | CONFIRMED (same root cause: host.py:421 catches only `CodexAgentError`) |
| R-E4 | engineering | R-7 | Major → Major | CONFIRMED |
| R-V5 | conventions | R-8 | Major → Major | CONFIRMED, plus a deviation-entry |
| R-V6 | conventions | R-9 | Major → Major | CONFIRMED |
| R-E5 | engineering | R-10 | Major → Major | CONFIRMED |
| R-V4 | conventions | R-11 | Major → Major | CONFIRMED |
| R-E7 | engineering | R-12 (+ R-25) | Major → Major | CONFIRMED as spec-change + tests-only; the real-validator option is split off as [scope-adding] R-25 |
| R-E6 | engineering | R-13 | Major → Major | CONFIRMED (M1, M2) |
| R-E8 | engineering | R-14 | Major → Major | CONFIRMED (M3) |
| R-C2 | conformance | R-15 | Minor | passed through, trivial |
| R-E11 | engineering | R-16 | Minor | passed through, trivial |
| R-E9 | engineering | R-17 | Minor | passed through, trivial |
| R-V10 | conventions | R-18 | Minor | passed through, trivial |
| R-E13 | engineering | R-19 | Minor | passed through, follow-up |
| R-V9 | conventions | R-20 | Minor | passed through, follow-up |
| R-V8 | conventions | R-21 | Minor | passed through, follow-up |
| R-V7 | conventions | R-22 | Minor | passed through, follow-up |
| R-E10 | engineering | R-23 | Minor | passed through, follow-up |
| R-E12 | engineering | R-24 | Minor | passed through, follow-up (tests-only; M4, M5) |
| (part of R-E7) | engineering | R-25 | Minor [scope-adding] | follow-up, never routed to repair |

Totals:
- Confirmed: 5 Blockers and 9 Majors.
- Minors: 11 (10 passed through plus R-25).
- Refuted: 0. Downgraded: 0.
- Trimmed sub-claims: 3.

Two pairs were not merged:
- **R-E8 with R-6.** R-E8 is a missing test of the tool's slot release on failure; R-6 is a host bug in the cancel path. They are different code with a different fix kind. Their fixes interact (§5).
- **R-E11 with R-E12's M5.** R-E11 is code: a second interrupt is sent. M5 is a test gap: `stop_sent` is never asserted. Both sit on the same line, host.py:385.

## 2. Verification of every Blocker and Major

### R-1 (R-E1): a review cancelled during its D-23 read-back is never watched or interrupted. CONFIRMED.
- **Code.** host.py:627 `client.register_turn_notifications(handle.turn_id)`, then :628 `turn = self._registry.track(…, review=True)`, then :629 `stored = None if self._stopped() else await self._read_back(operation, handle)`. There is no try. `turn.watch` (:643) and the late `self._stop` (:645) come after the await.
- **Probe.** Hold `thread/read` with `lambda p: bool(p.get("includeTurns"))`, cancel the review task, release the hold, then call `server.complete_turn`. Output:
  ```
  caller got CancelledError
  registered snapshot: inProgress
  turn/interrupt sent: 0
  after Codex completed it, wait(1s) -> inProgress
  continue -> codex.session_busy
  ```
- **Spec.**
  - INV-14 says "Its terminal transition is observed even when nobody waits on it", and it fails here.
  - INV-11 says "no accepted turn is left unowned". It is broken in spirit: the review was accepted, but its caller never got the handle and nothing stops it.
  - INV-24 then blocks the thread forever, because `_running[thread_id]` holds a turn that never finishes.
- **Existing guard.** None. `_read_back` suppresses only `CodexAgentError`, and a timeout maps to one, so only cancellation hits this window.
- **Fix check (in memory).** With the read-back wrapped in `try/except BaseException`, running watch, then `_stop(turn, None)`, then re-raise, the same probe printed `FIX R-E1: interrupts 1 status interrupted problem None`. The full pack with the patch applied printed `ran 101 failed 0`.
- **Tier.** Blocker: a wrong and broken result. A completed review reports RUNNING forever, and the thread is unusable until close.

### R-2 (R-E2): a bad `output_schema` fails after `thread/start`. CONFIRMED.
- **Code.**
  - codex_host.py:205-206 accepts any `type` or `Mapping`.
  - The conversion happens in wire.py:222 (`self._schemas.output_schema(...)`) and wire.py:231 (`TurnStartParams…model_dump(mode="json")`).
  - That code is called from `_start_turn` (host.py:531), after `_open_thread` (host.py:240).
  - host.py:232-233 says "Build the input and the tools first, so a bad prompt or tool fails before anything is sent", but the schema is not built there.
- **Probe output.**
  ```
  dataclass type -> vidbyte.lib.errors.base.ConfigurationError | output_schema must be a Pydantic BaseModel subclass or a dict, got 'type'.
  dataclass type thread/start sent: 1 turn/start sent: 0
  mapping with object() -> pydantic_core._pydantic_core.PydanticSerializationError | Unable to serialize unknown type: <class 'object'>
  mapping with object() thread/start sent: 1 turn/start sent: 0
  int type -> vidbyte.lib.errors.base.ConfigurationError | output_schema must be a Pydantic BaseModel subclass or a dict, got 'type'.
  int type thread/start sent: 1 turn/start sent: 0
  ```
- **Spec.**
  - INV-8 says that no pydantic error escapes, and that "When a thread was already created, the message names its thread id". Both are broken.
  - G-2 and the weighted words "return semantic error messages if something goes wrong" are broken by the raw `PydanticSerializationError`.
  - INV-12 is broken for continue, where `thread/resume` is listed as a spending request and goes out before the failure.
- **request.md.** The R2 design the user accepted types the field `type[BaseModel] | Mapping[str, Any] | None` (request.md:304). The spec's §8.5 and §9.1 loosened it to "a type".
- **Tier.** Blocker: a weighted word and INV-8 are broken on realistic input. Records in this repo are dataclasses, so a developer can easily pass a dataclass type.
- **Fix kind.** `code`, by checking the schema at host level before preflight. The record-level alternative is smaller code, but it contradicts §9.1's literal "a type", so it would be a spec-change. Both are listed in review.md.

### R-3 (R-V3): closed vocabularies are typed as `str`. CONFIRMED.
- **Code at 099fac83 (all quoted in review.md):**
  - turns.py:197 and :211;
  - errors.py:39-41 and :148;
  - constants/codex.py:352 and :404-406;
  - connection.py:187-200;
  - preflight.py:129-133;
  - wire.py:301, :370-373 and :378-390.
- **The enums already exist:** `CodexGoalStatus` (enums/codex.py:212, `NONE = ""`), `CodexSandboxReadiness` (:136, `NOT_CHECKED = ""`) and `CodexApprovalMode` (:17, `AUTO_REVIEW = "auto_review"`).
- **Rule.** AGENTS.md:63: "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`." It sits in the Placement Rules, which AGENTS.md calls "binding for all new code".
- **Test impact checked.** test_codex_host_records.py:430 and :447 compare with `assertEqual(getattr(constants, name), value)`. A str-enum member equals its value, so the change keeps them green. The fake's `sandbox_status = "ready"` is wire data, which the fix does not change.
- **Trimmed.** Re-keying the three wire tables (constants:368-383) is optional. §9.3 fixes their keys, and both the reviewer and I treat it as optional.
- **Tier.** Blocker: it contradicts AGENTS.md.

### R-4 (R-V2): call chains are deeper than one level, and the header claims otherwise. CONFIRMED.
- **AST scan.** An inline script parses `git show 099fac83:<path>` and follows `ast.Call` nodes whose function is `self.<method>` inside the same class. Output:
  ```
  host.py spawn_codex_thread -> _start_goal -> _stopped
  host.py continue_codex_thread -> _accept -> _stopped
  host.py launch_codex_subagents -> _stop -> _spawn_task
  host.py start_codex_review -> _accept_review -> _stop -> _spawn_task
  host.py _adopt_late_turn -> _stop -> _spawn_task
  host.py _adopt_late_goal -> _stop -> _spawn_task
  host.py _adopt_late_review -> _accept_review -> _stop -> _spawn_task
  host.py _accept_review -> _stop -> _spawn_task
  host.py _on_turn_event -> _complete_review -> _read_back
  ```
  No other harness, tool-base or record class has a chain of two or more. My first scan also counted callback references such as `partial(self._x)`; I discarded it because it inflated the depths.
- **Rule.** AGENTS.md:21-25 (principle 1) and spec.md:1331. host.py:5 claims "a flat list of leaf helpers".
- **Fix adjustment.** The reviewer's fix moves `_spawn_task` and `_stopped` and replaces `_read_back`. That still leaves `start_codex_review -> _accept_review -> _stop` two deep. So `_stop` must also leave `CodexHost`: onto `CodexConnection`, or with its state flip onto `CodexLiveTurn`. Otherwise `_accept_review` must be split so that its callers make the stop call.
- **INV-11 check.** `connection.start`, `_hand_over` and `_post_late` are unchanged. The late callbacks keep calling the same logic, only on another object. No class is added.
- **Trimmed.** wire.py's `turn_snapshot -> _snapshot -> final_answer`: `final_answer` is a module function (wire.py:129), not a same-class helper.
- **Tier.** Blocker: it contradicts AGENTS.md, and the header states a false invariant that the next agent will rely on.

### R-5 (R-V1): 172 added comment lines are wider than 72 columns. CONFIRMED.
- **Measurements.**
  ```
  git diff origin/main...099fac83 -- vidbyte | grep -E '^\+\s*#' | wc -l                                  -> 596
  git diff origin/main...099fac83 -- vidbyte | grep -E '^\+\s*#' | awk 'length($0) > 73' | wc -l         -> 172
  … | sed 's/^+//' | awk 'length($0) > 72 {…bucket…}'                                                    -> 73-76: 148 77-88: 18 >88: 6
  per file (diff-only): host 41, wire 26, connection 26, errors 18, codex_host 17, turns 17, preflight 9, _base 6, threads 3, delegation 3, constants 3, agents/codex/tools 3
  widest: codex_host.py:66 (119), :209 (102), :58 (97)
  ```
- **Written rule.** The rule is written down. Field guide `comment-format.md:3-7` says "Wrap every comment line at 72 columns, counting the indent", and gives the awk Check. Spec.md:1331 says "Multi-line comments wrap at 72 columns". AGENTS.md itself does not state 72 columns.
- **Shared files.** None of the 12 files is a request.md §C shared file. The 3 lines in agents/codex/tools.py are this PR's row-7 additions.
- **Tier.** Blocker: it contradicts a field-guide lesson that records the owner's own rejection (PR #690).

### R-6 (R-C1 + R-E3): a cancelled launch leaves its started turns running. CONFIRMED.
- **Code.** host.py:421 has `except CodexAgentError as exc:`, so a `CancelledError` at :417 or :418 skips the `_stop` loop. In delegation.py:70-74 the slots are released in `finally`, and `own` runs only on success.
- **Host-level probe** (hold the 2nd `thread/start` through a counting predicate, then cancel):
  ```
  host: turn/start so far: 1
  host: launch cancelled
  host: turn/interrupt after 1s: 0
  host: thr-1 turn-1 inProgress
  ```
- **Tool-level probe** (`CodexHostTools(host, max_live_turns=2)`):
  ```
  tools: launch tool call cancelled
  tools: spawn 0 ToolStatus.SUCCESS
  tools: spawn 1 ToolStatus.SUCCESS
  tools: turns inProgress on fake: 3 with max_live_turns=2; interrupts: 0
  ```
- **Fix check (in memory).** With `except BaseException`, stop every started turn and re-raise anything that is not a `CodexAgentError`. Output: `FIX R-C1/R-E3: interrupts 1 [('thr-1', 'interrupted')]`, and the pack ran 101 with 0 failures.
- **Tier.** Major, as both reviewers proposed. The turns are watched and finalize, so the thread is not blocked, unlike R-1. But they run unowned and over the cap until they end.

### R-7 (R-E4): a cancelled `__aexit__` leaks the process and the executor. CONFIRMED.
- **Probe.** One running turn, `turn/interrupt` held, the `__aexit__` task cancelled:
  ```
  R-E4: __aexit__ cancelled
  R-E4: client.close() calls: 0
  R-E4: after a second __aexit__, client.close() calls: 0
  R-E4: executor shut down: False
  ```
- **Code.** host.py:178 returns early once `_closing` is set, and :180 sets it. Steps 4-6 (:198-200) follow the await at :193 with no try/finally.
- **Fix check (in memory, Python 3.11).** With :188-195 in `try` and :198-200 in `finally`, the probe printed `FIX R-E4: client.close() calls 1 executor shut down True`, and the pack ran 101 with 0 failures.
- **Tier.** Major: INV-7 says close always finishes its steps, and a retry cannot repair it.

### R-8 (R-V5): two checks are reshaped around C002. CONFIRMED, plus a deviation-entry.
- **The C002 matcher.** lint/rules/c002_duplicate_inline_bool_guard_validation.py:84-93 matches only `isinstance(<Name|Attribute>, bool)`. Line 23, `_GENERIC_IDENTITIES = frozenset({"value", …})`, skips generic names.
- **Existing guards on main.** `git grep -n "isinstance(limit, bool)\|isinstance(timeout_seconds, bool)" origin/main -- vidbyte` finds `vidbyte/lib/dataclasses/coding.py:143` and `vidbyte/workflows/validation.py:172`. An inline guard would therefore trip C002, and the implementer reshaped the code instead:
  - host.py:495 uses `type(limit) is not int`, a bool guard the matcher cannot see;
  - host.py:346-349 builds a whole `CodexSpawnRequest` to borrow one field rule.
- **Owners that already exist.** `_reject_small_int` (codex_host.py:57) and `_reject_bad_seconds` (:65) own exactly these rules and guard `value`. Calling them adds no C002 occurrence, because the call site has no `isinstance`.
- **Message constants.** The tests assert only the type: test_codex_host_turns.py:215-217 (`assertRaises(ConfigurationError)` for 0, -1.0 and NaN) and test_codex_host_threads.py:135-136 (`launch limit 0`, `launch limit True`). So `BAD_TIMEOUT_MESSAGE` and `LAUNCH_LIMIT_MESSAGE` can go.
- **The deviation text.** `git show 79eadcf4 -- docs/spec/codex-host/spec.md` adds "- **Two argument checks take a different shape because of lint C002.** …". It was written by S3, not decided at S1. Its reason ("would have exceeded the 15-record budget") is wrong, because no new record is needed.
- **Fix kind.** `code`, plus a deviation-entry that withdraws spec.md:1561.

### R-9 (R-V6): seven new functions are missing their A002 marker. CONFIRMED.
- **Command.** `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py --rule A002 --all --format json`, piped into a JSON walk. It printed `A002 findings listed: 607` and these seven hits in this PR's new files:
  ```
  vidbyte/harnesses/native/codex/host.py 311 list_codex_threads
  vidbyte/harnesses/native/codex/oneshot.py 70 list_codex_threads
  vidbyte/harnesses/native/codex/preflight.py 163 reject_unusable_fields
  vidbyte/lib/dataclasses/codex_host.py 384 __post_init__
  vidbyte/tools/builtins/codex/threads.py 107 _perform
  vidbyte/tools/builtins/codex/threads.py 202 _continue_defaults
  vidbyte/tools/builtins/codex/threads.py 277 _perform
  ```
- **Spec.** spec.md:1297 requires the marker. The gate passes only because the baseline is 703.
- **Tier.** Major: §12.4 is broken, and S3-implementer.md:79 claimed it held. The lint gate does not fail, so it is not Blocker-class.

### R-10 (R-E5): continue and review release their reservation while the start is still in flight. CONFIRMED.
- **First probe attempt.** The second continue was awaited while the first `turn/start` was still held. It hit the 10 s bound, because openai-codex queues a second `turn/start` behind the pending first one.
- **Restructured probe.** The second continue runs as a task, the probe waits for `thread/resume` #2, and then releases the hold:
  ```
  R-E5: first continue cancelled while its turn/start is in flight
  R-E5: second continue passed require_idle and sent thread/resume #2
  R-E5: second continue returned handle turn-3
  R-E5: turn/start count: 2 turn/interrupt: 1
  R-E5: turns on thread now: [('turn-1', 'completed'), ('turn-2', 'interrupted'), ('turn-3', 'inProgress')]
  ```
- **Spec.** INV-24: "never starts a second turn on a thread where its own turn is running or reserved … raises codex.session_busy before any request". The host's own start was still in flight when the second continue passed `require_idle`.
- **Fix detail.** The registry reservation is a set (turns.py:279-289). Once `_adopt_late_turn` calls `track`, `_running[thread_id]` keeps the thread busy. So the reservation must be released after `track` on acceptance; immediately when `future.cancel()` succeeds; and from `_post_late`'s failed-start branch, which today returns without posting anything.
- **Tier.** Major: a retry after `codex.api_error` (EC-36) is exactly when this happens.

### R-11 (R-V4): JSON-RPC method names are inline literals. CONFIRMED.
- **Grep** (`git show 099fac83:<f> | grep -n -o -E '"(account/read|thread/[a-z/]+|turn/[a-z]+|initialize|cancel_goal_operation)"'`) finds 16 sites:
  - host.py: 208, 268, 301, 308, 326, 374, 509, 516, 533, 560, 653;
  - preflight.py: 97, 159;
  - connection.py: 153, 261, 263.
- **Private copies.** errors.py:31-32 holds `THREAD_READ_METHOD` and `THREAD_FORK_METHOD`.
- **The constant on main.** `CODEX_THREAD_START_METHOD` is on main at `vidbyte/lib/constants/codex.py:189` and is used at `agents/codex/tools.py:115`.
- **No test blocks it.** No packaging test pins the constants module's `__all__`; test_codex_host_packaging.py checks only the enum and builtins lists.
- **Tier.** Major: house style forbids hardcoded meaningful strings, the repo already has a constant for one of these names, and the D-13 overrides are only as reliable as the matching spellings.

### R-12 (R-E7): a mapping schema is never validated. CONFIRMED, as spec-change + tests-only.
- **Command.** `$PY -P -c "…OutputSchemaFormatter().validate('{\"y\": 1}', {'type':'object','required':['x'],…})"` prints `({'y': 1}, None)`. With `'not json'` it prints `(None, 'output is not valid JSON: …')`.
- **Same helper as the existing agent.** `git grep -n "\.validate(" -- vidbyte/agents/codex vidbyte/harnesses` shows that `agents/codex/result.py:218` and `harnesses/native/codex/wire.py:569` both call `self._schemas.validate`. The host matches the existing Codex agent and the repo's canonical helper.
- **The description promises more.** descriptions.py:40 promises a check against the schema. It is false for every tool call, because the spawn tool always passes a mapping.
- **No in-scope validator.** `JSONSchemaGrader._validate_node` (`vidbyte/evals/graders/json_schema.py`) is a private method of an evals grader, not a lib helper. Changing `OutputSchemaFormatter` touches a file outside §12.3 and changes `CodexHarnessAgent` (NG-5). Adding a dependency breaks NG-7.
- **Fix kind.** spec-change of INV-21 and EC-32, with the description and docstring text following, plus a pin test. The validator itself is [scope-adding] R-25.
- **Note for the spec author.** request.md:330, in the R2 design the user accepted, describes `schema_violation` as a "local check: The answer didn't match the schema". The revision should state that the local check for a mapping is JSON parsing only, and leave real validation to the user (R-25).

### R-13 (R-E6), R-14 (R-E8): test gaps. CONFIRMED by mutation.
- **The sweep.** One subprocess per mutant. The mutant is patched in memory, then the unittest loader runs every `tests.features.codex_host.test_codex_host_*` module. Nothing is written to disk. Output:
  ```
  baseline                                      ran 101 failed 0 []
  M1 late goal not stopped                      ran 101 failed 0 []
  M2 late label timed_out                       ran 101 failed 0 []
  M3 launch tool frees slots on success only    ran 101 failed 0 []
  M4 launch limit uses >=                       ran 101 failed 0 []
  M5 interrupt does not set stop_sent           ran 101 failed 0 []
  ```
- **Mutant definitions:**
  - M1: `_adopt_late_goal` tracks and watches, but never calls `_stop`.
  - M2: `_adopt_late_turn` calls `_stop(turn, FailureCode.CODEX_TURN_TIMED_OUT)`.
  - M3: `LaunchCodexSubagentsTool._perform` without `try/finally`.
  - M4: `_launch_items` uses `len(prompts) >= limit`.
  - M5: `interrupt_codex_turn` without `turn.stop_sent = True`.
- **R-13.** The helper at test_codex_host_failures.py:77-86 asserts only `snapshot.status.value == "interrupted"`.
- **R-14.** test_codex_host_tools.py:187-198 and :239-245 use the spawn tool only.
- **Test plan.** Neither gap is listed under "Tests deliberately NOT written" (test-plan.md:80-94).
- **Tiers.** R-13 and R-14 stay Major: D-35 and the slot release are specified behaviour with no test that can fail. M4 and M5 stay Minor (R-24).

## 3. Calibration decisions
- **Tiers kept.** No tier changed. Each of the five Blockers matches the S4 Blocker definition:
  - R-1 is a broken result.
  - R-2 breaks INV-8 and the weighted words "return semantic error messages".
  - R-3 contradicts AGENTS.md:63.
  - R-4 contradicts AGENTS.md principle 1.
  - R-5 contradicts the field-guide comment-format lesson.
- **Majors.** Each of the nine Majors is a real gap that would draw a review comment or surface in production.
- **Ordering.** Within each tier, findings are ordered by how much the fix touches, smallest first:
  - Blockers: R-1 (~6 lines), R-2 (~10), R-3 (~20 across 6 files), R-4 (~40, a refactor), R-5 (172 comment lines).
  - Majors: R-6 (~4), R-7 (~6), R-8 (~6 plus a §17 edit), R-9 (7 comment blocks), R-10 (~15 across two files), R-11 (16 sites plus constants), R-12 (spec and text), then the two tests-only findings.

## 4. Adjudications between reviewers
- **§17 deviation 1.** Conformance says it HELD; conventions says it is a lint evasion (R-V5). Both are right, on different axes. Behaviour is identical, which conformance checked, but the shape works around C002 and the stated reason is wrong. Verdict: fix the code and withdraw the deviation (R-8).
- **INV-7, INV-8, INV-11, INV-14, INV-24 and INV-26.** Conformance marked these "defense", reading the code plus the AC tests. Engineering's probes broke INV-7 (R-7), INV-8 and INV-26 (R-2), INV-11 and INV-14 (R-1) and INV-24 (R-10), and I reproduced every one. Conformance's AC-based defense covers the happy and specified-failure paths, not the cancellation windows that no AC names. The probes win.
- **INV-32.** Conformance's note that "only the cancel path in R-C1 escapes the cap" is consistent with engineering's R-E3. They are merged as R-6.
- **R-V2's fix.** The conventions fix (move `_spawn_task` and `_stopped`, replace `_read_back`) is incomplete, as R-4 explains. I extended it to move `_stop` too, and kept the reviewer's version as the base.
- **C011.** Conventions noted that C011 now sits at 2 of 2 (turns.py:320 `UsageTracker()`, which D-19 requires) and did not raise it. I agree it is not a finding: D-19 is settled.

## 5. Fix interactions and order for S5
- **The `_accept_review` group.** R-1, R-4 and R-22 all edit `_accept_review`. Fix R-1 first (behaviour), then R-4 (structure). Leave R-22's split optional, or fold it into R-4.
- **The `launch_codex_subagents` group.** Fix R-2 before R-6, or together with it. With R-6's `BaseException` path, a non-`CodexAgentError` failure on item k+1 is re-raised without INV-37's "k turns were started" text. Today only R-2's `ConfigurationError` or the pydantic error can reach that path, and R-2's fix removes them. R-14's test, once granted, should also cover R-6's cancel path.
- **The interrupt line.** R-16, the `stop_sent` check in `interrupt_codex_turn`, and R-24's M5 test touch the same line (host.py:385).
- **The comment pass.** Fix R-9 and R-21 (intent blocks), then R-5 (the 72-column rewrap) last. R-4 rewrites host.py:5 and several method comments, so R-5 must follow it.
- **R-3 and R-11** both edit `lib/constants/codex.py`. Append new names at the end of `__all__` (definition order, §12.4). No shared file is touched.
- **R-8 and R-12** each carry a spec edit. R-8 withdraws spec.md:1561. R-12 amends spec.md:289 (INV-21) and :447 (EC-32). Both go to the spec author in Revision mode, and R-12's code (descriptions.py:40 and the docstring) follows that revision.
- **Regression tests.** R-1, R-2, R-6, R-7 and R-10 fix windows that no current test covers. Each would want a regression test, which needs the orchestrator's grant (§14 "modifying any test file").

## 6. Severity blind-spot check (step 6)
I looked for Blocker-class risks between the lenses and found no new Blocker or Major to add. What I checked:
- **Shared-file safety of every fix.** No confirmed fix touches `failure.py`, `lib/enums/__init__.py`, `tools/builtins/__init__.py`, `tools/toolsets/__init__.py`, `REPO_MAP.md`, `harnesses/README.md` or `native/__init__.py`. The R-5 rewrap set (12 files) has none of them.
- **Conventions fixes against conformance requirements.**
  - R-3's enum members equal their wire values, so §9.3 and the constants test hold.
  - R-8's validators keep the accepted sets and the `ConfigurationError` type.
  - R-11 adds constants only.
  - R-4 leaves the INV-11 start path untouched.
- **Interaction of R-6 and R-2.** Recorded in §5 rather than as a finding, because it disappears once R-2 is fixed.
- **Tool path of R-1.** `StartCodexReviewTool` releases its slot in `finally` and owns the handle only on success. A review cancelled in the read-back window therefore also runs outside the cap; R-1's fix interrupts it.
- **Fork cancelled after `thread/fork` returns but before the router registration.** The fork's tool calls would get `CODEX_UNREGISTERED_TOOL_TEXT`. Nothing is spent and the failed tool result is documented (EC-47), so it is not raised.

## 7. Commands run
- `git log --oneline -3`, `git status --short`, `git diff --quiet 099fac83 HEAD -- vidbyte tests`: the code is identical, and the only untracked files are the three review reports.
- `git diff --stat origin/main...099fac83 -- vidbyte REPO_MAP.md` gives `28 files changed, 4631 insertions(+), 4 deletions(-)`.
- `gh run view 38500042527 -R cerredz/Vidbyte-SDK --json status,conclusion,headSha,name` gives `{"conclusion":"success","headSha":"099fac83…","name":"CI","status":"completed"}`. The same for 38500046011 gives `"name":"Static policy"`, also `success`.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/codex_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` gives `101 passed in 7.42s`.
- Probes for R-1, R-2, R-6 (host and tool), R-7 and R-10: outputs are quoted in §2.
- The mutation sweep for M1-M5 and the baseline: output in §2.
- The in-memory fix check for R-1, R-6 and R-7: the probes printed the `FIX …` lines in §2, and the pack with all three patches printed `PACK WITH FIXES: ran 101 failed 0 []`.
- `lint/run.py --rule A002 --all --format json`: 607 findings, 7 in new files (§2, R-9).
- The comment-width measurements in §2, R-5.
- The AST call-chain scan in §2, R-4.
- Reads: AGENTS.md; spec.md (§0-§9.1, §9.3, §12.4-§12.6, §14-§17); request.md §C shared-file contract and the R2 spawn design (:293-336); test-plan.md (grep); code-map not needed beyond the spec's citations; field guide `comment-format.md` and `blocking-lint-invariants.md` (the C002 entry); `lint/rules/c002_duplicate_inline_bool_guard_validation.py`; the host, connection, turns, wire, preflight, errors, codex_host, delegation and descriptions sources at 099fac83; `providers/output_schema.py:60-110`; `evals/graders/json_schema.py`.
