# Code map: agent output connectors (S0 scout, 2026-10-11)

Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-output-connectors` (no commits on the branch yet). All paths below are relative to that root. Line numbers are from this session's reads. "unverified" marks anything not opened in this session.

## 1. Rules, commands, and conventions from AGENTS.md that bind this change

### AGENTS.md rules (heading, then a short quote)

- **Repository Map.** Read `REPO_MAP.md` "before you create a file, move code, or search for where something lives, and put new code where it says that kind of code belongs." Read each folder `README.md` "to the end before you change anything inside the folder". Its `## Notes for agents` section records past review findings. "lint rule A009 keeps every folder README at or under 40,000 characters".
- **Repository Map, `docs/` rule.** "Do not grep, glob, or read files under `docs/` as part of ordinary work".
- **Repository Map, gate rule.** "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- **Placement Rules enforcement.** "binding for all new code, and the `AGENTS.md placement` workflow enforces it on every pull request". The workflow file `.github/workflows/agents-md-placement.yml` exists.
- **Style 1, Keep Call Chains One Level Deep.** "a function may call another of its own functions, but that second function should not call a third". No nested functions "unless an API requires a callback or a decorator".
- **Style 2, Narrate Main Functions in Plain English.** Put plain-English step comments throughout the main function's body. Update them in the same edit whenever the steps change.
- **Style 3, Build in Layers of Small, Single-Purpose Classes.**
  - "nothing in `vidbyte/lib/` may import from a layer above it"
  - "no two modules depend on each other in a cycle"
  - "Keep files well below 1,000 lines"
  - "If describing the job of a function or a class needs the word 'and', it is probably two"
- **Style 4, Use Validated Dataclasses for Core Inputs and Outputs.**
  - Core functions take a dataclass and return a dataclass.
  - Validate in `__post_init__` "and raises a clear error that names the field and the bad value".
  - "Prefer `@dataclass(frozen=True, slots=True)`".
  - "type any field whose value comes from a small, closed set as an enum".
- **Placement Rules, dataclasses.** "Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`". "Do not create `types.py`, `records.py`, `models.py`, or `schemas.py`". A feature package may re-export from its own `__init__.py`. "If a dataclass seems to need a type from a higher layer, move the contract down (a `Protocol` or a smaller record in `vidbyte/lib/`)". There are two exceptions:
  - Agent `*Settings` classes go in `vidbyte/agents/settings/` or the agent's own `settings.py`.
  - JEV preflight questions have their own home.
- **Placement Rules, enums.** "Every new enum ... is defined in `vidbyte/lib/enums/<domain>.py`, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
- **New JEV code.** "**A new JevAgent capability** is a named, validated field on `JevAgentSettings`." A JEV constant goes in `vidbyte/lib/constants/jev.py`. "Never create a `types.py`, `enums.py`, or `constants.py` under `vidbyte/agents/jev/`".
- **Existing code.** Modules that predate the rules are "not precedent". "Moving it to `vidbyte/lib/` is a change of its own".
- **CLAUDE.md** contains only `@AGENTS.md`.

### REPO_MAP.md entries that bind this change

- **`vidbyte/providers/`**: "Provider adapter factories covering text, image, video, audio, embeddings, and streaming ... This is the folder to extend when adding support for a new model vendor."
- **`vidbyte/lib/http/`**: "Nothing else in the package should reach for an HTTP client directly outside of this layer."
- **`vidbyte/lib/providers/`** holds database persistence providers. Its name collides with `vidbyte/providers/`.
- **`vidbyte/agents/settings/`**: "A new configurable behavior for agents should be added as a setting here rather than as another constructor parameter."
- **`vidbyte/config/`**: "Understanding this folder is worthwhile before adding any new configurable field to an agent."
- **`vidbyte/lib/errors/`**: "A new failure mode should usually reuse an existing error type."
- **`vidbyte/sources/`** is the inbound artifact-to-context layer. It has no README.

### Commands (verified in `scripts/run_ci.py`, `lint/README.md`, `pyproject.toml`, `.github/workflows/*.yml`, and the field guide)

**Install, once:** `python -m pip install -e ".[dev]"`. `ci.yml` runs `pip install -e ".[dev]"`. The dev extras are build, mypy 2.3.1, pytest 8.3.5, pytest-asyncio 1.3.0, ruff 0.16.4, and twine.

**Lint:**
- `python lint/run.py` runs the ratchet against `lint/baseline.json`.
- `python lint/run.py --rule S012` runs one rule.
- `python lint/run.py --rule S012 --all` lists every finding.
- `python lint/run.py --format json` gives JSON output.
- The last line of the output is `SDK-LINT: PASS` or `SDK-LINT: FAIL` (`lint/core/report.py:58`).
- A rule passes as CLEAN, RATCHETED, or IMPROVED. It fails as REGRESSED or ERRORED (`lint/core/baseline.py:22`, `lint/core/runner.py:37`).
- `--rule X --update-baseline` is only for a real improvement. Never raise a baseline.

**Import order (S051):** `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` (field guide `local-ci-verification.md`).

**Tests:**
- One file: `PYTHONPATH=$(pwd) python -m pytest -q tests/test_agent_base.py`.
- One area: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent`.
- Everything: `python -m pytest`, configured by `pyproject.toml` with testpaths `tests` and `--strict-config --strict-markers`.

**Full gate:** `python scripts/run_ci.py`. Its `--stage` choices are all (the default), source, and package.
- **Source stage:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`. It runs these steps:
  - the no-tracked-bytecode check
  - `lint/run.py`
  - `compileall -q vidbyte`
  - `scripts/check_context_write_paths.py`
  - `scripts/check_context_primitive_introductions.py`
  - `scripts/check_reasoning_trace_contracts.py`
  - the full pytest suite
- **Package stage:** `python scripts/run_ci.py --stage package` with PYTHONPATH unset. It runs these steps:
  - build
  - twine check
  - wheel inspection
  - a clean venv install
  - pip check
  - a smoke test, which pops PYTHONPATH itself

