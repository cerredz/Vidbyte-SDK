# Code map: meta-muse-managed-text (S0 scout)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-meta-muse-managed-text`, branch `feat/meta-muse-managed-text`, HEAD `845a4d9b` (the origin/main base that request.md names). The scout opened every `path:line` below in this session at that HEAD, unless it is marked "unverified". Commands use `py -3.11` in place of `python`, because request.md §C says bare `python` on this machine lacks the test dependencies.

## 1. Rules, commands, and conventions that bind this change

### AGENTS.md (81 lines, read in full; the worktree CLAUDE.md is only `@AGENTS.md`)

- **Map (AGENTS.md:9).** Read `REPO_MAP.md` before you create or move a file. For a deeper index, read `artifacts/file_index.md` and `llms.txt`. The scout read all three. None of them mentions the gateway, the relay, or the set of served providers (a grep for `gateway`, `relay`, `managed`, `TextModelMode`, `kimi`, `muse`, and `meta` found no such entry). No map entry needs to change.
- **Folder READMEs (AGENTS.md:11).** Read a folder's README to the end before you change anything in that folder, and keep its `## Notes for agents` section. Lint rule A009 caps a folder README at 40,000 characters. Two older READMEs keep higher fixed ceilings, and the root `README.md` is exempt.
- **`docs/` is opaque (AGENTS.md:13).** Read a file under `docs/` only when a human names it. request.md names `docs/spec/byok-api-keys/spec.md`.
- **Full gate (AGENTS.md:13).** Before the change is complete, run `python scripts/run_ci.py`. "None of the narrow verification scripts beside it substitutes for it."
- **Style (AGENTS.md:17-41).** Keep call chains one level deep. Narrate main functions in plain English. Build layers of small, single-purpose classes, with `vidbyte/lib/` at the bottom. Use validated dataclasses for core inputs and outputs. Write shared logic once, as a helper in `lib/`. Do not rewrite untouched code to make it conform (:19).
- **Placement (AGENTS.md:43-81).** Dataclasses go in `vidbyte/lib/dataclasses/` and enums in `vidbyte/lib/enums/`. A JEV or gateway constant goes in `vidbyte/lib/constants/jev.py` (:69). Editing an existing definition in place is fine (:79-81).
- **PR and commit conventions.** AGENTS.md states none. request.md §C sets these instead:
  - Open one draft PR. The pipeline never merges it.
  - The PR body must say the PR merges only after cerredz/Vidbyte#710 is deployed.
  - Run A's deploy step requires ops to set `META_API_KEY` on the backend service before any SDK release routes `meta` through the gateway.

### Commands (the scout ran none of them: its brief forbids gate runs and installs)

- **Install:** `py -3.11 -m pip install -e ".[dev]"`. Source: the SDK row of `~/.claude/skills/spec-pipeline/references/vidbyte-gates.md:19`.
- **Lint:**
  - Run `py -3.11 lint/run.py`. To focus, add `--rule <ID>`. `--all` lists every finding, and `--format json` gives JSON output.
  - The final line must read `AGENT-LINT: PASS` (vidbyte-gates.md:28).
  - Never raise a number in `lint/baseline.json` (:29).
- **Test one file:** `PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/sdk_provider_keys/test_provider_keys_modes.py`.
  - The file's own header gives the command (`TESTS:` line, :10).
  - `tests/features/sdk_provider_keys/FEATURE.md:101` adds: run with `PYTHONPATH` set to the worktree and with `DEEPSEEK_API_KEY` unset.
- **Test the area:** `PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys`. Sources: `tests/features/sdk_managed_text/FEATURE.md:82` and `tests/features/sdk_provider_keys/FEATURE.md:101`.
- **Test everything:** `py -3.11 -m pytest`. Unverified: that `testpaths = ["tests"]` is set. The byok spec §13 (spec.md:1249) cites `pyproject.toml:78-79` for it, but the scout did not open pyproject.toml.
- **Full gate:**
  1. Run `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`.
  2. Run `py -3.11 scripts/run_ci.py --stage package` with no `PYTHONPATH` (field guide `local-ci-verification.md:5`).
  3. The proof is `py -3.11 scripts/run_ci.py` with `PYTHONPATH` unset (AGENTS.md:13). Never export `PYTHONPATH` before a full run (request.md §C).
