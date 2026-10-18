# Feature: Composite thread functions

## High-Level Feature Description

`vidbyte.harnesses.native.compose` puts the nine harness thread functions (`run_`, `continue_` and `fork_` for Grok Build, opencode and Muse Code) together into larger workflows. It has five composites: `chain_threads`, `verify_with`, `handoff_thread`, `run_staged_threads` and `run_ensemble`. It also has nine aliases generated from the chain and verify composites, the binders `bind_thread` and `bind_continue`, and the helpers `capture_diff`, `in_worktree` and `parse_json_answer`. A composite takes caller-bound `ThreadStep`s, each of which is one of the nine functions plus the caller's own key, workspace, model, skills and config. It runs every step through that function unchanged and returns every step's result or error. The real `git` takes the snapshots, diffs and disposable worktrees that keep reader steps from changing the workspace.

## Contract

- Binding: `bind_thread` accepts the three `run_*` and three `fork_*` functions, and `bind_continue` accepts the three `continue_*` and three `fork_*` functions. Each binder checks every argument when the step is built. The step's key never shows in a `repr`, and `await step(prompt)` makes exactly one call to the bound function.
- Validation: every composite checks its whole input before it starts any git command, step or temporary folder. A refusal is a `ConfigurationError` whose `details["field"]` names the argument path (`steps[1]`, `verifiers[0]`, `stages[0].template`, `roster.proposers[0]`, `opencode`, `prompt`, …) and whose message never holds a key.
- Git: `git` is needed exactly when a diff, a phase snapshot or a worktree is needed, and its failures are a `ThreadComposeError` with a closed `ThreadComposeProblem`. Snapshots never touch the working tree, the real index, `HEAD` or a ref.
- One writer: in `verify_with` only the writer, and in `run_ensemble` only the implementer, may change the workspace. Grok readers run in place in `PLAN` or `DEFAULT` mode. opencode and Muse readers run in their own disposable worktrees. A snapshot backstop turns any change during a read-only phase into `READER_CHANGED_WORKSPACE`.
- Results: a composite returns its record however many steps failed. It raises only `ConfigurationError` (before any I/O), `ThreadComposeError` (with the record so far), `asyncio.CancelledError`, or a defect.
- Prompts: every text sent to a model comes from the 22 Markdown files in `compose/prompts/`. Spliced values are never parsed as templates, have every bound key replaced by `[redacted]`, lose their NUL characters, have their surrogate halves repaired, and are shortened to fit the receiving harness.
- Structured answers: an answer goes through `parse_json_answer` with at most two repair turns on the same thread. A cut answer is never decoded.

## Actors / Callers

Python callers of `vidbyte.harnesses.native.compose`. Underneath it are the nine functions of `vidbyte.harnesses.native`, `CliRunner` and `CliArgv` in `vidbyte.lib.process` (for git as well as the vendors), and the new lib modules `vidbyte.lib.dataclasses.native_compose`, `vidbyte.lib.dataclasses.native_ensemble`, `vidbyte.lib.enums.native_compose`, `vidbyte.lib.constants.native_compose`, `vidbyte.lib.util.json_text` and `vidbyte.lib.util.secret_text`. The error is `ThreadComposeError` in `vidbyte.lib.errors`.

## Inputs and Preconditions

The tests run offline only. Every vendor program is the base pack's stand-in `tests/features/harness_threads/fake_harness.py`. Each bound step points at its own scenario of the stand-in through its config's `<harness>_command`. AC-1 instead puts `.exe` (win32) or script (POSIX) stand-ins on `PATH`. The real `git` is reachable on `PATH`: on win32 its Git for Windows folder is appended, and on POSIX a symbolic link inside the sandbox is used. The machine's git configuration is shut out with `GIT_CONFIG_NOSYSTEM=1`, an empty `GIT_CONFIG_GLOBAL` and `GIT_CEILING_DIRECTORIES` set to the sandbox root, and the 15 repository-location variables are removed. The user home and the temporary folder point into the sandbox, so compose's worktrees and temporary indexes land outside every test repository. Two tests make one fan-out child fail from outside compose with a `reference-transaction` hook that the sandbox repository's own `core.hooksPath` names (EC-59: compose's git still runs it during `worktree add`), and one more makes the add slow instead, pausing in that hook while git holds the new registration's lock. Three tests keep a reader's worktree folder from being deleted, from outside compose: on win32 they hold a file open inside it, and on POSIX they take write permission away from a folder inside it, so as root, where permissions do not hold, they skip. The stand-in's `delete_paths` field deletes a skill folder while a step runs, so a step compose derives later meets a folder that is gone. Its `term_linger` field makes a POSIX stand-in outlast SIGTERM until the forced kill, so a second cancel lands inside its stop. No real key, network or vendor CLI is used.