**Public API contract (C016):**
- Check: `python scripts/generate-sdk-public-api.py --check`.
- Regenerate: `python scripts/generate-sdk-public-api.py`.
- The generator "refuses to write while `vidbyte/__init__.py` or `pyproject.toml` has uncommitted changes". The order is: commit the root `__init__` change, then regenerate, then commit `contracts/sdk-public-api.json`.
- The contract records the sorted `vidbyte.__all__`, the distribution name, the version, and `source.commit`.

**Semgrep** is NOT run by `run_ci.py`. It lives in `.github/workflows/static-policy.yml`:
- `pip install semgrep==1.170.1`
- `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`
- `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`

Semgrep scans tracked files only, so run `git add -A` first (field guide). The user's memory notes say Semgrep needs its own venv or pipx; this was not re-verified this session.

**Lint discovery uses `git ls-files`** (`lint/core/discovery.py`). A new untracked file is invisible to lint until it is staged. `python_files()` covers `vidbyte/` only. `all_python_files()` covers every tracked `.py` file, so A001 also checks tests, scripts, and lint files.

**CI workflows are `workflow_dispatch` only.** Auto-triggers are disabled.

### Lint rules most likely to fire on new code here (baseline count; any increase means REGRESSED)

- **A001 (643).** Every tracked `.py` file, tests included, needs a module docstring with non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, and `TESTS:` (`lint/rules/a001_agent_readable_file_headers.py:24-32`).
  - The "Context Protocol Header / Description: / Purpose:" style used by `base.py`, `audit.py`, `brave.py`, and `_base.py` does NOT satisfy it.
  - `vidbyte/agents/coding.py`, `vidbyte/agents/jev/agent.py`, `vidbyte/lib/enums/__init__.py`, and `tests/features/coding_agent/conftest.py` do satisfy it.
- **A002 (703).** Applies to `vidbyte/` functions whose identifiers contain retry, backoff, attempt, permission, authorize, secret, redact, persist, fallback, transport, request, fetch, send, provider, and similar words. Such a function needs `# @intent <name>` within 4 lines before or 20 lines after its `def`.
- **A003 (36).** Applies to `*Error` classes in `vidbyte/lib/errors/`. Each needs a literal `DIAGNOSTIC_FIELDS` tuple of all 8 fields, exposed as attributes or in details. Full examples: `ReasoningTraceArgumentError`, `CodexAgentError`, `FailureRaisedError`, `AgentSpeedError`, and `UsageAccountingError` in `vidbyte/lib/errors/base.py`.
- **A005 (33).** A parameter named transport, runner, store, client, tracer, or fetcher must not be annotated `object` or `Any`.
- **A006 (34), layering and cycles.**
  - `LOWER_LAYER_PREFIXES` are `vidbyte.lib`, `vidbyte.providers`, `vidbyte.sessions`, and `vidbyte.sources`.
  - These must not import `ORCHESTRATION_PREFIXES` (vidbyte.agents, context, middleware, tools, pipelines, workflows, harnesses, trace, evals, paradigms) or `APPLICATION_PREFIXES` (vidbyte.client, config, cli, mcp_server).
  - Function-local imports count. Only `TYPE_CHECKING` imports are skipped. `__init__.py` files are excluded from the graph.
- **A007 (255).** Numeric literals near names containing timeout, retry, attempt, backoff, delay, byte, limit, status, or interval, and literals inside sleep, send, or request calls, must be UPPERCASE named constants. Operational parameter defaults count too.
- **A008 (3).** No `print()` outside `vidbyte/cli/`.
- **A009 (0).** A README may be at most 40,000 characters.
- **C011 (2).** A public class ending in Agent, Runner, Harness, Session, or Machine must pair `arun` with `run`.
- **C015 (3).** Package-data coverage. `pyproject.toml` package-data lists only prompts and paradigms.
- **C016 (0).** `contracts/sdk-public-api.json` must equal the generator output.
- **S011 (0).** Raw `httpx`, `requests`, `http.client`, or `urllib.request` imports are allowed only in `vidbyte/lib/http/transport.py` and `vidbyte/tools/mcp/transport.py`. `smtplib` is not on that list.
- **S012 (0).** Any call named request, request_bytes, stream_request, upload_multipart, or urlopen must pass `timeout=` or `timeout_seconds=`. The field guide adds that S012 flags any helper named `request`.
- **S013 (4).** `max_response_bytes` is required only under `tools/builtins/{code_search,mcp,operations}` and `tools/mcp`.
- **S015 (13).** `__all__` integrity. The root must list every public name it imports.
- **S016 (50).** No builtin raises (Exception, RuntimeError, TypeError, ValueError) in `vidbyte/providers/`, `tools/mcp/`, `tools/builtins/`, `lib/runners/`, or `cli/`.
- **S017 (79).** No `str(exc)` or f-string exception text in Error constructors or returns in `providers/`, `tools/`, `mcp_server/`, or `lib/runners/`.
- **S019 (5).** An async handler that catches BaseException, CancelledError, or uses a bare except must re-raise.
- **S024 (25).** Control-flow nesting may go at most 3 deep.
- **S046 (0) and S052 (0).** Ruff ASYNC rules flag blocking IO inside async code.
- **S063 (4).** The results of `gather(return_exceptions=True)` must be checked against BaseException.
- **S064 (4).** A retry loop that sleeps needs one overall deadline.
- **S008 (19).** C901, PLR0912, and PLR0915 complexity limits.
- **Semgrep `no-untyped-mapping-fallback`.** It matches a function with an `object` or `Any` parameter that does `if not isinstance(x, Mapping|dict): return ...`. It excludes `vidbyte/lib/http`, `vidbyte/providers`, `vidbyte/mcp_server`, and `vidbyte/tools/mcp`.

### PR and commit conventions

AGENTS.md states none. The only ordering constraint found is the contract regeneration order described above.

## 2. Files this change will touch

### New package (does not exist)

