# S6 PR author: harness-thread-helpers-skills

- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1147
- **Head:** `5c93e6c9` (`docs(spec): finalize harness-thread-helpers-skills for PR`). The code is identical to `ade57291`: `git diff ade57291 5c93e6c9 -- . ':!docs'` is 0 lines.
- **State:** draft, base `main`, title without `[WIP]`. The 4 dispatched check-runs on `5c93e6c9` are all success.

## What the code does, in my own words

I read the diff before I opened the spec.

PR #1036 shipped nine native functions that run, continue and fork Grok Build, opencode and Muse Code threads. This PR adds 47 async functions to `vidbyte.harnesses.native`:

- **22 keyless thread helpers.**
  - Grok gets 8: list, recent, since, get, read, lineage, search and delete.
  - opencode gets the same 8.
  - Muse gets 6: everything except search and delete.
- **`init_muse_workspace`**, which runs `muse init [--dry-run]`.
- **24 paid command and skill functions:**
  - Grok has 14: `run_grok_command` and 13 named wrappers.
  - opencode has 4: command, review, init and plan.
  - Muse has 6: skill, goal, plan, import, scaffold and browser_app.

**Validation and error handling.** Every public function checks all of its arguments in one record (`NativeHelperRequest`, or `NativeThreadRequest` plus `GrokCommandArguments`). That check happens inside one guarded `_call` per class, before any file is read or any child starts. `_call` passes `CancelledError` and `NativeThreadError` through. It maps `ConfigurationError` to `configuration.invalid_argument`, and anything else to `runtime.error`.

**How the helpers read each vendor's store:**
- **Grok:** the helpers read `summary.json` files themselves through `GrokStore`.
  - SDK scope is the private home `~/.vidbyte/grok-homes/<sha16>`. USER scope is `~/.grok`, filtered to the workspace by the decoded group name or `.cwd`.
  - A scan is strict. A one-id read touches only its own file.
  - If session folders exist but none has a `summary.json`, and the newest is older than 60 s, the call raises `protocol_mismatch`.
  - read and delete are keyless `grok export` and `grok sessions delete`. The delete then checks on disk that the session is gone.
- **opencode:** the helpers run `opencode session list --format=json --max-count=10000`; a result of exactly 10000 rows is refused. get and lineage run one `opencode db` query by a pattern-checked id. read and delete use `export` and `session delete`.
- **Muse:** each method is one keyless `muse serve` batch, run in a private `XDG_CONFIG_HOME` that is removed in `finally`. read exports into an empty temp folder.

**Shared parts of every helper:**
- No helper or evidence child inherits `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY`, `OPENCODE_CONFIG_CONTENT` or `META_API_KEY`.
- Each child gets a 30 s control timeout and a 64 MiB cap.
- `NativeErrorFactory.child_problem` maps every child outcome to its problem, in one place.
- `NativeThreadListing` gives every list the same order: dedupe, window, newest first, ties by id descending, then limit. Search is a literal casefold match. Lineage stops at a cycle or at depth 64.

**What each paid function counts as proof that its command ran:**
- **Grok:**
  - It runs `grok --output-format=streaming-json --session-id=<minted uuid4> --single=<§9.2 line>`, with `GROK_WORKFLOWS=0` for `/goal`.
  - The proof is a streaming `tool_call` whose `rawInput`, after backslash folding, holds the persona or `CORE.md` fragment; or the tool `update_goal`, `image_gen` / `image_edit` or `image_to_video`.
  - For plan and explore, the proof is `agent_name` in the new thread's `summary.json`.
  - For `/code-review`, the proof is the Core Prompt fragment in a keyless `grok export` of the run.
- **opencode:** the functions reuse #1036's run with `--command=<name>`, with the arguments on stdin. opencode's `Command not found: "<name>"` maps to `command_not_run`.
- **Muse:**
  - `muse exec` does not expand slash commands, so the skill or goal is asked for in a prompt template. The run is #1036's exec run.
  - A keyless `session/read` with items follows. The proof is a `toolCall` item, from `history.items` or `history.snapshot.state.items`: either a `read_skill` whose parsed `args.id` equals the skill, or any `create_goal`.
  - Mode `none` fails closed. Message text never counts.

