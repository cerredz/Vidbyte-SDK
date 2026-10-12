# Code map: managed-generative-models (S0 scout)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-managed-generative-models`, branch `feat/managed-generative-models`, base `c07529316a5325bce986f84868ecbabb3b7f3056`. Every path, symbol, line, and command below was opened in this session unless marked "unverified".

## 1. Rules, commands, and conventions from AGENTS.md

### 1.1 Binding rules (quoted from `AGENTS.md`; `CLAUDE.md` is just `@AGENTS.md`)

**## Repository Map**
- "Read it before you create a file, move code, or search for where something lives, and put new code where it says that kind of code belongs." (it = `REPO_MAP.md`)
- "Each folder's own `README.md` documents that folder in more depth, so read it to the end before you change anything inside the folder. Its closing `## Notes for agents` section, where one exists, records mistakes that review has already caught there". Lint rule A009 caps each folder README at 40,000 characters. The root `README.md` is exempt.
- "**Do not grep, glob, or read files under `docs/` as part of ordinary work**"
- "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- "The Placement Rules below are not part of the map. That section is prescriptive, not descriptive: it is binding for all new code, and the `AGENTS.md placement` workflow enforces it on every pull request". The workflow file is `.github/workflows/agents-md-placement.yml`.

**### 1. Keep Call Chains One Level Deep**: "a function may call another of its own functions, but that second function should not call a third." "Avoid defining functions inside other functions as well, unless an API requires a callback or a decorator."

**### 2. Narrate Main Functions in Plain English**: "Inside that function, place short plain-English comments throughout the body, so that a reader can follow the whole feature by reading only the comments."

**### 3. Build in Layers of Small, Single-Purpose Classes**: "In this repository `vidbyte/lib/` is the bottom layer ... nothing in `vidbyte/lib/` may import from a layer above it." "Keep files well below 1,000 lines".

**### 4. Use Validated Dataclasses for Core Inputs and Outputs**: "Each dataclass validates itself strictly when it is created, in `__post_init__`". "Prefer `@dataclass(frozen=True, slots=True)` ... type any field whose value comes from a small, closed set as an enum."

**### Dataclasses go in `vidbyte/lib/dataclasses/`**: "**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`**". "Do not create `types.py`, `records.py`, `models.py`, or `schemas.py` modules". "`vidbyte/lib/` must never import from a layer above it. If a dataclass seems to need a type from a higher layer, move the contract down (a `Protocol` or a smaller record in `vidbyte/lib/`)." There are two exceptions: `*Settings` classes and JEV preflight questions.

**### Enums go in `vidbyte/lib/enums/`**: "**Every new enum ... is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions." "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`."

**### New JEV code**: "**A record** goes in `vidbyte/lib/dataclasses/jev.py`, **an enum or enum member** in `vidbyte/lib/enums/jev.py`, and **a constant** in `vidbyte/lib/constants/jev.py`."

**### Existing code**: "Do not copy them as precedent. Editing one in place (adding a field or a member) is fine."

Related binding text in `REPO_MAP.md` (opened): `vidbyte/lib/` is "not permitted to depend back on any of them"; for `lib/http`, "Nothing else in the package should reach for an HTTP client directly outside of this layer"; for `lib/constants`, "if a literal value would otherwise need to appear in two places, it belongs here".

### 1.2 Commands

AGENTS.md names exactly one command: `python scripts/run_ci.py`. Every other command here comes from the source cited next to it.

| Purpose | Command | Source |
|---|---|---|
| Install (once) | `python -m pip install -e ".[dev]"` | `CONTRIBUTING.md:35`; `.github/workflows/ci.yml:36` |
| Full gate | `python scripts/run_ci.py` | AGENTS.md; `scripts/run_ci.py` |
| Source stage only | `python scripts/run_ci.py --stage source` | `scripts/run_ci.py:260-264`; `CONTRIBUTING.md:62` |
| Package stage only | `python scripts/run_ci.py --stage package` | `scripts/run_ci.py:260-264` |
| Worktree source stage (Bash) | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no PYTHONPATH | field guide `local-ci-verification.md` |
| Worktree source stage (PowerShell) | `$env:PYTHONPATH=(Get-Location).Path` then `python scripts/run_ci.py --stage source` | `lint/README.md` |
| Worktree import check | `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` | field guide `local-ci-verification.md` |
| Lint, all rules | `python lint/run.py` | `lint/README.md`; `lint/run.py:35-40` |
| Lint, one rule | `python lint/run.py --rule C017`; add `--all` to show every finding; `--format json` for JSON | `lint/run.py:36-38` |
| Tests, one file | `python -m pytest tests/test_text_model_runner.py` | pytest config `pyproject.toml:78-80` (`testpaths = ["tests"]`, `addopts = ["--strict-config", "--strict-markers"]`); form used in `tests/test_jev_managed_gateway.py:9` |
| Tests, this area | `python -m pytest tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_text_model_runner.py tests/test_config_validation.py tests/test_model_registry.py tests/test_streaming_text_runner.py tests/test_sync_runner_default_transport.py` | file list from §3 |
| Tests, all | `python -m pytest` | `scripts/run_ci.py:93` |
| Focused Jev script | `python scripts/test-jev-managed-gateway.py` | named in `tests/test_jev_managed_gateway.py:9`; file exists in `scripts/` (unverified: contents not read) |
| Static policy (separate CI job) | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with `semgrep==1.170.1` | `.github/workflows/static-policy.yml:24,30` |

