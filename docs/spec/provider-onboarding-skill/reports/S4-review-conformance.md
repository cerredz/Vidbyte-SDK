LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — the skill meets the spec and the user's words on almost every ID. Two gaps block the user's real outcome: an A13 provider run always ends `PROOF_FAILED`, and the "never invent a URL" rule (INV-13) is never stated. Both fixes are small text edits.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The user's mid-run decision is honoured exactly:
  - SKILL.md `## What one invocation does` explains continuous mode (fetch, select, fresh worktree, one subagent, verify, loop).
  - It names exactly the user's three stops (`NO_CANDIDATE`, `BACKPRESSURE`, `PROOF_FAILED`) and says "There is no scheduler".
  - It keeps context small: a fresh subagent per vendor, and "Keep only the brief and the result block".
  - No routine, cron, `/schedule` or `/loop` remnant appears in any shipped file (sweep below).
- The fixed contracts are byte-identical to the spec: the 33-row wiring table (§12.3), the subagent brief (§8.5), the 12 output forms (§9.2) and the PROVIDER RESULT block (§8.5).
- The selection reads, the back-pressure filter and the skip dispositions behave as INV-3 to INV-5 require against live GitHub. The per-slug `state=all&head=cerredz:…` query maps real closed PRs correctly: #234 gives `closed unmerged`, and #319 gives a `merged_at` date.
- The self-check and `qualify_ids.py` probe name only symbols that exist. All eight §8.5 assertions ran against 7 existing providers and resolved: `price.input_per_million`/`output_per_million`/`cache_read_per_million`, `_PROVIDER_FAMILY_HINTS` as `(tokens, family)` pairs, and `Runner._normalize_provider_and_model`. The C9 and C6 templates use helpers that exist in the fixtures (`ScriptedGateway`, `header`, `flat`, `key_view`, `K_SK_UNPROVEN`, `refused`).

FINDINGS (ranked, most severe first, max 15)

R-C1 [Blocker] [out-of-lens: field-guide lesson / user's proof bar] .claude/skills/onboard-model-provider/references/provider-run.md:127 — Every provider run that applies wiring row A13 ends `PROOF_FAILED gate-source`, so the loop stops on a proof failure that is not real.
  Evidence:
    - provider-run.md:127 (§3.8) adds "a `PROVIDER_SUPPORT` tier (row A13) only with a first-party quote", and row A13 (:167) edits `vidbyte/lib/configs/structured_output.py`.
    - `tests/features/harness_threads/test_harness_threads_surface.py:224-232` (the same on origin/main 845a4d9b) does this:
      `scoped = ("vidbyte/tools", "vidbyte/lib/configs", OLD_SPEC_FOLDER)`
      `changed = git("diff", "--name-only", base, "--", *scoped)` with `base = merge_base()`
      `assert changed.stdout.split() == [] …`
    - The known-red rule at provider-run.md:300-310 excludes a failing node only when it fails on `<worktree>-main` built from `<base>`. There, merge-base = base and the scoped diff is empty, so the test passes, and then "Anything else ends the run `PROOF_FAILED gate-source`".
    - The field guide `local-ci-verification.md:45-49` warns: "Two `harness_threads` surface tests fail locally on any branch that touches `vidbyte/tools`, `vidbyte/lib/configs` … Check: The control edit on main fails the same way."
    - `git diff --name-only 9fefb065^ 9fefb065 -- vidbyte/tools vidbyte/lib/configs …` is the xAI structured-output tier commit, an A13-shaped edit. It prints `vidbyte/lib/configs/structured_output.py`, so the scoped list is non-empty.
    - 11 of 14 providers on main have a `PROVIDER_SUPPORT` entry, 9 of them NATIVE_SCHEMA or JSON_MODE. A13 is therefore the expected case, not an edge.
    - Neither the spec nor the code map mentions this test (grep for `test_branch_leaves|lib/configs` finds only the A13 row).
  Failure:
    - Input: a vendor whose first-party docs state a JSON-schema or JSON-object response format. State: §3.8 adds the A13 tier.
    - §8 then fails `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` 3 of 3 times on the branch, and the test passes 3 of 3 on the twin.
    - Wrong output: `STOP PROOF_FAILED <slug> gate-source`. The session stops on the user's stop (3), and the next invocation skips the vendor as `local-branch` forever, until the person cleans up by hand.
    - This blocks "creates a new pr per provider" for most OpenAI-compatible vendors.
  Smallest fix: change provider-run.md §3.8 so that a provider PR never touches `vidbyte/lib/configs`. The quoted tier goes under the PR's Follow-ups, and the text cites the harness_threads branch check. Row A13 stays in the table (33 refs pinned), and §3.8 states that it does not apply. Record this as an implementation deviation in spec §17.
  The alternative is to add the field guide's control-edit check to §8.3 (copy the branch's scoped file into the twin, and require the same failure there). It is larger, and it loosens exclusion.
  Spec IDs: FR-9, INV-15, INV-26 (provider runs), D-15, EC-40, §11 field guide `local-ci-verification.md`; request §C "known-red tests excepted".

