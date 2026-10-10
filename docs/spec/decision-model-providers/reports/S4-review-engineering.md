LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the adapters, billing and guards are sound and every default is priced, but OpenRouter receives a one-key noul `criteria` that breaks INV-6, a `clef-flash` request most likely bills at clef's rate while the ledger records 0.038, and the per-call refusal that keeps a `vb_live_` key off TypeSafe's direct host has no test that can fail.

Reviewed: `git diff origin/main...9784a3f6` (53 files, +8092/-254). Local HEAD `f23da1da` changes only `pipeline.md`, so the code is identical.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Billed usage survives every failure path.**
  - `SystemOneProvider.run_decision` reads `usage` before it normalizes the answers (systemone.py:263-265).
  - `DecisionFailures.unexpected` carries that usage onto the error.
  - `DecisionModelRunner.arun` records a billed failure exactly once (decision.py:52).
  - Mutants that drop the usage (M14) or record it twice (M9) are both killed.
- **INV-30 ordering is explicit and pinned by index.**
  - `provider_for_model("inception/mercury-decide") == baseten`, `"mercury-decide" -> inception`, and `kai`/`instinct`/`clef-flash`/`d1` route to their own hosts (probe p1).
  - Do not reorder `constants/runners.py`.
- **The pricebook math is right.**
  - gpt-6-luna at 272,000 input tokens costs 0.0272 and at 272,001 costs 0.0544002, which is the strict `>` boundary; mutant M2 (inclusive threshold) is killed.
  - Every decision default resolves to a row, `PRICING_AS_OF` and the vintage lock moved together, and C009, C010 and S014 pass.
- **A Vidbyte key cannot reach a vendor host today.**
  - Managed mode is refused in `DecisionModelConfig` for every provider except TypeSafe, and in `SystemOneProvider` both at construction and per call (probe V4: 0 requests).
  - A malformed key (non-ASCII, newline) never appears in an error message or in `details` (probe p5).
  - The 401 message names each host's own env var.

FINDINGS (ranked, most severe first, max 15)

R-E1 [Major] [pre-mortem / correctness] vidbyte/providers/systemone.py:85-89 — OpenRouter receives a one-key noul `criteria` when only one of the true/false options is given, which violates INV-6 and gets a vendor 400
  Evidence: The code synthesizes both keys only when the question has *no* options:
  ```
  if not question.options and question.question_type is JevQuestionType.NOUL and host.noul_criteria_required:
      return MappingProxyType({JEV_NOUL_TRUE: None, JEV_NOUL_FALSE: None})
  if not question.options:
      return None
  return MappingProxyType({option.name: option.description for option in question.options})
  ```
  Probe `p4_openrouter.py` builds the OpenRouter body:
  ```
  [] -> {'true': None, 'false': None}
  [('true', 'refund now')] -> {'true': 'refund now'}
  [('false', None)] -> {'false': None}
  [('true', 'a'), ('false', 'b')] -> {'true': 'a', 'false': 'b'}
  ```
  The test `test_decision_systemone_wire.py:110-131` covers only "no options" and "both described", so it cannot catch this.
  Failure: Take an OpenRouter config and `JevQuestion(NOUL, options=(JevOption("true", description="refund now"),))`. The question is valid, since `JevQuestion` accepts it. The body sent is `criteria: {"true": "refund now"}`. OpenRouter rejects it ("criteria must contain both true and false keys", EC-6), so the caller gets a `ProviderRequestError` for a request that INV-6 says always carries both keys. The decision never succeeds.
  Smallest fix: In `criteria`, check the host before the general mapping. For a noul question on a host with `noul_criteria_required`, return `MappingProxyType({JEV_NOUL_TRUE: described.get(JEV_NOUL_TRUE), JEV_NOUL_FALSE: described.get(JEV_NOUL_FALSE)})`, where `described = {o.name: o.description for o in question.options}`. Add two OpenRouter subtests: true only, and false only.
  Spec IDs: INV-6, EC-6, AC-4

