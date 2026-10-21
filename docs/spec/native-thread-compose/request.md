---
slug: native-thread-compose
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-15 18:04
flags: --repo C:\Users\422mi\vidbyte-repos\vidbyte-sdk ; base branch and PR base overridden to feat/native-grok-opencode-meta-hosts (stacked PR on open PR #1036) ; no --from, no --until, no --keep-worktree
---

# Request: Composable multi-harness thread functions over the nine native thread functions

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening prompt; it was followed by a brainstorm of 25 ideas, not captured here):

````text
take a look at pr #1036 for the vidbyte-sdk/, what are some more complex functions that we can create inside of this pr? run_opencode_then_grok, run_opencode_verify_with_grok_and_muse(), etc. (can even take from the runtime primitive architectures that we have inside of the vidbyte-cli/.
````

**Prompt 2** (after the brainstorm; the owner picked five ideas; this is the prompt that invoked the pipeline):

````text
run the implementation of the following inside of a subagent with opus 5.5 max reasoning effort that runs the "spec-pipeline" skill file for the following, with the ones I pick, can also run/implement like variations of them if they exist:

run_opencode_then_grok(prompt, ...): opencode does the task, then Grok receives the original prompt plus opencode's final text and diff, and continues the work. Implement as chain_threads([step_a, step_b], template="...{previous}...") where each step's result is spliced into the next prompt, the same sequential handoff the CLI's stages.py uses.

run_opencode_verify_with_grok_and_muse(prompt, ...): opencode implements, then Grok (PLAN mode) and Muse (in a worktree) independently review the diff and answer a structured verdict. Return both verdicts plus an agreement flag. Implement with capture_diff around the writer, then asyncio.gather over two bound verifier steps feeding parse_json_answer.

handoff_thread(from_step, to_step): ask a thread to summarize its state, decisions and open items, then seed a thread on another harness with that summary. The migration primitive for when a harness hits key_rejected or a quota mid-task. Implement as continue_* with a fixed summary prompt, then run_* on the target.

run_staged_threads(stages: Sequence[StageSpec]): a direct port of the CLI stages primitive. Each stage is a fresh thread on a chosen harness with a retry budget, and a failure classifier keyed on NativeThreadProblem decides whether to retry, raise effort, or abort. Returns a per-stage result list.

run_ensemble(prompt, proposers=3): port of same-host-ensemble. One planner thread writes a role roster, N forks in PLAN mode each propose weighed approaches, a selector narrows to one, and one writer with ACCEPT_EDITS implements. The prompts move over from services/ensemble/prompts/. (small feedback, want the user to be able to define the threads/different providers that we have to offer for this).
````

