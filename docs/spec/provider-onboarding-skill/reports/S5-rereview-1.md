LENS: conformance (S5 final re-review, round 1)
VERDICT: MERGEABLE AFTER FIXES — 14 of the 15 repairs hold when executed, and spec r7 quotes the skill faithfully, but two S2 tests still cannot catch defects the test plan says they catch (one of them a loop that never stops), and the R-E8 guard never passes when a Linux checkout sits in a top-level directory such as `/workspace`.

Reviewed at e98a2381 (`git diff origin/main...HEAD`; `git diff 32ca7991..HEAD -- .claude REPO_MAP.md tests`). Scratch evidence is in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/rr1/` (written `<rr1>` below). Every script there reads the commands it tests from the skill files.

FIX CONFIRMATION (one line per R-id: confirmed | not confirmed — evidence)
- R-1 confirmed — provider-run.md:16 states the rule; :215 (D1 note) and :346 (Sources) tie the D1 links to 2xx fetch-log lines; spec INV-13 quotes :16 verbatim. Regression: the attribution line contradicts the rule (RR-3). No test pins the rule: deleting or inverting it gives `50 passed` (`<rr1>/rr1_mut.py`).
- R-2 confirmed — `<rr1>/r2_exec.py` (a copy of the repair reproducer, rerun at 6f5a7310) reads §8.3's fences from the file. A13 branch: check 1 printed `['vidbyte/lib/configs/structured_output.py']`, the control-edit twin printed the same `AssertionError: assert (['vidbyte/lib...ed_output.py'] == []`, verdict EXCLUDE. WIDE branch: check 1 printed two paths, verdict `PROOF_FAILED gate-source`. A1-only: `1 passed`, nothing to exclude. No twin was left behind.
- R-3 confirmed — `s2r/mut_r3r8.py` rerun on fresh copies: control `50 passed`, and each of the 33 other rows gives `1 failed, 49 passed` in the test it names.
- R-4 confirmed — the `awk` 72-column check over provider-run.md prints nothing, also with `<s>` filled as sambanova, deepinfra, fireworks or cerebras.
- R-5 confirmed — every `-c` line in provider-run.md starts `cd <worktree> && `. The one exception, :56 (`<py> -I -c`, the text form), is isolated and imports only the standard library.
- R-6 confirmed — executed in `<rr1>/clone`. Session A printed the SHA and `add exit 0`. Session B printed `fatal: a branch named 'feat/provider-cerebras' already exists`, `add exit 255` and no SHA. Cleanup while locked printed `cleanup exit 128` and kept the worktree, the evidence and the branch. After an unlock it printed `cleanup exit 0` and left nothing. No test pins the add-failure sentence (RR-1 note).
- R-7 confirmed — provider-run.md:41 adds the fact kinds and :85 the response-example rule; spec D-11, INV-9 and EC-30 match. The rule can pass for the top seeds through first-party links: Cerebras' `/api-reference/chat-completions` page shows `"usage" : { "prompt_tokens" : 69 , "completion_tokens" : 45`, and AI21's `/reference/jamba-api-response` has 12 `prompt_tokens` hits. The seed entry pages alone have none.
- R-8 confirmed — the R8-C9a/b/c, R8-BP and R8-D13 rows are red (same run as R-3).
- R-V4 confirmed — the D1 row in provider-run.md:187 is byte-identical to spec §12.3 (`<rr1>/contracts_diff.py`: 33 rows identical), and the Symbol cell still names both headings, as W2 pins.
- R-V5 confirmed — the description has the "Use it when …" sentence, 895 characters, and the frontmatter still has exactly 3 keys.
- R-C4 confirmed — SKILL.md:219 states the three criteria from request §C and D-23's rank order; spec §9.1 quotes it.
- R-E3 confirmed — the live AC-1 run printed `prs exit 0` for the open-PR read and for all 10 per-slug reads.
- R-E4 confirmed — SKILL.md:95 includes `test -e "$WORKTREE-main"`; :102 and :180 name the twin and its removal; spec INV-5(d) and the rollback match.
- R-E8 not confirmed (partial) — on Git Bash the guard no longer aborts, and an ordinary word no longer blocks the push. `<rr1>/re8_check.py` gives `grep exit 1` for a clean body and `grep exit 0` for the three local-path shapes. The review asked for an outcome "when it keeps matching", and none was named: when the worktree's parent is `/`, or when HOME is `/`, the guard matches permanently (RR-2).
- R-E2f confirmed — X13 exists, and the EX-VIN "vintage comparison inverted" mutation is red.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The fixed contracts are byte-identical to spec r7: the 33 wiring rows, the subagent brief, the 12 output forms and the PROVIDER RESULT block. The four commands r7 quotes (the paths skip read, the show-ref read, the add chain and the cleanup chain) and the eight skill sentences it quotes all occur verbatim in the skill. The spec-to-skill direction of the realignment is faithful.
- The user's decision is honoured: continuous mode, exactly the user's three stops, "There is no scheduler", one fresh subagent per vendor that keeps only the brief and the result, and no routine, cron, `/schedule`, `/loop` or "hourly" in any added line of `.claude`, `REPO_MAP.md` or `tests`.
- AC-1 reproduces live. Run verbatim in a scratch `--shared` clone pointed at GitHub, every preflight and pass-top line exits 0, `py: python`, vintage `2026-10-11`, today `2026-10-17`, no open provider PR, 14 members. All 10 seeds print `prs exit 0`, `remote-branch exit 2`, `local-branch exit 1` and `paths exit 1`, so cerebras (rank 1) is the pick, as the S3 report says.
- Red-first can be done on the current main. With only the A1 member `CEREBRAS = "cerebras"` added to `origin/main` 6f5a7310, the §4 red-first paths give `448 passed`, with no collection error. Any new C-, B4 or B5 test would therefore fail red while the pack collects, as D-15 requires.

FINDINGS (ranked, most severe first, max 15; new findings only, numbered RR-1, RR-2, …)
RR-1 [Blocker] [out-of-lens: test quality; conformance defence for INV-20 and INV-5] tests/features/onboard_model_provider_skill/test_onboard_skill_commands.py:325-334 (X10) and :158-174 (X4) — Two S2 tests cannot fail for defects the test plan says they catch. One uncaught defect makes a session re-research the same disqualified vendor forever.
  Evidence:
    - test-plan.md:33 (row D-19 / INV-9 / INV-20) and FEATURE.md:70 claim that X10 catches "a plain vendor 403 called NETWORK_BLOCKED". X10 checks only that the words `x-deny-reason`, `docs-unreachable` and `NETWORK_BLOCKED` appear in `## 2. Research`.
    - test-plan.md:27 (row INV-4 / INV-5 a–e) claims that X4 catches "local or remote branch, evidence path or session ledger ignored". X4 checks only that the phrases `-evidence` and "this session" appear anywhere in `## Each pass`.
    - `<rr1>/rr1_mut2.py` copies the skill fresh for each row, requires every anchor to occur exactly once, and runs the pack through `s2_harness`. Results:
      - control: `50 passed`.
      - provider-run.md:78 "is first checked against GitHub with" rewritten to "ends the run `NETWORK_BLOCKED` at once; it is not checked against GitHub with": `50 passed`.
      - `|| test -e "$WORKTREE-evidence"` removed from SKILL.md:95: `50 passed`.
      - SKILL.md:87 "Skip without a query a vendor that already has an outcome in this session's ledger, or whose slug is a member." reduced to "… a vendor whose slug is a member.": `50 passed`.
      - Controls in the same run were red as expected: the D-29 eligibility reading, the back-pressure off-by-one, and parallel subagents.
    - These are the same class as R-3, which the verifier confirmed as a Blocker.
  Failure:
    - Session ledger rule dropped: rank-1 vendor → `DISQUALIFIED` → D-8 cleanup removes its worktree and branch → the next pass's walk finds no skip rule for it, because disqualification is never persisted (INV-7) → it is selected again. The session loops on that vendor and never reaches a STOP (INV-1 "always ends").
    - Plain-403 rule turned into NETWORK_BLOCKED: a vendor host's bot protection stops the session. NETWORK_BLOCKED records nothing against the vendor (INV-20), so every later invocation stalls at that vendor. This is spec review r1-5's failure.
    - Evidence path dropped: a stale `-evidence` directory with old fetch-log lines is reused. Those lines could then satisfy R-1's "final URL of a line in `<evidence>/fetch-log.txt`".
    - The pack stays green through all three.
  Smallest fix (S2 test author, strengthen-only grant):
    - X10: pin the prose lines at provider-run.md:77-78. "A match, or a sandbox or tool permission-denial message for the fetch, ends the run `NETWORK_BLOCKED`" and "is first checked against GitHub" must each sit on one line, and a negative pattern must forbid a line that ends a run NETWORK_BLOCKED on an HTTP status alone.
    - X4: compare the paths read as a whole string (all three `test -e`), and pin the sentence at SKILL.md:87.
    - While under the same grant (R-8 precedent, Major on its own): pin R-1's "Never invent a URL" bullet (provider-run.md:16; request §D weighted "**Never** invent a URL") and R-6's add-failure sentence (SKILL.md:112). Deleting either of them now gives `50 passed`.
  Spec IDs: INV-20, INV-5 (d), INV-5 (e), INV-1, INV-7, EC-21, EC-17; test-plan rows INV-4/INV-5 and D-19/INV-20.

RR-2 [Major] [fix confirmation R-E8; NFR-1 portability] .claude/skills/onboard-model-provider/references/provider-run.md:354, :357 — The PR-body guard never passes when the worktree's parent is `/` or HOME is `/`, and "never push until it prints `grep exit 1`" names no outcome, so such a run cannot finish.
  Evidence:
    - :354 is `grep -n -F -e "$(dirname "<worktree>")" -e "$HOME" -e "/$(basename "$HOME")/" …`.
    - :357: "When it prints a line, replace the path or name in that line … and run it again. Any exit other than 1 means the body is not yet clean or the check did not run: never push until it prints `grep exit 1`."
    - `<rr1>/re8_container.py` runs the line as read from the file against a body with a Sources table:
      - checkout `/workspace`, so `<worktree>` is `/workspace-onboard-cerebras` and its dirname is `/`, HOME=/root: `grep exit 0`, 2 lines matched;
      - HOME=/: `grep exit 0`;
      - HOME=/home/dev with a Sources URL that has a `/dev/` segment: `grep exit 0`;
      - control, checkout `/home/alice/src/Vidbyte-SDK`: `grep exit 1`.
    - The `dirname` pattern dates from S3. R-E8 (review.md:39) asked to "name an outcome" for a guard that keeps matching, and commit 39e37702's title claims it does.
  Failure:
    - A Linux container run, which §9.3 and D-27 name as the only place for `bypassPermissions`, often has the checkout in a top-level directory such as `/workspace` or `/app`. Every provider run there reaches §9 with a correct body, and the pattern `/` matches every Sources URL.
    - The procedure gives no exit. The subagent either loops, or "replaces the path" inside Sources URLs, which breaks request §C "The PR body cites **every** first-party source", or improvises an outcome outside the §8.5 grammar.
  Smallest fix:
    - Match the checkout path (`<worktree>` with its `-onboard-<slug>` suffix removed) instead of its parent directory, so the pattern is never `/`.
    - Skip the `$HOME` patterns when HOME is `/`.
    - Add: "If a line still matches after you rewrote every local path, or the match is inside a Sources URL, end the run `PUBLISH_FAILED push local-path-guard` without pushing."
  Spec IDs: NFR-1, D-16 (no local path), INV-9, FR-10 (body cites every source), §8.5 outcome grammar; review R-E8.

RR-3 [Minor] [weighted word, internal consistency; regression from R-1] .claude/skills/onboard-model-provider/references/provider-run.md:16 vs :349 (spec.md:216 INV-13 vs :425 D-16) — The new absolute URL rule forbids the attribution line that §9 requires last in every PR body.
  Evidence:
    - :16: "Every URL you write into code, a test, a README or the PR body is either the base URL fact … or the final URL of a line in `<evidence>/fetch-log.txt` … A URL you did not fetch never enters the PR, even when you know it."
    - :349: "and last, the pull-request attribution line your session's instructions give". This session's attribution line is `🤖 Generated with [Claude Code](https://claude.com/claude-code)`, a URL no run fetches.
    - The spec has the same conflict: INV-13 (r7) uses the same absolute wording, and D-16 says "The body ends with the attribution line".
    - The PR template (`.github/pull_request_template.md` on origin/main) holds no URL, so the attribution line is the only conflict.
  Failure: every provider run meets two contradictory instructions. It drops the attribution line, breaking D-16, or keeps it and breaks its own rule. A third option, fetching claude.com to put it in the fetch log, records a non-first-party page.
  Smallest fix:
    - In :16, add ", apart from the attribution line your session's instructions give".
    - Add the same clause to spec INV-13.
  Spec IDs: INV-13, D-16; request §D "Never invent a URL" (not violated in spirit, because the attribution URL is not invented).

VERIFIED CLAIMS:
- "AC-1: the preflight and pass-top commands exit 0 and cerebras is the first pick" (S3 report, spec §6.2): HELD, re-derived on 2026-10-17 in `<rr1>/clone` (`<rr1>/ac1_out.txt`). The commands were run as read from SKILL.md, with the e-mail address withheld. `git fetch` ran in the scratch clone, so the shared repo's refs were not written.
- "S2 r3r8: 34 of 34 mutations red, control 50 passed" (S2-test-author-r3r8.md, review.md R-3/R-8): HELD (rerun).
- "R-2: A13 exclusion only with the scoped diff plus control edit; a wider configs change fails closed" (S5-repair-1.md): HELD (rerun, cases A13, WIDE and A1).
- "R-6: a second add prints `add exit 255` and no SHA; a failed remove keeps everything" (S5-repair-1.md): HELD (`add exit 255`, `cleanup exit 128`, `left: worktree yes evidence yes branch yes`).
- "R-E8: `grep exit 1` for a clean body, `grep exit 0` for local paths under Git Bash in the C locale" (S5-repair-1.md): HELD for the Windows shapes, NOT HELD for Linux top-level checkouts and HOME=/ (RR-2).
- "df0f4bb7 only adds or strengthens; no assertion deleted" (brief, §14 "Never weaken tests"): HELD. `git diff 8e9b8b7f..df0f4bb7 -- tests` removes only header text, which longer text replaces, and the body of `fenced_blocks()`, which now delegates to `fenced_blocks_with_info()` with the same return value. No skip or xfail was added. `git log origin/main..HEAD -- tests` shows only 90e584ef and df0f4bb7.
- "Budget §8.4 and boundaries §14": HELD.
  - Outside `docs/spec/provider-onboarding-skill/` and `tests/features/onboard_model_provider_skill/`, the diff names only `SKILL.md`, `references/provider-run.md` and `REPO_MAP.md`: 2 new files, 1 modified, 0 deliverable `.py`.
  - `git diff --quiet origin/main...HEAD -- vidbyte lint scripts .github .claude/ci-settings.json` exits 0, and `git diff origin/main...HEAD -- lint/baseline.json` is 0 bytes.
  - The `ci-settings.json` blob is `f5c44a20…` at 72a4ade1 and at HEAD.
  - There is no `git stash`, force push, `gh pr` or `gh issue` in either file, and no key-shaped literal in the added lines.
- "Red-first runs red while the pack collects" (D-15, AC-8): HELD at current main (`448 passed` with A1 only).
- "Spec §9.1 Cerebras: Every check was verified on first-party pages": STALE but harmless. r6 added the response-example check after the seed list was verified. That check can pass for Cerebras through `/api-reference/chat-completions`, two first-party links from the docs URL.
- "All 15 R-ids are fixed in the commits review.md names": HELD. `git show --stat` of each commit touches only the files its fix names.
- Field guide `local-ci-verification.md:45-50`, cited in spec D-15 and §11: HELD; those lines are the harness_threads section.
- Not pinned by any test, though each is spec text the user relies on (each mutation gives `50 passed`):
  - R-1, R-6, R-7, R-E3, R-E4, R-5, R-E8, R-C4 and R-V4: deleting or inverting the repaired sentence or command passes.
  - INV-1 ("exactly one STOP line" → "one or more").
  - INV-11 (table F from the gitleaks config).
  - INV-12 (rounding allowed).
  - FR-17 ("find one more vendor by web search").
  - RR-1 asks the S2 author to pin R-1 and R-6. The rest can be follow-ups.
- Weighted words on every path:
  - Held: "one PR per provider" (single refspec, no force, D-8 kept states); "never merges" (SKILL.md:208, provider-run.md:371); "skip forever" (SKILL.md:100, :209); "no changes" at back-pressure (nothing written before the add); "first-party only"; "every new key rule mutation-checked" (C1, C2, C3, outside the contract pin); "never invent a vendor" (SKILL.md:215).
  - Has an exception: "never invent a URL" (RR-3).
  - Not on every path: "cites every source" (RR-2, container path).
- Spec §5 flowchart compared with SKILL.md. These divergences change no behaviour; they are framing:
  - (1) Node W omits the session-ledger skip (INV-5e) and the paths read (worktree, `-evidence`, `-main`).
  - (2) `DISQUALIFIED` goes straight to cleanup. SKILL.md:160-168 first runs the clean check, which can stop `RESULT_UNVERIFIED worktree-not-clean` (EC-49).
  - (3) `NETWORK_BLOCKED` from the subagent goes straight to STOP. SKILL.md runs the clean check and the D-8 cleanup first.
  - (4) There is no edge for a failed fetch, a failed `gh api` read (`prs exit` not 0), or an `ls-remote` exit other than 0 or 2 (`NETWORK_BLOCKED`, EC-56).
  - (5) There is no edge for a missing result block (`no-result`).
  - (6) There is no edge for `cleanup exit` not 0, after which the session continues with no STOP (r7 added only the failed-add edge).
  - (7) The cleanup node omits the evidence directory.
  - The sequence diagram matches.
- §4 snippet: HELD. The grammar of every illustrative line is in SKILL.md `## Output`. Steps 1–6 match `## Each pass` and the subagent and verification sections.
- Deviations: S3's 14 deviations are recorded in spec §17. The S5 repair's judgment call (the base URL as a quoted fact, not an opened page) is recorded in INV-13 r7 (s5a-10). R-7 option (c) was not taken and is recorded in s5r1-2. No unreported deviation was found.
- REPO_MAP `.claude/` entry: HELD (5 sentences, no file name or command, describes the review settings and invoked skills; C11 passes).

COMMANDS RUN:
- `git log --oneline -40`; `git merge-base origin/main HEAD` → `72a4ade1…`; HEAD `e98a2381`. `git status --short` → ` M docs/spec/provider-onboarding-skill/pipeline.md` (not this reviewer's edit).
- `PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` → `50 passed in 0.90s`.
- `git diff --stat origin/main...HEAD` → 30 files, `5929 insertions(+), 1 deletion(-)`; `git diff --stat 32ca7991..HEAD -- .claude REPO_MAP.md tests` → 9 files, `239 insertions(+), 41 deletions(-)`; `git diff origin/main...HEAD -- lint/baseline.json | wc -c` → `0`.
- `git diff 8e9b8b7f..df0f4bb7 -- tests | grep -E '^-[^-]'` → 13 lines, all header text or the `fenced_blocks` body.
- `py -3.11 <rr1>/ac1_run.py <SKILL.md> <rr1>/clone` → preflight `true`, `py: python`, `exit 0` on each line; pass top `2026-10-11`, `2026-10-17`, `prs exit 0`, 14 members; walk ×10 → `prs exit 0`, `remote-branch exit 2`, `local-branch exit 1`, `paths exit 1`.
- `git archive origin/main | tar -x -C <rr1>/a1tree`; A1 member added; red-first command → `pytest exit 0`, `448 passed in 2.98s`.
- `curl -sSL --max-time 60 …` for 9 first-party pages into `<rr1>/dl_r7/` (all `200`, curl-exit=0), plus the procedure's text-form command → `cerebras-chat prompt_tokens=15 completion_tokens=35 choices=68`; `ai21-resp prompt_tokens=12 completion_tokens=12 choices=20`; the seed docs and pricing entry pages → 0.
- `py -3.11 <rr1>/re8_check.py` → clean `grep exit 1`; Git Bash, drive-letter backslash and forward-slash paths `grep exit 0`; attribution line `grep exit 1`.
- `py -3.11 <rr1>/re8_container.py` → `/workspace` checkout `grep exit 0`; HOME=/ `grep exit 0`; `/dev/` URL `grep exit 0`; control `grep exit 1`.
- The `awk` 72-column check, plain and slug-filled → no output; `grep -n -E -- '-c "' provider-run.md | grep -v 'cd <worktree> && '` → only :56 (`<py> -I -c`).
- `py -3.11 <rr1>/contracts_diff.py <worktree>` → wiring rows, brief, output grammar and result block `IDENTICAL`; 4 commands and 8 sentences found in both spec and skill.
- `py -3.11 <scratchpad>/s2r/mut_r3r8.py` → CONTROL `50 passed`; 33 other rows `1 failed, 49 passed`.
- `py -3.11 <rr1>/rr1_mut.py` → CONTROL `50 passed`. All 18 repair-rule mutations pass with `50 passed`. FR-15, INV-17 and INV-18 (draft PR) are red.
- `py -3.11 <rr1>/rr1_mut2.py` → CONTROL `50 passed`. X4 evidence path, X4 session ledger, X4 local-branch text, X10 plain 403, INV-1, INV-11 and FR-17 give `50 passed`. A3, C6, X12 (off by one) and S5 are red.
- In `<rr1>/clone`: the add block twice → `add exit 0`, then `fatal: a branch named 'feat/provider-cerebras' already exists` / `add exit 255`. Cleanup while locked → `cleanup exit 128`, everything kept; after an unlock → `cleanup exit 0`.
- `py -3.11 <rr1>/r2_exec.py 6f5a7310…` → A13 `verdict: EXCLUDE`; WIDE `verdict: PROOF_FAILED gate-source`; A1 `1 passed`; `twin left behind: False` ×3.
- `git cat-file -e origin/main:<dir>/README.md` for every touched folder → every README that exists is in §1 Orient's list.
- `git show --stat` for the 13 fix commits → each touches only the files its fix names.
- Not rerun: the full gate. The orchestrator recorded `SDK-LINT: PASS`, `1 failed, 5819 passed, 16 skipped` (known-red harness test) and the package stage `CI passed.`.
