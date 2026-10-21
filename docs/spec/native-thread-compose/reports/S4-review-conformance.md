LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — The surface, scope, call path, prompt-fit arithmetic and AC-1 all conform, but two reachable paths break explicit "every" and "never" guarantees: a worktree-removal failure discards finished reader answers and their thread ids, and a template made only of placeholders sends a step a blank prompt; each has a small, local fix.

WHAT THE IMPLEMENTATION GETS RIGHT
- **AC-1 is real.**
  - `SNIPPET` is byte-identical to the spec §4 block (1,565 characters each, compared by script). Only the `"C:/code/my-repo"` literal is swapped (test line 80, its count asserted at line 81).
  - The snippet runs in a fresh interpreter against stand-ins on `PATH` and the real git, and the test passes.
  - The compose pack passes 276 of 276. The base pack has 436 passed and 2 skipped, which is INV-35's 438.
  - `python lint/run.py` ends with `SDK-LINT: PASS`.
- **Scope and surface are exact.**
  - 27 files plus 22 prompts are exactly the 28 rows of §12.3, and nothing else changed outside `tests/` and `docs/`.
  - `__all__` lists 42 names. There are 9 aliases (6 pairs, 3 trios) with keyword-only steps, and no compose name appears in `native.__all__` or the root `vidbyte` package.
  - The diff adds no `noqa`, no `type: ignore` and no `os.environ` read. It changes nothing under tests, lint, contracts, `.github` or scripts since S2.
- **These weighted words hold on every path I traced.**
  - One writer. `verify.py:67-70` runs the writer alone between S0 and S1. The ensemble implementer runs only after the backstop at `ensemble.py:104`. Chain, handoff and stages run strictly in sequence.
  - No second timeout system. The only time bound compose adds is `COMPOSE_GIT_TIMEOUT_SECONDS`.
  - `text_truncated=True` is never decoded (`answers.py:124-125`).
  - Every verdict, plan, round and selection goes through the shared `JsonAnswers.ask` core. It allows at most 2 repair turns, all on the same thread (`answers.py:82`, `answers.py:100`).
- **The prompt-fit arithmetic is right, measured independently.**
  - Ten 100,000-character proposals into a Grok selector produce a 23,995-character prompt against a cap of 24,000.
  - Each proposal keeps 1,565 characters plus a note saying exactly 98,435 characters were left out.
  - The EC-23 change (~1,100 in the spec body, ~1,560 measured) is recorded in §17, and the README's "about 1,500" agrees with it.

FINDINGS (ranked, most severe first)

R-C1 [Blocker] [weighted word "every" / EC-16] vidbyte/harnesses/native/compose/verify.py:141-143 — A reader whose worktree cannot be removed after it answered loses its own answer and every finished sibling's answer, so `ThreadComposeError.result` drops step results and thread ids, against ledger 7 and EC-16
  Evidence:
  - **`_review` keeps no answer.** `verify.py:141-143` returns the answer from inside `async with DisposableWorktree.from_tree(git, after, before) as folder:`, so a removal failure in `__aexit__` discards it. Compare `_plan` at `ensemble.py:199-207`, which keeps it: `answer = await JsonAnswers.ask(...)`, then `except ThreadComposeError ... error.result = EnsembleResult(plan=answer)`.
  - **`fan_out` discards finished children.** At `calls.py:73-91`, after `asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)` it cancels the rest, gathers, and then `raise failure`. The values of children that already finished are thrown away.
  - **The verify record predates the stage.** At `verify.py:83-84` and `verify.py:89-94`, `record` is still `VerifyResult(writer=...)` when the error arrives, so `error.result = record`.
  - **The ensemble does the same.** See `ensemble.py:86`, `:93`, `:109` and `_propose` at `:220-222`. Its own header (line 9) admits it: "after one of several proposers running at once, the result holds the plan only".
  - **Repro.** Python run from stdin, with the real git and real worktrees; only `ThreadBinder.invoke` is faked. The slow reader keeps a file open in its worktree, which is EC-16's own trigger.
    - Two verifiers, the fast one finishing first, print `raised worktree_failed`, `error.result.verdicts = ()` and `thread ids in error.result: ['ses_writer']`.
    - One verifier prints the same three lines.
    - The error message reads: `Compose could not create or remove the folder C:\Users\422mi\AppData\Local\Temp\s4-rc1-dtj3p356\vidbyte-compose-worktree-c7t7agft (PermissionError). ... otherwise run git worktree prune, delete the named folder and retry.`
  Failure:
  - **Scenario.** In `verify_with(writer, [A, B])`, A answers (`ses_fast`) and B answers (`ses_slow`), but a file is still held open in B's worktree folder.
  - **What goes wrong.** Compose raises `WORKTREE_FAILED`, and its `result` holds only the writer. Both verdicts and both thread ids are lost, so the caller can neither read nor continue threads it paid for.
  - **One verifier is enough.** No sibling is cancelled, yet its answer is still dropped.
  - **The §17 deviation does not cover this.** It says "Several readers running at once (verifiers, proposers) give the record from before their stage, because the first failure cancels the others (D-17)". That reason does not apply to a single reader. It also cannot override the owner's ledger 7: "Partial success is reported, not discarded ... every thread id".
  - **D-17 and INV-14 do not excuse it.** D-17 only picks gather over `TaskGroup`. INV-14 cancels children that are still running; neither says to discard finished ones.
  Smallest fix:
  - In `_review` and `_propose`, capture the answer inside the worktree block, as `_plan` does. On the `ThreadComposeError` from the exit, attach that answer when `error.result is None`.
  - Have `fan_out` pass the values of finished children to the composite alongside the error it raises.
  - In verify and ensemble, build `error.result` from those values: the writer plus the finished verdicts, or the plan plus the finished proposals.
  - Cancelled siblings stay absent, as INV-14 requires. If `failed_verifiers` positions must stay exact on a partial record, that needs a one-line spec ruling.
  Spec IDs: ledger 7; INV-15; EC-16; D-26 ("always with the record so far"); INV-14 (bounds the fix); §17 "The record so far" bullet 3

