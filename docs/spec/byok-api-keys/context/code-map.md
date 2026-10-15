# Code map: byok-api-keys (Vidbyte-SDK half)

Scout: S0, read-only. Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-byok-api-keys`, branch `feat/byok-api-keys`, base `52aab816` (#972). The only untracked path is `docs/spec/byok-api-keys/`. Every path:line below was opened in this session. Anything not confirmed is marked "unverified".

## 1. Rules, commands, and conventions that bind this change

### AGENTS.md (81 lines, read in full)

- **Repository Map.** "Read it before you create a file, move code, or search for where something lives, and put new code where it says that kind of code belongs." Read each folder's `README.md` to the end. Its closing `## Notes for agents` section records past review findings.
  - None of the READMEs in the touched folders has that section. Only `vidbyte/agents/coding_context/README.md` does, outside AGENTS.md and REPO_MAP.md.
  - The touched folders with no README at all are `vidbyte/lib/dataclasses`, `enums`, `http`, `runners`, `constants`, `util`, `config`, `vidbyte/agents/settings`, and `vidbyte/sessions`.
- **A009.** "lint rule A009 keeps every folder README at or under 40,000 characters". The root `README.md` is exempt. In `lint/rules/a009_readme_size_limit.py`, `LEGACY_CEILINGS` gives two READMEs higher ceilings:
  - `vidbyte/providers/README.md` has a 55,000 ceiling and is 41,573 characters today.
  - `vidbyte/agents/codex/README.md` has a 65,000 ceiling.
  - `vidbyte/agents/README.md` is 20,558 characters today.
- **docs/ is opaque.** "Do not grep, glob, or read files under `docs/` as part of ordinary work". `tests/features/sdk_managed_text/README.md` cites `docs/spec/managed-generative-models/spec.md` as its source. This scout did not read it.
- **Gate.** "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- **Style §1.** Keep call chains one level deep: a main function calls a flat list of helpers. Do not nest functions unless an API requires a callback.
- **Style §2.** Narrate each main function with plain-English comments. Update those comments in the same edit that changes the steps.
- **Style §3.** Build in layers, with `vidbyte/lib/` at the bottom. Nothing in lib imports from above. There are no import cycles.
  - "Keep files well below 1,000 lines". If describing a function needs "and", it is two functions.
  - Note: `vidbyte/agents/base.py` is already 1,725 lines.
- **Style §4.** Core functions take and return validated dataclasses, with `__post_init__` checks that name the field and the bad value. Prefer `@dataclass(frozen=True, slots=True)`. Type a closed set as an enum.
- **Style §5.** Write shared logic once, as a canonical helper in `vidbyte/lib/`. Look there for an existing helper and extend it rather than copying it. `HttpTransport` is the example.
- **Placement.**
  - Every new dataclass goes in `vidbyte/lib/dataclasses/<domain>.py`. "Do not create `types.py`, `records.py`, `models.py`, or `schemas.py`". The exceptions are a `*Settings` class in `vidbyte/agents/settings/` or the agent's own `settings.py`, and JEV preflight questions.
  - Every new enum goes in `vidbyte/lib/enums/<domain>.py`, is exported from `vidbyte/lib/enums/__init__.py`, and has "no exceptions".
  - "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum".
  - A new JEV constant goes in `vidbyte/lib/constants/jev.py`.
  - Editing existing misplaced code in place is fine. Moving it is its own PR.
- **PR and commit conventions.** AGENTS.md states none.

### REPO_MAP.md (lib entries quoted)

- `vidbyte/lib/enums/`: "Extending an existing enumeration is treated as an interface change with its own weight, since code elsewhere may be matching against it exhaustively." This applies to `TextModelMode.DIRECT`.
- `vidbyte/lib/constants/`: "if a literal value would otherwise need to appear in two places, it belongs here instead."
- `vidbyte/lib/http/`: "Nothing else in the package should reach for an HTTP client directly outside of this layer."
- `vidbyte/lib/models/` is an empty placeholder. Model discovery lives in `vidbyte/lib/registries/`, which REPO_MAP describes as "Name-to-implementation lookup".
- REPO_MAP has no `##### vidbyte/lib/util/` entry, so the map has drifted. `lib/util/credential_keys.py` exists anyway.

### Commands (verified in source this session)

- **Full gate.**
  - `python scripts/run_ci.py`. `--stage` is one of `all|source|package` and defaults to `all` (`scripts/run_ci.py:255-272`).
  - The source stage runs `lint/run.py`, `compileall`, `check_context_write_paths.py`, `check_context_primitive_introductions.py`, `check_reasoning_trace_contracts.py`, and then `python -m pytest` (`:79-93`).
  - The package stage runs build, twine check, a clean-venv install, and a smoke test (`:95-215`).
- **From this worktree.** Field guide `local-ci-verification.md`: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no `PYTHONPATH`.
- **Lint.**
  - Run `python lint/run.py [--rule ID] [--format text|json] [--all] [--update-baseline]` (`lint/run.py:36-39`).
  - The pass line is `SDK-LINT: PASS` (`lint/core/report.py:58`).
  - `lint/baseline.json` holds one count per rule: C017 0, C018 0, C019 0, C020 2, A009 0, A001 643, A007 255, S060 32, S039 5, C002 9, A003 36, A006 34.
  - Lint sees only git-tracked files: `lint/core/discovery.py:76-85` runs `git ls-files -z`. `git add` a new file before trusting a clean lint.
