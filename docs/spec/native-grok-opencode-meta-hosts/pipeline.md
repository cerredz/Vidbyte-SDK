---
slug: native-grok-opencode-meta-hosts
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-grok-opencode-meta-hosts
branch: feat/native-grok-opencode-meta-hosts
base_commit: aa8c380c4cd1d5791526dd545f5ef1020b28a5cc
s3_head: de5b7c4c
s2_head: 96df0b45 (cfad74f8 → a716c858 [D-1..D-3] → 762b68e7 [r5 catalog row] → 91e874b2 [D-4..D-6] → 96df0b45 [S4 regression tests, r8] → 5ce6e85d [re-review R-16/R-17 tests])
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1036
until: none
started: 2026-10-13 01:30 UTC
---

# Pipeline: GrokHost, OpencodeHost, MuseHost (Meta Muse Code), and GLM / DeepSeek backend profiles, with exhaustive error handling

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-13 01:30 UTC | 2026-10-13 02:20 UTC | reports/S0-scout.md | base_commit aa8c380c; code-map.md, 4 sections, 21 notes |
| S1 spec + review | done | 2026-10-13 02:22 UTC | 2026-10-13 05:40 UTC | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-r2.md | spec r3 @f1b2fa31 approved; r1 review SOUND WITH FIXES (15/15 accepted), r2 review SOUND WITH FIXES (11/11 accepted) |
| S2 tests | done | 2026-10-13 05:50 UTC | 2026-10-13 07:35 UTC | reports/S2-test-author.md | 1635 tests (grok 458, opencode 581, muse 458, backends 138), all red; S2_HEAD cfad74f8 |
| S3 implement | done | 2026-10-13 08:20 UTC | 2026-10-13 13:40 UTC | reports/S3-implementer.md | S3_HEAD de5b7c4c; draft PR #1036; 51 commits; budget 56/56 create, 12/12 modify, 66/66 records, 13/13 enums, 53/53 codes; 1616 passed, 19 skipped (re-run by orchestrator); full gate + Semgrep green; ci.yml 38379243965 dispatched, static-policy 38379248609 success |
| S4 adversarial review | done | 2026-10-13 13:50 UTC | 2026-10-13 15:10 UTC | reports/S4-review-{conformance,conventions,engineering}.md, S4-findings-verifier.md | review.md: NEEDS REWORK; confirmed 2 Blocker (R-1, R-2) / 11 Major (R-3..R-15) / 9 Minor (R-M1..R-M9); refuted 0; downgraded 3 (R-V1→Major, R-V2→Major, R-V3→Minor); CI-1 reclassified by orchestrator as a code defect |
| S5 repair loop | done | 2026-10-13 16:45 UTC | 2026-10-13 23:05 UTC | reports/S5-repair-{1,2,3}.md, verify-log.md | converged in 3/8; all 13 confirmed Blocker/Major + CI-1 + R-M1/R-M6 fixed; code HEAD af3e05e8; remote ci 38418651864 + static-policy 38418656187 green |
| S5 re-review | running (round 1 done) | 2026-10-13 23:10 UTC | | reports/S5-rereview.md | round 1: MERGEABLE AFTER FIXES; fixes confirmed 21/21; new 0 Blocker / 3 Major (R-RR1..R-RR3) / 1 Minor (R-RR4) → scoped verifier |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 (round 2 focused on the r2 changes)
- S5 repair iterations: 3/8 (converged)
- S5 re-review rounds: 1/2 (launched)

## Decisions the orchestrator made

- **2026-10-13 01:30 — Scope is the catalog's ★ set for each target, plus `build_opencode_backend_provider`.**
  - Why: Prompt 2's "for now" applied the same way as the upstream Codex first PR. The added function is the only runnable GLM/DeepSeek route while ClaudeHost is unmerged.
  - Recorded as request.md Q-1, default ★ only.
- **2026-10-13 01:30 — GrokHost's ACP code is protocol-generic but not a public `AcpHost`.**
  - Why: Prompt 2 narrows to five targets, and the upstream ledger rejects a base class that has only one implementation.
- **2026-10-13 01:30 — This PR follows the codex-host/claude-host shared-file contract.**
  - `native/__init__.py` must have SHA-256 `0374a2c8…497a`.
  - Tests go only in host-named folders.
  - Export indexes are edited append-only.
  - `pyproject.toml` stays unchanged unless Q-2 is resolved with evidence.
  - Why: three PRs create `vidbyte/harnesses/native/` in parallel.
- **2026-10-13 02:20 — Muse transport wording.** request.md §C quotes the catalog verbatim, so it still says "Talks MSP through `muse-code-sdk`" (request.md:598). That line is the catalog's description, not a decision. Q-2 (default: no new dependency) governs how Muse is reached.
  - Why: the scout flagged the two lines as conflicting (code-map §4.11).