- **Known red on pristine main, per request.md §C:** `harness_threads ... test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (148 != 120) and the MCP stdio `test_cancelled_waiter_does_not_break_transport` flake. The scout did not re-check either.

### Field-guide entries that apply (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`)

- **`local-ci-verification.md`.** Quick checks:
  - :7 `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` must print the worktree path.
  - :12 Run `git add -A` before `semgrep` 1.170.1.
  - :38 Check S051 import sorting with ruff over the whole `vidbyte` tree.
- **`comment-format.md:7`.** Wrap comments at 72 columns. Check: `awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing. This applies to the comment at `jev.py:72-73`.
- **`provider-api-contracts.md:7`.** Mirror the vendor's reference. Check: one scripted-transport test per documented answer example, and `ModelPricingRegistry.default().resolve(provider, "<versioned id>")` is not None.
- **`operation-pricebook-rates.md`.** Never re-derive a rate. It applies only if a Muse price row is touched. The entry has no quick-check line.
- **`blocking-lint-invariants.md`.** Checks:
  - `python lint/run.py --rule A006` (:7, :28, :42).
  - `--rule A003` (:14).
  - `--rule S012` (:35).
  - `--rule C002` (:50).
- **`strict-config-dataclasses.md:8`.** It applies only if a config dataclass changes.
- **`review-scope.md`.** Keep the diff to the request. The entry has no quick-check line.
- **Not applicable:**
  - `agents-md-map.md`: AGENTS.md is not edited.
  - `declarative-config-resolution.md`: no YAML or config resolution is involved.

### byok-api-keys spec rules for gateway-served providers (`docs/spec/byok-api-keys/spec.md`)

**Invariants (§6.1)**

- **INV-1 (:320).** In AUTO, every text call reaches only `VIDBYTE_GENERATIVE_GATEWAY_ENDPOINT`.
- **INV-2 (:322).** A request carries the header if and only if the mode is AUTO and the call has a provider key. The value is the stripped key: printable ASCII, no spaces, at most 512 characters.
- **INV-3 (:323).** A key goes only with a call to the provider it was matched to.
- **INV-5 (:330).** VIDBYTE_MANAGED never sends the header and never reads provider keys.
- **INV-8 (:333-334).** A config whose mode is not DIRECT is refused when it is built. A provider outside `VIDBYTE_MANAGED_TEXT_PROVIDERS` raises `UnsupportedProviderError`, and the message names `TextModelMode.DIRECT`.
- **INV-20 and INV-21 (:367-368).** A relay call gets the same 32,768 cap and 630 s floor. Every re-send keeps the same `Idempotency-Key`.

**Edge cases (§7)**

- **EC-15 (:436).** It lists `meta` among the providers refused in AUTO and VIDBYTE_MANAGED.

**Decisions (§8.1)**

- **D-11 (:562).** AUTO with an unserved provider raises. It "Flips if the backend serves more providers. Then widen `VIDBYTE_MANAGED_TEXT_PROVIDERS`."
- **D-15 (:566).** The failure wording takes `relays`. The wording differs only where the facts differ (table G).
- **D-22 (:573).** The header constant sits in the managed block of `jev.py` and is not in `__all__`.
- **D-23 (:574).** The gateway-shape check runs in `__post_init__` for every mode except DIRECT.
- **D-32 (:583).** Every resolved key must match the pattern. A relayed key must be at most 512 characters.

**API and interface surface (§9.2)**

- **Table R (:883).** In AUTO, the provider key is the matched record or the env var, or None, which means Vidbyte-paid. In VIDBYTE_MANAGED, the provider key is never read.
- **M-12 (:907).** The message reads "The Vidbyte gateway serves only: {supported}. Use mode=TextModelMode.DIRECT …". Its facts column says "the six providers".
- **M-18 (:913).** The words "or Vidbyte's own {primary} account" appear only when the primary is served.
- **Table G (:918-931).**
  - Vidbyte-paid 5xx: "… unavailable or refused Vidbyte's own account …".
  - Relay 5xx: "… is unavailable (HTTP {s}), and the cause is not known".
  - 422: the base wording, plus the DIRECT remedy.
  - Relayed 400: adds the `api_keys` / `{ENV}` hint.
  - Relayed 401, 402, or 403: "… your own {provider} key …".

### Request constraints (request.md §C and §D)

- Build fake keys by concatenation.
- Never invent a price.
- A key goes only to the vendor it was matched to. Never log a secret.
- Add no new header, field, or endpoint. Reuse the #1027 contract.
- Rule 11: an extra becomes an optional Q-n whose default is "no".

## 2. Files this change will touch

**Production: the served set**

- **`vidbyte/lib/constants/jev.py` (794 lines)**
  - *Today:*
    - :72-73 is a comment: "The six providers the generative gateway dispatches: cerredz/Vidbyte backend spec r3 section 9.2.8 at commit a14b37e7e".
    - :74-81 define `VIDBYTE_MANAGED_TEXT_PROVIDERS = frozenset({OPENAI, ANTHROPIC, GEMINI, XAI, DEEPSEEK, KIMI})`.
    - The related constants:

      | Line | Constant |
      |---|---|
      | :84 | `VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS = 32_768` |
      | :88 | `VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS = 630.0` |
      | :97 | `VIDBYTE_PROVIDER_KEY_HEADER` |
      | :98 | `VIDBYTE_PROVIDER_KEY_PATTERN = r"[!-~]+"` |
      | :99 | `VIDBYTE_PROVIDER_KEY_MAX_LENGTH = 512` |
      | :113 | `META: "META_API_KEY"` |

    - `__all__` (:498) lists only `JEV_*` names.
  - *Will change:* `ModelProvider.META` joins the frozenset, and the :72-73 comment's count and source change.
  - *Pattern:* :6 says to change the provider set "only when the backend gateway contract changes, together with the README managed-mode section, tests/features/sdk_managed_text/, and tests/features/sdk_provider_keys/". Keep comments at 72 columns or less.

**Production: readers of the set (no code change expected; behavior changes)**

- **`vidbyte/lib/dataclasses/model_configs.py` (601 lines).** This is the only gate in code.
  - `__post_init__` calls `_require_gateway_shape` at :95-96, before `ProviderKeyMatcher.match` (:100). The check refuses an endpoint at :199-203 and an unserved provider at :204-209.
  - The message builds `supported` from the sorted set, so `meta` appears in it automatically.
  - `credentials()` (:123-171) handles AUTO at :152-169: `find_provider_api_key` (:157), then the 512-character check (:163).
  - `TextCredentials.uses_gateway` (:266) and `relays` (:271-277).
  - `validate()` (:111-121) checks only that the model is not empty.
- **`vidbyte/lib/registries/provider_keys.py` (312 lines).** :308 adds "or Vidbyte's own {provider} account" to M-18 when the provider is in the set, so `meta` gains this clause.
  - The Meta rule `LLM\|[0-9]+\|[A-Za-z0-9_-]+` is at :55. `META` is format-bound (:60).
  - :7 notes that a Meta key's `|` passes the relay pattern.

**Production: adapter (changes only if the spec picks another cap field)**

- **`vidbyte/providers/compatible.py` (259 lines)**
  - `MetaProvider` (:243-244) is a bare subclass, the same shape as `KimiProvider` (:239-240). DeepSeek (:175/:178), GLM (:220/:223), and MiniMax (:228/:231) override `_extract_chat_text`.
  - The payload (:58-66) always carries `model` and `messages`.
  - `_attach_sampling` (:80-89) sets `max_tokens` only when `max_output_tokens` is set (:86-87), and never sets `max_completion_tokens`.
  - `_attach_metadata` (:125-129). `_attach_extra_body` (:131-134) merges any keys.
  - The structured-output tier for META is PROMPT_ONLY (`vidbyte/lib/configs/structured_output.py:47`), so no `response_format` is sent and the schema goes into the system prompt (:112-122).

**Read; no change expected**

- **`vidbyte/lib/runners/text.py` (128 lines).**
  - :57-62 apply, in every gateway mode, `max_output_tokens = config.max_output_tokens or 32_768` and `timeout_seconds = max(630.0, …)`.
  - :90-98 build `VidbyteGatewayTransport(provider=call_config.normalized_provider(), model=…, api_key=…, provider_api_key=self._credentials.provider_api_key)`.
  - :6 says a new gateway requirement is pinned in `__init__`.
- **`vidbyte/lib/http/vidbyte_gateway.py` (242 lines).** It has no branch for a single provider.
  - `retryable` (:64-73): 409, 502, or a body that is not JSON.
  - `failure_reason` (:75-105) never echoes the body. The relayed 401/402/403 wording is at :101, and the relayed 400 hint at :104.
  - `gateway_reason` (:107-136): the 422 list of causes is at :124, and the 5xx cause at :134.
  - The header is set at :191-192, and the envelope is built at :195.
  - The re-send loop is at :208-216 (`JEV_DEFAULT_RETRY_COUNT`). The error is raised at :223.
- **`vidbyte/lib/runners/streaming_text.py`.** `_refuse_gateway_streaming` (:68) refuses every gateway mode. `STREAMING_SUPPORTED_PROVIDERS` is at :28.
- **`vidbyte/lib/enums/text_model.py:20-22`.** The three modes: AUTO, VIDBYTE_MANAGED, and DIRECT.
- **`vidbyte/lib/registries/models.py`.**
  - The default META model `muse-spark-1.1` is at :82, and the endpoint `https://api.meta.ai/v1` at :103.
  - `find_provider_api_key` is at :172.
  - `validate_model` (:329) and `validate_provider_model_pair` (:344) check the catalog only. Neither `TextModelConfig` nor `TextModelRunner` calls them.
