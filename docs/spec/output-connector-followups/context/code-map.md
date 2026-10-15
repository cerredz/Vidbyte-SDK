# Code map: output-connector-followups (S0 scout)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-output-connector-followups`, HEAD `2ce44a1f` (docs commit) on base `336d6c78` (merge of origin/main into `feat/agent-output-connectors`), read 2026-10-13. Scope read from `request.md` §B sections 0–5 minus the §C exclusions. Line numbers refer to this HEAD. Everything below was opened in this session unless it is marked "unverified".

## 1. Rules, commands, and conventions from AGENTS.md that bind this change

### 1.1 AGENTS.md (CLAUDE.md is only `@AGENTS.md`)
- **Repository map.** Read `REPO_MAP.md` before you create a file. Read each folder's `README.md` to the end before you change that folder; its `## Notes for agents` section, where one exists, records mistakes review has already caught. Neither `vidbyte/lib/outputs/README.md` nor `vidbyte/agents/output/README.md` has a `## Notes for agents` section today.
- **A009.** Every folder README is at most 40,000 characters.
- **`docs/` is opaque.** The only exceptions are documents a human names; this run names `docs/spec/agent-output-connectors/spec.md` (§9.2(b) corrections) and this run's own spec folder.
- **The gate.** "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- **Style 1.** Call chains are one level deep: a main function calls flat helpers, and a helper does not call another helper of the same class or module. Calls to another class, a lower layer, or the standard library do not count. No nested `def` unless an API needs a callback.
- **Style 2.** Narrate each main function in plain-English comments, and update the comments whenever the steps change.
- **Style 3.** Layers. `vidbyte/lib/` is the bottom layer and never imports a higher one; no import cycles. Keep files "well below 1,000 lines"; if describing a function or class needs "and", it is probably two.
- **Style 4.** Core inputs and outputs are validated `@dataclass(frozen=True, slots=True)` records whose `__post_init__` checks types, ranges, and allowed values and names the bad field. A closed set of values is an enum.
- **Style 5.** Write shared logic once, in `vidbyte/lib/`. The example is `HttpTransport`: "if one is close, add the option you need to it rather than copying it into a variant beside your feature." A new canonical helper goes in `vidbyte/lib/<domain>/` and takes what it needs as arguments.
- **Placement rules (binding; the `AGENTS.md placement` workflow enforces them on every PR).**
  - Every new dataclass goes in `vidbyte/lib/dataclasses/<domain>.py`; for this change that is `vidbyte/lib/dataclasses/outputs.py`.
  - Every new enum goes in `vidbyte/lib/enums/<domain>.py` (`vidbyte/lib/enums/outputs.py`), and every public enum is exported from `vidbyte/lib/enums/__init__.py`.
  - Never create `types.py`, `records.py`, `models.py`, or `schemas.py`.
  - Existing code that predates the rules is not precedent.
- **Not in AGENTS.md:** commit or PR conventions, and install or test commands other than `run_ci.py`.

### 1.2 REPO_MAP entries that bind this change
- **`vidbyte/lib/outputs/`:** "Add a new destination here alongside its provider reference, which records where its credential comes from and when its limits were last checked."
- **`vidbyte/agents/output/`:** the agent-side layer. It holds the contract, the shaping and skip rules, and the dispatcher.
- **`vidbyte/lib/http/`:** "Nothing else in the package should reach for an HTTP client directly outside of this layer."

### 1.3 Gate commands (each read in `scripts/run_ci.py`, `lint/README.md`, the workflows, or the field guide)
- **Full gate:** `python scripts/run_ci.py`, which prints `CI passed.` Its stages are `--stage all|source|package`, and `--dist-dir` sets the build output folder.
  - **Source stage:** a check for tracked bytecode, then `python lint/run.py`, then `python -m compileall -q vidbyte`, then `scripts/check_context_write_paths.py`, `scripts/check_context_primitive_introductions.py`, and `scripts/check_reasoning_trace_contracts.py`, then `python -m pytest`.
  - **Package stage:** build, `twine check`, wheel inspection, an install into a clean venv, and a smoke test.
- **Field guide `local-ci-verification.md`:** run `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with **no** `PYTHONPATH`.
- **Lint:**
  - `python lint/run.py`, `python lint/run.py --rule <ID>`, `--all`, `--format json`.
  - Pass line: `SDK-LINT: PASS` (`lint/core/report.py:58`; `SDK-LINT: FAIL` otherwise). Exit 0 means CLEAN, RATCHETED, or IMPROVED.
  - Use `--update-baseline` only after a genuine improvement, and never raise a baseline.
- **Import order (S051):** `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`. Run `--fix` only on files you created.
- **Pack tests:** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors` (the command in `conftest.py:11`). One file: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_<x>.py`.
- **Public API contract:** `python scripts/generate-sdk-public-api.py --check`.
  - Regenerate it with `python scripts/generate-sdk-public-api.py` only after the `vidbyte/__init__.py` change is committed; the generator refuses to run while its inputs are dirty.
  - The contract is `contracts/sdk-public-api.json`: version `0.2.1`, `source.commit` = `4272c308aeb426e37e06c525e7e630361d7ea6f6`. C016 enforces it.
  - `contracts/README.md`: tell the vidbyte-cli owners when an export is removed or renamed.
- **Semgrep** runs only in `.github/workflows/static-policy.yml`, not in `run_ci.py`.
  - Command: `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, with `semgrep==1.170.1` in its own venv.
  - It scans only git-tracked files, so `git add` new files first.
- **CI:** both workflows are `workflow_dispatch` only (`ci.yml` also allows `workflow_call`).
  - `ci.yml` source job: Python 3.11 and 3.12, `pip install -e ".[dev]"`, then `run_ci.py --stage source`, then a package job.
- **Dependencies (`pyproject.toml`):**
  - `requires-python >=3.11`.
  - Runtime: `pydantic>=2,<3`, `httpx>=0.27`, `PyYAML>=6,<7` only. There is no Markdown library and no HMAC library (`hmac` is in the standard library).
  - Dev: `mypy==2.3.1`, `ruff==0.16.4`.

### 1.4 Lint rules that bite this change (`lint/rules/*.py`; baselines from `lint/baseline.json`)
**Scope.** Most rules scan tracked `vidbyte/**.py` only (`python_files()`). A001 and S062 scan every tracked `.py` file, tests included (`all_python_files()`). The Ruff-backed rules run `ruff check pyproject.toml vidbyte`, so they never see tests. An untracked file is not linted until it is `git add`-ed.

