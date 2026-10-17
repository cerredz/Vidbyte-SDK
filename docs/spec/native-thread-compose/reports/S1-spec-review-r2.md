VERDICT: SOUND WITH FIXES — r2 closes R-1 to R-4 and R-6 to R-11, and its git design held on every repository state I ran it on; the fixes left are text edits: INV-4's key-hygiene bullets and AC-15 contradict INV-4's last paragraph and EC-71, and D-2 still leaves the lib/compose split to a later review.

WHAT THE SPEC GETS RIGHT
- The §9.2 git table and D-6 are correct as written.
  - I ran the table literally through the worktree's own `CliRunner` and `CliArgv`. Every command exits 0 in each state tried:
    - a dirty repository;
    - spaces and `ü` in the repository path;
    - `& % ^ ü` in the temporary path;
    - no git identity;
    - a linked worktree;
    - a sparse checkout.
  - The real index, `HEAD`, refs and `.git` files stay byte-identical.
  - The diff names only the writer's paths and adds no CRLF noise.
  - Ten concurrent worktree readers plus three snapshots leave 0 worktree registrations, and S2 == S1.
  - The table runs git from the repository root. That is also the only working folder that gives correct diffs when the user has set `diff.relative=true` (R-15).
- INV-18's prompt fit is now sound.
  - One `sys.maxsize` note is reserved per spliced value, and the note counts inside the share.
  - So the prompt never gets shorter as the share grows, and the smallest share always fits.
  - This also holds in win32 command-line units. Prefix plus note measured 54 units, then 55 one character later.
  - A bare prefix that ends in backslashes is not monotone: 13 units, then 10 one character later. INV-18 never measures a bare prefix, so this does not matter.
- R-3 is closed everywhere.
  - These signatures are identical in §4, §8.5, INV-24, FR-2, FR-4, D-25, row 19, AC-1 and AC-2: `chain_threads(steps, template=None, *, prompt)`, `verify_with(writer, verifiers, *, prompt)` and the aliases' `(prompt, *, …)`.
  - The aliases are class-attribute instances, bound as `name = Class.ATTR` (D-18). That passes the static policy.
- The counts hold.
  - New files: 18 `.py` plus 22 `.md`, so 40. Modified files: 9. §12.3 rows: 28.
  - No pinned vocabulary and no `__all__` gains a member (INV-33).
  - The per-file port rules remove every CLI output contract that would conflict with `json_answer`.

FINDINGS

R-12 [Blocker] [L9] §6.1 INV-4, §6.2 AC-15 — AC-15 forbids a key the stand-ins echoed from appearing in result-record reprs and `ThreadComposeError` attributes, but INV-4's last paragraph and EC-71 keep those records raw, so two P0 statements cannot both pass
  Evidence:
  - INV-4 bullets (spec.md:251–252): "the `repr` of any record" and "any `ThreadComposeError` message, attribute or `details`".
  - INV-4 (spec.md:256): "The caller's own prompt, templates and the records returned to the caller are not altered."
  - EC-71 (spec.md:573): "The records keep the raw text, which is the caller's own data".
  - AC-15 (spec.md:487):
    - Given: "stand-ins that echo the key into their answer and into a file they write".
    - Then: "No key appears in: … the `repr` of any `ThreadStep` or result record; any `ThreadComposeError` message, attribute or `details`".
  - §8.5 (spec.md:875–877): `ThreadComposeError` carries `diff` and `result`.
  - INV-11 (spec.md:316): `result` "is the composite's record so far".
  - `vidbyte/lib/dataclasses/native_threads.py:218`: `text: str` is a plain field, so `repr(NativeThreadResult)` prints the answer.
  - The base wire builders store the answer unscrubbed: `vidbyte/harnesses/native/grok/wire.py:82`, `opencode/wire.py:97` and `muse/wire.py:187`.
  - `WorkspaceDiff.text` is a plain field as well (spec.md:777).
  Failure:
  - With AC-15's stand-ins, `repr(ChainResult)` contains `NativeThreadResult(… text='…<key>…')` and the writer's `WorkspaceDiff.text`.
  - When a composite fails, `error.result` holds the same text. If a reader wrote the key into a file, `error.diff.text` holds it too.
  - The blind test author will write AC-15 literally.
    - An implementer who follows INV-4's last paragraph and EC-71 fails that test.
    - An implementer who makes the test pass has to scrub the caller's records, including the diff text the caller reads. That breaks EC-71.
  - S5 cannot reconcile the two without editing a test.
  Smallest fix:
  - Scope INV-4's bullets to text that compose itself produces:
    - the git argv and environment;
    - the `repr` of `ThreadStep`, and of any record field that holds a step;
    - the `ThreadComposeError` message, `details`, `safe_runtime_details`, `git_message`, `likely_cause` and `next_step`;
    - every `ConfigurationError`;
    - files compose writes;
    - prompts sent to later steps.
  - Add one sentence: text that a step returned or wrote (`NativeThreadResult.text`, `WorkspaceDiff.text`) stays raw wherever a record carries it, including `ThreadComposeError.result` and `.diff` (EC-71).
  - Change AC-15's Then list to match that scope.