**Invocation** (typed by the parent session on the owner's behalf):

````text
/spec-pipeline native-thread-compose --repo C:\Users\422mi\vidbyte-repos\vidbyte-sdk
````

## B. Handoff block and decision ledger (verbatim)

No `/talk` HANDOFF block exists. The parent session captured the owner's settled decisions as the following ledger. It is reproduced verbatim and is binding ("do not reopen").

````markdown
## B. Settled decisions (do not reopen)

1. **Build on the nine functions as they are.** `run_/continue_/fork_` × `grok/opencode/muse` in `vidbyte/harnesses/native/` on the base branch. Do not change their signatures or the records `NativeThreadRequest`, `NativeThreadResult`, `GrokThreadConfig`, `OpencodeThreadConfig`, `MuseThreadConfig`, or `NativeThreadError`. Read `docs/spec/harness-thread-functions/spec.md` on the base branch for their invariants (INV-*), edge cases (EC-*) and the security rules (§10); every one of them still holds for the composites.
2. **The five named functions are thin wrappers over general primitives.** The general forms are the deliverable; the named ones are convenience aliases:
   - `chain_threads(steps, template)` → `run_opencode_then_grok` and, as generated variations, every other ordered pair the owner may want (`run_grok_then_opencode`, `run_muse_then_grok`, …). Generate variations from the general form, never hand-write nine functions.
   - `verify_with(writer, verifiers, ...)` → `run_opencode_verify_with_grok_and_muse`. Any writer, any set of verifiers, each verifier answers one structured verdict, result carries all verdicts plus an agreement flag.
   - `handoff_thread(from_thread, to_step)` as a standalone primitive.
   - `run_staged_threads(stages)` with a `StageSpec` record (harness step, prompt template, retry budget, effort ladder) and a failure classifier keyed on `NativeThreadProblem`.
   - `run_ensemble(prompt, roster)` where the **caller supplies the thread step for every role** (planner, each proposer, selector, implementer). A proposer may be a Grok fork in PLAN mode, an opencode run on GLM, a Muse run, or any mix. No role is hard-wired to one harness. Default roster helpers are fine, but the roster is a public argument.
3. **One callable shape for every harness.** Add a `bind_thread(...)` adapter (name per repo conventions) that closes over `api_key`, `workspace`, `model`, `skills`, `config` and returns `ThreadStep = Callable[[str], Awaitable[NativeThreadResult]]`, plus a continue/fork-bound form. Composites take `ThreadStep`s and never harness names or raw keys. The key is still passed only to the nine functions and still never reaches argv, files, `os.environ`, error messages or logs.
4. **Exactly one writer per composite, enforced by mechanism not prompt.** Grok reviewers use `GrokPermissionMode.PLAN` (or `DEFAULT`). opencode and Muse have NO read-only mode in the base PR (its NG-9), so a reviewer on those harnesses must run inside a disposable git worktree (`in_worktree` helper) or have its diff captured and the composite must fail loudly if a reviewer changed files. Pick the worktree route unless the repo audit shows a reason not to; record the decision.
5. **Diff capture is a first-class helper.** `capture_diff(workspace)` snapshots `git status --porcelain` and `git diff` before and after a step through the existing `vidbyte.lib.process.CliRunner`, and returns changed files and the unified diff, bounded in size. Verifiers receive the diff, not a prose claim. A workspace that is not a git repository is reported as a closed failure, not a crash.
6. **Structured answers through one helper.** `parse_json_answer` (name per conventions) wraps a prompt with a schema instruction, parses the answer text, and on a parse or validation failure runs a bounded number of `continue_*` repair turns with the error text. Every verdict, roster and selection in the composites goes through it. `text_truncated=True` must fail the parse, never be silently graded.
7. **Partial success is reported, not discarded.** Every composite result record carries every step's `NativeThreadResult` or its `NativeThreadError`, every thread id, and which step failed. Only an empty result aborts. This is the CLI's runtime-primitive rule and it applies here.
8. **Cancellation and budgets.** Composites propagate `asyncio` cancellation to running steps; a `gather` cancels siblings on the first unrecoverable failure unless the composite is explicitly all-results. Each step gets the harness config's own `timeout_seconds`; no composite invents a second timeout system.
9. **Where it lives.** A new subpackage under `vidbyte/harnesses/native/` (`compose/` or the name the repo's conventions suggest), with records in `vidbyte/lib/dataclasses/`, enums in `vidbyte/lib/enums/`, constants in `vidbyte/lib/constants/`, following the base PR's layering exactly (lib never imports harnesses). Exported from `vidbyte.harnesses.native` (or `vidbyte.harnesses.native.compose`), never from the root `vidbyte` package. No new dependencies.
10. **Prompts are Markdown files, not Python strings.** Copy the CLI rule: every sentence addressed to a model lives in a `prompts/*.md` file loaded by a small library module, so a prompt change is reviewed as prose. Port the ensemble prompts from `C:\Users\422mi\vidbyte-repos\vidbyte-cli\src\vidbyte_cli\services\ensemble\prompts\` (planner_system/turn, role_system/turn, fork_turn, selector_system/round_turn/final_turn, implementer_system/turn), adapted from Codex wording to harness-neutral wording.
11. **Grok concurrency.** Concurrent Grok calls in one workspace share one private home and can collide while its skills folder is rebuilt (base PR EC-27). Fan-out over Grok in one workspace must either serialize Grok steps per workspace or run each in its own worktree. Decide and record.
12. **Async only. No sync wrappers. No model-facing tools. No payment or admission logic** (that is the CLI's concern). No live streaming or interrupt (base PR NG-2).
13. **Tests reuse the fake harness** at `tests/features/harness_threads/fake_harness.py` on the base branch, extended if needed, so the composite tests never need a real vendor CLI or key. Follow `tests/features/<feature>/` layout with FEATURE.md and README.md as the base PR did.
````

## C. Structured conversation notes

### Key decisions
- **The work lands inside PR #1036's lineage as a stacked PR.** Branch `feat/native-thread-compose` is cut from `origin/feat/native-grok-opencode-meta-hosts` (the head of open PR #1036, commit `5c08c35edcb1827e190ca4e2b2b1370808ef24be` at capture time) and the draft PR targets that branch, not `main`. *Reason:* Prompt 1 asks for functions "inside of this pr", and the nine thread functions exist only on that branch.
- **General primitives are the deliverable; the five named functions are thin aliases** (ledger item 2). *Reason:* Prompt 2 asks to "implement like variations of them if they exist", and each named idea is described as an instance of a general mechanism (`chain_threads`, `capture_diff` + `gather` + `parse_json_answer`, `continue_*` then `run_*`).
- **The caller chooses every harness, model and provider** (ledger items 2 and 3). *Reason:* the owner's feedback in Prompt 2: "want the user to be able to define the threads/different providers that we have to offer for this". Composites receive bound `ThreadStep` callables, never harness names or raw keys.
- **One writer per composite, enforced by mechanism** (ledger item 4): Grok reviewers in `GrokPermissionMode.PLAN` (or `DEFAULT`); opencode/Muse reviewers in a disposable git worktree (preferred) or with diff capture that fails loudly. Prompt 2 itself names this shape: "Grok (PLAN mode) and Muse (in a worktree) independently review the diff".
- **Verifiers judge the captured diff, not a prose claim** (ledger item 5). Prompt 2: "independently review the diff and answer a structured verdict".
- **Structured answers go through one bounded-repair parser** (ledger item 6); a truncated answer is a parse failure.
- **Partial success is reported** (ledger item 7), cancellation propagates, timeouts come only from each harness config's `timeout_seconds` (ledger item 8).
- **Prompts addressed to models are Markdown files** (ledger item 10); the ensemble prompts are ported from the CLI and made harness-neutral.
- **Grok fan-out in one workspace must be serialized per workspace or isolated per worktree** (ledger item 11). The choice is open; record it as a `D-` decision with its reason.

### Rejected alternatives
- **Hand-writing each ordered harness pair as its own function** — rejected: "Generate variations from the general form, never hand-write nine functions." (ledger item 2).
- **Hard-wiring ensemble roles to harnesses** (for example, proposers always Grok forks) — rejected by the owner's feedback in Prompt 2 and ledger item 2 ("No role is hard-wired to one harness").
- **Prompt-only read-only enforcement for reviewers** ("do not edit files" in the prompt) — rejected: "enforced by mechanism not prompt" (ledger item 4).
- **Changing the nine functions or their records** — rejected (ledger item 1).
- **Importing or depending on the CLI** — rejected: the CLI sources are reference implementations to port shapes from; the SDK must not depend on the CLI.
- **Sync wrappers, model-facing tools, payment or admission logic, live streaming, interrupt** — rejected (ledger item 12).
- **A second timeout system inside the composites** — rejected (ledger item 8).
- **Exporting from the root `vidbyte` package** — rejected (ledger item 9).

### Constraints and assumptions
- Target repository: `C:/Users/422mi/vidbyte-repos/vidbyte-sdk`. The workspace folder `C:/Users/422mi/vidbyte-repos` is not a git repository.
- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose`, branch `feat/native-thread-compose`, created with `--no-track` so the branch has no upstream until it is pushed as itself. Nobody pushes to or rewrites `feat/native-grok-opencode-meta-hosts`.
- The nine thread functions, their records, the fake harness and the base PR's spec folder `docs/spec/harness-thread-functions/` exist only on the base branch; read them from the worktree, not from the main checkout (which is on `main`).
- The base branch is live: it moved from `4a7987c7` to `5c08c35e` (a merge of `main`) during S0. Compare drift against `origin/feat/native-grok-opencode-meta-hosts`, never `origin/main`.
- No new dependencies. `vidbyte/lib/` never imports from `vidbyte/harnesses/` or any higher layer.
- Async only.
- Python `>=3.11`; dev extras pin `pytest==8.3.5` and `pytest-asyncio==1.3.0` (base-branch `pyproject.toml`).
- Development host is Windows 11 (Muse runs through WSL there); CI runs on Ubuntu with Python 3.11 and 3.12. Tests must pass on both.
- The SDK's GitHub workflows (`ci.yml`, `static-policy.yml`) have their automatic triggers disabled (`workflow_dispatch` only, plus `workflow_call` for CI). A PR therefore shows no attached checks; the remote signal is a dispatched run on the branch (`gh workflow run ci.yml --ref feat/native-thread-compose`), which is how PR #1036's head was verified.
- `docs/` is opaque per AGENTS.md: agents read only the `docs/` files their briefing names.

### Clarifications and answers
- Q: May the implementation go beyond the five picked functions? — A: "can also run/implement like variations of them if they exist" (Prompt 2). The ledger narrows this: variations are generated from the general forms, not hand-written (ledger item 2).
- Q: Should the ensemble's roles be fixed to particular harnesses? — A: "(small feedback, want the user to be able to define the threads/different providers that we have to offer for this)" (Prompt 2).
- Q: Where may the architecture come from? — A: "(can even take from the runtime primitive architectures that we have inside of the vidbyte-cli/." (Prompt 1).

### Terminology
- **The nine thread functions** — `run_`, `continue_` and `fork_` for each of `grok`, `opencode` and `muse` in `vidbyte/harnesses/native/` on the base branch (exact names to be read from `vidbyte/harnesses/native/__init__.py`).
- **Harness** — one of the three native coding-agent CLIs the SDK launches: Grok, opencode, Muse (the `NativeHarness` enum).
- **Thread** — one conversation with a harness, identified by `NativeThreadResult.thread_id`; `continue_*` adds a turn to it, `fork_*` branches it.
- **`ThreadStep`** — `Callable[[str], Awaitable[NativeThreadResult]]`: a prompt in, one thread result out, with key, workspace, model, skills and config already bound.
- **Composite** — a function in the new subpackage that coordinates several `ThreadStep`s (`chain_threads`, `verify_with`, `handoff_thread`, `run_staged_threads`, `run_ensemble`, and their named aliases).
- **Writer** — the one step in a composite that may change the workspace. **Verifier / reviewer / proposer** — a step that must not change the workspace.
- **PLAN mode / ACCEPT_EDITS** — members of `GrokPermissionMode` (`DEFAULT`, `ACCEPT_EDITS`, `DONT_ASK`, `PLAN`). opencode and Muse have no permission mode (base PR NG-9).
- **The CLI stages primitive** — `vidbyte-cli/src/vidbyte_cli/lib/runtime_primitives/stages.py` with `stage_failures.py` (`StageFailureClassifier`, `StageExhausted`) and types `StageSpec`, `StagesResult`, `StageStepResult` in `src/vidbyte_cli/types/runtime.py`.
- **same-host-ensemble** — the CLI's ensemble service at `vidbyte-cli/src/vidbyte_cli/services/ensemble/` (`service.py`, `settings.py`, `prompts/`).
- **`NativeThreadProblem`** — the closed enum of failure kinds; a `NativeThreadError` carries a `FailureCode` of the form `<harness>.<problem>`.

### Implementation hints
- **Base PR surface** (from the parent capture): `vidbyte/harnesses/native/__init__.py` (exports), `grok/threads.py`, `opencode/threads.py`, `muse/threads.py`, `hostkit/` (`NativeErrorFactory`, `NativeLauncher`, `NativeSkillFolders`), `vidbyte/lib/dataclasses/native_threads.py`, `vidbyte/lib/enums/native_threads.py` (`NativeHarness`, `NativeThreadVerb`, `NativeThreadProblem`, `GrokPermissionMode` with `DEFAULT`/`ACCEPT_EDITS`/`DONT_ASK`/`PLAN`, reasoning efforts), `vidbyte/lib/constants/native_threads.py`, `vidbyte/lib/errors/base.py` (`NativeThreadError`), `vidbyte/lib/process/` (`CliArgv`, `CliRunner`, `CliInvocation`, `CliOutcome`).
- `NativeThreadResult(harness, thread_id, text, text_truncated)`.
- `NativeThreadError` carries a closed `FailureCode` of the form `<harness>.<problem>`: `not_installed`, `launcher_refused`, `launch_failed`, `key_rejected`, `thread_not_found`, `timed_out`, `output_too_large`, `protocol_mismatch`, `run_failed`, plus `muse.wsl_unavailable`.
- **CLI reference implementations** (read, do not import): `C:/Users/422mi/vidbyte-repos/vidbyte-cli/src/vidbyte_cli/lib/runtime_primitives/stages.py`, `stage_failures.py`; `C:/Users/422mi/vidbyte-repos/vidbyte-cli/src/vidbyte_cli/types/runtime.py`; `C:/Users/422mi/vidbyte-repos/vidbyte-cli/src/vidbyte_cli/services/ensemble/service.py`, `settings.py`, `prompts/` (ten prompt `.md` files, the ten ledger item 10 names, plus `SKILL.md` and the loader `library.py`); the doctrine `C:/Users/422mi/vidbyte-repos/vidbyte-cli/skills/harnesses/runtime-primitives/SKILL.md` (seven-part shape, one writer, partial success reported). The CLI checkout is on `main` at `abd31b4`.
- **The SDK already has a Markdown prompt catalog**: `vidbyte/prompts/catalog.py` and `vidbyte/prompts/prompts/<family>/`, with prompt keys in `vidbyte/lib/enums/prompts.py` (AGENTS.md, "New JEV code": "A new Jev-facing prompt is a new family under `vidbyte/prompts/prompts/`, with its key in `vidbyte/lib/enums/prompts.py`"). There is an existing `vidbyte/prompts/prompts/handoff/` family. Whether ledger item 10's "small library module" should be this catalog is for the spec author to decide from the code and record.
- **Repo rules**: `AGENTS.md`, `CLAUDE.md` (it only includes AGENTS.md), `REPO_MAP.md` at the SDK root; folder READMEs with `## Notes for agents`; lint rule A009 caps folder READMEs at 40,000 characters.
- **The base PR's accepted pipeline artifacts** show the exact spec, test-plan, review and report formats this repo already accepted: `docs/spec/harness-thread-functions/spec.md`, `test-plan.md`, `review.md`, `context/code-map.md`, `context/vendor-facts.md`, `request.md` (in the worktree).
- **The fake harness**: `tests/features/harness_threads/fake_harness.py`, with `conftest.py`, `FEATURE.md`, `README.md` and fourteen `test_harness_threads_*.py` files beside it.

### Acceptance in the owner's terms (verbatim from the parent capture)

````markdown
- `await run_opencode_then_grok(prompt, opencode=bind_thread(run_opencode_thread, ...), grok=bind_thread(run_grok_thread, ...))` runs opencode, then Grok with the original prompt, opencode's text and the diff, and returns both results and both thread ids.
- `await run_opencode_verify_with_grok_and_muse(prompt, writer=..., grok=..., muse=...)` returns the writer result, two structured verdicts and `agreement: bool`, with neither verifier able to change the workspace.
- `await handoff_thread(from_thread=bind_continue(continue_grok_thread, thread_id, ...), to_step=bind_thread(run_opencode_thread, ...))` returns the summary text and the new thread's result.
- `await run_staged_threads([StageSpec(...), ...])` returns one entry per stage, retried per its budget, with the classifier's decision recorded for each attempt.
- `await run_ensemble(prompt, roster=EnsembleRoster(planner=..., proposers=[...], selector=..., implementer=...))` runs the four stages with the caller's own steps and returns the roster text, every proposal, the selection and the implementation result.
- Every function is covered by feature tests against the fake harness, including: a failing step mid-chain, a verifier that tries to write, a truncated answer feeding a parser, cancellation mid-gather, a Grok fan-out in one workspace, and a stage that exhausts its retries.
````

The parent session added one target: every item in this acceptance list is covered by a test against the fake harness.

### Open questions
- Package name for the new subpackage (`compose/` or what the repo's conventions suggest) and the names of the adapters' continue/fork-bound forms. The acceptance list already uses `bind_thread` and `bind_continue` literally.
- Reviewer isolation on opencode and Muse: disposable git worktree (preferred by ledger item 4) versus diff capture that fails loudly. Muse runs through WSL on Windows; whether a worktree path works there must be checked against the Muse launcher.
- Grok fan-out in one workspace: serialize per workspace versus one worktree per Grok step (ledger item 11).
- Placement of `capture_diff`, `in_worktree` and the JSON-answer parser: a canonical helper in `vidbyte/lib/` (AGENTS.md principle 5) or the harnesses layer.
- How `parse_json_answer` validates an answer without new dependencies (a validated dataclass, a schema, or a parse function supplied by the caller).
- How ordered-pair variations are generated from `chain_threads` without hand-writing them, while staying importable and documented.
- What "raise effort" means per harness for `run_staged_threads`' effort ladder (Grok has reasoning efforts; whether opencode and Muse configs carry one).
- What the ensemble's "N forks in PLAN mode" becomes when a proposer runs on opencode or Muse, which have no PLAN mode.

## D. Weighted words

From the owner's prompts:
- "Each stage is a fresh thread on a chosen harness with a retry budget, and a failure classifier keyed on NativeThreadProblem decides whether to retry, raise effort, or abort." — Prompt 2
- "where each step's result is spliced into the next prompt, the same sequential handoff the CLI's stages.py uses." — Prompt 2
- "Grok (PLAN mode) and Muse (in a worktree) independently review the diff and answer a structured verdict. Return both verdicts plus an agreement flag." — Prompt 2
- "One planner thread writes a role roster, N forks in PLAN mode each propose weighed approaches, a selector narrows to one, and one writer with ACCEPT_EDITS implements." — Prompt 2
- "want the user to be able to define the threads/different providers that we have to offer for this" — Prompt 2

From the binding decision ledger (§B):
- "every one of them still holds for the composites." — ledger 1
- "Generate variations from the general form, never hand-write nine functions." — ledger 2
- "Any writer, any set of verifiers, each verifier answers one structured verdict, result carries all verdicts plus an agreement flag." — ledger 2
- "where the **caller supplies the thread step for every role**" ... "No role is hard-wired to one harness." — ledger 2
- "Composites take `ThreadStep`s and never harness names or raw keys. The key is still passed only to the nine functions and still never reaches argv, files, `os.environ`, error messages or logs." — ledger 3
- "**Exactly one writer per composite, enforced by mechanism not prompt.**" — ledger 4
- "the composite must fail loudly if a reviewer changed files." — ledger 4
- "Verifiers receive the diff, not a prose claim. A workspace that is not a git repository is reported as a closed failure, not a crash." — ledger 5
- "Every verdict, roster and selection in the composites goes through it. `text_truncated=True` must fail the parse, never be silently graded." — ledger 6
- "Every composite result record carries every step's `NativeThreadResult` or its `NativeThreadError`, every thread id, and which step failed. Only an empty result aborts." — ledger 7
- "a `gather` cancels siblings on the first unrecoverable failure unless the composite is explicitly all-results. Each step gets the harness config's own `timeout_seconds`; no composite invents a second timeout system." — ledger 8
- "lib never imports harnesses" ... "never from the root `vidbyte` package. No new dependencies." — ledger 9
- "every sentence addressed to a model lives in a `prompts/*.md` file loaded by a small library module" — ledger 10
- "Fan-out over Grok in one workspace must either serialize Grok steps per workspace or run each in its own worktree." — ledger 11
- "**Async only. No sync wrappers. No model-facing tools. No payment or admission logic**" — ledger 12
- "so the composite tests never need a real vendor CLI or key." — ledger 13

From the acceptance list (§C):
- "with neither verifier able to change the workspace." — acceptance 2
- "returns one entry per stage, retried per its budget, with the classifier's decision recorded for each attempt." — acceptance 4
- "returns the roster text, every proposal, the selection and the implementation result." — acceptance 5
- "Every function is covered by feature tests against the fake harness" — acceptance 6
