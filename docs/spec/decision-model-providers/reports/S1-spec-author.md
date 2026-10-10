# S1 — Spec author report

- **Spec:** `docs/spec/decision-model-providers/spec.md` (r1, 768 lines, all 18 sections §0–§17)
- **Commit:** `ecf0c4b7762cfd11b9ecf586bddc46f59f9716d5` on `feat/decision-model-providers` — `docs(spec): add decision-model-providers spec r1`
- **Base:** `278448b05155cb25b0a7fb667609256a496404b2` (worktree was at `b14b1674` with the S0 context before this commit)
- **Date:** 2026-10-10

## What the spec decides

- **Shape:** one adapter per *wire*, not per vendor. `vidbyte/providers/systemone.py` serves seven System One hosts (Perplexity, OpenRouter, Liquid, Baseten, meraGPT, Cloudflare, Microsoft Foundry) through frozen `SystemOneHost` rows; `vidbyte/providers/openai_decisions.py` serves OpenAI's `/v1/decisions` (and Vercel AI Gateway by endpoint override); `vidbyte/providers/decisions.py` holds the shared `DecisionHttpCall` and `DecisionFailures`. `typesafe.py` is rebuilt on the shared pieces and keeps only managed-gateway, `/models`, and run-close code. TypeSafe bodies, headers, and error strings must stay byte-identical (INV-23/24) so no existing test changes.
- **Catalog:** six new `ModelProvider` members (`PERPLEXITY`, `CLOUDFLARE`, `FOUNDRY`, `LIQUID`, `BASETEN`, `MERAGPT`), each registered in the three S014 parity maps, both runner catalogs, `PROVIDER_DEFAULT_RUNNER_TYPE_MAP`, and `_usage_class_map()` → `JevUsage`. OpenAI and OpenRouter are reused as decision providers (their text defaults untouched) via a new `ProviderModelRegistry.DECISION_DEFAULT_MODELS` map; `DECISION_SUPPORTED_PROVIDERS` derives from its keys (nine providers).
- **Config:** `DecisionModelConfig.model` becomes `str | None = None`, filled per provider in `__post_init__` (`object.__setattr__`, precedent `failure.py:95-106`); managed mode is rejected for non-TypeSafe providers; `validate()` resolves key *and* endpoint so tenant-scoped hosts (Cloudflare, Foundry — `""` default endpoints) fail at runner construction.
- **Pricebook:** verified rows only (Perplexity 0.02, Cloudflare clef 0.24 / clef-flash 0.038, Foundry 0.042, OpenAI `gpt-6-luna` 0.10 in / 0.0 out); Liquid, Baseten, meraGPT get empty blocks with dated comments; `PRICING_AS_OF = "2026-10-10"`. `OpenRouterUsage` learns the `input_tokens`/`output_tokens` shape.
- **Budget (§8.4):** 3 new files, 12 classes (4 relocated under public names, 8 new) + 6 enum members + 1 enum (`DecisionAuthScheme`), 0 dependencies, 6 env vars.
- **Phases:** P1 catalog → P2 shared plumbing + System One + TypeSafe refactor → P3 config + OpenAI adapter + factory → P4 docs.
- **Not built (stated):** managed gateway for new providers (NG-1/Q-1), `JevAgent` on other providers (NG-2/Q-2), `ModelProvider.VERCEL` (NG-9/Q-3), logprob-derived decisions (NG-3/Q-7), third-party prices (Q-4).

## Self-check (Stage E)

- All 18 sections present in template order; §0.1 reproduces the prompt verbatim minus the elided last sentence, with the elision noted; the forbidden phrase does not appear (`grep -- '--cloud'` → 0).
- FR-1…FR-16 trace to G-/request; W-1…W-8 trace to FR and AC (AC-1…AC-18 all claimed; AC-15 added to W-2); every EC-1…EC-26 names its guard; T-1…T-7 name where the control sits.
- Weighted words from request §D appear as INV-1 ("besides just jev"), INV-21 ("actual decision model"), NFR-8 ("actual full-scope implementation", "10+").
- §4 names verified against code: `DecisionModelResponse.answer()`, `vidbyte.lib.config.DecisionModelConfig`, `JevOption(name, description=None)`, `JevQuestionType`/`ModelProvider` exports, `DecisionModelRunner(config, *, transport)`.
- Names in §4, §8.5, §9.1, §12.3 match (`SystemOneHost`, `SystemOneRequest`, `SystemOneAnswers`, `SystemOneProvider`, `DecisionHttpCall`, `DecisionFailures`, `OpenAIDecisionsRequest`, `OpenAIDecisionsAnswers`, `OpenAIDecisionsProvider`, `OpenAIDecisionsWireQuestion`, `OpenAIDecisionsWireRequest`, `DecisionAuthScheme`, `DECISION_DEFAULT_MODELS`).
- `CREATE` rows in §12.3 = 3 = §8.4 new-file budget. Every §12.3 row names a governing standard. No test cases anywhere; §13 is facts only.
- §11 commands copied from `context/code-map.md` §1 / `CONTRIBUTING.md` / `lint/README.md`; not executed (gates are not run in S1).

## Niche facts the next stages need

