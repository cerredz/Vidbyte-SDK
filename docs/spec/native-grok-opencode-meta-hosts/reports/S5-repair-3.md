# S5 repair, iteration 3 of 8

- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-grok-opencode-meta-hosts`
- **Branch:** `feat/native-grok-opencode-meta-hosts`
- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1036 (still a draft)
- **HEAD:**
  - At the start the local branch was at bae65c29, iteration 2's docs commit, which had not been pushed.
  - The last code commit is af3e05e8. It was pushed, and the remote runs were dispatched there.
  - review.md, verify-log.md and this report are committed after it, in `docs(spec): verify-log iteration 3 for native-grok-opencode-meta-hosts`.

## Result

Every finding in this packet is fixed: R-14, R-15 and R-13. Every gate is green, both locally and on the remote runs at af3e05e8.

- **Comment-only:** `ast.dump(ast.parse(...))` is equal, file by file, for all 38 changed `.py` files against bae65c29.
- **Tests:** no test file was edited.
- **Lint, config and spec:** nothing under `lint/`, `pyproject.toml` or the spec was touched, and the A002 baseline (703) was not changed.
- **review.md:** only status cells changed.
- **Invariants:**
  - INV-19 sha256 is unchanged (`0374a2c8…497a`).
  - The INV-22 diff against origin/main is empty.
  - `vidbyte/lib/enums/failure.py` is unchanged.
  - origin/main 8387d666 is an ancestor of HEAD.
- **Scope:** no new file, record, enum, failure code or dependency. `vidbyte/harnesses/native/__init__.py` was not touched.

## Commits

| Finding | Commit | Subject |
|---|---|---|
| R-14, R-15 | f067088d | docs(native): reflow PR comments to 72 columns and drop spec ids [R-14] [R-15] |
| R-13 | 4f243bc9 | docs(lib): give the PR's A002-flagged functions @intent blocks [R-13] |
| R-15 | 96705dfd | docs(native): rewrap the abort-source intent for the byte-counting width check [R-15] |
| R-13 | af3e05e8 | docs(lib): give ProcessStopper._kill_leader its own @intent block [R-13] |
| bookkeeping | (this commit) | docs(spec): verify-log iteration 3 for native-grok-opencode-meta-hosts |

**Deviation:** R-14 and R-15 share f067088d. The packet asked for both in one pass over each comment, and splitting the pass would have rewritten the same lines twice. The two `@intent` blocks that the reflow made necessary (see R-13) are in that commit too.

## Measures, before and after

All counts are over lines this PR adds under `vidbyte/`, against origin/main 8387d666.

| Measure | Before (bae65c29) | After (af3e05e8) |
|---|---|---|
| Added `#` comments citing a spec id (EC-/INV-/AC-/FR-/NFR-/D-/T-/W-/G-/§ and similar) | 295 | 0 |
| Added full-line `#` comments wider than 72 columns | 701 | 0 |
| Added trailing comments wider than 72 columns | 0 | 0 |
| `comment-format.md` awk over every new file, whole file | many | 0 lines |
| A002, repo's `IntentAnalyzer`, all of `vidbyte/` | 601 (origin/main 579) | 577 (origin/main 579) |
| Largest new module (NFR-4, ≤ 800 lines) | `opencode/host.py` | `opencode/host.py`, 790 lines |

- **Still wide, by design.** The 25 wide comment lines still in changed files are main's own lines:
  - `vidbyte/lib/enums/failure.py` (6);
  - `vidbyte/lib/errors/base.py` (9);
  - `vidbyte/tools/mcp/transport.py` (10).

  They are unchanged from origin/main and were left alone, as the packet asked.
- **A001 headers.** The header docstrings keep their RELATED DOCS and TESTS ids, as the packet asked.

## Per finding

### R-14 and R-15: one reflow pass

- **Method.** Each run of PR-added full-line comments at one column was taken as a block. The id tokens were stripped (parenthesised references and leading "EC-n:" labels), the lines were joined into paragraphs, and each paragraph was filled again at 72 columns counting the indent.
  - `# @intent <name>` stays on its own first line.
  - Blank `#` lines and list items are kept, so the blank-line structure is unchanged.
  - A block that mixes main's lines with the PR's was left alone.
- **Hand rewrites.** Where an id carried the meaning, the comment now names what it stood for:
  - the failure code: wsl_unavailable, protocol_mismatch, version_unsupported, process_exited, server_unreachable or turn_not_found;
  - or the step: the at-cap next step.

  For example, the native_hosts constants comment now reads "Default next step per failure code value. The shared contract tests compare these texts word for word, so change both together."
- **`@intent` names.** Seven names said "row", a spec-table word. They now say "failure":
  - `grok-json-rpc-codes-to-failures`
  - `grok-cli-outcome-to-failures`
  - `muse-wire-error-code-to-failure`
  - `native-errors-transport-reason-to-failure`
  - `opencode-client-status-failures`
  - `opencode-reply-error-to-failure`
  - `backend-balance-status-failures`
- **Rulers.** Section rulers were shortened to exactly 72 columns.
- **NFR-4.** The first fill pushed `opencode/host.py` past 800 lines, so 28 narration comments there were tightened. It is now 790.
- **Width fix.** A line in `opencode/turn.py` held "…" and measured 74 in the byte-counting awk, although it is 72 characters. It was rewrapped in 96705dfd.

### R-13: @intent blocks

