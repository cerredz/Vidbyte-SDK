# S6 PR author report: native-thread-compose

- **Stage:** S6 PR author. Output: `docs/spec/native-thread-compose/pr-body.md`, the spec frontmatter and one §17 row, the title and body of draft PR #1186, and this report.
- **Tree:** `feat/native-thread-compose`. Launched at `67f3d918`; resumed at `42f9c969`, the orchestrator's interruption log, which changed only `pipeline.md`. The body and spec commit is `b7db56d2`; this report is committed alone on top of it. Base `feat/native-grok-opencode-meta-hosts` = `5c08c35e`, unchanged.
- **Date:** launched 2026-10-20; an API rate limit stopped the stage while it read the R-34 diff; resumed and finished 2026-10-21.
- **Platform:** win32, Python 3.11.0, pytest 8.3.5, git 2.49.0.windows.1, Node 22.12.0. The snippet ran only against the pack's stand-ins. No real `grok`, `opencode` or `muse`, no real key, no network for the snippet.
- **Scratch:** `S6` below is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s6`.
- **No source, test, prompt, README or REPO_MAP change.** Staged files: `spec.md` and `pr-body.md` in `b7db56d2`, then this report alone.

## 1. Result

- PR #1186 now has the title `feat(harnesses): composite thread functions across Grok, opencode and Muse (vidbyte.harnesses.native.compose)` and the body from `pr-body.md`. It is still a draft, still based on `feat/native-grok-opencode-meta-hosts`.
- The live body, read back as JSON (`gh pr view --json body`), equals the committed body exactly: 39,348 characters, one mermaid block, ending with the Claude Code line; the live title equals line 1. The body states both review caps (2 of 2 rounds at S1 and at S5) and that R-34 was fixed after the cap, so tests, gates, CI and the orchestrator verify it but no reviewer re-read it (`pr-body.md` line 228).
- Spec: `status: pr-open`, `updated: 2026-10-21`, `pr:` unchanged, one new §17 row. `git diff` showed exactly those three lines, `git diff --check` was clean, the file stayed CRLF (1,627 to 1,628 CRLF, no lone CR), and the §4 bytes hash the same before and after (`85fcc2c6a61ff328` over the CRLF section).
- CI and Static policy are dispatched on the final pushed head after this report is committed. Their run ids and conclusions go in the STATUS block, not in a commit, because a committed file cannot name runs on its own commit.

## 2. What the code does, in my own words

`vidbyte.harnesses.native.compose` turns the nine thread functions into building blocks.

- **Steps.** `bind_thread` and `bind_continue` build a `ThreadStep`, a frozen record that checks its arguments by building the same `NativeThreadRequest` the function would (with a probe prompt that is never sent), hides the key from `repr`, and stores `ThreadBinder.invoke` as its invoker. A composite accepts only a step whose function is one of the nine by identity, so a `functools.partial` or a lambda is refused. Composites always call `ThreadBinder.invoke`, never a stored invoker.
- **Checks before I/O.** Every composite checks its whole input first: the step table, the counts, the reader and fork rules, one workspace for `verify_with` and `run_ensemble`, the templates, and the prompt fit at its longest (`PromptFitter.check`). A refusal is a `ConfigurationError` that names the argument and quotes no caller text (`quote=False`).
- **Git.** Only `verify_with`, `run_ensemble`, `capture_diff`, `in_worktree` and a chain whose template splices `{diff}` need git. `ComposeGit` finds git and the repository root, takes snapshots as tree ids through a temporary `GIT_INDEX_FILE` (`read-tree HEAD` when a commit exists, `add -A`, `write-tree`), and diffs tree to tree with external diff and textconv off. Every git child runs through `CliRunner` with a fixed prefix, without the 15 variables that could point it at another repository, index or config, and within 120 s and 16 MiB bounds. The real index, HEAD and refs are never touched.
- **One step call.** `PromptFitter.fit` removes NULs, repairs surrogates, replaces every bound key with `[redacted]` and cuts spliced values to a fair share found by bisection, in characters and, on win32 for Grok and Muse, in command-line units. `ComposeCalls.call` then runs `_invoke`, which holds the per-loop, per-workspace Grok slot for a Grok step, and `ThreadBinder.invoke`. A `NativeThreadError` becomes a `StepOutcome` holding that very error; a cancel or any other exception propagates.
- **Read-only phases.** Readers (verifiers, and the ensemble's planner, proposers and selector) run concurrently under `fan_out`, which waits with `asyncio.wait(FIRST_EXCEPTION)`, cancels the rest and `settle`s them through any number of cancels, so exactly one exception propagates. A Grok reader runs in place in `PLAN` or `DEFAULT`; an opencode or Muse reader runs in its own detached worktree filled from the phase's tree (a verifier's index is set to the before-writer tree so git inside shows the change). Structured answers go through `JsonAnswers.ask`: exactly one JSON object, the caller's `parse`, at most two repair turns on the same thread, and a cut answer is never decoded. Afterwards `DisposableWorktree.backstop` snapshots again and raises `READER_CHANGED_WORKSPACE` with the diff and the record so far if anything changed.
- **The five composites.** `chain_threads` runs steps in order, splices `{previous}` and optionally `{diff}`, and stops at the first failure. `verify_with` runs the writer alone between two snapshots, then the verifiers on its diff, then the backstop. `handoff_thread` sends a summary turn on an existing thread and seeds a new thread with the answer, with no git. `run_staged_threads` runs each stage fresh and maps each failure through `STAGE_DECISIONS` to retry, raise a ladder rung, or abort, with no sleep. `run_ensemble` snapshots, plans one role per proposer, runs the proposers (an unanchored Grok fork is anchored at the planner's thread), narrows with selector rounds while more than five proposals remain and then selects, runs the backstop, and only then runs the implementer in place.
- **Failures compose owns** are a `ThreadComposeError` with a closed problem, a message in the INV-6 order with keys scrubbed, and the record so far in `.result`. A folder failure keeps only the `OSError`'s type and raises after the handler (R-34).

## 3. Deviations

**From the spec** (recorded in the body's "Deviations from the spec"): the four S5 lib grants, the git failure mapping, the EC-16 record, the EC-23 numbers, the smaller shapes of §17, and one item found here: §5 names helpers the composites do not call.
- `spec.md:147` labels the snapshot node `DiffCapture`, and `spec.md:154` labels the answer node `JsonAnswers.parse_json_answer`; INV-19's last sentence (`spec.md:400`) and T-1 (`spec.md:1113`) say the same. The composites call `ComposeGit.snapshot` and `diff`, `DisposableWorktree.backstop`, and the shared `JsonAnswers.ask` core, which `parse_json_answer` also uses after its own argument checks.
- `spec.md:179-180`: the sequence diagram adds the Muse worktree before `par`; the code adds each opencode or Muse verifier's worktree inside that verifier's own task (`vidbyte/harnesses/native/compose/verify.py:91` fans out `_review`, which enters `DisposableWorktree.from_tree` at `:157`).
- Behavior is the same, so §5 was not edited; the §17 row points to the body.

**From the request:** the ten recorded items, plus the trio hint (`capture_diff`, `asyncio.gather`, `parse_json_answer`) becoming direct `ComposeGit` calls, `fan_out` (D-17) and `JsonAnswers.ask`. All are in the body.

**From my briefing** (each deliberate):
1. **Dates.** The briefing said `updated: 2026-10-20` and a §17 row dated 2026-10-20. The rate limit pushed the edit past midnight, so both say 2026-10-21, the day the edit was made, matching the pipeline log's own timestamps.
2. **The §17 row** starts with the briefing's text, `finalized for review`, and adds one sentence about the §5 names, so the spec itself points at the naming difference. It is still one row.
3. **A read-only landing dry run.** `git merge-tree --write-tree --name-only --merge-base=5c08c35e origin/main HEAD` changes no branch, index or working tree (only unreachable objects); it showed 8 conflicting files, which the body lists. Nothing was merged, rebased or retargeted.
4. **The body names its own §5 findings** and adds a `### Public surface` subheading inside "How to use", where the briefing asked for the table.
5. **The §4 check.** The briefing's §4 hash prefix `89f3dbc59ec2b067` matched none of the extractions I tried (committed and working copy; raw, LF and CRLF; the whole section, without its heading, stripped; the snippet alone), and its method is not recorded. I checked §4 instead by hashing the same bytes, `## §4` up to `## §5`, before and after the edit (`85fcc2c6a61ff328` both times). `git diff --unified=0 42f9c969 b7db56d2` has hunks only at spec lines 4, 12 and 1576; §4 is lines 108-138.

