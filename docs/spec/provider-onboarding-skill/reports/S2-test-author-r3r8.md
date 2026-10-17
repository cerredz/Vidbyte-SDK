# S2 test author report, round R-3/R-8: provider-onboarding-skill

Stage: S2 test author, test grant for review findings R-3 (Blocker) and R-8 (Major) · Spec: `docs/spec/provider-onboarding-skill/spec.md` · Review: `docs/spec/provider-onboarding-skill/review.md` rows R-3 and R-8 (from S4 engineering R-E2) · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill` · Branch: `feat/onboard-model-provider-skill` · Skill wording pinned: HEAD `233b18ce`, after S5 repair 1

## Outcome

Each rule the S2 pack claims to protect is now pinned by what it says, not by a token it contains. Before this round, 14 mutations from review.md passed the 46-test pack: an inverted D-29 condition, a self-check `assert` turned into a bare call, the known-red rule inverted or reduced to a log step, the contract test allowed to count, `PROOF_FAILED` moved into the cleanup, and all of R-8. Now every one of them, and 18 further mutations aimed at the new assertions, fails the test named for it. The unmutated control gives `50 passed`, and the real-file run gives `50 passed in 0.89s`. The skill files, the spec and `REPO_MAP.md` are untouched. No existing assertion was deleted, loosened or skipped.

## Pins added

| Test | Spec IDs | What is now asserted | Mutations it catches |
|---|---|---|---|
| S5 `test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it` (strengthened) | D-29, D-14, review R-3 (a), (b) | A Qualify prose line, outside every fence, holds `` `Runner._normalize_provider_and_model(None, <id>)[0]` is None `` together with "Otherwise `no-usable-model-id`", and no prose line says `[0]` "is not None". The single eligibility line holds "derived provider None". The probe fence prints `derived provider {Runner._normalize_provider_and_model(None, model)[0]}`. Each of the 11 self-check statements, `assert Runner._normalize_provider_and_model(None, model)[0] is None` among them, starts exactly one line of `## 6. Self-check`. Both python fences compile once bare `<placeholders>` become literals. | R3-S5a, R3-S5b, R3-S5c, R3-S5d (control), EX-S5, EX-S5e |
| X8 `test_gate_commands_and_output_lines_are_the_repositorys_real_ones` (strengthened) | D-15, §12.4, INV-17, review R-3 (h) | Every `## 8. Gate` prose line naming `diff --quiet <base> HEAD -- <file>` holds "only when its file is unchanged, meaning `git -C <worktree> diff --quiet <base> HEAD -- <file>` exits 0", and none says `exits 1`, "is changed" or "changed file". Exactly one prose line names the A13 node, and it holds "never its whole file", "only when both checks below hold" and "prints exactly one line, `vidbyte/lib/configs/structured_output.py`". A prose line holds "the same `AssertionError` line as on the branch". The scoped diff command and the `>> <worktree>-main/…` control edit are compared as whole strings. The A13 node exists in the real harness test file. | R3-X8a, R3-X8b, R3-X8c (control), EX-A13a to EX-A13e |
| X9 `test_mutation_check_commits_first_restores_by_checkout_and_confirms_a_clean_diff` (strengthened) | AC-8, INV-15, review R-3 (i) | Every `## 7.` prose line naming `test_provider_keys_contract` holds "At least one must be outside `test_provider_keys_contract.py`". One holds `` `PROOF_FAILED mutation-survived` ``. None says the contract test is "included", "counts" or "may be" the one. | R3-X9a, R3-X9b, EX-X9c |
| A5 `test_each_outcome_states_what_it_leaves_behind` (strengthened) | AC-13, D-8, review R-3 (j) | Exactly one bullet holds "keep the worktree", and the outcomes it names are exactly {`PROOF_FAILED`, `PUBLISH_FAILED`, `RESULT_UNVERIFIED`}. Exactly one bullet holds "remove the worktree", and it names exactly {`PR_OPENED`, `DISQUALIFIED`, `NETWORK_BLOCKED`}, with "after all four checks pass" and "after the clean check passes". The cleanup command is the one `&&` chain, compared as a string. The keep bullet removes the `-main` twin. | R3-A5a, R3-A5b, EX-A5c |
| W7 `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` (new) | C9 row, EC-43, D-12, review R-8 (c), (d) | One python fence in `## 5. Wiring checklist` holds the C9 `def`, and ten statements each start one of its lines. Among them are `self.assertEqual(header(sent, "authorization"), f"Bearer {K_<E>}")`, `self.assertNotIn(K_ANTHROPIC, flat(sent))`, `vendor = ScriptedGateway(provider_answer(ModelProvider.<E>))` and the mixed-key DIRECT run line. The fence holds no `x-api-key` and no `TextModelMode.AUTO`. It compiles. Every name it uses, and the cited Meta model test, exists in the real `test_provider_keys_modes.py`. The C9 Add cell holds "`authorization` is `Bearer <fake>`" and "the other key is absent". | R8-C9a, R8-C9b, R8-C9c, EX-C9d to EX-C9g |
| X12 `test_backpressure_counts_the_listed_prs_together_with_this_sessions_prs` (new) | INV-3, EC-9, D-5, review R-8 (e) | Exactly one `## Each pass` prose line holds `union`. That line holds "the open provider PRs are the union of the numbers printed and the PRs this session opened", "because GitHub's list can lag", "When that count reaches `MAX_OPEN_PROVIDER_PRS`, stop with `BACKPRESSURE`" and "Only PRs whose head repository is `cerredz/Vidbyte-SDK` count". | R8-BP, EX-BP |
| S7 `test_format_binding_needs_a_first_party_statement_not_an_example_key` (new) | D-13, EC-33, review R-8 (k) | One Qualify prose line holds "Add the vendor to `FORMAT_BOUND_PROVIDERS` (row C2) only with a quoted first-party statement that its keys begin with P." together with "An example key alone is not enough". No prose line says an example key "is enough", or binds "whenever an example key" shows P. | R8-D13, EX-D13a, EX-D13b |
| X13 `test_vintage_stops_the_session_when_mains_pricebook_is_not_before_today` (new) | FR-3, INV-3, D-10, EC-19, EC-20, review R-E2f (Minor) | Exactly one prose bullet starts `- Vintage:`, and it holds "when main's `PRICING_AS_OF` is not before today (UTC)" and "stop with `VINTAGE_DEFERRED`". | EX-VIN, S4 `mut.py` "vintage comparison inverted" |

