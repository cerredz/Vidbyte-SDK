LENS: engineering

VERDICT: MERGEABLE AFTER FIXES — Git hygiene, bounds, the Grok slot and key scrubbing are sound, and mutation tests show their tests can fail. But cleanup survives only one cancel: a second cancel, or an anyio cancel scope, leaks worktree folders and leaves vendor grandchildren running. Separately, several post-I/O and data-edge paths crash or drop the record. Every fix is local, and the main one was validated in scratch.

WHAT THE IMPLEMENTATION GETS RIGHT
- **Git hygiene is tight, and its test can fail.**
  - Every git child goes through `ComposeGit._run` with the fixed prefix.
  - The 15 location variables are removed, and `GIT_INDEX_FILE` is set only for snapshots.
  - Diffs are tree-to-tree with `--no-ext-diff --no-textconv`.
  - The hygiene test fails under both wrong-cwd mutations. One of them would rewrite the user's real index.
- **The Grok slot (INV-13) is right.**
  - It is a one-slot Semaphore keyed by the same normcase-of-resolved-workspace string the base uses for Grok's private home (`grok/threads.py:141`).
  - It is taken per call and released on every path.
  - In the local Python 3.11.0, a waiter cancelled after being woken gives the slot back (`locks.py:389-394`).
  - The map holds weak values, so it cannot grow.
  - Dropping the slot fails 2 AC-11 tests.
- **Single-cancel cleanup works.**
  - Removals are shielded tasks, and `__aexit__` waits out a cancel that lands mid-removal.
  - fan_out cancels its siblings and awaits them.
  - AC-10 passes.
  - A 120-trial cancel sweep over `add_worktree` left no registration, folder or task behind. 26 of those cancels landed inside `worktree add` and 37 inside `read-tree`.
- **Bounds and scrubbing hold.**
  - There is no sleep, deadline or backoff (INV-22).
  - Each git child is capped at 120 s and 16 MiB, and the diff caps apply after a full bounded read.
  - A truncated answer is never decoded.
  - Keys are scrubbed from spliced text and from git text, and both scrubs are pinned by tests: mutations m6 and m7 fail 3 and 1 keys tests.

FINDINGS (ranked)

