# S1 spec author report: managed-generative-models

- **Spec:** `docs/spec/managed-generative-models/spec.md`, r1, committed as `8ee7ed1e`.
- **Base:** `c07529316a5325bce986f84868ecbabb3b7f3056`.

## What I read

**Pipeline inputs**
- `docs/spec/managed-generative-models/request.md` (all of it).
- `docs/spec/managed-generative-models/context/code-map.md`.
- The backend spec `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-generative-model-gateway/docs/spec/generative-model-gateway/spec.md` (r1 at `263ed4e0e`), in particular §9.2, which is the wire contract, and §15. No other file under `docs/`.

**Repo rules**
- `AGENTS.md`, `REPO_MAP.md` (lib, constants, enums, errors and http sections).
- `vidbyte/lib/README.md`, `vidbyte/lib/registries/README.md`, `lint/contracts/README.md`.

**Code**
- `vidbyte/lib/dataclasses/model_configs.py` (TextModelConfig, DecisionModelConfig)
- `vidbyte/lib/registries/models.py` (resolve_api_key, resolve_endpoint, resolve_active, _resolve_from_environment)
- `vidbyte/lib/runners/text.py`, `vidbyte/lib/runners/streaming_text.py`, `vidbyte/lib/runners/utility.py` (build path)
- `vidbyte/lib/http/transport.py`, `vidbyte/lib/http/parser.py`, `vidbyte/lib/http/__init__.py`
- `vidbyte/lib/constants/jev.py`, `vidbyte/lib/enums/decision_model.py`, `vidbyte/lib/enums/model_provider.py`
- `vidbyte/lib/config/__init__.py`, `vidbyte/lib/errors/base.py`
- The adapters: `vidbyte/providers/openai.py`, `anthropic.py`, `gemini.py`, `compatible.py` (`run_text`, cap fields, `extra_body`)
- `vidbyte/providers/typesafe.py` (managed headers, failure mapping)
- `vidbyte/agents/base.py:_runner_for_model`
- `vidbyte/lib/registries/pricing.py`, for the priced default models

**Lint rules**
- `lint/rules/` A007, C008, C017 (with `lint/core/url_flow.py`), C020, S010, S012, S054.
- `lint/baseline.json`.

**Field guide**
- `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`: strict-config-dataclasses, provider-api-contracts, blocking-lint-invariants, local-ci-verification, class-bound-helpers.

**Tests**
- `tests/test_config_validation.py`, read to check that BYOK whitespace handling and missing-key behavior stay intact.

**Verification probe**
- I checked that mypy accepts the `HttpTransport.request` override shape. I wrote a replica in the scratchpad and ran `mypy 2.3.1 --strict --cache-dir=nul`; it printed "Success". Nothing was written in the worktree.

## Approaches weighed

1. **Transport decorator in lib http (chosen, D-1).**
   - `TextModelRunner` wraps its transport in `VidbyteGatewayTransport`.
   - The adapter builds its native body as usual. The decorator discards the adapter's URL and headers, wraps the body in `{provider, model, body}`, and POSTs it to the one route with the bearer key and an `Idempotency-Key`.
   - Zero adapter edits. Every change sits in `vidbyte/lib/`.
   - C017 traces the inner call to the constant URL, the same mechanism TypeSafe passes with.
2. **Endpoint redirect plus a header builder called by adapters** (request.md §E.2/E.3). Rejected, because the adapters append four suffixes:
   - it reaches four paths, not the 1 route;
   - C017 fails on non-contract paths;
   - it needs edits in `vidbyte/providers/`, outside lib.
3. **Fall-through inside `ProviderModelRegistry.resolve_api_key`** (request.md §E.2). Rejected. That method also serves the image, video, audio and embedding configs and direct-mode Decision, so `vb_live_` keys would reach vendors. The fall-through moved into two new classmethods instead.
4. **Content-addressed idempotency keys.** Rejected, because identical repeated prompts would replay a stale billed answer.
5. **Host.** I chose a new live-host literal (`vidbyte-backend.onrender.com`) over deriving it from the Jev constant (`api.vidbyte.pro`). Evidence:
   - C018's repair text says only live origins may appear.
   - The contract marks `api.vidbyte.pro` as `planned`.

## Disagreements with the scout or the request (with evidence)

