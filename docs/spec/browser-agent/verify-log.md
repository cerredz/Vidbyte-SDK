# Verification log: BrowserAgent: JevAgent-shaped agent and runtime for long-running browser tasks

Gate set (from context/code-map.md §1; run from the worktree root, in CI order, with every model key unset):

| # | Gate | Command | Where |
|---|---|---|---|
| 1 | Browser pack (new tests) | `PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q -p no:cacheprovider` (first check `python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` prints the worktree) | local |
| 2 | Lint | `python lint/run.py` → `SDK-LINT: PASS`, A002 at 562, no other rule count up vs S3 | local (also inside gate 5 and remote CI) |
| 3 | Semgrep | `python <scratchpad>/run_semgrep.py scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (global CLI crashes on import) → 0 findings | local; remote in Static policy |
| 4 | Public API contract | `python scripts/generate-sdk-public-api.py --check` | local (C016 also in lint) |
| 5 | Full source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` → only the two known local-only `harness_threads` failures (FailureCode surface; root-`__all__` vs merge-base main) | local |
| 6 | Package stage | `python scripts/run_ci.py --stage package` with no PYTHONPATH → `CI passed` | local |
| 7 | Remote checks | `gh workflow run CI --ref feat/browser-agent` and `gh workflow run "Static policy" --ref feat/browser-agent`, then `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs` → `Source / Python 3.11`, `Source / Python 3.12`, `Package`, Static policy all `completed success` (`gh pr checks` shows nothing for dispatched runs) | remote only |

## Iteration 1 — 2026-10-17 17:06 — agent report: reports/S5-repair-1.md
**Defects in:** R-4, R-2, R-1, R-3 (Major); R-14 (Minor, source); trivial Minors R-6, R-7, R-8, R-9, R-10, R-11. Failing gate: browser pack, `test_an_unpriced_call_raises_usage_accounting_error` (`['run_started', 'goal_set', 'goal_rechecked', 'run_finished']`, `1 failed, 108 passed`), which is R-4. Not handed over: R-15..R-18, R-21, R-22 (follow-ups), R-23 (refuted).
**Hypotheses and attempts:**
- R-4: settle the usage before choosing the terminal event; on `UsageAccountingError` emit `run_stopped` with the error type name and re-raise (the verifier's prototype shape, now in source, `runtime.py` arun). Worked first try: pack 109 passed. Considered moving the settle-and-emit into a `_close_run` helper and rejected it: the step belongs in the narrated main function, and the `with` → `try` nesting is depth 2, under S024's limit of 3. Header edge-case sentence rewritten to match.
- R-14: three shapes considered. (a) Append the preset to the `field_name` passed to `require_text`: rejected, it corrupts `details["field"]` and changes `_received`'s secret-name detection, which keys on the last dotted segment of the field name. (b) Hand-check blank values: rejected, C008 gives primitive validators one owner. (c) Chosen: catch the `ConfigurationError` from `require_text` and re-raise with a message that names `BrowserServerSettings.env[<NAME>]` plus `for the '<preset>' preset` on preset servers only, same `details`, no value quoted. The only failure reachable in that loop is a blank string, because `to_mapping` already refuses non-text values, so the new message ("must not be blank") is exact.
- R-1: a brute-force search over every split found no four-line wrap of the same words within 72 columns, so the block is five evenly filled lines (52–56 columns). Only `base.py:80-84` changed.
- R-2: markers on the first line of the existing comment blocks; `python lint/run.py --rule A002` → `A002 IMPROVED 703 -> 562`.
- R-10: `match` with one `case` per member and no `case _`, as `vidbyte/agents/infinite/journal.py:141` does; `to_enum` returns the enum type, so the match is exhaustive. S009 (mypy) stays at 350.
- R-11: `field(default=None, repr=False)`; positional `BrowserServerSettings(None, ("x",))` still works; settings tests pass.
- R-3: README line 40 qualified and one Notes bullet added; `settings.py:8` softened. The R-3 commit was first made as `docs(...)` and reworded to `fix(...)` before any push.
- No test, spec, baseline, or config was changed; `git diff c56f34bc..HEAD -- tests/` is empty.
**Changes:** `3f909eb3` R-4 · `e3aacaa7` R-2 · `b47b90ac` R-1 · `7a50daea` R-3 · `6a0bdb94` R-14 · `3db1f624` R-6 · `179c7c73` R-7 · `6b6e1ef8` R-8 · `12b1e6c7` R-9 · `3094ba92` R-10 · `57a22077` R-11.
**Gate matrix out (local, at `57a22077`):**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | `PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q -p no:cacheprovider` | PASS | `109 passed in 1.37s` (import path: `...\worktrees\vidbyte-sdk-browser-agent\vidbyte\__init__.py`) |
| lint | `python lint/run.py` | PASS | `A002 intent-comments 562 703 IMPROVED` … `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`; every rule at or below its baseline; no finding in any touched browser file |
| semgrep | `python run_semgrep.py scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `Findings: 0 (0 blocking)` / `Targets scanned: 996` / `Ran 1 rule on 996 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 8183aa6f… (vidbyte-sdk 0.3.0, 648 exports).` |
| full local gate (source) | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS except the 2 known local-only | `FAILED …test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 148 == 120`) / `FAILED …::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` (root `__all__` vs merge-base main: `'BrowserAgent' != 'JevAgent'`) / `2 failed, 6349 passed, 16 skipped in 101.02s` |
| package | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| remote checks | dispatched CI + Static policy | see "Remote" below | |

**Remote (dispatched on `54d23757`, which holds every code commit above):** CI run 39069591066 and Static policy run 39069592426, `headSha` `54d23757f814216ccd6edbaadc9c1ca399f1668d` confirmed before watching; `gh run watch --exit-status` → `CI exit=0`, `Static exit=0`; `gh api repos/cerredz/Vidbyte-SDK/commits/54d23757f814216ccd6edbaadc9c1ca399f1668d/check-runs` → `Package completed success` / `Static policy completed success` / `Source / Python 3.11 completed success` / `Source / Python 3.12 completed success`. The docs-only commit that records this (adds reports/S5-repair-1.md and this paragraph) is re-dispatched on its own head; its run IDs are in the S5 STATUS block.
**Still open:** none of the handed-over findings; every gate green. Follow-ups R-15..R-18, R-21, R-22 stay open by instruction; R-23 refuted.
