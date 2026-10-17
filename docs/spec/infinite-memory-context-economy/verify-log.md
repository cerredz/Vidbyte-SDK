# Verification log: InfiniteMemoryAgent context economy

Gate set: code-map.md §1, with the S5 briefing's corrected commands, which win. Run every gate from the worktree root, in CI order.

| Gate | Command | Where |
|---|---|---|
| Lint | `PYTHONIOENCODING=utf-8 python lint/run.py`. `git add` new files first. It must end `SDK-LINT: PASS`. | local; remote inside ci.yml |
| Source | `PYTHONPATH="$(cygpath -w "$(pwd)")" python scripts/run_ci.py --stage source`. It runs lint, compileall, the context and trace checks, and the whole `tests/` tree. Read run_ci's own summary line, not the wrapper's exit code. | local; remote ci.yml |
| Package | `env -u PYTHONPATH python scripts/run_ci.py --stage package`. It builds, runs twine check, inspects the wheel, installs it into a clean venv and runs the smoke checks. | local; remote ci.yml |
| Contract | `python scripts/generate-sdk-public-api.py --check` | local; also lint C016 |
| Semgrep | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`. Pinned to `semgrep==1.170.1` with `mcp<2`. It scans tracked files only. | local; remote static-policy.yml |
| New tests | `PYTHONPATH="$(cygpath -w "$(pwd)")" python -m pytest tests/features/infinite_memory_agent tests/test_compaction_windows.py tests/test_context_compaction_middleware.py tests/test_deterministic_compaction_middleware.py tests/test_fulltext_index.py tests/test_code_search_tools.py tests/test_anthropic_cache_breakpoints.py -q -p no:cacheprovider` | local |
| Remote | Dispatch only. `gh workflow run ci.yml` and `gh workflow run static-policy.yml` with `--ref feat/infinite-memory-context-economy`, then `gh run watch <id> --exit-status` and `gh api repos/cerredz/Vidbyte-SDK/actions/runs/<id>/jobs`. `gh pr checks` stays empty. | remote only |

## Iteration 1 — 2026-10-17 03:50–05:10 — agent report: reports/S5-repair-1.md

**Defects in:**
- Confirmed: R-1, R-2, R-3, R-4 and R-5 (Blockers); R-6 and R-7 (Majors).
- Test-pack: R-8, R-9, R-10, R-11 and R-24. Their tests are in fd6dab0b, and 10 of them were red at a7f53b09 for the right reasons.
- Trivial Minors: R-12, R-13, R-14, R-15, R-16 and R-19. R-16 is granted for `llms.txt:519`, `llms.txt:815` and `artifacts/file_index.md:422`.
- Failing gate: the PR was CONFLICTING with `origin/main` 6f5a7310 (#1055 CodexHost). That became `[gate:merge-main]`.
- Not handed in: follow-ups R-17, R-18 and R-20 to R-22; R-23 (waived); and the refuted rows.

**Hypotheses and attempts** are listed in order. Failed attempts are included, so the next agent does not repeat them.

`[gate:merge-main]`:
- I ran `git merge origin/main`, not a rebase.
- There was one conflict, in `vidbyte/tools/toolsets/__init__.py`, where both sides had added a line to the header inventory. I kept main's `CodexHostTools` line and the branch's `InfiniteMemoryAgentTools` line.
- The contract `--check` stayed current at 645 exports, so nothing was regenerated.
- The related suites were unchanged at 10 failed, 336 passed.

R-1:
- The example clause became "and any limit on the answer."
- The leaf still has no trailing newline.

R-2:
- I followed spec r5 FR-8.6 and INV-8.2 in order. The blank check runs on the raw query first. Then NUL becomes a space and lone surrogates are dropped (`encode("utf-8", "ignore")`). A query of `"\x00"` alone stays SUCCESS with 0 of 0.
- Each entry line's indexed text is test-encoded inside the existing per-line `try`. `UnicodeEncodeError` is a `ValueError`, so the existing `except` leaves the line out (EC-8.8).
- A note whose name UTF-8 cannot encode is left out before it is read.
- Failed first: a Bash heredoc collapsed `\\x00` into a real NUL byte in the source. I repaired it by byte replacement. Since then, every edit script is written with the Write tool using raw strings.

R-7:
- Profile first. At 1,900 files and 8,000 entries, warm searches took 494–532 ms, and 20 parallel warm searches took 9,916 ms wall.
- The cost came from `code_search/base.py`. `iter_files` resolves each path twice, and `is_text_file` reads 2 KB of every file on every call. `base.py` is off-limits.
- Attempt 1: a private `os.scandir` walk (`_listing`). It only stats, then sniffs and reads only the files whose `(st_mtime_ns, st_size)` changed. This brought warm searches to 25–32 ms and 20 parallel searches to 518 ms. cProfile then showed `pathlib.relative_to` once per file.
- Attempt 2 (kept): resolve each folder once and key its children by a folder prefix. Warm `_lookup` now takes 2.7 ms (listing 2.2 ms).
- `probe_walk_equiv.py` covers file and folder links, junctions in and out of the root, ignored files and oversize files. On that tree, `_listing` lists the same keys, files and order as `iter_files`. The one intended difference: a binary file is now listed with no rows, so it is not sniffed again.
- Main's `iter_files` raises `WinError 1921` on a junction that loops back to the root. `_listing` walks each real folder once.
- Process slips: the heredoc broke a `"\\n"` literal, which I repaired. A `perf(` commit prefix was amended to `fix(` before any push.

R-3:
- The newest model turn is the last message whose role is `assistant` or `model`. A scoped window masks only outputs before it. An unscoped window (`tools=()`) keeps main's behaviour.
- The review's original R-E1 fix (`role == "assistant"`) was avoided, because it misses Gemini's `model` role.
- Verifier probes: on Gemini, 5 sequential reads give 2 masked and a parallel batch of 5 gives 0. On the root's real middleware, batches of 3, 4, 5 and 8 give 0 on the Anthropic and OpenAI shapes.

R-6:
- Only the repeat digest encodes with `surrogatepass`. The body that is sent stays byte-equal to main's.

R-4:
- `_create_payload` runs the gate (`not _holds_cache_control and _is_repeat`) inline. `_marked_message`'s body is folded into the target loop of `_attach_cache_breakpoints`, and every marked message and block is a fresh dict.
- An AST depth scan finds no new 3-level chain.
- An in-place marking mutation fails 14 of the 15 cache tests.
- 28 cache and run-boundary tests pass, and so do 620 Anthropic-referencing tests.
- Failed first: the depth scan diffed against HEAD while parsing the working tree. It now diffs 845a4d9b against the working tree.

R-19:
- The pre-search and the task build sit inside the `try` that guards the retriever. A raise becomes the recall-shaped error.
- Interpretation: the quota still counts the attempt. Refunding it would need an `await` between the quota check and its increment, which the "gets right" list forbids. INV-10.6 frees only calls refused for validation or quota, and EC-10.3 counts an attempt that fails after it starts.

R-14:
- `current = await asyncio.to_thread(self.workspace.map_snapshot)`.

R-13:
- Attempt 1 (1fbe3ede) failed. It used the review's line, `getattr(importlib.import_module(_LAZY_EXPORTS[name]), name)`. The full source gate then failed on `C003 REGRESSED: 1 finding(s), allowance 0` (no-dynamic-import-from-data, blocking). S3 had already reverted this exact form in 7ebf289c (W-8.1).
- Attempt 2 (8da92fb9) is kept. It imports `vidbyte.lib.util.fulltext` by its literal name and returns `getattr(module, name)`. A listed name the module does not define now raises `AttributeError` instead of resolving to `FullTextIndex`.
- Probe: adding `Bogus` to the map gives `AE module 'vidbyte.lib.util.fulltext' has no attribute 'Bogus'`.
- C003 is clean and S015 ratcheted. `test_fulltext_index.py` gives 13 passed.
- Do not dodge C003 with a keyword argument or `importlib.__import__`.

R-12:
- The reference now reads "(see Anthropic Prompt-Cache Marks above)". A009 stays under its 55,000 ceiling.

R-15:
- Two headers changed. A comma splice was amended before any push.

R-16:
- No generator maintains these files, so I edited them by hand in each file's format: `llms.txt:519`, the `llms.txt:815` table row, and `artifacts/file_index.md:422`, rewrapped at that paragraph's 90 columns.
- The llms.txt BOM and CRLF are kept.

R-5:
- I listed every added comment line wider than 72 columns in `vidbyte/**.py`: 845a4d9b..HEAD, tracking `@@ +N`.
- Each rewrap covers only the paragraph that holds the line. An `@intent` line or a bare `#` ends a paragraph.
- Failed first: a whole-run rewrap reflowed main's verbatim `@intent limits-in-code-behavior-in-the-prompt` paragraph in `agent.py`. I reverted it, scoped the rewrap to paragraphs, and added an assert against on-main lines.
- A balanced fill was reverted to greedy, because 88% of the 518 conforming multi-line blocks are greedy.
- Result: 33 lines in 16 files. The awk check prints only the 6 refuted on-main `windows.py` lines (:38, :51, :83, :128, :145, :179). A002 passes.

Gate tooling:
- The shared `scratchpad/semgrep-venv` holds semgrep 1.181.0, not 1.170.1.
- I used a pinned venv at `scratchpad/s5-repair1/semgrep170` (semgrep 1.170.1 with `mcp<2`).

**Changes** (branch `feat/infinite-memory-context-economy`, from a7f53b09):

| Commit | Defect |
|---|---|
| 16e39b73 | merge origin/main 6f5a7310 [gate:merge-main] |
| 848469a2 | R-1 |
| 0e41b3a2 | R-2 |
| 7eb2942c | R-7 |
| 5634b579 | R-3 |
| 5698fdab | R-6 |
| 7d6d7449 | R-4 |
| d7bb1f4a | R-19 |
| 468303dc | R-14 |
| 1fbe3ede | R-13 (attempt 1) |
| 3ec30b9e | R-12 |
| a805c951 | R-15 |
| 7ab9a924 | R-16 |
| 1a6365e6 | R-5 |
| 8da92fb9 | [gate:sdk-lint], the C003 regression from R-13 |

- `git log --first-parent 3bda907e..HEAD -- tests` lists only the merge commit.
- No test file, lint baseline, suppression or CI file changed.

**Gate matrix out** (local gates ran at 8da92fb9 in this worktree):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | related suites (see gate set) | PASS | `346 passed in 9.34s` |
| lint | `PYTHONIOENCODING=utf-8 python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS` |
| full local gate: source | `run_ci.py --stage source` | lint, compileall, context checks and trace contracts PASS; pytest has only the 3 inherited failures | `reasoning trace contracts: ok (182 tools, 55 shapes)` · `FAILED …test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `…::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` · `…::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` · `3 failed, 6580 passed, 16 skipped in 116.66s` |
| full local gate: package | `env -u PYTHONPATH python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| contract | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 5ccc4926362e7f46620a1e1594d28f6b2686c959 (vidbyte-sdk 0.3.0, 645 exports).` |
| Semgrep 1.170.1 | `--test` + `scan --error … vidbyte` | PASS | `1/1: ✓ All tests passed` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 1008 files: 0 findings.` (exit 0) |
| remote: static-policy.yml | run 39017632180 @ 8da92fb9 | PASS | `Static policy: completed/success 8da92fb9` |
| remote: ci.yml | run 39017630351 @ 8da92fb9 | PASS (jobs API: 3/3 completed/success) | `Source / Python 3.11: 6399 passed, 200 skipped in 88.15s` · `CI passed.` · `Source / Python 3.12: 6399 passed, 200 skipped, 19 warnings in 129.38s` · `CI passed.` · `Package: Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |

The 3 source-stage failures are inherited. Each test compares the checkout with `git merge-base origin/main HEAD`, which is now main 6f5a7310 itself:
- `test_failure_codes…`: `assert 167 == 120`. Main's own `FailureCode` has 167 members, and the branch does not touch `failure.py`.
- `test_branch_leaves_the_tools…`: this PR changes `vidbyte/tools` by design.
- `test_import_vidbyte…`: the root `__all__` gains `InfiniteRecallMode`, the §8.4 export.

Two checks back this up:
- On a copy of main 6f5a7310 without git, which matches CI's depth-1 checkout, the file gives `8 passed, 1 skipped`.
- The set is the same as the briefing measured at a7f53b09.

R-7 measured again at 8da92fb9 (`probe_scale_r7.py`, 1,900 files, 8,000 entries):

| Run | Result |
|---|---|
| warm search | `4 ms` (NFR-8.1: 50 ms) |
| cold build | `952 ms` |
| 20 parallel warm searches | `81 ms` wall |

**Still open:**
- No confirmed finding is open.
- Follow-ups R-17, R-18, R-20, R-21 and R-22 are out of scope by the briefing. R-23 is waived.
- The 3 inherited `harness_threads` surface failures stay local only; I did not edit them. The remote Source jobs pass, because those tests skip without `origin/main`.
- Lint counts at 8da92fb9 equal origin/main 6f5a7310's on every rule. Main was linted in a scratch git copy, and `diff` of the two count lists is empty.