- **`vidbyte/lib/registries/pricing.py`.**
  - `PRICING_AS_OF = "2026-10-11"` (:58).
  - The META rows are at :278-287, citing dev.meta.ai/docs/pricing-rate-limits:

    | Model | Input / output / cache read (per million tokens) | Line |
    |---|---|---|
    | `muse-spark-1.3` | 1.25 / 4.25 / 0.15 | :282 |
    | `muse-spark-1.2` | 1.25 / 4.25 / 0.15 | :283 |
    | `muse-spark-1.1` | 1.25 / 4.25 / 0.15 | :284 |
    | `muse-spark-1.3-contributor` | 0.1 / 0.2 / 0.002 | :285 |
    | `muse-spark-1.2-contributor` | 0.1 / 0.2 / 0.002 | :286 |

  - `resolve` is at :333 and `_is_release_suffix` at :361.
  - `lint/pricebook_vintage_lock.json:51-55` locks all five rows.
- **`vidbyte/lib/constants/runners.py`.** The `meta/` ids are at :135-139, the bare ids at :298-302, and the `muse-spark` prefix at :432.
- **Other files:**
  - `vidbyte/lib/dataclasses/agents.py`: `ProviderKeys.key_for` (:283) matches the provider exactly.
  - `vidbyte/providers/__init__.py:53` maps META to `MetaProvider`.
  - `vidbyte/lib/enums/model_provider.py:72` maps META to `ChatCompletionUsage`.

