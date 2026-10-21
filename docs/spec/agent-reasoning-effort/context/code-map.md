# Code map: agent-reasoning-effort (R2)

Scout S0, 2026-10-20. Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-reasoning-effort`, branch `feat/agent-reasoning-effort`, head `db6dd49f`, code at `98a5d37b` (#1192). I opened every `path:line` below in this session. Anything I could not check is marked "unverified". No provider documentation was fetched. Wire-form claims about vendors are therefore always marked unverified.

---

## 1. Rules, commands, and conventions from AGENTS.md that bind this change

### 1.1 AGENTS.md rules (quoted, with their heading)

- **Repository Map:**
  - "**Do not grep, glob, or read files under `docs/` as part of ordinary work**". The spec author may read only the documents a human or the briefing names.
  - "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
  - "Each folder's own `README.md` documents that folder in more depth, so read it to the end before you change anything inside the folder." Lint rule A009 keeps every folder README "at or under 40,000 characters".
- **§1 Keep Call Chains One Level Deep:** "one main function that calls a flat list of helpers, where each helper does its job and returns without calling further helpers of its own."
- **§2 Narrate Main Functions in Plain English:** "place short plain-English comments throughout the body … When you change the steps of a main function, update its comments in the same edit".
- **§3 Build in Layers:** "`vidbyte/lib/` is the bottom layer … nothing in `vidbyte/lib/` may import from a layer above it." It also says: "Keep files well below 1,000 lines".
  - `vidbyte/agents/base.py` is already 1,847 lines.
  - `vidbyte/agents/runtime.py` is 2,339 lines.
  - `vidbyte/__init__.py` is 1,661 lines.
  - `vidbyte/lib/dataclasses/jev.py` is 4,694 lines.
- **§4 Use Validated Dataclasses:** "Each dataclass validates itself strictly when it is created, in `__post_init__` … raises a clear error that names the field and the bad value … Prefer `@dataclass(frozen=True, slots=True)` … type any field whose value comes from a small, closed set as an enum."
- **§5 Write Shared Logic Once:** "look in `vidbyte/lib/` for a helper that already does it, and if one is close, add the option you need to it rather than copying it". `HttpTransport` is the quoted example.
- **Placement Rules → Dataclasses:**
  - "**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`**".
  - Exception 1: "A `*Settings` class that configures an agent lives in `vidbyte/agents/settings/`, or in the owning agent's own `settings.py` (for example `vidbyte/agents/jev/settings.py`)."
- **Placement Rules → Enums:**
  - "**Every new enum … is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
  - "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`."
- **Placement Rules → New JEV code:**
  - "**A new JevAgent capability** is a named, validated field on `JevAgentSettings`."
  - New JEV code goes as follows: "**an enum or enum member** in `vidbyte/lib/enums/jev.py`, and **a constant** in `vidbyte/lib/constants/jev.py`."
- **Placement Rules → Existing code:** "Editing one in place (adding a field or a member) is fine. Moving it to `vidbyte/lib/` is a change of its own".
- **REPO_MAP.md** is descriptive. AGENTS.md says it is "not part of" the binding rules. For `vidbyte/agents/settings/` it says: "A new configurable behavior for agents should be added as a setting here rather than as another constructor parameter." Today, `temperature` is a `BaseAgent` constructor parameter (`vidbyte/agents/base.py:112`).

### 1.2 Commands

| Purpose | Command | Source |
|---|---|---|
| Full gate | `python scripts/run_ci.py` | AGENTS.md "Repository Map". This is the only command AGENTS.md states. |
| Gate stages | `python scripts/run_ci.py --stage source` / `--stage package` / `--stage all` | `scripts/run_ci.py:261-262` (`choices=("all", "source", "package")`). The source stage runs `lint/run.py`, `compileall`, `check_context_write_paths.py`, `check_context_primitive_introductions.py`, `check_reasoning_trace_contracts.py` and `pytest` (`scripts/run_ci.py:80-93`). |
| Worktree gate | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `--stage package` without `PYTHONPATH` | field guide `local-ci-verification` (read this session). Not in AGENTS.md. |
| Install | `python -m pip install -e ".[dev]"` | vidbyte-gates.md only. AGENTS.md states no install command. |
| Lint (all / one rule / every finding / JSON) | `python lint/run.py`, `python lint/run.py --rule S010`, `python lint/run.py --rule S010 --all`, `python lint/run.py --format json` | `lint/README.md:32-35` |
| Lint ratchet | `lint/baseline.json` maps each rule ID to a count, for example `"C002": 9` and `"C008": 45`. A rule above its count fails. | `lint/baseline.json:11,17`; `lint/README.md:50-57` |
| Public-API contract | `python scripts/generate-sdk-public-api.py` (write) / `--check` (stale check). C016 runs the same derivation (`python lint/run.py --rule C016`). | `scripts/generate-sdk-public-api.py:1-17` |
| One test file | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q <file>` | header of `tests/features/loop_spend_cap/test_loop_spend_cap_acceptance.py:25`. Other headers write `python -m pytest <file>`. |
| Interpreter in this workspace | `py -3.11`, never bare `python` | orchestrator briefing |

The contract writer refuses to stamp dirty inputs: "Pin provenance: source.commit must describe every file the derivation read, so those files must match HEAD." (`scripts/generate-sdk-public-api.py:69-72`). Its header says: "Commit the vidbyte/__init__.py or version change first, then run this script and commit the regenerated file in the same pull request." (`:7`).

### 1.3 PR and commit conventions

AGENTS.md states none. request.md states the program's own conventions:
- "The orchestrator squash-merges this PR with `--admin`" (`request.md:96`).
- "vidbyte-sdk merges need `gh pr merge --squash --admin` (ci.yml automatic triggers paused; dispatched CI does not attach to PRs)" (`request.md:195`).
- "Do not change the version number … Record the change in `docs/design/release-0-4-0.md`, in the "**Later changes on `main`.**" bullet, after the loop spend cap sentence" (`request.md:80`).

### 1.4 File-header and lint rules that bind this kind of change

- `vidbyte/lib/enums/native_threads.py:5` explains why that module uses `StrEnum`: "Every enum here is a StrEnum, so str(member) and an f-string give the value; Python 3.11 formats a (str, Enum) member as Class.MEMBER". The same header (`:8`) says "Do not turn an enum here back into a (str, Enum)." `CodexReasoningEffort` (`vidbyte/lib/enums/codex.py:34`), `TextModelMode` (`vidbyte/lib/enums/text_model.py:17`) and `ModelProvider` (`vidbyte/lib/enums/model_provider.py:29`) are `(str, Enum)`.
- `vidbyte/lib/dataclasses/validation.py:3-7`:
  - It is "the one canonical field validator for validated records and settings".
  - "the bool guards here are the single owner lint rules C002, C006, C007 and C008 point at".
  - "Every ConfigurationError also carries details["field"]".
  - "Add a new check as one more static method … never copy a check into a record."
- **C008** (`lint/rules/c008_shared_validator_owner.py:3`): "Detect primitive validators (positive int, finite number, strict bool, timeout, limit, temperature) defined outside the one shared validator module." Baseline: 45.
- **C002** (`lint/rules/c002_duplicate_inline_bool_guard_validation.py:3`): "Detect repeated meaningful isinstance(..., bool) validation identities." Baseline: 9.
- **S015** (`lint/rules/s015_public_export_integrity.py:3`): "Verifies package __all__ entries and root public imports are statically bound."
- **C016** (named in `scripts/generate-sdk-public-api.py:4`): fails when `contracts/sdk-public-api.json` is stale.
- **S060** (`lint/rules/s060_typed_public_seam_mappings.py:3`): "Rejects dict[str, Any] in public-seam function and method signatures."
- **A007** (`lint/rules/a007_operational_constants.py:3-4`): "Keeps timeout, retry, limit, budget, truncation, and status policy explicit."
- **A009** README ceilings (`lint/rules/a009_readme_size_limit.py:20-31`): `MAXIMUM_CHARACTERS = 40_000`. The legacy ceilings are `"vidbyte/agents/codex/README.md": 65_000` and `"vidbyte/providers/README.md": 55_000`. Current sizes:

  | README | Characters now | Ceiling |
  |---|---|---|
  | `vidbyte/agents/README.md` | 33,641 | 40,000 |
  | `vidbyte/agents/jev/README.md` | 18,260 | 40,000 |
  | `vidbyte/providers/README.md` | 41,573 | 55,000 |

  None of the folders `vidbyte/agents/settings/`, `vidbyte/lib/dataclasses/`, `vidbyte/lib/enums/` or `vidbyte/lib/runners/` has a README.
- `request.md:86`, the ratchet trap: "`lint/run.py` ratchet slack can hide a new finding (S009 is 346 against a baseline of 350). Compare per-rule findings with the base, not the totals."

### 1.5 Field-guide entries read (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`)

