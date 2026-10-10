# S3 implementer report: decision-model-providers

- **Status:** DONE
- **Branch:** `feat/decision-model-providers`; HEAD `67070b22`, pushed.
- **Draft PR:** https://github.com/cerredz/Vidbyte-SDK/pull/697
- **Base:** `278448b0`. The S2 tests head is `c07abf49`, and `git diff c07abf49..HEAD --stat -- tests/` is empty.

## Commits (oldest first)

| SHA | Rows | Subject |
|---|---|---|
| `c58e8746` | 2 | feat(enums): add DecisionAuthScheme for decision-host auth headers |
| `372bf26e` | 3 | feat(enums): export DecisionAuthScheme from vidbyte.lib.enums |
| `aff0a647` | 4 | feat(constants): add decision-host wire paths and OpenAI Decisions type tags |
| `f90e113c` | 5 | feat(jev): add SystemOneHost and the OpenAI Decisions wire records |
| `8a140ba2` | 1, 6, 7 | feat(providers): register six decision providers in the catalog (all three rows in one commit; see deviation 8) |
| `7c181a80` | 8 | feat(pricing): price the new decision hosts and stamp PRICING_AS_OF 2026-10-10 |
| `371b6e9a` | 10 | feat(pricing): parse OpenRouter decision usage keys |
| `9f5c79a2` | 11 | docs(pricing): name every System One host JevUsage parses |
| `fc71d41c` | 9 | feat(config): accept every decision provider in DecisionModelConfig |
| `45b48993` | 12 | feat(providers): add shared decision HTTP call and failure mapper |
| `1a1c3792` | 13 | feat(providers): add the System One adapter for seven direct decision hosts |
| `a332f879` | 14 | refactor(providers): rebuild TypeSafeProvider on the shared System One pieces |
| `62d7dc33` | 15 | feat(providers): add the OpenAI Decisions adapter |
| `6681ffa2` | 16 | feat(providers): route every decision provider to its wire's adapter |
| `c4069454` | 17 | fix(runners): read the decision model through resolved_model() |
| `54a4f489` | 18 | docs(providers): document the decision hosts, wires, and recipes |
| `dce65304` | 19 | docs(repo-map): list the decision wire modules in the JEV table |
| `3b7e2ec6` | 20 | docs(skill): point the jev-agent skill at the decision wire modules |
| `ad4721bf` | 21 | docs(enums): say DecisionModelMode.TYPESAFE is direct mode for every provider |
| `d07c328b` | 13, 15 | fix(providers): build direct decision URLs from the vendor endpoint (C017; see deviation 1) |
| `600463c0` | — | docs(spec): record draft PR for decision-model-providers |
| `67070b22` | — | docs(spec): record implementation proof for decision-model-providers |

Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## What was built, in data-flow order

1. **Catalog** (rows 1, 6, 7)
   - Six new `ModelProvider` members: `PERPLEXITY`, `CLOUDFLARE`, `FOUNDRY`, `LIQUID`, `BASETEN`, `MERAGPT`.
   - Each member is bound to `JevUsage` and has a row in every S014 parity map. `CLOUDFLARE` and `FOUNDRY` default to an endpoint of `""` because their URL is tenant-scoped.
   - New `ProviderModelRegistry.DECISION_DEFAULT_MODELS` map (nine rows) and its reader `decision_default_model`.
   - Runner-catalog keys and prefixes added for every new model and provider.
2. **Records and literals** (rows 2–5)
   - `DecisionAuthScheme` (`Bearer` or `Api-Key`).
   - Seven path and type constants.
   - Three frozen, validated records: `SystemOneHost`, `OpenAIDecisionsWireQuestion`, `OpenAIDecisionsWireRequest`.
3. **Config** (row 9)
   - `DecisionModelConfig` accepts the nine providers.
   - `model` is `str | None`. When it is None, the per-provider default fills it, and `resolved_model()` is the typed reader.
   - Managed mode is still TypeSafe-only, now with its own message.
   - `validate()` resolves the key, then the endpoint, so a Cloudflare or Foundry config with no endpoint fails before any call.
