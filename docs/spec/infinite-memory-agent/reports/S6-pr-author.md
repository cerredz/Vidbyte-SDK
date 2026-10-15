# S6 PR author: report

PR: https://github.com/cerredz/Vidbyte-SDK/pull/1084 (draft, base `main`), head `9babcaa1`.

- Title set: `feat(agents): add InfiniteMemoryAgent — a delegating agent with a guarded file-workspace memory`.
- Body: `docs/spec/infinite-memory-agent/pr-body.md`, line 2 onward. The remote body was checked to be identical to that file.

Source, test and lint files are unchanged by this stage. This stage changed only three files:

- `pr-body.md` (new);
- `spec.md`: the frontmatter, §5's two diagrams and its last paragraph, and one §17 row;
- this report, which is not committed; the commit named only `spec.md` and `pr-body.md`.

## 1. What the code does (written from the diff before opening the spec)

**Construction.** `InfiniteMemoryAgent(settings)` (`vidbyte/agents/infinite/agent.py`) accepts only an `InfiniteMemoryAgentSettings`. The settings check every field in `__post_init__` (`settings.py`):

- names and the prompt must be non-blank;
- the provider becomes an enum, and the provider/model pair is checked against `ProviderModelRegistry`;
- `root_dir` must exist;
- the workspace, policy and loop must be the SDK's own types;
- the extras must form a valid `Tools` catalog and use no reserved name;
- `max_depth` and `max_parallel` must be at least 1, and `max_agents` at least 2.

The workspace settings resolve `root`, accept the preset or its value, check that the seeds exist with distinct names, and require whole-number caps of at least 1, with `max_file_tokens <= max_tokens`.

The agent then builds `InfiniteWorkspace`. That creates the folder and the three empty bookkeeping files, copies each seed to `seed/<name>` and makes the copy writable, and refuses a workspace already over a cap. Last, it calls `BaseAgent.__init__` with:

- runtime `INFINITE_MEMORY`;
- the developer prompt plus the root rules;
- `bash` over `root_dir`, then `grep` and `read_lines` over the workspace, then the extras;
- a `MessageHistoryCompactionMiddleware` trim at 60,000 tokens;
- the default loop: 100 iterations, tool results cut at 100,000 characters.

**Each run.** `run(task)` reaches `InfiniteMemoryRuntime.arun` (`runtime.py`), which gets settings, workspace and any resuming journal from `_runtime_extension_kwargs`. It runs these steps in order:

1. Refuse the run if any tool already uses a run-bound name. Nothing is journaled yet.
2. Take the extras: every non-reserved, non-internal tool the root holds now.
3. Start a journal at `.runs/<UTC>-<8 hex>.jsonl` with `run_started`, or continue the resumed journal.
4. Add `launch_subagent` and the root's memory tools. The root's `remember` commits at once, with `verified_by` null.
5. Clear `tool_calls` and `history`, and drop `options["tools"]`.
6. Copy the context manager, and upsert the workspace map at `TOP_OF_CONTEXT`.
7. Run the inherited loop, re-rendering the map after every tool iteration.
8. When the loop returns, write `run_finished`. A cancelled or failed run has none, so it stays resumable.

**One launch.** `InfiniteLaunchTool.execute` (`launch.py`) works in this order:

1. Read the tasks into closed `InfiniteTaskCard`s (1 to `max_parallel`; unknown fields refused).
2. Separate names already finished in this run; these replay their recorded card.
3. Check the batch. The name check covers the whole batch. The tool-grant check (a subset of the launcher's extras), the live `#N` context check and the `max_agents` check cover only the new pairs.
4. On any failure, return `ToolResult.error`. Nothing starts.
5. Write `pair_started` for each new pair.
6. Run the new pairs through `ParallelPipeline`, unless there are none.
7. Return the cards in task order, with replays labelled.

**One pair.** `InfinitePair.run` builds and runs two agents:

1. The generator is a plain `BaseAgent` with:
   - a fresh context holding the map, and the generator rules;
   - the three preset tools, plus staging memory tools over the pair's shared staged and dropped lists;
   - `launch_subagent` when depth + 1 < `max_depth`;
   - the named extras, cloned through `AgentForker._clone_tool`;
   - the same model, policy and loop, and its own history trim.
2. Its status: a blank reply is FAILED; `final_response` or `is_done` is DONE; anything else is PARTIAL.
3. After one fairness `sleep(0)`, unless the status is FAILED, a verifier runs. It gets `drop_entry` and no launch tool. Its message carries the card, the status and summary, the staged entries and the files written, never the transcript.
4. The verdict is the last `VERDICT:` line; with none, it is UNCHECKED.
5. Unless the verdict is UNCHECKED, the staged entries are committed, each checked again (a FAILED verdict commits too, as INV-15 says).
6. `_finish` drops the rest, builds the `InfiniteResultCard` and writes `pair_finished`.

Any `VidbyteSdkError`, `OSError` or `ValueError` becomes the pair's own UNCHECKED card, with the error's cause as the review. Cancellation propagates.

**Workspace.**

- Every write runs under one class-level lock and recounts the file and token totals from disk, excluding `.runs/`.
- Entry rules: at most the token cap, not a duplicate of a live or staged entry with case and spacing ignored, `supersedes` must name a live entry, and the text must be UTF-8-encodable.
- Ids are one more than the highest live or superseded id.
- A supersede moves the old line to `superseded.jsonl`.
- Note-path rules: inside the root, a text suffix, one line, no colon, and not `seed/`, `.runs/` or a bookkeeping file, compared casefolded.
- Each agent may create one new file, with a one-line description.
- Every file write is a temp file plus `os.replace`.
- `map_text` never raises on content.

**Journal.** Each record is ASCII JSON, flushed, fsynced and closed under a lock. A torn last line is ignored and cut off before the next write. `find` checks the run id pattern, then returns the newest unfinished run or the one named.

**Resume.** `resume()`/`aresume()` find the journal and set a per-instance `ContextVar`, then run with a resume prompt: the task, one line per finished root pair, and the names of interrupted ones. Relaunching a finished name replays its card, and an interrupted one runs again.

**Shared pieces and exports.**

- `TokenEstimate` (characters divided by four, rounded up) is the canonical helper in `vidbyte/lib/util/text.py`.
- `INFINITE_MEMORY` is added to `_LINEAR_LOOP_RUNTIMES` and to `RuntimeRegistry`.
- There are six enums, six records and one constants module.
- The new 40-leaf prompt family holds all model-facing text.
- The root exports four names, and the public-API contract is regenerated.
- `session_persistence_supported = False`.

## 2. Spec §4 snippet: what I ran and what it printed

I ran `$S/s6/run_snippet.py`, where `$S` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/316f126c-6db0-45d5-b506-cdb76c0921d5/scratchpad`:

```
PYTHONPATH=$(pwd) python -B $S/s6/run_snippet.py $S/s6/work
```

The script holds spec §4's snippet verbatim, run inside `ScriptedTree.install()` from the test fixtures. That patches `BaseAgent._runner_for_model` to answer by agent name, so no network call is made. The scripted model:

- the root launches task `pricing`;
- the generator calls `remember` with one fact, then replies;
- the verifier replies with `VERDICT: passed`;
- the root answers.

The snippet ran as written. Its output is in `$S/s6/snippet-output.txt` and in the PR body: the root's answer printed, and then the card the root received, which was `done`, `passed`, with entry `#1`. `memory/` held:

- `seed/brief.md`;
- the three bookkeeping files;
- one journal: `run_started`, `pair_started`, `pair_finished`, `run_finished`.

The entry carried `by=root/pricing/gen` and `verified_by=root/pricing/ver`, and usage showed 5 model calls. AC-1 is met, and no OPEN ITEM arises from the snippet.

## 3. Deviations found (code vs spec §4, §5, §8, §9, §12)

All are recorded in spec §17 (S3 and S5 lists), and the PR body's "Deviations" section repeats them:

1. **Model catalog check.** Stricter than a plain `BaseAgent`; the same as `BaseAgentSettings`, with `STRICT_MODEL_VALIDATION = False` as the escape hatch. §9.3 line 760's "same meaning as `BaseAgent`" is about meaning; the PR body says so (R-7, R-30).
2. **Note paths.** One line, no colon, protected names casefolded (R-1, R-8, R-2). INV-20 lists only three rules.
3. **UTF-8.** Memory text must be UTF-8-encodable (R-27).
4. **Workspace writes.** Every write is a whole-file temp file plus `os.replace`, appends included. `superseded.jsonl` is written first. Stamps read `+00:00`, not `Z` (§9.1, row 17).
5. **Journal.** ASCII JSON, and a complete last line without its newline is kept (D-25, §9.1).
6. **Seed copies.** Made through `LocalFileSystemBackend.copy`, then made owner-writable (D-24; R-7, R-26).
7. **Constants and yield.** Four constants beyond row 3 (`INFINITE_ROOT_DEPTH`, `INFINITE_DEPTH_STEP`, `INFINITE_PAIR_TURN_SECONDS`, `INFINITE_MIN_CAP`), and the fairness `sleep(0)` (R-13).
8. **§8.5 internal shapes.**
   - `check_entry(draft, staged: tuple[InfiniteStagedEntry, ...])` takes staged entries, not drafts.
   - `quota()` is public.
   - `InfinitePair.render` and `finished_lines` are added.
9. **Inline texts.** Five short model-facing formats are inline literals, not `INFINITE_` constants (§9.2; R-14, open).

**§5 drift, fixed in this stage.** The sequence diagram showed the commit as unconditional, it left out the skipped verifier, and the prose named only `VidbyteSdkError` for the pair guard. The code follows INV-12, INV-15 and INV-29. I replaced both §5 diagrams with the PR's flow chart and sequence, corrected the paragraph, and logged it in §17 (row `r5 | 2026-10-15 | S6 PR | finalized for review …`).

**Complexity budget.** §8.4 holds: 18 new non-test files, 15 modified, no new dependency.

## 4. Verification I ran (at `ff23d32d`; logs in `$S/s6/gate-*.txt`)

| Gate | Final lines |
|---|---|
| Pack | `111 passed in 3.11s` |
| `python lint/run.py` | `SDK-LINT: PASS`. 0 REGRESSED among 133 rule lines. C012 23 and S061 5 are IMPROVED against the baseline, as on main. `lint/` is unchanged. Re-run after the docs commit `9babcaa1`: `SDK-LINT: PASS`, 0 REGRESSED. |
| ruff I001 | `Found 223 errors.`, and an `origin/main` export gives 223 too |
| semgrep (via `$S/s5-1/semgrep_launch.py`) | `Ran 1 rule on 946 files: 0 findings.`, exit 0 |
| `scripts/generate-sdk-public-api.py --check` | `contracts/sdk-public-api.json is current at 41e9421044f1f8bf91111262b451ab86b031d792 (vidbyte-sdk 0.2.1, 643 exports).` |
| source stage | `5284 passed, 14 skipped, 1 warning in 55.17s` / `CI passed.`. The warning is an MCP stdio unclosed transport in `test_remote_jsonrpc_error`; the flaky MCP test passed this run. |
| package stage | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |

Final PR state:

```
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1084 --json title,isDraft,baseRefName,url,headRefOid
{"baseRefName":"main","headRefOid":"9babcaa155d4178dd0dc39a0e71629ca5bb3da0b","isDraft":true,"title":"feat(agents): add InfiniteMemoryAgent — a delegating agent with a guarded file-workspace memory","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1084"}
$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1084
no checks reported on the 'feat/infinite-memory-agent' branch
```

There are no remote checks. Five of the six workflows carry "TEMPORARILY DISABLED"; `claude.yml` runs only on an `@claude` review or comment. Nothing was dispatched. `mergeable: MERGEABLE`, and `mergeStateStatus: BLOCKED` while the PR is a draft. `origin/main` has not moved past the merge base `179d8adc`.

## 5. Things that looked wrong while reading

Neither item below breaks a spec ID. Both are listed in the PR's Follow-ups.

1. **`vidbyte/agents/infinite/memory.py:98-99` (and `:105-106` for `edit_file`).** `files_written` keeps the model's raw path spelling. A note written as `./notes/a.md` and then as `notes/a.md` shows up twice on the card, while `files.jsonl` holds one normalized path.
   - Probe: `$S/s6/probe_observations.py` printed `card files: ['./notes/a.md', 'notes/a.md']`.
   - Fix: record the `relative` path that `_note_path` returns, which the workspace would have to hand back.
2. **`vidbyte/agents/infinite/journal.py:81-83`.** `find(None)` parses journals newest first, so a malformed line in a newer **finished** journal refuses resuming an older unfinished run.
   - Probe output: `resume(None): ConfigurationError - The journal 20261016T081500Z-5e6f7a8b.jsonl has a bad record at line 2; fix or remove that line before resuming.`
   - The message is actionable, so this is minor.
   - Fix if wanted: skip finished journals by scanning for a `run_finished` line before a full parse, or catch the parse error per file while searching.
3. **Stale gate wording (docs only).** `docs/spec/infinite-memory-agent/spec.md:439` (NFR-6), `:847` and `:1077`, and `context/code-map.md:29`, say the lint's final line is `AGENT-LINT: PASS`. `lint/run.py` prints `SDK-LINT: PASS` (`lint/core/report.py:58`). I did not edit those lines, which are outside my grant.

I saw no dead code. I did not mutation-test the pack; S4's mutation plugin already found the three vacuous spots, and R-11 fixed them. Every AC test the spec names exists on the branch (47 of 47 names), and the pack collects 111 tests.

## 6. Candidate field-guide lessons (report only; not written to the field guide)

Each entry gives a trigger, the preferred action, the project-specific reason, a quick check, and the link: https://github.com/cerredz/Vidbyte-SDK/pull/1084.

1. **Don't offset a new lint finding by editing untouched code (R-5, conventions).**
   - Trigger: a PR adds a finding to a ratcheted rule (here S062 in a new test), and the count is kept equal by "fixing" an old finding in a file the spec does not list.
   - Action: fix the new finding where it was introduced, and restore the untouched file.
   - Reason: `lint/README.md` ratchets "freeze existing debt while failing any count increase", and AGENTS.md says "Do not rewrite untouched code just to make it conform".
   - Check: `git diff origin/main...HEAD -- <file>` shows only the rows the spec lists, and `python lint/run.py --rule S062 --all` still lists main's own locations.
2. **Compare lint counts with an `origin/main` export, not just the baseline (R-7, conventions).**
   - Trigger: `lint/run.py` passes, and a rule shows RATCHETED at the baseline count.
   - Action: run the rule on a `git archive origin/main` export. If main is IMPROVED below the baseline, your PR spent that headroom, so remove your new finding.
     - For C012, call `ProviderModelRegistry.validate_provider_model_pair` in a `_validate_model` helper; inline, it raises S008.
     - For S061, copy through `self.backend.copy(...)`, because only `<x>.backend.<method>` receivers are exempt.
   - Reason: the baseline holds stale headroom from other reductions.
   - Check: `python lint/run.py --rule C012` and `--rule S061` give the same counts at HEAD and on the main export.
3. **A model-field catalog check makes settings stricter than `BaseAgent`, so say so (R-7, R-30, conformance).**
   - Trigger: a new `*Settings` has `provider` and `model_name` fields, and C012 forces a `ProviderModelRegistry` check.
   - Action: document that the settings accept only catalog names, like `BaseAgentSettings`, and name the `ProviderModelRegistry.STRICT_MODEL_VALIDATION = False` escape hatch. Never claim parity with a plain `BaseAgent`.
   - Reason: a plain `BaseAgent` runs `gpt-4.1-2025-04-14` and the like, which the settings refuse.
   - Check: build the settings with a dated model name, with strict mode on and off.
4. **`LocalFileSystemBackend.copy` keeps mode bits (R-26, conformance).**
   - Trigger: copying a developer file into a folder that a later construction will copy over again.
   - Action: after `self.backend.copy(src, dst)`, run `dst.chmod(dst.stat().st_mode | stat.S_IWRITE)`. Enforce read-only status through path rules, not file modes.
   - Reason: the backend uses `shutil.copy2`, so a read-only source makes the second copy raise `PermissionError`, which breaks re-attach and resume.
   - Check: build the agent twice over a `chmod 0444` seed.
5. **Prompt-catalog descriptions still need 4–5 general sentences (R-10, conventions).**
   - Trigger: tool or parameter descriptions loaded with `Prompts().get(...)`.
   - Action: write 4–5 general sentences with no concrete examples, as `model-facing-tool-contracts.md` asks.
   - Reason: S025 skips text built by a method call, so the lint passes on one-line labels; the rule still applies.
   - Check: a sentence count per leaf of the family JSON (S4's `count_sentences.py`).
6. **Compare protected paths casefolded (R-2, conformance).**
   - Trigger: a tool refuses writes to reserved names under a root resolved with `FileSystemPermissions.resolve_scoped_path`.
   - Action: compare `relative.as_posix().casefold()` with the lowercase constants.
   - Reason: on default macOS, `Path.resolve()` keeps the caller's case, so `Entries.jsonl` passes a case-sensitive check. Windows hides this because `resolve()` returns the disk's case.
   - Check: `write_note("SEED/x.md")` and `write_note("Entries.jsonl")` are refused.
7. **Build a stage's card and write its record inside the stage guard (R-1, conformance and engineering).**
   - Trigger: a `BasePipeline` stage run under `ParallelPipeline` that records its result.
   - Action: put the record build and the journal write inside the `try` that catches `VidbyteSdkError`/`OSError`/`ValueError`, and write journals as ASCII JSON (`json.dumps` without `ensure_ascii=False`).
   - Reason: an exception that escapes one stage loses every sibling's result (`jev-capability-layout.md` stage rule), and a lone surrogate from a model reply cannot be UTF-8-encoded.
   - Check: a pair whose summary holds `\ud83d` still returns its siblings' cards.
8. **Look for a lib helper before writing another atomic write (R-20, conventions; open).**
   - Trigger: a temp file plus `os.replace` written inline.
   - Action: check `vidbyte/lib/` first. Two inline copies already exist (`sessions/stores/file.py` and `sources/cache/file.py`), so the third should become an atomic option on the lib filesystem helper, in its own PR.
   - Reason: AGENTS.md principle 5.
   - Check: `grep -rn "os.replace" vidbyte/`.