What `run_ci.py --stage source` runs (`scripts/run_ci.py:79-93`), in order:
1. A tracked-bytecode check.
2. `lint/run.py`.
3. `python -m compileall -q vidbyte`.
4. `scripts/check_context_write_paths.py`.
5. `scripts/check_context_primitive_introductions.py`.
6. `scripts/check_reasoning_trace_contracts.py`.
7. `python -m pytest`.

The package stage (`:95-218`) builds the wheel, runs `twine check`, installs into a clean venv, and runs smoke tests. `lint/run.py` fails when any rule count rises above its `lint/baseline.json` value.

Two notes on the semgrep policy:
- Its file pattern excludes `/vidbyte/lib/http/**` and `/vidbyte/providers/**` (`.semgrep/typed-mapping-boundary-policy.yml:12-18`), so a new file under `lib/dataclasses` or `lib/registries` is in scope.
- The field guide's local-ci-verification entry says semgrep scans only git-tracked files.

### 1.3 PR and commit conventions

- AGENTS.md states no PR or commit conventions.
- `CONTRIBUTING.md:75-85` says: "Use the pull-request template". A PR should include the problem and intended outcome, compatibility implications, the commands run and their output, documentation changes, and out-of-scope follow-ups.
- `.github/pull_request_template.md` has these sections: Motivation, Changes, Compatibility, Verification (with four checkboxes), and Follow-ups.
- Observed commit style (`git log --oneline -8`, a convention, not a written rule): `fix(scope): summary (#NNN)`, for example `fix(jev): give CLONE, SWARM, ... (#691)`.

## 2. Files this change will touch

The "Change" lines restate what `request.md` asks for. They are not designs. Line numbers are from the base commit.

### 2.1 `vidbyte/lib/dataclasses/model_configs.py` (444 lines): will change
- **Today:**
  - Defines the model configs: `TextModelConfig` (`:45-115`), Image, Video, Audio, Embedding, and `DecisionModelConfig` (`:341-431`).
  - `TextModelConfig` is `@dataclass(frozen=True, slots=True)` with 20 fields, including `api_key: str | None = None` (`:49`, no `repr=False`), `endpoint` (`:65`), and `timeout_seconds: float = 60.0` (`:66`). It has **no `__post_init__`**.
  - `validate()` (`:75`) runs the field validators and then `resolved_api_key()`. `resolved_api_key()` (`:84`) and `resolved_endpoint()` (`:88`) delegate to `ProviderModelRegistry`.
- **Change (request §B, E.2 l.237, E.3 step 10):** add a managed mode to `TextModelConfig` that mirrors `DecisionModelConfig`:
  - a mode field
  - the key hidden from repr
  - a managed key resolver that accepts only the live format
  - a managed endpoint resolver that pins the gateway and rejects a custom endpoint
- **Pattern to follow:** `DecisionModelConfig`.
  - Key field: `api_key: str | None = field(default=None, repr=False)` (`:347`). Mode field: `mode: DecisionModelMode = DecisionModelMode.TYPESAFE` (`:351`).
  - `__post_init__` (`:353`) rejects a custom endpoint in managed mode.
  - `resolved_api_key` (`:390`), under `# @intent managed-mode-never-falls-back-to-typesafe-key` (`:392`), checks `re.fullmatch(r"vb_live_[A-Za-z0-9_-]{32,}", key)` (`:401`). It raises `ConfigurationError(..., details={"error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND})` (`:402`).
  - `resolved_endpoint` (`:409`), under `# @intent managed-key-stays-on-vidbyte-host` (`:411`), returns `VIDBYTE_JEV_GATEWAY_ENDPOINT`.
  - `resolved_run_close_url` (`:419`) builds its URL with `removesuffix(JEV_MANAGED_GATEWAY_SUFFIX)` plus `JEV_MANAGED_RUN_CLOSE_PATH.format(run_id=...)`.
  - The classmethod `vidbyte_managed()` is at `:427`.
- **Header and helpers:**
  - The module header is the old "Context Protocol Header" style, without the A001 fields. Its "Similar Files: vidbyte/lib/models/registry.py" (`:17-18`) points to a file that does not exist (`vidbyte/lib/models/` holds only `__init__.py`).
  - Private `_validate_positive_int` and `_validate_positive_float` copies already sit in several classes (`:107`, `:112`, `:161`, `:166`, `:209`, `:214`, `:279`, `:325`, `:330`).