## Observable Outcomes

- The returned records and the raised errors (their attributes and the order of the parts of their messages).
- What each stand-in process received. Its log holds the argv, cwd, stdin, credential digests, the scenario `label` and launch `turn`, the files it wrote, and digests of the files it found.
- A spy around `CliRunner.run` that records every git and vendor child: its argv, cwd, environment overlay and removals, and the order of its start and finish.
- git state: `status`, `worktree list`, the bytes of the real index, `HEAD` and the refs.
- What is left in the sandbox's temporary folder, and which processes are still alive.

## State Transitions

- The workspace changes only through writer steps: chain, handoff and stage steps, the verify writer and the ensemble implementer.
- Snapshots add only unreachable git objects.
- A reader's worktree exists from just before its first turn to just after its last turn, and also goes away on failure and cancellation.
- A Grok step call holds its loop-and-workspace lock for that one call.
- A JSON answer moves from its first turn through at most two repair turns on the same thread.
- A stage moves from rung to rung only on `RAISE_EFFORT`.
- An ensemble moves from plan to propose, select (with a narrowing round when more than five proposals succeed), the backstop, and implement.

## Invariants

The spec's INV-1 to INV-36 (`docs/spec/native-thread-compose/spec.md` §6.1). These tests pin most directly:

- the 42-name surface and the alias signatures (INV-1, INV-24);
- the binders' six functions and their checked fields (INV-2);
- steps only, validation first and no I/O after a refusal (INV-3, INV-5);
- key hygiene (INV-4);
- git as a closed failure, with its message order (INV-6);
- snapshots and diffs (INV-7, INV-8);
- worktree readers, Grok readers and the backstop (INV-9 to INV-11);
- one writer and the Grok lock (INV-12, INV-13);
- fan-out, partial success and early stop (INV-14 to INV-16);
- splicing, prompt fit and structured answers (INV-17 to INV-19), with every record bounded (NFR-8);
- the prompt files (INV-20);
- stage retries with no sleep (INV-21, INV-22);
- the ensemble shape (INV-23);
- agreement (INV-25);
- git hygiene (INV-26);
- a composite step starting exactly the process a direct call starts (INV-28, INV-31);
- the command-line unit count keeping the existing check's results and errors (INV-36).

## External Dependencies

At test time there are three:

- The real `git`, 2.17 or later, which must be on the machine's `PATH` when the tests start. Without it, the tests that need a sandbox skip.
- pip's distlib `t64.exe` launcher, which builds AC-1's `.exe` stand-ins and the hook tests' `.exe` hooks on win32. Those tests skip when pip does not ship it.
- anyio, which httpx installs but the project does not declare. The cancel-scope test imports it with `pytest.importorskip` and skips without it.

## Known Failure Modes

Each is an input and state that leads to a wrong output, and each has a test here:

- A verifier that writes: a Grok `PLAN` verifier's edit is accepted silently, or an opencode or Muse verifier's edit reaches the workspace under review.
- Cut answers: a cut answer whose prefix still decodes is graded as a verdict.
- Repair turns: a repair turn starts a new thread or runs outside the reader's worktree, or an error on a repair turn is followed by another turn.
- Keys:
  - a key that one model printed, or a writer saved into a file, reaches another vendor's prompt;
  - a key string passed as a step is quoted in the refusal;
  - a key inside a caller's prompt, template, schema, thread id or model is quoted in the refusal of that text;
  - a key is shown by a `functools.partial` `repr`;
  - a key inside git's error text, or in the name of a file a reader changed, is shown by a `ThreadComposeError` message.
