---
slug: decision-model-providers
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-10 01:32
flags: none
---

# Request: Add more decision model providers beyond TypeSafe Jev

## A. Every user prompt in this conversation, verbatim and in order

_The pipeline was invoked cold with one argument string; there is exactly one prompt._

**Prompt 1** (the invoking prompt, passed as the argument to `/spec-pipeline`):

```
Can you take a look at the JevAgent inside of the vidbyte-sdk/, and then take a look at the actual decision model that we are using. i want to add more decision models that we offer besides just jev (there has been alot recently to copy what jev does, even at some of the frontier labs). Do some research, find out preferable like 10+ decision model providers that we can add; and then think through pricebook, api keys, and actual full-scope implementation of the different decision model providers. Also, can you try to run this request (just copy skill and what i said) using the "claude --cloude" command
```

## B. Handoff block and decision ledger (verbatim, if present)

none

## C. Structured conversation notes

### Key decisions
- **Target repository is `vidbyte-sdk`.** The user named "the JevAgent inside of the vidbyte-sdk/". The PR lands in the SDK only. The Vidbyte backend (`vidbyte/` repo, which hosts the managed decision gateway) is a different repository and is not changed by this PR.
- **The feature is: offer more decision model providers besides Jev.** Today the SDK's only decision model is TypeSafe's Jev. The user wants the SDK to support additional decision-model providers, selectable the same way Jev is selected today, with each provider's pricing ("pricebook"), credential resolution ("api keys"), and a real working adapter ("actual full-scope implementation").
- **Research is a required input, not an afterthought.** The user asked for research first ("Do some research, find out preferable like 10+ decision model providers that we can add"). A research scout captures that research at `docs/spec/decision-model-providers/context/provider-research.md` (absolute path given in every briefing). The spec author designs from that document plus the code; it does not redo the web research.
- **The last sentence of the prompt (run the request via `claude --cloud`) is NOT part of the feature.** It is an experiment the orchestrator runs outside the PR. No subagent acts on it. It must not appear in the spec, tests, or code.

### Rejected alternatives
- none stated by the user.

### Constraints and assumptions
- "10+" is the research target: the research document lists at least ten candidate providers with evidence. The user did not say every one of them must ship as a working adapter in this single PR; how many providers get a full adapter in this PR, versus being catalogued for a follow-up, is a design decision for the spec author (carry it as an `A-`/`Q-` item with a stated default). The user's phrase "actual full-scope implementation of the different decision model providers" weighs toward building real adapters rather than a stub catalog, so the default should be as many real adapters as fit the smallest complete design, with the rest listed in the spec as follow-ups.
- Today Jev is reachable in two connection modes: direct (`DecisionModelMode.TYPESAFE`, key from `TYPESAFE_API_KEY`) and Vidbyte-managed (`DecisionModelMode.VIDBYTE_MANAGED`, key from `VIDBYTE_API_KEY`, routed through the Vidbyte backend gateway). The managed mode requires the backend to proxy a provider. Because the backend is out of scope, the assumption is: **new providers ship in direct (own API key) mode only in this PR; the managed gateway stays TypeSafe-only**, recorded as a stated limitation and an optional `Q-n` (default: not built here).
- A "decision model" in this SDK is defined by what Jev does: a request carrying context plus a set of questions, answered with calibrated probabilities (boolean questions return P(true); score questions return a distribution over levels plus a weighted score; "noul" questions return a free answer with no confidence). The exact shapes live in `vidbyte/lib/dataclasses/jev.py` (`JevDecisionRequest`, `JevAnswer`, `JevModelCard`) and `vidbyte/lib/runners/types.py` (`DecisionModelResponse`). A new provider counts as a "decision model provider" only if it can honestly answer at least the boolean question kind with a probability; how a non-calibrated chat model is adapted (for example token log-probabilities over a yes/no answer, or a structured output carrying a self-reported confidence) is a design decision for the spec author, and the spec must say which answer kinds each provider supports and what happens for the ones it does not.
- Every decision call must keep being metered: `DecisionModelRunner.arun` records every call (and every billed failure) in the active usage ledger with `UsageKind.DECISION`. New providers must not bypass this.
- The SDK is alpha; APIs may change between minor versions (AGENTS.md). Still, `JevAgent` users today configure Jev through `JevRuntimeSettings`/`DecisionModelConfig`; existing configurations must keep working unchanged.

