---
slug: codex-host
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host
branch: feat/codex-host
base_commit: 678136bd4358bcf9f120504cecd818d36a3d46fe
pr:
until: none
started: 2026-10-13 00:45 UTC
---

# Pipeline: CodexHost: small atomic Codex functions with one agent tool per function

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-13 00:45 UTC | 2026-10-13 01:27 UTC | reports/S0-scout.md | base_commit 678136bd; code-map.md, 4 sections |
| S1 spec + review | done | 2026-10-13 01:35 UTC | 2026-10-13 11:25 UTC | reports/S1-spec-author.md, reports/S1-spec-review.md, reports/S1-spec-review-r2.md | spec r3 81a71d00, status: approved; 2 review rounds (SOUND WITH FIXES ×2), 18 findings applied, 0 disputed |
| S2 tests | done | 2026-10-13 11:30 UTC | 2026-10-13 16:35 UTC | reports/S2-test-author.md | S2_HEAD 1d110811 (tests 46f1a9db, proof 55f01f44, report 1d110811); 101 tests in tests/features/codex_host/, all red (`101 failed` in the [dev,codex] venv; CI view `35 failed, 66 skipped`); spec r4 38e3a820 pins the S2 spec defects; spec status: tests-written |
| S3 implement | done | 2026-10-13 16:40 UTC | 2026-10-14 02:40 UTC | reports/S3-implementer.md | S3_HEAD 099fac83; draft PR https://github.com/cerredz/Vidbyte-SDK/pull/1055 ([WIP] title); 30 commits; 28/28 §12.3 rows; budget 18/18 files, 30/30 classes, 15/15 records, 13/13 enums, 0 deps (no headroom); pack 101 passed, CI view 35 passed / 66 skipped (orchestrator re-run); full suite 4041 passed / 22 skipped; run_ci source+package PASS; SDK-LINT PASS; semgrep 0; public API --check 0; spec status: implemented |
| S4 adversarial review | done | 2026-10-14 02:50 UTC | 2026-10-14 04:05 UTC | reports/S4-review-conformance.md, reports/S4-review-conventions.md, reports/S4-review-engineering.md, reports/S4-findings-verifier.md, review.md | MERGEABLE AFTER FIXES; confirmed 5 Blockers (R-1..R-5) / 9 Majors (R-6..R-14) / 11 Minors (R-15..R-25, R-25 scope-adding); refuted 0; every fix within the exhausted §8.4 budget; spec status: reviewed |
| S5 repair loop | done | 2026-10-14 04:40 UTC | 2026-10-14 09:30 UTC | reports/S5-repair-1.md, reports/S5-repair-2.md, verify-log.md | iteration 2 (R-26 @30109e89 + @736d4a58, R-27 @ad363725, R-28 @3d26abfe, R-29 by spec r6 130dd828) converged at 7b05e68b (code at 77c92838): orchestrator gate 4122 passed, 22 skipped in 38.58s (source), Installed vidbyte-sdk 0.2.1 passed smoke checks. (package); remote 38526282824 + 38526285681 green on 77c92838. Iteration 1 converged at bbaa5a8b (code at fb76e558): fixed R-1..R-18 (R-12 also by spec r5 bbe9672f); 10 new tests (granted file); merge origin/main 8387d666 at fb76e558; orchestrator gate: 4117 passed, 22 skipped in 38.55s (source), Installed vidbyte-sdk 0.2.1 passed smoke checks. (package); remote ci.yml 38519843721 + static 38519846158 green on fb76e558; R-19..R-25 follow-ups |
| S5 re-review | cap reached (round 2 of 2 done: MERGEABLE AFTER FIXES 0B/1M/2m; scoped verifier r2 running) | 2026-10-14 06:50 UTC | | reports/S5-rereview.md, reports/S5-findings-verifier-r1.md | round 1 at bbaa5a8b: MERGEABLE AFTER FIXES 0B/2M/2m — R-C1 Major (R-16 regression: after any failed stop, a user interrupt sends nothing, host.py:407), R-C2 Major (R-2's refusal puts pydantic exception text in the harness error and chains it, wire.py:262, §12.4/INV-9), R-C3 Minor (title/instructions descriptions), R-C4 Minor (spec §9.3 lacks R-11's constants) |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 2/8 · S5 re-review rounds: 2/2 (cap reached)

## Parallel run
- **Sibling pipeline:** `claude-host`, in worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host` on branch `feat/claude-host`, from the same base commit. Each run follows the shared-file contract in its request.md §C.
- **The orchestrator checks byte-identity** of `vidbyte/harnesses/native/__init__.py` in both PRs. Its SHA-256 must be `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.

## Decisions the orchestrator made
- 2026-10-13 00:45 UTC — **Scope is CodexHost's ★ set only** (14 rows, 15 functions), plus the spawn request, the host class, the error mapper, one tool per function, the toolset and contract tests. *Why:* R3's legend says "★ = first PR for that host", and Prompt 4 asks for one PR per host (request.md §C).
- 2026-10-13 00:45 UTC — **Answers to the R3 "Needs you" questions.**
  - Q1 (⚑ functions): default, left out.
  - Q3 (installed binary): default.
  - Q2 (sequential PRs): superseded by Prompt 4's parallel PRs.
  *Why:* Prompt 4 ("great, …") is the reply to R3's card.
- 2026-10-13 01:30 UTC — **Revised the shared-file contract in request.md §C after S0.**
  - `native/__init__.py` now carries the A001 seven-field header (fixed bytes, SHA above).
  - No `native/README.md`.
  - No shared test files; tests go in per-host feature packs, which carry no `__init__.py`.
  *Why:* the S0 scout's C1 finding. A001 has no empty-file exemption, and its baseline (643) has no headroom. No lint rule requires a folder README.
- 2026-10-13 01:30 UTC — **Environments.**
  - The dedicated Semgrep venv `C:/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1` (semgrep 1.170.1) is created and shared by both runs.
  - This run's Python venv for tests and gates is `C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host`, created at S2.
  *Why:* never pip-install into the global Python. Its editable `vidbyte` install points at the canonical checkout, and two parallel runs would clobber each other. Semgrep breaks next to the SDK's mcp 2.x.

- 2026-10-13 05:32 UTC — **An API session limit (HTTP 429) killed the S1 author** after it had written spec.md but before it committed. Once the limit reset, the orchestrator resumed the same agent with SendMessage. The resume message carried three corrections:
  - export lists take sorted inserts;
  - S045 forbids a `timeout` parameter on async methods;
  - every raw `request` call must stay S012-compliant without suppressing the rule.
