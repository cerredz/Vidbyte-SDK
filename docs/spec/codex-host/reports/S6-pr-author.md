# S6 PR author: codex-host

Worktree `vidbyte-sdk-codex-host`, branch `feat/codex-host`, draft PR https://github.com/cerredz/Vidbyte-SDK/pull/1055, base `main` (`8387d666`, 0 commits behind). In: HEAD `5c65eec8`, clean; origin at `19bc9931`, so the two docs commits `9b79a493` and `5c65eec8` go up with this stage's push. The code is unchanged since `888db88f`. Out: one commit, `docs(spec): finalize codex-host for PR`, holding `spec.md`, `pr-body.md` and this report, then a second docs commit that records the run ids and the `gh` output below.

## What I changed

- **`spec.md` frontmatter:** `status: verified` → `status: pr-open`. `pr:` and `updated: 2026-10-14` were already right.
- **`spec.md` §5:** redrawn (see "§5 drift" below), with a one-line preface that points at §17.
- **`spec.md` §17:** row `r6 | 2026-10-14 | S6 PR`, saying the spec was finalized on draft PR #1055, the status moved to `pr-open`, and §5 was redrawn.
- **`pr-body.md`:** written. Its first line is the title, `feat(harnesses): add CodexHost with one agent tool per Codex function`. The headings follow the brief, with the repo template's Motivation and Compatibility added, and the template's four checkboxes closing Verification. The last line is the Claude Code attribution.
- No source, test, lint, contract or generated file changed. I did not touch `feat/claude-host`, PR #1044 or the main checkout.

## The code in my own words

`CodexHost` is an async context manager over one `codex app-server` process. On enter it resolves the binary with `shutil.which` (host.py:159-167), or runs `launch_args_override` as given, and never uses openai-codex's bundled binary. It builds the sync `CodexClient`, refuses a runtime older than 0.151.0, and starts a liveness monitor. Every SDK call goes through `CodexConnection`, which runs it on the host's own 32-worker pool under a 300 s bound. Turn starts are shielded. A start that outlives its caller is handed over: a queued one is withdrawn, and a running one keeps its thread busy, is adopted when it lands, and gets one interrupt. Each spending operation checks its own inputs, then `CodexPreflight` (sign-in, usage, Windows sandbox, model, busy thread), then the D-32 reviewer check on the thread Codex reports, and only then starts a turn or a goal. A started turn becomes a `CodexLiveTurn`, or a `CodexGoalTurn` for a goal run, in `CodexTurnRegistry`. One `CodexTurnWatcher` thread per turn posts notifications back to the loop, where the turn keeps items and usage, stops itself once on a timeout or the output cap, and finishes once into a `CodexTurnSnapshot`. Errors are built in one place, `CodexErrorMapper`, and are raised `from None` with a `codex.*` code and a next step. Close, and process death, end every running turn as FAILED with `codex.process_exited`. Only close then interrupts those turns. Both close goal streams and close the client on a daemon thread. The 15 tools in `vidbyte/tools/builtins/codex/` are thin: each builds a record from the model's arguments, calls one host method, and turns a `CodexAgentError` into an error `ToolResult`. `CodexToolScope` holds the live-turn cap and the handles that scope owns.

## §4 snippet

I ran spec §4 verbatim inside the AC-1 test's `HostTestCase`, at the fake seam (`codex_host_fakes.py`, a subclass of the real `CodexClient`), from a scratch script outside the repo. It printed:

```text
True
completed The readme describes the SDK.
15 check_codex_ready
```

The fake's log shows `initialize`, `account/read` and `windowsSandbox/readiness` for `check_codex_ready`, then `account/read`, `account/rateLimits/read`, `windowsSandbox/readiness`, `thread/start` (`approvalPolicy: on-request`, `approvalsReviewer: auto_review`, `ephemeral: false`, `sandbox: read-only`) and `turn/start` for the spawn. The requests ran on `codex-host_0`, and the client closed on `codex-host-close`. No real `codex`, app-server or account was used. A live run spends the user's plan and stays manual QA.

## Gate matrix (local, on `5c65eec8`, whose code equals `888db88f`)

