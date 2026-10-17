# S6 PR author: claude-thread-functions

Branch `feat/claude-host`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1044, base `main` (origin/main 845a4d9b throughout, so no catch-up merge was needed). The finalize commit is 3244af75 ("docs(spec): finalize claude-thread-functions for PR"). The code was last changed at ee3b4e88. `git diff --stat ee3b4e88..3244af75 -- . ':!docs'` is empty.

## What the code does, in my words

The PR adds three coroutines, `run_claude_thread`, `continue_claude_thread` and `fork_claude_thread`. They are exported from `vidbyte.harnesses.native` (and `vidbyte.harnesses.native.claude`), and they take the same keyword arguments as #1036's nine Grok, opencode and Muse functions. Each one is a static method of `ClaudeThreads` (`vidbyte/harnesses/native/claude/threads.py`), bound by name in `claude/__init__.py`. All three go through one guarded `_call`. It passes `CancelledError` and `NativeThreadError` through unchanged. A `ConfigurationError` from the request record or the config check becomes `configuration.invalid_argument`, naming the argument. Anything else becomes `runtime.error`, named only by its class.

One call does seven things, all in `ClaudeThreadRun.execute`:
1. It validates the arguments into `NativeThreadRequest` before anything is looked up or started. The prompt must match `CLAUDE_PROMPT_PATTERN` (no NUL, no lone surrogate). The thread id must be a lowercase UUID. The config must be a `ClaudeThreadConfig`.
2. It finds `claude`. It uses `claude_command` if one is given, otherwise PATH (never the current folder), otherwise `~/.local/bin/claude[.exe]`. It refuses `.cmd` and `.bat` launchers.
3. It prepares the private config folder `~/.vidbyte/claude-configs/<first 16 hex of sha256(normcase(resolved workspace))>`. Its `skills/` folder is rewritten to hold exactly the caller's skills. This step runs in `asyncio.to_thread` through the new shared helper `NativePrivateFolders` (`hostkit/folders.py`). Grok's `_prepare_home` now calls the same helper.
4. It registers the key with the scrubber.
5. It starts the CLI once through `CliRunner`. The arguments are `--print --output-format json --setting-sources user --permission-mode M`, then `[--model] [--effort]`, then, for continue and fork, `--resume <id>`, and for fork, `--fork-session`. The prompt goes on stdin. The child runs in the workspace with the call's timeout and a 64 MiB stdout cap.
6. It builds the child's environment. The overlay sets `ANTHROPIC_API_KEY`, `CLAUDE_CONFIG_DIR`, `DISABLE_AUTOUPDATER=1` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. Every inherited `ANTHROPIC_*` or `CLAUDE*` name is removed except `CLAUDE_CODE_GIT_BASH_PATH`.
7. `ClaudeWire.read` reads the answer. It checks, in this order: the timeout; the output cap (both report the stderr text and the newest thread id they can read); `is_error` (401/403 → `claude.key_rejected`, else `claude.run_failed`); a non-zero exit (the "No conversation found" marker → `claude.thread_not_found`, else `claude.run_failed` with stderr); `claude.protocol_mismatch` for anything it cannot read; and the wrong-thread checks (a continue answered on another id → `thread_not_found`, a fork answered with its source id → `protocol_mismatch`). The answer text is capped at 100,000 characters.

Nine `claude.*` members are appended to `FailureCode` after `MUSE_WSL_UNAVAILABLE`, so main's 148 values keep their order. Every literal lives in `vidbyte/lib/constants/native_threads.py`. #1044's earlier `ClaudeHost`, 15 tools, toolset and `claude-agent-sdk` extra were removed on this branch (commits fdd21650 to 29ec0755). That removal does not show in `origin/main...HEAD`, because that code never reached main. Outside `docs/`, `git grep -nE "ClaudeHost|ClaudeTools|claude-agent-sdk|claude_agent_sdk"` finds only three kinds of hit: the surface test that pins those names as absent, the FEATURE.md history line, and `skills/runtime-primitives`, whose reference to `claude-agent-sdk` is on main too.

Size: 38 files outside `docs/` changed (+2,599 / −125). The three Claude modules hold 364 lines (22 + 190 + 152).