## 4. Snippet output

Captured with a scratch pytest plugin (`S6/plugin/s6_snippet_tee.py`) that wraps `subprocess.run` and echoes the child's stdout, loaded with `-p` and `PYTHONPATH`, so the repository was not touched:

`PYTHONPATH="$(pwd);$S6/plugin" python -m pytest -q -p no:cacheprovider -p s6_snippet_tee -rA -s "tests/features/harness_compose/test_harness_compose_acceptance.py::test_developer_snippet_runs_as_written_against_stand_ins_on_path"`

At `42f9c969` (`S6/snippet_run.txt`; this run is the one in the body):

```
S6 SNIPPET RETURN CODE: 0
['ses_7d0d56c5-e2c5-45bd-827c-d24754e3ab64', 'a95bf4e2-20d0-4eaf-90d7-ecdfc15bee59'] None
['approve', 'approve'] True
None 3
1 passed in 2.73s
```

At `67f3d918`, before the interruption: `['ses_efb67e19-9773-4c04-8476-98e0ed1141e1', '9b15036f-97f5-4606-a501-5140fa1428ef'] None`, `['approve', 'approve'] True`, `None 3`, `1 passed in 2.55s`. The ids differ because the stand-ins mint them per run; the AC-1 test asserts the lines against the ids it reads from the stand-ins' logs (`test_harness_compose_acceptance.py:91-98`), then that no compose folder or registration is left and that `git status` shows only the writers' files (`:99-101`).