- `local-ci-verification`: gives the staged commands in §1.2. It also says the harness_threads surface tests go red locally on root-export branches.
- `strict-config-dataclasses`, `blocking-lint-invariants`, `comment-format`, `runtime-boundaries` and `fallback-coordination`.
- `provider-api-contracts`: provider facts come from the raw vendor documentation.
- `jev-capability-layout`: generative fields go on `JevAgentSettings`, and usage flows through `JevUsage`.

### 1.6 Folder README rules read (AGENTS.md: "read it to the end before you change anything inside the folder")

Neither README has a `## Notes for agents` section (`grep -n '^## Notes for agents'` returned nothing for both).

- `vidbyte/agents/README.md` "Model Fallback" (`:185-248`):
  - "bare name inherits provider and temperature; keys come from the agent's api_keys" (`:200`); "Entries may also be `FallbackModel` objects when a backup needs its own temperature" (`:206`).
  - "**Same-wire-format switches keep the transcript.** OpenAI, DeepSeek, xAI, and OpenRouter share one payload shape, so an in-flight run carries its tool history over intact. Switching across wire formats (OpenAI ↔ Anthropic ↔ Gemini) resets the transcript" (`:234-237`).
  - "Fallback requires the linear runtime and an agent with its own `provider`/`model_name`; both are rejected at construction otherwise. `fork()` inherits the chain, and `AgentForkSettings(fallback=...)` overrides it." (`:246-248`).
- `vidbyte/agents/README.md` "Spend Cap" (`:386-431`): "Construction refuses it on a non-linear runtime, a non-text runner, a configured model the pricebook cannot price (OpenRouter, which reports its own cost, is exempt), a JevAgent specialist without its own cap at or below JevAgent's, and `CodexHarnessAgent`" (`:425-427`). It also says "JevAgent's fixed-prompt agents, carry no cap by design" (`:422-423`).
- `vidbyte/agents/jev/README.md`:
  - "`settings.py` is the complete public configuration surface" (`:5`).
  - Preset propagation splits Jev's children into two groups: "specialists without their own value, clones, swarm helpers, bulk workers, and the fresh-continuation agent all inherit it through the run scope. Jev's fixed-prompt machinery (`JevRunState`, `JevHandoff`, `JevReviewer`, `JevRunBriefWriter`, and `JevClarificationAgent`) opts out with `system_prompt_presets=()`" (`:28`).
  - "Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities" (`:46`, repeated at `:53`).

---

## 2. Files this change will touch

Where the request requires an edit, the entry says so. For every other entry, "Change surface" says what a field that crosses this file must do there. It does not choose where the field lives.

### 2.1 The generative request path, end to end

`BaseAgent.arun` → `_runner_for_model` (`base.py:940`, `:1676-1691`) → `Runner.from_model(...).build()` (`utility.py:49-52`, `:81-90`) → `TextModelRunner(TextModelConfig(...))` (`text.py:33-67`) → `TextModelRunner.arun` → `dataclasses.replace(self._config, tools=…, messages=…)` (`text.py:72-79`) → `ModelProviders.text(config)` (`providers/__init__.py:41-57`) → adapter `run_text` → payload builder → `transport.request(method="POST", url=…, json_body=payload, …)`.

In every mode except DIRECT, `VidbyteGatewayTransport` wraps the adapter's body unchanged: `envelope = {"provider": …, "model": …, "body": dict(json_body or {})}` (`vidbyte/lib/http/vidbyte_gateway.py:195`).

The runner is built lazily, at the first run (`base.py:940`), not in `__init__`. A fallback hop's runner is built only when the chain switches models (`base.py:1375` → `fallback.py:193-213`).

**The 7 CLI providers.** request.md:151 maps them as claude→anthropic, grok→xai, muse→meta.

| CLI name | SDK `ModelProvider` | Adapter class (reached how) | HTTP call | Payload builder | Reads `thinking_config` / any reasoning field today | Gateway-served (AUTO default) |
|---|---|---|---|---|---|---|
| openai | `OPENAI` | `OpenAIProvider`, direct (`providers/openai.py:22`) | `POST {endpoint}/responses` (`openai.py:37`) | `_create_text_payload` (`openai.py:252-261`); sampling and cap in `_attach_sampling` (`:296-303`) | No; no `reasoning` key is ever emitted | yes (`constants/jev.py:74-81`) |
| claude | `ANTHROPIC` | `AnthropicProvider`, direct (`providers/anthropic.py:20`) | `POST {endpoint}/messages` (`anthropic.py:31`) | `_create_payload` (`anthropic.py:54-63`) | **Yes**: `if config.thinking_config: payload["thinking"] = dict(config.thinking_config)` (`anthropic.py:112-113`, inside `_attach_tools`) | yes |
| gemini | `GEMINI` | `GeminiProvider`, direct (`providers/gemini.py:18`) | `POST {endpoint}/models/{model}:generateContent` (`gemini.py:31`) | `_create_payload` (`gemini.py:58-69`); `_attach_generation_config` (`:179-197`) | **Yes**: `if config.thinking_config is not None: generation_config["thinkingConfig"] = dict(config.thinking_config)` (`gemini.py:194-195`) | yes |
| grok | `XAI` | `XAIProvider(OpenAICompatibleProvider)` (`providers/xai.py:13`). Text is inherited unchanged; xai.py overrides only images. | `POST {endpoint}/chat/completions` (`compatible.py:35`) | `OpenAICompatibleProvider._create_payload` (`compatible.py:58-66`) | No | yes |
| deepseek | `DEEPSEEK` | `DeepSeekProvider(OpenAICompatibleProvider)` (`compatible.py:175`). It overrides only `_extract_chat_text`. | same (`compatible.py:35`) | same (`compatible.py:58-66`) | No | yes |
| glm | `GLM` | `GLMProvider(OpenAICompatibleProvider)` (`compatible.py:220`). It overrides only `_extract_chat_text`. | same | same | No | **no**: DIRECT only |
| muse | `META` | `MetaProvider(OpenAICompatibleProvider)` (`compatible.py:243-244`, no overrides). Default model `"muse-spark-1.1"` (`lib/registries/models.py:82`), endpoint `"https://api.meta.ai/v1"` (`:103`). | same | same | No | **no**: DIRECT only |

`git grep -n "thinking_config" -- vidbyte tests` returns:
- three code sites: `model_configs.py:71`, `anthropic.py:112-113` and `gemini.py:194-195`;
- three test sites: `tests/features/sdk_managed_text/test_managed_text_selection.py:56` and `test_managed_text_wire_contract.py:64,65,71`.

No agent, runner or settings object sets `thinking_config`.

### 2.2 Entries

**`vidbyte/agents/base.py`** (1,847 lines)
- *Today.* This is the base agent.
  - The constructor (`:92-130`) takes `temperature: float | None = None` (`:112`), `model_mode` (`:109`) and `fallback` (`:128`).
  - It builds `AgentRunnerConfig(api_keys=…, provider=…, model_name=…, temperature=temperature, timeout_seconds=…, run_id=…, model_mode=…)` (`:193-201`) and then `AgentFallback.from_spec(...)` (`:204`).
  - It refuses spend-cap misconfiguration at construction (`:250-257`).
- *Change surface.* The request requires the setting to reach "every `BaseAgent`" (`request.md:38,51`). Inside this file, the existing model knob `temperature` passes through these sites:

  | Line | What happens to `temperature` |
  |---|---|
  | `:112` | constructor kwarg |
  | `:197` | stored in `AgentRunnerConfig` |
  | `:561` | `export_state` writes `temperature=self.runner_config.temperature` |
  | `:606` | `restore` passes `temperature=state.temperature` |
  | `:1685` | `_runner_for_model` passes `temperature=self.runner_config.temperature` to `Runner.from_model` |

  - `_export_runtime_config` (`:634-669`) stores the fallback chain as `[m.identity() for m in self.fallback.models[1:]]` (`:652`), and `restore` passes those strings back as `fallback=` (`:613`).
  - `_export_loop_settings` (`:671-695`) lists loop fields by name. R3 added `"max_spend_usd"` there (`:680`).
  - `_runner_for_model` passes only `{"timeout_seconds": …}` as `options` (`:1679`).
- *Pattern.* The construction refusal is: `spend_cap_refusal = AgentSpendCap.model_refusal(self.agent_loop_settings.max_spend_usd, self.runner_config, self.fallback)`, then `raise ConfigurationError(f"Agent {name} sets max_spend_usd, but {spend_cap_refusal}", details={"agent": name})` (`:255-257`).