### 2.2 `vidbyte/lib/enums/decision_model.py` and `vidbyte/lib/enums/__init__.py`: will change if a mode enum is added or extended
- **Today:** `class DecisionModelMode(str, Enum): TYPESAFE = "typesafe"; VIDBYTE_MANAGED = "vidbyte_managed"`. The file has a full A001 header. `lib/enums/__init__.py` (220 lines, full A001 header) imports every public enum and lists it in `__all__`. `vidbyte.lib.config` re-exports `DecisionModelMode`.
- **Change:** a text-mode enum, or reuse of `DecisionModelMode`. The request does not choose.
- **Pattern:** AGENTS.md: a new enum goes in `vidbyte/lib/enums/<domain>.py` and "is added to the export list in `vidbyte/lib/enums/__init__.py`".

### 2.3 `vidbyte/lib/constants/jev.py` (694 lines): will change, or a sibling constants module will be added
- **Today:**
  - `JEV_SYSTEMONE_PATH="/systemone"` (`:18`) and `JEV_MODELS_PATH="/models"` (`:19`).
  - `VIDBYTE_JEV_GATEWAY_ENDPOINT: str = "https://api.vidbyte.pro/api/v1/models/typesafe"` (`:20`) and `VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND` (`:21`).
  - `JEV_MAX_RESPONSE_BYTES=16_000_000` (`:44`).
  - `JEV_MANAGED_GATEWAY_SUFFIX="/typesafe"`, `JEV_MANAGED_RUN_CLOSE_PATH`, `JEV_MANAGED_RUN_ID_HEADER="X-Vidbyte-Run-Id"`, `JEV_MANAGED_RUN_ID_PREFIX`, `JEV_MANAGED_RUN_ID_PATTERN`, and `JEV_IDEMPOTENCY_KEY_HEADER="Idempotency-Key"` (`:47-52`).
  - `VIDBYTE_STATUS_*` and `VIDBYTE_MANAGED_ACCESS_DENIAL_STATUS_CODES = frozenset({401,402,403,429})` (`:67-71`).
  - There is no `*API_KEY_PREFIX` constant.
- **Change (request E.2 l.235, E.3 step 9):** move the header names into shared gateway constants and add a gateway root. Lint C020 requires one owner constant for the `vb_live_` prefix.
- **Pattern:**
  - lint `c020_api_key_prefix_contract.py:32-34`: `OWNER_SUFFIX = "API_KEY_PREFIX"`, `RECOMMENDED_OWNER = "VIDBYTE_API_KEY_PREFIX"`, `RECOMMENDED_HOME = "vidbyte/lib/constants/jev.py"`.
  - C017 repair text (`c017_platform_route_contract.py:204`): "Keep the constant that holds the path in vidbyte/lib/constants/ beside the endpoint it extends."
- **Other constants modules:** `lib/constants/` holds `__init__.py`, `codex.py`, `cot_events.py`, `failure.py`, `jev.py`, `reasoning_strategies.py`, `runners.py`, `speed.py`, and `trace.py`. There is no generic gateway module. `constants/__init__.py` does not re-export the jev constants.

### 2.4 `vidbyte/lib/registries/models.py` (354 lines): will change
- **Today:**
  - `ProviderModelRegistry` holds `DEFAULT_PROVIDER_MODELS`, `API_KEY_ENV_VARS` (`:73`), and `DEFAULT_ENDPOINTS` (`:90`).
  - `resolve_api_key` (`:152`) tries the explicit key, then the provider env var, then raises `ConfigurationError("Missing API key for provider ... Pass api_key or set {env_var}.")` (`:161`).
  - `resolve_endpoint` is at `:164`. `resolve_active` (`:221`) and `_resolve_from_environment` (`:337`) choose the active providers from the env keys.
  - The module imports `vidbyte.lib.agents.modality_detector.ModalityDetector` (`:43`).
- **Change (request l.239, E.3 step 11):** add a third fall-through step, `VIDBYTE_API_KEY`. A resolved key with the `vb_live_` prefix means managed mode.
- **Pattern:** the existing explicit-then-env order. S014 requires `API_KEY_ENV_VARS`, `DEFAULT_ENDPOINTS`, and `DEFAULT_PROVIDER_MODELS` keys to match the `ModelProvider` members exactly. `vidbyte/lib/config/constants.py` re-exports `API_KEY_ENV_VARS` and `DEFAULT_ENDPOINTS`.

### 2.5 `vidbyte/lib/http/` (`transport.py` 211 lines, `parser.py` 48 lines, `__init__.py`): will change (new header builder)
- **Today:**
  - `HttpResponseParser.bearer_headers(api_key)` (`parser.py:21`) returns `{"authorization": f"Bearer {api_key}", "content-type": "application/json"}`.
  - `parse_json_response` (`parser.py:13-18`) raises `ProviderRequestError(..., response_excerpt=response.body)` on a non-2xx status. It does the same on invalid JSON (`:30`) and non-object JSON (`:32`).
  - `_IDEMPOTENT_METHODS` (`transport.py:19`) and `_require_idempotency_guard` (`:22-25`) raise only when `retry_count > 0`, the method is non-idempotent, and no key is given.
  - `HttpTransport.request(..., retry_count=0, ..., max_response_bytes=None, idempotency_key=None, follow_redirects=False)` is at `:40`. `SyncHttpTransport.request` is at `:101`.
  - `__init__.py` exports `HttpResponse`, `HttpResponseParser`, `HttpTransport`, and `SyncHttpTransport`.
  - `transport.py` has no header docstring, and `lib/http` has no README.