R-C2 [Blocker] [weighted word "never" / INV-18] vidbyte/harnesses/native/compose/texts.py:88-99 — A template made only of placeholders sends the next step a blank prompt, and the step refuses it with `configuration.invalid_argument`, the outcome INV-18 and INV-29 say never happens
  Evidence:
  - **The up-front check measures only length.** `PromptFitter.check` (`texts.py:88-99`) renders only the longest form (`longest if spliced else text`) and checks characters or command-line units.
  - **`fit` falls back to the floor.** `fit` (`texts.py:115-140`) returns the share-0 floor `best` even when no candidate passes `_fits`. For a blank render, no candidate ever passes.
  - **Placeholder-only templates are accepted.**
    - `chain.py:105-106` accepts `"{previous}"`: it runs `require_template`, then `require_text` on the raw template, which is not blank.
    - `stages.py:103` and `stages.py:117` do the same for `stages[i].template`.
  - **The headers admit the gap.**
    - `chain.py:9`: "A template made only of {previous} sends a blank prompt when the previous answer is empty, which the next step refuses as its own failure (configuration.invalid_argument)."
    - `stages.py:9` says the same.
  - **Repro.** Python run from stdin; step 0 is faked, and step 1 is the real `run_grok_thread`, which checks its prompt before starting anything.
    - A whitespace answer prints `second step receives prompt: '   '`, `chain failed_step: 1`, `second outcome error: NativeThreadError FailureCode.CONFIGURATION_INVALID_ARGUMENT` and `staged failed_stage: 1`.
    - An answer of only NULs prints `second step receives: ''` and `failed_step: 1 | code: FailureCode.CONFIGURATION_INVALID_ARGUMENT`.
  Failure:
  - **Inputs.** `chain_threads([opencode, grok], "{previous}", prompt=...)`, or a later `StageSpec(template="{previous}")`.
  - **What goes wrong.** When the previous answer is empty, whitespace or only NULs, the next step is sent `''` or `'   '` and fails before it starts.
  - **What that contradicts.**
    - INV-18: "not blank", and "A step therefore never fails with configuration.invalid_argument because of a spliced value".
    - INV-29: "never sends a step a prompt the step would refuse".
    - EC-37's expected result: "The step runs".
  - **Not accepted anywhere.** No EC row accepts this.
  Smallest fix:
  - In the up-front checks (`ThreadChains._template` and `ThreadStages._fit`, or once in `PromptFitter.check`), also render the template with every spliced value empty.
  - If that render is blank, raise the existing `ConfigurationError` naming `template` or `stages[i].template`, the same way INV-18 already names them for a prompt that is too long.
  - This is not scope-adding, because INV-5 and INV-18 already require an up-front refusal.
  - The only alternative is an owner ruling that adds an accepted-limitation EC row and amends INV-18, INV-29 and EC-37.
  Spec IDs: INV-18; INV-29; FR-18 (P0); EC-37; INV-5