**`vidbyte/lib/dataclasses/agents.py`** (488 lines)
- *Today.* It holds three records that carry a model knob:
  - `AgentRunnerConfig` (`:305-325`) is frozen, with fields `api_keys, provider, model_name, temperature, run_id, timeout_seconds, model_mode`. `__post_init__` checks only `api_keys` and `model_mode`.
  - `FallbackModel` (`:329-354`) has `provider, model, temperature: float | None = None`. Its `__repr__` names the temperature (`:351-354`).
  - `AgentForkSettings` (`:433-488`) has `temperature: float | None = None` (`:464`), checked as `if self.temperature is not None and not 0.0 <= self.temperature <= 2.0: raise AgentForkConfigurationError("temperature must be between 0 and 2 when provided.")` (`:475-476`).
- *Change surface.* Any field that travels like `temperature` crosses all three records: the agent runner identity, the fallback hop, and the fork override.
- *Pattern.* `AgentRunnerConfig.__post_init__` refusal: `raise ConfigurationError("AgentRunnerConfig.model_mode must be a TextModelMode value.")` (`:324-325`).

**`vidbyte/lib/runners/utility.py`**
- *Today.* `Runner.__init__(…, temperature: float | None = None, options: Mapping[str, Any] | None = None)` (`:29-47`). `Runner.from_model` (`:49-52`). `build` creates `TextModelRunner(TextModelConfig(provider=…, model=…, **config_options), transport=transport)` (`:90`).
- *Change surface.* `_config_options_for` (`:117-134`) adds `temperature` only for text runners: `if self.temperature is not None and runner_type == RUNNER_TYPE_TEXT: options["temperature"] = self.temperature` (`:131-132`). It then **silently drops** any key that is not a field of the config dataclass: `return {key: value for key, value in options.items() if key in allowed}` (`:134`).
- *Pattern.* The `temperature` keyword plus the text-only filter above.

**`vidbyte/lib/dataclasses/model_configs.py`** (601 lines)
- *Today.* `TextModelConfig` (`:54-109`) is `@dataclass(frozen=True, slots=True)`.
  - Its fields, in order (`:56-79`), are `provider, model, api_keys, system, messages, temperature, top_p, max_output_tokens, stop_sequences, response_format, tools, tool_choice, tool_config, safety_settings, cached_content, thinking_config, metadata, extra_body, endpoint, timeout_seconds, mode, prompt_index, vidbyte_api_key`.
  - `thinking_config: Mapping[str, Any] | None = None` (`:71`).
  - `__post_init__` (`:81-102`) refuses an unserved provider in any gateway mode (`:95-96` → `_require_gateway_shape`, `:204-209` raises `UnsupportedProviderError`).
  - Range checks run in `validate()` (`:111-121`), not in `__post_init__`. For example, `_validate_temperature` (`:211-214`): `raise ConfigurationError("temperature must be between 0 and 2.")`.
  - `DecisionModelConfig` (`:503-587`) is covered in §2.6.
- *Change surface.* This is the record every adapter reads. A field that adapters read has to be present on the `config` they receive. The field order is pinned by a test (§3).
- *Pattern.* Comment style `# @intent text-mode-shape-fails-at-construction` (`:87`). Validators are `_validate_*` helpers called from `validate()`.

**`vidbyte/lib/runners/text.py`**
- *Today.*
  - `__init__` calls `config.validate()` (`:48`).
  - For a gateway call it applies `replace(config, max_output_tokens=config.max_output_tokens or VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS, timeout_seconds=max(VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS, config.timeout_seconds))` (`:57-62`).
  - `arun` replaces only per-call fields (`tools, tool_choice, messages, response_format, prompt_index`, `:72-79`) and keeps every other config field.
  - In gateway modes it wraps the transport (`:91-98`).
- *Change surface.* This is the layer that turns gateway use into body changes (the output cap). A config field survives `arun` unchanged.

**`vidbyte/agents/fallback.py`** (235 lines) and **`vidbyte/agents/settings/fallback.py`**
- *Today.*
  - `_primary_model` returns `FallbackModel(provider=provider, model=model_name, temperature=runner_config.temperature)` (`fallback.py:131-142`).
  - `build_runner(index)` lazily builds `Runner.from_model(…, temperature=target.temperature, options=options).build()` (`fallback.py:193-213`).
  - `_resolve_entry` handles chain entries (`settings/fallback.py:139-146`): `if isinstance(entry, FallbackModel): return entry`. A string entry becomes `FallbackModel(provider=resolved_provider, model=model, temperature=primary.temperature)`.
- *Change surface.* This is where each chain hop gets its model knobs. String hops inherit the primary's value. An explicit `FallbackModel` keeps its own value, which may be `None`.
- *Pattern.* `# @intent fallback-runner-keeps-agent-timeout` (`fallback.py:196-198`).

**`vidbyte/agents/spend_cap.py`** (R3, the model for chain-wide construction checks)
- *Today.* `model_refusal(max_spend_usd, runner_config, fallback)` (`:48-69`) builds one `Runner` utility per chain entry with `_chain_runners` (`:90-98`). It does not call `.build()`, and it returns a refusal string or `None`.
- *Pattern.* `return [Runner.from_model(provider=entry.provider, model_name=entry.model) for entry in fallback.models]` (`:98`). The header says: "The construction refusals stop an agent before any spend; a model that only appears at run time falls to the blind stop instead." (`:5`).

**`vidbyte/agents/jev/settings.py`** (417 lines)
- *Today.*
  - `JevAgentSettings` (`:131-151`) has fields `name, system_prompt, provider, model_name, api_keys, temperature, timeout_seconds, tools, permission_policy, loop, agents, bulk_work, alignment, outputs, vidbyte_api_key, model_mode, system_prompt_presets`. It has **no fallback field**.
  - `__post_init__` (`:153-187`) calls `self._validate_temperature()` (`:177`).
  - `_validate_temperature` (`:225-231`): `if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 2.0: raise ConfigurationError("JevAgentSettings.temperature must be a finite number between 0 and 2.")`.
  - `JevRunBriefSettings` (`:285-339`) has its own `temperature` (`:299`) and validator (`:334-339`).
  - `JevRuntimeSettings.decision` (`:374`) is covered in §2.6.
  - `__all__` (`:417`).
- *Change surface.* The request requires a field here: "`JevAgentSettings` carries it for JevAgent's main model" (`request.md:51`). AGENTS.md says the same: "A new JevAgent capability is a named, validated field on `JevAgentSettings`."
- *Pattern.* `_validate_temperature` above. The header (`:6`) says: "Add a generative-agent field to JevAgentSettings or a Jev policy setting to JevRuntimeSettings".

**`vidbyte/agents/jev/agent.py`**
- *Today.* It maps `JevAgentSettings` into `BaseAgent`:
  - `super().__init__(…, provider=settings.provider, model_name=settings.model_name, temperature=settings.temperature, timeout_seconds=settings.timeout_seconds, …)` (`:92-107`; temperature at `:103`). No `fallback=` is passed.
  - The FRESH continuation factory `partial(BaseAgent, …, temperature=settings.temperature, …)` (`:63-77`; temperature at `:71`).
  - The specialist guards `_require_metered_specialists` (`:115-127`) and `_require_capped_specialists` (`:129-145`). The second is the R3 rule that each specialist carries its own cap.
- *Change surface.* This is the main model, plus every child built here.

**Jev child agents that copy `settings.temperature`** (each builds a `BaseAgent` from `JevAgentSettings`):

| File:line | Child |
|---|---|
| `vidbyte/agents/jev/bulk_work.py:56` | bulk-work workers |
| `vidbyte/agents/jev/compute/clone.py:39` | CLONE copies |
| `vidbyte/agents/jev/compute/swarm.py:51` | SWARM helpers |
| `vidbyte/agents/jev/done/handoff.py:166` | handoff writer |
| `vidbyte/agents/jev/done/reviewer.py:42` | done reviewer |
| `vidbyte/agents/jev/done/run_state.py:286` | run-state writer |
| `vidbyte/agents/jev/gate/clarification.py:59` | clarification agent (constructed at `gate/gate.py:52`) |
| `vidbyte/agents/jev/agent.py:71` | FRESH continuation |
| `vidbyte/agents/jev/brief/writer.py:65` | brief writer, with `temperature=brief.temperature` (constructed at `brief/keeper.py:31`) |

- *Change surface.* `request.md:71` names only the "brief model and specialists" as keeping their own settings. These eight other children copy the main agent's `temperature` today.

**Other `BaseAgent` builders that copy `temperature`** (each is a copy path for a field that travels like temperature):
- `vidbyte/agents/fork.py:72`: `temperature=agent.runner_config.temperature if settings.temperature is None else settings.temperature`.
- `vidbyte/agents/continual_trace.py:66` and `vidbyte/agents/handoff.py:70`: `temperature=source_agent.runner_config.temperature`.
- `vidbyte/agents/aggregation.py:249,321,354`: the proposers share one temperature.
- `vidbyte/agents/infinite/agent.py:93`, `vidbyte/agents/infinite/launch.py:307` and `vidbyte/agents/infinite/settings.py:120,177-179`: `InfiniteMemoryAgentSettings.temperature`.
- `vidbyte/paradigms/context_minimal_fanout/paradigm.py:88,167,199` and `types.py:435`.
- `vidbyte/tools/builtins/fork/fork.py:165,193,287-297,473`: the **model-callable** fork tool accepts `"temperature": {"type": "number", "minimum": 0, "maximum": 2, "description": "Optional child runner temperature override."}` (`:473`).

