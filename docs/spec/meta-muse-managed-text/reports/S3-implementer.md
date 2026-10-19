# S3 implementer report: meta-muse-managed-text

**Status:** DONE. **Branch:** `feat/meta-muse-managed-text` (pushed, tracking `origin/feat/meta-muse-managed-text`). **Draft PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1180 (placeholder body; S6 writes the real one). **Base:** `845a4d9b`. **S2_HEAD:** `ea63e319`.

## Commits (S3 only)

```
4b384b60 docs(spec): record implementation proof for meta-muse-managed-text
1cdf9717 docs(spec): record draft PR for meta-muse-managed-text
98b91e11 docs(readme): name Meta in the managed-mode providers, cap and prefixes bullets [W-2; FR-7, AC-13]
b2306206 feat(gateway): serve meta in the managed text provider set [W-1, W-2; FR-1, FR-2, FR-3, FR-6, FR-7, AC-1..AC-12, AC-14]
```

This report is committed after them, in its own commit. The full `git log origin/main..HEAD` also lists the S0 to S2 docs and test commits (`75761b81` through `c408067f`), which are not S3's.

## What was built, in data-flow order

1. `vidbyte/lib/constants/jev.py`: `VIDBYTE_MANAGED_TEXT_PROVIDERS` gains `ModelProvider.META` after `ModelProvider.KIMI`. Its comment now reads (67, 67, 69, 42 columns):
   ```
   # The seven providers the generative gateway dispatches: the six of
   # cerredz/Vidbyte backend spec r3 section 9.2.8 at commit a14b37e7e
   # (spec.md A-1), plus meta from cerredz/Vidbyte#710 meta-muse-gateway
   # spec r4 section 9.2 at commit c395349bd.
   ```
2. Everything downstream is unchanged code that reads the set (spec D-1):
   - `TextModelConfig._require_gateway_shape` now admits `meta`, and M-12 lists it.
   - `ProviderKeyMatcher` M-18 offers "Vidbyte's own meta account".
   - `TextModelRunner.__init__` pins the 32,768 cap and the 630 s floor.
   - `VidbyteGatewayTransport` builds the envelope and the relay header.
   - `MetaProvider` writes `max_tokens`.
3. `README.md`, in `### Vidbyte-managed text calls`, changes three bullets:
   - **Providers:** "OpenAI, Anthropic, Gemini, xAI, DeepSeek, Kimi, and Meta."
   - **Output cap:** "For xAI, DeepSeek, Kimi, and Meta, set the cap with `max_output_tokens` …"
   - **Prefixes:** "… `xai-` (xAI), `LLM|` (Meta), and `AIza` or `AQ.` (Gemini)."

   Only the edited lines are re-wrapped, greedily to the section's existing 78-column width (new lines measure 72, 45, 76, 77, 65, 76, and 76 columns).

## §12.3 rows

- [x] **Row 1, `vidbyte/lib/constants/jev.py`:**
  - (a) `ModelProvider.META,` is added after `ModelProvider.KIMI,`. The annotation is still `frozenset[ModelProvider]`, with no string member.
  - (b) The comment is rewritten as the spec's example, word for word.
  - (c) `__all__`, the header, and every other constant are untouched: the diff is 5+/2- on lines 72-83 only.
- [x] **Row 2, `README.md`:** bullets (a), (b), and (c) are edited. Nothing else in the README changes (`git diff --stat`: 7+/7-).
- [x] **Row 3:** S2 owns it. `git diff --stat ea63e319..HEAD -- tests/` is empty.

## §12.4 checklist

