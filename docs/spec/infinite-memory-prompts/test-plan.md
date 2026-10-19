# Test plan: Rewrite and expand the InfiniteMemoryAgent prompt family so every prompt reinforces the agent's intended behavior

Spec: `docs/spec/infinite-memory-prompts/spec.md` r3 · Framework: pytest 8.3.5 with pytest-asyncio 1.3.0; tiktoken 0.12.0 optional (guarded by `importlib.util.find_spec`, skipped with a message when absent) · Prior art copied: `tests/features/infinite_memory_agent/test_infinite_memory_contract.py` (A001 header shape, `EXPECTED_LEAVES` discipline, offender-list assertions), `infinite_memory_fixtures.py` (`prompt_text`, `int_token`), `tests/features/jev_bulk_work/test_jev_bulk_work.py:289` (guarded tiktoken), `lint/rules/s025_model_facing_description_depth.py:29,185-200` (`ABBREVIATIONS`, `SentenceCounter`, copied because `lint/` is not importable from tests), `test_infinite_memory_acceptance.py` (the §4 snippet pasted as printed between marker comments).

New module: `tests/features/infinite_memory_agent/test_infinite_memory_prompts.py` — 17 test functions, 131 collected cases (parametrized by leaf, phrase and measure). All cases are pure text checks through `Prompts().get`; no model, no network, no subprocess, no file bytes.

"Red at HEAD" below means the case fails at `b8443198` (assets identical to `base_commit` `7efceb55`) for the stated reason and turns green only when the rewrite lands. "Guard" means the case is green at HEAD by design and turns red only if the rewrite breaks what it names.