- 2026-10-13 03:50 — S1 review r1 (SOUND WITH FIXES; 2 Blocker, 9 Major, 4 Minor) was passed to the author by path instead of pasted. The report file holds the findings verbatim (reports/S1-spec-review.md:23-219). Why: the findings are 25 KB and the author can read files, which keeps the orchestrator's context small.
- 2026-10-13 03:50 — The author was told the in-distro WSL kill (R-4) is the orchestrator's request.md Q-8 default, not a user decision. Downgrading it needs evidence beyond idle-only runs. Why: the user asked for "extensively handle errors for every single function", and an orphaned Muse process could keep editing files.

- 2026-10-13 05:10 — Bootstrap: no `pip install -e` from this worktree. The global Python 3.11.0 has `vidbyte-sdk` 0.2.1 installed editable from the canonical checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk`, and its dev tools are already there (pytest 8.3.5, pytest-asyncio 1.3.0, ruff 0.16.4, mypy 2.3.1). Re-pointing that install would break the parallel codex-host and claude-host pipelines and the main checkout. Every stage runs with `PYTHONPATH=<worktree>` instead, as the field guide's `local-ci-verification.md` says. Why: the editable install is shared state across every pipeline.
- 2026-10-13 05:40 — Spec Q-14, Q-15, Q-17, Q-18 and Q-19 take their stated defaults (no / not built). Request Q-1..Q-13 were resolved in spec §8.1; Q-16 was resolved by building D-23. Why: S1 rule, no planned stop.
- 2026-10-13 07:35 — S2_HEAD = cfad74f8 (tests at e8289019; spec proof column and S2 report at cfad74f8). Later stages diff `tests/` against this SHA. I re-ran the red proof: `native_backends` 138 errors; `grok_host` 89 failed, 13 skipped, 356 errors.
- 2026-10-13 07:35 — S2's 14 spec ambiguities go to the spec author for r4, before S3. The spec must state each reading the tests took. Any reading the author thinks is wrong comes back to me and goes to the test author. Why: the skill says to resolve spec defects before S3, and the tests are the contract.
- 2026-10-13 08:05 — Spec r4 (1f97640b, `status: tests-written`) states the reading the tests took for each of S2's 14 ambiguities, plus S2-15. Nothing was routed back to the test author. The transport's dispatch fix is now named as INV-18's one exception: a server request whose `id` collides with a pending client request is dropped instead of failing that request.
- 2026-10-13 08:05 — The test author was asked to merge its §6.2 Proof values (put in a 7th cell) into the 6-column table. Why: the spec should render correctly on GitHub, and the test author owns that column.
- 2026-10-13 08:55 — S3 reported BLOCKED after P1 on three S2 test defects. I decided them myself, because the spec already answers all three:
  - D-1: a test expected a plain `set` of enum members to be rejected. Spec §9.1, EC-23, EC-134 and §16 S2-4 say a set is accepted.
  - D-2 and D-3: test helpers passed `argv` / `workspace` twice, causing a `TypeError` before any SDK code ran.

  The S2 test author fixed them at 66d5c3bb (3 files, 4+/4−). I checked the diff `git diff cfad74f8..HEAD -- tests/`: exactly those 3 files. S2_HEAD moves to a716c858; later test-tree diffs use this base. I ran the fix and S3's resume one after the other, not in parallel, because both agents commit in the same worktree.
- 2026-10-13 08:55 — The S2 author reports `lint/run.py` SDK-LINT: FAIL. Rule A007 has 263 findings against an allowance of 255, caused by P1 code: `lib/dataclasses/grok.py` 4, `lib/process/runner.py` 4, `lib/process/managed.py` 2. S3 had reported PASS. This was handed to S3 to fix at the source.
- 2026-10-13 09:40 — S3 reported BLOCKED a second time, at the start of P3: in spec §6.3.1, `muse.budget_exhausted`'s exact next-step text did not contain its own required token `continue_muse_session`. I took the implementer's option 1 and put the token into the text, which matches every other row, where the token names the function to call. The fix went in three steps: spec r5 (254ebc53), a one-line change to the test CATALOG row (762b68e7, verified 1 file, 1+/1−), then resuming S3 to update `NATIVE_HOST_NEXT_STEPS`. S2_HEAD moves to 762b68e7.
- 2026-10-13 12:10 — S3 reported BLOCKED a third time, after building all 68 rows. I ruled on four items:
  - D-4: the test's argv guard contradicted itself. The fix makes it match the approve-everything flag only as a whole argv element or as a `--flag=` prefix. Prompt text inside `--single=` is data.
  - D-5: a flaky fixture ordered peer logs by PID. It now uses an atomic launch counter.
  - D-6: wrong expected opencode ids. The fake was right.

  The test author fixed all three at 209c4085 (9 test files, +47/−16; I checked the diff against 762b68e7). Two runs gave 1 failed and 1615 passed; the one failure is the EC-95 test. S2_HEAD moves to 91e874b2.
- 2026-10-13 12:10 — EC-95 (exit code 127 means `muse.not_installed`) needed an exit code that §8.5 did not expose. I approved S3's option 1: spec r6 (f4659a58) adds read-only `McpStdioTransport.returncode` and `NativePeer.exit_code`. The spec author also raised D-3's reversal trigger from about 160 to about 200 changed lines, because the extension now has about 167. I accepted that, but flagged transport size for S4 reviewers to judge independently. Why: the spec row explicitly asks for exit 127, and the 9-line change is already tested.
- 2026-10-13 12:10 — The harness flagged the S2 author's status message as instruction-shaped ("bypass-permissions"). It only described the test guard rejecting the vendor value `bypassPermissions`. Not an injection; no action taken.
- 2026-10-13 14:00 — Remote `ci.yml` run 38379243965 on 9d51a3fb ended `failure`. Source / Python 3.11 passed; Source / Python 3.12 failed with 1 failed, 5572 passed, 31 skipped. The failing test is `tests/features/grok_host/test_grok_host_turns.py::test_interrupt_raises_process_exited_when_the_cancel_write_fails` (EC-51, `@posix_only`, so it skips on Windows): `DID NOT RAISE NativeHostError` at line 335. The log is saved at scratchpad `ci-38379243965-failed.log`. I re-ran the failed job (`gh run rerun --failed`) to tell a flaky test from a defect that depends on the Python version. Either way it goes to the S4 verifier as an item to adjudicate, and S5 must make remote CI green. Why: a Linux-only path (closed-stdin write detection under asyncio 3.12) never ran locally.
- 2026-10-13 14:25 — The re-run of run 38379243965 (attempt 2) failed the same way: Python 3.12 failed only `test_interrupt_raises_process_exited_when_the_cancel_write_fails`; 3.11 passed. Two identical results mean this is not a flaky test. It is deterministic and depends on the Python version. It goes to the S4 verifier as item CI-1 with its log paths, and S5 has to turn it green. It sits in the same area as R-C2: the transport's `stdin.drain()` bound at `transport.py:303`.
- 2026-10-13 15:15 — **CI-1: I overruled the verifier. It is a code defect, not a test defect, and the test stays as written.** The verifier called the EC-51 fixture fragile across Python versions. EC-51 (spec:512) needs one thing: when the `session/cancel` write fails, interrupt raises `grok.process_exited`. The fixture makes that write genuinely fail: the fake closes its stdin, and the kernel returns EPIPE, the same broken pipe an exited peer gives. So the test does not contradict any spec ID, and the default answer for a test change is no.
  - Likely mechanism, from CPython asyncio and not from reading repo code; the S5 agent must verify it. On EPIPE, `_UnixWritePipeTransport.write` calls `_fatal_error`, which marks the transport closing and schedules `_call_connection_lost`. That reaches `SubprocessStreamProtocol.pipe_connection_lost` only through a second `call_soon` hop, via `WriteSubprocessPipeProto` and `_pipe_connection_lost`. `drain()` yields once (`sleep(0)`) and then sees `_connection_lost` still False, so it returns normally and the broken pipe is swallowed.
  - On 3.11, `asyncio.wait_for` wrapped `drain()` in a Task, which adds the missing loop iteration. On 3.12, `wait_for` awaits inline. So production on 3.12 would also miss a dead peer on this path.
  - Candidate fix, the agent's to choose: check `stdin.is_closing()` (the transport sets `_closing` synchronously inside `write()` on EPIPE) after the write and drain on the new write paths, and map it to the same closed-pipe error.
  - The `Tests to add` row for CI-1 in review.md is void.
- 2026-10-13 15:15 — **R-3: I chose Option A.** On the default path (`timeout_seconds is None`) keep the plain unbounded `await drain()`, and bound only an explicit per-call deadline. Why: INV-18 stays as approved and the spec needs no edit. The fix must keep CI-1's closed-pipe detection on whatever path `session/cancel` takes.
- 2026-10-13 15:15 — **R-2 needs a spec rule before tests and repair: spec r8.** The rule: on win32, never start a batch launcher (`.cmd`/`.bat`) whose argv carries caller-supplied values. Resolution skips it, prefers `~/.grok/bin/grok.exe`, and otherwise raises `grok.not_installed`. The spec author must also audit every opencode and Muse CLI launch for the same exposure, and adjust AC-1's Windows clause.
  - Also folded into r8, docs-only: R-M2 (record `OpencodeHost.mcp_servers` in §17 as deviation 9) and R-M3 (correct deviation 7's reason).
  - Order: spec r8, then an S2 test addendum (R-1, R-2, R-5, R-6, R-7, R-8 regression tests, proven red), then S5 iteration 1. Why: test-first, and repair agents may not write tests.
- 2026-10-13 15:15 — I chose not to use the `Ubuntu` WSL2 distro on this machine as a Linux 3.12 reproducer. Why: it is the user's environment and would need packages installed. Remote CI (`ci.yml`, matrix 3.11 and 3.12) is the Linux reproducer for CI-1.
- 2026-10-13 15:15 — Spec `status: reviewed`, set by an orchestrator docs commit as S4 prescribes.
- 2026-10-13 15:55 — **Spec r8**, written in revision mode by a fresh spec author: e377b7c2 for R-2, R-M2 and R-M3, then fadd6b81 for EC-39. The status stays `reviewed`.
  - **R-2:** D-19 plus a new EC-157. On win32, Grok never starts a `.cmd` or `.bat` launcher, whether found on PATH or set explicitly. A shim found on PATH falls back to `~/.grok/bin/grok.exe`; otherwise `__aenter__` raises `grok.not_installed` with the EC-157 next step. AC-1's win32 branch moves to the §13 seam.
  - **Audit:** opencode and Muse put no caller value on argv, so their launchers are unchanged (§10 T-2).
  - **Counts unchanged:** 53 codes; §8.4 counts the same.
- 2026-10-13 15:55 — **EC-39 target clause, my decision; the spec author's open note asked for one.** I recorded the implementer's `!= target` fork check in EC-39 and listed it as §17 deviation 10, rather than dropping it. Why: dropping it would accept a paid fork that names the wrong session.
  - The r8 INV-14 change goes with it: Grok and Muse session ids are compared ignoring letter case (the busy check, EC-32, EC-35, EC-36, EC-39); opencode `ses…` ids are compared exactly.
- 2026-10-13 15:55 — **Next step: an S2 test addendum before S5 iteration 1.**
  - New regression tests for R-1, R-2/EC-157, R-5, R-6, R-7 and R-8 (case-insensitive ids, the EC-39 target clause), proven red against HEAD.
  - I granted one test change: AC-1's win32 branch moves to the `grok_command` seam, as spec r8 §14 says. Any other existing test whose assertion now contradicts r8 (EC-157, D-19, AC-1, EC-39, INV-14) may change only with its before and after recorded.
- 2026-10-13 16:40 — **S2 addendum done.** The tests are at 96df0b45 and the report at 9442dd0b.
  - 20 new regression tests are red for their stated reasons: R-1 ×5, R-2/EC-157 ×7, R-5 ×1, R-6 ×2, R-7 ×1, R-8 ×4. Two EC-39 lock tests are green.
  - Grant (a) was used: AC-1 on win32 now uses the `grok_command` seam.
  - My own re-run: `20 failed, 1618 passed, 19 skipped in 160.51s`. The test-tree diff from 900b1d62 is additions, except the 6 lines removed in `test_grok_host_acceptance.py` (grant a) and inventory lines in the FEATURE.md files.
  - Not written, both accepted: R-2 case (iii), the fallback to grok.exe, which needs a real `.exe` peer; and the R-8 EC-32 equality case, a near duplicate.
- 2026-10-13 16:40 — **I re-recorded the S2 addendum's two unpushed commits** (061580cd → 96df0b45, 44cc9677 → 9442dd0b). Their messages had stray `@` lines from PowerShell here-string syntax. I checked that the trees are byte-identical to the originals. Nothing published was rewritten.
- 2026-10-13 16:40 — **Spec r8 is complete** at cf6b0103. The test author found a gap for R-6, so the spec now has EC-158: an opencode turn the host fails itself first sends one `POST /session/{id}/abort`, bounded by `request_timeout_seconds` and dropped on failure. INV-13 gained a sentence, and EC-87 now says an uncounted poll failure ends the turn at once.
- 2026-10-13 16:40 — **origin/main moved 36 commits past base.**
  - The trial merge conflicts in `vidbyte/tools/mcp/transport.py`: main's 80400db5 (#1010, "send notifications/initialized after initialize", +34 lines) overlaps this branch's transport extension. `vidbyte/lib/configs/__init__.py` auto-merges.
  - Main also changed `tests/test_mcp_stdio_transport.py`.
  - Iteration 1 merges origin/main first (merge, never rebase) and only then fixes R-3 and CI-1 in that file.
- 2026-10-13 16:40 — **S5 plan, my scoping decision.** The 15 open findings split into three packets to protect each repair agent's context, and so the comment reflow runs once, last, over stable code:
  - **Iteration 1:** the merge, then the behaviour, security and conformance fixes (R-1, R-2, R-3 with CI-1, R-4, R-5, R-6, R-7, R-8), plus the trivial R-M1. Mark R-M2, R-M3 and R-M9 resolved by spec r8 and the S2 addendum.
  - **Iteration 2:** structure (R-9, R-10, R-11, R-12, R-M6).
  - **Iteration 3:** comments (R-13, R-14, R-15) in a single reflow pass.

  Each iteration's DONE means its packet is closed and every gate is green. Later packets are listed as deferred by me, not as open defects.
- 2026-10-13 19:10 — **S5 iteration 1 is DONE and verified by me.** HEAD is 406edb56 and the last code commit is d6733882.
  - **Commits:** the origin/main merge 3cdd9704 (no rebase; the one conflict, `notify` in transport.py, keeps both the timeout and main's frame without params); R-1 749b7583, R-2 137fa778, R-3 a9223a02, CI-1 eea8cf36, R-6 1e62494b, R-5 93c42f68, R-7 a4d74982, R-8 e70be132, R-4 54d5c17b, R-M1 87217940.
  - **My checks:**
    - the tree is clean;
    - the four packs are byte-identical to S2_HEAD 96df0b45; the only other test change (`tests/features/coding_agent/test_coding_agent_web_fetch.py`) is identical to origin/main and came with the merge;
    - every packet row in review.md reads `fixed @sha`;
    - remote `ci.yml` 38401581802 and `static-policy.yml` 38401585901 both succeeded on d6733882 (3.11 and 3.12 each `5646 passed, 39 skipped`);
    - my own `run_ci --stage source` gave `5653 passed, 32 skipped in 184.27s` / `CI passed.`;
    - INV-19's hash is intact.
  - **CI-1's root cause was confirmed in the CPython source** as I had predicted: a bare `drain()` returns normally after EPIPE on 3.12. The fix: a write that names a deadline raises if stdin is closing after drain. The default transport path stays as main's (INV-18).
- 2026-10-13 21:00 — **S5 iteration 2 is DONE and verified by me.** HEAD is 1717bb3b; the last code commit is 04be59fa. Commits: R-11 7f61f927 and 3c896557, R-9 616e8a0f, R-10 0f93301a, R-12 5a7e09de, R-M6 04be59fa.
  - **My checks:**
    - the tree is clean and in sync with origin;
    - the packs are byte-identical to S2_HEAD, and the other tests match origin/main;
    - the five rows read `fixed @sha`;
    - `ci.yml` 38409525140 and `static-policy.yml` 38409529932 passed on 04be59fa;
    - my own `run_ci --stage source` gave `5653 passed, 32 skipped in 180.96s` / `CI passed.`;
    - INV-19 holds, and origin/main has not moved since the iteration 1 merge.
  - **Behaviour changes, intended:** Muse and opencode approval titles are now cut at 200, the record's cap, instead of 128. Muse next steps lost their backticks.
  - **A deviation to state in S6:** `require_url` sits on `RecordFieldConverter`, not `RecordFieldValidator`, because a test pins the validator at 13 public methods.
  - The repair agent says 11 call chains remain and all are accepted: `build→scrub`, `_read_balance`, and the transport and FailureCode chains that predate this PR. The final re-review must check that judgement.
- 2026-10-13 23:05 — **S5 iteration 3 is DONE and verified by me; the loop has converged.** Commits: R-14 and R-15 f067088d plus 96705dfd, R-13 4f243bc9 plus af3e05e8. HEAD is b0e35a32, docs only after af3e05e8.
  - **My checks:**
    - I compared the AST myself: all 38 `.py` files changed since bae65c29 parse to the same AST before and after.
    - The packs are byte-identical to S2_HEAD, `lint/` matches main, and main has not moved.
    - review.md has no open confirmed Blocker or Major.
    - `ci.yml` 38418651864 and `static-policy.yml` 38418656187 passed on af3e05e8.
    - My own `run_ci --stage source` gave `5653 passed, 32 skipped in 179.29s` / `CI passed.`
  - **True A002 counts for S6:** main 8387d666 579, head 577. S3's "703→623" claim was misleading, because 703 is the stale baseline.
  - **Follow-ups left (Minor):** R-M4, R-M5, R-M7, and R-M8 [scope-adding].
- 2026-10-14 00:00 — **Re-review round 1: MERGEABLE AFTER FIXES.** All 21 fixes hold and the refactors caused no regression. There are 3 new Majors, each reproduced, and 1 Minor.
  - **R-RR1:** Grok and Muse session ids *returned by the vendor* are bound verbatim, so an upper-case returned UUID slips past the case-insensitive busy check (INV-14).
  - **R-RR2:** a 404 on a child session's `children` call ends an opencode turn as `session_not_found` with no EC-158 abort.
  - **R-RR3:** Grok and Muse approval titles are not scrubbed, which §9.1 requires; opencode scrubs them.
  - **R-RR4 (Minor):** 86 header lines outside RELATED DOCS, plus one docstring, still cite spec ids.

  Per the skill, the new Majors go to a fresh findings verifier scoped to R-RR1 to R-RR4, then back into repair, which counts toward the 8 iterations. Re-review rounds: 1 of 2 used.
- 2026-10-14 00:30 — **The scoped verifier for re-review round 1 confirmed 2 Majors, both reproduced, neither needing a spec change.**
  - **R-16 (R-RR1):** Grok and Muse bind a vendor-returned session id verbatim, which breaks INV-14. The fix site is NativeTurnTable, lower-casing keys for GROK and MUSE only, per §8.5.
  - **R-17 (R-RR3):** Grok and Muse approval titles are unscrubbed, which breaks §9.1 and INV-6. The fix is to scrub before the cap, as opencode does.
  - **Downgraded to Minor:** R-RR2 became R-M10, follow-up and a spec gap. R-RR4 became R-M11, trivial.
- 2026-10-14 00:30 — **R-M10 stays a stated follow-up, not built.** A child session's 404 during the tree walk fails the turn as `session_not_found` and sends no EC-158 abort. Why:
  - it needs a narrow race;
  - the turn still fails with a structured error;
  - the fix needs a spec design choice about how a child's 404 is classified, and the verifier proposed EC-154/EC-158 wording;
  - opening a spec revision on the last allowed re-review round adds risk.

  S6 must list it under Follow-ups with the proposed wording.
- 2026-10-14 00:30 — **Next:** an S2 addendum with regression tests for R-16 and R-17, proven red. Then S5 iteration 4 (R-16, R-17, R-M11), then re-review round 2, the last.
- 2026-10-14 01:10 — **S2 addendum 2 done** (tests 5ce6e85d, report 1c74c450). It adds 11 regression tests, all red for the stated reasons: R-16 ×8 (Grok and Muse; continue and fork; the handle's id and its lower-case form) and R-17 ×3.
  - My run of the new files: `11 failed, 34 passed`.
  - The test diff only adds; the few removed lines are A001 header fields, rewritten.
  - **Open note from the author:** no test pins opencode's exact id comparison. Iteration 4 is briefed that opencode must stay exact (INV-14), and re-review round 2 checks it.

## User replies (verbatim)
(none during the run)

## Niche facts accumulated (carried into every later briefing)

### S5 iteration 1 facts
- `ci.yml` and `static-policy.yml` run only when dispatched; `gh pr checks 1036` shows "no checks reported". Read results with `gh run view <id>` and dispatch with `gh workflow run`. — *source:* S5-1
- On Windows (Proactor), `drain()` raises for a dead pipe in every mode, so pipe-timing bugs only show on remote Linux 3.12. — *source:* S5-1
- A full-suite WinError 10055 means the machine has thousands of TIME_WAIT sockets; rerun before suspecting code. — *source:* S5-1
- `ToolsFormatter._parameters_schema` emits only type and description. Categorical values are listed by adding an `input_schema` built from it, as `fork.py` and Muse's `MuseHostTool.spec()` do; do not change `ToolParameter`. — *source:* S5-1
- S025 resolves f-strings with a placeholder when counting description sentences. `ruff --select I001` reports 223 findings already on main, none in this feature's files. — *source:* S5-1
- Muse session ids are lower-cased at all five `require_uuid` sites, Grok's at continue and fork; NativeTurnTable stays exact for opencode. — *source:* S5-1

### Lint and gates
- **S011 bans `import httpx`** outside `vidbyte/lib/http/transport.py` and `vidbyte/tools/mcp/transport.py` (baseline 0).
  - opencode must go through `HttpTransport.request` (`lib/http/transport.py:55`), or change that owner module.
  - `HttpTransport.request` has no SSE, no query params, and creates a new client per call. — *source:* S0 code-map §4.1
- **The full-lint pass line is `SDK-LINT: PASS`**, not `AGENT-LINT`. — *source:* S0
- **Semgrep is not part of `run_ci.py`.**
  - Static policy: `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, using semgrep 1.170.1 from the venv at `C:/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1`. — *source:* S0 code-map §1