- [x] Only `jev.py` changes in `vidbyte/`. `git diff --stat 845a4d9b..HEAD -- vidbyte` gives `1 file changed, 5 insertions(+), 2 deletions(-)`. (The spec's command uses `origin/main`, but origin/main moved to `6f5a7310` with #1055, so the base commit is the right comparison.)
- [x] `ModelProvider.META` is an enum member. No `"meta"` string appears in the `vidbyte/` diff.
- [x] The comment block is at most 72 columns. `sed -n 60,100p jev.py | awk 'length > 72' | grep '^\s*#'` prints nothing.
- [x] The comment cites #710 spec r4 §9.2 at `c395349bd` and keeps the `a14b37e7e` citation for the original six.
- [x] `__all__`, the header, and the other constants are byte-identical to the base (see the diff hunk).
- [x] The README changes only the three named bullets. Both existing README tests and the new AC-13 test pass (area `183 passed`).
- [x] No Meta key shape appears as a literal. `git diff ea63e319..HEAD | grep -E 'LLM\|[0-9]'` and the same grep over the commit messages print nothing. The README uses `LLM|` alone.
- [x] No other production file changes: no change to `MetaProvider`, `_attach_sampling`, the transport, or the runner.
- [x] `pricing.py`, `lint/pricebook_vintage_lock.json`, and `lint/baseline.json` are unchanged (their `git diff --stat` is empty).
- [x] Lint ends `SDK-LINT: PASS`. No baseline was raised, and no IMPROVED verdict was ratcheted (see below).
- [x] The import check printed the worktree path before the first test run.
- [x] The full gate ran in the §11 order. The only red is the pre-existing harness_threads test, and `--stage package` passes.
- [x] The implementer modified no test file and no test-pack doc.
- [x] The only files changed under `docs/` are in `docs/spec/meta-muse-managed-text/`.

## §12.5 non-code actions

- The draft PR is opened with the placeholder body, which already carries the canonical merge-prerequisites sentence.
- The template-shaped PR body belongs to S6, and so do these: the EC-11 and EC-16 disclosure, the served Muse ids, the cap evidence, the pre-existing red, and the pre-merge live check listed as an open prerequisite.
- The pre-merge live check cannot run in the pipeline: there is no real key, and #710 is not deployed.

## §6.2 proof

No AC row has a blank Proof cell. AC-1 to AC-14 cite pytest tests, and AC-15 cites "PR body (S6)". So no commit SHA was filled in. §17 has the row `r3 | 2026-10-17 | S3 implement | …`.

## Deviations

None in what was built.

The facts below differ from the spec's text. None of them changed the change itself:
- **S001 also reports IMPROVED (59 → 56).** The spec §11 list of pre-existing IMPROVED rules omits it. It shows the same `IMPROVED 59 -> 56` on a detached `845a4d9b` worktree, so it predates this PR. It scans `vidbyte/` with Ruff codes F/E4/E7/E9, and one enum member and a comment cannot change that count. It was not ratcheted.
- **The full-gate pytest count is `6260 passed`.** The spec's §11 baseline says `6245`; the extra 15 are S2's new tests.
- **origin/main moved one commit** (`6f5a7310`, #1055 CodexHost). It touches none of the §12.3 or read-verified files. Its only overlap is a harnesses paragraph in `REPO_MAP.md`, which has no gateway entry. No rebase was done; the PR merges cleanly at the file level.

## Files outside §12.3 touched

None in the product. The only other files are this run's own spec artifacts: the `spec.md` frontmatter and the §17 row, and this report.

## Budget (§8.4)

| Item | Allowed | Used |
|---|---|---|
| New files | 0 | 0 (this report is a pipeline artifact) |
| New classes or modules | 0 | 0 |
| New dependencies | 0 | 0 |
| New config keys | 0 | 0 |
| New collections | 0 | 0 |
| New endpoints | 0 | 0 |
| Production lines | about 5 | 5+/2- in one file |

## Gates (final lines, quoted)

**Import check** (both with and without PYTHONPATH):
```
C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-meta-muse-managed-text\vidbyte\__init__.py
```

**Red baseline at `c408067f`** (area, `DEEPSEEK_API_KEY` unset): `24 failed, 159 passed in 2.20s`

**After row 1 only:**
```
FAILED tests/features/sdk_managed_text/test_managed_text_acceptance.py::ManagedTextAcceptanceTests::test_readme_managed_section_names_meta_as_served_in_the_chat_cap_guidance_and_by_its_llm_prefix
1 failed, 182 passed in 2.16s
```

**After rows 1 and 2** (area: `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys`):
```
183 passed in 2.07s
```

**Lint** (`py -3.11 lint/run.py`, exit 0):
```
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
IMPROVED, not ratcheted: A002 703→562, C011 2→1, S001 59→56, S009 350→346, S010 5→0, S025 263→261, S061 6→5, S063 4→3.

**Full gate 1, `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`:**
```
SDK-LINT: PASS
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
============ 1 failed, 6260 passed, 16 skipped in 96.56s (0:01:36) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-meta-muse-managed-text).
```

**Full gate 2, `py -3.11 scripts/run_ci.py --stage package`** (PYTHONPATH unset, exit 0):
```
No broken requirements found.
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
```

**Full gate 3, the proof run `py -3.11 scripts/run_ci.py`** (PYTHONPATH unset):
```
SDK-LINT: PASS
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
============ 1 failed, 6260 passed, 16 skipped in 90.81s (0:01:30) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-meta-muse-managed-text).
```
The proof run stops before its package stage, so the package stage was run separately (gate 2 above).

**Known red, proven on a detached worktree** (removed afterwards; `git worktree list` no longer shows it):
- `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`:
  - At `845a4d9b`: `…test_harness_threads_surface.py:193: AssertionError: assert 148 == 120` / `1 failed, 1 passed in 0.84s`. The pass is the MCP test.
  - At origin/main `6f5a7310`: `…:193: AssertionError: assert 167 == 120` / `1 failed in 0.80s`.
- `test_cancelled_waiter_does_not_break_transport`: passed at `845a4d9b`, and passed in both branch full runs. The flake did not fire.
- Semgrep (`semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`) fails the same way on the base and on the branch: `ModuleNotFoundError: No module named 'mcp.server.fastmcp'. This is mcp 2.x …`. It is not a `run_ci.py` step. It runs only in the remote Static policy workflow, which does not attach to PRs. Nothing was installed to fix it.

## Tricky parts (where to look first)

1. **The harness_threads assertion value depends on the merge base.** The test reads `FailureCode` at `git merge-base origin/main HEAD`. It shows `148 == 120` on this branch (merge base `845a4d9b`) and `167 == 120` on current main. If the branch is rebased or main is merged in, the quoted number changes. S6 should quote the value at the head it ships. CI's shallow checkout returns early, so the test passes there.
2. **The README Prefixes re-wrap** moved "Vidbyte key in the list is the Vidbyte key." to begin a new line. The previous line now ends "… (Gemini). A". This is greedy fill to 78 columns, the same style as the Providers bullet's old "… Kimi. A gateway". The AC-13 test collapses whitespace, so any wrap passes. The choice only affects how the text reads.
3. **The `jev.py` header was left byte-identical**, as spec §12.4 requires. I checked it against the file-header practice ("update the header the change contradicts"): the header names "provider set" with no count, and its COMMON MODIFICATION PATTERNS already describes this change. So nothing in it became false. The comment above the set was the only production text that stated "six"; a grep of `vidbyte/`, `skills/`, and the maps found no other served-provider list.
4. **The behavior change is larger than the diff** (EC-11, EC-16). Muse fallbacks, forks, handoffs, grader members, and critic, judge, and brief-writer stages that were silently skipped now run and bill. Only the grader and the fork are pinned by tests (S2's choice; test-plan "not written" row). S6 must disclose this in Compatibility.
5. **The full runs in `run_ci.py` ran with `DEEPSEEK_API_KEY` set**, because `run_ci.py` does not unset it. The area tests passed there too (6260 passed), so that key does not change the result in a full run.
6. **A-2, the Muse 1.1 output limit of at least 32,768, is still unverified.** If it is false, every `Agent` Muse call in a gateway mode gets Meta's 400 (EC-3). Only the §12.5 live check can settle it. It is an open merge prerequisite.
