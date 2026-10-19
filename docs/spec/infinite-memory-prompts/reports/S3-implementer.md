# S3 implementer report: infinite-memory-prompts

Spec: `docs/spec/infinite-memory-prompts/spec.md` r4 · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-prompts` (branch `feat/infinite-memory-prompts`, stacked on `origin/feat/infinite-memory-agent` = `7efceb55`) · Started at `b140af69` · Date: 2026-10-16.

## Rows done (running list; a successor resumes after the last row listed)

- Drift check: `origin/feat/infinite-memory-agent` = `7efceb5504b0d2ac64a3b5874ada635a47ac35cf`; `git diff --stat 7efceb55..origin/feat/infinite-memory-agent -- vidbyte/prompts vidbyte/agents/infinite tests/features/infinite_memory_agent` empty (no drift).
- P1 done: row 1 `32aae37e` (root 1,829 -> 2,424 tik), row 2 `f34ed002` (generator 1,277 -> 1,478), row 3 `307f841b` (verifier 1,059 -> 1,209). Pack after P1: 23 failed (all in the new module, P2-P4 items), 221 passed; no pre-existing test failed.
- P2 done: row 4 `8660e374` (task_prompt 241 -> 1,136 tik), row 5 `de8012e6` (verifier_task_prompt 251 -> 1,135), row 6 `e5487315` (resume_prompt 232 -> 1,123), row 7 `05d96252` (launch_tool_description 416 -> 1,139). Pack after P2: 3 failed (the P3/P4 pins of rows 12, 16, 35), 241 passed.
- P3 done: row 12 `c294030a`, row 16 `8ba1521d`, row 23 `b4372d6a`, row 24 `d968689a`; rows 8-11, 13-15, 17-22, 25-30 verified with no change. Pack after P3: 1 failed (row 35 pin), 243 passed.
- P4 done: row 35 `549d62e7`, row 42 `ce4072cb`; rows 31-34, 36-41, 43 verified with no change. Pack after P4: 244 passed.

## Commits (on `b140af69`, oldest first)

| SHA | Row(s) | Subject |
|---|---|---|
| `32aae37e` | 1 | root system prompt states the nine principles per stage |
| `f34ed002` | 2 | generator system prompt states the principles per stage |
| `307f841b` | 3 | verifier system prompt states the principles per stage |
| `4bb42787` | - | report progress after P1 |
| `8660e374` | 4 | task_prompt carries the generator's start-of-work checklist |
| `de8012e6` | 5 | verifier_task_prompt carries the verifier's start-of-check checklist |
| `e5487315` | 6 | resume_prompt carries the resumed root's checklist |
| `05d96252` | 7 | launch_tool_description carries why and when to delegate and the cross-field card rules |
| `22e4e538` | - | report progress after P2 |
| `c294030a` | 12 | generator_prompt description asks for exactly what the parent will need |
| `8ba1521d` | 16 | remember tool description makes not remembering the default |
| `b4372d6a` | 23 | note_path description keeps one stable path per subject |
| `d968689a` | 24 | write_note text description appends findings as they are made |
| `549d62e7` | 35 | remember_saved reply points longer material to a note |
| `ce4072cb` | 42 | README states the measured prompt sizes |

Verify-only rows have no diff and so no commit; each was read against its §12.3.1 outline and the code truths of §11.

## Row tick list (§12.3)

- [x] 1 root_system_prompt · [x] 2 generator_system_prompt · [x] 3 verifier_system_prompt (P1)
- [x] 4 task_prompt · [x] 5 verifier_task_prompt · [x] 6 resume_prompt · [x] 7 launch_tool_description (P2)
- [x] 8–11 launch_tasks / name / goal / done_criteria: verified, keep nudges present, no change
- [x] 12 launch_generator_prompt_description: "ask for exactly what you will need", never a transcript, which detail belongs in a note
- [x] 13–15 launch_verifier_prompt / context / tools: verified, no change
- [x] 16 remember_tool_description: "The default is not to remember" replaces "Remember only what will matter again"
- [x] 17–22 remember_kind / text / tags / refs / supersedes, write_note_tool: verified, no change
- [x] 23 note_path_description: one stable path per subject, given again to append
- [x] 24 write_note_text_description: "Append findings as you make them"
- [x] 25–30 write_note_file, the three edit_file leaves, the two drop_entry leaves: verified, no change
- [x] 31 result_card: verified (labels, order, placeholders, size unchanged)
- [x] 32 replayed_label, 33 launch_rejected, 34 memory_rejected, 36 remember_staged, 37 note_saved, 38 entry_dropped: verified, keep anchors present, no change (deviation 3)
- [x] 35 remember_saved_prompt: "Keep anything longer in a note." (25 -> 32 tik)
- [x] 39 quota_line, 40 map_header: verified, no change
- [x] 41 infinite_memory.json: verified (40 `{path, source_url}` leaves; the family description is still true)
- [x] 42 `vidbyte/agents/infinite/README.md:68`: about 2,800 / about 5,900 / near 107,000
- [x] 43 `vidbyte/prompts/README.md:67` and `:229-250`: verified still true, no change
- 44–46 are S2 rows; `git diff --stat f4cad411..HEAD -- tests/` is empty.

## The seven behavior assets (chars / est / tik)

| Asset | Before | After | Review ceiling or aim (tik) |
|---|---|---|---|
| root_system_prompt | 8516 / 2129 / 1829 | 11248 / 2812 / 2424 | ≤ 2,600 |
| generator_system_prompt | 6011 / 1503 / 1277 | 6941 / 1736 / 1478 | ≤ 1,900 |
| verifier_system_prompt | 4981 / 1246 / 1059 | 5698 / 1425 / 1209 | ≤ 1,600 |
| task_prompt | 1141 / 286 / 241 | 5374 / 1344 / 1136 | 1,100–1,300 |
| verifier_task_prompt | 1176 / 294 / 251 | 5388 / 1347 / 1135 | 1,100–1,300 |
| resume_prompt | 1090 / 273 / 232 | 5238 / 1310 / 1123 | 1,100–1,300 |
| launch_tool_description | 1977 / 495 / 416 | 5418 / 1355 / 1139 | 1,100–1,300 |

All seven clear est ≥ 1,000 and tik ≥ 1,100. None crosses a review ceiling, and the four expanded assets sit at the low end of their band.

## Sums and bounds

- The 23 compact descriptions, as per-leaf sums: est 4455 -> 4586 (bound 4,900) and tik 3803 -> 3913 (bound 4,183), which is 102.9 % of baseline by both measures.
- All 24 descriptions (the README figure): est 4950 -> 5941.
- Replies: remember_saved is 32 tik / 33 est (≤ 80); the other six are unchanged. The shape leaves are unchanged.
- Per-call prompt load in tiktoken (system prompt + first message + SPARSE schema): root 5,267 -> 6,695; generator 4,956 -> 6,885; verifier 3,346 -> 4,461.
- Run budget: about 0.6M of the 15M-token session budget used across this run and its pre-compaction part; no review ceiling or ask-first threshold was crossed.

## Deviations

1. Root (row 1): the #1113 sentence "Remember only what will matter again, never progress chatter" is merged into the new "The default is not to remember" paragraph, which keeps "never for progress chatter". "Keep a large plan in a note" became "keep the plan in that note", because the plan note is now flow step 2. The `:64` clause is reworded as outline 1.8 directs.
2. Outline 1.3's "the root does the smallest piece itself" at a refused launch is stated once, in §When a call is refused ("do the work yourself at a depth or agent limit"), and not repeated in §What to delegate.
3. Rows 33, 34, 36 and 37: the optional ≤ 1 nudges were not added. Row 33: at an agent limit "do the work yourself" is the true fix, and a "smallest piece" nudge would steer away from it. Row 34: the reply already ends "or move on if the content is not worth keeping". Row 36: "one idea per entry" is already on remember_text. Row 37: a pointer-entry nudge on every note write would push against sparse memory.
4. Row 7: the cross-field card rules sit in §How it behaves, so the four headings stay exactly as they were, with no fifth heading.
5. Gate 4: the global `semgrep` CLI (1.170.1) no longer starts, because the global `mcp` package is 2.3.0 (`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`). The same scan, with the same arguments, ran through a scratch venv (`--system-site-packages` plus `mcp<2`) in the session scratchpad. Nothing in the repo or the global environment changed.

## Gates (run at `ce4072cb`, in order)

1. New module: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` ended `131 passed in 0.97s`.
2. Pack: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` ended `244 passed in 4.77s` (and again `244 passed in 5.34s` after the Phase 7 spec edit).
3. `python lint/run.py` ended `SDK-LINT: PASS`.
4. `git add -A && semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off`, run through the scratch venv (deviation 5), ended `Ran 1 rule on 980 files: 0 findings.` with exit code 0.
5. `python scripts/generate-sdk-public-api.py --check` ended `contracts/sdk-public-api.json is current at 9eca4a33ddb5ea1a21c07f840e556487a8770e19 (vidbyte-sdk 0.3.0, 644 exports).`
6. `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`: lint inside it ended `SDK-LINT: PASS`; pytest ended `3 failed, 6174 passed, 16 skipped in 97.11s` and `CI failed: Command failed with exit code 1: ... python.exe -m pytest`. The three failures are all in `tests/features/harness_threads/test_harness_threads_surface.py` (`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`, `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`). They compare the branch with `git merge-base origin/main HEAD`, and the stacked base `feat/infinite-memory-agent` adds the failure codes, `vidbyte/tools/` files and the `InfiniteMemoryAgent` export they object to. The same file run in a detached worktree at the start commit `b140af69` ended `3 failed, 6 passed in 2.73s`, so these failures come from the base branch and not from this change. The worktree was removed afterwards. The known stdio flake passed.
7. `python scripts/run_ci.py --stage package` (no PYTHONPATH) ended `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.`, exit code 0.

## PR

Draft PR https://github.com/cerredz/Vidbyte-SDK/pull/1176 (base `feat/infinite-memory-agent`, still a draft, body is the placeholder). Spec frontmatter `pr:` set and `status: implemented` in `b45c3e60`; §6.2 AC-11/AC-12 proofs and the §17 S3 row plus implementation deviations in `1a0ca869`.

## Files outside §12.3

None. Besides the assets, the only files changed are `vidbyte/agents/infinite/README.md` (row 42), this report, and the spec's frontmatter, §6.2 and §17 (Phase 7).

## Tricky parts

- Reaching 1,100 tik in the three briefings and the launch description with rules rather than padding. Each section got guidance on how to read that field at that moment, plus the edge cases the code produces: a missing start file, an ambiguous criterion, a partial status, a cut summary, reworded duplicate entries, a same-name relaunch that keeps its finished children, interrupted relaunches that count toward the agent limit again, and a refused call that records nothing.
- Code truths that changed the wording:
  - The verifier never sees the generator_prompt, so a requirement stated only there is never checked.
  - The duplicate-entry check ignores only case and spacing, so a reworded copy gets through.
  - A pair started twice counts twice toward max_agents (`journal.py` edge case).
  - A card's drop reason is fixed text, so the review must say why.
  - Assistant text is trimmed too. A claim that the brief's own sentences survive trimming was cut; the first message itself does stay.
- Within-asset duplicate sentences (INV-15 e) were caught three times during drafting and removed. Restatement across assets was kept where each stage needs the rule.