R-E1 [Blocker] [failure modes] vidbyte/harnesses/native/compose/calls.py:79-81 — Cleanup survives only one cancel: after a second cancel or an anyio cancel scope, the composite returns while removals are still pending, and worktree folders and live vendor grandchildren are left behind
  Evidence:
  - **Double cancel.** `test_second_cancel_during_fan_out_cleanup` runs verify_with with two held opencode verifiers that each have a grandchild, cancels, then cancels again 0.05 s later. In 3 of 3 runs both `vidbyte-compose-worktree-*` folders were still in TMP after every task had settled. The registrations were gone. Gaps of 0 s, 0.2 s and 0.5 s were clean.
  - **What the removal sees.** In the instrumented run, both removals start with 0 live leaders and 2 live grandchildren. Both raise WORKTREE_FAILED, and `__aexit__` swallows it because a CancelledError is in flight (workspace.py:146-149).
  - **anyio.** I cancelled an `anyio.CancelScope` around verify_with (anyio 4.14.1 is installed; it re-delivers the cancel to the host task on every loop turn).
    - At return: `worktrees=3`, both folders present, 4 pending tasks, 2 live grandchildren.
    - After everything settled: registrations gone, both folders leaked, 2 grandchildren still alive. 2 of 2 runs; the Grok+opencode variant leaked 1 folder.
    - An opencode planner in run_ensemble under the same cancel leaked its folder and its grandchild.
  - **Direct sweep.** An `add_worktree` sweep with a second cancel 20 ms after the first returned while the removal task was still running in 5 of 100 trials, with a registration or folder present at return. It also logged one "Task exception was never retrieved" for an orphaned WORKTREE_FAILED.
  - **Mechanism, in four steps:**
    1. fan_out's `finally` awaits `asyncio.gather(*tasks, return_exceptions=True)` (calls.py:81). A second cancel cancels the gather, and gather then cancels every child again in the middle of its cleanup.
    2. That second cancel interrupts the base's `ProcessStopper.stop_tree` (runner.py:41-73). Its `finally` closes the transport of the taskkill that is still running, and closing a running process's transport kills it (base_subprocess.py:106-117).
    3. So the grandchildren survive, and they hold the worktree folder as their working directory while `remove_worktree` runs.
    4. Meanwhile fan_out propagates the cancel before its children have finished.
  - **The other cleanup sites.**
    - `__aexit__` waits only once (`await asyncio.wait({removal})`, workspace.py:142), and that wait can itself be cancelled.
    - The failure paths in `add_worktree` (git.py:174-175) and `__aenter__` (workspace.py:124-125) do not wait at all after a second cancel.
    - Readers that run in the composite's own task (the planner, the selector, `in_worktree`) receive every re-delivered cancel directly inside the base's stop.
  Failure:
  - INV-14 says "every running child is cancelled, the nine functions stop its process tree, its worktree is removed … No task outlives the composite call". EC-17 says "No leftover registration or folder".
  - Both break on any double cancel, and for every caller hosted on anyio, such as MCP servers and Starlette apps.
  - Each leaked folder is a full copy of the working tree, and vendor grandchildren keep running after the call returns. Nothing reports the leak.
  Smallest fix:
  - Add one settle helper. It cancels its tasks once, then loops `await asyncio.wait({t for t in tasks if not t.done()})`.
    - It catches each later CancelledError and never cancels the tasks again.
    - When every task is done, it re-raises the CancelledError object it caught. A fresh `CancelledError()` escaped anyio's scope in my probe.
  - Use the helper in three places:
    1. in fan_out's `finally`, instead of gather;
    2. for each worktree reader that runs in the composite's own task (the planner and the selector), run as a one-child fan-out;
    3. around the removal task in `__aexit__` and in the two failure paths.
  - Validated in scratch with plugin `fix_settle` (the fan_out half) plus `fix_planner_isolated` (the one-child planner):
    - all four probes end with `worktrees=1`, `leftovers=[]`, 0 pending tasks and 0 live pids;
    - the pack still passes, `276 passed`.
  - Add two tests: the AC-10 setup with a second cancel at +0.05 s, and an anyio CancelScope variant. Both assert at return `worktrees()==1`, `leftovers()==[]`, no pending tasks and no live stand-in pid.
  - Follow-up outside the diff: `CliRunner.run`'s cancel path should always finish `stop_tree`.
  Spec IDs: INV-14, EC-17, INV-9, FR-15, D-17

R-E2 [Major] [failure modes] vidbyte/harnesses/native/compose/git.py:188 — A kill during `worktree add` leaves the registration locked "initializing"; one `--force` cannot remove it, `git worktree prune` never removes it, and compose hides the failure
  Evidence:
  - **Part A of `probe_f1_locked.py`** (a real worktree with its `locked` file set to "initializing"):
    - `ComposeGit.remove_worktree` raises worktree_failed: "fatal: cannot remove a locked working tree, lock reason: initializing / use 'remove -f -f' to override or unlock first".
    - It deletes the folder, but the admin entry stays.
    - `git worktree prune -v` prunes nothing, and `git worktree list` still shows "locked initializing".
    - `remove -f -f` followed by `prune` clears it.
  - **Part B** (a real cancel on Windows, with the window widened by a 3 s `reference-transaction` hook; EC-59 says such a hook runs during `worktree add`):
    - `add_worktree` raised CancelledError, and its suppressed removal (git.py:174) failed.
    - `vidbyte-compose-worktree-…` (HEAD 0000…) is still locked after prune.
  - **Without a hook**, the window is git's own update-ref child: git writes `locked` before spawning it and unlinks the file afterwards.
    - `taskkill /F` skips git's junk-removal handler. POSIX sends SIGTERM first, which runs that handler.
    - My 1 ms sweep landed 39 cancels inside `worktree add` and never hit the window, so it is narrow but real.
  Failure:
  - EC-17 ("No leftover registration") breaks permanently, and nothing reports it.
  - Each hit adds one locked entry to `.git/worktrees`.
  - The WORKTREE_FAILED next step ("run git worktree prune") cannot clean it.
  Smallest fix:
  - Pass `worktree remove --force --force <folder>`. This is git's documented override for a locked worktree, and it is safe because compose only ever removes folders it created.
  - Update the §9.2 row, the INV-9 text and the hygiene test's word index (`[3]` becomes `[4]`, test_harness_compose_git.py:182).
  - Add an EC-17 test that cancels inside a hook-widened `worktree add`. The AC-10 test cancels only after add and fill have finished.
  Spec IDs: EC-17, INV-9, EC-16, §9.2