4. **Shared plumbing** (row 12): `decisions.py` holds `DecisionHttpCall`, which is the former `_TypeSafeHttpCall`, and `DecisionFailures`, which is the direct-mode status table worded per host.
5. **System One wire** (row 13): `systemone.py` holds three classes.
   - `SystemOneRequest`: OpenRouter's row sends noul criteria `{"true": null, "false": null}`.
   - `SystemOneAnswers`: messages are labelled with the host name, and `model()` follows INV-27.
   - `SystemOneProvider`: eight `HOSTS` rows, a per-call provider guard (INV-28), and a managed refusal at construction and per call.
6. **TypeSafe** (row 14)
   - `typesafe.py` drops its four private wire classes.
   - It reuses the System One pieces through `_TYPESAFE_HOST`.
   - The managed gateway, `/models`, and run close are byte-identical.
7. **OpenAI Decisions wire** (row 15): `openai_decisions.py` holds three classes.
   - `OpenAIDecisionsRequest`: noul is sent as a predicate, choice with `choices`, score with `levels`. A described noul option is refused.
   - `OpenAIDecisionsAnswers`: matches entries by name, and treats a refusal, a duplicate, missing or extra names, or a malformed distribution as a `ProviderResponseError` that keeps the usage.
   - `OpenAIDecisionsProvider`.
8. **Routing and runner** (rows 16, 17)
   - `ModelProviders.decision` routes nine providers to three adapter classes.
   - `DecisionModelRunner` reads `resolved_model()`.
9. **Metering** (rows 8, 10, 11)
   - Pricebook rows dated 2026-10-10.
   - `OpenRouterUsage` parses the decision usage keys.
   - Header text names every System One host that `JevUsage` parses.
10. **Docs** (rows 18–21): providers README, the JEV table in REPO_MAP, the jev-agent skill, and the `DecisionModelMode` docstring.

## Rows (§12.3)

- [x] 1 `vidbyte/lib/enums/model_provider.py`
- [x] 2 `vidbyte/lib/enums/jev.py`
- [x] 3 `vidbyte/lib/enums/__init__.py`
- [x] 4 `vidbyte/lib/constants/jev.py`
- [x] 5 `vidbyte/lib/dataclasses/jev.py`
- [x] 6 `vidbyte/lib/registries/models.py`
- [x] 7 `vidbyte/lib/constants/runners.py`
- [x] 8 `vidbyte/lib/registries/pricing.py`
- [x] 9 `vidbyte/lib/dataclasses/model_configs.py`
- [x] 10 `vidbyte/agents/pricing/openrouter.py`
- [x] 11 `vidbyte/agents/pricing/typesafe.py`
- [x] 12 `vidbyte/providers/decisions.py` (new)
- [x] 13 `vidbyte/providers/systemone.py` (new)
- [x] 14 `vidbyte/providers/typesafe.py`
- [x] 15 `vidbyte/providers/openai_decisions.py` (new)
- [x] 16 `vidbyte/providers/__init__.py`
- [x] 17 `vidbyte/lib/runners/decision.py`
- [x] 18 `vidbyte/providers/README.md`
- [x] 19 `REPO_MAP.md`
- [x] 20 `skills/jev-agent/SKILL.md`
- [x] 21 `vidbyte/lib/enums/decision_model.py`

I checked the §12.4 obligations and the §12.5 checklist against `git diff 278448b0..HEAD`. Each new module has the seven-field A001 header and an explicit `__all__`. Every policy-token function has an `@intent` comment. No new exception class was added, no `httpx` import was added outside `vidbyte/lib/http`, and no module imports `vidbyte.agents` from `providers/` or `lib/`.

## Deviations

These are also recorded in spec §17, "Implementation deviations".

1. **Rows 13 and 15 build the URL differently (lint C017).**
   - Spec text: `f"{resolved.resolved_endpoint()}{path}"`. Built instead: `f"{ProviderModelRegistry.resolve_endpoint(self.provider, config.endpoint)}{path}"`.
   - In direct mode the two values are identical.
   - C017 followed `resolved_endpoint()` into its managed branch (`VIDBYTE_JEV_GATEWAY_ENDPOINT`) and reported two blocking findings:
     - POST `/api/v1/models/typesafe/decisions` matches no route in the contract;
     - `{host.path}` could match two contract routes.
   - Side effect: if nothing else changed, a managed TypeSafe config passed per call to a direct `SystemOneProvider` would send a `vb_live_` key to TypeSafe's direct host. To close that, `SystemOneProvider._config_for` now refuses `VIDBYTE_MANAGED`, with the same message as the constructor guard.
   - `OpenAIDecisionsProvider` cannot receive a managed config, because the config rejects managed mode for any provider except TypeSafe.
   - No suppression, baseline change, or contract edit. Commit `d07c328b`.