- 2026-10-13 05:55 UTC — **S1 r1 spot-check passed.** The frontmatter `base_commit` and `worktree` match, there are 18 `## §` sections, §12.3 (lines 1190–1222) has 28 numbered rows, and the last commit is `docs(spec): add codex-host spec r1` (a1ee792a).
- 2026-10-13 05:55 UTC — **Two revisions to request.md §C, the shared-file contract,** with the same change made to the ClaudeHost request.md:
  1. The export-list bullet now says "insert only your own entries, in the file's own sorted order; never reorder or remove existing ones", replacing "append-only".
  2. A new bullet fixes byte-identical text for the `REPO_MAP.md` native section and the `vidbyte/harnesses/README.md` bullet. The bullet block is byte-identical in both request.md files (SHA-256 `6da4fa77…51277b0`).
  *Why:* spec r1 §12.5 proposed its own REPO_MAP text and asked the orchestrator to give PR B identical text, but ClaudeHost spec r1 had different text at the same two insertion points, which would conflict at the second merge. Spec r1's REPO_MAP text also broke the field guide's `agents-md-map.md` rule, which forbids backtick-quoted names and child-folder paths in a folder description. The fixed text is host-neutral and follows that rule. The spec author must adopt it in revision.
- 2026-10-13 06:35 UTC — **Review round 1: SOUND WITH FIXES, 13 findings.**
  - Every finding (R-1 to R-13) went to the author; none is tagged `[scope-adding]`, and none was declined.
  - They were forwarded by report path and line range (lines 1–278 of reports/S1-spec-review.md), not pasted into the message.
  - R-4, R-5 and R-6 change §8, §9 and §10, so a scoped round 2 follows the r2 revision.
- 2026-10-13 06:35 UTC — **R-5: the orchestrator accepted the fail-closed fix.**
  - The `approvals_reviewer` field and its `USER` member stay, because they are R3's spawn-field vocabulary.
  - Validation rejects `USER` with the spec's unsupported-combination configuration code. Its next step says that answering approvals in code comes with `set_codex_approval_handler`, which R3 marks ✗ and which is not in this PR.
  - The handler is not built (rule 11).
  *Why:* openai-codex 0.162.1 has no decline decision, and its default handler answers `accept`. In this PR, a `USER` reviewer with no handler would silently approve every escalation, the opposite of what that setting asks for. Rejecting the value narrows nothing the user can safely use today.
- 2026-10-13 06:35 UTC — **R-9: new records go in a new domain module,** not into the 1,205-line `vidbyte/lib/dataclasses/codex.py`. *Why:* AGENTS.md:31 says to split before adding more once a file heads toward four digits. So this is repo-forced, and Q-1 is no longer a question.
- 2026-10-13 07:40 UTC — **r2 spot-check passed.** `revision: 2`, §16 holds a disposition row for each of R-1 to R-13, there are 18 sections and 28 §12.3 rows (18 CREATE, 10 MODIFY), and the commit is `docs(spec): revise codex-host spec r2 (apply review round 1, R-1 to R-13)` (b38d573a).
  - The spec contains the request.md §C REPO_MAP paragraph and README bullet byte for byte (checked with `grep -F`).
  - The orchestrator committed the author's r2 report addendum.
- 2026-10-13 07:40 UTC — **Launched review round 2 (the last allowed), scoped to what r2 changed and what depends on it.** That covers §8, §8.5, §9.1–9.4, §10 T-3/T-6, §12, and the new INV/EC items. It also covers three calls the author made beyond the review:
  - INV-25/EC-74: a failed goal-budget request cancels the goal;
  - Q-3 resolved instead of left open;
  - the §11 hash command form.
- 2026-10-13 ~10:30 UTC — **An API session limit (HTTP 429) stopped the round-2 reviewer** before it wrote its report. Once the limit reset, the orchestrator resumed the same agent with SendMessage.
- 2026-10-13 10:50 UTC — **Review round 2: SOUND WITH FIXES, 5 findings** (0 Blockers, 3 Majors, 2 Minors). All five went to the author for the final revision r3, forwarded by path (lines 1–152 of reports/S1-spec-review-r2.md), with an instruction to set `status: approved`. The S1 review cap (2/2) is reached.
- 2026-10-13 10:50 UTC — **R-1 is accepted as not scope-adding.** It applies the orchestrator's earlier R-5 rule (a `user` reviewer fails closed) to the reviewer Codex *reports* in the start and resume responses, not only the one the caller writes.
  - Constraint added by the orchestrator: the check must not break the §4 default spawn, where no approval fields are set.
  - The author must establish from openai-codex what a default thread reports, and choose a default-path behavior that never silently approves and keeps §4 working, using only existing fields and settings.
  - It records that choice as a D-n with evidence, plus an A-n where it cannot be verified offline.
- 2026-10-13 11:25 UTC — **Spec r3 approved; spot-check passed.**
  - The frontmatter has `revision: 3` and `status: approved`.
  - §16 has rows r2-1 to r2-5, and the author disputed none.
  - There are 18 sections and 28 §12.3 rows.
  - The commit is `docs(spec): revise codex-host spec r3 (apply review round 2, R-1 to R-5; approved)` (81a71d00).
  R-1 became D-32. A `user` reviewer reported with any policy except `never` starts no turn or goal. Spawn still sends the SDK's own default (`on-request` plus `auto_review`), so §4 works. Resume sends nothing unless set (A-15, A-16). The "Spec ready" summary was printed, and the run continued to S2 without waiting.
- 2026-10-13 11:25 UTC — **Every Q-n takes its stated default:**
  - Q-1: resolved by the new `codex_host` module.
  - Q-2: minimum `codex` version 0.151.0.
  - Q-3: resolved; `USER` is rejected, and `accept` remains only as a fallback.
  - Q-4: no root exports.
  - Q-5: `launch_codex_subagents` limit, default `None`.
  - Q-6: `prompt` and `goal` are mutually exclusive.
  - Q-7: no MCP permission check.
  - Q-8: no thread-ownership restriction.
  - Q-9: no ceilings; model-supplied values replace defaults.
- 2026-10-13 11:30 UTC — **S2 environment:** `C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host` with `pip install -e "<W>[dev,codex]"`.
  *Why:* spec §13 builds fake responses from openai-codex's real generated models, so host tests need openai-codex locally and are gated with `skipUnless(find_spec("openai_codex"))` for CI, which installs only `.[dev]`. The test author must also show which tests still run with openai_codex blocked, which is the CI view.

- 2026-10-13 16:35 UTC — **S2 spot-check passed.**
  - All of AC-1..AC-37 are cited in test-plan.md.
  - The red run is quoted for both views.
  - I re-ran `test_codex_host_turns.py` myself and got `13 failed in 1.05s`, all `ModuleNotFoundError`.
  - The test author made three commits, and the tree is clean. No bytecode is tracked.
  - The pack imports `tests.features.codex_host.*`, so when it runs from outside this worktree's root, it needs `python -P -m pytest … --rootdir=<worktree> -c <worktree>/pyproject.toml` with `PYTHONPATH=<worktree>`. Otherwise another checkout's `tests` package shadows it.
  *Why:* the S2 spot-check rule.
