# Verification log: Add more decision model providers beyond TypeSafe Jev

Gate set (from context/code-map.md §1, run from the worktree root in this order):

| # | Gate | Command | Where |
|---|---|---|---|
| 1 | Feature pack | `python -m pytest tests/features/decision_model_providers -q` | local |
| 2 | Area suite | `python -m pytest tests/test_jev_agent.py tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_jev_usage_ledger.py tests/test_jev_preflight.py tests/test_jev_done.py tests/test_model_registry.py tests/test_agent_pricing.py tests/test_embedding_runner.py tests/test_agent_settings_validation.py -q` | local |
| 3 | SDK lint | `python lint/run.py` (scans tracked files only: stage or commit new code first; only REGRESSED matters, IMPROVED counts are noisy) | local |
| 4 | Full local gate (gate of record, AGENTS.md) | `python scripts/run_ci.py` (compileall, lint, full pytest, package stage) | local |
| 5 | Test-contract diffs (must print nothing) | `git diff 3943089c HEAD -- tests/features/decision_model_providers/` (latest test grant, R-18; iteration 1 used `90ed9a29`) and `git diff $(git merge-base origin/main HEAD) HEAD -- tests/ ':(exclude)tests/features/decision_model_providers'` | local |
| 6 | Remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/697` | remote: none configured; every `.github/workflows/` file is `workflow_dispatch`-only and disabled by the owner, so do not trigger or wait |

## Iteration 1 — 2026-10-10 — agent report: reports/S5-repair-1.md
**Defects in:** R-1 (Blocker, OpenRouter one-key noul criteria), R-2 (Blocker, `DecisionHttpCall` outside `vidbyte/lib/dataclasses/`), R-3 (Major, closed by the test grant at 90ed9a29), R-4 (Major, OpenAI helper chains deeper than one level), trivial Minors R-6 and R-7, R-16 (already fixed by the test author). Failing gate at 90ed9a29: feature pack `2 failed, 88 passed` (R-1 wire test, R-2 `DecisionHttpCallTests`).

**Hypotheses and attempts:**
- R-1, H1 (worked first try): in `SystemOneRequest.criteria`, branch on `question_type is NOUL and host.noul_criteria_required` *before* the empty-options check and build `{true: described.get(true), false: described.get(false)}` from a name-to-description map. Every other host keeps its old branch, so INV-23 holds (`tests/test_jev_agent.py` green). Side effect worth knowing: OpenRouter's noul `criteria` keys are now always in `true, false` order whatever the option order; no other host changes.
- R-2, H1 (worked): followed spec r11 rows 5, 12-15 literally. Two lint traps met and resolved without touching any baseline:
  - S051/I001 REGRESSED (259 → 260) after adding `DecisionTransport` to the one-line `from vidbyte.providers.decisions import ...` in `systemone.py`, `openai_decisions.py`, `typesafe.py`: the line got long enough that ruff wraps it. Fix: `python -m ruff check --config lint/ruff.toml --select I001 --fix <those three files>`, then re-lint.
  - C002 (duplicate inline bool guard, baseline 9) is keyed on the *name* passed to `isinstance(<name>, bool)` across functions. `timeout_seconds` already has 3 sites (`vidbyte/workflows/contracts.py:149,176`, `vidbyte/workflows/validation.py:172`) and `retry_count` has `vidbyte/lib/dataclasses/model_configs.py:389`, so a new `isinstance(self.timeout_seconds, bool)` or `isinstance(self.retry_count, bool)` would regress C002 (predicted from `lint/rules/c002_duplicate_inline_bool_guard_validation.py`, not run). Chosen: `retry_count` goes through the existing shared `JevCount.require(..., minimum=JEV_NO_RETRIES)`, whose message ("an integer of at least 0") is rule 5's text verbatim; `timeout_seconds` uses an exact-type check `type(x) not in (int, float)`, which rejects `True` because `type(True) is bool`. Lint then PASS with C002 9/9 and C006 104/104.
  - Placement facts: `jev.py` imports nothing from `vidbyte.lib.http`; `JEV_NO_RETRIES` and `JEV_TIMEOUT_FLOOR_SECONDS` joined its constants import. `jev.py` is 4,752 lines (4,640 at the merge base), already far past AGENTS.md's "well below 1,000"; spec row 5 places the record there, so no split.
- R-3: no production change. `test_system_one_provider_refuses_a_managed_per_call_config_before_any_call` is green; R-7 kept the refusal sentence byte-identical.
- R-4, H1 (worked): lift calls into the main functions; no new class, because §8.4's class budget is at 13/13 once `DecisionTransport` exists. `build` resolves instruction text and passes `instructions=` to `question`; `encode` resolves description text and passes it to `option(name, description, *, key)`; `normalize` calls `_require_type`, `_predicate`, `_entries`, `_level`, `_distribution`, `_choice`, `_score` directly (`_answer` became `_require_type`). Only `self.error(...)` is still called from helpers, which review R-4 explicitly allows (the §8.5 error factory calls nothing further). Equivalence: an old-vs-new differential probe (scratchpad `r4_diff_probe.py`, loads the HEAD~ module from a file) over 4 request and 25 answer cases (refusal, wrong type, duplicate option, missing/extra options, 1.5 and bool probabilities, label/index fallback, bad confidence and score, duplicate and missing names) printed `MISMATCHES 0`, messages and `details` included.
- R-7: a private `_MANAGED_REFUSAL: ClassVar[str]` on `SystemOneProvider` rather than a constant in `vidbyte/lib/constants/jev.py`, because a public constant would add to the public contract beyond §8.5/§9 and the sentence is used only by this class. Added the comment on the config-less `provider="systemone"` error.
- R-6: one "Keys" bullet under the providers README "Decision Providers" naming all 16 decision-host variables (README 52,543 characters; A009 ceiling 55,000).

**Changes:**
- f6f3df8f fix(providers): send OpenRouter both noul criteria keys for any option subset [R-1]
- c5b4a4ab fix(providers): define DecisionHttpCall in lib/dataclasses/jev.py with validation; send via DecisionTransport [R-2]
- 2da50682 fix(providers): keep OpenAI Decisions helper chains one level deep [R-4]
- e7c48376 docs(providers): describe OpenRouter's both-keys noul criteria in README and SystemOneHost [R-1]
- f42b1b1b fix(providers): list every decision host's key variable in the providers README [R-6]
- 93e2bd1a fix(providers): one managed-refusal sentence and a note on the adapter-named provider field [R-7]

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (feature pack) | `python -m pytest tests/features/decision_model_providers -q` | PASS (90) | `..................  [100%]` / `90 passed in 1.07s` |
| area suite | `python -m pytest tests/test_jev_agent.py tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_jev_usage_ledger.py tests/test_jev_preflight.py tests/test_jev_done.py tests/test_model_registry.py tests/test_agent_pricing.py tests/test_embedding_runner.py tests/test_agent_settings_validation.py -q` | PASS (406) | `406 passed in 2.53s` |
| lint | `python lint/run.py` (inside run_ci, all changes committed) | PASS | `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` (C002 9/9, S009 349/350, S051 257/259, A001 643/643; no REGRESSED) |
| full local gate | `python scripts/run_ci.py` at 93e2bd1a | PASS (exit 0) | `2921 passed, 1 skipped in 15.42s` / `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| test-contract diffs | `git diff 90ed9a29 HEAD -- tests/features/decision_model_providers/` and `git diff $(git merge-base origin/main HEAD) HEAD -- tests/ ':(exclude)tests/features/decision_model_providers'` | PASS (both empty) | `0` bytes each (piped to `wc -c`) |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/697` | none configured (workflows disabled) | `no checks reported on the 'feat/decision-model-providers' branch` |

Pushed: `9784a3f6..93e2bd1a  feat/decision-model-providers -> feat/decision-model-providers`. `gh pr view 697 --json mergeable,mergeStateStatus` → `MERGEABLE`, `BEHIND` (origin/main moved; S6 merges, as briefed).

**Still open:** No confirmed finding. Follow-up Minors stay open by design: R-5, R-8, R-9, R-10, R-11, R-12, R-13, R-14, R-15, R-17 (see review.md).

## Iteration 2 — 2026-10-10 — agent report: reports/S5-repair-2.md
**Defects in:** R-18 (Major, `DecisionHttpCall` refused `int`/`float` subclass timeouts that spec r11 row 5 rule 3 admits; INV-23, AC-23). R-19 (Minor, spec-only, already fixed by `44dc3faf`). `[gate:integration]`: origin/main was 33 commits ahead (`7be96284` → `4e7f73fb`). Failing gate at 3943089c: feature pack `1 failed, 90 passed` (`DecisionHttpCallTests::test_decision_http_call_accepts_int_and_float_subclass_timeouts`, both subtests: `... received Seconds 30.0.` / `... received WholeSeconds 30.`).

**Hypotheses and attempts:**
- R-18, H1 (worked first try): at `vidbyte/lib/dataclasses/jev.py` rule 3 (line 525 before the merge, 527 after), `type(self.timeout_seconds) is bool or not isinstance(self.timeout_seconds, (int, float))` in place of `type(...) not in (int, float)`; the finite and `> JEV_TIMEOUT_FLOOR_SECONDS` checks and the message are unchanged. The comment now says why bool is checked by exact type (it is an int subclass) and that this spelling keeps the line out of C002's `timeout_seconds` group. Reproducer red → green; `C002 9 9 RATCHETED`. Probe: `True`, `0`, `inf`, `nan`, `'30'` keep the AC-23 message; `Seconds(30.0)`, `WholeSeconds(30)`, `30`, `0.5` construct.
- Considered and not tried, with reasons: `isinstance(self.timeout_seconds, bool)` (exhausted in iteration 1: C002 10/9); coercing with `float(...)` (changes the stored value and type, which row 5 does not ask for); a shared `JevSeconds.require`-style helper (a new class breaks the §8.4 budget of 13/13; a new function with one caller is an overcomplication smell).
- Integration: `git merge --no-ff origin/main` → merge commit `d1737132`, no conflicts (main does not touch `lint/`, `pyproject.toml` or the pricebook). No gate broke after the merge, so no `[gate:*]` fix commit was needed and C010 needed no `--refresh-lock`. Lint deltas versus iteration 1 all come from main and none is REGRESSED: S009 349 → 345 (improved), S051 257 → 258 of 259. The S051 +1 is not this branch's: `ruff --select I001,UP006,UP007,UP035,UP045` over every `vidbyte/` file the branch changes finds 3 I001s (`lib/enums/model_provider.py`, `lib/registries/models.py`, `providers/__init__.py`), and the same 3 exist in origin/main's copies (`git show origin/main:<f> | python -m ruff check --config lint/ruff.toml --stdin-filename <f> -`). Watch it: S051 has one unit of headroom left.

**Changes:**
- b5be5ca4 fix(lib): accept int and float subclass timeouts in DecisionHttpCall [R-18]
- d1737132 Merge origin/main into feat/decision-model-providers [gate:integration]

**Gate matrix out** (all at d1737132, the merged tree, everything committed):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (feature pack) | `python -m pytest tests/features/decision_model_providers -q` | PASS (91) | `...................  [100%]` / `91 passed in 1.12s` |
| area suite | `python -m pytest tests/test_jev_agent.py tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_jev_usage_ledger.py tests/test_jev_preflight.py tests/test_jev_done.py tests/test_model_registry.py tests/test_agent_pricing.py tests/test_embedding_runner.py tests/test_agent_settings_validation.py -q` | PASS (406) | `406 passed in 2.46s` |
| lint | `python lint/run.py` | PASS (exit 0, 0 REGRESSED) | `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` (C002 9/9, C009 1/1, C010 0, S009 345/350, S051 258/259, S015 13/13, A001 643/643, A009 0) |
| full local gate | `python scripts/run_ci.py` | PASS (exit 0) | `3071 passed, 1 skipped in 16.15s` / `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| test-contract diffs | `git diff 3943089c HEAD -- tests/features/decision_model_providers/` and `git diff $(git merge-base origin/main HEAD) HEAD -- tests/ ':(exclude)tests/features/decision_model_providers'` (merge base is now `4e7f73fb`) | PASS (both empty) | `0` bytes each (piped to `wc -c`); `git diff origin/main HEAD -- lint/baseline.json` also `0` |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/697` | none configured (workflows disabled) | `no checks reported on the 'feat/decision-model-providers' branch` |

**Still open:** No confirmed finding. R-18 fixed @b5be5ca4, R-19 fixed @44dc3faf (spec). Follow-up Minors stay open by design: R-5, R-8, R-9, R-10, R-11, R-12, R-13, R-14, R-15, R-17 (see review.md).