- **Change (request l.243, E.3 step 12):** "one shared header builder in `vidbyte/lib/http/`". In direct mode it returns the native auth headers. In managed mode it returns `Authorization: Bearer vb_live_…` plus the managed headers.
- **Pattern:** `bearer_headers` as above. TypeSafe adds its managed headers in `providers/typesafe.py:171-177`.

### 2.6 `vidbyte/lib/runners/streaming_text.py`: will change (reject managed mode)
- **Today:** `STREAMING_SUPPORTED_PROVIDERS` (`:17`) is `{OPENAI, ANTHROPIC}`. `__init__` (`:22`) calls `config.validate()` (`:25`) and `_validate_streaming_provider` (`:51-54`), which raises `UnsupportedProviderError`. It uses `SyncHttpTransport` and `ModelProviders.streaming_text`.
- **Change (request §B, E.3 step 15):** "Streaming raises a clear error in managed mode."
- **Pattern:** `_validate_streaming_provider`, which rejects at construction.

### 2.7 `vidbyte/lib/runners/text.py` (71 lines, no header): may change
- **Today:** `TextModelRunner.__init__` (`:19`) coerces the config and calls `config.validate()` (`:29`), which resolves the key at construction. It then sets `self._provider = ModelProviders.text(config)` (`:32`). `arun` (`:34`) builds the call config with `dataclasses.replace(...)` (`:36`), so `__init__`/`__post_init__` run again on every call, and then calls `self._provider.run_text(...)`. It does not write to the usage ledger.
- **Change:** none is named in the request. The managed mode passes through it.
- **Pattern:** `vidbyte/lib/runners/decision.py:40-55` records into the ledger (`UsageKind.DECISION`).

### 2.8 `vidbyte/lib/runners/utility.py` and `vidbyte/lib/agents/modality_detector.py`: read-only context, possible pass-through
- **utility.py today:** `Runner.from_model` (`:34`), `build` (`:65`), `_refuse_decision_runner` (`:89`), and `_config_options_for` (`:101`). The last filters options down to the config dataclass fields, so a new `TextModelConfig` field is accepted automatically.
- **modality_detector.py today:** `ModalityDetector.create_runner` (`:121`) and `build_config` (`:208`) filter to the config fields the same way.
- **Agent path:** `BaseAgent._runner_for_model` (`vidbyte/agents/base.py:1444`) calls `Runner.from_model` (`:1448`). The fallback chain calls it too (`vidbyte/agents/fallback.py:162`).

### 2.9 Provider adapters (`vidbyte/providers/`): touched only if adapters call the new builder (see §4 item 6)

| File | `run_text` | URL composition | Auth headers | Usage key |
|---|---|---|---|---|
| `openai.py` | `:27` | `f"{config.resolved_endpoint()}/responses"` (`:30`) | `self._parser.bearer_headers(config.resolved_api_key())` (`:30`) | `usage` (`:32`) |
| `anthropic.py` | `:22` | `/messages` (`:25`) | `_create_headers`: `{"x-api-key": ..., "anthropic-version": "2023-06-01", ...}` (`:58`) | `usage` (`:27`) |
| `gemini.py` | `:23` | `/models/{quote(model)}:generateContent` (`:26-27`); the model appears only in the URL | `{"x-goog-api-key": ...}` (`:44`) | `usageMetadata` (`:29`) |
| `compatible.py` (DeepSeek, GLM, MiniMax, Kimi, Meta, Mistral; `xai.py:13` subclasses it) | `:29` | `/chat/completions` (`:32`) | bearer (`:32`) | `usage` (`:34`) |
| `openrouter.py` (excluded from managed mode) | `:37` | `/chat/completions` (`:43`) | bearer plus Referer and title headers (`:40`) | `usage`; payload sets `usage: {"include": True}` (`:50`) |

- The streaming paths are `openai.py:94/99` and `anthropic.py:99/104`.
- No text adapter passes `retry_count` or `idempotency_key`.
- `providers/__init__.py`: `ModelProviders.text` (`:42`) maps 11 providers, OpenRouter included. `decision` is at `:88`; `streaming_text` (`:97`) maps OpenAI and Anthropic.
- `providers/README.md` (614 lines) has no `## Notes for agents` section. Its Contract Invariants include "API keys never appear in a URL".