2. **Row 10.** `_decision_usage` computes `total_tokens` as input plus output when the payload has no total. It also falls back to the decision keys when the chat parse found only a total.
3. **Row 13.** `SystemOneProvider(decision_config=None)` raises with `provider="systemone"`, because no provider is known yet.
4. **Rows 13 and 15 add private helpers** beyond the named methods:
   - `_call` on both providers;
   - `OpenAIDecisionsRequest.question` and `option`;
   - `OpenAIDecisionsAnswers._by_name`, `_answer`, `_predicate`, `_choice`, `_score`, `_entries`, `_distribution`, `_level`.

   `text()` turns a `RecursionError` into a `ConfigurationError` that names `field_name`. No new class.
5. **Row 14.** Passes `label=_TYPESAFE_HOST.display_name` (equal to "TypeSafe") instead of the literal.
6. **Row 20.** The SKILL.md "line 47" sentence is at line 46 on this base.
7. **Not rebased.**
   - `origin/main` is 40 commits ahead. Rebasing would pull main's test changes into the `tests/` diff the orchestrator checks.
   - `git merge-tree --write-tree origin/main HEAD` reports three conflicts. All are cases where both sides appended to the same list:
     - `__all__` in `vidbyte/lib/constants/jev.py` (main adds SWARM constants);
     - `__all__` in `vidbyte/lib/enums/jev.py` (main adds `JevSwarmPlanQuestionKey` above it);
     - the constants import list in `vidbyte/lib/dataclasses/jev.py`.
   - Resolve each by keeping both sides.
8. **Rows 1, 6 and 7 share commit `8a140ba2`.** A new member without its registry and runner rows fails S014, so no commit holding only part of the three could pass.
9. **The §17 row is labelled `r5`, not `r4`.** The spec already had an `r4` row (the S1 clarification). Frontmatter `revision:` is unchanged at 4, since only `pr:` and `status:` were mine to edit.

## Files touched outside §12.3

None. `git diff --name-only 278448b0..HEAD -- . ':!docs' ':!tests'` lists exactly the 21 §12.3 paths. Under `docs/`, I edited only the spec cells I was allowed to: frontmatter `status:` and `pr:`, the AC-16 Proof cell, and §17.

## Budget (§8.4)

| Item | Allowed | Used |
|---|---|---|
| New files | 3 | 3 (`decisions.py`, `systemone.py`, `openai_decisions.py`) |
| New classes | 12 | 12: `DecisionAuthScheme`, `SystemOneHost`, `OpenAIDecisionsWireQuestion`, `OpenAIDecisionsWireRequest`, `DecisionHttpCall`, `DecisionFailures`, `SystemOneRequest`, `SystemOneAnswers`, `SystemOneProvider`, `OpenAIDecisionsRequest`, `OpenAIDecisionsAnswers`, `OpenAIDecisionsProvider` |
| New dependencies | 0 | 0 |
| Config keys | 6 env vars + 1 map + 7 constants | same |
| New collections | 2 | 2 (`SystemOneProvider.HOSTS`, six pricing blocks) |

## Gates (final lines, all run at code HEAD `d07c328b`; lint re-run at `67070b22`)

`python -m pytest tests/features/decision_model_providers -q`
```
........................................................................ [100%]
72 passed in 1.20s
```

Area suite: `python -m pytest tests/test_jev_agent.py tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_jev_usage_ledger.py tests/test_jev_preflight.py tests/test_jev_done.py tests/test_model_registry.py tests/test_agent_pricing.py tests/test_embedding_runner.py tests/test_agent_settings_validation.py -q`
```
...................................                                      [100%]
395 passed in 2.78s
```