## 5. How the body's claims were checked

- **`S6/check_body.py`** (exit 0): conventional-commit title with no `[WIP]`; headings in the briefing's order; the body's snippet is byte-identical to spec §4 and to the AC-1 test's `SNIPPET` (1,565 characters each); the output lines have the shape the AC-1 test asserts; all 48 cited test functions and 15 cited test modules exist (`git grep "def <name>"`, `git ls-files`); all 28 eight-hex tokens are commits (`git cat-file -t`); no key-shaped text; body 39,348 characters, 39,386 bytes. A separate loop confirmed that all 21 review-table SHAs are ancestors of HEAD (`git merge-base --is-ancestor`). Every `path:line` citation in the body was read against the code at `b7db56d2`, and each points at the line it describes.
- **Mermaid** (`S6/mermaid-check/check.js`, re-run on the committed file): the body's chart parses and renders in mermaid 10.9.3 and 11.4.1 in headless Chromium (19 nodes, 26 edges, 2 subgraphs). The same checker fails a deliberately broken chart (`S6/mermaid-check/bad.md`, a parse error on both builds) and passes the spec's two §5 charts, so a pass means something. I read a PNG render (`S6/mermaid-check/flow.png`): every label is legible.
- **Fresh packs at `42f9c969`:** `389 passed in 56.94s` (compose) and `436 passed, 2 skipped in 43.39s` (base).
- **Remote runs at `1511846c`,** read with `gh run view`: CI 39531295940 success (Source / Python 3.11, Source / Python 3.12, Package), Static policy 39531298277 success. `git diff --stat 1511846c..42f9c969` touches only `docs/spec/native-thread-compose/` (4 files).
- **Landing facts on `origin/main` (`98a5d37b`):** `git merge-base --is-ancestor f216fdcf origin/main` holds; `tests/features/codex_host/test_codex_host_packaging.py:184-204` is `CodexHostFixedBytesTests`, which pins the SHA-256 of `native/__init__.py` (line 190) and the exact text of the REPO_MAP section (193-199) and of the README bullet (202-204); `git rev-list --count 5c08c35e..origin/main` is 85, and `5c08c35e` is not an ancestor of `origin/main`. The body's sentence on these pins (`pr-body.md` line 286) can be read as saying all three are hashes; only the marker's is. Its conclusion, that the pins move with the conflict resolution, holds, so the published body was left as it is.
- **Hygiene:** no file added under `__pycache__` or ending `.pyc`, no build output, no common key format in any added line of `git diff 5c08c35e HEAD`.

