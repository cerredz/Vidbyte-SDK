VERDICT: SOUND WITH FIXES — The architecture (tree snapshots, worktree readers, a per-workspace Grok lock, partial-success records, aliases that pass the static policy) is right and buildable, but the prompt ports, the fitter's worst case, the composites' parameter order, one handoff check and three git/worktree edge cases need spec edits before S2 freezes tests against §8.5 and §9.2.

WHAT THE SPEC GETS RIGHT
- D-6, INV-7 and INV-8 build snapshots as git trees through a temporary index and diff tree to tree. This is the right answer to EC-6 and EC-7: the literal `git status --porcelain` and `git diff` texts cannot separate one step's change from earlier edits, and they never show untracked files (re-probed). INV-26's flags (`--no-optional-locks`, `-c core.fsmonitor=false`, `--no-ext-diff`, `--no-textconv`) and the removal of the 15 `git rev-parse --local-env-vars` names close the hostile-config paths that matter. Keep this.
- INV-15 compliance is designed in, not hoped for. Aliases are class-attribute instances bound as `name = Class.attr` in compose `__init__` (D-18). That is exactly what `tests/features/harness_threads/test_harness_threads_static_policy.py:77` allows. Every literal lives in lib enums and constants. `native.__all__`, the FailureCode count check and `lib.process.__all__` stay untouched, so no pinned test changes. Keep this.
- Concurrency and cancellation are specified at the level a reviewer needs:
  - one `asyncio.Lock` per (loop, normcased workspace) in a class-level `WeakValueDictionary`, held for exactly one step call, so the table cannot grow without bound;
  - an all-results fan-out that records `NativeThreadError` but cancels and awaits siblings on anything else, and never raises `ExceptionGroup`;
  - shielded worktree removal on cancel;
  - no second timeout system (INV-13, INV-14, INV-22, EC-17, EC-19).
- §6.2 and §13 are ready for tests. Every bullet of the owner's acceptance list maps to AC-2..AC-12, and so do its six named scenarios. The §13 facts I checked are true, including the stand-in gaps S2 must fill: strict pytest-asyncio, `conftest.py:257–258` (PATH and tempdir), the `conftest.py:406` pack fixture, `fake_harness.py:7` and `:169`, and `run_ci.py:50`. The one exception is R-10.

FINDINGS

