# S2 test author report: provider-onboarding-skill

Stage: S2 test author · Spec: `docs/spec/provider-onboarding-skill/spec.md` r3 · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill` · Branch: `feat/onboard-model-provider-skill` · Base of this stage: `b6cdf3fa`
Commits: `90e584ef` test(skills): add failing tests for provider-onboarding-skill [AC-1..AC-15] · `8e9b8b7f` docs(spec): record test proof for provider-onboarding-skill

## Outcome

The skill's failure modes are now executable checks. All 46 tests are red because the skill files and the map entry do not exist yet, and nothing else causes a failure. A spec-conforming skill makes all 46 pass. Each of 101 targeted defects is caught by the test named for it, and 12 benign variants a correct implementation might write pass. Every test stays valid inside the provider PRs the skill will open, because no test reads git state or pins the provider list, the member count, `PRICING_AS_OF` or a line number.

## Inventory (what was written)

`tests/features/onboard_model_provider_skill/`:

| File | Content |
|---|---|
| `README.md` | Folder intent, non-goals, File Index (S020 parity), log. |
| `FEATURE.md` | Contract, actors, inputs, outcomes, invariants (provider-branch invariance, non-vacuity), 38 failure-mode lines tagged with test codes, historical regressions, test suite map, omitted strategies. |
| `onboard_skill_fixtures.py` | Paths. Spec-r3 values spelled from the spec (11 + 10 headings, 7 constants, 6 enumerations, 12 §9.2 forms, both table headers, 10 seed slugs, 33 `WiringRow`s with kind and silent flag, the C6 reference test). `MarkdownDoc`: a fence-aware line classifier with sections, H2s, shell commands (continuations joined), code spans, fenced blocks, document-ordered commands and table rows. `split_row`. `SedEmulator`: POSIX BRE to Python, `sed -n 's/P/R/p'` semantics. |
| `test_onboard_skill_acceptance.py` | A1–A5 (5 tests): invocation line, §9.2 grammar, three stops plus continue-on-disqualify, rules, leave-behind. |
| `test_onboard_skill_contract.py` | C1–C12 (17 tests with parametrization): frontmatter, two-file folder, headings ×2, constants, seed table, seed hosts, brief, result block, enumerations ×5, verifying, publish, REPO_MAP. |
| `test_onboard_skill_wiring_checklist.py` | W1–W6 (6 tests): header and refs, cell grammar, tree existence, silent rows, C6 swap and collision check, the orchestrator's `sed` over the real table. |
| `test_onboard_skill_commands.py` | X1–X11 (11 tests): read-only pass-top, pass order and safe worktree add, vintage and member `sed` over the real sources, back-pressure and skip queries, preflight setup, `<py>` spelling, PYTHONPATH, gate commands and producers, mutation order, research protocol, named paths. |
| `test_onboard_skill_security.py` | S1–S6 (7 tests): forbidden constructs ×2, GitHub writes, push refspec, managed set, D-29 with the real `Runner`, key shapes. |

Also written: `docs/spec/provider-onboarding-skill/test-plan.md` (coverage map, omitted tests, red run, implementer notes) and the spec §6.2 Proof column (14 cells; nothing else in the spec changed, verified by a prefix-identity check of every changed line).

No shared fixtures were added or changed, and no existing test was touched. No production file, skill file, stub or `REPO_MAP.md` edit was made.

## Pruning (candidates considered and dropped)

- Diff or merge-base tests (AC-10, INV-23/24): forbidden by §13 and R-1. They are PR-time evidence.
- The `.claude/ci-settings.json` guard: it already passes, so it proves nothing.
- Live pass-top commands, wheel contents, the full gate (AC-1 behavior, AC-11, AC-12): network or build. They are PR-time evidence.
- Seed slugs not yet members; pinned seed URLs, names or reasons; pinned `PRICING_AS_OF`, member count or line numbers: these break on provider branches or add no spec rule. C5 tests the host property instead.
- Brief length ≤ 40 lines (NFR-2): C6 pins the content, and length adds no new failure mode.
- Property, fuzz, concurrency and idempotency tests: there is no code invariant, and the runtime is a model against live GitHub.
- A set-only comparison in W6: replaced by an ordered 33-line comparison after the self-check showed a padded `|  A1 |` slips past a set (A2 shares A1's path).

## Red run (exact output)

Bootstrap: none. `py -3.11 -c "import vidbyte, inspect; print(inspect.getfile(vidbyte))"` → `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-provider-onboarding-skill\vidbyte\__init__.py`.

```
$ PYTHONPATH="C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill" py -3.11 -W error::DeprecationWarning -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider --tb=line
…onboard_skill_fixtures.py:308: AssertionError: .claude/skills/onboard-model-provider/SKILL.md does not exist; spec 12.3 row 2 (SKILL.md) creates it                      x29
…onboard_skill_fixtures.py:308: AssertionError: .claude/skills/onboard-model-provider/references/provider-run.md does not exist; spec 12.3 row 1 (references/provider-run.md) creates it   x15
…test_onboard_skill_contract.py:250: AssertionError: the entry no longer says interactive sessions do not load the folder
…test_onboard_skill_contract.py:81: AssertionError: assert [] == ['SKILL.md', ...vider-run.md']
46 failed in 0.79s
```

Per file: acceptance `5 failed in 0.11s` · contract `17 failed in 0.13s` · wiring_checklist `6 failed in 0.10s` · commands `11 failed in 0.81s` · security `7 failed in 0.80s`. Re-run on the committed tip `8e9b8b7f`: `46 failed in 1.34s`.

The area still passes and the whole suite collects:
```
$ PYTHONPATH=<worktree> py -3.11 -m pytest tests/features/sdk_provider_keys tests/features/sdk_model_catalog tests/test_agent_pricing.py tests/features/sdk_managed_text -q -p no:cacheprovider
................                                                         [100%]
448 passed in 2.54s
$ PYTHONPATH=<worktree> py -3.11 -m pytest --collect-only -q -p no:cacheprovider
5832 tests collected in 3.48s
```

Lint (pack staged, so the tracked-file rules see it; baseline untouched):
```
$ py -3.11 lint/run.py
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all
SDK-LINT: PASS
```
`--rule A001/S062/S020/A009/S051/S054/S060/S061/S063/S064 --all` each reported 0 findings in the pack. `py -3.11 -m ruff check tests/features/onboard_model_provider_skill` → `All checks passed!`. The S061 and S063 "IMPROVED" lines predate this stage and were left alone.

## Independent verification of the tests (scratch, not committed)

Under the scratchpad `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/`:
- `synth/`: a minimal skill that conforms to the spec, built from the spec's own §8.5 brief, constants and pass-top block, the §9.2 grammar and the §12.3 table (`s2_build_synth.py` copies the table verbatim from the spec).
- `s2_harness.py`: a pytest plugin that points the fixtures at `S2_SYNTH`.
- `s2_mutate.py`: the mutation runner.

Results:
- Synthetic run: `46 passed in 0.84s`, so every test can be satisfied.
- Mutations: 101 targeted defects (100 scripted plus an extra file in the skill folder), every one killed by its named test (`PROBLEMS: none`).
- Benign variants: 12, all passing (`git -C` fetch, `2>&1`, `$PROCEDURE`, a backticked dash, an extra symbol, prose "never `export PYTHONPATH`", prose "never push to main", `git merge-base`, regex escapes, a pytest node ID, a `gh api -X POST` fragment in prose, prose about `git worktree remove --force`).
- `s2_sed_selfcheck.py`: the emulator on the real files gives the vintage `['2026-10-11']` and the 14 member values.

## Spec defects and interpretations (for S3 and the orchestrator)

1. **`git stash` contradiction.** AC-3, INV-21 and AC-8 forbid the literal `git stash` in both files, but §12.3 row 2 asks `## Rules` to say "never `git stash`". The tests follow AC-3, so the Rules line must read "Never stash …". Suggested spec fix: reword §12.3 row 2 to "never stash".
2. **`export PYTHONPATH` contradiction.** AC-8 says "Neither file contains `export PYTHONPATH`", but the §8.5 brief template, which SKILL.md must hold verbatim, contains "never export PYTHONPATH", and §12.3 row 2 asks for "never `export PYTHONPATH`". The tests are command-aware: no `export PYTHONPATH` in `sh`/`bash` fences and no `export PYTHONPATH=` anywhere; the prose prohibition is allowed.
3. **"Interpreter command" is undefined.** AC-8 forbids a bare `python` except on the probe and remedy lines, while the brief says "never a bare python" in prose. The tests define an interpreter command as `python`, `python3` or `py -3.x` followed by a flag or a `.py` path. The probe must be the only line holding `python3` or `py -3.11`.
4. **The pass-top block is called "illustrative" but is bound.** §8.5 labels the block "illustrative", yet NFR-1 (read git blobs) and AC-1 ("parsable values") make its form load-bearing. X3 binds the vintage and member reads to `git show origin/main:<path> | sed -n 's/…/…/p'`, and the §8.5 scripts pass as written.
5. **Padded rows (new finding).** The §8.5 checklist `sed` (`^| [A-D][0-9]* | ` with single spaces) silently skips any wiring row written with other spacing. For a padded A1 the extracted set is unchanged, because A2 shares the path, so a set check hides it. W6 compares the ordered 33-line output. Suggested spec fix: state the row format ("one space after each pipe") under the §8.5 cell grammar.
6. **AC-15 "never instructs a merge".** The tests also forbid `git merge` commands, `/merge` endpoints and `state=closed`; `git merge-base` is allowed.
7. **Bare push spans.** S3 checks every `git … push` command, including inline code spans. A prose fragment such as "never `git push` to main" would fail, so prohibitions must be phrased without spelling a push command.

## Fixtures and seams

No mocks: the tests read files and call two pure functions (`Runner._normalize_provider_and_model`, the `ModelProvider` enum) and constants. `vidbyte` is imported at module level in the commands and security modules (`ModelProvider`, `PRICING_AS_OF`, `Runner`, `ProviderModelRegistry`, `ModelPricingRegistry`, `ModalityDetector`, `ToolsFormatter`); the pack collects in the normal gate.
