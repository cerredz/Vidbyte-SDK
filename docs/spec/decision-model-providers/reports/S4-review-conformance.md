LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — the PR delivers spec r10 nearly row for row (87/87 pack tests, 406 area tests, SDK-LINT PASS, and the §4 snippet reproduces AC-1 exactly), but OpenRouter still gets a one-key noul `criteria` whenever a question names only one of true/false, which breaks INV-6 "always" and EC-6, and the new OpenAI normalizer nests its helpers three levels deep, against AGENTS.md principle 1.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- TypeSafe regression safety. In `vidbyte/providers/typesafe.py` the managed branches are byte-identical to main, and direct mode reaches System One only through `SystemOneProvider.HOSTS[ModelProvider.TYPESAFE]`, `SystemOneRequest`, `SystemOneAnswers` and `DecisionFailures`. All 7 regression-pack tests and the 406-test area suite pass. Do not re-split the relocated classes.
- Config guards are exact.
  - The unsupported-provider message lists all 16 providers sorted.
  - Managed mode for any non-TypeSafe provider raises "VIDBYTE_MANAGED decision mode is available only for provider typesafe." (`model_configs.py:376`).
  - `validate()` resolves the key first, then the endpoint (`:402`).
  - `model` is filled from `DECISION_DEFAULT_MODELS` in `__post_init__`, and `resolved_model()` reads it (`:410`).
  - Probes of EC-1, EC-2, EC-4, EC-20, EC-24 and AC-8 all print the spec's exact messages.
- Catalog ownership (INV-30, AC-22, EC-34). In `vidbyte/lib/constants/runners.py`, `baseten/inception/mercury-decide` comes before `inception/mercury-decide`. As a result, `provider_for_model("inception/mercury-decide")` returns baseten, `provider_for_model("mercury-decide")` returns inception, and `(BASETEN, "mercury-decide")` raises the ownership message word for word.
- The pricebook matches §9.1 cell for cell.
  - 13 new decision blocks, plus the `gpt-6-luna` tier row (`pricing.py:110`: threshold 272_000, 0.20 over it, `threshold_inclusive=False`, so strict `>`).
  - Each block has a contiguous comment directly above it that carries every §9.1 URL and 2026-10-10.
  - `PRICING_AS_OF="2026-10-10"` (`pricing.py:54`), and the lock file was refreshed through C010.
  - C009 reports only the old Mistral entry. C010 is 0.

FINDINGS (ranked, most severe first, max 15)

R-C1 [Blocker] [every-ID] vidbyte/providers/systemone.py:85-89 — a noul question with only one of true/false sends OpenRouter one criteria key, not both, violating INV-6 "always" and EC-6
  Evidence:
      if not question.options and question.question_type is JevQuestionType.NOUL and host.noul_criteria_required:
          return MappingProxyType({JEV_NOUL_TRUE: None, JEV_NOUL_FALSE: None})
      if not question.options:
          return None
      return MappingProxyType({option.name: option.description for option in question.options})
    - The `noul_criteria_required` branch only fires when the option set is empty.
    - `JevQuestion` accepts any subset of the noul keys (`vidbyte/lib/dataclasses/jev.py:294-297`: "only the optional keys ('true', 'false')").
    - `python <scratchpad>/s4/probe1.py` sends each case through `DecisionModelRunner(DecisionModelConfig(provider=OPENROUTER, api_key="k"))` over a scripted transport and prints the `criteria` in the body that was sent:
      options [] -> criteria sent to OpenRouter: {'true': None, 'false': None}
      options ['true'] -> criteria sent to OpenRouter: {'true': 'refund owed'}
      options ['false'] -> criteria sent to OpenRouter: {'false': None}
      options ['true', 'false'] -> criteria sent to OpenRouter: {'true': None, 'false': None}
  Failure:
    - Input: `JevQuestion(name="q", question_type=NOUL, instructions="i", options=(JevOption("true", description="refund owed"),))` on an OpenRouter runner.
    - Result: the body carries `criteria: {"true": "refund owed"}`. EC-6 says OpenRouter rejects any noul criteria without both keys ("criteria must contain both true and false keys"). The caller gets a provider error for a question the SDK validated and accepted.
    - INV-6 says the host "always receives `criteria: {"true": <description or null>, "false": <description or null>}` on noul questions". That holds on the empty path and the full path, but not on the two partial paths.
    - The pack test `test_openrouter_always_sends_noul_criteria_while_other_hosts_keep_typesafe_behaviour` (`tests/features/decision_model_providers/test_decision_systemone_wire.py:110`) exercises only the empty and complete option sets, so it stays green.
  Smallest fix: in `SystemOneRequest.criteria`, handle noul with `host.noul_criteria_required` before the empty-options check, and always emit both keys:
    `descriptions = {o.name: o.description for o in question.options}`
    `return MappingProxyType({JEV_NOUL_TRUE: descriptions.get(JEV_NOUL_TRUE), JEV_NOUL_FALSE: descriptions.get(JEV_NOUL_FALSE)})`
    Other hosts keep today's TypeSafe-identical body. A partial-option assertion in the existing OpenRouter test needs a test grant.
  Spec IDs: INV-6, EC-6, FR-7 ("builder + encoder honouring `noul_criteria_required`"), A-5