- **Source and package stages need different `PYTHONPATH` settings.**
  - Source stage: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`.
  - Package stage and full gate: run with no `PYTHONPATH`. — *source:* S0 code-map §1
- **S039 bans `asyncio.Lock`.** The precedent is `asyncio.Semaphore(1)` at `vidbyte/agents/codex/agent.py:82-86`. — *source:* S0
- **S045 (ASYNC109) flags an async parameter named `timeout`.** Use `timeout_seconds`. — *source:* S0
- **S012 flags every `.request(` call without a timeout** (baseline 0). — *source:* S0
- **C012 requires `ProviderModelRegistry` proof for model fields.**
  - It applies to `model` / `*_model` str fields on `*Settings`, `*Config`, `*Spec` and `*Options` classes, and the registry is strict.
  - Vendor model strings (Grok, opencode `provider/model`, Muse, `glm-5.3[1m]`) are not in that registry.
  - Exemptions are rows inside the rule file; editing that file may count as weakening a rule. — *source:* S0 code-map §4.14

### Module layout and packaging
- **Don't copy the `builtins/sessions/` layout for headers or error handling.** It is baseline debt: a non-A001 header, raw exception text (S017), adjacent literals (S062), and a sync `_caught`.
  - Headers: copy `vidbyte/tools/toolsets/coding.py:1-12`.
  - Error translation: copy `vidbyte/agents/codex/transport.py`. — *source:* S0
- **`vidbyte/tools/mcp/transport.py` does not fit ACP or MSP as-is.**
  - It drops notifications (`:416-418`).
  - It can't answer server requests (`:419-450`).
  - `request()` has no timeout keyword (`:222-226`).
  - A006 does allow the `harnesses` → `tools.mcp` import. — *source:* S0 code-map §4.2
- **No process-tree kill exists in the SDK.** On Windows the SDK kills only the direct child (`bash.py:9`). The Muse `.cmd` shim routes arguments through `cmd.exe` `%*` parsing. — *source:* S0 code-map §4.9-10
- **Commit order for the public API.**
  - `scripts/generate-sdk-public-api.py` refuses to run while `vidbyte/__init__.py` has uncommitted changes.
  - So commit the export first, then regenerate `contracts/sdk-public-api.json`. — *source:* S0 code-map §4.16
- **C015 plus the frozen `pyproject.toml`:** no non-.py, non-README data files may live under `vidbyte/` (no vendored JSON schemas or fixtures). — *source:* S0 code-map §4.17

### Failure codes
- **`FailureCode` spans `vidbyte/lib/enums/failure.py:25-144`.**
  - The CODEX block is lines 35-46. Line 34 sits directly before it (Claude's suggested spot) and line 47 directly after it (Codex's spot).
  - Safe insertion spots for this PR: after 144, between 67 and 68, between 99 and 100, or between 129 and 130. — *source:* S0
- **Only `codex.*` codes need classification rows,** enforced by `tests/test_codex_failure_recovery.py:192-202`. No table exists for other prefixes. — *source:* S0

### Tool exposure
- **MCP runs tools without a permission check.** `mcp_server/handlers.py:84-88` calls `tool.execute` with no `PermissionPolicy`, no validation and no timeout.
  - The server is serial, so a blocking `wait_*` tool stalls every other call.
  - It serves only the tools passed to `McpStudioServer(tools=...)`. — *source:* S0 code-map §4.5, §4.7
- **Every public `BaseTool` exported from `vidbyte.tools.builtins` becomes YAML-declarable,** including WRITE tools (`lib/registries/components.py:101-124`). — *source:* S0 code-map §4.6
- **Dynamic tools inside a Codex agent are cancelled at 300 s** (`lib/constants/codex.py:193`). — *source:* S0 code-map §4.8
- Installed Grok is 1.0.52, not 1.0.13: the facts marked verified in the spec come from 1.0.52 (spec A-2); the version floor stays 1.0.13. — *source:* S1 author
- S054: no string literal may be assigned to a password/token/secret-named identifier (hence `OPENCODE_SERVER_LOGIN`, `server_password: str | None`). — *source:* S1 author
- Spec contract names: launchers are argv prefixes `grok_command`/`opencode_command`/`muse_command` (D-19); fake Grok/Muse peers are `(sys.executable, "-u", script)`; opencode HTTP is faked by patching `vidbyte.lib.http.transport.httpx.AsyncClient` with `httpx.MockTransport`; one error type `NativeHostError(AgentExecutionError)`; 53 codes appended after `RULE_EVALUATION_FAILED`; shared plumbing in `vidbyte.harnesses.native.hostkit`; process helpers in new `vidbyte.lib.process`. — *source:* S1 author
- Byte-identical files (spec INV-22): root `vidbyte/__init__.py`, `contracts/sdk-public-api.json`, `vidbyte/tools/builtins/__init__.py`, `lib/dataclasses/__init__.py`, `lib/constants/__init__.py`, `pyproject.toml`. Transport-extension tests live in `tests/features/grok_host/` (no existing test file may be edited). — *source:* S1 author
- PR body must state limitations T-1, T-2, T-5, T-7 (spec §10) and assumptions A-5 (headless Grok refuses approval-needing tools, unverifiable without a prompt) and A-7 (opencode revert restores files). — *source:* S1 author
- MSP 1.0.1 requires a client-made UUIDv7 `commandId` on session/start, resume, fork, approval/decide, userInput/cancel and turn/*. `turn/steer` needs `expectedTurnId`. Fork takes `cutPoint:{lastTurnId}`. A fresh turn's `turnId` equals its `commandId`. Stdlib `uuid.uuid7` exists only on Python 3.14+, so `MuseWire.new_command_id()` builds the id itself. — *source:* S1 review r1 R-1
- `grok agent` must get `--no-leader`, because the user's `[cli] use_leader` config otherwise attaches to a shared leader. — *source:* S1 review r1 R-7
- `ToolsFormatter` forwards the metadata keys `hint`, `retryable` and `detail`, not `next_step`. `ToolExecutor` runs `validate_call` before `execute` (`executor.py:61-66`). — *source:* S1 review r1
- Transport: the new options are `exit_grace_seconds: float | None = None` and `stop_process_tree: bool = False`. With both at defaults, close behaves exactly as before (INV-18). C002 and C006 traps apply to inline `isinstance(x, bool)` and to `__init__` guards, so both go through `RecordFieldValidator`. — *source:* S1 author r2
- AC-20: each entry module must import cleanly in a fresh interpreter. If it passes only with a function-level import, report BLOCKED (spec §14). — *source:* S1 author r2
- The installed Grok is 1.0.52, not 1.0.13. A top-level `grok --single` run has no `--no-leader` flag (A-18). The Grok argv is `grok agent --no-leader --model=MODEL stdio`, with `--name=value` argument form. — *source:* S1 r3
- Muse in-distro cleanup is `wsl.exe -d <distro> -e sh -s <mark>`, with the script on stdin. There is deliberately no `--`. The mark is 32 lowercase hex characters checked against `MUSE_PEER_MARK_PATTERN`. The cleanup env is `NativeChildEnvironment.build({})`, never the peer's overlay. The script can be tested on Linux CI. — *source:* S1 r3
- `stop_tree` assumes `start_new_session=True`. On POSIX it always kills the process group (TERM then KILL), even after the leader has exited. Windows uses `taskkill /T /F`. The residual risk is stated in EC-10, A-9 and T-7. — *source:* S1 r3
- `muse/wire.py` reads `vidbyte.__version__` at call time through a module-level `import vidbyte`, for MSP `clientInfo.version`. — *source:* S1 r3
- Timing constants must be read through the module at call time (for example `native_hosts.NATIVE_STOP_GRACE_SECONDS`). Tests patch the module, so a `from … import` copy breaks the time-bound tests. — *source:* S2
- Resolve `wsl.exe` with `shutil.which`. A bare `wsl.exe` finds System32 before PATH and runs the real one instead of the test fake. — *source:* S2
- In AC-1 on Windows, `grok` is a `grok.cmd` shim on a PATH limited to that folder plus System32, and HOME/USERPROFILE are empty. The fake grok reads its role from argv: `models`/`agent` must come first, `--version` can appear anywhere, and a one-shot is recognised by `--single=`. — *source:* S2
- opencode's `abort` returns `200 true` and `diff` returns `200 []` even for a missing session, so the host calls `GET /session/{id}` first. Take the message baseline before `prompt_async`. — *source:* S2
- AC-18 needs `import vidbyte` to load `vidbyte.tools.toolsets.{grok,opencode,muse,harness_backends}`. `test_method_frames_are_dropped_without_a_callback` is the regression proof for the transport dispatch fix. — *source:* S2
- The suite runs fast: all four packs red in about 16 s on Windows. The 19 skips are platform guards that should run on Linux CI. — *source:* S2
- Lint rules A002 and A007 skip untracked files, so `git add` new files before running `python lint/run.py`. S3's first "PASS" was false for this reason. — *source:* S3
- A007 matches whole split tokens (`byte` yes, `bytes` no) and flags literals near read/send/request/sleep calls. A002 wants `# @intent` near any `def` whose identifiers contain request/send/transport/subprocess/provider/permission; its slack is 625/703. S024 allows nesting depth 3 at most. — *source:* S3
- `NativePeer.call` re-raises JSON-RPC error answers as `McpProtocolError` with `details["error"]`, for each host's wire code to map; transport failures become `NativeHostError`. The transport change came out at +156/−8 lines. — *source:* S3
- Semgrep on this machine needs `PATH="/c/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1/Scripts:$PATH"`. The global pysemgrep breaks under mcp 2.x. — *source:* S3
- `McpStdioTransport.returncode` is saved in `_detach_process_state`, so it survives `close()`. The transport diff is +166/−8. — *source:* S3
- S3 deviations are listed under spec §17 "Implementation deviations". Two of them:
  - (8) `list_harness_backends` has no §12.4 try, because it returns a constant.
  - The opencode list tools return wrapped objects such as `{"models": ...}`, which S6 must state.
  — *source:* S3
- An untested race: when `turn/completed` and a -32030 answer arrive together, a Muse steer may raise `api_error` (vendor_code -32030) instead of `turn_not_found`. That follows EC-115/EC-102 as written. — *source:* S3