- **Four routes versus one.** request.md §E.2–E.4 has "no adapter change to the URL logic" through suffix paths. That conflicts with Prompt 5's one route, and the user's prompt wins. Evidence: the adapter suffixes in `providers/openai.py:30`, `anthropic.py:25`, `gemini.py:27`, `compatible.py:32`.
- **"Adapters call one shared header builder"** (request.md §C, E.3 step 12). Under D-1 the adapters never address the gateway, so a builder they call would have no caller. I recorded "one shared header builder" as the single managed-header construction inside `VidbyteGatewayTransport` (D-3).
- **"`HttpTransport` refuses to retry a POST without an idempotency key"** (request.md §C). This holds only when `retry_count > 0` (`lib/http/transport.py:22-25`), and text adapters pass 0. The SDK sends a fresh key per request. Reusing a key across agent-runtime retries needs `agents/runtime.py`, so it became Q-1, default no.
- **Host `api.vidbyte.pro`** (request.md E.2/E.3). It is not live per the contract (`lint/contracts/vidbyte-platform-contract.json:207-208`), so D-4 uses the live Render host.
- **Key-crossing guards need relaxing** (request.md §E.3 step 11). They drop only an explicit key, so an environment `VIDBYTE_API_KEY` already works for children (code-map §4.10). They are unchanged; Q-4, default no.
- **Scout §4.9 risk on `tests/test_model_registry.py:57-61`.** Because `resolve_api_key` is untouched, that test stays valid on a machine with `VIDBYTE_API_KEY` set. Only text-config tests that do not clear the environment are affected; this is noted in §13.
- **The constant move** in request.md §E.2/E.3 step 9 (header names into a shared gateway module) is not needed and is out of scope (NG-8). The existing `JEV_IDEMPOTENCY_KEY_HEADER` is reused.

## Least-sure assumptions

1. **A-1: the backend contract may change.** The backend spec reviewer is still running. The decorator design survives any single-route contract, but the envelope keys, the discriminator and the provider list are consumed verbatim from r1.
2. **A-3: mypy acceptance of the override.** It is verified only on a replica, not through `lint/mypy.ini` / S009 on the real package.
3. **D-8 / A-6: an 8,192-token default cap for all six providers**, Anthropic included, where the BYOK default is 1,024. Output limits were not checked against vendor docs. A model whose output limit is below 8,192 returns a relayed 400 until the caller sets `max_output_tokens`.
4. **A-2: C017 tracing.** I believe the tracer evaluates the decorator's inner call with the constant URL and the `bearer_headers` + subscript header shape and judges it API_KEY-credentialed. This is from reading `lint/core/url_flow.py`, not from running it, because the contract cannot be re-vendored at S1.
5. **D-12: the placeholder key.** `resolved_api_key()` returns `"vidbyte-managed"` in managed state, which keeps the real key out of adapter-built headers. It is a new convention, and a reviewer could prefer another shape.
6. **EC-27: behavior change for Jev users.** Anyone who already has `VIDBYTE_API_KEY` set and no provider key used to get an error from text calls. They are now billed. This is intended by the request, but it is money-affecting.

## Addendum — revision round 1 (spec r2)

Inputs: `reports/S1-spec-review.md` (REVISE: R-1 Blocker, R-2..R-7 Major, R-8..R-14 Minor) and backend spec r3 at `a14b37e7e` (approved, final), with its author report's "§9.2 changes in r2/r3" and "SDK obligations that follow from r3". Status stays `draft`, because §8, §8.5, §9, §10 and the shape of §12 changed. Revision 2.

### Triage
- **All 14 findings accepted.** None rejected, none deferred to the user. The scope-adding parts became optional questions defaulting to not built: Q-8 (client-side `extra_body` checks, R-4), Q-9 (fall-through warning, R-6), Q-10 (refuse managed `cached_content`, R-7). Every disposition is in spec §16.
- **R-1:** floor 630.0 (D-9, INV-10, §8.5, §9.3). AC-9: 60/30/120/900 → 630/630/630/900.
- **R-2:** new D-17 binds the raise shape: record locals in `except`, raise after the block, `json.loads` in a narrow try, no `parse_json_response`. AC-11/12 assert `__context__ is None`.
- **R-3:** per the orchestrator. The endpoint constant is split into new row 15. P2 = rows 15, 6, 11, 12 in one commit, copied from the backend branch commit for backend §12.3 row 20. The C020 ratchet moves to P1. §15 has a merge-order note (squash-merge follow-up). No main or merge-base gate.
- **R-4 to R-7:** INV-9 scoped, plus EC-8 and AC-8 (c)(d). A §9.2 emitted-keys table plus AC-26 and A-14. EC-30 and the per-provider README rule. T-7 and EC-31.
- **R-8 to R-14:** the `HTTPStatus` 2xx test and S008/S002/S019 in §12.4. AC-17 corrected. Row 7 withdrawn. INV-14 narrowed, with the AC-21 reverse case. AC-25, EC-33, EC-34. Header inventories updated in rows 4 and 5. Citation and PowerShell fixes.