- Git:
  - a snapshot built with the real index, which changes what the user staged;
  - a caller's `GIT_DIR` or `GIT_INDEX_FILE` that points the snapshots at another repository;
  - a hostile `diff.external` or textconv that runs during a diff;
  - a caret argument that cmd.exe strips.
- Worktrees: a worktree left registered or on disk after a raise or a cancel.
- Removal: a reader worktree that cannot be removed after its reader answered drops the finished verdicts or proposals and their thread ids from the error's record, or leaves a running sibling, a task or a registration behind.
- Derived steps: a verifier relocated into its worktree, a repair turn anchored on its thread or a stage attempt on a ladder rung is checked again after I/O, so a skill folder deleted meanwhile raises a bare `ConfigurationError` and the record is lost.
- Fan-out: when one child's worktree cannot be added, a sibling left running or a task left pending as the error propagates, or the error held back until the sibling ends by itself.
- Repeated cancels: a second cancel during cleanup, or an anyio cancel scope that cancels again and again, cuts the stops and removals short, so a process, a task, a folder or a registration outlives the call.
- Slow adds: a cancel during a slow worktree add stops git, which on Windows leaves the registration locked as "initializing".
- Diffs: earlier uncommitted edits mixed into the writer's diff, a new untracked file missing from it, or diff paths made relative to a subfolder workspace.
- Concurrency: Grok verifiers on one workspace overlapping, or one lock per composite instead of per workspace.
- Stopping:
  - a chain that goes on after a failed step;
  - a stage retry that sleeps, stays on the wrong rung or reuses a thread;
  - an ensemble that runs its selector after every proposal failed, or skips the backstop after an early stop.
- Spliced text:
  - a 100,000-character answer that makes the next Grok step fail;
  - ten long proposals cut first come, first served, so later ones reach the selector as their note alone;
  - a NUL that makes the next step refuse its prompt;
  - a surrogate half in an answer that makes the next Grok or Muse step raise `UnicodeEncodeError` with no record, or leaves an opencode child running;
  - an answer full of quotes cut by characters only, so on win32 the next Grok step exceeds the command-line unit ceiling;
  - braces in model output that are parsed again as a template.
- Templates: a template that is blank once its spliced values are empty is accepted, so a blank answer later sends the next step a blank prompt; or a template that holds `{prompt}` is refused as blank.
- Caller text: a surrogate code point in the caller's prompt, a template or a schema raises `UnicodeEncodeError` instead of a refusal that names the argument.
- Aliases: an alias that silently ignores a misspelled step keyword.
- Missing preconditions:
  - an untracked nested repository with no commit that fails the snapshot after the writer ran, without the record so far;
  - a worktree reader in a repository with no commit, refused only after the writer has already edited files.

## Historical Regressions

2026-10-17: none yet. The pack was written at S2 of the spec pipeline, before the implementation existed, and every test was proven red against the base commit (`docs/spec/native-thread-compose/test-plan.md`, Red run).

2026-10-18: after S5 repair 1, each fix that only scratch probes had proven got a test here that fails on S3's code (`e1bf20d8`) and passes on the repair (`docs/spec/native-thread-compose/test-plan.md`, Coverage added after S5 repair 1):

- R-8: a reader worktree that could not be removed lost every finished answer from the error's record.
- R-15: a step compose derived after I/O was checked again and raised a bare `ConfigurationError`.
- R-10: a second cancel, or an anyio cancel scope, cut the cleanup short.
- R-14: a cancel during a slow worktree add left a registration locked.
- R-12: a surrogate half in an answer crashed the next step's prompt, or left its opencode child running.
- R-13: a template blank without its spliced values was accepted, and a later step was sent a blank prompt.
- EC-81, from R-12: a surrogate code point in caller text raised `UnicodeEncodeError` instead of a refusal.
- AC-22: `SecretText`, which S5 repair 1 added, is pinned as a `vidbyte.lib.util` export.

## Test Suite Map

