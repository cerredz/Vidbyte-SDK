# Adversarial review: Agents take vidbyte_api_key and a list of provider api_keys (SDK half)

Diff reviewed: `origin/main...8bd1963d` (merge base 595a7260; code final at 3481ed66) · Lenses: conformance, conventions, engineering · Verifier: reports/S4-findings-verifier.md

## Verdict
MERGEABLE AFTER FIXES — routing, billing, and secret handling hold, but the verifier confirmed one AGENTS.md §1 call-depth Blocker, nine Majors, and eight Minors. The nine Majors are:

- one ordering bug against INV-8;
- a weakened S014 lint rule;
- a worsened A002 count;
- one `match` violation;
- public annotations that reject the documented list (this one needs a ruling);
- four guard lines that no test covers. For each, the verifier re-ran the mutation, and it survives the full suite (`4101 passed, 13 skipped`).

Every Blocker and Major below was reproduced by the verifier on a private `git archive 8bd1963d` copy. Nothing rests on a reviewer's output.

## Confirmed findings (must fix) — 10

| ID | Severity | Lens | Where (path:line) | Finding (claim) | Evidence (verifier's own) | Smallest fix | Owner | Status |
|---|---|---|---|---|---|---|---|---|
| R-1 | Blocker | conventions (R-V1) | `vidbyte/lib/dataclasses/model_configs.py:119`, `:162`, `:135`, `:149` | `validate()` and `resolved_api_key()` call `credentials()`, and `credentials()` calls three of its own helpers (`normalized_provider`, `_refuse_missing_provider_key`, `_require_relayable_length`). That makes six two-level chains. AGENTS.md §1: "a function may call another of its own functions, but that second function should not call a third … lift that call up into the main function". Spec §12.4 caps `credentials()` at "at most one own helper … and that helper calls no own helper". The deviation is not reported in §17 or the S3 report. | An AST scan (`verify/calldepth.py`) finds 0 chains in `TextModelConfig` at base 595a7260 and 6 at HEAD: `validate -> credentials -> {normalized_provider, _refuse_missing_provider_key, _require_relayable_length}` and the same three from `resolved_api_key`. A diff-wide scan (`verify/chaindiff.py`) finds no other new chains. | Inline the M-8 raise into `case TextModelMode.DIRECT` and the M-21 length check, with its `@intent relayed-key-fits-the-gateway-header` block, into `case TextModelMode.AUTO`. Delete both helpers. `credentials()` then calls one leaf own helper (`normalized_provider`), which is exactly what §12.4 allows. It grows to about 47 lines, still within house style. Update its narration in the same edit. | code | fixed @66bfa272 |
| R-2 | Major | engineering (R-E2) | `vidbyte/lib/registries/provider_keys.py:204`; test gap at `tests/features/sdk_provider_keys/test_provider_keys_matching.py:368-373` | No test covers the record check that refuses a Vidbyte key filed as a provider key (INV-13, the §17 deviation). If the clause is dropped, DIRECT sends the Vidbyte key to the vendor. | The verifier's mutation `kk_record_allows_vidbyte_key` drops `and not key.startswith(VIDBYTE_API_KEY_PREFIX)`. Full suite: `4101 passed, 13 skipped in 36.85s` (sequential re-run), so the mutation survives. Probe at HEAD: M-20 "…key 0 does not fit deepseek". Under the mutation: `BUILT; DIRECT provider key -> VB`. | Add test T-2 (below). | test | fixed @f1f6a4f4 |
| R-3 | Major | engineering (R-E4) | `vidbyte/agents/aggregation.py:219-220`; test gap at `tests/features/sdk_provider_keys/test_provider_keys_agents.py:272` | No test proves that the default aggregator (the agent's own provider and model) is a primary. If those two lines go, an aggregate whose list lacks that provider's key builds, and every synthesis call goes Vidbyte-paid silently (D-27, NFR-10). | The verifier's mutation `vv_default_aggregator_not_primary` survives: `4101 passed, 13 skipped in 39.63s`. Probe at HEAD: M-18 "…holds keys for openai but none for anthropic". Under the mutation: `BUILT`. | Add test T-3. | test | fixed @e6ae4990 |
| R-4 | Major | engineering (R-E3) | `vidbyte/lib/dataclasses/model_configs.py:137-141`; test gap at `tests/features/sdk_provider_keys/test_provider_keys_acceptance.py:257-270` | The AC-13 check "never reads the provider variable" cannot fail. It passes `api_keys=[K_OPENAI]`, so `find_provider_api_key` returns the record's key before it reads the environment. If VIDBYTE_MANAGED were changed to resolve the provider key, it would break INV-5. A developer who still has the old habit (a Vidbyte key in `OPENAI_API_KEY`, EC-13) would then get M-14 in that mode. | The verifier's mutation `ad_managed_reads_provider_key` survives: `4101 passed, 13 skipped in 38.72s`. Probe: HEAD gives `credentials ok: mode=vidbyte_managed provider_key=None`. Under the mutation: `ConfigurationError: OPENAI_API_KEY holds a Vidbyte API key…`. | Add test T-4. | test | fixed @32cf23e5 |
| R-5 | Major | engineering (R-E1) | `vidbyte/lib/runners/utility.py:130`, `vidbyte/lib/agents/modality_detector.py:226`; test gap at `tests/features/sdk_provider_keys/test_provider_keys_agents.py:421-436` | The AC-23 test uses only single-key lists, so it cannot tell `key_for(provider)` from "first key". If a non-text runner took the first key, it would send another vendor's key to OpenAI's image endpoint (INV-3, NFR-10). | Both mutations survive. `o_runner_first_key`: `4101 passed, 13 skipped in 36.47s` (sequential re-run). `an_detector_first_key`: `4101 passed, 13 skipped in 40.18s`. With `api_keys=[K_XAI, K_OPENAI]`, HEAD gives `K_OPENAI` at both sites. Under the mutations, it gives `K_XAI` at the mutated site. | Add test T-5. | test | fixed @d971f491 |
| R-6 | Major | conformance (R-C1) | `vidbyte/lib/dataclasses/model_configs.py:94-100` | A gateway-mode `TextModelConfig` matches keys (M-18) before the INV-8 shape check. So an unserved provider or an endpoint, combined with another provider's key, raises M-18, whose remedy cannot work, instead of M-12 or M-13 naming DIRECT. INV-8 says this config is refused "before any key or environment is read". | `verify/probe/probe_c1.py` at HEAD: `AUTO mistral + xai key: ConfigurationError: …holds keys for xai but none for mistral… Vidbyte's own mistral account`. The same config with no keys raises `UnsupportedProviderError: The Vidbyte gateway serves only…`. Endpoint plus anthropic key: M-18, not M-13. With the fix applied (`c1_shape_before_match`), the probe gives M-12 and M-13, and the full suite passes (`4101 passed, 13 skipped in 39.42s`). No S2 test pins the old order, and INV-24 at the Agent root is untouched. | Move `if self.mode is not TextModelMode.DIRECT: self._require_gateway_shape(self.normalized_provider())` above the `ProviderKeyMatcher.match` call, and reorder the comment and docstring. Then add test T-6, which is red at HEAD and green with the fix. | code (+ test T-6) | fixed @bae3534e |
| R-7 | Major | conventions (R-V5) | `vidbyte/lib/dataclasses/model_configs.py:256-261` | `TextCredentials.__post_init__` dispatches on mode with an if/elif/else ladder. Its silent `else` would give a future mode AUTO's key rule. §12.4 requires "Mode dispatch uses `match` with an explicit `case _:` that raises", and `credentials()` in the same file follows that rule. | Read at `:256-261`: `if … DIRECT … elif … VIDBYTE_MANAGED … else: fits = has_vidbyte_key and (…)`. | `match self.mode:` with three cases that set `fits`, plus `case _: raise ConfigurationError("TextCredentials.mode must be a TextModelMode value.")`. | code | fixed @c72387d3 |
| R-8 | Major | conventions (R-V3) | `vidbyte/lib/dataclasses/model_configs.py:273` (`relays`), `vidbyte/agents/settings/fallback.py:98` (`named_providers`), `:165` (`_inherited_provider`), `vidbyte/agents/aggregation.py:341` (`_build_aggregator`) | The A002 count rose from 584 to 585 while lint still passed. §12.4 says "Every business rule has an `@intent` within 20 lines of its `def`". `relays` decides whether a secret goes on the wire. | `lint/run.py --rule A002 --all --format json`: head `found 585`, base `found 584`. Added: the four functions listed in Where. Removed: aggregation `__init__` and `_build_proposer_agent`, and fallback `to_fallback`. | Add one `# @intent <slug>` block (≤ 72 columns) inside each of the four functions, then re-run A002 and expect 581. Diff the finding set, not only the count: neighbouring `@intent` blocks cover `resolved_endpoint` and `normalized_provider` only because they are close by, so R-1, R-6, and R-7 edits can move them. | code | fixed @ab841c1f |
| R-9 | Major | conventions (R-V2) | `lint/rules/s014_provider_model_registry_parity.py:46-48`; header `:9` | S014 treats any non-literal, empty, or missing `API_KEY_ENV_VARS` as an alias and passes CLEAN. The base rule reported every provider for the same edits. The S014 ruling (0d0b484b) allowed reading `jev.py` only "when the registry attribute is not a literal", on the condition that "Parity stays equally strict". `{}` is a literal. The header at `:9` claims the opposite of what the code does. | `verify/s014_mut.py`, run on edits to `models.py:91`. Base 595a7260: `= {}`, deletion, and `= DEFAULT_TEXT_MODELS` each give `found 14 REGRESSED`. HEAD: `= {}`, deletion, `= DEFAULT_TEXT_MODELS`, and `= OTHER_TABLE` each give `found 0 CLEAN`. The `jev.py`-side control gives `found 1 REGRESSED`. The test suite does catch an emptied table at runtime (managed-text tests fail), so this weakens the lint rule but ships no wrong result. | Set `aliased` only when the `ProviderModelRegistry` body `AnnAssign`s `API_KEY_ENV_VARS` to `ast.Name(id="PROVIDER_API_KEY_ENV_VARS")`; otherwise keep the class-dict result. Correct header `:9`, and record the mutation matrix in the S3 proof. The verifier's prototype (`verify/s014fix`) gives `found 14` at `models.py` for all four registry-side edits, `found 1` at `jev.py` for the control, and CLEAN unmutated. | code | fixed @e164d700 |
| R-10 | Major | conventions (R-V4) | `vidbyte/lib/dataclasses/model_configs.py:58`, `vidbyte/agents/jev/settings.py:132`, `:285`, `vidbyte/paradigms/context_minimal_fanout/types.py:430` | The public `api_keys` annotations (`ProviderKeys`, `tuple[str, ...]`) reject the list form that the spec, the ACs, and the repo's own scripts pass. mypy (and so an IDE) flags `TextModelConfig`, `JevAgentSettings`, `JevRunBriefSettings`, and `AgentRoleSettings` calls. The spec prescribes these annotations (§8.5, §9.1, row 7), so the fix **needs a ruling** (OPEN ITEM 1). | `mypy --config-file lint/mypy.ini` on `verify/probe/typing_probe.py` gives four `[arg-type]` errors: `"list[str]"; expected "ProviderKeys"` (×2) and `expected "tuple[str, ...]"` (×2). `Agent(api_keys=[...])` is clean. A prototype of option (a) (`verify/r4a`) raises S009 from 350 to 355. All five new errors sit at read sites of the two `ProviderKeys` fields (`model_configs.py` ×4 and `jev/brief/writer.py:56`). Widening the two tuple fields adds 0 errors. | Wait for the ruling. Recommended: (a) widen all four, with narrowing at the five read sites (see OPEN ITEM 1). | code | fixed @f4e4c16c |

### Test cases for the test author (R-2 to R-6)

The verifier ran each case below from a scratch module (`verify/proposed/test_s4_verify_proposed.py`) against HEAD and against each mutant:

- At HEAD, T-2 to T-5 pass and T-6 fails.
- Each mutant fails only its own case.
- The R-6 fix tree passes all five.

Follow each file's WHAT NOT TO DO rules: import feature symbols inside the test, use the existing concatenated fake keys, and clear the environment.

- **T-2 (R-2).** File: `tests/features/sdk_provider_keys/test_provider_keys_matching.py`. Test: `test_a_hand_built_record_whose_key_does_not_fit_its_provider_is_refused_at_construction`.
  - Input: add this row to `records`: `("vidbyte key at deepseek", ProviderKeys(providers=(ModelProvider.DEEPSEEK,), keys=(VIDBYTE_KEY,)), "deepseek", VIDBYTE_KEY)`.
  - Assertion: the existing loop asserts a `ConfigurationError` on both the `Agent` and `TextModelConfig` roots, with no key text, `deepseek` in the message, and `details` `(0, "deepseek")`.
  - Kills: `kk_record_allows_vidbyte_key` (under it: "ConfigurationError not raised").
- **T-3 (R-3).** File: `tests/features/sdk_provider_keys/test_provider_keys_agents.py`. Test: `test_an_aggregate_needs_every_spec_built_models_key_unless_its_list_holds_none`, inside its cleared-environment block.
  - Input: `AggregateAgent(name="panel", system_prompt="Answer.", proposers=[("openai", "gpt-5.5")], provider="anthropic", model_name="claude-sonnet-5", api_keys=[K_OPENAI])`.
  - Assertion: it raises `ConfigurationError`, `assert_no_key_text(self, exc, K_OPENAI)` holds, and `exc.details.get("provider") == "anthropic"`.
  - Kills: `vv_default_aggregator_not_primary`.
- **T-4 (R-4).** File: `tests/features/sdk_provider_keys/test_provider_keys_acceptance.py`, class `TextCallAcceptanceTests`. New test: `test_vidbyte_managed_with_no_list_never_reads_the_provider_variable_even_when_it_holds_a_vidbyte_key`.
  - Input: `RecordingEnviron({"OPENAI_API_KEY": OTHER_VIDBYTE_KEY, "VIDBYTE_API_KEY": VIDBYTE_KEY})` and `ScriptedGateway(provider_answer(ModelProvider.OPENAI))` at `RUNNER_TRANSPORT_TARGET`. Run `TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED)).run(PROMPT)`.
  - Assertion: there is exactly one request, `provider_key_header(sent) is None`, and `"OPENAI_API_KEY" not in environment.reads`.
  - Kills: `ad_managed_reads_provider_key` (under it, M-14 is raised).
- **T-5 (R-5).** File: `tests/features/sdk_provider_keys/test_provider_keys_agents.py`, class `NonTextModelKeyTests`. New test: `test_a_non_text_runner_takes_its_own_providers_key_when_another_providers_key_comes_first`.
  - Input, in a cleared environment: `Agent(name="artist", system_prompt="Draw.", provider="openai", model_name="gpt-image-1", api_keys=[K_XAI, K_OPENAI])._runner_for_model()` and `ModalityDetector.create_runner("image", provider="openai", model="gpt-image-1", api_keys=[K_XAI, K_OPENAI])`.
  - Assertion: the runner type is `"image"`, and both `_config.api_key == K_OPENAI`.
  - Kills: `o_runner_first_key` and `an_detector_first_key`.
  - The reviewer's extra "only another provider's key → None" case is not constructible at a root (M-18 fires), so leave it out.
- **T-6 (R-6, red until the code fix).** File: `tests/features/sdk_provider_keys/test_provider_keys_modes.py`, class `GatewayShapeTests`. New test: `test_an_unserved_provider_or_an_endpoint_is_refused_before_another_providers_key_is_matched`.
  - Input: for each of AUTO and VIDBYTE_MANAGED, in a cleared environment, `TextModelConfig(provider="mistral", model="mistral-large-latest", api_keys=[K_XAI], mode=m)` and `TextModelConfig(provider="xai", model="grok-4.5", api_keys=[K_ANTHROPIC], endpoint="https://proxy.example/v1", mode=m)`.
  - Assertion: the first raises `UnsupportedProviderError`, which is not a `ConfigurationError` subclass, whose message names `TextModelMode.DIRECT`. The second raises `ConfigurationError` whose message contains `custom endpoint` and `TextModelMode.DIRECT`.
  - Kills: the current match-then-shape order.

## Refuted or downgraded by the verifier — 0 findings (3 sub-claims corrected)

| ID | Original severity | Why refuted / downgraded (evidence) |
|---|---|---|
| R-V4 sub-claim "mypy flags every README example" (now R-10) | Major (kept) | The claim is overstated. The README's `api_keys=[…]` examples (`README.md:246`, `:258`, `:1492`) and `vidbyte/agents/README.md:184` use `Agent`/`Session.resume`, whose union annotation type-checks cleanly. The errors hit `TextModelConfig`, `JevAgentSettings`, `JevRunBriefSettings`, and `AgentRoleSettings` calls, which the spec's ACs and the repo's own `scripts/test-*.py` use. The finding stands. |
| R-E1 sub-claim "add a case where the list holds only another provider's key, assert `api_key is None`" (now R-5) | Major (kept) | At any root that case raises M-18 (INV-24), and `ModalityDetector._config_options` matches with `require_primary_key=True`, so no runner is built to assert on. T-5 drops it. The other-key-first case kills both mutations. |
| R-V1 fix "credentials() then calls only … the leaf normalized_provider()" (now R-1) | Blocker (kept) | Correct, but the result still leaves `validate -> credentials -> normalized_provider`. That chain is the one-leaf-helper shape §12.4 explicitly sanctions, not a residual defect. Do not add a narrowing helper (R-10) inside `credentials()`, or the violation returns. |

## Minor findings (fix if trivial, otherwise follow-ups)

| ID | Where | Finding | Tag | Status |
|---|---|---|---|---|
| R-11 (R-V8) | `vidbyte/agents/fork.py:45`, `:62` | An edited comment is 119 columns (`:45`), and a new `@intent` line is 73 columns (`:62`). This breaks comment-format.md's 72-column rule for touched blocks. The verifier's awk scan confirms both. | trivial | fixed @54cb16de |
| R-12 (R-V7) | `vidbyte/lib/registries/provider_keys.py:4`; `vidbyte/lib/runners/text.py:6`; `vidbyte/lib/constants/jev.py:9` | Three headers do not match the code. The ROLE line omits three `match` callers: `Runner.__init__` (`utility.py:44`), `ModalityDetector._config_options` (`:226`), and `JevRunBriefWriter` (`writer.py:56`). `text.py` names one "uses_gateway branch", but `arun` branches on `vidbyte_api_key is not None` (`:91`). The `jev.py` TESTS line omits `tests/features/sdk_provider_keys/`. | trivial | fixed @a07219f8 |
| R-13 (R-C2) | `vidbyte/lib/registries/provider_keys.py:293` | M-18 offers "Vidbyte's own {primary} account" for providers the gateway does not serve, and in DIRECT, where Vidbyte is never contacted. Probe: DIRECT mistral + xai key. After R-6, AUTO no longer reaches M-18 for unserved providers, but DIRECT and the Agent root still do. Fix: append the clause only when the provider is in `VIDBYTE_MANAGED_TEXT_PROVIDERS`. | trivial | fixed @940ff97c |
| R-14 (R-E7) | `vidbyte/paradigms/context_minimal_fanout/types.py:444` | `AgentRoleSettings` refuses a padded Vidbyte key that `Agent` accepts, and its message wrongly says the key is malformed. Probe: role → "must be a live key in the vb_live_ format"; agent → accepted. Fix: strip, store, then check. | trivial | fixed @fcc98f17 |
| R-15 (R-E5) | `vidbyte/lib/util/credential_keys.py:76`; `vidbyte/harnesses/serialization.py:74` | `CredentialKeyPolicy` and the harness redactor do not know the new header name. Probe: `is_secret_key('X-Vidbyte-Provider-Key') = False`, and both a mapping dump and a free-text dump keep the provider key while the bearer token is scrubbed. No current code path dumps request headers, so this is defense in depth (NFR-1). Fix: add the `_provider_key` suffix and the `provider[_-]?key` alternation. | trivial | fixed @15907973 |
| R-16 (R-V6) | `vidbyte/lib/dataclasses/agents.py:280-281` vs `vidbyte/lib/registries/models.py:208-209`; `vidbyte/lib/registries/provider_keys.py:239`, `:275` | The Vidbyte-key format check and its M-10 message exist twice, at the new `agents.py` copy and the base `models.py` copy. The M-7 f-string also appears twice. Fix: one message constant beside `VIDBYTE_API_KEY_PATTERN`, and one M-7 class constant. Mind the 300-line cap on `provider_keys.py` (NFR-4, now 296 lines). | follow-up | fixed @6ac82305 |
| R-17 (R-E6) | `vidbyte/lib/http/vidbyte_gateway.py:111` (`gateway_reason`, `:101`) | In VIDBYTE_MANAGED, a gateway 402 tells the developer to add a provider key to `api_keys`, which that mode ignores (INV-5, D-15). The transport sees only `relays`, never the mode. Table G has no VIDBYTE_MANAGED column, so this is a spec gap. No test pins the managed 402 wording, and `ManagedCall` runs AUTO. The wording and the plumbing are OPEN ITEM 2. | follow-up | fixed @9150b3cf |
| R-18 (R-E8) `[scope-adding]` | `vidbyte/lib/registries/provider_keys.py:64`, `:82` (checks at `:137`, `:204`) | Vidbyte test keys (`vb_test_`) are not reserved, so one binds as an unproven provider key. Probe: `vb_test_…` with primary deepseek binds to `['deepseek']`. Table F defines only `vb_live_`, so the spec does not require this. It is for the user to decide. | follow-up | deferred: scope-adding, user follow-up (orchestrator) |

## What the implementation gets right (so nobody "fixes" it)

- **The user's words hold on every path checked.**
  - Every agent entry point takes both `api_keys` and `vidbyte_api_key`: BaseAgent and its kwargs subclasses, AggregateAgent, JevAgentSettings, AgentRoleSettings, and Session.resume/fork_from. `MultiAgent` owns no model.
  - One lib class, `ProviderKeyMatcher`, matches each key.
  - In AUTO, the fallback, fork, aggregate children, and resumed or forked sessions each relay only their own provider's key.
- **The §4 snippet (AC-1) runs offline exactly as written.**
  - It makes one gateway POST with Bearer V and the xAI key in `X-Vidbyte-Provider-Key`, with envelope `("xai", "grok-4.5")`.
  - On an xai 503, the Claude backup relays only the Anthropic key.
  - The DIRECT agent makes one request to `https://api.x.ai/`, never reads `VIDBYTE_API_KEY`, and never contacts the gateway.
- **"Extend the api_key functionality" is honoured.**
  - With no list, AUTO relays `XAI_API_KEY` from the environment.
  - VIDBYTE_MANAGED never relays (INV-5); it sends exactly `{authorization, content-type, idempotency-key}`.
  - An image runner gets `key_for(openai)` (row 11, INV-19).
  - Restore re-matches against the stored names, with the INV-24 switch set correctly. EC-53 and EC-54 behave as specified.
- **INV-15 holds across children.** Each of these carries the root's `ProviderKeys` and `model_mode` unchanged, and each was checked by mutation (c1, c2, p, pp, qq, rr, ss, tt, u, w, and e1/e2/v for restore):
  - fork, session fork, and fork recovery;
  - handoff and continual trace;
  - the Jev clone and the brief writer;
  - aggregate children and the runner.
- **Matching is strict and gives nothing away.**
  - Every near miss is refused: `AIza` with 34 or 36 characters, `xai-client-secret.`, `sk-ant` with a dot, and `sk-svcacct-` at any provider but openai.
  - Unique assignment does not depend on key order.
  - CR, LF, NUL, tab, and non-ASCII characters raise M-6b before a key can reach a header.
  - No M-n message or `details` contains key text.
- **The billing route is correct on every mode path.**
  - `X-Vidbyte-Provider-Key` is sent only when a key is relayed.
  - DIRECT never reads the Vidbyte key.
  - AUTO without a Vidbyte key raises rather than quietly going DIRECT.
  - `TextModelRunner` pins its credentials at init.
  - The 32,768 output cap and the 630 s floor apply only to gateway calls.
  - Each call builds its own gateway transport.
  - The key is never in the envelope.
  - The engineering lens killed 47 of 54 mutations.
- **No secret appears in any repr or state.**
  - The reprs of all 12 key-holding objects show no key.
  - `export_state` and `SessionSerializer._safe` write only `key_providers` names.
  - Every key field is `repr=False`.
- **Layering and D-21 hold.**
  - `provider_keys.py` imports only `re`, `collections.abc`, `typing`, `lib.constants.jev`, `lib.enums`, and `lib.errors` at module level.
  - `ProviderKeys` is imported late, inside `match`, under an `@intent`.
  - `lib/dataclasses/agents.py` imports no registries module.
  - Both D-21 import commands succeed, and A006 stays at 34 = 34.
- **House patterns are followed.**
  - `ProviderKeyMatcher` is a class-bound static helper. `match` is narrated (Steps 1–7), and every `_` helper is a leaf `@staticmethod`.
  - `credentials()` uses `match` with a raising `case _`.
  - The new constants live in `lib/constants/jev.py`.
  - The relay header is stored by subscript with the imported constant (C017 CLEAN). No header literal, `[!-~]+` pattern, or 512 cap appears elsewhere under `vidbyte/`.
- **Scope and budget are clean.**
  - The diff touches exactly the 49 §12.3 files plus the authorized S014 rule file.
  - There is 1 new file, 3 new classes, and 0 new dependencies.
  - `base.py` grows by +34/−8 (net +26 ≤ 30), and `provider_keys.py` has 296 lines (≤ 300).
  - `lint/baseline.json` only lowers A001 (643 → 641).
  - The diff adds no `type: ignore`, `noqa`, or `nosemgrep`.
  - Every `tests/` commit is a `test(sdk):` commit.
  - No text- or agent-level `api_key=` remains, and the deleted symbols are gone.
- **Docs and non-code actions (§12.5) are done.**
  - The registries README "Provider Key Format Sources" section labels each source first-party or secondary. The OpenAI admin-key URL replacement points at OpenAI's own GitHub organization.
  - The root and agents READMEs, `skills/sessions.md`, `skills/usage/create_agent.md`, and `llms.txt:1113` are updated. Row 36's conditional sentence is correctly omitted.
  - `ProviderKeys` and `ProviderKeyMatcher` are exported.
  - The scripts build text configs with `api_keys` in DIRECT, and non-text configs keep `api_key`.
  - Commits carry one work item each, with IDs. The diff holds no secrets and no generated files.
- **Gates (re-run by the verifier on an archive copy).** Full suite: `4101 passed, 13 skipped in 37.59s`. The flaky `test_mcp_stdio_transport` test did not fail in any verifier run.