## Coverage map

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1, G-2, FR-2, NFR-6 | `test_infinite_memory_prompts.py` → `test_section_4_snippet_prints_seven_lines_each_at_or_over_the_floor` | acceptance | The §4 snippet, run as printed, shows an asset under 1,000 estimate or 1,100 tiktoken, or prints a line in another shape → the developer's documented check is false. **Red at HEAD** for `verifier_system_prompt` (tiktoken 1,059), `task_prompt`, `verifier_task_prompt`, `resume_prompt`, `launch_tool_description` | It parses exactly seven lines by regex in the spec's order, requires the tiktoken column to be numeric when tiktoken is importable, and collects every short line; an empty capture or a wrong order fails |
| INV-14, AC-7, FR-2, D-2, D-8 | → `test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[estimate\|tiktoken-<leaf>]` (14 ids) | contract | An asset under the floor by either measure, or a system prompt cut below its base tiktoken size → a thinner brief than the user asked for; an estimate-only floor hiding an asset under 1,000 real tokens. **Red at HEAD**: 9 ids (the four sub-floor assets by both measures; `verifier_system_prompt` by tiktoken) | Each id asserts one number against a spec constant; the tiktoken id skips, never passes, when tiktoken is absent |
| INV-16, AC-4, FR-11, D-4, D-9 | → `test_pinned_phrase_is_present_in_its_leaf[<leaf>-<phrase>]` (46 ids over the ten INV-16 leaves) | contract | A principle's rule dropped, reworded past recognition, or placed in a leaf other than the one its stage reads → the behavior is not stated where it acts. **Red at HEAD**: the 27 phrases §8.5 marks **new**; the 19 **kept** phrases are guards | One phrase per id, matched inside that leaf only after D-9 normalization (lowercase; ’ ‘ “ ” folded; `*`, `_`, backtick, `,` removed; whitespace collapsed); a phrase moved to another leaf does not satisfy its id |
| INV-6, AC-4, EC-8 | → `test_verifier_system_prompt_states_the_three_verdict_literals_exactly` | contract (guard) | A `VERDICT:` literal reworded or lost → the parser finds no verdict, the pair is `unchecked`, every staged entry is dropped | Exact, case-sensitive substring of each of the three literals; any one missing names it |
| INV-11, AC-3, EC-1, T-1 | → `test_formatted_leaf_renders_each_placeholder_once_and_leaves_no_brace[<leaf>]` (12 ids) | property (guard) | A renamed, doubled or dropped placeholder, or a literal `{`/`}` in prose → `KeyError`/`ValueError` at the first launch, `map_header` and `resume_prompt` raise before a run starts | `Formatter().parse` must yield exactly the documented list (duplicates fail the list equality), `str.format` with one dummy per name must run, each dummy must appear exactly once, and no brace may survive the render |
| INV-11, INV-22, AC-3 | → `test_raw_leaves_hold_no_brace_at_all` | contract (guard) | A brace in one of the 28 raw leaves → mistaken for a placeholder, or a `{word}` that silently weakens `template_regex` | Collects every offender over the real family; the set of raw leaves is the family minus `PLACEHOLDERS` |
| INV-12, AC-8, EC-2 | → `test_fragments_end_without_a_newline_and_whole_texts_with_exactly_one` | contract (guard) | A fragment gains a trailing newline, or a whole text loses its one newline or gains two → blank lines in every tool result and the map | Checks all 40 against the 13/27 split; offenders listed by name |
| INV-13, AC-5, EC-3, NG-10, D-6 | → `test_digits_appear_only_as_ordered_list_markers` | contract (guard) | A numeric limit quoted in prose → the model obeys a number the settings may have changed | Strips only `^\d+\. ` markers and reports every token still holding a digit |
| INV-8, AC-5, EC-4 | `test_infinite_memory_contract.py` → `test_prompt_family_text_carries_no_coding_only_rules` (existing) | contract (guard) | A coding-only word in any leaf | Existing `CODING_ONLY_WORDS` scan over every leaf; not duplicated |
| INV-15 (a), AC-6, EC-7, NFR-1, D-3 | → `test_compact_description_sum_stays_within_ten_percent_of_baseline[estimate\|tiktoken]` | contract (guard) | The 23 compact descriptions grow past 110 % of baseline (≤ 4,900 estimate, ≤ 4,183 tiktoken as per-leaf sums) → the growth rides in every model call of every agent | Asserts the set is exactly 23 leaves before summing; prints every per-leaf count on failure |
| INV-15 (b), AC-6, FR-6 | → `test_every_compact_description_has_at_least_four_sentences` | contract (guard) | A description tightened below four S025 sentences → a label where the model needs operating knowledge | S025's own terminal rule and abbreviation list; offenders listed with their counts |
| INV-15 (c), AC-6, FR-7, NFR-2 | → `test_every_reply_leaf_stays_within_eighty_tokens[estimate\|tiktoken]` | contract (guard) | A reply over 80 tokens → paid on every tool result | Both measures over all seven replies; offenders listed |
| INV-15 (d), AC-6, FR-8, NFR-2 | → `test_shape_leaf_never_grows_past_its_baseline[estimate\|tiktoken-<leaf>]` (6 ids) | contract (guard) | `quota_line`, `map_header` or `result_card` grows by even one token → every memory reply, every map, every card pays it | One number per id against the spec's baseline |
| INV-15 (e), AC-7, EC-11, NFR-4, A-7 | → `test_no_rule_sentence_repeats_inside_a_behavior_asset[<leaf>]` (7 ids) | contract (guard) | An asset clears the floor by pasting a rule twice → tokens with no behavior gain | Splits on the S025 boundaries, normalizes by D-9, reports every repeated sentence of five or more words (see Open item 1 for why under five words is exempt) |
| INV-17, AC-10, EC-5 | → `test_result_card_keeps_its_labels_in_order_and_never_carries_the_cut_marker` | contract (guard) | A card label dropped or reordered; the marker `" … [cut]"` written into the template → the parent misreads cards; NFR-7's test counts five markers | Finds each of the eight literals and asserts their positions are increasing |
| INV-17, AC-10, EC-6 | → `test_quota_line_renders_each_count_as_a_standalone_integer` | contract (guard) | A letter, digit or hyphen touching a quota count → the count is unreadable and `int_token` fails in the workspace test | Renders with four distinct values and checks each with the pack's own `int_token` |
| INV-19, AC-13, EC-15, EC-16, D-5 | → `test_every_base_heading_survives_in_order[<leaf>]` (31 ids: the seven assets plus the 24 descriptions) | contract (guard) | A heading dropped, renamed or reordered → the principle × stage matrix no longer locates its rule; a #1113 section vanishes | Subsequence check: every base heading in order, extra headings allowed between |
| INV-10, AC-2, NG-2, D-D | → `test_family_folder_holds_exactly_the_leaf_assets_as_path_and_source_url` | contract (guard) | A stray `.md` in the folder, a leaf turned into inline JSON text, a 41st or 39th leaf → an asset ships that no enum names, or the 40-leaf contract breaks | Compares the folder listing, the JSON records and the catalog's family keys three ways |
| AC-2, INV-10 | `test_infinite_memory_contract.py` → `test_prompt_family_has_exactly_the_forty_documented_leaves` (existing) | contract (guard) | A leaf missing, blank, or without its enum member | Existing; the new folder test adds the on-disk and `{path, source_url}` halves |
| AC-9, INV-21 | the pack run: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | regression | Any existing pin on leaf text (all through `template_regex(prompt_text(leaf))` or schema `fullmatch`) broken by the rewrite | 113 pre-existing cases pass at HEAD unchanged; no existing assertion was edited |
| AC-14 | `test_infinite_memory_delegation.py` → `test_the_verifier_gets_the_generators_outcome_but_never_its_transcript` (existing) | integration (guard) | The verifier's system string no longer carries the whole `verifier_system_prompt`, or its first message loses the rendered `verifier_task_prompt` content | Existing; tracks the asset through `template_regex` |
| AC-11, INV-20 | review of the PR body (no test) | — | README figures false after the rewrite | See "Tests deliberately NOT written" |
| AC-12 | the gate (`python lint/run.py`, semgrep, `generate-sdk-public-api.py --check`, `run_ci.py --stage source` / `--stage package`) | — | — | Run by S3/S5; `python lint/run.py` ended `SDK-LINT: PASS` with the new module tracked (A001 header, S020 File Index row) |

