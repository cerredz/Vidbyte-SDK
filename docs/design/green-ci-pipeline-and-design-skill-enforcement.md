# Design Doc: Green CI Pipeline and Design Skill Enforcement

**Status:** Approved
**Author:** Codex
**Created:** 2026-07-17
**Last Updated:** 2026-07-17

---

## 1. Overview

This change establishes the first required pull-request CI pipeline for `vidbyte-sdk`, gives contributors and coding agents one cross-platform command that runs the same source and package acceptance gates locally, reuses the verified distribution artifact during tag publication, and updates the user-global `design-doc-no-tests` workflow in Codex, Claude Code, OpenCode, and Grok Build so an implementing model must keep diagnosing, fixing, and rerunning the pipeline until both local and pull-request checks are green. The implementation also reconciles the currently red `origin/main` test baseline without restoring intentionally removed public runner/modality injection APIs or weakening existing assertions.

---

## 2. Goals & Non-Goals

### Goals

- Add a GitHub Actions workflow for pull requests, pushes to `main`, and reusable tag-release invocation.
- Run the complete canonical test suite on Python 3.11 and 3.12.
- Provide one repository-owned command, `python scripts/run_ci.py`, for agents and contributors to run before opening a pull request.
- Make the local command check tracked generated files, compile the SDK, run the complete test suite, build distributions, validate metadata, install the wheel in a clean environment, and smoke-test the installed package outside the source checkout.
- Repair the current red baseline so the new workflow is green when introduced, rather than adding a permanently failing check.
- Preserve the intentional model/provider runner-inference API and reconcile stale tests with that contract.
- Restore the already-merged removal of hidden `BaseAgent` aggregation overload behavior that was accidentally reintroduced by a later conflicting change.
- Make tag publishing consume the exact wheel and sdist produced and accepted by the reusable CI workflow.
- Update the global `design-doc-no-tests` surfaces for Codex, Claude Code, OpenCode, and Grok Build with the Vidbyte-specific local and remote CI persistence loop.
- Require implementing models to rerun the full pipeline after targeted fixes and to withhold the handoff report until all local and remote checks pass.
- Configure `main` protection to require the observed CI checks after the workflow has run successfully at least once.

### Non-Goals

- Adding Ruff, mypy, coverage thresholds, dependency auditing, or live-provider tests in this first version.
- Adding new product behavior or new feature-specific test cases beyond the shared test support needed to migrate existing tests to the current runner contract.
- Restoring `runner=`, `runners=`, `runner_options=`, or `modality=` to the public `BaseAgent` API solely to make stale tests pass.
- Running tests that need real provider keys, LangSmith credentials, or network access on pull requests.
- Changing the supported-version declaration beyond validating Python 3.11 and 3.12 in V1.
- Publishing a package as part of ordinary pull-request CI.
- Updating the separate `design-doc`, `create-design`, or `implement-design-doc` skills; “design doc skills” is interpreted here as the platform-specific copies of the explicitly invoked `design-doc-no-tests` workflow.
- Editing Grok's bundled skills or marketplace cache, which may be overwritten by application updates.

---

## 3. Background & Context

The requested audit described an older repository state. The current working checkout at `C:\Users\422mi\vidbyte-repos\vidbyte-sdk` is a dirty feature branch with modified tracked bytecode and many unrelated untracked design/worktree files. Implementation must not use or clean that checkout. The clean `main` worktree at `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-main-job-applier` and `origin/main` both point to commit `213d337`.

Current `origin/main` already contains the SDK launch gate added by commit `d575a3f`: `.github/workflows/publish.yml` validates the version tag, builds wheel and sdist, checks metadata, inspects wheel contents, performs a clean installation smoke test, uploads immutable workflow artifacts, and grants OIDC permission only to the downstream PyPI publish job. It also has zero tracked `.pyc` or `__pycache__` files. That release work should be reused rather than recreated.

The remaining repository gaps are:

- GitHub exposes only the tag-triggered “Publish to PyPI” workflow; no workflow runs on pull requests or pushes to `main`.
- The `main` branch has no branch protection or repository ruleset.
- `pyproject.toml` has no developer extra or pytest configuration.
- Contributor documentation still lists several separate verification commands instead of one canonical pipeline entry point.
- The full `python -m unittest discover -s tests` baseline on clean `origin/main` currently runs 1,419 tests and reports 184 errors, 9 failures, and 2 skips.

The failures are highly clustered rather than 193 unrelated defects:

- 135 errors construct `BaseAgent(..., runner=...)` after runner injection was intentionally removed.
- 29 errors construct `RunState(..., modality=...)` after that field was intentionally removed.
- 9 errors use stale fake-runner return shapes and unpacking assumptions.
- 1 error reads the removed `AgentForkSettings.modality` field.
- 1 import error references the removed `ConfiguredAgentRunner` class.
- Most durable-session failures cascade because stale runner fixtures prevent an agent run from creating the checkpoint the test expects.
- Aggregation-removal tests fail because a later runner-inference conflict reintroduced hidden `BaseAgent` aggregation fields and constructor keywords after commit `9fed56b` had removed them.

The runner-inference design on `main` makes the intended direction clear: public agents accept primitive `provider` and `model_name` values, build runners internally through `vidbyte.lib.runners.Runner`, and do not accept injected runner or modality parameters. The baseline repair must migrate tests to that contract by binding offline fake runners through a shared test-only helper, not by weakening the public design.

The global workflow currently exists in different native forms:

- Codex: `C:\Users\422mi\.codex\skills\design-doc-no-tests\SKILL.md`, with a separate template and `agents/openai.yaml`.
- Claude Code: `C:\Users\422mi\.claude\skills\design-doc-no-tests\SKILL.md`, with the design template embedded.
- OpenCode: `C:\Users\422mi\.config\opencode\commands\design-doc-no-tests.md`, implemented as a global command rather than a skill folder.
- Grok Build: no native `design-doc-no-tests` user skill exists. Grok currently discovers the Claude copy through compatibility scanning, but the user requested an explicit Grok-global installation under `C:\Users\422mi\.grok\skills`.

These global files are outside the Git repository. They cannot be committed in the Vidbyte PR and must be deployed and validated as an explicit user-environment rollout after the repository command is stable.

---

## 4. Requirements

### Functional Requirements

1. `pyproject.toml` must define a `dev` optional dependency group containing the tools required by the local CI command: pytest, pytest-asyncio, build, and twine.
2. `pyproject.toml` must configure pytest with `testpaths = ["tests"]` and strict configuration/marker handling.
3. `scripts/run_ci.py` must be the canonical cross-platform local entry point and must run successfully from a clean repository worktree with `python scripts/run_ci.py` after `python -m pip install -e ".[dev]"`.
4. The default local command must run every V1 gate: generated-file hygiene, source compilation, the complete test suite, distribution build, metadata validation, wheel inspection, clean wheel installation, dependency validation, and installed-package smoke checks.
5. The command must support explicit `source` and `package` stages so GitHub Actions can matrix-test source behavior without redundantly rebuilding distributions in every Python job.
6. The hygiene stage must fail if Git tracks a `.pyc`, `.pyo`, or path below `__pycache__`.
7. The source stage must run pytest over the configured `tests` path and must never silently select a smaller subset.
8. The package stage must produce exactly one wheel and one sdist, run `twine check`, verify required prompt assets and absence of generated bytecode in the wheel, install the wheel in a fresh virtual environment, run `pip check`, and execute smoke assertions from a neutral directory outside the source tree.
9. Smoke assertions must validate distribution/module version agreement, root imports, `VidbyteSDK` construction, a non-empty prompt catalog, and installed console entry points.
10. `.github/workflows/ci.yml` must trigger on `pull_request`, on pushes to `main`, and through `workflow_call`.
11. The source job must run on Ubuntu for Python 3.11 and 3.12 with `fail-fast: false`.
12. The package job must run only after both source matrix legs pass and must upload the verified `dist/` directory as `python-package-distributions`.
13. The workflow must use read-only repository permissions, pip caching, per-ref concurrency, and cancellation of superseded PR runs.
14. `publish.yml` must preserve its tag/version validation and OIDC-only publishing boundary while delegating source/package acceptance to the reusable CI workflow.
15. The publish job must download and upload the exact `python-package-distributions` artifact built by the reusable workflow; it must not rebuild distributions.
16. The current full test baseline must be repaired to zero failures and zero errors before the CI workflow is pushed.
17. Existing tests that inject fake runners must move to a shared test-only support seam that configures primitive provider/model identity and binds an offline fake runner without reopening the removed public constructor API.
18. Existing session fixtures must stop supplying removed `modality` fields to `RunState` and `AgentForkSettings`.
19. Existing algorithm tests must update stale fake-runner patches and result-shape assumptions to the current `Runner` utility contract.
20. `BaseAgent` must again reject hidden aggregation constructor keywords and list-valued model names, with dedicated aggregation remaining available through `AggregateAgent` and `sdk.agents.aggregate(...)`.
21. Baseline repairs must not delete failing tests, mark them skipped, narrow test discovery, restore removed APIs, or weaken assertions merely to make CI green.
22. `README.md` and `CONTRIBUTING.md` must document `python scripts/run_ci.py` as the canonical pre-PR verification command and retain the one-time development-extra installation command.
23. The Codex, Claude Code, OpenCode, and Grok Build global workflows must each contain a concise `Vidbyte SDK CI Gate` section.
24. That skill section must identify a Vidbyte SDK checkout by repository context, require running from the implementation worktree root, and provide the exact commands `python -m pip install -e ".[dev]"` when needed and `python scripts/run_ci.py` for the full gate.
25. Before PR creation, the skill must require a green full local run after the final implementation change.
26. On any local failure, the model must inspect the failure, fix its root cause within the approved design scope, rerun the focused failing check when useful, and then rerun the entire local pipeline.
27. The model must not bypass the gate by skipping checks, editing the runner to omit failures, deleting tests, lowering thresholds, or declaring a failure pre-existing.
28. After opening the draft PR, the skill must run `gh pr checks --watch`; on failure it must inspect failed logs, fix, commit, push, and repeat until every check is green.
29. The skill may stop before green only for a genuine external blocker that cannot be fixed from the repository, such as unavailable GitHub authentication, an unavailable protected secret, or a confirmed third-party outage; the handoff must name the exact blocker and evidence.
30. Phase 7 handoff must not run until both the final full local pipeline and the current PR head checks are green.
31. The updated Codex, Claude, and Grok skill folders must pass the available skill validator, and Grok inspection must resolve the native Grok path rather than the compatibility-loaded Claude copy.
32. After a successful workflow run establishes the exact check contexts, `main` protection must require the Python 3.11, Python 3.12, and package acceptance checks before merge.