## 6. `gh pr view` and `gh pr checks` after the PR edit

```
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1186 --json title,isDraft,baseRefName,url,headRefOid
{"baseRefName":"feat/native-grok-opencode-meta-hosts","headRefOid":"b7db56d24292ad6c85cdcc1f3e8970c4b3326a65","isDraft":true,"title":"feat(harnesses): composite thread functions across Grok, opencode and Muse (vidbyte.harnesses.native.compose)","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1186"}

$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1186
no checks reported on the 'feat/native-thread-compose' branch
```

`gh pr checks` exits 1 because both workflows run only on `workflow_dispatch` (`ci.yml` also keeps `workflow_call`, which never starts by itself). A later JSON read showed the same title, draft state, base and head. The runs dispatched on the final head are in the STATUS block.

## 7. Candidate field-guide lessons (not written to the field guide)

Shape: trigger · preferred action · project-specific reason · quick check · link.

1. A PR body or report claims "checks green" in the SDK · dispatch `ci.yml` and `static-policy.yml` on the pushed head and cite run ids; in a committed file, cite the last code commit's runs plus "docs only since" · both workflows are `workflow_dispatch` only, so `gh pr checks` is empty · `gh run list --branch <b> --limit 4 --json headSha` equals `git rev-parse HEAD` · https://github.com/cerredz/Vidbyte-SDK/pull/1186
2. Turning an `OSError` into a scrubbed SDK error · keep only `type(error).__name__` in the handler, then build and raise after it, with no `from` · the `OSError` names a file a step may have named after a key; `from error` keeps it in `__cause__`, raising inside the handler keeps it in `__context__`, printed tracebacks show both, and `from None` only stops `__context__` from printing · `grep -n "from error"` over the module finds nothing, and a test walks `__cause__` and `__context__` · https://github.com/cerredz/Vidbyte-SDK/pull/1186
3. A test asserts on the file an `rmtree` failure names · assert on the exception chain directly, or rely on win32 and Python 3.11 · since CPython 3.12.4 (feb7870b46, GH-89727) the iterative POSIX `rmtree` catches a failed unlink again in its outer handler and sets `filename` to the folder being walked (`Lib/shutil.py:695-707` in the local 3.13.1), so CI's Linux 3.12 leg cannot show a held file's name · the CI log's CPython versions · https://github.com/cerredz/Vidbyte-SDK/pull/1186
4. A stacked PR whose base PR was squash-merged · measure landing with `git merge-tree --write-tree --name-only --merge-base=<base> origin/main HEAD`, which moves no ref, and list the conflicts in Follow-ups · #1036 landed as `f216fdcf`, so `main` does not descend from the base branch · `git merge-base --is-ancestor <base> origin/main` is false · https://github.com/cerredz/Vidbyte-SDK/pull/1186
5. Editing `vidbyte/harnesses/native/__init__.py`, the REPO_MAP native section or the harnesses README native bullet on `main` · update the pins in `tests/features/codex_host/test_codex_host_packaging.py` in the same change · `CodexHostFixedBytesTests` pins the marker's SHA-256 and the exact text of the map section and the README bullet · run that test file · https://github.com/cerredz/Vidbyte-SDK/pull/1186
6. A mermaid chart for a PR body · parse and render it with mermaid 10.9.3 and 11.x in headless Chromium (Playwright is installed globally) before publishing, and quote every label holding parentheses, brackets, commas or quotes · GitHub shows a syntax-error box instead of a chart · the checker prints `MERMAID CHECK: PASS` · https://github.com/cerredz/Vidbyte-SDK/pull/1186
7. Editing a pipeline file whose `git ls-files --eol` shows `i/lf w/crlf` · edit the bytes and end each new line with `\r\n` · the system git config (`C:/Program Files/Git/etc/gitconfig`) sets `core.autocrlf=true`; `git diff` normalizes line endings and so hides a mixed-ending file, but a byte hash of a section, such as a §4 check, changes with them · the CRLF count rose by exactly the lines added, no lone CR, and `git diff --stat` shows only your lines · https://github.com/cerredz/Vidbyte-SDK/pull/1186
8. Validating a model id · refuse control characters up front · the base `NATIVE_MODEL_PATTERN` (`^[A-Za-z0-9]\S*$`) matches a NUL, so the step binds and later fails as `launch_failed`, which `run_staged_threads` retries · `re.match(NATIVE_MODEL_PATTERN, "a\x00b")` matches · https://github.com/cerredz/Vidbyte-SDK/pull/1186
9. A refusal could quote caller text or a field a caller can fill · pass `quote=False`, including for records a caller builds directly or with `dataclasses.replace` · `RecordFieldValidator._received` (`vidbyte/lib/dataclasses/validation.py:163`) quotes a short scalar whose repr is 80 characters or fewer unless the field's name marks it secret, so a short key inside a prompt, template or thread id is quoted whole (R-3, R-33) · drive the refusal with a 16-character key and assert it is absent · https://github.com/cerredz/Vidbyte-SDK/pull/1186
10. Cleanup that must survive cancellation · run it as a task and wait with `asyncio.wait` in a loop that suppresses repeated cancels, then re-raise the first; let a started `git worktree add` finish · a second cancel or an anyio cancel scope otherwise cuts cleanup short, and a killed add leaves a locked registration (R-10, R-14) · the concurrency pack's second-cancel and anyio rows · https://github.com/cerredz/Vidbyte-SDK/pull/1186