R-13 [Major] [L4] §8.1 D-2, §12.3 row 7 — The primary design puts the nine functions' calling convention and the fork guard in a lib record on a precedent that matches only the fallback, and the fallback that review may force later leaves three behaviors open
  Evidence:
  - D-2 (spec.md:644) says `__call__` "forwards its own fields to its own stored function, in the argument order its own `verb` names".
    - It cites "the shape `vidbyte/lib/dataclasses/runner.py:RunnerHandle.invoke` already has".
    - The fallback applies if "Review or the placement workflow rules the forward out of lib".
  - `vidbyte/lib/dataclasses/runner.py:14–20` has `self._invoke = invoke` … `return await self._invoke(self.runner, message, **options)`. That is an injected invoker with no verb dispatch and no guard, which is the fallback's shape.
  - INV-2 (spec.md:240): "`thread_id` first for continue and fork". This is the harness functions' parameter order, and the primary encodes it in lib.
  - AGENTS.md:51: "Behavior that acts on the record lives in the layer that owns that behavior".
  - AGENTS.md:15 says the placement workflow "enforces it on every pull request by moving misplaced code". Today `agents-md-placement.yml` has only `workflow_dispatch` ("TEMPORARILY DISABLED").
  - Row 7's fallback stores the invoker "in a `field(repr=False, compare=False)`" but gives no name, type or default.
  - §8.5's `ThreadStep` (spec.md:755–765) has no such field.
  - Layering holds in both shapes: lib imports nothing above lib.
  Failure:
  - S3 builds the primary. An S4 reviewer, a human reviewer or the re-enabled workflow may rule it out. Then S5 must switch shapes in the middle of the PR with three questions unanswered:
    - (1) What does `await step(prompt)` do on a step that a caller built without a binder? `ThreadStep` is public, and INV-3 accepts such a step.
    - (2) If composites call `step(prompt)`, a caller can swap the invoker with `dataclasses.replace`. That step still passes INV-3 but runs arbitrary code, which breaks INV-28. Under the primary, INV-3 catches a swapped `function`.
    - (3) What is the field called? Tests that build steps need the name.
  Smallest fix:
  - Build the agreed fallback now.
    - It is observably identical: `await step(prompt)`, INV-2, EC-44 and all 42 names stay.
    - It matches the cited precedent, so placement review has nothing to move.
  - Pin its details:
    - `invoker: Callable[..., Awaitable[NativeThreadResult]] | None = field(default=None, repr=False, compare=False)`;
    - `__call__` raises `ConfigurationError` naming `ThreadStep.invoker` when the field is `None`;
    - composites call `ThreadBinder.invoke(step, prompt)` directly, never the stored invoker. INV-3 and INV-28 then hold for every step. Update §5's `ThreadStep(prompt)` edge to match.
  - If the author keeps the primary instead:
    - delete the fallback from D-2, row 7 and r1-5;
    - correct the precedent sentence.