### Non-Functional Requirements

- **Performance:** Each source matrix leg should complete within five minutes and package acceptance within three minutes under normal GitHub-hosted runner conditions. The current local suite completes in seconds, leaving ample margin.
- **Determinism:** Pull-request checks must be offline and require no provider credentials, user-specific environment variables, timezone, or live service availability.
- **Cross-platform execution:** `scripts/run_ci.py` must use `pathlib`, `sys.executable`, `venv`, and `subprocess` without shell-specific command syntax. V1 hosted checks run on Ubuntu; the same command must run on the user's Windows workstation.
- **Security:** Pull-request CI must request no secrets. Only the publish job receives `id-token: write`. Third-party actions remain pinned to reviewed immutable commits.
- **Reliability:** Any non-zero stage stops publication and PR handoff. Focused reruns are diagnostic only; a final complete run is mandatory.
- **Maintainability:** Repository commands are the source of truth. Global skills name the command and persistence policy but do not duplicate stage implementation.
- **Observability:** Each local and hosted stage prints a clear name and failing subprocess. GitHub jobs remain separately visible for each Python version and package acceptance.
- **Repository safety:** Implementation starts from refreshed `origin/main` in a new isolated worktree and does not clean, reset, or reuse the dirty current checkout.

---

## 5. High-Level Design

The repository receives a Python orchestration script as the executable CI contract. It owns process invocation, artifact inspection, neutral-directory smoke testing, and clear failure propagation. GitHub Actions becomes a thin scheduler around that script: two source matrix jobs call the source stage, and one dependent package job calls the package stage and uploads accepted distributions. Contributors and coding agents call the default all-stages mode locally, so local and hosted behavior cannot drift into separate command lists.

Before the workflow becomes merge-gating, the implementation reconciles `origin/main` with intentional API changes already documented and partly merged. Existing tests are migrated from public runner injection to a shared offline test seam; removed session modality fields are removed from fixtures; stale result-shape patches are updated; and the regressed BaseAgent aggregation overload removal is restored. The full suite, not a selected subset, defines green.

Tag publishing calls the same reusable workflow. Once source and package jobs pass, `publish.yml` downloads the distribution artifact from that workflow run and sends only that artifact to PyPI using the existing OIDC environment. Ordinary PRs never receive publish permissions.

Finally, each user-global design workflow gains the same small Vidbyte-specific policy block. The block is intentionally procedural rather than an embedded copy of CI logic: run the repository command, persist until local green, open the draft PR, persist until remote green, then hand off. Platform-native validation proves each environment can discover the updated workflow.

```text
Implementation worktree
        |
        v
python scripts/run_ci.py
        |
        +--> hygiene --> compile --> full pytest suite
        |
        +--> build --> twine --> inspect wheel --> clean install --> smoke
        |
        v
local green only
        |
        v
draft PR --> ci.yml --> source (3.11) ----+
                     --> source (3.12) ----+--> package artifact --> remote green
                                                              |
version tag --> publish.yml --> reusable CI ------------------+--> OIDC publish

Codex / Claude / OpenCode / Grok
        |
        +--> require local green --> require PR green --> allow handoff
```

---

## 6. Detailed Design

### 6.1 Developer Dependencies and Pytest Contract

**File(s):** `pyproject.toml`
**Type:** Modified

#### What it does

