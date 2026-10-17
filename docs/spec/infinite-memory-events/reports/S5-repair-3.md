# S5 repair 3: infinite-memory-events (replay onto main)

New branch `feat/infinite-memory-events-on-main`, replayed from `feat/infinite-memory-events` at `7692b9bc` onto `origin/main` at `6f5a7310`. PR https://github.com/cerredz/Vidbyte-SDK/pull/1159 is untouched: its head is still `7692b9bc` and its base is still `feat/infinite-memory-agent`. `SCRATCH` below is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/3e21357e-da06-45b9-8218-c0b25aec2a6d/scratchpad`. This iteration's files are in `SCRATCH/s5r3/`.

## Outcome

- The replay was clean: 71 of 71 commits, no textual conflict, and no design decision needed. The PR's diff on `main` is line-for-line the diff it had on `7efceb55`.
- One semantic conflict was found, the one S6 predicted. `main`'s #1169 records each note on the card once, by its workspace-relative path. Four spec clauses were reworded, then the one granted assertion followed them.
- The public-API contract is current with no regeneration. Its blob is `91e9f11893e8` before and after, so the CLI sibling does not re-vendor.
- Gates: focused 194 passed, lint PASS, package PASS, semgrep PASS, contract PASS, and remote checks 4/4 green on `4aba9eac`. The local source stage fails only 2 branch-scoped `harness_threads` checks. One fails on `main` itself. The other fails on `main` as soon as any root export is added. CI skips both.

## Gate matrix

The source and tests are at `4aba9eac` (the last code or test commit). During the package stage, semgrep, and the probes, only `docs/spec/infinite-memory-events/pr-body.md` was uncommitted. All commands ran from the worktree root, prefixed by `env -u VIDBYTE_API_KEY PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring` (except where no PYTHONPATH is noted).

