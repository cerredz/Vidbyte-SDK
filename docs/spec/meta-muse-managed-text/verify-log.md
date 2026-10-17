# Verification log: Let the SDK's gateway text modes (AUTO and VIDBYTE_MANAGED) use provider meta

Gate set (from `context/code-map.md` §1 and spec §11; `py -3.11` stands in for `python` on this machine):
- **area tests (local):** `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider`. Target: `192 passed`.
- **lint (local):** `py -3.11 lint/run.py`. It must end `SDK-LINT: PASS` with 0 REGRESSED and 0 ERRORED.
- **full source stage (local):** `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`.
- **package stage (local):** `py -3.11 scripts/run_ci.py --stage package`, with no PYTHONPATH.
- **proof run (local):** `py -3.11 scripts/run_ci.py`, with PYTHONPATH unset. It stops before its package stage when pytest fails, so the package stage runs separately.
- **known red, inherited:** `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`148 == 120` at merge base `845a4d9b`). The MCP stdio cancelled-waiter test is a known Windows timing flake.
- **semgrep (remote only):** `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`. It cannot run locally (mcp 2.x import error) and is not a `run_ci.py` step.
- **remote checks (remote only):** `gh pr checks 1180`. SDK CI triggers are paused, so the PR shows 0 checks.

## Iteration 1 — 2026-10-17 — agent report: reports/S5-repair-1.md

**Defects in:**
- R-1 (Blocker), production half: the META row of `KEY_FORMATS` proved only `LLM|`, so Meta's documented `LLM_` key raised M-6 in `api_keys` and was misrouted by elimination in a mixed list.
- R-2, R-3, R-6, R-7: already fixed by the r4 test author; verify only.
- R-4, R-5, R-9, R-10, R-11: fixed in spec r4 `04729669`; record only.
- R-8: a follow-up; left open by design.
- Gate in: the area ran `15 failed, 177 passed` at `607c2e16`. All 15 were r4 tests, red by design.

**Hypotheses and attempts:**
1. *The only production change needed is the §8.5 row, its comment, the registries README row, and the root README bullet.* Confirmed. I applied the row exactly as §8.5 states it and wrote a 6-line comment of at most 72 columns. Contract file: `1 failed, 15 passed`, with only the registries README test left. Then I edited the README row. Contract file `16 passed`; area `192 passed in 2.32s`. No test needed a change.
2. *Meta's page still says what the spec quotes.* Confirmed. I fetched both pages again with curl at 13:17 UTC: `authentication.md` HTTP 200, 2,692 bytes, sha256 `065bf421…d008f4`; `error-handling.md` HTTP 200, 30,145 bytes, sha256 `5a827b56…02d6a`. `authentication.md:13` is the quoted sentence, word for word. `error-handling.md:509` and `:511` say what the spec says. `LLM|` appears 0 times on both pages, which supports the README clause "On 2026-10-17 that page no longer shows the `LLM\|` form". The example ID on the authentication page has 16 digits.
3. *The fix routes keys correctly outside the test suite, and the regex cannot backtrack badly.* Confirmed by a probe script (`<scratchpad>/s5r1_probe.py`, not committed):
   - Both shapes prove `meta`, and no provider takes either one unproven.
   - Five malformed `LLM_` keys (word ID, dot in the secret, no secret, bare `LLM_`, missing ID) are unproven and taken by no provider.
   - The near misses lowercase `llm_`, `LLM-` and `LLMx` stay open to 8 providers (INV-17).
   - The S4 misroute case (anthropic primary, kimi other, list `[K_ANTHROPIC, <Meta key>]`, with and without meta configured): kimi gets no Meta key in either shape.
   - A lone Meta key for a deepseek primary is refused, and the error text holds no key.
   - 1,000 `fullmatch` calls on 512-character adversarial inputs take 0.9 to 2.1 ms in total, so matching is linear. The ID class (digits) cannot match the separator, so the pattern has no ambiguous split.
4. *R-3's mutant is now killed on the real row, not only in S2b's in-memory green state.* Confirmed. `S4E_MUTANT=meta_key_to_keyless -p s4e_mutants` over the area gives `1 failed, 191 passed`. The failure is `MetaAgentTests::test_a_meta_key_in_either_shape_never_rides_on_a_kimi_fallback_that_holds_no_key_of_its_own`. In S4 the mutant survived with `183 passed`.
5. *The production commit P stands alone (orchestrator's hotfix-split rule).* Confirmed. In a detached worktree at origin/main `6f5a7310`, `git cherry-pick --no-commit 9309eed04f8bcec7bad29d73715933f49d0ba550` exited 0. It staged exactly `vidbyte/lib/registries/README.md` and `vidbyte/lib/registries/provider_keys.py` (8 insertions, 4 deletions) with no conflict. The worktree was then removed and pruned. origin/main has not touched either file, or the root README, since `845a4d9b`. No tests were run there; a later agent builds the hotfix branch.

Nothing failed, so there is no dead end to record.

**Changes:**
- `9309eed04f8bcec7bad29d73715933f49d0ba550` (P), `fix(provider-keys): prove and reserve Meta's documented LLM_ key shape [R-1]`. It changes `vidbyte/lib/registries/provider_keys.py` (the META row becomes prefixes `("LLM|", "LLM_")` with the §8.5 alternation and no flags, still last, plus the 6-line comment at 70/71/69/72/69/63 columns) and `vidbyte/lib/registries/README.md` (the table F meta row). Nothing else changes in those files: not the other five rows, their order, `FORMAT_BOUND_PROVIDERS`, `RESERVED_PREFIXES`, any method or message, or the header.
- `874890bd`, `fix(readme): name both Meta key prefixes in the Prefixes bullet [R-1]`. In the root `README.md`, the Prefixes bullet now reads "`LLM_` or `LLM|` (Meta)", and only its last two lines are re-wrapped (70 and 57 columns). **No test binds the `LLM_` half** (AC-13 asserts only "`LLM|` (Meta)"). I checked it by eye and by grep: `grep -nF '`LLM_` or `LLM|` (Meta)' README.md` finds `README.md:292`.
- Docs commit `docs(spec): verify-log iteration 1 for meta-muse-managed-text`: `review.md` statuses, this entry, and `reports/S5-repair-1.md`. The orchestrator's counter bump in `pipeline.md` was committed by the orchestrator as `cda14a71`, not by me.