**Docs**

- **`README.md` (root; exempt from A009).** The `### Vidbyte-managed text calls` section starts at :236.
  - :333 "**What the gateway serves and refuses**".
  - :337-339 "**Providers:** OpenAI, Anthropic, Gemini, xAI, DeepSeek, and Kimi."
  - :340-345 is the output-cap bullet: "For xAI, DeepSeek, and Kimi, set the cap with `max_output_tokens`, not `max_completion_tokens` in `extra_body`."
  - *Will change:* add Meta to both lists.
  - *Pattern:* `test_managed_text_acceptance.py:176-197` binds the provider names and facts in this section.
- **`vidbyte/providers/README.md`** (41,573 bytes; under the A009 legacy ceiling of 55,000, `lint/rules/a009_readme_size_limit.py:29-32`). It has no gateway content. :45 lists `compatible.py` as "(DeepSeek, GLM, MiniMax, Kimi, Mistral)", without Meta. The "Meta Llama" section at :362 covers Llama, not Muse. It changes only if the spec takes this gap.
- **No gateway list to change:** `vidbyte/lib/registries/README.md` (it has a Meta key-format row) and `vidbyte/lib/README.md`. These folders have no README: `vidbyte/lib/{http,constants,dataclasses,runners,enums}`, `tests/`, and `tests/features`.
- **Prose that says "six":**
  - `tests/features/sdk_managed_text/FEATURE.md:76`
  - `tests/features/sdk_managed_text/README.md:12`
  - `managed_text_fixtures.py:39`
  - `test_managed_text_acceptance.py:3`