**`vidbyte/agents/output/`**
- **Today:** absent (`ls` reports "No such file or directory"). `vidbyte/outputs/` is absent too.
- **Change:** the new abstraction package, by user decision.
- **Pattern for a user-built class configured by keyword arguments:** `vidbyte/middleware/builtins/audit.py`, where `AuditLogMiddleware(sink, *, hooks=None)` validates in `__init__` under `# @intent name-lists-reject-bare-strings`. That file predates the rules: it raises `ValueError` and uses the "Context Protocol Header" style.
- No README exists in `vidbyte/middleware/builtins/` or `vidbyte/sources/`.

### Agent classes

**`vidbyte/agents/base.py`** (1694 lines, already above "well below 1,000")
- **Today:** `class BaseAgent(McpAttachableMixin)`. `__init__` (81–115) is keyword-only:
  `name, system_prompt, runtime, tools, permission_policy, agent_loop_settings, max_tool_rounds, max_iterations, max_tokens, compaction_trigger_tokens, compaction_target_tokens, middleware, api_key, provider, model_name, temperature, timeout_seconds, run_id, description, capabilities, agent_metadata, context_items, context_manager, algorithm, metadata, tracer, trace, output_schema, handoff, trace_option, fallback`
- Non-linear runtimes (MCTS_SEARCH and the ACTOR_MODEL variants) reject middleware, trace_option, algorithm, fallback, and output_schema at lines 128–162. `_LINEAR_LOOP_RUNTIMES = frozenset({LINEAR, JEV})` is at line 75.
- **Attribute storage:**
  - `self.middleware = tuple(middleware)` at 231
  - `self.output_schema` at 246
  - `self._handoff_spec = handoff` at 253
  - `self._trace_option` at 259
  - `self.last_reply` at 262
  - `self._active_session` at 269
  - pending prompts and contextvars at 272–275
- **Reply path** (every reply passes through here):
  - `generate_reply` (784–809) claims the queue and opens a usage-ledger scope.
  - `_generate_reply` starts at 821. Its try block runs from 832 to 895. Its `except Exception` wraps errors in `AgentExecutionError`, except `UsageAccountingError` and `FailureRaisedError`.
  - **Post-try steps:**
    - 896: `self._active_prompt = ""`
    - 897–904: `metadata = {strategy, runner_type, provider, model_name, **dict(input_metadata), **dict(result.metadata)}`
    - 905–906: `metadata["structured"]`
    - 907–913: `reply = AgentMessage(sender, recipient, content=result.output, metadata=metadata, structured=result.structured)`
    - 914: `self.history.append(reply)`
    - 915–916: set `last_prompt` and `last_reply`
    - 917–919: `last_trace`
    - 920–927: `if self._handoff_spec is not None: try: await self._run_auto_handoff(metadata) except BaseException: self._queued_prompts.clear(); raise` (under `# @intent failed-run-leaves-no-queued-prompts`)
    - 928: `self._notify_session(reply)`
    - 931: `self._assert_schema_satisfied(result)`
    - 932–933: `if self._queued_prompts and not self._draining_queued_prompts: await self._drain_queued_prompts(metadata)`
    - 934: `return reply`
  - **Helpers on the path:**
    - `_close_failed_reply` (936–945)
    - `_assert_schema_satisfied` (947–963): raises `OutputSchemaViolationError` after `_notify_session_exception`, with intent "raise-after-the-turn-is-recorded".
    - `_notify_session_exception` (965–972)
    - `_notify_session` (491–503): calls `session.record_turn(reply)` and stores a session error in `metadata["__session_error__"]`.
    - `_drain_queued_prompts` (1073–1107): calls `self.generate_reply(prompt)` with draining=True, so drained replies take the same path.
    - `_run_auto_handoff` (1136–1148): `produced = await HandoffAgent.run_auto_handoff(...)`, `self.record_handoff(produced)`, `metadata["handoff"] = produced`. On error it sets `metadata["handoff_error"] = repr(exc)` and calls `_notify_session_exception`.
  - **Entry points:** `arun` (985–987), `run` (994–1001; `asyncio.run(...)`, and it raises `AgentExecutionError` inside a running loop), `arun_sequentially` (1034–1044), and `run_sequentially` (1046–1052) all call `generate_reply`.
- **State and composition:**
  - `as_tool()` (352–371) returns `AgentTool(self)`.
  - `fork()` (508–512) delegates to `AgentForker.fork`.
  - `export_state()` (514–541) builds `RunState` field by field.
  - `restore(cls, state, *, tools=(), middleware=(), tracer=None, trace=None, output_schema=None)` (543–575) calls `cls(...)` with explicit keywords.
  - `_export_output_schema` (686–692) and `_restore_output_schema` (726–736).
  - `_runtime()` (1285–1331), `_runtime_extension_kwargs` (1333–1335), `_runtime_middleware` (1337–1351, lazy import of middleware builtins), and `_output_contract_with_schema` (1353–1361).
- **Change:** a new keyword parameter, its stored attribute, and a call in the reply path.
- **Pattern to follow:** `output_schema` and `handoff`. Each is a keyword in `__init__` stored on `self`, passed by `fork.py`, and accepted or ignored by `restore()`. The handoff block at 920–927 shows the post-reply side effect, with metadata written onto the already-built reply and queued prompts cleared on failure.
- **Header:** "Context Protocol Header" style, which does not satisfy A001.

**`vidbyte/agents/fork.py`** (228 lines)
- **Today:** `AgentForker.fork` (53–81) calls `BaseAgent(...)` with an explicit keyword list: name, runtime, tools, permission_policy, agent_loop_settings, middleware (line 59), system_prompt, api_key, provider, model_name, temperature, timeout_seconds, run_id, description, capabilities, agent_metadata, context_items, context_manager, algorithm, metadata, tracer, output_schema (line 76), handoff (line 77), trace_option, and fallback.
- It always builds a plain `BaseAgent`, never the subclass. `_copy_run_state` (215–225) copies history and, under `include_run_state`, handoffs and `_tool_call_contexts`.
- **Change:** whether outputs are carried is decided by passing or omitting a keyword here.
- **Settings record:** `AgentForkSettings` (`vidbyte/lib/dataclasses/agents.py:306-362`) has no outputs field.

