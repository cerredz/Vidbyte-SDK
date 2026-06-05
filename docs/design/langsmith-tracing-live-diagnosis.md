# Design Doc: LangSmith Tracing Live Diagnosis

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-05
**Last Updated:** 2026-06-05

---

## 1. Overview

This cross-repository change diagnoses and fixes why MBPP eval runs from `vidbyte-evals` do not appear in the user's LangSmith project even when LangSmith environment variables are configured. The work covers `vidbyte-evals` for local credential loading, eval execution, and run verification, and `vidbyte-sdk` for the LangSmith tracing adapter, error visibility, endpoint support, and tracer verification tests.

---

## 2. Goals & Non-Goals

### Goals

- Load local, ignored `vidbyte-evals/.env` values before MBPP eval scripts initialize tracers and model providers.
- Keep real API keys out of committed files, logs, reports, and PR descriptions.
- Verify that MBPP eval agents receive a LangSmith tracer when `LANGSMITH_API_KEY` is configured.
- Make the SDK `LangSmithTracer` honor `LANGSMITH_ENDPOINT`.
- Make LangSmith delivery failures diagnosable without breaking normal agent runs by default.
- Add no-network tests for env loading, endpoint wiring, and error reporting.
- Add a live smoke verification script that can create and close one LangSmith run before spending model-provider tokens on a full eval.
- After approval, run the MBPP eval with the provided local credentials and use the result to decide whether the resolving PR belongs in `vidbyte-evals`, `vidbyte-sdk`, or both.

### Non-Goals

- Commit real `.env` files or secrets.
- Change LangSmith project/account settings.
- Rewrite the agent tracing abstraction.
- Add LangGraph-specific instrumentation. The current SDK traces raw SDK agent/runtime calls, not LangGraph graph internals.
- Run all benchmark variants unless the baseline smoke run shows the tracing path works and the user approves the additional cost.

---

## 3. Background & Context

`vidbyte-evals` contains MBPP eval scripts in `evals/mbpp/`. `MBPPEval._init_tracer()` dynamically imports `vidbyte.providers.tracing.langsmith.LangSmithTracer` when `LANGSMITH_API_KEY` is present. The tracer is passed to the primary `BaseAgent` and to the two agent-as-tool subagents. Existing `scripts/test_mbpp_eval_runs.py` verifies this with mocked `langsmith.Client`.

`vidbyte-evals/.gitignore` already ignores `.env` and `.env.*`, so local credentials can be added without a committed gitignore change. The current MBPP config points at `provider: gemini`, `model: gemini-2.5-flash`, and `api_key_env: GEMINI_API_KEY`; the user provided an xAI key, so either the config must be intentionally changed to xAI or the run must use a Gemini key that is not currently supplied.