- **True numbers before.** origin/main 8387d666 has 579 A002 findings. bae65c29 had 601, which is +22: 24 newly flagged functions, less 2 that this PR clears in transport.py (6 → 4).
- **The 24 functions:**
  - opencode.py: the 12 record validators;
  - grok.py: 3 (`GrokOneShotRequest`, `GrokOneShotResult`, `GrokPermissionRequest`);
  - muse.py: 2 (`MuseModelCatalog`, `MuseSession`);
  - harness_backends.py: 2 (`HarnessBackend`, `OpencodeBackendProvider`);
  - native_hosts.py: 1 (`NativeApprovalDecision`);
  - errors/base.py: `NativeHostError.__init__`;
  - process/runner.py: `CliRunner._feed_stdin`, `CliRunner._outcome` and `ProcessStopper._kill_leader`.
- **Format.** Each block follows main's format: the first lines of the body, `# @intent <name>` and then the plain-English reason, ≤ 72 columns. When the body already opened with a narration comment, the block replaced it and kept its meaning (`NativeHostError.__init__`, `_feed_stdin` and `_outcome`).
- **Two more, caused by the reflow.** `NativePeer.send` and `ProcessStopper._bounded_wait` had passed A002 only because the next function's `@intent` sat within their 20-line window. The reflow pushed it out (601 → 603), so both got real blocks in f067088d.
- **`_kill_leader`.** After the reflow it passed only through `_bounded_wait`'s new block 7 lines below. It got its own block in af3e05e8, so all 24 now carry their own `@intent`.
- **After.** A002 is 577 at HEAD against 579 on origin/main. The only per-file difference is transport.py 6 → 4.
- **Rejected:** lowering `lint/baseline.json`, which lint itself suggests ("A002 IMPROVED 703 -> 577. Lower it with: python lint/run.py --rule A002 --update-baseline"). That is a `lint/` change, outside repair scope.

## Gates (run in this worktree, this iteration, at af3e05e8)

| Gate | Result | Final lines |
|---|---|---|
| 1 packs | PASS (rerun alone) | `1638 passed, 19 skipped in 145.24s (0:02:25)` |
| 2 neighbour suites | PASS | `464 passed, 12 skipped in 16.89s` |
| 3 full suite | PASS | `5653 passed, 32 skipped in 178.98s (0:02:58)` |
| 4 lint | PASS (A002 577/703, down from 601; A001 643/643; A007 255/255; the others at or under their baselines) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| 5 source stage | PASS | `5653 passed, 32 skipped in 183.92s (0:03:03)` / `CI passed.` |
| 6 package stage | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| 7 semgrep | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API check | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| AST equality | PASS | `AST-equality: 38 changed .py files, 38 equal and clean, 0 with differences` |
| remote CI 38418651864 | PASS | 3.11 `5646 passed, 39 skipped in 175.89s` / `CI passed.`; 3.12 `5646 passed, 39 skipped, 19 warnings in 191.73s` / `CI passed.`; Package `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote static policy 38418656187 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| invariants | PASS | INV-19 sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py`, `tests/`, `lint/`, `pyproject.toml` and spec.md unchanged since bae65c29 |

**Checks per commit.** Each code commit was checked before it was made. The packs passed every time (1638 passed, 19 skipped), and lint passed at f067088d (A002 600) and at 4f243bc9 (A002 577).

**First run.** The first full run, at 96705dfd, failed 14 `coding_agent` verify-command tests ("the runtime asked the model for more turns than the test scripted"):
- Those tests time real `bash` runs, and my measurement scripts were running at the same time.
- The file passed alone (`44 passed in 5.10s`), and the code is AST-equal to iteration 2's, which passed.
- When I stopped that run to add af3e05e8, the stop killed only the forked sh child. The parent script went on through gates 4–8 while the new run's packs ran.
- In the final run, gates 2–8 ran with nothing alongside, and gate 1 was rerun alone afterwards.

## Notes for S6

- **The S3 A002 claim was misleading.** S3 wrote "A002 improved 703→623", but 703 is the stale `lint/baseline.json`, not main. Measured with the repo's own analyzer over each tree:
  - S4 measured main aa8c380c at 600 and head de5b7c4c at 623, so the PR had **added** 23.
  - Today main 8387d666 is 579. The branch was 601 before this iteration (+22) and is **577** now (−2).

  The PR body or S3 sentence should say "A002 579 on main → 577 on the branch".
- **Neighbour cover.** A002 clears a function when an `@intent` lies anywhere from 3 lines above its `def` to 20 lines below, so a short function is cleared by the next function's block. A stricter count, which allows only an `@intent` inside the function's own lines, gives main 657 and HEAD 670. Fifteen PR functions pass only through a neighbour:
  - `profiles._read_balance`
  - grok `turn.__init__` and `wire.is_cancel_answer`
  - five in `hostkit/peers.py`: `__init__`, `closed`, `notify`, `answer` and `exit_code`
  - `muse/host._start_turn`, plus `approval_decide_params` and `user_input_cancel_params` in `muse/wire.py`
  - `opencode/host._watcher` and `opencode/server._attached`
  - `managed.__init__` and `runner._close_pipes`

  The rule never flagged them, so they are not a packet defect and were left alone. A later comment edit can uncover them, as this reflow uncovered `send` and `_bounded_wait`.
- **Width is counted in bytes.** gawk on this machine counts bytes, so `…` counts as 3. Check width with the `comment-format.md` awk, not with Python's `len`.
- **Line endings.** `core.autocrlf=true` checks files out as CRLF, while the blobs are LF. A tool that keeps the checked-out endings rewrites whole files, so write LF.
- **Module size.** `opencode/host.py` is at 790 of NFR-4's 800 lines.
- **Stopping a background gate run.** In Git's sh, a stop can kill only the forked child. Check that no gate process remains before starting another run.

## Still open

- **From this packet:** nothing.
- **Follow-ups:** R-M4, R-M5, R-M7 and R-M8.