### 2.10 `vidbyte/providers/typesafe.py` (502 lines): reference pattern; changes if shared constants replace the Jev ones
- **Today:**
  - `_MANAGED_RUN` ContextVar (`:74`).
  - The builder adds managed headers (`:171-177`) and builds the URL `f"{config.resolved_endpoint()}{JEV_SYSTEMONE_PATH}"` (`:177`).
  - The close call is at `:181` and the models list at `:188`.
  - `managed_transport_error` (`:222`) carries `# @intent managed-error-output-never-echoes-gateway-body`. `managed_failure_reason` is at `:230`.
  - Inline redaction `re.sub(r"vb_live_[A-Za-z0-9_-]{32,}", "[redacted]", ...)` appears at `:255` and `:271`.
- **Pattern:** managed errors use `provider="vidbyte"`, carry no response excerpt, and are raised `from None`.

### 2.11 `vidbyte/lib/jev/managed.py` (67 lines): reference only (run ids deferred, request §B l.60/l.66)
- **Today:** `JevManagedRun` is an async context manager. It imports `vidbyte.providers.typesafe.TypeSafeManagedRunContext`, opens `JevManagedRunScope(run_id="jev:...")` (`vidbyte/lib/dataclasses/jev.py:3971`), and closes best-effort through `DecisionModelRunner(...).aclose_run`.

### 2.12 Read-only context outside lib
- **`vidbyte/agents/settings/fallback.py:147-155`** (`_inherited_api_key`): returns `None` on a provider change. Comment: "None lets the target provider read its own env key".
- **`vidbyte/agents/fork.py:85-95`** (`_api_key`): same rule.
- **`vidbyte/agents/aggregation.py:331-340`** (`_resolve_key_owner`) and **`:342-349`** (`_child_api_key`): same rule.
- **`vidbyte/agents/runtime.py:607-690`**: middleware-driven model retries (`on_model_error` at `:679`; sleep and retry at `:684-685`).
- **`vidbyte/lib/usage_ledger.py`** and **`vidbyte/agents/pricing/tracker.py`**: these are where local usage is recorded and priced.
- **`vidbyte/lib/enums/model_provider.py`**: `ModelProvider` has 14 members. `usage_class()` imports `vidbyte.agents.pricing` lazily.

### 2.13 Contract and docs files
- **`lint/contracts/vidbyte-platform-contract.json`**: vendored byte for byte from cerredz/Vidbyte. "Never hand-edit." The re-vendor procedure and provenance row are in `lint/contracts/README.md`. Contents:
  - Source commit `3b501a63...` (`:3`).
  - The only `models.*` routes (`:15-17`): `models.runs.close` POST `/api/v1/models/runs/{run_id}/close`, `models.typesafe.list` GET `/api/v1/models/typesafe/models`, and `models.typesafe.systemone` POST `/api/v1/models/typesafe/systemone`. All are `API_KEY` with scope `models:invoke`.
  - `model_gateway_*` and `model_run_not_found` error codes (`:144-152`).
  - `"api_key_prefix": "vb_live_"` (`:205`).
  - Hosts (`:207-208`): `https://vidbyte-backend.onrender.com` is `live` and `https://api.vidbyte.pro` is `planned`.
- **`README.md`** (1801 lines): no managed-mode or `VIDBYTE_API_KEY` section today. Request step 15 asks for one.
- **`llms.txt`**: no `VIDBYTE_API_KEY` or managed mention.
- **No `.env.example`** exists at the repo root.
- **`REPO_MAP.md`**: the JEV File Locations table lists the managed pieces.
- **`skills/jev-agent/SKILL.md:14,24`**: describes the Jev managed gateway.
- **`contracts/sdk-public-api.json`** (C016): changes only if root `vidbyte.__all__` changes. `TextModelConfig`, `DecisionModelConfig`, and `DecisionModelMode` are not root exports.

## 3. Tests that cover those files

**Framework:**
- pytest runs unittest-style classes. `unittest.TestCase` and `unittest.IsolatedAsyncioTestCase` are the norm. `tests/test_sync_runner_default_transport.py` uses plain pytest with `monkeypatch`.
- Config is at `pyproject.toml:78-80`. There is no `tests/conftest.py`. The shared helper is `tests/agent_test_support.py` (`bind_test_runner`).
- No test touches the network. A scripted transport is injected, or `HttpTransport` or `urlopen` is patched.