R-E3 [Major] [failure modes] vidbyte/harnesses/native/compose/texts.py:159 — A lone surrogate in one step's answer crashes the prompt fit on win32 when the next step is Grok or Muse, losing the record, and leaves the opencode child running when the next step is opencode
  Evidence:
  - **How a lone surrogate arises.** `json.loads` of a vendor's `\ud83d` escape yields a lone code point. A surrogate pair split across two JSON text parts stays two lone code points (probe: len 2).
  - **The crash in compose.** `RecordFieldValidator.command_line_units` (validation.py:81, strict `utf-16-le`) raises UnicodeEncodeError, and so does `PromptFitter.fit` for a GROK step on win32.
  - **End to end.** `chain_threads([opencode answering "answer \ud83d end", grok])` raises UnicodeEncodeError with no ChainResult, and the Grok step never launches.
  - **When the next step is opencode**, the base records `runtime.error` ("An unexpected UnicodeEncodeError…").
    - But the opencode child (pid 28364) was still alive 2 s after the chain returned, blocked on a stdin pipe that is never closed.
    - Cause: runner.py:330 encodes the prompt after launch, and `run` stops the process tree only on timeout or cancel.
  - **POSIX, Grok or Muse.** `os.fsencode` raises ValueError inside `launch`, which becomes OS_ERROR, a closed failure. This is from the CPython source, not probed.
  - **In run_ensemble**, the same crash happens at the implementer's fit (ensemble.py:120), after every read-only stage has run.
  Failure:
  - Open item 4, answered: it is a crash in compose-owned code on win32 and a closed failure that leaks a process elsewhere.
  - Either way a step fails, or the composite crashes, because of a spliced value. INV-18 says that never happens, and the record that INV-15 promises is lost.
  Smallest fix:
  - In `PromptFitter._scrub` (texts.py:162-168), after removing NULs, add `text = text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")`. This rejoins split pairs and turns lone halves into U+FFFD.
  - Add a chain test with a lone-surrogate answer before a Grok step.
  - Base follow-up: encode the stdin text before launch.
  Spec IDs: INV-18, INV-15, INV-4 (the send-time scrub), open item 4