`vidbyte-sdk` defines the tracing contract in `vidbyte/lib/tracing/base.py`, exposes `Trace.langsmith()`, and implements `LangSmithTracer` in `vidbyte/providers/tracing/langsmith.py`. `BaseAgent.generate_reply()` opens one `agent.run` trace, `AgentRuntime._invoke_with_middleware()` opens `llm.call` spans, and `AgentRuntime.execute_tool_call()` opens `tool.call` spans. Current SDK tests use a fake tracer and do not verify that LangSmith accepts the real adapter payload. The adapter also swallows all LangSmith API exceptions, which can make trace delivery fail silently.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-evals` must load `vidbyte-evals/.env` before `MBPPEval._init_tracer()` checks `LANGSMITH_API_KEY`.
2. `vidbyte-evals` must not require `python-dotenv`; a small local parser is sufficient for `KEY=value` lines and quoted values.
3. `vidbyte-evals` must preserve existing OS environment variables over `.env` values unless explicitly documented otherwise.
4. The local `.env` must include `LANGSMITH_TRACING`, `LANGSMITH_ENDPOINT`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and the model provider key required by `evals/mbpp/config.yaml`.
5. If the user wants to run with the provided xAI key, MBPP config must use `provider: xai`, a Grok text model, and `api_key_env: XAI_API_KEY`.
6. `LangSmithTracer` must pass `api_url` or the current LangSmith client equivalent when `endpoint` or `LANGSMITH_ENDPOINT` is configured.
7. `LangSmithTracer` must expose safe delivery diagnostics for create/update failures without exposing API keys.
8. Normal agent runs must continue even when LangSmith delivery fails, matching the existing best-effort tracing behavior.
9. A strict verification mode or smoke script must fail when LangSmith create/update fails, so live diagnosis cannot silently pass.
10. The verification scripts must print `PASS` or `FAIL` per test case and exit non-zero on failures.

### Non-Functional Requirements

- Security: never commit secrets; never echo full API keys; redact any key-like value in diagnostics.
- Reliability: failed trace delivery should not fail production agent runs unless strict verification is explicitly requested.
- Observability: live smoke verification must distinguish missing package, missing key, auth failure, endpoint failure, payload rejection, and invisible-project mismatch where possible.
- Compatibility: keep `tracer=` and `trace=` public APIs stable.
- Cost control: run the LangSmith smoke check before any live model eval.

---

## 5. High-Level Design

The change will use a two-stage verification flow. First, `vidbyte-evals` loads local env values and runs a LangSmith-only smoke check against the SDK tracer. This confirms that credentials, endpoint, project, create-run, and update-run all work without calling xAI or Gemini. Second, MBPP runs one small baseline eval with the same tracer and model provider configuration.

The likely SDK change is to turn `LangSmithTracer` from a completely silent adapter into a best-effort adapter with inspectable diagnostics and optional strict behavior. The adapter will still swallow delivery exceptions during normal agent execution, but it will record the last failure in safe metadata and let verification code force those failures to surface.

```text
vidbyte-evals/.env
  -> eval env loader
  -> MBPPEval._init_tracer()
  -> vidbyte-sdk LangSmithTracer(endpoint, project, diagnostics)
  -> BaseAgent.generate_reply()
  -> AgentRuntime llm/tool spans
  -> LangSmith project
```

---

## 6. Detailed Design

### 6.1 Eval `.env` Loader

**File(s):** `lib/env_loader.py`, `evals/mbpp/base_agent_execution_grader.py`
**Type:** New file, Modified

#### What it does

Loads `vidbyte-evals/.env` into `os.environ` before eval code resolves LangSmith and model provider keys.

#### Interface / API

```python
class EnvLoader:
    def __init__(self, path: str | Path) -> None: ...
    def load(self, *, override: bool = False) -> dict[str, str]: ...
```

#### Logic / Algorithm

1. `MBPPEval.__init__()` calls `EnvLoader(repo_root / ".env").load()` before `self._init_tracer()`.
2. The loader ignores blank lines and `#` comments.
3. The loader parses `KEY=value`, trims whitespace, strips matching single or double quotes, and leaves internal characters unchanged.
4. Existing environment variables win when `override=False`.
5. The loader returns the keys loaded for tests without printing values.
6. Eval scripts accept `VIDBYTE_SDK_PATH` as an explicit SDK checkout override so the eval worktree can run against the paired SDK worktree instead of the original sibling checkout.

#### Edge Cases & Error Handling

- Missing `.env` returns `{}` and does not raise.
- Malformed non-comment lines raise `ValueError` in tests and local runs.
- Empty values are loaded as empty strings only if the key does not already exist.
- UTF-8 BOM-prefixed files written by Windows PowerShell are accepted by stripping `\ufeff` from the first parsed key.

### 6.2 MBPP Provider Configuration

**File(s):** `evals/mbpp/config.yaml`, `scripts/test_mbpp_eval_runs.py`
**Type:** Modified

#### What it does

Aligns the live MBPP run with the API key available for diagnosis.

#### Interface / API

```yaml
defaults:
  provider: xai
  model: grok-4-fast-non-reasoning
  api_key_env: XAI_API_KEY
```

#### Logic / Algorithm

1. Set MBPP defaults to xAI if using the user-provided xAI key.
2. Update tests that currently accept both Gemini and xAI to assert the intended provider.
3. Update helper functions in `scripts/test_mbpp_eval_runs.py` to set and restore the configured provider key.

#### Edge Cases & Error Handling

