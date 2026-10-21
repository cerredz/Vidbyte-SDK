LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the wire, the guard, the unset path and spend are sound, but an agent whose context-window algorithm builds its own runners drops a set effort on every call without a word (INV-3), and `Runner(options=...)` drops it the same way.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- An unset effort is byte-identical to base. 58 scripted scenarios and 87 requests match base 98a5d37b exactly: method, URL, headers and JSON body, after the random idempotency and run ids are normalized. The scenarios cover 7 providers × plain, sampling, schema, tools, extra_body and thinking_config, AUTO and VIDBYTE_MANAGED envelopes, an agent with tools and a schema, a 3-hop chain with failing hops, an AUTO agent, Jev machinery and bare Jev. All 9 `export_state().runtime_config` captures are identical. `AgentLoopSettings.to_runtime_config` is untouched, with a 0-line diff in `vidbyte/agents/settings/loop.py`.
- The refusal has three layers: the construction guard, the `TextModelConfig` check and the `attach` check. A set effort could not be pushed past them. Each case below was refused with 0 requests sent:
  - each test case from the briefing: case and whitespace, a dated snapshot, prefix-map ids, image, audio and embedding models, a deep fallback hop, AUTO and VIDBYTE_MANAGED, a `dataclasses.replace` of `JevAgentSettings`, a fork override and tampered checkpoints;
  - `agent.runner_config` replaced after construction with AUTO, VIDBYTE_MANAGED or `o3`. The runner-build check refuses these.
- The wire forms match §9.2, including the hard cases (33/33 probe checks plus 3/3 stream checks):
  - Both requests of a tool-call turn carry the effort on all 7 providers.
  - After a 500 on openai, the anthropic fallback hop sends its own `output_config` form.
  - A disjoint `extra_body` is merged deeply.
  - Anthropic `output_config.format` and `effort` sit side by side.
  - Each `stream_text` body equals the non-stream body plus `stream: true`.
- Reasoning tokens reach the spend ledger on all 7 adapters. A capped agent with `high` stops at `max_spend` after one request. The pack is strong: of 47 new mutants, 40 are killed, including all 9 Jev child reverts, every copy path and every fallback hop.

FINDINGS (ranked, most severe first, max 15)
R-E1 [Blocker] [failure-modes] vidbyte/agents/algorithms/multi_provider_agentic_grader.py:96 — An agent with `reasoning_effort` and the multi_provider_agentic_grader algorithm sends the effort on none of its calls, which violates INV-3 "never silently ignored" and G-1
  Evidence: `:96` `p_runner = ModalityDetector.create_runner(modality=ModelModality.TEXT, provider=provider_name, model=model_name, api_keys=handle.api_keys, mode=handle.model_mode)`. Three other sites build a runner the same way, with no effort argument:
    - `:152` (`grader_runner = ModalityDetector.create_runner(...)`);
    - `vidbyte/agents/algorithms/independent_critic.py:214-220`, when `reviewer_provider` is set;
    - `vidbyte/agents/algorithms/prosecutor_defender_judge.py:250`, when a stage sets provider and model.

    The guard checks only `runner_config` and the fallback chain (`vidbyte/agents/reasoning_effort.py:44`). Probe `probe_algorithm.py`, with `BaseAgent(openai/gpt-5.5, DIRECT, reasoning_effort="high", algorithm=multi_provider_agentic_grader(provider_models={"openai": "gpt-5.5", "anthropic": "claude-sonnet-5"}, grader openai/gpt-5.5))`:
    `MPAG -> api.openai.com model=gpt-5.5 reasoning=None output_config_effort=None`
    `MPAG -> api.anthropic.com model=claude-sonnet-5 reasoning=None output_config_effort=None`
    `MPAG -> api.openai.com model=gpt-5.5 reasoning=None output_config_effort=None`
    With independent_critic and `reviewer_provider="anthropic"`, the producer request carries the effort but the reviewer request does not:
    `reviewer=claude-sonnet-5 -> api.openai.com model=gpt-5.5 reasoning={'effort': 'high'}`
    `reviewer=claude-sonnet-5 -> api.anthropic.com model=claude-sonnet-5 reasoning=None output_config={'format': ...}`
    A reviewer with no row, `claude-haiku-4-5`, is neither refused nor sent the effort.
  Failure: A developer sets `reasoning_effort="high"` on a DIRECT agent and picks multi_provider_agentic_grader. Construction succeeds, and every trial and the grader run at the vendor default. That includes the trial on the agent's own `gpt-5.5`, whose row lists `high`. Nothing reports the drop. The spec is wrong here: the §9.2 "Every agent" row (spec.md:453) and A-8 (spec.md:1197) assume that every algorithm side call goes through the agent's own `RunnerHandle`, but these three algorithms build a fresh runner for a model they name themselves.
  Smallest fix: Refuse at construction, as D-2 does for gateway modes. Move the `AgentReasoningEffortGuard.refuse_unsupported` call (base.py:262) below `self.algorithm = ContextWindow.resolve_algorithm(algorithm)` (base.py:284), and pass it the algorithm. Then raise when an effort is set and the algorithm runs models of its own, naming the algorithm:
    - multi_provider_agentic_grader, always;
    - independent_critic, when `reviewer_provider` is set;
    - prosecutor_defender_judge, when any stage sets provider and model.

    Add one refusal test per algorithm. Forwarding the effort to those models, and checking each one in the guard, is [scope-adding] and belongs in a Q.
  Spec IDs: INV-3, G-1, G-2, A-8, §9.2 "Every agent"