Without that proof, each paid function raises `<harness>.command_not_run`. `remember_thread` makes every error raised after the paid run carry the new thread id.

**Refactors:** `GrokHome` moved to `grok/store.py`, and `MuseChildren` moved to `muse/children.py`.

**Docs:** the README native bullet now covers the helpers. #1036's EC-44 sentence is replaced by the EC-63 limitation (Grok still loads `~/.claude` hooks).

## What I produced

- **`docs/spec/harness-thread-helpers-skills/pr-body.md`,** committed at `5c93e6c9`.
  - The title is on line 1. The sections follow the required order, and the footer is the last line.
  - The live PR body is that file plus the final check-runs table for `5c93e6c9`, which I could add only after the dispatched runs finished. The committed copy says the table is added to the PR description; the live body says the table exists only there. Live body: 57,551 chars.
- **`spec.md`:** `status: pr-open`, and the §17 row `| r5 | 2026-10-16 | S6 PR | finalized for review |`. `pr:` and `updated: 2026-10-16` were already right. §5 has not drifted (its flow matches the code), so I left it alone.
- **This report.** It is not committed, because committing it would move the head off the SHA whose checks are green.

### Body length

The body is 57.6k characters, against the 30k aim and well under the 65,536 limit.
- The binding `probe.py` alone is 25.5k, inside a collapsed `<details>`.
- The narrative is about 31k.
- To get there I cut the AC table from 10.2k to 5.7k (one proving test per AC, which points to §6.2 for the twin tests) and shortened the Manual QA table.

## Snippet output (AC-1, the §4 snippet unchanged)

I ran it with `PYTHONPATH="<worktree>;<scratch>/s6plug" $PY -m pytest -p no:cacheprovider -p s6_snippet_tee -q tests/features/harness_threads/test_harness_threads_acceptance_helpers.py::test_the_helpers_example_runs_as_written_against_stand_ins_on_path`. Result: `1 passed in 1.11s`. The subprocess returned code 0, and the scratch plugin captured its stdout:

```text
0cea13c1-6be5-48f3-860b-723d3ee9e480 grok answer to: /goal Make the auth test suite pass without changing public endpoints.
grok 2026-10-16T18:06:19.945884+00:00 0cea13c1-6be5-48f3-860b-723d3ee9e480 /goal Make the auth test suite pass without changing public None
opencode 2026-10-16T16:06:19+00:00 ses_recentfix Fix flaky login test None
opencode 2026-10-15T12:06:19+00:00 ses_oldercache Refactor the cache None
['0cea13c1-6be5-48f3-860b-723d3ee9e480']
```

The test's embedded snippet is spec §4 verbatim, so the snippet runs as written, with no deviation.

## Gates I ran myself

- **Pack at `f85d08af`, with `DEEPSEEK_API_KEY` set:** `1025 passed, 3 skipped in 90.41s (0:01:30)`.
- **`lint/run.py` with the body and spec staged:** exit 0, `SDK-LINT: PASS` (A001 642/642, A002 605/703). `git diff --cached origin/main -- lint/baseline.json` is 0 lines.
- **Dispatched CI on `5c93e6c9`:**
  - run 38947953850: Source 3.11 `6580 passed, 69 skipped in 151.50s`, Source 3.12 `6580 passed, 69 skipped, 19 warnings in 120.51s`, Package `Installed vidbyte-sdk 0.3.0 passed smoke checks.`
  - Static policy run 38947957489: `1/1: ✓ All tests passed`, then `Ran 1 rule on 975 files: 0 findings.`

## Manual QA probe: how I verified it

These are independent checks, made with no real key and no real vendor CLI:

1. **Signatures.** `inspect.signature(fn).bind(...)` succeeded for all 20 SDK functions the probe imports (all of them coroutines) and for both config records. The internals exist with these signatures:
   - `MuseWire.batch_frames(method, params)`
   - `MuseSessionWire.read_items_params(thread_id)`
   - `MusePathTranslator.to_wsl(PureWindowsPath)`

   Every `C.*` constant it reads exists.