| Test file | Covers | Fixtures and patterns | Command |
|---|---|---|---|
| `tests/test_jev_managed_gateway.py` (293 lines) | `DecisionModelConfig` managed key, endpoint, and repr; `_TypeSafeCallBuilder`; managed error redaction; Jev failure policy | `VIDBYTE_KEY = "vb_live_" + "a" * 32` (`:39`); `ScriptedTransport` records the `request(**kwargs)` calls (`:43-54`); `patch.dict(os.environ, {...}, clear=True)`; asserts the host `https://api.vidbyte.pro/api/v1/models/typesafe` (`:120`, `:154`, `:163`); checks `follow_redirects` defaults False (`:200`) | `python -m pytest tests/test_jev_managed_gateway.py` |
| `tests/test_jev_managed_runs.py` (175 lines) | Run-id header, idempotency header, run close, `JevManagedRun` | `GatewayTransport` stands in for the HttpTransport class through `patch("vidbyte.lib.runners.decision.HttpTransport", new=transport)` (`:35`, `:38-61`); imports `VIDBYTE_JEV_GATEWAY_ENDPOINT` (`:23`); idempotency key length 32 when `retry_count=2` (`:126-135`) | `python -m pytest tests/test_jev_managed_runs.py` |
| `tests/test_text_model_runner.py` (145 lines, no header) | `TextModelRunner` plus the OpenAI, Anthropic, Gemini, and xAI request shapes | `FakeTransport.request(*, method, url, headers, json_body, timeout_seconds, **kwargs)` (`:12-36`); sync `runner.run(...)`; asserts the vendor URLs and headers (`:50`, `:112`, `:127-128`, `:140`) | `python -m pytest tests/test_text_model_runner.py` |
| `tests/test_config_validation.py` (64 lines) | `TextModelConfig` key and endpoint resolution, validation | `patch.dict("os.environ", {...}, clear=True)` (`:19`, `:25`) | `python -m pytest tests/test_config_validation.py` |
| `tests/test_model_registry.py` (101 lines) | `ProviderModelRegistry.resolve_api_key` and `resolve_endpoint` | `patch.dict(os.environ, {})` **without** `clear=True`, then deletes `OPENAI_API_KEY` and expects `ConfigurationError` (`:57-61`) | `python -m pytest tests/test_model_registry.py` |
| `tests/test_streaming_text_runner.py` (232 lines) | `StreamingTextModelRunner` | `FakeStreamingTransport.stream_request` (`:15-22`); an unsupported provider raises at init (`:175-187`) | `python -m pytest tests/test_streaming_text_runner.py` |
| `tests/test_sync_runner_default_transport.py` (100 lines) | Default `SyncHttpTransport` for streaming, audio, and embedding | Monkeypatches `transport_module.urlopen` (`:48-57`) | `python -m pytest tests/test_sync_runner_default_transport.py` |
| `tests/test_agent_fork_isolation.py:382-404` | Fork key guard | `patch.dict(os.environ, {"OPENAI_API_KEY": ...})` | `python -m pytest tests/test_agent_fork_isolation.py` |
| `tests/test_aggregate_agent.py:339-391` | Aggregation key guard | n/a | `python -m pytest tests/test_aggregate_agent.py` |
| `tests/test_fork_tool.py:113-132` | Fork-tool provider swap drops the key | n/a | `python -m pytest tests/test_fork_tool.py` |
| `tests/test_agent_settings_validation.py:32-66` | Fallback key inheritance (`FallbackApiKeyInheritanceTests`) | n/a | `python -m pytest tests/test_agent_settings_validation.py` |
| `tests/test_multi_provider_agentic_grader.py` | Iterates `API_KEY_ENV_VARS` to set or clear env (`:37`, `:77`, `:286-287`, `:330`, `:343`) | n/a | `python -m pytest tests/test_multi_provider_agentic_grader.py` |

Also found by `git grep` for `TextModelConfig|resolve_api_key|HttpTransport|ProviderModelRegistry` (not read in full): `tests/test_gemini_tool_wire_format.py`, `tests/test_deepseek_provider.py`, `tests/test_openrouter_provider.py`, `tests/test_output_schema_provider_dialect.py`, `tests/test_agent_tool_loop.py`, `tests/test_memory_tools.py`, `tests/test_mcp_discovery_tools.py`, and `tests/test_web_operation_client_retry.py`.

The Jev test headers use the `FILE:` / `PURPOSE:` / ... `TESTS:` docstring (`tests/test_jev_managed_gateway.py:1-10`). That is the shape a new test module would copy. REPO_MAP says Jev tests are `tests/test_jev_*.py` and focused scripts are `scripts/test-jev-*.py`.

## 4. Notes for the spec author

1. **C017: the SDK PR cannot be green on its own.**
   - **Request assumes:** "Each PR must be independently mergeable and green in its own repo" (request l.48).
   - **Code shows:** C017 baseline is 0 (`lint/baseline.json:19`). Every SDK request whose origin is a Vidbyte host must match a route in the vendored contract. The contract's only `models.*` routes are the three Jev routes (`lint/contracts/vidbyte-platform-contract.json:15-17`). The file is a byte copy that is regenerated in cerredz/Vidbyte and re-vendored (`lint/contracts/README.md`).
   - **Consequence:** a new generative route makes `python lint/run.py` fail until the backend route merges and the contract is re-vendored here.
