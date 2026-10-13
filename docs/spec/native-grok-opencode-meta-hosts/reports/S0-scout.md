# S0 scout report: native-grok-opencode-meta-hosts

- **Stage:** S0 scout, read-only.
- **Base:** `aa8c380c4cd1d5791526dd545f5ef1020b28a5cc`.
- **Output:** `docs/spec/native-grok-opencode-meta-hosts/context/code-map.md`.
- **What I did and did not do:** no commits, installs, gate runs or vendor CLIs. I read nothing under `docs/` except `request.md`, read no credential files, and did not open the codex-host or claude-host worktrees.

## Planned list

These came from the request's "Implementation hints" (request.md:258-280), the orchestrator briefing questions, and AGENTS.md's instruction to read REPO_MAP.md and folder READMEs:

1. **Rules:** AGENTS.md (and CLAUDE.md), REPO_MAP.md, and the field guide index plus its relevant entries.
2. **Lint:**
   - the lint rules A001-A009, C002, C006-C008, C012, C015, C016 and the S-series (S011-S064);
   - `lint/baseline.json`, `lint/ruff.toml` and `lint/mypy.ini`;
   - `lint/core/{discovery,ruff,report,public_api_contract}.py`;
   - the `.semgrep` policy.
3. **CI:** `scripts/run_ci.py`, `.github/workflows/*`, `pyproject.toml`, `scripts/generate-sdk-public-api.py`, `contracts/`.
4. **Tool layer:**
   - `vidbyte/tools/{base,executor,catalog}.py`, `vidbyte/lib/dataclasses/{tools,security}.py`;
   - `vidbyte/tools/builtins/{__init__.py,sessions/*,bash.py}`, `vidbyte/tools/toolsets/*`;
   - `vidbyte/lib/registries/components.py`.
5. **MCP:**
   - `vidbyte/tools/mcp/{transport,client}.py` and its README;
   - `vidbyte/mcp_server/{handlers,__init__,__main__,schema}.py`, `server/core.py`, `server/handlers/tools_{call,list}.py` and the MCP server README.
6. **Codex agent:**
   - `vidbyte/agents/codex/{transport,failures,agent,tools}.py` and its README;
   - `vidbyte/lib/{dataclasses,enums,constants}/codex.py`.
7. **Failures and errors:** `vidbyte/lib/enums/{failure,__init__}.py`, `vidbyte/lib/errors/base.py`, `vidbyte/harnesses/errors.py`.
8. **HTTP and redaction:** `vidbyte/lib/http/{transport,parser}.py`, `vidbyte/harnesses/serialization.py`, `vidbyte/lib/util/credential_keys.py`, `vidbyte/lib/dataclasses/failure.py`, and the #993 and #990 commits.
9. **Models:** `vidbyte/lib/registries/models.py`, `vidbyte/lib/enums/model_provider.py`.
10. **Public surface and harnesses:** `vidbyte/__init__.py`, `vidbyte/harnesses/{README.md,__init__.py}`.
11. **Tests:**
    - `tests/features/coding_agent/{README.md,conftest.py,test_bash_tool_process_bounds.py}`;
    - `tests/test_mcp_stdio_transport.py`, `tests/test_codex_tools.py`, `tests/test_http_transport_content_type.py`;
    - the enumerating tests.

## Files actually read