### Clarifications and answers
- none; the user could not be asked (the pipeline runs unattended). Everything below is the orchestrator's reading of the one prompt, to be verified by the scout and carried as `A-` items by the spec author.

### Terminology
- **Jev** — TypeSafe's calibrated decision-model family (docs: https://docs.typesafe.ai/api.md and https://docs.typesafe.ai/models.md). Also the name of the SDK agent (`JevAgent`, `vidbyte/agents/jev/`) that asks Jev preflight, done, and compute questions.
- **decision model** — a model that answers questions with calibrated probabilities rather than generating text; in the SDK, anything run through `DecisionModelRunner` (`vidbyte/lib/runners/decision.py`).
- **decision model provider** — an outbound adapter under `vidbyte/providers/` that `ModelProviders.decision(config)` (`vidbyte/providers/__init__.py`) selects for a `DecisionModelConfig`; today the only one is `TypeSafeProvider` (`vidbyte/providers/typesafe.py`).
- **pricebook** — the SDK's pricing data: the per-provider model token-rate tables in `vidbyte/lib/registries/pricing.py`, the per-provider usage parsers/pricers under `vidbyte/agents/pricing/` (`typesafe.py` prices Jev: input tokens at the table rate, output tokens free), and, for priced operations, `OPERATION_PRICING` in `vidbyte/lib/registries/operation_pricing.py` (governed by field-guide entry `operation-pricebook-rates.md` and lint rule C004). Cost math must stay inside `vidbyte/agents/pricing/` (lint rule C005, per the typesafe pricing header).
- **api keys** — per-provider credential resolution: the `ModelProvider` to environment-variable-name table in `vidbyte/lib/registries/models.py` (today `ModelProvider.TYPESAFE: "TYPESAFE_API_KEY"`), and the key resolution of `DecisionModelConfig` in `vidbyte/lib/dataclasses/model_configs.py` (direct mode resolves the provider key; managed mode resolves `VIDBYTE_API_KEY` and raises `ConfigurationError` with `VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND` when missing).
- **managed mode / Vidbyte gateway** — `DecisionModelMode.VIDBYTE_MANAGED`: calls go through the Vidbyte backend, grouped into a managed run (`vidbyte/lib/jev/managed.py`, header `X-Vidbyte-Run-Id`). Backend code is in the separate `vidbyte/` repository.

