# S2 test author report, re-review round 1 (R-9 to R-12): provider-onboarding-skill

Stage: S2 test author, test grant for re-review round 1 findings R-9 (Blocker) and R-10 (Major), with the R-11 and R-12 repairs · Spec: `docs/spec/provider-onboarding-skill/spec.md` · Review: `reports/S5-rereview-1.md` and `reports/S5-rereview-1-verifier.md` · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill` · Branch: `feat/onboard-model-provider-skill` · Skill wording pinned: HEAD `7676468e` (last skill changes `8edfdec1`, R-11, and `1cac918e`, R-12)

## Outcome

Every safety sentence that re-review round 1 found unprotected now fails a named test when it is deleted, inverted or loosened. Before this round, 66 mutations of the final skill passed the 50-test pack:

- 21 from the grant: the verifier's `v_mut.py` rows and the repair's eight `mut_r11_r12.py` rows;
- 30 aimed at each new assertion;
- 15 found by probing rules the pack claimed beyond the grant.

All 66 now fail. The unmutated control gives `63 passed`, and the three positive controls are red before and after. The real-file run gives `63 passed`. The skill files, the spec and `REPO_MAP.md` are untouched. No existing assertion was deleted, loosened or skipped. The change consists of:

- new assertions appended to existing tests;
- four new tests: S8, S9, C13, and G1 with ten cases;
- module-header text;
- the pack's FEATURE.md and README.md;
- the test plan.

## Pins added

| Test | Spec IDs | What is now asserted | Mutations it catches |
|---|---|---|---|
| X10 `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` (strengthened) | D-19, INV-20, INV-9, re-review R-9 | Exactly three `## 2. Research` prose lines name `NETWORK_BLOCKED`, each once. The first is the line "Network rule. `NETWORK_BLOCKED` needs positive evidence that your session's own policy refused the fetch:". The second is the bullet that starts "- After each fetch, ", which holds the anchored `grep -i '^x-deny-reason'` check and the deny sentence whole. The third is the other-failure bullet, with its three sentences and the GitHub `curl` check verbatim. The deny bullet names no HTTP status. | X10-a to X10-c, EX-X10a to EX-X10e |
| X4 `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` (strengthened) | INV-4, INV-5 a–e, EC-52, T-4, re-review R-9, S5 repair 1 R-E3 | Five reads each occur exactly once as whole commands: the open-PR read, the per-slug read, the `remote-branch` read, the `local-branch` read, and the paths read (`test -e "$WORKTREE" \|\| test -e "$WORKTREE-evidence" \|\| test -e "$WORKTREE-main"; echo "paths exit $?"`). The failed-`gh api` sentence is pinned. The one walk line starts "2. Walk the seed vendors in rank order …" and holds the ledger sentence whole. The `member`, `remote-branch` and `local-branch` disposition bullets, the closed-unmerged rejection sentence and the `NO_CANDIDATE` line are compared whole. | X4-a to X4-e, EX-X4a to EX-X4h, P1-RE3a, P1-RE3b |
| X2 `test_each_pass_runs_fetch_vintage_backpressure_and_selection_before_one_safe_worktree_add` (strengthened) | D-3, EC-52, FR-3, re-review R-10 | The one worktree add equals `git worktree add -b "feat/provider-$SLUG" "$WORKTREE" origin/main && git -C "$WORKTREE" rev-parse HEAD; echo "add exit $?"`. The step sentence ("This is the pass's first write: …") is pinned. Exactly one prose line names "`add exit` is not 0", and it holds both failure sentences ("… launch no subagent, record `local-branch` for the vendor, and continue the walk of step 2 with the next vendor."). No prose line says "launch the subagent on that worktree" or "SHA that printed is the pass's". | ADD-3, ADD-4, EX-X2a to EX-X2c |
| S8 `test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt` (new) | INV-13, request §D, re-review R-10, R-12 | Among the bullets of "Rules for the whole run:", the one that holds "invent a URL" must equal the whole rule. That rule runs from "- Never invent a URL." through "A URL you did not fetch never enters the PR, even when you know it." to "The one exception is the pull-request attribution line your session's instructions give, which section 9 puts last.". No prose line says a URL "may", "can" or "might enter the PR". No prose line says "may invent", "unless you did not fetch" or "unless you know". `## 9. Publish` holds "and last, the pull-request attribution line your session's instructions give, if any." exactly once. | ADD-1, ADD-1b, ADD-2, R12, EX-S8a to EX-S8c |
| S9 `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` (new) | EC-63, D-16, NFR-1, FR-10, re-review R-11 | The pinned guard holds two `\134` escapes and no doubled backslash, which is the file's spelling. The `## 9. Publish` shell commands that hold `pr-body.md` and `grep` are exactly that guard. Its lead line ("The body writes `<worktree>` and `<evidence>` …") and its paragraph of 11 sentences are compared whole. The paragraph runs from "It first deletes every `http://` and `https://` URL …" to "… never push until it prints `grep exit 1`.". Every `local-path-guard` in the procedure is the outcome `` `PUBLISH_FAILED push local-path-guard` ``, and there is at least one. "run it again", "run it until" and "repeat … until" are forbidden. The proof rule is compared whole. It starts "- Sections 1 to 5 are work …" and includes "The reruns that section 8 allows, and the body check's rerun in section 9 step 1, are the only repeats". | R11-a to R11-g, EX-S9a to EX-S9g |
| G1 `test_the_pr_body_guard_passes_only_a_clean_body` (new module `test_onboard_skill_publish_guard.py`, ten cases) | EC-63, D-16, NFR-1, re-review R-11 | The guard line is read from the file, never retyped. `<worktree>` and `<evidence>` become paths under `tmp_path`, and the line runs offline as `[sh, "-c", line]` with a chosen `HOME`. The clean body holds URLs with `/app/`, `/dev/` and `/home/<user>/` segments, and the user name as a plain word. It prints only `grep exit 1` whether `HOME` is a fake home, `/` or empty. Seven dirty or missing bodies print `grep exit 0`, and each dirty body also prints a numbered match. These are: the evidence path with backslashes, the `/c/` twin, the worktree with `HOME=/`, the home directory, the user name between slashes, the user name between backslashes, and no body file. The missing body prints "pr-body.md was not read". The test is skipped, with its reason, where no `sh` exists. | the guard's behaviour behind R11-a to R11-d, EX-S9a and EX-S9c; their text is caught by S9 |
| A3 `test_intro_names_the_three_user_stops_and_disqualified_vendors_are_skipped_not_stopped` (strengthened) | AC-13, FR-15, D-7, INV-7 | The intro's three stop bullets, the other-stops line and the one continue-on-disqualify rule are compared whole. | P2-A3, EX-A3b |
| A4 `test_rules_section_states_the_promises_a_person_relies_on` (strengthened) | AC-13, FR-15, AC-15, INV-8, T-1 | The nine `## Rules` bullets of SKILL.md equal the final wording, in order. | P2-A4a to P2-A4d, EX-A4e |
| S4 `test_the_managed_text_provider_set_is_only_ever_named_as_untouched` (strengthened) | D-12, AC-15 | No line naming `VIDBYTE_MANAGED_TEXT_PROVIDERS` holds add, put, append, include, register or insert before the name in the same clause. The procedure's rule ("- Never change `VIDBYTE_MANAGED_TEXT_PROVIDERS` or a gateway relay table: the vendor is DIRECT-only.") is compared whole. | P2-S4 |
| C10 `test_publish_uses_the_pr_title_body_rules_and_quote_cap` (strengthened) | INV-9, D-16, T-2b | The quote sentence ("Each quote is at most 200 characters, …") is pinned whole, and "at least", "more than" or "over" 200 is forbidden. | P2-C10 |
| C13 `test_qualify_requires_the_chat_completions_response_and_usage_names` (new) | D-11, EC-30, INV-9, S5 repair 1 R-7 | The fact-kinds bullet in Research is compared whole, so usage key names stay a recorded fact. Exactly one Qualify `**Dialect.**` line exists, and it starts with its three pinned sentences. | P1-R7a, P1-R7b, EX-C13b |
| X7 `test_pythonpath_only_prefixes_one_command_and_never_the_package_stage` (strengthened) | D-15, D-20, S5 repair 1 R-5 | At least three `PYTHONPATH=… <py> -c` commands exist in provider-run.md, and each starts `cd <worktree> && PYTHONPATH=<worktree> <py> -c `. The rule that every repository-relative command starts with `cd <worktree> && ` is pinned. | P1-R5a, P1-R5b, EX-X7b |
| X5 `test_preflight_names_every_prerequisite_and_the_permission_setup` (strengthened) | FR-2, D-27 | The sentence that an `acceptEdits` allowlist is not enough, with its two reasons, is pinned. | P2-X5 |
| W7 `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` (strengthened) | §12 comments, S5 repair 1 R-4 | Every comment line of the C9 template is at most 72 columns with the longest seed slug in place of `<s>`. The 72-column comment rule of section 5 is pinned. | P1-R4 |