R-E4 [Major] [failure modes] vidbyte/harnesses/native/compose/steps.py:119 — Derived steps are re-validated, and diff paths must be non-blank; both raise a bare ConfigurationError after I/O and drop the record
  Evidence:
  - **Deleted skill, opencode verifier.** In my probe the writer removes a skill folder, inside the repository, that an opencode verifier uses.
    - `relocate` uses `replace`, which re-runs ThreadStep's NativeThreadRequest probe (native_compose.py:102-113).
    - It raises `ConfigurationError: skills[0] must be an absolute path to an existing directory…`, which leaves verify_with with no record.
  - **Same skill, Grok verifier.** It is recorded as an ordinary failure: `failed_verifiers=(0,)`, `configuration.invalid_argument`.
  - **Blank path.** `ComposeGit.diff` against a tree holding the path " " raises `ConfigurationError: WorkspaceDiff.files must hold non-blank paths.` (native_compose.py:145). A writer on POSIX can create such a file.
  - **Other derived steps.** `anchor` and `rung` (steps.py:114, :124) re-validate the same way: a selector turn, or a ladder rung after an attempt removed a skill folder.
  Failure:
  - INV-15 allows a ConfigurationError only before any I/O. Here the writer has already changed the workspace, and its outcome, thread id and diff are lost.
  - The message names `skills[0]`, not `verifiers[0]`.
  - Inside fan_out this is an EC-19 trigger: it cancels the sibling verifiers.
  Smallest fix:
  - Build derived steps without re-checking paths they do not change, for example with a private constructor that validates only the changed field.
    - A missing skill then surfaces as the nine function's own recorded NativeThreadError, as it already does for a Grok reader.
  - Drop the non-blank rule on `WorkspaceDiff.files`, since git allows such names, or keep only "non-empty".
  Spec IDs: INV-15, INV-5, EC-19

R-E5 [Major] [test quality] vidbyte/harnesses/native/compose/calls.py:73-91 — No test can fail for INV-14's sibling-cancel rule: rewriting fan_out as a plain gather still passes all 276 tests
  Evidence:
  - **The mutation.** Plugin `m4_fanout` replaces fan_out with `tuple(await asyncio.gather(*children))`. EC-19 says this pattern "would leave siblings running". The pack still reports `276 passed in 48.26s`.
  - **The test plan's reason.** Test-plan row 143 skips EC-19, saying there is "No seam … failing one sibling's worktree needs a git hook". Two non-mock seams exist:
    - a `reference-transaction` hook that exits 1 makes `worktree add` fail cleanly (probe: "fatal: ref updates aborted by hook", exit 128, nothing left behind), and T-6 accepts hooks;
    - the R-E4 skill trigger.
  - **Another option.** Patching the `ComposeGit.add_worktree` leaf for one call is not mocking fan_out.
  - **Why AC-10 still passes** under the mutation: gather forwards the caller's cancel to its children.
  Failure:
  - A regression to gather, or a dropped cancel loop, would ship green.
  - The one-exception, siblings-stopped, worktrees-removed guarantee, which is the reason D-17 exists, is not verified by any test.
  Smallest fix: add one test with two opencode verifiers.
  - One verifier is held and has a grandchild.
  - The other fails at `worktree add`, through a sandbox hook that fails the second add.
  - Assert that the composite raises that one ThreadComposeError only after the held tree is dead, with `worktrees()==1`, `leftovers()==[]` and no pending tasks.
  Spec IDs: INV-14, EC-19, D-17, FR-15

R-E6 [Major] [security] vidbyte/harnesses/native/compose/chain.py:46 — A short invalid prompt or template that contains a bound key is quoted, key included, in compose's ConfigurationError
  Evidence:
  - **Probe** with a 12-character key: `chain_threads(prompt="use <key>\x00")` raises `prompt must match [^\x00]+; got 'use vbk-k3y-9d2f\x00'.`
  - The chain template, the verify prompt and a staged template give the same result. All 4 of 4 messages hold the key.
  - **Where the quote comes from:** `_received` (validation.py:159-167), reached from six sites: chain.py:46 and :106, verify.py:51, ensemble.py:54, answers.py:57-58 and stages.py:103.
  Failure:
  - **Rules broken:**
    - spec line 269 ("its message never quotes a key");
    - INV-4 ("any ConfigurationError compose raises");
    - AC-15. Its tests pass because they do not cover this case.
  - **Impact is narrow:**
    - the key gets in only through the caller's own invalid text, and only when its repr is 80 characters or fewer;
    - a direct call to the base quotes the same way.
  - I rate it Major for that reason. Under the weighted-word rule it could be promoted to Blocker.
  Smallest fix:
  - Check caller texts without quoting them. Either add a `quote: bool = True` keyword to `require_text` and pass `quote=False` at the six sites, or use `accepts_text` and raise a compose refusal that names only the argument.
  - `require_template` already takes that second approach.
  Spec IDs: INV-4, AC-15, INV-5 (the refusal rule, spec line 269)

