# S4 findings verifier (scoped): re-review round 2 (FINAL)

Stage: S4 findings verifier, scoped to the three findings of `reports/S5-rereview-2.md` · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill` · Branch: `feat/onboard-model-provider-skill` · HEAD: `07e06aec` (clean). `git diff --quiet 12937997 07e06aec -- .claude tests REPO_MAP.md` exits 0, so the text I verified is the text the reviewer reviewed. Scratch evidence: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/rr2v/` (`v_mut.py`, `v_regex.py`, `v_guard_meta.py` and their `*_out.txt` files). The reviewer's `rr2/mut_rr2.py` was read but not run; every row below comes from my own scripts.

## Verdict

SOUND. Round 2 leaves no confirmed Blocker or Major.

- RR2-1 holds as a fact: S10 and W8 stay green when a new line contradicts the rule in words outside their patterns. But it is not "a test that cannot fail". Both tests fail for every deletion and inversion of their rule, and the "any line" claim is one that no text check can meet. The defect is the claim's wording, so I **downgrade it from Blocker to Minor** (R-13, `trivial`). The fix is documentation only, made by the S2 test author.
- RR2-2 is confirmed as Minor (R-14, `follow-up`).
- RR2-3 is confirmed as Minor (R-15, `follow-up`).
- Blind spots: none of Blocker class in `git diff 5d1cc44a..HEAD -- .claude tests`.

Counts: confirmed Blockers 0, Majors 0, Minors 3. Refuted 0. Downgraded 1 (RR2-1).

## Merge map

| Re-review ID | Merged ID | Reviewer severity | Verified severity | Fix kind | Who |
|---|---|---|---|---|---|
| RR2-1 (S10 and W8 claims) | R-13 | Blocker | Minor, `trivial` | test-plan.md and FEATURE.md wording (test comments optional) | S2 test author |
| RR2-2 (keep rule vs rows D2 and C4) | R-14 | Minor | Minor, `follow-up` | skill text, spec D-13, S10 pin | repair agent, then S2 test author |
| RR2-3 (proof rule names PROOF_FAILED for section 9) | R-15 | Minor | Minor, `follow-up` | skill text (spec deviation 2 optional), S9 pin | repair agent, then S2 test author |

## RR2-1: the facts hold; the grade does not

### Method

`v_mut.py` copies `SKILL.md`, `references/provider-run.md` and `REPO_MAP.md` into a fresh directory for every row. The anchor of each edit must occur exactly once. After the edit, the script reads the file back and checks that the anchor is gone or the new text is present. Then it runs the pack through the fixture redirect:

```
S2_SYNTH=<copy root> PYTHONPATH="<worktree>;<scratch>" py -3.11 -B -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider -p s2_harness --tb=no
```

Every row printed `applied=yes`. Output: `rr2v/v_mut_out.txt`.

| Row | Edit | Result | Test that fails |
|---|---|---|---|
| CONTROL | none | `65 passed in 2.47s` | none |
| A1 | step-7 keep paragraph deleted, with its blank line | `1 failed, 64 passed` | S10 |
| A2 | "keep the rule, because keys issued in the old shape still exist" → "update that vendor's rule to the new shape, because the old shape is retired" | `1 failed, 64 passed` | S10 |
| A3 | C4 note deleted | `1 failed, 64 passed` | W8 |
| A4 | C4 note → "and may paraphrase the page when the statement is long." | `1 failed, 64 passed` | W8 |
| A5 | new §5 line: "… overwrite the existing rule with it." | `1 failed, 64 passed` | S10 |
| A6 | new §5 line: "The link text may paraphrase the page title." | `1 failed, 64 passed` | W8 |
| B-a (reviewer ANY-a) | new §5 line: "When Meta's own docs show a newer key shape, update the Meta rule to that shape." | `65 passed` | none |
| B-c (ANY-c) | new §5 line: "… replace the existing Meta prefix with the new one." | `65 passed` | none |
| B-d (ANY-d) | new §5 line: "If the vendor changed its format, overwrite the older entry." | `65 passed` | none |
| B-e (ANY-e) | new §5 line: "If P overlaps, narrow the openai rule so P fits." | `65 passed` | none |
| B-g (ANY-g) | new run-rules bullet after :21: "… update the Meta rule to it." | `65 passed` | none |
| B-W8x (W8-x) | new §5 line: "The README row may summarize the vendor's statement in your own words." | `65 passed` | none |
| C1 (mine) | new SKILL.md line in `## Verifying a result`: "A provider run that sees a newer key shape for Meta may update the Meta rule to it." | `65 passed` | none |
| C2 (mine) | new §3 line **directly under the keep paragraph**: "If the newer shape is on Meta's own docs page, update Meta's key rule to it as well." | `65 passed` | none |
| C3 (mine) | new §5 line: "Rewrite `KEY_FORMATS` so that Meta's keys in the new shape match." | `65 passed` | none |
| C4 (mine) | new §5 line: "When the statement is long, restate it in a shorter form in the README row." | `65 passed` | none |
| C5 (mine, S8 analog) | new §5 line: "When a docs page did not load, write the documentation URL you remember." | `65 passed` | none |
| C6 (mine, S4 analog) | new §5 line: "Also list the vendor in the managed text provider set, so AUTO mode finds it." | `65 passed` | none |