R-1 [Major] [L3] §9.2 prompt table, §12.3 row 17 — The port rules keep the CLI prompts' own output contracts, which contradict D-13 and the §9.2 answer schemas. A real selector therefore gets two incompatible JSON contracts, and `implementer_turn` cannot be ported as written
  Evidence:
  - Row 17: "Ten are ported from the CLI ensemble prompts: `{{x}}` becomes `{x}`, literal braces are doubled, `<examples>` blocks are dropped, and sandbox and Codex wording becomes harness-neutral."
  - D-13: "Proposals are free text. Only the plan, rounds and selection are JSON. Candidates are whole proposals numbered by position, not per-approach ids".
  - §9.2 defines a round as `kept` (offered numbers) plus `summary`, and a selection as `proposal`, `approach`, `rationale`, `guidance`. It gives `implementer_turn` the fields "task, role_name, proposal, approach, rationale, guidance", and says "Extra members are refused."
  - `selector_system.md:60–68` in the CLI: "Return one JSON object and nothing else. It has exactly four top-level keys: `round_summary` … `comparison_basis` … `kept` contains exactly the required number of verdict objects; and `eliminated` contains every dropped id. Each verdict has exactly eight keys: `candidate_id`, `pros`, `cons`, `score`, … Missing keys, extra keys, prose, or code fences fail the run."
  - `selector_round_turn.md`: "list every id you drop". `selector_final_turn.md`: "Your `round_summary`, `comparison_basis`, `rationale`, `evidence`, `uncertainties`, `implementation_guidance`, and `cons` are the brief…". Both end with "Return the round as the single JSON object described in your instructions".
  - `role_system.md:76–85`: "Return one JSON object and nothing else … `approaches` is an array of {{minimum}} to {{maximum}} objects. Every approach has exactly ten keys". `role_system.md:37`: "You are running in a read-only sandbox … any attempt to do so will fail."
  - Measured: `implementer_turn.md` has 19 placeholders (approach, assumptions, candidate_id, candidates, comparison_basis, cons, evidence, files, implementation_guidance, pros, rationale, roles, round_summary, score, task, title, tradeoffs, uncertainties, validation_steps). Only task, approach and rationale are among the spec's six.
  - The contract in `planner_system.md:63–69` matches the plan schema, so the planner is not affected.
  Failure:
  - A faithful port first sends a Grok selector `selector_system`, which asks for `round_summary`, verdict objects in `kept`, `eliminated`, and ids like `role.approach`. It then sends `json_answer` + `round_schema`, which ask for `kept` as numbers and a `summary`.
  - Whichever contract the model obeys, it breaks the other. Obeying the system file yields extra members, which `AnswerDecoders` refuses. Rounds then burn repair turns and fail after `COMPOSE_JSON_REPAIR_TURNS`, and `run_ensemble` ends at SELECT with no implementation.
  - Stand-ins return scripted JSON whatever the prompt says, so AC-6 and AC-20 stay green while every real ensemble degrades.
  - For `implementer_turn`, `require_template` refuses the literal port at first load (16 unknown placeholders). The implementer must rewrite the `<selected-approach>` block with no spec guidance.
  Smallest fix: Add a porting rule for each file to row 17, or as a column in the §9.2 table:
  - In `role_system` and `role_turn`, replace the JSON output section with a prose instruction that matches D-13.
  - In `selector_system` and both selector turns, replace the output section and every id, score, `eliminated` or `round_summary` reference with "answer in the JSON shape given at the end of this message". `json_answer` + schema is then the only contract.
  - Rewrite `implementer_turn` around its six fields.
  - Replace the "read-only sandbox … will fail" sentence with a harness-neutral "do not change any file".
  - Add to AC-21 that no ported file contains "Return one JSON object", `candidate_id`, `eliminated` or `round_summary`.

R-2 [Major] [L5] §6.1 INV-18, §6.3 EC-36, D-19, §12.3 row 13 — The up-front fit check measures prompts with spliced values empty, so the send-time fit can still overflow. The last resort then sends verifiers and selectors blank inputs, and their answers are recorded as valid
  Evidence:
  - INV-18: "Before any I/O, compose renders every prompt it will send with all spliced values empty … each shortened value ends with the `truncation_note` … (in a selector prompt, each proposal's text)". It also says: "A step therefore never fails with `configuration.invalid_argument` because of a spliced value."
  - EC-36: "up to `COMPOSE_FIT_ROUNDS` times. As a last resort it sends the spliced values empty, which the up-front check proved fits | The step runs".
  - §9.2: `proposal_block` (number, role_name, text) is "one block per candidate inside `candidates`".
  - Repo: `NATIVE_ARGV_PROMPT_MAX_CHARS = 24000` and `NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS = 30000` (`vidbyte/lib/constants/native_threads.py:27,32`). `RecordFieldValidator.require_command_line_units` measures `list2cmdline` UTF-16 units (`vidbyte/lib/dataclasses/validation.py:64`).
  Failure:
  - (a) Take a Grok selector with ten proposers and a 16,000-character task. It passes the up-front check, because the empty render holds no proposal blocks and no notes. The fixed files are about 7,500 characters (`selector_system` alone is 6,534 in the CLI), so the total is about 23,500, under the 24,000 cap. At send time, ten `proposal_block` wrappers plus ten truncation notes need more than the roughly 500 characters left, even with every text cut to nothing. The rounds cannot converge, so the last resort sends ten blank candidates. When the wrappers alone overflow, it instead sends a prompt that Grok refuses with `configuration.invalid_argument`, which INV-18 says cannot happen. The selector picks a number among blanks, the implementer builds it, and `failed_stage is None`.
  - (b) A verifier whose prompt reaches the last resort gets `verify_turn` with empty `files` and `diff` and no note. It answers "approve", and the verdict counts toward `agreement`. That is a verdict on a diff the verifier never saw, graded silently, which ledger 6 forbids for cut answers.
  Smallest fix:
  - Make `PromptFitter.check` render every spliced value as a full-length truncation note, and render selector prompts with the maximum number of `proposal_block`s. A fair-share cut then always fits in characters.
  - On win32, cut each value to its share measured in command-line units. The measure only grows as the cut point grows, so a bisection on the cut point is exact in one pass.
  - Delete the blank last resort and `COMPOSE_FIT_ROUNDS`.
  - [scope-adding] Optional Q-11: mark in `StepOutcome` that a spliced input was shortened (default: not built).

