# S6 PR author: infinite-memory-events

- PR: https://github.com/cerredz/Vidbyte-SDK/pull/1159 (draft, base `feat/infinite-memory-agent`)
- Title: `feat(infinite): add native run events and a model-free run handoff to InfiniteMemoryAgent`
- Diff read: `origin/feat/infinite-memory-agent...HEAD`. That is 68 commits before S6 (39 code or test, 29 `docs(spec)`): 36 code and test files, +4,334/−164, and 20 docs files, +3,691.
- Commits made at S6: `cfd64939` `docs(spec): finalize infinite-memory-events for PR` (spec frontmatter, the 31,093 figure, a §17 row, and `pr-body.md`), and this report's commit.
- No source or test file was changed at S6.

## What the code does (in my own words)

`InfiniteMemoryAgentSettings` gets one new field, `on_event`. It is `None` or a plain synchronous callable. `require_callable(optional=True, synchronous=True)` refuses anything async, including an async function behind `functools.partial` layers and an object whose class `__call__` is async.

At run time, `InfiniteMemoryRuntime.arun` builds one `InfiniteEvents` per run once the journal is open, then announces `run_started` or `run_resumed`. Everything after that sits inside `try/except BaseException`. On any exception the runtime announces `run_stopped` and re-raises it unchanged, so the journal never gets `run_finished` and the run stays resumable. On a normal return it calls `journal.finish(stop_reason, answer, root files)`, announces `run_finished`, and returns the reply with `metadata["infinite_run_id"]` set to the journal's stem.

`InfiniteEvents` is the only code that builds `InfiniteEvent` records. It has 14 public methods, one per kind. Each one:

- returns at once when there is no sink, so nothing is built;
- runs inside `_shielded`, which catches `Exception` only and logs `infinite_event_failed run_id=… kind=… error_type=…` with no event text;
- builds a flat details record.

Its helpers are:

- `_cut`: replaces lone surrogates with `?`, optionally collapses lines, and cuts with `" … [cut]"`.
- `_items`: keeps the first 5 plus an omitted count.
- `_key`: shortens a key over 508 characters to `~` + 16 hex digits of its SHA-256 + `/` + its last 490 characters, then adds the role suffix back.
- `_usage`: sums the tokens over the replies' rollups. The cost is known only if every rollup is complete.
- `_count`: clamps to 2^63−1.

`_deliver` stamps the time in UTC to the millisecond, builds the envelope, and calls the sink. If the sink returns a coroutine, `_deliver` closes it and raises `TypeError` inside the shield.

The emitting sites are:

- **Launch tool.** It emits `batch_rejected` when it refuses a batch. Then, in task order, it either journals `pair_started` and emits `subagent_launched`, or emits `subagent_replayed` for a name that already finished.
- **Pair.** `InfinitePair` keeps both replies for usage, emits `generator_finished` right after the generator's reply, and keeps typed `committed` and `dropped` lists. The card's `dropped` strings are rebuilt from those lists in their old exact words. It emits `subagent_finished` after `pair_finished` is journaled.
- **Memory tools.** They emit `memory_saved` (root only), `memory_staged`, `memory_dropped`, and `file_written` (created, appended, or edited) after each durable change, and `tool_refused` in each tool's error branch.

Model calls and `bash`, `grep`, and `read_lines` emit nothing.

`agent.run_handoff(run_id=None)` works in five steps:

1. It loads the journal in any state (`find(..., unfinished=False)`).
2. It reads this run's live entries and the notes' descriptions.
3. It lists each note once by its workspace-relative path. `relative()` never raises; a symlink loop gives the path back as given.
4. It renders the nine `InfiniteHandoff` sections with fixed wording, capping the Outcome at 239,000 characters, every other section at 15,900, and each list line at 1,000. The list-line cut goes through the new shared `TokenEstimate.truncate_chars`.
5. It saves `.runs/<run_id>.handoff.md` through an atomic write with `\n` line ends, and returns the handoff. No model is called.

## Snippet run (spec §4, verbatim)

The snippet ran at `e7c1c950` with `env -u VIDBYTE_API_KEY PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring PYTHONPATH=$(pwd)`. It used the pack's `ScriptedTree({ROOT: [reply("Acme is cheapest at 49 USD per seat.")]})`, so there were no network calls. `vidbyte` was imported from the worktree. The output:

```text
run_started root Run started: Compare the list prices of our five competitors.
run_finished root Run finished (final_response): Acme is cheapest at 49 USD per seat.
('Outcome', 'Work done', 'Decisions', 'Facts', 'Lessons', 'Open questions', 'Files', 'Unverified or failed work', 'How to continue')
```

The checks on that run:

- The output matches the spec's text block exactly (`True`).
- `memory/.runs` holds `<id>.handoff.md` and `<id>.jsonl`.
- The handoff file's bytes equal `to_context_text().encode("utf-8")` and contain no `\r`.
- `reply.metadata` includes `infinite_run_id`.

The PR body's extra usage lines were also run:

- `json.dumps(dataclasses.asdict(event), default=…)` serializes both events.
- An `async def` sink raises `ConfigurationError` with `details={'field': 'InfiniteMemoryAgentSettings.on_event'}`.

## Gates run at S6

The source is identical from `2073421b` to the head; every later commit is docs only.

| Gate | SHA | Final line(s) |
|---|---|---|
| focused pack (`tests/features/infinite_memory_agent`, the two helper test files) | `e7c1c950` | `193 passed in 7.42s` |
| `scripts/run_ci.py --stage source` | `e7c1c950` | `SDK-LINT: PASS` … `3 failed, 6123 passed, 16 skipped in 104.34s (0:01:44)` / `CI failed: Command failed with exit code 1: … -m pytest`. The failures are the 3 inherited `harness_threads` surface tests. |
| `scripts/run_ci.py --stage package` | `e7c1c950` | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| semgrep typed-mapping policy (scratch venv, 1.170.1) | `e7c1c950` | `Ran 1 rule on 982 files: 0 findings.` |
| `generate-sdk-public-api.py --check` | `e7c1c950` | `contracts/sdk-public-api.json is current at 52249854c2da0ca5961a743e961d5b8972fa35ce (vidbyte-sdk 0.3.0, 647 exports).` |
| worst-case re-measure (AC-30 builders, full envelope) | `e7c1c950` | `max details 27015 max event 31093`. Per-kind envelopes measured 4,072 to 4,079 bytes. |
| replay onto `main` (`git merge-tree --write-tree --merge-base=7efceb55 origin/main HEAD`) + focused pack | `main` `6f5a7310` + `e7c1c950` | No conflicts, tree `908eab5a`. `1 failed, 193 passed`; the failure is AC-34 `:517`. |

## Final PR state

`gh pr view 1159 --json title,isDraft,baseRefName,url` after the edit:

```json
{"baseRefName":"feat/infinite-memory-agent","isDraft":true,"title":"feat(infinite): add native run events and a model-free run handoff to InfiniteMemoryAgent","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1159"}
```

So the title has no `[WIP]` (the old title was `[WIP] feat: InfiniteMemoryAgent native run events and handoff`), and the PR is still a draft on the same base.

`gh pr checks 1159` prints `No checks reported on the 'feat/infinite-memory-events' branch` and exits 1. That is expected: this repo's PRs get no automatic checks, and runs started with `workflow_dispatch` are not attached to the PR.

The remote checks were dispatched with `gh workflow run CI --ref feat/infinite-memory-events` (run 39013426908) and `gh workflow run "Static policy" --ref feat/infinite-memory-events` (run 39013428202). `gh run watch --exit-status` exited 0 for both. Then `gh api repos/cerredz/Vidbyte-SDK/commits/cfd649396a616bd2cec4ac324a33737b73f14917/check-runs` returned:

```text
Package	completed	success
Static policy	completed	success
Source / Python 3.12	completed	success
Source / Python 3.11	completed	success
```

That is 4/4 green on `cfd64939`, with no rerun needed (the known `coding_agent` bash flake did not occur). This report's commit changes only `docs/spec/`, and its own dispatch is recorded in the STATUS message.

## Deviations recorded in the PR body

There are 11, and the PR body lists them all. Items 1 to 8 are spec §17 deviations 1, 2, 4, 5, 6, 7, 8 and 9; deviation 3 (the inline cut) was superseded by 9. Items 9 to 11 are found at S6:

- 9: the extra `INFINITE_HANDOFF_RUN_ID_METADATA_KEY` constant (m-6).
- 10: `require_callable` checks every partial layer, which is stricter than D-27's wording.
- 11: the whole-event figure is 31,093. It is now fixed in spec INV-33, §9.1 and §9.2, and the §17 row records it.

The other whole-event cells in §9.1 used a flat 4,076-byte envelope and are off by −4 to +3 bytes. They are left as estimates, because the S6 mandate allowed only the 31,093 figure.

## Things that looked wrong (not fixed; S6 changes no source)