- 2026-10-13 16:35 UTC — **Sent the three S2 spec defects to the spec author in Revision mode (r4) before S3.** Lines 210–219 of the S2 report and test-plan.md from line 218 were forwarded by path.
  - r4 (38e3a820) adds D-33 (handles owned by value: a registered `(thread_id, turn_id)`, late-accepted turns included), D-34 (`limit_reached` is `rateLimits.rateLimitReachedType`, or `""`) and D-35 (a late-accepted interrupted turn carries no problem code).
  - I verified that only spec.md and the author report changed, that the §6.2 Proof column hashes the same before and after, and that there is no test diff since S2_HEAD.
  *Why:* the skill resolves spec defects before the implementer meets them.
- 2026-10-13 16:35 UTC — **Routed the INV-11 coverage gap to the S4 engineering reviewer, not back to the test author.** The gap is late acceptance for goal start (`cancel_goal_operation` exactly once), continue and launch.
  - The test author covered INV-11 through spawn and review (AC-32), following the doctrine's "single test per inventory entry".
  - The two tests it flagged as able to pass without exercising their case (the EC-78 queued start, and the goal update after completion with its 0.2 s wait) go to S4 as well.
  *Why:* S4 engineering exists to find "plausible bugs no test catches". Reopening S2 would delay S3 for a path that shares the spawn mechanism. If S4 confirms a defect, the test change goes to the test author then.

- 2026-10-13/14 — **Two more HTTP 429 session-limit interruptions hit the S3 implementer.**
  - The first came at about 18:20 UTC, at e0187887 with a clean tree.
  - The second came at about 22:30 UTC. HEAD was still e0187887, with about 74 KB of `vidbyte/harnesses/native/codex/` files untracked and not committed.
  - Each time, after the reset, I checked the tree, an empty test diff since 1d110811 and the native blob hash. I resumed the same agent through SendMessage, at 20:32 UTC and at 01:41 UTC. On the second resume I told it to commit each row as soon as it went green.
  - No work was lost.
- 2026-10-14 02:40 UTC — **S3 spot-check passed.**
  - `git status --porcelain` is empty.
  - There are 30 commits since 51dd290b. Every code commit cites W-/FR-/AC- ids, and the three `docs(spec)` commits need none.
  - `git diff 1d110811..HEAD --stat -- tests/` is empty.
  - I re-ran the pack: `101 passed in 7.40s`. The CI view (`sys.modules['openai_codex']=None`) gave `35 passed, 66 skipped in 2.12s`.
  - `gh pr view` shows draft PR #1055, title "[WIP] feat(harnesses): add CodexHost with one agent tool per Codex function", head 099fac83.
  - The spec reads `status: implemented` with `pr:` set, and the native blob hash 0374a2c8… is correct.
  *Why:* the S3 spot-check rule.
