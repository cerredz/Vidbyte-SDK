LENS: conformance (S5 final re-review, round 2 of 2)
VERDICT: MERGEABLE AFTER FIXES — every round-1 fix and the s5r3-1 repair hold when executed, and the skill text conforms; but the S10 and W8 test-plan rows claim to catch phrasings their checks cannot fail for (RR2-1, a Blocker by the rubric's test-claim rule), which a two-line claim narrowing or one regex recalibration closes.

Reviewed at 12937997 (branch `feat/onboard-model-provider-skill`, worktree clean). Diffs reviewed: `git diff e98a2381..HEAD -- .claude REPO_MAP.md tests` (9 files, 448+/29-) and `git diff 5d1cc44a..HEAD -- .claude tests` (5 files, 77+/11-). All mutation work ran on fresh copies under `<scratchpad>/rr2/` through `s2_harness` (`S2_SYNTH`). Each anchor occurred exactly once and each edit was confirmed. The copies were removed afterwards.

FIX CONFIRMATION
- R-9 (X4/X10 could not fail for six claimed defects) — confirmed. X4 and X10 now compare the whole commands and sentences (`test_onboard_skill_commands.py`). The ledger-skip sentence is at SKILL.md:87. The S2 rr1 table has 66/66 mutations red. The pack gives `63 passed` at 5d1cc44a and `65 passed` at 12937997.
- R-10 (R-1 URL rule and R-6 add-failure branch unpinned) — confirmed. S8 pins the URL rule at provider-run.md:16 whole, and X2 pins the add-failure sentence at SKILL.md:112. Their rr1 rows are red.
- R-11 (the PR-body guard cannot pass in a root container or with HOME=/, and no outcome is named) — confirmed by execution. I ran the guard line, as read from provider-run.md:357, on three shells:
  - Git Bash: 46/46 scored cells.
  - WSL1 dash 0.5: 129/129.
  - WSL1 bash: 129/129.
  
  The 14 checkout and HOME layouts include `/workspace`, `/app`, HOME `/`, HOME unset, HOME empty, a node devcontainer, a mac-like home and a checkout outside HOME. G1's committed test function passes 10/10 on Linux dash. The outcome `PUBLISH_FAILED push local-path-guard` is at :360 and matches spec EC-63 (spec.md:358). Five independent R11 mutations are red: the segment slashes dropped, the backslash pattern dropped, `-n` dropped, the HOME strip dropped and the rerun bound removed.
- R-12 (URL rule vs the attribution line) — confirmed. The exception sentence is at provider-run.md:16, INV-13 (spec.md:216) quotes it, and S8 pins it. It occurs once in the spec and once in the skill.
- §9.1 Cerebras note (@c660063e) — confirmed. spec.md:633 now says the r3 checks were verified and that the D-11 check passes through the first-party `/api-reference/chat-completions` page. s5r2-3 (:1027) records it. The change is text only.
- s5r3-1 (relayed key-format lesson) @164ac9fd + pins @e9226643 — confirmed for the pinned forms. The step-7 keep rule is at provider-run.md:129, the C4 note at :197 and the Follow-ups sentence at :348, and they carry D-13 r9 (spec.md:423) in meaning. The K mutations are red against S10: the paragraph deleted, "keep the rule" turned into "replace the rule", and the Follow-ups sentence dropped. The C4 "or paraphrases the page" mutation is red against W8. The claims beyond those forms over-reach; see RR2-1.

WHAT THE IMPLEMENTATION GETS RIGHT
- The rewritten guard is a real fix, not a test artefact. It runs the same way under Git Bash, dash and bash and fails closed on a missing or unreadable body (`1:pr-body.md was not read`, `grep exit 0`). A clean body that holds the user name as a plain word, or `/app/`, `/dev/` and `/root/` inside URLs, passes.
- Round 2 and repair 3 change no contract the spec quotes. `contracts_diff.py` prints IDENTICAL for the 33 wiring rows, the subagent brief, the output grammar and the PROVIDER RESULT block. Every spec-quoted sentence I counted occurs in the skill.
- The s5r3-1 repair puts the rule where a run meets it: in `## 3. Qualify` step 7, the step that decides P. An overlap stays `key-prefix-collision`, and a newer shape goes to Follow-ups for a separate PR that adds it beside the old one.
- The tests carry no machine hard-coding. G1 uses `shutil.which("sh")` with a skipif, `tmp_path` and the fake user `s2guard`. The only Windows-looking string, test_onboard_skill_publish_guard.py:61, is built from `FAKE_USER`.

FINDINGS

RR2-1 [Blocker] [out-of-lens: test quality; the conformance defence for D-13 r9 / s5r3-1] docs/spec/provider-onboarding-skill/test-plan.md:59, :60; tests/features/onboard_model_provider_skill/FEATURE.md:125, :128; tests/features/onboard_model_provider_skill/test_onboard_skill_security.py:124-130; tests/features/onboard_model_provider_skill/test_onboard_skill_wiring_checklist.py:198 — S10 and W8 cannot fail for natural phrasings of the defects their test-plan rows claim to catch
  Evidence:
  - test-plan.md:59 (S10) claims it catches "any line of either skill file that tells a run to edit, update, replace, narrow or overwrite a key rule, entry or prefix". FEATURE.md:125 repeats this as "or any line of either file says so".
  - test-plan.md:60 (W8) claims it catches "another wiring note that allows a paraphrase". FEATURE.md:128 has the same claim.
  - The S10 negative regex (`_EDITS_A_KEY_RULE`, security.py:126) allows only a fixed list of words between the verb and the noun: `the`, `its`, `existing`, `old`, `vendor's`, `key` and similar. A vendor name, or an adjective outside that list, breaks the match.
  - W8 (wiring_checklist.py:198) matches the token `paraphras` only.

  `mut_rr2.py` added each of the lines below to a fresh copy as a new line. Every row applied, and each one leaves the pack at `65 passed`:
  - ANY-a: a §5 note, "When Meta's own docs show a newer key shape, update the Meta rule to that shape."
  - ANY-b: a §5 note, "… update the existing Meta key rule to it."
  - ANY-c: a §5 note, "… replace the existing Meta prefix with the new one."
  - ANY-d: a §5 note, "If the vendor changed its format, overwrite the older entry."
  - ANY-e: a §5 note, "If P overlaps, narrow the openai rule so P fits." This is the escape that S5-repair-3.md:76 says the overlap clause closes.
  - ANY-f: a §3 line after step 7, "If Meta's docs show `LLM_`, update the Meta rule to match."
  - ANY-g: a bullet in the run's top rules list, "… update the Meta rule to it."
  - W8-x: a §5 note, "The README row may summarize the vendor's statement in your own words."

  The controls in the canonical shape are red (`1 failed, 64 passed`, S10): "update its key rule", "replace an existing vendor's rule", and the §9 Changes line "edit the existing rule". A SKILL.md Rules bullet is red only through A4's whole-section pin, not S10. "W8-y … may paraphrase" is red against W8.
  Failure: Take a later edit to the skill, such as a §5 C1 note "When Meta's own docs show a newer key shape, update the Meta rule to that shape." The pack stays green, although the test plan says S10 makes it red. A provider run that follows the note replaces Meta's `LLM|` rule and strands every key issued in the old shape, which is the exact harm s5r3-1 records. The step-7 keep rule would still stand, because S10 pins it whole, so the skill would contradict itself rather than lose the rule. That makes this a test-claim defect, not a product defect. The rubric still names it: "a test that cannot fail for a defect its own test-plan row claims it catches". It is the same class as R-9.
  Smallest fix: either fix works.
  - (a) Documentation only, inside the strengthen-only grant. Narrow test-plan.md:59 and FEATURE.md:125 to the forms S10 catches: "a line that tells a run to edit … the, its, an existing or another vendor's key rule, entry or prefix". Narrow the W8 claim (test-plan.md:60, FEATURE.md:128) to "a wiring note that mentions a paraphrase".
  - (b) Widen `_EDITS_A_KEY_RULE` to allow one free word or backticked name before `rule|entry|entries|prefix`, and add `older|stale|previous`. Then recalibrate it so that the real text still passes; provider-run.md:276, "Remove only that rule from …", is the line the widened pattern must not hit. Add ANY-a to ANY-g and W8-x to the S2 mutation table.
  Spec IDs: D-13 (r9), EC-33, FR-7, INV-9, G-2, s5r3-1; precedent R-9.

RR2-2 [Minor] [consistency] .claude/skills/onboard-model-provider/references/provider-run.md:129 — The new keep rule's "README lines that document them" also covers the shared lines that rows D2 and C4 must touch
  Evidence:
  - provider-run.md:129 says "Never edit or remove an existing vendor's … entry, or the README lines that document them". This carries D-13 r9 (spec.md:423) verbatim.
  - Row D2 (provider-run.md:190) adds the new table F prefix to the root `README.md` `Prefixes:` bullet (README.md:268). That one bullet documents every existing vendor's table F rule.
  - vidbyte/lib/registries/README.md:62, the table A "never" row, documents the existing `FORMAT_BOUND_PROVIDERS` entries. A new C2 (format-bound) vendor belongs on that row, but row C4 (:180) offers only "a table F row … or the slug added to the table A 'any' row".
  - No test ties either README line to the code (`git grep` over tests, vidbyte and scripts).
  Failure: A literal run that wires a vendor with a documented prefix must edit the `Prefixes:` bullet (D2) while step 7 forbids editing the README lines that document the existing rules. If it resolves that conflict by skipping D2, the root README silently omits the new prefix (D2 is a silent row). In either case, a format-bound vendor never joins the table A "never" row. No behaviour of the matcher changes.
  Smallest fix: One clause in step 7 and in D-13: "adding the new vendor to a shared README line (rows C4 and D2) is not an edit of an existing vendor's lines". Update S10's whole-paragraph pin in the same commit. Adding "or, for a C2 vendor, its slug on the table A 'never' row" to row C4 is Minor [scope-adding] and belongs in follow-ups.
  Spec IDs: D-13 (r9), §12.3 rows C4 and D2, FR-8.

RR2-3 [Minor] [consistency] .claude/skills/onboard-model-provider/references/provider-run.md:23 — The proof rule names `PROOF_FAILED <check>` as the outcome of every first failure in sections 6 to 9, while section 9's failures are `PUBLISH_FAILED`
  Evidence:
  - provider-run.md:23 says "Sections 6 to 9 are proof: … its first failure ends the run with `PROOF_FAILED <check>`".
  - Section 9 ends with `PUBLISH_FAILED push local-path-guard` (:360), `PUBLISH_FAILED push <reason>` (:362) and `PUBLISH_FAILED pr <status>` (:368).
  - Round 2 (8edfdec1) rewrote :23 to add "the body check's rerun in section 9 step 1" and kept the outcome as it was. :24 lists `PUBLISH_FAILED` as an outcome.
  - SKILL.md:180 keeps the worktree, its evidence and the branch for both outcomes, so nothing is lost.
  Failure: A run that applies the general rule over the step text reports a failed push as `PROOF_FAILED push`. The STOP line then mislabels it, and the cleanup does not change.
  Smallest fix: Change :23 to "its first failure in sections 6 to 8 ends the run with `PROOF_FAILED <check>`, and section 9's failures end it as its steps say". Update S9's `PROOF_RULE` pin in the same commit.
  Spec IDs: EC-63, D-16, FR-10.

VERIFIED CLAIMS
1. HEAD is 12937997a0ba2db836574c416aed24eeafc1cdc7 and `git status --short` is empty. Held.
2. The guard line read from provider-run.md:357 passes only clean bodies on Git Bash (46/46), WSL1 dash (129/129) and WSL1 bash (129/129). Every dirty case prints `N:` lines and `grep exit 0`; every clean body prints only `grep exit 1`. Held.
3. G1 behaves on Linux CI. The committed `test_the_pr_body_guard_passes_only_a_clean_body` passes 10/10 under WSL1 dash, run through a pytest stub because WSL python3 has no pytest; `shutil.which("sh")` resolves there. Held.
4. The settled repair-2 residuals reproduce as described, and nothing else appears:
   - A launcher-checkout path inside HOME is caught (G1-real, L7, L8, L9), and one outside HOME is missed (G2, L10), which is settled.
   - A scheme-less vendor quote whose segment equals the user name fails closed, which is settled.
   - Observation only: a local path glued to a URL with no whitespace (`|https://x.example/a|/home/u/y |`) is stripped with the URL. This is the URL-strip trade-off; the Sources table writes cells with spaces.
   Held.
5. The spec's quotes of the skill are present at HEAD. "A URL you did not fetch never enters the PR" occurs once in the spec and once in the skill. The attribution exception occurs once in each, `PUBLISH_FAILED push local-path-guard` twice in the spec and once in the skill, and "Each step runs only after…" once in each. `contracts_diff.py` prints IDENTICAL for the 33 rows, the brief, the grammar and the result block. Held.
6. INV-13 (spec.md:216) and provider-run.md:16 agree, attribution exception included, and D-16's last-line attribution matches §9. Held.
7. The s5r3-1 row's anchors (:129 and :348) point at the step-7 paragraph and the Follow-ups bullet at HEAD, and the C4 note is at :197. Held.
8. The drift-record clause at :129 ("When a page this run opened from that vendor's own docs …") is dormant, because no step opens an existing vendor's docs. The effective control is the keep rule, which S10 pins whole. This is an observation, not a finding: the clause is harmless and matches D-13.
9. The user's weighted words hold end to end at HEAD. SKILL.md is unchanged since e98a2381.
   - Location: `.claude/skills/onboard-model-provider/`.
   - One provider and one PR per pass: SKILL.md:116 and :129.
   - Idempotent selection from live state: :29 and :87.
   - Back-pressure 3: :85.
   - Stop when done: `NO_CANDIDATE` at :21, :104 and :191.
   - Fail closed on facts, and first-party only: :126 and :219.
   - The proof bar: provider-run.md:23 and sections 6 to 8.
   - No merging: SKILL.md:208.
   - No routine or cron: "There is no scheduler", :29.
   - Continuous mode, its stops and how it keeps context small: :17-29 and :116.
   - Not Windows-dependent: claim 2.
   Held.
10. No test hard-codes this machine. A grep for `422mi`, `C:/Users`, `AppData`, `MuseUbuntu` and `vidbyte-repos` over the pack and the skill matches only the `FAKE_USER`-built string at publish_guard.py:61, plus gitignored `__pycache__`. Held.
11. The round-3 pins are not vacuous. The K and W8 inversions are red, and the unmutated control is `65 passed`. Held for the pinned forms; not held for the "any line" claims (RR2-1).
12. Row s5r3-1's claim that "the verbatim-quote requirement was already met" holds as a pointer: spec.md:1028 cites provider-run.md :41, :43, :45-51 and :59-65. Held as cited; the drift itself is outside this PR (R-E7).

COMMANDS RUN
- `git -C <wt> rev-parse HEAD; git -C <wt> status --short` → `12937997a0ba2db836574c416aed24eeafc1cdc7`, with no status lines.
- `git -C <wt> diff --stat e98a2381..HEAD -- .claude REPO_MAP.md tests` → `9 files changed, 448 insertions(+), 29 deletions(-)`.
- `git -C <wt> diff --stat 5d1cc44a..HEAD -- .claude tests` → `5 files changed, 77 insertions(+), 11 deletions(-)`.
- `PYTHONPATH="<wt>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` (at 12937997) → `65 passed in 3.25s`. At 5d1cc44a it gave `63 passed in 2.01s`.
- `py -3.11 rr2/guard_rr2.py <provider-run.md> gitbash` → `SUMMARY gitbash: 46/46 scored cells as expected`.
- `py -3.11 rr2/guard_rr2.py <provider-run.md> linux-script`, then `MSYS_NO_PATHCONV=1 wsl.exe -d MuseUbuntu1 -u root -- env SHELL_UNDER_TEST=sh sh /mnt/c/.../rr2/lin/run.sh` and `linux-parse` → `SUMMARY linux dash: 129/129 scored cells as expected`.
- The same run with `SHELL_UNDER_TEST=bash` → `SUMMARY linux bash: 129/129 scored cells as expected`.
- `MSYS_NO_PATHCONV=1 wsl.exe -d MuseUbuntu1 -u root -- python3 -B rr2/g1_linux/run_g1.py /mnt/c/.../<wt> /mnt/c/.../rr2/g1_linux/tmp` → `SUMMARY G1 linux: 10 passed, 0 failed of 10`.
- `py -3.11 rr2/mut_rr2.py` (21 rows on fresh copies through `-p s2_harness`):
  - CONTROL → `65 passed`.
  - The three K rows and the W8 row → `1 failed, 64 passed`.
  - ANY-a to ANY-g → `65 passed` each.
  - ANY-h, ANY-ctl and ANY-ctl2 → `1 failed, 64 passed` (S10).
  - ANY-i → `1 failed, 64 passed` (A4).
  - The R11 rows → `3 failed`, `2 failed`, `8 failed`, `2 failed`, `1 failed` (S9 and G1).
- `py -3.11 -` (mut_rr2 with W8 rows) → CONTROL `65 passed in 3.01s`; W8-x "summarize … in your own words" `65 passed in 2.68s`; W8-y "may paraphrase" `1 failed, 64 passed in 3.31s`.
- `py -3.11 rr1/contracts_diff.py` (at 12937997) → IDENTICAL for the wiring rows (33), the subagent brief, the output grammar and the PROVIDER RESULT block.
- `grep -rn -i "422mi|C:/Users|AppData|MuseUbuntu|vidbyte-repos"` over the pack and the skill → only publish_guard.py:61 (built from `FAKE_USER`) and gitignored `__pycache__/*.pyc`; `grep exit 0`.
- `git -C <wt> grep -n "| anthropic, xai, gemini, openrouter, meta | never" HEAD` → `vidbyte/lib/registries/README.md:62`; `^- **Prefixes:**` → `README.md:268`. No test reads either line.
- `git -C <wt> log -L23,23:.claude/skills/onboard-model-provider/references/provider-run.md` → `8edfdec1 fix(skills): make the PR-body guard pass a clean body … [R-11]`, `90c199be docs(skills): add … per-provider procedure`.