Also served: `NFR-7` (the new module runs in about 1.4 s, no model or subprocess); `T-1` (AC-3 cases); `EC-12`/`EC-13` (the tiktoken skip and the catalog-only reads are properties of the module, not tests).

## Tests deliberately NOT written

| Candidate | Why it would not earn its keep |
|---|---|
| A second banned-word scan in the new module | `test_prompt_family_text_carries_no_coding_only_rules` already runs the exact `\b`-anchored `CODING_ONLY_WORDS` regexes over every leaf (so "repository" inside a longer word does not fire and "repos" does); a copy re-proves it and nobody may delete the original |
| A phrase pin on the 30 compact leaves whose nudges exist at base (`launch_tasks_description` … `replayed_label`) | Spec r2 ruling R-5: review guidance under INV-19, not a test; a pin would semi-freeze #1113 wording this PR does not change |
| System-prompt ceilings (root 2,600 / generator 1,900 / verifier 1,600), the 1,500 upper target, per-leaf ratio bounds | Spec r2 ruling R-4 and D-3: review thresholds read from the PR-body figures; a tested ceiling would fail the next earned sentence for no behavioral reason |
| README size figures (AC-11, INV-20) | The README sentence's shape after the rewrite is not fixed, so a parser would pin wording the spec leaves free; the spec itself says review-checked from the PR body |
| Each tool schema's `description` equals its leaf (`remember`, `write_note`, `edit_file`, `drop_entry`) | No Python changes (D-D, INV-24), so no drift is possible in this PR; the seven launch card fields are already `fullmatch`ed by the contract module; the test would be green before and after any rewrite |
| A unit test of `normalize()` / `sentences()` (the D-9 and S025 helpers) | Tests the test; the helpers are three functions copied from the spec and the lint rule, and every phrase id exercises them at base (all 19 kept phrases are found, which fails if the comma or quote folding is wrong) |
| "uses no file quota" in `quota_line` and "found with grep" in `map_header` as literal pins | §8.5 (4) lists them as "literal text that must stay", but INV-17 (the tested invariant) names only `result_card`'s labels and `quota_line`'s integers, and R-5 keeps literal nudges on the shape leaves under review; reported as Open item 2 |
| A Q-3 "content is data" sentence | Spec D-13 / NG-7: not built, must not be tested for |
| A forbidden-word test on "note"/"pointer" in `memory_rejected_prompt` | Withdrawn by the spec (r1-6, D-11): the base EC-18 test reads the advice from the code's problem text |
| `git diff` against `base_commit` for `vidbyte/*.py` (INV-24) | A pipeline check, not a pytest test; S3/S5 and the PR author diff the tree |
| Hypothesis-style generation of templates | No `hypothesis` dependency (pack convention); the 12 real templates are the input space |

