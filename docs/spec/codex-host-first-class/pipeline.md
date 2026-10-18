---
slug: codex-host-first-class
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-first-class
branch: feat/codex-host-first-class
base_commit: a7730107  # slice 1 (codex-host-hardening) verified HEAD; branch stacked on PR #1178
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1181
until: none
started: 2026-10-17 22:40
---

# Pipeline: CodexHost first-class Codex features (slice 2 of 2)

Slice 1 (`docs/spec/codex-host-hardening/`, status `verified`) is done on this branch. This slice adds the P0 and P1 functions from request.md §C.10 that slice 1 did not build. S6 runs once, at the end of this slice, and covers both specs. The PR already exists (draft #1181), so S3 skips creating it.

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 recon | done | 22:40 | 23:05 | reports/S0-scout.md | code-map.md: 4 sections, 564 lines; per-function protocol table (§4.1); pins table (§3.4) |
| S1 spec + review | done | 23:10 | 03:10 | reports/S1-spec-author.md, reports/S1-spec-review.md, reports/S1-spec-review-r2.md | r1 fde5a8b0; round 1 SOUND WITH FIXES (1B/6M/6m, 040e56c1); r2 603519bb; round 2 SOUND WITH FIXES (0B/3M/2m, 4db45a23); **r3 d9072cdb status approved**. Budget 13 files / 69 classes / 0 deps / 46 config keys / 42 endpoints; INV 55, AC 44, EC 62, FR 36 |
| S2 tests | done | 03:15 | 06:40 | reports/S2-test-author.md | 236 tests in 14 new modules plus the §13 pin rewrites (fa27a3ad, ab13e1e7, 893f1df4); **S2_HEAD 625279c6, then e3d41513 after S3's blockers**; red set 253 = 233 new + 19 superseded pins + 1 inherited; spec r4 d0529d15 |
| S3 implement | done | 06:45 | 03:40 | reports/S3-implementer.md | 39 rows; budget exact (13/69/0/42); **S3_HEAD 8ea8734f** pushed; #1181 body updated, still draft; area 1 failed (inherited) / 1293 passed; source gate 1 failed (inherited) / 6824 passed; package `CI passed.`; 13 implementation deviations in spec §17 |
| S4 adversarial review | done | 03:45 | 05:10 | reports/S4-review-{conformance,conventions,engineering}.md, reports/S4-findings-verifier.md | review.md: 8 confirmed (2 Blockers R-1, R-2; 6 Majors R-3…R-8), 7 Minors m-1…m-7, 0 refuted |
| S5 repair loop | done | 06:20 | 07:15 | reports/S5-repair-1.md, verify-log.md | iteration 1/8 closed R-1…R-5, R-8, m-2…m-5 (R-6/R-7 by S2 9ad2771e, m-1 by r6); HEAD ec17d5ce pushed; area 1 failed (inherited)/1302 passed; source 1 failed (inherited)/6833 passed; package `CI passed.` |
| S5 re-review | round 1 done | 07:20 | 07:50 | reports/S5-rereview.md | MERGEABLE AFTER FIXES: R-RR1 Blocker (record `is_dir()` re-raises EACCES), R-RR2 Minor, R-RR3 Minor (spec); 8 of 10 S4 items CLOSED with revert-mutant proof; spec r7 e736c93f (deviation 5) |
| S6 PR (both slices) | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 2/8 · S5 re-review rounds: 2/2

## Decisions the orchestrator made
- 2026-10-17 22:40: **The same branch, worktree and PR as slice 1.** The precedent is #1055's two specs in one PR. Slice 2's base is slice 1's verified HEAD a7730107. request.md is slice 1's verbatim conversation capture with a slice-2 header (scope, what slice 1 already built, and the machinery to reuse).
- 2026-10-17 23:05: **Queue scope is P1 add, list and start only.** request.md's "`thread/queue/*`" was the assistant's shorthand. The research the user asked to build from ("create the codex functions that you thought about") ranks `thread/queue/add|list|start` as P1 and `update|delete|reorder` as P2 (codex-gap-report.md:152, :334, matrix rows 21-25). P2 is not built (slice 1 Q-1 default).
- 2026-10-17 23:05: **`create_codex_worktree` has no app-server method.** The research's own proposal is to implement it with `git worktree add` under a Vidbyte-owned root (codex-gap-report.md:314-315). That is the design input.
  - The alternative, shelling out to `codex exec --worktree`, is out: it starts a paid Codex run.
  - Codex's managed-worktree default root is unverified, because the `codex_worktree` crate is not in the scratchpad. The spec must not claim compatibility with that root.

- 2026-10-18 00:40: **Spec r1 (fde5a8b0) checked.** It has 18 sections, 73 §12.3 rows, base_commit a7730107 and the right commit message.
  - **The queue (NG-1 / D-20 / Q-1, default "not built"): I accepted the author's evidence.** It overrides my own 23:05 scope decision.
  - **Evidence I verified myself:** `codex-src/codex-rs/tui/src/session_queue_commands.rs:34` refuses `codex queue` without the shared daemon ("Queuing must discover the shared server to avoid writing through a separate server"), and `:42-48` refuses queuing through an embedded app-server. CodexHost is always a private stdio app-server.
  - **The author's other points:**
    - the TUI never calls `thread/queue/start` or `list`, so Codex drains the queue itself and the resulting turns are untracked by the host (slice-1 INV-11);
    - inside one private server, the queue is redundant with `continue_codex_thread` and with `wait_codex_turn` followed by continue.
  - **Not stopping for the user:** the default is evidence-backed and conservative, so I don't stop. It is named in the S1 summary so the user can interrupt.

- 2026-10-18 03:10: **S1 done.** r3 (d9072cdb) has `status: approved` and 18 sections, and §16 records every finding from both rounds (R-1…R-18). The defaults I applied, all printed in the S1 summary:
  - Q-1, the queue: not built.
  - Q-2…Q-9: no.
  - Q-10 and Q-11: optional and scope-adding, not built.
  - **R-14 took a different form from the reviewer's fix.** The side-chat tool uses `DENY_ALL` approval modes, which send `approvalPolicy "never"` and no reviewer on both `thread/fork` and `turn/start`. The reviewer's explicit `NEVER` would have reached only `thread/fork`, because `turn_start` never sends explicit fields. I accepted it, since it narrows on both requests.
  - **The host stream bound is enforced (D-39):** `CodexTurnRegistry.charge_stream` with limits of 65,536 events and 32,000,000 chars.

- 2026-10-18 05:45: **S2 came back BLOCKED** with 236 tests (fa27a3ad, f8146997; report 9d3aed8c) and two spec defects. I checked both myself and answered them from the spec, without asking the user:
  - **Two missed 26-tool pins:** `test_codex_host_lifecycle.py:101` and `test_codex_host_helper_lifecycle.py:109`. §13 intends a 42-tool catalog that S3 can reach without editing tests, so this is option (a): §13 gains both rows, then S2 rewrites them.
  - **`CODEX_HOST_NO_GOAL_MESSAGE` already exists** (`constants/codex_host.py:312`, used by `run_codex_goal` and pinned at `helper_surface.py:94`). INV-48 freezes `run_codex_goal`, so this is option (a): the new message is renamed `CODEX_HOST_NO_STORED_GOAL_MESSAGE`, unused, and chosen by me over S2's `GOAL_MISSING`. That keeps it in the `NO_*GOAL` family next to the pinned `CODEX_HOST_NO_GOAL_CAUSE` and `_NEXT_STEP`.
  - **My sweep of all 47 constant names in the spec's tables** found no other collision.
  - **The S1 author's r4** (an amendment, not a review round) also resolves S2's six ambiguities, choosing only options the tests already accept.

- 2026-10-18 06:40: **Spec r4 (d0529d15) accepted**, including three of the author's deviations from my wording:
  - the method constants use the `CODEX_` prefix, matching the two §9.3 names that were already pinned (my `CODEX_HOST_` anchor was wrong);
  - the sandbox slot uses `.name`, because `.value` prints an empty name for `PROVIDER_DEFAULT`;
  - unregistered handles also get the thread sentence (INV-25).
  
  I sent S2 back once more to close its three open items. They live in the test tree, where S3 cannot follow up: the stored-goal name pin, FEATURE.md :5/:40, and the README log. My own run at 625279c6: `253 failed, 1041 passed, 3 skipped`, `SDK-LINT: PASS`, and an empty diff of production paths since a7730107. **S2_HEAD = 625279c6.** From now on, `git diff 625279c6..HEAD -- tests` must stay empty.
- 2026-10-18 06:45: **The S3 drift check came back clean.** origin/main is still 6f5a7310 (the #1055 merge), and #1178's head 8baff351 is an ancestor of HEAD. #1181 already exists as a draft with title `[WIP] feat: CodexHost production hardening and first-class Codex features`, so S3 updates its body (`gh pr edit`) instead of creating a PR.

- 2026-10-18 22:35: **S3 stopped with an API usage limit** before committing anything. I resumed the same agent with SendMessage once the limit reset.
- 2026-10-18 01:30: **S3 came back BLOCKED** at f0d52eca: all 39 rows committed, budget exact, and `git diff 625279c6..HEAD -- tests` empty. My area run gave `8 failed, 1286 passed, 3 skipped`, the 7 blocker tests plus the inherited one. I verified each blocker and decided all five without asking the user:
  - **B-1** `test_codex_host_hardening_records.py:356` pins `CodexSpawnRequest`'s tail after `name` as 3 fields. D-5 appends `collaboration_mode`, so this is a third missed §13 pin. Route: spec r5 §13 row, then S2 rewrites it.
  - **B-2** `test_codex_host_feature_records.py:309`'s `_snapshot()` builds a COMPLETED snapshot with no result, which the INV-48-frozen record refuses (`codex_host.py:354`). Test defect, so S2.
  - **B-3** `test_codex_host_mcp_memory.py:159` expects `thread/read {"threadId"}`, but openai-codex `thread_read` always sends `includeTurns` (`client.py:498-503`). Test defect, so S2.
  - **B-4** `codex_host_feature_support.py:334` calls `_enter("rename_codex_thread", ..., name=name)`, which collides with `_enter(self, name, ...)` (`codex_host_support.py:630`) and raises TypeError. Fixture defect, so S2.
  - **B-5** ruff S105 (S054, allowance 3) flags `CodexMcpAuthStatus.BEARER_TOKEN = "bearerToken"` on its NAME alone. S3 proposed raising the allowance, but the rule's own guidance says "Raising lint/baseline.json for a newly introduced violation ... does not authorize new debt", and spec §14 forbids it too. Decision: spec r5 renames the member `BEARER`, with the wire value `"bearerToken"` unchanged, which removes a purely name-based false positive. S2 updates the two pins (`test_codex_host_records.py:83`, `test_codex_host_mcp_memory.py:83`), and S3 renames it in production. No user approval needed, because no baseline moves.
  
  **Order:** spec author r5, then S2 (S2_HEAD moves), then S3 resumes (rename, gates, push, PR edit).

- 2026-10-18 02:10: **Spec r5 (5f6c4fc4) and S2 round 3 (32e1a404, e3d41513) checked.**
  - r5 adds §13's third missed pin row and D-40, which renames `BEARER_TOKEN` to `BEARER`. The author's sweep found no other `CodexSpawnRequest` field pin.
  - **S2 fixed B-4 in the shared fixture,** making `_enter(self, name, /, *args, **kwargs)` positional-only. That changes a fixture signature, not an assertion, so rule 5 allows it. Every caller already passed the name positionally.
  - **My area run:** `3 failed, 1291 passed, 3 skipped`. The two failures are the B-5 pins waiting on S3's production rename; the third is the inherited failure.
  - **S2_HEAD is now e3d41513.** S3's no-test-edit check is `git diff e3d41513..HEAD -- tests`.

- 2026-10-18 03:40: **S3 checked myself at 8ea8734f:**
  - HEAD equals origin; the tree is clean;
  - `git diff e3d41513..HEAD -- tests` is 0 lines, and `lint/` is unchanged since a7730107;
  - the spec says `status: implemented`, r5;
  - #1181 is a draft, with title and base unchanged and the placeholder body in place;
  - my area run: `1 failed (inherited), 1293 passed, 3 skipped`; `SDK-LINT: PASS`;
  - file sizes: host.py 786/900, wire.py 839/840, dataclasses/codex_host.py 891/900, every new module ≤ 779.
  
  The source and package gate tails are S3's, quoted in its report. (An earlier note in this log was dated 2026-10-19 by mistake; corrected to 10-18.)
- 2026-10-18 03:45: **S4 diff scope** is `a7730107..8ea8734f`, slice 2 only. Slice 1 was already reviewed and verified (its review.md has R-1…R-12 and m-1…m-9). Reviewers may read the full PR diff against `origin/ai/resolve-pr-1055-comments` for context, but they file findings only against slice-2 changes.

- 2026-10-18 05:10: **S4 checked.**
  - The reviews found: conformance 1B/0M/2m, conventions 1B/1M/5m, engineering 1B/5M (29/33 mutants killed).
  - The verifier merged them into 8 confirmed and 7 Minors, refuting nothing. Each row has a fixer tag and its own repro under `scratchpad/s4-slice2/verifier/`.
  - **Routing plan, so each role stays separate (the slice-1 pattern):**
    1. **Spec author r6:**
       - R-1: a new §9.2 worktree-root failure message trio, with §8.4 config keys pre-authorised (+3);
       - R-5: the side-chat tool resets the rejected spawn defaults (name, tools, personality), as the resume and continue tools do; this is §9.2 rows 34/36 and D-22;
       - R-4: check that the §9.2 resume row states the cancel, and add an EC row if it is ambiguous;
       - m-1: record the reviewer restyle as deviation 14;
       - set `status: reviewed`.
    2. **S2 round 4:**
       - mutant-killing tests for R-6 (S7, mid-turn subscription, with the first read bounded by a timeout) and R-7 (S3b/S3c cumulative bounds), proven with the engineering `mutant.py`;
       - red regression tests for R-1, R-3 (oversize event, EC-19 GAP(1)), R-4 (malformed goal/set answer → cancel) and R-5 (`_side_chat_view` plus a tool run under name/tools/personality defaults).
       
       Then a new S2_HEAD.
    3. **S5 repair iteration 1:** R-1…R-5 and R-8 code, plus the trivial Minors m-2…m-5 (m-6 and m-7 only if the verifier tagged them trivial), then every gate.

- 2026-10-18 06:20: **Spec r6 and S2 round 4 checked.**
  - **r6 (4d972438, `status: reviewed`):**
    - adds the `CODEX_HOST_WORKTREE_ROOT_*` trio, EC-63, the INV-31 cancel rule plus EC-64, the INV-43/D-22 side-chat default reset, and deviation 14;
    - config keys stay at 46, because §8.4 counts only §9.3 non-message constants. That matches the earlier worktree trios, so I accepted it.
  - **S2 round 4 (9ad2771e, 25c2de9b)** adds 9 tests, with no production diff. My checks:
    - area run: `8 failed, 1295 passed, 3 skipped`, which is the 7 intended red regression tests plus the inherited one;
    - mutant runner on `stream_wait`: NONE exits 0 (26 passed), while S7, S3b and S3c each exit 1 (S3b with `AssertionError: 1000 not less than or equal to 300`).
  - **S2_HEAD is now 25c2de9b.** R-6 and R-7 are closed by tests. S5 iteration 1 launches for R-1…R-5, R-8 and the trivial m-2…m-5; m-1 is closed by r6 deviation 14, and m-6/m-7 are follow-ups.

- 2026-10-18 07:15: **S5 iteration 1 checked myself at ec17d5ce:**
  - HEAD equals origin; the tree is clean;
  - `git diff 25c2de9b..HEAD -- tests` is 0, and `lint/` is unchanged;
  - area `1 failed (inherited), 1302 passed, 3 skipped`; `SDK-LINT: PASS`;
  - the 72-column check over the iteration's touched `.py` is clean;
  - host 786 / wire 839 / dataclasses 891.
  
  **Two things to judge:**
  - **R-3's variant.** `_fits_alone` applies only the per-turn bound on a log never attached to the host. On an attached log it matches the verifier's proven fix. Sent to the re-reviewer to judge.
  - **Spec deviation 5 is stale.** It still says `thread/list` after m-2 renamed the refusal to `parentThreadId`/`ancestorThreadId`. The spec author fixes it (r7, docs only), in parallel with the re-review.

- 2026-10-18 07:50: **Re-review round 1 checked.**
  - **I reproduced R-RR1 myself.** The `probe_rr_repo_stat` output: Python 3.11 pathlib ignores errnos [2, 9, 20, 10062], so EACCES from `CodexWorktreeRequest.__post_init__`'s `require_directory` (`codex_host_inputs.py:590-591`) escapes as a raw `PermissionError` with the absolute path, which breaks INV-2 (r6 names OSError).
  - **Routing:**
    1. spec author r8 for R-RR3: INV-20's "What is dropped" and D-39 still describe evicting everything for an oversize event, so add r6's missing EC-19 sentence;
    2. S2 round 5: a red regression row for R-RR1, copying the probe (expect the `CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE` packet with `__cause__ is None`);
    3. S5 iteration 2: R-RR1 (`except (ConfigurationError, OSError)`), plus R-RR2's wrong comment at `thread_actions.py:118-119`. The repair agent also appends the R-RR rows to `review.md`;
    4. re-review round 2, the last allowed.
  - **R-RR2's shared-helper refactor** (one `_base.py` helper for the resume and side-chat resets) is a follow-up: the reviewer marked it optional, and it is churn this late.

- 2026-10-18 08:20: **Spec r8 (2d0f5216) and S2 round 5 (4de2c91d, d11c5d9d) checked.**
  - r8 adds the `_fits_alone` rule to INV-20 and D-39.
  - Round 5 adds 2 tests: a record test that runs without the SDK, and a host test. They cover two refusal kinds, EACCES and ENAMETOOLONG, so a `PermissionError`-only fix fails too; a `from exc` fix also fails.
  - My area run: `3 failed, 1302 passed, 3 skipped`, the 2 intended red tests plus the inherited one. The diff is tests and docs only.
  - **S2_HEAD is now d11c5d9d.** S5 iteration 2 launches.

- 2026-10-18 08:55: **S5 iteration 2 checked myself at bff67286:**
  - HEAD equals origin;
  - the tests diff since d11c5d9d is 0, and `lint/` is unchanged;
  - the code diff since ec17d5ce is 2 files, +10/-7;
  - area `1 failed (inherited), 1304 passed, 3 skipped`; `SDK-LINT: PASS`.
  
  Iteration 2 also quoted source `1 failed (inherited)/6835 passed` and package `CI passed.`
  
  **My briefing error:** I gave `codex_host_inputs.py` a 600-line ceiling, but spec NFR-1 says 900. The agent caught it, and nothing depended on it.
  
  **New follow-up for the PR body:** `RecordFieldValidator.require_directory` (`validation.py`) is the canonical place to map a refused stat. `native_threads.py:120` and `:146` call it with no OSError handling, so they likely leak the same raw OSError. That is outside §12.3, so it needs its own PR.
  
  Re-review round 2, the last allowed, launches on `ec17d5ce...bff67286`.

- 2026-10-18 09:20: **Re-review round 2 checked.** Report: `reports/S5-rereview-2.md`.
  - **Verdict:** SOUND, with 0 Blockers, 0 Majors and 1 Minor, so the cap is not hit.
  - R-RR1 is closed: five in-memory mutants each fail S2's two tests. R-RR2's comment is true, and r7 and r8 match the code.
  - Area run: `1 failed (inherited), 1304 passed, 3 skipped`. `SDK-LINT: PASS`.
  - **R-RR2-1 (Minor), checked myself.** `CodexWorktreeRequest(repository=<PathLike whose __fspath__ returns 5>, ...)` raises a raw `TypeError` from `os.fspath`, inside `RecordFieldConverter.to_path`. INV-2 says that no `TypeError` ever reaches the caller. A grep of every `vidbyte/` file changed since 6f5a7310 finds one `to_path` call: `codex_host_inputs.py:590`. The only other path conversion, `thread_methods.py:162`, wraps a value the record has already validated.
  - **Decision:** run a minimal S5 iteration 3 (3/8), as slice 1 did for m-9. INV-2 is a weighted word, and the user's bar is "exception handle everything".
    1. The S2 author adds one red regression test, as for R-RR1.
    2. A fresh repair agent adds `TypeError` to the record's except tuple, with no spec change: the code is being brought up to INV-2.
    3. I verify it myself with a revert mutant and the gates.
    
    There is no round-3 re-review, because the cap is 2. The root fix in `validation.py` `to_path` joins the separate follow-up PR, with `require_directory` and `native_threads.py:120,146`.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- **Interpreter:** `V="C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/venv-codex163/Scripts/python.exe"`. It is the editable worktree install with openai-codex 0.163.0. Never use the global Python, which holds the user's editable install, and never pip. *Source:* slice 1
- **Gates:**
  - area tests: `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider`;
  - lint: `"$V" lint/run.py`, whose last line is `SDK-LINT: PASS`;
  - full gate: `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source`, then `"$V" scripts/run_ci.py --stage package` with no PYTHONPATH. Run them one at a time, because the MCP stdio timeout test is load-sensitive.
  
  At a7730107 the source stage gives `1 failed (inherited), 6588 passed, 27 skipped`, and the package stage gives `CI passed.` *Source:* slice 1
- **The inherited failure:** `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (167 != 120) is not ours. *Source:* slice 1
- **Semgrep:** the global CLI is broken, so use `C:/Users/422mi/AppData/Local/Programs/Python/Python311/Lib/site-packages/semgrep/bin/semgrep-core.exe -rules .semgrep/<rule>.yml -lang python -json <file>` and strip the leading `"."`. It scans git-tracked files only. *Source:* slice 1
- **Lint:**
  - C021 (baseline 0) allows no top-level UPPER_CASE under `vidbyte/harnesses/native/`, so constants and messages go in `vidbyte/lib/constants/codex_host.py`;
  - S008 allows complexity ≤10 and branches ≤12;
  - S024 allows nesting ≤3;
  - S012 forbids a method named `request`;
  - A002 keeps `# @intent` within 20 lines of its `def`;
  - source comments wrap at 72 columns, tests are exempt by grain.
  
  Run the full lint before every push. *Source:* slice 1
- **The user's #1055 conventions:**
  - constants and messages in lib;
  - error packets read "`<operation> failed with <code>. <summary> The thread id was <id>. Likely cause: <cause> Next step: <step>`";
  - every host function takes a strictly validated input dataclass in `vidbyte/lib/dataclasses/codex_host_inputs.py`, built right after `_guard`.
  
  *Source:* request.md §B.1
- **Slice-1 machinery to reuse:** `ExceptionOrigin.describe` (one token), `LogToken.of(value, CODEX_HOST_LOG_TOKEN_MAX_CHARS)` at log calls, the INV-7 call records, `CodexTurnEvents`, `CodexReviews`, retries through `CODEX_HOST_RETRIED_METHODS`, and post-validation injection of experimental fields, refused locally when `experimental_api=False`. *Source:* slice 1 spec
- **Log record shape:**
  - the event is the first word of a %-style msg, followed by single-space `key=value` tokens;
  - there is no `exc_info`;
  - the tests' `log_fields` is now strict, so a word with no `=` fails.
  
  *Source:* slice 1 S2
- **Push:** only `git push -u origin feat/codex-host-first-class`. Never a bare push, never force. *Source:* user constraints
- **Remote checks:** none run on push (workflow_dispatch only), so the local gate is authoritative. *Source:* slice 1
- **No paid Codex turns:** never run the `codex` binary, and never set `VIDBYTE_CODEX_LIVE_TESTS`. *Source:* user constraints
- **The raw path:** `CodexConnection.raw` (`connection.py:372`) needs a `v2_all` response model by name. Most experimental slice-2 methods have none: `thread/settings/update`, `turn/settings/update`, `collaborationMode/list`, `memory/*`, `thread/queue/*`, `thread/backgroundTerminals/*` and `thread/search`. `mcpServerStatus/list`, `thread/inject_items` and `thread/revert` do have models. *Source:* S0 scout
- **SDK models drop fields:** `TurnStartParams` drops `collaborationMode`, and `ThreadListParams` drops `parentThreadId`. `_params_dict` passes dicts through (`client.py:107-108`), so keys injected after validation reach the wire (`wire.py:207-209`, `:249-253`). *Source:* S0 scout
- **JSON null:** every `wire.py` params dump uses `exclude_none=True`, so it cannot send a JSON null. `serviceTier: null` (clear) on `thread/settings/update` and a null `developer_instructions` in plan settings both need one. *Source:* S0 scout
- **Notifications with no turnId:** the liveness monitor (`connection.py:540-548`) discards every notification without a turnId, for example `thread/settings/updated`, `mcpServer/startupStatus/updated`, `thread/archived` and `thread/queue/changed`. *Source:* S0 scout
- **Turn subscriptions:** the SDK's only multi-consumer turn subscription is private (`_subscribe_turn_notifications`, `client.py:409`). The host watcher holds the public default consumer. The router, `items` and the global queue are unbounded. *Source:* S0 scout
- **Pins:** no free failure-code or `CodexHostOperation` slot exists without editing pins (`helper_surface:245-251,253-266`, `records:63-69,432-440`, `harness_threads:176-195`). The full table is code-map §3.4. *Source:* S0 scout
- **The 1,000-line rule:**
  - `host.py` 937, `wire.py` 797, `lib/dataclasses/codex_host.py` 873, `codex_host_fakes.py` 902, `codex_host_support.py` 828;
  - `lib/dataclasses/codex.py` is already 1,205 and under "no growth" (D-17).
  
  New functions need new modules. *Source:* S0 scout
- **Two test-harness traps:** `test_codex_host_inputs.py:216` uses `iscoroutinefunction`, so it cannot see an async-generator host method. A change under `vidbyte/tools/` outside the four excluded paths fails the harness_threads branch-scope test locally. *Source:* S0 scout
- **Stashes:** never a bare `git stash`, because the stash stack is shared with other worktrees. *Source:* environment
- **Long heredocs:** a long quoted heredoc fails to parse in this Git Bash, so write docs with the Write or Edit tool. *Source:* S5 repair 2, orchestrator
- **Slice-2 contract names (r3):**
  - the mixins `CodexSettingsMethods`, `CodexStreamMethods`, `CodexThreadMethods` and `CodexGoalMethods` over `CodexHostCore`;
  - `CodexTurnStarts`, `CodexTurnEventLog` and `CodexJsonObjectResponse`;
  - `raw(method, params, parse=None)`;
  - `GitWorktrees` in its own lib module;
  - the record modules `codex_host_modes` and `codex_host_features`;
  - `CodexThreadHelpers.fork(..., *, starts_turn=False)`.
  
  *Source:* S1 author r3
- **Slice-2 seams:**
  - patchable limits `turn_stream.CODEX_HOST_STREAM_EVENT_LIMIT`, `_TEXT_LIMIT_CHARS`, `_HOST_EVENT_LIMIT` and `_HOST_TEXT_LIMIT_CHARS`, plus `turn_starts.CODEX_HOST_GOAL_RESUME_START_SECONDS`;
  - read the host totals with `host._registry.charge_stream(0, 0)`;
  - the fake answers -32601 for every slice-2 method, so new handlers go in a stateless mixin module, because `codex_host_fakes.py` is 902 lines;
  - the fake's `thread/search` must apply Codex's default source filter: an empty `sourceKinds` means cli and vscode only, and `FakeThread.source="appServer"`;
  - the fake's fork copies the parent's reviewer and policy unless params override them (`codex_host_fakes.py:857`).
  
  *Source:* S1 author r3
- **S2 bindings for S3:**
  - `CODEX_HOST_NO_STORED_GOAL_MESSAGE` is new and listed in `__all__`. `CODEX_HOST_NO_GOAL_MESSAGE` keeps its text, which `helper_surface.py:94` pins.
  - The 15 `CODEX_*_METHOD` constants go in `lib/constants/codex_host.py`, never in `codex.py`; a guard test checks this.
  - Expected texts are in `tests/features/codex_host/codex_host_feature_support.py`, and the fake's slice-2 answers in `codex_host_feature_fakes.FeatureHandlers` (`feature_answers[method]` scripts a malformed reply).
  - The worktree tests use the real git with `Path.home` patched. "git missing" means `PATH` points at an empty folder, because `CliRunner.find_program` walks `PATH`.
  - Lint prints "S063 IMPROVED 4 -> 3" and still passes; never edit `lint/` to ratchet it.
  
  *Source:* S2
- **S3 facts:**
  - wire.py is at 839/840, so a repair that adds to it must split it first.
  - A007 flags any numeric literal within 7 ancestor nodes of a name containing timeout, limit or token. Moving the arithmetic into a helper fixes it; a named constant does not.
  - S009 is a whole-file mypy ratchet. Narrow SDK unions with `isinstance` plus a `TypeError` tail.
  - semgrep-core JSON starts with a "." line, so parse from the first `{`.
  
  *Source:* S3