Supporting change: `MarkdownDoc` in `onboard_skill_fixtures.py` gained `fenced_blocks_with_info()`, which returns each fence with its info word, and `prose_lines()`, which returns the lines outside every fence. `fenced_blocks()` now delegates to the first and returns the same value as before.

## Mutation table

Method: `scratchpad/s2r/mut_r3r8.py` copies the worktree's current `.claude/skills/onboard-model-provider/` and `REPO_MAP.md` afresh on every run. The copy at `scratchpad/s4eng/real` was stale at `32ca7991`, and none of these runs reads it. The script then applies one mutation to a copy of that copy. Every anchor must occur exactly once, or the row reports `applied: no`. It runs the pack through S2's fixture-redirect plugin, `s2_harness.py`, with `PYTHONDONTWRITEBYTECODE=1` and no cache provider. The before column runs the 46-test pack exported from HEAD (`git archive HEAD`, `REPO_ROOT` pointed at the worktree), and the after column runs the 50-test pack in the worktree. The table is generated from the two run logs (`before-head.txt`, `after.txt`) by `scratchpad/s2r/table.py`. Rows R3-S5d and R3-X8c are review.md's deletion controls, red before and after, as intended. EX-JEV was already caught by C9 and stays caught.

| ID | Mutation | Source | Applied | Before: 46-test pack (HEAD 233b18ce) | After: 50-test pack | Test that fails after |
|---|---|---|---|---|---|---|
| CONTROL | unmutated | control | yes | 46 passed | 50 passed | none (control) |
| R3-S5a | Qualify forgets D-29 (clause and eligibility reading removed, probe kept) | R-3 mut2 | yes | 46 passed | 1 failed, 49 passed | `test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it` |
| R3-S5b | D-29 Qualify condition negated | R-3 mut | yes | 46 passed | 1 failed, 49 passed | `test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it` |
| R3-S5c | D-29 self-check assert turned into a bare call | R-3 mut | yes | 46 passed | 1 failed, 49 passed | `test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it` |
| R3-S5d | control: D-29 self-check line deleted | R-3 mut2 control | yes | 1 failed, 45 passed | 1 failed, 49 passed | `test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it` |
| R3-X8a | known-red: unchanged-file condition only logged | R-3 mut2 | yes | 46 passed | 1 failed, 49 passed | `test_gate_commands_and_output_lines_are_the_repositorys_real_ones` |
| R3-X8b | known-red: exclude when the file CHANGED | R-3 mut | yes | 46 passed | 1 failed, 49 passed | `test_gate_commands_and_output_lines_are_the_repositorys_real_ones` |
| R3-X8c | control: unchanged-file command deleted | R-3 mut2 control | yes | 1 failed, 45 passed | 1 failed, 49 passed | `test_gate_commands_and_output_lines_are_the_repositorys_real_ones` |
| R3-X9a | mutation proof: any test counts, contract test included | R-3 mut2 | yes | 46 passed | 1 failed, 49 passed | `test_mutation_check_commits_first_restores_by_checkout_and_confirms_a_clean_diff` |
| R3-X9b | mutation proof: contract test may be the one | R-3 mut | yes | 46 passed | 1 failed, 49 passed | `test_mutation_check_commits_first_restores_by_checkout_and_confirms_a_clean_diff` |
| R3-A5a | PROOF_FAILED moved from keep to cleanup | R-3 mut2 | yes | 46 passed | 1 failed, 49 passed | `test_each_outcome_states_what_it_leaves_behind` |
| R3-A5b | cleanup before the clean check, failing outcomes always cleaned | R-3 mut | yes | 46 passed | 1 failed, 49 passed | `test_each_outcome_states_what_it_leaves_behind` |
| R8-C9a | Bearer assertion deleted | R-8 mut/mut2 | yes | 46 passed | 1 failed, 49 passed | `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` |
| R8-C9b | Bearer assertion rewritten to x-api-key | R-8 mut | yes | 46 passed | 1 failed, 49 passed | `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` |
| R8-C9c | the three key lines of the C9 fence deleted | R-8 mut2 | yes | 46 passed | 1 failed, 49 passed | `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` |
| R8-BP | back-pressure drops the union with this session's PRs | R-8 mut/mut2 | yes | 46 passed | 1 failed, 49 passed | `test_backpressure_counts_the_listed_prs_together_with_this_sessions_prs` |
| R8-D13 | FORMAT_BOUND on an example key | R-8 mut | yes | 46 passed | 1 failed, 49 passed | `test_format_binding_needs_a_first_party_statement_not_an_example_key` |
| EX-S5 | eligibility reading drops 'derived provider None' | extra | yes | 46 passed | 1 failed, 49 passed | `test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it` |
| EX-A13a | scoped diff: 'exactly one line' weakened | extra | yes | 46 passed | 1 failed, 49 passed | `test_gate_commands_and_output_lines_are_the_repositorys_real_ones` |
| EX-A13b | control edit: 'same AssertionError line' dropped | extra | yes | 46 passed | 1 failed, 49 passed | `test_gate_commands_and_output_lines_are_the_repositorys_real_ones` |
| EX-A13c | exclusion widened to the whole file on either check | extra | yes | 46 passed | 1 failed, 49 passed | `test_gate_commands_and_output_lines_are_the_repositorys_real_ones` |
| EX-A13d | scoped diff unscoped | extra | yes | 46 passed | 1 failed, 49 passed | `test_gate_commands_and_output_lines_are_the_repositorys_real_ones` |
| EX-C9d | other key no longer asserted absent | extra | yes | 46 passed | 1 failed, 49 passed | `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` |
| EX-C9e | mixed key list reduced to the vendor key | extra | yes | 46 passed | 1 failed, 49 passed | `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` |
| EX-C9f | template mode AUTO | extra | yes | 46 passed | 1 failed, 49 passed | `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` |
| EX-BP | union kept, this session dropped | extra | yes | 46 passed | 1 failed, 49 passed | `test_backpressure_counts_the_listed_prs_together_with_this_sessions_prs` |
| EX-D13a | example-key sentence removed only | extra | yes | 46 passed | 1 failed, 49 passed | `test_format_binding_needs_a_first_party_statement_not_an_example_key` |
| EX-D13b | statement requirement weakened only | extra | yes | 46 passed | 1 failed, 49 passed | `test_format_binding_needs_a_first_party_statement_not_an_example_key` |
| EX-JEV | jev check: any number of added lines | extra | yes | 1 failed, 45 passed | 1 failed, 49 passed | `test_verifying_a_result_runs_the_four_checks_without_a_copy_of_the_checklist` |
| EX-VIN | vintage comparison inverted | extra | yes | 46 passed | 1 failed, 49 passed | `test_vintage_stops_the_session_when_mains_pricebook_is_not_before_today` |
| EX-X9c | 'At least one' weakened to 'Prefer one' | extra | yes | 46 passed | 1 failed, 49 passed | `test_mutation_check_commits_first_restores_by_checkout_and_confirms_a_clean_diff` |
| EX-A5c | cleanup chain broken: branch deleted even when the remove fails | extra | yes | 46 passed | 1 failed, 49 passed | `test_each_outcome_states_what_it_leaves_behind` |
| EX-A13e | control edit lands on the branch worktree, not the twin | extra | yes | 46 passed | 1 failed, 49 passed | `test_gate_commands_and_output_lines_are_the_repositorys_real_ones` |
| EX-S5e | another self-check assert dropped (tool-format pin) | extra | yes | 46 passed | 1 failed, 49 passed | `test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it` |
| EX-C9g | C9 row Add cell drops the Bearer outcome | extra | yes | 46 passed | 1 failed, 49 passed | `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` |

