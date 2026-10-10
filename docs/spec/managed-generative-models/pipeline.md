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
| S1 spec + review | running | 2026-10-10 19:20 | | reports/S1-spec-review.md | r1 reviewed: REVISE (1B/6M/7m); revision waits for backend r3 contract |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 1/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-10 18:08 — Ran the request as two linked pipelines (backend `vidbyte`, SDK `vidbyte-sdk`) — Prompt 5 names one change in each repo; one worktree cannot span two repos.
- 2026-10-10 18:08 — Unset the auto-configured upstream (`origin/main`) on the new feature branch — prevents a bare `git push` from targeting main; implementers push with `git push -u origin feat/managed-generative-models`.
- 2026-10-10 18:08 — Appended the assistant's four substantive answers verbatim to request.md as §E — the user's "great" in Prompt 5 accepts the §E.4 proposal, so downstream agents need its exact scope table.
- 2026-10-10 19:20 — Started this pipeline's S1 author against backend spec r1 in parallel with the backend review — most SDK design questions are independent of §9.2 details; §9.2 changes are forwarded as a revision.
- 2026-10-10 20:40 — Launched SDK review round 1 on r1 while backend r2 is still in revision — the reviewer is told which §9.2 changes are coming; the author applies reviewer findings and backend contract changes in one revision.
- 2026-10-10 22:45 — The reviewer was cut off by a usage-limit error and resumed with SendMessage; its report completed normally.
- 2026-10-10 22:45 — Holding the SDK revision until backend spec r3 lands, so the author absorbs reviewer findings plus backend §9.2 r2 and r3 changes in one revision.
- 2026-10-10 22:45 — Contract vendoring: re-vendor from the backend branch commit that regenerates the contract (C017-C020 check only repository, 40-hex commit, schema_version, generator). Backend origin/main mixes merge commits and squash merges, so if the backend PR is squash-merged the SDK must re-vendor from backend main afterwards; this is a stated merge-order note, not a gate.

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
- SDK design D-1: `VidbyteGatewayTransport(HttpTransport)` in `vidbyte/lib/http/vidbyte_gateway.py`, wrapped around the transport by `TextModelRunner` in managed state; discards the adapter URL and headers; sends `{provider, model, body}` with bearer key and uuid4 `Idempotency-Key`; zero adapter edits. — *source:* S1 author
- The gateway wrapper must be built inside async `arun`; passing `self._transport` from a sync method trips S010 (baseline 5). Copying `HttpTransport.request` numeric defaults adds A007 findings; use `timeout_seconds: float = VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS` plus `**transport_options: object`. — *source:* S1 author
- Build headers as `bearer_headers(key)` then `headers[JEV_IDEMPOTENCY_KEY_HEADER] = ...` (the TypeSafe shape C017 accepts); pass `timeout_seconds` on the inner call (S012). No new `vb_live_` literal anywhere (C020): f-strings from `VIDBYTE_API_KEY_PREFIX`; Decision messages stay byte-identical. — *source:* S1 author
- Re-vendoring the contract: use Git Bash, not PowerShell (`>` re-encodes bytes); the backend repo is `C:/Users/422mi/vidbyte-repos/vidbyte` (not `../vidbyte` relative to the worktree). — *source:* S1 author
- Tests inject the transport via `TextModelRunner(..., transport=fake)`; for the agent path patch `vidbyte.lib.runners.text.HttpTransport`. `TextModelConfig.__post_init__` re-runs on every `arun` (`replace`), so AUTO mode must not read the environment there. — *source:* S1 author
- `lint/core/platform_contract.py` checks only `source.repository`, a 40-hex `source.commit`, `schema_version`, `generator`; a contract copied from a backend branch passes C017-C020. C017 also flags Vidbyte URL literals no traced request uses, so an endpoint constant without a request is red. — *source:* S1 reviewer
- `raise ... from None` inside `except` still sets `__context__`, so the gateway body stays reachable via `__context__.response_excerpt`; raise after leaving the except block. — *source:* S1 reviewer
- `extra_body` merges last: in Gemini it replaces the whole `generationConfig` (cap included); in chat dialects `max_completion_tokens` can sit beside an injected `max_tokens`. Gemini runner metadata becomes top-level `labels` (`gemini.py:164`); OpenAI forwards non-function tools unchanged (`openai.py:225-231`). — *source:* S1 reviewer
- No 2xx constant exists; `HTTPStatus.OK <= s < HTTPStatus.MULTIPLE_CHOICES` avoids an A007 literal. `TextModelRunner` is built at `vidbyte/lib/runners/utility.py:72-74`. `tests/test_config_validation.py:24-29` asserts only the error type. — *source:* S1 reviewer