| ID | What it enforces | Baseline | Where it bites here |
|---|---|---|---|
| A001 | The module docstring has non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, `TESTS:` | 643 | Every new `.py`, tests included. First-batch files use the `"""FILE: <path>` style (copy `vidbyte/lib/outputs/slack.py:1-10`). `transport.py` has no header (pre-existing). |
| A002 | A function whose name, body names, or attributes contain a policy token needs `# @intent <name>` within def−4 … def+20. Tokens: retry, backoff, attempt, permission, authorize, pricing, price, billing, redact, **secret**, persist, persistence, checkpoint, fallback, transition, **transport**, **request**, **fetch**, **send**, urlopen, provider, subprocess, mcp. | 703 | Every new `send`; any helper that reads `request.*` or calls `.send`/`.request`; `WebhookOutput.__init__` once it takes a `secret` parameter; GET/PATCH helpers in `delivery.py`. |
| A003 | An `*Error` class in `vidbyte/lib/errors/` declares the literal 8-field `DIAGNOSTIC_FIELDS` and sets each on `self` and in `details` | 36 | Only if a new error class is added. |
| A006 | Lower layers (`vidbyte.lib`, providers, sessions, sources) never import orchestration (`agents`, context, middleware, tools, pipelines, workflows, harnesses, trace, evals, paradigms) or application (client, config, cli, mcp_server). Function-local imports count; `TYPE_CHECKING` is exempt; `__init__.py` targets are skipped. | 34 | `lib/outputs` cannot use `harnesses/stores/file.py` or `sources/llms_txt` helpers. |
| A007 | A numeric literal near a name containing timeout, retry, attempt, backoff, delay, token, char, byte, truncate, limit, budget, status, depth, or interval, or passed to sleep/urlopen/send/request/read/read_bytes, or used as the default of such a parameter, must be an UPPERCASE constant | 255 | New caps (12,000; 32,768; 100), the 1 MiB summary limit, timestamps, page sizes, and HTTP statuses all belong in `vidbyte/lib/constants/outputs.py`. |
| A009 | README ≤ 40,000 characters | 0 | `lib/outputs/README.md` is 11,715 bytes over 150 lines today (`wc -c`). |
| C016 | The public API contract is current | 0 | Any root export change. |
| S008 | Ruff C901, PLR0912, PLR0915 at Ruff's defaults: complexity >10, branches >12, statements >50 (`lint/ruff.toml` has no override; the values are as quoted in first-batch spec §12.4) | 19 | `BaseAgent._generate_reply` has zero headroom; do not touch it. Long multi-request `send` methods. |
| S009 | mypy on `vidbyte` | 350 | All new annotations must be fully parameterized. `lint/mypy.ini` was not opened; its `disallow_any_generics` and `check_untyped_defs` settings are unverified and come from spec §12.4. |
| S011 | `http.client`, `httpx`, `requests`, or `urllib.request` may be imported only in `vidbyte/lib/http/transport.py` and `vidbyte/tools/mcp/transport.py` | 0 | `lib/outputs` reaches HTTP only through `HttpTransport`. |
| S012 | A call named `request`, `request_bytes`, `stream_request`, `upload_multipart`, or `urlopen` must pass `timeout=` or `timeout_seconds=` | 0 | Do not name a non-HTTP helper `request`. |
| S013 | Requests under tools/builtins/code_search, mcp, operations, and tools/mcp pass `max_response_bytes` | 4 | Not `lib/outputs`, but the first batch passes it anyway (`OUTPUT_MAX_RESPONSE_BYTES`). |
| S015 | Root `__all__` integrity | 13 | Root exports. |
| S020 | A README `## File Index` must match the tracked direct children (opt-in by that heading) | 1 | `lib/outputs/README.md` uses `## Modules` (line 30), so it is not opted in. Keep that heading. |
| S024 | Control-flow nesting ≤ 3 | 25 | Pagination and sticky-comment loops. |
| S041 | Ruff PLW1514: text file operations pass an explicit `encoding` | 0 | The GitHub job-summary file write. |
| S045 / S046 | ASYNC109 / ASYNC210 | 2 / 0 | |
| S047 | ASYNC230: blocking `open()` inside `async def` | 0 | The job-summary write inside `async send`. Whether Ruff also matches `Path.open` here is unverified. |
| S050 | Ruff S324: insecure hash | 0 | `hashlib.sha256`/`hmac` are fine. Do not use md5 or sha1. |
| S052 | ASYNC100, ASYNC105, ASYNC110, ASYNC220, ASYNC221 | 0 | Blocking I/O in async code. |
| S054 | Ruff S105, S106, S107, S108, S301, S302, S501. S105 flags a string literal assigned to a name with a password/pass/pwd/**token**/**secret** segment; S106 keyword args; S107 defaults. | 3 | A constant such as `WEBHOOK_SECRET_PREFIX = "whsec_"` or `GITLAB_TOKEN_HEADER = "private-token"` would be flagged. Pipeline: "S054/S105 flags string constants with a `_TOKEN_` name segment". |
| S056 | `HttpTransport.request` and `SyncHttpTransport.request` must declare `idempotency_key` | 0 | Any `HttpTransport.request` signature change. |
| S061 | A bare `open(<non-literal>)`; `.write_text`, `.write_bytes`, `.read_text`, or `.read_bytes`; `shutil` copy/move; or `extractall` with a non-literal first argument is a finding. The allowlist is only `vidbyte/lib/tools/filesystem/backends/local.py`. The AST check does not match an attribute call `Path.open(...)`. | 6 | The job-summary write. |
| S062 | No adjacent string literals (all tracked `.py`) | 889 | `errors/base.py:486-497` already has them (main's code); do not copy. |
| S063 | `gather(return_exceptions=True)` results are checked against `BaseException` | 4 | Only if a connector gathers. |
| S064 | A retry loop that sleeps needs a cumulative deadline | 4 | Hand-written pagination or retry loops. |
| S017 | Scoped to providers, tools, mcp_server, and lib/runners | 79 | Not `lib/outputs`. |
| S051 | Ruff I001 import order | 259 | New files. |

- **`lint/ruff.toml` bans (TID251):** `typing.TypedDict`, `typing.assert_never`, and `asyncio.Lock`.
- **Semgrep `no-untyped-mapping-fallback`** (`.semgrep/typed-mapping-boundary-policy.yml`):
  - **Scope:** `/vidbyte/**/*.py`, excluding `lib/http`, providers, `mcp_server`, and `tools/mcp`, so it applies to `lib/outputs`.
  - **Flags:** a `def f(..., v: object|Any, ...)` whose body begins `if not isinstance(v, Mapping|dict): return ...`.
  - **Fix:** use positive `isinstance` branches, the way `WebhookOutput._structured_json` and `OutputHttp._link` do.

### 1.5 Field-guide rules that apply (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`)
- **`provider-api-contracts.md`:**
  - Mirror the vendor API reference exactly, and write one scripted-transport test per documented example.
  - Use one guarded `try` per provider call, and never catch `BaseException`.
- **`blocking-lint-invariants.md`:**
  - A new error carries the full A003 packet.
  - S060: no `dict[str, Any]` wire encoder on lib records, and no TypedDict.
  - S012 naming: do not call a non-HTTP helper `request`.
  - A006: function-local imports count.
  - A007: a literal such as `read(CAP+1)` is flagged.
- **`strict-config-dataclasses.md`:** keep the constructor a thin layer over a validated dataclass. Bounds are named constants in `lib/constants`, and generous caps are derived from vendor limits.
- **`comment-format.md`:**
  - A multi-line comment block is at most 72 columns, indentation included, and sits directly above its line; `# @intent` is the first line of the block.
  - Check with `awk 'length($0) > 72' <file> | grep -E '^\s*#'`.
- **`class-bound-helpers.md`:** prefer a static helper class over a bag of module-level free functions (precedent: `OutputText`, `OutputArguments`, `ToolsFormatter`).
- **`local-ci-verification.md`:** see §1.3.
- **`review-scope.md`:** never re-sort or `--fix` an untouched import block.

### 1.6 Conventions found in the code
- **Connectors.**
  - Every connector constructor is keyword-only and ends with `render: Callable[[AgentMessage], OutputContent] | None = None`. It calls `super().__init__(render=render)` and resolves its credential once with `OutputArguments.credential(...)`. Each connector module is about 48–81 lines.
  - Each `send` opens with a `# @intent <name>` comment block and ends `return await OutputHttp.post(self.destination, OutputRequest(...))`.
- **Header keys** passed to `HttpTransport` are lowercase; `OutputRequest.__post_init__` rejects anything else (`dataclasses/outputs.py:86-87`).
- **Error messages.** `OutputArguments.text`, `texts`, `identifier`, `matching`, and `address` echo the bad value (`{value!r}`). Only `credential` and `https_url` never echo it (`base.py:42`, `47-57`).
- **Exports.** Export from `vidbyte/lib/outputs/__init__.py`, `vidbyte/agents/output/__init__.py` (its header says to add the import and `__all__` entry there and in `vidbyte/__init__.py` together), and root `vidbyte/__init__.py`. Then regenerate the contract.
- **Constants** go in `vidbyte/lib/constants/outputs.py` with `__all__`. That module is not in `vidbyte/lib/constants/__init__.py`. Its header (line 6) says: "Add a named constant here before introducing another delivery limit, version, or endpoint literal."

## 2. Files this change will touch

### 2.0 Shared delivery code (read in full; every work group depends on it)

**`vidbyte/lib/dataclasses/outputs.py`** (116 lines). All records are `frozen=True, slots=True`, and each raises `ConfigurationError(f"{field} {message}", details={"field": ...})`.
- **Today:**
  - `OutputContent(title: str, body: str)`: both must be non-blank (lines 44-53).
  - `DeliveryReceipt(destination: OutputDestination, status: DeliveryStatus, url: str | None = None, error_code: str | None = None)`. `error_code` is non-blank exactly when FAILED, and `url` is allowed only on SENT and only when it starts `https://` (56-71).
  - `OutputRequest(url: str = field(repr=False), headers: Mapping[str, str] = field(repr=False), json_body: Mapping[str, object] = field(repr=False), link_path: tuple[str, ...] = (), link_prefix: str = "")` (74-91):
    - `url` must start `https://`;
    - `headers` must map lowercase `str` names to `str` values;
    - `json_body` must be a `Mapping` (a JSON array is rejected);
    - `link_path` is a tuple of non-blank `str`, and `link_prefix` is a `str`;
    - there is no method field, no raw-bytes field, and no query-string field;
    - the mappings are stored as passed, not copied.
  - `SmtpSettings(host, port, username, password=field(repr=False), sender, recipients)`.
  - `__all__` (line 116).
- **Will change:** whatever new request shape GET, PATCH, signed bytes, or a returned response body needs, plus any new records (for example a signing or summary-target record). All of them belong in this module (Placement Rules).
- **Pattern:** `_require` / `_is_text` / `_is_address` checks, `repr=False` on any field that can carry a secret, and `Mapping[str, object]` types (never `dict[str, Any]`, S060).

**`vidbyte/lib/outputs/delivery.py`** (182 lines).
- **Today:**
  - `_OUTPUT_POST_ACTIVE: ContextVar[bool]` (line 49).
  - **`OutputHttp.post(destination: OutputDestination, request: OutputRequest) -> DeliveryReceipt`** is a static async method (56-93), `# @intent output-post-retries-only-rate-limits`. Its steps, in order:
    1. Set the context var.
    2. Call `HttpTransport().request(method="POST", url=request.url, headers=request.headers, json_body=request.json_body, timeout_seconds=OUTPUT_TIMEOUT_SECONDS, retry_count=OUTPUT_RATE_LIMIT_RETRIES, retry_status_codes=OUTPUT_RETRY_STATUS_CODES, max_response_bytes=OUTPUT_MAX_RESPONSE_BYTES, idempotency_key=uuid4().hex, follow_redirects=False)`. `"POST"` is hard-coded on line 67.
    3. `ProviderRequestError` gives FAILED `network`; the context var is reset in `finally`.
    4. A status outside 200–299 gives FAILED `_error_code(response)`.
    5. An empty `link_path` gives SENT.
    6. Otherwise `_link(...)`: `None` gives FAILED `invalid_response`, and a link gives SENT with `url=link`.
    7. **The response body is never returned to the caller.**
  - `_error_code(response) -> str` (96-103): `http_<status>`, plus `:<token>` when the whole stripped body fully matches `OUTPUT_ERROR_TOKEN_PATTERN`.
  - `_link(response, request) -> str | None` (106-120), `# @intent created-object-link-is-https`. It runs `json.loads(body)` (`ValueError` gives `None`), then walks `link_path` **through Mappings only** (a list cannot be indexed), requires a non-blank `str` (an `int` id fails), prepends `link_prefix` (a **prefix only**, no suffix), and requires the `https://` prefix.
  - `_keep_log_record(record) -> bool` (123-129), `# @intent output-request-log-hides-the-url`, is registered once with `logging.getLogger("httpx").addFilter(...)` (line 180).
  - `OutputSmtp.send(settings, message) -> DeliveryReceipt` (136, `# @intent smtp-is-one-verified-tls-attempt`) and `_client` (171).
  - `__all__ = ["OutputHttp", "OutputSmtp"]`.
- **Will change (§B5):** "`OutputHttp` gains GET and PATCH and returns the response JSON to the connector." Every new path must keep these guarantees:
  - the log filter context var is set around every send, not only POST;
  - `follow_redirects=False`;
  - retries only on 429, at most twice;
  - `OUTPUT_MAX_RESPONSE_BYTES`;
  - error codes never carry response text.
- **Will change (§B2):** signing needs the exact body bytes (see `transport.py` below).
- **Pattern:** a narrated main function over leaf static helpers; one guarded `try`; `# @intent` on every function that reads `request` or sends.

**`vidbyte/lib/http/transport.py`** (244 lines, no A001 header). It is the canonical helper named in AGENTS.md Style 5.
- **Today:**
  - `_IDEMPOTENT_METHODS = frozenset({"GET","HEAD","OPTIONS","PUT","DELETE"})` (20).
  - `_require_idempotency_guard(*, method, retry_count, idempotency_key)` (23-26) raises `ProviderRequestError` when `retry_count > 0`, the method is not in that set, and the key is `None`. **PATCH and POST need a key to retry; GET does not.**
  - `_json_request_headers(headers) -> dict[str, str]` (34-39), `# @intent exactly-one-content-type-in-any-spelling`, adds `content-type: application/json` only when no spelling of the header is present.
  - `HttpResponse(status_code: int, body: str, headers: Mapping[str, str], raw_bytes: bytes | None = None, attempts: int = 1, url: str | None = None)` (42-49) is frozen and slotted.
  - **`HttpTransport.request`** (55-72):
    - Signature: `self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, retry_count: int = 0, backoff_seconds: float = 0.5, backoff_multiplier: float = 2.0, retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504), max_response_bytes: int | None = None, idempotency_key: str | None = None, follow_redirects: bool = False) -> HttpResponse`.
    - It accepts any method string, so GET and PATCH already work.
    - It opens one `httpx.AsyncClient(timeout=..., follow_redirects=...)` and makes `retry_count + 1` attempts.
    - It retries only when the status is in `retry_status_codes`, with `asyncio.sleep(delay)` and `delay *= backoff_multiplier`. **It has no Retry-After support.**
    - It returns `replace(response, attempts=n)`.
    - `httpx.RequestError` becomes `ProviderRequestError`.
    - **`idempotency_key` is only checked by the guard and is never sent on the wire.**
  - **`HttpTransport._send_once`** (74-88; this is the test seam):
    - Signature: `self, client, *, method, url, headers, json_body, timeout_seconds, max_response_bytes=None`.
    - When `json_body is not None`, it serializes `content = json.dumps(json_body).encode("utf-8")` (line 79: Python default separators `", "` and `": "`, `ensure_ascii=True`) and applies `_json_request_headers`.
    - It builds `client.build_request(method, url, headers=..., content=content)`. **No parameter accepts pre-serialized bytes or a non-JSON body.**
    - With `max_response_bytes` set, it calls `_send_bounded`.
  - `_send_bounded` (90-110) streams the response; a declared `content-length` or a running total above the ceiling raises `ProviderRequestError`. It returns `headers=dict(response.headers)` and `raw_bytes`. Whether httpx header keys come back lowercased is unverified.
  - `SyncHttpTransport` (urllib; `request`, `request_bytes`, `upload_multipart`, `stream_request`) is not used by outputs.
- **Will change (§B2, only if the spec routes signing through the transport):** an option for exact body bytes, per Style 5 ("add the option you need to it").
  - **Callers:** `HttpTransport()` is constructed in 12 modules: `lib/outputs/delivery.py`, five `lib/runners/*`, `sources/fetches/http.py`, `tools/builtins/{mcp/search.py, memory/base.py, operations/clients/_base.py}`.
  - **Test fakes:** every `_send_once` fake (`tests/test_web_operation_client_retry.py:32`, `tests/features/coding_agent/conftest.py:81`, `tests/features/agent_output_connectors/conftest.py:74`, `scripts/test-async-http-transport.py:141,159,184,208`) takes `**kwargs`, so a new keyword stays compatible. `scripts/test-async-http-transport.py:115` calls the real `_send_once` with explicit keywords.
- **Pattern:** keyword-only defaulted options; S056 keeps the `idempotency_key` parameter; S011 keeps the `httpx` import here only.

**`vidbyte/lib/outputs/base.py`** (134 lines).
- **Today, `OutputArguments` static methods** (32-107), each raising `ConfigurationError` that names `parameter`:
  - `credential(destination, explicit, *, parameter) -> str` reads `OUTPUT_CREDENTIAL_ENV_VARS[destination]` with a hard index, so a destination missing from the map raises `KeyError`. It tries the explicit value, then the environment, each stripped, and fails with "Missing credential for {destination.value} output. Pass {parameter} or set {env_var}." and `details {parameter, env_var}`.
  - `https_url(value, *, parameter)` requires an `https://` prefix, a host, and a parseable port. Its message never echoes the value.
  - `text`, `texts` (rejects a bare `str`), `non_empty`, `identifier` (UUID, returned dashed), `optional_callable`, `matching(value, pattern, *, parameter)` (`re.fullmatch`, no strip), and `address`.
- **Today, `BaseOutput(ABC)`** (110-131): `destination: OutputDestination`; `__init__(self, *, render=None)`; a `render` property; abstract `async send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt` with `# @intent one-send-one-receipt`; and `__repr__` returning `f"{type(self).__name__}(credential='***')"`. The repr is hard-coded, even for a connector with no credential.
- **Will change:** possibly new checks: header-mapping validation that must not echo values, an optional-credential path for the job summary, numeric issue and comment ids, issue keys, GitLab `host=`, and a numeric Confluence space id.
- **Pattern:** add a static method to `OutputArguments` (its header, line 6: "Add a static check to OutputArguments when a new connector argument needs one").

**`vidbyte/lib/outputs/text.py`** (47 lines). `OutputText` has four static methods:
- `first_line(text)` (22);
- `chat_text(content)` (28): `title\n\nbody`, or the body alone when its first line equals the title;
- `truncate(text, limit)` (35): the marker `OUTPUT_TRUNCATION_MARKER = "\n\n[truncated]"` counts inside the limit;
- `single_line(text, limit)` (42): collapses whitespace and cuts with no marker.

It holds **no Markdown or ADF builder.** No Markdown parser exists in `vidbyte/lib`. `vidbyte/sources/llms_txt/parser.py` is llms.txt-specific, and A006 plus the pack's layering test forbid `lib` from importing it.
- **Will change:** possibly the home of shared rich-text helpers (Jira and Confluence ADF, Telegram or Slack Markdown limits), or a new sibling module under `vidbyte/lib/outputs/`.
- **Pattern:** pure static helpers with no agent logic.

**`vidbyte/lib/constants/outputs.py`** (160 lines).
- **Today:**
  - Operational (21-31): `OUTPUT_TIMEOUT_SECONDS = 10.0`, `OUTPUT_RATE_LIMIT_RETRIES = 2`, `OUTPUT_RETRY_STATUS_CODES = (429,)`, `OUTPUT_MAX_RESPONSE_BYTES = 1_000_000`, `OUTPUT_DELIVERY_DEADLINE_SECONDS = 35.0`, `OUTPUT_HTTP_SUCCESS_MIN/MAX = 200/299`, `OUTPUT_DELIVERIES_METADATA_KEY`, `OUTPUT_TRUNCATION_MARKER`, `OUTPUT_TITLE_MAX_CHARS = 250`, `OUTPUT_DELIVERABLE_STOP_REASONS`.
  - Error codes (36-46): `network`, `invalid_response`, `smtp_error`, `smtp_recipients_refused`, the `http_`, `smtp_`, and `unexpected:` prefixes, `OUTPUT_ERROR_TOKEN_MAX_CHARS = 64`, and `OUTPUT_ERROR_TOKEN_PATTERN`.
  - `OUTPUT_CREDENTIAL_ENV_VARS: Mapping[OutputDestination, str] = MappingProxyType({...})` (49-61): all 11 destinations.
  - Validation, SMTP, caps, mention, and endpoint constants (67-105). `__all__` starts at line 107.
  - Header, line 7: "The delivery deadline must stay above three request timeouts plus the 429 backoff, or a rate-limited send is cut short."
- **Will change:** new env vars, caps, endpoints, versions, GraphQL mutations, headers, and markers.
- **Pattern:** an UPPERCASE name plus an `__all__` entry, with no `_TOKEN_` or `_SECRET_` segment on a string constant (S105).

**`vidbyte/lib/enums/outputs.py`** (41 lines).
- **Today:** `OutputDestination(str, Enum)` has SLACK, DISCORD, TEAMS, GOOGLE_CHAT, TELEGRAM, EMAIL, GITHUB_ISSUE, LINEAR_ISSUE, JIRA_ISSUE, NOTION_PAGE, and WEBHOOK (values `slack` … `webhook`). `DeliveryStatus` has SENT, FAILED, and SKIPPED. Both are exported from `vidbyte/lib/enums/__init__.py` (import at line 111; `__all__` entries near lines 169 and 212).
- **Will change:** members for the five new connectors (GitLab, GitHub job summary, Confluence, Typefully, HubSpot task) unless a connector reuses a member. Comment or sticky modes are a closed set, so they would be an enum here too (Style 4).
- **Pattern:** append members. A new enum class also needs an export in `lib/enums/__init__.py`.

### 2.1 Work group 0: docs pass

**`vidbyte/lib/outputs/README.md`** (150 lines, 11,715 bytes).
- **Today:**
  - **Sections:** intro (1-15); `## Non-goals` (17-28: No OAuth; no MCP, YAML, or CLI; "No retries beyond HTTP 429"); `## Modules` (30-52); `## Provider Reference` (54-75), whose table header is at line 60 and whose columns are Destination, Connector, Credential (environment variable), How to get it, Body cap, Official docs, Retrieved.
  - **Provider rows:** Slack 62, Discord 63, Teams 64, Google Chat 65, Telegram 66, Email 67, GitHub 68, Linear 69, Jira 70, Notion 71, Webhook 72. Every row is dated 2026-10-11, and line 74 reads "Retrieved 2026-10-11".
  - **Later sections:** `### Email Providers` (77-92); `## How To Add A Destination` (94-106, five steps: enum member; env var plus constants; one module with `__init__` and `send` through `OutputHttp.post` or `OutputSmtp.send`; exports plus contract; a dated README row); `## Footguns` (108-150).
  - **Footgun lines:** Teams 110-112 ("only flows whose trigger allows **Anyone** work"); Jira tokens "expire within 365 days" 119-120 (already present); Deadline and resend caution 140-148.
  - **There is no webhook or Apps Script section and no Email-in section.** The webhook row says "The request is unsigned, so keep the URL unguessable."
- **Will change:**
  - The Discord, Teams, Telegram, and Jira rows and the Teams note;
  - a new Email-in section;
  - a webhook section covering the Apps Script 302, signing, and `headers=`/`payload=` examples (ntfy, Gotify, Home Assistant, Pushcut, Apprise, Inngest, incident.io, Mattermost and Rocket.Chat, n8n with header auth, Jira Automation);
  - five new provider rows and Modules lines;
  - footguns for multi-request sends and the one-issue-per-key race.
- **Pattern:** a dated row that holds the env var and an `https://` link (the pack's docs test looks rows up by env var). Stay ≤ 40,000 characters, and keep the `## Modules` heading (S020).

**`docs/spec/agent-output-connectors/spec.md`** (first batch; the user named it).
- **Today:**
  - The §9.2(b) "destinations researched and excluded" table is at lines 806-854. Its rows include HubSpot (notes) 836, X 817, LinkedIn 818, Bluesky 821, Twilio SMS 822, Mastodon 831, GitLab Issues 838, Asana 840, Pushover 846, ntfy 847, Webex 844, and Zulip 853.
  - Zendesk, Shopify, Greenhouse, Bandwidth, Bitbucket, Relay.app, OneNote, LINE Notify, Typefully, Buffer, Apprise, and Threads do not appear anywhere in the file (grep).
  - Table (a), the per-destination catalog, is at lines 790-804. The wire-contract table is at 765-777. Frontmatter: status `pr-open`, revision 8, base_commit `db3988ff`.
- **Will change:** the corrections listed in §B0, and possibly rows (a) and the wire table for changed shapes.
- **Pattern:** the table's own columns (Platform | Category | Verified reason | Official doc).

**`vidbyte/agents/output/README.md`** (104 lines, 5,238 bytes).
- **Today:** it covers when delivery runs, forks, failure behavior, and the resend recipe. The resend caution (codes `network`, `invalid_response`, `smtp_error`, `smtp_recipients_refused`, `http_5`) is at about lines 98-104.
- **Will change:** possibly a note that a connector `send` may now make several requests under one 35 s deadline, and the partial-write meaning of a failure. Unverified whether the spec needs this.
- **Pattern:** prose, ≤ 40,000 characters.

### 2.2 Work group 1: rendering (same credentials)

**`vidbyte/lib/outputs/discord.py`** (48 lines).
- **Today:** `DiscordOutput(*, webhook_url: str | None = None, render=None)`, env `DISCORD_WEBHOOK_URL`, URL is `https_url(credential)`.
  - `send` (38): text = `truncate(chat_text(content), DISCORD_CONTENT_MAX_CHARS=2_000)`, then `OutputRequest(self._webhook_url, {}, {"content": text, "allowed_mentions": {"parse": []}})` (44).
  - No `link_path`, so the receipt URL is `None`. `# @intent discord-text-cannot-ping-everyone` (40). The header notes the default 204 response has no body.
- **Will change:** opt-in `forum=True` plus optional `forum_tags=`, which send `thread_name` (the title, at most 100 characters, unverified) and `applied_tags`. The default body must stay byte-identical.
- **Pattern:** keyword-only option validated in `__init__` through `OutputArguments`; the cap as a named constant.

**`vidbyte/lib/outputs/slack.py`** (49 lines).
- **Today:** `SlackOutput(*, webhook_url=None, render=None)`, env `SLACK_WEBHOOK_URL`.
  - `send` (38): escaped = `truncate(chat_text, SLACK_TEXT_MAX_CHARS=40_000)` with `&`, `<`, `>` escaped after truncation. Request `OutputRequest(url, {"content-type": "application/json"}, {"text": escaped})` (45).
  - `# @intent slack-text-cannot-ping-the-channel` (40). Receipt URL `None`.
- **Will change:** send Slack's `markdown` block (cumulative 12,000-character limit, unverified) together with a plain `text` notification. Longer replies keep today's escaped text.
- **Pattern:** keep `{"text": ...}` as the notification text, and put the 12,000 cap in constants.

**`vidbyte/lib/outputs/telegram.py`** (56 lines).
- **Today:** `TelegramOutput(*, chat_id: int | str, bot_token: str | None = None, render=None)`.
  - `chat_id` must be an `int` that is not a `bool`, or a non-blank `str` (so `"@channel"` already passes). Anything else raises `ConfigurationError` inline (lines 38-43).
  - Env `TELEGRAM_BOT_TOKEN`. URL `f"{TELEGRAM_API_URL}/bot{token}/sendMessage"`. Body `{"chat_id": ..., "text": truncate(chat_text, TELEGRAM_TEXT_MAX_CHARS=4_096)}`, with no `parse_mode` (52).
  - `# @intent telegram-text-is-plain` (48).
- **Will change:** use `sendRichMessage` with Markdown (32,768 characters, unverified; Bot API 10.1), and add optional `topic_id=`, which maps to `message_thread_id` (unverified).
- **Pattern:** the URL method name as a constant (today the `/sendMessage` path is a literal f-string fragment).

**`vidbyte/lib/outputs/teams.py`** (53 lines).
- **Today:** `TeamsOutput(*, webhook_url=None, render=None)`, env `TEAMS_WEBHOOK_URL`.
  - The card is `{"type":"AdaptiveCard","version":TEAMS_ADAPTIVE_CARD_VERSION("1.2"),"body":[{"type":"TextBlock","text":truncate(chat_text, TEAMS_TEXT_MAX_CHARS=7_000),"wrap":True}]}`.
  - The attachment is `{"contentType":"application/vnd.microsoft.card.adaptive","contentUrl":None,"content":card}`, and the body is `{"type":"message","attachments":[attachment]}` with headers `{}` (49).
  - `# @intent teams-text-is-plain` (43).
- **Will change:** the title as its own bold TextBlock (`weight`/`size`), the body below it, and `msteams: {"width": "Full"}` (unverified).
- **Pattern:** an inline card dict, with version and width values as constants.

**`vidbyte/lib/outputs/jira.py`** (81 lines).
- **Today:** `JiraIssueOutput(*, site: str, project: str, email: str, issue_type: str = JIRA_DEFAULT_ISSUE_TYPE("Task"), api_token: str | None = None, render=None)` (43-61).
  - `site` must match `JIRA_SITE_PATTERN` `[A-Za-z0-9-]+\.atlassian\.net` (`# @intent jira-site-is-a-bare-atlassian-host`, 54). `email` goes through `address`, and `project` and `issue_type` through `text`. Env `JIRA_API_TOKEN`.
  - `send` (63): Basic auth `base64(email:token)`.
    - Paragraphs: one `{"type":"paragraph","content":[{"type":"text","text":line}]}` per non-blank line of `truncate(body, JIRA_TEXT_MAX_CHARS=32_767)` (67).
    - Fields: `project{key}`, `issuetype{name}`, `summary` = `single_line(title, 250)`, and `description` = `{"type":"doc","version":JIRA_ADF_VERSION(1),"content":paragraphs}`.
    - URL `f"https://{site}{JIRA_ISSUE_PATH}"` (`/rest/api/3/issue`). `link_path=("key",)` and `link_prefix=f"https://{site}{JIRA_BROWSE_PATH}"` (`/browse/`) (77).
    - `# @intent jira-issue-link-is-built-from-the-key` (74).
- **Will change:**
  - (G1) headings, bullet and ordered lists, and code blocks in ADF (`heading` attrs.level 1-6, `bulletList`/`orderedList` → `listItem` → `paragraph`, `codeBlock` attrs.language; unverified);
  - (G3) `comment_on="PROJ-12"`: `POST /rest/api/3/issue/{key}/comment` with `{body: ADF}`, link `https://{site}/browse/{KEY}?focusedCommentId={id}` (unverified);
  - (G3) `labels=` as label names in `fields.labels`.
- **Pattern:** a shared ADF builder in `lib`, also used by Confluence (§B4: "reuses Jira's rich-text builder"). Today the ADF is an inline list comprehension, so no builder exists yet.

**`vidbyte/lib/outputs/google_chat.py`** (53 lines).
- **Today:** `GoogleChatOutput(*, webhook_url=None, render=None)`, env `GOOGLE_CHAT_WEBHOOK_URL`. Text = `truncate(chat_text, GOOGLE_CHAT_TEXT_MAX_CHARS=8_000)` with `"<users/"` replaced by `"＜users/"`. Headers `{"content-type": "application/json; charset=UTF-8"}`, body `{"text": ...}` (49). `# @intent google-chat-text-cannot-mention-all` (44).
- **Will change (conditional):** `markupSyntax: MARKUP_SYNTAX_MARKDOWN`, only if Google's docs show that incoming webhooks accept it (request §C). Otherwise the file is unchanged and the item is listed as a live check.
- **Pattern:** as above.

### 2.3 Work group 2: webhook

**`vidbyte/lib/outputs/webhook.py`** (57 lines).
- **Today:** `WebhookOutput(*, url: str | None = None, render=None)`, env `VIDBYTE_OUTPUT_WEBHOOK_URL`, `https_url(credential)`.
  - `send` (38-44): body `{"agent": reply.sender, "title": content.title, "body": content.body, "structured": WebhookOutput._structured_json(reply.structured)}`, headers `{}`, no `link_path`.
  - `# @intent webhook-payload-is-plain-json` (40: "nothing is cut or signed").
  - `_structured_json(structured: object) -> object` (47-54): a pydantic `BaseModel` gives `model_dump(mode="json")`; a dict, list, str, int, float, or bool passes through; anything else gives `None`.
  - Header (line 6): "Add a payload key here only when every receiver can ignore it".
- **Will change:**
  - `headers=`: fixed headers, hidden in `repr` and never logged;
  - `payload=`: a callable that builds the JSON. The default envelope stays frozen (backward compatibility).
  - `secret=`: Standard Webhooks signing. Headers `webhook-id`, `webhook-timestamp`, and `webhook-signature: v1,<base64 HMAC-SHA256 over "{id}.{timestamp}.{body}">`; the secret is `whsec_` plus base64 (unverified).
- **Pattern:**
  - `OutputArguments` checks that never echo secret values;
  - lowercase header keys (an `OutputRequest` rule);
  - `# @intent` on `__init__` once a parameter is named `secret` (A002);
  - `payload=` validated like `render=` through `OutputArguments.optional_callable`, which is typed for `render`'s signature.

**`vidbyte/lib/outputs/delivery.py` and `vidbyte/lib/http/transport.py`:** see §2.0 for exact bytes.

### 2.4 Work group 3: comments and labels

**`vidbyte/lib/outputs/github.py`** (58 lines).
- **Today:** `GitHubIssueOutput(*, repo: str, labels: Sequence[str] = (), token: str | None = None, render=None)` (40).
  - `repo` must match `GITHUB_REPO_PATTERN` `[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+`; `labels` goes through `texts`. Env `GITHUB_TOKEN`.
  - `send` (46): URL `f"{GITHUB_API_URL}/repos/{repo}/issues"`. Headers `{"authorization": f"Bearer {token}", "accept": "application/vnd.github+json", "x-github-api-version": GITHUB_API_VERSION("2026-03-10")}`. Body `{"title": single_line(title, 250), "body": truncate(body, GITHUB_BODY_MAX_CHARS=65_536), "labels": list(labels)}`. `link_path=("html_url",)` (54).
  - `# @intent github-issue-target-is-fixed` (48). Header: bump `GITHUB_API_VERSION` after checking the changelog.
- **Will change:**
  - (G3) `comment_on=<issue or PR number>`: `POST /repos/{repo}/issues/{n}/comments` `{body}`, linking to `html_url`;
  - (G5) sticky comment: hidden marker `<!-- vidbyte:<key> -->`, list comments (paginated) and then PATCH `/repos/{repo}/issues/comments/{id}` or POST;
  - (G5) one-issue-per-key: `GET /repos/{repo}/issues?labels=vidbyte:<key>&state=open`, then comment on the match or create a new issue.
  - All endpoint facts are from request §C and unverified.
- **Pattern:** keyword-only option; the target fixed at construction (INV-3); GET and PATCH through the extended `OutputHttp`.

**`vidbyte/lib/outputs/linear.py`** (54 lines).
- **Today:** `LinearIssueOutput(*, team_id: str, api_key: str | None = None, render=None)` (38). `team_id` goes through `identifier` (UUID). Env `LINEAR_API_KEY`.
  - URL `LINEAR_GRAPHQL_URL` (`https://api.linear.app/graphql`), headers `{"authorization": api_key}` (no Bearer).
  - Body `{"query": LINEAR_ISSUE_CREATE_MUTATION, "variables": {"input": {"teamId", "title": single_line(250), "description": content.body}}}`, with no cap. `link_path=("data","issueCreate","issue","url")` (50).
  - `# @intent linear-success-needs-the-issue-link` (45). The mutation is `mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { url } } }` (constants:98).
- **Will change:**
  - `comment_on="ENG-123"` via `commentCreate(input: {issueId, body})` → `comment { url }`. Whether an identifier is accepted as `issueId` is unverified.
  - `labels=` (label ids) as `labelIds` on `issueCreate` (unverified).
- **Pattern:** the GraphQL text as a constant; the link checked through `link_path`.

**`vidbyte/lib/outputs/jira.py`:** see §2.2 for `comment_on` and `labels`.

**`vidbyte/lib/outputs/notion.py`** (60 lines).
- **Today:** `NotionPageOutput(*, parent_page_id: str, api_key: str | None = None, render=None)` (40). `parent_page_id` goes through `identifier`. Env `NOTION_API_KEY`.
  - URL `NOTION_PAGES_URL` (`https://api.notion.com/v1/pages`). Headers `{"authorization": f"Bearer {key}", "notion-version": NOTION_API_VERSION("2026-03-11")}`.
  - Body `{"parent": {"type":"page_id","page_id": id}, "properties": {"title": {"title": [{"text": {"content": single_line(250)}}]}}, "markdown": body.replace("<mention-", "＜mention-")}`. `link_path=("url",)` (57).
  - `# @intent notion-markdown-cannot-mention-people` (47).
- **Will change:** add to an existing page instead of creating a child page: `PATCH /v1/pages/{page_id}/markdown`. The operation name is unconfirmed (request §C).
- **Pattern:** a PATCH via the extended `OutputHttp`; the mention neutralizing kept.

### 2.5 Work group 4: new connectors (all five are built, per request §C)

- **GitLab issue and MR comment:** new `vidbyte/lib/outputs/gitlab.py`.
  - `PRIVATE-TOKEN` header, `POST /api/v4/projects/:id/issues` (`title`, `description`, `labels`) → `web_url`.
  - MR notes `POST /projects/:id/merge_requests/:iid/notes`, and `host=` for self-hosted GitLab.
  - All unverified (request §C).
  - Pattern: `github.py`. Name any header constant without a `_TOKEN_` segment (S105).
- **GitHub job summary:** a new module.
  - Appends Markdown to the file named by `$GITHUB_STEP_SUMMARY` (1 MiB per step, unverified). No HTTP and no credential.
  - Nothing in `vidbyte/` reads `GITHUB_STEP_SUMMARY` today (grep).
  - **File-append helpers that exist:**
    - `vidbyte/lib/tools/filesystem/backends/local.py:32` `LocalFileSystemBackend.append_text(self, path: Path, content: str, *, encoding: str, create_parents: bool, newline: str | None = None) -> None`. It is synchronous, uses `path.open("a", ...)`, imports only `vidbyte.lib.*`, and is the only file on the S061 allowlist.
    - `vidbyte/harnesses/stores/file.py:56` `await asyncio.to_thread(self._append, record)` with `self._path.open("a", encoding="utf-8", errors="backslashreplace", newline="\n")`. It is in the harnesses layer, so `lib` cannot import it (A006).
    - Email's precedent: a module-level `_SMTP_EXECUTOR = ThreadPoolExecutor()` plus `run_in_executor` (`email.py:30,72`). This is the INV-19 rationale: Python 3.11 `asyncio.run` joins the default executor with no timeout.
- **Confluence page:** a new module.
  - `POST /wiki/api/v2/pages` with `spaceId` (numeric), optional `parentId`, `title`, and `body: {representation: "atlas_doc_format", value: <JSON string>}`.
  - The same Atlassian email and token as Jira (unverified). Pattern: `jira.py` (site pattern, Basic auth), plus the shared ADF builder.
- **Typefully drafts:** a new module. A v2 API key; it creates drafts only and never sends `publish_at`. The request shape is unverified (request §C, 🧪).
- **HubSpot task:** a new module. `POST /crm/v3/objects/tasks` with `hs_task_subject`, `hs_task_body`, and `hs_timestamp` (required), using a private-app token. The response has an id but no URL, so `link_path=()` gives a SENT receipt with no URL (unverified).
- **For every new module:**
  - an A001 header in the `"""FILE:` style;
  - a `BaseOutput` subclass with only `__init__` and `send` (README steps 94-106);
  - a `destination` member;
  - an env var in `OUTPUT_CREDENTIAL_ENV_VARS` (except the job summary; see §4 N-6);
  - exports in three places;
  - a dated README row.

### 2.6 Exports and the public contract
- **`vidbyte/lib/outputs/__init__.py`** (46 lines). Exports `BaseOutput`, `OutputArguments`, `OutputHttp`, `OutputSmtp`, `OutputText`, and the 11 connectors; its header says the helpers are not root exports. It will add the new connector classes.
- **`vidbyte/agents/output/__init__.py`** (52 lines). `__all__` has 18 names: `DeliveryReceipt`, `DeliveryStatus`, the 11 connectors, `OutputConnector`, `OutputContent`, `OutputDeliveryError`, `OutputDestination`, `OutputDispatcher`. It will add the new connectors.
- **`vidbyte/__init__.py`** (1336 lines; only the header and the output sections were read). Header line 20 says "the eleven destination connectors (SlackOutput through WebhookOutput)". The import block from `vidbyte.agents.output` is at 266-285, the `__all__` entries at 995-1012, and `__version__ = "0.2.1"`. It will add the new names and update line 20. Commit before regenerating.
- **`contracts/sdk-public-api.json`** is regenerated by script and never hand-edited.

### 2.7 Files that must not change (request constraints, confirmed in code)
- **`vidbyte/agents/base.py`** (`_generate_reply`; S008 zero headroom).
- **`vidbyte/agents/output/dispatcher.py`** (110 lines). `_deliver_one` runs `asyncio.wait_for(connector.send(reply, content), OUTPUT_DELIVERY_DEADLINE_SECONDS)` and reads the module global at call time; a `TimeoutError` gives FAILED `network`. The request says no dispatcher change is needed.
- **`vidbyte/agents/output/connector.py`** (75 lines; the `OutputConnector` Protocol: `destination`, `render`, `async send`).
- **`vidbyte/lib/errors/base.py`** (`OutputDeliveryError`, lines 184-224). Its `repair_approaches` third item lists the codes that "may already have been delivered". It changes only if a new code or a new partial-write meaning is introduced (§4 N-9).
- **`vidbyte/lib/outputs/email.py`** (75 lines). Email-in is docs only.
  - `EmailOutput(*, to, host, username, password=None, sender=None, port=SMTP_STARTTLS_PORT, render=None)`.
  - The message sets only `From`, `To`, `Subject` (`single_line(title, 250)`), and a plain-text body (67-71), so it never adds `Auto-Submitted` or `Precedence`. `render=` can already set a fixed subject.

## 3. Tests that cover those files

### 3.1 Framework and commands
- **Framework:** pytest with pytest-asyncio and `@pytest.mark.asyncio`. Per first-batch spec §13, `pyproject.toml` pins pytest 8.3.5 and pytest-asyncio 1.3.0 with `--strict-config --strict-markers`. The pin versions themselves were not re-read and are unverified.
- **Run the pack:** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors`. **Run everything:** `python scripts/run_ci.py`.
- **Headers:** every test file needs an A001 header. The pack uses `"""FILE: tests/...` with `FUNCTION INVENTORY` and `WHAT NOT TO DO IN THIS FILE` sections as well.
- **No real network.** Every request stops at `HttpTransport._send_once` or at `httpx.MockTransport`.
- **Other tests that touch the transport:**
  - `tests/test_web_operation_client_retry.py` (fake `_send_once(self, client, **kwargs)`, line 32);
  - `scripts/test-async-http-transport.py`, a standalone script that calls the real `_send_once` with explicit keywords at line 115. It is not part of `run_ci` (unverified).

### 3.2 `tests/features/agent_output_connectors/`: files, purpose, fixtures

- **`conftest.py`** (116 lines). Its fixtures:
  - **`isolated_output_env`** (autouse) deletes **only** the 11 `OUTPUT_ENV_VARS`.
  - **`output_api`** imports `vidbyte.agents.output`; **`output_constants`** and **`dispatcher_module`** import their modules.
  - **`fake_http`** (69-82) patches `HttpTransport._send_once` with `fake_send(self, client, **kwargs)`, which calls `HttpScript.respond(kwargs)`, and patches `transport_module.asyncio.sleep` with a no-op.
  - **`fake_smtp`** patches `delivery.smtplib.SMTP` and `SMTP_SSL` and refuses `socket.create_connection`.
  - **`httpx_destination`** (96-106) replaces `transport_module.httpx.AsyncClient` with a real client over `httpx.MockTransport`.
  - **`http_case`** and **`any_case`** parametrize over `HTTP_DESTINATION_KEYS` and `ALL_DESTINATION_KEYS`.
- **`factories.py`** (380 lines).
  - **Credentials and ids:** `SECRET_MARKER = "S3CRET"` and credentials `SLACK_URL`, `DISCORD_URL`, `TEAMS_URL`, `GOOGLE_CHAT_URL`, `TELEGRAM_TOKEN`, `GITHUB_TOKEN`, `LINEAR_KEY`, `JIRA_TOKEN`, `NOTION_KEY`, `WEBHOOK_URL`, `SMTP_PASSWORD` (37-47). Ids and links at 49-56.
  - **`OUTPUT_ENV_VARS`** (59-71).
  - **`ConnectorCase(key, class_name, parameter, env_var, credential, options, host, success, wire_secret)`** with `build` and `build_without_credential` (74-95). `CONNECTOR_CASES` (98-110) has 11 rows, keyed by `OutputDestination` value.
  - **Key tuples:** `HTTP_DESTINATION_KEYS` (10 keys) and `ALL_DESTINATION_KEYS` (also includes email) (111-112).
  - **`HttpScript`** (115-148):
    - `answer(url_fragment, *responses, repeat=False)` queues responses. A response is `(status, body)`, an exception, or `HANG`.
    - `sends` records every kwarg plus `headers` and `json_body` after a JSON round-trip.
    - `sends_to(fragment)` filters by URL fragment. A route is the first one whose fragment is in the URL and that still has responses.
    - It **always returns `HttpResponse(..., headers={})`**, so it cannot script response headers such as GitHub's `Link` pagination header.
  - **Other fakes:** `HttpxRequests` (151-), `SmtpScript`, `ScriptedSmtp`, `ScriptedSmtpSsl`, `AnswerRunner`, `ScriptedConnector`, `build_reply`, `receipt_rows`.
- **`test_output_connectors_wire_contract.py`** (373 lines). It proves each connector's exact request and caps.
  - **`WIRE_ROWS`** (53-63) holds the exact URL, headers, and `json_body` per HTTP destination: Slack `{"text": CHAT}`; the full Teams card; Google Chat `{"text": CHAT}`; Telegram `/sendMessage` with `{"chat_id","text"}`; Jira paragraphs; Notion; and the webhook envelope with `"structured": None`.
  - **`test_each_http_connector_sends_its_documented_request`** (92-107) asserts `[send] = fake_http.sends` (exactly one request), `method == "POST"`, lowercase headers, `timeout_seconds == 10.0`, and `max_response_bytes == 1_000_000`.
  - **`CAPPED`** (67-74): Slack `body["text"]` 40,000; Discord; Teams `attachments[0].content.body[0].text` 7,000; Google Chat; Telegram 4,096; GitHub. **`UNCAPPED`** (75-79).
  - **Link test:** the created-object-link test (110-131) covers Linear errors, GitHub with a list body giving FAILED `invalid_response`, and others.
  - **Mention test** (about 150-156): exact Slack escaped text, Google Chat `＜users/`, and `"parse_mode" not in telegram["json_body"]`.
  - **Slack escape and cap test** (217), and the Jira 32,767 paragraph test (222-229).
  - **Title tests** (246-263, 317-322) and the webhook `structured` tests (about 346).
  - Uses `fake_http` and `output_api`.
- **`test_output_connectors_http_failures.py`** (150 lines). It proves how failures become receipts.
  - `ATTEMPT_TABLE`: 429 is retried at most twice; 408/409/425/5xx are tried once. Also the success range, the mixed-failure message, and `TOKEN_TABLE`.
  - The redirect test (GitHub 302 gives FAILED `http_302` and the Location host is never contacted) and the size-ceiling test both use `httpx_destination`.
- **`test_output_connectors_configuration.py`** (234 lines). It covers the `INVALID_ARGUMENTS` rows, invalid `outputs` values, env-var resolution, and the exact missing-credential message. `test_every_connector_reads_its_own_environment_variable` looks for `wire_secret` in the URL or in header values.
- **`test_output_connectors_security.py`** (201 lines). It scans every surface for `SECRET_MARKER`, checks that `repr == f"{class_name}(credential='***')"` for every case, and checks that each credential travels only in its own request.
  - The `URL_CREDENTIAL_HOSTS` httpx-log test (129-) uses the real `_send_once` over `MockTransport` with `caplog` INFO on the root logger.
  - It also covers model output not being able to steer delivery, and path-shaped repo or site values being rejected.
- **`test_output_connectors_contract.py`** (328 lines). Its fixed lists and their tests:
  - `ROOT_NAMES` (35-54, 18 names); `CONNECTOR_NAMES = ROOT_NAMES[7:]`; `NOT_ROOT_NAMES` (56); `LIB_OUTPUT_MODULES` (57); `AGENT_OUTPUT_MODULES` (58).
  - `assert len(output_api.__all__) == 18` (68).
  - The exact ordered `OutputDestination` value list (98).
  - Operational constants (216-228), including `OUTPUT_CREDENTIAL_ENV_VARS ==` the `CONNECTOR_CASES` env vars and `sorted(values) == sorted(OUTPUT_ENV_VARS)`.
  - The layering test (263-282) globs `vidbyte/lib/outputs/*.py` (direct children only) plus `{enums,constants,dataclasses}/outputs.py`. It forbids non-lib `vidbyte` imports and `httpx`, `requests`, `aiohttp`, `http.client`, and `urllib.request`.
  - The agent-side import test (285-299).
  - The docs test (307-313): **every `OUTPUT_ENV_VARS` name must appear in a README table row that also contains `"https://"` and `"2026-10-11"`**.
  - REPO_MAP headings (316-322) and README ≤ 40,000 characters (325-328).
- **`test_output_connectors_dispatch.py`** (316 lines). It covers the skip rule and shaping. `SHAPING_CASES` asserts `slack["json_body"] == {"text": slack_text}` (125) and the GitHub `{"title","body","labels": []}` body. The render test asserts `{"text": "# Heading\nrest"}` (148). It also covers concurrency, the deadline (patching `dispatcher_module`), the diagnostic packet, resend, and two replies with `json_body["text"]` (315).
- **`test_output_connectors_acceptance.py`** (177 lines). The spec snippet asserts `slack["json_body"] == {"text": f"{BUG_TITLE}\n\n{BUG_BODY}"}` (97). It also covers partial failure, schema violation, and sessions, using `tests/agent_test_support.py` (`build_test_agent`, `bind_test_runner`).
- **`test_output_connectors_agent_wiring.py`** (221 lines). `_slack_texts` reads `json_body["text"]` (61-62); assertions at 96, 110, 132, and 178. It also covers forks, restore, Jev, CodingAgent, cancellation, drained follow-ups, and the max_iterations skip.
- **`test_output_connectors_email.py`** (195 lines). It covers the SMTP sequence, failures, QUIT, the sync `run` deadline (which needs the dedicated executor), and sender rules.
- **`FEATURE.md`** (111 lines) holds the contract, the INV-* invariants, and the Test Suite Map.
- **`README.md`** (35 lines). Its Non-Goals line 12 reads "Do not test OAuth destinations, YAML configuration, CLI commands, HMAC signing, or per-user mention suppression."

### 3.3 Seams for the new behavior (facts only)
- **Multi-request sends** (sticky comment, one-issue-per-key, Notion append) can be scripted with `HttpScript.answer` per URL fragment, and `sends_to` reads them back in order.
- **Response headers** (pagination `Link`) cannot be scripted until `HttpScript.respond` can return headers; today it hard-codes `headers={}` (factories.py:148).
- **Exact signed bytes.** `HttpScript.respond` records kwargs and round-trips `json_body` through `json.dumps`/`loads`, so a test of exact signed bytes must read whatever kwarg carries the bytes. The `httpx_destination` MockTransport handler sees the real request bytes.
- **Job-summary tests** need `tmp_path` and `monkeypatch.setenv("GITHUB_STEP_SUMMARY", ...)`. The autouse `isolated_output_env` does not delete `GITHUB_STEP_SUMMARY`, and per request §C research (unverified) GitHub runners set it.
- **The deadline** is shortened by setting `dispatcher_module.OUTPUT_DELIVERY_DEADLINE_SECONDS`.

## 4. Notes for the spec author

- **N-1. The request changes default wire shapes that first-batch tests pin exactly.**
  - The pinning tests:
    - `WIRE_ROWS` Slack, Teams, Google Chat, Telegram, and Jira (`test_output_connectors_wire_contract.py:54-61`);
    - `CAPPED` Slack, Teams, and Telegram (68-72);
    - the mention test (152-156);
    - the Slack cap test (217) and the Jira paragraph test (222-229);
    - `test_output_connectors_dispatch.py:125,148,315`;
    - `test_output_connectors_acceptance.py:97`;
    - `test_output_connectors_agent_wiring.py:61-62`.
  - The request asks for a Slack markdown block, Telegram `sendRichMessage`, a bold Teams title with full width, Jira rich ADF, and (conditionally) Google Chat `markupSyntax`.
  - The backward-compatibility constraint covers constructors, env vars, enum values, receipts, error codes, and the webhook envelope, **not chat wire shapes**. So S2 must edit first-batch tests, and pipeline.md's no-test-edit check across merges must allow that.
- **N-2. Five new connectors break the pack's fixed counts.**
  - `len(output_api.__all__) == 18` (contract.py:68).
  - The exact ordered `OutputDestination` list (98).
  - `OUTPUT_CREDENTIAL_ENV_VARS` equality with `CONNECTOR_CASES` (224-225).
  - The docs test requires `"2026-10-11"` in each env-var row (311). Rows re-checked or added on 2026-10-13 fail unless that test changes; this also applies to the docs-pass edits of the Discord, Teams, Telegram, and Jira rows if their date changes.
- **N-3. The webhook id cannot be the idempotency key.** Request §B2 says "the request's existing idempotency key doubles as `webhook-id`". The code shows `idempotency_key=uuid4().hex` is created inside `OutputHttp.post` (`delivery.py:75`) and used only by `_require_idempotency_guard` (`transport.py:23-26`); it is never sent on the wire. Request §C already corrects this.
- **N-4. No parameter carries signed bytes.** Signing must cover the exact body bytes. Today `_send_once` serializes `json.dumps(json_body).encode("utf-8")` itself (`transport.py:79`), with default separators and `ensure_ascii`. Neither `HttpTransport.request` nor `_send_once` nor `OutputRequest` has a parameter for pre-serialized bytes. AGENTS.md Style 5 says to add the option to `HttpTransport` rather than build a variant.
- **N-5. `OutputHttp` has no read or update path.**
  - Request §B5 and §C: `OutputHttp` "returns the response JSON to the connector". Code: `OutputHttp.post` returns only a `DeliveryReceipt` (`delivery.py:56-93`) and hard-codes `"POST"` (67). `OutputRequest` has no method field (`dataclasses/outputs.py:74-82`), and `_link` cannot index a JSON list or use a suffix (106-120).
  - GitHub's list endpoints return arrays. The pack already pins that a JSON-list body to the create call is FAILED `invalid_response` (`wire_contract.py:120`).
  - PATCH is not in `_IDEMPOTENT_METHODS`, so retrying it needs an `idempotency_key` (`transport.py:20-26`).
- **N-6. The job summary has no credential, but the code assumes one.**
  - `OUTPUT_CREDENTIAL_ENV_VARS` is keyed by every destination (`constants/outputs.py:49-61`), and `OutputArguments.credential` hard-indexes it (`base.py:38`); its message says "Missing credential for …".
  - `BaseOutput.__repr__` always prints `credential='***'` (`base.py:130-131`).
  - The pack's `ConnectorCase` needs `parameter`, `env_var`, `credential`, and `wire_secret`. The security, configuration, and repr tests iterate `ALL_DESTINATION_KEYS`.
  - README step 2 ("Add its environment variable to `OUTPUT_CREDENTIAL_ENV_VARS`") assumes a credential.
- **N-7. Writing the summary file from async code meets several rules.**
  - S047 (ASYNC230) flags blocking `open()` in `async def`.
  - S061 flags bare `open(<non-literal>)` and `Path.write_text` and similar; its allowlist is only `lib/tools/filesystem/backends/local.py`.
  - S041 needs an explicit encoding.
  - First-batch INV-19 forbids `asyncio.to_thread` for SMTP because of `asyncio.run`'s default-executor join (`email.py:26-30`); the same reasoning would apply to a file write.
  - `LocalFileSystemBackend.append_text` exists in `lib` (`local.py:32-36`) and is synchronous.
- **N-8. Multi-request sends can outrun the dispatcher deadline.**
  - Request §C says "a connector may make more than one request inside `send()` without a dispatcher change".
  - Code: one 35 s `wait_for` covers the whole `send` (`dispatcher.py`; `OUTPUT_DELIVERY_DEADLINE_SECONDS = 35.0`). Each request may take up to 3 attempts × 10 s plus 1.5 s of backoff, and constants line 7 says the deadline must stay above one such request path.
  - A read, then pagination, then a write can pass 35 s. A cancelled write may already have landed (it would be FAILED `network`).
- **N-9. Multi-request flows give existing error codes new meanings.** `OutputDeliveryError`'s resend caution (`errors/base.py` about 184-224) and both READMEs list the codes that "may already have been delivered". A failed list call (nothing written) and a failed write after a successful read now share those codes. Unverified whether the spec needs to distinguish them.
- **N-10. New signing and header parameters must not reuse value-echoing checks.** `OutputArguments.text`, `texts`, `matching`, `address`, and `identifier` echo the value in their error (`base.py:64,71,86,100,107`). `OutputRequest.headers` rejects non-lowercase keys (`dataclasses/outputs.py:86-87`), so a user-supplied `Authorization` key fails at send time as FAILED `unexpected:ConfigurationError` unless it is normalized earlier.
- **N-11. String-constant and helper names trip lint.** S105 (S054) flags string constants with `token` or `secret` name segments; examples are the `whsec_` prefix and the `PRIVATE-TOKEN` header name. A002 needs `# @intent` on any function that mentions `secret`, `request`, `send`, or `fetch`. S012 forbids naming a helper `request`.
- **N-12. The first batch ruled out several things this run builds.** First-batch spec non-goals: NG-7 (HMAC-signed webhooks; Q-3 default "no"), NG-8 (Slack blocks, Adaptive Card layouts beyond one TextBlock, Telegram `parse_mode` or rich messages, Notion block trees, Jira markdown-to-ADF, threads), NG-10 (GitLab, Asana, Webex), and NG-12 (self-hosted endpoints other than the webhook). The pack README's Non-Goals line 12 also says "Do not test … HMAC signing". This run reverses all of them, so these docs need updating.
- **N-13. The docs pass edits a README that is partly correct already.**
  - **Teams:** README line 110 says only "Anyone" flows work. The request wants "Microsoft now labels 'Anyone' a Legacy setting", plus the group-chat template and the email fallback.
  - **Jira:** "tokens expire within 365 days" is already at README line 119.
  - **Telegram:** `chat_id="@name"` is already accepted (`telegram.py:40-41`).
  - **Webhook:** the README has no webhook section. The Apps Script 302 behavior is pinned by the redirect test (`http_failures.py`), which yields FAILED `http_302`.
- **N-14. The spec corrections land in an opaque file.** The §9.2(b) corrections target `docs/spec/agent-output-connectors/spec.md:806-854`. None of Zendesk, Shopify, Greenhouse, Bandwidth, Bitbucket, Relay.app, OneNote, LINE Notify, Typefully, Buffer, Apprise, or Threads appears there today; HubSpot appears only as "notes" (836).
- **N-15. No Markdown or ADF builder exists.** Confluence is meant to reuse "Jira's rich-text builder", but `jira.py:67` holds an inline comprehension. A shared builder would be new code in `vidbyte/lib/` (Style 5). No Markdown dependency exists, and request Q4 says do not add one.
- **N-16. Every vendor fact in request §C is unverified.** That covers endpoints, caps (Slack 12,000; Telegram 32,768; Discord `thread_name` 100), header names, the GraphQL fields, the Notion operation name, and the Typefully and HubSpot shapes. The spec author must confirm each from official docs and cite the URL and the date read.
- **N-17. vidbyte-gates.md is wrong for the SDK.**
  - It says the lint pass line is `AGENT-LINT: PASS`. The SDK prints `SDK-LINT: PASS` (`lint/core/report.py:58`).
  - It describes the full gate as `pip install -e .[dev]` once, then `run_ci --stage source`, then `run_ci`. The SDK's AGENTS.md names only `python scripts/run_ci.py`; the PYTHONPATH split comes from the field guide.
- **N-18. Other unverified items.**
  - Whether Ruff ASYNC230 matches `Path.open`.
  - Whether `HttpResponse.headers` keys are lowercased by httpx.
  - The `lint/mypy.ini` settings.
  - That `scripts/test-async-http-transport.py` is outside `run_ci`.
  - The 1 MiB summary limit and the runner setting `GITHUB_STEP_SUMMARY`.
  - Any vidbyte-cli #166 usage beyond the constructors, the root `OutputDispatcher`, and the receipt shape. That PR is in another repo and was not opened.