R-E2 [Major] [failure-modes] vidbyte/lib/runners/utility.py:134 — `Runner(options={"reasoning_effort": ...})` drops the effort without a word on every runner type, which contradicts INV-3 "never dropped by Runner"
  Evidence: The effort is written into `options` unconditionally, so it overwrites a caller's key. The non-text refusal checks only the keyword argument, and the options filter then drops the key from a non-text config:
    `:134` `options["reasoning_effort"] = self.reasoning_effort`
    `:137` `if self.reasoning_effort is not None and runner_type != RUNNER_TYPE_TEXT:`
    `:144` `return {key: value for key, value in options.items() if key in allowed}`
  Compare temperature at `:142-143`: `if self.temperature is not None and runner_type == RUNNER_TYPE_TEXT: options["temperature"] = self.temperature`. Probe `probe_options.py`:
    `options effort, DIRECT: built TextModelRunner config.reasoning_effort=None url=https://api.openai.com/v1/responses 'reasoning' in body=False`
    `options effort, AUTO: built TextModelRunner config.reasoning_effort=None url=https://vidbyte-backend.onrender.com/api/v1/models/generate`
    `gpt-image-2 (image) options: BUILT ImageModelRunner` (the same happens for tts-1, whisper-1, text-embedding-3-small and sora-2; the keyword form is refused for all of them)
    Mutant N06, the temperature-style `if self.reasoning_effort is not None:`, SURVIVED with `703 passed`, so no test pins either behavior.
  Failure: `Runner(provider="openai", model_name="gpt-5.5", model_mode=DIRECT, options={"reasoning_effort": "high"}).build()` sends no effort. In AUTO the call reaches the gateway, when it should be refused. On an image, audio, embedding or video model the runner builds and the field filter drops the key. The spec is wrong here: row 9(b) (spec.md:1024) prescribes the unconditional assignment. That conflicts with INV-3 (spec.md:165), because `options` is filtered against the target config's fields (`:121-123`, `:144`) and `TextModelConfig` now has this field.
  Smallest fix: In `_config_options_for`, set `effort = self.reasoning_effort if self.reasoning_effort is not None else self.options.get("reasoning_effort")` and use `effort` at `:134` and in the `:137` refusal. Add 3 test cases: DIRECT sends, AUTO is refused and image is refused. Refusing an options key outright would also work.
  Spec IDs: INV-3, FR-5, EC-9, §12.3 row 9(b)

R-E3 [Major] [test-quality] tests/features/agent_reasoning_effort/test_agent_reasoning_effort_copy_paths.py:109 — No test restores a fallback agent that has an effort; mutant N22 survives
  Evidence: The mutant changes base.py:612 so that `restore` drops the effort whenever `fallback_models` is stored:
    `reasoning_effort=None if state.runtime_config.get("fallback_models") else state.runtime_config.get("reasoning_effort"),`
    Result: `N22 restore ignores a stored effort for a fallback agent: SURVIVED (5s) 703 passed in 4.33s`.
    Every restore in the pack (`:123`, `:140`, `:154`) is of a single-model openai agent.
    Today's code is correct (`probe_stream_restore.py`): `OK restored fallback agent effort=<ReasoningEffort.HIGH: 'high'> hops=[('api.openai.com', {'effort': 'high'}, None), ('api.anthropic.com', None, {'effort': 'high'})]`.
  Failure: A later change to restore for chained agents, such as Q-4 per-hop work near D-6, can resume a two-hop agent at the vendor default without a word, and the pack stays green.
  Smallest fix: Add one test. Export a DIRECT `openai/gpt-5.5` agent with `fallback=["anthropic/claude-sonnet-5"]` and an effort, restore it, run it with `Wire(fail={openai: 500})`, and assert that each hop sends its own fragment.
  Spec IDs: AC-11, INV-14, FR-6, D-6

