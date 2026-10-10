---
slug: managed-generative-models
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-managed-generative-models
branch: feat/managed-generative-models
base_commit: c07529316a5325bce986f84868ecbabb3b7f3056
pr:
until: none
started: 2026-10-10 18:10
---

# Pipeline: Vidbyte-managed mode for generative model calls (lib layer)

Linked run: this request spans two repos. The sibling pipeline is `generative-model-gateway in C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-generative-model-gateway`. The backend spec defines the HTTP wire contract; the SDK spec consumes it verbatim.

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-10 18:10 | 2026-10-10 18:24 | reports/S0-scout.md | base_commit c07529316 |
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-10 18:08 — Ran the request as two linked pipelines (backend `vidbyte`, SDK `vidbyte-sdk`) — Prompt 5 names one change in each repo; one worktree cannot span two repos.
- 2026-10-10 18:08 — Unset the auto-configured upstream (`origin/main`) on the new feature branch — prevents a bare `git push` from targeting main; implementers push with `git push -u origin feat/managed-generative-models`.
- 2026-10-10 18:08 — Appended the assistant's four substantive answers verbatim to request.md as §E — the user's "great" in Prompt 5 accepts the §E.4 proposal, so downstream agents need its exact scope table.

## User replies (verbatim)
- none yet

## Niche facts accumulated (carried into every later briefing)

- Lint C017 (baseline 0) requires every SDK call to a Vidbyte host to match a route in the vendored `lint/contracts/vidbyte-platform-contract.json` (generated in cerredz/Vidbyte by `scripts/generate-platform-contract.py`; lists only the 3 Jev model routes). The new gateway route must be added by re-vendoring the contract regenerated on the backend branch, which gives the SDK PR a merge-order dependency on the backend PR. â€” *source:* S0 scout
- If `TextModelConfig.resolved_endpoint()` returns a Vidbyte URL, C017 traces every adapter path (/responses, /messages, /models/{m}:generateContent, /chat/completions) as a Vidbyte request and treats `x-api-key` / `x-goog-api-key` as no credential. â€” *source:* S0 scout
- Host: the contract marks `api.vidbyte.pro` as `planned`, only `vidbyte-backend.onrender.com` is `live`; a new literal on the planned host regresses C018 (baseline 1). Deriving from the existing Jev gateway constant avoids a new literal (unverified whether C018 counts derived URLs). â€” *source:* S0 scout
- C020 needs one owner constant for the `vb_live_` prefix (none exists, e.g. `VIDBYTE_API_KEY_PREFIX` in `lib/constants/jev.py`); any new `vb_live_` literal, even in an error message, regresses C020. â€” *source:* S0 scout
- URL and auth-header composition happens in `vidbyte/providers/*` adapters, not in `vidbyte/lib/`; a lib-only change must work through what lib already controls (config resolution, transport, header helpers). â€” *source:* S0 scout
- `TextModelConfig.api_key` lacks `repr=False`; the class has no `__post_init__`; `TextModelRunner.arun` calls `dataclasses.replace` on every call (`vidbyte/lib/runners/text.py:36`). â€” *source:* S0 scout
- The transport's POST idempotency guard fires only when `retry_count > 0`; text adapters never pass an idempotency key; model retries live in `vidbyte/agents/runtime.py:607-690` (outside lib), so each retry is a fresh POST. â€” *source:* S0 scout
- Key-crossing guards (`agents/settings/fallback.py:147-155`, `agents/fork.py:85-95`, `agents/aggregation.py:331-349`) filter only explicit keys; an env-resolved `VIDBYTE_API_KEY` does not trip them; an explicit `vb_live_` key is dropped for a child on another provider. â€” *source:* S0 scout
- Text adapters' `parse_json_response` attaches `response_excerpt=response.body` (`vidbyte/lib/http/parser.py:18`); only the TypeSafe adapter has a managed path that never echoes the body. â€” *source:* S0 scout
- `tests/test_model_registry.py:57-61` does not clear the environment, so a developer's `VIDBYTE_API_KEY` changes its outcome once a key fall-through exists; lint S014 forbids a non-provider entry in `API_KEY_ENV_VARS`. â€” *source:* S0 scout
- C008 regresses on any new `_validate_*` helper copy; `vidbyte/lib/dataclasses/jev.py` must not import `model_configs` (import cycle via `ModalityDetector`). â€” *source:* S0 scout
- `tests/test_jev_managed_gateway.py:120,154,163` assert the api.vidbyte.pro URLs; Gemini puts the model only in the URL and reports usage under `usageMetadata`. â€” *source:* S0 scout
- AGENTS.md names only `python scripts/run_ci.py`; install/lint/pytest commands and the worktree `PYTHONPATH` step come from CONTRIBUTING.md, `lint/README.md`, `scripts/run_ci.py`, `pyproject.toml`, and the field guide (see code-map.md Â§1). â€” *source:* S0 scout
