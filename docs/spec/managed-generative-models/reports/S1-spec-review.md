# S1 spec review — managed-generative-models (spec r1)

Reviewed: `docs/spec/managed-generative-models/spec.md` r1 against the worktree at HEAD `2cf287db` (base `c07529316a5325bce986f84868ecbabb3b7f3056`), request.md, context/code-map.md, AGENTS.md, the field guide, house style and the template. Wire contract: backend spec r1 §9.2 (`263ed4e0e`), re-checked against backend r2 (`0e397290b`) and its "§9.2 changes in r2" addendum. Lenses L1–L11.

VERDICT: REVISE — 1 Blocker, 6 Major, 7 Minor. The D-1 design (transport decorator, lib-only, one route) is sound and verified. The spec is pinned to backend r1, and r2 has already changed three things the SDK depends on: the upstream timeout, the 422 refusal set, and the always-required cap. The fixes are constants, AC rows, one raise shape, phase order and README text. No settled decision has to be reversed.

## WHAT THE SPEC GETS RIGHT

- **D-1 holds.** Every package text path ends in `TextModelRunner.arun`: agents go through `Runner.build` (`lib/runners/utility.py:72-74`), and `agents/base.py:1444-1457` passes only `timeout_seconds`. The four adapters add four different path suffixes, so the §8.3 rejection of an endpoint-only redirect is correct. Managed routing really is one decorator with zero adapter edits.
- **D-5 is the right cut.** `resolve_api_key` stays untouched, so image, video, audio and embedding configs can never send a `vb_live_` key to a vendor (INV-18). Because the provider env var wins before `VIDBYTE_API_KEY` (EC-1), nobody is billed for a provider whose key they hold.
- **D-14 delegation preserves behavior.** `DecisionModelConfig.resolved_api_key` (`model_configs.py:394-403`) strips the explicit key, falls back to `VIDBYTE_API_KEY`, strips again, and uses the same two messages and `error_kind` that `resolve_vidbyte_api_key` is specified to produce. C020 falls to exactly 2 (`providers/typesafe.py:255,271`).
- **The key fails closed everywhere.** `resolved_api_key()` returns the placeholder (D-12), unmanaged providers are refused before any send (EC-3), the key is hidden from repr, and messages are written by the SDK and keyed on the `"error": true` discriminator. Backend r2 §9.2.5–9.2.6 confirms that the gatekeeper's own 401/403/429/503 bodies also carry `"error": true`, so the gateway-versus-relayed split is correct.

## FINDINGS

### R-1 [Blocker] [L5] §6.1 INV-10, §8.1 D-9, §8.5, §9.3, AC-9, EC-14, EC-20, AC-18 — The 90 s timeout floor is below backend r2's 600 s upstream timeout

**Evidence.**
- The spec sets `VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS = 90.0` with the flip condition "The backend timeout changes" (D-9).
- AC-9 expects 90/90/120, and EC-14 says "The 90 s floor closes the 60 s timeout race".
- Backend r2 §9.2.4 step 11 (`spec.md:670` at `0e397290b`) says: "**The SDK's managed client timeout for this route must exceed 600 s** (e.g. 630 s). Otherwise the SDK abandons a call the gateway may still complete and bill."
- Backend r2 D-21 sets `MODEL_GATEWAY_GENERATIVE_TIMEOUT_SECONDS = 600.0`. INV-22 sets the pending claim to 660 s. The addendum repeats both under "SDK obligations".
- `HttpTransport` turns an httpx timeout into `ProviderRequestError(provider="http")` (`lib/http/transport.py`).

**Failure.** Take any managed generation that runs between 90 s and 600 s, which is common for reasoning models with the 8,192 default cap. The SDK raises "no response arrived" at 90 s. The gateway finishes the call and bills the 2xx at cost plus 2%, so the developer pays for an answer they never receive. If the agent's RETRY middleware is on, it sends a new POST with a new `Idempotency-Key`, and that second call is paid as well. The backend has explicitly made this an SDK obligation. D-9's flip condition has already fired.

