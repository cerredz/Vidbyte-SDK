# S5 repair, iteration 2 of 8: decision-model-providers

Branch `feat/decision-model-providers`, started at `68cc97d7`, PR https://github.com/cerredz/Vidbyte-SDK/pull/697. Inputs read: `verify-log.md` (iteration 1), `review.md`, the orchestrator's failure evidence, AGENTS.md, spec r11 §12.3 row 5, field guide `blocking-lint-invariants.md` (C002), house style.

## Gate matrix (all at `d1737132`, the merged tree, everything committed)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| 1 feature pack | `python -m pytest tests/features/decision_model_providers -q` | PASS (91) | `........................................................................ [ 79%]` / `...................                                                      [100%]` / `91 passed in 1.12s` |
| 2 area suite | `python -m pytest tests/test_jev_agent.py tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_jev_usage_ledger.py tests/test_jev_preflight.py tests/test_jev_done.py tests/test_model_registry.py tests/test_agent_pricing.py tests/test_embedding_runner.py tests/test_agent_settings_validation.py -q` | PASS (406) | `........................................................................ [ 88%]` / `..............................................                           [100%]` / `406 passed in 2.46s` |
| 3 SDK lint | `python lint/run.py` | PASS, exit 0, 0 REGRESSED | `S063 RATCHETED: 4 known finding(s). ...` / `S064 RATCHETED: 4 known finding(s). ...` / `SDK-LINT: PASS` |
| 4 full local gate | `python scripts/run_ci.py` | PASS, exit 0 | `====== 3071 passed, 1 skipped in 16.15s ======` / `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| 5 test-contract diffs | `git diff 3943089c HEAD -- tests/features/decision_model_providers/ \| wc -c` and `git diff $(git merge-base origin/main HEAD) HEAD -- tests/ ':(exclude)tests/features/decision_model_providers' \| wc -c` | PASS | `0` and `0` (merge base now `4e7f73fb` = origin/main); `git diff origin/main HEAD -- lint/baseline.json \| wc -c` → `0` |
| 6 remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/697` | none configured (workflows disabled) | `no checks reported on the 'feat/decision-model-providers' branch` |

Lint rows that matter: `C002 9 9 RATCHETED`, `C009 1 1 RATCHETED`, `C010 0 0 CLEAN`, `S009 345 350 IMPROVED`, `S051 258 259 IMPROVED`, `S015 13 13 RATCHETED`, `A001 643 643 RATCHETED`, `A009 0 0 CLEAN`. No baseline, config or suppression was touched.

## Per finding

### R-18 (Major) — fixed @b5be5ca4
- Reproduced at `68cc97d7`: `python -m pytest "tests/features/decision_model_providers/test_decision_failures.py::DecisionHttpCallTests::test_decision_http_call_accepts_int_and_float_subclass_timeouts" -q` → `ConfigurationError: Invalid Jev decision call timeout_seconds: expected a finite number of seconds greater than 0; received Seconds 30.0.` / `1 failed in 0.89s`.
- Root cause: rule 3 of `DecisionHttpCall.__post_init__` checked the exact type (`type(x) not in (int, float)`), which refuses every `int`/`float` subclass. Spec r11 row 5 rule 3 refuses only a `bool`, a non-`int`/`float`, a non-finite value, or `<= 0`.
- Change (`vidbyte/lib/dataclasses/jev.py`, line 525 before the merge, 527 after): `type(self.timeout_seconds) is bool or not isinstance(self.timeout_seconds, (int, float)) or not math.isfinite(...) or ... <= JEV_TIMEOUT_FLOOR_SECONDS`. The comment above now reads: "A bool is an int subclass, so True is refused by its exact type; int and float subclasses pass." and "The exact-type spelling also keeps this off C002's shared `timeout_seconds` bool-guard group." The message and the other checks are unchanged.
- Evidence after the fix: `DecisionHttpCallTests` → `2 passed`; pack → `91 passed`; `python lint/run.py --rule C002` → `C002 9 9 RATCHETED` / `SDK-LINT: PASS`. Probe over `DecisionHttpCall(timeout_seconds=...)`: `True`, `0`, `inf`, `nan`, `'30'` each refused with `Invalid Jev decision call timeout_seconds: expected a finite number of seconds greater than 0; received <type> <repr>.`; `Seconds(30.0)`, `WholeSeconds(30)`, `30`, `0.5` construct.
- "Gets right" items re-checked: the `retry_count` path on `JevCount.require` is untouched; the TypeSafe regression tests and the area suite (406) pass; C002 is unchanged.

### R-19 (Minor, spec-only) — fixed @44dc3faf (spec)
No code change. `review.md` status updated, as briefed.

### [gate:integration] — merged @d1737132
- `git fetch origin`: origin/main had moved to `4e7f73fb` (33 commits ahead of the old merge base `7be96284`). `git merge-tree --write-tree HEAD origin/main` exited 0.
- `git merge --no-ff origin/main` made merge commit `d1737132`, with no conflicts and no rebase. Main changes no file under `lint/`, no `pyproject.toml`, and no pricebook file. It touches `vidbyte/lib/constants/jev.py` and adds an import to `vidbyte/lib/dataclasses/jev.py`, which shifted the R-18 line to 527.
- No gate broke after the merge, so there is no `[gate:*]` fix commit. C009 and C010 did not fire, so the C010 lock was not refreshed and no rate was touched.
- Lint movement since iteration 1, all from main's code: S009 349 → 345, S051 257 → 258 (baseline 259). To check the S051 +1, I ran `ruff --select I001,UP006,UP007,UP035,UP045` over every `vidbyte/` file the branch changes. It finds 3 I001s (`vidbyte/lib/enums/model_provider.py`, `vidbyte/lib/registries/models.py`, `vidbyte/providers/__init__.py`), and origin/main's copies have the same 3 (`git show origin/main:<f> | python -m ruff check --config lint/ruff.toml --select ... --stdin-filename <f> -`). This branch adds no S051 finding. One unit of headroom remains.

## Test changes proposed
None. `tests/` is byte-identical to `3943089c` inside the pack and to origin/main outside it.

## Findings I believe are wrong
None.

## Commits this iteration
- b5be5ca4 fix(lib): accept int and float subclass timeouts in DecisionHttpCall [R-18]
- d1737132 Merge origin/main into feat/decision-model-providers [gate:integration]
- docs(spec): verify-log iteration 2 for decision-model-providers (this report, `verify-log.md`, `review.md`)

## Still open
No confirmed finding. The follow-up Minors stay open by design and are not this iteration's to fix: R-5, R-8, R-9, R-10, R-11, R-12, R-13, R-14, R-15, R-17.

## If a next iteration is needed
- If main moves again before merge, re-run `git merge --no-ff origin/main` and the four gates. S051 is at 258/259, so any import that main or this branch adds out of order would regress it. Fix it with `python -m ruff check --config lint/ruff.toml --select I001 --fix <file>`, run only on files this branch changes.
- R-18 has a single seam: the bool clause must stay `type(...) is bool`. `isinstance(self.timeout_seconds, bool)` takes C002 to 10/9.