**In full:**
- AGENTS.md, CLAUDE.md, `request.md` (802 lines).
- Field guide entries: init, cli-backed-source-integrations, strict-config-dataclasses, class-bound-helpers, model-facing-tool-contracts, provider-api-contracts, comment-format, blocking-lint-invariants, declarative-config-resolution, review-scope, local-ci-verification.
- `vidbyte/tools/mcp/transport.py`, `vidbyte/tools/mcp/client.py`, `vidbyte/tools/mcp/README.md`.
- `vidbyte/mcp_server/handlers.py`, `vidbyte/mcp_server/__init__.py`, `vidbyte/mcp_server/__main__.py`, `vidbyte/mcp_server/server/core.py`, `vidbyte/mcp_server/server/handlers/tools_call.py`, `vidbyte/mcp_server/server/handlers/tools_list.py`, `vidbyte/mcp_server/README.md`.
- `vidbyte/agents/codex/transport.py`, `vidbyte/agents/codex/failures.py`.
- `vidbyte/tools/builtins/__init__.py`, `vidbyte/lib/http/parser.py`, `vidbyte/lib/http/transport.py`.
- `vidbyte/harnesses/README.md`, `vidbyte/harnesses/__init__.py`.
- `vidbyte/lib/enums/failure.py`, `vidbyte/lib/enums/codex.py`, `vidbyte/lib/enums/__init__.py`.
- `vidbyte/tools/base.py`, `vidbyte/tools/executor.py`, `vidbyte/lib/dataclasses/security.py`, `vidbyte/tools/toolsets/__init__.py`.
- `scripts/run_ci.py`, `pyproject.toml`, `lint/ruff.toml`, `lint/mypy.ini`, `lint/baseline.json`.
- `lint/rules/s012_explicit_outbound_timeout.py`, `contracts/README.md`.

**In part (headers, signatures and the line ranges cited in the code map):**
- `vidbyte/__init__.py`, `vidbyte/agents/codex/README.md`, `vidbyte/agents/codex/agent.py`, `vidbyte/agents/codex/tools.py`.
- `vidbyte/lib/dataclasses/codex.py`, `vidbyte/lib/dataclasses/tools.py`, `vidbyte/lib/dataclasses/failure.py`.
- `vidbyte/lib/constants/codex.py`, `vidbyte/lib/registries/models.py`, `vidbyte/lib/registries/components.py`, `vidbyte/lib/errors/base.py`.
- `vidbyte/harnesses/errors.py`, `vidbyte/harnesses/serialization.py`.
- `vidbyte/tools/builtins/bash.py`, `vidbyte/tools/builtins/sessions/{_base,checkpoint,batch_fork,descriptions}.py`, `vidbyte/tools/toolsets/coding.py`, `vidbyte/tools/README.md`.
- `REPO_MAP.md`.
- Lint rules A001, A002, A003, A006, A007, C012, C015, C016, S009, S010, S011, S013, S014, S016, S017, S021, S025, S056, S058, S060, S063, S064, C003, C009, plus `lint/core/{discovery,mypy,report,public_api_contract}.py` and `lint/run.py`.
- `scripts/generate-sdk-public-api.py`, `contracts/sdk-public-api.json`.
- `tests/features/coding_agent/{README.md,conftest.py,test_bash_tool_process_bounds.py}`, `tests/features/sdk_model_catalog/README.md`.
- `tests/test_mcp_stdio_transport.py`, `tests/test_codex_tools.py`, `tests/test_http_transport_content_type.py`, `tests/test_codex_failure_recovery.py`, `tests/test_session_failures.py`.
- `.semgrep/typed-mapping-boundary-policy.yml`, `.github/workflows/{ci,static-policy}.yml`.

**Untrusted research folder:**
- Listing only, plus the 59-byte `muse-shim-muse.cmd.txt`. Nothing was executed and no instructions were followed.

**Not read:** `tests/test_mcp_studio_server.py`, the full `__all__` body of `vidbyte/__init__.py`, and the remaining field guide entries (runtime-boundaries, fallback-coordination, prebuilt-agents and others).

## What the hints got wrong or left incomplete

1. **"opencode … using `httpx`"** (request.md:124,153,731). S011 has a baseline of 0 and bans importing `httpx` outside `vidbyte/lib/http/transport.py` and `vidbyte/tools/mcp/transport.py` (`lint/rules/s011_raw_http_client_ownership.py:22-23`). The route is `HttpTransport`, which has no async SSE and no query-parameter argument.
2. **"Copy the `builtins/sessions/` layout"** (request.md:92,261). The folder copies three kinds of baseline debt:
   - the A001-failing "Context Protocol Header";
   - raw `{exc}` text in error results (`_base.py:90`, `batch_fork.py:56`; S017 scope);
   - S062 adjacent literals in `descriptions.py`.

   Its `_caught` helper is synchronous.
