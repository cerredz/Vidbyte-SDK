LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the production change (one enum member, its cited comment, three README bullets) honors every binding AGENTS.md rule, field-guide entry and §12.4 item, but the 15 new tests and 10 extended tables break the field guide's 72-column comment lesson on every added comment line and leave the packs' modification patterns short of the tables the next served provider must touch.

Reviewed: `git diff origin/main...2ba4a678` (merge-base `845a4d9b`), 30 files, every hunk read with its whole file open. Worktree HEAD `94d3f381`, clean.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **`vidbyte/lib/constants/jev.py:72-83`.** `ModelProvider.META` is an enum member, never the string `"meta"`. The set is still a `frozenset[ModelProvider]` literal (runtime check: 7 members, all `ModelProvider`).
  - The rewritten comment is a PEP 8 block of 67/67/69/42 columns, directly above the set.
  - It mirrors the `a14b37e7e` precedent from #759 (`0d24f286`): repo, spec revision, section, commit. It also keeps the original citation for the six.
  - The header, `__all__` and every other constant are byte-identical. The header's PURPOSE says "provider set" with no count, so nothing in it became false.
- **`README.md`.** Exactly the three named bullets change (7+/7-), and the re-wrapped lines measure 45–77 columns, within the section's 78.
  - `LLM|` (Meta) documents the existing format-bound rule (`provider_keys.py:55`, `:60`).
  - A repo-wide grep (excluding `docs/` and `tests/`) finds no other served-provider list.
  - `REPO_MAP.md`, `llms.txt` and `artifacts/file_index.md` have no gateway entry, and no `.env.example` exists, so §12.5's "no map, llms or env change" is correct.
- **Test packs.**
  - **Prose:** every "six" is gone from both packs (grep: 0). The FEATURE.md and README File Index and Logs entries are updated, and every touched header's ROLE and RELATED DOCS cite the meta IDs.
  - **Modification patterns:** the lines that already existed were followed. `jev.py:6` (README plus both packs), `managed_text_fixtures.py:7`, `test_provider_keys_wire_contract.py:6` (RELAY_KEYS, CAP_FIELD), `test_managed_text_selection.py:6` (UNMANAGED) and `test_managed_text_wire_contract.py:6` (EMITTED_KEYS taken from spec §9.2, not from the adapter) are all honored.
  - **Fakes and imports:** every fake Meta key is concatenated (0 `LLM|<digit>` literals in the diff or in any commit message), and neither fixture module gained a module-level import.
- **Commit hygiene.**
  - The three product commits (`856e3c0a`, `b2306206`, `98b91e11`) each carry one work item and cite W-, FR- and AC- IDs.
  - Every commit has the attribution line.
  - No `.pyc` or cache file is in the diff, and no secret appears.
  - The branch merges cleanly with the moved `origin/main` (`6f5a7310`). #1055 touches none of the PR's files.

## FINDINGS (ranked, most severe first)