**Session checkpoint: `vidbyte/lib/dataclasses/sessions.py`, `vidbyte/sessions/serialization.py`**
- *Today.*
  - `RunState` has a top-level `temperature: float | None` (`sessions.py:64`), and `SESSION_SCHEMA_VERSION: int = 1` (`sessions.py:24`).
  - Serialization writes `"temperature": state.temperature` (`serialization.py:148`) and reads `temperature=data.get("temperature")` (`:176`).
  - A different `schema_version` is rejected (`serialization.py:249`, `sessions/portable.py:121`).
  - Loop settings round-trip as a dict (`loop_settings=…`, `vidbyte/sessions/serialization.py:157,185`).
- *Change surface.* This is the checkpoint copy path. R3 tested it (`tests/features/loop_spend_cap/test_loop_spend_cap_copy_paths.py:103`).

**YAML surfaces: `vidbyte/lib/dataclasses/config.py`, `vidbyte/lib/dataclasses/agent_descriptor.py`, `vidbyte/lib/config/loader.py`**
- *Today.* Both YAML records carry `temperature` and tighten it per provider.
  - `config.py`: `AgentSettings` (`:314-371`) declares `temperature` (`:322`). Its `_ALLOWED_FIELDS` (`:341-346`) rejects unknown keys. The value flows through `from_payload` (`:396`), `to_agent_kwargs` (`:420`) and `expected_structure` (`:447`). `_validated_temperature` (`:531-546`) applies `_PROVIDER_TEMPERATURE_CEILING = {"anthropic": 1.0}` (`:85`).
  - `agent_descriptor.py`: `AgentDescriptor` (`:107-170`) declares `temperature` (`:120`). It is checked at `:265-275` against its own `_PROVIDER_TEMPERATURE_CEILING: dict[str, float] = {"anthropic": 1.0}` (`:64`).
  - `vidbyte/lib/config/loader.py:259` builds `AgentDescriptor(…, temperature=raw.get("temperature"), …)`.
- *Change surface.* This is a copy path for a field that YAML can set. R3 tested the YAML loop cap (`test_loop_spend_cap_copy_paths.py:122,136`).
- *Pattern.* The per-provider ceiling dict is the only existing per-provider capability check on a model knob.

### 2.3 Provider adapters (what each sends, what each parses)

**`vidbyte/providers/__init__.py`**
- `ModelProviders.text` (`:41-57`) maps the 11 text providers to adapter classes.
- `ModelProviders.streaming_text` (`:96-100`) maps only OpenAI and Anthropic.

**`vidbyte/providers/openai.py`**
- *Payload.*
  - `_create_text_payload`: `{"model": config.model, "input": self._create_input(config, prompt)}`, then `_attach_instructions`, `_attach_sampling`, `_attach_tools`, `_attach_response_format`, `_attach_metadata`, `_attach_extra_body` (`:252-261`).
  - `_attach_sampling` sets `temperature`, `top_p` and `max_output_tokens` (`:296-303`).
  - `_attach_extra_body`: `payload.update(dict(config.extra_body))` (`:340-343`).
  - History: `_responses_items` (`:274-288`), with the comment "Item ids (fc_...) are never echoed: without their reasoning items reasoning models reject them." (`:276`).
- *Parsing.*
  - `_extract_response_text` (`:369-383`) reads `output_text` or the output items.
  - `_collect_output_text` (`:385-398`): `# @intent reasoning-items-are-not-the-answer` / `# A "reasoning" item's content is the model's chain of thought (reasoning_text), never the answer; streaming yields only output_text.` / `if item.get("type") == "reasoning": return` (`:389-392`).
  - `stream_text` (`:120-128`) yields only `output_text` deltas (`_extract_stream_delta`, `:201-227`).
- *Usage.* `run_text` passes `usage=parsed.get("usage")` (`:37-47`).

**`vidbyte/providers/anthropic.py`**
- *Payload.*
  - `_create_payload`: `{"model": config.model, "max_tokens": config.max_output_tokens or 1024, "messages": …}` (`:56`). The 1024 default applies only in DIRECT. A gateway call sets 32,768 first (`text.py:57-62`).
  - `_attach_response_format` assigns `payload["output_config"] = {"format": {...}}` as a whole (`:65-70`).
  - `_attach_sampling` (`:97-104`).
  - `_attach_tools` also attaches `thinking` (`:106-113`).
  - `_attach_extra_body` uses `payload.update(...)` (`:121-124`).
- *Parsing.* `_extract_text` keeps text blocks only (`:161-181`). The stream delta reads only `text_delta` (`:136-159`).
- *Usage.* A billed 200 with no usable text keeps its usage on the error: `exc.details["usage"] = dict(usage)` (`:34-39`).

**`vidbyte/providers/compatible.py`** (`OpenAICompatibleProvider` plus the DeepSeek, GLM, MiniMax, Kimi, Meta and Mistral subclasses)
- *Payload.*
  - `_create_payload` (`:58-66`).
  - `_attach_sampling` maps `max_output_tokens` to `payload["max_tokens"]` and stop sequences to `"stop"` (`:80-89`).
  - `_attach_extra_body` uses `payload.update(...)` (`:131-134`).