### Backend r3 contract changes beyond the findings
- A response that is not a JSON object, at any status, is an edge failure, classified before the 2xx and `"error": true` checks (INV-11, EC-15, AC-12).
- Strict model catalogue and the model pattern (EC-9, A-8).
- A relayed 429 or 400 can describe Vidbyte's own account (EC-32).
- 409 cannot arise, because every call sends a fresh key. Same-key retries stay unbuilt (NG-13, Q-7).
- The 600 s limit is a total deadline (D-9).
- D-8 and FR-5 no longer cite backend r1 Q-4/Q-5. They cite r3 §9.2.4 steps 4.6 and 11.

### Least-sure points in r2
1. **Edge-failure wording.** For a non-JSON answer, the message says the edge answered, the failure is usually transient, and Vidbyte may already have billed the call. Whether a billed 2xx can be replaced by an edge page is not stated by the backend. I kept the cautious "may have billed".
2. **Branch-commit lookup.** §12.5 finds the row-20 commit as the last commit on the local `feat/generative-model-gateway` branch that touched `contracts/vidbyte-platform-contract.json`. The backend worktree shares `C:/Users/422mi/vidbyte-repos/vidbyte/.git` (checked). If a later backend commit regenerates the contract again, the latest one is the right copy.
3. **A-14.** The emitted-keys table matches the r3 lists by reading. A drift in either repository is caught only by AC-26 on the SDK side, plus the backend's own tests.

## Addendum — revision round 2 (spec r3, final)

Input: `reports/S1-spec-review-2.md` (SOUND WITH FIXES: R-1 Major, R-2..R-4 Minor), plus the orchestrator's guidance. This is the last round. Status is `approved`, revision 3. All four findings are accepted, so nothing is disputed and no new blocking question exists. Spec §16 rows r2-1..r2-4 record the dispositions, together with two rows for the orchestrator's facts.

- **r2-1 (R-1):**
  - INV-10 now promises only that the SDK's own transport never times out before the gateway's 600 s deadline.
  - The floor comes first in `max(VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS, config.timeout_seconds)`, so a NaN timeout gives 630.0. This changed INV-10, D-9 and §8.5, and AC-9 gains a NaN case.
  - New EC-35 names the 120 s `DebateStageSettings` default, which is on by default, and the three opt-in multi-agent limits. Each was checked at its cited line.
  - The README line is in AC-18 and row 14, and §4 has one sentence.
  - Changing those agent timeouts is outside lib, so it became optional Q-11, not built.
- **r2-2 (R-2):**
  - The lookup is now `log -1 origin/main..feat/generative-model-gateway -- contracts/...`. Empty output means STOP.
  - A pre-copy check greps the commit's contract for `"models.generate"` and `"/api/v1/models/generate"`. Both values come from backend r3 §9.2.1, and backend §12.3 row 20 adds that route row. The vendored file's route rows use `{"name": …, "path": …}`.
  - The backend P1 row-5 regeneration, which adds only the error codes, fails this check.
  - §15 has a risk note on backend-main-only routes (`6dfc4d20`).
- **r2-3 (R-3):** row 5 gains a 413 reason, using `HTTPStatus.REQUEST_ENTITY_TOO_LARGE` because `constants/jev.py` has no 413 constant. Also added EC-36 and a README line.
- **r2-4 (R-4):** AC-26 now checks only top-level keys and direct `generationConfig` keys.
- **Orchestrator facts:**
  - §12.5 records that `platform_contract.py:175` decodes strict UTF-8, so a byte-order mark makes the rules report ERRORED.
  - S001 runs Ruff `F`. Row 5 now removes `os` and `re` outright (their only uses are `:398` and `:401`). The §9.2 raise-shape bullet, row 6 and §12.4 forbid an unused `except … as exc`.
  - §11 has a drift note and §14 an Always check (`jev.py` is 694 lines at the base and 712 on origin/main). D-7's line counts are updated.

Least sure: whether the backend generator keeps the `"name"` and `"path"` string tokens unchanged. The grep checks only the quoted values, so a whitespace change cannot break it.