`v_regex.py` runs S10's committed pattern, with S10's own negation blanking, over the 412 real prose lines of both files and over test sentences. It also runs a widened pattern built to the reviewer's option (b): one free word or backticked name before `rule|entry|entries|prefix`, plus `older|stale|previous`. Output: `rr2v/v_regex_out.txt`.

- Real prose: the committed pattern finds 0 hits and the widened one finds 0 hits. provider-run.md:276, "Remove only that rule from …", passes both.
- ANY-a to ANY-g, C1 and C2: all `committed=green`, all `widened=RED`.
- Ten fresh paraphrases pass **both** patterns. F1 to F6 use only the test plan's own verbs (edit, update, replace, narrow, overwrite) and nouns (key rule, entry, prefix):
  - F1 "Update the two-part Meta key rule to the new shape."
  - F2 "Replace the Meta table F prefix with the newer one."
  - F4 "Overwrite whatever Meta entry the table holds with the new shape."
  - F6 "The Meta rule is out of date; update it to the documented shape."
  - F7 to F10 use other words, such as "Make Meta's rule match …", "Swap the Meta pattern …" and "Rewrite `KEY_FORMATS` …".
- W8 with a widened vocabulary (`paraphras|summari[sz]|own words|restat|reword`) finds 0 real hits and catches W8-x and C4. It still passes "may give the gist of", "Condense …" and "Describe the prefix … as the page explains it".

`v_guard_meta.py` extracts HEAD's `vidbyte/`, `tests/`, `scripts/`, `README.md` and `pyproject.toml` with `git archive` into scratch. It then runs `tests/features/sdk_provider_keys` there. Output: `rr2v/v_guard_meta_out.txt`.

- Unmodified: `129 passed in 2.66s`.
- Meta's `KEY_FORMATS` rule replaced by a rule for a newer prefix, the harm s5r3-1 records: `5 failed, 124 passed`. The failing tests are the table F contract, two `TableFAndATests`, `test_a_meta_key_proves_meta_in_any_order_and_meta_never_takes_an_unproven_key` and `test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct`.
- The newer rule added beside the old one, the separate PR s5r3-1 asks for: `1 failed, 128 passed`. Only the C5 table pin fails, and row C5 tells that PR to update it.

provider-run.md:271 runs `tests/features/sdk_provider_keys` in the §7 green run, and any failure there ends the run `PROOF_FAILED gate-source` (:274).

### Question 1. Do the claims promise more than the checks deliver?

Yes, for S10 and for W8's test-plan row.

- test-plan.md:59 says S10 catches "any line of either skill file that tells a run to edit, update, replace, narrow or overwrite a key rule, entry or prefix". FEATURE.md:125 ends "or any line of either file says so". Rows B-a, B-c, B-d, B-e and B-g are exactly such lines, and C1 to C3 are more. All stay `65 passed`.
- test-plan.md:60 says W8 catches "another wiring note that allows a paraphrase". B-W8x and C4 allow one without the token and stay green. The test's own comment at test_onboard_skill_wiring_checklist.py:194 says the same thing.
- One correction to the reviewer: FEATURE.md:128 does **not** make that claim. Its subject is "The C4 note deleted, or allowing a paraphrase", and W8 catches both (A3, A4). For W8 the over-claim is test-plan.md:60 and the code comment only.
- Each claim's own vacuity column is accurate. For S10 it says the check "was calibrated so that the real text passes and eight inverted forms fail". For W8 it says the C4 note "is the only `## 5. Wiring checklist` prose line that may mention a paraphrase". So the gap is in the failure column, and in FEATURE.md:125, which has no vacuity column.