### Implementation hints
_Orientation facts gathered by the orchestrator from file headers only; the scout verifies each against the code and corrects what is wrong._
- Entry points that choose and run a decision model: `vidbyte/lib/runners/decision.py` (`DecisionModelRunner`: validates `DecisionModelConfig`, builds the adapter via `ModelProviders.decision`, runs `JevDecisionRequest`, lists models), `vidbyte/providers/__init__.py` (`ModelProviders.decision(config) -> TypeSafeProvider` at line ~88), `vidbyte/providers/typesafe.py` (wire shape both directions; `_TypeSafePayloadBuilder`, `_TypeSafeAnswerNormalizer`; 401 message names `TYPESAFE_API_KEY`).
- Config: `DecisionModelConfig` in `vidbyte/lib/config/models.py` / `vidbyte/lib/dataclasses/model_configs.py`; `DecisionModelMode` enum in `vidbyte/lib/enums/decision_model.py` (header: "Add a mode only when its credential source and endpoint policy are implemented together"); `JevRuntimeSettings` in `vidbyte/agents/jev/settings.py` defaults to managed mode while a standalone `DecisionModelConfig` defaults to TypeSafe direct.
- Provider enum and key table: `ModelProvider` with `usage_class` binding (see `vidbyte/agents/pricing/typesafe.py` header: "Bound to ModelProvider.TYPESAFE through ModelProvider.usage_class"); env var names in `vidbyte/lib/registries/models.py`.
- Pricing: `vidbyte/lib/registries/pricing.py` (rates), `vidbyte/agents/pricing/{base,records,tracker,typesafe,openai,anthropic,gemini,openrouter,compatible}.py` (usage parsing and pricing per provider).
- Usage ledger: `vidbyte/lib/usage_ledger.py` (`active_usage_ledger`, `record_call`, `record_billed_failure`), `vidbyte/lib/enums/usage.py` (`UsageKind.DECISION`).
- Shared question scoring for Jev lives in `vidbyte/lib/jev/decision.py` (`DecisionModelHelper`; `score_noul` needs no key).
- Existing non-decision adapters that show the repo's provider pattern: `vidbyte/providers/openai.py`, `anthropic.py`, `gemini.py`, `openrouter.py`, `xai.py`, `compatible.py` (OpenAI-compatible base), `base.py`, `client.py`, and `vidbyte/providers/README.md`. The embedding runner (`vidbyte/lib/runners/embedding.py`, `ModelProviders.embedding` returning `OpenAIProvider | GeminiProvider`) is the closest sibling of a multi-provider semantic runner.
- Placement rules that will bite: every new dataclass in `vidbyte/lib/dataclasses/<domain>.py`; every new enum in `vidbyte/lib/enums/<domain>.py` and exported from `vidbyte/lib/enums/__init__.py`; `vidbyte/lib/` never imports a higher layer; new Jev records go in `vidbyte/lib/dataclasses/jev.py`, enum members in `vidbyte/lib/enums/jev.py`, constants in `vidbyte/lib/constants/jev.py`; never create `types.py`/`enums.py`/`constants.py` under `vidbyte/agents/jev/` or `vidbyte/lib/jev/` (AGENTS.md "Placement Rules" and "New JEV code").
- `REPO_MAP.md` has a "JEV File Locations" table that must be updated when files are added (AGENTS.md "Repository Map").
- Field-guide entries that apply (index: `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/init.md`): `provider-api-contracts.md`, `operation-pricebook-rates.md`, `strict-config-dataclasses.md`, `blocking-lint-invariants.md`, `local-ci-verification.md`, `declarative-config-resolution.md`, `class-bound-helpers.md`, `jev-capability-layout.md`, `review-scope.md`.
- Gates: `python -m pip install -e ".[dev]"` once, `python lint/run.py`, `python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py` (full gate; semgrep included). Final lint line must read `AGENT-LINT: PASS`.
- Tests named by headers: `tests/test_jev_agent.py`, `tests/test_jev_managed_gateway.py`, `tests/test_jev_managed_runs.py`, `tests/test_jev_preflight.py`, `tests/test_jev_usage_ledger.py`, `tests/features/sdk_model_usage/FEATURE.md` (feature test packs exist in this repo).
- Things NOT to touch: the backend repository; existing tests' assertions; `lint/baseline.json`.

### Open questions
- Q: Which providers (from the research document) get a full adapter in this PR, and which are catalogued as follow-ups? — The spec author decides with the smallest complete design and states the default; the summary shows it to the user.
- Q: How is a chat/completions model turned into a calibrated boolean decision (log-probabilities over a constrained yes/no answer, a structured-output confidence field, or a provider-native classification endpoint)? Which answer kinds (boolean, score, noul) does each provider support, and what does the SDK do for an unsupported kind (raise a typed error, or degrade with a documented flag)?
- Q: Does the Vidbyte-managed mode extend to the new providers? — Default: no in this PR (backend out of scope); stated limitation plus optional `Q-n`.
- Q: Does `JevAgent` (preflight, done, compute questions) accept a non-Jev decision provider, or is the new provider surface only for direct `DecisionModelRunner` callers in this PR? — The user said "more decision models that we offer besides just jev", which reads as the SDK offering them wherever a decision model is configured; the spec author verifies what `JevRuntimeSettings` allows today and states the default.
- Q: Does the research document ship in the PR? — Yes: `docs/spec/<slug>/` is committed with the change, so `context/provider-research.md` is part of the PR's docs.
- Q: Pricing entries for providers whose pricing is per request rather than per token: does the pricebook support that shape today? — The scout checks `vidbyte/lib/registries/pricing.py` and `operation_pricing.py`.

## D. Weighted words

- "i want to add **more** decision models that we offer besides **just** jev" — Prompt 1 (the deliverable is plural providers, selectable alongside Jev, not a replacement of Jev).
- "find out preferable like **10+** decision model providers that we can add" — Prompt 1 (research target: at least ten candidates with evidence).
- "think through pricebook, api keys, and **actual full-scope** implementation of the different decision model providers" — Prompt 1 (each shipped provider is complete: pricing entry, credential resolution, working adapter, tests; no stubs).
- "take a look at the **actual** decision model that we are using" — Prompt 1 (the design is grounded in the real TypeSafe/Jev integration as it exists in code, not an imagined abstraction).