R-V1 [Major] [field guide: comment-format] tests/features/sdk_provider_keys/test_provider_keys_modes.py:260 (and 51 more added or edited lines across 12 test files) — Every comment line the PR adds or edits in the test packs is wider than 72 columns: 52 of 52, up to 154 columns
  Evidence: `git diff -U0 origin/main...2ba4a678 -- '*.py'` piped through an awk filter for added `#` lines longer than 72 columns:
  ```
  test_managed_text_acceptance.py: 10 of 10   test_provider_keys_acceptance.py: 8 of 8
  test_provider_keys_failures.py: 7 of 7      managed_text_fixtures.py: 4 of 4
  test_provider_keys_agents.py: 4 of 4        test_provider_keys_modes.py: 4 of 4
  test_provider_keys_wire_contract.py: 4 of 4 test_managed_text_wire_contract.py: 3 of 3
  test_provider_keys_security.py: 3 of 3      provider_keys_fixtures.py: 2 of 2
  test_provider_keys_matching.py: 2 of 2      test_managed_text_deadline.py: 1 of 1
  vidbyte/lib/constants/jev.py: 0 of 4        TOTAL >72: 52
  ```
  Examples:
  - `test_provider_keys_modes.py:260` (154 columns): "# meta-muse-managed-text INV-1 (enum and string spellings), INV-12 (an endpoint is still refused for meta), INV-14 (streaming still refuses meta)."
  - `managed_text_fixtures.py:39` (127 columns).
  - `test_provider_keys_failures.py:66` (137 columns). This one is an existing comment the PR edited.
  - `test_managed_text_acceptance.py:52` (122 columns).
  Failure: `field-guide/vidbyte-sdk/comment-format.md` says: "Wrap every comment line at 72 columns … A single-line comment that would pass 72 columns becomes a wrapped block too." Its Check is "`awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing for the files you touched."
  - **Tests are covered.** The evidence commit `f7a02bae`, which resolved the owner's comment ("if a comment is a multi line comment, then format it correctly"), wrapped the comments it added to a *test* file (`tests/features/coding_agent/test_coding_agent_cli.py`) at 61–70 columns.
  - **Why Major, not Blocker:** the entry's "When" says "SDK code", and both packs' existing comments are wide (20 of 21 lines in `test_provider_keys_modes.py` and 11 of 11 in `test_managed_text_acceptance.py` on `origin/main`). The byok pack merged with them after the rule existed.
  - **Spec gap:** spec §11 and §12.4 row 3 applied the entry to the `jev.py` block only, so S2 never ran the check.
  - **What a reviewer would write:** "multi-line comment, format it correctly."
  Smallest fix: re-wrap only the 52 added or edited comment lines as PEP 8 blocks of at most 72 columns, each directly above the code it explains. Leave the pre-existing wide lines alone: the entry says "leave untouched files alone", and AGENTS.md says "Do not rewrite untouched code". Change no code or assertion. Re-run the awk-over-diff check until it reports `TOTAL >72: 0`.
  Spec IDs: n/a. Spec §11 field-guide list and §12.4 row 3 scope the entry to `jev.py` only, which is the gap.

R-V2 [Minor] [agentic: file headers / COMMON MODIFICATION PATTERNS] tests/features/sdk_provider_keys/test_provider_keys_modes.py:6, tests/features/sdk_managed_text/test_managed_text_deadline.py:6, tests/features/sdk_managed_text/test_managed_text_wire_contract.py:6 — The packs' modification patterns still do not name three served-provider tables that a missing provider leaves silently stale, and the one trap S2 did record went into the feature's failure inventory
  Evidence:
  - **`SERVED`** (`test_provider_keys_modes.py:48`) is read only by `for served in SERVED: assertIn(...)` (`:230`). Its CMP line (`:6`) reads in full: "When a mode is added, add its row to the table R test and its refusals to the streaming test. Keep message checks to the facts table M binds."
  - **`MANAGED_PROVIDERS`** (`test_managed_text_deadline.py:48`) is read only by `for provider in MANAGED_PROVIDERS: assertIn(...)` (`:198`). Its CMP line (`:6`) covers retry waits only.
  - **`FULL_CONFIG`** (`test_managed_text_wire_contract.py:69`) is iterated with `.items()` (`:181`), so a provider without an entry is simply skipped by the emitted-keys test. That file's CMP (`:6`) names only `EMITTED_KEYS`, although `:111` and `:122` also index `ORACLE_KEYS` and `CAP_FIELD` per provider.
  - **`_CHAT_PROVIDERS`** (`managed_text_fixtures.py:60`) decides `provider_answer`'s usage shape and had to change for meta. The fixture's CMP (`:7`) does not name it.
  - The `ORACLE_KEYS` trap was added to `tests/features/sdk_managed_text/FEATURE.md:70` under "Known Failure Modes". Per `feature_test_packs.md`, that section lists ways *the feature* breaks, not test-harness traps. The trap is also, correctly, in `test_managed_text_acceptance.py:6`.
  Failure: `agentic-engineering/references/file_headers.md:15` says COMMON MODIFICATION PATTERNS must name "which other files must be updated in the same operation". Spec §13 had to discover these tables by hand ("Also present, with no `meta` entry: … `FULL_CONFIG` …, `MANAGED_PROVIDERS` …, and `SERVED`").
  - **For a stale `SERVED` or `MANAGED_PROVIDERS`,** no test goes red when the next provider joins the set. A missing `FULL_CONFIG` entry just drops that provider from the emitted-keys check.
  - **Why it matters beyond this PR:** this PR is the first widening of the set, so it is the template for the user's provider-onboarding agent (request.md §A, item #7). That agent will follow these CMP lines.
  Smallest fix: add one clause to each of four CMP lines. The `ORACLE_KEYS` clause must say "a key its own rule proves". Then delete `FEATURE.md:70` from Known Failure Modes; `test_managed_text_acceptance.py:6` already covers it.
  - `test_provider_keys_modes.py:6`: "When the gateway serves a new provider, add it to SERVED."
  - `test_managed_text_deadline.py:6`: "… add it to MANAGED_PROVIDERS."
  - `test_managed_text_wire_contract.py:6`: "… add it to ORACLE_KEYS, CAP_FIELD and FULL_CONFIG."
  - `managed_text_fixtures.py:7`: "… and to `_CHAT_PROVIDERS` when it answers in chat-completions usage."
  Spec IDs: W-3 (pack docs); the spec §13 "per-provider tables" facts.