2. **C017 traces into every adapter.**
   - The tracer follows `config.resolved_endpoint()` through calls. The C017 diagnostic cites `providers/typesafe.py:177` as its correct example.
   - If `TextModelConfig.resolved_endpoint()` can return a Vidbyte URL, every adapter's URL becomes a traced Vidbyte request, and each path must exist in the contract: `openai.py:30` `/responses`, `anthropic.py:25` `/messages`, `gemini.py:27` `/models/{model}:generateContent`, `compatible.py:32` `/chat/completions`, plus the streaming paths at `openai.py:99` and `anthropic.py:104`.
   - **Request assumes** "exactly ONE new route" (§B l.54) and also "no adapter change to the URL logic" with four suffix paths (E.2 l.237, E.4). Those two statements conflict, and the request lists it as open (l.103-104).
   - C017 counts credentials as API_KEY only with an `authorization` header. `anthropic.py:58` (`x-api-key`) and `gemini.py:44` (`x-goog-api-key`) count as no credential. Unverified: how the tracer scores a header dict chosen at runtime.
3. **The host is planned, not live.**
   - **Request assumes:** `https://api.vidbyte.pro/api/v1/models/...` (l.212, l.235, l.298).
   - **Code shows:** the contract marks `api.vidbyte.pro` as `planned` and `vidbyte-backend.onrender.com` as `live` (`contract:207-208`). C018's baseline of 1 (`lint/baseline.json:20`) is the existing `VIDBYTE_JEV_GATEWAY_ENDPOINT` (`lib/constants/jev.py:20`). C018 says "Raising C018's baseline ... a second non-live host is a second outage" (`c018_canonical_api_host.py:114`).
   - Unverified: whether a URL derived from the existing constant (as `resolved_run_close_url` derives one) adds a C018 finding. The rule reports literals.
4. **C020 prefix owner.**
   - **Request assumes:** the key format `vb_live_[A-Za-z0-9_-]{32,}` (l.77).
   - **Code shows:** no `*API_KEY_PREFIX` constant exists. Inline copies appear at `model_configs.py:401-402` and `providers/typesafe.py:255`, `:271`. The C020 baseline is 4 (`lint/baseline.json:22`). Unverified: that these are exactly the four baselined sites.
   - Any new literal that spells `vb_live_`, including one inside an error message, adds a finding. The recommended owner is `VIDBYTE_API_KEY_PREFIX` in `vidbyte/lib/constants/jev.py` (`c020_api_key_prefix_contract.py:33-34`).
5. **C019:** baseline 0 (`lint/baseline.json:21`). Any decision-position literal that the SDK compares, maps, or defines in the `model_gateway_*` family must be one of the contract codes at `contract:144-152`.
6. **"SDK changes stay in `vidbyte/lib/`" versus adapter edits.**
   - **Request assumes:** the adapters "call it from their existing header methods" (E.3 step 12, l.359).
   - **Code shows:** those methods live in `vidbyte/providers/`: `anthropic.py:58`, `gemini.py:44`, and inline `bearer_headers` calls at `openai.py:30`, `compatible.py:32`. URL composition is also in the adapters. lib supplies only `resolved_endpoint()`, `resolved_api_key()`, and `bearer_headers` (`lib/http/parser.py:21`). The request lists this as open (l.104).
7. **Layering is stated two ways.**
   - AGENTS.md Style 3 says "`vidbyte/lib/` is the bottom layer". REPO_MAP says lib is "not permitted to depend back on any of them".
   - Code: lib already imports providers. `lib/runners/text.py`, `streaming_text.py`, and `decision.py` import `vidbyte.providers.ModelProviders`. `lib/jev/managed.py` imports `vidbyte.providers.typesafe`.
   - Lint A006 treats `vidbyte.lib`, `vidbyte.providers`, `vidbyte.sessions`, and `vidbyte.sources` as one lower tier and flags only lower-to-orchestration imports and concrete cycles. Baseline 34.
8. **Idempotency.**
   - **Request assumes:** "`HttpTransport` refuses to retry a POST without an `idempotency_key`" (l.77, l.247).
   - **Code shows:** that holds only when `retry_count > 0` (`lib/http/transport.py:22-25`). Text adapters pass neither `retry_count` nor `idempotency_key`, so the default is 0 (`:40`).
   - Model retries happen in `vidbyte/agents/runtime.py:607-690` (`on_model_error` at `:679`), and each retry calls the runner again and sends a new POST. A key minted per request inside lib would differ on every retry. Run ids are deferred (§B l.60, l.66).
9. **Key fall-through timing.**
   - **Request assumes:** adding `VIDBYTE_API_KEY` to `ProviderModelRegistry.resolve_api_key` (l.239; code at `registries/models.py:152-161`).
   - **Code shows:** `TextModelRunner.__init__` resolves the key at construction (`lib/runners/text.py:29`). `resolve_active` and `_resolve_from_environment` (`:221`, `:337`) pick active providers from `API_KEY_ENV_VARS`. Unverified: whether the fall-through should change active-provider detection.
   - S014 (baseline 0) requires `API_KEY_ENV_VARS` keys to equal the `ModelProvider` members, so a non-provider env entry there fails the lint.
   - `tests/test_model_registry.py:57-61` does not clear the environment. A developer machine with `VIDBYTE_API_KEY` set would change that test's outcome after a fall-through.