Verification scripts, run with `PYTHONPATH=$(pwd)`. These are read-only scripts; none was modified.
```
40/40 Jev scaffold tests passed          (scripts/test-jev-agent-scaffold.py)
19/19 Jev managed gateway tests passed   (scripts/test-jev-managed-gateway.py)
Verification PASSED.                     (scripts/test-openrouter-provider-integration.py)
43/43 tests passed.                      (scripts/test-new-runners.py)
```

`git add -A && python lint/run.py` (exit 0):
```
A002   intent-comments                           680    703 IMPROVED
C016   public-api-contract-current                 0      0 CLEAN
C017   platform-route-contract                     0      0 CLEAN
S009   staged-mypy-contracts                     340    350 IMPROVED
S010   transport-parity                            0      5 IMPROVED
S014   provider-model-registry-parity              0      0 CLEAN
S024   maximum-control-flow-nesting               21     25 IMPROVED
S051   modernized-import-and-syntax-hygiene      258    259 IMPROVED
...
S062 RATCHETED: 889 known finding(s). Inspect with: python lint/run.py --rule S062 --all

SDK-LINT: PASS
```
No count is above its baseline, and `lint/baseline.json` is untouched.

`PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` (exit 0):
```
tests\test_web_operation_client_retry.py ..                              [100%]

====================== 2707 passed, 1 skipped in 19.92s =======================
CI passed.
```

`python scripts/run_ci.py` (exit 0; lint, compileall, the three check scripts, pytest, build, twine check, then install and smoke test in a fresh venv):
```
====================== 2707 passed, 1 skipped in 25.55s =======================
...
No broken requirements found.
Installed vidbyte-sdk 0.2.0 passed smoke checks.
CI passed.
```

`git diff c07abf49..HEAD --stat -- tests/` printed nothing.

## Tricky parts

- **C017 follows `DecisionModelConfig.resolved_endpoint()` through both branches.** Any new adapter that builds its URL from `resolved_endpoint()` is judged as a possible request to the Vidbyte gateway. Direct-only adapters must resolve the vendor endpoint themselves, and must then refuse managed configs, or a `vb_live_` key can reach a vendor.
- **`model: str | None` and S009.** Reading `config.model` anywhere typed as `str` adds staged-mypy findings. Every read goes through `resolved_model()`, including the two in `decision.py`. S009 fell from 350 to 340.
- **INV-24 pins `_TypeSafeCallBuilder`.** `tests/test_jev_managed_gateway.py` pins its name, its signature, and the header-free `repr` of the call it returns. `DecisionHttpCall` keeps `_TypeSafeHttpCall`'s field order and `repr=False` on `headers`.
- **S051 (I001) checks import order at a line length of 88** through `lint/ruff.toml`. New multi-line imports were sorted with `ruff --config lint/ruff.toml --select I001 --fix` on the new files only. The existing I001 in `models.py` was left alone, so its count stays at the baseline.
- **Encoding.** Python's stdin on this host decodes as cp1252, so scripts that replace em-dash text must read `sys.stdin.buffer` as UTF-8. Bash heredocs larger than about 8 KB fail with "unexpected EOF" and should be split.
- **README size.** `vidbyte/providers/README.md` is now 48,690 characters. Main's new A009 caps it at 55,000, so there is room, but not a lot, for the S6 merge.

## Merge with main (coordinator follow-up): BLOCKED

**State**
- Local HEAD: `7bfe29e8` (`chore(merge): merge origin/main into feat/decision-model-providers`).
  - Parents: `67070b22` (branch) and `77084eb2` (origin/main, 40 commits ahead).
  - The commit carries the `Co-Authored-By` trailer.
  - **Not pushed.** The merged tree fails `SDK-LINT`. `origin/feat/decision-model-providers` is still `67070b22`.
- Conflicts were resolved by keeping both sides:
  - `vidbyte/lib/constants/jev.py`: in `__all__`, main's SWARM constants come first, then the seven decision constants, following the file's append order.
  - `vidbyte/lib/dataclasses/jev.py`: the import list stays alphabetical, so the `JEV_SWARM_*` names come before `OPENAI_DECISIONS_PREDICATE_TYPE`.
  - `vidbyte/lib/enums/jev.py`: main's `JevSwarmPlanQuestionKey` is kept, and main's sorted `__all__` gets `DecisionAuthScheme` prepended.