R-V3 [Minor] [PEP 8 / module layout] tests/features/sdk_provider_keys/test_provider_keys_agents.py:494 — The new `MetaAgentTests` class introduces an E302 in a file that was clean on main, and `test_provider_keys_failures.py` defines two module constants mid-file, after three classes
  Evidence:
  - `py -3.11 -m ruff check --no-cache --isolated --preview --select E301,E302,E303,E305 <changed .py files>` gives `test_provider_keys_agents.py:494: class NonTextModelKeyTests … help: Add missing blank line(s)` and `Found 1 error.` The same check on `origin/main`'s copy of that file gives 0.
  - `test_provider_keys_failures.py:208` (`META_UNSUPPORTED_MODEL = answer(422, …)`) and `:210` (`META_MISSING_KEY = answer(502, …)`) sit after `GatewayCall` (`:62`), `FailureAssertions` (`:89`), `GatewayErrorWordingTests` (`:109`) and `RelayedProviderRefusalTests` (`:169`). Every other constant in that file is at `:42-59`.
  Failure: PEP 8 requires two blank lines before a top-level class. House style says "Optimize for reading": a reader looking for the module's scripted bodies finds them at the top everywhere else in the pack.
  Smallest fix: add one blank line before `test_provider_keys_agents.py:494`, and move the two `META_*` constants up beside `RELAY_FORBIDDEN` (`:59`).
  Spec IDs: n/a.