The grant's named pins map onto these as follows.

- **X10:** the three Research sentences, with only they naming `NETWORK_BLOCKED`.
- **X4:**
  - the paths command whole;
  - the ledger sentence;
  - the `remote-branch` and `local-branch` dispositions.
- **R-10:**
  - "Never invent a URL." and "A URL you did not fetch never enters the PR, even when you know it.", with "may enter" forbidden (S8);
  - the add command whole and the add-failure sentences (X2).
- **R-11 (S9):**
  - the guard command, copied from the file;
  - the guard sentences;
  - the clause "The reruns that section 8 allows, and the body check's rerun in section 9 step 1, are the only repeats".
- **R-11, optional `sh` test:** G1.
- **R-12:** the exception sentence must sit on the same line as "Never invent a URL.", because S8 compares that line whole.

`GUARD_COMMAND` in the security module is a raw string written with the Write tool. S9 checks its two octal escapes before comparing it with the file. G1 runs the file's own line, not the pinned copy, and takes the home directory and paths from `tmp_path`. No path on this machine is hard-coded.

## Mutation table

Generated by `s2rr/table.py` from the two run logs, with no hand transcription. Every row copies the skill files and `REPO_MAP.md` afresh, and requires each anchor exactly once. It checks that each edit landed, then runs the pack through the `s2_harness` fixture redirect. "Before" is the 50-test pack exported from HEAD `7676468e`, run against the same skill. "After" is the 63-test pack of this commit. "Applied" gives the after run, then the before run. A G1 failure counts its failing cases.