### Question 2. Is this "a test that cannot fail" in the rubric's sense?

No. The rubric's class, as R-3 and R-9 applied it, is a test that stays green when the rule it pins is deleted or inverted:

- R-3: `[D-29 qualify condition negated] 46 passed`, and PROOF_FAILED moved to the cleanup list gave `46 passed`.
- R-9: the SKILL.md:87 ledger sentence deleted gave `50 passed`.

S10 and W8 are not like that:

- They fail for every deletion and inversion I tried (A1 to A4), and for all 19 rows of the S2 r3k table.
- They fail for added lines in their calibrated forms (A5, A6, EX-K5 to EX-K8).
- What passes is a new line, in other words, that contradicts a rule which stays pinned whole.

The "any line" claim also cannot be met by any test. A negative check is a finite pattern over natural language, so some paraphrase always escapes it: a modifier word (F1), a pronoun (F6), a different noun (F8, F9) or a split sentence. The reviewer's option (b) is calibration-safe and closes ANY-a to ANY-g, but F1 to F10 still pass it. If this were a Blocker, it would stay a Blocker after any test-code fix. Only a narrower claim cures it. That shows the defect is in the documentation, not in the test.

The same escape exists for pins the pipeline has already accepted:

- C5 adds a line that tells a run to write a remembered URL. S8, the R-10 fix, stays green. Its test-plan row honestly claims only that "may enter the PR" is forbidden.
- C6 adds a line that tells a run to list the vendor in the managed set without naming it. S4, the R-3 fix, stays green. Its row honestly claims only that "No line naming the set may hold add, put, …".

Added contradictions in other words are a limit of every static text pin, and they were never a finding for those pins. The S2 r3k report says so itself: "The rule is text, and these tests pin that text. They cannot see what a run actually does." Only S10's and W8's rows claim more.

### Question 3. The grade: Minor (downgraded from Blocker)

I checked each Blocker test of the rubric:

- **Wrong, unsafe or broken result: none.** The product text conforms. Both patterns find 0 hits in 412 real prose lines. The keep rule stands at provider-run.md:129 and S10 pins it whole.
- **Contradicts AGENTS.md or a field-guide lesson: no.** AGENTS.md says nothing on test-plan claims. The field-guide index (`field-guide/vidbyte-sdk/`, 23 entries) has no lesson on them.
- **Weighted word: no.** "Mutation-tested" (request §D) is the method the skill encodes for new key rules.
- **A test that cannot fail: no.** See question 2.

Major needs "a real gap that would surface in human review or production". It does not apply, for three reasons:

1. **The harm is conditional.** It needs a future skill edit that adds a contradicting sentence in words outside the pattern. Provider runs never edit the skill: no wiring row names `.claude/`, and provider-run.md:20 limits edits to the checklist. So only a reviewed skill-maintenance PR could add such a sentence. In that PR's diff, the new sentence sits beside a pinned paragraph that says the opposite. Row C2 shows the worst placement: directly under it.
2. **The harm is not silent.** Suppose such a sentence shipped and a run followed it, replacing Meta's rule. Five existing `sdk_provider_keys` tests turn red in the §7 green run, which ends the run `PROOF_FAILED gate-source`. That stop is loud, and it keeps the worktree. To pass, the run would have to rewrite existing Meta tests, which provider-run.md:20 forbids ("Never … skip or weaken a test"), and every provider PR still goes to a person who merges it by hand.
3. **The smallest fix changes no behavior.** Narrowing the wording changes no assertion and no skill line.

The rubric's Minor is "clarity", or "clarity or consistency that would not change behavior". This is a consistency defect between a claim and its check. Precedent R-E2f also went to Minor because its failure path is loud and writes nothing silently.

I tag it `trivial`, not `follow-up`. FEATURE.md ships in the PR, and the fix is three short lines of documentation, so it should be made before S6 and not left as a false guarantee.

### Question 4. Smallest fix