2. **End-to-end dry run against the pack's stand-ins.** The harness is the scratch `probe_dryrun.py`. It loads `conftest.Sandbox` by path, sets fake keys that override the machine's real `DEEPSEEK_API_KEY`, and points `PATH` at only the sandbox bin plus git and Python. `HOME`, `USERPROFILE` and `TMP` point into the sandbox.
   - **Default run:** exit 0, 24 verdicts. 23 `HOLDS`; A-28 is `NOT EXERCISED` because the stand-in served inline history.
   - **Run through the `wsl.exe` stand-in, serving `anchoredSnapshot`:** all 5 Muse verdicts `HOLDS`, A-28 included.
   - **Both runs:** no fake key value in stdout, stderr or any file under the sandbox.
   - `run_muse_goal` raised `muse.command_not_run` against the default stand-in. This is correct: the stand-in emits `create_goal` only through `exec_items` (`fake_harness_helpers.py:418-423`).
3. **Live body.** The `probe.py` block in the live PR body is byte-identical to the dry-run-tested file.

These problems surfaced during verification, and I fixed them in the probe before publishing:
- The backslash fold on dict `rawInput` now uses `json.dumps` with the SDK regex.
- A-4 now compares with `normcase`.
- Vacuous checks (A-12, A-16/A-21) now report `NOT EXERCISED` instead of passing.
- opencode flags are joined (`--format=json`), as the SDK passes them.
- `find_grok` skips a `.cmd`/`.bat`, as `NativeLauncher.resolve` does.
- `wsl.exe` is found on `PATH`, as `MuseLauncher.resolve` finds it; `CreateProcess` would have preferred System32.
- A-18 handles `text_truncated`.
- The `muse exec --help` call now runs keyless.
- I added A-8 (stream members) and A-14 (delete the session made by the probe's own refused opencode command, then expect `thread_not_found`), so every assumption in §12.5 (f) is covered.

## Deviations (as written in the body)

1. **Plumbing outside the letter of §8.5/§9/§12.3** (S3 items 1, 2, 4, 5, 6 and 10). None changes a public signature.
2. **Every helper or evidence child removes all four key variables.** §9.2 still says "both key variables" / `META_API_KEY` (S3 item 3).
3. **Muse lists cut in the SDK** (S3 item 7, Muse half). The Grok half, "search matches before the dedupe", was reversed by R-3.
4. **Extra constants**, and the implementer's wording of `MUSE_GOAL_PROMPT_TEMPLATE` (S3 item 8).
5. **`NativeEnvironmentVariable.PWD = auto()`,** and `end.sessionId` is compared case-insensitively (S3 item 9).
6. **D-33 moved from r3/r4** (export transcript) **to r5** (`history.snapshot.state.items`) after the orchestrator's real Muse 1.0.1 probe. This is a spec revision. A-28 in the probe checks it.
7. **Environment only.** Semgrep runs from an isolated venv. S3 item 11 was resolved by r4/R-7. S3 item 13 no longer applies after R-4.

## Final `gh pr view` / `gh pr checks`

```text
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1147 --json title,isDraft,baseRefName,url
{"baseRefName":"main","isDraft":true,"title":"feat(harnesses): thread helpers and verified built-in skill functions for Grok, opencode and Muse","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1147"}

$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1147
no checks reported on the 'feat/harness-thread-helpers-skills' branch      (exit 1)

$ gh api repos/cerredz/Vidbyte-SDK/commits/5c93e6c931814d2646f7cf60eb5229d46482e368/check-runs --jq '.check_runs[] | [.name,.status,.conclusion] | @tsv'
Package	completed	success
Static policy	completed	success
Source / Python 3.11	completed	success
Source / Python 3.12	completed	success
```

`gh pr checks` reports nothing because CI is dispatch-only. `workflow_dispatch` runs do not join the PR's `statusCheckRollup`: `gh pr view --json statusCheckRollup` gives 0 entries. The check-runs API on the head SHA shows all 4 green, and the github-actions check suites on `5c93e6c9` are `completed success`.

## Candidate field-guide lessons

Each lesson reads: trigger · preferred action · project-specific reason · quick check · link.

1. **Adding or moving a `#` comment in `vidbyte/**/*.py`** · wrap it at 72 columns · this is the owner's `comment-format.md` rule. Lint does not enforce it, and S4 raised R-1 to Blocker on #1036 precedent · `awk 'length($0) > 72 && $0 ~ /^[ \t]*#/'` on each changed file, `comm -23` against the same awk over `origin/main` · PR #1147 R-1 (`3a1dc4b1`).
2. **A new vendor child (helper, export, init, evidence read)** · map its outcome through `NativeErrorFactory.child_problem` only · S4 found the timeout, cap, not-found and exit mapping copied five more times (AGENTS.md principle 5) · `grep -n "TIMED_OUT\|OUTPUT_TOO_LARGE" vidbyte/harnesses/native/*/wire.py` shows no per-wire mapping · R-6 (`53bca187`).
3. **A test asserting that a child's environment has no key** · clear every `CREDENTIAL_NAMES` variable in the `sandbox` fixture · this machine exports `DEEPSEEK_API_KEY`, so the pack was red in the user's own shell · run the pack with `DEEPSEEK_API_KEY` set · R-4 (`228b2a9e`).
4. **A "did the command or skill run" check** · require a structural tool-call item with an exact parsed member, never a substring of any text · the SDK's own prompt templates contain `create_goal` and skill ids, so text evidence always passes. A prefix id (`bundled:grill` against `bundled:grill-and-record`) also passed · add a negative test where only the prompt names the tool or a longer id · R-2 (`f8c00aa7`), R-23 (`3fbe9568`).
5. **Any step that runs after a paid vendor run returns** · call `errors.remember_thread(new_id)` right after the stream is read or exec returns · INV-5 and AC-35: the caller must be able to find, and pay attention to, the thread they paid for · inject a failure after the run and assert on `error.thread_id` · R-5 (`cdbbd72b`).
6. **Moving #1036 code into a new module, or changing a design** · cite #1036's IDs as "#1036 INV-9", and re-read the module header's WHAT NOT TO DO list against the new design · the two specs share one ID space, and A001 requires accurate headers. R-11 and R-24 both came from stale headers · `grep -n "spec INV-\|export" <moved module>` · R-11 (`8953669d`), R-24 (`ade57291`).
7. **Reporting checks on a vidbyte-sdk PR** · read `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`, not `gh pr checks` · CI is dispatch-only, so dispatched runs never join the PR rollup, and `gh pr checks` says "no checks reported" even when everything is green · `gh pr view --json statusCheckRollup` returns `[]` · PR #1147 S6.
8. **A manual QA probe that must observe the SDK's own argv and env** · pass the probe script itself as the harness's explicit `grok_command` (a `--tee` mode that `Popen`s the real binary and redacts the key) · the SDK accepts any non-batch argv tuple in `GrokThreadConfig.grok_command`, so the probe sees exactly what the SDK sends without patching it · dry-run the probe against `conftest.Sandbox` stand-ins with fake keys and grep every file for the key values · PR #1147 Manual QA.

## Things that looked wrong (not fixed: no source changes at S6)

- `vidbyte/harnesses/native/grok/store.py:104-106`: three blank lines between `GrokHome` and `GrokStore` (PEP 8 E303). Cosmetic; lint passes.
- `vidbyte/harnesses/README.md:179`: the "Thread helpers" sub-bullet says "22 keyless functions" but lists 23 names, because it includes `init_muse_workspace`. Spec TL;DR `spec.md:17` counts it among "25 skill functions" instead (22 + 25 = 47). The counting convention is inconsistent; the functions are not.
- `origin/main` is 3 commits past the merge base `8da41971` (#1160 `f7f32b19`, #1162 `d5c1532d`, #1163 `7ab22063`). None touches a file this PR changes. I did not merge.