R-C3 [Major] [INV-4 key hygiene] vidbyte/harnesses/native/compose/chain.py:106 — A short caller prompt or template that holds a bound key and a NUL is quoted, key included, in a `ConfigurationError` raised by compose
  Evidence:
  - **The base validator quotes short values.** `RecordFieldValidator._received` (`vidbyte/lib/dataclasses/validation.py:159-167`) quotes any `str` whose repr is at most `NATIVE_QUOTED_VALUE_MAX_CHARS` (80) characters.
  - **Compose checks caller text with it** at `chain.py:46`, `chain.py:106`, `verify.py:51`, `ensemble.py:54`, `stages.py:103` and `answers.py:57-58`.
  - **Repro.** A Zhipu-shaped 49-character key (`<32 hex>.<16 chars>`) is bound to the opencode step.
    - The chain template case prints: `template must match [^\x00]+; got '0123456789abcdef0123456789abcdef.AbCdEfGhIjKlMnOp {previous}\x00'.` and `key in message: True`.
    - The chain `prompt` and the `verify_with` prompt print the same.
  - **The key test overclaims.** Its comments say "a ConfigurationError never quotes a key a caller put in a bad template" (`test_harness_compose_keys.py:111-112`) and "a ConfigurationError even when the caller put a key in a bad template" (line 3). The test only drives `{nope}` (line 139), which `require_template` refuses at `chain.py:105` without quoting anything.
  Failure:
  - **Scenario.** `chain_threads`, `verify_with`, `run_ensemble`, `run_staged_threads` or `parse_json_answer` gets a prompt or template that holds a bound key and a NUL, with a repr of at most 80 characters.
  - **What goes wrong.** The `ConfigurationError` message contains the key, against the INV-4 bullet "any `ConfigurationError` compose raises".
  - **Why Major, not Blocker.**
    - The caller must put its own key into its own short text, together with a NUL.
    - A typical xAI key (`xai-` plus 80 characters) is too long to be quoted.
    - The base functions behave the same way: `run_opencode_thread(zkey + "\x00", api_key=zkey, ...)` prints `key in message: True | key in repr(details): True`. Ledger 3's "still never" is therefore not regressed.
  Smallest fix:
  - Add one compose helper for these seven caller-text checks. It catches the `ConfigurationError`, replaces every bound key in the message with `COMPOSE_REDACTED_KEY`, and re-raises with the same `details`.
  - A test can use `"{previous}" + key + "\x00"`, which passes `require_template`.
  - The base functions' quoting is a follow-up outside this PR.
  Spec IDs: INV-4; AC-15; §14 Never bullet 1

R-C4 [Minor] [INV-11] vidbyte/harnesses/native/compose/verify.py:83-94 — After a reader's `WORKTREE_FAILED` the backstop is skipped, although INV-11 skips it only after a cancellation or a defect
  Evidence:
  - The backstop (`verify.py:88`, `ensemble.py:104`) comes after `fan_out` inside the `try`. The `except ThreadComposeError` re-raises without running it.
  - The module's own rule at `verify.py:8` says: "Do not skip the backstop after a verifier failed; skip it only on a cancellation or a defect."
  Failure:
  - A Grok PLAN verifier writes a file in place while an opencode sibling's worktree cannot be removed.
  - The composite raises `WORKTREE_FAILED` with `diff=None`. The reader's edit is never reported as a workspace change, which breaks §4's promise that "a reviewer that changes files is reported".
  Smallest fix:
  - The spec has no precedence between two compose failures, so this needs a ruling first.
  - Then run `DisposableWorktree.backstop` in the `WORKTREE_FAILED` branch. When the trees differ, attach the change, or raise `READER_CHANGED_WORKSPACE` from the worktree error.
  Spec IDs: INV-11

R-C5 [Minor] [ledger 10 / INV-20] vidbyte/lib/constants/native_compose.py:277 — `COMPOSE_TRUNCATED_PROBLEM` holds an instruction to the model in Python
  Evidence:
  - `COMPOSE_TRUNCATED_PROBLEM = "The answer was cut at the length limit, so it was not read. Answer again with a shorter JSON object."`
  - The other problem constants (lines 278-282) are purely descriptive.
  - `json_repair.md` already asks for a new answer: "Reply again with exactly one JSON object ...".
  Failure (convention):
  - Ledger 10 says "every sentence addressed to a model lives in a prompts/*.md file". D-10 admits problem texts only as error messages, that is, data.
  - A reviewer would write: "drop the imperative; json_repair.md owns the ask."
  Smallest fix: Keep only "The answer was cut at the length limit, so it was not read."
  Spec IDs: ledger 10; INV-20; D-10