| Gate | Result |
|---|---|
| Pack, `-P`, with the `codex` extra | `116 passed in 7.90s` |
| Pack, CI view (`sys.modules['openai_codex'] = None`) | `36 passed, 80 skipped in 1.87s` |
| `run_ci.py --stage source` | `SDK-LINT: PASS` … `4122 passed, 22 skipped in 42.91s` / `CI passed.` |
| `run_ci.py --stage package` (no `PYTHONPATH`) | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.`; the build log adds all 18 new modules |
| `generate-sdk-public-api.py --check` | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| A002 JSON, filtered to the 27 branch files under `vidbyte/` | `found 579 baseline 703 verdict IMPROVED`; 4 rows, all main's `lib/errors/base.py` `__init__`s (161, 251, 266, 275) |
| Hygiene | no key, token or email pattern in added lines; 0 tracked `.pyc`; every path under `vidbyte/`, `tests/features/codex_host/`, `docs/spec/codex-host/` or `REPO_MAP.md`; `pyproject.toml`, `contracts/`, `lint/baseline.json` and `vidbyte/__init__.py` have no diff |
| Semgrep, local | not run: the global install fails on an `mcp` 2.x import. The remote `static-policy.yml` run is the evidence |

All 78 test names in spec §6.2's proof column exist on the branch. Per file: bridge 2, failures 6, lifecycle 13, packaging 7, records 11, review_gaps 15, review_goals 9, router 1, sdk_contract 3, threads 19, tools 17, turns 13.

## Remote checks and the PR

The first commit, `601daff9`, was pushed (`19bc9931..601daff9`). Then:

- `gh pr edit` set the title from line 1 of `pr-body.md` and the body from `tail -n +2`. `gh pr view --json title,isDraft,baseRefName,url` printed `{"baseRefName":"main","isDraft":true,"title":"feat(harnesses): add CodexHost with one agent tool per Codex function","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1055"}`. There is no `[WIP]`, the PR is still a draft, and the base is `main`.
- `gh pr checks` printed `no checks reported on the 'feat/codex-host' branch` (exit 1), because both workflows run only on dispatch.
- `static-policy.yml` run 38621318168, headSha `601daff95405b2fa83bbdebe5cc17f945f4b792a`: success, `Ran 1 rule on 911 files: 0 findings.`
- `ci.yml` run 38621314395, same headSha: failure. `Source / Python 3.12` passed with `4045 passed, 99 skipped, 19 warnings in 43.35s` / `CI passed.` `Package` was skipped, because it needs both source jobs.
  - `Source / Python 3.11`, attempt 1: `1 failed, 4044 passed, 99 skipped in 44.45s`. `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` raised `MCP request timed out`: the child Python did not answer within the test's 5 s `request_timeout`.
  - `gh run rerun 38621314395 --failed`, attempt 2: `2 failed, 4043 passed, 99 skipped in 70.76s`. It hit the same MCP test, and also the known flake `test_coding_agent_environment.py::test_real_bash_reports_its_version_and_git` ("bash did not finish within 15 seconds").
- **Why I read this as the runner, not the branch.**
  - `git diff --name-only 780c26f4 601daff9` lists only `docs/spec/codex-host/` files.
  - `ci.yml` run 38530861705 on `780c26f4` passed 3.11 on the same Python, 3.11.17.
  - The branch touches no MCP or stdio file.
  - Attempt 2 took 70.76 s against about 45 s, and both failures are timeouts on a child process.
  - Other branches' 3.11 jobs passed today, for example runs 38612263492 and 38607162300.
  - Locally, on Python 3.11.0, I ran the pack's CI view and then `tests/test_mcp_stdio_transport.py` in one process (`sys.modules['openai_codex'] = None`). This looked for an order dependency, and it passed 3 times out of 3 with `58 passed, 80 skipped`. The MCP file alone gives `22 passed`.

  I did not rerun the run a second time. The second docs commit gets a fresh dispatch instead.

`pr-body.md` cites the runs on `601daff9`, because the file cannot cite runs on the head that contains it. The GitHub description is regenerated after the second commit's runs finish, and its Verification rows cite that head's run ids.

## §5 drift

§5 at r5 drew preflight before the params translator, had no output-schema check before `thread/start`, no hand-over of an outlived start, and one shared stop step on the host. The code checks its local inputs (input items, tool names, `experimental_api`, the schema serializing) before preflight, hands over outlived starts in `CodexConnection._hand_over`, and stops a turn through `CodexLiveTurn.stop`. The close drawing also missed that process death skips the interrupts and that the executor shuts down only at close. The redraw is a main flowchart, a six-step close and death flowchart and an updated sequence diagram. The PR body's Flow section uses the same two flowcharts.

## Deviations listed in the PR body (8)

1. S3's deviation 1 (C002 reshape) is withdrawn by R-8 (`f2e9db7e`).
2. Process death also closes goal streams and reaps (host.py:757-768), beyond D-27's steps 1 and 2.
3. The one stop lives on `CodexLiveTurn.stop` (turns.py:166), not the host's late-acceptance handler (§12.3 row 15).
4. A handed-over start keeps its thread busy through `CodexConnection._starting` (connection.py:149, :244-269), beyond INV-24's wording.
5. Interrupt also skips while an earlier stop is pending (host.py:410; `send_stop` at turns.py:179), beyond §9.2's row.
6. A cyclic mapping `output_schema` is refused with EC-82 (wire.py:252-264), from `736d4a58`, beyond the review packet.
7. The six `CODEX_*_NOTIFICATION` constants (constants/codex.py:366-371) are not read by any source file; the watcher matches typed models (turns.py:102-107). §9.3 says the watcher reads them.
8. §5 drifted and is redrawn in this stage's commit.

## Things that looked wrong (not fixed here: no source changes in S6)

- **Unused constants.** vidbyte/lib/constants/codex.py:366-371 defines six notification names that no source file reads. Only tests/features/codex_host/test_codex_host_records.py:436-441 pins them. Either delete them or correct spec §9.3.
- **R-32 overclaim.** tests/features/codex_host/FEATURE.md:100 and tests/features/codex_host/test_codex_host_review_gaps.py:395 say a user interrupt "while one is in flight" is covered. Only Vidbyte's own timeout stop in flight is tested.
- **Spec §0.2 is stale.** It says "None yet" for user answers, but pipeline.md records the user's `continue` (2026-10-14, about 18:50 UTC). It is outside S6's edit scope (frontmatter, §5, §17).
- **Remote CI never runs the host tests.** `ci.yml` installs `.[dev]` without the `codex` extra, so the 80 host tests skip on every remote run. Only local runs exercise them.
- **`gh pr checks` shows nothing.** Both workflows are dispatch-only, so it prints `no checks reported on the 'feat/codex-host' branch`. Run results are read with `gh run view`.

## Candidate field-guide lessons (not written to the guide)

- **When** a field holds a closed vocabulary and an enum for it already exists in `vidbyte/lib/enums/`. **Do** type the field as that enum and convert once at the wire edge. **Because** AGENTS.md:63 forbids plain `str` for closed sets, and review raised it as a Blocker (R-3). **Check** grep the new records for `: str` fields whose values come from a fixed table. **Evidence** R-3, `8f6975e8`.
- **When** a class's helper calls another of its own helpers. **Do** lift the call into the main function, or move the pair to a collaborator class. **Because** AGENTS.md principle 1 caps call chains at one level, and review raised depth 2 and 3 as a Blocker (R-4). **Check** for each private method, list the `self._*` calls it makes. **Evidence** R-4, `846ce849`, which moved the stop onto `CodexLiveTurn`.
- **When** lint C002 flags an argument check. **Do** call the existing `_reject_*` helpers instead of reshaping the check. **Because** reshaping to dodge the rule was a Major (R-8), and a spec deviation that excused it was withdrawn. **Check** `blocking-lint-invariants.md:48`. **Evidence** R-8, `f2e9db7e`.
- **When** a new function's name has an A002 policy token (`send`, `start`, `stop` and others, split on `_` and `.`). **Do** put a `# @intent` line within 20 lines of the def. **Check** with `lint/run.py --rule A002 --all --format json`, filtered to the branch's files. **Because** the text form prints only the summary when the verdict is IMPROVED, and the baseline of 703 leaves slack that hides new rows. **Evidence** R-9 `fad8c55f`, R-30 `888db88f`.
- **When** code sends JSON-RPC method names that error mapping also compares. **Do** use `CODEX_*_METHOD` constants in both places. **Because** inline literals drifted apart (R-11). **Evidence** `528e5ef6`.
- **When** a harness error wraps a library exception. **Do** carry only the exception's type name and `raise … from None`. **Because** S017 does not scan `vidbyte/harnesses/`, so nothing else catches leaked library text (R-26). **Evidence** `30109e89`.
- **When** a tool description or docstring promises an output-schema check. **Do** say it only for Pydantic types. **Because** `OutputSchemaFormatter.validate` validates Pydantic types, and a mapping schema is only JSON-parsed (R-12). **Evidence** `bbe9672f`, `4a9ecc49`.

## After the push

The second docs commit adds the results above to this report and to `pr-body.md`. Both workflows are then dispatched again on its head. The final head, its run ids and their conclusions are in the STATUS block this stage returns, and in the PR description on GitHub.

A further candidate lesson, from this stage: **when** `ci.yml`'s 3.11 job fails only on a test that waits on a child process under a fixed timeout (`test_mcp_stdio_transport.py`'s 5 s, the bash probe's 15 s), and the code equals a head that passed, **do** compare the job's wall time and the diff to that head before suspecting the branch. **Because** a slow runner fails several of these tests at once. Attempt 2 here took 70.76 s against about 45 s.
