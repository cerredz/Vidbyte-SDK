# Test plan: meta-muse-managed-text (S2)

**Spec:** `docs/spec/meta-muse-managed-text/spec.md` r3 (the contract). **Base:** `845a4d9b` (the worktree's `vidbyte/` is byte-identical to it at S2). **Packs:** `tests/features/sdk_managed_text/` and `tests/features/sdk_provider_keys/`. No new module: every test fits an existing layer of one of the two packs.

**Fakes used (spec §13 "Real seams" only):** the inner HTTP transport (`transport=` or `RUNNER_TRANSPORT_TARGET`), the retry wait (`SLEEP_TARGET`), and `os.environ` (`patch.dict(..., clear=True)` or `RecordingEnviron`). `TextModelConfig.credentials()`, `ProviderModelRegistry`, `ProviderKeyMatcher`, `ProviderKeys`, the adapters, `TextModelRunner`, and `VidbyteGatewayTransport` all run unmocked. No sleeps, no wall clock, no network.

**Fake keys:** every Meta key is built by concatenation: `K_META = "LLM" + "|" + "1" * 15 + "|" + "m" * 32` (existing), `K_META_2 = "LLM" + "|" + "2" * 15 + "|" + "e" * 32` (new), and the oracle key `"LLM" + "|" + "0" * 15 + "|" + "o" * 32` (new, in two `ORACLE_KEYS` tables). No key shape appears as one literal.

**Totals:** 15 new test methods; 10 existing tests whose data tables were extended by the S2 grant (assertion logic unchanged); 24 tests red at HEAD, all for the meta-unserved reason; 183 green with the set widened and the README edited.

## Coverage map

"Red at HEAD" is the failure the test shows on `base_commit`. Every subtest failure was audited one by one under `unittest` (which reports each failing subtest): 33 `UnsupportedProviderError` M-12 raised at construction, 6 `'meta' not found` in the M-12 message, 5 `UnsupportedProviderError ... is not an instance of ProviderRequestError`, 4 `AgentExecutionError` whose `details["error_type"]` is `UnsupportedProviderError` with 0 requests sent, 2 sets missing `meta`, 1 M-18 without "Vidbyte's own meta account", and 2 README facts missing. No `KeyError`, import error, collection error, or typo.

File prefixes: `mt/` = `tests/features/sdk_managed_text/`, `pk/` = `tests/features/sdk_provider_keys/`.

| Spec ID | Test | Level | Failure caught (input + state → wrong output) | Why it cannot pass vacuously |
|---|---|---|---|---|
| AC-1, G-1, G-2, INV-2, INV-3, INV-5 | `pk/test_provider_keys_acceptance.py::SnippetAcceptanceTests::test_meta_muse_snippet_relays_the_meta_key_for_the_agent_and_sends_the_paid_call_without_it` (new) | acceptance | §4 snippet with `VIDBYTE_API_KEY`, `ANTHROPIC_API_KEY`, `META_API_KEY` → agent raises instead of relaying; the agent relays the Anthropic key; the paid call relays `META_API_KEY`; cap missing or not 32,768 | Asserts printed `["Hi", "Hello"]` (both scripted answers consumed), exactly 2 gateway POSTs, per-request provider, relay header value, header set, and `max_tokens` 32,768. Red at HEAD: `AgentExecutionError` (inner `UnsupportedProviderError`, 0 requests). |
| AC-2, INV-2, FR-2 | `pk/test_provider_keys_wire_contract.py::RelayHeaderTests::test_each_served_provider_relays_its_own_key_in_the_header_and_nowhere_else` (extended: `RELAY_KEYS[META]`) | wire contract | `meta` with `api_keys=[K_META]` → header missing, wrong value, or key echoed in URL, body, or another header | Exact header-name set and exact relay value; key searched outside the relay header. Red at HEAD: M-12 on the meta subtest only. |
| AC-2, INV-2, INV-4, T-1 | `pk/test_provider_keys_wire_contract.py::MetaRelayTests::test_a_meta_call_relays_the_lists_meta_key_before_meta_api_key_stripped_and_no_other_key` (new) | wire contract | mixed list `[K_ANTHROPIC, K_OPENAI, K_META, K_XAI]` plus `META_API_KEY=K_META_2` → relays `K_META_2` or another vendor's key; padded list entry or padded `META_API_KEY` → unstripped header; `META_API_KEY` ignored when the list has no Meta key | Two distinct Meta fakes make the source observable; the absent keys are searched in the whole request. Red at HEAD: M-12 in all 3 subtests. |
| AC-3, INV-3, FR-3 | `pk/test_provider_keys_wire_contract.py::MetaRelayTests::test_a_meta_call_without_a_meta_key_sends_exactly_the_three_vidbyte_paid_headers` (new) | wire contract | no key, blank `META_API_KEY`, or a Vidbyte-only list → a relay header (empty or blank) is sent, or the call refuses | Exact 3-name header set, `provider: "meta"`, `max_tokens` 32,768, timeout 630. Red at HEAD: M-12 in all 3 subtests. |
| AC-4, INV-3 | `pk/test_provider_keys_acceptance.py::TextCallAcceptanceTests::test_vidbyte_managed_meta_never_reads_meta_api_key_or_sends_a_meta_key` (new) | acceptance | `VIDBYTE_MANAGED` with `api_keys=[K_META]` and `META_API_KEY=K_META_2` → either key sent, or `META_API_KEY` read | `RecordingEnviron` records reads; both Meta fakes searched in the request. Red at HEAD: M-12. |
| AC-5, INV-5, FR-4, D-2 | `mt/test_managed_text_wire_contract.py::OutputCapTests::test_managed_body_carries_the_default_cap_or_the_callers_exact_value_in_each_dialects_field` (extended: `MANAGED_MODELS[META]`, `CAP_FIELD[META]`) | wire contract | paid `meta` with cap unset/100/40,000 → `max_tokens` absent, `max(N, 32768)`, `min(N, 32768)`, a float, or `max_completion_tokens` added | Reads `max_tokens` as an `int`, exact value, and asserts no `max_completion_tokens`. Red at HEAD: M-12 on the 3 meta subtests. |
| AC-5, INV-5 (relay) | `pk/test_provider_keys_wire_contract.py::RelayCapAndFloorTests::test_a_relay_body_carries_the_default_cap_or_the_callers_exact_value` (extended: `RELAY_KEYS[META]`, `CAP_FIELD[META]`) | wire contract | relay `meta` with cap unset/100/40,000 → wrong cap on the relay path | Same exact-int check, plus the relay header value. Red at HEAD: M-12 on the 3 meta subtests. |
| AC-6, INV-6 | `pk/test_provider_keys_wire_contract.py::RelayHeaderTests::test_the_relay_envelope_body_is_the_direct_body_with_the_gateway_cap` (extended) | wire contract | relay envelope differs from paid envelope, or body differs from the `DIRECT` body plus `max_tokens` 32,768 | Oracle is the real `MetaProvider` in `DIRECT`. Red at HEAD: M-12 on the meta subtest. |
| AC-6, AC-12, INV-6, INV-11 | `pk/test_provider_keys_acceptance.py::TextCallAcceptanceTests::test_meta_in_direct_sends_base_commits_request_and_both_gateway_envelopes_wrap_that_body_with_the_cap` (new) | acceptance | `DIRECT` meta request changes (URL, headers, body, 60 s timeout) or reads `VIDBYTE_API_KEY`; the gateway envelopes are not `{provider, model, body: golden + max_tokens 32768}` or differ between relay and paid | Golden literal recorded from `base_commit`'s adapter; `set(envelopes) == {"relay", "vidbyte-paid"}` stops a vacuous `None == None`. Red at HEAD: M-12 in both gateway subtests (the `DIRECT` half passes at HEAD, as INV-11 requires). |
| AC-6, INV-1, INV-6 (paid, end to end) | `mt/test_managed_text_acceptance.py::ManagedTextAcceptanceTests::test_each_managed_provider_posts_its_byok_body_once_to_the_gateway_and_parses_the_answer` (extended: `MANAGED_MODELS[META]`, `ORACLE_KEYS[META]`) | acceptance | paid `meta` call → not one POST, body is not the `DIRECT` oracle body, usage not parsed as chat usage | `DIRECT` oracle with a fully matching Meta key (an unproven one would fail at M-6); `response.usage == provider_usage(META)` (chat usage). Red at HEAD: M-12 on the meta subtest. |
| INV-6 (allowed keys) | `mt/test_managed_text_wire_contract.py::EmittedKeyTests::test_managed_body_emits_only_the_keys_on_each_dialects_allowed_list` (extended: `EMITTED_KEYS[META] = _CHAT_KEYS`, `FULL_CONFIG[META]`) | wire contract | every mapped field set → a key outside spec §9.2's meta list, a forbidden key, or a body that differs from `DIRECT` | Equality with the `DIRECT` oracle proves every mapped field was exercised; cap 4,096 checked exactly. Red at HEAD: M-12 on the meta subtest. |
| AC-7, EC-1, EC-15, FR-5, D-4 | `pk/test_provider_keys_failures.py::MetaGatewayFailureTests::test_a_muse_id_the_gateway_does_not_serve_is_sent_unchanged_once_and_gets_the_422_wording` (new) | failure | `muse-spark-1.3` relay, `muse-spark-1.2` paid, `muse-spark-1.3-contributor` in `VIDBYTE_MANAGED`, answered 422 `model_gateway_unsupported_model` → refused in the SDK, id rewritten, 422 re-sent, wrong wording, body text echoed | Envelope and body `model` equal the id; no waits; facts "unmanaged or unpriced provider or model" and `TextModelMode.DIRECT`; full credential-safety check (canary, `LEAKED_KEY`, every relay key, no chain). Red at HEAD: M-12 in all 3 subtests. |
| AC-8, EC-2, INV-7, INV-8 | `pk/test_provider_keys_failures.py::MetaGatewayFailureTests::test_a_meta_502_is_sent_three_times_with_one_key_and_worded_for_who_pays` (new) | failure | paid 502 with Run A's missing-key copy, relay 502 → not 3 sends, new `Idempotency-Key` or changed headers per attempt, waits not `[0.5, 1.0]`, relay message blames "Vidbyte's own account", paid message lacks it, or the subtitle remedy is echoed (Q-1 = No) | Canary in the subtitle and `LEAKED_KEY` in the description; identical headers and envelope across attempts. Red at HEAD: M-12 in both subtests. |
| AC-9, EC-13 | `pk/test_provider_keys_failures.py::MetaGatewayFailureTests::test_a_relayed_meta_401_names_the_callers_own_meta_key_and_a_relayed_429_is_withheld` (new) | failure | Meta's own `{"error": {...}}` body at 401 and 429 → read as the gateway's `"error": true`, re-sent, blames quota or wallet, or omits "your own meta key" (401) | Status in message, `meta` named at least twice, "withheld", not billed, 1 POST, no waits. Red at HEAD: M-12 in both subtests. |
| AC-10, INV-10, INV-12 | `pk/test_provider_keys_modes.py::GatewayShapeTests::test_every_unserved_provider_and_any_endpoint_is_refused_at_construction_in_both_gateway_modes` (changed per grant: `SERVED` + `meta`, `("meta", "llama-4")` row removed) | mode | openrouter/glm/minimax/mistral in AUTO or VIDBYTE_MANAGED → M-12 does not list `meta`, or a key is read before refusing | Every `SERVED` name asserted in the message. Red at HEAD: `'meta' not found in` the M-12 message. |
| AC-10 | `mt/test_managed_text_selection.py::KeySelectionTests::test_managed_state_refuses_every_provider_the_gateway_does_not_serve` (changed per grant: `UNMANAGED_TEXT_PROVIDERS` − META; reads `MANAGED_MODELS`) | selection | same, through `UNMANAGED_TEXT_PROVIDERS` | Asserts every `MANAGED_MODELS` provider is in the message. Red at HEAD: `'meta' not found` for 4 providers. |
| AC-10 | `mt/test_managed_text_deadline.py::DirectValidateTests::test_validate_refuses_an_explicit_vidbyte_key_for_a_provider_the_gateway_does_not_serve` (extended: `MANAGED_PROVIDERS` + `"meta"`) | deadline | openrouter with an explicit Vidbyte key → M-12 omits `meta` | Every listed provider asserted in the message. Red at HEAD: `'meta' not found`. |
| AC-11, INV-1, INV-4 | `pk/test_provider_keys_agents.py::MetaAgentTests::test_a_relayed_meta_401_falls_back_to_anthropic_and_each_call_carries_only_its_own_providers_key` (new) | agent | Muse primary with `[K_ANTHROPIC, K_META]` and an Anthropic fallback; Meta answers 401 → no fallback, or either key on the other's request | Reply must be the fallback's answer; requests are `["meta", "anthropic"]`; cross-key search. Red at HEAD: `AgentExecutionError` (inner `UnsupportedProviderError`, 0 requests). |
| AC-12, INV-11 | `pk/test_provider_keys_modes.py::...::test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct` (existing; comment corrected) and the AC-6 golden test above | mode / acceptance | `DIRECT` meta changes vendor, bearer, or leaks the Anthropic key | Exact URL prefix and bearer. Passes at HEAD by design (must not regress). |
| AC-13, FR-7 | `mt/test_managed_text_acceptance.py::ManagedTextAcceptanceTests::test_readme_managed_section_names_meta_as_served_in_the_chat_cap_guidance_and_by_its_llm_prefix` (new) | acceptance | README section → Providers bullet's served list lacks Meta; the `max_completion_tokens` sentence lacks Meta; Prefixes bullet lacks "`LLM\|` (Meta)" or loses an old prefix | Each bullet must exist (an empty string fails); whitespace is collapsed so a re-wrap cannot change the outcome. Red at HEAD: served list `'OpenAI, Anthropic, Gemini, xAI, DeepSeek, and Kimi'`. Mutants killed: Providers-only edit (fails on cap), Providers + cap edit (fails on `LLM\|`). The two existing README tests keep binding the old facts. |
| AC-14, INV-8, INV-9, NFR-1 | `pk/test_provider_keys_security.py::LeakScenarioTests::test_every_meta_gateway_failure_logs_and_raises_no_key_canary_or_key_shaped_body_text` (new) | security | 422, 502 ×3, relayed 400 echoing `K_META`, relayed 401, network failure whose excerpt holds `K_META` → any of `K_META`, the Vidbyte key, `LEAKED_KEY`, `BODY_CANARY` in a DEBUG log record on the root logger, `str`, `details`, `repr`, traceback, `__cause__`, `__context__` | Asserts first that the error is a `ProviderRequestError` with the expected status and that the transport saw the meta relay attempts, so a refusal before any request cannot pass. Red at HEAD: 5 subtests, `UnsupportedProviderError ... is not an instance of ProviderRequestError`. |
| AC-14 (all failure tests) | `pk/test_provider_keys_failures.py` `FailureAssertions.assert_credential_safe` (extended: `PROVIDER_KEYS[META] = K_META`) | failure | any failure message, details, or traceback that holds `K_META` | Strengthens every existing failure test's leak list. |
| INV-1, INV-12, INV-14 | `pk/test_provider_keys_modes.py::GatewayShapeTests::test_meta_builds_in_both_gateway_modes_and_still_refuses_a_custom_endpoint_and_streaming` (new) | mode | meta (enum and string) in AUTO/VIDBYTE_MANAGED → M-12; meta + endpoint → not refused; `StreamingTextModelRunner(meta config)` → streams or raises without naming `TextModelRunner` and `DIRECT`, or `details["mode"]` wrong | The streaming config is built outside `assertRaises`, so HEAD's M-12 cannot satisfy it. Red at HEAD: M-12 in the 4 build subtests and 2 streaming subtests (the endpoint subtests pass at HEAD, as INV-12 requires). |
| EC-6, INV-10, FR-6 | `pk/test_provider_keys_matching.py::ConfiguredPrimaryTests::test_m18_offers_vidbytes_own_meta_account_for_a_meta_primary_whose_list_holds_only_another_providers_key` (new) | unit | meta primary, `api_keys=[K_ANTHROPIC]`, via `TextModelConfig` and `Agent` → M-12 instead of M-18, or M-18 without "Vidbyte's own meta account" | Requires `ConfigurationError` (M-12 is not a subclass), `details["provider"] == "meta"`, no key text. Red at HEAD: M-12 (config root); clause missing (agent root). |
| EC-11, INV-3, INV-4 | `pk/test_provider_keys_agents.py::MetaAgentTests::test_a_fork_to_muse_relays_meta_api_key_or_goes_vidbyte_paid_and_never_carries_the_parents_anthropic_key` (new) | agent | Anthropic parent with `[K_ANTHROPIC]` forked to Muse → raises; relays the Anthropic key; ignores `META_API_KEY`; relays when no Meta key exists | Fork keeps the parent's record (asserted); header count 4 or 3; `max_tokens` 32,768. Red at HEAD: `AgentExecutionError` (inner `UnsupportedProviderError`, 0 requests). |
| EC-16 (accepted; Q-6 = No) | `pk/test_provider_keys_agents.py::MetaAgentTests::test_the_multi_provider_grader_adds_a_muse_member_that_relays_only_meta_api_key` (new) | agent / composition | grader with `provider_models` unset, `ANTHROPIC_API_KEY` and `META_API_KEY` set → Muse member dropped, or a member sends the other's key | Counts member runs (`total_runs == 2`, candidates `{anthropic, meta}`), not requests. Red at HEAD: candidates lack `meta`. |

**Mutation check (scratch plugin `s2_mutants.py`, not committed).** Each mutant ran against the whole area; each was killed:

| Mutant | Tests that failed |
|---|---|
| README with only the Providers bullet edited | AC-13 test (cap sentence) |
| README with Providers and Output cap edited, Prefixes untouched | AC-13 test (`LLM\|`) |
| `meta` served by `TextModelConfig` but not in `provider_keys`' set | EC-6 test (M-18 clause) |
| `meta` served, gateway default cap 16,384 | 15 tests, including the AC-1, AC-3, AC-6, AC-11, EC-11, EC-16 meta tests |

## Tests deliberately NOT written

| Spec ID | Why no new test |
|---|---|
| AC-15, FR-8 | The PR body is checked at S6, not by pytest. |
| INV-15, NFR-2 | A price test would pass at HEAD (rule 6). The `META/muse-spark-1.1` row is pinned by lint C010 (`lint/pricebook_vintage_lock.json:51`), run by the full gate, and NFR-2 is a 0-line diff check for S4. `tests/features/sdk_model_catalog/test_catalog_pricing_contract.py:64-99` pins only the 1.2, 1.3, and contributor rows. |
| INV-13 | The six served providers' requests are already pinned by the existing per-provider tests, which still pass with `meta` added. |
| INV-7 (NaN floor), EC-12, T-4 | Provider-generic: the floor and the per-call `Idempotency-Key` live in `TextModelRunner` and `VidbyteGatewayTransport`, which have no provider branch, and are pinned for openai (`RelayCapAndFloorTests`, `ConcurrentRelayTests`, the managed-text deadline tests). The 502 test above checks one key and identical headers on every meta attempt. |
| EC-3, EC-4, EC-7, A-2, A-4 | Live Meta behavior (configured maximum, context window, unsupported fields). Offline tests cannot observe it; the §12.5 pre-merge live check is the check. |
| EC-5, the INV-5 `extra_body` exception | The merge order is generic (`compatible.py:131-134`) and pinned for xAI by `OutputCapTests.test_extra_body_generation_config_and_completion_cap_reach_the_gateway_unchanged`. Pinning `extra_body={"max_tokens": None}` would freeze a footgun the spec only accepts. |
| EC-8 | Unchanged matching, already pinned by `test_provider_keys_matching.py`'s Meta table F cases. |
| EC-9, EC-10 | M-14 and M-21 are provider-generic guards in `find_provider_api_key` and `credentials()`, pinned for other providers. The meta variable name is proven by the `META_API_KEY` relay subtest above. |
| EC-14 | An accepted limitation shared by every provider; nothing meta-specific to bind. |
| EC-2's "(re-sends in this call: 2)" text | Not an AC-8 fact; the re-send count wording is pinned provider-generically by `test_managed_text_deadline.py`. |
| EC-16's other compositions (aggregate, fanout, critic, prosecutor/defender/judge, Jev brief writer) and EC-11's handoff path | The same mechanism: each ends in `ModalityDetector.create_runner` or `BaseAgent._runner_for_model` building a `TextModelRunner`, and the handoff passes the parent's record like the fork. One composition (the grader) and one child (the fork) prove the mechanism. |
| Q-1 to Q-6 | All defaulted to No; no test demands any of them. The 502 test asserts the status-only wording, which is the Q-1 = No behavior already required by INV-8. |
| Property-based / fuzz | `hypothesis` is not a dependency; the inputs here are small closed sets covered exhaustively. |

## Red run

Bootstrap ("install"), no `pip install`:

```
$ PYTHONPATH=$(pwd) py -3.11 -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"
C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-meta-muse-managed-text\vidbyte\__init__.py
```

Baselines before any S2 edit: unwidened `168 passed in 2.04s`; widened `2 failed, 166 passed in 1.86s` (the two by-design failures named in spec §13).

Red at HEAD (`82a3bd8e`, code = `base_commit`):

```
$ env -u DEEPSEEK_API_KEY PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider --tb=no
...
FAILED tests/features/sdk_provider_keys/test_provider_keys_wire_contract.py::MetaRelayTests::test_a_meta_call_without_a_meta_key_sends_exactly_the_three_vidbyte_paid_headers
FAILED tests/features/sdk_provider_keys/test_provider_keys_wire_contract.py::RelayCapAndFloorTests::test_a_relay_body_carries_the_default_cap_or_the_callers_exact_value
24 failed, 159 passed in 2.13s
```

The 24 are the 15 new tests and the 9 extended or changed tests marked "Red at HEAD" above; the reasons are audited in the coverage map's preamble.

Green proof, with `VIDBYTE_MANAGED_TEXT_PROVIDERS` widened in memory by a scratch plugin (`s1_widen`, rebinding the set in `jev`, `model_configs`, and `provider_keys`; not committed):

```
$ env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd);<scratchpad>/plugins" py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider -p s1_widen --tb=no
FAILED tests/features/sdk_managed_text/test_managed_text_acceptance.py::ManagedTextAcceptanceTests::test_readme_managed_section_names_meta_as_served_in_the_chat_cap_guidance_and_by_its_llm_prefix
1 failed, 182 passed in 1.44s
```

The one failure is the README test, which needs the README edit, not the set. With a second scratch plugin (`s1_readme`) that points both README tests at a copy of `README.md` carrying exactly spec §12.3 row 2 (a) to (c):

```
$ ... -p s1_widen -p s1_readme --tb=no
183 passed in 1.41s
```

## Notes for the implementer

- The whole change is spec §12.3 rows 1 and 2: `ModelProvider.META,` in `VIDBYTE_MANAGED_TEXT_PROVIDERS` with its comment, and the three README bullets. After both, the area command above must end `183 passed`. Do not edit any test file or test-pack doc (§14).
- Run the area with `DEEPSEEK_API_KEY` unset (`env -u DEEPSEEK_API_KEY`); it is set in this machine's shell.
- The AC-13 test binds, after collapsing whitespace (re-wrap freely):
  - the bullets still start at line start as `- **Providers:**`, `- **Output cap:**`, and `- **Prefixes:**`, inside the `### Vidbyte-managed text calls` section;
  - the Providers bullet's first sentence (up to the first `. `) names OpenAI, Anthropic, Gemini, xAI, DeepSeek, Kimi, and Meta as whole words;
  - one Output cap sentence that contains `max_completion_tokens` names xAI, DeepSeek, Kimi, and Meta;
  - the Prefixes bullet contains exactly `` `LLM|` (Meta) `` (backticks, one space, parentheses) and still contains `` `sk-ant-` (Anthropic) ``, `` `xai-` (xAI) ``, and `(Gemini)`.
- If any of the 24 stays red after row 1, the set change did not reach that reader: `model_configs.py` (M-12, construction) and `provider_keys.py` (M-18) both import the set by name.
- The grader test (EC-16) expects exactly two members, `anthropic` and `meta`. It clears the environment, so a developer's other keys cannot add members.
- Expected per-provider usage: `provider_answer(ModelProvider.META)` now answers in chat usage (`prompt_tokens`/`completion_tokens`), matching `MetaProvider`'s parser.

## Before/after of every edit to an existing test or fixture

All edits are inside the S2 grant (pipeline.md, 2026-10-17 03:40). No assertion was weakened, and no test was deleted or skipped.

| File | Symbol | Before | After | Reason |
|---|---|---|---|---|
| `mt/managed_text_fixtures.py` | comment at `:39` | `# The six providers the gateway serves, …` | `# The seven providers the gateway serves, …` plus a line citing FR-1 and the `muse-spark-1.1` default | grant ("six" prose) |
| `mt/managed_text_fixtures.py` | `MANAGED_MODELS` | 6 entries | + `ModelProvider.META: "muse-spark-1.1"` | grant |
| `mt/managed_text_fixtures.py` | `UNMANAGED_TEXT_PROVIDERS` | OPENROUTER, GLM, MINIMAX, META, MISTRAL | OPENROUTER, GLM, MINIMAX, MISTRAL | grant |
| `mt/managed_text_fixtures.py` | `_CHAT_PROVIDERS` | `{XAI, DEEPSEEK, KIMI}` | `{XAI, DEEPSEEK, KIMI, META}` with a comment | grant; Meta's usage is chat usage (§13) |
| `mt/managed_text_fixtures.py` | `relayed_provider_error` | no Meta note | comment: Meta uses the OpenAI-style default branch (no code change) | grant |
| `mt/test_managed_text_acceptance.py` | header PURPOSE / ROLE / COMMON MODIFICATION PATTERNS / RELATED DOCS | "all six providers"; no meta IDs; no `ORACLE_KEYS` hint | "all seven providers"; meta AC-13, INV-1, INV-6; "give it an ORACLE_KEYS entry … a missing oracle key is a KeyError"; meta spec cited | grant ("six" prose) |
| `mt/test_managed_text_acceptance.py` | `ORACLE_KEYS` | 6 entries | + `META: "LLM" + "\|" + "0" * 15 + "\|" + "o" * 32` | grant (KeyError trap; M-6 needs a full match) |
| `mt/test_managed_text_acceptance.py` | new module constants and helpers | — | `SERVED_PROVIDER_NAMES`, `CHAT_CAP_PROVIDER_NAMES`, `readme_bullet`, `names_word` (used only by the new AC-13 test) | new test support |
| `mt/test_managed_text_wire_contract.py` | `ORACLE_KEYS`, `CAP_FIELD`, `EMITTED_KEYS`, `FULL_CONFIG` | no META entry | `ORACLE_KEYS[META]` as above; `CAP_FIELD[META] = "max_tokens"`; `EMITTED_KEYS[META] = _CHAT_KEYS` (spec §9.2 meta list); `FULL_CONFIG[META] = ({}, {"tools": (_FUNCTION_TOOL,), "tool_choice": "auto"})` | grant |
| `mt/test_managed_text_wire_contract.py` | header ROLE / RELATED DOCS | no meta IDs | + meta AC-5, INV-5, INV-6; meta spec §6.1, §9.2 | documentation |
| `mt/test_managed_text_deadline.py` | `MANAGED_PROVIDERS` | `("openai", "anthropic", "gemini", "xai", "deepseek", "kimi")` | + `"meta"`, with a comment citing AC-10 | grant |
| `mt/FEATURE.md` | Test Suite Map, Known Failure Modes | "all six providers" | "all seven providers … `meta` since meta-muse-managed-text FR-1", AC-13; two meta failure modes | grant ("six" prose) |
| `mt/README.md` | File Index, Logs | "all six managed providers" | "all seven managed providers", "the README's Meta bullets"; 2026-10-17 log line | grant ("six" prose) |
| `pk/provider_keys_fixtures.py` | `K_META_2`, `__all__`, `chat_done` comment | — ; "(xai, deepseek, kimi, mistral)" | `K_META_2 = "LLM" + "\|" + "2" * 15 + "\|" + "e" * 32` exported; "(xai, deepseek, kimi, mistral, meta)" | fixture extension (a second Meta key makes the relay source observable) |
| `pk/test_provider_keys_wire_contract.py` | `RELAY_KEYS`, `CAP_FIELD`, imports, header | no META; imports without Meta keys | `RELAY_KEYS[META] = K_META`; `CAP_FIELD[META] = "max_tokens"`; imports `K_META`, `K_META_2`; meta IDs in ROLE and RELATED DOCS | grant |
| `pk/test_provider_keys_modes.py` | `SERVED` (`:47`) | 6 names | + `"meta"`, with a comment | grant |
| `pk/test_provider_keys_modes.py` | `GatewayShapeTests` row list (`:223`) | includes `("meta", "llama-4")` | row removed (meta now served; its positive case is the new INV-1 test) | grant |
| `pk/test_provider_keys_modes.py` | comment at `:379` | "Table F: the gateway does not serve meta, so a Muse call is DIRECT; …" | "Table F, meta-muse-managed-text INV-11: in DIRECT a Muse call goes straight to Meta, as at base_commit; …" | grant (comment that became false) |
| `pk/test_provider_keys_modes.py` | header ROLE / RELATED DOCS | no meta IDs | + meta AC-10, INV-1, INV-10, INV-12, INV-14; meta spec §6.1 | documentation |
| `pk/test_provider_keys_failures.py` | `PROVIDER_KEYS` | OPENAI, ANTHROPIC, XAI, GEMINI | + `META: K_META`, with a comment | fixture extension; strengthens every failure test's leak list |
| `pk/test_provider_keys_failures.py` | `GatewayCall.__init__` / `run` | `(*steps, relay, provider=OPENAI)`; model always `MANAGED_MODELS[provider]`, mode always the default | `(*steps, relay, provider=OPENAI, model=None, mode=None)`; `model or MANAGED_MODELS[provider]`; `mode` passed only when given | fixture extension; existing callers behave exactly as before |
| `pk/test_provider_keys_failures.py` | imports, header | — | + `K_META`, `idempotency_key`; meta IDs in ROLE and RELATED DOCS | documentation |
| `pk/test_provider_keys_security.py` | imports, new helper `run_meta_relay`, header | — | + `functools`, `BODY_CANARY`, `LEAKED_KEY`, `answer`, `relayed_provider_error`, `K_META`, `provider_key_header`; helper for the AC-14 scenarios | new test support |
| `pk/test_provider_keys_acceptance.py`, `pk/test_provider_keys_agents.py`, `pk/test_provider_keys_matching.py` | imports, header | — | + `K_META`, `K_META_2` where used; meta IDs in ROLE and RELATED DOCS | documentation |
| `pk/FEATURE.md` | Known Failure Modes, Test Suite Map | no meta entries | five meta failure modes; meta tests named per module | documentation |
| `pk/README.md` | Logs | one entry | + 2026-10-17 meta-muse-managed-text S2 line | documentation |

## r4 delta

**Spec:** r4 (`04729669`; pipeline r4 and S2 delta grant `121911df`). **Production under test:** HEAD `121911df`, the r3 implementation with no r4 change, so the Meta row of `ProviderKeyMatcher.KEY_FORMATS` is still `(META, ("LLM|",), LLM\|[0-9]+\|[A-Za-z0-9_-]+)`. **Commits:** `23c4e9c4` (r4 tests), `4af4d8e0` (R-2, R-6, R-7 tidy). **New files:** none (budget 0).

**What this delta protects.** A Muse user pastes the key Meta issues today, `LLM_<numeric id>_<secret>`. That key must reach Meta and only Meta, in every mode and on every path. A malformed `LLM_` key must fail closed with M-6 and never be sent to a vendor. At HEAD the documented key is unproven and unreserved, so it binds by elimination to kimi, deepseek, mistral, glm or minimax and is relayed to that vendor (probe at HEAD: `match([K_ANTHROPIC, K_META_DOC], primary="anthropic", others=("kimi",))` gives `{anthropic, kimi}`; the same call with `K_META` gives `{anthropic, meta}`).

**Fixture:** `K_META_DOC = "LLM" + "_" + "1" * 16 + "_" + "m" * 32` in `pk/provider_keys_fixtures.py`, exported in `__all__`. `LLM_` joins the reserved-prefix list on its KNOWN EDGE CASES line. Malformed keys are built inline by concatenation, so no literal Meta key shape appears in the tree.

**Totals:** 9 new test methods (matching 5, agents 1, contract 3) and 7 extended existing tests: about 290 new subtests. At HEAD, 15 tests and 139 subtests are red, all on `LLM_` subtests or the r4 source text. Every `LLM|` subtest passes at HEAD. Green-ability: 192 passed. Mutants: 13 of 13 killed.

### Failure inventory (r4)

Each line is input + state → wrong output, and the test that catches it.

| # | Input + state → wrong output | Caught by |
|---|---|---|
| F1 | documented key in a mixed list for a `meta` agent in `AUTO` → M-6 at construction, so the §4 snippet does not run | AC-1 subtest `shape="LLM_"`; MetaRelayTests case "LLM_ key in a mixed list beats META_API_KEY" |
| F2 | documented key beside a kimi, deepseek, mistral, glm or minimax model, with or without `meta` configured → bound to that provider by elimination and relayed to that vendor (EC-17) | `test_a_meta_key_in_either_shape_goes_to_meta_beside_every_provider_that_takes_unproven_keys`; AC-17 (i) agent test |
| F3 | `anthropic` primary, relayed 401, `kimi` fallback, `MOONSHOT_API_KEY` unset → the Meta key rides on the kimi envelope (S4 R-1, R-3) | `MetaAgentTests::test_a_meta_key_in_either_shape_never_rides_on_a_kimi_fallback_that_holds_no_key_of_its_own` |
| F4 | lone Meta key, either shape, for a `deepseek`, `kimi`, `mistral`, `glm` or `minimax` config → bound to that vendor instead of M-18 | `ConfiguredPrimaryTests::test_a_lone_meta_key_for_a_provider_that_takes_unproven_keys_is_refused_with_m18` |
| F5 | malformed `LLM_` key (word ID, `.` in the secret, no secret, trailing separator, `LLM_<id>` then `\|`, bare `LLM_`) on any root → bound to an open provider instead of M-6 | `UniqueAssignmentTests::test_a_malformed_llm_key_is_refused_at_construction_on_every_root_whatever_its_providers`; `TableFAndATests::test_every_meta_shaped_key_is_reserved_to_meta_and_no_provider_takes_it_unproven` |
| F6 | missing ID (`LLM__…`) → same as F5 | reserved test; table F unproven rows |
| F7 | non-ASCII digit ID or non-ASCII secret letter → proven `meta` by a `\d` or `\w` class (D-9) | table F unproven rows "LLM_ non-ASCII digit ID" and "LLM_ non-ASCII secret". Through a root these keys are refused earlier by the printable-ASCII check (M-6b), so the provider_of table is the seam. |
| F8 | whitespace: a padded `LLM_` entry or a padded `META_API_KEY` → not stripped, or relayed padded | MetaRelayTests case "LLM_ META_API_KEY with no list"; padded duplicate in the M-7 test. An inner space is M-6b, generic, not re-tested. |
| F9 | both shapes in one list → bound to two providers instead of M-7 | `test_two_meta_keys_in_different_shapes_are_refused_and_the_same_documented_key_twice_is_one_key` |
| F10 | the same documented key twice → refused instead of one key | same test |
| F11 | `META_API_KEY` in the documented shape, no list → not relayed | MetaRelayTests case "LLM_ META_API_KEY with no list" |
| F12 | list key `LLM_` beside `META_API_KEY` `LLM\|` → the variable wins | MetaRelayTests case "LLM_ key in a mixed list beats META_API_KEY" |
| F13 | `VIDBYTE_MANAGED` Muse call with an `LLM_` list key and `META_API_KEY` set → refused at construction, or the variable read or a key sent | AC-4 subtest `listed="LLM_"` |
| F14 | `DIRECT` Muse call with an `LLM_` key → refused, or not sent as `Bearer` to `https://api.meta.ai/v1/chat/completions` | modes DIRECT subtest `shape="LLM_"` |
| F15 | lowercase `llm_`, `LLM-`, `LLMx` → reserved (over-reach, INV-17 and EC-8) | reserved test, near-miss half; table F unproven row "lowercase llm_" |
| F16 | the Meta row widened with a word ID, `[!-~]+`, `\d`/`\w`, ignore-case, a reserved `LLM`, or `LLM\|` dropped; another row, the order, or a flag changed (D-8, D-9, INV-17) | `NamesAndConstantsTests::test_the_meta_row_is_the_section_8_5_row_and_every_other_row_keeps_its_rule` plus the behavior rows (see the mutation table) |
| F17 | the Meta-row comment without `LLM_`, the URL or the 2026-10-17 date, wider than 72 columns, or with an example key (AC-18) | `KeyFormatSourceTests::test_the_comment_above_the_meta_row_names_the_llm_shape_and_cites_metas_page` |
| F18 | the registries README meta row without both patterns (the `LLM_` one first), Meta's 2026-10-17 sentence, the error page, or #1027's kept 2026-10-15 text, or with an example key | `KeyFormatSourceTests::test_the_registries_readme_meta_row_quotes_metas_llm_sentence_and_keeps_the_older_source` |
| F19 | fork or handoff to Muse with an `LLM_` key in the parent list | not written (see below) |

### Coverage map (r4)

| Spec ID | Test | Level | Red at HEAD (input + state → wrong output) | Why it cannot pass vacuously |
|---|---|---|---|---|
| FR-9, INV-16, AC-16 (provider_of) | `pk/test_provider_keys_matching.py::TableFAndATests::test_each_table_f_sample_proves_its_provider_and_every_unsourced_shape_is_unproven` (extended: 3 proven `LLM_` rows, 10 unproven rows) | unit | `provider_of(K_META_DOC)` → None, not META (3 subtests) | Expected providers are spelled from the spec, never read from `KEY_FORMATS`. The 10 unproven rows pass at HEAD and exist to kill the m3, m7, m8 and m9 mutants. |
| INV-16, EC-8, AC-17 (iii), INV-17 | `…matching.py::TableFAndATests::test_every_meta_shaped_key_is_reserved_to_meta_and_no_provider_takes_it_unproven` (new) | unit | 8 `LLM_`-shaped keys × 8 open providers → `accepts_unproven` True (64 subtests) | Runs over every `ModelProvider`. The near-miss half asserts True for open providers, so a test that reserved everything would fail it. |
| INV-16, EC-17, FR-9 | `…matching.py::UniqueAssignmentTests::test_a_meta_key_in_either_shape_goes_to_meta_beside_every_provider_that_takes_unproven_keys` (new) | unit | `{anthropic, kimi: <Meta key>}` instead of `{anthropic, meta}` for all 5 providers × meta configured or not; a meta primary with a DeepSeek key raises (12) | Compares the whole `key_view`. The `LLM\|` subtests pass at HEAD, so the test is not red for an unrelated reason. |
| INV-16, M-7 | `…matching.py::UniqueAssignmentTests::test_two_meta_keys_in_different_shapes_are_refused_and_the_same_documented_key_twice_is_one_key` (new) | unit | M-6 at index 1 instead of M-7; with a kimi backup no error at all; the same key twice gives M-6 (3) | Checks `details.indexes == (0, 1)` and `provider == "meta"`, so an M-6 or M-19 cannot satisfy it. |
| AC-17 (iii), EC-8, INV-16 | `…matching.py::UniqueAssignmentTests::test_a_malformed_llm_key_is_refused_at_construction_on_every_root_whatever_its_providers` (new) | unit (through the roots) | 6 malformed keys × 6 roots (kimi and deepseek in `AUTO`; mistral, glm and minimax in `DIRECT`; an Agent with a kimi fallback) → "ConfigurationError not raised" (36) | Checks `details.index`, `details.length` and each configured provider in `details.providers`, plus no key text. The `meta` root passes at HEAD, which shows the assertions accept M-6. |
| AC-17 (ii), EC-17 | `…matching.py::ConfiguredPrimaryTests::test_a_lone_meta_key_for_a_provider_that_takes_unproven_keys_is_refused_with_m18` (new) | unit (TextModelConfig) | `LLM_` × 5 providers → no error, so the key would go to that vendor (5) | Requires `details.provider == p` and `providers == ["meta"]`. The `LLM\|` subtests pass at HEAD with the same assertions. |
| AC-17 (i), EC-17, INV-4 (S4 R-1, R-3) | `pk/test_provider_keys_agents.py::MetaAgentTests::test_a_meta_key_in_either_shape_never_rides_on_a_kimi_fallback_that_holds_no_key_of_its_own` (new) | agent, real transport seam | the kimi envelope relays the `LLM_` key (2: meta configured or not) | Asserts the call order `["anthropic", "kimi"]` and the reply from kimi, so the fallback really ran. Kills `meta_key_to_keyless` in both shapes, at HEAD rows and green. |
| AC-1, AC-16 (i) | `pk/test_provider_keys_acceptance.py::SnippetAcceptanceTests::test_meta_muse_snippet_relays_the_meta_key_for_the_agent_and_sends_the_paid_call_without_it` (extended: subTest per shape) | acceptance | `shape="LLM_"`: M-6 raised by the §4 snippet's `Agent(...)` | Every r3 assertion kept and applied to both shapes. |
| AC-4, INV-3 | `…acceptance.py::TextCallAcceptanceTests::test_vidbyte_managed_meta_never_reads_meta_api_key_or_sends_a_meta_key` (extended: list `K_META_DOC`, variable `K_META`) | acceptance | M-6 at construction | `META_API_KEY` reads are recorded by `RecordingEnviron`, and both keys are absent from the request. |
| AC-16 (i), (ii), INV-2, INV-4 | `pk/test_provider_keys_wire_contract.py::MetaRelayTests::test_a_meta_call_relays_the_lists_meta_key_before_meta_api_key_stripped_and_no_other_key` (extended: 2 rows) | wire contract | the mixed-list row raises M-6. The `META_API_KEY` row passes at HEAD (the variable is trusted by its name) and pins AC-16 (ii). | The relay header must equal the list key, and the key must be absent everywhere else in the request. |
| AC-16 (iii), INV-11 | `pk/test_provider_keys_modes.py::UnsendableKeyTests::test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct` (extended: subTest per shape, exact URL) | mode | `shape="LLM_"`: M-6 | Exactly one request, to the exact Meta URL, with `Bearer <key>`; so no gateway call. |
| §8.5, D-8, D-9, INV-17 | `pk/test_provider_keys_contract.py::NamesAndConstantsTests::test_the_meta_row_is_the_section_8_5_row_and_every_other_row_keeps_its_rule` (new) | contract | META row `(("LLM\|",), …)` ≠ the §8.5 row | The 5 other rows pass at HEAD with literal `base_commit` prefixes, patterns and flags. |
| §8.5 (grant 1) | `…contract.py::NamesAndConstantsTests::test_the_key_format_tables_follow_table_f_table_a_and_the_reserved_prefixes` (`:71` changed by grant) | contract | last set `{"LLM\|"}` ≠ `{"LLM\|", "LLM_"}` | Unchanged otherwise. |
| AC-18, row 4(b) | `…contract.py::KeyFormatSourceTests::test_the_comment_above_the_meta_row_names_the_llm_shape_and_cites_metas_page` (new) | doc contract | the HEAD block lacks `LLM_` and `2026-10-17`, and its first line is 74 columns (4) | Fails if no comment sits directly above the row. Reads `MATCHER_SOURCE`, a module constant. |
| AC-18, row 5 | `…contract.py::KeyFormatSourceTests::test_the_registries_readme_meta_row_quotes_metas_llm_sentence_and_keeps_the_older_source` (new) | doc contract | the pattern pair, the date, the quote and the error page are missing (4). The kept 2026-10-15 text passes. | Requires exactly one `\| meta \|` row. `REGISTRIES_README` is a module constant. |
| FR-9 (CMP) | `pk/test_provider_keys_property.py` (`POOL` and `PROVEN` gain `K_META_DOC`) | property | passes at HEAD (INV-9 holds for any table) | The vacuity guard (`> CASES // 8` of each outcome) still passes at HEAD and green. |

### Tests deliberately NOT written (r4)

| Spec ID / case | Why no new test |
|---|---|
| AC-11 (relayed Meta 401 → anthropic fallback) in the `LLM_` shape | Re-proves AC-1 (`LLM_` relayed on the meta call) plus AC-17 (i) (no key on the other provider's call). |
| EC-11 fork or handoff to Muse with an `LLM_` parent key | The child carries the root's matched record unchanged (D-13), and that is shape-agnostic. F2 and the AC-1 subtest cover how the record is built. |
| AC-14 leaks with an `LLM_` key | Header placement, error wording and redaction do not depend on the key's shape. The leak tests use `LEAKED_KEY` and `K_META` canaries. |
| EC-18 (workaround: an off-class secret through `META_API_KEY`) | byok EC-14 already pins that the variable is trusted by its name, and the MetaRelayTests "META_API_KEY with no list" rows relay it. The `api_keys` half of EC-18 is the F5 dotted-secret case. |
| EC-19 (another vendor's key proven `meta`) | An accepted limitation (A-7). A test would only re-prove the proven-row samples and the M-18 test. |
| Padded `LLM_` list entry | Stripping is generic (`_entries`). It is covered for the `LLM\|` shape and by the padded duplicate in the M-7 test. |
| A no-misroute property test over random lists | Re-proves the reserved test and the either-shape test. Instead, `POOL` gained `K_META_DOC`, so INV-9 and INV-10 run over both shapes. |
| AC-13's r4 text "`LLM_` or `LLM\|` (Meta)" in the root README | Outside the grant ("AC-13 stays as is"). The existing assertion still holds after the r4 edit. **Open item:** no test binds the `LLM_` half of the root README Prefixes bullet. |
| AC-18 clause "today's page no longer shows that form" | A paraphrase with no fixed wording, left to the S5 review. Every fact AC-18 fixes in words is bound. |

### Red run (r4)

Per file, at HEAD `4af4d8e0` (tests) over `121911df` (production):

```
$ PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_provider_keys/test_provider_keys_<file>.py -q -p no:cacheprovider
matching: 6 failed, 32 passed in 1.02s
agents: 1 failed, 25 passed in 0.94s
acceptance: 2 failed, 12 passed in 0.91s
wire_contract: 1 failed, 13 passed in 0.97s
modes: 1 failed, 18 passed in 0.89s
contract: 4 failed, 12 passed in 0.88s
property: 2 passed in 1.25s
```

Area:

```
$ PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_provider_keys tests/features/sdk_managed_text -q -p no:cacheprovider
FAILED test_provider_keys_acceptance.py::SnippetAcceptanceTests::test_meta_muse_snippet_relays_the_meta_key_for_the_agent_and_sends_the_paid_call_without_it
FAILED test_provider_keys_acceptance.py::TextCallAcceptanceTests::test_vidbyte_managed_meta_never_reads_meta_api_key_or_sends_a_meta_key
FAILED test_provider_keys_agents.py::MetaAgentTests::test_a_meta_key_in_either_shape_never_rides_on_a_kimi_fallback_that_holds_no_key_of_its_own
FAILED test_provider_keys_contract.py::NamesAndConstantsTests::test_the_key_format_tables_follow_table_f_table_a_and_the_reserved_prefixes
FAILED test_provider_keys_contract.py::NamesAndConstantsTests::test_the_meta_row_is_the_section_8_5_row_and_every_other_row_keeps_its_rule
FAILED test_provider_keys_contract.py::KeyFormatSourceTests::test_the_comment_above_the_meta_row_names_the_llm_shape_and_cites_metas_page
FAILED test_provider_keys_contract.py::KeyFormatSourceTests::test_the_registries_readme_meta_row_quotes_metas_llm_sentence_and_keeps_the_older_source
FAILED test_provider_keys_matching.py::TableFAndATests::test_each_table_f_sample_proves_its_provider_and_every_unsourced_shape_is_unproven
FAILED test_provider_keys_matching.py::TableFAndATests::test_every_meta_shaped_key_is_reserved_to_meta_and_no_provider_takes_it_unproven
FAILED test_provider_keys_matching.py::UniqueAssignmentTests::test_a_malformed_llm_key_is_refused_at_construction_on_every_root_whatever_its_providers
FAILED test_provider_keys_matching.py::UniqueAssignmentTests::test_a_meta_key_in_either_shape_goes_to_meta_beside_every_provider_that_takes_unproven_keys
FAILED test_provider_keys_matching.py::UniqueAssignmentTests::test_two_meta_keys_in_different_shapes_are_refused_and_the_same_documented_key_twice_is_one_key
FAILED test_provider_keys_matching.py::ConfiguredPrimaryTests::test_a_lone_meta_key_for_a_provider_that_takes_unproven_keys_is_refused_with_m18
FAILED test_provider_keys_modes.py::UnsendableKeyTests::test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct
FAILED test_provider_keys_wire_contract.py::MetaRelayTests::test_a_meta_call_relays_the_lists_meta_key_before_meta_api_key_stripped_and_no_other_key
15 failed, 177 passed in 2.35s
```

(The `FAILED` paths are shortened by dropping `tests/features/sdk_provider_keys/`.) The 177 are the 183 r3 tests minus the 6 extended ones above, so the rest of the area still passes. Subtest audit under `unittest` (scratch `s2b_sub.py`, which counts each failing subtest): 139 failing subtests in the 15 tests. Every one is an `LLM_` subtest, the §8.5 row, or the r4 source text. No `LLM|` subtest fails. Reasons: "ConfigurationError not raised" (41: the misroute or the missing M-18); "True is not false" (64: `LLM_` not reserved); `kimi` in place of `meta` in `key_view` (10); a ConfigurationError where the call must succeed (7: M-6 in AC-1, AC-4, the relay row and DIRECT; the meta-primary split twice; the same documented key twice); M-6 or no error where M-7 is due (2); `provider_of` None (3); the kimi relay header holding the key (2); the section 8.5 row and the `:71` pin (2); and the r4 source text (8).

### Green-ability (r4)

The scratch pytest plugin `<scratchpad>/plugins/s2b_r4.py` (not committed) rebinds the Meta row of `ProviderKeyMatcher.KEY_FORMATS` in memory to the exact §8.5 row. It also writes scratch copies of `provider_keys.py` and the registries README, carrying the row 4(b) example comment and the row 5 text, and points the contract module's `MATCHER_SOURCE` and `REGISTRIES_README` at them.

```
$ S2B_MODE=green PYTHONPATH="<worktree>;<scratchpad>/plugins" env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_provider_keys tests/features/sdk_managed_text -q -p no:cacheprovider -p s2b_r4
192 passed in 1.44s
```

### Mutation check (r4)

All mutants are applied in memory on top of the green state (`S2B_MODE=<mutant>`, same command). `m4` is `S4E_MUTANT=meta_key_to_keyless -p s4e_mutants` on top of green.

| Mutant | Area result | Killed by (besides the §8.5 pin) |
|---|---|---|
| m1 `LLM_` in prefixes, pattern unchanged | 10 failed, 182 passed | table F `LLM_` rows; either-shape; M-7; M-18; AC-1, AC-4, AC-16 (i) and (iii); agent AC-17 (i) |
| m2 pattern widened, `LLM_` not reserved | 4 failed, 188 passed | reserved test; malformed-key M-6 test; `:71` pin |
| m3 word ID in the `LLM_` branch | 3 failed, 189 passed | table F "LLM_ word ID"; malformed M-6 ("word ID") |
| m4 `meta_key_to_keyless` (S4 R-3) | 1 failed, 191 passed | agent AC-17 (i), 4 of 4 subtests (both shapes; at HEAD rows too, where the `LLM\|` subtests fail under the mutant) |
| m5 `LLM\|` prefix and branch dropped | 25 failed, 167 passed | every r3 Meta test |
| m5b `LLM\|` prefix dropped, branch kept | 4 failed, 188 passed | `accepts_unproven` `bad_meta`; reserved test; `:71` pin |
| m6 `LLM` reserved instead of `LLM_` | 3 failed, 189 passed | reserved test, near misses `LLM-` and `LLMx`; `:71` pin |
| m7 `\d` and `\w` in the `LLM_` branch | 2 failed, 190 passed | table F non-ASCII digit and letter rows |
| m8 `[!-~]+` secret (D-9 rejected) | 3 failed, 189 passed | table F dotted secret; malformed M-6 ("dotted secret") |
| m9 ignore-case flag | 2 failed, 190 passed | table F "lowercase llm_" and "lowercase llm pipe" |
| m11 README row copies an example key | 1 failed, 191 passed | AC-18 README test |
| m12 a 75-column comment line | 1 failed, 191 passed | AC-18 comment test |
| m13 neither source dated 2026-10-17 | 2 failed, 190 passed | both AC-18 tests |

13 of 13 killed. Every row mutant is also killed by a behavior test, not only by the §8.5 pin.

### R-2, R-6 and R-7 results

- **R-2:** `git diff -U0 origin/main...HEAD -- '*.py' | grep -E '^\+\s*#' | awk 'length($0) > 73'` prints nothing (0 lines), new comments included. Of S4's 52 lines, 9 were rewritten by the r4 commit (corrected or re-indented) and 43 were wrapped in place by the tidy commit (`<scratchpad>/plugins/s2b_wrap.py`, which checks that the words are unchanged). Pre-existing wide comments that S2 did not touch are untouched.
- **R-6:** COMMON MODIFICATION PATTERNS now names `SERVED` (`pk/test_provider_keys_modes.py:6`), `PROVIDER_KEYS` (`pk/test_provider_keys_failures.py:6`), `POOL`/`PROVEN` for a new key shape (`pk/test_provider_keys_property.py:6`), `MANAGED_PROVIDERS` (`mt/test_managed_text_deadline.py:6`), `ORACLE_KEYS`/`CAP_FIELD`/`EMITTED_KEYS`/`FULL_CONFIG` (`mt/test_managed_text_wire_contract.py:6`) and `_CHAT_PROVIDERS` (`mt/managed_text_fixtures.py:7`). `RELAY_KEYS`/`CAP_FIELD` (`pk/…wire_contract.py:6`) and `MANAGED_MODELS`/`ORACLE_KEYS` (`mt/…acceptance.py:6`) were already named. The `ORACLE_KEYS` trap left `mt/FEATURE.md` Known Failure Modes, which lists feature failures (feature_test_packs doctrine). It is now WHAT NOT TO DO item 3 in the two headers that hold `ORACLE_KEYS`, and it names both Meta shapes.
- **R-7:** `py -3.11 -m ruff check --no-cache --isolated --preview --select E301,E302,E303,E305 <the 14 branch-changed .py files>` → `All checks passed!`. The new test inserted before `class NonTextModelKeyTests` brings its blank lines to two. `META_UNSUPPORTED_MODEL` and `META_MISSING_KEY` now sit in the constants block after `RELAY_FORBIDDEN`. `ruff --select F,E9` is clean, and `python lint/run.py` prints `SDK-LINT: PASS`.

### Before/after of every edit to an existing test or fixture (r4)

All edits are inside the r4 grant (pipeline.md, S2 delta grant). No assertion was weakened, skipped or deleted.

| File | Symbol | Before | After | Grant |
|---|---|---|---|---|
| `pk/test_provider_keys_contract.py` | `test_the_key_format_tables_…` `:71` | last prefix set `{"LLM\|"}` | `{"LLM\|", "LLM_"}` | (1) |
| `pk/provider_keys_fixtures.py` | header `:9`; `K_META` comment; new `K_META_DOC`; `__all__` | reserved list ends `LLM\|`; comment "(LLM pipe app id pipe secret)" | reserved list adds `LLM_`; comment names the 2026-10-15 form kept by Q-7; fixture and export added | (2), (3) |
| `pk/test_provider_keys_matching.py` | table F test | 10 proven rows, 12 unproven | +3 proven `LLM_` rows, +10 unproven rows | (2) |
| same | `test_accepts_unproven_…` comment | "LLM pipe is reserved to meta …" | wrapped, and points to the `LLM_` test | (3) |
| same | `test_a_meta_key_proves_meta_in_any_order_…` two comments | "an LLM pipe key is meta's …"; "Meta issues only LLM pipe keys" (false) | "a Meta key …, this test uses the pipe form"; "Every Meta key starts with LLM_ or LLM pipe" | (3) |
| `pk/test_provider_keys_acceptance.py` | AC-1 snippet test | one run with `K_META` | the same body in `for shape, meta_key in (("LLM\|", K_META), ("LLM_", K_META_DOC))` under `subTest`; `K_META` → `meta_key` in the environment, the relay-header assertion and the paid-call absence check; comments wrapped | (2) |
| same | AC-4 test | list `K_META`, variable `K_META_2` | loop over that pair and (`K_META_DOC`, `K_META`) under `subTest`; assertions identical | (2) |
| `pk/test_provider_keys_modes.py` | DIRECT Muse test | one run with `K_META`; URL `startswith` | `subTest` per shape; `startswith` kept, plus exact URL `https://api.meta.ai/v1/chat/completions` (AC-16 (iii)); comments wrapped | (2) |
| `pk/test_provider_keys_wire_contract.py` | `RELAY_KEYS` comment; MetaRelayTests cases | "format-bound (LLM pipe form)"; 3 cases | names both shapes; +2 `LLM_` cases | (2), (3) |
| `pk/test_provider_keys_property.py` | `POOL`, `PROVEN`; CMP line | `K_META` only | `+ K_META_DOC`; CMP names a new key shape | (2), (3) |
| `pk/test_provider_keys_agents.py` | blank lines before `NonTextModelKeyTests` | 1 | 2 (new test inserted above it) | (4) |
| `pk/test_provider_keys_failures.py` | `META_UNSUPPORTED_MODEL`, `META_MISSING_KEY` | mid-file before `MetaGatewayFailureTests` | constants block, after `RELAY_FORBIDDEN`; bytes of the values unchanged | (4) |
| `mt/test_managed_text_acceptance.py`, `mt/test_managed_text_wire_contract.py` | `ORACLE_KEYS[META]` comment; WHAT NOT TO DO | "format-bound (LLM pipe digits pipe secret)" | names both shapes and says the oracle uses the pipe form; item 3 holds the moved trap | (3) |
| `mt/test_managed_text_acceptance.py` | AC-13 (c) comment | "lists LLM pipe as the prefix" | "as a prefix …; since r4 it reads `LLM_` or `LLM\|` (Meta), which still holds this text" | (3) |
| `mt/FEATURE.md` | Known Failure Modes `:70` | the `ORACLE_KEYS` trap with the pipe shape only | corrected to both shapes (r4 commit), then moved to the headers (tidy commit) | (3) |
| 12 files | 43 comment lines (R-2) | single lines of 73 to 164 columns | PEP 8 blocks of at most 72 columns, same words | (3) |

### Notes for the repair agent (implementer)

- **Change only** spec §12.3 rows 4 and 5, plus the root README Prefixes bullet (row 2(c), r4 text). Row 4 is `vidbyte/lib/registries/provider_keys.py`: the Meta row becomes exactly the §8.5 row (prefixes `("LLM|", "LLM_")`, pattern `LLM(?:\|[0-9]+\|[A-Za-z0-9_-]+|_[0-9]+_[A-Za-z0-9_-]+)`, no flags, still last), and the comment directly above it becomes a block of at most 72 columns. Row 5 is the registries README meta row.
- **The comment block** (AC-18 test) must sit directly above the line that starts `(ModelProvider.META,`. Every line must be at most 72 columns with its 8-space indent. The joined text must contain `LLM_`, `LLM|`, `https://dev.meta.ai/docs/authentication` and `2026-10-17`, and no `LLM_` or `LLM|` followed by a digit.
- **The registries README `| meta |` row** (AC-18 test) must contain, verbatim:
  - the Pattern cell `` `LLM_[0-9]+_[A-Za-z0-9_-]+` or `LLM\\|[0-9]+\\|[A-Za-z0-9_-]+` ``, with the two backslashes as today;
  - `https://dev.meta.ai/docs/authentication` and `2026-10-17`;
  - ``API keys start with `LLM_`, followed by a numeric ID and the secret, separated by underscores``;
  - `https://dev.meta.ai/docs/error-handling`;
  - the kept `2026-10-15` and `API keys look like this` text.
  - It must not contain an example key.
- **Do not change** any test file or pack doc, any other `KEY_FORMATS` row, the row order, `FORMAT_BOUND_PROVIDERS`, `RESERVED_PREFIXES`, the `OPENAI_*` prefixes, or any message. The §8.5-row test pins the other five rows literally.
- After rows 4 and 5, `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_provider_keys tests/features/sdk_managed_text -q -p no:cacheprovider` must end `192 passed`.