R-E2 [Major] [data / money] vidbyte/lib/constants/jev.py:29 + vidbyte/providers/systemone.py:217 — every Cloudflare model is posted to the fixed clef URL, so a `clef-flash` call most likely runs and bills as clef (0.24) while the ledger records 0.038
  Evidence: The path is fixed, whatever the model:
  ```
  CLOUDFLARE_CLEF_PATH: str = "/run/@cf/cloudflare/clef"
  ModelProvider.CLOUDFLARE: SystemOneHost(display_name="Cloudflare", path=CLOUDFLARE_CLEF_PATH, model_from_request=True),
  ```
  Probe p3 shows what a `clef-flash` request produces:
  ```
  Cloudflare clef-flash: url https://api.cloudflare.com/client/v4/accounts/abc/ai/run/@cf/cloudflare/clef body model clef-flash | echo @cf/cloudflare/clef | record clef-flash 0.038
  ```
  Workers AI selects the model from the `/ai/run/<model>` URL. `context/provider-research-2.md:502` says of `clef-omni`: "Its curl path is `/ai/run/@cf/cloudflare/clef-omni` with body `model: "clef-omni"` ... Calling `clef-omni` would need either that path to accept `model:"clef-omni"` (unverified) or a per-model path." `clef-flash` has the same unverified premise, yet it ships through this path.
  The tests pin this behavior instead of testing it:
  - `test_decision_acceptance.py:76-80` asserts that a `clef-flash` run posts to `.../run/@cf/cloudflare/clef`.
  - `test_decision_usage_metering.py:29` scripts the echo `@cf/cloudflare/clef` for a `clef-flash` request and expects 0.038.
  Failure: Running the spec §4 snippet `DecisionModelConfig(provider=CLOUDFLARE, model="clef-flash", endpoint=...)` has two effects:
  - The caller asks for the cheap model but is answered by clef.
  - Cloudflare bills 0.24/M input, while `UsageTracker` records `clef-flash` at 0.038/M, a 6.3x under-report on every call. The echo that would reveal it (`@cf/cloudflare/clef`) is discarded because `model_from_request=True`.

  A related case: an explicit `model="clef-omni"` resolves by prefix to clef's 0.24 (probe p1), although NG-22 excludes it.
  Smallest fix: Build the Cloudflare path from the request model, `f"/run/@cf/cloudflare/{config.resolved_model()}"`, in `_call` for the Cloudflare row. This adds no `SystemOneHost` field, and the acceptance test URL becomes `.../run/@cf/cloudflare/clef-flash`.

  If the orchestrator rules that this is NG-22's "per-model path, a new host capability" (spec §12 "ask first"), treat it as [scope-adding] and take it as a follow-up. In that case the in-scope fix is a README "Tenant endpoints" sentence: every Cloudflare model is posted to the clef URL, and `clef-flash` on that URL is unverified and may be billed at clef's rate. The verifier should check r1 `context/provider-research.md` §3.4, which I was not allowed to read, for proof that the clef URL serves `clef-flash`.
  Spec IDs: INV-27, EC-27, AC-12 (the 0.038 expectation rests on this), D-17, NG-22