- **Semgrep.** It runs in the Static policy workflow, not in `run_ci.py` (`.github/workflows/static-policy.yml:24-30`).
  - Run `python -m pip install semgrep==1.170.1`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`.
  - The one rule is `no-untyped-mapping-fallback`: no silent fallback for a non-Mapping `object`/`Any` parameter. It excludes `vidbyte/lib/http/**` and `vidbyte/providers/**`.
- **PR CI** (request §C). It does not start automatically. Run `gh workflow run CI --ref <branch>` and `gh workflow run "Static policy" --ref <branch>`.

### Lint rules this change can trip

- **C017** (`lint/rules/c017_platform_route_contract.py`).
  - Every SDK request to a Vidbyte host must hit a contract route with an accepted method, and with a credential its access class admits: `ACCESS_ACCEPTS = {"API_KEY": {api_key}, "PUBLIC": {api_key, none}, "SESSION": {}}`.
  - "Headers the tracer cannot read leave API_KEY and PUBLIC access unchecked."
  - The route is `models.generate`: POST `/api/v1/models/generate`, access `API_KEY`, scope `models:invoke` (`lint/contracts/vidbyte-platform-contract.json:18`).
  - The contract file contains no header names (0 matches for "header"), so the new header name is mirrored by hand.
- **C018.** A Vidbyte API URL literal under `vidbyte/` must use a `live` host from the contract. A URL inside a message string counts.
- **C019.** A snake_case code literal in a decision position must be a contract error code.
- **C020** (`lint/rules/c020_api_key_prefix_contract.py`).
  - `vb_live_` may be spelled only by `VIDBYTE_API_KEY_PREFIX` (`vidbyte/lib/constants/jev.py:64`).
  - "The contract prefix counts anywhere in a literal (a message naming the vb_live_ format is a copy too)."
  - The foreign-prefix check covers only the `vb_<word>_` family. Provider prefixes such as `sk-ant-`, `xai-`, and `AIza` are NOT flagged.
  - The baseline of 2 is `vidbyte/providers/typesafe.py:255,271`. Tests are out of scope.
- **A001** (`lint/rules/a001_agent_readable_file_headers.py`).
  - Every tracked `.py` file (`all_python_files`, which includes tests) needs non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, and `TESTS:` within the first 80 lines.
  - `vidbyte/lib/runners/text.py` and `streaming_text.py` have no such header today.
- **A009.** See above.

### Field guide (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`): the trigger and check quoted for each relevant topic

- **local-ci-verification**
  - Worktree run. When: "Verifying any change from a git worktree (`worktree-*`) rather than the canonical `vidbyte-sdk/` checkout." Check: "`PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` must print the worktree path."
  - Semgrep. When: "A change adds a new `.py` file and you run the Static policy gate locally." Check: "Scan the new path explicitly (`semgrep … <new-file>`) and confirm the rule ran on it."
  - S051. When: "`lint/run.py` reports S051 (I001) REGRESSED, but `ruff check <file>` on your own files passes." Do: "`python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`".
  - Mid-merge. When: "`lint/run.py` reports REGRESSED during a merge…" Do: "`git add` the resolved files so `git ls-files -u` is empty".
- **blocking-lint-invariants**
  - A003. When: "Adding a new exception class to `vidbyte/lib/errors/base.py`". Check: "`python lint/run.py --rule A003`".
  - S060/S039. When: "Adding a `to_dict()`/wire-encoding method to a record in `vidbyte/lib/dataclasses/`." Check: "`python lint/run.py --rule S060` and `--rule S039` stay at their baselines."
  - A006. When: "A lazy import inside `vidbyte/lib/registries/*` … needs a class under `vidbyte/agents/`." Check: "`python lint/run.py --rule A006`."
  - S012. When: "A helper that is not an HTTP call is named `request`". Check: "`python lint/run.py --rule S012`."
  - C002. When: "A new `vidbyte/lib/dataclasses/` record stores a status bool next to the content it summarizes". Do: "Never add a second `isinstance(x, bool)` guard for a field name that is already guarded."
- **strict-config-dataclasses**
  - Thin adapter. When: "Defining or refactoring the `__init__` of a settings/config class … (e.g. `AgentFallbackSettings`…)". Check: "The settings class's own `__init__` and instance methods contain no `raise ConfigurationError` calls".
  - BaseAgent subclass. When: "A prebuilt `BaseAgent` subclass adds its own keywords (a root folder, provider keys…)". Check: "`__init__` contains no `raise`. … `repr(settings)` shows no key."
  - Shared check. When: "A raw parameter … is checked with the same inline `isinstance`/range logic in more than one place". Check: "after the refactor only the dataclass's `__post_init__` should contain them."
  - Strip-union. When: a review asks to strip an `Enum | str` union on one symbol. Check: "grep the codebase (including `tests/` and `skills/*.md` examples) for existing calls using a raw string".
  - Bounds. When: "multiple field-size, count, or numeric bounds". Check: "each validation comparison should reference the feature's constants module."
- **fallback-coordination**
  - Policy. When: "Adding a fallback trigger, attempt accounting, or proactive model-switch condition." Check: "`AgentRuntime.should_fallback` delegates to a run-scoped `AgentFallback.for_runtime()` view".
  - Validation. When: "Adding a fallback model, policy kind, or runtime model-switch trigger." Check: "… attempt records stay credential-free and share one shape."
- **prebuilt-agents.** When: "A `BaseAgent` subclass … picks a provider from a key". Check: "`repr(agent.export_state())` and `repr(agent.tools)` contain no key."
- **comment-format.** When: "Writing or editing any `#` comment in SDK code that runs past one line, including the `# @intent` blocks". Check: "`awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing … A002 still passes, because the `@intent` line has to stay within 20 lines of the `def`."
- **class-bound-helpers.** When: "A new or edited module exports several related free functions that share one concern". Check: "The module's public `__all__` exports the class (and constants), not a list of peer free functions".
- **provider-api-contracts**
  - Mirror the vendor. When: "Adding or reviewing records, limits, pricing, or defaults for an outbound model/decision provider". Do: "Download the vendor's own `api.md`/`models.md`…". This bears on the unverified key formats.
  - One guarded try. When: "Writing a provider adapter's public call method". Check: "Tests for each status, a raised `RuntimeError`, and `asyncio.CancelledError` from a scripted transport."
- **review-scope.** When: "A reviewer says a feature … should not be in this PR, but that feature already merged to `main`". Check: "`git diff origin/main -- <feature files>` prints nothing."

### Conventions in code that the new code must follow

- **`@intent name-lists-reject-bare-strings`.** A bare `str` raises `ConfigurationError`. Examples:
  - `vidbyte/agents/base.py:234-240` for capabilities.
  - `vidbyte/agents/settings/fallback.py:44-49` for `AgentFallbackSettings.models`.
  - `AllowedToolNames` (`vidbyte/lib/dataclasses/agents.py:160`).
  - Test: `tests/test_agent_settings_validation.py:46`.
- **Keys hidden from repr.**
  - `field(default=None, repr=False)`: `model_configs.py:51` (Text), `:418` (Decision), and `vidbyte/agents/jev/settings.py:129,271`.
  - Or a masking `__repr__`: `FallbackModel` at `vidbyte/lib/dataclasses/agents.py:236-240`.
- **Credential errors.** `ConfigurationError(..., details={"error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND})` (`jev.py:27`).
- **Gateway errors.** `ProviderRequestError(provider="vidbyte")` with no excerpt and no `__cause__`/`__context__` (`vidbyte_gateway.py:192`).
- **Header-name constant precedent.** `JEV_MANAGED_RUN_ID_HEADER: str = "X-Vidbyte-Run-Id"` (`vidbyte/lib/constants/jev.py:55`). The managed `VIDBYTE_*` constants are not in `jev.py`'s `__all__`.
- **Gateway constants in `jev.py`.** `jev.py`'s header says to change a managed value "only when the backend gateway contract changes, together with the README managed-mode section and tests/features/sdk_managed_text/".

## 2. Files this change will touch

The format for each entry is: **path (size)**. Today: … Change: … Pattern: …. The change lines follow request §0, §B.2, §B.4, and §C. They are not a design.

### 2.1 Lib: modes, key resolution, gateway

1. **`vidbyte/lib/enums/text_model.py` (24 lines).**
   - Today: `class TextModelMode(str, Enum)` with `AUTO="auto"` and `VIDBYTE_MANAGED="vidbyte_managed"`. The header's KNOWN EDGE CASES says "AUTO still becomes managed when the key … is a Vidbyte key".
   - Change: add `DIRECT`, and rewrite the header.
   - Pattern: the same file. It is already exported at `vidbyte/lib/enums/__init__.py:139,231` and `vidbyte/lib/config/__init__.py:16,34`.
2. **`vidbyte/lib/dataclasses/model_configs.py` (509 lines).**
   - Today, in `TextModelConfig` (`:48`):
     - `api_key: str|None = field(default=None, repr=False)` is the third field (`:51`). `endpoint` is at `:67`. `mode: TextModelMode = AUTO` is at `:69`, the second-to-last field before `prompt_index`.
     - `__post_init__` (`:73`) checks the mode type. "AUTO reads no environment here" (`:79`). It calls `_require_managed_shape` in VIDBYTE_MANAGED (`:84`).
     - `validate()` (`:93`).
     - `is_vidbyte_managed()` (`:112`) is VIDBYTE_MANAGED or `find_vidbyte_api_key(provider, api_key) is not None` (`:119`).
     - `resolved_vidbyte_api_key()` (`:121-135`).
     - `resolved_api_key()` (`:137`) returns `VIDBYTE_MANAGED_KEY_PLACEHOLDER` when managed (`:143`).
     - `_require_managed_shape` (`:157-166`) refuses an endpoint, and raises `UnsupportedProviderError` outside `VIDBYTE_MANAGED_TEXT_PROVIDERS`.
   - Today, the other configs:
     - Image `:190`, Video `:244`, Audio `:304`, and Embedding `:357` each have `api_key: str|None = None` with no `repr=False` (`:193,247,307,360`).
     - `DecisionModelConfig` (`:413`, `api_key` at `:418`) is out of scope, but it shares `resolve_vidbyte_api_key` at `:468`.
   - Change: replace `api_key` with `api_keys` (a list), add `vidbyte_api_key`, implement DIRECT/AUTO/VIDBYTE_MANAGED resolution, and add a resolved-credentials record. B.4 step 4 names it `TextCredentials`, in this domain module.
   - Pattern: frozen+slots; `__post_init__` raises with `details`; credential errors carry `error_kind`.
3. **`vidbyte/lib/registries/models.py` (445 lines).**
   - Today:
     - `API_KEY_ENV_VARS` (`:85-100`): KIMI uses `MOONSHOT_API_KEY`, XAI uses `XAI_API_KEY`, TYPESAFE uses `TYPESAFE_API_KEY`.
     - `resolve_api_key` (`:168-177`) raises "Missing API key for provider {p}. Pass api_key or set {env_var}."
     - `find_vidbyte_api_key` (`:180-198`) checks the explicit key, then the provider env var (each managed only if it is `vb_live_`), then `VIDBYTE_API_KEY` for the 6 providers.
     - `vidbyte_key_follows_provider` (`:201-209`).
     - `resolve_vidbyte_api_key` (`:212-225`) raises "Missing Vidbyte API key. Pass api_key or set VIDBYTE_API_KEY." or "…must be a live key in the {prefix} format."
     - `provider_for_model` (`:330-339`) uses `MODEL_PROVIDER_RUNNER_TYPE_MAP`.
     - It imports `vidbyte.lib.agents.modality_detector` (`:48`).
   - Change: B.4 step 5 says "replace `find_vidbyte_api_key` with the pair resolver". It keeps `resolve_vidbyte_api_key` and `vidbyte_key_follows_provider`.
   - Pattern: `@intent` blocks on classmethods.
4. **New lib key-classifier class (path unverified; still to be decided).**
   - Today: no provider key-format knowledge exists. The only key formats are `VIDBYTE_API_KEY_PREFIX`/`PATTERN` (`jev.py:64-65`) and two redaction regexes: `vidbyte/providers/typesafe.py:255,271` (`vb_live_…{32,}`) and `vidbyte/providers/tracing/langsmith.py:175` (`xai-[A-Za-z0-9_\\-]+`).
   - Change: add a deterministic key→provider class (request §0).
   - Pattern: `vidbyte/lib/util/credential_keys.py` is a static-policy class with no SDK dependencies. Its records go in `lib/dataclasses/`, any enum in `lib/enums/`, and the prefix constants in `lib/constants/`.
   - Constraint: `vidbyte/lib/registries/pricing.py:40` imports `registries/models.py`, so `models.py` cannot import pricing without a cycle.
5. **`vidbyte/lib/constants/jev.py` (760 lines).**
   - Today: `VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND` `:27`, `JEV_MANAGED_RUN_ID_HEADER` `:55`, `VIDBYTE_API_KEY_PREFIX` `:64`, `_PATTERN` `:65`, `_ENV_VAR` `:66`, `VIDBYTE_GENERATIVE_GATEWAY_ENDPOINT` `:69`, `VIDBYTE_MANAGED_TEXT_PROVIDERS` `:72`, `VIDBYTE_MANAGED_KEY_PLACEHOLDER` `:89`.
   - Change: add the `X-Vidbyte-Provider-Key` name constant.
   - Pattern: `:55`.
6. **`vidbyte/lib/http/vidbyte_gateway.py` (211 lines).**
   - Today:
     - `VidbyteGatewayTransport.__init__(inner, *, provider, model, api_key)` (`:129`).
     - The headers are built only at `:161-162` (`bearer_headers(self._api_key)` plus `Idempotency-Key`). The header docstring says this is "the shape lint C017 traces".
     - `failure_reason` (`:73-91`): relayed vendor errors say "…the provider's message is withheld, and the call was not billed" (`:90`).
     - `gateway_reason` (`:93-113`):
       - 401 says "check VIDBYTE_API_KEY or TextModelConfig.api_key" (`:99`).
       - 402 ends "or set your own provider key" (`:100`).
       - 413 ends "use your own provider key" (`:103`).
       - 5xx says "refused Vidbyte's own account" (`:111`).
   - Change: add a `provider_api_key` param and the header, and reword the messages.
   - Pattern: `@intent managed-request-reaches-only-the-gateway` (`:156-160`).
7. **`vidbyte/lib/runners/text.py` (113 lines, no A001 header).**
   - Today: `__init__` (`:24`) calls `validate()`. Then `self._managed = config.is_vidbyte_managed()` (`:45`) and it pins `replace(config, mode=VIDBYTE_MANAGED, api_key=resolved_vidbyte_api_key(), max_output_tokens=…or 32768, timeout_seconds=max(630, …))`. `arun` (`:60`) wraps `VidbyteGatewayTransport(…, api_key=call_config.resolved_vidbyte_api_key())` (`:78-83`). `_coerce_config` (`:108`).
   - Change: pin both keys and pass the provider key per call.
   - Pattern: `@intent managed-runner-is-pinned-at-construction`.
8. **`vidbyte/lib/runners/streaming_text.py` (92 lines, no header).**
   - Today: `_refuse_managed_streaming` (`:56`) runs when `is_vidbyte_managed()`. Its message names `{env_var}` and `TextModelRunner`, with `details={"provider", "mode": "vidbyte_managed"}`.
   - Change: refuse in every gateway state, and name DIRECT.
9. **`vidbyte/lib/runners/utility.py` (165 lines).**
   - Today: `Runner.__init__(…, api_key=None, …)` (`:26-29`). `_config_options_for` (`:101`) sets `options["api_key"]` for every runner type (`:106-107`), so the agent key also reaches Image/Video/Audio/Embedding configs. `build` (`:65`) and `TextModelRunner(TextModelConfig(...))` (`:74`). `_normalize_provider_and_model` (`:128`).
   - Change: carry the key list and the Vidbyte key, and decide what non-text configs get.
10. **`vidbyte/lib/runners/router.py:30,40` and `vidbyte/lib/agents/modality_detector.py:127,140-141`.** Today they pass `api_key` through. Change: rename or carry the list. The algorithm callers (`independent_critic.py:197`, `multi_provider_agentic_grader.py:82,122`, `prosecutor_defender_judge.py:243`) pass no key.

### 2.2 Credential guards (each misses `api_keys`; see the table)

11. **`vidbyte/lib/util/credential_keys.py` (87 lines).**
    - Today: an exact name in `_SECRET_KEYS` (`:53-72`) or a suffix in `_SECRET_SUFFIXES` (`:73`). The pattern is "Add a credential name to `_SECRET_KEYS` or a suffix to `_SECRET_SUFFIXES`; both harness capture and session trace artifacts pick it up."
    - Users: `HarnessSecretPolicy`, the YAML policy, base.py trace scrubbing, and session trace artifacts.
12. **`vidbyte/lib/dataclasses/config.py:56-66`.** `_YamlSecretKeyPolicy` extends CredentialKeyPolicy. YAML `AgentSettings` has no `api_key` field, and `_ALLOWED_FIELDS` rejects unknown top-level keys.
13. **`vidbyte/lib/dataclasses/agent_descriptor.py:58-75`.** `_has_secret_like_keys` checks TOP-LEVEL keys only: a suffix `api_key|token|password|secret|credential` as the whole key or after `_`, or a prefix. It is used at `:93,313,442,453`.
14. **`vidbyte/harnesses/serialization.py:61-94`.** `HarnessRedactor._ERROR_ASSIGNMENT` (`:70`) is a free-text regex anchored on `\b(api[_-]?key|…)`.
15. **`vidbyte/sessions/serialization.py:31,229-235`.** `_is_secret_key` is a substring match, so it catches plurals. But the trace artifact uses CredentialKeyPolicy (`precise_keys=True`, `:58,208`).
16. **`vidbyte/agents/base.py:1482-1495` (`_safe_trace_value`/`_is_secret_trace_key`) and `:1678` (`_safe_trace_mapping`).** These use CredentialKeyPolicy.

Scratch check: I re-implemented each policy from its source in the scratchpad and read the regex from `harnesses/serialization.py:70`. I did not import vidbyte.

| key | CredentialKeyPolicy | YAML policy | Descriptor guard | SessionSerializer |
|---|---|---|---|---|
| `api_key` | yes | yes | yes | yes |
| `api_keys` | **no** | **no** | **no** | yes |
| `apiKeys` | no | no | no | no |
| `vidbyte_api_key` | yes | yes | yes | yes |
| `vidbyteApiKey` | yes | yes | no | no |

Free text through `_ERROR_ASSIGNMENT`:
- `api_key='xai-abc'` is redacted.
- `api_keys=['xai-abc']`, `{'api_keys': ['xai-abc']}`, and `vidbyte_api_key='vb_live_x'` are NOT redacted.
- `openai_api_key=sk-x` is NOT redacted. That gap predates this change, because `\b` does not fire after `_`.

### 2.3 Agents, sessions, and paradigms (the public `api_key` provider-key surface)

17. **`vidbyte/agents/base.py` (1,725 lines).**
    - Today: `__init__(…, api_key: str|None=None, …)` (`:97`) becomes `AgentRunnerConfig(api_key=…)` (`:173-180`), then `AgentFallback.from_spec(fallback, runner_config=…)` (`:184`). `restore(cls, state, *, …, api_key=None)` (`:545`, passed at `:559`). `_runner_for_model` (`:1555-1568`) calls `Runner.from_model(api_key=self.runner_config.api_key)`.
    - `export_state` holds no key. Fallback models are stored as identity strings.
18. **`vidbyte/lib/dataclasses/agents.py` (374 lines).**
    - `AgentRunnerConfig` (`:201`) has `api_key` at `:204` with **no `repr=False`**, so `repr(agent.runner_config)` shows the key today.
    - `FallbackModel` (`:213`) has `api_key` at `:218`, a masked `__repr__` at `:236-240`, and `identity()`.
    - `AgentForkSettings` (`:319`) has no key field.
19. **`vidbyte/agents/fallback.py` (196 lines).** `_primary_model` builds `FallbackModel(api_key=runner_config.api_key)` (`:106`). `build_runner` calls `Runner.from_model(api_key=target.api_key)` (`:167-170`). Attempt records are credential-free.
20. **`vidbyte/agents/settings/fallback.py` (174 lines).** `_resolve_entry` gives `api_key=self._inherited_api_key(...)` (`:121`). `_inherited_api_key` (`:157-165`) drops the key on a provider switch unless `vidbyte_key_follows_provider`. An explicit `FallbackModel` keeps its own key.
21. **`vidbyte/agents/fork.py` (237 lines).** `fork` uses `api_key=cls._api_key(agent, child_provider, parent_provider)` (`:63`). `_api_key` (`:110-118`) applies the same #884 rule.
22. **`vidbyte/agents/aggregation.py` (400 lines).**
    - `AggregateAgent.__init__(…, api_key=None, …)` (`:201`), then `_proposer_api_key` (`:210`) and `_key_owner` (`:215`).
    - `_resolve_key_owner` (`:334-343`) and `_child_api_key` (`:345-352`) give a child the key only for the owner provider. They do NOT use `vidbyte_key_follows_provider`.
23. **`vidbyte/agents/continual_trace.py:60` and `vidbyte/agents/handoff.py:64`.** `from_source_agent` passes `source_agent.runner_config.api_key`.
24. **`vidbyte/agents/jev/settings.py`.**
    - `JevAgentSettings.api_key` (`:129`) and `JevRunBriefSettings.api_key` (`:271`, docstring `:266`). Both are text provider keys.
    - Consumers: `jev/agent.py:68,97`, `brief/writer.py:55`, `bulk_work.py:54`, `compute/clone.py:37`, `compute/swarm.py:49`, `done/handoff.py:162`, `done/reviewer.py:38`, `done/run_state.py:282`, `gate/clarification.py:55`.
25. **`vidbyte/sessions/session.py:204-205,292,304,318,321,479,482` and `vidbyte/sessions/failure/recovery/fork_recovery.py:54,63`.** These are the `api_key` arguments of `Session.fork`, `resume`, `continue_`, `fork_from`, and `_restore_agent`, plus the `runner_config.api_key` reads.
26. **`vidbyte/paradigms/context_minimal_fanout/types.py:426` and `paradigm.py:79,143,168`.** `AgentRoleSettings.api_key` (`types.py:426`, no `repr=False`) is passed in `paradigm.py`.
27. **`vidbyte/agents/codex/fallback.py:17,93`.** These mention `FallbackModel.api_key` in comments only.

### 2.4 Docs

28. **`README.md`.**
    - `### Vidbyte-managed text calls` (`:214-300`). The acceptance test finds it with the regex `^(#{2,4}) …vidbyte[- ]managed…` and requires these facts in it: `2%`, `VIDBYTE_API_KEY`, `Idempotency-Key`, `maxOutputTokens`, `max_output_tokens`, `previous_response_id`, `2,000,000`, `32,768`, and `630`, plus the six provider names and stream/service tier/snake case.
    - The "On / Off" bullets at `:240-258` describe today's BYOK-wins rule. `:1431` shows `Session.resume(..., api_key=tenant_key)`.
29. **`vidbyte/agents/README.md`.** `:156` says "bare name inherits provider, api_key, temperature". `:175` shows `FallbackModel(..., api_key=ANTHROPIC_KEY)`.
30. **`llms.txt`.** It has no TextModelMode or managed-mode text. `:1113` says "The serializer scrubs `api_key`…".
31. **`tests/features/sdk_managed_text/FEATURE.md` and `README.md`.** The contract text describes today's AUTO behavior.

### 2.5 Rename blast radius: `api_key` in `vidbyte/**/*.py`

Bare `api_key` (`git grep -cP "(?<![A-Za-z_])api_key\b"`) appears on 175 lines in 52 files (239 occurrences). Another 13 files contain only prefixed or method forms such as `resolved_api_key()` and `firecrawl_api_key`.

- **(a) Text-model provider key: 30 files, 95 lines.** These are the files in §2.1–2.3 above:
  - `agents/base.py`, `agents/aggregation.py`, `agents/fallback.py`, `agents/fork.py`, `agents/continual_trace.py`, `agents/handoff.py`, `agents/codex/fallback.py`
  - `agents/settings/fallback.py`, and 10 Jev files (`agents/jev/*`)
  - `lib/dataclasses/agents.py`, `lib/dataclasses/model_configs.py` (22 lines; includes the non-text and Decision fields), `lib/registries/models.py`
  - `lib/runners/{text,utility,router}.py`, `lib/agents/modality_detector.py`, `lib/http/vidbyte_gateway.py`
  - `sessions/session.py`, `sessions/failure/recovery/fork_recovery.py`, `paradigms/context_minimal_fanout/{paradigm,types}.py`
- **(b) A different secret: 16 files, 72 lines.**
  - `providers/tracing/langsmith.py` (7) and `trace/base.py` (8): LangSmith.
  - `providers/typesafe.py` (1): Decision/TypeSafe.
  - `tools/builtins/memory/{base,cognee,letta,mem0,supermemory,zep}.py` (42).
  - `tools/builtins/operations/clients/{_base,brave,browserbase,exa,firecrawl,parallel,tavily}.py` (14).
  - The prefixed-only files are `agents/coding.py`, `lib/dataclasses/coding.py`, and `tools/toolsets/coding.py` (the firecrawl, browserbase, parallel, and tavily keys).
- **(c) Internal plumbing or guards: 6 files, 8 lines.** `lib/http/parser.py`, `lib/util/credential_keys.py`, `lib/dataclasses/config.py`, `lib/dataclasses/agent_descriptor.py`, `harnesses/serialization.py`, `sessions/serialization.py`.
  - The provider adapters (`providers/{anthropic,compatible,gemini,openai,openrouter,xai,playai,elevenlabs}.py`) call `config.resolved_api_key()`, and `streaming_text.py` calls `get_api_key_env_var`. Neither is a bare match.
- **Docs:** `README.md` (3), `llms.txt` (2), `vidbyte/agents/README.md` (2), `vidbyte/tools/README.md` (1), `vidbyte/trace/README.md` (3). The last two are (b).

## 3. Tests that cover those files

- **Framework.** Tests are `unittest.TestCase` and `IsolatedAsyncioTestCase` classes collected by pytest 8.3.5 with pytest-asyncio 1.3.0 (`pyproject.toml:48-49`). `[tool.pytest.ini_options] testpaths = ["tests"]` (`:78-79`).
  - There is no root `tests/conftest.py`; the only conftest is `tests/features/coding_agent/conftest.py`. Nothing clears `VIDBYTE_API_KEY` globally.
- **Fixtures** (`tests/features/sdk_managed_text/managed_text_fixtures.py`, 180 lines, plain helpers rather than pytest fixtures).
  - `ScriptedGateway(*steps)` deep-copies each `request(**kwargs)` into `.requests`, answers from the script, and repeats the last step. Calling it returns itself, so it can replace a class.
  - `BackoffRecorder` records retry waits and can raise cancellation.
  - Body factories: `provider_answer`, `gateway_error` (carries `BODY_CANARY` and `LEAKED_KEY`), `relayed_provider_error`, and `edge_page`.
  - Helpers: `header(request, name)` (case-insensitive) and `idempotency_key`.
  - Constants: `VIDBYTE_KEY = "vb_live_" + "a"*32`, `GATEWAY_URL` as a literal, `MANAGED_MODELS` (6 providers, e.g. xai `grok-4.5`, kimi `kimi-k2.7-code`), and `UNMANAGED_TEXT_PROVIDERS`.
  - Patch targets: `RUNNER_TRANSPORT_TARGET = "vidbyte.lib.runners.text.HttpTransport"` and `SLEEP_TARGET = "vidbyte.lib.http.vidbyte_gateway.asyncio.sleep"`.
  - The environment is always `patch.dict(os.environ, {...}, clear=True)`.
  - Rule from its header: "Do not import symbols the feature adds … at module level". Import them inside the test so the pack still collects while it is red.
- **Feature pack `tests/features/sdk_managed_text/`.**
  - `test_managed_text_selection.py` (359): the INV-4 fall-through table (`:80-103`), explicit mode, credential errors, endpoint and provider refusals, the streaming refusal, runner pinning, other modalities, the field contract (`:47-51,277-289`), repr, adapter placeholder, and the Decision-shared resolver (`:327-347`).
  - `test_managed_text_acceptance.py` (191): the README snippet, the 6 providers (exactly 3 headers at `:97`), the BYOK goldens (`:110-143`), README facts (`:145-166`), and the Agent path (`:172-187`).
  - `test_managed_text_wire_contract.py` (172): caps, `extra_body`, the 630 s floor (with a BYOK 30 s case at `:138-143`), and emitted keys.
  - `test_managed_text_failures.py` (306): credential-safe errors and the remedy table (`:126-146`; the 402 remedy must match `wallet` and `provider key`), relayed errors, retries, and concurrency.
  - `test_managed_text_deadline.py` (203): the retry deadline, and direct `validate()` refusals (`:184-203`).
- **Module tests on the same boundary.**
  - Runners and modes: `tests/test_text_model_runner.py` (BYOK shapes), `tests/test_streaming_text_runner.py` (18 constructions), `tests/test_jev_managed_gateway.py` (Decision managed mode), `tests/test_model_registry.py` (`resolve_api_key` at `:50-61`; does not clear the env), `tests/test_config_validation.py`.
  - Agent key inheritance: `tests/test_agent_fork_isolation.py:444-518` (#884 fork key rules), `tests/test_agent_settings_validation.py:46-120` (fallback inheritance and the bare-string fallback), `tests/test_aggregate_agent.py:358-400` (aggregate key owner).
  - Sessions: `tests/test_durable_sessions.py:218-326,1077-1104` (scrubbing, tenant key on resume/fork), `tests/test_session_failures.py:575-582`.
  - Guards: `tests/test_harness_redaction.py`, `tests/test_lib_agent_descriptor_secrets.py` (#967), `tests/test_readme_size_limit.py` (A009).
- **`api_key=` in tests.** Bare `api_key=` appears 186 times in 44 files. Another 8 prefixed uses (firecrawl, tavily, parallel, browserbase) sit in the coding_agent files. By file:
  - About 15 are LangSmith (`test_tracing.py` 13, `test_trace_facade.py` 1, `test_semantic_tracing.py` 1).
  - About 17 are `DecisionModelConfig` (`test_jev_managed_gateway` 5, `test_jev_agent` 3, `test_jev_tool_selector` 3, `test_jev_usage_ledger` 2, `test_jev_managed_runs` 2, `test_jev_preflight` 1, `test_jev_skill_preload` 1).
  - About 37 are non-text modality configs (`test_audio_runner` 17, `test_embedding_runner` 15, `test_image_video_runners` 3, `test_config_validation` 2).
  - 5 are other secrets (`test_harness_redaction` 4, the webhook in `test_durable_sessions` 1).
  - That leaves about 112 text-model or agent provider keys.
  - Separately, 39 lines in 8 test files read `.api_key` as an attribute, such as `runner_config.api_key` and `FallbackModel.api_key`.
- **Commands.** Run from the worktree root with `PYTHONPATH=$(pwd)`.
  - One file: `PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text/test_managed_text_selection.py -q`
  - Area: `PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text tests/test_text_model_runner.py tests/test_streaming_text_runner.py tests/test_jev_managed_gateway.py tests/test_model_registry.py tests/test_config_validation.py tests/test_agent_fork_isolation.py tests/test_agent_settings_validation.py tests/test_aggregate_agent.py tests/test_durable_sessions.py tests/test_session_failures.py tests/test_harness_redaction.py tests/test_lib_agent_descriptor_secrets.py -q`
  - Lint focus: `python lint/run.py --rule C017` (and C018, C019, C020, A001, A009).
  - Full: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package`. AGENTS.md's gate is `python scripts/run_ci.py`. Then run semgrep after `git add -A`.
  - The pack's FEATURE.md says: "Run `python -m pytest tests/features/sdk_managed_text` (from a worktree, with `PYTHONPATH` set to the worktree)."

## 4. Notes for the spec author

### Contradictions (request assumes X; code shows Y)

1. **BYOK traffic changes.**
   - Request (§B.4 "What deliberately does not change … every existing test") assumes existing tests stay. Code shows that today's AUTO with a provider key goes vendor-direct, and these tests pin that behavior:
     - `test_managed_text_selection.py:83-93`: the rows "explicit provider key beats VIDBYTE_API_KEY" and "provider env key beats VIDBYTE_API_KEY" go to `OPENAI_RESPONSES_URL`.
     - `test_managed_text_acceptance.py:110-136`: the BYOK goldens are vendor URLs with `VIDBYTE_API_KEY` set.
     - `FEATURE.md`: "Developers who bring their own provider key (BYOK) must see no change at all" and "BYOK requests stay byte-identical to the base commit."
   - The new AUTO (relay) breaks all of these by design.
2. **A Vidbyte key passed as `api_key`.**
   - Request §C retires "a vb_live_ value in api_key stays Vidbyte-paid". Code shows `api_key=vb_live_…` IS the managed switch today: `registries/models.py:189-191` and `vidbyte_key_follows_provider` (`:207`).
   - Tests pin it: `test_managed_text_selection.py:84,151-152,176,196,312`, `test_agent_fork_isolation.py:456-469`, `test_agent_settings_validation.py:70-79`.
   - The README "On" bullet (`README.md:240`) says "pass a Vidbyte key as `api_key`".
3. **Positional and field contract.** Request assumes `api_key` is renamed to `api_keys`. Code: `api_key` is `TextModelConfig`'s third positional field, and tests pin both the order and the positional use (`test_managed_text_selection.py:47-51,284,286`, `TextModelConfig("openai","gpt-5.5","sk-positional").api_key`).
4. **Decision messages are shared.**
   - Request assumes Jev `DecisionModelConfig` is out of scope. Code: text and Decision share `resolve_vidbyte_api_key`, whose messages say "Pass api_key or set VIDBYTE_API_KEY." (`registries/models.py:221`). `test_managed_text_selection.py:327-347` asserts that Decision and the shared resolver give identical messages.
   - Rewording the text-mode message to name `vidbyte_api_key` therefore either changes Decision's message or splits the resolver.
5. **"Match keys with the pricebook".**
   - Request (Prompt 5) suggests matching keys using the pricebook. Code: `ModelPricingRegistry.resolve(provider, model)` needs the provider already (`registries/pricing.py`), and it imports `registries/models.py` (`:40`), so `models.py` cannot use it.
   - Model→provider today comes from `ProviderModelRegistry.provider_for_model` (`:330-339`), which reads the runner maps, not the pricebook.
6. **Key formats.** Request §C lists formats to check against first-party docs. Code has no provider key-format knowledge: the only format is `VIDBYTE_API_KEY_PATTERN` (`jev.py:65`), plus redaction regexes at `typesafe.py:255,271` and `langsmith.py:175`. Every request format is unverified (see below).
7. **Test keys are not real key shapes.** Request assumes deterministic format matching. Code: existing tests pass fake keys such as `"main-key"`, `"test-key"`, `"key"`, `"PARENTKEY"`, `"sk-explicit"`, `"sk-openai-byok"`, `"sk-deepseek-SECRET"`, and `"sk-tenant-acme"`. Examples: `tests/test_jev_compute_clone.py:49`, `test_agent_fork_isolation.py:493`, `test_managed_text_selection.py:83`, `test_durable_sessions.py:1077`. A strict classifier rejects all of them.
8. **The key reaches other modalities.** Request covers text calls. Code: `Runner._config_options_for` (`utility.py:101-107`) passes the agent's single key to Image/Video/Audio/Embedding configs too. Their `api_key` fields lack `repr=False` (`model_configs.py:193,247,307,360`). A list has no defined mapping for those configs.
9. **Aggregation.** Request B.4 step 8 names only `fork.py` and `settings/fallback.py`. Code: `AggregateAgent` (`aggregation.py:334-352`) has its own key-owner rule without `vidbyte_key_follows_provider`. `README.md:250-252` says fallback, fork, and aggregation children are all covered.
10. **AUTO for unserved providers.**
    - Request defaults to refusing AUTO for glm, minimax, meta, mistral, and openrouter. Code: these providers work BYOK in AUTO today, and `test_managed_text_selection.py:105-118` pins today's "Missing API key for provider openrouter…" message for AUTO with only `VIDBYTE_API_KEY`.
    - The algorithm helpers call `ModalityDetector.create_runner` with no key or mode (`multi_provider_agentic_grader.py:82,122`, `prosecutor_defender_judge.py:243`, `independent_critic.py:197`).
11. **Streaming.** Request: "the streaming runner keeps refusing gateway state". Code: if AUTO always means gateway, every default-mode `StreamingTextModelRunner` is refused. Tests build 23 streaming runners, 18 of them in `tests/test_streaming_text_runner.py`, and `test_managed_text_selection.py:227-233` expects BYOK streaming next to `VIDBYTE_API_KEY` to work in AUTO.
12. **Gateway wording.** Request B.2 wants the 402 text reworded. Code: `test_managed_text_failures.py:130` requires the 402 message to match `provider key`. The 413 message (`vidbyte_gateway.py:103`, "use your own provider key") and the 401 message (`:99`, "TextModelConfig.api_key") also stop being accurate.
13. **The repr of the agent's key record.** Request §C: "never … anywhere but the gateway transport's one header". Code: `AgentRunnerConfig.api_key` (`lib/dataclasses/agents.py:204`) has no `repr=False`, so `repr(agent.runner_config)` prints the key today. `AgentRoleSettings.api_key` (`paradigms/context_minimal_fanout/types.py:426`) has the same gap.
14. **Credential guards.** Request: the key never appears in logs or traces. Code: the field name `api_keys` escapes `CredentialKeyPolicy`, `_YamlSecretKeyPolicy`, the descriptor guard, and `HarnessRedactor._ERROR_ASSIGNMENT`. Only `SessionSerializer._is_secret_key` catches it (table in §2.2).
15. **File size.** AGENTS.md §3 says keep files well below 1,000 lines. Code: `vidbyte/agents/base.py` is already 1,725 lines, and the new parameters add more to it.
16. **No env isolation in the test suite.** Request: the AUTO check runs at construction. Code: there is no root conftest. Any test that builds a `TextModelRunner` in AUTO with only a provider key changes outcome depending on whether the developer's shell exports `VIDBYTE_API_KEY`. There are 42 `TextModelRunner(` lines in 12 test files, 8 of them outside the feature pack.

### Unverified

- Every key format in request §C: `sk-ant-`; `sk-proj-`, `sk-svcacct-`, `sk-admin-`, and legacy `sk-`+48; the `T3BlbkFJ` substring; `xai-`; `AIza`+35; DeepSeek `sk-`+32 hex; Kimi `sk-`+~48; OpenRouter `sk-or-v1-`+64 hex. Nothing in the repo confirms any of them.
- Whether C017's tracer still classifies the gateway request as `API_KEY` once a second header is added. The `string_flow.py:658-750` credential logic was skimmed, not traced. Run `python lint/run.py --rule C017`.
- Where the new classifier class should live (`lib/registries/` vs `lib/util/`). REPO_MAP does not map `lib/util/`.
- How many agent-level tests reach a real `TextModelRunner` through `Runner.build` with only a provider key. Only direct `TextModelRunner(` constructions were counted.
- The backend's exact handling of the header. I did not read the companion worktree, by instruction.