R-V4 [Minor] [house style: write shared logic once] tests/features/sdk_managed_text/test_managed_text_acceptance.py:218-224 — The README-section extraction block is now copied a third time instead of becoming a helper beside the new `readme_bullet`
  Evidence: the same six lines (search `README_SECTION_HEADING`, `fail` if it is absent, slice `rest`, find `next_heading`, cut `section`) appear at `test_managed_text_acceptance.py:198-204` (AC-18), at `:218-224` (new AC-13), and at `tests/features/sdk_provider_keys/test_provider_keys_acceptance.py:380-386`. S2 added module-level helpers `readme_bullet` (`:65`) and `names_word` (`:71`) in the same module but did not lift this block.
  Failure: AGENTS.md style principle 5, "Write Shared Logic Once", and the house-style rule against duplicated logic. The next README test (for example, the next served provider's bullets) will copy it a fourth time.
  Smallest fix: add a module-level `readme_section(text: str) -> str | None` next to `readme_bullet`, and call it from both tests in `test_managed_text_acceptance.py`. Leave the AC-18 test's six-name tuple alone: the test plan says the existing README tests keep binding the old facts on purpose.
  Spec IDs: n/a.

S6-owned, not S3 defects:
- **PR body.** The body must follow `.github/pull_request_template.md` (`CONTRIBUTING.md:75-83`).
  - The placeholder body on #1180 reads "Do not merge: this PR merges only after … the pre-merge live check (spec §12.5) has passed." AC-15 requires the sentence word for word: "This PR merges only after … (§12.5) has passed." The placeholder's lowercase "this" and its "spec §12.5" differ from that.
  - The body must also cover the EC-11 and EC-16 disclosure, the served Muse ids, the cap evidence, the harness_threads red test quoted at the head S6 ships, and the live check listed as an open merge prerequisite.
- **PR title.** It still reads `[WIP] feat: …`.

## VERIFIED CLAIMS

1. **Holds:** "jev.py diff is 5+/2- on lines 72-83 only" (S3). `git diff --stat origin/main...2ba4a678 -- vidbyte` gives `1 file changed, 5 insertions(+), 2 deletions(-)`, and the hunk touches only the comment and the new member.
2. **Holds:** "README 7+/7-, three bullets only" (S3, §12.4 row 6). The diff shows the Prefixes, Providers and Output cap bullets only. The section contains `ProviderKeys` 0 times, and the edited lines measure 72/45/76/77/65/76/76 columns.
3. **Holds:** "the header names 'provider set' with no count, so nothing became false" (S3 tricky part 3). Checked at `jev.py:3-9`: ROLE, KNOWN EDGE CASES, RELATED DOCS and TESTS are all still accurate.
4. **Holds:** "the comment block is at most 72 columns" (§12.4 row 3). Measured 67/67/69/42, with the neighbours at 69/57 and 68/67.
5. **Holds:** "no other served-provider list in `vidbyte/`, `skills/` or the maps" (S3).
   - `git grep` (excluding `docs/` and `tests/`) finds only `README.md:337`/`:343` and `jev.py`.
   - `skills/sdk/SKILL.md:28` lists adapters, and `skills/sdk/update-skill-files.md:402` lists the 12 enum members. Neither is a served-provider list. Both are older gaps that predate this PR.
6. **Holds:** Q-5. No repo rule forces edits to `vidbyte/providers/README.md:45`/`:362` or `skills/usage/create_agent.md:33`.
   - `jev.py:6` names only the README managed-mode section and the two packs.
   - AGENTS.md:11 binds the README of a folder you change, and this PR changes nothing in `vidbyte/providers/` or `skills/`.
   - Neither file states a gateway fact this PR makes false: `providers/README.md` has no gateway content, and its "Meta Llama" section was already incomplete.
7. **Holds:** "area 183 passed" (test plan, S3). I re-ran it: `183 passed in 2.01s`.
8. **Holds:** "the selection test reads `MANAGED_MODELS`" (test-plan row AC-10). `test_managed_text_selection.py:254` has `for managed_provider in MANAGED_MODELS: self.assertIn(...)`.
9. **Holds:** "fake keys are built by concatenation" (NFR-3, briefing). A grep for `^\+.*LLM\|[0-9]` over the full diff returns 0, and the same grep over every branch commit message also returns 0. `K_META_2` is `"LLM" + "|" + "2" * 15 + "|" + "e" * 32`.
10. **Holds:** "fixtures do not import feature symbols at module level" (§13). Neither fixture module's import block changed.
11. **Holds:** "the 'six' prose is updated" (§13). `grep -rn -i '\bsix\b'` over both packs returns nothing.
12. **Holds:** "the implementer modified no test file" (§12.4 row 13). `git diff --stat ea63e319..2ba4a678 -- tests` is empty.
13. **Holds:** "no pricing, lint or baseline change, and no `docs/` change outside this run's folder" (§12.4 rows 9, 10 and 14). The diff stat over `pricing.py` and `lint/` is empty, and `docs/` outside `docs/spec/meta-muse-managed-text/` has no change.
14. **Does not hold literally, but is not a PR defect:** "`git diff --stat origin/main -- vidbyte` lists one file" (§12.4 row 1). Today it lists 33 files, because `origin/main` moved to `6f5a7310` (#1055 CodexHost). The three-dot form lists 1 file. S3 disclosed this. `git merge-tree --write-tree origin/main 2ba4a678` exits 0, so the merge is clean.
15. **Holds:** "lint `SDK-LINT: PASS`, with the pre-existing IMPROVED verdicts not ratcheted" (S3). My run shows exit 0 and no REGRESSED verdict. IMPROVED: A002 703→562, C011 2→1, S001 59→56, S009 350→346, S010 5→0, S025 263→261, S061 6→5, S063 4→3, exactly S3's list. `lint/baseline.json` is not in the diff.
16. **Holds:** the import check. It prints `…\worktrees\vidbyte-sdk-meta-muse-managed-text\vidbyte\__init__.py`.
17. **Partly holds:** "no assertion was weakened" (test plan).
    - Removing the `("meta", "llama-4")` row from `GatewayShapeTests` is inside the grant, and its positive case moved to the new `test_meta_builds_in_both_gateway_modes_and_still_refuses_a_custom_endpoint_and_streaming`.
    - However, 3 of the 10 extended tables (`SERVED`, `MANAGED_PROVIDERS`, `FULL_CONFIG`) are silent when stale (R-V2).

**Field-guide quick checks:**
- **`comment-format.md`:** the `jev.py` block passes. The test lines fail (R-V1).
- **`provider-api-contracts.md`:** passes.
  - `ModelPricingRegistry.default().resolve(META, "muse-spark-1.1")` returns 1.25, and so does the dated snapshot `muse-spark-1.1-2026-04-01`.
  - Scripted tests exist for Meta's documented 200, 400, 401 and 429 answers.
- **`review-scope.md`:** passes. Every product file traces to §12.3 rows 1-2, and every test file to row 3 or the S2 grant.
- **`operation-pricebook-rates.md`:** not applicable. No rate is touched (NFR-2 holds).
- **`strict-config-dataclasses.md` and `declarative-config-resolution.md`:** not applicable. No settings class, record, YAML or registry changes.
- **`blocking-lint-invariants.md`:** A003, A006, S012, C002 and C021 cannot move, because there is no new class, import edge, error class or harness constant. The full lint run shows none of them REGRESSED.
- **`agents-md-map.md`:** not applicable. AGENTS.md is not edited, and `REPO_MAP.md`, `llms.txt` and `artifacts/file_index.md` need no entry (grep: no gateway, managed-mode or relay entry).
- **`local-ci-verification.md`:** passes. The import check prints the worktree, and the known red test is the one the entry names (`assert 167 == 120` on main, 148 at merge-base `845a4d9b`). Semgrep cannot run locally (S3 disclosed this).
- **`jev-capability-layout.md`:** not applicable. The "list it in `__all__`" rule is for new capability constants. This PR adds no constant, and the `VIDBYTE_*` gateway constants stay out of `__all__` by byok D-22.

**§12.4 checklist, line by line:**
1. Only `jev.py` changes in `vidbyte/`: done (3-dot).
2. An enum member, not a string: done.
3. Comment at most 72 columns: done.
4. Citation for the six kept, and #710 cited at `c395349bd`: done.
5. `__all__`, header and other constants byte-identical: done.
6. README changes only the three bullets: done.
7. No key literal: done.
8. No other production file: done.
9. No pricing change: done.
10. Lint passes with no baseline raised: done.
11. Import check: done.
12. Full gate: S3 quotes it red only on the known harness_threads test, and package passes. I did not re-run it, per the briefing.
13. Implementer touched no test file: done.
14. `docs/` only in this run's folder: done.

**§12.5, line by line:**
- **Merge prerequisites in the PR body:** S6. The placeholder is close but not verbatim.
- **Template body:** S6.
- **Pre-merge live check:** open. It cannot run in the pipeline.
- **Behavior change, served ids, cap evidence, pre-existing red:** all S6.
- **No README change outside rows 2(a)-(c), and no llms, REPO_MAP, file_index, `.env.example` (none exists), export, baseline or design-doc change:** done.

## COMMANDS RUN

- `git diff --stat origin/main...2ba4a678`. Final line: `30 files changed, 2832 insertions(+), 51 deletions(-)`.
- `git diff origin/main...2ba4a678 -- <each path group>`. I read every hunk.
- `git log --reverse --format='==== %h %s%n%b' 845a4d9b..2ba4a678`. It lists 20 commits, and `grep -c "Co-Authored-By: Claude Opus 5.5"` over their bodies returns 20.
- `git diff -U0 origin/main...2ba4a678 -- '*.py' | awk '<added # lines > 72>'`. Final line: `TOTAL >72: 52`, with `vidbyte/lib/constants/jev.py: 0 of 4`.
- `git show f7a02bae -- tests/features/coding_agent/test_coding_agent_cli.py | grep '^+\s*#' | awk '{print length-1}'`. Widest added comment: 70 columns.
- `git show origin/main:<file> | grep -E '^\s*#' | awk 'length>72' | wc -l`. Results: `test_provider_keys_modes.py: 20 of 21` and `test_managed_text_acceptance.py: 11 of 11`.
- `py -3.11 lint/run.py` (one run). Exit 0. Final line: `SDK-LINT: PASS`. 70 RATCHETED, 8 IMPROVED, 0 REGRESSED.
- `PYTHONPATH=$(pwd) py -3.11 -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"`. Output: `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-meta-muse-managed-text\vidbyte\__init__.py`.
- `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider`. Final line: `183 passed in 2.01s`.
- `py -3.11 -m ruff check --no-cache --isolated --select E1,W2,F,I --line-length 400 <changed .py>`. Output: `All checks passed!`
- `py -3.11 -m ruff check --no-cache --isolated --preview --select E301,E302,E303,E305 <changed .py>`. Output: `test_provider_keys_agents.py:494 … Found 1 error.` The same check on `origin/main`'s copy of that file finds 0.
- `PYTHONPATH=$(pwd) py -3.11 -c "<ModelPricingRegistry.default().resolve(META, …)>"`. Output: `muse-spark-1.1 1.25`, `muse-spark-1.1-2026-04-01 1.25`, and the set `['anthropic','deepseek','gemini','kimi','meta','openai','xai'] frozenset True`.
- A grep over the full diff and every commit message for `LLM\|[0-9]`. Both counts are 0.
- `git grep -n -i -E "gateway (serves|dispatches)|six providers|…" -- ':!docs' ':!tests'`. Only the README and `jev.py` hits listed in claim 5.
- `grep -n -i "gateway|VIDBYTE_MANAGED|TextModelMode|relay|muse|kimi|api_keys|managed" llms.txt REPO_MAP.md artifacts/file_index.md`. None of the hits is a gateway or relay entry.
- `git diff --stat origin/main -- vidbyte | tail -1`. Output: `33 files changed …`. `git merge-tree --write-tree origin/main 2ba4a678` exits 0.
- `gh pr view 1180 --json title,isDraft,headRefOid,body`. Output: `isDraft: true`, `headRefOid: 94d3f381…`, title `[WIP] …`, placeholder body.
- `git status --short`. Empty before and after my runs.