- The constants `__all__` has 293 entries. Four names appear twice (`JEV_DONE_*_FIELD`), but that duplication already exists on base and on main.
- Auto-merged files were checked for semantic collisions and none were found:
  - `REPO_MAP.md`: main added SWARM rows, and the four decision rows each appear once.
  - `skills/jev-agent/SKILL.md`: main changed only the dynamic-compute line.
  - `vidbyte/lib/enums/__init__.py`: both `DecisionAuthScheme` and `JevSwarmPlanQuestionKey` are imported and exported.
  - `vidbyte/lib/registries/models.py`: main added an OpenRouter ownership-check early return inside `validate_provider_model_pair`, which does not interact with the decision rows.

**Gates on the merged tree**
- `python -m pytest tests/features/decision_model_providers -q` → `72 passed in 1.08s`
- Area suite → `404 passed in 3.12s`
- Test-tree contract: both `git diff c07abf49 HEAD -- tests/features/decision_model_providers/` and `git diff origin/main HEAD --stat -- tests/ ":(exclude)tests/features/decision_model_providers"` printed nothing.
- `git add -A && python lint/run.py` → exit 1:
  ```
  C009   default-model-priced                        4      1 REGRESSED
  C010   pricebook-vintage-bump                      1      0 REGRESSED
  ...
  SDK-LINT: FAIL
  ```
  Main's own new rules are clean: A009 0/0, C006 104/104, C007 16/16, C008 45/45. C017 is 0.
- `python scripts/run_ci.py` → `SDK-LINT: FAIL` / `CI failed: Command failed with exit code 1: ...lint\run.py`
- Full `python -m pytest -q` → `1 failed, 2842 passed, 1 skipped`.
  - The failure is `tests/test_codex_tools.py::CodexSdkContractTests::test_cancelled_turn_releases_its_waiting_reader`.
  - It is environment drift, not this change: main's #695 pins `openai-codex>=0.162.1,<0.163.0`, and the local interpreter has `0.147.0`.
  - I did not upgrade it, because that would change the shared global Python environment.

**Why this is blocked**
- C009 comes from main's #587 and is BLOCKING. It requires every default model of a `RUNNER_TYPE_TEXT` or `RUNNER_TYPE_DECISION` provider to resolve to a rate in `PROVIDER_PRICING`.
  - It states that an empty table is not a declaration and that guessed rates do not count.
  - New findings: `LIQUID: "d1"` (`models.py:78`), `BASETEN: "inception/mercury-decide"` (`:79`), and `MERAGPT: "sd-1"` (`:80`).
- Spec D-10, INV-18, and FR-4 require exactly those three empty blocks, because research found no first-party price for them.
- So the spec now contradicts a blocking rule on main. The fixes the rule offers are each closed to S3:
  - first-party rates would need new web research (spec §14 Never);
  - `_PRICED_PER_RESPONSE` is a lint change, and it does not describe these vendors anyway;
  - a baseline bump is on the never-list;
  - dropping the providers is a scope change and needs the S2 tests changed.
- C010 can be fixed mechanically: `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock` regenerates `lint/pricebook_vintage_lock.json` for the 2026-10-10 vintage.
  - That file is generated, lint-owned, and outside §12.3.
  - It should run only after the C009 outcome fixes the final rates.

### Merge with main, round 2 (after spec r6)

This round covers the C009 pricing fix for Liquid and meraGPT and a second merge of main. Nothing is pushed yet.

**Commits added on top of `b9843bca`**
- `da619d9a` feat(pricing): price Liquid d1 and meraGPT sd-1 per spec r6 [W-3; FR-4, AC-12]
  - Touches only `vidbyte/lib/registries/pricing.py`.
  - Adds `LIQUID: {"d1": ModelPricing(input_per_million=0.04, output_per_million=0.0)}`.
  - Adds `MERAGPT: {"sd-1": ModelPricing(input_per_million=0.04, output_per_million=0.0)}`.
  - Each row has a dated comment citing the first-party URLs listed in row 8.
  - I checked that `resolve(LIQUID, "d1:free")` returns the d1 rate (Q-10). `resolve(BASETEN, "inception/mercury-decide")` is still `None`.