| ID | Mutation | Source | Applied | Before: 50-test pack (HEAD 7676468e) | After: 63-test pack | Test that fails after |
|---|---|---|---|---|---|---|
| CONTROL | unmutated | control | yes/yes | 50 passed | 63 passed | none (control) |
| POS-X4 | pagination dropped | rr1v v_mut (positive control) | yes/yes | 1 failed, 49 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| POS-X10 | capture timeout 600 | rr1v v_mut (positive control) | yes/yes | 1 failed, 49 passed | 1 failed, 62 passed | `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` |
| POS-X4b | every -evidence mention deleted | rr1v v_mut (positive control) | yes/yes | 1 failed, 49 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| X10-a | vendor HTTP error ends NETWORK_BLOCKED at once | R-9 v_mut (reviewer) | yes/yes | 50 passed | 1 failed, 62 passed | `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` |
| X10-b | a 403 joins the deny-header rule | R-9 v_mut (verifier) | yes/yes | 50 passed | 1 failed, 62 passed | `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` |
| X10-c | 'without x-deny-reason' qualifier replaced | R-9 v_mut (verifier) | yes/yes | 50 passed | 1 failed, 62 passed | `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` |
| X4-a | -evidence test removed from the paths read | R-9 v_mut (reviewer) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| X4-b | ledger skip reduced to members | R-9 v_mut (reviewer) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| X4-c | ledger skip sentence deleted | R-9 v_mut (verifier) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| X4-d | local-branch no longer names show-ref | R-9 v_mut (verifier) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| X4-e | remote-branch exit codes swapped | R-9 v_mut (verifier) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| ADD-1 | URL rule reworded to 'Every value', last sentence dropped | R-10 v_mut | yes/yes | 50 passed | 1 failed, 62 passed | `test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt` |
| ADD-1b | URL rule bullet deleted whole (anchor updated for R-12) | R-10 v_mut (anchor refreshed) | yes/yes | 50 passed | 1 failed, 62 passed | `test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt` |
| ADD-2 | URL rule inverted to 'may enter the PR' | R-10 v_mut | yes/yes | 50 passed | 1 failed, 62 passed | `test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt` |
| ADD-3 | add-failure sentence deleted | R-10 v_mut | yes/yes | 50 passed | 1 failed, 62 passed | `test_each_pass_runs_fetch_vintage_backpressure_and_selection_before_one_safe_worktree_add` |
| ADD-4 | add failure adopts the worktree | R-10 v_mut | yes/yes | 50 passed | 1 failed, 62 passed | `test_each_pass_runs_fetch_vintage_backpressure_and_selection_before_one_safe_worktree_add` |
| R11-a | guard: basename W -> dirname W | R-11 mut_r11_r12 | yes/yes | 50 passed | 3 failed, 60 passed | `test_the_pr_body_guard_passes_only_a_clean_body` (2 cases), `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| R11-b | guard: URL strip replaced by cat | R-11 mut_r11_r12 | yes/yes | 50 passed | 2 failed, 61 passed | `test_the_pr_body_guard_passes_only_a_clean_body`, `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| R11-c | guard: HOME fallback removed | R-11 mut_r11_r12 | yes/yes | 50 passed | 2 failed, 61 passed | `test_the_pr_body_guard_passes_only_a_clean_body`, `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| R11-d | guard: unreadable-body sentinel removed | R-11 mut_r11_r12 | yes/yes | 50 passed | 2 failed, 61 passed | `test_the_pr_body_guard_passes_only_a_clean_body`, `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| R11-e | bounded rerun turned into a loop | R-11 mut_r11_r12 | yes/yes | 50 passed | 1 failed, 62 passed | `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| R11-f | outcome -> PROOF_FAILED | R-11 mut_r11_r12 | yes/yes | 50 passed | 1 failed, 62 passed | `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| R11-g | rules: body-check rerun clause removed | R-11 mut_r11_r12 | yes/yes | 50 passed | 1 failed, 62 passed | `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| R12 | attribution exception deleted | R-12 mut_r11_r12 | yes/yes | 50 passed | 1 failed, 62 passed | `test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt` |
| EX-X2a | add prints no base SHA | extra (X2 add command) | yes/yes | 50 passed | 1 failed, 62 passed | `test_each_pass_runs_fetch_vintage_backpressure_and_selection_before_one_safe_worktree_add` |
| EX-X2b | add may reset an existing branch | extra (X2 step sentence) | yes/yes | 50 passed | 1 failed, 62 passed | `test_each_pass_runs_fetch_vintage_backpressure_and_selection_before_one_safe_worktree_add` |
| EX-X2c | add failure stops the session | extra (X2 failure sentence) | yes/yes | 50 passed | 1 failed, 62 passed | `test_each_pass_runs_fetch_vintage_backpressure_and_selection_before_one_safe_worktree_add` |
| EX-X4a | per-slug read loses per_page | extra (X4 per-slug command) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| EX-X4b | show-ref without --verify | extra (X4 local-branch command) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| EX-X4c | paths read ignores the -main twin | extra (X4 paths command) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| EX-X4d | walk not in rank order | extra (X4 walk sentence) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| EX-X4e | member read from the checkout | extra (X4 member disposition) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| EX-X4f | closed unmerged PR skipped only until reopened | extra (X4 rejection sentence) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| EX-X4g | kept paths may be overwritten | extra (X4 local-branch disposition) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| EX-X4h | no-candidate stop replaced by a wait | extra (X4 no-candidate sentence) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| EX-X10a | extra Research line ends a 403 as NETWORK_BLOCKED | extra (X10 line set) | yes/yes | 50 passed | 1 failed, 62 passed | `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` |
| EX-X10b | GitHub check inverted | extra (X10 other-failure sentence) | yes/yes | 50 passed | 1 failed, 62 passed | `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` |
| EX-X10c | vendor failure disqualifies at once | extra (X10 section 3 sentence) | yes/yes | 50 passed | 1 failed, 62 passed | `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` |
| EX-X10d | deny-header grep unanchored | extra (X10 deny check) | yes/yes | 50 passed | 1 failed, 62 passed | `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` |
| EX-X10e | GitHub check pointed elsewhere | extra (X10 GitHub check) | yes/yes | 50 passed | 1 failed, 62 passed | `test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep` |
| EX-S8a | URL rule exception widened | extra (S8 full rules line) | yes/yes | 50 passed | 1 failed, 62 passed | `test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt` |
| EX-S8b | attribution line no longer last | extra (S8 section 9 counterpart) | yes/yes | 50 passed | 1 failed, 62 passed | `test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt` |
| EX-S8c | fetch-log status any | extra (S8 full rules line) | yes/yes | 50 passed | 1 failed, 62 passed | `test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt` |
| EX-S9a | guard grep gains -i | extra (S9 command; G1 behaviour on Windows) | yes/yes | 50 passed | 11 failed, 52 passed | `test_the_pr_body_guard_passes_only_a_clean_body` (10 cases), `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| EX-S9b | guard backslash doubled instead of octal | extra (S9 command) | yes/yes | 50 passed | 1 failed, 62 passed | `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| EX-S9c | guard drops the /user/ pattern | extra (S9 command; G1 behaviour) | yes/yes | 50 passed | 2 failed, 61 passed | `test_the_pr_body_guard_passes_only_a_clean_body`, `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| EX-S9d | body rule drops home and user name | extra (S9 lead line) | yes/yes | 50 passed | 1 failed, 62 passed | `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| EX-S9e | guard paragraph gains a push-anyway sentence | extra (S9 full paragraph) | yes/yes | 50 passed | 1 failed, 62 passed | `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| EX-S9f | proof steps may repeat | extra (S9 proof rule) | yes/yes | 50 passed | 1 failed, 62 passed | `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| EX-S9g | guard outcome named a second way | extra (S9 outcome count) | yes/yes | 50 passed | 1 failed, 62 passed | `test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome` |
| P1-RE3a | open-PR read prints no exit status | probe R-E3 (1dbdfede) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| P1-RE3b | failed gh read may be an empty list | probe R-E3 (1dbdfede) | yes/yes | 50 passed | 1 failed, 62 passed | `test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5` |
| P1-R5a | collision probe runs from the launcher | probe R-5 (ff307d1e) | yes/yes | 50 passed | 1 failed, 62 passed | `test_pythonpath_only_prefixes_one_command_and_never_the_package_stage` |
| P1-R5b | A9 probe runs from the launcher | probe R-5 (ff307d1e) | yes/yes | 50 passed | 1 failed, 62 passed | `test_pythonpath_only_prefixes_one_command_and_never_the_package_stage` |
| P1-R7a | response and usage names not checked | probe R-7 (1c0ec03c) | yes/yes | 50 passed | 1 failed, 62 passed | `test_qualify_requires_the_chat_completions_response_and_usage_names` |
| P1-R7b | other usage names accepted | probe R-7 (1c0ec03c) | yes/yes | 50 passed | 1 failed, 62 passed | `test_qualify_requires_the_chat_completions_response_and_usage_names` |
| P1-R4 | C9 comment back on one long line | probe R-4 (6dc92270) | yes/yes | 50 passed | 1 failed, 62 passed | `test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays` |
| P2-A3 | a disqualification stops the session | probe A3 claim | yes/yes | 50 passed | 1 failed, 62 passed | `test_intro_names_the_three_user_stops_and_disqualified_vendors_are_skipped_not_stopped` |
| P2-A4a | the skill merges green PRs | probe A4 claim | yes/yes | 50 passed | 1 failed, 62 passed | `test_rules_section_states_the_promises_a_person_relies_on` |
| P2-A4b | closing skips only until the next session | probe A4 claim | yes/yes | 50 passed | 1 failed, 62 passed | `test_rules_section_states_the_promises_a_person_relies_on` |
| P2-A4c | stashing allowed | probe A4 claim | yes/yes | 50 passed | 1 failed, 62 passed | `test_rules_section_states_the_promises_a_person_relies_on` |
| P2-A4d | several sessions allowed | probe A4 claim | yes/yes | 50 passed | 1 failed, 62 passed | `test_rules_section_states_the_promises_a_person_relies_on` |
| P2-S4 | vendor added to the managed set | probe S4 claim | yes/yes | 50 passed | 1 failed, 62 passed | `test_the_managed_text_provider_set_is_only_ever_named_as_untouched` |
| P2-C10 | quote cap inverted to a minimum | probe C10 claim | yes/yes | 50 passed | 1 failed, 62 passed | `test_publish_uses_the_pr_title_body_rules_and_quote_cap` |
| P2-X5 | acceptEdits enough | probe X5 | yes/yes | 50 passed | 1 failed, 62 passed | `test_preflight_names_every_prerequisite_and_the_permission_setup` |
| EX-A3b | back-pressure stop raised to 4 | extra (A3 stop bullets) | yes/yes | 50 passed | 1 failed, 62 passed | `test_intro_names_the_three_user_stops_and_disqualified_vendors_are_skipped_not_stopped` |
| EX-A4e | any vendor may be a candidate | extra (A4 rules) | yes/yes | 50 passed | 1 failed, 62 passed | `test_rules_section_states_the_promises_a_person_relies_on` |
| EX-C13b | usage key names dropped from the fact kinds | extra (C13 fact kinds) | yes/yes | 50 passed | 1 failed, 62 passed | `test_qualify_requires_the_chat_completions_response_and_usage_names` |
| EX-X7b | import probe runs from the launcher | extra (X7 probe prefix) | yes/yes | 50 passed | 1 failed, 62 passed | `test_pythonpath_only_prefixes_one_command_and_never_the_package_stage` |

Totals from the generator: 66 mutations; 66 survived the 50-test pack; 66 red after; 3 positive controls red before and after; the control gives `50 passed` before and `63 passed` after.

Rows by source:

- **Positive controls** (`POS-`): the verifier's three rows. They prove the redirect reaches the tests, so they are red in both columns.
- **Grant rows** (21):
  - The verifier's `v_mut.py`: X10-a to X10-c, X4-a to X4-e, and ADD-1 to ADD-4. ADD-1b has its anchor refreshed for R-12's appended sentence.
  - The repair's `s5r2/mut_r11_r12.py`: R11-a to R11-g and R12. That script edits the real skill file in place, so its eight rows were ported unchanged into the copy-based runner rather than run as written.
- **Extras** (`EX-`, 30): one mutation aimed at each new assertion.
- **Probes** (`P1-`, `P2-`, 15):
  - Rules beyond the grant that a token check let through. P1 covers the S5 repair-1 fixes: R-E3 (`prs exit`), R-5 (probes from the worktree), R-7 (response and usage names) and R-4 (72 columns).
  - P2 covers claims in the test plan that held only by token: A3, A4, S4, C10 and X5.

## The verifier's and the earlier runners, rerun on the final pack

- `rr1v/v_mut.py`, unchanged, writes `s2rr/v_mut_final.txt`:
  - The control gives `63 passed`, and the three positive controls are red.
  - 12 of its 13 mutation rows are red, each failing the test the table names.
  - ADD-1b reports "NOT APPLIED: anchor count 0". Its anchor is the URL bullet as it stood before R-12 appended the exception sentence. The refreshed ADD-1b row above deletes the final bullet whole, and it is red.
- `s2r/mut_r3r8.py` writes `s2r/r3r8_final.txt`:
  - All 35 rows applied, and the control gives `63 passed`.
  - All 34 mutation rows are red, the same tests as at `df0f4bb7`.
  - None of this round's changes weakened an R-3 or R-8 pin.

## G1 on two shells

- Git for Windows `sh`, through the pack: 10 of 10 cases pass.
- Linux dash, under WSL (`/usr/bin/sh -> /usr/bin/dash`): `s2rr/wsl_guard.py` runs the committed test body with a two-decorator `pytest` stub, because pytest is absent there. It ends `SUMMARY linux dash: 10/10 cases pass; failures: []`. CI runs on ubuntu-latest, whose `sh` is dash.

## Real-file pack

`PYTHONPATH="C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` → `63 passed in 1.97s`