R-14 [Major] [L3] §6.1 INV-24, §12.3 row 19 — The aliases advertise `(prompt, *, <a>, <b>)` but accept `**steps`, and the spec never says what a missing or misspelled keyword does
  Evidence:
  - Row 19 (spec.md:1294): "`ThreadChainPair`: callable, with `__signature__` and `async __call__(prompt, **steps)`".
  - INV-24 (spec.md:430): "Each alias checks that every step it is given is on the harness its parameter names … `inspect.signature` of each alias shows exactly its parameters".
  - The only bad-argument outcome the spec states for aliases is a step on the wrong harness (EC-42).
  - Probe on Python 3.11.0 (`python_facts.py`):
    - `inspect.signature(alias)` gives `(prompt, *, opencode, grok)`;
    - yet `alias("p", opencode=1)` returned `('p', {'opencode': 1})`;
    - so Python does not enforce a declared `__signature__`.
  Failure:
  - `run_opencode_verify_with_grok_and_muse(p, writer=w, grok=g, muze=m)` has no specified outcome.
  - Reasonable builds would behave differently:
    - a raw `KeyError` from a public function. That goes against "refuses bad input … with `ConfigurationError`" (spec.md:974).
    - a `ConfigurationError` naming `muse`;
    - silently ignoring `muze`.
  - A test author may expect Python's `TypeError`, which is what the general composites raise for a missing `prompt`. The implementer may build any of the above. They will disagree.
  Smallest fix:
  - Add one sentence to INV-24 and row 19: `__call__` first binds its arguments with `self.__signature__.bind(prompt, **steps)`. A missing or unknown keyword then raises `TypeError` before any check, as a function with that signature would.
  - Add one EC row for this case.

R-15 [Minor] [L9] §6.1 INV-26, §9.2 git table — INV-26 says git runs in "the workspace or the worktree folder", while the table runs snapshot, diff and worktree add/remove from the repository root, and only the table's choice gives correct diffs under a user's `diff.relative=true`
  Evidence:
  - INV-26 (spec.md:435) contradicts the §9.2 rows (spec.md:1006–1012), which say "repository root".
  - Probe: tree-to-tree `diff --name-only` with `-c diff.relative=true` in `s1probe-r2/runs2/normal`.
    - Run from the `sub` folder, it printed `b.txt` and `new_by_writer.txt`. It dropped `c.txt` and made the paths folder-relative.
    - Run from the repository root, it printed `c.txt`, `sub/b.txt` and `sub/new_by_writer.txt`.
  Failure:
  - An implementer or S4 reviewer who follows INV-26 runs `diff` in the workspace.
  - If the user has set `diff.relative=true`, the diff then loses every change outside the workspace. That breaks INV-8 and EC-10.
  Smallest fix: Change INV-26's cwd bullet to: "The `cwd` is the one §9.2 names for each command: the repository root, the workspace or the worktree folder."

R-16 [Minor] [L5] §6.1 INV-6, §6.3 EC-73 — Every snapshot `add` failure gets the "untracked repository with no commit" texts, including a timeout and an unreadable file
  Evidence:
  - INV-6 (spec.md:281): "a `GIT_FAILED` from the snapshot's `add` gets the texts that name an untracked repository with no commit, EC-73".
  - INV-6 (spec.md:279): "A later git command that exits non-zero or passes its time bound is `GIT_FAILED`".
  - EC-9 (spec.md:511): a snapshot can be "slower than the git bound".
  - EC-73 (spec.md:575) itself names another cause of an `add` failure: unreadable files, "such as a file another program holds open".
  Failure: Suppose `add` timed out on a large file, or failed on a locked file. The message still tells the user to "commit in that folder, list it in `.git/info/exclude`, or remove its `.git`", but no such folder exists.
  Smallest fix:
  - Give the two `add` texts only to an `add` that exited non-zero. A timeout keeps the generic `GIT_FAILED` texts.
  - Word the two texts so they name both causes: an untracked repository with no commit, or a file git could not read.

R-17 [Minor] [L9] §9.2 port rules (`role_system`) — The port rule replaces "the read-only sandbox sentence", but the CLI text has two such sentences, so a literal port keeps "any attempt to do so will fail", which is false for worktree readers and slips past AC-21
  Evidence:
  - CLI `role_system.md:37–38`: "You are running in a read-only sandbox. You cannot write, move, or delete any file, and any attempt to do so will fail."
  - Port rule (spec.md:1046): "the read-only sandbox sentence becomes 'Do not change any file in the workspace'".
  - §12.4 (spec.md:1347): "no sandbox or approval claims".
  - AC-21's forbidden texts catch only the word "sandbox", which appears only in the first sentence.
  Failure:
  - A literal port keeps the second sentence.
  - opencode and Muse proposers then work in a worktree where writes succeed, while the prompt tells them every write will fail.
  - AC-21 still passes.
  Smallest fix: Reword the port rule: "the two sentences 'You are running in a read-only sandbox. You cannot write, move, or delete any file, and any attempt to do so will fail.' become 'Do not change any file in the workspace.'"