## Deviations from the spec (4, all in the PR body)

1. **`ClaudeWire._missing_member` signature.** §8.5 and §12.3 row 20 say `(answer, session, text)`. The code has `(answer, session)` (687141f7, R-8). Spec §17 items 2 and 5 record this.
2. **Exit-0 `protocol_mismatch` thread id.** Row 20 says `thread_id=session`. The code passes the newest id instead: the caller's id on a continue, else the session id. INV-6 requires this. Spec §17 item 1.
3. **Two shared sentences**, in the README's hostkit sentence and REPO_MAP's "Plumbing the harnesses share". The new helper made the old wording wrong. Spec §17 item 4.
4. **Spec §5 drifted, and I updated it in 3244af75.** The old text listed three failure points. It missed the private-folder step (`claude.launch_failed`) and the `runtime.error` catch-all. Its sequence diagram also did not parse: two `;` in one message are statement breaks in Mermaid. §5 now carries the PR body's flow chart, and the semicolons are now commas. Spec §17 item 7 records this, and the r4 row is `| r4 | 2026-10-17 | S6 PR | finalized for review: … |`.

Frontmatter: `status: pr-open`, `updated: 2026-10-17`. The `pr:` URL was already correct.

## The §4 snippet (AC-1), run by hand

I copied §4 into `scratchpad/s6conf/snippet_run.py` and changed only the two paths: the workspace became `s6conf/ws/my-app` and the skill became `s6conf/skills/write-tests`. I ran it with PYTHONPATH set to the worktree, HOME and USERPROFILE set to `s6conf/home`, a fake `sk-ant-…` key, and PATH reduced to the S4 stand-in `bin/` (`s4conf/bin/claude.exe`, which logs every start), Python and System32. The real `claude` never ran.

Output, exit 0:
```
claude True True
answer to: Try it with argparse instead.
```

