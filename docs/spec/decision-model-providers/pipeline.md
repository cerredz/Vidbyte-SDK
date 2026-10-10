---
slug: decision-model-providers
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-decision-model-providers
branch: feat/decision-model-providers
base_commit: 278448b05155cb25b0a7fb667609256a496404b2
pr:
until: none
started: 2026-10-10 01:32
---

# Pipeline: Add more decision model providers beyond TypeSafe Jev

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-10 01:32 | 2026-10-10 02:45 | reports/S0-scout.md, reports/S0-research.md | base_commit 278448b0; context/code-map.md (244 lines); context/provider-research.md (473 lines, 32 catalog rows) |
| S1 spec + review | in progress | 2026-10-10 02:50 | | reports/S1-spec-author.md (spec r1 at ecf0c4b7; report at 9fb806b8); reviewer round 1 running | spec.md r1 (768 lines, 18 sections, 20 §12.3 rows, 3 new files, 6 new ModelProvider members) |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-10 01:33 — Ran a second S0 agent (a research scout) alongside the code scout, writing `context/provider-research.md` — the request explicitly asks for web research on 10+ providers, and a spec author should design from a sourced catalog rather than research on its own. Logged as a deviation from the playbook's "one scout".
- 2026-10-10 01:39 — Ran the user's `claude --cloud` sentence as an experiment outside the pipeline: vendored the spec-pipeline and agentic-engineering skills on scratch branch `cloud/spec-pipeline-trial-20261010` (pushed), launched from a console window because `--cloud` requires a TTY. Cloud session `session_01W6gqR6YGeAdCmaBqcvk4jw`. It is not part of this PR and no subagent acts on it.
- 2026-10-10 ~01:55 — Both S0 agents were terminated by the account's session usage limit (HTTP 429, reset 02:30). Resumed both with SendMessage after the reset; no artifact was lost (nothing had been written yet).
- 2026-10-10 02:45 — The request.md §C vocabulary "boolean / score / noul (free answer)" is wrong; both scouts independently corrected it to `JevQuestionType` = NOUL (yes/no, P(yes), no confidence) / CHOICE / SCORE. request.md is left verbatim as captured; the correction is carried in the niche facts below and in every briefing.

## User replies (verbatim)
- 2026-10-10 ~01:50 — "it says the session couldnt be found on the website" (about the cloud session; answered: CLI account is vidbyte4@vidbyte.pro in org Vidbyte; not a pipeline instruction)