| Gate | Command | Result | Final lines |
|---|---|---|---|
| focused tests | `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py -q -p no:cacheprovider` | PASS | `… [ 74%]` / `… [100%]` / `194 passed in 5.52s` (progress dots elided). This is 193 from this PR plus `main`'s #1169 test `test_a_note_written_under_several_spellings_is_listed_once_on_the_card`; `main` alone collects 114 in the feature folder |
| focused tests, feature folder (the briefing's command) | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS | `188 passed in 5.43s` |
| changed test, kill check | the AC-34 test at the head; then in `SCRATCH/s5r3/mut` (a `git archive HEAD` copy) with #1169's two assignments in `memory.py` reverted | PASS at the head; KILLED by the mutant | head `1 passed in 0.79s`; mutant `E AssertionError: assert ['./notes/a.md', 'notes/a.md'] == ['notes/a.md']` / `1 failed in 1.38s` |
| lint | `PYTHONPATH=$(pwd) python lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. Lower it with: …` / `S064 RATCHETED: 4 known finding(s). Inspect with: …` / `SDK-LINT: PASS`; exit 0; no rule REGRESSED; `lint/baseline.json` untouched |
| full gate, source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | FAIL, inherited only | `reasoning trace contracts: ok (182 tools, 55 shapes)` / `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `=========== 2 failed, 6524 passed, 16 skipped in 107.21s (0:01:47) ============` / `CI failed: Command failed with exit code 1: … -m pytest (cwd=…vidbyte-sdk-infinite-memory-events).` Earlier in the log: `SDK-LINT: PASS`, `context write-path integrity: ok`, `context primitive introductions: ok` |
| full gate, package stage | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `> …\venv\Scripts\python.exe -c from importlib.metadata import …` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| semgrep static policy | `PATH="<SCRATCH>/semgrep-venv/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (1.170.1) | PASS | `Scanning 1247 files tracked by git with 1 Code rule:` / `Scanning 1006 files.` / `Ran 1 rule on 1006 files: 0 findings.`; exit 0 |
| public-API contract | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 52249854c2da0ca5961a743e961d5b8972fa35ce (vidbyte-sdk 0.3.0, 647 exports).`; exit 0 |
| §4 snippet | `PYTHONPATH=$(pwd) python SCRATCH/s6/run_snippet.py` | PASS | `---- match spec text block: True` / `---- .runs: ['…handoff.md', '….jsonl']` / `---- handoff bytes == to_context_text().encode('utf-8'): True \| has \r: False` |
| worst-case size | `PYTHONPATH=$(pwd) python SCRATCH/s6/measure_events.py` | PASS | `max details 27015 max event 31093` |
| remote checks @ `4aba9eac` | `gh workflow run CI --ref feat/infinite-memory-events-on-main` (run 39039578860), `gh workflow run "Static policy" --ref …` (run 39039580375), then `gh api repos/cerredz/Vidbyte-SDK/commits/4aba9eac6dc09123955460ecf8b0d9783a48c6ba/check-runs` | 4/4 green | `Package completed success` / `Source / Python 3.11 completed success` / `Source / Python 3.12 completed success` / `Static policy completed success`. No rerun was needed |

The final head adds only `docs/spec/` commits after `4aba9eac`. It was dispatched again after this report was pushed. Its run ids and check-runs are in the STATUS message, because a commit cannot record its own checks.

## Step 2: the replay

- **Overlap check before replaying.** `git diff --name-only 7efceb55 7692b9bc` and `git diff --name-only 7efceb55 origin/main` share three files:
  - `vidbyte/agents/infinite/memory.py` and `vidbyte/agents/infinite/workspace.py`, both changed by #1169 (`write_note` returns `(created, relative)`, and `edit_file` returns `relative`);
  - `vidbyte/lib/enums/__init__.py` (#1055 added Codex enums).

  `git diff 7efceb55 2c84049c` touches nothing under `vidbyte/agents/infinite`, `tests/features/infinite_memory_agent`, or `contracts`. So #1084's squash equals the old base for everything this PR builds on.
- **Command.** `git switch -c feat/infinite-memory-events-on-main feat/infinite-memory-events`, then `git rebase --onto origin/main 7efceb5504b0d2ac64a3b5874ada635a47ac35cf`. The rebase printed `Successfully rebased and updated refs/heads/feat/infinite-memory-events-on-main` after `Rebasing (71/71)`. There was no conflict at any step, and the range holds no merge commits.
- **Proof that only this PR's commits moved.** `git log --oneline origin/main..HEAD | wc -l` printed 71 right after the replay. The 71 subjects match the pre-replay subjects in order (0 mismatches), and none of them is a #1084 commit.
- **Proof that the diff is preserved.** For each of the 58 changed files, the md5 of the `^[+-]` lines of `git diff origin/main HEAD -- <file>` equals that of `git diff 7efceb55 7692b9bc -- <file>`. The file sets are equal, and no file differs.
- **How the merged code reads.** In `memory.py`, #1169's `created, path = self.workspace.write_note(...)` and `path = self.workspace.edit_file(...)` run before this PR's `self.events.file_written(self, path, ...)`. Events therefore receive the relative path. `InfiniteWorkspace.relative` is idempotent on it, and it still normalizes `run_handoff`'s descriptions, root files, and any card journaled before #1169 (`agent.py:131,139`, `events.py:250,307`).
- The new branch was pushed (`git push -u origin feat/infinite-memory-events-on-main`, `* [new branch]`) before any fix, so that a usage stop could not lose the replay.

## Step 3: the semantic conflict and the granted change

**Reproduced.** On the replay, the focused pack gave `1 failed, 193 passed`:

```
>       assert finished_cards(workspace_root(tmp_path))[pair_key(PAIR)]["files"] == ["./notes/a.md", "notes/a.md"]
E       AssertionError: assert ['notes/a.md'] == ['./notes/a.md', 'notes/a.md']
tests\features\infinite_memory_agent\test_infinite_memory_events_pairs.py:517: AssertionError
```

The two assertions before it (`file_written` paths and `subagent_finished.files`) passed. Only the card clause conflicts with `main`.

**Spec first (`5f6d0595`).** Only the card-files wording changed:

| Clause | Before | After |
|---|---|---|
| INV-28 | `card.files` keeps each path as the model spelled it. | `card.files` lists each note once by the workspace-relative POSIX path that `main` records since #1169 (`08f67e7f`), which this PR does not change. |
| AC-34 (Then) | …, while the card's `files` keeps both spellings as before. | …, and the card's `files` is `["notes/a.md"]`, the one relative path that `main` records since #1169. |
| EC-16 (System behavior) | The card keeps the model's spelling (INV-28). | The card's `files` holds the same relative path, which `main` records since #1169 (INV-28). |
| D-23 (Decision) | Card text and `files_written` keep the model's spelling. | Since `main`'s #1169 (`08f67e7f`), `files_written` and the card's `files` hold the same relative path, so `relative` returns it unchanged and still normalizes cards journaled before #1169. |
| D-23 (Runner-up) | Return the relative path from `InfiniteWorkspace.write_note`. Rejected: `write_note` already returns the created flag, and the card text would change. | Return the relative path from `InfiniteWorkspace.write_note`. Rejected in r2 because the card's `files` would change; `main`'s #1169 has since made that change, and events still use `relative`, which also normalizes the handoff's descriptions and root files. |
| §17 | — | New row `r3 \| 2026-10-17 \| S5 repair 3 \| Rebased onto main (…); card file paths are relative after #1169. …` |

**Then the one assertion (`4aba9eac`).** In `tests/features/infinite_memory_agent/test_infinite_memory_events_pairs.py`, `test_two_spellings_of_one_note_are_one_relative_path_in_events_and_the_handoff`:

```diff
-    assert finished_cards(workspace_root(tmp_path))[pair_key(PAIR)]["files"] == ["./notes/a.md", "notes/a.md"]
+    assert finished_cards(workspace_root(tmp_path))[pair_key(PAIR)]["files"] == ["notes/a.md"]
```

The same test's docstring described that assertion, so its phrase was changed with it, from "a card that keeps both spellings" to "a card whose files list that one relative path (main's #1169)". No other line of any test changed. The assertion is still strict. On a copy of the head with #1169's two assignments reverted, it fails, while the event assertions in the same test still pass there. That shows the PR's own `relative` path handling is still pinned independently of #1169.

## Step 4: contract

- `git rev-parse HEAD:contracts/sdk-public-api.json` gives `91e9f11893e886f068f8e6dd67e6710bc9b83e7d` before and after. It equals the blob on `feat/infinite-memory-events`, so the CLI's vendored `91e9f11893e8` stays valid.
- `--check` passed right after the replay, so the generator was not run. Running it would also write nothing: `run` keeps `source.commit` whenever the derived data equals the committed data (`scripts/generate-sdk-public-api.py:65-67`).
- The pin `52249854` is the pre-replay "docs(infinite): document run events…" commit (now `05a216ac`). `git diff --stat 52249854 HEAD -- vidbyte/__init__.py pyproject.toml` is empty, so the pin still names inputs identical to the head's.
- `main`'s own contract pins `9eca4a33` ("Merge origin/main into feat/infinite-memory-agent"), which is not an ancestor of `main` (`merge-base --is-ancestor` exit 1). A pin off `main` is normal here after a squash. Hand-editing the pin is forbidden by the generator's header.

## The two remaining source-stage failures

Both are in `tests/features/harness_threads/test_harness_threads_surface.py`. Both compare with `git merge-base origin/main HEAD`, which skips in CI's shallow clone. The control environment was `git clone --shared` of the repository into `SCRATCH/s5r3/mainclone`, checked out at `6f5a7310`, with `refs/remotes/origin/main` = `6f5a7310`, so the merge base is `main` itself:

| Test | At `main` `6f5a7310` | At `main` plus one unrelated root export (`CodexTurnStatus`) | On this branch | Verdict |
|---|---|---|---|---|
| `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`:193`) | FAIL: `assert 167 == 120` (`1 failed, 8 passed in 2.86s`) | — | FAIL, same message | inherited: `main` now has 167 `FailureCode` members, and the test hardcodes 120 |
| `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` (`:258`) | PASS | FAIL: `assert ['CodexTurnSt...criptor', ...] == ['HARNESS_SCH...ettings', ...]` (`1 failed in 1.47s`) | FAIL: `At index 26 diff: 'InfiniteEvent' != 'InfiniteMemoryAgent'` / `Left contains 3 more items` | inherited by design: it requires the root `__all__` to equal `main`'s, so every PR that adds a root export fails it locally (field guide `local-ci-verification.md`). This PR's three exports are FR-17 and AC-24 |
| `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` | — | — | PASS | fixed by the new base (it failed on `7efceb55`) |

The control edit was reverted with `git checkout -- vidbyte/__init__.py` in the clone, which left `git status --porcelain` empty. Neither test was changed. Changing either one is outside the grant, and both belong to the harness-threads feature on `main`.

## Step 6: the commands the user runs

Run them from any checkout of the repository, in this order. The first command replaces the PR head. Its lease fails if the remote `feat/infinite-memory-events` moved from `7692b9bc`. The second command retargets the base and applies the body. It reads `pr-body.md` from the commit itself, which has LF line ends, so no `\r` reaches GitHub, and the result does not depend on which branch is checked out.

```bash
git fetch origin
NEW=$(git rev-parse origin/feat/infinite-memory-events-on-main)   # the tip; its SHA is in the STATUS message, and its parent is the pr-body commit bf021db0
git push --force-with-lease=feat/infinite-memory-events:7692b9bcf894c82c69a2af3c13ddee3934ab9a6b origin "$NEW":refs/heads/feat/infinite-memory-events
git show "$NEW":docs/spec/infinite-memory-events/pr-body.md | tail -n +2 > /tmp/body.md && gh pr edit 1159 --repo cerredz/Vidbyte-SDK --base main --body-file /tmp/body.md
```

The tip is the commit that adds this report, so this file cannot hold its own SHA. The STATUS message gives both commands with the literal SHA. The briefing's form, `tail -n +2 docs/spec/infinite-memory-events/pr-body.md`, also works, but only from a checkout of the new head. On Windows the working copy is CRLF (`core.autocrlf=true`), so pipe it through `tr -d '\r'` there.

After the retarget:

- Delete the helper branch with `git push origin --delete feat/infinite-memory-events-on-main`. Optionally delete `feat/infinite-memory-agent` too, since #1084 is merged; that is what stopped GitHub from retargeting.
- Re-pin the CLI sibling (cerredz/vidbyte-cli-internal#171) to the new head. Its vendored contract blob does not change.
- Dispatched checks run per SHA. The pushed head is the same commit that was checked here, so its check-runs carry over.

## Pre-replay → replayed SHA map

| # | Pre-replay | Replayed | Subject |
|---|---|---|---|
| 1 | `b5e87043` | `39d95785` | docs(spec): add infinite-memory-events request capture, recon, and pipeline state |
| 2 | `4b8d6a58` | `daad94b8` | docs(spec): add infinite-memory-events spec r1 |
| 3 | `3d091490` | `c25ebe59` | docs(spec): record infinite-memory-events S1 author report, request amendments, and pipeline state |
| 4 | `91576d73` | `e9d154d2` | docs(spec): add infinite-memory-events S1 review r1 |
| 5 | `a27ff27c` | `9d268aef` | docs(spec): revise infinite-memory-events spec r2 (re-baseline on #1113, bound event sizes, review r1) |
| 6 | `977141c4` | `a8f58190` | docs(spec): record infinite-memory-events spec r2 author addendum and pipeline state |
| 7 | `ea0ea4b8` | `4ad0c576` | docs(spec): add infinite-memory-events S1 review r2 and pipeline state |
| 8 | `c6774e94` | `75833c1d` | docs(spec): revise infinite-memory-events spec r3 (middleware refusals, review r2; approved) |
| 9 | `9a180d40` | `e44f2100` | docs(spec): approve infinite-memory-events spec r3 and record pipeline state |
| 10 | `28f45271` | `e2e4ce11` | test(infinite): add failing tests for infinite-memory-events [AC-1..AC-37] |
| 11 | `1944edab` | `4270fd44` | docs(spec): record test proof for infinite-memory-events |
| 12 | `eb89992e` | `0445b088` | docs(spec): record infinite-memory-events S2 test proof check and pipeline state |
| 13 | `a87e6da4` | `8486d046` | feat(infinite): add allow_zero, require_utc_datetime and require_callable to RecordFieldValidator [W-11; FR-23, AC-37, AC-21] |
| 14 | `f6a0288d` | `ce9ceff0` | feat(infinite): let OutputText.truncate take the caller's marker [W-11; FR-23, AC-37] |
| 15 | `143ce503` | `3529c43d` | feat(infinite): add the event kind, drop reason, file change and stop cause enums [W-1; FR-1, AC-24] |
| 16 | `19fdbbb0` | `4be7f6ef` | feat(infinite): export the four event enums from vidbyte.lib.enums [W-1; FR-17, AC-24] |
| 17 | `ae1648fe` | `166fd6ff` | feat(infinite): add the event caps, key rule, summary templates, metadata keys and handoff caps [W-1, W-9; FR-11, FR-21, FR-22, AC-14, AC-30] |
| 18 | `0b987caa` | `daa35abd` | feat(infinite): add InfiniteEvent, the 13 details records and the committed and dropped items [W-1; FR-2, FR-3, FR-10, FR-21, AC-13, AC-30, AC-37] |
| 19 | `fe104bad` | `d7eb356e` | feat(infinite): add the on_event setting, refused unless None or synchronous [W-2; FR-4, AC-21] |
| 20 | `e8c5ef27` | `b1152dad` | feat(infinite): add InfiniteWorkspace.relative for one path per note in events [W-8; FR-14, AC-34] |
| 21 | `75eb0018` | `d35c7502` | feat(infinite): add InfiniteEvents, the single writer of run events [W-3; FR-5, FR-7, FR-11, FR-12, FR-21, AC-32, AC-37] |
| 22 | `6936e3e6` | `3db48fb2` | feat(infinite): announce memory saves, stages, drops, note writes, and refusals [W-6; FR-6, FR-10, AC-2, AC-9, AC-12] |
| 23 | `475267b0` | `8ff6f8ba` | feat(infinite): announce refused batches, launches, replays, generator replies, and finished pairs [W-5; FR-6, FR-10, AC-2, AC-9, AC-23] |
| 24 | `42ad3510` | `ae105dc5` | feat(infinite): record the answer and root files at run end, load runs in any state [W-7; FR-13, AC-16, AC-17, AC-18, AC-20] |
| 25 | `5e5b845c` | `df01ea0e` | feat(infinite): announce the run's start, resumption, finish, and stop, and return its run id [W-4; FR-6, FR-8, FR-9, AC-2, AC-5, AC-6, AC-17, AC-20] |
| 26 | `7b1b42d3` | `1bbe00b2` | fix(infinite): name the launch loop's task card apart from the replayed card [W-5; FR-6] |
| 27 | `8cd15dab` | `a076598d` | feat(infinite): read one run's live entries and note descriptions for the handoff [W-8; FR-14, AC-15, AC-16] |
| 28 | `72f1f56d` | `1faccf58` | feat(infinite): add InfiniteHandoff, the nine-section handoff of a run [W-9; FR-14, FR-15, AC-16, AC-17, AC-33] |
| 29 | `dfdc9a81` | `c2297149` | feat(infinite): add run_handoff, a deterministic handoff saved beside the journal [W-9; FR-15, FR-16, FR-22, AC-16, AC-17, AC-18, AC-19, AC-33] |
| 30 | `80a24e22` | `c6a6e731` | fix(infinite): cut handoff lines without importing vidbyte.lib.outputs [W-9; FR-15, AC-33] |
| 31 | `41b79d79` | `22503ce5` | feat(infinite): export InfiniteEvent, InfiniteEventKind, and InfiniteHandoff [W-10; FR-17, AC-24] |
| 32 | `6ca50676` | `bf878631` | fix(infinite): wrap memory.py's grown import blocks one name per line [W-6; FR-6] |
| 33 | `52249854` | `05a216ac` | docs(infinite): document run events, the run id, and run_handoff [W-10, W-11; FR-18, FR-23] |
| 34 | `5a8791a7` | `c53203fb` | chore(infinite): regenerate the public API contract with the three new exports [W-10; FR-19, AC-24] |
| 35 | `581ab74b` | `c96f822c` | fix(infinite): clear the A007 and S024 regressions in events and the journal [W-3, W-7; FR-5, FR-13] |
| 36 | `6e94bb97` | `b1dbd021` | docs(spec): record draft PR for infinite-memory-events |
| 37 | `15bd473b` | `d12cbffd` | docs(spec): record implementation proof for infinite-memory-events |
| 38 | `24297ccf` | `643dad39` | docs(spec): add the infinite-memory-events S3 implementer report |
| 39 | `b0200f12` | `b26736ec` | docs(spec): record infinite-memory-events S3 check and pipeline state |
| 40 | `50a75ddb` | `00c4009d` | docs(spec): record infinite-memory-events S4 launch and pacing decision |
| 41 | `41bf4988` | `992f7634` | docs(spec): add infinite-memory-events S4 conformance review and pipeline state |
| 42 | `7cb2077a` | `24b983c6` | docs(spec): add infinite-memory-events S4 engineering review and pipeline state |
| 43 | `aaabddd7` | `a22c53b6` | docs(spec): add infinite-memory-events S4 conventions review and pipeline state |
| 44 | `0139fcce` | `6357577d` | docs(spec): add infinite-memory-events verified review, R-7 ruling and pipeline state |
| 45 | `ca5157a4` | `f5633a1e` | fix(infinite): return a looped note path as given from InfiniteWorkspace.relative [R-2] |
| 46 | `99c5908d` | `a5aef63b` | test(infinite): pin the handoff's lone-surrogate scrub with a run_handoff test [R-3] |
| 47 | `d8186147` | `e25f8db6` | test(infinite): measure NFR-2 across all 14 event methods with no sink [R-4] |
| 48 | `755e55cd` | `45528bc0` | test(infinite): pin D-18's all-parts and no-parts cost rule on a real pair [R-5] |
| 49 | `ae71adb1` | `80502c10` | test(infinite): pin the all-depth counts of run_resumed and run_finished [R-6] |
| 50 | `e7625553` | `2c33508c` | fix(infinite): point the lib headers' worst-case figures at the AC-30 tables [R-1] |
| 51 | `a16ba2f8` | `b883453f` | fix(infinite): cut handoff list lines with one canonical lib helper [R-7] |
| 52 | `3f68608d` | `4ad3955d` | fix(infinite): tag each memory event site with its @intent rule [m-7] |
| 53 | `cd07e8f0` | `dec4ba67` | fix(infinite): name the handoff's run_id metadata key as a constant [m-6] |
| 54 | `e7e6dd59` | `19936ae5` | fix(validation): refuse a partial around an object with an async __call__ [m-5] |
| 55 | `146effaa` | `277a1323` | docs(infinite): correct the whole-event worst case in the README to 31,093 bytes [m-8] |
| 56 | `1dbfdd84` | `cc670f55` | test(infinite): keep the symlink-loop test true on Python 3.13 [R-2] |
| 57 | `52e7571a` | `89cad933` | docs(spec): record S5 repair 1 statuses and the R-1, R-7 deviations for infinite-memory-events |
| 58 | `9cc288ca` | `17cf2357` | docs(spec): verify-log iteration 1 for infinite-memory-events |
| 59 | `b3632d49` | `2d7f00ca` | docs(spec): record infinite-memory-events S5 convergence in pipeline state |
| 60 | `5bf5bfc7` | `4781e5f9` | docs(spec): add infinite-memory-events S5 re-review 1 and pipeline state |
| 61 | `d913802b` | `3141ae5a` | fix(validation): refuse a partial subclass whose own __call__ is async [R-C1] |
| 62 | `3bd374c3` | `e9a8a411` | fix(infinite): state the measured envelope and whole-event bytes [R-C2] |
| 63 | `2073421b` | `87bf3ec5` | fix(text): name truncate_chars as the cut two callers share [R-C3] |
| 64 | `6c7e0bd1` | `a1325707` | docs(spec): record re-review 1 findings rr-1..rr-3 as fixed for infinite-memory-events |
| 65 | `4013eeb2` | `f1444180` | docs(spec): verify-log iteration 2 for infinite-memory-events |
| 66 | `adaff68b` | `5f68b870` | docs(spec): add S5 repair 2 report for infinite-memory-events |
| 67 | `900be217` | `0b4f6b26` | docs(spec): record S5 repair 2 remote checks for infinite-memory-events |
| 68 | `e7c1c950` | `3c36b01e` | docs(spec): mark infinite-memory-events verified after S5 iteration 2 |
| 69 | `cfd64939` | `dbbfc888` | docs(spec): finalize infinite-memory-events for PR |
| 70 | `af7c473c` | `f1a9ebdd` | docs(spec): add S6 report for infinite-memory-events |
| 71 | `7692b9bc` | `8355a6fa` | docs(spec): record S6 and the base retarget plan for infinite-memory-events |
| 72 | — | `5f6d0595` | docs(spec): state that the card's files are relative after main's #1169 |
| 73 | — | `4aba9eac` | fix(infinite): expect the card's one relative note path after main's #1169 |
| 74 | — | `bf021db0` | docs(spec): update PR body for the main-based branch |

The commit that adds this report and the verify-log entry follows `bf021db0`.

## Decisions and why

- **The test docstring changed with the assertion.** It stated the old card behavior in words ("a card that keeps both spellings"), so leaving it would have made the test describe something it no longer checks. It is part of the same test function and describes the same assertion. No other test text changed.
- **D-23's runner-up was reworded too, not only the decision.** Its rejection reason ("the card text would change") is card-files wording that `main` has since overturned. The rewording keeps the r2 history and states why `relative` still earns its place: it covers older cards, the handoff's descriptions, and root files.
- **The contract was not regenerated.** `--check` is the gate. The generator would write nothing for unchanged data, and a hand-edit of `source.commit` is forbidden. Regenerating would only have been needed if the data had changed. That would flip if `main` had added or removed a root export since `7efceb55`; it had not.
- **The PR body maps every PR-commit SHA to its replayed SHA** (`SCRATCH/s5r3/remap.py`, by subject order). After the force-push, the pre-replay SHAs are no longer in the PR's history. Pre-replay references that are deliberate (`7efceb55`, the contract pin `52249854`, and `7692b9bc` in the replay row) are kept. Old SHAs in the spec, the review, the reports, and earlier verify-log entries are history and were not rewritten.
- **No `fix` touched `vidbyte/`.** The only source-adjacent change is the granted test line. The scope ruling allowed a replay plus the conflict, with no new behavior.

## Niche facts for the next agent

- `main`'s #1169 makes `InfiniteAgentMemory.write_note` and `edit_file` rebind `path` to the workspace-relative path before this PR's `events.file_written` call. The card's `files`, `files_written`, and the tool reply to the model are all relative now.
- `generate-sdk-public-api.py` never moves `source.commit` for unchanged data. After a replay or a squash, the pin names an off-branch commit by design, and `main`'s own pin `9eca4a33` is off-`main`.
- On `main` at `6f5a7310`, `test_harness_threads_surface.py:193` fails by itself (`167 == 120`). Treat it as `main`'s bug, not the branch's.
- `git archive HEAD a b missing.py | tar -x` writes nothing when one path is missing. List only paths that exist.
- `pr-body.md` and `verify-log.md` are CRLF in this worktree. Append through a script that writes `\r\n`, or use the Edit tool.

## Open items

- The 2 local-only `harness_threads` failures, shown above to be inherited from `main`. Remote CI is green.
- Stale wording outside this iteration's write list (briefing section 7): `test-plan.md:51`, the AC-34 row ("the card loses one spelling", "The card's two spellings are asserted…"), and the struck-through NG-11 note at `spec.md:58` ("`write_note`'s return value and the card text still keep the model's spelling"). The spec frontmatter `base_commit: 7efceb55…` is left as history, and the new §17 row records the new base. An orchestrator ruling can extend the write list for these.
- The force-push and the retarget are the user's to run (above).