R-3 [Major] [L1] §8.5, D-25, §4 — The general composites reorder the binding ledger's `chain_threads(steps, template)` and `verify_with(writer, verifiers, ...)`. The owner's positional forms then raise TypeError, and the owner was never asked
  Evidence:
  - request.md §B, ledger 2 (binding, "do not reopen"): "`chain_threads(steps, template)` → `run_opencode_then_grok` …" and "`verify_with(writer, verifiers, ...)` → `run_opencode_verify_with_grok_and_muse`".
  - Prompt 2: "Implement as chain_threads([step_a, step_b], template="...{previous}...")".
  - Spec §8.5: `async def chain_threads(prompt: str, steps: Sequence[ThreadStep], *, template: str | None = None)` and `async def verify_with(prompt: str, *, writer: ThreadStep, verifiers: Sequence[ThreadStep])`.
  - D-25: "the ledger's shape `chain_threads(steps, template)` has no place for it | `chain_threads(steps, template, *, prompt)` | The owner wants the ledger's literal positional order". §15 has no Q for it.
  - Python 3.11 against the §8.5 signatures: `chain_threads([a, b], "T {previous}", prompt="p")` raises "TypeError: chain_threads() got multiple values for argument 'prompt'". `verify_with(w, [g, m], prompt="p")` raises "TypeError: verify_with() got multiple values for argument 'prompt'".
  Failure: A caller who writes the ledger's form gets a TypeError. Once S2 writes tests against §8.5 ("These names are a contract"), the reordering is frozen. Reversing it later touches the §4 snippet, AC-1 and every composite test.
  Smallest fix: Adopt D-25's own runner-up: `chain_threads(steps, template=None, *, prompt)` and `verify_with(writer, verifiers, *, prompt)`. The aliases keep `(prompt, *, …)`, which is how the acceptance list writes them. Change §4 to `verify_with(opencode, [planner, opencode], prompt="Write a test for the --verbose flag.")`. If the author keeps the prompt first, record that as a blocking Q for the owner rather than a settled decision.

R-4 [Major] [L5] §6.1 INV-7, §6.3 EC-13, D-6/Q-10 — `add -A` into the temporary index fails outright when the repository holds an untracked nested repository with no commit. Every composite that needs git then raises GIT_FAILED there, while EC-13 says nested repositories only hide changes
  Evidence:
  - INV-7: "`read-tree HEAD^{tree}` (skipped when the repository has no commit), then `add -A`, then `write-tree`".
  - EC-13: "Submodules or nested repositories | A submodule is a gitlink in the snapshot: uncommitted edits inside it are not seen … | Missing changes inside submodules. Accepted limitation".
  - Probe setup: git 2.49.0.windows.1; a scratch repository with one commit, an edited file, an untracked file, and an untracked `scratch/` made with `git init` and no commit; a fresh `GIT_INDEX_FILE`.
  - `add -A` prints "error: 'scratch/' does not have a commit checked out" and "fatal: adding files failed", and exits 128.
  - `add -A --ignore-errors` prints the same error, exits 1, and indexes the other files.
  - `git status --porcelain` in the same state prints " M a.txt", "?? new.txt", "?? scratch/" and exits 0.
  Failure:
  - Suppose a repository holds `tools/scratch/`, initialised but never committed, or a chain step's writer ran `git init` in a new folder. The first snapshot after that point fails with `ThreadComposeError(GIT_FAILED)` naming `add`. This happens on every `verify_with`, `run_ensemble`, `capture_diff`, `in_worktree` and diff-using chain, until the user finds the folder.
  - Ledger 5's literal commands work in the same state, so D-6's trade-off is under-stated.
  - `--ignore-errors` is not a safe fix. It also skips unreadable files (a Windows file lock), which would then appear as deletions in the diff.
  Smallest fix:
  - Correct EC-13: a nested repository with a commit becomes a gitlink, but one with no commit fails the snapshot.
  - Add an EC row for the second state.
  - Give `GIT_FAILED` from `add` a likely cause and next step that name it: "an untracked folder is a git repository with no commit: commit in it, list it in `.git/info/exclude`, or remove its `.git`".
  - Add this refusal to D-6 and Q-10, so the owner sees what the tree mechanism refuses that the literal commands accept.