R-E3 [Major] [test quality / security] vidbyte/providers/systemone.py:302-303 — the per-call managed refusal is the only thing that keeps a `vb_live_` key off TypeSafe's direct host (S3 deviation 1), and deleting it leaves all 493 tests green
  Evidence:
  ```
  if resolved.mode is DecisionModelMode.VIDBYTE_MANAGED:
      raise ProviderConfigurationError("SystemOneProvider sends direct calls only; managed TypeSafe decisions go through TypeSafeProvider.", provider=self.provider.value)
  ```
  Mutant M1 removes these two lines:
  ```
  MUT=M1_no_percall_managed_guard PYTHONPATH="$SP;." python -m pytest -p mutplug tests/features/decision_model_providers <area suite> -q -p no:cacheprovider -> 493 passed in 3.05s
  ```
  Probe `p6_m1_effect.py`, with M1 applied, passes a managed config per call to `SystemOneProvider(decision_config=DecisionModelConfig(api_key="ts-key"))`:
  ```
  SENT https://api.typesafe.ai/v1/systemone auth= Bearer vb_live_a...
  ```
  The current code instead raises `ProviderConfigurationError`, with 0 requests sent.

  The tests do not reach this line:
  - Test-plan row 76 (`test_system_one_provider_construction_guards`) covers only the constructor guard.
  - Row 75 (`test_adapter_refuses_a_config_for_another_provider_before_any_call`) covers only a foreign provider.
  - `S3-implementer.md:111` names this exact leak as the reason the line exists.
  Failure: The code holds today. A later refactor that drops or reorders the check, for example by merging `_config_for` with `TypeSafeProvider._config_for` (which accepts managed configs), would post the tenant's Vidbyte gateway key to `api.typesafe.ai` as a vendor bearer token, and no test would fail.
  Smallest fix: Add one negative test in `test_decision_failures.py::CapabilityAndGuardTests`. Build a direct TypeSafe `SystemOneProvider`, call `run_decision(config=DecisionModelConfig(mode=VIDBYTE_MANAGED, api_key="vb_live_"+"a"*32))`, and assert the exact message, `provider == "typesafe"`, and `transport.requests == []`.
  Spec IDs: T-4, INV-3, INV-28, AC-19 (deviation 1 safeguard)

R-E4 [Minor] [test quality] vidbyte/providers/openai_decisions.py:79-80 — AC-17's literal input, a description on one option, is never tested; mutant M21 ("refuse only when every option is described") survives
  Evidence: The code refuses if *any* option has a description:
  ```
  if any(option.description is not None for option in question.options):
  ```
  The test `test_decision_openai_wire.py:70` describes both options:
  ```
  described = fx.noul_question(options=(JevOption("true", description="refund now"), JevOption("false", description="no refund")))
  ```
  AC-17's Given is `JevOption("true", description="...")` alone.
  ```
  MUT=M21_refuse_only_when_all_described ... -> 493 passed in 2.87s
  ```
  Failure: A regression from `any` to `all`, which is a natural "both criteria present" reading, would silently drop a one-sided rubric and send a bare predicate. That is exactly the case EC-7 says must never happen. The code is correct today.
  Smallest fix: Add a third case to that test, `(JevOption("true", description="refund now"), JevOption("false"))`, expecting the same `ConfigurationError` and no requests.
  Spec IDs: AC-17, EC-7, D-11

R-E5 [Minor] [test quality] vidbyte/providers/systemone.py:261, vidbyte/providers/openai_decisions.py:253 and :213-214 — two adapter behaviors that no test can fail on
  Evidence:
  - **M12, the per-call config is ignored when sending.** Mutant M12 makes `_call` use `self._decision_config` instead of the resolved per-call config, and 493 tests still pass. "Per-call config wins" (§8.5) is asserted only at `test_decision_failures.py:154-155`, `self.assertIs(baseten._config_for(same_provider), same_provider)`, never on the request that is sent. `DecisionModelRunner.arun` always passes `config=self._config` (decision.py:48), which is why no runner-level test notices.
  - **M4, the duplicate-entry check is gone.** Mutant M4 deletes the duplicate-entry check, `if len(keys) != len(names): raise ... "list an option more than once."`, and 493 tests still pass. Probe p3 shows the check works today: `dup distribution -> ProviderResponseError OpenAI 'probabilities' for 'team' list an option more than once.`
  Failure:
  - **Under M12:** a direct caller of `run_decision(config=other_key_same_provider)` sends the adapter's key, endpoint and model, so the wrong account is billed.
  - **Under M4:** a vendor answer that lists `billing` twice is accepted silently, and the later value wins.
  Smallest fix:
  - In `test_adapter_refuses_a_config_for_another_provider_before_any_call`, run the `same_provider` config through `run_decision` and assert its model and endpoint on `transport.requests[0]`.
  - Add one OpenAI answer with a repeated option, expecting `ProviderResponseError`.
  Spec IDs: §8.5 `_config_for` ("per-call config wins"), INV-28, INV-8 (a duplicate answer is malformed)