## Red run (before implementation)

Bootstrap: none needed (no install). Check that the worktree's package wins: `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` → `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-infinite-memory-prompts\vidbyte\__init__.py` (Python 3.11.0, pytest 8.3.5, pytest-asyncio 1.3.0, tiktoken 0.12.0).

```
$ PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider
FAILED ...::test_section_4_snippet_prints_seven_lines_each_at_or_over_the_floor
FAILED ...::test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[estimate-task_prompt]
FAILED ...::test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[estimate-verifier_task_prompt]
FAILED ...::test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[estimate-resume_prompt]
FAILED ...::test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[estimate-launch_tool_description]
FAILED ...::test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[tiktoken-verifier_system_prompt]
FAILED ...::test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[tiktoken-task_prompt]
FAILED ...::test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[tiktoken-verifier_task_prompt]
FAILED ...::test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[tiktoken-resume_prompt]
FAILED ...::test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline[tiktoken-launch_tool_description]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[root_system_prompt-the default is not to remember]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[root_system_prompt-check each deliverable against the cards]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[root_system_prompt-a card is not memory]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[root_system_prompt-never end your turn to ask]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[root_system_prompt-trimming is not a reason to remember]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[generator_system_prompt-the default is not to remember]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[generator_system_prompt-check each criterion before you reply]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[generator_system_prompt-state plainly what is not done]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[generator_system_prompt-trimming is not a reason to remember]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[verifier_system_prompt-drop what is not worth keeping]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[verifier_system_prompt-the workspace is the record]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[verifier_system_prompt-say what you fixed]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[verifier_system_prompt-trimming is not a reason to remember]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[task_prompt-wrong or slower without it]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[task_prompt-keep a note as you go]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[task_prompt-nothing the parent does not need]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[verifier_task_prompt-nothing below has been checked yet]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[verifier_task_prompt-check them in place]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[verifier_task_prompt-stage only what the generator missed]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[resume_prompt-compare the deliverables with the finished cards]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[resume_prompt-never save a card's status or progress]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[resume_prompt-no one will answer during the run]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[launch_tool_description-only the result card comes back]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[launch_tool_description-never ask for a transcript]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[launch_generator_prompt_description-ask for exactly what you will need]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[remember_tool_description-the default is not to remember]
FAILED ...::test_pinned_phrase_is_present_in_its_leaf[remember_saved_prompt-keep anything longer in a note]
37 failed, 94 passed in 1.42s
```

Reasons, quoted from the failures: `under the floor (estimate >= 1000, tiktoken >= 1100): ['verifier_system_prompt: estimate 1246, tiktoken 1059', 'task_prompt: estimate 286, tiktoken 241', 'verifier_task_prompt: estimate 294, tiktoken 251', 'resume_prompt: estimate 273, tiktoken 232', 'launch_tool_description: estimate 495, tiktoken 416']`; `verifier_system_prompt is 1059 tiktoken tokens, under the floor of 1100`; `remember_saved_prompt does not state 'keep anything longer in a note'`. Every red case is rewrite-dependent (the §4 snippet, the 9 floor ids, the 27 new-phrase ids); every guard (94 cases, including all 19 kept phrases) is green.

```
$ PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider
37 failed, 207 passed in 5.88s
```

207 passed = the 113 pre-existing cases (the briefing's "111" is the count at PR #1084's gate; the pack at `7efceb55` collects 113 and all pass) + 94 new guards. No pre-existing case fails.