## Lint

- The full run: after `git add` of the pack, the test plan and this report, `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py` ends `SDK-LINT: PASS`.
- Per-rule runs: `--rule A001`, `S062`, `S020`, `A009` and `S055`, each with `--all`, report 0 findings in the pack and in the spec folder.
- A001: the new module carries the full nine-part header.
- S020: the new module is listed in the pack README's File Index.
- S062: no implicit string concatenation. The long pinned sentences are tuples joined with `" ".join(...)`.
- S055: G1 runs `sh` with an argument list, never `shell=True`.
- `ruff check` on the pack passes. A first run flagged an unsorted import and three FLY002 joins of literal tuples. They were fixed by wrapping the import and naming each tuple (`URL_RULE_SENTENCES`, `PROOF_RULE_SENTENCES`, `CLEAN_BODY_LINES`) before joining. All three runners were rerun after that fix.
- `lint/baseline.json` is untouched.

## Test-plan claims made true

- **:27, INV-4/INV-5 (X4):** The row claimed that ignoring the evidence path or the session ledger fails X4. Before, it did not: X4-a to X4-e passed. Now the five reads, the ledger sentence and the dispositions are compared whole, and the row says so.
- **:33, D-19/INV-20 (X10):** The row claimed that a plain vendor 403 called `NETWORK_BLOCKED` fails X10. Before, it did not: X10-a to X10-c passed. Now only the network rule's three lines may name `NETWORK_BLOCKED`, and the row says so. The same row's C10 quote cap is now compared whole.
- **:64, EC-52 omitted strategy:** The row claimed that the text guards were tested. Now each named guard is tested by content: the skip rules (X4), one session (A4), the single refspec (S3), and the failed-add branch (X2).
- **:25, :26, :28, :29 (A3/A4, S4, X2, X5):** These rows said the same as these pins. Each now states the stronger check.
- **New rows:** one per new pin, with its spec IDs and the mutations it catches.
- **Re-verification paragraph:** added for this round.
- **"Sentences pinned word for word" note:** extended with every sentence pinned here.

