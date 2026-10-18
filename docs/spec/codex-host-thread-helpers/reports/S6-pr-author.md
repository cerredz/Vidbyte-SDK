# S6 PR author: codex-host-thread-helpers on PR #1055

Stage: S6, the last stage of the spec pipeline, run on the existing draft PR https://github.com/cerredz/Vidbyte-SDK/pull/1055 (branch `feat/codex-host`, base `main`). Date: 2026-10-16.

## Outcome

- The PR body was rewritten to cover the whole PR: the original `CodexHost` (15 functions, 15 tools) plus this run's 12 methods (11 new tools, 26 in all). It is derived from `git diff origin/main...HEAD` first and the two specs second. Every AC row cites a test name that exists on the branch, every review finding cites its fixing commit, and every gate row quotes the gate's real final lines.
- Title, changed minimally: `feat(harnesses): add CodexHost with agent tools, thread helpers and skill functions` (it was the same without "thread helpers and skill functions"). No `[WIP]`.
- Body: 59,639 characters as GitHub stores it (cap 60,000), 3 mermaid blocks, and the last line is `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. The local file `docs/spec/codex-host-thread-helpers/pr-body.md` is LF and UTF-8, and after `--body-file` the stored body equals it exactly.
- Spec finalized: `status: pr-open`, `pr:` and `updated: 2026-10-16` already set. §5's first flowchart was redrawn to match the code and the body's third chart, and §17 has the row `r3 | 2026-10-16 | S6 PR | Finalized for review …`, which records the redraw.
- No source or test file was changed. The PR stays a draft. Main was not merged.

## What the code does (in my own words)

`CodexHost` is an async context manager that launches one installed `codex app-server` (the absolute path `shutil.which` finds, never openai-codex's bundled binary) and drives openai-codex 0.162.1's synchronous `CodexClient` from asyncio:

- Every client call runs on the host's own 32-worker pool, under a 300 s bound. A turn-starting call is shielded, so a caller that is cancelled or times out hands it over instead of abandoning it. If the start is still queued it is withdrawn; if it is already running, its thread stays busy, and the turn is adopted when it lands and stopped with exactly one interrupt.
- Spawning, continuing, forking, launching subagents and starting a review return a `CodexTurnHandle` as soon as Codex accepts the turn. One watcher thread per turn feeds notifications back to the loop, where `CodexLiveTurn` keeps the items and usage. A timeout or the output cap sends one interrupt, and `CodexTurnRegistry.finish` turns the result into a validated `CodexTurnSnapshot`.
- Every failure is mapped in one place, `CodexErrorMapper`, to a `CodexAgentError` with a `codex.*` code and a next step.
- Close runs a fixed order: tool handlers removed and their calls cancelled, then turns ended as `process_exited`, one bounded interrupt each, goal streams closed, then the client closed on a daemon thread.

This run adds two collaborators beside the host. Each new host method is "guard, then one delegation", so `host.py` stays at 893 lines.

- **`CodexThreadHelpers`** (`thread_helpers.py`):
  - **Listings.** Recent, since and search share one bounded walk over `thread/list`: newest first, every top-level source kind (`cli`, `vscode`, `exec`, `appServer`, `unknown`). The walk stops at the limit, an empty or repeated cursor, the first thread older than `since`, or 1,000 pages.
  - **Lineage** reads each parent once and ends quietly at an unreadable one.
  - **The transcript** is a raw `thread/turns/list` with full items, oldest first.
  - **Compact and delete** both check the host's own busy state, reserve the thread, read it, refuse an `active` one, and release in `finally`. Compact checks the goal of a `notLoaded` thread before it resumes it, and refuses an unfinished goal with `codex.goal_unfinished`. Delete never resumes.
  - **The goal read** is `thread/read` plus a raw `thread/goal/get`, never a resume.
- **`CodexSkillFunctions`** (`skill_functions.py`, reached through the `CodexSkillHost` Protocol):
  - **The goal run** uses spawn's goal path, then reads the goal back.
  - **The skill and docs runs** list skills for the folder and take the first enabled exact-name match. They send a text item, then the skill item, and poll the turn's recorded input up to 10 times under a 10 s deadline.
  - **A failed run.** A run that did not take gets one interrupt and `codex.command_not_run`. A read-back that itself fails gets one interrupt and keeps its own error, every field included, plus one sentence.
- **Tools.** Eleven new tools (7 READ, 4 WRITE) join `CodexHostTools`. `delete_codex_thread` has no tool. The four run tools each hold one cap slot until their call ends.

## Deviations found (code vs spec)

CodexHost (spec r6), all already in that spec's §17 or review record:

1. S3 deviation 1 (reshaped checks) withdrawn by R-8 `f2e9db7e`.
2. A process death also closes goal streams (`vidbyte/harnesses/native/codex/host.py:879-890`).
3. The single stop lives on `CodexLiveTurn.stop` (`vidbyte/harnesses/native/codex/turns.py:166`), not the host's late-acceptance handler.
4. A handed-over start keeps its thread busy (`vidbyte/harnesses/native/codex/connection.py:162`, `:262-280`).
5. Interrupt also skips while an earlier stop is pending (`vidbyte/harnesses/native/codex/host.py:426`).
6. A cyclic mapping `output_schema` is refused (`736d4a58`).
7. The six `CODEX_*_NOTIFICATION` constants (`vidbyte/lib/constants/codex.py:442-447`) are read by no source file; the watcher matches openai-codex's typed models (`turns.py:102-107`).
8. §5 was redrawn at that spec's S6.

Thread helpers (spec r3):

1. **D-9:** an empty since window returns `()`, where request §C lists it among the error cases.
2. **D-14:** an idle loaded thread may be deleted, and only a busy one is refused, where request §C lists "delete of a loaded thread" among the error cases.
3. The listing `limit` check goes through `RecordFieldValidator.require_int` (§17 deviation 1).
4. `CODEX_USER_MESSAGE_ITEM_TYPE` is outside §9.3's constant list (R-2, §17 deviation 8).
5. Both rebuilt errors keep every field (R-17, R-18; spec `04aa8cbe`).
6. The pinned line `vidbyte/tools/toolsets/__init__.py:11` is false (27 functions, 26 tools), knowingly left by NG-14 and Q-18.
7. §5's flowchart had drifted. It showed the busy check after the existence read and had no path for a failed read-back. It was redrawn at this stage (§17 S6 row).
8. Spec §4 gives the snippet's output as from a live, signed-in `codex`. The body shows the run at the fake seam and says the live run is manual QA.

## Snippet output

Both §4 snippets were run at the fake app-server seam (`tests/features/codex_host/codex_host_fakes.py` behind a subclass of the real `CodexClient`), on HEAD `5218b423`, Python 3.11, win32, openai-codex 0.162.1. The runner was a scratch `HostTestCase` subclass, kept outside the repo. No live `codex` was touched.

Snippet 1 (codex-host §4):

```text
True
completed The readme describes the SDK.
26 check_codex_ready
methods: initialize account/read windowsSandbox/readiness account/read account/rateLimits/read windowsSandbox/readiness thread/start turn/start
```

Snippet 2 (thread-helpers §4):

```text
codex thr-2 Release notes 1760000040
codex thr-3 None 1760000030
codex thr-4 None 1760000020
active 200000
completed Use the response.output_text.delta event.
1 completed 2
26 False
```

The request log: one `thread/list` with `sourceKinds ['cli','vscode','exec','appServer','unknown']`, `sortKey updated_at`, `sortDirection desc` and `limit 3`. Then the goal path, with `thread/goal/set` sending `status active` and then `tokenBudget 200000`, and the read-back `thread/read` and `thread/goal/get`. Then `skills/list {}`, `turn/start` with a text item and the `openai-docs` skill item, one read-back `thread/turns/list` with `limit 1`, and the transcript `thread/turns/list` without a limit. Then `thread/read` and `thread/delete`. At close came `thread/goal/set {status: paused}` and one `turn/interrupt` for the still-active goal run.

## Gates (local, at `5218b423`; its code equals the pushed head)

| Gate | Final lines |
|---|---|
| Area tests (`tests/features/codex_host tests/features/harness_threads tests/test_codex_output_contracts.py`) | `1 failed, 686 passed, 2 skipped in 59.01s` (the inherited test only) |
| Feature pack | `200 passed in 13.24s` |
| Pack with openai_codex blocked | `57 passed, 143 skipped in 2.47s` |
| `lint/run.py` | `SDK-LINT: PASS`; IMPROVED A002 703→563, C012 24→23, S001 59→56, S010 5→0, S025 263→261, S061 6→5, S063 4→3 |
| `generate-sdk-public-api.py --check` | `contracts/sdk-public-api.json is current at d08e89ef75ff4a6ee07465ee5097363e7d0d26c4 (vidbyte-sdk 0.3.0, 640 exports).` |
| `run_ci.py --stage source` | `1 failed, 6236 passed, 26 skipped in 116.26s (0:01:56)` (the inherited test only) |
| `run_ci.py --stage package` | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| Semgrep | `1/1: ✓ All tests passed` / `Ran 1 rule on 986 files: 0 findings.` |
| mypy (5 files) | `Success: no issues found in 5 source files` |

Body checks I ran before publishing:

- **Cited tests.** A script parsed every AC row and the mutation paragraph and resolved each `file.py::test_name` with `ast`: 148 references were checked, 0 missing. `CodexRunReRaiseTests` is in `test_codex_host_goal_skills.py`, and `CodexHostLaunchRebuildFieldTests` is in `test_codex_host_review_gaps.py`.
- **Counts.** Per-file test counts add up to 200. `test_codex_host_review_gaps.py` had 15 tests at `c181be65` and has 16 now.
- **Line counts.** `host.py` 893, `codex_host_fakes.py` 894 and `codex_host_helper_fakes.py` 237 lines.
- **Line references.** Every path:line cited in the body was re-read on HEAD.
- **Mermaid.** All 3 body charts and both §5 spec charts parse with `mermaid.parse` (mermaid 11.4.1 under jsdom, installed in a scratch folder). A deliberately broken chart fails the same checker.
- **FailureCode.** It has 148 members on origin/main `6983afd2` and 167 on HEAD.
- **Cleanliness.** A secret scan of the added lines finds nothing, and 0 `.pyc` files are tracked.

## GitHub outputs

`gh pr edit 1055 --repo cerredz/Vidbyte-SDK --title "$TITLE" --body-file <tail -n +2 of pr-body.md>` printed `https://github.com/cerredz/Vidbyte-SDK/pull/1055`.