R-E4 [Major] [test-quality] tests/features/agent_reasoning_effort/test_agent_reasoning_effort_refusals.py:599 — The non-text refusal is pinned only for an image model; mutant N05 survives
  Evidence: The test builds only `model_name="gpt-image-2"` (`:606`). Mutant N05 changes the check to `runner_type == "image"`: `N05 non-text refusal only for image runners: SURVIVED (5s) 703 passed in 3.97s`.
    Today's code refuses every type (`probe_options.py`), for example: `tts-1 (audio) kwarg: refused`, `text-embedding-3-small (embedding) kwarg: refused`, `sora-2 (video) kwarg: refused`.
  Failure: Suppose a refactor special-cases image. Then `Runner(model_name="tts-1", reasoning_effort=HIGH).build()` builds, and the field filter drops the effort without a word. That is EC-9's own failure, on 3 of the 4 non-text types, and the pack stays green.
  Smallest fix: Parametrize the test over `gpt-image-2`/image, `tts-1`/audio, `text-embedding-3-small`/embedding and `sora-2`/video, with the same text and `details` checks.
  Spec IDs: FR-5, AC-16, EC-9

VERIFIED CLAIMS:
1. Break the wire: HELD.
   - `probe_wire.py` passed 33/33 checks. They cover:
     - a tool-call turn on 7 providers, where both requests carry the fragment;
     - a disjoint `extra_body` on 7 providers, which equals `deep_merge(unset, fragment)`;
     - an overlapping top-level key and a nested dict at the same path on 7 providers, both refused;
     - `thinking_config` set to `{"thinkingBudget":128}` or `{}`, refused on Gemini 3.5, Gemini 2.5 and Anthropic;
     - Anthropic `output_config` with both `format` and `effort`;
     - Anthropic `none` with a schema, which gives `thinking: disabled` and no effort;
     - an openai→anthropic fallback after a 500, where each hop sends its own form;
     - `"high"` and `GrokReasoningEffort.HIGH`, both stored as `ReasoningEffort.HIGH`.
   - `probe_stream_restore.py` passed 3/3 stream checks: openai `xhigh`, anthropic `low` and anthropic `none`. Each stream body equals the non-stream body plus `stream: true`.
   - No duplicate, remapped or wrong-form effort was found.
2. Break the guard: HELD. `probe_guard.py` printed `TOTAL 19 FAIL 0`.
   - Refused with 0 requests:
     - `GPT-5.5` + `minimal`;
     - the dated snapshot `gpt-5.5-2026-04-23`;
     - the prefix-map ids `claude-opus-4-7` and `gemini-3.5-flash-001`;
     - the non-text models `gpt-image-2`, `tts-1` and `text-embedding-3-small`;
     - a third-hop `gemini-2.5-pro`;
     - the default AUTO, and VIDBYTE_MANAGED;
     - `JevAgentSettings` after `dataclasses.replace` to `o3`, and with the default AUTO;
     - a fork to `gemini-2.5-pro`;
     - a restore whose stored `model_mode` is `auto`, or whose stored effort is `max` or `minimal`.
   - `' GPT-5.6 '` + `xhigh` sends the fragment.
   - `runner_config` replaced after construction with AUTO, VIDBYTE_MANAGED or `o3` is refused at runner build with 0 requests. That error surfaces as `AgentExecutionError` whose cause is the `TextModelConfig` refusal (`probe_switched.py`).
3. Silent ignore (D-P9): NOT HELD. See R-E1 (algorithm-built runners) and R-E2 (`Runner` options).
   - Held for:
     - all 9 Jev agents and the fork, ContinualTrace and Handoff copy paths;
     - each fallback layer (`build_runner`, `from_spec`, `to_fallback`) and `_runner_for_model`;
     - all 4 builders. N25–N40 and N44 were killed. N01 and N02 are equivalent (see claim 6).
   - D-6 is as stated: the per-hop form is not stored, and the agent-wide effort survives restore (claim 2, R-E3).
4. Unset is identical: HELD, apart from a repr change the spec accepts.
   - `diff_unset.py`: `scenarios 58 requests 87 bodies/urls/headers identical in 58`, `state entries identical: True`.
   - All 45 differing keys are `repr:` keys. `reasoning_effort=None` is appended to `TextModelConfig`, `AgentRunnerConfig` and `JevAgentSettings`, because spec.md:1136 keeps the field `repr=True`. So this is not a finding.
   - `to_runtime_config` (`loop.py`) is unchanged.
5. Spend: HELD. `probe_spend.py` passed 7/7.
   - In every run: `stop=max_spend vendor_requests=1 output_tokens=2000010`.
   - Cost: openai 60.0, anthropic 20.0, gemini 15.0, deepseek 7.92, xai 12.0, glm 8.8, meta 8.5. The cap was 0.05.
   - xAI's separately reported `reasoning_tokens` are added into `output_tokens`.