**`vidbyte/agents/jev/agent.py`** (128 lines)
- **Today:** `class JevAgent(BaseAgent)` with `__init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings | None = None)` (line 35).
- `super().__init__` (90–102) passes only name, system_prompt, `runtime=AgentRuntimeType.JEV`, tools, permission_policy, `agent_loop_settings=settings.loop`, api_key, provider, model_name, temperature, and timeout_seconds.
- The ARCHITECTURE NOTE says "callers cannot replace its runtime or pass arbitrary BaseAgent customization kwargs."
- The fresh-continuation factory (62–76) is `partial(BaseAgent, ...)`. `_require_metered_specialists` (110) requires `type(agent).generate_reply is BaseAgent.generate_reply`. `_runtime_extension_kwargs` is at 123–125.
- It overrides no reply-path method. It defines only `__init__`, `response`, `_require_metered_specialists`, and `_runtime_extension_kwargs`.
- **Change:** wire the new capability through.
- **Pattern:** a field on `JevAgentSettings`, passed into `super().__init__`, per AGENTS.md "New JEV code".

**`vidbyte/agents/jev/settings.py`** (387 lines)
- **Today:** `@dataclass(frozen=True, slots=True) class JevAgentSettings` (121–214). Its fields are name, system_prompt, provider, model_name, `api_key: str | None = field(default=None, repr=False)`, temperature, timeout_seconds, tools, permission_policy, `loop`, `agents`, `bulk_work`, and `alignment`.
- `__post_init__` carries `# @intent opinionated-settings-fail-before-runtime` and raises `ConfigurationError`. `__all__` is at 387.
- It lives in the agents layer and imports `vidbyte.agents.settings` and `vidbyte.tools.security`.
- **Change:** a named, validated field.
- **Pattern:** `api_key` uses `field(default=None, repr=False)` for secret masking. Tuple fields such as `tools` and `agents` show the tuple pattern.

**`vidbyte/agents/coding.py`** (78 lines)
- **Today:** `class CodingAgent(BaseAgent)`. Its signature is `__init__(self, *, root_dir, firecrawl_api_key=None, browserbase_api_key=None, parallel_api_key=None, tavily_api_key=None, tools=(), permission_policy=None, **kwargs)`.
- It builds `CodingAgentSettings` (from `vidbyte/lib/dataclasses/coding.py`) and `CodingAgentTools`, then calls `super().__init__(tools=(...), permission_policy=..., **kwargs)`. Its header says it "takes every BaseAgent keyword unchanged".
- It overrides no BaseAgent method. Its `fork()` returns a plain BaseAgent, and `restore()` raises `TypeError`.
- **Change:** none is required for a new BaseAgent keyword to reach it, because `**kwargs` passes it through. This header is the A001-compliant example.

**`vidbyte/agents/codex/agent.py`** (lines 1–260 read)
- **Today:** `class CodexHarnessAgent:` is not a BaseAgent. Its signature is `__init__(self, settings: CodexHarnessAgentSettings)`.
- `arun(request: CodexAgentInput) -> AgentMessage` (100–178) builds its own reply, uses `replace()` for middleware metadata, and appends it to history.
- It has its own `generate_reply` and `run` (197–209).
- **Change:** open question (see §4).

**`vidbyte/tools/agent_tool.py`** (100 lines)
- **Today:** `AgentTool.execute` does `child = self._agent.fork()` at line 59, then `reply = await child.generate_reply(serialized)`. It catches `Exception` and returns `ToolResult.error(self._name, str(exc), ...)`. It has no A001 header.
- **Change:** possibly none. It sets how `as_tool` behaves under any fork rule.

### Records, enums, constants, errors (Placement Rules)

**`vidbyte/lib/dataclasses/<domain>.py`**
- **Today:** 36 domain modules exist: agents, coding, config, jev, middleware, operations, sessions, sources, tools, and others. No output or delivery module exists.
- **Change:** new records.
- **Patterns** in `vidbyte/lib/dataclasses/agents.py` (362 lines):
  - `PauseDuration` shows `__post_init__` validation.
  - `FallbackModel` has a masked `__repr__` (`api_key='***'`).
  - Agents-layer types are imported only under `TYPE_CHECKING`.

**`vidbyte/lib/dataclasses/agents.py`**
- **Today:**
  - `AgentMessage` (268–280): `sender, recipient, content, message_type="response", metadata: Mapping = field(default_factory=dict), structured: Any = None, codex: CodexMessageData | None = None`. It is frozen, but `metadata` is the mutable dict that `_generate_reply` built.
  - `AgentStopReason(str, Enum)` (51–70) includes `MIDDLEWARE_ABORT = "middleware_abort"`. It predates the enum placement rule.
- **Change:** likely read-only reference. `vidbyte/agents/types.py` re-exports `AgentMessage` and others from lib.

**`vidbyte/lib/enums/<domain>.py` and `vidbyte/lib/enums/__init__.py`**
- **Today:** 20 domain modules. `__init__` has an A001 header and states "Update the sibling enum and this export list together".
- **Change:** a new enum for any closed set.

**`vidbyte/lib/constants/<domain>.py`**
- **Today:** `codex.py`, `cot_events.py`, `failure.py`, `jev.py`, `reasoning_strategies.py`, `runners.py`, `speed.py`, and `trace.py`.
- **Change:** named constants for timeouts and status codes, to satisfy A007. The field guide `strict-config-dataclasses.md` says bounds go in `lib/constants`.

**`vidbyte/lib/errors/base.py`** (503 lines) **and `vidbyte/lib/errors/__init__.py`** (116 lines)
- **Today:**
  - `VidbyteSdkError(message, *, details=None)`.
  - `ConfigurationError` (235) has no custom `__init__`.
  - `ProviderRequestError` (247–259) is `(message, *, provider, status_code=None, response_excerpt=None)`. It stores `response_excerpt[:500]` in details. `ProviderResponseError` has the same shape.
  - `OutputSchemaViolationError(AgentExecutionError)` (167–175) is `(message, *, raw_output, validation_error=None, stop_reason=None)`. It is the sibling for "raise after the turn is recorded".