**Smallest fix.**
- Set the constant to `630.0`, with the comment "backend generative upstream timeout 600 s + 30 s".
- Keep `max(timeout_seconds, floor)`.
- Change AC-9 to 60/30/120 → 630/630/630, and add a case where 900 → 900.
- Rewrite EC-14 and EC-20 around the 630 s figure.
- AC-18 and the README must say that a managed call can wait up to 10.5 minutes.
- Rebase A-1 to backend r2 `0e397290b`, and to r3 once it lands.

### R-2 [Major] [L9/L10] §6.1 INV-11, AC-10, §9.2 failure mapping, §12.3 row 6 — `from None` does not clear `__context__`, so AC-10 cannot pass with the prescribed shape and the gateway body stays reachable

**Evidence.**
- INV-11 says the error is "raised with `__cause__` and `__context__` suppressed (`from None`)". AC-10 asserts both "are `None`".
- Row 6 says to "check the result with `parse_json_response`". That function raises `ProviderRequestError(..., response_excerpt=response.body)` for a non-2xx status, invalid JSON, or a non-object body (`lib/http/parser.py:18,30,32`). The decorator therefore raises its own error from inside an `except` block.
- Run locally: `raise E(...) from None` inside `except ValueError` leaves `e.__context__ == ValueError('body')`, with only `__suppress_context__ = True`.
- The cited precedent, `providers/typesafe.py:432`, uses the same inside-except shape.

**Failure.** An implementer who follows the spec and the precedent fails the S2 test written from AC-10, and may then be tempted to weaken the test. Worse, `err.__context__.response_excerpt` holds the full gateway or provider body. Any consumer that walks `__context__` without honoring `__suppress_context__` (custom loggers, trace serializers, error trackers) can print it. INV-6 promises that no `response_excerpt` "raised by managed mode" carries body text.

**Smallest fix.** Bind the raise shape in §9.2:
- In the `except` block, copy only `status_code` and the classification into locals.
- Leave the `except` block, then raise. B904/S002 does not apply outside an `except` block.
- Read the `"error": true` discriminator with `json.loads(response.body)` inside its own narrow try, which also exits before the raise.
- Keep AC-10 as written, and add the `__context__ is None` assertion to AC-11 and AC-12.

### R-3 [Major] [L11] §9.4 "Cross-repo order", §12.5, §12.6, §14, AC-17 — C017 goes red at P1, and a branch copy of the contract passes every SDK gate, so "not ready until re-vendored from main" is not enforced

**Evidence.**
- `lint/rules/c017_platform_route_contract.py` PURPOSE says C017 flags "Vidbyte API URL literals that no traced request uses" (`untraced-url`).
- Row 3 (P1) adds `VIDBYTE_GENERATIVE_GATEWAY_ENDPOINT`, and no request uses it until row 6 (P2). After that it is `unknown-route` until row 11 (P4).
- §12.6 says the problem lasts from P3 until P4. §14 says to stop BLOCKED if "C017 still fails".
- `lint/core/platform_contract.py` checks only `source.repository`, a 40-hex `source.commit`, `schema_version` and `generator`. Nothing checks that the commit is on backend `main`.
- The §12.6 sentence "may not be marked ready until row 11 is re-done from `main`" is prose only. The backend is now at r2 and moving to r3, so the route can still change.

**Failure.** Per-phase gate runs fail from P1, which conflicts with the §14 stop rule. Separately, a PR that carries a backend-branch contract can merge green. If r3 changes the route, or the backend PR merges late or never, SDK `main` ships a contract that backend `main` does not have. The next routine re-vendor then makes C017 fail on unrelated PRs, and requests reach a host that answers 404 (EC-26).