**Tests:** see §3.

## 3. Tests that cover those files

**Framework.** `unittest.TestCase` and `IsolatedAsyncioTestCase` classes, collected by pytest. The versions are unverified (spec.md:1249 names pytest 8.3.5).

**Fixtures:**
- `ScriptedGateway`, `RecordingEnviron`, `BackoffRecorder`, and `ProviderRouter`.
- `patch.dict(os.environ, …, clear=True)`.
- `SLEEP_TARGET = "vidbyte.lib.http.vidbyte_gateway.asyncio.sleep"`.
- Fake keys in `tests/features/sdk_provider_keys/provider_keys_fixtures.py`:
  - `K_META = "LLM" + "|" + "1" * 15 + "|" + "m" * 32` (:39), already built by concatenation.
  - `K_UNPROVEN` (:42) and `K_UNPROVEN_2` (:43).
  - `VENDOR_BASES` maps `"https://api.meta.ai/"` to META (:60).

**`tests/features/sdk_provider_keys/`**

- **`test_provider_keys_modes.py`**
  - `SERVED` (:47) lists the six providers.
  - `GatewayShapeTests` (:215-256): :223 includes `("meta", "llama-4")` and expects `UnsupportedProviderError`. **This test fails by design once meta is served.** :229 asserts that every `SERVED` name appears in the message.
  - :378-389 `test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct` still holds. Its comment at :379, "the gateway does not serve meta", becomes false.
- **`test_provider_keys_wire_contract.py`**
  - `RELAY_KEYS` (:58-65) and `CAP_FIELD` (:67) have no META.
  - The pattern at :6: "When the gateway serves a new provider, add its fake key to RELAY_KEYS and its cap field to CAP_FIELD."
  - The loops at :113, :128, and :197 iterate `RELAY_KEYS`. :75 and :89 read `MANAGED_MODELS[provider]`.
- **Unaffected:**
  - `test_provider_keys_failures.py`: `PROVIDER_KEYS` (:40) covers only openai, anthropic, xai, and gemini.
  - `test_provider_keys_matching.py`: the Meta test (:259-275) binds facts only. The M-18 served/unserved test (:311-336) uses mistral.
  - `test_provider_keys_contract.py:70-74`: `KEY_FORMATS` and `FORMAT_BOUND`, including META.

**`tests/features/sdk_managed_text/`**

- **`managed_text_fixtures.py`**
  - `MANAGED_MODELS` (:40-47) has the six providers.
  - `UNMANAGED_TEXT_PROVIDERS` (:49-55) includes `META` (:53).
  - `_CHAT_PROVIDERS` (:58) is {XAI, DEEPSEEK, KIMI}. It picks the usage shape in `provider_usage` (:109-115).
  - `provider_answer` (:118-129) and `relayed_provider_error` (:137-144).
  - The pattern at :7: "Add a provider to MANAGED_MODELS, provider_answer and relayed_provider_error together when the gateway starts serving it."