6. Test quality: PARTLY HELD. Of 47 new mutants (N01–N47), 40 were killed. 4 are equivalent:
   - N01/N02, attach after `_attach_extra_body`: every `_attach_extra_body` is a top-level `payload.update`, and a top-level overlap is refused, so the two orders give equal bodies.
   - N04, `.strip()` dropped: `normalize_model` already strips (`models.py:255`).
   - N15, partial-identity chain: it cannot be built. `AgentFallback` refuses an unnamed primary, and a bare hop takes the primary's provider (`probe_identity.py`).

   3 are real survivors: N05 (R-E4), N06 (R-E2) and N22 (R-E3). These are the three plausible bugs that no test catches.

   No test pins the table's size, its key set or a literal date. The registry test says "Size and key set are not pinned", and `REASONING_EFFORT_AS_OF` is read from the module. `first_request` asserts that a request was sent, so the exclusion equalities (brief writer, decisions) are not vacuous.
7. Robustness: HELD.
   - Every refusal and send test goes through `_require_provider` and `Runner._normalize_provider_and_model`: N03, N13, N18, N20 and N23 were killed through them. So a change to either signature fails the pack.
   - Import adds exactly 3 modules (951→954). `vidbyte.lib.configs.reasoning_effort` costs 840 µs of its own time and imports only typing and enums.
   - `attach` deep-copies the table rows (N07 killed). The only module-level state is the constant tables.
8. Security: HELD.
   - The added non-docs lines contain 0 key-shaped strings.
   - `DecisionModelConfig.api_key` has `repr=False`, and the key does not appear in `repr`. The root exports are the same objects as the lib ones (`is`).
   - Refusal texts and `details` carry only the agent, field, provider, model, value, mode and the `extra_body` key names.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort tests/features/sdk_managed_text/test_managed_text_selection.py tests/features/sdk_provider_keys/test_provider_keys_contract.py tests/test_agent_modality_routing.py` → `703 passed in 2.82s`
- `py -3.11 probes/probe_wire.py` (worktree on PYTHONPATH) → `TOTAL 33 FAIL 0`
- `py -3.11 probes/probe_stream_restore.py` → `OK stream openai:gpt-5.5:xhigh ... same_as_nonstream_minus_stream=True` (3 OK); `OK restored fallback agent effort=<ReasoningEffort.HIGH: 'high'>`
- `py -3.11 probes/probe_guard.py` → `TOTAL 19 FAIL 0`; `probes/probe_switched.py` → 3 × `OK ... requests= 0 AgentExecutionError ... <- ConfigurationError: TextModelConfig sets reasoning_effort, but ...`
- `py -3.11 probes/probe_identity.py` → `REFUSED primary model None + named fallback: ... declares a fallback chain but no provider/model_name to fall back from.`
- `py -3.11 probes/probe_options.py` → `options effort, DIRECT: built TextModelRunner config.reasoning_effort=None ... 'reasoning' in body=False`; `sora-2 (video) options: BUILT VideoModelRunner effort_field='<no field>'`
- `py -3.11 probes/probe_algorithm.py` → `MPAG -> api.openai.com model=gpt-5.5 reasoning=None output_config_effort=None` (3 of 3 requests without the effort)
- `py -3.11 probes/probe_spend.py` → `OK meta:muse-spark-1.1:high stop=max_spend vendor_requests=1 output_tokens=2000010 cost_usd=8.500055 cap=0.05` (7 of 7 OK)
- `PYTHONPATH=<scratch base|branch> py -3.11 probes/probe_unset.py ...` then `py -3.11 probes/diff_unset.py` → `scenarios 58 requests 87 bodies/urls/headers identical in 58`; `state entries identical: True`; `differing keys: 45` (all `repr:`)
- `py -3.11 -X importtime -c "import vidbyte"` (base and branch) → `951 954 ['vidbyte.agents.reasoning_effort', 'vidbyte.lib.configs.reasoning_effort', 'vidbyte.lib.registries.reasoning_effort'] []`; `import time: 840 | 840 | vidbyte.lib.configs.reasoning_effort`
- `py -3.11 probes/mutate.py <scratch branch>` → `CONTROL exit=0 703 passed`; N01, N02, N04, N05, N06, N15, N22 SURVIVED, the rest KILLED; `CONTROL AFTER exit=0 703 passed in 5.41s`
- `py -3.11 probes/mutate2.py <scratch branch>` → N24–N47 all KILLED; `CONTROL AFTER exit=0 703 passed in 4.02s`
- `git diff 98a5d37b..8e773244 -- . ':(exclude)docs' | grep '^+' | grep -cE '<key shapes>'` → `0`; DecisionModelConfig check → `api_key repr flag: False | key in repr: False | root is lib: True True`
- `git status --porcelain` (worktree) → only `?? docs/spec/agent-reasoning-effort/reports/S4-review-conformance.md` (another reviewer's file) before this report was written

Probes, outputs and the two scratch trees (`git archive` of 98a5d37b and 8e773244) are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r2e-s4/engineering/`.