**Smallest fix.**
- Move a provisional re-vendor (rows 11–12) into P1, taken from the backend branch commit that regenerates the contract. Record that commit plus "PROVISIONAL" in the Provenance row.
- Correct the §12.6 annotations: C017 is green from P1 when the provisional copy is in place, and red otherwise.
- Add a binding pre-ready step to §12.5 and §14, all three of which must hold:
  - re-vendor from `origin/main`;
  - the blob matches (the §12.5 command);
  - `git -C C:/Users/422mi/vidbyte-repos/vidbyte merge-base --is-ancestor <provenance commit> origin/main` succeeds.
- The SDK merges only after the backend is deployed to the onrender host.

### R-4 [Major] [L5] §6.1 INV-9, AC-8, EC-8, §9.2 cap table — `extra_body` is merged last, so it can drop or contradict the injected cap

**Evidence.** Every adapter merges with `payload.update(dict(config.extra_body))`:
- Gemini `gemini.py:166-167` replaces the whole `generationConfig` that was built at `:126-143`, where `maxOutputTokens` is set at `:133`.
- Compatible `compatible.py:74` sets `max_tokens`, then merges at `:120-121`.
- OpenAI sets the cap at `openai.py:213-214`, then merges later.

On the backend side:
- r2 AC-6 and EC-3 refuse a missing cap with 422. The addendum says "an output cap is always required".
- r2 EC-5 prices the largest of `max_tokens` and `max_completion_tokens`.
- The SDK's INV-9 says "Every managed request carries the dialect's output-token cap". AC-8 tests only the unset and explicit `max_output_tokens` cases.

**Failure.**
- (a) A Gemini user passes `extra_body={"generationConfig": {...}}`, the only way to set Gemini options that `TextModelConfig` lacks. The body then has no `maxOutputTokens`, and every call gets a 422. The SDK message cannot say which rule fired (D-11).
- (b) A chat-dialect user (xAI, DeepSeek or Kimi) passes `extra_body={"max_completion_tokens": 2000}`. The body then carries `max_tokens: 8192` as well, so the gateway admits and holds against 8,192 tokens. That causes spurious 402/429 answers, and some vendors reject both fields together.

**Smallest fix.**
- Scope INV-9: the cap is guaranteed unless `extra_body` supplies or replaces the dialect's cap container.
- Add both cases to EC-8 and AC-8 with their outcomes.
- State in the README: under managed mode, a `generationConfig` passed in `extra_body` must include `maxOutputTokens`, and chat-dialect caps belong in `max_output_tokens`, not in `extra_body`.
- Optional `[scope-adding]` Q-8: refuse these collisions in `validate()` in managed state.

### R-5 [Major] [L5/L11] §9.2 failure mapping, §6.3, AC-18, §15 A-1 — Backend r2's unpriced-feature refusals and r3's planned per-dialect top-level allowlist are missing; the 422 guidance is wrong, and nothing lists what the adapters emit

**Evidence.** Backend r2 §9.2.4 step 4.4 (addendum) answers 422 `model_gateway_unbillable_request` to:
- a non-function tool;
- a non-standard `service_tier`;
- Anthropic `cache_control.ttl` other than `5m`;
- Gemini tools other than `functionDeclarations`, or non-text `responseModalities`;
- xAI `search_parameters`;
- Kimi `builtin_function`.

r3 is expected to replace this with an allowlist of top-level body fields per dialect.

On the SDK side:
- `openai.py:225-231` forwards any non-function tool unchanged (`tools.append(dict(tool))`), and all adapters merge `extra_body` last.
- The spec's 422 reason covers only "not managed or priced… streaming, a missing or invalid output-token limit, or a body model that differs".

Top-level keys the adapters can emit, found by grep:

| Adapter | Top-level keys |
|---|---|
| openai | `model`, `input`, `instructions`, `temperature`, `top_p`, `max_output_tokens`, `tools`, `tool_choice`, `text`, `metadata` |
| anthropic | `model`, `messages`, `max_tokens`, `system`, `temperature`, `top_p`, `stop_sequences`, `tools`, `tool_choice`, `thinking`, `metadata`, `output_config` |
| gemini | `contents`, `systemInstruction`, `generationConfig`, `tools`, `toolConfig`, `safetySettings`, `cachedContent`, `labels` (built from runner metadata, `gemini.py:164`) |
| compatible (xai, deepseek, kimi) | `model`, `messages`, `temperature`, `top_p`, `max_tokens`, `stop`, `tools`, `tool_choice`, `response_format`, `metadata` |

The spec records none of these.

**Failure.**
- (a) A user who adds `{"type": "web_search"}` is told the problem is streaming, the cap or the model. The `code` is withheld (D-11), so the error cannot be diagnosed.
- (b) Suppose the r3 allowlist omits a key the SDK emits on its own, for example Gemini `labels` (sent whenever run metadata is non-empty), Anthropic `output_config` (`response_format`), or OpenAI `text`/`metadata`. Then every managed call that uses that feature gets a 422. No SDK AC catches it, because the S2 tests use scripted transports.

**Smallest fix.**
- Add the table above to §9.2 as "keys the SDK emits per dialect".
- Add an assumption: "backend r3 allowlist ⊇ this table; if not, revise the spec".
- Send the table to the backend r3 author.
- Widen the 422 reason to include "a hosted (non-function) tool, a non-standard service tier or another unpriced feature, or a body field the gateway does not accept".
- In the README (AC-18), state that hosted tools, non-standard tiers and unknown `extra_body` fields are refused.
- Also rebase these r1 details to r2:
  - Gemini bodies may carry no `model` at all, so update D-2 and the EC-8 example.
  - 402 now always means the caller's wallet.
  - 502 is ambiguous, per the r2 §9.2.6 note.

### R-6 [Major] [L5/L1] §6.3 EC-1/EC-27, §9.4, §15 Q-3 — A BYOK user who also has `VIDBYTE_API_KEY` set is silently billed for every managed provider they hold no key for

**Evidence.**
- INV-4 step 3 is evaluated per provider.
- EC-1 covers only a provider whose key is set, and EC-27 covers only "no provider key" at all.
- Q-3's default rationale, "AUTO plus a provider key already keeps BYOK (EC-1)", holds only for that one provider.
- Calls to a second provider happen without the user writing them:
  - fallback children (`agents/fallback.py:162`; the guard at `agents/settings/fallback.py:147-155` drops the explicit key, so the child resolves through the environment);
  - fork (`agents/fork.py:85-95`);
  - aggregation (`agents/aggregation.py:331-349`);
  - utility runners built through `Runner.build`.
- `VIDBYTE_API_KEY` is the existing JevAgent variable, so Jev users already have it set.

**Failure.** Take a Jev user with `OPENAI_API_KEY` set and an Anthropic fallback, but no `ANTHROPIC_API_KEY`. At `base_commit` the fallback fails with "Missing API key". After this PR it runs silently on Vidbyte's bill at cost plus 2%. The only opt-out, unsetting `VIDBYTE_API_KEY`, breaks their Jev calls. The README states the fee, but not this per-provider rule.

**Smallest fix.**
- Add an EC row for this mixed case.
- State the per-provider rule in AC-18 and the README: "BYOK applies per provider. With `VIDBYTE_API_KEY` set, any managed provider without its own key is billed through Vidbyte."
- Correct Q-3's rationale.
- Optional `[scope-adding]` Q-9: emit a one-time warning when step 3 is selected while another provider key is set.
- The settled key fall-through stays as it is.

### R-7 [Major] [L7] §10, AC-18 — Provider-side state held under Vidbyte's shared provider accounts is missing from the threat model and the README