R-5 [Major] [L4] §8.1 D-2, §12.3 row 7 — D-2 puts an `async __call__` that dispatches harness calls on a `vidbyte.lib` record. The Placement Rule assigns that behavior to the owning layer, the spec never engages that sentence, and the placement workflow may move the code after tests depend on it
  Evidence:
  - AGENTS.md › Placement Rules: "Validation of the record itself (`__post_init__`, field checks) lives with the dataclass. Behavior that acts on the record lives in the layer that owns that behavior."
  - AGENTS.md: "the `AGENTS.md placement` workflow enforces it on every pull request by moving misplaced code to the location it names."
  - D-2: "`ThreadStep` is a frozen, slotted lib record with `async __call__(prompt)`".
  - INV-2: "`await step(prompt)` makes exactly one call to the bound function with the bound arguments (`thread_id` first for continue and fork) … Calling an unanchored fork step directly raises `ConfigurationError` naming `thread_id`".
  - Row 7 cites only "AGENTS.md Placement Rules › Dataclasses and principle 4".
  - The closest shape in the repo is `vidbyte/lib/dataclasses/runner.py:RunnerHandle.invoke`, a plain class that forwards to an injected callable. It was added on 2026-06-02 (86a85cdb), before the placement rule (09365b34, #468, 2026-09-27).
  Failure: The placement workflow or the `@claude` review moves the verb-specific argument order and the unanchored-fork guard into compose, which leaves `ThreadStep` uncallable. INV-2, every composite's `await step(prompt)`, the §4 snippet and AC-1 then break, after S2 has written tests against them.
  Smallest fix: In D-2, quote the Placement Rule sentence and argue why `__call__` is record plumbing rather than layer behavior. It is a single forward to the stored function in its verb's argument order, the shape `RunnerHandle.invoke` already has. Then name D-2's runner-up in §12 as the agreed fallback if review still objects. Either way, `await step(prompt)` and the public names survive.

R-6 [Major] [L5] §6.1 INV-9, §6.3 EC-6/EC-8 — Worktree readers are relocated into a folder the worktree may not contain, and the worktree's index holds the after-state. So opencode/Muse readers fail on an empty or ignored workspace folder, and they see earlier edits as part of the writer's change
  Evidence:
  - INV-9: "It is filled with `read-tree -u --reset` from the phase snapshot … The step runs with its workspace set to the folder inside the worktree that has the original workspace's path relative to the repository root."
  - INV-7 holds only tracked files and untracked files that are not ignored, and git trees hold no empty folders.
  - The nine functions turn the workspace refusal into a recorded error: `vidbyte/harnesses/native/opencode/threads.py:75–76` (`except ConfigurationError as exc: raise errors.from_configuration_error(exc, request) from exc`).
  - EC-6 promises "The writer's diff without the earlier edits". EC-8 lists changed ignored files but not an ignored workspace.
  Failure:
  - (a) Take `run_ensemble("Scaffold a service here", …)` with workspace `repo/newsvc/` still empty, or holding only ignored files. The phase snapshots lack `newsvc/`, so every opencode or Muse planner, proposer and selector fails with `configuration.invalid_argument`, naming a temporary path the caller never chose. An opencode planner ends the run at PLAN. If the workspace folder is itself ignored, every writer diff is also empty, so verifiers approve nothing.
  - (b) In a dirty workspace (EC-6), a verifier's worktree has its index at S1 and HEAD at the last commit. `git diff` there is empty, and `git status` shows the user's earlier edits staged with the writer's. That is the opposite of the S0→S1 diff in the verifier's prompt, and the worktree is the verifier's only route past a truncated diff.
  Smallest fix: After the fill, create the relative folder in the worktree, through `asyncio.to_thread`. For a verifier phase, run `read-tree <S0>` in the worktree (index only, no `-u`), so that `git diff` there equals the prompt's diff. Add an EC row for an ignored workspace: its diffs are always empty.

R-7 [Major] [L3] §7 FR-6, §6.1 INV-3/INV-5, AC-14 — FR-6 asks an anchored thread for the summary, but no rule refuses a `RUN` step as `from_thread`. A handoff from a fresh thread therefore reports success with a summary of nothing
  Evidence:
  - FR-6: "`handoff_thread(from_thread, to_step)` asks an anchored thread for a fixed summary of its state, decisions and open items".
  - request.md Prompt 2: "Implement as continue_* with a fixed summary prompt, then run_* on the target."
  - EC-44 refuses only "An unanchored fork step … passed where none is allowed (… `handoff_thread` …)", and INV-5's role rules say nothing about `from_thread`.
  Failure: `handoff_thread(from_thread=bind_thread(run_grok_thread, …), to_step=…)` starts a new Grok thread with `handoff_summary`. The new thread has no state, so it answers that there is no prior work. Compose seeds the target with that answer and returns `failed_step is None`. A migration that carried nothing is reported as success.
  Smallest fix: Add to INV-3, INV-5 and AC-14: `from_thread` must be a `CONTINUE` step or an anchored `FORK`, and a `RUN` step is refused with `ConfigurationError` naming `from_thread`.

R-8 [Major] [L5] §9.2 git table, §6.3 EC-65, D-24 — EC-65 says a batch `git.cmd` launcher behaves normally, but cmd.exe strips the caret from compose's own `HEAD^{tree}`, so a repository with commits reads as having none. The trigger is narrow: a win32 host whose only git is a `.cmd` launcher
  Evidence:
  - §9.2: "`rev-parse --verify --quiet HEAD^{tree}` (exit 1 means none)" and "`read-tree HEAD^{tree}`".
  - EC-65: "It runs. Compose's git argv carries no caller or model text | Normal behavior".
  - Probes: `subprocess.run(['cmd.exe','/d','/c','echo','HEAD^{tree}'])` prints `HEAD{tree}`. `subprocess.list2cmdline` leaves `HEAD^{tree}` unquoted. `git rev-parse --verify --quiet 'HEAD{tree}'` exits 1, while `HEAD^{tree}` and `HEAD` both exit 0.
  Failure: On such a host, every composite with an opencode or Muse reader raises `WORKTREE_FAILED` ("no commit") on a repository that has history. Every snapshot also skips `read-tree`, so tracked files that match an ignore rule drop out of each tree.
  Smallest fix: Use `rev-parse --verify --quiet HEAD` and `read-tree HEAD`; both accept a commit, and neither needs a caret. Correct EC-65 as well: cmd.exe also re-parses `&`, `%` and `^` in the temporary-folder paths compose passes to `worktree add` and `worktree remove`. Either refuse a batch launcher as the base does (Q-9), or state that limit.

R-9 [Minor] [L9] §8.5, §12.3 row 9, §11 layout — Three statements contradict each other or the tree
  Evidence:
  - (a) §8.5: "details holds only problem, workspace and git_message (never diff text or result)". Row 9: "the A003 packet: a literal `DIAGNOSTIC_FIELDS`, each field set as an attribute and passed in `details`". A003 accepts either form (`lint/rules/a003_context_rich_error_packets.py:68`: "Finds canonical fields assigned to self or supplied as literal details keys"), and `NativeThreadError` (`vidbyte/lib/errors/base.py:558`) passes all eight in `details`.
  - (b) The §11 layout says "harness_threads/ base pack: fake_harness.py, conftest.py, 14 test files (unchanged)". §13 fact 4 says the stand-in has no file-writing or key-echo mode, and that "AC-2, AC-3, AC-8, AC-15 and AC-17 need such modes".
  - (c) The header of `vidbyte/harnesses/native/__init__.py` never mentions the new public `compose` subpackage. Its PURPOSE reads "The package of harness thread functions: nine async functions …", and its ARCHITECTURE NOTE names every other subpackage. No row touches it.
  Failure: S2 and S3 each pick a different `details` shape for AC-15's checks. A reader of §11 assumes `fake_harness.py` must stay frozen. The package header misleads the next agent.
  Smallest fix:
  - (a) Keep row 9's form: the eight A003 keys plus problem, workspace and git_message, never diff text or result. Fix the §8.5 comment to match.
  - (b) Relabel the §11 line "extended by the test author with `.get`-read scenario fields; base tests unchanged".
  - (c) Add a docstring-only line to row 25 or a new row. D-1 keeps `native.__all__` unchanged either way.

R-10 [Minor] [L10] §13 "The wheel (AC-21)" — §13 says nothing in the gate checks the compose prompts, but C015 runs in the source stage and fails when a prompt does not ship
  Evidence:
  - §13: "Nothing in the gate checks the compose prompts ('the gate will not catch it', `agent-stage-prompts.md:144–152`), so the gate alone does not show AC-21".
  - `scripts/run_ci.py:82` runs `lint/run.py` in the source stage.
  - `lint/rules/c015_package_data_coverage.py` PURPOSE: "Detect a non-Python file inside the vidbyte import package that the built wheel omits". It works by "Static emulation of setuptools build_py over tracked files".
  Failure: S2 spends effort building a wheel to prove what lint already proves, or under-tests the parts lint does not cover.
  Smallest fix: State that C015 proves statically that the 22 files ship. Only loading from an installed copy and checking the placeholder sets need the wheel.

R-11 [Minor] [L7] §6.1 INV-4, §10 T-3 — INV-4 claims a key that a writer saved into a file never reaches another vendor, but compose scrubs only spliced values
  Evidence:
  - INV-4: "So a key that one model printed, or that a writer saved into a file, never reaches another step's argv or another vendor."
  - D-28 scrubs "spliced values before they enter a prompt". AC-15 checks only prompts, argv, reprs and errors.
  Failure: A writer saves its key into `notes.txt`. A Muse verifier opens `notes.txt` in its worktree, or a Grok reader opens it in place, and sends its content to that reader's own vendor. The spec promises this cannot happen.
  Smallest fix: Narrow the sentence to "never reaches another step's prompt or argv through compose". Add to T-3 that readers can read a key a writer saved into a workspace file (accepted, like T-2).

VERIFIED CLAIMS:
- INV-15 and the static policy (briefing claim 1): HELD.
  - `test_harness_threads_static_policy.py:68–79` allows a docstring, imports, classes, a literal `__all__` and, only in `__init__`, `name = Class.attr`. `ALLOWED_VALUES = ("", 0, 1)` (line 24).
  - Rule 2 walks every `ast.Constant`, class bodies included. D-18's class-attribute aliases, whose parameter names come from enums, therefore pass.
  - Modules are found with `rglob`, so compose is scanned without any test change.
- Pinned surface, FailureCode and A003 (claim 2): HELD.
  - `test_harness_threads_surface.py` pins the 17 names in EXPECTED_EXPORTS, `len(members) == len(main_members) + len(NEW_FAILURE_CODES)` and `sorted(lib_api.process.__all__) == ["CliArgv","CliRunner","ProcessStopper"]`.
  - The spec adds no FailureCode member, and it leaves `native.__all__` and `lib.process` alone.
  - A003 accepts attributes or literal `details` keys (see R-9(a)).
- D-2 placement (claim 3): DID NOT HOLD CLEANLY. See R-5.
- D-6 against ledger 5 (claim 4): HELD as a recorded refinement. It keeps CliRunner, the before and after snapshots, the closed failure and the bounded output, and Q-10 asks the owner. Re-probed: `git diff` omits untracked files, and an already-edited file keeps the same status line. It has a new cost: see R-4.
- Size (claim 5): HELD.
  - 40 new files: 18 Python modules (rows 1, 3, 5, 7, 8, 11–16 and 19–25) plus 22 prompts.
  - 8 modified files (rows 2, 4, 6, 9, 10, 18, 26 and 27).
  - 49 classes: 22 compose classes, 18 records, 7 enums, 1 error and `JsonText`. This matches §8.5.
  - L2: no abstraction with one implementation and no knob with one caller. Every budget line maps to an FR or a placement rule.
- Prompt arithmetic (claim 6): HELD for sizes; the contents do not hold (R-1).
  - Measured CLI sizes: `planner_system` is 58,578 characters, and 7,966 without `<examples>`. `implementer_system` is 35,852, and 5,480 without them. `selector_system` is 6,534 and `role_system` 5,704. The turn files run from 166 to 847.
  - Every fixed combination fits NFR-11's 12,000-character limit with room for `json_answer` + schema.
- Worktree and temporary-index side effects (claim 7): HELD, with the exceptions in R-4, R-6 and R-8.
  - Snapshots through `GIT_INDEX_FILE` leave the real index, HEAD and refs unchanged.
  - `worktree add --detach --no-checkout` works into an existing empty `mkdtemp` folder.
  - `git rev-parse --local-env-vars` lists 15 names on git 2.49.0.windows.1, which matches INV-26.
  - `CliRunner` builds the child environment as `os.environ` minus `env_remove`, then applies `env_overlay` (`vidbyte/lib/process/runner.py`), so the `GIT_INDEX_FILE` overlay works.
- "Neither verifier able to change the workspace" (claim 8): HELD, with the stated limit.
  - opencode and Muse verifiers cannot reach the workspace: they run in worktrees (INV-9).
  - Grok verifiers rely on PLAN or DEFAULT, the mechanism the owner chose (ledger 4). The backstop turns a breach into `READER_CHANGED_WORKSPACE`.
  - The edits from a breach stay in the workspace (NG-11), so row 26's README bullet must say so.
- Acceptance-list coverage (claim 9): HELD.
  - `run_opencode_then_grok` → AC-2; verify → AC-3; handoff → AC-4; staged → AC-5 and AC-12; ensemble → AC-6.
  - Failing step mid-chain → AC-7; verifier that writes → AC-8; truncated answer → AC-9; cancellation mid-gather → AC-10; Grok fan-out in one workspace → AC-11; stage that exhausts its retries → AC-12.
- §11 commands (claim 10): HELD. They match the briefing: lint with `python lint/run.py` (SDK-LINT: PASS), focused and full pytest with `PYTHONPATH=$(pwd)`, the source stage with `PYTHONPATH`, the package stage without it, and the two semgrep commands. `scripts/run_ci.py:82` runs lint inside the source stage.
- §13 facts: HELD except R-10. Checked: `pyproject.toml:48–49` (pytest 8.3.5, pytest-asyncio 1.3.0); `:78–81` (testpaths, strict flags, function loop scope); `conftest.py:257–258`; `conftest.py:406`; `fake_harness.py:7` and `:169`; `run_ci.py:50`.
- `JsonText` in `vidbyte/lib/util`: HELD. The folder header reads "general-purpose, domain-agnostic helper classes that have no dependency on any specific SDK feature", and row 6 updates its re-exports.
- Muse in worktrees: HELD as specified. `MusePathTranslator.to_wsl` (`vidbyte/harnesses/native/muse/launcher.py:40–52`) accepts any drive-letter path, so a worktree in the temporary folder maps to `/mnt/<drive>/…`. The UNC and WSL `gitdir:` limits are already EC-55, EC-56 and A-4.
- Grok lock table growth: HELD. Row 12's class-level `WeakValueDictionary` drops a lock once no composite holds it.
- Base EC-27, which this spec inherits: HELD. It limits collisions to calls whose skill set differs or that come first, so D-5's per-workspace serialization is conservative and within ledger 11.
- INV-1's alias wording: HELD. `inspect.iscoroutinefunction` is False on a callable instance, and INV-1 says only that calling an alias returns a coroutine.
- L6: N/A, because there is no database, query or migration. I checked for unbounded growth: the lock table is weak, and `git gc` prunes the snapshot objects (rollback item 3).