- *Parsing.*
  - `_extract_chat_text` (`:136-162`) reads `message["content"]` only. It returns `""` for a tool-call turn (`:152-155`).
  - Content that is a list is joined from its text chunks: `# @intent chunked-content-answers-with-its-text-chunks` / `# Mistral reasoning models send content as a list of chunks; the answer is the text chunks, never the thinking.` (`:156-159`).
  - No code reads `reasoning_content`. `git grep reasoning_content -- vidbyte` matched nothing in the adapters (this session's grep of reasoning fields).
  - DeepSeek (`:175-217`) raises on `finish_reason == "insufficient_system_resource"` and unwraps whole-JSON fences.
  - GLM (`:220-225`) raises on `"network_error"`.
  - MiniMax (`:228-236`): `# @intent inline-thinking-is-not-the-answer` (`:232`), then `_LEADING_THINK.sub("", …, count=1)`. The pattern `_LEADING_THINK = re.compile(r"\A\s*<think>.*?</think>\s*", re.DOTALL)` is at `:19`.
  - Meta (`:243-244`) has no overrides.

**`vidbyte/providers/xai.py`**: `XAIProvider(OpenAICompatibleProvider)`. It overrides only `__init__` and the image methods (`:13-57`), so its text payload is `compatible.py:58-66`.

**`vidbyte/providers/gemini.py`**
- *Payload.* `_attach_generation_config` (`:179-197`) builds `temperature`, `topP`, `maxOutputTokens`, `responseMimeType`/`responseSchema` and `thinkingConfig`. `_attach_extra_body` uses `payload.update(dict(config.extra_body))` (`:216-221`), so a `generationConfig` in `extra_body` replaces the whole adapter `generationConfig`, `thinkingConfig` included (tested at `test_managed_text_wire_contract.py:134-137`).
- *Parsing.* `_extract_text` (`:288-306`): `# @intent thought-parts-are-not-the-answer` / `# With thinkingConfig.includeThoughts, Gemini sends thought summaries as parts marked "thought": true` (`:298-301`).
- *Usage.* Usage comes from `parsed.get("usageMetadata")` (`:33`).

**`vidbyte/providers/openrouter.py`** (not one of the 7, a neighbour): it adds `payload["usage"] = {"include": True}` (`:56-60`).

**Gateway: `vidbyte/lib/http/vidbyte_gateway.py`, `vidbyte/lib/constants/jev.py`**
- `VIDBYTE_MANAGED_TEXT_PROVIDERS` = {OPENAI, ANTHROPIC, GEMINI, XAI, DEEPSEEK, KIMI} (`constants/jev.py:74-81`), "cerredz/Vidbyte backend spec r3 section 9.2.8 at commit a14b37e7e".
- The 422 reason text includes "a body field outside the gateway's allowed list" (`vidbyte_gateway.py:124`).
- `TextModelMode` (`vidbyte/lib/enums/text_model.py:17-22`) has `AUTO = "auto"`, `VIDBYTE_MANAGED = "vidbyte_managed"` and `DIRECT = "direct"`. Its header says "AUTO always uses the gateway and needs a Vidbyte key, even when a provider key is held (the call then relays)." (`:7`).

**`vidbyte/lib/runners/streaming_text.py`** (neighbour): "Streams text from a provider over server-sent events, only in TextModelMode.DIRECT" (`:3`). It builds its own `TextModelConfig` (`:103`).

### 2.4 Tool-loop history: what is echoed back to the model

`vidbyte/lib/tools/formatter.py`:
- `format_assistant_tool_calls` (`:322-332`) dispatches by provider.
- OpenAI Responses: `_assistant_turn_openai_responses` (`:359-381`) keeps only `function_call`/`tool_call` items and `output_text` parts. **Reasoning items are not kept.**
- Chat completions: `_assistant_turn_openai` returns `{**message, "tool_calls": […]}` (`:347`). This is the whole assistant message, including any extra keys the provider returned.
- Anthropic: `_assistant_turn_anthropic` returns `{"role": "assistant", "content": list(content)}` (`:396`). This is the full content list, including any `thinking` blocks.
- Gemini: `_assistant_turn_gemini` returns `dict(content)` (`:415`). These are the full parts, including thought parts.

### 2.5 Usage and reasoning tokens (where they reach `UsageRollup` and the spend cap)

The usage chain:
1. The adapter puts `usage` on `TextModelResponse`.
2. `AgentRuntime` calls `self.usage_tracker.record_call(raw_result)` (`vidbyte/agents/runtime.py:478`). Billed failures go through `record_billed_failure(...)` (`runtime.py:804`).
3. Context-window side calls go through `_invoke_context_window_runner`, which awaits `runner.invoke(...)` on **the agent's own `RunnerHandle`** and then calls `record_call(response)` (`runtime.py:1054-1061`). Reflexion reflections pass the same `handle: RunnerHandle` to `_invoke_with_middleware` and then call `record_call(raw_result)` (`vidbyte/agents/algorithms/reflexion.py:110-133`).
4. `UsageTracker._record` (`vidbyte/agents/pricing/tracker.py:87`) parses the usage through `_parse_usage`, which calls `provider.usage_class()` (`tracker.py:213-222`). The provider-to-class map is in `vidbyte/lib/enums/model_provider.py:63-75`.
5. `rollup()` sums `usage.output_tokens` and `cost_usd` (`tracker.py:168-197`).
6. The spend cap reads `rollup.cost_usd` and `rollup.cost_measured` (`spend_cap.py:34-48`).

`UsageRollup` has no reasoning-token field. Its token fields are `input_tokens, output_tokens, total_tokens, cached_input_tokens` (`pricing/records.py:70-91`).

| Provider | Usage class | Output measure that is priced | Reasoning / thinking handling |
|---|---|---|---|
| OpenAI | `OpenAIUsage` (`pricing/openai.py:26-56`) | `output_tokens` as reported (`:42`) | `reasoning_tokens=cls.nested_int(payload, "output_tokens_details", "reasoning_tokens")` (`:45`) is parsed and **not** added. `providers/README.md:570-572` says reasoning tokens "are **already included** in `output_tokens`". Vendor quote unverified. |
| xai, deepseek, glm, meta | `ChatCompletionUsage` (`pricing/compatible.py:29-91`) | `_billed_output` (`:61-71`) | `# @intent reasoning-outside-completion-is-billed-output`: it adds `completion_tokens_details.reasoning_tokens` only when `total == prompt + completion + reasoning` (`:69-70`). Otherwise `completion_tokens` stays as reported. |
| Anthropic | `AnthropicUsage` (`pricing/anthropic.py:36-125`) | `output_tokens` (`:51`) | No thinking-specific field is parsed. Whether the vendor's `output_tokens` includes thinking is unverified. |
| Gemini | `GeminiUsage` (`pricing/gemini.py:26-81`) | `output_tokens = candidates + thoughts` (`:58-63`) | `thoughtsTokenCount` is parsed (`:44`) and billed as output. |

The loop's `max_tokens` budget uses provider totals in `vidbyte/lib/token_usage.py:36-53`. Its fallback sum includes `"thoughtsTokenCount"` (`:48`).

### 2.6 Enums, validation, root exports, the release record

**Existing effort enums** (all three are already root exports; `py -3.11` import check this session):

| Enum | Module:line | Base | Members (value) |
|---|---|---|---|
| `CodexReasoningEffort` | `vidbyte/lib/enums/codex.py:34-43` | `(str, Enum)` | `PROVIDER_DEFAULT=""`, `NONE="none"`, `MINIMAL="minimal"`, `LOW="low"`, `MEDIUM="medium"`, `HIGH="high"`, `XHIGH="xhigh"` |
| `GrokReasoningEffort` | `vidbyte/lib/enums/native_threads.py:147-156` | `StrEnum` | `NONE … XHIGH` plus `MAX="max"` ("The reasoning efforts grok --reasoning-effort accepts.") |
| `MuseReasoningEffort` | `vidbyte/lib/enums/native_threads.py:159-168` | `StrEnum` | `NONE … XHIGH` plus `ULTRA="ultra"` ("The reasoning efforts muse exec --reasoning-effort accepts.") |

These enums are used here:
- `CodexReasoningEffort`: `vidbyte/lib/dataclasses/codex.py:145-146` (`default_reasoning_effort`, default `PROVIDER_DEFAULT`) and `:252` (`CodexTurnSettings.effort`). `vidbyte/agents/codex/config.py:264` sends it only `if settings.default_reasoning_effort.value:`.
- `GrokThreadConfig.reasoning_effort: GrokReasoningEffort | None = None` (`vidbyte/lib/dataclasses/native_threads.py:452`).
- `MuseThreadConfig.reasoning_effort: MuseReasoningEffort | None = None` (`:487`).

**Enum export list** (`vidbyte/lib/enums/__init__.py`):
- It imports each enum from its module, for example `from vidbyte.lib.enums.text_model import TextModelMode` (`:214`) and `from vidbyte.lib.enums.decision_model import DecisionModelMode` (`:97`).
- It lists the enum in `__all__` (`:217-373`).

**Validation helpers** (`vidbyte/lib/dataclasses/validation.py`):
- `RecordFieldValidator.require_enum(value, enum_type, field_name)`, for a member only (`:122-126`).
- `RecordFieldConverter.to_enum(value, enum_type, field_name)` takes "A member of enum_type, or the exact value string of one … case is not folded." (`:222-230`). On failure it raises `ConfigurationError(f"{field_name} must be one of {', '.join(members)}; got …", details={"field": field_name})` (`:230`).
- Pattern in use: `object.__setattr__(self, "reasoning_effort", RecordFieldConverter.to_enum(self.reasoning_effort, GrokReasoningEffort, "GrokThreadConfig.reasoning_effort"))` (`native_threads.py:459`, guarded by `if self.reasoning_effort is not None:` at `:458`).
- R3's loop-field pattern is `RecordFieldValidator.require_number(max_spend_usd, "AgentLoopSettings.max_spend_usd", maximum=sys.float_info.max) if max_spend_usd is not None else None` (`vidbyte/agents/settings/loop.py:82-89`).

**Errors** (`vidbyte/lib/errors/base.py`):
- `class ConfigurationError(VidbyteSdkError)` (`:330`) is a root export.
- `class UnsupportedProviderError(VidbyteSdkError)` (`:334`) is not a root export and is not a `ConfigurationError` subclass (import check).

**Capability-table precedent** (for "a value a provider cannot express"):
- `vidbyte/lib/configs/structured_output.py` declares `PROVIDER_SUPPORT` (`:37`) and `MODEL_SUPPORT` (`:51`) with `STRUCTURED_OUTPUT_AS_OF = "2026-07-28"` (`:31`).
- `vidbyte/lib/registries/structured_output.py:38-87` resolves them. Its header (`:5-8`) says "provider adapters must not duplicate it or infer capability from provider names".
- No registry in `vidbyte/lib/registries/` names reasoning or thinking (`git grep -i "reason\|thinking"` on `models.py` and `pricing.py` returned nothing).

**`vidbyte/__init__.py`** (1,661 lines; the request requires an edit for `DecisionModelConfig`)
- *Today.* The header bullet "- Agent setting exports: AgentLoopSettings (loop limits), PermissionPolicy … TextModelMode … JevDynamicComputeOption" (`:13`) was added by #1190.
- The eager imports include the `from vidbyte.lib.enums import (…)` block (`:490-504`, with `TextModelMode` at `:503`).
- `__all__ = [` (`:831`). `_LAZY_NATIVE_THREAD_EXPORTS` (`:1573`) is the lazy mapping that S015 reads.
- `len(vidbyte.__all__) == 733` (import check).
- Root membership, checked with `py -3.11` this session:

  | Name | Root export |
  |---|---|
  | `TextModelMode`, `AgentLoopSettings`, `JevAgentSettings`, `JevRuntimeSettings`, `JevRunBriefSettings`, `JevSpecialist`, `ConfigurationError`, the three effort enums | yes |
  | `DecisionModelConfig`, `DecisionModelMode`, `ModelProvider`, `TextModelConfig`, `FallbackModel`, `AgentFallbackSettings`, `UnsupportedProviderError` | **no** |

- *Pattern (#1190, `git show 22993b5f -- vidbyte/__init__.py`).* The commit made three edits:
  1. it added one header bullet;
  2. it added the name to an existing eager import block (`from vidbyte.agents import (… AgentLoopSettings, …)`, `from vidbyte.lib.dataclasses.security import PermissionPolicy`, `from vidbyte.lib.enums import (… JevDynamicComputeOption, … TextModelMode,)`);
  3. it inserted one `__all__` string per name.

  The same commit regenerated `contracts/sdk-public-api.json`, which changed the `source.commit` line plus one sorted line per name.

**`DecisionModelConfig`** (`vidbyte/lib/dataclasses/model_configs.py:503-587`)
- Fields:
  - `provider: ModelProvider | str = ModelProvider.TYPESAFE`
  - `model: str = JEV_DEFAULT_MODEL`
  - `api_key: str | None = field(default=None, repr=False)`
  - `endpoint: str | None = None`
  - `timeout_seconds: float = JEV_DEFAULT_TIMEOUT_SECONDS`
  - `retry_count: int = JEV_DEFAULT_RETRY_COUNT`
  - `mode: DecisionModelMode = DecisionModelMode.TYPESAFE` (`:507-513`)
- `__post_init__` (`:515-536`) raises `ConfigurationError("mode must be a DecisionModelMode value.")` for a non-enum mode (`:526-527`).
- `vidbyte_managed()` takes no arguments and returns `cls(mode=DecisionModelMode.VIDBYTE_MANAGED)` (`:582-587`).
- `JevRuntimeSettings.__post_init__` refuses anything else:
  - `if type(self.decision) is not DecisionModelConfig: raise ConfigurationError(...)`;
  - `if self.decision.mode is not DecisionModelMode.VIDBYTE_MANAGED: raise ConfigurationError(...)` (`vidbyte/agents/jev/settings.py:383-386`).
- Its other public paths are `vidbyte.lib.config` (`vidbyte/lib/config/__init__.py` re-exports it with `TextModelConfig`, `DecisionModelMode`, `ModelProvider` and `TextModelMode`) and `vidbyte.lib.dataclasses.model_configs.__all__` (`:590-601`).

**`contracts/sdk-public-api.json`** (741 lines, 733 exports): `{"schema_version": 1, "source": {"repository": "cerredz/Vidbyte-SDK", "commit": "731f094c…", "generator": "scripts/generate-sdk-public-api.py"}, "distribution": "vidbyte-sdk", "version": "0.4.0", "exports": [...]}`. It is generated and never hand-edited (`scripts/generate-sdk-public-api.py:8`).

**`docs/design/release-0-4-0.md`** (19 lines; the request requires an edit)
- The "**Later changes on `main`.**" bullet (`:17`) ends with: "The loop spend cap (#1192) adds `AgentLoopSettings.max_spend_usd` … No root name, `FailureCode` member, or default changes, so the contract still lists 733 exports."
- `:19` also tallies the count: "The contract now lists 733 exports, against 639 at `v0.3.0`: 94 added and none removed, 3 from #1099, … 4 from #1190, and `SystemPromptPreset` from #1095."

**Docs-in-code neighbours.** `vidbyte/providers/README.md` lists the reasoning doc links. These links were not fetched:

| Provider | Line | Link |
|---|---|---|
| OpenAI | `:133` | "Reasoning models" `https://developers.openai.com/api/docs/guides/reasoning` |
| OpenAI | `:134` | "Reasoning best practices" `…/reasoning-best-practices` |
| Anthropic | `:165` | "Extended thinking" `https://platform.claude.com/docs/en/build-with-claude/extended-thinking` |
| Gemini | `:179` | "Thinking" `https://ai.google.dev/gemini-api/docs/thinking` |
| DeepSeek | `:243` | "Thinking mode" `https://api-docs.deepseek.com/guides/thinking_mode` |
| DeepSeek | `:244` | streaming example `…/thinking_mode_api_example_streaming` |
| GLM | `:275` | "Thinking" `https://docs.z.ai/guides/capabilities/thinking` |
| GLM | `:276` | "Thinking mode" `https://docs.z.ai/guides/capabilities/thinking-mode` |
| OpenRouter | `:444` | "Reasoning tokens" |
| xAI | none | The section `:204-230` lists "Models" `:206` and "Chat inference" `https://docs.x.ai/developers/rest-api-reference/inference/chat` `:208`. It has no reasoning page. |
| Meta/Muse | none | The Meta Llama section `:362-385` and the table row `:101` name Llama resources. `api.meta.ai` and Muse are not mentioned. |

The file is 41,573 characters against a ceiling of 55,000.

---

## 3. Tests that cover those files

**Framework.**
- `pytest==8.3.5` and `pytest-asyncio==1.3.0` (`pyproject.toml:48-49`), with `[tool.pytest.ini_options] testpaths = ["tests"]` (`:78-79`).
- Many files are `unittest.TestCase` classes collected by pytest.
- Feature packs live in `tests/features/<slug>/` with `FEATURE.md`, `README.md`, a `*_fixtures.py` and `test_*.py` files (see `tests/features/loop_spend_cap/README.md`).

**HTTP seams already used.**
- `HttpTransport.request(*, method, url, headers, json_body, timeout_seconds, retry_count, …, idempotency_key, …)` (`vidbyte/lib/http/transport.py:55`) is the one network seam.
- Three styles fake it:
  1. **Adapter-level scripted transport.** `tests/test_gemini_provider_text.py:30-35` defines `class _ScriptedTransport` with `async def request(self, *, method, url, headers, json_body=None, timeout_seconds=60.0, **kwargs) -> HttpResponse`. It drives `GeminiProvider(model="test-model", api_keys=[…], mode=TextModelMode.DIRECT)` and then `provider.run_text(...)` (`:41-44`). The test key is built at run time from parts (`:26`).
  2. **Runner-level recorder.** `tests/features/sdk_managed_text/managed_text_fixtures.py:61-79` defines `class ScriptedGateway`, which "records each request and answers from a script". `RUNNER_TRANSPORT_TARGET = "vidbyte.lib.runners.text.HttpTransport"` is at `:37`, `MANAGED_MODELS` at `:40-47` and `UNMANAGED_TEXT_PROVIDERS` at `:49-55`. `test_managed_text_wire_contract.py:81-109` builds `TextModelRunner(TextModelConfig(...), transport=transport)` and reads `transport.requests[0]["json_body"]["body"]` for the gateway, or `["json_body"]` for DIRECT.
  3. **Agent-level, R3.** `tests/features/loop_spend_cap/test_loop_spend_cap_acceptance.py:78-123` defines a `GatewayWire` callable and calls `monkeypatch.setattr(HttpTransport, "request", wire)`. It runs the root `vidbyte.Agent` end to end in AUTO mode and asserts on `wire.bodies` ("the cap never reaches the model's request"). The R3 pack's other files bind a `ScriptedRunner` (`loop_spend_cap_fixtures.py:177-197`) through `priced_agent` → `bind_test_runner` (`:308-322`). That bypasses the adapters.

**Tests that pin what this change touches.**

| Test | What it pins | Why it matters here |
|---|---|---|
| `tests/features/sdk_managed_text/test_managed_text_selection.py:54-58` and `:344` | `EXPECTED_TEXT_CONFIG_FIELDS` is the exact ordered field list of `TextModelConfig`, asserted by `self.assertEqual([field.name for field in fields(TextModelConfig)], EXPECTED_TEXT_CONFIG_FIELDS)`. `:346` also builds `TextModelConfig` positionally (`provider, model, api_keys`). | Any new `TextModelConfig` field turns it red. |
| `tests/features/sdk_managed_text/test_managed_text_wire_contract.py:46-54` | `EMITTED_KEYS`, "copied from the table, not from the adapters" of `docs/spec/managed-generative-models/spec.md` §9.2 (not read; docs opaque). | See the key lists below. |
| `tests/features/sdk_managed_text/test_managed_text_wire_contract.py:55` | `GEMINI_GENERATION_CONFIG_KEYS = {"temperature", "topP", "maxOutputTokens", "responseMimeType", "responseSchema", "thinkingConfig"}` | Same allow-list rule for Gemini. |
| `tests/features/sdk_managed_text/test_managed_text_wire_contract.py:63-79` | `FULL_CONFIG` passes `thinking_config` for OpenAI (`{"effort": "low"}`, which the OpenAI adapter ignores), Anthropic and Gemini. | — |
| `EmittedKeyTests` (`:169-191`) | It asserts `set(body) <= EMITTED_KEYS[provider]` (`:181`) and that the managed body equals the DIRECT body. The header (`:6`) says: "When backend's allowed lists or an adapter's emitted keys change, update EMITTED_KEYS from the spec's section 9.2 table, never from the adapter's current output." | — |
| `tests/test_compatible_provider_text.py:60-61,68` | Mistral chunk thinking and MiniMax inline thinking are kept out of the answer. | — |
| `tests/test_gemini_provider_text.py:46-52` | Gemini thought parts are kept out of the answer. | — |
| `tests/test_agent_pricing.py:61-72` | OpenAI `output_tokens_details.reasoning_tokens` is parsed. | — |
| `tests/test_agent_pricing.py:147-171` | The chat `completion_tokens_details.reasoning_tokens` billed-output convention. | — |
| `tests/features/sdk_model_usage/test_billed_unusable_replies.py:9,35` | "Gemini can spend its whole budget on thinking and return no parts". | — |
| `tests/features/loop_spend_cap/test_loop_spend_cap_copy_paths.py:103-176` | Checkpoint, YAML, fork, and fork-tool copy paths, including `test_the_fork_tool_refuses_any_model_supplied_cap` (`:176`). | The R3 template for "every file a field must reach". |
| `tests/features/loop_spend_cap/test_loop_spend_cap_refusals.py` | Construction refusals for primary and fallback models. Its README says it "checks the construction refusals: non-linear runtimes, non-text runners, unpriced primary and fallback models, forks and Codex". | — |
| `tests/features/loop_spend_cap/test_loop_spend_cap_jev.py` | The JevAgent specialist guard. | — |
| `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py` | `SETTING_NAMES` (`:29-34`), the `EXPORT_PATHS` identity table (`:41-54`), `HEADER_BULLET = "- Agent setting exports:"` with "want one … bullet" (`:35`, `:181`), and the contract check (`:157-169`). The header says: "Do not compare against base_commit, origin/main or the merge base, and do not pin an export count … (spec NG-13)". | The R1 test template for a root export. |
| `tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py:47,78` | Native names are in the root `__all__`. | — |
| `tests/features/harness_threads/test_harness_threads_surface.py:281-309` | Fresh `import vidbyte`: "Main's names keep their order, and the only additions are the native names the root re-exports for vidbyte-cli." `assert set(report["all"]) - set(before) <= set(importlib.import_module("vidbyte.harnesses.native").__all__)` (`:309`), compared with `git merge-base origin/main HEAD`. | Locally `origin/main` = `98a5d37b` = the merge base, so this **runs and goes red locally** for any non-native root addition. It skips only when `origin/main` is missing (`:139-142`). |
| `tests/features/harness_threads/test_harness_threads_surface.py:270-278` | "no file of vidbyte.tools or vidbyte.lib.configs … differs from main". | Any edit under `vidbyte/tools/` (for example `tools/builtins/fork/fork.py`) **or `vidbyte/lib/configs/`** turns it red locally. |

The `EMITTED_KEYS` lists:
- `OPENAI`: `{"model", "input", "instructions", "temperature", "top_p", "max_output_tokens", "tools", "tool_choice", "text", "metadata"}`.
- `ANTHROPIC`: `{…, "thinking", "metadata", "output_config"}`.
- `_CHAT_KEYS` for XAI, DEEPSEEK and KIMI: `{"model", "messages", "temperature", "top_p", "max_tokens", "stop", "tools", "tool_choice", "response_format", "metadata"}`.

Other tests named in file headers (not opened this session):
- from `vidbyte/agents/jev/settings.py:9`: `tests/test_jev_agent.py`, `tests/test_jev_run_brief.py` and `scripts/test-jev-agent-scaffold.py`;
- from `vidbyte/lib/enums/text_model.py:9`: `tests/features/sdk_provider_keys/test_provider_keys_modes.py`;
- other provider tests: `tests/test_deepseek_provider.py`, `tests/test_openrouter_provider.py` and `tests/test_streaming_text_runner.py`;
- `tests/features/sdk_loop_settings/test_contract.py`.

No test asserts by name that Anthropic `thinking` reaches a DIRECT payload. The only coverage is the managed `EMITTED_KEYS` check and the DIRECT-equality oracle above.

**Commands.** These follow the file-header form plus the workspace interpreter. Nothing was run in this stage.

| Scope | Command |
|---|---|
| One file | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/sdk_managed_text/test_managed_text_wire_contract.py` |
| The area | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/sdk_managed_text tests/features/loop_spend_cap tests/features/jev_cli_root_exports tests/features/root_native_thread_exports tests/test_gemini_provider_text.py tests/test_compatible_provider_text.py tests/test_deepseek_provider.py tests/test_agent_pricing.py tests/test_jev_agent.py` |
| Contract and lint | `py -3.11 scripts/generate-sdk-public-api.py --check`, `py -3.11 lint/run.py --rule C016`, `py -3.11 lint/run.py --rule S015`, `py -3.11 lint/run.py --rule C008` |
| Everything | `python scripts/run_ci.py` (AGENTS.md) |

---

## 4. Notes for the spec author

### 4.1 Request assumes X; code shows Y

1. Request assumes a `ModelConfig` class (`request.md:41,52`). Code shows `class TextModelConfig` at `vidbyte/lib/dataclasses/model_configs.py:55`. No class named `ModelConfig` exists (`git grep "class ModelConfig"` returned nothing).
2. Request assumes the harness efforts sit at `native_threads.py:452,487`, including Codex (`request.md:42`). Code shows those two lines are the `GrokThreadConfig` and `MuseThreadConfig` fields. `CodexReasoningEffort` is in `vidbyte/lib/enums/codex.py:34`. The three enums differ:
   - Codex has an `""` `PROVIDER_DEFAULT` sentinel and is `(str, Enum)`.
   - Grok adds `MAX="max"` and Muse adds `ULTRA="ultra"`, and both are `StrEnum`.

   The six requested values equal Codex minus its sentinel.
3. Request assumes "`vidbyte/providers/README.md:160-280` lists each provider's thinking or reasoning doc links" (`request.md:57`). Code shows:
   - OpenAI's links are at `:133-134`, outside that range.
   - xAI has no reasoning link (its section is `:204-230`).
   - Meta/Muse has no link of any kind for `api.meta.ai`. The section `:362-385` covers Llama.
4. Request assumes "Muse" has a wire form. Code shows CLI "muse" → `ModelProvider.META` → `MetaProvider`, a bare `OpenAICompatibleProvider` subclass (`compatible.py:243-244`) at `https://api.meta.ai/v1` (`registries/models.py:103`). `MuseReasoningEffort` belongs to the Muse Code harness CLI ("muse exec --reasoning-effort", `enums/native_threads.py:160`), not to this adapter.
5. Request assumes `compatible.py:232` (`inline-thinking-is-not-the-answer`) is relevant to the 7 providers (`request.md:73`). Code shows that intent is on `MiniMaxProvider` (`compatible.py:228-236`), and `:157` is the Mistral chunk path. Neither is one of the 7. For xai, deepseek, glm and meta, `_extract_chat_text` reads only string `content` (`compatible.py:136-162`).
6. Request assumes Q3 "including each model in its fallback chain" for JevAgent too (`request.md:71`). Code shows:
   - `JevAgentSettings` has no fallback field (`agents/jev/settings.py:132-151`).
   - `JevAgent` passes no `fallback=` to `BaseAgent` (`agents/jev/agent.py:92-107`).
   - The chain exists only for `BaseAgent(fallback=…)`.
7. Request assumes the Jev roles are main, brief, specialists and decision (`request.md:71`). Code shows eight more SDK-built Jev children that copy `temperature=settings.temperature` today (§2.2 table). Code also shows:
   - Context-window side calls and reflexion calls reuse the agent's own `RunnerHandle` (`runtime.py:1054-1061`; `algorithms/reflexion.py:110-133`), so they run with the main agent's `TextModelConfig`.
   - Specialists are developer-built `BaseAgent`s held in `JevSpecialist.agent` (`lib/dataclasses/jev.py:660-683`).
   - The brief writer uses `JevRunBriefSettings.temperature` (`agents/jev/brief/writer.py:65`).
8. Request assumes the effort can be refused "at construction … before any spend" (`request.md:69`). Code shows:
   - The generative config's own range checks run in `TextModelConfig.validate()` (`model_configs.py:111-121`), which runs in `TextModelRunner.__init__` (`text.py:48`).
   - That runner is built at the first `arun` (`base.py:940`), and a fallback hop's runner only on a switch (`base.py:1375`).
   - The only construction-time chain check is R3's `AgentSpendCap.model_refusal` (`spend_cap.py:48-69`, called at `base.py:255-257`). It uses `Runner.from_model` without `.build()`.
   - `JevAgentSettings` validates its own temperature in `__post_init__` (`settings.py:177,225-231`).
9. Request assumes Q2, "`thinking_config` and the effort set together" (`request.md:70`). Code shows no agent path can set `thinking_config` today:
   - `BaseAgent` passes only `temperature` and `options={"timeout_seconds": …}` to `Runner` (`base.py:1679-1686`).
   - `Runner` passes only fields that exist on `TextModelConfig` (`utility.py:134`).
   - `thinking_config` is set only by code that builds `TextModelConfig` or `TextModelRunner` directly.
   - The two readers differ: Anthropic checks truthiness (`if config.thinking_config:`, `anthropic.py:112`), while Gemini checks `is not None` (`gemini.py:194`).
10. Request assumes the default mode can carry the new body field. Code shows the default `mode=TextModelMode.AUTO` (`base.py:109`; `jev/settings.py:150`) sends every call through the gateway, even with the user's own provider key (`text_model.py:7`). The managed allow-list in `test_managed_text_wire_contract.py:46-54`:
    - has no `reasoning` key for OpenAI and no `reasoning_effort` or `thinking` for the chat dialects;
    - has `thinking` and `output_config` for Anthropic and `thinkingConfig` for Gemini.

    `vidbyte_gateway.py:124` names "a body field outside the gateway's allowed list" as a 422 cause. GLM and META are refused in every gateway mode at `TextModelConfig.__post_init__` (`model_configs.py:95-96,204-209`; `constants/jev.py:74-81`). D-P5 (`request.md:175`) says the CLI uses only the user's own key, but which `TextModelMode` C4 will pass is unverified.
11. Request assumes billed reasoning tokens reach the spend cap (Q4, `request.md:72`). Code shows:
    - They reach it only through each usage class's `output_tokens` and `cost_usd` (§2.5).
    - `UsageRollup` has no reasoning field (`records.py:70-91`).
    - OpenAI relies on the vendor including reasoning in `output_tokens` (`providers/README.md:570-572`). Anthropic thinking is not parsed separately (`pricing/anthropic.py:47-58`).
12. Request assumes R1's root-export pattern is a single name (`request.md:76`). Code shows:
    - `DecisionModelConfig`'s `mode` field type `DecisionModelMode` and its `provider` type `ModelProvider` are not root exports (import check).
    - `DecisionModelConfig()` defaults to `mode=DecisionModelMode.TYPESAFE` (`model_configs.py:513`), which `JevRuntimeSettings` refuses (`jev/settings.py:383-386`).
    - `vidbyte_managed()` takes no arguments, so it cannot carry `api_key` (`:582-587`).
    - The #1190 commit message records "ModelProvider stays non-root as optional Q-3 (default not built)" (`git show 22993b5f`).
    - `JevRuntimeSettings` checks `type(self.decision) is not DecisionModelConfig`, so a root name must be the same class object. `test_jev_cli_root_exports_contract.py` checks identity.
13. Request assumes only `vidbyte/tools/` trips the harness surface test (`request.md:85`). Code shows the same test also scopes `vidbyte/lib/configs` (`test_harness_threads_surface.py:274`). That folder holds the only existing capability tables (`lib/configs/structured_output.py`). The fork tool that exposes `temperature` to the model is under `vidbyte/tools/builtins/fork/fork.py:473`.
14. Request assumes the release note needs one sentence after #1192 (`request.md:80`). Code shows "733" appears twice: `release-0-4-0.md:17` ("so the contract still lists 733 exports") and `:19` (the 733 / 94-added tally by PR). No test pins 733 (`git grep -n "733" -- tests lint scripts` returned nothing).

### 4.2 Other facts the design must account for (no recommendation)

- **The per-hop value is lost on restore.** `export_state` stores fallback hops as `identity()` strings (`base.py:652`), and `restore` passes them back as strings (`base.py:613`). They are then re-resolved with `temperature=primary.temperature` (`settings/fallback.py:146`), so a per-hop `FallbackModel.temperature` does not survive a checkpoint. `CodexHarnessAgent` (not a `BaseAgent`: `class CodexHarnessAgent:` at `agents/codex/agent.py:55`) ignores `FallbackModel.temperature` (`agents/codex/fallback.py:21-22`).
- **Fallback carries the transcript across OpenAI and every chat-completions provider.** `AgentFallback.transform` keeps `messages` only when `is_wire_compatible` (`agents/fallback.py:154-167`), which compares `ToolsFormatter.wire_format`. That returns `"anthropic"` or `"gemini"` and collapses everything else to `"openai"`: "xAI and every OpenAI-compatible provider (deepseek, glm, minimax, kimi, openrouter) collapse to the OpenAI payload here so fallback treats them as one format" (`lib/tools/formatter.py:67-73`). The OpenAI adapter posts to `/responses` (`providers/openai.py:37`) while the others post to `/chat/completions` (`compatible.py:35`); both reply shapes are stored as a "chat-shaped assistant tool-call message" (`formatter.py:335-347`). So a chat hop's whole echoed message (`{**message`, `:347`) is in the history a later OpenAI hop receives. What `openai.py` does with extra keys in such a message is unverified.
- **Unknown runner options are dropped silently** (`utility.py:134`).
- **`extra_body` wins over adapter keys in every adapter** (`openai.py:340-343`, `anthropic.py:121-124`, `compatible.py:131-134`, `gemini.py:216-221`).
- **Anthropic's `output_config` is assigned whole** for `response_format` (`anthropic.py:69-70`). In DIRECT, `max_tokens` defaults to 1024 (`anthropic.py:56`).
- **History echo per dialect** (§2.4):
  - OpenAI Responses drops reasoning items and never echoes item ids (`formatter.py:359-381`; `openai.py:276`).
  - Chat completions echoes the whole message (`formatter.py:347`).
  - Anthropic and Gemini echo full content, including thinking or thought parts (`formatter.py:396,415`).
- **Streaming is DIRECT-only and OpenAI/Anthropic-only** (`streaming_text.py:3-5`; `providers/__init__.py:96-100`). It yields only answer-text deltas.
- **Two YAML records thread `temperature`,** each with its own `{"anthropic": 1.0}` ceiling (`lib/dataclasses/config.py:85`; `lib/dataclasses/agent_descriptor.py:64`). `AgentSettings._ALLOWED_FIELDS` rejects unknown YAML keys (`config.py:341-346`).
- **The fork tool lets the model set a child's `temperature`** (`tools/builtins/fork/fork.py:287-297,473`). R3 tested that the same tool refuses a model-supplied cap (`test_loop_spend_cap_copy_paths.py:176`).
- **Error types differ by site:** `AgentForkSettings` raises `AgentForkConfigurationError` (`lib/dataclasses/agents.py:475-476`), `FallbackModel` raises `ValueError` (`:343-346`), and the rest raise `ConfigurationError`.
- **Checkpoints refuse other schema versions:** `RunState` uses `SESSION_SCHEMA_VERSION = 1` (`sessions.py:24`), and restore refuses any other version (`serialization.py:249`).
- **A009 headroom:** `vidbyte/agents/README.md` has 6,359 characters left under 40,000.

### 4.3 Unverified

- unverified: every vendor wire form (OpenAI `reasoning.effort`, Anthropic `thinking`/`effort`/`output_config.effort`, Gemini `thinkingConfig` level or budget, xAI, DeepSeek, GLM `thinking`, and Meta/Muse at `api.meta.ai`). Nothing was fetched.
- unverified: which values each provider or model accepts, and which models reason at all. No SDK table records this.
- unverified: the backend gateway's current per-dialect allow-lists. The SDK test copies them from `docs/spec/managed-generative-models/spec.md` §9.2, which was not read. The backend spec is cited at `constants/jev.py:72-73`.
- unverified: whether the vendors' `output_tokens` include thinking (Anthropic) or reasoning (OpenAI). The OpenAI claim comes only from `providers/README.md:570-572`.
- unverified: whether a provider requires its reasoning output to be echoed, or forbids it, in a stateless tool loop. This covers OpenAI reasoning items, DeepSeek `reasoning_content` and Anthropic thinking signatures.
- unverified: whether `tests/features/harness_threads/test_harness_threads_surface.py` is skipped in remote CI. `request.md:84` says "CI skips it". Locally it runs (origin/main = `98a5d37b`).
- unverified: which of `AgentSettings` (`config.py`) and `AgentDescriptor` (`agent_descriptor.py`) the public `vidbyte.config` loader returns today. `vidbyte/lib/config/loader.py:259` builds `AgentDescriptor`, and the `config.py` header says it is "Constructed by vidbyte.config.loader".
- unverified: the sections of `vidbyte/agents/README.md` other than `:185-250` and `:386-455`, and the parts of `vidbyte/agents/jev/README.md` outside a grep for settings, model, fallback, temperature, child, specialist and brief (matched lines read to 400 characters; `:24` and `:28` read in full). Also unverified: the contents of `tests/test_jev_agent.py`, `tests/test_deepseek_provider.py`, `tests/features/sdk_loop_settings/test_contract.py` and `docs/spec/loop-spend-cap/spec.md` beyond §5 and §9.2. Only sizes or headers were read.
- unverified: `FailureCode` impact. No new member is implied by the code read here.