3. **"`mcp/transport.py` … may be reusable for ACP and MSP framing"** (Q-3). Reuse is blocked in three ways:
   - it discards notifications (`:416-418`);
   - it misroutes server-initiated requests (`:419-450`);
   - `request()` has no per-call timeout keyword, so S012 fails every new call site.

   The layering, on the other hand, is allowed by A006.
4. **"`vidbyte/agents/codex/` … transport isolation"**. `CodexTransport` owns no subprocess; the `openai-codex` SDK does. There is no process-tree or kill helper to copy.
   - The only process-group kill is POSIX `os.killpg` in `bash.py` and `setup_commands.py`.
   - On Windows only the direct child is killed (`bash.py:9`).
5. **"Each new FailureCode may need a row"** (`constants/codex.py:95-174`). Only `codex.*` codes are forced to have a row, by a test (`tests/test_codex_failure_recovery.py:192-202`). No other table exists.
6. **"`models.py:90-107`"**. The env vars are at :90-94, but the endpoints are at :107-111, so GLM (:108) and META (:111) fall outside the cited range.
7. **"`vidbyte/lib/dataclasses/codex.py` … validated frozen, slotted settings records"**. The file is 1205 lines, already over the "well below 1,000" guidance. Its `_require_bool` and `_require_non_negative_int` helpers are C008 debt.
8. **Things the hints did not mention:**
   - `asyncio.Lock` is banned (S039).
   - S045 flags an async parameter named `timeout`, which `wait_opencode_turn(id, timeout)` would trip.
   - C012 forces registry validation of `model` fields on *Settings, *Config and *Spec records against a strict catalog that lacks the Grok, opencode, Muse and `[1m]` model names.
   - C015 plus the frozen `pyproject.toml` forbid non-`.py` data under `vidbyte/`.
   - The public-API generator needs `vidbyte/__init__.py` committed first.
   - `ComponentRegistry` makes every exported builtin YAML-declarable.
   - The MCP server handles one request at a time and ignores cancellation.
   - Codex dynamic tools are cut at 300 s.
9. **Correct as stated:**
   - The `coding.py:1-12` header form.
   - `transport.py:197-201` (the `shutil.which` launcher).
   - `handlers.py:88` (no `PermissionPolicy`).
   - The A001 seven-field requirement, which applies to tests and `__init__` too.
   - The S012 behaviour.

## What the gates reference got wrong

The reference is `C:/Users/422mi/.claude-account3/skills/spec-pipeline/references/vidbyte-gates.md`.

1. **Lint pass marker** (`:28`). It says the final line reads `AGENT-LINT: PASS …`. For vidbyte-sdk the line is `SDK-LINT: PASS` or `SDK-LINT: FAIL` (`lint/core/report.py:58`).
2. **Semgrep** (`:19`). It says "semgrep is part of [run_ci.py]". It is not:
   - `scripts/run_ci.py:79-93` runs bytecode check, lint, compileall, three check scripts and pytest.
   - Semgrep runs only in `.github/workflows/static-policy.yml`, and must be run by hand after `git add -A`.
3. **Suppressions** (`:29`). It says they "do nothing: backend rules read the AST, Next.js rules strip comments". That describes the vidbyte app repo. For the SDK, the Ruff-backed S-rules are noqa-aware: S035 and S038 exist, and `lint/core/ruff.py:150` forbids `# noqa`. Whether a noqa would hide a finding is unverified, but it is forbidden either way.
4. **Sparse checkout** (`:31`). `git sparse-checkout set backend next-app docs lint` names folders that do not exist in vidbyte-sdk.
5. **Missing worktree nuance** (`:19`). From a worktree, the source stage needs `PYTHONPATH=$(pwd)`, and the package stage must run without it (field guide `local-ci-verification.md`; `scripts/run_ci.py:226` pops it). Otherwise the editable install tests the canonical checkout.