- The `__init__` instructions say: "Add a new base error to both the import tuple and `__all__` in alphabetical family order." The root `vidbyte/__init__.py` (438–452) imports a subset of errors, including `OutputSchemaViolationError`.
- **Change:** a new error type, if one is introduced. A003 applies to it.

**`vidbyte/lib/registries/models.py`** (354 lines)
- **Today:** `ProviderModelRegistry` has `API_KEY_ENV_VARS` (73–88) and `resolve_api_key` (151–161). The resolution order is: an explicit key that is non-blank after `strip()`, then a non-blank environment variable after `strip()`, then `ConfigurationError(f"Missing API key for provider {p_name}. Pass api_key or set {env_var}.")`.
- **Change:** reference only.

**`vidbyte/lib/util/credential_keys.py`**
- **Today:** `CredentialKeyPolicy.is_secret_key(key)` classifies key names by exact names and by suffixes such as `_token` and `_secret`. It does not resolve credentials. Reference only.

### HTTP and provider-specific clients

**`vidbyte/lib/http/transport.py`** (211 lines, no module docstring)
- **Today:**
  - `HttpTransport.request(*, method, url, headers, json_body=None, timeout_seconds=60.0, retry_count=0, backoff_seconds=0.5, backoff_multiplier=2.0, retry_status_codes=(408,409,425,429,500,502,503,504), max_response_bytes=None, idempotency_key=None, follow_redirects=False) -> HttpResponse` (line 40).
  - The body is JSON only.
  - HTTP error statuses come back as responses. `httpx.RequestError` is wrapped as `ProviderRequestError(..., provider="http", response_excerpt=str(exc))`.
  - `_require_idempotency_guard` (22–25) refuses to retry a non-idempotent call without a key. The key is never sent.
  - `_send_once` (59–73) is the seam tests patch.
  - `HttpResponse(status_code, body, headers, raw_bytes=None, attempts=1)` (28–34).
  - `SyncHttpTransport` adds `request_bytes`, `upload_multipart` (sync only), and `stream_request`.
  - `vidbyte/lib/http/__init__.py` exports `HttpResponse`, `HttpResponseParser`, `HttpTransport`, and `SyncHttpTransport`. `parser.py` has `bearer_headers(api_key)` and `parse_json_response`.
- **Change:** used, not necessarily changed.
- **Importers today:**
  - `vidbyte/lib/runners/*`
  - every `vidbyte/providers/*.py` model adapter
  - `vidbyte/sources/fetches/http.py` (sync)
  - `vidbyte/tools/builtins/mcp/search.py` (sync)
  - `vidbyte/tools/builtins/memory/base.py`
  - `vidbyte/tools/builtins/operations/clients/{_base,brave,browserbase,exa,firecrawl,parallel,tavily}.py`

**`vidbyte/tools/builtins/operations/clients/_base.py`** (133 lines) **and `brave.py`** (88 lines)
- **Today:** the only precedent for non-model, third-party, credentialed HTTP clients.
  - `RetryPolicy` is a local frozen dataclass that predates the rules.
  - `WebOperationClient(api_key, *, provider, base_url, timeout_seconds=15.0, retry=None, max_response_bytes=2_000_000, transport: HttpTransport | None = None)`.
  - `request_json` (71–92) passes `idempotency_key=f"{provider}-{operation}-{uuid4().hex}"` under `# @intent read-only-post-operations-declare-retry-safety`.
  - `_require_ok` (99–102) raises `ProviderRequestError` without echoing the body.
  - `BraveClient._headers()` keeps the key inside the header mapping.
- These live in the tools layer.
- **Pattern** for transport injection and per-call idempotency key: `self._transport = transport or HttpTransport()`.

**`vidbyte/providers/`**
- **Today:** model adapters only.
  - `__init__.py` (the `ModelProviders` factory) eagerly imports every adapter.
  - `base.py` has `tool_spec_to_provider_schema` and imports `vidbyte.tools.types`.
  - Other modules: `client.py`, `anthropic.py`, `compatible.py`, `elevenlabs.py`, `gemini.py`, `openai.py`, `openrouter.py`, `output_schema.py`, `playai.py`, `typesafe.py`, `xai.py`, and `tracing/` (langfuse, langsmith, phoenix).
  - The README is 41,130 characters (a legacy A009 ceiling of 55,000). It has no Notes for agents or File Index section.
  - "Contract Invariants" include: "Transport is injected, never created"; "Missing config raises `ProviderConfigurationError`"; "API keys never appear in a URL".
- **Change:** candidate home for provider-specific logic, per the user's decision. See §4 for layer facts.

### Public exports and contract

- **`vidbyte/agents/__init__.py`** (546 lines). `from vidbyte.agents.coding import CodingAgent` is at line 64, `Agent = BaseAgent` at 291, and `__all__` starts at 293. **Change:** exports, if the package is public.
- **`vidbyte/__init__.py`** (1297 lines). Imports from `vidbyte.agents` start at line 41. `__all__` starts at 690. `__version__ = "0.2.1"`. S015 applies. **Change:** root exports.
- **`contracts/sdk-public-api.json`** and **`scripts/generate-sdk-public-api.py`**. **Change:** regenerate after the root `__all__` changes (C016).

### Documentation

- **`vidbyte/agents/README.md`** (239 lines, 11,329 characters). It has no `## Notes for agents` and no `## File Index`, so S020 does not apply. **Change:** document the new parameter.
- **`REPO_MAP.md`.** A new folder entry, if the map should list `vidbyte/agents/output/`. The field guide `agents-md-map.md` covers regenerating the map; it was not read.

### Read and likely unchanged (record for the spec)

- **`vidbyte/sessions/session.py`.**
  - `Session.arun` (155–166) calls `self._agent.arun`. It calls `notify_exception` on BaseException and re-raises. It calls `record_turn(reply)` only when the agent does not record turns itself.
  - `record_turn` is at 182–188 and `fork` at 190.
  - `fork_from` (304) and line 459 call `BaseAgent.restore(..., tools, middleware, tracer, output_schema)`.