## 8. Anything that looked wrong

None needs a source change before review; nothing here is an OPEN ITEM. Observations, with `path:line` at `b7db56d2`:

1. `vidbyte/harnesses/native/compose/workspace.py:136-142`: when entering a worktree fails half-way, a removal failure is suppressed so the first error wins. A leftover folder or registration then goes unreported. This is the documented choice (the file's WHAT NOT TO DO item 2), but it is a debugging gap.
2. `vidbyte/harnesses/native/compose/git.py:176-182`: if `_run` raises and `_delete` in the `finally` raises too, the `_delete` error propagates and the `_run` error survives only as its `__context__`. Both are scrubbed `ThreadComposeError`s, so nothing leaks; the first cause is just harder to see. A caller's cancel cannot be swallowed there, because `remove_worktree` is called only through `DisposableWorktree._settled` (`workspace.py:141`, `:154`), which runs it as a task of its own.
3. `vidbyte/harnesses/native/compose/ensemble.py:124`: `record.plan.thread_id is None` repeats what `_brief` already implies; it narrows the type only.
4. `vidbyte/lib/dataclasses/native_compose.py:194-195`: R-26 is still open (a whitespace-only diff file name raises after I/O on POSIX); it waits for the owner's ruling.
5. `vidbyte/lib/constants/native_threads.py:55`: the base model pattern accepts a NUL. I checked that such a model binds for all three harnesses; by `vidbyte/lib/process/runner.py:301-302` and `vidbyte/harnesses/native/hostkit/errors.py:161-167` it then fails as `launch_failed`. It is a base fix (NG-1), listed in the body.
6. Spec §5 and INV-19 and T-1 name helpers the composites do not call (section 3). Names only.
7. By design and listed in the body, not defects: `JsonAnswer.problem` keeps raw decoder text (EC-71), and a very short key makes the scrub rewrite ordinary text (D-28).