- If the user prefers Gemini, this section will be skipped and a Gemini key must be supplied locally.
- Missing provider key must fail before downloading/running the benchmark.

### 6.3 LangSmith Tracer Endpoint and Diagnostics

**File(s):** `vidbyte-sdk/vidbyte/providers/tracing/langsmith.py`
**Type:** Modified

#### What it does

Adds endpoint support and safe delivery diagnostics to the SDK LangSmith adapter.

#### Interface / API

```python
class LangSmithTracer(TracerBase):
    def __init__(self, *, api_key: str | None = None, project: str | None = None, endpoint: str | None = None, strict: bool = False) -> None: ...
    @property
    def last_error(self) -> Exception | None: ...
```

#### Logic / Algorithm

1. Resolve `api_key` from argument or `LANGSMITH_API_KEY`.
2. Resolve `project` from argument or `LANGSMITH_PROJECT`, defaulting to `"default"`.
3. Resolve `endpoint` from argument or `LANGSMITH_ENDPOINT`, defaulting to the LangSmith client default.
4. Construct `langsmith.Client(api_key=..., api_url=endpoint)` when an endpoint is present.
5. Wrap `create_run` and `update_run` calls in a helper that records a sanitized `last_error`.
6. If `strict=True`, re-raise delivery failures as `TracerConfigurationError` or the original safe exception wrapper.
7. Keep non-strict mode best-effort for normal SDK usage.

#### Edge Cases & Error Handling

- Unsupported installed `langsmith.Client` signature: fall back to `api_url` only when accepted or raise in strict mode.
- Bad endpoint/auth/payload: strict smoke script fails; normal runs continue and expose `last_error`.
- Error strings must not include API keys.

### 6.4 LangSmith Live Smoke Script

**File(s):** `vidbyte-sdk/scripts/test-langsmith-tracing-live.py`
**Type:** New file

#### What it does

Creates and closes a single LangSmith root trace in strict mode and prints a clear PASS/FAIL result.

#### Interface / API

```powershell
python scripts/test-langsmith-tracing-live.py
```

#### Logic / Algorithm

1. Instantiate `LangSmithTracer(strict=True)`.
2. Call `start_trace("vidbyte.langsmith.smoke", smoke=True)`.
3. Call `start_span("llm.call", parent=root, provider="smoke", iteration=0)` and `end_span(...)`.
4. Call `end_trace(root, output="ok")`.
5. Print project and endpoint, with no key values.
6. Exit non-zero on any failure.

#### Edge Cases & Error Handling

- Missing env vars fail before network.
- Auth/endpoint errors fail with sanitized message.
- Successful create but failed update fails the script.

### 6.5 SDK Async HTTP Transport Compatibility

**File(s):** `vidbyte-sdk/vidbyte/lib/http/transport.py`, `scripts/test-async-http-transport.py`
**Type:** Modified

#### What it does

Fixes live provider calls under installed `httpx` versions where `AsyncClient.send()` rejects a per-call `timeout=` keyword.

#### Interface / API

```python
class HttpTransport:
    async def request(...) -> HttpResponse: ...
    async def _send_once(...) -> HttpResponse: ...
```

#### Logic / Algorithm

1. Construct `httpx.AsyncClient(timeout=timeout_seconds)` in `request()`.
2. Build the request as before.
3. Call `client.send(request)` without a per-call timeout keyword.
4. Preserve existing retry and response normalization behavior.

#### Edge Cases & Error Handling

- `httpx.RequestError` is still wrapped as `ProviderRequestError`.
- Non-2xx HTTP responses are still returned to provider parsers rather than raised by transport.

### 6.6 Eval Verification Script

**File(s):** `vidbyte-evals/scripts/test-langsmith-eval-env.py`, `scripts/test_mbpp_eval_runs.py`
**Type:** New file, Modified

#### What it does

Verifies env loading and MBPP tracer construction without live model calls.

#### Interface / API

```powershell
python scripts/test-langsmith-eval-env.py
python scripts/test_mbpp_eval_runs.py
```

#### Logic / Algorithm

