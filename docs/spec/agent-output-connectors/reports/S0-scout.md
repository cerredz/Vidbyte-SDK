# S0 scout report: agent output connectors

Stage: S0 scout. Date: 2026-10-11. HEAD: no commits.

Output: `docs/spec/agent-output-connectors/context/code-map.md`, which has 4 numbered `## ` sections; `grep -c "^## "` returns 4.

Nothing else was created or modified. Nothing was installed, committed, or gated. Only read-only git commands were used (`git grep`, `git ls-files`).

## Planned file list

These are the files the change is expected to touch. Details are in code-map §2.

- **New:** the `vidbyte/agents/output/` package, which does not exist today.
- **Agents:**
  - `vidbyte/agents/base.py` (new keyword, attribute, and reply-path step)
  - `vidbyte/agents/fork.py` (decides whether forks carry the field)
  - `vidbyte/agents/jev/settings.py` (field on `JevAgentSettings`)
  - `vidbyte/agents/jev/agent.py` (pass the field to `super().__init__`)
- **CodingAgent:** `vidbyte/agents/coding.py` needs no edit, because it forwards `**kwargs`.
- **Records, enums, constants, errors:**
  - a new `vidbyte/lib/dataclasses/<domain>.py`
  - a new `vidbyte/lib/enums/<domain>.py`, plus `vidbyte/lib/enums/__init__.py`
  - a new `vidbyte/lib/constants/<domain>.py`
  - `vidbyte/lib/errors/base.py` and `vidbyte/lib/errors/__init__.py`, if a new error is added
- **Provider-specific logic:** goes in `vidbyte/lib/...` or `vidbyte/providers/...`. The placement is open; see code-map §4 items 11–12.
- **Exports:**
  - `vidbyte/agents/__init__.py`
  - `vidbyte/__init__.py`
  - `contracts/sdk-public-api.json`, regenerated with `scripts/generate-sdk-public-api.py`
- **Docs:** `vidbyte/agents/README.md`, and `REPO_MAP.md` if the new folder is listed.
- **Tests:** new test files under `tests/`, plus the `JevAgent` and `CodingAgent` contract tests that pin signatures.
- **Open:** `vidbyte/agents/codex/agent.py` (CodexHarnessAgent), depending on how the open question is answered.

## Files actually read this session

### Read in full

**Repo guidance and request**
- `AGENTS.md`, `CLAUDE.md`, `REPO_MAP.md`
- `docs/spec/agent-output-connectors/request.md` (the only file read under `docs/`)
- `C:/Users/422mi/.claude-work/skills/spec-pipeline/references/vidbyte-gates.md`

**Agents**
- `vidbyte/agents/coding.py`
- `vidbyte/agents/jev/agent.py`
- `vidbyte/agents/jev/settings.py`
- `vidbyte/agents/fork.py`
- `vidbyte/agents/types.py`
- `vidbyte/tools/agent_tool.py`

**Library**
- `vidbyte/lib/dataclasses/agents.py`
- `vidbyte/lib/http/transport.py`, `vidbyte/lib/http/__init__.py`, `vidbyte/lib/http/parser.py`
- `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`
- `vidbyte/lib/registries/models.py`
- `vidbyte/lib/util/credential_keys.py`

**Operation clients**
- `vidbyte/tools/builtins/operations/clients/_base.py`
- `vidbyte/tools/builtins/operations/clients/brave.py`
- `vidbyte/tools/builtins/operations/clients/README.md`

**Folder READMEs**
- `vidbyte/agents/README.md`
- `vidbyte/lib/README.md`
- `vidbyte/config/README.md`

**Lint**
- `lint/README.md`, `lint/rules/README.md`
- `lint/run.py`
- `lint/core/discovery.py`
- `lint/baseline.json`

**Contracts and scripts**
- `contracts/README.md`
- `scripts/generate-sdk-public-api.py`
- `scripts/run_ci.py`

**CI and packaging**
- `.github/workflows/static-policy.yml`, `.github/workflows/ci.yml`
- `.semgrep/typed-mapping-boundary-policy.yml`
- `pyproject.toml`

**Tests**
- `tests/agent_test_support.py`
- `tests/test_restore_output_schema.py`
- `tests/test_web_operation_client_retry.py`
- `tests/features/coding_agent/test_coding_agent_contract.py`