VERIFIED CLAIMS:
All probes ran from `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s1probe-r2/`. They used the worktree's own `vidbyte.lib.process`, and the worktree status stayed clean.

- a. Static policy against the r2 design: HELD.
  - `test_harness_threads_static_policy.py:29` scans `PACKAGE.rglob("*.py")`, so compose is covered.
  - Rule 1 (:68–79, applied at :88) looks only at `tree.body`. It allows:
    - a docstring;
    - imports and classes;
    - a literal `__all__`;
    - in `__init__`, a binding `name = <Name>.<attr>` whose name does not start with an underscore.
  - Rule 2 (:92–104) rejects every str, bytes, int and float literal, including f-string text. The only exceptions are docstrings, `__all__` strings, `""`, `0` and `1`.
  - These all pass:
    - class-attribute aliases and their `name = Class.ATTR` bindings;
    - a class-level `WeakValueDictionary`;
    - row 28's docstring-only edit.
  - A module-level `if TYPE_CHECKING:` would fail rule 1.
  - `WeakValueDictionary` probe: 1 entry while the lock is held, 0 after release.
- b. Git table, D-6 and `set_index` through the real `CliRunner`: HELD on every state, and each result matches its EC.
  - Normal repository:
    - snapshot `[('read-tree HEAD', 0, ''), ('add -A', 0, ''), ('write-tree', 0, '')]`;
    - "snapshot left index/HEAD/refs/.git files unchanged: True";
    - "objects before/after: 9 -> 14";
    - "same content same tree id: True";
    - diff names `['c.txt', 'sub/b.txt', 'sub/new_by_writer.txt']`;
    - "has user edit leak: False | crlf noise: False".
  - Verifier worktree after `read-tree <S0>`:
    - status `['MM c.txt', 'M  sub/a.txt', ' D sub/b.txt', 'A  user_untracked.txt', '?? sub/new_by_writer.txt']`;
    - `git diff` gives `['c.txt', 'sub/b.txt']`;
    - removal exits 0, the folder is gone, and S2 == S1.
  - Unborn `HEAD`:
    - `has_commit` exits 1;
    - the snapshot runs without `read-tree`;
    - `worktree add` gives `(128, 'fatal: invalid reference: HEAD')` (EC-5).
  - Nested repository with no commit: `add -A` exits 128 with "error: 'nested_nocommit/' does not have a commit checked out / fatal: adding files failed" (EC-73).
  - Nested repository with a commit: it becomes a gitlink (mode 160000), and an edit inside it is invisible (EC-13).
  - No identity (`GIT_CONFIG_GLOBAL` set to an empty file, `GIT_CONFIG_NOSYSTEM=1`, `user.email` exits 1): every command exits 0, because none needs an identity.
  - Spaces and `ü` in the repository path, `& % ^ ü` in the temporary path, with git.exe: identical results.
  - Linked-worktree workspace: works.
  - Sparse checkout: the snapshot tree equals the `HEAD` tree.
  - Ignored workspace:
    - the writer's change is invisible (EC-75);
    - `check-ignore -q` exits 0; `check-ignore -q .` run inside the workspace also exits 0, and it exits 1 at a root that is not ignored;
    - so if the owner ever wants a refusal for this state, one is available using only fixed argv words;
    - EC-75 already states the limitation, so I raised no finding.
  - Empty workspace: its folder is missing after the fill (EC-74).
  - Concurrency: "readers ok: 10 / 10"; three concurrent snapshots equal S1; "registrations left: 0"; S2 == S1.
  - `CliRunner` supports what the table needs:
    - `env_overlay` plus `env_remove` (runner.py:278–279);
    - `cwd`;
    - `max_output_bytes` (up to 64 MiB) and `timeout_seconds`;
    - stdin `DEVNULL` when `stdin_text` is None (runner.py:200).
  - L6 object cost: EC-9 and A-6 state it. The only bound is the 120 s git timeout. The new objects are unreachable and stay until `git gc` removes them.
- c. No `^ { } ~` revision syntax, and every argv word is a constant: HELD.
  - The only revision in any argv is `HEAD`.
  - `HEAD^{tree}` appears only as "never" (INV-26, D-24, EC-65) and in a §15 fact.
  - Every flag is one of the 17 `GitFlag` members.
  - Every other word is a constant, a tree id or a folder compose made.