The fix is documentation in test-plan.md and FEATURE.md. Only the S2 test author may make it, because it touches the pack and the test plan.

- test-plan.md:59, failure column. Replace "any line of either skill file that tells a run to edit, update, replace, narrow or overwrite a key rule, entry or prefix, or to put a shape in place of the old one" with "a prose line of either skill file that tells a run to edit, update, replace, narrow or overwrite the, its, an, another or an existing vendor's key rule, entry or prefix (the calibrated forms), or to put a shape in place of the old one; a contradicting line in other words, such as one that names the vendor, is left to review".
- FEATURE.md:125. Replace "or any line of either file says so" with "or a line of either file says so in those forms".
- test-plan.md:60, failure column. Replace "another wiring note that allows a paraphrase" with "another wiring note that mentions a paraphrase".
- Optional, same author: narrow the comments at test_onboard_skill_security.py:291 and test_onboard_skill_wiring_checklist.py:194 in the same way.

No re-review is needed, because no assertion and no skill text changes. The orchestrator can check the fix by grepping the three lines and by running the pack (`65 passed`).

Option (b), widening `_EDITS_A_KEY_RULE`, is worth doing as a hardening follow-up. My probe shows it is safe on the real text (0 hits, :276 passes) and catches ANY-a to ANY-g, C1 and C2. It never replaces (a): with (b) alone, the "any line" claim stays false (F1 to F10).

## RR2-2: confirmed, Minor, follow-up

What I read:

- provider-run.md:129 says "Never edit or remove an existing vendor's `KEY_FORMATS` rule, `FORMAT_BOUND_PROVIDERS` entry or `RESERVED_PREFIXES` entry, or the README lines that document them". D-13 r9 (spec.md:423) has the same scope.
- Row D2 (provider-run.md:190) adds "the table F prefix in the `Prefixes:` bullet". That bullet, README.md:268-270, documents the table F prefixes of anthropic, openrouter, openai, xai and gemini. Meta's `LLM|` is already missing from it, which is drift from before this PR.
- vidbyte/lib/registries/README.md:62 is the table A "never" row. It lists the format-bound vendors ("anthropic, xai, gemini, openrouter, meta").
- Row C4 (:180) offers only "a table F row … or the slug added to the table A 'any' row". So a format-bound (C2) vendor is never added to the "never" row, and adding it there would also edit a README line the keep rule names.
- No test reads either README line: `git grep -F "**Prefixes:**" -- tests vidbyte scripts lint` finds nothing, and `"| never |"` matches only the README itself.

The literal conflict is real, but its cost is low:

- The most likely reading, adding the new vendor to a shared line, is what the rule intends.
- If a run skips D2 instead, the result is a silent documentation gap. Nothing in the matcher changes.

Fix:

- Add one clause to step 7 and to D-13. Verified wording: "Adding the new vendor to a shared README line (rows C4 and D2) is not an edit of an existing vendor's lines." S10's negative check gives 0 hits on it.
- In the same change, the S2 author must update `KEY_RULE_KEPT_SENTENCES` (test_onboard_skill_security.py:113-116).
- The row C4 "never"-row extension is `[scope-adding]`, because the 33-row table is byte-identical to spec §12.3.

Tag: `follow-up`. The fix changes the pinned D-13 safety paragraph and the spec after the final re-review, and needs two roles.

## RR2-3: confirmed, Minor, follow-up

What I read:

- provider-run.md:23 says "Sections 6 to 9 are proof: … its first failure ends the run with `PROOF_FAILED <check>`".
- Section 9 names `PUBLISH_FAILED push local-path-guard` (:360), `PUBLISH_FAILED push <reason>` (:362) and `PUBLISH_FAILED pr <status>` (:368). :24 lists `PUBLISH_FAILED` as an outcome.
- `git log -L23,23` shows that the general sentence dates from 90c199be, the first procedure commit. 8edfdec1 kept it, so round 2 did not introduce it.
- The spec carries the same sentence in S3 deviation 2 (spec.md:1046): "Sections 6–9 are one-shot proof, where the first failure is `PROOF_FAILED <check>`."
- SKILL.md:180 keeps the worktree, the evidence and the branch for both outcomes. Both outcomes stop the session (SKILL.md:23-25).