- **`test_managed_text_selection.py`**
  - :245-261 iterate `UNMANAGED_TEXT_PROVIDERS`. **The META row fails once meta is served.**
  - The pattern at :6 covers `UNMANAGED_TEXT_PROVIDERS`.
  - `run_text` (:75-84) uses `MANAGED_MODELS.get(provider, "openrouter/auto")`.
- **`test_managed_text_acceptance.py`**
  - `ORACLE_KEYS` (:45-52) has no META.
  - The per-provider test (:90-122) iterates `MANAGED_MODELS` and indexes `ORACLE_KEYS` (:102). **It raises `KeyError` if META is added to `MANAGED_MODELS` without an oracle key.**
  - The README test (:176-197) checks the provider names at :192.
  - The pattern at :6: add the provider to `MANAGED_MODELS`.
- **`test_managed_text_wire_contract.py`**
  - The tables: `ORACLE_KEYS` (:29-36), `CAP_FIELD` (:38-44), `_CHAT_KEYS` (:46), `EMITTED_KEYS` (:47-54), and `FULL_CONFIG` (:63-78).
  - The pattern at :6: update `EMITTED_KEYS` from the spec's §9.2 table, "never from the adapter's current output".
  - The cap test (:121-130) iterates `MANAGED_MODELS` and asserts `"max_completion_tokens"` is not in the body (:130). The `extra_body` example is at :137-139.
- **`test_managed_text_failures.py`.** :65 reads `MANAGED_MODELS[self.provider]`. Unverified: which providers it iterates.
- **`test_managed_text_deadline.py`.** `MANAGED_PROVIDERS` (:47) has the six providers. :193-201 use openrouter as the unserved example and assert each served name, so the test still passes when `meta` is added to the message.

**Elsewhere (unaffected)**

- `tests/features/sdk_model_catalog/test_catalog_pricing_contract.py:64-99` pins the Muse price rows.
- `tests/test_agent_pricing.py:124` covers META.
- `tests/test_agent_fork_isolation.py:460-491` and `tests/test_agent_settings_validation.py:84-100` use glm as the unserved example.

**Commands.** Run from the worktree:
- `PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/sdk_provider_keys/test_provider_keys_modes.py`
- `PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/sdk_managed_text/test_managed_text_wire_contract.py`
- `PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys`, with `DEEPSEEK_API_KEY` unset.
- The full gate in §1.

## 4. Notes for the spec author

**Contradictions**

1. The request (§C) and the wire contract (§9.2 Body) assume that `MetaProvider` "sets `max_tokens` only when `max_output_tokens` is configured", so "every call answers `output_cap_missing`". The code shows that adapter clause at `vidbyte/providers/compatible.py:86-87`. But `vidbyte/lib/runners/text.py:57-62` sets `max_output_tokens` to 32,768 in every gateway mode before the adapter runs. So a gateway body for `meta` already carries `max_tokens`, with no code specific to `meta`. The same mechanism covers xai, deepseek, and kimi (`test_managed_text_wire_contract.py:38-44`). The only open path is an `extra_body` (`compatible.py:131-134`), which merges fields after the cap.
2. The wire contract recommends sending the cap as `max_completion_tokens`. The code shows that `test_managed_text_wire_contract.py:130` asserts no managed body contains `max_completion_tokens`, and `README.md:343-345` tells xAI, DeepSeek, and Kimi users not to use it.
3. The byok spec's EC-15 (spec.md:436) lists `meta` as refused, and M-12's facts (spec.md:907) say "the six providers". The code comment at `jev.py:72-73` says "The six providers … backend spec r3 … a14b37e7e". The request makes the count seven.
4. The request's hint names "Kimi and DeepSeek" as the nearest siblings. The code shows only Kimi has the same shape: `compatible.py:239-240` and `:243-244` are both bare subclasses, while DeepSeek overrides `_extract_chat_text` (:178). Also, META uses the `ChatCompletionUsage` class (`model_provider.py:72`) but is not in the test fixture `_CHAT_PROVIDERS` (`managed_text_fixtures.py:58`). So `provider_answer(META)` returns the `input_tokens`/`output_tokens` usage shape (:109-115), which `test_provider_keys_modes.py:382` already uses.