R-C6 [Minor] [deviation record] docs/spec/native-thread-compose/spec.md:1567 — The deviation record puts `JSON_KIND_NAMES` on `ThreadStep`, but it is a module constant in `vidbyte/lib/util/json_text.py:57`
  Evidence:
  - `S3-implementer.md:122` says: "`ThreadStep` has `CONFIG_TYPES` and `JSON_KIND_NAMES` as class attributes."
  - `grep -n "^JSON_" vidbyte/lib/util/json_text.py` shows line 54 `JSON_FENCE`, line 55 `JSON_FENCE_LANGUAGES` and line 57 `JSON_KIND_NAMES`.
  Failure (record accuracy):
  - A repair agent looking for the recorded attribute finds nothing.
  - Three unrecorded module constants sit in a util module, not in `vidbyte/lib/constants`. Whether that placement is acceptable is the conventions lens's call.
  Smallest fix: Correct S3 item 8 and the §17 bullet to read: "`ThreadStep.CONFIG_TYPES`; `JSON_FENCE`, `JSON_FENCE_LANGUAGES` and `JSON_KIND_NAMES` in json_text.py".
  Spec IDs: n/a (§17 accuracy)

VERIFIED CLAIMS
1. **AC-1 runs the §4 text: HELD.**
   - `SNIPPET` equals the §4 block: 1,565 characters each, and the script printed `identical: True`.
   - The only source change is the folder literal.
   - The environment is stand-ins on `PATH`, the real git, placeholder `XAI_API_KEY`/`ZHIPU_API_KEY`, and `HOME`/`USERPROFILE`/`TMP` redirected.
   - The test passed.
2. **Test counts and lint: HELD.**
   - The compose pack has 276 cases, matching the test plan's 276.
   - The base pack has 436 passed and 2 skipped, which is INV-35's 438.
   - The lint loop passes.
3. **§12.3: HELD.** All 28 rows map to 27 non-prompt files plus 22 prompts. No other file outside `tests/` and `docs/` changed, and the diff has 80 files in total.
4. **Surface (INV-1, INV-24, NG-2): HELD.**
   - 42 names, and 9 aliases with signatures `(prompt, *, grok, muse)` and `(prompt, *, writer, grok, muse)`.
   - No compose name appears in `native.__all__` or the root package.
5. **"Exactly one writer per composite": HELD.**
6. **"Never" for the key, within INV-4's scope.**
   - argv and environment: HELD. The only overlay is `GIT_INDEX_FILE`, and 15 variables are removed.
   - `ThreadStep` repr: HELD.
   - `ThreadComposeError` attributes, checked by the AC-15 test: HELD.
   - `ConfigurationError`: DID NOT HOLD (R-C3).
7. **"Every step's result or error, every thread id, which step failed".**
   - Chain: HELD. The outcome is appended before the post-snapshot (`chain.py:66-80`).
   - Planner (`ensemble.py:199-207`) and selection: HELD.
   - Readers run through `fan_out`: DID NOT HOLD (R-C1, reproduced).
8. **"Only an empty result aborts" (D-26): HELD.** A composite raises only a `ConfigurationError` before any I/O, a `ThreadComposeError`, a cancellation or a defect, and step failures are recorded. What the record holds on failure is R-C1.
9. **"No composite invents a second timeout system": HELD.** grep finds only `COMPOSE_GIT_TIMEOUT_SECONDS` and the comment "no sleep and no backoff between attempts" at `stages.py:67-68`.
10. **"`text_truncated=True` must fail the parse": HELD.** `answers.py:124-125` returns the problem before `JsonText.decode` runs.
11. **INV-18.**
    - Length and unit fit and the note arithmetic: HELD (measured).
    - "Not blank": DID NOT HOLD (R-C2).
    - INV-17 (values are never parsed as templates): HELD.
12. **Open item 5 (EC-23): HELD, as a recorded deviation.**
    - Measured 1,565 characters kept per proposal; §17 records ~1,560, and the README says "about 1,500".
    - The spec's EC-23 body still says 1,100.
13. **EC-16.**
    - Message shape: HELD. It names the folder, and the next step names `git worktree prune`.
    - Its `result`: DID NOT HOLD (R-C1).
