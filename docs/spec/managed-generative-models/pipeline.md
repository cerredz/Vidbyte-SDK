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
| S1 spec + review | done | 2026-10-10 19:20 | 2026-10-11 01:10 | reports/S1-spec-review-2.md | spec r4 approved @ed9f098a; 2 review rounds + orchestrator r4 |
| S2 tests | done | 2026-10-11 01:12 (est.) | 2026-10-10 22:36 | reports/S2-test-author.md | 32 tests red (32 failed, orchestrator re-ran; no collection errors); area suites 69 passed; test commit 2eb7e3e5, proof 6069160f; S2_HEAD set at the status commit |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-10 18:08 — Ran the request as two linked pipelines (backend `vidbyte`, SDK `vidbyte-sdk`) — Prompt 5 names one change in each repo; one worktree cannot span two repos.
- 2026-10-10 18:08 — Unset the auto-configured upstream (`origin/main`) on the new feature branch — prevents a bare `git push` from targeting main; implementers push with `git push -u origin feat/managed-generative-models`.
- 2026-10-10 18:08 — Appended the assistant's four substantive answers verbatim to request.md as §E — the user's "great" in Prompt 5 accepts the §E.4 proposal, so downstream agents need its exact scope table.
- 2026-10-10 19:20 — Started this pipeline's S1 author against backend spec r1 in parallel with the backend review — most SDK design questions are independent of §9.2 details; §9.2 changes are forwarded as a revision.
- 2026-10-10 20:40 — Launched SDK review round 1 on r1 while backend r2 is still in revision — the reviewer is told which §9.2 changes are coming; the author applies reviewer findings and backend contract changes in one revision.
- 2026-10-10 22:45 — The reviewer was cut off by a usage-limit error and resumed with SendMessage; its report completed normally.
- 2026-10-10 22:45 — Holding the SDK revision until backend spec r3 lands, so the author absorbs reviewer findings plus backend §9.2 r2 and r3 changes in one revision.
- 2026-10-10 22:45 — Contract vendoring: re-vendor from the backend branch commit that regenerates the contract (C017-C020 check only repository, 40-hex commit, schema_version, generator). Backend origin/main mixes merge commits and squash merges, so if the backend PR is squash-merged the SDK must re-vendor from backend main afterwards; this is a stated merge-order note, not a gate.
- 2026-10-10 23:50 — Launched scoped review round 2 (last allowed) — r2 changed §8, §8.5, §9, §10 and the shape of §12 and absorbed the backend r3 contract.
- 2026-10-11 00:30 — Round-2 R-1: INV-10 rewording, an EC row, a README line and floor-first max() are in scope; changing DebateStageSettings or other agent timeouts outside vidbyte/lib/ is out of scope (stated limitation).
- 2026-10-11 00:55 — Resolved SDK Q-7 as YES (same-key transport retries in VidbyteGatewayTransport, only on 409/502/non-JSON answers) and withdrew NG-13 — request.md §C 'idempotent replay on retries' and §E.4 'SDK retries a timed-out call and you pay twice → Reuse existing, send the header', plus the settled mirror-Jev decision (Jev retries twice with one key). Applied as r4 without a third review round (cap 2 reached); S4 reviewers check it.
- 2026-10-11 01:10 — Q-n defaults applied (no user reply): Q-1 no key reuse across agent-runtime retries (outside lib; EC-14 limitation); Q-2 SDK-authored error messages only; Q-3 no direct-only mode; Q-4 key-crossing guards unchanged; Q-5 8,192 default cap for all six providers; Q-6 resolve_active unchanged; Q-8..Q-11 not built.
- S2 spot-check: re-ran 'PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text -q' -> '32 failed in 1.98s'; S2 spec diff touches only '| AC-n |' proof rows; S2 left its report uncommitted, orchestrator committed it.
- Test layout: spec §13 says flat test files; S2 used the repo's tests/features/sdk_* feature-pack convention (tests/features/sdk_managed_text/ with FEATURE.md and README.md). Accepted: the repo convention outranks the spec's description of layout (AGENTS.md > spec for HOW).
- EC-26 vs §9.2 (S2 open item): §9.2's failure-mapping rows are binding and 'the first match decides'. A FastAPI default 404 body {"detail":"Not Found"} is a non-2xx JSON object without top-level "error": true, so row 6 (relayed provider error, '<provider> returned HTTP 404 through the Vidbyte gateway', not billed) applies. EC-26's 'Vidbyte returned HTTP 404' column is illustrative; the binding fact is that the message carries HTTP 404. No new row is built. S3 records the EC-26 wording fix as a deviation in §17.
- Clock note: S0–S2 timestamps in this file were estimates ahead of the system clock (2026-10-10 22:35 at backend S3 close); later rows use date.

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
- r2: timeout floor 630.0 s (above backend 600 s total deadline); D-17 raise pattern: `except` saves locals, raise after the block, body decoded with `json.loads` in a narrow try (no `parse_json_response`), `__context__ is None`. — *source:* S1 author r2
- r2 phases: endpoint constant in row 15; P2 = rows 15, 6, 11, 12 in one commit with the contract copied from the backend branch row-20 commit, found with `git log -1 --format=%H feat/generative-model-gateway -- contracts/vidbyte-platform-contract.json` (backend worktree shares `C:/Users/422mi/vidbyte-repos/vidbyte/.git`); C020 ratchet in P1; §14 Ask-first if the row-20 commit is missing. — *source:* S1 author r2
- §9.2 failure order: inner ProviderRequestError -> other Exception -> not a JSON object (any status) -> 2xx success -> `"error": true` -> relayed; catches only `Exception`, never `BaseException`. §9.2 table: `*` marks fields allowed only as false/null. spec.md is CRLF in the working tree (autocrlf=true). — *source:* S1 author r2
- Agent timeouts that can cancel a managed call the gateway still bills: `DebateStageSettings.timeout_seconds = 120.0` (`vidbyte/context/algorithms/prosecutor_defender_judge.py:67`, enforced at `vidbyte/agents/algorithms/prosecutor_defender_judge.py:494`); `per_proposer_timeout`, `run_timeout_seconds`, `worker_timeout_seconds` default None (`lib/dataclasses/multi_agent.py:127,399,401`). — *source:* S1 reviewer round 2
- `lint/core/platform_contract.py:175` decodes the vendored contract as strict UTF-8; a BOM (PowerShell) makes C017-C020 ERRORED. S001 runs Ruff F (F401/F841): no unused `except ... as exc`; `os`/`re` in `model_configs.py` go after delegation. — *source:* S1 reviewer round 2
- SDK origin/main has moved past the base (`jev.py` 694 lines at base, 712 on origin/main); the SDK origin/main vendors contract copy b17222cd; backend main's 6dfc4d20 (agent-run routes) is not on the backend branch. mypy 2.3.1, Python 3.11.0 installed; C017 CLEAN today. — *source:* S1 reviewer round 2
- r4: `VidbyteGatewayTransport` owns the retry loop: up to 1 + `JEV_DEFAULT_RETRY_COUNT` (3) attempts with one `Idempotency-Key` and identical envelope; each attempt is one `inner.request` with `timeout_seconds` and `idempotency_key`, `retry_count` 0; waits `n × JEV_RETRY_BACKOFF_SECONDS` via `asyncio.sleep` (patch it in `vidbyte.lib.http.vidbyte_gateway`). Retries only 409, 502, non-JSON-object answers; never 401/402/403/413/422/429, JSON 500/503, or a missing response. — *source:* S1 author r4
- `HttpTransport.request` (`lib/http/transport.py:40-57`) retries only on `retry_status_codes`; a `RequestError` escapes on first failure; POST guard requires `idempotency_key` only when `retry_count > 0`. `JEV_DEFAULT_RETRY_COUNT = 2`, `JEV_RETRY_BACKOFF_SECONDS = 0.5`, `JEV_NO_RETRIES = 0` (`constants/jev.py:40-43`). — *source:* S1 author r4
- Retry-wait seam: vidbyte.lib.http.vidbyte_gateway.asyncio.sleep. The module must 'import asyncio'; 'from asyncio import sleep' breaks all 10 failure tests.
- Feature symbols are imported inside test functions so the suite collects before the feature exists; keep it that way.
- Error messages must contain the managed provider value and, when there is one, the status number (INV-11). Endpoint refusal must contain 'endpoint'; the streaming refusal must contain 'managed', 'TextModelRunner', '<PROVIDER>_API_KEY' and have details mode 'vidbyte_managed'.
- README section is found by a level-2..4 heading containing 'Vidbyte-managed' (or 'Vidbyte managed'); it must contain 2%, VIDBYTE_API_KEY, Idempotency-Key, maxOutputTokens, max_output_tokens, previous_response_id, 2,000,000, 8,192, 630, the six providers, stream, service tier and snake_case.
- unittest.TestCase reserves _outcome; never name a helper _outcome.
- SDK lint reads git ls-files: stage new files before running lint. Full lint takes about 1 minute. AC-14/AC-17 need the C020 count cut from 4 to 2.
- Backend contract to re-vendor at SDK P2: commit ceabda93ea8f782d0d91f897c05b0ee974f2c5a3 on feat/generative-model-gateway (pushed; PR cerredz/Vidbyte#672). It lists "models.generate" and "/api/v1/models/generate". Re-check before SDK S6 that no later backend commit changed contracts/.