R-C2 [Major] [every-ID] vidbyte/providers/openai_decisions.py:160-227 — the new `OpenAIDecisionsAnswers` nests helpers three levels deep (`normalize` → `_answer` → `_choice`/`_score` → `_entries`/`_distribution`/`_level`), against AGENTS.md principle 1 and the §12.4 checklist's "never deeper"
  Evidence:
    - The call chain:
      - `:137`: `normalize` calls `self._answer(...)`.
      - `:169-172`: `_answer` calls `self._predicate`, `self._score` and `self._choice`.
      - `:184-185`: `_choice` calls `self._entries(...)` and `self._distribution(...)`.
      - `:194-195`: `_score` calls `self._entries`, `self._distribution` and `self._level`.
    - AGENTS.md:23: "a function may call another of its own functions, but that second function should not call a third ... lift that call up into the main function".
    - spec.md:742 (§12.4): "call chains stay one level deep (`run_decision` → builder/encoder/normalizer, never deeper)".
    - S3 deviation 4 lists these helpers but not their depth.
    - The builder has the same shape: `build` → `question` → `text` at `:63-92`, and `encode` → `option` → `text` at `:95-113`. But §8.5 prescribes that shape for System One's `build` → `question` → `criteria`, so the spec contradicts itself there. Only the normalizer is unambiguous.
    - No lint rule checks call depth (`lint/rules/README.md` has none), so `SDK-LINT: PASS` cannot catch this.
  Failure:
    - (convention) The rule is AGENTS.md "1. Keep Call Chains One Level Deep". A human reviewer would write: "`_choice` and `_score` call their own helpers; lift `_entries`/`_distribution`/`_level` into `_answer`."
    - Rated Major rather than Blocker for four reasons:
      - AGENTS.md says "should".
      - The behaviour is correct (11/11 OpenAI-wire tests pass).
      - The spec's own §8.5 prescribes a two-level builder.
      - `SystemOneAnswers` has the same depth only because §12.3 row 13 relocates today's `_TypeSafeAnswerNormalizer` as-is, so it is not part of this finding.
  Smallest fix: have `_answer` fetch the entries, build the pairs (calling `_level` for score), compute the distribution, and pass the result to `_choice`/`_score`. After that, no helper calls another `self.` helper. Messages and behaviour stay unchanged.
  Spec IDs: §12.4 checklist (AGENTS.md principle 1). Behaviour conforms to FR-9 and INV-7.

