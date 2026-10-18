# S4 findings verifier: codex-host-first-class (slice 2)

Diff: `git diff a7730107...8ea8734f`. HEAD `57f3f687` adds only the docs commits (`pipeline.md` and the three S4 reports), and `git diff --stat 8ea8734f HEAD` lists only those 4 files. Inputs: the three S4 reviews, spec r5, test-plan.md, request.md, AGENTS.md, the field guide (`comment-format.md`, `blocking-lint-invariants.md`), the house style, and the slice-1 verified review as format precedent. Output: `docs/spec/codex-host-first-class/review.md`.

Every probe and fix checker is under `VD = C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/s4-slice2/verifier/`. Every probe is read-only: fixes are applied in memory with `exec` and `setattr`, and no worktree file is edited. `git status --porcelain` lists only the two untracked outputs, `review.md` and this report.

`V` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/venv-codex163/Scripts/python.exe`, which is Python 3.11.0.

## Result

**Verdict:** MERGEABLE AFTER FIXES. 2 Blockers, 6 Majors and 7 Minors are confirmed. None was refuted and none downgraded.

## 1. Merge map

| Original | Lens | Proposed | Merged | Final tier | Fixer |
|---|---|---|---|---|---|
| R-C1 | conformance | Blocker | **R-1** | Blocker | code (+S2 row; spec: deviation for the new message triple) |
| R-E1 | engineering | Blocker | **R-1** | Blocker | (same) |
| R-V1 | conventions | Blocker | **R-2** | Blocker | code |
| R-E3 | engineering | Major | **R-3** | Major | code (+S2 row; spec: one INV-20 sentence) |
| R-E2 | engineering | Major | **R-4** | Major (conformance lens added) | code (+S2 row) |
| R-E6 | engineering | Major | **R-5** | Major | spec → code (+S2 row) |
| R-E5 | engineering | Major | **R-6** | Major | tests |
| R-E4 | engineering | Major | **R-7** | Major | tests |
| R-V2 | conventions | Major | **R-8** | Major | code |
| R-C2 | conformance | Minor | m-1 | Minor, trivial | spec |
| R-C3 | conformance | Minor | m-2 | Minor, trivial | code + spec |
| R-V3 | conventions | Minor | m-3 | Minor, trivial | docs |
| R-V4 | conventions | Minor | m-4 | Minor, trivial | docs |
| R-V5 | conventions | Minor | m-5 | Minor, trivial | docs |
| R-V6 | conventions | Minor | m-6 | Minor, follow-up | code (+spec budget) |
| R-V7 | conventions | Minor | m-7 | Minor, follow-up | code ([scope-adding] half) |
| K1 (engineering, not filed) | engineering | — | — | not a finding (equivalent mutant) | — |

**Ordering.** Confirmed findings run most severe first. Within a tier they run by how much code the fix touches, smallest first:
- R-1 touches 2 files, R-2 touches 10;
- R-3 is 1 line, R-4 about 3, R-5 about 6;
- R-6 is 1 test, R-7 is 2 tests, and R-8 is about 30-40 comment lines in 3 files.

## 2. Verification of each Blocker and Major

### R-1 (R-C1 + R-E1), Blocker, CONFIRMED
- **Code.** `thread_methods.py:162-166` runs `Path.home()`, `target.exists()` and `root.mkdir(parents=True, exist_ok=True)` outside any `try`.
- **Probe** `VD/probe_v_worktree.py`. It subclasses `CodexWorktreeHostTests` (real git, private git config, `Path.home` patched) with three cases. Command: `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 "$V" -m pytest -q -s -p no:cacheprovider --rootdir=$(pwd) $VD/probe_v_worktree.py -k probe`. Output:
  ```
  VPROBE vidbyte-file: builtins.FileExistsError typed=False: [WinError 183] Cannot create a file when that file already exists: 'C:\\Users\\422mi\\AppData\\Local\\Temp\\tmp9fgovsjv\\home\\.vidbyte'
  VPROBE vidbyte-file branches: ['master'] sent: []
  VPROBE home-unresolvable: builtins.RuntimeError typed=False: Could not determine home directory.
  VPROBE home-unresolvable branches: ['master'] sent: []
  VPROBE mkdir-denied(simulated): builtins.PermissionError typed=False: [Errno 13] Permission denied: 'C:\\...\\home\\.vidbyte\\codex-worktrees'
  VPROBE mkdir-denied(simulated) branches: ['master'] sent: []
  11 passed in 23.34s
  ```
  `typed=False` means the exception is neither a `ConfigurationError` nor a `CodexAgentError`. The third case simulates the denial by patching `Path.mkdir`. The first two are real filesystem and `Path.home` behaviour.
- **No other gap on this method.** `vidbyte/lib/process/runner.py:5` says "Every failure is a field of the returned CliOutcome; only asyncio.CancelledError is raised". Its `launch` catches `FileNotFoundError`, `PermissionError` and `(OSError, ValueError)` (`:294-301`). So lines 162-166 are the only raw-exception gap on this method.
- **Spec.**
  - INV-2: "Every failure a new method raises is one of two kinds … No KeyError, TypeError …". Its only carve-out is the EC-3 no-loop `RuntimeError`.
  - INV-29: "Every failure raises `CONFIGURATION_INVALID_ARGUMENT`".
  - The weighted words in request.md §D: "exception handle everything that could potentially go wrong".
- **Existing guard: none.** `GitWorktreeSpec` does no filesystem I/O (§16 r1-11), and no outer handler exists.
- **Fix choice.** Keep the `mkdir` wrapped, do not delete it. In-repo evidence: the `test_codex_host_worktree.py` header says "git worktree add creates the branch before it finds the target folder taken". The conformance reviewer separately showed git 2.49 leaving `feat-y` behind on exit 128.
- **Spec interaction.** §9.2 lists "exact texts", and §14 asks the implementer to stop before changing a §9.2 message text. So the new triple must be recorded as an implementation deviation. §8.4 is unaffected: messages are not config keys (§8.4 row "New config keys … The message texts … are not config").

### R-2 (R-V1), Blocker, CONFIRMED
- **Command** (the field guide's own check, CRLF-normalised, over every changed `vidbyte/*.py`): `for f in $(git diff --name-only a7730107...8ea8734f -- 'vidbyte/*.py'); do tr -d '\r' < $f | awk -v F=$f 'length($0) > 72 && $0 ~ /^[ \t]*#/ {printf "%s:%d [%d]\n", F, NR, length($0)}'; done`.
- **Output.** Exactly 14 lines:
  - `feature_wire.py:197 [74]`, `goal_methods.py:98 [73]`, `settings_methods.py:173 [73]`, `:187 [73]`;
  - `thread_helpers.py:231 [73]`, `wire.py:301 [74]`, `codex_host_inputs.py:678 [73]`;
  - `controls.py:73 [76]`, `:163 [73]`, `:168 [73]`, `live.py:237 [74]`;
  - `thread_actions.py:133 [76]`, `:183 [76]`, `toolsets/codex.py:139 [75]`.
- **Base.** The same loop over `git show a7730107:<file>` gives `0` lines.
- **Field guide.** `comment-format.md`: "Wrap every comment line at 72 columns, counting the indent … A single-line comment that would pass 72 columns becomes a wrapped block too." The check "prints nothing for the files you touched." Spec §12.4 repeats it.
- **Calibration.** It is Blocker by the rubric, because it breaks a field-guide lesson. That matches the slice-1 verifier's identical R-1 (six 73-column lines, Blocker, fixed @df460ec7). Each fix is mechanical.
- **Interaction found.** `wire.py` is 839 lines against its 840 ceiling. `textwrap.wrap` of the `:299-301` block at width 72 takes 4 lines, giving 840, which is allowed but leaves no headroom. Re-word it to stay at 3 lines.
- **Pins.** `grep -rn "a-side-chat-fork-is-ephemeral" tests/ lint/` finds nothing, so the `@intent` rename is free.

### R-3 (R-E3), Major, CONFIRMED
- **Code.** `turn_stream.py:142-145`: `while self._events and not self._fits(size): self._drop_oldest()`, then `if self._fits(size): self._append(...)`. An event with `size > CODEX_HOST_STREAM_TEXT_LIMIT_CHARS` can never fit, so the loop empties the log first.
- **First probe was flawed, and redone.** My first probe used a subscription that was never iterated. That shows `GAP(1, 6)` only because an un-iterated subscription holds nothing at end of turn (D-37, AC-43), which masks the drop. So I discarded it and wrote `VD/probe_v_stream.py`. There the subscription is created mid-turn after three kept 1-character deltas, reads event 1, and then lags. The bound is patched to 500 and a 600-character diff arrives.
- **Command:** `PYTHONPATH=$(pwd) "$V" -m pytest -q -s -p no:cacheprovider --rootdir=$VD $VD/probe_v_stream.py`. Output:
  ```
  VPROBE[control] kinds: ['message_delta', 'message_delta', 'message_delta', 'message_delta', 'item_completed', 'ended']
  VPROBE[control] delta texts: ['a', 'b', 'c', 'd']
  VPROBE[oversize] kept after oversize: (0, 0)
  VPROBE[oversize] kinds: ['message_delta', 'gap', 'message_delta', 'item_completed', 'ended']
  VPROBE[oversize] gaps (seq,dropped): [(2, 3)]
  VPROBE[oversize] delta texts: ['a', 'd']
  ```
- **Spec reading.**
  - EC-19's "User sees" column says "Subscribers see `GAP(dropped=1)` in its place".
  - INV-20's last sentence says "an event that alone passes the character bound is dropped and counted".
  - INV-20's earlier sentence ("drops its own oldest events until it fits") is literally what the code does, and for an oversize event it can never be met.
  - So the spec contradicts itself. EC-19 is the specific rule for this exact trigger, so the code breaks it. A clarifying INV-20 sentence goes to the spec author, but the repair agent is not blocked on it.
- **Fix proven** (`VD/fixcheck2.py RE3`, which adds `size <= TEXT_LIMIT and size <= HOST_TEXT_LIMIT` to the loop condition): `kept after oversize: (3, 3)`, `gaps: [(4, 1)]`, `delta texts: ['a','b','c','d']`.
- **Existing test.** It cannot see this. `test_codex_host_stream_wait.py:346-358` reads everything kept before emitting the diff.

### R-4 (R-E2), Major, CONFIRMED (conformance lens added)
- **Code.** In `turn_starts.py:204-216`, `sent = True` is set only after `activate()` returns, and the cancel is gated on `sent`. `activate` is `connection.raw(CODEX_GOAL_SET_METHOD, …)` with no `parse`, so the SDK validates the answer against `ThreadGoalSetResponse` on the worker. A malformed answer raises after Codex applied the set.
- **Probe** `VD/probe_v_engineering.py -k resume`. My malformation differs from the reviewer's, who removed `goal`: here the echoed `goal.status` is `"notAStatus"`. Command: `PYTHONPATH=$(pwd) "$V" -m pytest -q -s -p no:cacheprovider --rootdir=$VD $VD/probe_v_engineering.py -k resume`. Output:
  ```
  VPROBE resume: CodexAgentError code=codex.protocol_mismatch
  VPROBE goal status at Codex: active
  VPROBE fake turn statuses: ['completed', 'inProgress']
  VPROBE host busy on thread: False
  VPROBE goal-op calls: ['finish', 'unregister_goal_operation']
  VPROBE goal sets: ['active'] interrupts: 0
  ```
- **SDK reference.** `openai_codex/client.py:625-648`: `activated = False` … `self.thread_goal_set(...)`, then `activated = True`, then `except BaseException as exc: if activated or not isinstance(exc, InvalidRequestError): self.cancel_goal_operation(state)`. So the SDK cancels on every failure except a refusal before activation.
- **Spec reading.** The orchestrator asked whether this is a spec gap. It is not.
  - §9.2's resume row is in the "Requests, in order" column, which §9.2 declares normative. It says: "If the start then fails after the set was sent, the SDK's goal cancel follows: a pause set, then at most one `turn/interrupt`."
  - EC-37 exempts only "`thread/goal/set` is refused by Codex".
  - INV-31's "cancelled only if the status was set" holds too: Codex did set it.
  - So the code breaks the spec as written, and the fixer is `code`. Rewording INV-31 is optional clarity only.
- **Fix proven** (`VD/fixcheck2.py RE2`: `sent = True` before `activate()`, `except BaseException as exc`, cancel when `sent and not isinstance(exc, JsonRpcError)`):
  ```
  VPROBE goal status at Codex: paused
  VPROBE fake turn statuses: ['completed', 'interrupted']
  VPROBE goal-op calls: ['cancel_goal_operation', 'finish', 'unregister_goal_operation']
  VPROBE goal sets: ['active', 'paused'] interrupts: 1
  ```
- **Which class to skip on.** `JsonRpcError` is chosen over the SDK's narrower `InvalidRequestError`, because EC-37 treats any refusal by Codex as "never set". The SDK-faithful alternative (`not isinstance(exc, InvalidRequestError)`) also satisfies §9.2, and would cancel on a -32603 that came after an applied set.

### R-5 (R-E6), Major, CONFIRMED
- **Code.** `thread_actions.py:103-117` narrows the sandbox and approvals but keeps every field of `CODEX_HOST_REJECTED_FIELDS[START_CODEX_SIDE_CHAT]` (`vidbyte/lib/constants/codex_host.py:207-216`: prompt, goal, name, tools, `thread.ephemeral`, `thread.personality`, `thread.service_name`, `thread.session_start_source`). `CodexToolScope` refuses only prompt and goal in `spawn_defaults` (`vidbyte/tools/builtins/codex/_base.py:69`), so `tools`, `name` and `personality` can all reach the method.
- **Probe** `VD/probe_v_engineering.py -k side_chat`, with a third trigger: a `tools` default, the ordinary way to give spawned threads a Vidbyte tool. Output:
  ```
  VPROBE spawn tool with tools default: success
  VPROBE side-chat tool with tools default: error: configuration.invalid_argument: start_codex_side_chat does not use the CodexSpawnRequest field tools; leave it at its default, because start_codex_side_chat would otherwise drop the value without appl…
  ```
- **The grain.** The continue tool clears its row (`threads.py:204-215`, slice 1). The resume tool clears its row (`skill_functions.py:320-329`, spec §9.2 row 36, deviation 12). The fork tool passes `overrides=None`.
- **Spec reading.** It is a spec gap, not a misread. Row 34 lists the narrowings and says nothing about this row, while row 36 has the reset for resume. EC-53 accepts a refusal only for `collaboration_mode`, whose value carries the developer's intent. Clearing `tools`, `name` or `personality` for an ephemeral fork that shares the parent's tools is pure narrowing (INV-43 "only narrows it"). G-3 fails for any scope that sets them.
- **Calibration.** It is kept Major because it disables a tool for an ordinary posture. The fixer is `spec → code`.
- **Fix proven.** `VD/fixcheck_re6.py` resets the row's paths to a fresh request's values, then calls the original narrowing. The probe gives `success: {"thread_id": "thr-3", "turn_id": "turn-3"}`. `test_codex_host_feature_tools.py`, `test_codex_host_side_chat.py`, `test_codex_host_tools.py` and `test_codex_host_tool_hardening.py` give `53 passed in 1.88s`. AC-36 stays green because `_writable_defaults` sets none of these fields.

### R-6 (R-E5) and R-7 (R-E4), Major, CONFIRMED (test-pack gaps)
- **Re-run against the whole suite.** The engineering reviewer ran the mutants against only 12 test modules (`engineering/files.txt`). Four test modules outside that set reference the stream: `feature_docs`, `feature_structure`, `first_class_snippet` and `records`. So I re-ran each survivor against the **whole** `tests/features/codex_host` directory with the engineering `mutant.py`, which runs pytest with `-x`.
- **Command:** `PYTHONPATH=$(pwd) "$V" $S/engineering/mutant.py <id> tests/features/codex_host -q -p no:cacheprovider`. Results, counted from the progress marks:
  ```
  NONE                                   rc=0  dots=589 s=1 F=0 E=0
  S3b-fits-ignores-host-text             rc=0  dots=589 s=1 F=0 E=0
  S3c-fits-ignores-cumulative-turn-text  rc=0  dots=589 s=1 F=0 E=0
  S7-subscribe-starts-at-next            rc=0  dots=589 s=1 F=0 E=0
  ```
  `mutant.py` applies the mutation before pytest and exits non-zero with `MUTANT-NOT-APPLIED` if the pattern is missing.
- **The S7 mutant is live.** With `mutant.py S7-subscribe-starts-at-next $VD/probe_v_stream.py -k control`, the mid-turn subscriber's first read hangs until the probe's bound cancels it (`CancelledError` in `asyncio/locks.py:213`). Without the mutant it yields sequence 1. So a test can tell the two apart, and none does.
- **What the suite patches.** `grep -n "patch_stream(" tests/features/codex_host/test_codex_host_stream_wait.py` gives `:211` and `:325` (`CODEX_HOST_STREAM_EVENT_LIMIT`), `:348` (`CODEX_HOST_STREAM_TEXT_LIMIT_CHARS`, one oversize event) and `:385` (`CODEX_HOST_STREAM_HOST_EVENT_LIMIT`). `HOST_TEXT_LIMIT_CHARS` is never patched.
- **The plan's claim does not hold.** test-plan.md:197's NFR-3 row claims "The four bounds are patched small". test-plan.md:99's INV-22 row cites no mid-turn subscription test.
- **Calibration.** These are missing tests, not vacuous ones. NFR-3 is a memory bound and not a privacy or security rule, so it matches slice-1's R-5, R-6 and R-8 (Major, test), not slice-1's R-4. The fixer is `tests`.

### R-8 (R-V2), Major, CONFIRMED
- **Counter.** `VD/narr.py` uses tokenize and the AST to count comment lines inside each public method body, after the docstring. Command: `"$V" -I $VD/narr.py <the four mixins>`. These 13 methods give `comments=0`:
  - `settings_methods.py`: `:95` list_codex_collaboration_modes (7 statements), `:133` list_codex_mcp_servers (7), `:222` get_codex_memory_status (8), `:232` reset_codex_memories (7);
  - `thread_methods.py`: `:185` archive (6), `:196` unarchive (7), `:205` revert (7), `:221` rename (7), `:230` inject (7), `:243` list_codex_background_terminals (9), `:257` clean_codex_background_terminals (9), `:271` search_codex_thread_content (8);
  - `goal_methods.py`: `:135` clear_codex_goal (6).
- **The other 12 methods** carry 2-14 comments each.
- **Precedent.** On `a7730107`'s `host.py`, six public methods give `comments=0`: `read_codex_thread` (6 statements), `get_codex_turn_result` (5), `track_codex_thread_usage` (8), and `list_recent_codex_threads`, `list_codex_threads_since` and `search_codex_threads` (4 each).
- **Claims the code contradicts.**
  - The headers `settings_methods.py:4` and `thread_methods.py:4`: "Each method is a thin narrated main function".
  - Spec §12.3 rows 26 and 28, the same words.
  - §8.2: "It is a narrated main function per feature".
  - §12.4: "Every main function is narrated".
  - AGENTS.md §2.
- **Field guide.** `grep -rli narrat` over the field guide finds only `comment-format.md` and `init.md`. No separate owner lesson on narration exists.
- **Calibration.** It is kept Major, not raised to Blocker. Read literally, AGENTS.md §2 is contradicted. But the owner accepted the 6 thin unnarrated methods, slice 1's verified review left them alone, and the new 13 have 6-9 statements, at that precedent. What makes it a sure defect is the false header claim and the spec rows that promise narration.

## 3. Minors (passed through, de-duplicated, each spot-checked)
- **m-1 (R-C2).** `git diff … host.py` shows the two `-if self._approval_handler is None and self._responses.routes_to_user(...)` / `+self._preflight.reject_routed_reviewer(...)` pairs at `:347` and `:749`. `preflight.py:164-165` raises when `routed and not self._approvals_answered`, and `host.py:202` builds it with `approvals_answered=handler is not None`, so the refusal is identical. It appears neither in §12.3 row 30 nor in the 13 deviations.
- **m-2 (R-C3).** `thread_methods.py:295` passes `CODEX_THREAD_LIST_METHOD`. `test_codex_host_feature_contract.py:175-178` asserts only `details["field"]`, the message head and the tail, so the feature word is free.
- **m-3 (R-V3).** `V -I` over `openai_codex.generated.v2_all` gives: `ModeKind present ['plan','default']`, `ThreadMemoryMode present`, `McpAuthStatus present […,'bearerToken','oAuth']`, `McpServerStatusDetail present`, `McpServerStartupState present`, `TurnPlanStepStatus present`, `TurnSettingsUpdateStatus ABSENT`.
- **m-4 (R-V4).** `constants/codex_host.py:7` reads "A summary never quotes an exception's own text, stderr, …". `errors.py:7` reads "No message carries an exception's own text, stderr, …". The slice-2 diff edited both lines' KNOWN EDGE CASES, and `thread_methods.py:315-316` puts git's first stderr line into `CODEX_HOST_WORKTREE_FAILED_MESSAGE`, as INV-29 and EC-34 require.
- **m-5 (R-V5).** The wrong citations are confirmed:
  - `skill_functions.py:181` "(first-class INV-16, D-16)", `:185` "(EC-14)", `:4` "(first-class D-16)", `:7` "(first-class INV-16, EC-12, EC-14)", and `:8`'s RELATED DOCS, which lists D-16;
  - `settings_methods.py:8` RELATED DOCS lists D-16;
  - `constants/codex_host.py:544` "(first-class INV-38)";
  - `stream_methods.py:63-64` "(first-" / "class INV-23".
  Spec D-8 is the plan run (spec.md:745), and D-16 is goal origin (spec.md:753).
- **m-6 (R-V6).** The literals are at `feature_wire.py:302`, `:303`, `:338`, `:204` and `:205`. The C021 lesson (`blocking-lint-invariants.md:68-73`) scopes to top-level bindings. Slice 1's verified review called field labels and wire keys the #1178 grain. Moving the template, separator and path test would add config keys past §8.4's 46, so this is a follow-up.
- **m-7 (R-V7).** The duplicated sandbox rule is confirmed: `codex_host_features.py:128-142` against `codex_host.py:258-271`, with the identical `bad_roots` line at `:139` and `:269`. Inline absolute-path messages are at `codex_host_features.py:104-105` and `process.py:117-118`. `codex_host.py` is at 891/900.

## 4. Adjudications between reviewers
1. **R-C1 against R-E1, the fix shape.** Both wrap lines 162-166. The conformance reviewer says do not delete the `mkdir`, and I agree, with in-repo evidence (the test header). The engineering reviewer adds `type(exc).__name__` to the message. I agree: INV-9 and the constants header allow a type name as a variable part. Neither reviewer noted that §9.2's text table is exact, so I added the deviation-record requirement.
2. **R-E3's spec footing.** The engineering reviewer cites EC-19 and INV-20's last sentence. INV-20's middle sentence supports the code's literal behaviour. I rule that EC-19, the specific rule for this trigger, governs, and route an INV-20 clarifying sentence to the spec author without blocking the repair.
3. **R-E2's lens.** Filed under engineering's pre-mortem. I found §9.2's normative resume row requires the cancel, so the finding is also a conformance defect, and no spec change is needed. This answers the orchestrator's "spec gap?" question: no.
4. **R-E6, spec gap or misread.** The engineering reviewer frames it as INV-43 "only narrows". I rule it a spec gap with a production failure: row 34 is silent, while row 36 resets for resume. So the fixer is `spec → code`, not `code` alone.
5. **R-V2's tier.** The conventions reviewer chose Major because of precedent. I re-derived the precedent counts myself (6 base methods of 4-8 statements against the new 13 of 6-9) and agree.
6. **The orchestrator's comment-width question.** The 73-76-column comments are Blocker-class: the rubric, slice-1's precedent and an owner-sourced field-guide lesson all point there. The calibration note says the fix is mechanical.
7. **Engineering's mutant scope.** Its survivors were measured against 12 modules. I widened the run to all of `tests/features/codex_host`, and they still survive (589 passed, 1 skipped).

## 5. Blind-spot check
- **Fixes that could break conformance.**
  - R-V6's full fix would push §8.4's 46 config keys up, so it stays a spec follow-up (m-6).
  - R-1's new message is not a config key, but it is a §9.2 text, so it needs a deviation record.
  - R-2's re-wrap of `wire.py` touches the 840 ceiling.
  - R-8's new comments must pass R-2's check.
- **Gaps between lenses.**
  - The test plan's NFR-3 "four bounds are patched small" claim is false. That is evidence for R-7, not a separate finding.
  - No other new-method path leaks a raw exception. `CliRunner` never raises, and the other paths map through `CodexErrorMapper` or `ConfigurationError`, as the conformance reviewer's INV-2 walk found and my reading of `thread_methods.py`, `turn_starts.py` and `turn_stream.py` confirms.
- **No `[verifier]` finding** was added. I found no further Blocker-class risk I could anchor to a `path:line`.

## 6. Proof that the proposed code fixes keep the area green
- **Area run with both fixes.** The command `PYTHONPATH=$(pwd) "$V" $VD/fixcheck2.py BOTH -q tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py` applies R-3's and R-4's fixes in memory. Final lines:
  ```
  FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
  1 failed, 1293 passed, 3 skipped in 83.72s (0:01:23)
  ```
  These are the same counts as the conformance reviewer's unfixed baseline (`1 failed, 1293 passed, 3 skipped`). The one failure is the inherited 167 != 120.
- **R-5's fix:** `53 passed in 1.88s` on the four tool and side-chat modules (section 2).

## 7. Commands run (final lines)
- `PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 "$V" lint/run.py` gave:
  ```
  S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

  SDK-LINT: PASS
  ```
- `PYTHONPATH=$(pwd) "$V" -m pytest -q tests/features/codex_host/test_codex_host_first_class_snippet.py -p no:cacheprovider` gave `1 passed in 1.36s`.
- The four probes and the mutant re-runs, with outputs quoted in section 2:
  - `probe_v_worktree.py`: `11 passed in 23.34s`;
  - `probe_v_engineering.py`: `4 passed in 1.25s`;
  - `probe_v_stream.py`: 2 passed;
  - the mutant re-runs: rc=0 four times.
- The fix checks: `fixcheck2.py RE2` (1 passed, PROBE lines above), `fixcheck2.py RE3` (1 passed), `fixcheck2.py BOTH` on the area suite (above) and `fixcheck_re6.py` (53 passed).
- `wc -l` gave: wire 839, `dataclasses/codex_host` 891, `constants/codex_host` 756, thread_methods 320, turn_starts 258, turn_stream 277, thread_actions 303, settings_methods 245, goal_methods 172.
- `git status --porcelain` lists only `?? docs/spec/codex-host-first-class/reports/S4-findings-verifier.md` and `?? docs/spec/codex-host-first-class/review.md`. No source file changed.