- d. R-2 arithmetic: HELD.
  - Measured CLI sources:
    - `planner_system`: 58,578 characters (50,612 in examples, 7,966 without);
    - `implementer_system`: 35,852 (5,480 without examples);
    - `role_system`: 5,704;
    - `selector_system`: 6,534;
    - `fork_turn`: 720;
    - `implementer_turn`: 847, with 19 placeholders.
  - Every fixed combination is far under NFR-11's 12,000.
  - The worst case is defined: one `sys.maxsize` note per spliced value.
- e. Signatures are identical in §4, §8.5, INV-24, FR-2, FR-4, D-25, row 19, AC-1 and AC-2: HELD.
- f. D-2:
  - Layering: HELD.
  - The precedent claim: DID NOT HOLD. runner.py:14–20 has the fallback's shape.
  - Which shape to build is clear for S3, but it depends on a later review (R-13).
- g. Worktree lifecycle: HELD.
  - Worktree folders are made through `tempfile` with `COMPOSE_WORKTREE_PREFIX`.
  - A worktree is removed on success, failure and cancellation, with a shielded cleanup. EC-16 covers a removal that fails.
  - opencode and Muse readers must be `RUN` steps (INV-9). So no reader needs a thread that was created in another folder.
  - A reader's first turn, its repair turns and every selector round run in the same worktree before it is removed (INV-9).
- h. Counts and pins: HELD.
  - 40 new files, 9 modified, 28 rows.
  - The surface test pins `native.__all__` (17 names), the `FailureCode` tail (`120 + 28`), `NativeThreadOperation`, `NativeThreadProblem` and `lib.process.__all__` (3 names). No row touches any of them.
  - The 42 names are 10 + 9 + 18 + 4 + 1.
  - §8.4 names the four exported enums only by role ("the four enums callers branch on"). Read against §8.5, they can only be `VerdictDecision`, `StageDecision`, `EnsembleStage` and `ThreadComposeProblem`.

Round-1 closure:
- R-1 closed. §9.2: "each file's own output contract goes, and with it every mention of a JSON member, id, score or return format that the §9.2 schemas lack". The remaining wording problem is R-17.
- R-2 closed. INV-18: "the `truncation_note` with an omitted count of `sys.maxsize`" and "finds by bisection the largest share for which the rendered prompt fits".
- R-3 closed. D-25: "`chain_threads(steps, template=None, *, prompt)` and `verify_with(writer, verifiers, *, prompt)`".
- R-4 closed. EC-73: "`add -A` into the temporary index exits 128", and the probe confirms it. The diagnostic texts are R-16.
- R-5 reopened as R-13.
- R-6 closed. The probe confirms both parts of INV-9:
  - compose "creates … the folder inside the worktree";
  - compose "sets the worktree's index, and only the index, to the before-writer snapshot (`read-tree <S0>`)".
- R-7 closed. INV-5: "`from_thread` is a `CONTINUE` step or an anchored `FORK` step". EC-76 matches.
- R-8 closed. INV-26: "No argument holds a caret: compose names `HEAD`, never `HEAD^{tree}`". The git table matches.
- R-9 closed. §8.5: "details holds the eight A003 fields, and safe_runtime_details holds problem, workspace and git_message". Row 28 changes only the header docstring.
- R-10 closed. §13: "lint C015 runs in the source stage … proves statically that the wheel ships them".
- R-11 closed in the prose: "never reaches another step's prompt or argv through compose", and T-3 records the remaining risk. The bullets above that prose are R-12.

Repository claims spot-checked, all HELD:
- `vidbyte/harnesses/README.md:178` (the file is 10,771 characters);
- `REPO_MAP.md` lines 159–161, 197 and 215;
- `pyproject.toml` lines 48–49, 69–76 and 78–81;
- `errors/base.py`: `TYPE_CHECKING` at lines 61–65, plus :134 and :558;
- `serialization.py:65`;
- `conftest.py` lines 257, 258 and 406;
- `fake_harness.py` :7 and :169;
- `run_ci.py` :50 and :82;
- hostkit `__init__` :4;
- the 438 base tests collect;
- neither Git for Windows folder (`mingw64/bin`, `cmd`) holds `grok`, `opencode`, `muse` or `wsl`;
- on Python 3.11.0, `JsonAnswer[int](…)` raises `TypeError`, and `iscoroutinefunction(alias)` is False.