**Gaps**

5. **Model ids.** The SDK lists and prices five Muse ids (`runners.py:135-139`, `pricing.py:282-286`). Production serves only `muse-spark-1.1` (wire contract §9.2).
   - The SDK has no model check in gateway mode: `validate()` (`model_configs.py:111-121`) checks only that the model is not empty, and `validate_model` (`models.py:329`) is never called from the text config or runner.
   - So an id the gateway does not serve gets the gateway's 422, worded by status alone at `vidbyte_gateway.py:124`.
   - None of the six served providers has a list of served models in the SDK.
   - The default META model (`models.py:82`) is the served id.
6. **Contributor ids.** The SDK prices both `-contributor` ids (`pricing.py:285-286`). The wire contract says a backend pin that lists them would serve them under Vidbyte's own key, where Meta may train on the content (backend EC-29, Q-4). The production pin `54a8e1a5` does not list them. The SDK has no rule that refuses a model only in some modes.
7. **The 502 for a missing backend key.** The SDK re-sends a 502 twice (`vidbyte_gateway.py:64-73`, :208-216) and words it "is unavailable or refused Vidbyte's own account" (:134). It never surfaces body text: `failure_reason` (:75-105) does not echo the body, and the managed fixtures plant `BODY_CANARY` to prove that. No existing SDK pattern surfaces body text, so under rule 11 the `subtitle` append is an optional Q-n whose default is "no".
8. **M-18 wording for meta.** Once `meta` is served, the M-18 message adds "or Vidbyte's own meta account" (`provider_keys.py:308`). That is true only after ops sets `META_API_KEY` (wire contract §9.3).
9. **The relay goes only to meta (verified).** A key flows through these steps:
   1. `credentials()` (`model_configs.py:152-169`).
   2. `find_provider_api_key` (`models.py:172`).
   3. `ProviderKeys.key_for`, which matches the provider exactly (`agents.py:283`).
   4. `text.py:90-98`, which passes the config's own provider and credentials.
   5. The envelope (`vidbyte_gateway.py:195`) and the header (:191-192).

   META is format-bound (`provider_keys.py:60`), so an `LLM|` key binds only to `meta`. `META_API_KEY` (`jev.py:113`) is also relayed in AUTO, as it is for the six served providers.
10. **Unverified: Muse's maximum output.** It is not known whether Muse's limit is at least the 32,768 default (`jev.py:84`). If Meta refuses that cap on a relay call, the relayed-400 hint (`vidbyte_gateway.py:104`) tells the user to check their own meta key.
11. **Unverified: other Meta field behavior.** It is not known whether Meta accepts `metadata` (`compatible.py:125-129`), or whether `max_tokens` counts reasoning tokens (backend A-3).
12. **No change needed:**
    - Streaming: every gateway mode refuses it (`streaming_text.py:68`).
    - Structured output: META is PROMPT_ONLY, so no `response_format` is sent.
    - The timeout floor: 630 s is above the gateway's 600 s upstream deadline.
    - The SDK price row for `muse-spark-1.1` (`pricing.py:284`) equals the rates request.md says Run A verified: 1.25 / 4.25 / 0.15.
13. **Older README gaps** (outside the request unless the spec takes them):
    - `README.md:289-292`: the list of key prefixes leaves out `LLM|`.
    - `vidbyte/providers/README.md:45`: the `compatible.py` list leaves out Meta.
    - `vidbyte/providers/README.md:362`: the Meta section covers Llama, not Muse.
14. **Merge order.** The rule that this PR merges after #710 is deployed and after ops sets `META_API_KEY` has no site in the code. It belongs only in the PR body (request.md §C).