- `test_harness_compose_acceptance.py`: the spec §4 snippet run as written against stand-ins on `PATH` (AC-1).
- `test_harness_compose_surface.py`: the 42 names and the lib exports (`SecretText` among them), the vocabularies, the function kinds and parameters, the alias signatures, a side-effect-free import, and the import layering (AC-22, INV-1, INV-24, INV-27, INV-32).
- `test_harness_compose_prompts.py`: the 22 prompt files, their field sets, the ported files' forbidden texts, the 12,000-character room and the package-data entry (AC-21 static part, INV-20, NFR-11).
- `test_harness_compose_binding.py`: the binders' six functions, the checked fields of a step, direct calls, the `invoker` rules and the same child process as a direct call (INV-2, INV-3, INV-28, INV-31, EC-43, EC-44, EC-78).
- `test_harness_compose_validation.py`: every invalid input refused before any I/O, a template blank without its spliced values and caller text holding a surrogate among them, alias arguments bound first, and the command-line unit count unchanged (AC-14, INV-3, INV-5, INV-36, EC-39 to EC-48, EC-62, EC-76, EC-77, EC-79, EC-81).
- `test_harness_compose_chain.py`: the pair alias with answer and diff splicing, the early stop, the prompt fit, in characters and in win32 command-line units, and surrogate halves repaired before they are sent (AC-2, AC-7, AC-19, EC-36, EC-80).
- `test_harness_compose_verify.py`: the trio alias with isolated verifiers, reader writes caught or kept in their worktrees, and a failed writer (AC-3, AC-8a, AC-8b, EC-52).
- `test_harness_compose_answers.py`: cut answers, repair turns and their problems, `parse_json_answer` with a caller parser, `JsonText.decode`, and the record bounds (AC-9, AC-16, INV-19, NFR-8, EC-24 to EC-33).
- `test_harness_compose_handoff.py`: a handoff to a new harness, and the stop after a failed summary (AC-4, EC-64).
- `test_harness_compose_stages.py`: stages through fresh threads, the decision table and the retry rungs (AC-5, AC-12, EC-53, EC-54).
- `test_harness_compose_ensemble.py`: every role in its place, narrowing and repairs, long proposals sharing a selector's room fairly, no successful proposal, and a writing proposer (AC-6, AC-8c, AC-20, INV-18, EC-23, EC-49 to EC-51, EC-70).
- `test_harness_compose_git.py`: a folder outside any repository, no usable git, git hygiene, a hostile repository configuration, an untracked nested repository and an unborn `HEAD` (AC-13, INV-6, INV-26, T-6, T-8, EC-1 to EC-5, EC-10, EC-58, EC-73).
- `test_harness_compose_workspace.py`: `capture_diff` and `in_worktree` (AC-17, AC-18, INV-7, INV-8, EC-74).
- `test_harness_compose_concurrency.py`: cancellation, a second cancel or an anyio cancel scope during the cleanup, a cancel during a slow worktree add, a failed worktree add that stops its siblings before its error propagates, Grok serialization within a composite, and the lock per workspace across composites (AC-10, AC-11, INV-13, INV-14, INV-30, EC-17, EC-19, EC-22).
- `test_harness_compose_removal.py`: a reader worktree that cannot be removed after its reader answered, with the record keeping every verdict or proposal and its thread id, and a running sibling stopped first (EC-16, INV-14, INV-15, D-26).
- `test_harness_compose_derived_steps.py`: a relocated verifier, an anchored repair turn and a ladder rung that meet a deleted skill folder are recorded failures, never a raise (INV-9, INV-15, INV-19, INV-21, D-26).
- `test_harness_compose_keys.py`: no key in another step's prompt, an error (the refusal of every caller text that holds a key included), a `repr` or git's argv or environment, while the raw records keep the step's own text (AC-15, INV-4, INV-5, EC-71, T-3).

Run `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose`.

## Omitted Testing Strategies

The tests leave these out:

- real vendor CLIs and real keys;
- the wheel itself: AC-21's installed-copy load is left to the package stage, and lint C015 proves statically that the files ship;
- the gate run of AC-23;
- Muse in WSL mode inside a worktree (EC-55, EC-56);
- timing budgets and repository-size limits (EC-9, EC-66);
- the accepted limitations of §6.3, which have no control to test.

`docs/spec/native-thread-compose/test-plan.md` lists every candidate that was left out and why.