**Evidence.**
- Backend r2 EC-41: "Tenant B sends tenant A's OpenAI `resp_…` id as `previous_response_id` | OpenAI loads A's stored conversation under Vidbyte's org key … Accepted limitation (Q-8)".
- Backend r2 NG-18: `store: false` is not forced.
- Backend r2 EC-24 lists `previous_response_id`, `conversation` and `cachedContent`.
- `TextModelConfig.cached_content` is a first-class field (`model_configs.py:61`), sent as Gemini `cachedContent` (`gemini.py:159-160`). `extra_body` can add `previous_response_id` or `store`.
- SDK §10 T-1–T-6 and the AC-18 README list say nothing about any of this.

**Failure.**
- Managed OpenAI prompts and answers are stored by default in Vidbyte's organization, not the developer's.
- Someone holding a leaked response id can load another tenant's context.
- A managed `cached_content` names a cache in Vidbyte's Gemini project. The developer's own caches stop working, and another tenant's cache becomes usable if its name leaks.
- The developer is told none of this.

**Smallest fix.**
- Add a T-7 row that cites backend EC-41/Q-8 as an accepted limitation enforced server-side.
- Add an EC row for managed `cached_content`.
- Add a README line (AC-18): "managed calls run under Vidbyte's provider accounts; provider-side stored state lives there".
- Optional `[scope-adding]` Q-10: refuse `cached_content` in managed state.

### R-8 [Minor] [L8] §9.2 "no 2xx literal is added", §8.4, §12.4 — The failure mapping needs a 2xx test and many branches; the spec claims it needs no literal and leaves out S008

**Evidence.**
- `parse_json_response` raises the same `ProviderRequestError` for a non-2xx status (`parser.py:16-18`) and for a 2xx body that is non-JSON or not an object (`:30,:32`).
- To tell row 2 (unreadable 2xx) from rows 3–4, the decorator must test the 2xx range. The only existing test is the literal `200`/`300` at `parser.py:16`, and no 2xx constant exists in `lib/constants` (grep).
- The mapping has at least 9 outcomes. `managed_failure_reason` already has 7 ifs.
- S008 is ruff C901 (default 10), PLR0912 (12) and PLR0915, with a baseline of 19. §12.4 does not list it.

**Failure.**
- Writing `200 <= status < 300` makes A007 REGRESSED.
- Adding a 9th constant exceeds the §8.4 budget, so the implementer must stop BLOCKED.
- One large classifier function makes S008 REGRESSED.

**Smallest fix.**
- Allow `HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES` (stdlib enum members, not numeric literals) in §9.2.
- Add S008 to §12.4, with a split between classification (transport, unreadable, gateway, relayed) and a status-to-reason lookup.

### R-9 [Minor] [L9] AC-17 versus NFR-5 and §11 — AC-17 says C018 stays at 0, but the baseline is 1

**Evidence.**
- `lint/baseline.json` has C018 = 1, the Jev `api.vidbyte.pro` constant. NFR-5 and §11 say 1.
- AC-17 says "C017, C018 and C019 stay at 0".

**Failure.** A test or verifier written from AC-17 fails on a correct tree.

**Smallest fix.** Change AC-17 to "C017 0, C018 1, C019 0, C020 2".

### R-10 [Minor] [L2] §8.4, §9.2 surface table, §12.3 row 7 — `VidbyteGatewayTransport` is exported publicly even though it "trusts its constructor inputs"

**Evidence.**
- The §9.2 row says it trusts its inputs.
- It silently discards the `method`, `url` and `headers` it is given (§8.5).
- AGENTS.md style 4 requires validation at the boundary.

**Failure.** A class that sends any caller-supplied string as a Vidbyte bearer, and ignores the URL it was handed, becomes supported public API. That is surprising for anyone who wraps it around a BYOK transport.

**Smallest fix.**
- Drop row 7.
- The runner imports from `vidbyte.lib.http.vidbyte_gateway`.
- §8.4's public surface shrinks by one class.

### R-11 [Minor] [L5] §6.1 INV-14, AC-21, EC-21 — BYOK runners are not pinned, so `resolved_api_key()` still reads the environment on every call