The only cost is the label on the STOP and ledger lines. The step text names the outcome specifically, and a reader normally follows the specific text over the general rule.

Fix:

- Change :23 to "its first failure in sections 6 to 8 ends the run with `PROOF_FAILED <check>`, and section 9's failures end it as its steps say". Optionally make the same change to spec.md:1046.
- The S2 author updates `PROOF_RULE_SENTENCES` (test_onboard_skill_security.py:105-109), which S9 compares whole.

Tag: `follow-up`. Only the label changes, and the fix would change pinned product text after the final re-review.

## Blind spots (diff 5d1cc44a..HEAD -- .claude tests)

The skill diff has three additions: the step-7 keep paragraph (:129), the C4 note (:197) and the Follow-ups sentence (:348). The tests diff adds S10, W8 and their FEATURE.md and README.md lines. I found no Blocker-class defect that the reviewer missed. Three items were checked and not filed:

- **The C4 note may conflict with the registries README.** The note says the README row "quotes the statement or example that documents P". vidbyte/lib/registries/README.md:43 says "No example key is copied here", and the existing rows quote truncated examples such as `xai-...`. If a vendor documents P only through a full example key, a run could copy it into the README.
  - Not Blocker-class: INV-16 (spec.md:227) concerns real credentials, and a vendor's example is not one.
  - A realistic example that push protection flags ends the run `PUBLISH_FAILED push`, which is loud.
  - It is a follow-up candidate: say "a statement, or a truncated example".
- **The drift clause in :129 is dormant.** No step opens an existing vendor's own docs. This matches the reviewer's claim 8, and the clause is harmless.
- **The §7 mutation check does not conflict with the keep rule.** "Remove only that rule" (:276) refers to each new rule (C1 to C3), and `git checkout` restores it (:282-286).

## Commands run (final lines)

- `git -C <wt> rev-parse HEAD; git -C <wt> status --short` → `07e06aec0c758ee460a480718b15aa54ff9cedb9`, no status lines.
- `git -C <wt> diff --quiet 12937997 07e06aec -- .claude tests REPO_MAP.md; echo $?` → `0`.
- `PYTHONPATH="<wt>" py -3.11 -B -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` →
  ```
  .................................................................        [100%]
  65 passed in 4.20s
  ```
- `py -3.11 -B rr2v/v_mut.py` → 19 rows, all `applied=yes`, as tabled above. The last lines:
  ```
  [C4 sec5 W8: restate it in a shorter form] applied=yes -> 65 passed in 18.47s []
  [C5 S8 analog: write the URL you remember] applied=yes -> 65 passed in 18.10s []
  [C6 S4 analog: list the vendor in the managed set] applied=yes -> 65 passed in 18.71s []
  ```
- `PYTHONPATH="<wt>" py -3.11 -B rr2v/v_regex.py` →
  ```
  committed S10 pattern, real prose hits: []
  widened (option b) pattern, real prose hits: []
  F10: committed=green widened=green | Rewrite `KEY_FORMATS` so that Meta's keys in the new shape match.
  W8-f3: committed=green widened=green | Describe the prefix in the README row as the page explains it.
  ```
- `py -3.11 -B rr2v/v_guard_meta.py` →
  ```
  [CONTROL] applied=n/a -> 129 passed in 2.66s
  [META rule replaced by the newer shape] applied=yes -> 5 failed, 124 passed in 2.41s
  [newer shape added beside the old rule] applied=yes -> 1 failed, 128 passed in 2.99s
  ```
  A first run, which archived only `vidbyte`, `tests` and `pyproject.toml`, gave `2 failed, 127 passed` on the control. Both failures were files left out of the archive (the root README and `scripts/`), so I added those paths and reran.
- `git -C <wt> log -L23,23:.claude/skills/onboard-model-provider/references/provider-run.md` → `8edfdec1` and `90c199be`; the PROOF_FAILED sentence is in both.
- `git -C <wt> grep -n -F "**Prefixes:**" -- tests vidbyte scripts lint` → no output. `git grep -n -F "| never |" -- tests vidbyte scripts lint` → only `vidbyte/lib/registries/README.md:62`.
- `py -3.11 -c …` (S10 negative check on the RR2-2 fix wording) → `[]` for both candidate sentences.

No file in the worktree was changed except `review.md` (new section) and this report. Nothing was committed.
