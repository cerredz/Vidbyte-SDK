LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — every §12.3 row, FR, AC, and the user's weighted words hold on the paths tested and on the extra paths I probed. Two spec claims hold only on the common path: EC-10's `phase commit`, and INV-10's "every launch is closed". A third claim is a sentence in the docs that is wrong.

Reviewed: `git diff origin/main...c1c3ecc0` (merge base `181f1992`). The worktree HEAD `6185889b` differs from `c1c3ecc0` only in `pipeline.md`.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **Every §12.3 row is done, and nothing else changed.**
  - Rows 1–12 and 14 are done as written, including the prescribed wording. Examples: the `InfiniteStopCause` docstring, the `_after_tool_iteration` docstring, launch.py header rule 2, the `@intent one-failed-pair-never-sinks-its-siblings` ending, the agents README sentence, and the six README notes.
  - The source diff touches exactly the 13 files of §12.3. `git diff 181f1992 c1c3ecc0 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/middleware vidbyte/pipelines vidbyte/__init__.py contracts/` is empty (INV-20, NG-7, NG-12).
  - S3 changed no test (`git diff 2cab5070 c1c3ecc0 -- tests` is empty).
  - There is no lint change, no suppression, and no baseline edit.
- **G-5 and INV-6 hold beyond what AC-21 and AC-26 cover.**
  - The tree I used has a tool refusal, a replay, a rule drop, an unchecked drop, a child-agent error, and an AC-13 commit abort.
  - On that tree, the text every model call received (prompt, system, messages, tools) and every workspace file are byte-identical with a sink and without one.
  - Two runs with a sink give equal 47-event streams once `run_id` and `duration_ms` are normalized.
- **D1 is derived, not observed.**
  - Denials are read only from existing DENIED `ToolCallContext`s that carry a `limit`. `limit` is set only in `vidbyte/middleware/builtins/delegation_limits.py:55,67`, so A-1 holds.
  - `state.call_contexts` is only ever appended to (searched `vidbyte/` for any other change to it), and `result.metadata["tool_calls"]` is `tuple(state.call_contexts)` (`runtime.py` `_runtime_metadata`). So the `_announced` high-water mark indexes both lists the same way.
  - The catch-up runs before `journal.finish`, so every root denial comes before `run_finished` (INV-11, INV-15).
  - `InfiniteRunJournal.started` returns `tuple(self._started)`. It is a read-only view, and the journal format does not change.
- **The §4 snippet works as written, and deviation 1 does not change behaviour.**
  - I took the §4 snippet verbatim from `spec.md` and ran it through `ScriptedTree` with a script I wrote myself. It printed the refusal's rule and source, two commits, and `1 2 0`, and both of its asserts held (AC-1). No network was used.
  - The `_in_flight` changes now sit just before the shield, which is behaviourally identical to the first line inside it. The no-sink path still returns first. The guard `journal.finished` is `self._cards.get(key)` (`journal.py:121-123`), which cannot raise.
  - Counters start at `INFINITE_MIN_COUNT`, which is 0 (`constants/infinite.py:34`). `attempt` is 1 or more, `batch_index` and `batch` start at 0, and `_level` starts at `(0, False)`, all as §9.1 says.

## FINDINGS

**R-C1 [Major] [every-ID / weighted word] `vidbyte/agents/infinite/launch.py:307-312`: a pair that records its card from the error branch reports the wrong phase in its abort.**

When the pair records its card from the error branch, `phase` still reads `generator` or `verifier`. So `subagent_aborted` names that phase, not `commit` as EC-10 states.

- **Evidence (code).** `phase = InfinitePairPhase.COMMIT` is set only at `launch.py:300`, inside the inner `try`. The `except (VidbyteSdkError, OSError, ValueError)` branch at :307-312 sets `self.error = exc` and calls `self._finish(last, …)` without changing `phase`.
- **What the spec says.**
  - Row 6 places COMMIT "so that every path reaches `_commit`/`_finish` in phase `commit` (D-10, EC-10)".
  - EC-10 says the abort is announced with "(phase `commit`)" and does not limit this to one path.
  - `InfinitePairPhase.COMMIT` is defined as "commit, drop, and record the card".