Result: 34 of 34 mutations are red after the change, and 31 of them passed the 46-test pack before it. Every mutation applied. The unmutated control gives `46 passed` before and `50 passed` after.

**The reviewers' own scripts, rerun unchanged.** The stale `scratchpad/s4eng/real` was kept as `real-32ca7991` and refreshed from HEAD. All three files were stale.

- `s4ver/mut2.py`: 10 of 10 rows applied. The control gives `50 passed`, and each of the 9 mutation rows fails the test it names: S5, X8, X9, W7, X12 and A5.
- `s4eng/mut.py`: 14 of 14 rows applied, and 13 are red. The one green row is "skip precedence reversed" (`50 passed`). review.md row R-E2 (g) refuted it as a defect: `closed-unmerged`, `open-pr` and `merged` all skip the vendor, so reversing the precedence changes only the ledger label. The review says the pack has no reason to pin it, so it stays unpinned on purpose.

## Real-file pack

`PYTHONPATH="C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` → `50 passed in 0.89s`

## Lint

After `git add` of the pack and the test plan, `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py` ends `SDK-LINT: PASS`. `--rule A001`, `S062`, `S020`, `A009`, `S051`, `S054`, `S060`, `S061`, `S063` and `S064` with `--all` each report 0 findings in the pack, and `ruff check` on the pack passes. `lint/baseline.json` is untouched. `ruff format --check` would reformat the same six pack files at HEAD, and the gate does not run it, so the pack's style is unchanged.