14. **EC-28 (bools refused in `kept`): HELD.** `to_tuple` refuses bools (`validation.py:178`).
15. **§5 against the real call path: HELD.**
    - The path is composite → `PromptFitter.fit` → `ComposeCalls.call` → `_invoke` (the Grok slot, for Grok only, `calls.py:94-99`) → `ThreadBinder.invoke` (`steps.py:86-97`) → the nine functions.
    - Verify takes S0 at `verify.py:67` and S1 at `:70`, and S2 inside `backstop` once every worktree is gone (`:88`).
    - The ensemble takes one snapshot before the planner (`ensemble.py:80`) and reuses it as the reader tree and the backstop baseline.
    - Chain snapshots only when the template has `{diff}`, before and after each step whose diff is read (`chain.py:62,71`).
    - The diagram's divergences are cosmetic, so there is no finding: composites call `ComposeGit.snapshot` directly rather than `DiffCapture`, and each worktree is added inside its fan-out child rather than before `par`.
16. **§8.4 budget: HELD.** 40 new files and 49 classes. The compose modules total 2,218 lines; the largest is `ensemble.py` at 260.
17. **The §14 Never list: HELD,** except the error-message clause (R-C3).
18. **S3 item 8 (`JSON_KIND_NAMES` as a `ThreadStep` class attribute): DID NOT HOLD** (R-C6).
19. **Open item 3 (blank `{previous}`): a violation, not an accepted limitation.** No EC row accepts it, and EC-37 contradicts it (R-C2).
20. **Open item 2, judged against ledger 7, EC-16 and D-17: a violation** (R-C1).

COMMANDS RUN
1. `git status && git log --oneline -5` → clean; `98613de2`, `e1bf20d8`, `ce8ad488`, `feea90c8`, `e05f812b`
2. `git merge-base HEAD origin/feat/native-grok-opencode-meta-hosts` → `5c08c35edcb1827e190ca4e2b2b1370808ef24be`, which is the base
3. `git diff --stat origin/feat/native-grok-opencode-meta-hosts...e1bf20d8` → `80 files changed, 12252 insertions(+), 28 deletions(-)`
4. `git diff --stat origin/feat/native-grok-opencode-meta-hosts...e1bf20d8 -- lint .semgrep contracts .github scripts` → (empty)
5. `git diff --stat 2ef11f3a..e1bf20d8 -- tests` → (empty)
6. `git diff --name-status origin/feat/native-grok-opencode-meta-hosts...e1bf20d8` with tests, docs and prompts filtered out → 27 files; prompts `22`; tests plus docs `31`
7. Python AST comparison of `SNIPPET` against the spec §4 block → `spec block len 1565 test SNIPPET len 1565` and `identical: True`
8. `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose/test_harness_compose_acceptance.py` → `1 passed in 2.53s`
9. `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose` → `276 passed in 43.55s`
10. `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads` → `436 passed, 2 skipped in 43.45s`
11. `PYTHONPATH=$(pwd) python lint/run.py` → `SDK-LINT: PASS` and `exit=0`; 0 REGRESSED or ERRORED
12. R-C1 repro (fake `ThreadBinder.invoke`, the real git, a file held open in the reader's worktree) → `raised worktree_failed`, `error.result.verdicts = ()` and `thread ids in error.result: ['ses_writer']`, for both the two-verifier and one-verifier cases
13. R-C2 repro → `second step receives prompt: '   '`, `chain failed_step: 1`, `NativeThreadError FailureCode.CONFIGURATION_INVALID_ARGUMENT` and `staged failed_stage: 1`. The EC-37 NUL variant → `second step receives: ''` and `failed_step: 1 | code: FailureCode.CONFIGURATION_INVALID_ARGUMENT`
14. R-C3 repro → `key in message: True` for the chain template, chain prompt and verify prompt. Base `run_opencode_thread` → `key in message: True | key in repr(details): True`
15. EC-23 measurement → `selector prompt length: 23995`, `kept prefix per proposal: [1565, ...x10]` and `notes: ['98435', ...] count 10`
16. Surface check → `42 names in compose.__all__`, `9 aliases`, `compose names leaked into native.__all__: []` and `compose names in vidbyte root: []`
17. `grep -n "sleep\|wait_for\|timeout\|deadline\|monotonic" vidbyte/harnesses/native/compose/*.py` → only comments in `stages.py`; the constants hold `COMPOSE_GIT_TIMEOUT_SECONDS = 120.0`
18. `git diff ... -- vidbyte pyproject.toml`, filtered for `noqa`, `type: ignore`, `os.environ` and `getenv` → no matches
19. `git status --short` (final) → empty

Every temporary repository under `%TEMP%` (`s4-rc1-*`, `s4-rc2-*`, `s4-ec23-*`, `s4-ec37-*`) was deleted. The lint log went to the session scratchpad, outside the worktree. No other file was written.