## Invariance and constraints

- Provider branches: every new assertion reads the skill text, or runs the guard line over temporary files. None reads git state, a base, the provider list, the member count, `PRICING_AS_OF` or a line number. W7's longest seed slug comes from the fixtures' seed list, which a provider PR does not change.
- No network and no key: G1 sends `stdin` to the null device and touches only `tmp_path`. The fake user and paths are plain words. No key shape appears anywhere.
- Writes: these stayed inside `tests/features/onboard_model_provider_skill/**`, `test-plan.md` and this report. Every line this round removed from a test module is header text replaced by longer text. No assertion was removed.

## Wording that could not be pinned

None. Every sentence the grant names is present in the final skill wording, unambiguous, and pinned verbatim.

One rule is left unpinned on purpose: skip precedence. Review R-E2 (g) refuted it as a defect, because `closed-unmerged`, `open-pr` and `merged` all skip the vendor, so reversing their order changes only the ledger label.

As in the last round, these sentences are now compared word for word. A rewording that keeps the rule must change the test in the same commit, and the test plan's "Notes for the implementer" lists them.

## Scratch evidence (not committed)

All paths are under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/`:

- `s2rr/mut_rr1.py`: the copy-based runner, all 70 rows. `S2_PACK=<dir>` selects an exported pack.
- `s2rr/before.txt`, `s2rr/final.txt`: the run logs for the 50-test pack at `7676468e` and for this commit's pack.
- `s2rr/table.py`, `s2rr/headpack/`: the table generator and the HEAD pack export.
- `s2rr/v_mut_final.txt`, `s2r/r3r8_final.txt`: the reruns of the verifier's runner and the R-3/R-8 runner.
- `s2rr/wsl_guard.py`: the Linux dash run of G1.