## Niche facts accumulated (carried into every later briefing)
- `JevQuestionType` has only NOUL / CHOICE / SCORE; NOUL is the yes/no kind (`noul` = P(true), confidence must be None); CHOICE returns a probability per named option plus confidence; SCORE returns a probability per ordered level, a weighted `score`, a `legend`, and confidence. There is no free-answer kind. — *source:* S0 scout, S0 research
- `DECISION_SUPPORTED_PROVIDERS = {TYPESAFE}` at `vidbyte/lib/dataclasses/model_configs.py:336`; direct-mode key and endpoint already route through `ProviderModelRegistry`, but the mode is named `DecisionModelMode.TYPESAFE` and the default model is `jev-latest`. — *source:* S0 scout
- `JevRuntimeSettings.__post_init__` rejects any non-managed config and any subclass (`vidbyte/agents/jev/settings.py:274-279`), so JevAgent cannot see a direct-mode provider today regardless of vendor. — *source:* S0 scout
- Lint S014 (baseline 0) requires a new `ModelProvider` member to appear in `DEFAULT_PROVIDER_MODELS`, `API_KEY_ENV_VARS`, `DEFAULT_ENDPOINTS` and its default model in both runner maps in `vidbyte/lib/constants/runners.py`. — *source:* S0 scout
- Pricing is per-million-token only (`ModelPricing`); a provider without a `_usage_class_map` entry is counted as unaccounted, not priced (`vidbyte/agents/pricing/tracker.py:94-96`). `JevUsage` is hard-coded in ~30 JevAgent call sites. — *source:* S0 scout
- `git grep -i logprob` is empty: no adapter handles log-probabilities or a constrained yes/no answer today. — *source:* S0 scout
- Lint A006 (layering) is satisfied only via the call-time import in `_usage_class_map()`; a new adapter under `vidbyte/providers/` must not import `vidbyte.agents` at module level. Every new `.py` file needs the 7-field A001 header or A001 (baseline 643) regresses. — *source:* S0 scout
- Stale docs: `REPO_MAP.md:374`, `skills/jev-agent/SKILL.md:46`, `vidbyte/lib/jev/done/expert_depth.py:5` attribute `score_noul` to `DecisionModelRunner`; it lives on `DecisionModelHelper`. — *source:* S0 scout
- Gate commands (code-map.md §1): `python -m pip install -e ".[dev]"` once; `python lint/run.py` (focus `--rule <ID>`); `python scripts/run_ci.py --stage source`; `python scripts/run_ci.py` (full). `scripts/run_ci.py --stage {all,source,package}`. The literal final line `AGENT-LINT: PASS` is unverified in this repo (gates reference only). — *source:* S0 scout
- Research vocabulary of wire shapes (provider-research.md §4): (A) TypeSafe System One body, served by 9 hosted providers plus self-hosted models; (B) OpenAI Decisions body (`POST /v1/decisions`, also Vercel AI Gateway); (C) OpenAI-compatible chat log-probabilities (9 providers; Together/Fireworks legacy variant); (D) Gemini `logprobsResult`; (E) chosen-token-only; (F) structured output with self-reported confidence (weakest). — *source:* S0 research
- OpenAI Decisions renames noul to `predicate` (scalar `probability`), returns answers as an ordered array rather than a name-keyed map, encodes probabilities as arrays of `{value, probability}`, and adds a `refusal` answer type; its API-reference URL 404s, so limits and `usage` schema are unverified. — *source:* S0 research
- OpenRouter's decisions schema requires noul `criteria` with both `true` and `false` keys (TypeSafe makes criteria optional and the SDK omits them); OpenRouter also returns `usage.cost` in USD. — *source:* S0 research
- Non-Bearer auth: Anthropic `x-api-key`; Baseten decisions `Authorization: Api-Key`; Azure `api-key` header or Entra token; Microsoft Foundry sample uses Entra Bearer; Perplexity rejects `x-api-key` with 401; Cloudflare needs the account id in the path plus a token. — *source:* S0 research
- Log-probability caps: OpenAI/DeepSeek/Cerebras/Baseten/Novita/Nebius `top_logprobs` max 20; HF router 5; Fireworks 5 by default; Together's `logprobs` is an integer 0–20 with a legacy response shape; Gemini `responseLogprobs` (1–20) is deprecated for Gemini 3.x; xAI silently ignores logprobs on grok-4.20+; Groq and SambaNova do not support them. Score levels (≤10) fit under a cap of 20; 255 choice options do not. — *source:* S0 research
- Every qualifying provider prices per input token with output free or zero; no per-request pricing found. Cloudflare silently truncates `state` to a 65,536-token window; clef-flash is $0.038/M. — *source:* S0 research
- Renamed or deprecated in 2025–2026: Nebius AI Studio → Token Factory; Mistral Classifier Factory deprecated; Cohere `/v1/classify` deprecated 2025-09-15; Writer palmyra-x4/x5 deprecated 2026-12-14; DeepSeek pricing has peak/off-peak and cache tiers. — *source:* S0 research
- Perplexity Decisions: 10 rps/org, 1–128 questions, 1–255 options, 1–10 levels, < 262,144 input tokens, 504 after ~1 minute, `Retry-After` on 429; official price $0.02/M. — *source:* S0 research
- `ModalityDetector` treats the `gpt-` prefix as a TEXT model, so a `VERCEL` enum member defaulting to `openai/gpt-6-luna-decisions` would auto-activate as a text provider via `_resolve_from_environment`; the spec uses a README recipe (D-8) instead of a member. — *source:* S1 author
- `_catalog_name` strips to after the first `/`, so the Baseten default `inception/mercury-decide` needs the bare alias `mercury-decide` in `MODEL_RUNNER_TYPE_MAP` or `test_accepts_every_text_provider_default_model` fails (D-16). — *source:* S1 author
- `get_default_endpoint` already raises on falsy values, so `""` defaults for the tenant-scoped hosts (Cloudflare, Foundry) need only a message change (D-7). — *source:* S1 author
- `tests/test_jev_usage_ledger.py` patches `vidbyte.providers.typesafe.TypeSafeProvider.run_decision`; that import path and its keyword-only signature must survive the refactor (INV-24). — *source:* S1 author
- `gpt-6-luna` is absent from every text catalog at base, so a 0.0 output price cannot under-bill chat usage (A-16 / D-12). — *source:* S1 author
- Lint and semgrep scan tracked files only: run `git add -A` before `python lint/run.py` or the gate skips new files. — *source:* S1 author
