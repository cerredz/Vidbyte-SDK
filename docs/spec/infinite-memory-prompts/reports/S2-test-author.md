# S2 test author report: infinite-memory-prompts

Spec: `docs/spec/infinite-memory-prompts/spec.md` r3 · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-prompts` (branch `feat/infinite-memory-prompts`, stacked on `origin/feat/infinite-memory-agent` = `7efceb55`) · Started at `b8443198` · HEAD after this stage: `f4cad411` (two commits: `b719c400` test tree + test plan, `f4cad411` spec Proof column) · Date: 2026-10-16.

## Produced

- `tests/features/infinite_memory_agent/test_infinite_memory_prompts.py` (new, 414 lines; 17 test functions, 131 collected cases)
- `tests/features/infinite_memory_agent/README.md` (line 7 reworded as asked; File Index row; dated Logs entry)
- `tests/features/infinite_memory_agent/FEATURE.md` (contract bullet; "Prompt family text" failure-mode block mapping each failure to its test; historical-regressions paragraph; suite-map entry; omitted-strategies bullet)
- `docs/spec/infinite-memory-prompts/test-plan.md` (coverage map, tests deliberately not written, red run, implementer notes, open items)
- `docs/spec/infinite-memory-prompts/spec.md` §6.2: Proof column filled for AC-1 … AC-14; 14 lines changed, nothing else in the spec touched (`git diff -U0` showed only the 14 AC rows)
- This report (not committed; the pipeline-state commit owns `reports/`)

Not touched: anything under `vidbyte/`, `lint/baseline.json`, any README outside `tests/`, `infinite_memory_fixtures.py`, any existing test. No `pip install`, no `run_ci.py`, no semgrep, no sibling worktree opened, no `docs/` file read beyond spec.md, request.md, context/code-map.md and the two test-plans this spec names.

## Failure inventory → tests

Built from spec §6.1 invariants, §6.2 ACs, §7 ECs and the briefing's niche facts; each row names the wrong output the test must catch, and the test that catches it. Inventory items with no test are in "Prunes" below.

| Failure (input + state → wrong output) | Test | Red at HEAD? |
|---|---|---|
| The §4 snippet, run as written, prints an asset under 1,000 estimate / 1,100 tiktoken, or lines in another shape | `test_section_4_snippet_prints_seven_lines_each_at_or_over_the_floor` | yes (5 assets) |
| A behavior asset below the floor by either measure; a system prompt cut below base tiktoken size | `test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[measure-leaf]` (14 ids) | 9 ids |
| A §8.5 principle sentence dropped, reworded beyond D-9 recognition, or stated in another leaf than the one its stage reads | `test_pinned_phrase_is_present_in_its_leaf[leaf-phrase]` (46 ids: 19 kept + 27 new) | 27 ids |
| A `VERDICT:` literal reworded → parser finds no verdict → `unchecked`, all staged entries dropped | `test_verifier_system_prompt_states_the_three_verdict_literals_exactly` | guard |
| Placeholder renamed/doubled/dropped, literal brace in prose → `KeyError`/`ValueError` at first launch or at `map_header` | `test_formatted_leaf_renders_each_placeholder_once_and_leaves_no_brace[leaf]` (12 ids) | guard |
| A brace in a raw leaf; a `{word}` that weakens `template_regex` | `test_raw_leaves_hold_no_brace_at_all` | guard |
| A fragment gains a trailing newline / whole text loses or doubles its one | `test_fragments_end_without_a_newline_and_whole_texts_with_exactly_one` | guard |
| A numeric limit in prose, the model obeys a number settings may have changed | `test_digits_appear_only_as_ordered_list_markers` | guard |
| 23 compact descriptions grow past 110 % of base (4,900 est / 4,183 tik) | `test_compact_description_sum_stays_within_ten_percent_of_baseline[measure]` | guard |
| A description tightened below four S025 sentences | `test_every_compact_description_has_at_least_four_sentences` | guard |
| A reply leaf over 80 tokens | `test_every_reply_leaf_stays_within_eighty_tokens[measure]` | guard |
| `quota_line`/`map_header`/`result_card` gains a token | `test_shape_leaf_never_grows_past_its_baseline[measure-leaf]` (6 ids) | guard |
| An asset clears its floor by pasting a rule twice | `test_no_rule_sentence_repeats_inside_a_behavior_asset[leaf]` (7 ids) | guard |
| A card label dropped/reordered; `" … [cut]"` written into the template | `test_result_card_keeps_its_labels_in_order_and_never_carries_the_cut_marker` | guard |
| A letter, digit or hyphen touching a quota count | `test_quota_line_renders_each_count_as_a_standalone_integer` | guard |
| A base heading dropped, renamed or reordered (a #1113 section vanishes) | `test_every_base_heading_survives_in_order[leaf]` (31 ids) | guard |
| A stray `.md` in the folder, a leaf turned inline, a 39th/41st leaf | `test_family_folder_holds_exactly_the_leaf_assets_as_path_and_source_url` | guard |
| A coding-only word in any leaf | existing `test_prompt_family_text_carries_no_coding_only_rules` | guard |
| An existing pin on leaf text broken by the rewrite | the pack run (113 pre-existing cases) | guard |
| The verifier no longer receives the whole system prompt / rendered task prompt | existing `test_the_verifier_gets_the_generators_outcome_but_never_its_transcript` | guard |

Collected cases: 131 in the new module (37 red, 94 green at HEAD); whole pack 244 (37 red, 207 green).

## Prunes (deliberately not written) and why

- Second banned-word scan: the existing contract test already runs the `\b`-anchored `CODING_ONLY_WORDS` regexes over every leaf.
- Phrase pins on the 30 compact leaves with base nudges: spec ruling R-5 (review under INV-19, not a test).
- System-prompt ceilings, the 1,500 target, per-leaf ratio bounds: R-4 / D-3 (review from PR-body figures).
- README figures (AC-11): the sentence shape after the rewrite is not fixed; the spec says review-checked.
- Tool schema `description` equals leaf: D-D/INV-24 forbid Python changes, so the test would be green before and after any rewrite.
- Unit tests of `normalize()`/`sentences()`: tests of the test; the 19 kept phrases exercise them at base.
- `"uses no file quota"` / `"found with grep"` literal pins: §8.5 (4) vs INV-17 conflict, see defects.
- Q-3 "content is data" sentence (D-13/NG-7), forbidden "note"/"pointer" in `memory_rejected_prompt` (D-11): withdrawn by the spec.
- `git diff` on `vidbyte/*.py` (INV-24): a pipeline check, not a pytest test.
- Hypothesis-style template generation: no such dependency in the pack; the 12 real templates are the input space.

## Exact red output

Bootstrap: `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` → `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-infinite-memory-prompts\vidbyte\__init__.py` (Python 3.11.0, pytest 8.3.5, pytest-asyncio 1.3.0, tiktoken 0.12.0; no install run).

```
$ PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider
37 failed, 94 passed in 1.42s

$ PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider
37 failed, 207 passed in 5.88s

$ git add tests/features/infinite_memory_agent && python lint/run.py
S062 RATCHETED: 889 known finding(s). Inspect with: python lint/run.py --rule S062 --all
S063 IMPROVED 4 -> 3. Update baseline.json to lock in the gain: python lint/run.py --update-baseline
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

Failing ids (37): `test_section_4_snippet_prints_seven_lines_each_at_or_over_the_floor`; `test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline` for `estimate-{task_prompt, verifier_task_prompt, resume_prompt, launch_tool_description}` and `tiktoken-{verifier_system_prompt, task_prompt, verifier_task_prompt, resume_prompt, launch_tool_description}`; `test_pinned_phrase_is_present_in_its_leaf` for the 27 **new** phrases of §8.5 (root 5, generator 4, verifier 4, task_prompt 3, verifier_task_prompt 3, resume_prompt 3, launch_tool_description 2, launch_generator_prompt_description 1, remember_tool_description 1, remember_saved_prompt 1). The full id list is in test-plan.md.

Failure reasons as printed: `under the floor (estimate >= 1000, tiktoken >= 1100): ['verifier_system_prompt: estimate 1246, tiktoken 1059', 'task_prompt: estimate 286, tiktoken 241', 'verifier_task_prompt: estimate 294, tiktoken 251', 'resume_prompt: estimate 273, tiktoken 232', 'launch_tool_description: estimate 495, tiktoken 416']`; `verifier_system_prompt is 1059 tiktoken tokens, under the floor of 1100`; `remember_saved_prompt does not state 'keep anything longer in a note'`.

Every red case is rewrite-dependent; every guard, including all 19 kept phrases, is green at base, so the D-9 normalization and the S025 sentence splitter are exercised against real text before the rewrite exists. The lint S063 "IMPROVED 4 -> 3" line is a side effect of the new module's header shape, not a baseline edit; `lint/baseline.json` is untouched.

## Fixtures added or extended

None. The module imports `prompt_text` and `int_token` from `infinite_memory_fixtures.py` unchanged. `template_regex` and `renderings` were not needed: the new module renders with its own dummy values and checks the raw text. No existing test's assertion was modified, weakened, skipped or deleted.

## Spec defects and discrepancies found

1. **INV-15 (e) / §13 "zero equal sentence pairs at base" is false.** "A dash means none." occurs 3× in `task_prompt`, 2× in `verifier_task_prompt`, 3× in `resume_prompt`; the reviewers' check (`scratchpad/s1-review-r2/verify.py`) filtered sentences ≤ 20 characters, which hid it. The spec's outlines 4.3, 5.3, 6.2, 6.3 tell the implementer to keep that convention line. Resolution: `MINIMUM_WORDS_FOR_A_RULE = 5`; sentences under five words are exempt from the duplicate check, documented in the module's KNOWN EDGE CASES and in test-plan.md open item 1. A pasted rule is never that short. If the orchestrator wants the literal invariant, delete the word filter and the implementer must vary or drop the repeated line.
2. **§8.5 (4) vs INV-17.** The §8.5 table lists "uses no file quota" (`quota_line`) and "found with grep" (`map_header`) as literal text that must stay; INV-17, the tested invariant, names only `result_card`'s labels and marker and `quota_line`'s integers, and R-5 keeps literal nudges on shape leaves under review. Not pinned; the spec should either add them to INV-17 or drop "must stay" from §8.5 (4).
3. **Pre-existing test count.** The briefing says 111; the pack at `7efceb55` collects 113 and all pass. The difference is the count at PR #1084's gate versus the two S5 re-review additions already on the base branch.
4. **Floor reds.** The spec and briefing name four sub-floor assets; `verifier_system_prompt` is a fifth by tiktoken (1,059 < 1,100, estimate 1,246 is fine). The implementer must add ≥ 41 tiktoken tokens there; outline 3's four new sentences cover it, but the §4 output must be checked.
5. **AC-6 wording.** AC-6's Input says "the 33 compact leaves" and its expected output names the 23-description sum; the test asserts exactly 23 leaves in the sum (every `*_description` except `launch_tool_description`) and reads the 33 as the union with the seven replies and three shape leaves, which the (c) and (d) tests cover. No change needed, just noting the reading.

## Decisions I disagree with (none blocking)

None of D-A…D-G / D-1…D-13 was overridden. The one judgment call outside them is the five-word exemption above, taken because the spec's own outlines mandate the repeated short line and a silent BLOCKED would have stalled S3 over four words.