R-E7 [Major] [data and scale] vidbyte/harnesses/native/compose/verify.py:142-143 — On EC-16, a verifier or proposer loses its own finished answer, while the planner and the selector keep theirs
  Evidence:
  - **Where the answer is kept.** When the worktree cannot be removed, `_plan` (ensemble.py:199-207) and `select` (selection.py:93-98) attach the finished answer to the error.
  - **Where it is lost.**
    - `_review` (verify.py:142-143) and `_propose` (ensemble.py:220-222) return from inside `async with`, so WORKTREE_FAILED replaces the finished answer. This happens even with a single verifier.
    - With several readers, fan_out (calls.py:85-90) also drops the siblings' finished values.
    - verify_with then attaches only `VerifyResult(writer=…)` (verify.py:89-93).
  - This confirms implementer open item 2, and the loss is broader than the report says.
  Failure:
  - A finished, paid-for verdict or proposal is thrown away.
  - EC-16 says the error's `result` "holds the record so far", but that is true only for the planner and the selector.
  - On Windows this is easy to reach: a reader whose grandchild outlives it is enough (see R-E1).
  Smallest fix:
  - Mirror `_plan` in `_review` and `_propose`: attach the finished answer to the error, and have verify_with and run_ensemble merge it into the record.
  - Keeping the sibling answers too would need a partial-result shape for fan_out [scope-adding].
  Spec IDs: EC-16, INV-15, INV-14

R-E8 [Minor] [data and scale] [scope-adding] vidbyte/harnesses/native/compose/git.py:126-134 — Every snapshot re-hashes the whole working tree; a stat-seeded temporary index gives the same tree id about 40 times faster at 100,000 files
  Evidence: `probe_scale.py`, warm cache, 2 KB files:

  | Files | Compose snapshot (best of 3) | Real-index `git status` | `copy2`-seeded temporary index (`add -A` + `write-tree`) |
  |---|---|---|---|
  | 2,000 | 0.29 s | not measured | not measured |
  | 20,000 | 0.46 s | not measured | not measured |
  | 100,000 | 2.36 s | 0.11 s | 0.06 s, same tree id |

  verify_with takes 3 snapshots, so it pays about 7 s at 100,000 files.
  Failure:
  - None against the spec: EC-66 is an accepted limitation.
  - A-6 holds by a wide margin, and is now measured.
  - The cost grows linearly with the bytes that are not ignored.
  Smallest fix (follow-up):
  - Seed the temporary index with a `copy2` of `.git/index`, which keeps its mtime so git's racy-entry check still holds. Fall back to `read-tree HEAD`.
  - INV-7's wording has to change, because the real index would then be read, though never written.
  Spec IDs: INV-7, EC-66, A-6

VERIFIED CLAIMS
1. **Baseline.** The compose pack reports `276 passed in 43.62s`, matching the expected 276.
2. **INV-13.**
   - The slot is keyed by (running loop, normcase of the resolved workspace). That matches the base's Grok home key, so the lock covers exactly the calls that share a home, and it is never used across loops.
   - It covers one step call, and each repair turn takes it again.
   - The local Python 3.11.0 `Semaphore.acquire` gives back a slot whose waiter was cancelled after being woken.
   - Mutation m2 (no slot) fails `test_grok_verifiers_on_one_workspace_take_turns…` and `test_composites_serialize_grok_per_workspace…`.