- **Evidence (probe).** A heredoc probe used `ScriptedTree`. The sink raises `KeyboardInterrupt` on the first `subagent_finished`, which is EC-10's trigger.
  ```
  normal          aborted: [('cancelled', 'KeyboardInterrupt', 'commit', 0)]
  generator-error aborted: [('cancelled', 'KeyboardInterrupt', 'generator', 0)]   # generator("a"): [fail(RuntimeError(...))]
  verifier-error  aborted: [('cancelled', 'KeyboardInterrupt', 'verifier', 0)]    # verifier("a"): [fail(RuntimeError(...))]
  ```
- **How it fails.** A child agent errors, so its card is recorded through `_finish` in the error branch. Then either:
  - a sink interrupt arrives during that branch's `subagent_finished` (EC-10), or
  - a journal write fails a second time in that branch (EC-25).

  Either way the dashboard shows "aborted in its generator step" (or verifier step) for a pair whose card was already being recorded. In the EC-10 case its `subagent_finished` has already been delivered. The only EC-10 test (`test_an_interrupt_the_sink_raises_on_subagent_finished_gives_one_abort_in_the_commit_phase`) covers only the normal path, so the gap is untested.
- **Smallest fix.** Make `phase = InfinitePairPhase.COMMIT` the first statement of the inner `except (VidbyteSdkError, OSError, ValueError)` branch, before `self.error = exc`.
  - It adds no nesting.
  - It makes launch.py 456 of 470 lines.
  - Every existing phase assertion still holds. AC-12's generator phase comes from a `CancelledError`, which bypasses that branch. The other phase checks are component calls with explicit phases.
- **Spec IDs:** EC-10, EC-25, D-10, §12.3 row 6, INV-10, FR-11.

**R-C2 [Minor] [weighted word] `vidbyte/agents/infinite/launch.py:160-163`: INV-10 says every launched pair is closed, and two paths leave a pair open that INV-10 does not list.**

INV-10 says "every `subagent_launched` is followed by exactly one `subagent_finished` or `subagent_aborted`", and lists only EC-4 and EC-10 as exceptions.

- **Evidence (code).**
  ```
  for task, key in zip(cards, keys, strict=True):
      if key in pairs:
          self.journal.pair_started(key)
          self.events.subagent_launched(self, task, batch, tuple(pairs).index(key), len(pairs))
  ```
- **Probe 1.** I patched `InfiniteRunJournal.pair_started` to raise `OSError` on its second call. Root script: `launch(task("a"), task("b"))`, then `reply("done")`.
  ```
  ['run_started', 'subagent_launched', 'run_finished']
  launched: ['root/a'] closed: []   in_flight on launch: [1]
  ```
- **Probe 2.** The sink raises `KeyboardInterrupt` on `subagent_launched`.
  ```
  ['run_started', 'subagent_launched', 'run_stopped']
  ```
