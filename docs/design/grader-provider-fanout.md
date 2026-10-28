# Design Doc: The multi-provider grader spends only on the agent's own keys and grades on a priced model

**Status:** Draft · **Author:** Claude · **Created:** 2026-10-27 · **Last Updated:** 2026-10-27

## 1. Overview
`ContextWindow.preset.multi_provider_agentic_grader` runs one trial per provider, then a grader call. With no explicit
`provider_models`, `ProviderModelRegistry.resolve_active` picked providers from environment variables
(`_resolve_from_environment`) and ignored the agent's matched `api_keys`. So an agent given only an Anthropic key also
spent on Gemini and DeepSeek whenever their variables were exported. The default grader, `openai:gpt-4o`, has no price,
so the grader call was unmeasured, and it needed an OpenAI key the agent might not have. This change has two parts.
Trials come from the providers the agent's matched `api_keys` name. The grader defaults to the agent's own provider and
model, which its keys reach and which the spend cap already prices.

## 2. Goals & Non-Goals
**Goals:**
- With `api_keys` naming providers, trials run only on those providers.
- The default grader is the agent's own model.
- A partly configured grader is completed: a provider alone gets that provider's priced default model, and a model
  alone gets its catalogued provider, or the old `openai` provider.

**Non-Goals:**
- Agents with no matched provider keys still fall back to environment variables. That covers both no `api_keys` at all
  and only a Vidbyte key, and the behavior is unchanged.
- Spend-cap construction refusal for an explicitly configured but unpriced grader model.
- Extending lint C009. C009 checks registry default models, and after this change no algorithm hard-codes a model
  default, so there is nothing new for it to check.

## 3. Background
Reproduced offline by `repro_N1_grader_env_fanout.py`, which exits 1 on `origin/main` f0896962. That run sent requests
to Gemini and DeepSeek hosts for an Anthropic-only agent, and the grader resolved to an unpriced `gpt-4o`.

## 4. Requirements
1. `resolve_active(None, opts, api_keys=K)`: if `K.providers` is non-empty, return the text default model of each
   provider in `K.providers`, in `DEFAULT_PROVIDER_MODELS` order. Otherwise use the environment, as today.
2. `MultiProviderAgenticGraderAlgorithm()` has `grader_provider = grader_model = None`. The runtime then grades with
   `handle.provider` and the handle's model.
3. Setting `grader_provider` alone fills in `ProviderModelRegistry.default_model(provider)`. Setting `grader_model`
   alone fills in `provider_for_model(model)`, or `"openai"`. An explicit pair is unchanged.

## 5-6. Design
- `vidbyte/lib/registries/models.py`: `resolve_active` gains one branch that calls a new `_resolve_from_keys(api_keys)`.
- `vidbyte/context/algorithms/multi_provider_agentic_grader.py`: both fields become optional, and `__post_init__`
  completes a partial pair before it validates.
- `vidbyte/agents/algorithms/multi_provider_agentic_grader.py`: `_grader_identity(handle)` returns the configured pair,
  else the agent's provider and model (`AgentRuntime._speed_model_name`). `arun` passes that pair to `_run_grader` and
  to the result metadata.

## 7-8. Data Model / API Changes
`grader_provider` and `grader_model` are now `str | None` (default `None`). The behavior change: the preset's grader is
now the agent's own model instead of `openai:gpt-4o`.

## 9. File Change Manifest
| Action | File | Reason |
|---|---|---|
| MODIFY | `vidbyte/lib/registries/models.py` | Trials follow the matched keys |
| MODIFY | `vidbyte/context/algorithms/multi_provider_agentic_grader.py` | Optional grader identity |
| MODIFY | `vidbyte/agents/algorithms/multi_provider_agentic_grader.py` | Resolve the grader at run time |
| MODIFY | `tests/test_multi_provider_agentic_grader.py` | Regression tests |
| CREATE | `docs/design/grader-provider-fanout.md` | This doc |

## 10. Testing Plan
- `resolve_active` with Anthropic-only keys and Gemini/DeepSeek variables set returns only Anthropic. [Silent Failure]
- `resolve_active` with keys for two providers returns both. [Edge Case]
- `resolve_active` with a Vidbyte-only `ProviderKeys` still uses the environment. [Hidden Assumption]
- The default config has no grader identity, and the preset grades with the agent's own model. [Silent Failure]
- A provider-only config gets a priced default model. A model-only config gets the inferred provider, or `openai`.
  [Edge Case]
- Integration: a DIRECT Anthropic-only `Agent` with the preset, with Gemini/DeepSeek variables exported, contacts only
  `api.anthropic.com`, and every ledger call is priced. [Hidden Failure]
- Repro: on main it exits 1, and on this branch it exits 0.

## 11-12. Dependencies / Rollout
None. Gateway customers get the fix only after an SDK release and a backend pin bump. Rollback is a revert.

## 13. Open Questions
- [ ] When an agent holds only a Vidbyte key (AUTO), which providers should the grader fan out to? Today the
  environment decides, unchanged. I recommend requiring an explicit `provider_models` in that case.

## 14. Alternatives
- **Change the default grader string to a priced OpenAI model.** Rejected: an Anthropic-only agent still cannot reach
  OpenAI, so the run would fail after the trials had already spent.