- **`vidbyte/sessions/serialization.py`.**
  - `message_to_dict` (111–120) scrubs metadata.
  - `_safe` (198–215) keeps primitives, Mapping, list, tuple, and pydantic BaseModel. Anything else becomes `{"__dropped__": TypeName}`.
  - `_SECRET_TOKENS = ("API_KEY","TOKEN","SECRET","PASSWORD","CREDENTIAL","AUTH")` is matched as a substring of each key.
- **`vidbyte/lib/dataclasses/sessions.py`.** `RunState` (53–78) has explicit fields only, ending with `output_schema` and `permission_policy`.
- **`vidbyte/agents/runtime.py`** (2100 lines; sections read). Its header says not to add public exports or network clients there.
  - `_finish_result` (838–862) runs `after_run` middleware.
  - `_middleware_abort_result` (1072–1099) produces the abort result.
  - `_runtime_metadata` (1902–1918) has the keys stop_reason, iteration_count, tokens_used, tool_call_count, tool_call_states, tool_calls, and usage_rollup.
  - `_final_result` (1513–1545) fills `structured`.
  - A before_run abort happens at 325–331.
- **`vidbyte/lib/dataclasses/config.py`** (828 lines) **and `vidbyte/config/loader.py`.**
  - `AgentSettings` (313) has `_ALLOWED_FIELDS` (339–345), which rejects unknown keys.
  - `to_agent_kwargs` (412–436) maps to BaseAgent keywords.
  - `loader.py:292` does `BaseAgent(**settings.to_agent_kwargs(...))`.

### Confirmed unrelated

- **`vidbyte/lib/config/mcp_presets.py`.** Its header reads "Defines the canonical catalog of built-in MCP server preset definitions." This is the rejected approach. Only the header was read.

## 3. Tests that cover those files

### Framework and configuration

- pytest 8.3.5 and pytest-asyncio 1.3.0 (`pyproject.toml`). Options are `--strict-config --strict-markers`, `asyncio_default_fixture_loop_scope = "function"`, and testpaths `tests`.
- Async tests use `@pytest.mark.asyncio`. Some use `unittest.IsolatedAsyncioTestCase`.
- There is no `tests/conftest.py`. The only conftest is `tests/features/coding_agent/conftest.py`.
- A001 applies to new test files. `tests/features/coding_agent/conftest.py` shows the accepted header: `FILE:`, `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `FUNCTION INVENTORY:`, `COMMON MODIFICATION PATTERNS:`, `WHAT NOT TO DO IN THIS FILE:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, `TESTS:`.

### Fixtures and helpers

**Agents without a model** (`tests/agent_test_support.py`)
- `build_test_agent(..., runner=FakeRunner)` and `bind_test_runner` write into `agent._runner_cache`.
- `OfflineTestAgent` is also available.
- The file warns: do not monkeypatch `BaseAgent.__init__`.

**Scripted model turns**
- `tests/test_restore_output_schema.py`: the runner's `run(prompt, **kw)` returns an object with `.text` and `.raw` in the OpenAI Responses shape. An `isDone` function_call carries `final_answer`.
- `tests/features/coding_agent/conftest.py`: `ScriptedToolRunner` (chat-completions shape) is exposed through the `script_model` fixture.

**Faking HTTP: three patterns in use**
1. `monkeypatch.setattr(HttpTransport, "_send_once", fake_send)` together with `monkeypatch.setattr(transport_module.asyncio, "sleep", no_sleep)`. Used in `tests/test_web_operation_client_retry.py`, `@pytest.mark.asyncio`.
   - The coding_agent conftest fixture `fake_provider_http` uses the same seam but does not patch sleep. Its header says "responders must use statuses the transport never retries (200, 401)".
2. A `MockTransport` class with `async request(...)`, injected with `tool._transport = transport` (`tests/test_memory_tools.py`).
3. Per-file `FakeTransport` or `ScriptedTransport` classes in `tests/test_jev_agent.py:48`, `tests/test_jev_managed_gateway.py:43`, `tests/test_openrouter_provider.py:40`, and `tests/test_text_model_runner.py`.

### Tests that pin behavior this change touches

- **`tests/test_jev_agent.py:504-509`**, `test_constructor_exposes_only_settings`. It asserts `tuple(inspect.signature(JevAgent.__init__).parameters) == ("self", "settings", "runtime_settings")` and that "middleware" is not among them.
- **`tests/features/coding_agent/test_coding_agent_contract.py`.**
  - `EXPECTED_SIGNATURE` is root_dir, the four API keys, tools, permission_policy, and exactly one `**kwargs`.
  - `PARITY_KEYWORDS` should gain any BaseAgent keyword that `RunState` exports.
  - It asserts that CodingAgent overrides no BaseAgent method.
  - Command: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_contract.py`.
- **`tests/test_restore_output_schema.py`** (140 lines): the `restore(..., output_schema=)` round trip. This is the sibling for re-supplying a non-serialized input.
- **Named and sized, contents unverified:**
  - `tests/test_agent_fork_isolation.py` (547 lines): fork field copying.
  - `tests/test_agent_base.py` (443 lines).
  - `tests/test_durable_sessions.py`, `tests/test_agent_tool.py`, `tests/test_custom_exception_constructors.py`, `tests/test_readme_size_limit.py`, `tests/test_middleware_builtins.py`.
- **No test** compares BaseAgent keywords with `AgentSettings` or the YAML config (git grep found none).

### Commands

- One file: `PYTHONPATH=$(pwd) python -m pytest -q tests/test_jev_agent.py`.
- Coding-agent pack: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent`.
- All tests: `python -m pytest`.
- Then the full gate: `python scripts/run_ci.py`.

## 4. Notes for the spec author

### Contradictions (request assumes X; code shows Y)