R-E6 [Minor] [data / ledger] vidbyte/lib/runners/decision.py:52, vidbyte/lib/registries/pricing.py:248, vidbyte/providers/README.md:698-699 — three ids the SDK itself offers record `cost_usd=None` without saying so
  Evidence: Probes p1 and p3:
  - `meragpt state-decider-1 -> None`. This is a registered bare catalog key (`constants/runners.py:338`, spec §9 bare list). meraGPT is `model_from_request=True`, so the record keeps `state-decider-1`, while the only row is `"sd-1"`, which the row's own comment calls an alias of the same model.
  - `Vercel recipe: ... record openai openai/gpt-6-luna-decisions None cost_complete False`. This is the README recipe verbatim.
  - `Nace alias billed failure record: drex-latest None cost_complete False`. A billed failure is priced on `self._config.resolved_model()`, while the success path prices the echo `drex-v1.5` (EC-35).
  Failure: A user who follows the catalog or README gets an incomplete ledger rollup (`cost_complete=False`) and no warning. The README says this outright for Foundry deployment names only.
  Smallest fix: Add one README sentence under "Decision providers" saying that the Vercel model id and meraGPT's `state-decider-1` record `cost_usd=None`. As a [scope-adding] follow-up, add alias normalization (`state-decider-1`/`decider-1` -> `sd-1`; for Nace billed failures, a priced fallback or acceptance of the gap).
  Spec IDs: INV-27, EC-35, INV-18 (no guessed rows, so the alias must cite meraGPT's own page)

VERIFIED CLAIMS: each claim checked and whether it held
1. **"The 87-test pack passes."** HELD: `87 passed in 1.17s`. The area suite also passes (`406 passed`), and so do the pack and area together (`493 passed`).
2. **INV-30 ordering.** HELD.
   - `provider_for_model("inception/mercury-decide") -> baseten`, `"mercury-decide" -> inception`, `"baseten/inception/mercury-decide" -> baseten`.
   - `kai -> hanzo`, `instinct -> zoodata`, `clef-flash -> cloudflare`, `d1 -> liquid`, `sd-1`/`state-decider-1 -> meragpt`.
3. **gpt-6-luna tier with `threshold_inclusive=False`.** HELD: 272,000 tokens -> 0.0272, 272,001 -> 0.0544002, 300,000 -> 0.06. Mutant M2 makes 2 tests fail.
4. **S3 deviation 1: "SystemOneProvider._config_for now refuses VIDBYTE_MANAGED".** HELD in code; probe V4 raises with 0 requests. NOT covered by any test (R-E3).
5. **INV-6: "OpenRouter always receives `criteria: {"true": …, "false": …}`".** DID NOT HOLD for one-sided options (R-E1).
6. **Test plan: AC-17 "described noul refused" is covered.** PARTIALLY HELD: only the two-sided case is tested (R-E4).
7. **INV-27 echo flags.** HELD.
   - Flipping `model_from_request` for HANZO, CELERIS or UPSTAGE (M3) fails tests.
   - Cloudflare, meraGPT and Upstage keep the request id; Nace, Hanzo and Vansa report the echo.
8. **Lint.** HELD:
   - `C009 RATCHETED: 1 known finding(s)` (the pre-existing MISTRAL baseline);
   - `S014 ... 0 0 CLEAN`;
   - `C010 ... 0 0 CLEAN`;
   - each run ends `SDK-LINT: PASS`.
9. **INV-29 / C010.** HELD: `PRICING_AS_OF = "2026-10-10"`, and the vintage lock was refreshed in the same diff.
10. **No secret leaks through error text.** HELD.
   - A key containing U+2010 makes the call fail with `perplexity decision failed with an unexpected UnicodeEncodeError: 'ascii' codec can't encode character ...`.
   - `message has key: False | details has key: False`.
11. **Transport policy.** HELD.
   - `DecisionHttpCall.send` does not override `follow_redirects`, so the transport default `follow_redirects=False` applies (transport.py:40).
   - In direct mode the idempotency key is never sent as a header; it exists only to satisfy the POST-retry guard (systemone.py:308-311).
12. **The longest-prefix pricing step prices unknown sibling ids at a neighbour's rate.** This is existing behavior, not new. Examples: `kai-pro`, `solar-decide-flash`, `gpt-6-luna-mini`, `d10`, `clef-omni` (probe p1). The spec adds rows for `drex-v1.0` and `instinct-*` against exactly this, so I record it with no finding.

COMMANDS RUN: each with its final lines
- `git log --oneline origin/main..HEAD`, `git diff origin/main...9784a3f6 --stat` -> `53 files changed, 8092 insertions(+), 254 deletions(-)`. `git diff 9784a3f6 HEAD --stat` -> pipeline.md only.
- `python -m pytest tests/features/decision_model_providers -q -p no:cacheprovider` -> `87 passed in 1.17s`
- `python -m pytest tests/test_jev_agent.py tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_jev_usage_ledger.py tests/test_jev_preflight.py tests/test_jev_done.py tests/test_model_registry.py tests/test_agent_pricing.py tests/test_embedding_runner.py tests/test_agent_settings_validation.py -q -p no:cacheprovider` -> `406 passed in 3.38s`
- Mutation runs, each as `MUT=<m> PYTHONPATH="$SP;." python -m pytest -p mutplug tests/features/decision_model_providers <area suite> -q -p no:cacheprovider`, where `$SP` is the scratchpad `probes/` directory:
  - base -> `493 passed`
  - **Survived** (493 passed):
    - `M1_no_percall_managed_guard`
    - `M12_run_uses_adapter_config`
    - `M21_refuse_only_when_all_described`
    - `M4_openai_no_duplicate_check`
  - `M2_luna_threshold_inclusive` -> `2 failed, 491 passed`
  - **Killed** in the earlier pass (failures as expected):
    - `M3_flip_echo_{HANZO,CELERIS,UPSTAGE}`
    - M5 (`_level` off by one)
    - M6
    - M7 and M8 (malformed-answer wrap removed)
    - M9 (double billed record)
    - M10 (Vansa path)
    - M11 (score choice)
    - M14 (`unexpected` drops usage)
    - M23 (unexpected answer names ignored)
    - M24 (response excerpt dropped)
- `python probes/p1_pricing.py` -> pricing and routing table (quoted in R-E2, R-E6 and claims 2, 3, 12)
- `python probes/p3_guards.py` -> `V4 managed per-call -> ProviderConfigurationError ... requests: 0`, the Cloudflare, Vercel, dup-distribution and Nace lines quoted above
- `python probes/p4_openrouter.py` -> the four criteria lines quoted in R-E1
- `PYTHONIOENCODING=utf-8 python probes/p5_header.py` -> `message has key: False | details has key: False`
- `PYTHONPATH="$SP;." python probes/p6_m1_effect.py` -> `SENT https://api.typesafe.ai/v1/systemone auth= Bearer vb_live_a...`. The unmutated twin, `p6_base.py`, prints `raised ProviderConfigurationError SystemOneProvider sends direct calls only; ...`.
- `python lint/run.py --rule C009` -> `SDK-LINT: PASS`. `--rule S014` -> `0 0 CLEAN` / `SDK-LINT: PASS`. `--rule C010` -> `0 0 CLEAN` / `SDK-LINT: PASS`.
- `git status --short` -> only the untracked S4 reports. No repo file was edited by this review apart from this report.