3. **INV-3.**
   - The only invoke sites are calls.py:97 and :99, so every step call runs through `ComposeCalls.call`, then `_invoke`, then `ThreadBinder.invoke`.
   - Mutation m3 (an alias accepts any harness) fails 3 validation cases: pair step, trio reader and trio writer on the wrong harness.
4. **INV-26.**
   - `_run` (git.py:195-212) builds the prefix, `env_remove`, an overlay limited to `GIT_INDEX_FILE`, the 120 s bound and the 16 MiB bound.
   - Mutations m1 (diff run from the workspace) and m1b (the verifier's `read-tree <S0>` run in the real repository) each give `1 failed, 25 passed`, and only the hygiene test fails each time. That test is load-bearing and it can fail.
5. **INV-4 scrubs.** Mutation m6 (keys left in spliced text) fails 3 keys tests, and m7 (`ComposeFailures` keeps keys) fails 1. The one exception is R-E6.
6. **INV-22.** There is no sleep, `wait_for`, timeout or backoff in compose (grep). The only time bound is `COMPOSE_GIT_TIMEOUT_SECONDS`.
7. **INV-12 and INV-11.**
   - verify's writer runs between two snapshots, before the fan-out (verify.py:67-83).
   - The implementer runs only after the backstop (ensemble.py:104-120).
   - The backstop runs after every child's `__aexit__`.
8. **Single cancel.**
   - AC-10 passes.
   - The single-cancel sweep (120 trials, 79 cancels) left no registration, folder or orphan task.
   - The leaks appear only with repeated cancels (R-E1), or with the locked window (R-E2).
9. **Open item 3** (a blank `{previous}` prompt) is confirmed by reading texts.py:131-140.
   - At share 0 an empty value is kept as it is, and `best` is returned without a fit check, so the step is sent a blank prompt and records `configuration.invalid_argument`.
   - This is a spec-level gap, which I leave to the conformance lens.
10. **Diff caps** (git.py:155-158).
    - 2,000 names and 100,000 characters, taken from a read bounded at 16 MiB.
    - A name cut at the byte boundary can reach the first 2,000 names only if names average 8 KiB or more.
11. **D-28, settled, not a finding.**
    - The base accepts a one-character key.
    - `_scrub` then rewrites `+export function fix(x)` as `+e[redacted]port function fi[redacted]([redacted])`.
    - That matters for a dummy key against a local opencode provider.

COMMANDS RUN
- **Baseline pack.** `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose` gave `276 passed in 43.62s`.
- **Lone-surrogate unit probe.** `python -W ignore <scratch>/probe_f7_units.py` gave:
  - `command_line_units(lone) -> RAISES UnicodeEncodeError 'utf-16-le' … surrogates not allowed`;
  - `PromptFitter.fit grok on win32 -> RAISES UnicodeEncodeError`;
  - `fit opencode -> 'Review this: answer \ud83d end'`;
  - `CliRunner.run RAISES UnicodeEncodeError 'utf-8' …`;
  - `child still running after 1 s: True`.
- **Single-cancel sweep.** `<scratch>/probe_f1_cancel.py <scratch> single 120 1` gave:
  - `stats: {'trials': 120, 'cancelled': 79, 'left_registration_at_return': 0, 'left_folder_at_return': 0, 'orphan_removals': 0}`;
  - `git commands interrupted by a cancel: {'worktree add': 26, 'read-tree': 37}`.
- **Double-cancel sweep.** `<scratch>/probe_f1_cancel.py <scratch> double 100 1` gave:
  - `stats: {'trials': 100, 'cancelled': 75, 'left_registration_at_return': 1, 'left_folder_at_return': 2, 'orphan_removals': 5}`;
  - `1 Task exception was never retrieved`.
- **Locked-registration probe.** `<scratch>/probe_f1_locked.py <scratch>` gave:
  - `[A] remove_worktree raised worktree_failed | git: fatal: cannot remove a locked working tree, lock reason: initializing`;
  - `[A] prune -v: (nothing pruned)`;
  - `[B after prune] admin entries: [('vidbyte-compose-worktree-y6yanfkf', 'initializing')]`.
- **Edge probes.** `PYTHONPATH=$(pwd) python -m pytest -q -s -p tests.features.harness_compose.conftest <scratch>/test_s4_probes.py` gave:
  - `F2 chain prompt: key in message = True` (and the same for chain template, verify prompt and staged template);
  - `F7 grok next: RAISED UnicodeEncodeError | has record: False`;
  - `F5 opencode verifier: RAISED ConfigurationError | has record: False`;
  - `F5 grok verifier: RETURNED writer.ok=True failed_verifiers=(0,)`;
  - `blank path: RAISED ConfigurationError | WorkspaceDiff.files must hold non-blank paths.`
- **Second cancel**, `-k second_cancel`, run 3 times: `gap=0.05: after the orphans ran: worktrees=1 leftovers=['vidbyte-compose-worktree-7s5mxdi3', 'vidbyte-compose-worktree-ekvidohq']`, with 2 leftovers in each run.
- **Leak mechanism**, `-k mechanism`:
  - `MECH removal starts: live leaders=0 live grandchildren=2` (twice);
  - `MECH removal raised ThreadComposeError: Compose failed with worktree_failed…`.
- **anyio**, `-k anyio`:
  - `ANYIO opencode: scope cancelled; at return: worktrees=3 leftovers=[2 folders] pending tasks=4 live leaders=0 live grandchildren=2`;
  - `after everything settled: worktrees=1 leftovers=[2 folders] live=2`.
- **anyio planner**, `-k anyio_cancel_scope_planner`:
  - unpatched: `leftovers=['vidbyte-compose-worktree-dlvl7msk'] … live grandchildren=1`;
  - with `-p fix_settle -p fix_planner_isolated`: `worktrees=1 leftovers=[] pending tasks=0 live leaders=0 live grandchildren=0`.
- **Candidate fix on the probes.** `-p fix_settle -k "second_cancel_during or anyio"` gave every case at `worktrees=1 leftovers=[] pending tasks=0`, and `6 passed`.
- **Candidate fix on the pack.** `-p fix_settle tests/features/harness_compose` gave `276 passed in 43.84s`.
- **Mutations**, run with `PYTHONPATH="<wt>;<scratch>"` and `-p <plugin>`:
  - m1_diff_cwd and m1b_index_cwd: `1 failed, 25 passed` each (the git hygiene test);
  - m2_nolock: `2 failed, 11 passed`;
  - m3_alias: `3 failed, 115 passed`;
  - m4_fanout: `276 passed in 48.26s`;
  - m6_scrub: `3 failed, 1 passed`;
  - m7_gitscrub: `1 failed, 3 passed`.
- **Orphan check.** `-k orphan_check` gave:
  - `ORPHAN processes of the second step alive right after the chain returned: [28364]`;
  - `ORPHAN alive 2 s later: [28364]`.
- **Snapshot scale.** `<scratch>/probe_scale.py <scratch> 100000 2000` gave:
  - `compose snapshot: 2.36s (best of 3)`;
  - `git status with the real index: 0.11s`;
  - `stat-seeded temporary index add -A + write-tree: 0.06s, same tree: True`.
  - The 20,000 and 2,000 runs gave 0.46 s and 0.29 s.
- **Hook seam.** A throwaway repository with a failing `reference-transaction` hook, followed by `git worktree add --detach --no-checkout`, gave `fatal: ref updates aborted by hook`, `exit=128`, 0 admin entries and no folder.
- **Diff size.** `git diff --stat origin/feat/native-grok-opencode-meta-hosts...e1bf20d8` gave `80 files changed, 12252 insertions(+), 28 deletions(-)`.
- **File locations.** `<scratch>` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s4-engineering/`. Every probe used throwaway repositories under `<scratch>` or the sandbox fixture; none touched the worktree's own `.git`.
