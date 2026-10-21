VERDICT: SOUND WITH FIXES — The design matches the code and the raw vendor docs: one registry, an attach in four builders before `_attach_extra_body`, a guard after the spend cap, and DIRECT only. But one P0 acceptance case cannot pass with the converter the spec requires, and the no-row refusal text states a vendor fact the SDK does not know.

Reviewer: S1 adversarial spec reviewer, round 1. Spec reviewed: `docs/spec/agent-reasoning-effort/spec.md` r1, worktree HEAD 3d417aea (code at 98a5d37b). Probe scripts: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r2e-s1-review/` (`rq.py`, `tagfind.py`, `probe_runner_ids.py`). No request was sent to a vendor.

WHAT THE SPEC GETS RIGHT

- **Attach placement and builder coverage are exact.**
  - Four builders, each before `_attach_extra_body`:
    - `openai.py:252-261`. `stream_text` at `:120-128` reuses it, so the Responses and streaming paths are covered.
    - `anthropic.py:54-63`.
    - `gemini.py:58-69` with `_attach_generation_config` at `:179-197`.
    - `compatible.py:58-66`. This one covers xAI, DeepSeek, GLM and Meta.
  - The deep merge is required. `anthropic.py:65-70` assigns `payload["output_config"]` as a whole, and `extra_body` uses `payload.update`. Do not "simplify" it into an `extra_body` write.
- **The guard is placed and scoped correctly.**
  - It runs after the spend-cap refusal at `base.py:250-257`, as one call with no new branch.
  - It covers every chain entry, including string hops (`settings/fallback.py:146` `_resolve_entry`).
  - Per-hop loss on restore is stated (D-6): `_export_runtime_config` at `:633-669` stores `fallback_models` as identity strings (`:652`).
- **Jev propagation is exact.**
  - The main agent (`agent.py:103`), the fresh partial (`:71`) and the 8 children that copy `temperature` all get the field: `bulk_work.py:56`, `compute/clone.py:39`, `compute/swarm.py:51`, `done/handoff.py:166`, `done/reviewer.py:42`, `done/run_state.py:286`, `gate/clarification.py:59`, plus the run-state relation through `super().__init__`.
  - The brief writer (`brief/writer.py:65`, which uses `brief.temperature`) is excluded.
  - `JevAgent.__init__` is unchanged, so the pins at `tests/test_jev_agent.py:506` and `test_output_connectors_agent_wiring.py:112` stay green.
- **The vendor evidence is real, and remaps are refused rather than sent.**
  - My independent checker matched 214 of 222 catalog lines verbatim and passed all 6 absence checks. Each of the other 8 is explained in R-6 and below.
  - Every documented remap is refused: DeepSeek DS-6, GLM GL-7, Meta MS-11, and grok-4.5 `xhigh`.
  - The release-record before-texts are verbatim, and the counts (94 to 97, 733 to 736) hold.

FINDINGS (ranked, most severe first)

R-1 [Blocker] [L10] §6.1 INV-8, §6.2 AC-10 — The required converter accepts "a member of another enum", so the P0 case cannot pass
  Evidence:
    - spec:170 says "Any other value is refused ... `max`, `""`, `"HIGH"`, a non-string, or a member of another enum."
    - spec:198 (AC-10) lists `GrokReasoningEffort.HIGH`.
    - spec:322 and §12 row 10 (and the `TextModelConfig` and `JevAgentSettings` rows) require `RecordFieldConverter.to_enum`.
    - `vidbyte/lib/dataclasses/validation.py:221-230` does this: `members = {str(member.value): member for member in enum_type}`, then `if isinstance(value, str) and value in members: return members[value]`.
    - The probe (`probe_runner_ids.py`) printed `to_enum(<GrokReasoningEffort.HIGH: 'high'>) -> <Probe.HIGH: 'high'>`, and the same for `CodexReasoningEffort.HIGH`.
    - `"max"`, `""`, `"HIGH"` and `3` are refused with the six-value message, as the spec says.
  Failure: S2 writes the AC-10 case `GrokReasoningEffort.HIGH` and expects a `ConfigurationError`. S4 builds §12 exactly, with `to_enum`. The test is red and stays red. The only way to make it green is a type check in each of three dataclasses. That is a primitive validator outside `validation.py` (C008), and §12 does not list it.
  Smallest fix:
    - Delete "or a member of another enum" from INV-8.
    - Delete `GrokReasoningEffort.HIGH` from AC-10.
    - Add one sentence to INV-8: "A str-valued member of another enum whose value is one of the six (for example `GrokReasoningEffort.HIGH`) is accepted by value, as `to_enum` does for every enum field in the SDK."

R-2 [Major] [L9/L1] §3 NG-14, §7 EC-10, §12 row 3, §13 — The reason given for leaving model ids out is false: the runner does build those ids
  Evidence:
    - spec:85 says "`Runner.build` raises "No runner mapping" for them today, so a row could never be used."
    - `vidbyte/lib/runners/utility.py:71` falls back to `MODEL_PREFIX_RUNNER_TYPE_MAP` ("claude-", "gpt-", "gemini-", "grok-", "deepseek-", "glm-", ...).
    - The probe printed `anthropic/claude-opus-4-7: type=text built=TextModelRunner`. It printed the same for `claude-opus-4-6`, `claude-opus-4-5-20251101`, `claude-sonnet-4-6`, `gpt-5.5-2026-04-23` and `gemini-3.5-flash-001`.
    - Raw `ant_effort.md:10-25` (`featureMetadata.supportedModels`) lists `claude-opus-4-7`, `claude-opus-4-6`, `claude-opus-4-5-20251101` and `claude-sonnet-4-6`.
    - `oai_model_gpt-5.5.md` names the snapshot `gpt-5.5-2026-04-23`.
  Failure: Take a user on `claude-opus-4-7`. The pricebook knows it, the runner builds it, and Anthropic documents it for effort. Setting `reasoning_effort="high"` is still refused with "(it supports no reasoning effort)". S4 follows the §12 row 3 rule "no row for an id the runner cannot build" and the §13 line. Both assume the gap cannot be reached, so nobody records it as a limitation.
  Smallest fix: Replace the "why not" in NG-14 with the true reason: "The table is limited to the provider catalog's text ids (`vidbyte/lib/registries/models.py`) as a scope choice. The runner's prefix map builds other ids (pricebook ids, dated snapshots), and those are refused as 'no row' (EC-10), an accepted limitation." Use the same wording in the §12 row 3 WHAT NOT TO DO entry and in the §13 line.
  Q-1 [scope-adding], default No: add sourced rows for the four Anthropic ids in `supportedModels`, and map vendor-documented snapshot ids to their alias rows.

R-3 [Major] [L5] §8.5 capability text, empty tuple — "(it supports no reasoning effort)" claims a vendor fact the SDK does not have
  Evidence:
    - spec:395 says "When the tuple is empty, the parenthesis reads `(it supports no reasoning effort)`."
    - EC-10 sends "a new vendor model, `openrouter/*`, `kimi`, `mistral`, `minimax`, or a bare-only id" to that same text.
    - EC-11 says "`REASONING_EFFORT_AS_OF` plus the README sources section make the staleness visible". But neither appears in any refusal text.
  Failure: `BaseAgent(provider="anthropic", model_name="claude-opus-4-7", model_mode=TextModelMode.DIRECT, reasoning_effort="high")` raises "anthropic:claude-opus-4-7 has no documented form for reasoning effort 'high' (it supports no reasoning effort)". Anthropic documents the opposite (`ant_effort.md:19`). C5 shows this text in the CLI, so users conclude the model cannot reason. A model released after 2026-10-20 gets the same false claim. The table's age is invisible at the one place a user meets it.
  Smallest fix:
    - Give the no-row case its own text: `{provider}:{model} is not in the SDK's reasoning-effort table, which was checked against vendor docs on {REASONING_EFFORT_AS_OF}; see "Reasoning Effort Sources" in vidbyte/lib/registries/README.md`.
    - Keep "(it supports a, b)" for ids that have a row.
    - Update the substring that EC-10 and AC-4 expect.
    - This also answers the staleness question in briefing item 2.

R-4 [Major] [L4] §7 D-17, §12 row 3 — The tables break the recorded capability-data convention, to avoid a red that is local only
  Evidence:
    - spec:317 says "`vidbyte/lib/configs/` would turn the surface test red locally (`:274`)."
    - Field guide `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/declarative-config-resolution.md:38-40`: "Capability declarations live in dependency-light config data; registries resolve and explain them". When: "Adding per-provider or per-model capability tables whose values are consumed by a registry and provider adapters." Do: "Put fixed declarations and typed developer-facing descriptions in `vidbyte/lib/configs/`; let the registry import them".
    - Precedent: `vidbyte/lib/configs/structured_output.py` with `vidbyte/lib/registries/structured_output.py`, and `llms.txt:607`.
    - The surface test `test_harness_threads_surface.py:270-278` calls `merge_base()`. That call skips when origin/main is missing (`:139-143`, "a shallow CI clone"). So the red happens only locally, the same class as `:309`.
    - D-17's "not added to `registries/__init__.py`" also departs from that package, which exports every registry, including structured_output's tables.
  Failure: The guide's When clause describes this change exactly: a per-model table read by one registry and four adapters. So the PR is likely to get the same review comment PR #321 got. The only recorded reason is a red that the gate already treats as inherited. This is rated Major, not Blocker, because `provider_keys.py` and `models.py` keep tables inside registries, which gives some cover.
  Smallest fix (the author picks one; (a) is the convention):
    - (a) Put `REASONING_EFFORT_FORMS`, `REASONING_EFFORT_SUPPORT`, `REASONING_EFFORT_AS_OF` and `GEMINI_THINKING_BUDGET_OFF` in `vidbyte/lib/configs/reasoning_effort.py`, exported from `configs/__init__.py`. Keep `ReasoningEffortRegistry` in registries, exported from `registries/__init__.py`. Name the `:270-278` local red as inherited in §11 and §13, next to `:309`.
    - (b) Keep D-17, but rewrite its rationale to cite the guide entry and say why the deviation is taken.

R-5 [Minor] [L10] §6.2 AC-5 — For `TextModelConfig`, GLM, Meta and a custom endpoint hit an earlier refusal, and that refusal is not a `ConfigurationError`
  Evidence:
    - AC-5 expects "`TextModelConfig` is constructed | `ConfigurationError` names `TextModelMode.DIRECT`".
    - spec:383 says `_validate_reasoning_effort` is "the last call in __post_init__".
    - `model_configs.py:95-96` calls `_require_gateway_shape` first. That raises `UnsupportedProviderError` for any provider outside `VIDBYTE_MANAGED_TEXT_PROVIDERS` (`:204-208`).
    - In `vidbyte/lib/errors/base.py:330` and `:334`, both classes subclass `VidbyteSdkError`; neither subclasses the other.
  Failure: Take an AC-5 test parametrized over the seven providers. `TextModelConfig(provider="glm", model="glm-5.2", reasoning_effort="high")` with the default AUTO raises `UnsupportedProviderError`, so `pytest.raises(ConfigurationError)` fails. The behavior is still safe: the call is refused, and the message names DIRECT.
  Smallest fix: Add to AC-5: "For `TextModelConfig`, a provider the gateway does not serve (GLM, Meta), or a custom endpoint, keeps the existing earlier refusal (`UnsupportedProviderError`, or the endpoint `ConfigurationError`), which also names DIRECT. The effort text applies to gateway-served providers."

R-6 [Minor] [L1] §9.2 source catalog — GL-20, GL-21 and the spacing of XA-29 are not verbatim
  Evidence:
    - spec:602 says "Every quote was checked against the raw-fetched text".
    - spec:816 quotes GL-20 as "components.schemas.ChatCompletionResponse.properties.usage.properties.completion_tokens.description: Number of output tokens". In raw `glm-chat-completion.md:716-718` this is three YAML lines: `completion_tokens:`, `type: number`, `description: Number of output tokens`. GL-21 is the same case at `:725-727`.
    - XA-29 is raw `"description":"Assistant reasoning content."`, with no space after the colon.
    - `rq.py ALL` did not find these 3. The other non-matches (DS-5, DS-8, DS-9, DS-10, DS-16) differ only in HTML markup, and `tagfind.py` confirmed them.
  Failure: A-3 rests on GL-20 and GL-21. A later auditor who reruns a verbatim check finds the catalog's own claim false, and then distrusts the whole table. The content itself is correct.
  Smallest fix: Requote GL-20 as "description: Number of output tokens" and GL-21 as "description: Total number of tokens", and give the YAML path as a locator outside the quote. Fix XA-29's spacing.

R-7 [Minor] [L1] §15 A-4, A-6, A-7, A-8 — Four assumptions can be proved from material already in hand
  Evidence:
    - A-4, for grok-4.7: `xai-legacy-chat-completions.md:50-51` has `completion = client.chat.completions.create(` and `model="grok-4.7",`. Source: https://docs.x.ai/developers/model-capabilities/legacy/chat-completions.md, fetched 2026-10-20T15:26:54Z. `xai-cost-tracking.md:69-70` shows the same. grok-4.6 is still unproven.
    - A-6: in `gem_discovery.json` (v1beta discovery, fetched 2026-10-20T15:30:13Z), the `ThinkingConfig.thinkingLevel` enum is upper case.
    - A-7: `deepseek-create-chat-completion.html` (fetched 2026-10-20T15:28:41Z) lists `reasoning_effort` as a top-level body field, a sibling of `thinking`.
    - A-8: `base.py:1694-1711` `_call_with_supported_kwargs` drops any kwarg the callee does not accept. `TextModelRunner.arun` has no `model_name` parameter, so `broker.py:168`'s `call_options["model_name"]` never changes the model.
  Failure: Nothing breaks at runtime. But S2 and S4 may write defensive tests or code for risks that are already closed.
  Smallest fix: Move A-4 (for grok-4.7), A-6, A-7 and A-8 to sourced facts with the citations above. Keep A-4 open for grok-4.6 only.

VERIFIED CLAIMS

1. Vendor facts. Every one of the 222 catalog lines was re-run with `rq.py`: 214 matched verbatim, 6 absence checks were OK, and the other 8 are explained in R-6. This covers the citation of every refused cell and every remap. Hand-checked against the raw files:
   - OpenAI, O11 and O45: on gpt-6.1-sol, `none` and `minimal` are not supported. Held; refused.
   - OpenAI, O12: on gpt-6-astra, `none` returns 400. Held; refused.
   - OpenAI, O37: astra supports low to max. Held.
   - OpenAI, O10: gpt-5 supports minimal to high. Held.
   - Anthropic, `ant_effort.md:10-25`: `featureMetadata.supportedModels` lists the 15 ids. This holds A-1: each id A-1 names is verbatim in the list.
   - Anthropic, A12 and A98: `disabled` is accepted on Opus 5, Sonnet 5 and Haiku 5.5 at high effort or below. Held.
   - Gemini, `gem_gc_thinking.md:512`: Gemini 3 models should use `thinkingLevel`. `:472` shows a lower-case REST example (G1). The discovery enum is upper case. Held (A-6).
   - Gemini: `none` is sent as `thinkingBudget: 0` on 2.5 Flash and Flash-Lite only. Held.
   - DeepSeek, DS-5: "Possible values: [none, low, high, max]". Held.
   - DeepSeek, DS-6: "minimal is accepted and mapped to low, and medium / xhigh are accepted and mapped to high". Held; remaps refused.
   - DeepSeek, DS-24: "Total number of tokens used in the request (prompt + completion)." Held.
   - xAI, `xai-reasoning.md:28`: "If not specified, `reasoning_effort` defaults to `"high"`. Reasoning cannot be disabled." Held; `none` refused.
   - xAI, XA-25: prompt 32, completion 9, total 135, reasoning 94. XA-26: 716, 126, 1009, 167. In both, reasoning is outside completion. Held.
   - GLM, GL-7: on GLM-5.2, none and minimal stop thinking; low and medium map to high; xhigh maps to max. Held; remaps refused.
   - GLM, GL-6: GLM-5.3 accepts only max, high and low. Held.
   - Meta, MS-3: `none` returns 400. Held; refused.
   - Meta, MS-11: xhigh maps to high. Held; refused.
   - Meta, MS-12: max exists only on 1.3. Held.
   - Meta, MS-20: "`reasoning_tokens` are part of `completion_tokens`". Held.
2. Exact-id table versus a family rule:
   - The exact-id table is the right call under D-P9. A family rule would send remapped values without a word (grok-4.5 `xhigh`, Muse `xhigh`), and those differ within a family.
   - Every CLI default model has a usable row:
     - gpt-5.6-sol: none, low to xhigh.
     - claude-sonnet-5: none, low to xhigh.
     - grok-4.5: low, medium, high.
     - deepseek-v4-pro: none, low, high.
     - glm-5.2: none, high.
     - muse-spark-1.1: minimal to high.
     - gemini-3.5-flash: minimal to high.
   - `REASONING_EFFORT_AS_OF = "2026-10-20"` matches the fetch timestamps (2026-10-20T15:xxZ).
   - Staleness is the gap; see R-3.
3. Attach placement held for all four builders and both streaming providers.
   - `ModelProviders` streaming covers only OpenAI and Anthropic. Both reuse their builders.
   - `streaming_text.py:103` builds `TextModelConfig(**config_options)`, so the field reaches it.
   - `openrouter.py:56` overrides `_create_payload` but calls `super()` first. §12 row 8's "none overrides" is wrong in wording only; the effect holds.
4. Guard: held.
   - Placement after `base.py:250-257` holds.
   - It checks every chain entry, string hops included.
   - Restore (`:582-631`) passes kwargs that narrow subclasses already lack, so adding `reasoning_effort` breaks nothing new.
   - `extra_body` and `thinking_config` cannot be reached from agent paths. `Runner` passes only temperature and timeout, and `_config_options_for` drops unknown keys (`utility.py:134`). So INV-7 serves direct `TextModelConfig` users only, which is correct.
5. Gateway ruling: held.
   - AUTO, the default, and VIDBYTE_MANAGED are both refused, and the text names `TextModelMode.DIRECT`.
   - `attach` returns at once for `None`, so the payload is unchanged when the field is unset.
   - See the caveat in R-5.
6. Jev propagation: held, with the sites listed above.
   - `JevAgentSettings` fields end with `system_prompt_presets`, so the new field is appended after it.
   - `__post_init__` validates `model_mode` before temperature, which is consistent.
   - The compute controller's FRESH_AGENT, FORK_AGENT and SUBAGENT are observe-only, so they are correctly excluded.
7. Spend: held for all seven vendors.
   - OpenAI: `pricing/openai.py:39-49` prices `output_tokens` and records `reasoning_tokens` at `:45`.
   - Anthropic: `pricing/anthropic.py:47-58` prices `output_tokens`.
   - Gemini: `pricing/gemini.py:59-63` adds candidates and thoughts.
   - xAI: `pricing/compatible.py` `_billed_output` adds reasoning only when total = prompt + completion + reasoning, which matches XA-25 and XA-26.
   - DeepSeek, Meta and GLM keep `completion_tokens` (GLM under A-3).
8. S2 pins: held.
   - `test_managed_text_selection.py:54-58`: `EXPECTED_TEXT_CONFIG_FIELDS` ends `"mode", "prompt_index", "vidbyte_api_key"` and is asserted at `:344`. Append `"reasoning_effort"`.
   - `test_provider_keys_contract.py:128-140`: the `AgentRunnerConfig` layout ends with `"model_mode"`, and the `JevAgentSettings` layout ends with `"model_mode", "system_prompt_presets"`. Append to both. The SignatureTests at `:200-219` are subset checks and are not affected.
   - No other layout pin exists. The `harness_threads` pin at `:189` covers native functions only.
9. Root slice: held.
   - `DecisionModelMode` is needed: a string mode raises "mode must be a DecisionModelMode value." (probe).
   - `len(vidbyte.__all__) == 733`, and none of the three names is present yet, so the count goes to 736.
   - `docs/design/release-0-4-0.md` line 17 ends verbatim with "...so the contract still lists 733 exports.", and the line 19 before-sentence is verbatim.
   - 3+4+17+11+3+51+4+1 = 94, so 97 is right. The #1184 "Do not tag" clause is untouched.
   - `test_jev_cli_root_exports_contract.py:173-184` requires exactly one "- Agent setting exports:" bullet that contains the 4 R1 names. Adding three names to that same bullet (AC-13) is compatible.
10. Weight and scope: held.
    - No CLI, gateway, harness-effort, decision-model or version change (D-P1, D-P2).
    - The bulk of the spec is the 222-line vendor catalog. That is evidence, not padding.
11. Gates and traps: held.
    - §11 uses `py -3.11`, with an inline `PYTHONPATH` for the source stage and pytest, and none for the package stage.
    - `:309` is named, and `:270-278` is named at spec:906 (true unless R-4 (a) is adopted).
    - The change adds 0 FailureCode members.