```
$ python lint/run.py        (after `git add tests/features/infinite_memory_agent`; the lint catalog reads git ls-files)
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

## Notes for the implementer

- **Names and numbers the tests bind to** (all from spec §8.5, §6.1 INV-11…INV-17, §12.3.1; none may change without a spec revision): the 40 leaf names; the placeholder sets in `PLACEHOLDERS`; the 13 fragments (12 formatted leaves + `replayed_label`) without a trailing newline and the 27 others with exactly one; the floors 1,000 estimate / 1,100 tiktoken; the tiktoken baselines 1,829 / 1,277 / 1,059 / 241 / 251 / 232 / 416 as lower bounds; the 23-description per-leaf sums ≤ 4,900 estimate and ≤ 4,183 tiktoken; ≥ 4 S025 sentences per description; replies ≤ 80 by both measures; `quota_line` ≤ 38/38, `map_header` ≤ 54/51, `result_card` ≤ 54/56 (estimate/tiktoken); the 46 phrases in `PINNED_PHRASES` and the three exact `VERDICT:` literals; the heading lists in `HEADINGS`; the eight `result_card` literals in order.
- **Floors by tiktoken**: five assets are red, not four. `verifier_system_prompt` must gain at least 41 tiktoken tokens (1,059 → ≥ 1,100); outline 3 adds four new sentences, which is more than enough, but check the §4 output.
- **Phrase matching**: D-9 as implemented in `normalize()`: lowercase; ’ ‘ “ ” → ASCII; `*`, `_`, backtick and `,` removed; whitespace collapsed; contiguous substring. So "exactly one line, and nothing after it" matches with or without the comma, "a card’s" matches "a card's", and `**never** end your turn to ask` matches. A phrase must sit inside the named leaf; the same words in another leaf do not count. "the default is not to remember" is pinned on three leaves (root, generator, `remember_tool_description`) and must appear in each.
- **Sentences**: the S025 definition — a `.`, `!` or `?` followed by whitespace or the end, not closing `e.g.`/`i.e.`/`etc.`/`vs.`/`approx.`. A bullet without a terminal mark does not count as a sentence; a heading merges with the sentence after it.
- **Duplicate-sentence rule**: after D-9 normalization, no sentence of five or more words may appear twice in one of the seven. "A dash means none." (four words) is exempt and may keep repeating in the briefings as the outlines say; nothing longer may.
- **Digits**: the only allowed digits are `^\d+\. ` ordered-list markers. "#1" examples, "24/7", "1st", "one-of-10" all fail.
- **Braces**: none anywhere except the documented placeholders; `{{` is a failure too (it renders as a brace).
- **Fixtures relied on**: `prompt_text(leaf)` and `int_token(n)` from `infinite_memory_fixtures.py` (unchanged); no fixture was added or extended.
- **Run**: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` for the module; the pack command above for everything; `python lint/run.py` must still end `SDK-LINT: PASS` (the module is already tracked, so A001/S020 are satisfied; do not touch the pack README's File Index).
- **Do not change** any test, the pack README/FEATURE.md, or the fixtures; S3, S5 and S6 diff the test tree against this stage's SHA.

## Open items (spec defects found while writing the tests)

1. **INV-15 (e) vs. the briefings' convention line.** The spec (§13 "Duplicate-sentence fact") says zero equal sentence pairs exist at `base_commit`. That is false: "A dash means none." occurs 3× in `task_prompt`, 2× in `verifier_task_prompt`, 3× in `resume_prompt` (the reviewers' check filtered sentences ≤ 20 characters). The spec's own outlines 4.3, 5.3, 6.2, 6.3 say to keep that convention. The test therefore exempts sentences under five words (`MINIMUM_WORDS_FOR_A_RULE = 5`) and is green at base; a pasted rule is never that short. If the orchestrator wants the literal invariant, delete the word filter and the implementer must vary or drop the repeated convention line.
2. **§8.5 (4) vs. INV-17.** The table lists "uses no file quota" (`quota_line`) and "found with grep" (`map_header`) as literal text that must stay, but INV-17 (the tested invariant) names only `result_card`'s labels, the marker, and `quota_line`'s integers, and R-5 keeps literal nudges on the shape leaves under review. Not pinned; review should check them.
3. **Briefing count.** The pack has 113 pre-existing cases at `7efceb55`, not 111; all pass.
