# Verification log: Rewrite and expand the InfiniteMemoryAgent prompt family so every prompt reinforces the agent's intended behavior

Gate set (from context/code-map.md §1 and the S5 briefing; all local, run from the worktree root; GitHub Actions are disabled repo-wide, so there are no remote checks):
1. new module — `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` → 131 passed
2. feature pack — `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → 244 passed
3. custom lint — `python lint/run.py` → `SDK-LINT: PASS`
4. semgrep — after `git add -A`, the scratchpad venv runner `semgrep-venv/Scripts/python.exe run_semgrep.py` (same arguments as `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off`; the global CLI is broken by global `mcp` 2.3.0) → `Ran 1 rule on 980 files: 0 findings.`
5. public API — `python scripts/generate-sdk-public-api.py --check` → current
6. full gate, source — `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` → only the 3 inherited `harness_threads` surface failures (reproduced at base 7efceb55)
7. full gate, package — `python scripts/run_ci.py --stage package` (no PYTHONPATH) → `CI passed.`
8. measure — `python <scratchpad>/measure_seven.py <worktree>` (all seven ≥ 1,000 est and ≥ 1,100 tik; 23-description sum ≤ 4,183 tik / ≤ 4,900 est)
- remote — `gh pr checks 1176` → none (Actions disabled); the local gates are the gates of record.

## Iteration 1 — 2026-10-17 03:28 — agent report: reports/S5-repair-1.md

**Defects in:** confirmed R-1 (Blocker), R-2, R-3, R-4, R-5, R-6 (Majors); Minors the orchestrator added: R-7, R-8, R-9, R-10, R-11, R-12, R-13 (root `:13` part only), R-19, R-26. No failing gate at entry (358bfadf: 131 / 244 / `SDK-LINT: PASS` / semgrep 0 / API current / source 3 inherited failures / package `CI passed.`).

**Hypotheses and attempts:**
- Reproduced every Blocker and Major in code before editing: `launch.py:309` (`_verifier_message` formats no entries or paths) for R-1; `workspace.py:219-229` plus `constants/infinite.py:71`, `:135` (map cut at its cap, "… and {count} more files") for R-2; `agents/runtime.py:2002-2005` and `:371-378` (a max_iterations stop returns normally), `infinite/runtime.py:101` (`journal.finish`), `journal.py:89-90` (finished run refuses to resume), `runtime.py:1649-1650` and `infinite/settings.py:126` (the root sees `max_iterations n/limit`, set by default) for R-6's new sentence. R-3, R-4 and R-5 are text-vs-text contradictions; each was shown by grep before the edit and gone after it.
- Applied the verifier's fix texts verbatim, in the verifier's order (R-1 before R-10 in launch `:13`; R-6's turn-limit rule only in resume, R-18 left a follow-up). Every measured result matched the verifier's what-if numbers to the token: generator 1,490, verifier 1,216, task 1,142, resume 1,137, launch 1,123; verifier_task 1,149 after R-3 + R-4 and +11 for R-12 → 1,160; root 2,452 after R-5, +20 (R-11) → 2,472, −12 (R-13) → 2,460, +5 (R-26) → 2,465; the 23-description sum 3,906.
- R-11: considered writing outline 1.6's ban with the literal words "never save a card's status or progress"; kept the verifier's measured wording ("Keep its status and progress in the plan note, never in an entry"), which states the same ban and which the orchestrator approved. Not a pin for root.
- R-26 moved the root prompt's estimate from 2,849 to 2,854, which rounds to 2,900 under AC-11, so `vidbyte/agents/infinite/README.md:68` "about 2,800 tokens" became false. No R-26 wording can stay under 2,850 (it would need ≤ 2 added characters), so the README figure was corrected in the same commit. The other two figures stay true (24 descriptions 5,915 est → about 5,900; 90,000 + 2,854 + 5,915 + 8,000 = 106,769 → near 107,000).
- The Edit tool rewrites a touched file with LF endings in the CRLF working tree; git warns "LF will be replaced by CRLF". Harmless: the index is LF and every measure goes through `Prompts().get`.
- `lint/run.py` prints `S063 IMPROVED 4 -> 3`; S063 is an AST rule over `vidbyte/**/*.py` (gather exceptions), and this repair changed no Python, so it is inherited; the baseline was not touched.
- New observation, not fixed (outside the packet): two base sentences make the same claim R-2 fixed in task_prompt. `note_path_description.md:7` "because the workspace map lists every file by its path" and `root_system_prompt.md:58` "one line per file with its size and description" are false once the map is cut at `INFINITE_MAP_MAX_TOKENS`. Both predate this PR (`origin/feat/infinite-memory-agent`), so a reword needs an INV-19 note.

**Changes:**
| Finding | Commit | Asset(s) | tiktoken before → after |
|---|---|---|---|
| R-1 | `a2ae814c` | launch `:13` | 1,139 → 1,149 |
| R-2 | `032dc49f` | task `:41` | 1,136 → 1,142 |
| R-3 | `572667bf` | ver `:11`, vtask `:51` | 1,209 → 1,216; 1,135 → 1,141 |
| R-4 | `d67bfadc` | task `:17`, vtask `:35` | 1,142 → 1,142; 1,141 → 1,149 |
| R-5 | `e04d62ea` | root `:20`, `:48`, `:3` | 2,424 → 2,452 |
| R-6 | `0253ed07` | resume `:25`, step 6 | 1,123 → 1,137 |
| R-7 | `08c412e0` | gen `:52` | 1,478 → 1,482 |
| R-8 | `7b5c9616` | gen `:37` | 1,482 → 1,490 |
| R-9 | `65c8884c` | note_path `:7` | 189 → 182 (sum 3,913 → 3,906) |
| R-10 | `6647ca4e` | launch `:13` | 1,149 → 1,123 |
| R-11 | `60cf9597` | root `:54` | 2,452 → 2,472 |
| R-12 | `19203993` | vtask `:17` | 1,149 → 1,160 |
| R-13 (root `:13`) | `347c8930` | root `:13` | 2,472 → 2,460 |
| R-19 | `5699f96e` | remember_staged_prompt | → 42 tik / 47 est (≤ 80) |
| R-26 | `689599d3` | root `:16`; README `:68` | 2,460 → 2,465 |

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` | PASS | `131 passed in 0.91s` |
| feature pack | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS | `244 passed in 4.66s` |
| lint | `python lint/run.py` | PASS | `S063 IMPROVED 4 -> 3 …` · `S064 RATCHETED: 4 known finding(s) …` · `SDK-LINT: PASS` |
| semgrep | venv `run_semgrep.py` after `git add -A` | PASS | `Ran 1 rule on 980 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 9eca4a33… (vidbyte-sdk 0.3.0, 644 exports).` |
| full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS except the 3 inherited `harness_threads` surface failures (reproduced by the orchestrator at base 7efceb55, `3 failed, 6 passed`; this repair touches no Python, root export, `vidbyte/tools` or `vidbyte/lib/configs`) | `SDK-LINT: PASS` (step 2) · `FAILED …test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `FAILED …test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` · `FAILED …test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` · `3 failed, 6174 passed, 16 skipped in 98.09s` (the Windows stdio flake did not fire) |
| full local gate, package | `python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| measure | `python <scratchpad>/measure_seven.py <worktree>` | PASS | root 2,854 est / 2,465 tik · generator 1,747 / 1,490 · verifier 1,434 / 1,216 · task 1,349 / 1,142 · verifier_task 1,373 / 1,160 · resume 1,323 / 1,137 · launch 1,338 / 1,123 · 23-description sums est 4,577 / tik 3,906 |
| remote checks | `gh pr checks 1176` | none | GitHub Actions disabled repo-wide; local gates are the gates of record |

**Still open:** no packet item. Follow-ups left as review.md records them: R-13 (vtask `:25`, resume `:1` parts), R-14 to R-18, R-20 to R-25. New observation for the orchestrator (not a packet item): note_path `:7` and root `:58` are base sentences that say the map lists every file, false past the map cap (the R-2 class); see Hypotheses.