R-C2 [Blocker] [weighted word "Never invent a URL" / INV-13] .claude/skills/onboard-model-provider/references/provider-run.md:213 — No rule ties a URL that the PR writes to a page opened in this run, and wiring row D1 requires such URLs.
  Evidence:
    - INV-13 (spec.md:215): "The skill never invents a vendor, URL, price or model ID. Every URL in a provider PR is one the subagent opened during that run." request.md §D lists "**Never** invent a URL, price, or model ID" as a weighted word.
    - `grep -n -i -E 'invent|opened during|you opened|opened in this run'` over both skill files prints nothing.
    - Facts are bound to opened pages (:40 "A fact is a base URL, chat path, …"; :50 "the 'opened' date the PR cites for every fact"; :330 Sources is "one row per fact").
    - Row D1 (:186), with :213 "One row in each table, shaped like its neighbours", adds a row to `vidbyte/providers/README.md` "Official Provider Documentation". That row's shape (README :91-105) is `| Provider | API overview | Contract reference |`, two or more doc links per vendor.
    - Those links are not a fact kind, so nothing requires them to be fetched, logged in `fetch-log.txt`, or cited with an opened date. FR-11 does not inspect them.
    - :148 "carries its source URL" also covers only price blocks and key rules.
  Failure:
    - Input: a provider run reaches D1. State: it fetched the docs and pricing pages, but no "Contract reference" page.
    - The procedure lets the agent fill a plausible reference URL it never opened. That is an invented URL in a merged README, and a first-party link in the PR with no opened date. This breaks INV-13 and request §C "cites every first-party source with the date it was opened".
  Smallest fix: add one bullet to provider-run.md "Rules for the whole run" and one sentence to §9 Sources:
    - The bullet: "Every URL you write into code, a README or the PR body is the final URL of a page in `<evidence>/fetch-log.txt`; never write a URL you did not open. D1's links are pages you fetched."
    - The sentence: the Sources table also lists each D1 link with its opened date.
  Spec IDs: INV-13, FR-10, NFR-5, D-24; request §C "Fail closed on facts", §D weighted "Never invent a URL".