R-C3 [Minor] [user's words] vidbyte/providers/README.md:94 — 11 of the 13 new API-key env vars appear in no README, although spec §12.5 says they "are documented in §9.3 and the README matrix"
  Evidence:
    - spec.md:775: "r7's seven env vars are documented in §9.3 and the README matrix instead; no `.env.example` is created".
    - The Endpoint And Auth Matrix columns are Provider / Module / Auth header / Endpoints, with no env-var column.
    - `grep -c <VAR> vidbyte/providers/README.md`:
      - PERPLEXITY_API_KEY: 1. VANSA_KEY: 1.
      - All 0: CLOUDFLARE_API_TOKEN, FOUNDRY_API_KEY, LIQUID_API_KEY, BASETEN_API_KEY, MERAGPT_API_KEY, CELERIS_API_KEY, NACE_API_KEY, UPSTAGE_API_KEY, INCEPTION_API_KEY, HANZO_API_KEY, ZOODATA_API_KEY.
  Failure:
    - The spec claims documentation the README does not contain.
    - Someone setting up Cloudflare from the README cannot learn the non-standard name `CLOUDFLARE_API_TOKEN`. Every name shows up only in the missing-key ConfigurationError (which does name it, per INV-13, so behaviour is unaffected; hence Minor).
    - This is not a request for `.env.example`, which is ruled out.
  Smallest fix: either
    - add one line to the README "Decision providers" section mapping each of the 13 hosts to its env var (about 450 characters; the README is at 52,002 of its 54,000 budget), or
    - reword the §12.5 sentence to cite §9.3 and the registry only.
  Spec IDs: §12.5, FR-15

R-C4 [Minor] [scope-adding] vidbyte/lib/constants/jev.py:29 — `model="clef-flash"` (the §4 snippet's own Cloudflare call) is posted to the fixed `/run/@cf/cloudflare/clef` route, while Cloudflare lists clef-flash as a separate Workers AI model, `@cf/cloudflare/clef-flash`
  Evidence:
    - `CLOUDFLARE_CLEF_PATH: str = "/run/@cf/cloudflare/clef"` is used by the Cloudflare `HOSTS` row (systemone.py:217).
    - `pricing.py` prices `clef-flash` at 0.038/0.0, against `clef` at 0.24/0.0.
    - context/pricing-proof.md:75 gives `@cf/cloudflare/clef-flash` its own price row, and :77 gives it its own model card.
    - provider-research-2.md:502, on clef-omni: "Calling `clef-omni` would need either that path to accept `model:"clef-omni"` (unverified) or a per-model path".
    - NG-22 (spec.md:84) excludes clef-omni for that reason, yet clef-flash ships on the same fixed path, and no allowed source shows the clef route honouring `model: "clef-flash"`.
  Failure:
    - The request is `DecisionModelRunner(DecisionModelConfig(provider=CLOUDFLARE, model="clef-flash", endpoint=".../ai"))`. It sends POST `.../ai/run/@cf/cloudflare/clef` with body model "clef-flash".
    - If Workers AI picks the model by path, Cloudflare runs and bills clef. The ledger records $0.038 per 1M tokens against a $0.24 charge, a 6.3x under-report. The other possibility is that Cloudflare rejects the body.
    - This is unverified, because vendor fetches are barred. The spec chose this path itself (§9.1 row at spec.md:535; §4 snippet at spec.md:118), so this is a risk, not an implementation miss.
  Smallest fix: follow-up for the user. Verify against Cloudflare's clef-flash model card. If the route is per-model, either:
    - derive the path from the model, which NG-22 calls a new host capability, or
    - drop the `clef-flash` aliases and price row until that capability exists.
  Spec IDs: AC-1, AC-12, FR-4, NG-22

R-C5 [Minor] [every-ID] vidbyte/agents/jev/alignment/skills.py:130 — a production read of `DecisionModelConfig.model` bypasses `resolved_model()`, so INV-2's "every production call site" does not hold as written
  Evidence:
    - The read: `request_bytes = len(json.dumps({"model": self.decision.model, "state": state, "questions": payloads}).encode("utf-8"))`.
    - spec.md:173 (INV-2): "`resolved_model() -> str` is the typed reader every production call site uses (`SystemOneRequest.build`, `OpenAIDecisionsRequest.build`, `DecisionModelRunner.arun` / `model_name`, and `TypeSafeProvider.run_decision` ...)".
    - The four call sites INV-2 names all conform.
    - This one came from origin/main (#698) after the spec's base, sits outside §12.3, and reads the field this PR widened to `str | None`.
  Failure: no runtime difference, because `__post_init__` always fills `model` and JevAgent stays on TypeSafe (NG-2). The invariant's weighted word is simply false for one site.
  Smallest fix: either narrow INV-2's wording to the four named sites (spec-only), or change the read to `self.decision.resolved_model()`. The second option is an edit outside §12.3 and needs the ask-first grant.
  Spec IDs: INV-2

VERIFIED CLAIMS:
1. "87-test pack passes on 9784a3f6": HELD. 87 passed. The area suite also HELD at 406 passed.
2. "SDK-LINT PASS, no baseline change": HELD.
   - Exit 0.
   - REGRESSED none.
   - C009 1/1 (Mistral, models.py:70), C010 0, C016 0, C017 0, S014 0, A006 34/34, A009 0, S009 349/350 IMPROVED.
   - `lint/baseline.json` diff is empty.
3. "Test tree changed only under the three grants": HELD. Both briefing diffs print 0 lines.
4. "Files outside §12.3: none (besides the C010 lock)": HELD. The non-docs, non-tests diff is exactly the 21 §12.3 paths plus `lint/pricebook_vintage_lock.json`.
5. AC-1, spec §4 snippet run as written: HELD.
   - With no keys: `ConfigurationError: Missing API key for provider perplexity. Pass api_key or set PERPLEXITY_API_KEY.`, and no network attempt.
   - With scripted transports:
     - `noul` 0.8, choice `billing`.
     - `(ModelProvider.PERPLEXITY, 'pplx-decider-v1.1-27b')`.
     - Probabilities `{'true': 0.8, 'false': 0.19999999999999996}`.
     - POST `https://api.perplexity.ai/v1/decisions`, and POST `https://api.openai.com/v1/decisions` with model `gpt-6-luna`.
6. INV-30 / AC-22 / EC-34 ordering and ownership: HELD (probe2; pack test `test_agent_settings_accept_decision_providers_but_runner_build_refuses_them` passes).
7. INV-20 (decision keys never activate a text runner; defaults detect as AUTO): HELD.
   - `_resolve_from_environment` with only decision keys raises "No model providers have API keys configured".
   - gpt-6-luna is TEXT and uncatalogued by design.
8. "Every decision default resolves to a price": HELD, except OpenRouter (`{}`, priced by `usage.cost`, by design).
9. §8.4 budget: HELD.
   - 3 new files and 3 adapters (12 classes in total).
   - 16 providers.
   - 15 `HOSTS` rows serving 14 direct hosts.
   - 13 env vars, 1 new map (`DECISION_DEFAULT_MODELS`), 7 constants, 13 pricing blocks plus 1 tier row.
   - 0 dependencies, 0 `SystemOneHost` fields added.
10. §14 Never list: HELD.
    - No added `noqa`, `type: ignore` or `nosec`.
    - No TODO, NotImplementedError or placeholder.
    - No weakened test, no baseline edit, no `.env.example`, no new `SystemOneHost` field, no change to `DecisionModelMode`, `JevRuntimeSettings` or `vidbyte.__all__`.
11. `claude --cloud` text: HELD (absent). It is not in vidbyte/, tests/, skills/, lint/, spec.md, test-plan.md, any branch commit message, or the PR body. It appears only in request.md, the verbatim record.
12. "Every implementation commit cites spec IDs and carries the trailer": HELD for every vidbyte-touching commit. The only commit without it is the S0 docs commit b14b1674, a process artifact.
13. "The §12.4 checklist is satisfied": NOT HELD. The call-depth item fails (R-C2).
14. "Echo hosts are exactly TypeSafe, Perplexity, Celeris, Nace.AI, Inception, Hanzo and Vansa" (INV-27, EC-19): HELD. The `HOSTS` rows have `model_from_request=False` for exactly those seven, and `UsageTracker` prices `response.model`.
15. README at or under 54,000 characters (§12.4, A009): HELD. 52,002 characters, read as UTF-8 with the BOM stripped.
16. PR state: HELD. OPEN, draft, head 9784a3f6. The local HEAD f23da1da differs only in pipeline.md.

ID-by-ID verdicts. Prosecution vs defense; "conform" means the defense cited the file logic or a passing pack test.
- FR-1..FR-16: conform, except that FR-7 is partially broken by R-C1 and FR-15's documentation claim is unmet per R-C3.
  - FR-4 checked row by row against §9.1.
  - FR-6, FR-7 and FR-9 checked against the three new files.
  - FR-8 checked against the typesafe.py diff.
- NFR-1..NFR-8: conform.
  - NFR-6: the URLs are above every block, and the README doc rows carry the URLs and the retrieval date.
- INV-1..INV-30: conform, except INV-6 (R-C1) and INV-2's "every" clause (R-C5).
  - INV-5: `Api-Key` for Baseten only.
  - INV-8: `DecisionModelResponse` has no `__post_init__`, so no unwrapped ConfigurationError can escape.
  - INV-13: the 401 message names the env var through `get_api_key_env_var`.
  - INV-22: the run-id logic stays in TypeSafe only.
  - INV-27, INV-29 and INV-30: verified above.
- AC-1..AC-22: conform.
  - Every proof-cell test name exists and passes.
  - AC-1 was run directly.
  - The AC-16 proof cell still says "S009 340" while the current count is 349. That is a process-artifact staleness, not a finding.
- EC-1..EC-38: conform, except EC-6 (R-C1).
  - Probes confirmed EC-1, EC-2, EC-4, EC-20 and EC-24.
  - EC-34 holds as restated in r10: the registry raises the ownership error, the settings accept the pair, and the runner build refuses it.
- §12.3 rows 1-21: all implemented as specified. Row 13 carries R-C1, and row 15 carries R-C2. The only non-row file is the C010 lock, which §14 allows.
- §5 diagram vs actual call path: two divergences, both recorded.
  - Deviation 1: the URL comes from `ProviderModelRegistry.resolve_endpoint(provider, config.endpoint)`, not from `resolved_endpoint()`.
  - `SystemOneProvider` refuses managed configs both at construction and in `_config_for`.
- Deviations 1-9: all recorded in spec §17.
  - Deviation 1 is necessary (C017 blocks otherwise) and minimal (it is identical in direct mode, and the managed refusal closes the `vb_live_` leak).
  - Deviations 2, 3, 5, 6 and 8 are minimal.
  - Deviation 4 (extra helpers) is recorded but hides the depth problem (R-C2).
  - Deviation 7 was superseded by merge 7bfe29e8.
  - The §17 labels r5 and r11 against frontmatter 10 are not misleading.
- User's words (request.md §A plus the mid-run reply): all honoured.
  - Inception is used.
  - Seven more System One providers and the OpenAI decision model were added.
  - Gemini is deferred with a reason (no hosted decision model).
  - A first-party price URL sits in a comment above every decision row.
  - No scope creep beyond §12.3.

COMMANDS RUN:
- `git rev-parse --short HEAD` → `f23da1da`. `git diff --stat 9784a3f6 f23da1da` → only `docs/spec/decision-model-providers/pipeline.md`.
- `git diff origin/main...9784a3f6 --name-only -- . ':(exclude)docs' ':(exclude)tests'` → 22 paths (the 21 §12.3 rows plus `lint/pricebook_vintage_lock.json`).
- `git diff 76b0674d 9784a3f6 -- tests/features/decision_model_providers/ | wc -l` → `0`.
- `git diff <merge-base origin/main 9784a3f6> 9784a3f6 -- tests/ ':(exclude)tests/features/decision_model_providers' | wc -l` → `0`.
- `git diff origin/main...9784a3f6 -- lint/baseline.json | wc -l` → `0`.
- Added-line grep of the vidbyte and lint diff for noqa, type: ignore, nosec, TODO and NotImplementedError → no output.
- `git log origin/main..9784a3f6` (subject and body) → every vidbyte commit has spec IDs and the trailer, except docs commit b14b1674.
- Grep for the cloud sentence across vidbyte, tests, skills, lint, spec.md, test-plan.md, the commit log and the `gh pr view 697` body → absent.
- `gh pr view 697 --json state,isDraft,headRefOid` → `OPEN`, `true`, `9784a3f6...`.
- `python -m pytest tests/features/decision_model_providers -q` → `87 passed in 1.09s`.
- `python -m pytest tests/test_jev_agent.py ... tests/test_agent_settings_validation.py -q` (the briefing's area suite) → `406 passed in 2.73s`.
- `python lint/run.py` → `S009 IMPROVED 350 -> 349 ...` and `SDK-LINT: PASS` (exit 0). `python lint/run.py --rule C009 --all` → only MISTRAL (models.py:70). `--rule S014` → PASS.
- `python <scratchpad>/s4/run_snippet.py nokeys` → `ConfigurationError: Missing API key for provider perplexity. Pass api_key or set PERPLEXITY_API_KEY.`
- `python <scratchpad>/s4/run_snippet.py scripted` → `0.8`, `billing`, `(ModelProvider.PERPLEXITY, 'pplx-decider-v1.1-27b')`, `{'true': 0.8, 'false': 0.19999999999999996}`, `POST https://api.perplexity.ai/v1/decisions`, `POST https://api.openai.com/v1/decisions gpt-6-luna`.
- `python <scratchpad>/s4/probe1.py` → the four OpenRouter criteria lines quoted under R-C1.
- `python <scratchpad>/s4/probe2.py` → `inception/mercury-decide -> baseten`, `mercury-decide -> inception`, `(BASETEN,'mercury-decide') -> ConfigurationError: Model 'mercury-decide' is registered under provider 'inception', not 'baseten'.`, every new default is AUTO and priced except OpenRouter `{}`, and `_resolve_from_environment` → "No model providers have API keys configured".
- Inline Python config probe → EC-1 `UnsupportedProviderError: DecisionModelRunner supports: baseten, celeris, ..., zoodata.`, EC-2 `model must be non-empty.`, AC-8 `VIDBYTE_MANAGED decision mode is available only for provider typesafe.`, EC-24 `https://x.test/v1`, EC-4 `No default endpoint registered for provider 'foundry'. Pass endpoint explicitly with the provider's base URL.`, EC-20 `ProviderConfigurationError: SystemOneProvider has no System One host row for provider 'openai'; build its adapter with ModelProviders.decision().`, factory `{'typesafe': 'TypeSafeProvider', 'openai': 'OpenAIDecisionsProvider', 'vansa': 'SystemOneProvider', 'cloudflare': 'SystemOneProvider'}`.
- `ModelPricingRegistry.default().resolve(ModelProvider.OPENAI, "gpt-6-luna")` → `ModelPricing(input_per_million=0.1, output_per_million=0.0, ..., threshold_tokens=272000, input_over_threshold_per_million=0.2, output_over_threshold_per_million=0.0, threshold_inclusive=False, tier_rates=None)`.
- `grep -c <VAR> vidbyte/providers/README.md` for each registry env var → only `PERPLEXITY_API_KEY`, `VANSA_KEY` and `OPENAI_API_KEY` appear. `len(README)` → `52002`.