Defines the tools and discovery contract used by the repository-owned CI command.

#### Interface / API

```toml
[project.optional-dependencies]
dev = [
  "pytest>=8",
  "build>=1",
  "twine>=5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["--strict-config", "--strict-markers", "-ra"]
```

#### Logic / Algorithm

1. Keep runtime dependencies unchanged.
2. Put development-only tools behind the `dev` extra.
3. Make `tests/` the only default collection root so untracked nested worktrees and ad hoc `scripts/test-*.py` files are not accidentally collected.
4. Retain unittest-style test classes; pytest is the runner, not a test rewrite.

#### Edge Cases & Error Handling

- A missing dev installation causes `run_ci.py` to fail with the exact setup command.
- The dependency ranges establish compatible floors without pretending the repository has a lockfile in V1.

### 6.2 Canonical Local Pipeline Runner

**File(s):** `scripts/run_ci.py`
**Type:** New file

#### What it does

Runs the V1 verification contract locally and inside GitHub Actions using the current Python interpreter.

#### Interface / API

```python
class CiPipeline:
    def run(self, stage: str = "all", dist_dir: Path | None = None) -> None:
        # Runs the requested CI stage and raises PipelineFailure on the first failed gate.

    def run_hygiene(self) -> None:
        # Rejects generated Python artifacts tracked by Git.

    def run_source(self) -> None:
        # Compiles the package and runs the complete configured pytest suite.

    def run_package(self, dist_dir: Path | None = None) -> Path:
        # Builds, validates, installs, and smoke-tests distribution artifacts.

def main() -> int:
    # Parses --stage/--dist-dir, runs the pipeline, and returns a shell-friendly status.
```

CLI contract:

```text
python scripts/run_ci.py
python scripts/run_ci.py --stage source
python scripts/run_ci.py --stage package --dist-dir dist
```

#### Logic / Algorithm

1. Resolve and validate the repository root from the script location.
2. Verify required Python modules and print the dev-extra install command if absent.
3. For hygiene, query `git ls-files` and reject bytecode/cache paths.
4. For source, run `python -m compileall -q vidbyte` and `python -m pytest`.
5. For package, build into the requested output directory or a temporary directory.
6. Require exactly one `.whl` and one `.tar.gz`.
7. Run `python -m twine check` on both artifacts.
8. Inspect the wheel for required prompt assets and forbidden generated artifacts.
9. Create a temporary virtual environment, install the wheel with no cache, and run `pip check`.
10. From a separate neutral temporary directory, validate distribution/module version equality, root imports, `VidbyteSDK`, `Prompts().keys()`, and declared console entry points.
11. Print a concise success summary only after all requested gates pass.

#### Edge Cases & Error Handling

- Subprocess failures include the stage and exact command in `PipelineFailure`.
- Temporary build/venv directories are automatically removed; an explicit `--dist-dir` is preserved for artifact upload.
- The script never publishes or accesses secrets.
- An empty or multiply produced artifact set is a hard failure.

### 6.3 Green Baseline Reconciliation

**File(s):** `tests/agent_test_support.py`, the 17 test files listed in Section 9, and the five `vidbyte/agents/` implementation files listed there
**Type:** New file, Modified

#### What it does

Makes the full current suite express the already-intended public API and restores source behavior that a later merge accidentally regressed.

#### Interface / API

```python
class AgentTestSupport:
    @staticmethod
    def build_agent(*, runner: object, **agent_options: object) -> BaseAgent:
        # Creates a provider/model-configured agent and binds an offline fake runner internally.

    @staticmethod
    def bind_runner(agent: BaseAgent, runner: object, runner_type: str = "text") -> BaseAgent:
        # Populates the test-only internal runner cache without reopening public injection.
```

#### Logic / Algorithm

1. Add a shared test-only helper that creates agents with a known offline provider/model pair and binds fake runners through the internal cache seam.
2. Replace `BaseAgent(..., runner=fake)` uses in existing tests with the helper.
3. For tests that verify lazy runner creation itself, patch `Runner.build` rather than using the helper.
4. Update fork tests so child runner identity/caching assertions match the intended isolated child behavior.
5. Remove obsolete `modality` arguments from `RunState` and `AgentForkSettings` fixtures.
6. Update fake-runner factory patches that still assume the pre-inference tuple/return contract.
7. Remove the `ConfiguredAgentRunner` import and assert behavior through the current `Runner` utility and BaseAgent flow.
8. Reapply the semantic parts of commit `9fed56b` that remove BaseAgent aggregation keywords, internal aggregate plan/agent state, and list-valued `model_name`, while preserving all newer runner-inference and agent-loop changes.
9. Keep dedicated `AggregateAgent`, aggregator, exports, and tests intact.
10. Run targeted files while migrating, then run `python scripts/run_ci.py` in full.