- **How it fails.** A disk error on the second `pair_started` of a batch makes `execute` raise after pair `a` was announced but before any pair runs. The run goes on and ends with `run_finished`, but `root/a` is never closed, and `in_flight` stays raised. No event explains the failed launch call: `batch_rejected` catches only `ConfigurationError` and `ToolExecutionError`. This is the "row stays running forever" case that G-3 and §1 set out to remove. It is bounded, because a consumer can close rows on `run_finished`.
- **Smallest fix (documentation only; a handler would add a code path, which EC-26's rationale rejects).**
  - Add both triggers to INV-10's exception list and to the EC-4 note in the package README: a `pair_started` write that fails part-way through a batch, and a sink `BaseException` on `subagent_launched`.
  - An optional code alternative: write every `pair_started` first, then announce in task order. That narrows only the disk case.
- **Spec IDs:** INV-10, INV-16, G-3.

**R-C3 [Minor] [spec/doc consistency] `vidbyte/agents/infinite/README.md:178` and the `launch.py:9` header: both say a child agent's error "always arrives as `AgentExecutionError`", which is false for two error types.**

- **Evidence.** `vidbyte/agents/base.py:967` re-raises `UsageAccountingError` and `FailureRaisedError` unwrapped. Neither is an `AgentExecutionError`; only `AllModelsFailedError` is.
  ```
  if isinstance(exc, (UsageAccountingError, FailureRaisedError, AllModelsFailedError)):
      ...
      raise
  ```
  The spec's own EC-27 says "Three typed errors pass through as they are". The sentence the implementer copied comes from row 6 and INV-19, which contradict EC-27.
- **How it fails.** A future agent who trusts the README or the header expects `error_type` to come from an `AgentExecutionError` wrapper.
  - A `FailureRaisedError` raised `from exc` (`sessions/failure/router.py:368`) reports its cause's class.
  - One raised without a cause (`raise_recovery.py:35`) reports `FailureRaisedError`.

  Behaviour is correct, because all three are `VidbyteSdkError`s and become the card. Only the documentation is wrong.
- **Smallest fix.** Reword both sentences to: "A child agent's error always arrives as a VidbyteSdkError (AgentExecutionError, or one of the three typed errors BaseAgent passes through) and becomes the pair's card". Correct INV-19 in the spec the same way.
- **Spec IDs:** EC-27, INV-19, §12.3 rows 6 and 12.

## VERIFIED CLAIMS

1. The pack passes 414 of 414 (S3 report, briefing). **Held.**
2. `python lint/run.py` ends `SDK-LINT: PASS` with no baseline raised. **Held.** There is no diff under `lint/` and no `noqa`, `type: ignore`, or `pragma` was added.
3. The public-API contract is current at 678 exports (§12.5). **Held.**
4. INV-20 and NG-7: no change to the base runtime, `base`, `middleware`, `pipelines`, the root `__init__`, or `contracts/`. **Held:** the diff is empty.
5. S3 changed no test (S3 report). **Held:** `git diff 2cab5070 c1c3ecc0 -- tests` is empty. The test-tree deletions in the PR are all the spec-mandated pin updates listed in test-plan.md "Existing tests updated".
6. The §8.4 budget holds. **Held:**
   - lines after the header: `events.py` 658/660, `launch.py` 455/470, lib records 832/870, the other modules 160 to 374 (≤ 400);
   - 9 package modules, every header ending at line 12;
   - 3 enums, 8 records, 18 constants, 0 settings, 0 dependencies, 0 root exports.
7. INV-7 and AC-23: the public `InfiniteEvents` functions are exactly the 22 kinds, and the 8 new members are appended after `TOOL_REFUSED` in §8.5 order (D-19). **Held.**
8. Deviation 1: the `_in_flight` placement gives identical behaviour on the no-sink path, under the guard, in EC-10, and in EC-25. **Held.** It is also the smallest change: keeping it inside the shield would need a non-literal increment and a 19th constant, which is over budget. I did not re-check the A007 mechanics; that belongs to the conventions lens.
9. Deviation 2: the counters start at 0. **Held** (`INFINITE_MIN_COUNT = 0`). No count starts at 1 where the spec says 0.
10. Deviations 3 to 6 match the spec. **Held:**
    - `tool_refused`'s problem is `str(error)`, as row 5 says, and it equals `exc.message` for `drop_entry`, because `VidbyteSdkError.__str__` is the message.
    - The extra commits change only import order and headers.
    - I found no deviation the implementer did not report, apart from small wording in the `_launched` comment ("by key, for its duration"), which does not change its meaning.
11. AC-1: the §4 snippet runs verbatim. **Held**, with an independent script (`entry_one_line` refusal, two commits, `1 2 0`). The AC-1 test pins the snippet's stdout and its attribute types.
12. G-5 and INV-5 also hold on the refusal, abort, child-error, and replay paths that AC-21 does not cover. **Held** (probe; normalized call ids, stamps, and tmp root).
13. AC-26 and INV-6 hold on a tree with an abort and a rule drop. **Held** (47 events, equal).
14. INV-3 with a sink that raises `ValueError` on `subagent_aborted`. **Held.** The original `RuntimeError` reached the root as "Tool execution failed: entries disk controller fault", and `run_finished.events_failed` was 1.
15. EC-10: the abort phase is `commit`. **Held only on the normal path** (R-C1).
16. INV-10: every launched pair is closed, except in EC-4 and EC-10. **Not held** on two paths the spec does not list (R-C2).
17. Every refusal raise site in §9.1 names its rule (FR-3, INV-12). **Held.** Searching `memory.py` and `workspace.py` for `raise` finds no untagged site except the three constructor `ConfigurationError`s that row 9 excludes. Every message is byte-identical to the base commit.
18. Scope matches request.md §C and the user's words. **Held:**
    - A1 to A8 (A8 folded into B2, per D-6), B1 to B5, C3, D1, and E1 for the root only are all present.
    - The out-of-scope items are absent: no context compaction (C1), no tool-output cut (C2), no model error (E2), and no heartbeat for generators or verifiers.
    - No wall-clock decision was added: `time.monotonic` is used only for `duration_ms`.
    - No hook, middleware, listener, or `AgentMiddleware` was added. `runtime.py` gained only `_launch`, `_announced`, and the private leaf `_announce_denials`, all specified in §8.5.
19. The §5 diagram matches the call path. **Held**, with no divergence: denials, then usage, then progress in the hook; the catch-up before `journal.finish`; `batch_finished` only after the pipeline returns; and a second `InfiniteEvents` built in `run_handoff`.

## COMMANDS RUN

- `git diff --stat origin/main...c1c3ecc0` showed 38 files: 13 under `vidbyte/`, the S2 tests, and the spec documents.
- `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` printed `…\worktrees\vidbyte-sdk-infinite-memory-derived-events\vidbyte\__init__.py`.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` ended `414 passed in 9.74s`.
- `python lint/run.py` ended `S064 RATCHETED: 4 known finding(s)…` and then `SDK-LINT: PASS`.
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` reported `contracts/sdk-public-api.json is current … (vidbyte-sdk 0.4.0, 678 exports).`
- `git diff --stat 2cab5070 c1c3ecc0 -- tests` was empty.
- `git diff --stat origin/main...c1c3ecc0 -- lint/` was empty.
- `git diff --stat 181f1992 c1c3ecc0 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/middleware vidbyte/pipelines vidbyte/__init__.py contracts/` was empty.
- An inspect probe printed `public==kinds: True 22`; the line counts 658, 455, and 832; and 9 package modules.
- Heredoc probes, each run through `ScriptedTree` with only the runner scripted:
  - EC-10 phase on three paths (output under R-C1);
  - `pair_started` raising `OSError` on its second call (output under R-C2);
  - a sink `KeyboardInterrupt` on `subagent_launched` (output under R-C2);
  - the §4 snippet extracted from `spec.md` and run with `exec` (`SNIPPET OK`, 4 lines printed);
  - sink against no sink on model-visible calls (`sink vs none equal: True  none vs none equal: True`) and on workspace files (`files equal: True`);
  - determinism (`equal: True 47`);
  - a sink that raises on abort (`root saw: … Tool execution failed: entries disk controller fault`, `events_failed: [1]`).
- Code searches:
  - `"limit"` appears only in `delegation_limits.py:55,67` (A-1);
  - `call_contexts` is never changed except by `append`;
  - the base-agent pass-through list is at `base.py:967`.
- `git status --short` was empty after the runs: no file in the worktree changed apart from this report.