## Invariance and constraints

- Every new assertion reads the skill text or the current tree only: the real `test_provider_keys_modes.py` and the harness test file named in A13. None reads git state, a base, the provider list, the member count, `PRICING_AS_OF` or a line number. A provider PR adds a test to `test_provider_keys_modes.py` but removes none of the names W7 looks up, so the pack stays green on every provider branch.
- No fake key appears in the new code. W7 compiles the template with `<E>` and `<s>` replaced by identifiers, never by a key.
- Writes stayed inside `tests/features/onboard_model_provider_skill/**`, `test-plan.md` and this report. The lines this round removed are module-header text replaced by longer text, plus the body of `fenced_blocks()`, which now delegates to `fenced_blocks_with_info()`.

## Wording that could not be pinned

None. Every sentence the grant names is present in the final skill wording, unambiguous and pinned verbatim.

One consequence for whoever edits the skill next: these sentences are now compared word for word. A rewording that keeps the rule must change the test in the same commit. The test plan's "Notes for the implementer" now lists them.

## Scratch evidence (not committed)

All paths are under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/`:

- `s2r/mut_r3r8.py`: the mutation runner. `S2_PACK=<dir>` selects an exported pack.
- `s2r/before-head.txt`, `s2r/after.txt`: the run logs.
- `s2r/before.txt`: the earlier before-run against the worktree pack, which lacks the last four extras.
- `s2r/table.py`, `s2r/headpack/`: the table generator and the HEAD pack export.
- `s4eng/real-32ca7991/`: the stale copy, kept.