1. **Registry class name.** Request assumes `ModelRegistry.resolve_api_key` (request lines 41, 58, 193, 214). Code shows `ProviderModelRegistry.resolve_api_key` at `vidbyte/lib/registries/models.py:151-161`. No class named `ModelRegistry` exists (git grep).
2. **JevAgent cannot take a new constructor parameter.** Request assumes `outputs=` "bolted onto" JevAgent. Code shows:
   - `JevAgent.__init__(self, settings, runtime_settings=None)` at `vidbyte/agents/jev/agent.py:35`.
   - The signature is pinned by `tests/test_jev_agent.py:504-509` and by the field guide `jev-capability-layout.md:63`.
   - AGENTS.md "New JEV code" routes a capability to a named field on `JevAgentSettings`.
   - The request itself lists this as open (line 228).
3. **JevAgent drops BaseAgent customization today.** Request assumes the JevAgent reply passes the schema check before delivery. Code shows `jev/agent.py:90-102` passes no `middleware`, `output_schema`, or `handoff`, so `_assert_schema_satisfied` (`base.py:947-963`) has no schema to enforce for a JevAgent. JevAgent children are all built with explicit keyword lists, so none carry a new attribute unless passed:
   - fresh-continuation `partial(BaseAgent, ...)` at `jev/agent.py:62-76`
   - `jev/bulk_work.py:49`
   - `jev/compute/clone.py:42`
   - `jev/compute/swarm.py:54`
4. **CodingAgent needs no edit.** Request line 209 says CodingAgent's "base class not yet checked". Code shows `class CodingAgent(BaseAgent)` at `vidbyte/agents/coding.py:27`, not `CodexHarnessAgent`.
   - It forwards `**kwargs` to BaseAgent.
   - `tests/features/coding_agent/test_coding_agent_contract.py` pins `EXPECTED_SIGNATURE`, with exactly one `**kwargs` and no explicit extra keyword, and asserts that no BaseAgent method is overridden.
5. **Forks versus `as_tool`.** Request line 67 says both "forks do not inherit outputs" and "an agent used through `as_tool` delivers on every call". Code shows `AgentTool.execute` forks first (`vidbyte/tools/agent_tool.py:59`, `child = self._agent.fork()`) and calls `child.generate_reply`. `AgentForker.fork` builds a fresh `BaseAgent` from an explicit keyword list (`vidbyte/agents/fork.py:53-81`).
   - So under the fork rule, an `as_tool` agent never delivers.
   - MultiAgent workers and the orchestrator also run on `.fork()` (`vidbyte/agents/multi/transfer.py:212,229`; `vidbyte/agents/multi/orchestrator.py:203`).
   - Separately, `AgentTool.execute` turns any `Exception` from the child into `ToolResult.error(..., str(exc), ...)`.
6. **Receipts versus the session record.** Request line 62 assumes receipts in `reply.metadata["deliveries"]` are recorded with the turn. Code shows `_notify_session(reply)` → `record_turn(reply)` at `base.py:928` runs before `_assert_schema_satisfied` at `base.py:931`. So a delivery placed after the schema check runs after the session has recorded the turn.
   - Unverified: whether the stored checkpoint serializes at `record_turn` time or later.
   - `SessionSerializer._safe` (`vidbyte/sessions/serialization.py:198-215`) replaces any non-pydantic, non-mapping object with `{"__dropped__": TypeName}`. A frozen dataclass receipt in metadata would therefore be persisted as dropped.
   - `_SECRET_TOKENS` scrubs metadata keys containing API_KEY, TOKEN, SECRET, PASSWORD, CREDENTIAL, or AUTH (substring match).
7. **The handoff sibling runs before the schema check.** Request line 59 cites `_run_auto_handoff` as the sibling for a step "after `_assert_schema_satisfied`". Code shows the handoff block at `base.py:920-927` runs before both `_notify_session` (928) and `_assert_schema_satisfied` (931). On failure it clears `self._queued_prompts` before re-raising (`# @intent failed-run-leaves-no-queued-prompts`).
8. **Drained replies take the same path.** Request line 59 places delivery "before queued follow-up prompts drain". Code shows `_drain_queued_prompts` (`base.py:1073-1107`) calls `self.generate_reply(prompt)` per queued prompt, so each drained reply goes through `_generate_reply` lines 896–934 again.
9. **Middleware-abort detection (request line 230, open).** Code shows `_middleware_abort_result` at `vidbyte/agents/runtime.py:1072-1099` sets:
   - `stop_reason = AgentStopReason.MIDDLEWARE_ABORT.value` (`"middleware_abort"`)
   - `"middleware_abort_reason"`
   - `"middleware_decision"`
   - The output is non-empty: `"Agent runtime stopped by middleware: {reason}"`.

   `base.py:903` merges `**dict(result.metadata)` into the reply metadata, so these keys reach `reply.metadata`. The empty-reply rule at request line 66 would not catch an abort by content alone. A before_run abort is at `runtime.py:325-331`.