**Evidence.**
- §8.5 pins only managed configs.
- In AUTO mode, `resolved_api_key()` calls `is_vidbyte_managed()`, which reads the environment, each time an adapter builds its headers.
- AC-21 does not define "the reverse case stays BYOK".

**Failure.** Suppose a BYOK runner's `OPENAI_API_KEY` is unset after construction while `VIDBYTE_API_KEY` is set. The runner then sends `Bearer vidbyte-managed` to api.openai.com and gets a vendor 401. That contradicts INV-14 as written. The Vidbyte key does not leak.

**Smallest fix.**
- Narrow INV-14 to managed runners.
- Spell out the reverse case in AC-21: the vendor URL is kept, and the placeholder produces a 401.
- Do not pin BYOK configs, because that would break INV-17.

### R-12 [Minor] [L5] §9.2 failure mapping — Exceptions other than `ProviderRequestError`, and cancellation, are not specified

**Evidence.**
- The table's first row covers only an inner `ProviderRequestError` with status `None`.
- The field guide (`provider-api-contracts.md`) says: "one guarded try… wrap any other Exception… never catch BaseException".
- Other exceptions are possible, for example a body value that httpx cannot JSON-encode.

**Failure.** One implementer lets a raw exception escape. Another uses `except BaseException` to honor "every failure becomes `ProviderRequestError`", which swallows `CancelledError` from agent cancellation.

**Smallest fix.** Add two rows:
- Any other `Exception` from the inner send becomes the transport row with status `None`. Do not say "may have billed" when nothing was sent, or state which wording applies.
- `CancelledError` and `KeyboardInterrupt` propagate unchanged.

### R-13 [Minor] [L8] §12.2, §12.3 rows 4–5 — Old-style headers in the modified files keep stale inventories

**Evidence.**
- The `model_configs.py` header has a "Key Functions" list and a stale "Similar Files: vidbyte/lib/models/registry.py".
- `registries/models.py` has a "Key Functions" inventory.
- §12.2 says "none (existing old-style header kept)".
- AGENTS.md style 2 says to update comments in the same edit.

**Failure.** The new public methods (`is_vidbyte_managed`, `resolved_vidbyte_api_key`, `find_vidbyte_api_key`, `resolve_vidbyte_api_key`) are missing from the file inventories that agents read first.

**Smallest fix.** Rows 4 and 5: add the new methods to each header's inventory. No header rewrite.

### R-14 [Minor] [L9] §7 NFR-1, §8.2, §11, §13 — Citation and command corrections

**Evidence.**
- NFR-1 cites `lib/runners/utility.py:44-45`, but `TextModelRunner` is built at `:72-74`.
- §8.2 cites `streaming_text.py:STREAMING_SUPPORTED_PROVIDERS` as a module-level frozenset. It is a class attribute of `StreamingTextModelRunner`.
- §13 says the suite pins "the existing missing-key message" at `tests/test_config_validation.py:24-29`. That test asserts only `ConfigurationError`, not the message.
- §11's PowerShell recipe sets `$env:PYTHONPATH` but never clears it before `--stage package`, which must run without it.

**Failure.**
- Implementers chase the wrong lines.
- The S2 author assumes message coverage that does not exist.
- The PowerShell package stage tests the worktree path instead of the installed package.

**Smallest fix.**
- Correct the three citations.
- Add `Remove-Item Env:PYTHONPATH` before the package stage.

## VERIFIED CLAIMS