The stand-in logged three starts (`s6conf/log/start-0..2.json`):
- **argv for each verb.** Run: `--print --output-format json --setting-sources user --permission-mode acceptEdits`. Continue adds `--resume e6a32a73-…`. Fork has `--model sonnet --resume e6a32a73-… --fork-session`. All three match AC-5.
- **Environment.** Each child saw only `ANTHROPIC_API_KEY`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` and `CLAUDE_CONFIG_DIR` among the `ANTHROPIC_*`/`CLAUDE*` names, and `DISABLE_AUTOUPDATER=1`. The 12 `CLAUDE*` session variables of my shell were removed. The key's sha256 prefix was `83f7b6ad28bb`, which is the fake key.
- **Config folder.** `CLAUDE_CONFIG_DIR` was `…\home\.vidbyte\claude-configs\16c334a80cd2cc17`, which equals the sha256 key I computed by hand from the resolved workspace. `skills` was `['write-tests']` for all three starts.
- **Workspace.** It was still empty after the run.

I also checked that every test named in the AC → proof table exists, by collecting the Claude pack (`s6conf/collected.txt`). After 3244af75, `tests/features/harness_threads/test_harness_threads_claude_surface.py` gave 32 passed.

## PR body checks

- **Mermaid.** Every Mermaid block in `pr-body.md` and `spec.md` parses with mermaid 10.9.1 `mermaid.parse` under jsdom (`scratchpad/mmd-check/check.mjs`). The negative control `neg.md` fails as it should.
- **Live body.** The body on GitHub (`gh pr view --json body`) matches `git show HEAD:…/pr-body.md` minus the title line. The only difference is one trailing newline, and the live body has no CR. I posted the LF form from `git show`, because `core.autocrlf=true` makes the working copy CRLF.
- **Required parts.** The body ends with the required Claude Code line, and the title line has no `[WIP]`.

## Final PR state

`gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1044 --json title,isDraft,baseRefName,url,headRefOid` after the `gh pr edit` (the head then moves to the report commit; see STATUS):
```
{"baseRefName":"main","headRefOid":"3244af7592cb219c46f83ea0e14da1a5823090aa","isDraft":false,"title":"feat(harnesses): run, continue and fork Claude Code threads with the caller's API key","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1044"}
```

## Check runs

Remote, on 3244af75, dispatched by hand (`gh workflow run ci.yml --ref feat/claude-host`, run 39004603149; `gh workflow run static-policy.yml --ref feat/claude-host`, run 39004604870). Read with `gh api repos/cerredz/Vidbyte-SDK/commits/3244af7592cb219c46f83ea0e14da1a5823090aa/check-runs`:
```
Package               completed  success
Static policy         completed  success
Source / Python 3.12  completed  success
Source / Python 3.11  completed  success
```
4/4 green, and no rerun was needed. The commit that adds this report changes only this file and one Verification row of `pr-body.md`. Its own check runs are in the S6 STATUS block.

Local source stage at 3244af75 (`PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source < /dev/null`, log `scratchpad/s6conf/source-gate.log`): `exit=0`, HEAD 3244af75 at the start and at the end, `SDK-LINT: PASS` (A002 566/703 and S009 346/350 IMPROVED, which are the same counts as at ee3b4e88; the baseline was not touched), `reasoning trace contracts: ok (182 tools, 55 shapes)`, `6445 passed, 16 skipped in 193.01s (0:03:13)`, `CI passed.`

## Candidate field-guide lessons (not written to the field guide)

Shape: trigger · preferred action · project-specific reason · quick check · link.

1. **A REPO_MAP entry stays code-free.**
   - Trigger: adding a feature to a folder entry in `REPO_MAP.md`.
   - Action: describe what the folder now holds in plain words, with no function names, file names, flags or paths.
   - Reason: `REPO_MAP.md:7` calls the map code-free. R-4 (Major) caught `CLAUDE.md`, three function names, `--setting-sources user` and a path, and AC-23 now pins the plain wording.
   - Quick check: `git diff origin/main...HEAD -U0 -- REPO_MAP.md | grep '^+' | grep '`'` prints nothing new.
   - Link: #1044, 0fd70984.
2. **Name the spec when you cite its IDs in a shared file.**
   - Trigger: citing `EC-`, `INV-`, `T-` or `D-` in a header or README that another spec's code already cites.
   - Action: write "(claude-thread-functions spec EC-38)". A bare "(spec …)" in those files means #1036's spec.
   - Reason: R-9 and R-17. Bare citations in the harnesses README, `hostkit/folders.py` and the two shared `native_threads.py` headers resolved to the wrong rows.
   - Quick check: `git diff origin/main...HEAD -U0 -- vidbyte | grep -E '^\+.*\(spec [A-Z]+-[0-9]+'`, then look each hit up in the spec its file belongs to.
   - Link: #1044, 547da5bf.
3. **A002 is a ratchet, not a rule for each function.**
   - Trigger: a review flags new functions without `# @intent`.
   - Action: run `python lint/run.py --rule A002`. At or below baseline is a pass. Add `@intent` where the merged siblings have it, and never pass `--update-baseline`.
   - Reason: the S4 verifier downgraded R-5 from Major to Minor for this reason. The merged Grok counterparts have no block either.
   - Quick check: the output shows `A002 … IMPROVED` or `OK` and `SDK-LINT: PASS`.
   - Link: #1044, review.md R-5.
4. **A child environment variable name is an enum member.**
   - Trigger: a new constant that holds an environment variable name for a native child.
   - Action: add it to `NativeEnvironmentVariable` in `vidbyte/lib/enums/native_threads.py` and update the `EXPECTED_ENUMS` pin, instead of keeping a raw string in constants.
   - Reason: AGENTS.md requires an enum for any value from a closed set. R-11 is open because §8.5 prescribed the literal `"CLAUDE_CODE_GIT_BASH_PATH"`.
   - Quick check: `git diff origin/main...HEAD -U0 -- vidbyte/lib/constants | grep -E '^\+.*"[A-Z][A-Z0-9_]{5,}"'`.
   - Link: #1044, R-11.