1. Create temporary `.env` content under a temp directory for parser tests.
2. Confirm quoted `LANGSMITH_PROJECT="vidbyte-sdk"` parses to `vidbyte-sdk`.
3. Confirm existing OS env wins over `.env` values.
4. Mock `langsmith.Client` and instantiate `MBPPEval`.
5. Assert tracer project and endpoint are wired.

#### Edge Cases & Error Handling

- Empty `.env`, missing `.env`, comments, quoted values, and malformed lines are covered.
- Tests must not call LangSmith or xAI.

### 6.7 HuggingFace Dataset Import Isolation

**File(s):** `vidbyte-evals/datasets/hf/base_loader.py`, `scripts/test_mbpp_eval_runs.py`
**Type:** Modified

#### What it does

Prevents the repo-local `datasets/` package from shadowing HuggingFace's external `datasets` package during live eval runs.

#### Interface / API

```python
class HFLoader:
    def _load_huggingface_dataset_fn(self) -> Any: ...
```

#### Logic / Algorithm

1. Temporarily remove the eval repo root from `sys.path`.
2. Temporarily remove the repo-local `datasets` root module from `sys.modules` when it points under this repo.
3. Import external `datasets` and return `load_dataset`.
4. Restore `sys.path` and the repo-local `datasets` module after resolving the function.

#### Edge Cases & Error Handling

- If HuggingFace `datasets` is missing, the original import error still surfaces clearly.
- Local `datasets.hf.*` modules remain usable after the temporary import isolation.

---

## 7. Data Model Changes

N/A - no database schema or persisted SDK data model changes. Existing eval result SQLite files remain generated artifacts.

---

## 8. API Changes

N/A - no HTTP API endpoints. The Python SDK constructor for `LangSmithTracer` gains optional `endpoint` and `strict` keyword arguments while preserving existing `api_key` and `project` behavior.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte-evals/docs/design/langsmith-tracing-live-diagnosis.md` | Cross-repo design doc for eval-side work |
| CREATE | `vidbyte-sdk/docs/design/langsmith-tracing-live-diagnosis.md` | Companion cross-repo design doc for SDK-side work |
| CREATE | `vidbyte-evals/lib/env_loader.py` | Local ignored `.env` parsing before eval setup |
| MODIFY | `vidbyte-evals/evals/mbpp/base_agent_execution_grader.py` | Load `.env` before tracer/model key resolution |
| MODIFY | `vidbyte-evals/datasets/hf/base_loader.py` | Avoid local `datasets/` shadowing HuggingFace `datasets.load_dataset` |
| MODIFY | `vidbyte-evals/evals/mbpp/config.yaml` | Align MBPP provider defaults with available xAI credential if approved |
| MODIFY | `vidbyte-evals/scripts/test_mbpp_eval_runs.py` | Assert env loading and intended provider/tracer wiring |
| CREATE | `vidbyte-evals/scripts/test-langsmith-eval-env.py` | Verification script for eval env loading and tracer setup |
| MODIFY | `vidbyte-sdk/vidbyte/providers/tracing/langsmith.py` | Add endpoint support, strict mode, and safe diagnostics |
| MODIFY | `vidbyte-sdk/vidbyte/lib/http/transport.py` | Move async timeout configuration from `send()` to `AsyncClient` |
| MODIFY | `vidbyte-sdk/tests/test_tracing.py` | Unit tests for endpoint, strict mode, and safe error recording |
| CREATE | `vidbyte-sdk/scripts/test-langsmith-tracing-live.py` | Live LangSmith adapter smoke verification |
| MODIFY | `vidbyte-sdk/scripts/test-async-http-transport.py` | Regression check for `AsyncClient.send()` timeout compatibility |

---

## 10. Testing Plan

### Unit Tests

- `[Edge Case] EnvLoader missing .env returns empty mapping`
- `[Edge Case] EnvLoader parses quoted LANGSMITH_PROJECT without quotes`
- `[Hidden Failure] EnvLoader rejects malformed non-comment lines`
- `[Hidden Assumption] EnvLoader does not override existing OS env by default`
- `[Silent Failure] MBPPEval loads .env before initializing LangSmithTracer`
- `[Hidden Assumption] MBPP config uses the provider matching the configured API key env`
- `[Silent Failure] MBPP primary and subagents share the same tracer instance`
- `[Edge Case] LangSmithTracer omits api_url when no endpoint is configured`
- `[Edge Case] LangSmithTracer passes LANGSMITH_ENDPOINT to Client when configured`
- `[Hidden Failure] LangSmithTracer strict mode raises on create_run failure`
- `[Hidden Failure] LangSmithTracer strict mode raises on update_run failure`
- `[Silent Failure] LangSmithTracer non-strict mode records last_error on delivery failure`
- `[Hidden Assumption] LangSmithTracer diagnostics redact key-like values`

### Integration Tests

- `[Integration] Run vidbyte-evals/scripts/test-langsmith-eval-env.py with mocked langsmith.Client and temporary .env`
- `[Integration] Run vidbyte-sdk/scripts/test-langsmith-tracing-live.py with real LangSmith credentials after approval`
- `[Integration] Run one MBPP baseline eval with `n_cases=1` or the smallest practical case count after the LangSmith smoke check passes`

### Manual / QA Test Cases

1. `[Hidden Assumption]` Given the ignored local `.env` contains LangSmith and provider keys, when `python evals/mbpp/base_agent_execution_grader.py` starts, then it reports tracer initialization without printing secrets.
2. `[Silent Failure]` Given the smoke script passes, when the user opens the `vidbyte-sdk` project in LangSmith, then `vidbyte.langsmith.smoke` appears.
3. `[Silent Failure]` Given the MBPP baseline run completes, when the user opens the configured LangSmith project, then at least one `agent.run` trace appears with child `llm.call` spans.
4. `[Hidden Failure]` Given an invalid LangSmith endpoint, when the smoke script runs, then it fails before any model-provider eval runs.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `langsmith` | Existing eval dependency | Send traces to LangSmith | Client API signature may differ by installed version |
| LangSmith API | `LANGSMITH_ENDPOINT` or client default | Trace storage and UI visibility | Auth/project/endpoint failures can be silent without strict smoke |
| xAI API | `https://api.x.ai/v1` via SDK registry | Live MBPP model calls if xAI config is approved | Cost, rate limits, model availability |
| HuggingFace datasets | `datasets` package | MBPP case loading | Network/cache availability |