- 2026-10-14 02:42 UTC — **Dispatched remote CI on 099fac83:** ci.yml run 38500042527 and static-policy.yml run 38500046011.
- 2026-10-14 02:50 UTC — **Chose the S4 focus for each lens.**
  - Conformance: the request.md §D weighted words, AC-1 (run against the fakes only, because a live run spends the user's plan, NG-13) and the two deviations.
  - Conventions: the spec §11 field-guide entries, the §12.4 obligations and the two C002 workaround shapes.
  - Engineering:
    - INV-11 late acceptance on goal start (`cancel_goal_operation` exactly once), continue and launch, which no test covers (logged at S2);
    - the weak tests: the EC-78 queued start, and goal update-after-completion with its 0.2 s wait;
    - the riskiest test, `test_codex_host_turns.py::test_the_output_cap_counts_only_the_turns_own_tokens_and_interrupts_once`;
    - the race paths the implementer is least sure of: `connection.py` start/_hand_over/_post_late, `host.py` `__aexit__`, `_on_death`'s reap and `CodexToolScope.reserve`.
  *Why:* the S2 routing decisions and the implementer's "Tricky parts".

- 2026-10-14 03:05–03:20 UTC — **The three S4 reviewers finished,** each with the verdict MERGEABLE AFTER FIXES:
  - conformance: 0 Blocker, 1 Major, 1 Minor;
  - conventions: 3 Blocker, 3 Major, 4 Minor;
  - engineering: 2 Blocker, 6 Major, 5 Minor.
- 2026-10-14 04:05 UTC — **S4 spot-check passed.**
  - review.md exists, with 14 confirmed rows. Each has a path:line, evidence, a fix kind and a budget note.
  - Every fix is within budget.
  - Nothing was refuted. 3 sub-claims were trimmed, with reasons.
  - I read only the verifier's SUMMARY and the row tags.
  *Why:* the S4 spot-check rule.
- 2026-10-14 04:05 UTC — **Routing.**
  - **To the spec author first, in Revision mode r5**, because the escalation table says to revise the spec through its author when a later stage finds a spec defect:
    - R-12: amend INV-21 (spec.md:289) and EC-32 (:447) so a mapping `output_schema` is not claimed to be validated. A real validator is R-25, which is scope-adding and never built.
    - R-8: withdraw §17 deviation 1 (spec.md:1561). S3 wrote it to excuse a C002-evasion shape, and its budget reason is wrong.
    - R-2 stays `code`: the verifier preferred a record-check method over its spec-change alternative.
  - **To S5 repair iteration 1**, after r5:
    - the code rows R-1..R-11, plus R-12's description fix and its test;
    - the tests-only rows R-13 and R-14;
    - the trivial Minors R-15..R-18.
  - **Left as follow-ups:** R-19..R-24, and R-25 (scope-adding).
  *Why:* a spec edit lands before the code that follows it, and one agent at a time commits in this worktree.
- 2026-10-14 04:05 UTC — **Granted new tests to the codex S5 repair agent.**
  - The new tests go in one new file, `tests/features/codex_host/test_codex_host_review_gaps.py`. The pack's README.md and FEATURE.md may be extended only by addition, to list it.
  - The 101 existing tests and the fakes/support modules stay byte-identical. A missing fixture is defined inside the new file.
  - Scope of the new tests:
    - R-13: the surviving mutants M1 (late goal not stopped) and M2 (late label timed_out);
    - R-14: M3 (launch slots released on success only);
    - R-12's test;
    - regression tests for R-1, R-2, R-6, R-7 and R-10.
  - Each new test must be shown failing for the right reason against the pre-fix code or its mutant, quoted in verify-log.md.
  *Why:* every row is a confirmed gap, and adding tests does not weaken the contract.

- 2026-10-14 04:35 UTC — **Spec r5 spot-check passed.**
  - bbe9672f changes only spec.md and the author report.
  - There is no test diff.
  - INV-21 now says a mapping `output_schema` is only parsed as JSON (D-36). EC-82 refuses an unusable schema before any request, and EC-83 records that a mapping mismatch goes undetected.
  - Q-10 (a validator) is optional, default no. Deviation 1 is withdrawn.
- 2026-10-14 ~05:30 UTC — **Session restart.** The orchestrator's session ended while S5 repair iteration 1 was running. The tree was clean at 8f6975e8, with R-1..R-3 committed and the granted test file +97. I resumed the same agent through SendMessage from R-4 and told it to commit each row as soon as it went green. No work was lost.
- 2026-10-14 06:45 UTC — **S5 iteration 1 spot-check passed. The loop converged.**
  - `git status` is clean, and HEAD equals origin at bbaa5a8b. origin/main is still 8387d666, merged at fb76e558.
  - There are 18 fix commits (2f098372..08d498d8), one per finding, plus 5 review-status checkpoint commits.
  - `git diff --numstat 1d110811..HEAD -- tests/features/codex_host` shows only the granted file: test_codex_host_review_gaps.py +330/-0, README.md +2/-0 and FEATURE.md +1/-0. Nothing outside codex_host differs from origin/main under tests/.
  - The branch's own commits since 099fac83 add no file except that test file, so the budget holds.
  - verify-log.md has "## Iteration 1". review.md marks R-1..R-18 `fixed @<sha>`, and R-19..R-25 stay open as follow-ups.
  - The native blob hash is unchanged.
  - My own run: pack `111 passed in 7.13s`, CI view `36 passed, 75 skipped in 1.82s`, `4117 passed, 22 skipped in 38.55s` / `CI passed.` (source), and `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` (package).
  - Remote: ci.yml 38519843721 succeeded (Source 3.11, Source 3.12, Package) and static-policy 38519846158 succeeded, both on fb76e558. bbaa5a8b adds only docs.
  *Why:* the skill's convergence test (DONE, my gate green, remote green, no open confirmed finding).
- 2026-10-14 06:45 UTC — **The repair agent departed from the reviewers' wording on two fixes.**
  - R-4: `stop` went on CodexLiveTurn, not CodexConnection, because on the connection it would form a new stop → interrupt → call chain.
  - R-10: a set of in-flight starts on the connection, instead of keeping the registry reservation, which would have needed three release sites.

  I accepted both, because the rows ask for the outcome (no helper calling a helper; a busy thread while a start is in flight), not that exact shape. The re-reviewer checks both.
- 2026-10-14 06:50 UTC — **Final conformance re-review (round 1 of 2) launched.**
  - FOCUS: the 18 fix commits 2f098372..08d498d8, plus the granted test file.
  - The merge commit fb76e558 brings in main's 41 commits, which are out of scope.

- 2026-10-14 ~06:25 UTC — **Sixth HTTP 429 session limit.** It stopped the re-reviewer before it had written a report. After the reset I checked that the tree was clean and unchanged at fbe64628, and resumed the agent through SendMessage. No work was lost.
- 2026-10-14 07:35 UTC — **Re-review round 1 returned MERGEABLE AFTER FIXES:** 0 Blocker, 2 Major, 2 Minor. 16 of the 18 fixes hold.
  - **R-C1, Major:** a regression from R-16 (host.py:407). The guard `turn.snapshot is not None or turn.stop_sent` turns every later user interrupt into a no-op once any earlier stop failed.
  - **R-C2, Major:** R-2's refusal (wire.py:262) puts library exception text into a harness error and chains it with `from exc`, against §12.4, row 10 and INV-9.
  - **R-C3, Minor:** the title and instructions descriptions.
  - **R-C4, Minor:** the R-11 constants are missing from §9.3.
- 2026-10-14 07:35 UTC — **Launched a scoped findings verifier** on R-C1..R-C4. It appends R-26 onward to review.md and leaves R-1..R-25 unchanged.
  - A confirmed Blocker or Major goes back into the loop as repair iteration 2, and a spec-text row goes to the spec author first.
  - Re-review round 2 of 2 is the last one the cap allows.
  *Why:* the skill's final re-review rule: any new Blocker or Major gets a scoped verifier, then returns to the loop.

- 2026-10-14 08:05 UTC — **Scoped-verifier spot-check passed.**
  - It confirmed R-26 (from R-C2) and R-27 (from R-C1), both Major, and passed through R-28 (R-C3, trivial code) and R-29 (R-C4, spec-change).
  - 0 refuted.
  - The review.md diff changes only the verdict line, the two section-count headings and one sentence in the refuted section. Rows R-1..R-25 are unchanged.
  *Why:* the S4 spot-check rule, applied to the scoped round.
- 2026-10-14 08:05 UTC — **Routing.**
  - **To the spec author first, in Revision mode r6, for R-29:** a §9.3 row for R-11's 11 method-name constants (constants/codex.py:446-457).
  - **To S5 repair iteration 2 after r6:**
    - R-26: the refusal's text becomes the type name only, raised `from None`, with a test asserting no `__cause__`;
    - R-27: a `stop_pending` flag plus `CodexLiveTurn.send_stop`, leaving `over_cap()` and `stop()` untouched, with regression tests;
    - R-28: two description strings.
  - **Then the final re-review, round 2 of 2,** the last one the cap allows.
  *Why:* a spec edit lands before the code that follows it.
- 2026-10-14 08:05 UTC — **The test grant carries into iteration 2.** New tests still go only in `test_codex_host_review_gaps.py`, by appending, with README.md and FEATURE.md extended by addition only. The 101 original tests and the fakes/support files stay byte-identical.

- 2026-10-14 08:20 UTC — **Spec r6 spot-check passed.**
  - 130dd828 changes only spec.md (+4/-1) and the author report (+17).
  - The frontmatter reads `revision: 6`, `status: reviewed`.
  - There is no test diff.
- 2026-10-14 09:30 UTC — **S5 iteration 2 spot-check passed.**
  - `git status` is clean, and HEAD equals origin at 7b05e68b. origin/main is still 8387d666, so no merge was needed.
  - Fix commits: 30109e89 and 736d4a58 [R-26], ad363725 [R-27] and 3d26abfe [R-28]. 77c92838 and 7b05e68b are docs only.
  - `git diff --numstat 1d110811..HEAD -- tests/features/codex_host` shows only the granted files: test_codex_host_review_gaps.py +440/-0, README.md +3/-0 and FEATURE.md +5/-0.
  - verify-log.md has "## Iteration 2". review.md marks R-26..R-28 `fixed @<sha>` and R-29 `fixed @130dd828 (spec r6)`.
  - The native blob hash is unchanged.
  - My own run: pack `116 passed in 7.42s`, CI view `36 passed, 80 skipped in 1.69s`, `4122 passed, 22 skipped in 38.58s` / `CI passed.` (source), and `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` (package).
  - Remote: ci.yml 38526282824 succeeded (Source 3.12, Source 3.11, Package) and static-policy 38526285681 succeeded, both on 77c92838.
  *Why:* the skill's convergence test.
- 2026-10-14 09:30 UTC — **Accepted one defect fixed beyond the packet.** Commit 736d4a58 [R-26] fixes a mapping `output_schema` with a cycle under `properties` or `items`: `OutputSchemaFormatter.annotate` recursed until `RecursionError`, which escaped spawn, continue and launch, against INV-8, INV-10 and EC-82. The fix adds `RecursionError` to the types the refusal catches, and the formatter is untouched (NG-5).
  *Why:* it is the same EC-82 refusal R-26 owns, not a new feature, and the agent proved its test red against bbaa5a8b. The re-reviewer checks it.
- 2026-10-14 09:30 UTC — **R-27 residual, noted by the repair agent and not raised as a finding.** If a user interrupt's caller is cancelled while the request is already on a worker, the mark clears early and a second call sends a second interrupt. That is the pre-R-16 behaviour, and the probe is `scratchpad/codex-repair2/probe_cancelled_interrupt.py`. The re-reviewer is told about it.
- 2026-10-14 09:35 UTC — **Final conformance re-review, round 2 of 2, launched.** This is the last round the cap allows.
  - FOCUS: 30109e89, 736d4a58, ad363725 and 3d26abfe, the new tests and spec r6. It also checks that iteration 1's fixes still hold beside them.
  - If it finds a new Blocker or Major, the verifier confirms it, and then I stop and report to the user.

- 2026-10-14 10:00 UTC — **Final re-review, round 2 of 2, returned MERGEABLE AFTER FIXES:** 0 Blocker, 1 Major, 2 Minor (`reports/S5-rereview-2.md`).
  - **R-C5, Major:** R-27's commit ad363725 made `interrupt_codex_turn` (host.py:400) call `turn.send_stop`. The token `send` triggers A002, and there is no `# @intent` line, so R-9 is back. A002's baseline slack (580 against 703) hides it, and the repair-2 claim that "A002 lists nothing under the branch's paths" is false. The fix is one comment block, with no behaviour change.
  - **R-C6, Minor:** if a caller cancels a user interrupt while its request is on a worker, a second call sends a second `turn/interrupt`. No spec ID is broken, but the comments at turns.py:182-183 and host.py:402-403 describe the case wrongly.
  - **R-C7, Minor:** no test kills a mutant that removes `turn.stop_pending = True` at host.py:414.
- 2026-10-14 10:00 UTC — **Launched a scoped findings verifier (r2) on R-C5..R-C7.** It appends R-30 onward to review.md.
  - **The plan, per the skill:** a confirmed Major goes back into the loop as repair iteration 3 (3 of 8 is within the cap). Re-review rounds are capped at 2, and both are used.
  - **So after iteration 3 converges,** I stop and report to the user rather than open a third re-review. Proceeding to S6 without one is the user's call.
  *Why:* rule 7, caps are hard. The iteration cap is not reached; only the re-review cap is.

- 2026-10-14 10:20 UTC — **Scoped-verifier r2 spot-check passed.**
  - It confirmed **R-30, Major** (from R-C5): `interrupt_codex_turn`, host.py:400, has no `# @intent` while it calls `send_stop`, so R-9 reopens at a new site. The tier follows R-9's precedent, and the fix is comment-only.
  - It passed through **R-31, Minor, trivial, comment-only** (from R-C6, widened to cover the timeout stop once it outlives its 300 s bound). No spec ID is broken.
  - It passed through **R-32, Minor, tests-only, follow-up** (from R-C7): the `user_no_pending` mutant passes 116/116.
  - The review.md diff changes only the verdict line, the two section-count headings and one sentence in the refuted section. Rows R-1..R-29 are unchanged.
- 2026-10-14 10:20 UTC — **Routing to S5 repair iteration 3 (3 of 8):** R-30 and R-31, as one comment edit at host.py:401-404 plus turns.py:181-184.
  - The iteration-3 verify-log entry corrects the false claim "A002 lists nothing" (verify-log.md:229, S5-repair-2.md:34).
  - R-32 stays a follow-up, because the skill routes only `trivial` Minors to repair, and a change made after the last re-review ships unreviewed.
  - After iteration 3 converges, I stop and ask the user whether to go on to S6 without a third re-review. The re-review cap (2/2) is reached.

## User replies (verbatim)
- none yet

## Niche facts accumulated (carried into every later briefing)
- **A001** requires a seven-field header (PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES, RELATED DOCS, TESTS) in every tracked `.py`: tests, `__init__` files, everything. Its baseline is 643 with no headroom.
  - Copy the header form of `vidbyte/tools/toolsets/coding.py:1-12`.
  - The `vidbyte/tools/builtins/sessions/` modules fail A001, S062 and S017, so copy their structure, not their headers, descriptions or error strings.
  *source:* S0 code-map §2.6, §4 C1–C2.
- **S012** (baseline 0) fails any call in `vidbyte/**` to a method named `request` (and similar) without a `timeout=` or `timeout_seconds=` keyword. openai-codex's `request(method, params, *, response_model)` has no timeout parameter, and `AsyncCodex._client` is private (api.py:317). *source:* S0 §4 C3–C4.
- **Operations with no high-level wrapper in openai-codex 0.162.1:**
  - `thread/fork` takes `last_turn_id` (fork through that turn, inclusive; it must not be running) and a bool `exclude_turns` (v2_all.py:9859-9904), but `AsyncCodex.thread_fork` exposes neither. `CodexForkSettings` is an agent-fork record with no turn id.
  - `token_budget` exists only in the raw `ThreadGoalSetParams` (v2_all.py:9938). An active goal starts its own turn on an idle, persisted thread and blocks `_start_turn` (client.py:549-671).
  - Also without a wrapper: rate limits, sandbox readiness, `review/start`, `approvalsReviewer` user/guardian, and `disabledPluginIds`.
  *source:* S0.
- **The message router drops events for a turn with no subscriber** (_message_router.py:196-206). Only `_start_turn` pre-registers, so a `review/start` handle created later can miss `turn/completed` and hang. Each handle's stream can be read only once. *source:* S0.
- **`codex_bin`:** the empty default means the bundled binary, and a set value must be an existing path (client.py:176-186). The PATH `codex` is an npm launcher whose package metadata says 0.162.1, not request.md's 0.161.0 (not executed). The Windows precedent resolves launchers with `shutil.which` (tools/mcp/transport.py:197-201). *source:* S0.
- **Settings and failure codes:**
  - The existing settings carry only `approval_mode` ("", auto_review, deny_all). `developer_instructions`, `approvals_reviewer`, `disabled_plugin_ids` and `name` are new fields, and `ThreadStartParams` has no `name`.
  - New `CODEX_*` codes go after failure.py:46, each with a classification row in `vidbyte/lib/constants/codex.py:95-174`. A test enforces the rows.
  *source:* S0.
- **Permissions are not enforced everywhere:**
  - openai-codex auto-accepts command and file-change approvals by default (client.py:833-839).
  - The MCP tool registry runs tools without a `PermissionPolicy` check (mcp_server/handlers.py:88).
  - `BaseAgent` gives each agent its own tool copy only for classes in explicit lists (agents/base.py:421-482). `agents/base.py` is shared with the ClaudeHost PR, so any edit there must be minimal and append-only.
  *source:* S0.
- **Design (spec r1, approach B).**
  - `CodexHost`, in `vidbyte.harnesses.native.codex`, is an async context manager that owns one Codex app-server.
  - It calls openai-codex's public sync `CodexClient` through `asyncio.wait_for(asyncio.to_thread(...), CODEX_HOST_REQUEST_TIMEOUT_SECONDS=300)`.
  - Typed client methods carry the full params.
  - Five raw calls go through `request_with_retry_on_overload`. The two that spend money (`review/start`, the goal budget set) get a single attempt (`CODEX_HOST_SINGLE_ATTEMPT`).
  - Runner-up A (AsyncCodex plus the private `_client`) was rejected: it uses a private attribute, and its raw `request` fails S012.
  - Budget: 17 new files, 30 classes, 15 records, 13 enums, 0 dependencies, 0 root exports.
  *source:* S1 author.
- **Contract names:**
  - `CodexHost`, `CodexToolScope`, `CodexHostTools`;
  - `CodexTurnSnapshot` (not `CodexTurnOutcome`, which already exists);
  - `CodexTurnStatus.RUNNING = "inProgress"`;
  - new failure codes directly after `CODEX_RUN_OPTION_UNSUPPORTED`.
  *source:* S1 author.
- **Test seam.** Patch the module attribute `vidbyte.harnesses.native.codex.connection.CodexClient` before entering the host; it is imported lazily in `__aenter__`. Also patch `shutil.which` and `sys.platform`. The fake needs no `request` or `model_list`, and the five raw calls go through `request_with_retry_on_overload`, keyed by method name. *source:* S1 author.
- **S012 matches any call to a name `request`, bare or as a method.** Passing `client.request` uncalled to `to_thread` is forbidden too. A002 `# @intent` comes next: it applies to identifiers containing request, retry, attempt, fallback, provider and similar words. *source:* S1 author.
- **The S1 author's least-sure assumptions:**
  - A-1: the Windows npm `.cmd` launcher works and stops at close.
  - A-2: a goal can start before the first turn.
  - A-3: usage totals are cumulative.
  - A-6: setting only the budget leaves the goal alone.
  - A-7: approvals arrive only when the reviewer is `user`.
  - A-12: the version reported at `initialize` can be parsed.
  Q-1 to Q-9 all have defaults:
  - Q-1: no split of the 1,205-line dataclass module.
  - Q-2: minimum CLI version 0.151.0.
  - Q-3: accept approvals.
  - Q-4: no root exports.
  - Q-5: refusal cap, default `None`.
  *source:* S1 author.
- **Line endings.** `core.autocrlf=true` is set and there is no root `.gitattributes`, so working copies are CRLF. Hash `native/__init__.py` from the blob (`git show HEAD:<path>` or `git cat-file -p :<path>`): the LF blob hash is `0374a2c8…`, and the CRLF working-copy hash is `fbf12a15…`. *source:* S1 reviewer R-8.
- **S054 (ruff S105, zero headroom: baseline 3, current 3).** S105 flags a string literal assigned to, or compared with, any name, attribute or subscript key with an `_`-separated segment `token`, `secret`, `pass`, `pwd` or `password`.
  - Safe: `tokens`, `tokenBudget`, `CODEX_USAGE_UPDATED_NOTIFICATION`.
  - Unsafe: `GOAL_TOKEN_BUDGET_DESCRIPTION`.
  - The three existing findings are `token_budget.py:28`, `compaction/base.py:28` and `workflows/contracts.py:73`.
  *source:* S1 reviewer R-1.
- **One reader thread.** openai-codex's `_reader_loop` (`client.py:863-881`) answers server requests synchronously on its single reader thread, so a slow dynamic tool stalls every notification and response on that app-server for up to 300 s. *source:* S1 reviewer R-3.
- **Closing on Windows.** `shutil.which("codex")` finds the npm `codex.cmd`. The chain is cmd.exe, then node `codex.js`, then `codex.exe` with stdio inherited. `CodexClient.close()` terminates cmd.exe only (`client.py:291-297`, plain Popen, no job object). *source:* S1 reviewer R-4.
- **Not public API.**
  - `CodexClient` is not in `openai_codex.__all__`; only `CodexConfig` is imported from `.client`.
  - Goal operations return the private `_GoalOperationState`.
  - The SDK's `ApprovalMode` offers only `deny_all` and `auto_review`, and 0.162.1 has no decline decision value.
  *source:* S1 reviewer.
- **Tool-call timeout.** `CodexToolCallHandler.handle` returns "Tool call timed out after 300 seconds." at `CODEX_TOOL_CALL_TIMEOUT_SECONDS`. `ToolExecutor` has no timeout of its own, so the wait tool's clamp must stay below 300 s. *source:* S1 reviewer R-7.
- **Precedent for a dedicated executor:** `openai_codex/async_client.py:53-54` uses `_TURN_START_EXECUTOR = ThreadPoolExecutor(...)`, and its cancelled-start cleanup runs on daemon threads (:258-261, :283-286). *source:* S1 reviewer R-6.
- **Stale and checked facts.**
  - The installed binary reports `codex-cli 0.162.1`; request.md's "0.161.0" is stale.
  - No test enumerates `ComponentRegistry`.
  - No lint rule caps file length.
  *source:* S1 reviewer.
- **Contract import paths (spec r2).** New records come from `vidbyte.lib.dataclasses.codex_host`. Settings records and helpers still come from `vidbyte.lib.dataclasses.codex`, which is not edited.
  - The new module's `__all__` is a list literal. Copying `codex.py`'s `Codex*` comprehension would re-export the imported records.
  - ruff `F` (unused imports) is in the lint selectors, so `codex_host.py` must not import `CodexClientSettings`.
  *source:* S1 author r2.
- **Executor and close constants.**
  - Host calls run on a host-owned executor, `CODEX_HOST_WORKER_THREADS=32`; there is no `to_thread`.
  - `close()` runs on a daemon thread, with 5 s and 10 s bounds.
  - The wait clamp is 240 s, below the 300 s tool-call cancel bound.
  - The connection module reads the request-timeout and close constants at call time, and the worker count when it builds the executor.
  *source:* S1 author r2.
- **Close order (INV-7):** finalize the turns, send each a single bounded interrupt, close the client on a daemon thread, then shut the executor down. *source:* S1 author r2.
- **A PowerShell trap.** Windows PowerShell 5.1 changes bytes piped between programs, so the `git cat-file | python` form prints a wrong hash there. The §11 hash command uses a Python `subprocess` form, which gives the same hash in both shells. *source:* S1 author r2 (verified).
- **Reviewer fields.**
  - Every `thread/start`, `thread/resume` and `thread/fork` response carries required `approvalsReviewer` and `approvalPolicy` fields (`v2_all.py:12458`, `:12363`, `:12288`).
  - Resume and `turn/start` accept a reviewer override (`:5987`, `:12544`).
  - When none is sent, the thread takes Codex's configured default (`:10782`).
  - The SDK never sends a policy that routes approvals to the client (`_approval_mode.py:28-35`).
  *source:* S1 reviewer r2.
- **Close and goal-watcher facts.**
  - The sibling `CodexTransport` cancels pending tool calls before closing (`transport.py:198-213`, `CodexToolCallHandler.close()`).
  - A goal state's `next_notification()` is a bare `Queue.get()`, woken only by a routed notification or by `fail_all` on a still-registered state.
  - The SDK cleans up a cancelled goal as cancel, then `finish()`, then `unregister_goal_operation` (`client.py:643-648`).
  - Executor workers are non-daemon and joined at exit. `shutdown(cancel_futures=True)` cancels only queued calls, and `submit` after shutdown raises `RuntimeError`.
  *source:* S1 reviewer r2.
- **`TransportClosedError` embeds the stderr tail** (`client.py:907-910`), so a mapped error is always raised `from None` (see also S017). *source:* S1 reviewer r2.
- **Error type.** `FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION` exists but nothing uses it, and `ConfigurationError` has no code field. The R-5 rejection must therefore carry the code through the spec's own error type. *source:* S1 reviewer r2, R-5.
- **Measured facts.**
  - The vidbyte MCP server applies no tool timeout, so the 240 s wait clamp is the only server-side bound.
  - The §11 hash command works in Git Bash and in PowerShell 5.1.
  - The `agents-md-placement.yml` workflow runs only by hand, and running it could move the `codex_host.py` records into `codex.py`.
  *source:* S1 reviewer r2.
- **Goal stream close (spec r3).** `_GoalStreamClosed` is an `Exception`. After `wake_notification_reader()`, a blocked `next_goal_notification` raises it; unregistering alone never wakes the reader. The SDK uses two cleanup orders:
  - after a failed start: cancel, `finish`, unregister;
  - when a stream closes: `finish`, wake, unregister.
  *source:* S1 author r3.
- **The six-step close (INV-7, r3):**
  1. close the tool handlers;
  2. finalize the turns, keeping goal runs registered;
  3. send interrupts;
  4. close each goal stream;
  5. close the app-server thread;
  6. shut down the executor.
  `CodexConnection` owns the shielded, bounded await and calls `future.cancel()` first on cancel or timeout. INV-6 refuses new calls once close begins. *source:* S1 author r3.
- **Test fakes (r3).** Fake start and resume responses must report `auto_review` (or the policy `never`) for turns to start (D-32). The fake goal state needs `finish()` and `wake_notification_reader()`. The `Thread` returned by `thread/read` has no reviewer fields. *source:* S1 author r3.
- **The USER rejection** is `CodexAgentError` with `configuration.unsupported_combination`, the next step `CODEX_HOST_USER_REVIEWER_TEXT`, and operation `CodexHostOperation.VALIDATE_SPAWN_REQUEST` at construction. `configuration.unsupported_combination` needs no row in `CODEX_FAILURE_CLASSIFICATION`; the coverage test checks only `codex.*` codes. *source:* S1 author r3.
- **S017's scan does not cover `vidbyte/harnesses/`.** The no-`str(exc)` and `from None` rule there is enforced only by review. *source:* S1 author r3.
- **The test layer (spec r3 §13).**
  - The pack is `tests/features/codex_host/`, with no `__init__.py`, plus a `FEATURE.md` ("High-Level Feature Description" and "Contract").
  - Prior art is `tests/test_codex_tools.py:640-680`, with SDK contract tests under `skipUnless(find_spec("openai_codex"))`, and the layout of `tests/features/coding_agent/`.
  - AC-2 import safety runs in a fresh `sys.executable -I` subprocess with `sys.modules["openai_codex"] = None`.
  - Run one file with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_<topic>.py`.
  *source:* spec r3 §13.
- **openai_codex must load lazily.** Nothing reachable from `import vidbyte`, or from `vidbyte.tools.builtins` (which the YAML component registry scans), may import openai_codex at module level. The precedent is `CodexTransport._load_sdk` (transport.py:215-259). CI installs only `.[dev]`, so SDK-dependent tests skip there (`skipUnless`). The global Python 3.11 has openai-codex 0.162.1. *source:* S0.
- **S2 seam, from the test author.**
  - Tests patch `vidbyte.harnesses.native.codex.connection.CodexClient` with a subclass of the real openai-codex client.
  - `connection.py` binds `CodexClient` and `CodexConfig` at module level, and only the host's open may import `connection`, or the AC-2 probe fails.
  *source:* S2 test author.
- **Values the tests patch in the connection module's namespace.** Read every one at call time, not import time.
  - `CODEX_HOST_WORKER_THREADS`, read at open; set to 1 as an ordering barrier.
  - `CODEX_HOST_REQUEST_TIMEOUT_SECONDS`, set to 0.3.
  - `CODEX_HOST_CLOSE_INTERRUPT_SECONDS`, set to 60.
  - `shutil.which` and `sys.platform`, patched on their modules.
  *source:* S2 test author.
- **Threads.** Requests run only on the host's own workers, never on `MainThread` or on a thread named `asyncio_*`. `client.close()` runs on a daemon thread. The goal watcher reads through `client.next_goal_notification(state)`. *source:* S2 test author.
- **Goal cleanup order:**
  - start failure: cancel, finish, unregister;
  - finished run: finish, wake, unregister;
  - close: cancel, finish, wake, unregister.
  *source:* S2 test author.
- **Errors.** Raise every mapped error `from None`, because the privacy tests scan the visible exception chain. *source:* S2 test author.
- **Messages the tests check:**
  - `model_unknown` lists `gpt-5.5` and `gpt-5.5-codex-latest`;
  - a launch that fails partway says a standalone `2`;
  - the user-reviewer refusal, the request-bound `api_error` and the close-wins `process_exited` each name the thread id.
  *source:* S2 test author.
- **The test most likely to catch a real bug** is `test_codex_host_turns.py::test_the_output_cap_counts_only_the_turns_own_tokens_and_interrupts_once`. Codex's `total` usage counts the whole thread, so a cap compared against it interrupts every continued turn. *source:* S2 test author.
- **CI coverage.** 66 of the 101 tests are gated on openai-codex and skip in CI, which installs `.[dev]` only. S3–S5 must run the pack in the `[dev,codex]` venv `C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host` (openai-codex 0.162.1). The CI view, run with `sys.modules['openai_codex']=None`, must show 66 skipped and 0 failed. *source:* S2 test author.
- **r4 pins.**
  - D-33: handles are owned by value. A `CodexTurnHandle` rebuilt from ids equals the returned one.
  - D-34: `limit_reached` comes from `GetAccountRateLimitsResponse.rate_limits.rate_limit_reached_type`, which is optional, or `""`.
  - D-35: a late-acceptance interrupt records no stop reason, so the turn ends INTERRUPTED with `problem=None`, and a later timeout or cap adds no label and sends no second interrupt.
  *source:* spec r4.
- **No budget headroom.** The §8.4 budget is used exactly: 18 files, 18 modules, 30 classes, 15 records, 13 enums and 0 dependencies. Any S4/S5 fix that adds a class, record, file or enum goes over it, and needs a spec revision or a deviation. *source:* S3 implementer.
- **Run the ruff I001 fixer on explicit file paths only.** Run on a directory, it rewraps imports in untouched files; it hit `toolsets/paradigm_minimal.py`. *source:* S3 implementer.
- **IMPROVED is not a reason to lower the baseline.** The lint prints IMPROVED for A002 (703→607), C012, S001, S010 and S025. The baseline stays untouched (request.md §C). *source:* S3 implementer.
- **Comparing the shared texts.** Working copies are CRLF and blobs are LF. Compare the REPO_MAP and README fixed texts against `git show HEAD:<path>`. *source:* S3 implementer.
- **The tool cap check.** `CodexToolScope.reserve` refreshes the live handles through `get_codex_turn_result`, which only reads locally, then checks and reserves with no await in between (INV-32). Cancellation frees the slot in the callers' `finally`. *source:* S3 implementer.
- **Running the pack from outside the worktree.** Use `PYTHONPATH=$W $PY -P -m pytest $W/tests/features/codex_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml`. Without `-P` and `--rootdir`, the cwd's `tests` package shadows `tests.features.codex_host`. *source:* orchestrator.
- **Drift from main.** The branch is 41 commits behind origin/main (8387d666), and `git merge-tree` is clean. In this area main touched only `vidbyte/harnesses/stores/file.py`. Catch up by merge, never rebase, in S5. *source:* S3 implementer.
- **The probe harness.**
  - Probes are inline `PYTHONPATH=$W $PY -P -` heredocs that subclass `tests.features.codex_host.codex_host_support.HostTestCase`. They use `server.hold(method, predicate)`, then `hold.wait_arrived`/`release` and `self.count(method)`.
  - The fake server scripts errors with `server.fail(method, FakeRpcError(code, msg), times=, predicate=)`.
  - `_stop` sends interrupts in the background. Count them after `asyncio.to_thread(server.wait_for, "turn/interrupt", None, n)`.
  *source:* S4 reviewers and verifier.
- **Reproducing R-10.** Release the hold only after the second `thread/resume`. openai-codex queues a second `turn/start` behind a held first one, so awaiting a second continue deadlocks. *source:* verifier.
- **Fix order and interactions.**
  - R-1 goes before R-4, because both edit `_accept_review`.
  - R-2 goes before or with R-6. Otherwise R-6's BaseException path re-raises without INV-37's "k turns" text.
  - R-6 and R-14 both touch launch slots. R-16 and R-24/M5 share host.py:385.
  - R-3 and R-11 both edit lib/constants/codex.py, so append to the end of `__all__`.
  *source:* verifier.
- **Comment passes, in order.** First R-4's header, then R-9's and R-21's intent blocks, then R-5's 72-column rewrap last. Keep `# @intent` first, inside the A002 window. Most over-wide lines were wrapped at 72 counted from the `#`, not from column 1. *source:* verifier and S4 conventions.
- **R-8's in-budget fix.** `_reject_small_int` and `_reject_bad_seconds` in codex_host.py guard a variable named `value`, which C002 skips. They can replace the evasion shapes at host.py:346 and :495. *source:* S4 conventions.
- **Do not change OutputSchemaFormatter.** It is shared with CodexHarnessAgent (NG-5). *source:* verifier.
- **R-6's hidden lint findings.** The gate's "A002 IMPROVED 703 -> 607" line hides this PR's seven new A002 findings. See them with `lint/run.py --all --format json`, filtered by path. C011 is now at its baseline of 2, with no slack. *source:* S4 conventions.
- **`PydanticUserError` subclasses RuntimeError, not TypeError,** so R-2's check catches it by name. *source:* S5 repair 1.
- **Counting the branch's own lines after the main merge.** Two-dot `git diff origin/main -- vidbyte` shows main's newer lines as `+`. Count the branch's own lines against `git merge-base origin/main HEAD`. *source:* S5 repair 1.
- **`W=$(pwd)` in Git Bash gives `/c/...`,** which breaks paths inside `python -c` strings. Use the `C:/...` form. *source:* S5 repair 1.
- **Holding on a request count.** Fake hold predicates run under the fake's lock, but `server.matching()` takes no lock, so a hold can be keyed on a request count. *source:* S5 repair 1.
- **Accepted R-1 residual.** A review that finished before registration, and whose caller is also cancelled during the read-back, stays RUNNING until close. The S4 verifier accepted this. *source:* S5 repair 1.
- **Reproducing R-27.** Run `VARIANT=current PYTHONPATH="$W;$S" $PY -P -m unittest probe_rc1` with `S=.../scratchpad/codex-verifier-r1`.
  - The current code sends 1 interrupt in cases A–C, and the turn stays inProgress.
  - `VARIANT=pending` (recommended) sends 2 in A–C and 1 in D–E, which keeps R-16.
  - `VARIANT=revert` sends 2 in A–E, so R-16 regresses.
  - All three keep the pack at 111/111.
  *source:* scoped verifier r1.
- **R-27's fix shape.**
  - Add `self.stop_pending = False` at turns.py:87.
  - Add an async `CodexLiveTurn.send_stop(connection, operation, *, quiet=False)` that clears the flag in a `finally`; `stop()` sets the flag and spawns it.
  - host.py:407 returns on `snapshot is not None or stop_pending`.
  - Leave `over_cap()` and `stop()`'s `stop_sent` check untouched (D-7, EC-30).
  - `send_stop` needs a `# @intent` line within 20 lines (A002).
  - Regression test B (the timeout interrupt fails, then the user interrupts) expects INTERRUPTED with `codex.turn_timed_out` (EC-27). Test A expects problem None.
  *source:* scoped verifier r1.
- **R-26's fix.** `raise ConfigurationError(f"{UNUSABLE_SCHEMA_MESSAGE} Got {type(exc).__name__}.") from None`. Add `assertIsNone(caught.exception.__cause__)` in the new test; the mapping case fails it today. The probe is `$S/probe_rc2.py`. *source:* scoped verifier r1.
- **R-24 (M5, open follow-up) shares the `interrupt_codex_turn` lines with R-27.** Keep `turn.stop_sent = True` on the user path. *source:* scoped verifier r1.
- **Running mutants in memory.** `scratchpad/codex-repair2/mutant_run.py <mutant> <TestClass>` runs one mutant: text_kept, no_recursion, revert_guard or pending_sticks. *source:* S5 repair 2.
- **Schema cycles fail two ways.** A cycle at a key the formatter skips (`schema["self"]`) fails as ValueError; one under `properties` or `items` fails as RecursionError. *source:* S5 repair 2.
- **Set the flag before the spawn.** `stop()` must set `stop_pending` before it spawns `send_stop`, because a spawned task's first step runs one loop iteration later. *source:* S5 repair 2.
- **The A002 text output hides per-file findings when the verdict is IMPROVED.** Always confirm "A002 clean under the branch's paths" with `lint/run.py --rule A002 --all --format json`, filtered by path. *source:* re-review r2 and verifier r2.
- **Do not rename `send_stop` or reshape the call to hide the `send` token.** That would repeat R-8's Major, dodging a lint rule. *source:* verifier r2.