1. **The PR base is stale. This blocks the merge.**
   - #1084 was squash-merged into `main` as `2c84049c` at 2026-10-16T19:45:40Z, from head `7efceb55`.
   - `feat/infinite-memory-agent` still exists at `7efceb55`, so GitHub did not retarget #1159, and `7efceb55` is not an ancestor of `main`.
   - Landing needs `git rebase --onto origin/main 7efceb55 feat/infinite-memory-events`, a force-push, and `gh pr edit 1159 --base main`. Both the force-push and the base change are the user's call.
   - The CLI sibling (#171) pins this branch, so re-pin it after the force-push.
2. **There is a semantic conflict with `main`'s #1169 (`08f67e7f`).** That PR makes `write_note` return `(created, relative)` and `edit_file` return the relative path, so the card's `files` holds the relative path once.
   - `tests/features/infinite_memory_agent/test_infinite_memory_events_pairs.py:517` asserts `["./notes/a.md", "notes/a.md"]` and gets `['notes/a.md']` on the replayed tree.
   - The fix after the rebase is to assert `["notes/a.md"]` and reword INV-28's card-files clause, EC-16, D-23 ("card keeps the model's spelling"), and AC-34's card clause. D-23's own rejected alternative is exactly what #1169 did.
   - After the rebase, rerun `generate-sdk-public-api.py --check`, because its `source.commit` pin moves.
3. **Bounded leak (observation, not a bug).** `vidbyte/agents/infinite/events.py:196` stores a launch time per pair, and `:229` pops it only in `generator_finished`. A pair whose generator raises leaves its entry until the run ends. The leak is bounded by the run's pair count.
4. **No `run_stopped` for a sink interrupt on the opening event (judged and kept, D-9).** If the sink raises `KeyboardInterrupt` while receiving `run_started` or `run_resumed` (`vidbyte/agents/infinite/runtime.py:88`, `:90`, before the `try` at `:96`), no `run_stopped` follows.
5. **Inherited `harness_threads` failures.** The three `tests/features/harness_threads/test_harness_threads_surface.py` tests (`:193`, `:232`, `:258`) fail at base `7efceb55` too. They diff against `merge-base origin/main HEAD`, which is far behind now that #1084 landed on `main` as a squash. Remote CI is green.

## Candidate field-guide lessons (for the orchestrator; S6 does not write the field guide)

Evidence for all of these is PR #1159 (https://github.com/cerredz/Vidbyte-SDK/pull/1159) and its `docs/spec/infinite-memory-events/review.md`.

1. **A stacked PR's base can merge under you.**
   - When: S6, or any late stage, on a PR whose base is another open PR's branch.
   - Do: run `gh pr view <base#> --json state,mergedAt,mergeCommit` and `git merge-base --is-ancestor <base tip> origin/main` before writing "merges after #N". Then replay without touching the worktree, using `git merge-tree --write-tree --merge-base=<base tip> origin/main HEAD`, and run the focused pack on that tree (`git archive <tree>` into scratch).
   - Because: a squash merge leaves the base branch in place, so GitHub does not retarget, and a clean text merge can still hide a semantic conflict. Here #1169 broke the AC-34 card clause.
   - Check: `gh pr view --json baseRefName`.
2. **Production headers must not send maintainers to `docs/spec`** (R-1). Point them at the test tables that enforce the rule. Because: AGENTS.md says `docs/` is unmaintained and off-limits in ordinary work. Check: `git grep -n "docs/spec" vidbyte/ | grep -v "RELATED DOCS"`.
3. **When an import cycle blocks the natural canonical helper**, move the logic down into a dependency-free lib module (here `vidbyte/lib/util/text.py`) and have the higher helper delegate to it, instead of copying it inline (R-7). Check: a differential test of the old cut against the new one (1,404 cases, 0 mismatches).
4. **Meet a line budget by asking for a cap or laying out one keyword per line**, not by packing keyword arguments (R-V1 → m-1). Because: `events.py` ended at 400/400 with a 414-character line that no formatter enforces.
5. **Commit subjects cite only the IDs that commit implements** (R-V7 → m-10). Fix a wrong one in the PR body, never by rewriting history.
6. **A "never raises" path helper must catch `RuntimeError`** (R-2). Because: on the Python 3.11 floor, `Path.resolve()` raises it on a symlink loop. Check: a test that replaces a note with a symlink loop, kept true on 3.13 as well.
7. **Prove a no-sink fast path builds nothing by counting record construction with `monkeypatch`** (R-4). Because: removing the guard in `_deliver` breaks mypy, so a mutant there is not a fair proof.
8. **Measure byte-size bounds on the full envelope**, with a millisecond `at` and the longest role, not as details plus a flat envelope estimate (m-8, rr-2). The flat estimate was 2 bytes low on the worst case and up to ±4 bytes off on the others.

Smaller practical notes:

- In this worktree `core.autocrlf=true`, so `spec.md` is CRLF in the working copy. An edit script must normalize `\r\n` before exact-match replacements.
- `gh pr edit --body-file` takes the body from line 2 onward of `pr-body.md`, with `\r` stripped.