- `ModalityDetector` prefix `gpt-` classifies `openai/gpt-6-luna-decisions` as TEXT; a `VERCEL` member with that default would be auto-activated as a text provider by `_resolve_from_environment` — the reason D-8 uses an endpoint-override recipe.
- Strict agent validation strips everything before the first `/` (`_catalog_name`), so Baseten's `inception/mercury-decide` default needs the bare alias `mercury-decide` in `MODEL_RUNNER_TYPE_MAP` (D-16) or `tests/test_agent_settings_validation.py::test_accepts_every_text_provider_default_model` fails.
- `ProviderModelRegistry.get_default_endpoint` already raises on a falsy value, which is what makes `""` defaults for Cloudflare/Foundry work (D-7).
- `tests/test_jev_usage_ledger.py` patches `vidbyte.providers.typesafe.TypeSafeProvider.run_decision`; that import path and keyword-only signature must survive the refactor (INV-24).
- `gpt-6-luna` is absent from every text catalog at base, so pricing output at 0.0 cannot under-bill chat (A-16, D-12).
- `.semgrep` and `lint/run.py` scan tracked files only — `git add -A` before running them.

## Open items

- Q-1…Q-8 are all non-blocking with default **no** (ship as specified). Q-8 (defer Foundry until auth/wire verified) is the one most likely to flip during implementation; A-3 records the fallback.
- A-1…A-16 are vendor-doc assumptions carried from `context/provider-research.md` §6; each names its blast radius.
- `docs/design/*.md` referenced by file headers were not opened (outside the allowed S1 reading set); S2 may want to confirm `jev-managed-gateway-credentials.md` does not constrain the `DecisionModelMode` docstring change.

## Revision r2

- **Commit:** `a8c16e18bcf1e27aae26cfa1682fe87a15c0d775` — `docs(spec): revise decision-model-providers spec r2 (S1 review round 1)`; spec now 792 lines, `revision: 2`, `status: draft` (round 2 pending).
- **Dispositions:** R-1, R-2, R-8 applied with change; R-3, R-4, R-6, R-7, R-9, R-10 applied; R-5 applied (option 1, move). None judged scope-adding; the one new knob the fixes could have implied (pricing Foundry deployments under other names) is carried as optional Q-9, default no.
- **R-1:** `DecisionModelConfig.resolved_model() -> str` added (row 9, §8.5, INV-2, FR-3, D-15); readers switched in rows 13 (`SystemOneRequest.build`), 15 (`OpenAIDecisionsRequest.build`), 17 (`decision.py:52,73`). `grep` shows `JevRuntimeSettings` reads no `.model`, so D-15's "five readers" became three. AC-16/NFR-2 now name S009 = 350. Row 9 moved P3 → P2 so the accessor exists before `systemone.py` calls it.
- **R-2:** `SystemOneHost.model_from_request: bool` (§8.5); §9.1 gained an "echoed `model` → `model_from_request`" column (TypeSafe, Perplexity = False; OpenRouter, Liquid, Baseten, meraGPT, Cloudflare, Foundry = True); INV-27, D-17, EC-27, EC-19 rewritten, AC-12 Given/Then extended, A-13 narrowed. Change from the reviewer's proposal: OpenAI also reports the request id, because research §3.1 documents only per-answer `name` echoes, not a response-level `model`. Foundry deployment-name limitation stated in §9.1 and README row 18.
- **R-5:** `DecisionAuthScheme` moved to `vidbyte/lib/enums/jev.py` (row 2; `REPO_MAP.md:372` and AGENTS.md "New JEV code"); row 3 uses the existing `vidbyte.lib.enums.jev` import block; new doc-only row 21 keeps the `DecisionModelMode` docstring change in `decision_model.py`; D-18 records why `DecisionModelMode` stays (placed by `docs/design/jev-managed-gateway-credentials.md`; the placement design note says legacy placements are not precedent).
- **R-7:** `SystemOneProvider._config_for` provider check (row 13, §8.5), INV-28, EC-28, AC-19 (claimed by W-5).
- **Other:** `SDK-LINT: PASS` (3 places); `_TypeSafeCallBuilder` pin in INV-24 and row 14; `DecisionFailures.unexpected(provider: ModelProvider)`; one `get_default_endpoint` sentence (EC-4, AC-7, FR-14, row 6); P1–P3 and dependency order rewritten; SKILL.md:47 everywhere with line 46 stated untouched; "Usage Key Divergence" rows in row 18, FR-15, §12.5.
- **Sections changed (for the scoped round 2):** frontmatter; §6.1 (INV-2, INV-24, new INV-27/28); §6.2 (AC-7, AC-12, AC-16, new AC-19); §6.3 (EC-4, EC-19, new EC-27/28); §7 (FR-3, FR-12, FR-14, FR-15, FR-16, NFR-2); §8.1 (D-15, new D-17/18); §8.2; §8.5; §9.1; §9.4; §11 (lint literal); §12.1 (W-5); §12.2; §12.3 (rows 2, 3, 5, 6, 9, 12, 13, 14, 15, 17, 18, 20, new 21); §12.4; §12.5; §12.6; §13; §15 (A-13, Q-6, new Q-9); §16; §17.
