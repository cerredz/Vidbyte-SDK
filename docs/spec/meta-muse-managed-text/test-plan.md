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