1. **D-1 / NFR-1 — confirmed, with a wrong line citation.** Every package text call path ends in `TextModelRunner.arun`. `Runner.build` constructs it at `lib/runners/utility.py:72-74`, not `:44-45`. `agents/base.py:1444-1457` passes only `timeout_seconds`.
2. **`lib/runners/text.py` — confirmed.** `__init__` calls `config.validate()` and `self._transport = transport or HttpTransport()`. `arun` calls `replace(...)`, then `run_text(..., transport=self._transport, config=call_config)`. The §8.5 wiring point exists.
3. **`TextModelConfig` — confirmed.** It has 20 fields, `timeout_seconds: float = 60.0` is last, there is no `__post_init__`, and `cached_content` is a field (`model_configs.py:45-66`). Appending `mode` is positionally safe. No positional construction was found (`git grep`).
4. **D-14 — confirmed.** Decision's managed branch (`model_configs.py:394-403`) strips the explicit key, falls back to the environment with a second strip, uses the regex literal at `:401` and the message at `:402`. Delegation preserves behavior, and the `os`/`re` imports serve only this code.
5. **C020 baseline — confirmed.** 4 = `model_configs.py:401,402` + `providers/typesafe.py:255,271`. After D-14 it is 2.
6. **`HttpTransport.request` — confirmed.** `timeout_seconds=60.0`, `retry_count=0`, retry statuses `(408,409,425,429,500,502,503,504)` and an `idempotency_key` parameter. httpx errors become `ProviderRequestError(provider="http", response_excerpt=str(exc))`. NG-13 / D-10 ("no retries today") holds.
7. **`parse_json_response` — confirmed, and it drives R-2 and R-8.** It puts `response.body` into `response_excerpt` on every failure path (`parser.py:16-32`). Its 2xx test uses the literals 200/300.
8. **§9.2 cap table — confirmed.**
   - OpenAI sets `max_output_tokens` only when configured (`openai.py:213-214`).
   - Anthropic uses `max_tokens = max_output_tokens or 1024`.
   - Gemini uses `generationConfig.maxOutputTokens` (`gemini.py:133`).
   - Compatible uses `max_tokens` (`compatible.py:74`).
   - Gemini puts `model` only in the URL (`gemini.py:26-27`), so the default path already meets r2's "no Gemini body `model`" rule.
9. **`extra_body` merge — confirmed, and it drives R-4 and R-5.** Every adapter merges it last with `payload.update` (`gemini.py:166-167`, `compatible.py:120-121`, `openai.py:61-62`, `:87-88`, `:251`). OpenAI forwards non-function tools unchanged (`openai.py:225-231`). No SDK text path adds hosted tools, `service_tier` or `cache_control` by itself; the only `service_tier` hits are in Codex.
10. **Lint baseline — matches §11 and NFR-5; AC-17 is wrong (R-9).** C017 0, C018 1, C019 0, C020 4, S008 19, S002 0, S056 0.
11. **C017 and the contract loader — confirmed, and they drive R-3.** C017 flags untraced Vidbyte URL literals as well as unknown routes (C017 PURPOSE). `lint/core/platform_contract.py` checks only the shape of `source.repository`/`source.commit`, plus `schema_version` and `generator`. A backend-branch copy therefore passes every SDK gate.
12. **D-4 — confirmed.** The vendored contract marks `vidbyte-backend.onrender.com` live and `api.vidbyte.pro` planned, with `api_key_prefix` `"vb_live_"`. C018 accepts the live-host literal.
13. **INV-11 / AC-10 — refuted (R-2).** Run locally: `raise … from None` inside `except` leaves `__context__` set.
14. **Backend r2 — confirmed, and it drives R-1 and R-5.** The upstream timeout is 600 s and "the SDK's managed client timeout … must exceed 600 s" (`spec.md:670` at `0e397290b`). Gatekeeper and gateway error bodies all carry `"error": true` (§9.2.5–9.2.6). A provider 402 becomes a 502.
15. **§11 commands — confirmed, except for the PowerShell gap in R-14.** `scripts/run_ci.py --stage {all,source,package}` exists. `lint/run.py` accepts `--rule`, `--all` and `--update-baseline`. `C:/Users/422mi/vidbyte-repos/vidbyte` exists with `origin` = cerredz/Vidbyte, so the §12.5 re-vendor commands resolve.