5. **Match the sibling harnesses' error detail, code by code.**
   - Trigger: adding a failure path to a native harness.
   - Action: attach what Grok, opencode and Muse attach for the same problem: the scrubbed stderr and the newest readable thread id.
   - Reason: G-4 and INV-6 ask for "the same detail as #1036's harnesses". R-1 (Major) was `output_too_large` without stderr.
   - Quick check: compare the `bound(...)` and `from_*` calls for that problem across `vidbyte/harnesses/native/*/wire.py`.
   - Link: #1044, bb624cc9.
6. **Read the answer before you classify a timeout or a cap.**
   - Trigger: a wire reader that checks `timed_out` or the stdout cap first.
   - Action: parse the newest thread id from the stdout that `CliRunner` keeps on timeout, and report it in the error.
   - Reason: R-3 (Major). Claude can print its answer and then hang, and the caller needs the id to continue. `runner.py:225-238` keeps stdout on timeout.
   - Quick check: a stand-in that prints a valid answer and then sleeps gives `claude.timed_out` with that `thread_id`.
   - Link: #1044, b65590a4.
7. **Refuse lone surrogates before a stdin prompt starts anything.**
   - Trigger: a harness that writes the prompt to the child's stdin as UTF-8.
   - Action: validate the prompt with a pattern that excludes `\ud800-\udfff`, as `CLAUDE_PROMPT_PATTERN` does.
   - Reason: R-2 (Major). The UTF-8 encode fails only after the child has started with the key, and the child was left running (`runner.py:216-236`). opencode on main has the same gap (EC-38).
   - Quick check: `run_claude_thread(prompt="a\ud800b", …)` raises `configuration.invalid_argument`, and no process starts.
   - Link: #1044, 9398d9ee.
8. **After a commit that changes only comments, check that no code moved.**
   - Trigger: a repair commit that edits comment or docstring text next to code.
   - Action: run `python -m ruff check --no-cache --isolated --select E225 --preview <files>`, which catches `thread_id =request`, or diff with `--word-diff`.
   - Reason: R-18. Two repair commits (687141f7, 821af103) dropped a space after `=`, and the repo's ruff config did not flag it.
   - Quick check: the command above prints `All checks passed!`.
   - Link: #1044, ee3b4e88.
9. **Parse every Mermaid block before you push it.**
   - Trigger: a spec or PR body with a `sequenceDiagram`.
   - Action: never put `;` in a message, because it ends the statement. Validate with `mermaid.parse` (mermaid 10.9.1 under jsdom).
   - Reason: this spec's §5 sequence diagram had failed to parse since S1, and no stage noticed.
   - Quick check: `node check.mjs <deps> <files>` prints `OK` for each block.
   - Link: #1044, 3244af75.
10. **Post the LF form of a tracked PR body.**
    - Trigger: running `gh pr edit --body-file` from a Windows worktree with `core.autocrlf=true`.
    - Action: build the body file from `git show HEAD:<path>`, not from the working copy.
    - Reason: the working copy is CRLF, and the committed file is the record of what was posted.
    - Quick check: `grep -c $'\r' <body file>` prints 0.
    - Link: #1044.

## Things that looked wrong while reading (none blocking, no source changed)

- **Cosmetic error text** at `vidbyte/harnesses/native/claude/wire.py:143-149`. When an `is_error` answer has `api_error_status` and a `result` but neither `terminal_reason` nor `subtype`, `reason or ""` with `CLAUDE_ERROR_STATUS_TEXT = "{reason} (status {status}): {message}"` (`vidbyte/lib/constants/native_threads.py:387`) gives `" (status 401): Invalid API key"`, with a leading space and no reason. The scratch probe `s6conf/probe_error_text.py` reproduces it. The code is right and the text is readable, but the template could drop the empty reason. This fits with R-12, which is about the same template.
- **AC-22 coverage.** AC-22 (a hostile workspace `.claude/`, `CLAUDE.md`, skill and `.mcp.json` reach nothing) is proved in tests against a stand-in, which checks the argv and environment the SDK sends. That `--setting-sources user` plus `CLAUDE_CONFIG_DIR` makes the real CLI ignore those files rests on the S0 vendor probes against Claude Code 2.1.301. The PR body says so under Known limitations (A-1 to A-3 offline only).
- I found no dead code and no vacuous test in the Claude pack. Each AC's named tests exist and are collected.