- `5647ec32` chore(merge): merge origin/main into feat/decision-model-providers
  - Merges main at `6b7ba7c3` (#699, #700).
  - The merge had no conflicts and the trailer is present.

**Deviation from row 8**
- `BASETEN: {}` keeps its r5 comment, as the coordinator instructed ("Leave BASETEN as is").
- Row 8 of r6 gives new wording for that comment: "no public first-party price … the rate sits behind login … pending the user's decision".
- That wording should go in with the Baseten ruling.

**Gates on the merged tree (HEAD `5647ec32`)**
- `python -m pytest tests/features/decision_model_providers -q` → `72 passed in 1.13s`
- Area suite → `404 passed in 2.90s`
- `git add -A && python lint/run.py` → exit 1. Only the two expected rules regressed:
  ```
  C009   default-model-priced                        2      1 REGRESSED
  C010   pricebook-vintage-bump                      1      0 REGRESSED
  SDK-LINT: FAIL
  ```
  - The two C009 findings are `models.py:70` (MISTRAL, which is in the baseline) and `models.py:79` (BASETEN).
  - Other rules: A009 0, C016 0, C017 0, S014 0, and S009 is at 347 against a baseline of 350.
- `python -m pytest -q` → `2855 passed, 1 skipped in 25.89s`
- Test-tree contract: both `git diff b9843bca HEAD -- tests/features/decision_model_providers/` and `git diff $(git merge-base origin/main HEAD) HEAD --stat -- tests/ ":(exclude)tests/features/decision_model_providers"` printed nothing.

**Not done yet, by instruction**
- I have not run the C010 `--refresh-lock`.
- I have not pushed.
- I have not touched `lint/`, `tests/`, or the spec.

## P5 (spec r9/r10): seven new providers and price proof. DONE (it was blocked on EC-34; resolved by the r10 ruling below).

### Commits (local only; nothing is pushed)
| SHA | What it does |
|---|---|
| `98576b76` | chore(merge): merges origin/main `7be96284`. The conflicts were in the `typesafe.py` header (main's `from_decision`/`total` sentence is kept), the `dataclasses/jev.py` `__all__`, and the `enums/jev.py` `__all__`. After the merge the pack showed exactly 24 failed / 63 passed. |
| `5d1ec7c4` | Rows 1, 6, 7 and 8, committed together with `lint/pricebook_vintage_lock.json`. |
| `9d6e2d51` | Row 13: 15 `HOSTS` rows, plus header and `HOSTS`-comment edits. |
| `ce5be9dd` | Row 16: factory routing. |
| `88e8a61e` | Row 11: host lists. |
| `af4c5db7` | Row 4: comment only. |
| `80aa2b9b` | Row 15: comment only. |
| `bbedefff` | Row 19: REPO_MAP. |
| `eeadd8de` | Row 20: SKILL.md. |
| `5e8c93dd` | Row 18: README, +3,312 characters, 52,002 in total. |

### C010 lock refresh
I ran it once, after the last rate edit and before `5d1ec7c4`:
`python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock`
Output: `Refreshed lint/pricebook_vintage_lock.json: PRICING_AS_OF 2026-07-30 -> 2026-10-10.` (exit 0)

### Gates at `5e8c93dd`
- Feature pack: `1 failed, 86 passed in 1.24s`. The failure is `test_decision_regression_typesafe.py::AgentBoundaryTests::test_agent_settings_accept_decision_providers_but_runner_build_refuses_them`, failing with `AssertionError: ConfigurationError not raised`.
- Area suite: `406 passed in 2.54s`.
- Lint (`git add -A`, then `python lint/run.py`): exit 0, `SDK-LINT: PASS`.
  - C009 `1 1 RATCHETED` (the Mistral finding already in the baseline).
  - C010 `0 0 CLEAN`; A009, C016, C017 and S014 also `0`.
  - S009 is at 349 against a baseline of 350.
- Full `python -m pytest -q`: `1 failed, 2917 passed, 1 skipped`.
- `python scripts/run_ci.py`: lint passes; pytest then fails with `CI failed: Command failed with exit code 1: ...python.exe -m pytest`.
- Test-tree contracts: `git diff 63b8cc5a HEAD -- tests/features/decision_model_providers/` and `git diff $(git merge-base origin/main HEAD) HEAD -- tests/ ':(exclude)tests/features/decision_model_providers'` both print nothing.

### Why it was blocked (resolved, see "Resolution")
- The test checks EC-34 (spec r9 §6.3, INV-30, D-20): it expects `JevAgentSettings(provider="baseten", model_name="mercury-decide")` to raise `Model 'mercury-decide' is registered under provider 'inception', not 'baseten'.` when the settings are constructed.
- `JevAgentSettings.__post_init__` (`vidbyte/agents/jev/settings.py:121-145`) never calls `ProviderModelRegistry.validate_provider_model_pair`. Only the generic agent settings do (`vidbyte/lib/dataclasses/config.py:514`).
- The registry part of EC-34 does work: `validate_provider_model_pair(BASETEN, "mercury-decide")` raises the exact message. So all 15 r9 rows are built, and the failure is in the settings class, not the data.
- `settings.py` is not in §12.3, and §14 says to ask first before touching any file outside it. Making the test pass that way would also change the public validation contract of `JevAgentSettings`, which §9.2 does not describe.
- Today that pair passes settings, and `Runner.build()` refuses it with `Model 'mercury-decide' is a decision model and cannot drive an agent loop; call it through DecisionModelRunner.` (`runner_type="decision"`).
- Probe: I temporarily added `ProviderModelRegistry.validate_provider_model_pair(provider, self.model_name)` to `JevAgentSettings.__post_init__`. The full suite then gave `2918 passed, 1 skipped`. I reverted the change and committed nothing from it.

### Held back during the block (done after the ruling)
- Spec frontmatter `status: implemented` and the §17 row.
- Committing this report.
- The push and the MERGEABLE check.

### Resolution (spec r10)
- **Ruling: option C.** D-14 and Q-5 already place this refusal at runner build. Spec r10 (`3240c66e`) restates EC-34 accordingly:
  - `JevAgentSettings` accepts `("baseten", "mercury-decide")`;
  - the registry check raises the INV-30 ownership message;
  - the first runner build refuses the pair through `_refuse_decision_runner`.
- **Test side.** S2 changed that one assertion at `76b0674d`.
- **No code outside §12.3 changed.** `vidbyte/agents/jev/settings.py` is untouched.
- **Commits after the ruling:**
  - `5c4a7f80` docs(providers): correct OpenAI decisions header echo note [W-6; FR-9]. This is the r10 row 15 header line, and it closes the stale-header item.
  - `765acca3` docs(spec): record S3 P5 implementation. It sets `status: implemented`, adds §17 row r11, and marks deviation 7 as superseded.

### Final gates (HEAD `765acca3`)
- `python -m pytest tests/features/decision_model_providers -q` → `87 passed in 1.15s`
- Area suite → `406 passed in 2.58s`
- `git add -A && python lint/run.py` → exit 0, `SDK-LINT: PASS`.
  - C009 is `1 1 RATCHETED`, from the existing Mistral finding.
  - C010, C017, S014 and A009 are all `0`.
  - S009 is 349 against a baseline of 350.
- `python scripts/run_ci.py` → exit 0:
  ```
  SDK-LINT: PASS
  ====================== 2918 passed, 1 skipped in 16.17s =======================
  Installed vidbyte-sdk 0.2.1 passed smoke checks.
  CI passed.
  ```
- Both test-contract diffs printed nothing:
  - `git diff 76b0674d HEAD -- tests/features/decision_model_providers/`
  - `git diff $(git merge-base origin/main HEAD) HEAD -- tests/ ':(exclude)tests/features/decision_model_providers'`

### P5 deviations
- None new. Deviation 1 (C017: the direct adapters resolve the vendor endpoint and refuse managed configs) still stands.

### Tricky parts in P5
- **Inception and Baseten share an id.** `inception/mercury-decide` is Baseten's model id and also Inception's qualified catalog key. `provider_for_model` returns the first match in insertion order, so Baseten's key must be inserted before Inception's.
- **AC-21 reads the comment block as text.** Each URL must sit whole on one line, and no blank line may separate the comment from its `ModelProvider.X: {` line. The OpenRouter citation goes directly above `ModelProvider.OPENROUTER: {},`.
- **C010 counts rates that are new to the lock.** The lock was still at vintage 2026-07-30, so it counted all 19 decision rates as added. The single refresh covered both the r6 and r7 rates.