**Checks (all in this worktree, this iteration):**
- R-2: `git diff -U0 origin/main...HEAD -- '*.py' | grep -E '^\+\s*#' | awk 'length($0) > 73'` prints nothing: 0 of 216 added `#` lines, R-1's six included.
- R-7: `py -3.11 -m ruff check --no-cache --isolated --preview --select E301,E302,E303,E305 <16 changed .py files>` gives `All checks passed!`.
- R-6: the six COMMON MODIFICATION PATTERNS lines name their tables, and `mt/FEATURE.md` no longer mentions `ORACLE_KEYS`.
- Test-tree baseline: `git diff --stat 263fa4e9..HEAD -- tests` is empty.
- Scope: `git diff --stat origin/main...HEAD -- vidbyte` lists exactly `jev.py`, `registries/README.md` and `provider_keys.py`. Outside `docs/` and `tests/`, only the root `README.md` is added to those. `lint/baseline.json`, `lint/pricebook_vintage_lock.json` and `pricing.py` are unchanged.
- Key literals: `grep -cE 'LLM\\*[_|][0-9]'` over the whole branch diff and over every branch commit message gives 0.
- Registries README size: 7,849 characters, under A009's 40,000-character limit.

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (area) | `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider` | PASS | `192 passed in 2.09s` |
| lint | `py -3.11 lint/run.py` | PASS (exit 0; 0 REGRESSED, 0 ERRORED) | `S063 IMPROVED 4 -> 3. …` / `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` |
| full source stage | `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source` | FAIL only on the inherited test | `SDK-LINT: PASS` · `context write-path integrity: ok` · `context primitive introductions: ok` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6269 passed, 16 skipped in 118.49s (0:01:58) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest …` |
| package stage | `py -3.11 scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS (exit 0) | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| proof run | `py -3.11 scripts/run_ci.py` (PYTHONPATH unset; the import check first printed `…\worktrees\vidbyte-sdk-meta-muse-managed-text\vidbyte\__init__.py`) | FAIL only on the inherited test; it stops before its package stage, which ran separately above | `SDK-LINT: PASS` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `E       AssertionError: assert 148 == 120` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6269 passed, 16 skipped in 123.56s (0:02:03) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest …` |
| known red at base | Detached worktree at `845a4d9b` (removed after): `PYTHONPATH=<it> py -3.11 -m pytest tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes -q -p no:cacheprovider` | FAIL at base too, so inherited | `>       assert len(main_members) == 120` · `E       AssertionError: assert 148 == 120` · `1 failed in 1.89s` |
| MCP stdio flake | inside the source and proof runs | PASS (did not fire) | `tests\test_mcp_stdio_transport.py ......................` |
| semgrep | remote only | not run locally (mcp 2.x; not a `run_ci.py` step) | — |
| remote checks | `gh pr checks 1180 --repo cerredz/Vidbyte-SDK` after pushing `874890bd` | 0 checks (CI triggers paused; an accepted external condition) | `no checks reported on the 'feat/meta-muse-managed-text' branch` |

**Still open:** R-8 (a follow-up by design). Merge prerequisites stay out of this loop: #710 deployed, the backend's `META_API_KEY`, and the §12.5 live check, which includes call (c), a real `LLM_` key through `api_keys`. That call is the only test of D-9's secret class.