**Field guide** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`)
- `init.md`
- `local-ci-verification.md`
- `blocking-lint-invariants.md`
- `strict-config-dataclasses.md`
- `prebuilt-agents.md`
- `comment-format.md`
- `provider-api-contracts.md`
- `review-scope.md`
- `class-bound-helpers.md`
- `declarative-config-resolution.md`
- `jev-capability-layout.md`
- `runtime-boundaries.md`

### Read in sections

**Agents**
- `vidbyte/agents/base.py`: header; 60–275; 352–371; 491–576; 686–736; 784–1148; 1285–1361; 1452–1466.
- `vidbyte/agents/runtime.py`: header; 272–331; 838–862; 1072–1099; 1513–1545; 1902–1918.
- `vidbyte/agents/codex/agent.py`: 1–260.
- `vidbyte/agents/__init__.py`: around 41–64, 291–293.

**Sessions and package root**
- `vidbyte/sessions/session.py`: 155–190, 304, 459.
- `vidbyte/sessions/serialization.py`: 111–120, 198–215, `_SECRET_TOKENS`.
- `vidbyte/lib/dataclasses/sessions.py`: `RunState`, 53–78.
- `vidbyte/__init__.py`: around 41, 438–452, 690, version.

**Library, config, and middleware**
- `vidbyte/lib/dataclasses/strategies.py`: `AgentResult`.
- `vidbyte/lib/dataclasses/config.py`: 20–32, 313–440.
- `vidbyte/config/loader.py`: 285–296.
- `vidbyte/lib/enums/__init__.py`: 1–40.
- `vidbyte/middleware/builtins/audit.py`: 1–80.

**Providers**
- `vidbyte/providers/`: directory listing, plus imports of `__init__.py` and `base.py`.
- `vidbyte/providers/README.md`: headings, 60–90, 590–614.

**Lint**
- `lint/rules/a001_agent_readable_file_headers.py`: 24–32.
- `lint/core/report.py:58` and `lint/core/baseline.py:22`, via grep.

**Tests**
- `tests/features/coding_agent/conftest.py`: 1–60.
- `tests/test_jev_agent.py`: 48, 504–509.
- `tests/test_memory_tools.py`: the `MockTransport` section.

### Header only

- `vidbyte/lib/config/mcp_presets.py`, to confirm it is unrelated.

### Listed or grepped only, not opened

- **Directories:** `vidbyte/lib/dataclasses/`, `vidbyte/lib/enums/`, `vidbyte/lib/constants/`, `vidbyte/middleware/builtins/`.
- **Grep only:** the JevAgent child construction sites (`jev/bulk_work.py:49`, `jev/compute/clone.py:42`, `jev/compute/swarm.py:54`), the multi-agent fork sites, and the HttpTransport importers.
- **Name and size only:** `tests/test_agent_base.py`, `tests/test_agent_fork_isolation.py`, `tests/test_durable_sessions.py`, `tests/test_agent_tool.py`, `tests/test_custom_exception_constructors.py`, `tests/test_readme_size_limit.py`, `tests/test_middleware_builtins.py`.

## What the areas guess and the gates reference got wrong

1. **The registry class name is wrong.** The request, and through it the briefing, name `ModelRegistry.resolve_api_key`. The class is `ProviderModelRegistry` (`vidbyte/lib/registries/models.py:151-161`). No `ModelRegistry` exists.
2. **JevAgent cannot take a new constructor keyword.** Its signature is pinned to `(self, settings, runtime_settings)` by `tests/test_jev_agent.py:504-509` and by the field guide. AGENTS.md routes a new capability to a `JevAgentSettings` field. JevAgent also passes no middleware, output_schema, or handoff to BaseAgent today (`jev/agent.py:90-102`).
3. **CodingAgent needs no change.** It is a direct `BaseAgent` subclass that forwards `**kwargs`. Its contract test pins the signature and forbids overriding BaseAgent methods.
4. **`vidbyte/providers/` is a model-adapter layer.** It is not a general "third-party provider" folder. A006 treats it as a lower layer, so it may not import `vidbyte.agents`. Its `__init__` eagerly imports every model adapter. The real precedent for credentialed non-model HTTP clients is `vidbyte/tools/builtins/operations/clients/`, which is in the tools layer.
5. **Expected READMEs are missing.** There is no README in `vidbyte/middleware/builtins/`, `vidbyte/sources/`, `vidbyte/lib/errors/`, `vidbyte/lib/http/`, `vidbyte/lib/dataclasses/`, `vidbyte/lib/enums/`, or `vidbyte/lib/constants/`. Neither `vidbyte/agents/README.md` nor `vidbyte/providers/README.md` has a `## Notes for agents` section.
6. **There is no `tests/conftest.py`.** The only conftest is `tests/features/coding_agent/conftest.py`.
7. **The gates reference has the lint result line wrong.** It expects `AGENT-LINT: PASS`. The real line is `SDK-LINT: PASS` or `SDK-LINT: FAIL` (`lint/core/report.py:58`).
8. **Semgrep is not part of `scripts/run_ci.py`.** It runs only in `.github/workflows/static-policy.yml` (semgrep==1.170.1, typed-mapping-boundary policy). A green `run_ci.py` does not cover it.
9. **The PYTHONPATH guidance conflicts.** The briefing says to run `run_ci` with PYTHONPATH unset. The field guide and lint README run the source stage with `PYTHONPATH=$(pwd)` and the package stage without it. The code map records both.
10. **New files are invisible to lint until staged.** Lint discovers files with `git ls-files`. A001 also applies to new test files, not only to `vidbyte/`.
11. **The request contradicts itself on forks and `as_tool`.** Forks drop outputs, but `as_tool` should deliver on every call, and `as_tool` runs on a fork (`vidbyte/tools/agent_tool.py:59`). Code-map §4 item 5 records this as a contradiction; it is not resolved here.