10. **Key-crossing guards.**
    - **Request assumes:** guard ranges fallback ~142-149, fork ~85-94, aggregation ~342-349 (l.98).
    - **Code shows:** actual ranges are `agents/settings/fallback.py:147-155`, `agents/fork.py:85-95`, and `agents/aggregation.py:331-340` plus `:342-349`.
    - All three filter only an **explicit** key and return `None`, so the child resolves its own env key (comments at `fallback.py:150-151`, `fork.py:88-89`, `aggregation.py:344-345`).
    - **So:** a `VIDBYTE_API_KEY` resolved from the environment does not trip them. The child goes through the same resolution. An explicit `api_key="vb_live_..."` on the parent is dropped for a cross-provider child. The request lists this as open (l.109).
11. **repr and validation location.**
    - `TextModelConfig.api_key` lacks `repr=False` (`model_configs.py:49`); `DecisionModelConfig` has it (`:347`).
    - `TextModelConfig` has no `__post_init__`; validation is in `validate()` (`:75`).
    - `TextModelRunner.arun` calls `dataclasses.replace` on every call (`lib/runners/text.py:36`), which re-runs construction-time checks.
    - `tests/test_jev_managed_gateway.py:125-132` pins `DecisionModelConfig` positional order.
    - Unverified: whether any caller constructs `TextModelConfig` positionally. A `git grep` for `TextModelConfig(ModelProvider.|"|'|provider,` found none.
12. **Error bodies.**
    - **Request assumes:** "never echo gateway or upstream bodies in managed error messages" (l.72).
    - **Code shows:** the text adapters use `HttpResponseParser.parse_json_response`, which attaches `response_excerpt=response.body` (`lib/http/parser.py:18`, `:30`, `:32`). Only the TypeSafe adapter has a managed path without excerpts (`providers/typesafe.py:222`, raised `from None`).
13. **C008:** baseline 45. `model_configs.py` already has per-class `_validate_*` copies (§2.1). `vidbyte/lib/dataclasses/validation.py` does not exist. A new primitive validator copy regresses C008.
14. **New files:**
    - A001 (baseline 643) requires the `PURPOSE:` / `ROLE IN CODEBASE:` / `ARCHITECTURE NOTE:` / `COMMON MODIFICATION PATTERNS:` / `KNOWN EDGE CASES:` / `RELATED DOCS:` / `TESTS:` header.
    - A002 (baseline 703) requires a `# @intent` marker near functions with policy tokens such as request, send, provider, secret, redact, or retry.
    - A007 (baseline 255) bars bare numeric literals in timeout, status, byte, and limit contexts.
    - C006 (104) and C007 (16) cover numeric and bool guards on new config fields.
15. **Usage and markup.**
    - `TextModelRunner` does not record into the usage ledger; only `DecisionModelRunner` does (`lib/runners/decision.py:40-55`).
    - The request places the 200 bps constant in the backend (l.58, E.3 step 2) and defers "showing marked-up cost in the SDK's local usage tracker" (§B l.60). Unverified: whether any SDK-side 200 bps constant is needed in v1.
16. **Request shape inputs:** Gemini carries the model only in the URL path (`gemini.py:26-27`) and reports usage under `usageMetadata` (`:29`). OpenRouter is in `ModelProviders.text` (`providers/__init__.py:42`), and no managed exclusion exists yet.
17. **Import cycles:** `lib/dataclasses/jev.py:5` says "This module must not import model_configs because that would close an import cycle through ModalityDetector". `registries/models.py:43` imports `ModalityDetector`.
18. **File size:** `lib/constants/jev.py` is 694 lines. AGENTS.md "New JEV code" sends constants there, but generative-gateway constants are not JEV, and no generic gateway constants module exists.
19. **Tests pin the current host and constant:** `tests/test_jev_managed_gateway.py:120,154,163` and `tests/test_jev_managed_runs.py:23,32`.
20. **Docs:** `README.md` and `llms.txt` have no managed or `VIDBYTE_API_KEY` content. There is no `.env.example`. `lib/http/` has no README. `vidbyte/lib/README.md` and `vidbyte/providers/README.md` have no `## Notes for agents` section.
21. **Unverified:**
    - The backend wire contract. The sibling `generative-model-gateway` spec does not exist yet, so the Jev shape in §2.10 and §2.13 is the reference.
    - The contents of `scripts/test-jev-managed-gateway.py`.
    - Whether `DecisionModelMode` can be reused for text.
    - Whether the C017 tracer follows a header builder's conditional return.

**Field-guide entries that apply** (from `field-guide/vidbyte-sdk/init.md`; listed, not summarized):
- `local-ci-verification.md`
- `blocking-lint-invariants.md`
- `strict-config-dataclasses.md`
- `provider-api-contracts.md`
- `class-bound-helpers.md`
- `fallback-coordination.md`
- `runtime-boundaries.md`
- `declarative-config-resolution.md`