---

## 12. Rollout & Deployment

- Create isolated worktrees for both repos only after explicit approval.
- Commit design docs first in each repo worktree.
- Implement SDK tracer diagnostics and tests before running live evals.
- Add local `.env` only in `vidbyte-evals`; do not commit it.
- Run no-network verification scripts.
- Run LangSmith smoke script.
- Run a minimal MBPP baseline eval.
- Open draft PRs only for repos with committed changes.
- Rollback: remove the eval env loader and script; revert SDK `LangSmithTracer` changes. Local `.env` can be deleted without repository impact.

---

## 13. Open Questions

- [ ] Should MBPP be switched from Gemini back to xAI for this diagnosis, since the provided model key is xAI?
- [ ] Should `LangSmithTracer(strict=True)` raise the original LangSmith exception or wrap it in `TracerConfigurationError` with sanitized details?
- [ ] Should the live smoke script live permanently in `scripts/`, or should it be a temporary diagnostic script removed before PR?
- [ ] Which LangSmith UI URL should be printed after a successful smoke run, if the client exposes a run URL?

---

## 14. Alternatives Considered

### Alternative 1: Only run the eval with environment variables set in PowerShell

- What: Skip repo changes and set `$env:*` values directly before running MBPP.
- Why rejected: This does not fix silent LangSmith delivery failures and does not create a repeatable verification path.

### Alternative 2: Add `python-dotenv`

- What: Add a new dependency and call `load_dotenv()`.
- Why rejected: The needed parsing is small, and avoiding a new dependency matches the eval repo's existing lightweight helper style.

### Alternative 3: Make every LangSmith delivery failure raise by default

- What: Remove best-effort behavior and fail agent runs when tracing fails.
- Why rejected: The existing tracing design explicitly keeps provider tracing non-fatal. Strict mode gives diagnostics without breaking normal use.