10. **Transport limits versus the platform list (request line 220).**
    - `HttpTransport.request` sends JSON bodies only (`vidbyte/lib/http/transport.py:40`). There is no form-encoded body. Request line 220 lists Twilio, which posts form-encoded fields (unverified for Twilio's API itself).
    - Multipart exists only on `SyncHttpTransport.upload_multipart`.
    - Backoff ignores `Retry-After`.
    - The default `retry_status_codes` include 408, 409, 425, and 5xx. Request line 61's "retry on 429 only" requires passing `(429,)` explicitly.
11. **`vidbyte/providers/` is a model-adapter layer.** Request line 56 offers it as a home for provider-specific output logic. Code and REPO_MAP show:
    - It is "the folder to extend when adding support for a new model vendor".
    - Its `__init__.py` (the `ModelProviders` factory) eagerly imports every model adapter.
    - Its README is model-vendor specific.
    - A006 classes `vidbyte.providers` as a lower layer alongside `vidbyte.lib`, `vidbyte.sessions`, and `vidbyte.sources`.
    - `vidbyte/providers/base.py` already imports `vidbyte.tools.types`.
    - The only existing non-model credentialed HTTP clients are in the tools layer (`vidbyte/tools/builtins/operations/clients/`).
12. **The layering constraint is concrete.** The request puts the abstraction in `vidbyte/agents/output/` (orchestration layer) and the provider logic in `vidbyte/lib/` or `vidbyte/providers/` (lower layers under A006). A006 counts function-local imports and skips only `TYPE_CHECKING` imports, so a lower-layer module may not import `vidbyte.agents.*` at all.
13. **Import path.** Request line 111 shows `from vidbyte.outputs import ...`, annotated "import path will follow the agents/output placement". No `vidbyte/outputs/` or `vidbyte/agents/output/` exists today.
14. **YAML parity.** Request line 229 asks whether `vidbyte/config/` must accept `outputs`.
    - Code shows `AgentSettings` "mirrors the YAML-serializable construction inputs of `BaseAgent`; the non-serializable inputs (permission_policy, context_manager, tracer, handoff, ...) are out of scope for the declarative surface" (`vidbyte/lib/dataclasses/config.py:25-28`).
    - `_ALLOWED_FIELDS` (`config.py:339-345`) rejects unknown keys today.
    - No test or lint rule enforces parity (git grep).
15. **CodexHarnessAgent (request line 223, open).** It is not a BaseAgent (`vidbyte/agents/codex/agent.py`, `class CodexHarnessAgent:`). It builds and appends its own `AgentMessage` in `arun` (100–178), so it never passes through `BaseAgent._generate_reply`. Prompt 4 does not name it. CodingAgent is not built on it (item 4).
16. **`restore()` on the subclasses.** `BaseAgent.restore` calls `cls(name=..., system_prompt=..., ...)` (`base.py:549-571`). That cannot bind to `JevAgent.__init__(settings, runtime_settings)`. Unverified at runtime; inferred by reading. `CodingAgent.restore` raises `TypeError` "for the missing root_dir" (`vidbyte/agents/coding.py:9`, header KNOWN EDGE CASES). Request line 67 ("`restore()` accepts `outputs=`") therefore only applies to plain BaseAgent.
17. **File size.** `vidbyte/agents/base.py` is 1694 lines. AGENTS.md Style 3 says "Keep files well below 1,000 lines; when a file heads toward four digits, split it ... before adding more."
18. **Error placement.** REPO_MAP says "A new failure mode should usually reuse an existing error type". Any new `*Error` in `vidbyte/lib/errors/` must carry the full `DIAGNOSTIC_FIELDS` packet (A003). `ConfigurationError` (`vidbyte/lib/errors/base.py:235`) has no custom `__init__`.

### Gaps and facts the spec must not get wrong

- **Delivery choke point.** Every BaseAgent reply goes through `BaseAgent._generate_reply` (`base.py:821-934`). That covers `run`, `arun`, `run_sequentially`, `arun_sequentially`, the queued drain, `Session.arun` (which calls `agent.arun`), and `AgentTool` (which calls `child.generate_reply` on a fork).
- **Non-linear runtimes** (MCTS_SEARCH and the ACTOR_MODEL variants) reject `middleware`, `output_schema`, and other options at `base.py:128-162`. Behavior for a new keyword on those runtimes is unspecified today.
- **Async SMTP.** `smtplib` is not banned by S011. S046 and S052 (Ruff ASYNC) flag blocking IO in async functions. Existing off-loop precedent uses `asyncio.to_thread` at `vidbyte/tools/builtins/operations/fetch.py:223`, `vidbyte/harnesses/stores/file.py:56`, and `vidbyte/tools/function_tool.py:71`. No `smtplib` or `hmac` usage exists in `vidbyte/` today (git grep).
- **Concurrency lint.** `asyncio.gather(return_exceptions=True)` requires a BaseException check (S063). Catching BaseException or CancelledError requires a re-raise (S019). The field guide `provider-api-contracts.md` says "Never catch BaseException" around provider calls.
- **Named constants.** A per-connector timeout (about 10 s) and the `(429,)` tuple are numeric literals near "timeout" and "status" names, so A007 requires UPPERCASE named constants.
- **Credential masking.** Precedents:
  - `JevAgentSettings.api_key` uses `field(default=None, repr=False)`.
  - `FallbackModel.__repr__` masks the key as `api_key='***'`.
  - `WebOperationClient` keeps the key in a private attribute and builds headers per call.
  - `CredentialKeyPolicy` only classifies key names.
- **`RunState` is explicit.** `export_state` (`base.py:514-541`) and `RunState` (`vidbyte/lib/dataclasses/sessions.py:53-78`) list every field explicitly, so a new attribute is not serialized unless added.
- **Field-guide entries** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`):
  - **Apply:** `blocking-lint-invariants.md`, `strict-config-dataclasses.md`, `jev-capability-layout.md`, `local-ci-verification.md`, `provider-api-contracts.md`, `comment-format.md`, `class-bound-helpers.md`, `review-scope.md`, `declarative-config-resolution.md`, and `prebuilt-agents.md` (no CLI in the SDK).
    - `comment-format.md`: wrap at 72 columns, with `# @intent` on its own first line.
    - `blocking-lint-invariants.md`: lib records must not expose a `dict[str, Any]` encoder (S060), TypedDict is banned (S039), and C002 forbids status bools.
  - **Not read:** `agents-md-map.md`, `cloud-trajectory-sinks.md`, `cli-backed-source-integrations.md`, `diagnostic-context.md`, `fallback-coordination.md`, `model-facing-tool-contracts.md`, `operation-pricebook-rates.md`, `priced-operation-execution.md`, `tracing-shape-contracts.md`.
- **PYTHONPATH.** The briefing says to run `run_ci` with PYTHONPATH unset. The field guide and lint README say to run the source stage with `PYTHONPATH=$(pwd)` and the package stage without it. The package smoke test pops PYTHONPATH itself, but the pip install step is affected (user memory note, not re-verified).
- **Unverified:**
  - Twilio's form-encoding requirement.
  - Which platforms accept an idempotency header.
  - Whether Slack incoming webhooks accept a `markdown` block.
  - Every environment-variable name per destination.
  - The contents of the test files listed in §3 as "named and sized".