#### Edge Cases & Error Handling

- Test helpers remain below `tests/` and are not exported by the installed SDK.
- No network transport is created by the helper.
- If a failure remains after fixture migration, diagnose whether it is an actual runtime regression; do not automatically rewrite the assertion.
- Any genuinely required source file outside the approved manifest requires design reconciliation before modification; green status cannot be obtained by silently expanding product scope.

### 6.4 Pull-Request CI Workflow

**File(s):** `.github/workflows/ci.yml`
**Type:** New file

#### What it does

Runs source verification on supported V1 Python versions and package acceptance on every PR/main push, and exposes the same jobs to the release workflow.

#### Interface / API

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]
  workflow_call:

permissions:
  contents: read

jobs:
  source:
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12"]

  package:
    needs: source
```

#### Logic / Algorithm

1. Check out the exact commit using immutable action pins consistent with `publish.yml`.
2. Set up the matrix Python version with pip caching.
3. Install the editable SDK plus dev extra.
4. Run `python scripts/run_ci.py --stage source`.
5. After all matrix legs pass, run package acceptance once on Ubuntu/Python 3.11 with `--dist-dir dist`.
6. Upload `dist/` as `python-package-distributions` with short retention and `if-no-files-found: error`.

#### Edge Cases & Error Handling

- `fail-fast: false` reports both supported-version outcomes.
- PR force-pushes cancel superseded runs; tag publication does not cancel an active release.
- Forked PRs need no secrets.

### 6.5 Release Workflow Reuse

**File(s):** `.github/workflows/publish.yml`
**Type:** Modified

#### What it does

Preserves tag identity validation and trusted publishing while replacing duplicated build/smoke logic with the reusable CI artifact.

#### Interface / API

```yaml
jobs:
  validate-tag:
    # Verify v{project.version} before release work.

  checks:
    needs: validate-tag
    uses: ./.github/workflows/ci.yml

  publish:
    needs: checks
    # Download python-package-distributions and publish with OIDC.
```

#### Logic / Algorithm

1. Keep the existing tag/version comparison in a no-secret validation job.
2. Invoke the reusable CI workflow for the tagged commit.
3. Let the reusable package job build, inspect, install, smoke, and upload distributions.
4. Download that exact artifact in the OIDC-scoped publish job.
5. Publish without rebuilding or setting a long-lived token.

#### Edge Cases & Error Handling

- A tag mismatch stops before CI and publication.
- A source or package failure prevents the OIDC job from starting.
- A PyPI outage leaves the already-verified artifact in the workflow run for diagnosis; no different artifact is rebuilt.

### 6.6 Contributor Documentation

**File(s):** `README.md`, `CONTRIBUTING.md`
**Type:** Modified

#### What it does

Makes the repository-owned command the visible pre-PR contract.

#### Interface / API

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

#### Logic / Algorithm

1. Replace the canonical multi-command verification block with the two commands above.
2. Explain that the full command includes source tests and installed-wheel acceptance.
3. Keep lower-level commands as troubleshooting details only if they add value.

#### Edge Cases & Error Handling

- Documentation must work in PowerShell, bash, and GitHub-hosted Ubuntu runners.

### 6.7 Global Design Workflow CI Enforcement

**File(s):** the six global skill/command files listed in Section 9
**Type:** New file, Modified

#### What it does

Adds the same Vidbyte-specific pre-PR and post-PR persistence policy to each requested coding environment.

#### Interface / API

Required policy block:

```markdown
## Vidbyte SDK CI Gate

When the implementation repository is `vidbyte-sdk`, run from the implementation worktree root:

1. Install the verification tools when needed: `python -m pip install -e ".[dev]"`.
2. Run the complete local gate: `python scripts/run_ci.py`.
3. On failure, fix the root cause and repeat until the full command passes.
4. After opening the draft PR, run `gh pr checks --watch` and continue fixing/pushing until all checks pass.
5. Do not enter the handoff phase while either gate is red.
```

#### Logic / Algorithm

1. Update the description/frontmatter so “no tests” means no new feature-specific tests, not permission to skip existing CI.
2. Add the gate after implementation/refinement and before PR creation.
3. Add the remote persistence loop inside the PR phase and make Phase 7 conditional on green checks.
4. State prohibited shortcuts and the narrow external-blocker exception.
5. Keep the repository command, not the skill text, as the executable source of truth.
6. Update Codex `agents/openai.yaml` so UI metadata no longer claims verification scripts are unnecessary.
7. Create a native Grok user skill plus template reference; do not edit bundled or cached Grok files.
8. Preserve OpenCode's existing global-command format instead of inventing an incompatible folder layout.

#### Edge Cases & Error Handling

- Existing active sessions may need a new session or skill reload to observe updated global instructions.
- Grok currently imports the Claude copy; native Grok discovery must be verified so duplicate-name priority is deterministic.
- Global changes are external user configuration and are not included in the repository PR diff.

### 6.8 Required Check Rollout

**File(s):** N/A - GitHub repository ruleset/branch protection
**Type:** External configuration

#### What it does

Prevents ordinary merges to `main` when any V1 CI check is red or missing.

#### Interface / API

Required observed contexts:

```text
CI / source (3.11)
CI / source (3.12)
CI / package
```

Exact names must be taken from the first successful GitHub run rather than assumed from this design.

#### Logic / Algorithm

1. Let the draft PR produce the final check context names.
2. Verify the names through `gh pr checks` or the checks API.
3. Create/update the `main` ruleset to require all three contexts and require a pull request.
4. Read the resulting ruleset back and record it in the handoff.

#### Edge Cases & Error Handling

- If the repository plan or permissions reject ruleset creation, report the exact API response; the skill-level green gate still applies, but repository enforcement remains an explicit blocker/follow-up.
- Do not require a guessed context that no workflow emits, which would deadlock merges.

---

## 7. Data Model Changes

N/A - this work changes developer dependencies, test fixtures, CI orchestration, repository policy, and user-global workflow instructions. It does not add or migrate a persisted application data model. Removal of stale `modality` arguments from tests aligns fixtures with the already-current `RunState` schema rather than changing that schema.

---

## 8. API Changes

### 8.1 Developer CI Command

**Change type:** New

**Request:**

```json
{
  "command": "python scripts/run_ci.py",
  "stage": "all | source | package",
  "dist_dir": "optional path for preserved build artifacts"
}
```

**Response:**

```json
{
  "exit_code": "0 only when every requested gate passes",
  "output": "named stage progress and final green summary"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| Non-zero | Missing dev dependency, tracked bytecode, compilation failure, test failure, malformed distribution, metadata failure, install/dependency failure, or smoke failure |

### 8.2 Python SDK Public API

**Change type:** Restored intended contract

No new public SDK API is added. The implementation preserves provider/model runner inference and restores the previously approved removal of hidden BaseAgent aggregation overloads. Public fake-runner injection is not restored.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/green-ci-pipeline-and-design-skill-enforcement.md` | Approved source of truth for the pipeline and global-skill rollout |
| CREATE | `.github/workflows/ci.yml` | Pull-request/main/reusable source and package acceptance workflow |
| CREATE | `scripts/run_ci.py` | Canonical cross-platform local CI entry point |
| CREATE | `tests/agent_test_support.py` | Shared offline seam for existing tests after public runner injection removal |
| MODIFY | `pyproject.toml` | Add dev dependencies and pytest discovery/configuration |
| MODIFY | `.github/workflows/publish.yml` | Reuse CI and publish the exact accepted artifact |
| MODIFY | `README.md` | Document the canonical local pipeline command |
| MODIFY | `CONTRIBUTING.md` | Replace separate pre-PR commands with the canonical gate |
| MODIFY | `vidbyte/agents/base.py` | Restore removal of the accidentally reintroduced aggregation overload while preserving runner inference |
| MODIFY | `vidbyte/agents/continual_trace.py` | Carry the inferred source runner into the internal continual-trace agent |
| MODIFY | `vidbyte/agents/handoff.py` | Carry the inferred source runner into the internal handoff generator |
| MODIFY | `vidbyte/agents/algorithms/multi_provider_agentic_grader.py` | Consume the current three-value middleware invocation result |
| MODIFY | `vidbyte/agents/algorithms/reflexion.py` | Consume the current three-value middleware invocation result |
| MODIFY | `tests/test_agent_base.py` | Remove stale ConfiguredAgentRunner/public runner-injection assumptions |
| MODIFY | `tests/test_agent_behavior.py` | Use the shared offline runner support |
| MODIFY | `tests/test_agent_fork_isolation.py` | Align fork fixtures with provider/model inference and isolated caches |
| MODIFY | `tests/test_agent_middleware.py` | Use the shared offline runner support |
| MODIFY | `tests/test_agent_tool.py` | Use the shared offline runner support |
| MODIFY | `tests/test_agent_tool_loop.py` | Use the shared offline runner support |
| MODIFY | `tests/test_continual_trace.py` | Use the shared offline runner support |
| MODIFY | `tests/test_concurrent_middleware.py` | Replace a real-time concurrency wait with deterministic clock advancement while strengthening the exact probe-count assertion |
| MODIFY | `tests/test_create_handoff_tool.py` | Use the shared offline runner support |
| MODIFY | `tests/test_durable_sessions.py` | Remove stale RunState modality fields and use offline runner support |
| MODIFY | `tests/test_evals.py` | Use the shared offline runner support |
| MODIFY | `tests/test_fork_tool.py` | Remove stale fork modality expectations and use offline runner support |
| MODIFY | `tests/test_handoff_agent.py` | Use the shared offline runner support |
| MODIFY | `tests/test_mcp_attachment.py` | Use the shared offline runner support |
| MODIFY | `tests/test_mcp_studio_server.py` | Use the shared offline runner support |
| MODIFY | `tests/test_semantic_tracing.py` | Use the shared offline runner support |
| MODIFY | `tests/test_tracing.py` | Use the shared offline runner support |
| MODIFY | `C:\Users\422mi\.codex\skills\design-doc-no-tests\SKILL.md` | Add the Vidbyte local/remote green persistence gate |
| MODIFY | `C:\Users\422mi\.codex\skills\design-doc-no-tests\agents\openai.yaml` | Remove stale “verification not required” UI wording |
| MODIFY | `C:\Users\422mi\.claude\skills\design-doc-no-tests\SKILL.md` | Add the same Vidbyte local/remote green persistence gate |
| MODIFY | `C:\Users\422mi\.config\opencode\commands\design-doc-no-tests.md` | Add the same gate to OpenCode's native global command |
| CREATE | `C:\Users\422mi\.grok\skills\design-doc-no-tests\SKILL.md` | Install a native Grok-global version of the workflow |
| CREATE | `C:\Users\422mi\.grok\skills\design-doc-no-tests\references\design-doc-template.md` | Supply the design template referenced by the Grok skill |

**Totals: 6 created, 30 modified, 0 deleted.** Four created files and 26 modified files belong to the repository implementation/PR; two created files and four modified files are user-global external rollout artifacts.

Implementation discovery narrowed the planned API-migration edits from 26 test files to 16: after the shared offline runner seam and production boundary fixes landed, the other ten enumerated tests already matched the current API and needed no edits. A seventeenth test file was added after the canonical full run exposed a real-time circuit-breaker wait that could flake under suite load; its deterministic clock now asserts the stronger exact one-probe/two-rejection result. Four production files were added because the complete suite exposed two internal agents that needed to inherit the inferred runner cache and two algorithms that still unpacked an older middleware result shape. These are direct baseline repairs required by the approved green-CI scope, not new feature behavior.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | 3.11 and 3.12 in hosted CI | Supported-version source validation | `requires-python >=3.11` is broader than the V1 matrix |
| pytest | >=8 development extra | Canonical collection/runner for existing unittest-compatible suite | Tool upgrades may surface stricter collection behavior |
| pytest-asyncio | >=0.23 development extra | Async test execution and declared asyncio configuration/markers on clean runners | Plugin upgrades may change loop-scope defaults; the repository pins its intended fixture scope |
| build | >=1 development extra | Standards-based wheel/sdist construction | Build backend changes can alter package contents; wheel inspection gates this |
| twine | >=5 development extra | Distribution metadata validation | Metadata validation does not replace installed-wheel smoke testing |
| Python `venv`, `subprocess`, `pathlib` | Standard library | Cross-platform clean installation and orchestration | Venv creation can fail in incomplete Python installations |
| GitHub Actions | Repository workflow service | PR/main/tag automation | Hosted runner or Actions outage can block remote green status |
| GitHub branch rulesets/protection API | `repos/cerredz/Vidbyte-SDK` | Require emitted CI contexts before merge | Repository plan/permissions may limit configuration |
| GitHub CLI | Authenticated `gh` | PR creation, log inspection, check watching, ruleset verification | Authentication is an external prerequisite |
| PyPI trusted publishing | Existing `pypi` environment | Publish verified artifacts without a long-lived token | External configuration/outage can block release only |
| Codex skill validator | Local skill-creator scripts | Validate updated Codex/Claude/Grok skill frontmatter | Valid syntax does not prove behavioral compliance |
| Grok `inspect --json` | Local Grok Build CLI | Verify native skill discovery path | Duplicate-name compatibility precedence must be checked |

No runtime SDK dependency is added.

---

## 11. Rollout & Deployment

1. **Approval:** Review this document and explicitly approve it. Approval accepts the recommended defaults in Section 12.
2. **Fresh implementation base:** Fetch `origin`, confirm `origin/main` is current, and create `feat/green-ci-pipeline-and-design-skill-enforcement` in a new isolated worktree directly from `origin/main`. Do not check out, clean, or reset the dirty current feature checkout.
3. **Design commit:** Copy this approved design doc into the new worktree and commit it first.
4. **Baseline reconciliation:** Add the shared offline test support, migrate the enumerated tests, and restore the aggregation-removal boundary. Use targeted tests during migration, but continue until the complete suite has zero errors/failures.
5. **Pipeline implementation:** Add the dev configuration, canonical runner, PR workflow, reusable release integration, and documentation.
6. **Local acceptance:** Install `.[dev]`, run `python scripts/run_ci.py`, fix every failure, and rerun the full command until green. Record the final command and output summary.
7. **Repository commits:** Commit baseline reconciliation and pipeline work in logical atomic commits. Confirm no generated/cache/build files are tracked.
8. **Global rollout:** After the command is stable, update the four requested user-global environments. This is an explicitly approved exception to the worktree-only rule because those files are user configuration outside any repository; all repository edits remain confined to the worktree.
9. **Global validation:** Run the skill validator against Codex, Claude, and Grok folders; read back OpenCode's command; run `grok inspect --json` and verify `design-doc-no-tests` resolves to `C:\Users\422mi\.grok\skills\design-doc-no-tests\SKILL.md`.
10. **Draft PR:** Push the branch and open a draft PR into `main` with the design doc as its body.
11. **Remote persistence loop:** Run `gh pr checks --watch`. For any failure, inspect failed logs, fix the root cause, commit, push, rerun the full local pipeline, and watch the new PR checks. Repeat until all checks on the current head are green.
12. **Required checks:** Read the exact successful context names and configure/read back `main` protection requiring both Python jobs and package acceptance.
13. **Handoff:** Only after local and remote green, report the PR URL, branch, commits, file summary, exact verification evidence, ruleset state, global skill paths, deviations, and follow-ups.

Rollback is split by surface:

- **Before merge:** Close the draft PR and delete only its isolated worktree/branch. Restore the six global files from pre-edit copies or inverse patches.
- **After merge but before a release:** Revert the repository PR, remove the newly required check contexts if the workflow is removed, and restore global skill copies.
- **After publication:** The existing PyPI immutability policy applies; yank a broken release and publish a new patch version rather than replacing artifacts.

---

## 12. Open Questions

Approval of this design is treated as approval of the following recommended defaults unless the user overrides one explicitly:

- [ ] Update only the four platform-specific `design-doc-no-tests` surfaces, not the separate full `design-doc`, `create-design`, or `implement-design-doc` workflows.
- [ ] Create a native Grok user skill even though Grok currently compatibility-loads the Claude copy, because the user explicitly requested an installation inside Grok Build.
- [ ] Treat user-global skill edits as an approved external rollout after the repository command is green, since they cannot live inside the Git worktree or PR.
- [ ] Make the full 1,419-test suite green by migrating stale fixtures to current APIs and restoring the previously merged aggregation-removal boundary; do not select a smaller green subset.
- [ ] Use Python 3.11 and 3.12 for the V1 hosted matrix, matching the explicit request, and track broader `>=3.11` support alignment as a follow-up.
- [ ] Defer Ruff, mypy, coverage, dependency audit, Windows-hosted Actions, and live integration checks to follow-up pipeline versions.
- [ ] Configure main protection after the first successful PR run reveals exact context names; if repository plan/permissions prevent it, report that as an external rollout blocker rather than guessing names.

---

## 13. Alternatives Considered

### Alternative 1: Add a Green Smoke-Only Workflow and Ignore the Full Suite

- What: Run imports and a hand-picked subset so the first PR check is immediately green.
- Why rejected: It would conceal the known 184 errors and 9 failures and would not satisfy the requested genuinely green baseline.

### Alternative 2: Restore Public `runner=` Injection

- What: Re-add the removed BaseAgent constructor parameter so legacy tests pass with few edits.
- Why rejected: Runner inference is an intentional current API decision documented on `main`. Restoring the old API to appease stale tests would reverse product behavior and create new compatibility debt.

### Alternative 3: Keep Local and GitHub Commands Separate

- What: Put all commands directly in YAML and teach each global skill to reproduce them.
- Why rejected: Four skill copies plus contributor docs and release YAML would drift. A repository-owned Python entry point gives every consumer one executable contract.

### Alternative 4: Rebuild in the Publish Job

- What: Let PR CI pass, then rebuild from the same commit in the OIDC publish job.
- Why rejected: Source identity is not artifact identity. Publishing the accepted artifact closes that gap and preserves least privilege.

### Alternative 5: Update Grok's Bundled `implement` or `design` Skill

- What: Modify files under `.grok/bundled/skills`.
- Why rejected: Bundled assets are application-owned and may be overwritten. A native user skill is the durable global customization surface.

### Alternative 6: Store One Shared Global Skill and Rely on Compatibility Scanning

- What: Update only Claude or `.agents` and let other tools discover it.
- Why rejected: The user explicitly requested platform-global installations, OpenCode already uses a distinct command surface, and independent discovery makes behavior easier to verify in each environment.