`gh pr view 1055 --repo cerredz/Vidbyte-SDK --json title,isDraft,baseRefName,headRefName,headRefOid,mergeable,mergeStateStatus,url,body`, taken right after the edit and before this stage's push:

```text
{"baseRefName": "main", "headRefName": "feat/codex-host", "headRefOid": "40eeebc453d8d1b7438b037a1f3f489e84a93e6a", "isDraft": true, "mergeStateStatus": "BEHIND", "mergeable": "MERGEABLE", "title": "feat(harnesses): add CodexHost with agent tools, thread helpers and skill functions", "url": "https://github.com/cerredz/Vidbyte-SDK/pull/1055"}
body chars 59639 equal_to_local True mermaid 3
last line: 🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

`gh pr checks 1055 --repo cerredz/Vidbyte-SDK` printed `no checks reported on the 'feat/codex-host' branch` (exit 1). CI is dispatch-only, so dispatched runs never attach to the PR. Results are read per commit from `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`.

- **Remote checks on `40eeebc4`**, whose code equals this head: `Package`, `Static policy`, `Source / Python 3.11` and `Source / Python 3.12`, all `completed success` (CI run 38942773026, static-policy run 38942776154).
- **Remote checks on this stage's final SHA.** The final SHA is the commit that carries this report, so the report cannot hold its own results. After the push I dispatch `ci.yml` and `static-policy.yml` on it. The final check-runs go in the stage's STATUS block and in the live PR body's "Remote checks" row.
- **Committed body vs live body.** The committed `pr-body.md` cites the `40eeebc4` runs and says the docs-only head is dispatched again. The live body's "Remote checks" row is edited after the runs to cite the final SHA's run IDs. That row is the only difference between them.
- **Branch state.** GitHub reports `mergeable: MERGEABLE` and `mergeStateStatus: BEHIND`. Main gained four commits after the last merge `f7f32b19`: `d5c1532d` #1162, `7ab22063` #1163, `1a73a19e` #1161 and `6983afd2` #1164. None touches a PR file (0 shared paths), and `git merge-tree --write-tree HEAD origin/main` is clean. The briefing named only `d5c1532d`; main moved during the stage. `BLOCKED` in other reads is branch protection (the owner merges with `--admin`).

## Candidate field-guide lessons (report only; not written to the field guide)

Each entry: trigger · preferred action · project-specific reason · quick check · link.

1. **Wire values in a feature module (R-2, Major).**
   - Trigger: a Codex wire string, such as an item type or method name, is added inside `vidbyte/harnesses/native/codex/`.
   - Action: define it in `vidbyte/lib/constants/codex.py` beside its precedent (`CODEX_COMPACTION_ITEM_TYPE`) and add it to `__all__`.
   - Reason: request §C and spec §12.4 say "never in feature files", the owner asked the same in PR #384, and the error mapping keys on these names.
   - Quick check: `git grep -n '"userMessage"' -- vidbyte` returns only the constants module.
   - Link: #1055 `54f599de`.
2. **Tool schema bounds parity (R-3, Major).**
   - Trigger: a new `integer` or `number` property in a Codex tool `input_schema`.
   - Action: give it the `minimum` and `maximum` the host validates, and match the sibling concept (`goal_token_budget` has a `minimum`, so `token_budget` gets one).
   - Reason: vidbyte runs no JSON-schema validation of tool arguments (`git grep jsonschema -- vidbyte` is empty), so the bound is the model's only signal, and every older Codex schema has one.
   - Quick check: `git grep -n '"type": "integer"\|"type": "number"' -- vidbyte/tools/builtins/codex/`, and every hit has bounds beside it.
   - Link: #1055 `dd3fe2c2`.
3. **TESTS header lines on modified files (R-7, R-16).**
   - Trigger: an existing module (an enum export, constants, failure codes) is modified, and new tests pin the change.
   - Action: append the new test files to that module's A001 `TESTS` line in the same commit.
   - Reason: spec §12.5 and NFR-8 require it, and no test pins it, so two review rounds caught 5 files.
   - Quick check: for each `git diff --name-only origin/main...HEAD -- vidbyte` file, its `TESTS` line names a test that pins the change.
   - Link: #1055 `4fbc88b6`, `ddc432fe`.
4. **A pinned docstring line that becomes false (R-6).**
   - Trigger: a change falsifies a byte-pinned line, here `vidbyte/tools/toolsets/__init__.py:11`, pinned by `test_codex_host_packaging.py`.
   - Action: leave the pinned line, correct every unpinned copy of the claim (class docstring, header, narration), and record the drift as a non-goal plus an open question.
   - Reason: the packaging tests pin those bytes, and editing them breaks an AC of the earlier spec.
   - Quick check: `git grep -n "One tool per CodexHost function"`.
   - Link: #1055 `c3a3ef98`.
5. **The placement recipe follows the structure (R-9).**
   - Trigger: collaborators are introduced that change where the next method goes.
   - Action: update the file header's COMMON MODIFICATION PATTERNS and the `__init__` narration in the same change.
   - Reason: A001 headers are how agents decide placement, and `host.py` sits near its 900-line cap, so a stale recipe sends new code into the full file.
   - Quick check: `sed -n 6p vidbyte/harnesses/native/codex/host.py` names `CodexThreadHelpers` and `CodexSkillFunctions`.
   - Link: #1055 `549c7475`.
6. **Error rebuilds after a merge widens the constructor (R-17, R-18).**
   - Trigger: a merge from main adds a keyword to an error class (here `thread_id` on `CodexAgentError`) while the branch rebuilds that error to append text.
   - Action: after the merge, find every rebuild and carry every field: code, operation, next step, `thread_id`, and `error_type` from `safe_runtime_details`, since `CodexAgentError` has no `error_type` attribute. Better still, use one canonical copy-with-new-message helper.
   - Reason: the dropped fields fail no existing test until some path sets them.
   - Quick check: `git grep -n "CodexAgentError(" -- vidbyte/harnesses/native/codex`, compared with the signature in `vidbyte/lib/errors/base.py`.
   - Link: #1055 `5e30a226`, `804bbc91`.
7. **Every reservation needs release tests (engineering R-1, R-4; codex-host R-14).**
   - Trigger: code reserves a tool cap slot or a thread reservation.
   - Action: test that success, failure and cancellation each release it.
   - Reason: mutants V36, V05 and V05b, which release only on success or never reserve, survived an 864-test suite until those tests were added.
   - Quick check: `git grep -n "reserve(" -- vidbyte`, and each hit has a `*releases*` test.
   - Link: #1055 `6c5eca2a`, `6a434afd`.

## Anything that looked wrong (no fix made; source and tests are out of scope here)

- **R-17 and R-18 are latent.** `vidbyte/harnesses/native/codex/errors.py:65`: `CodexErrorMapper.error` never passes `thread_id` or `error_type` to `CodexAgentError` (it folds the thread into the message text), so no host error carries those fields today. The fixes preserve fields nothing sets.
- **The `fifteen` test name is stale.** `tests/features/codex_host/test_codex_host_tools.py:149`: `test_toolset_holds_the_fifteen_tools_with_their_spec_schemas` asserts 26 tools at `:153`. The name kept its count because the AC tables cite it, and it now misleads.
- **A claim of coverage that no test backs (R-32, open).** `tests/features/codex_host/FEATURE.md:128` and the class docstring at `tests/features/codex_host/test_codex_host_review_gaps.py:424` say a user interrupt "while one is in flight" is covered. Only Vidbyte's own timeout stop in flight is tested (`:454`).
- **Dead constants.** `vidbyte/lib/constants/codex.py:442-447`: six `CODEX_*_NOTIFICATION` constants are read by no source file, only pinned by `tests/features/codex_host/test_codex_host_records.py:465`.
- **The deadline message overstates the wait (R-12).** `vidbyte/harnesses/native/codex/skill_functions.py:55`: `INPUT_NOT_RECORDED_MESSAGE` prints the 10 s deadline, but 10 reads 0.5 s apart end after about 4.5 s. The text is spec-mandated.
- **"Interrupted" may be untrue (R-11).** `vidbyte/harnesses/native/codex/skill_functions.py:54,57`: `GOAL_UNCHECKED_MESSAGE` and `SKILL_UNCHECKED_MESSAGE` say "was interrupted" even when the interrupt failed and was ignored.
- **A stale header (R-10).** `vidbyte/tools/builtins/codex/delegation.py:4` still says "CodexHostTools lists these last"; the 11 new tools come after it.
- **The inherited red test.** `tests/features/harness_threads/test_harness_threads_surface.py:176` fails with `assert 148 == 120` on plain main as well. CI passes it only because its shallow clone has no merge base.