R-C3 [Major] [EC-33 / D-13 collision check runs on the wrong tree] .claude/skills/onboard-model-provider/references/provider-run.md:123 — The fixture-fake collision probe and the A9 modality probe import from the shell's starting directory, not from `<worktree>`.
  Evidence:
    - :123 reads `PYTHONPATH=<worktree> <py> -c "import sys; from tests.features.sdk_provider_keys import provider_keys_fixtures as f; …"`.
    - :192 reads `PYTHONPATH=<worktree> <py> -c "…from vidbyte.lib.agents.modality_detector import ModalityDetector…"`.
    - Neither line has the `cd <worktree> && ` prefix that :136, :266, :288, :294 and :301 use. :16 and deviation 8 say "each shell call starts in another directory".
    - `PYTHONPATH="C:/some/worktree" py -3.11 -B -c "import sys; print(sys.path[:3])"` prints `['', 'C:\\some\\worktree', …]`. For `-c`, the current directory comes before PYTHONPATH.
  Failure:
    - Input: the subagent's shell starts in the launcher checkout, which is the session's directory and is often behind origin/main. State: a provider merged since that checkout was updated, and its fake `K_<X>` exists only on main.
    - The D-13 check "A fake key in the test fixtures starts with P" reads the launcher's older fixtures and prints `[]`. The collision goes unseen (fail-open on a fail-closed rule).
    - The A9 decision is likewise computed against the launcher's code rather than the wired worktree.
  Smallest fix: prefix both lines with `cd <worktree> && ` (they are not git commands, so deviation 8's rule applies).
  Spec IDs: EC-33, D-13, INV-11; request §C "Check whether a new rule could misroute another vendor's key".

R-C4 [Minor] [user's words: seed list "with selection criteria"] .claude/skills/onboard-model-provider/SKILL.md:219 — The seed list carries per-row reasons but not the criteria a seed vendor must meet, nor the ranking rule.
  Evidence:
    - request.md §C (settled): "Seeded candidate list lives in the skill, with selection criteria: suits the SDK's agent use; has an HTTP API with key auth; has first-party docs."
    - SKILL.md:219 says only "Walked in rank order. … The list changes only by a reviewed edit."
    - D-23's rank rule (spec.md:430: first-party evidence that every check can pass, then tools, then fewest wiring hazards) appears in neither skill file.
  Failure: a person who makes "a reviewed edit" to add or re-rank a vendor has no stated bar in the skill. The settled criteria live only in docs/, which AGENTS.md tells agents not to read.
  Smallest fix: one sentence under `## Seed vendors` stating the three request criteria and D-23's rank order.
  Spec IDs: D-23, FR-17, W-3; request §C "Seeded candidate list".

VERIFIED CLAIMS: <each claim checked and whether it held>
- "46/46 S2 tests pass": HELD (`46 passed in 1.19s`).
- "S3 changed no test": HELD (`git diff --stat 8e9b8b7f 32ca7991 -- tests` is empty).
- "The wiring table is byte-identical to spec §12.3": HELD (diff of the §12.3 occurrence against provider-run.md: identical).
- "The brief is byte-identical to §8.5", "the 12 output forms", "the PROVIDER RESULT block": HELD (all three diffs identical).
- "Every checklist path and symbol exists at HEAD": HELD (W3 passes). Extended to origin/main 845a4d9b, which provider runs actually wire against: all 33 rows' paths and symbols are present there too.
- "Diff scope: 2 skill files + REPO_MAP + docs/spec + S2 tests; nothing under vidbyte/lint/scripts/.github; ci-settings unchanged": HELD.
  - The name-status shows only those paths.
  - `git diff --stat … -- vidbyte lint scripts .github .claude/ci-settings.json` is empty.
  - `lint/baseline.json` is not in the diff.
  - The `ci-settings.json` blob is `f5c44a20…` at 72a4ade1 and at 32ca7991.
  - `claude.yml:50` still loads it.
- "AC-1 read-only run": HELD, reproduced 2026-10-17 UTC.
  - Preflight printed the toplevel, the origin URL, `true`, an e-mail (exit 0) and `py: python`.
  - Pass-top printed vintage `2026-10-11`, today `2026-10-17`, an empty open-provider list, and members `openai … typesafe`.
  - The walk printed for all 10 slugs: no PR, `remote-branch exit 2`, `local-branch exit 1`, `paths exit 1`. cerebras is the pick, and the run stopped before `git worktree add`.
- "The source stage fails only on known-red": HELD in substance. My run ended `2 failed, 5814 passed, 16 skipped`.
  - The two failures are exactly §11's harness test and the MCP waiter.
  - The MCP test then passed 3 of 3 reruns, so it is flaky per D-15.
  - `git status` was clean afterwards.
- "REPO_MAP `.claude/` entry: 4–5 sentences, unchanged on main": HELD. It has 5 sentences (C11 passes), and the base entry is identical on origin/main, so the change does not conflict with main.
- "Frontmatter keys and description ≤ 1,536": HELD (keys `description, disable-model-invocation, name`; 756 chars; flag `is True`; SKILL.md 241 lines).
- "Package stage: no `.claude/` in the wheel or sdist": NOT RE-RUN, because it writes build output. It is consistent with `pyproject.toml` `[tool.setuptools.packages.find] include = ["vidbyte*"]` and no MANIFEST.in.
- "PR-time evidence (AC-1/10/11/12) recorded in this PR's body": NOT YET. PR #1175 is a draft with a placeholder body. It is recorded in spec §6.2 and the S3 report, and S6 owns the PR body (S3's open item).
- Deviations 1–14 (spec §17): each is necessary or harmless and recorded. Deviation 8's rule is not applied to provider-run.md:123 and :192 (R-C3). No other unreported deviation was found.
- §5 diagram vs SKILL.md: two harmless divergences.
  - The diagram routes DISQUALIFIED straight to cleanup, while SKILL.md runs the FR-11 clean check first (correct per FR-11).
  - The diagram's NETWORK_BLOCKED stop omits the D-8 cleanup that SKILL.md applies.
- Weighted words checked on every path, all held except R-C2:
  - "one PR / one branch per provider" (single refspec, fixed branch name, no force);
  - "never merges";
  - "first-party only" for every fact kind;
  - "every new key rule mutation-checked" (C1/C2/C3 each, outside the contract pin);
  - "never invent a vendor" (FR-17 rule);
  - "skip forever" (closed-unmerged precedence);
  - "no changes" on back-pressure (X1, nothing written before the worktree add);
  - "must not depend on Windows" (AC-3 passes; `py -3.11` is only a probe fallback).

COMMANDS RUN: <each with its final lines>
- `git diff --stat origin/main...32ca7991` → `22 files changed, 4705 insertions(+), 1 deletion(-)`; `--name-status` → 2 A skill, M REPO_MAP.md, 11 A docs/spec, 8 A tests.
- `PYTHONPATH=<wt> py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` → `46 passed in 1.19s`.
- `git diff --stat 8e9b8b7f 32ca7991 -- tests; echo $?` → empty, `0`.
- Diffs of the wiring table, brief, §9.2 grammar and result block (spec vs skill, CR-stripped) → `WIRING TABLE IDENTICAL`, `BRIEF IDENTICAL`, `OUTPUT GRAMMAR IDENTICAL`, `RESULT BLOCK IDENTICAL`.
- Preflight and pass-top blocks of SKILL.md, verbatim → see AC-1 above. `git rev-parse origin/main` → `845a4d9b…`.
- The per-slug walk for all 10 seeds → all `remote-branch exit 2 local-branch exit 1 paths exit 1`, no PR lines.
- `gh api …pulls?state=all&head=cerredz:feat/provider-aware-tool-error-rendering` → `#234 closed unmerged`; `…registry-predicate` → `#319 closed 2026-07-27T20:40:42Z`.
- `gh api repos/cerredz/Vidbyte-SDK/pulls/1175` → `open draft=true head=feat/onboard-model-provider-skill sha=1144e198`, placeholder body.
- An inline read-only probe of the self-check assertions for kimi, deepseek, meta, mistral, glm, minimax and xai → all resolve. HINTS are `['openrouter','anthropic','claude','gemini','google','grok','xai']`.
- A loop over the 33 wiring rows with `git cat-file -e origin/main:<path>` and `git show … | grep -F <symbol>` → `check done`, no MISSING line.
- `PYTHONPATH=<wt> py -3.11 scripts/run_ci.py --stage source | tail` → `FAILED …test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, `FAILED …test_cancelled_waiter_does_not_break_transport`, `2 failed, 5814 passed, 16 skipped in 118.05s`, `CI failed: …-m pytest`.
- Three reruns of the MCP waiter node → `1 passed` ×3.
- The harness test's scoped diff over 9fefb065 → `vidbyte/lib/configs/structured_output.py`. `git diff --quiet 72a4ade1 32ca7991 -- tests/features/harness_threads` → exit 0.
- `grep -rln merge-base tests` → only `tests/features/harness_threads/test_harness_threads_surface.py`.
- `grep -n -i -E 'invent|opened during…'` over the skill files → no output.
- `PYTHONPATH="C:/some/worktree" py -3.11 -B -c "import sys; print(sys.path[:3])"` → `['', 'C:\\some\\worktree', …]`.
- The routine, cron and loop sweep over every non-docs file in the diff → no matches. In the skill, only SKILL.md:29 "There is no scheduler."
- `git status --short` → only `?? …/S4-review-conventions.md`, the parallel reviewer's file; the tree is otherwise clean.
