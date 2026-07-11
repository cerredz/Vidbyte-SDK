# Design Doc: SDK Launch Gate

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-11
**Last Updated:** 2026-07-11

---

## 1. Overview

Complete the Vidbyte SDK launch gate by making version 0.1.0 publishable and installable from PyPI, removing generated files from version control, correcting package and repository metadata, hardening the GitHub Actions trusted-publishing path, and adding a minimal public-repository contribution and safety baseline. The release is accepted only when the artifact built from a clean main checkout passes metadata validation, installs into a fresh virtual environment from an empty working directory, imports its public package and prompt catalog successfully, and then passes the same check from the production PyPI index after publication.

---

## 2. Goals & Non-Goals

### Goals

- Publish vidbyte-sdk 0.1.0 to the production PyPI index through GitHub Actions OpenID Connect (OIDC), without a long-lived PyPI token.
- Fix the current wheel defect in which root-level prompt Markdown assets are omitted and import vidbyte fails after installation.
- Modernize the PEP 639 license metadata and remove the current setuptools deprecation warnings.
- Remove all 238 tracked Python bytecode/cache files from the repository while preserving the existing ignore rules.
- Make the release workflow fail closed on tag/version mismatch, invalid distributions, broken dependencies, or failed clean-environment imports.
- Align the PyPI metadata, README, GitHub description, homepage, and topics around a concise public SDK position.
- Add the minimum contribution, security, conduct, issue, and pull-request guidance expected of a public developer repository.
- Verify both the pre-publication wheel and the post-publication PyPI package on a clean Python 3.11 environment.
- Leave every unrelated local modification, ignored cache, untracked worktree, and active feature branch untouched.

### Non-Goals

- Change runtime APIs, agent behavior, provider behavior, or any other product functionality.
- Add or modify automated test files or add a repository verification script.
- Build a hosted documentation site, marketing site, example gallery, or growth campaign.
- Declare support for a Python version that has not already been claimed and verified by the project.
- Rename the distribution, import package, repository, or organization.
- Publish a version other than 0.1.0 unless the package name becomes unavailable or the user explicitly changes the release target.
- Merge the implementation pull request without review.
- Delete local ignored files or clean user-owned working directories.

---

## 3. Background & Context

The packaging foundation was already merged in pull request #173: pyproject.toml identifies vidbyte-sdk 0.1.0, the MIT license exists, README.md advertises pip installation, .gitignore ignores generated packaging/cache outputs, and .github/workflows/publish.yml is configured for PyPI trusted publishing. The launch itself has not happened: as audited on 2026-07-11, PyPI returns no vidbyte-sdk project, the repository has no version tag or GitHub release, the Publish to PyPI workflow has never run, and the GitHub repository has no pypi environment configured.

A clean archive of origin/main at commit 181e871 builds both a source distribution and wheel, and twine check passes both artifacts. Installing the wheel and its dependencies into a fresh virtual environment also passes pip check. The decisive smoke import fails, however: importing vidbyte initializes the prompt catalog, error_correction.json references error_correction_auditor.md, and the Markdown file is absent from the wheel. The current package-data rule includes root JSON and nested JSON/Markdown, but not root Markdown. There are multiple root-level prompt Markdown assets, so this is a package rule defect rather than a missing source file.

The same clean build emits setuptools warnings because project.license uses the deprecated table form and the MIT trove classifier duplicates the newer SPDX mechanism. Current PyPA guidance calls for an SPDX license string plus license-files and requires setuptools 77.0.3 or newer for that metadata form.

Repository hygiene is also below launch quality. origin/main tracks 238 CPython bytecode files below vidbyte/**/__pycache__, although .gitignore now correctly excludes them. The wheel and source distribution currently exclude those bytecode files, so this is source-control noise rather than an artifact contamination issue. The public repository also lacks contribution, security, code-of-conduct, issue-template, and pull-request-template files. Its live description still says the tools are internal, it has no homepage or topics, and its documentation link refers to the obsolete master branch.

The active local checkout and the dedicated local main worktree contain user-owned changes, largely regenerated tracked bytecode. Implementation must therefore start from a fresh origin/main-based isolated worktree and must not clean, reset, switch, or otherwise alter those worktrees.

---

## 4. Requirements

### Functional Requirements

1. Building origin/main after the change must produce vidbyte_sdk-0.1.0.tar.gz and vidbyte_sdk-0.1.0-py3-none-any.whl.
2. Both artifacts must pass python -m twine check.
3. The wheel must contain every JSON and Markdown asset used by vidbyte.prompts.prompts, including root-level Markdown files such as error_correction_auditor.md.
4. Installing the wheel with dependencies into a newly created Python 3.11 virtual environment must make import vidbyte, VidbyteSDK, and Prompts succeed from an empty working directory.
5. The installed distribution metadata version and vidbyte.__version__ must both equal 0.1.0.
6. Prompts().keys() must load successfully, proving that all prompt references resolve from installed package resources.
7. pyproject.toml must use a valid MIT SPDX license expression and explicitly include LICENSE without emitting the audited license deprecation warnings.
8. All 238 tracked bytecode/cache files enumerated in Section 9.1 must be deleted from Git; the existing ignored local copies must not be targeted.
9. The publish workflow must reject a tag whose value does not equal v plus the package version.
10. The publish workflow must build, validate, smoke-install, and upload release artifacts in a non-OIDC job before a separate least-privilege publish job obtains an OIDC token.
11. The publish job must use the GitHub pypi environment and must not read a PyPI username, password, or API token.
12. README.md must accurately identify the alpha release, show the production install command, expose PyPI/release status, and link to support/contribution/security guidance.
13. The repository must provide CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md, bug and feature issue forms, and a pull-request template.
14. The live GitHub repository description, homepage, and topics must match the values defined in Section 6.6.
15. A PyPI pending trusted publisher must be registered with the exact owner, repository, workflow, environment, and project values defined in Section 6.7 before the release tag is created.
16. Creating GitHub release v0.1.0 from the merged main commit must trigger the publish workflow and create the PyPI project.
17. A second clean Python 3.11 environment must successfully install vidbyte-sdk==0.1.0 from production PyPI with --no-cache-dir and pass the same dependency, version, import, and prompt-catalog checks.
18. Publication failure must leave the repository tag/release visible for diagnosis but must not be reported as a successful launch.

### Non-Functional Requirements

- **Performance:** N/A - packaging and release are infrequent operations; correctness is the gate. The smoke install should nevertheless use normal pip behavior and finish within the GitHub Actions job timeout.
- **Scalability:** The release flow must remain valid for later semantic versions without hard-coding 0.1.0 into workflow logic; the tag/version comparison derives the expected value from pyproject.toml.
- **Security:** PyPI upload uses short-lived OIDC credentials, the publish job receives only id-token: write, the GitHub pypi environment restricts deployments to version tags, and third-party actions are pinned to reviewed immutable commits where practical.
- **Observability:** GitHub Actions logs each gate separately, preserves the built distributions as a workflow artifact, and links the workflow run to the GitHub release and deployment environment.
- **Reliability:** No upload occurs if build, metadata validation, dependency validation, package-resource import, or tag/version validation fails. A PyPI release is treated as immutable; remediation uses yanking plus a new patch version rather than overwriting files.
- **Compatibility:** The distribution name remains vidbyte-sdk, the import package remains vidbyte, the release remains alpha, and requires-python remains >=3.11.

---

## 5. High-Level Design

The repository change has four coordinated parts. First, pyproject.toml is corrected so setuptools packages all runtime prompt assets and emits modern license/project metadata. Second, all generated bytecode already tracked by Git is removed while .gitignore remains unchanged because it already prevents recurrence. Third, the release workflow is split into a verification/build job and an OIDC-only publish job. Fourth, the README and community files make the public repository consistent with the package being promoted.

Publication is deliberately separated from pull-request implementation. The implementation pull request proves that a clean source snapshot can build and install. After that pull request is reviewed and merged, the user registers a one-time pending trusted publisher in PyPI. Only then is GitHub release v0.1.0 created. The release tag starts the workflow; the publish job creates the PyPI project through the pending publisher. A final independent install from PyPI closes the gate.

The local worktree strategy protects current user changes:

~~~text
fresh origin/main
      |
      v
isolated launch worktree -> implementation commit(s) -> draft PR -> user review/merge
                                                                |
user registers PyPI pending publisher --------------------------+
                                                                v
                                                GitHub release/tag v0.1.0
                                                                |
                   +--------------------------------------------+----------------+
                   |                                                             |
             build/verify job                                             publish job
       no OIDC, creates artifacts                               pypi environment + OIDC
                   |                                                             |
                   +---------------------- pass only -----------------------------+
                                                                |
                                                                v
                                                         production PyPI
                                                                |
                                                                v
                                              fresh-index install verification
~~~

Key decisions are to fix the smallest correct package-data rule rather than broadly include every Markdown file, use production PyPI pending publishing instead of a manual first upload, and make the installed wheel—not the source tree—the release acceptance surface.

---

## 6. Detailed Design

### 6.1 Package Metadata and Runtime Assets

**File(s):** pyproject.toml
**Type:** Modified

#### What it does

Defines distribution identity, build backend, searchable metadata, project links, runtime dependencies, CLI entry points, package discovery, and non-Python runtime assets.

#### Interface / API

The relevant target shape is:

~~~toml
[build-system]
requires = ["setuptools>=77.0.3"]
build-backend = "setuptools.build_meta"

[project]
name = "vidbyte-sdk"
version = "0.1.0"
description = "Python SDK for building, evaluating, and debugging reliable AI agent harnesses."
license = "MIT"
license-files = ["LICENSE"]
keywords = [
  "ai-agents",
  "agent-harnesses",
  "harness-engineering",
  "llm",
  "mcp",
  "context-engineering",
  "evals",
  "observability",
]

[project.urls]
Homepage = "https://vidbyte.ai"
Documentation = "https://github.com/cerredz/Vidbyte-SDK/tree/main/docs"
Repository = "https://github.com/cerredz/Vidbyte-SDK"
Issues = "https://github.com/cerredz/Vidbyte-SDK/issues"
Changelog = "https://github.com/cerredz/Vidbyte-SDK/releases"

[tool.setuptools.package-data]
"vidbyte.prompts.prompts" = ["*.json", "*.md", "*/*.json", "*/*.md"]
~~~

The existing MIT trove classifier is removed because SPDX license metadata supersedes it and current setuptools warns that license classifiers are deprecated. Other classifiers, dependencies, Python compatibility declarations, scripts, and package-discovery settings remain unchanged.

#### Logic / Algorithm

1. Raise the minimum isolated build dependency from setuptools 68 to 77.0.3, the first setuptools release listed by PyPA as supporting PEP 639.
2. Replace the deprecated license table with license = "MIT" and license-files = ["LICENSE"].
3. Remove only the deprecated MIT license classifier.
4. Refine the one-line project description and keywords around agent-harness engineering.
5. Normalize project URL labels and add documentation and release links that PyPI will display.
6. Add *.md to the root prompt package-data pattern while retaining the current explicit one-subdirectory patterns.
7. Keep the distribution name and both version declarations at 0.1.0.

#### Edge Cases & Error Handling

- If vidbyte-sdk is claimed on PyPI before release, stop before tagging and select a new distribution name through a separate approved design; do not silently rename it.
- If a future prompt asset nests more than one directory deep, the explicit package-data pattern will not include it. That future change must extend the pattern and repeat the installed-wheel smoke check.
- If build tooling rejects PEP 639 metadata, the build-system minimum was not honored; treat that as a build failure rather than reverting to deprecated metadata.
- Source files that are not runtime assets, including general component README files, remain outside the wheel unless separately justified.

### 6.2 Tracked Generated-File Cleanup

**File(s):** The 238 paths in Section 9.1
**Type:** Deleted

#### What it does

Removes committed CPython bytecode and __pycache__ content from the source history at the launch commit. The existing .gitignore already ignores __pycache__/, *.py[cod], build/, dist/, and *.egg-info/, so it is intentionally not modified.

#### Interface / API

N/A - generated binary files expose no supported interface.

#### Logic / Algorithm

1. Create the implementation worktree directly from refreshed origin/main.
2. Recompute the tracked generated-file set and compare it with Section 9.1.
3. Stop for design reconciliation if new tracked generated files appeared or an enumerated path is no longer tracked.
4. Remove only the tracked files in that reconciled set from Git.
5. Confirm git ls-files contains no __pycache__ path or .pyc/.pyo file.
6. Confirm git check-ignore identifies a representative regenerated .pyc path as ignored.
7. Do not run a recursive clean command and do not touch the user's existing worktrees.

#### Edge Cases & Error Handling

- Modified bytecode in existing worktrees belongs to the user and is not reset or deleted.
- If a path that looks generated is actually an intentional fixture, stop and exclude it only with explicit justification.
- Empty __pycache__ directories disappear naturally because Git does not track directories.
- The package build already excludes these files; their removal must still be verified at the Git index level.

### 6.3 Fail-Closed Release Workflow

**File(s):** .github/workflows/publish.yml
**Type:** Modified

#### What it does

Builds and validates immutable release distributions in one job, then publishes exactly those artifacts in a separate trusted-publishing job.

#### Interface / API

The workflow contract is:

~~~yaml
trigger:
  push tags matching v*

concurrency:
  one release workflow per tag

build job:
  permissions: contents read
  verify tag equals v + pyproject project.version
  build sdist and wheel
  run twine check
  create fresh virtual environment
  install the wheel with dependencies
  run pip check
  verify distribution/module version, public imports, and prompt loading
  upload dist artifacts

publish job:
  needs: build
  environment: pypi
  permissions: id-token write
  download the exact build artifacts
  publish with pypa/gh-action-pypi-publish
~~~

Actions are pinned to reviewed immutable commits with human-readable release comments where repository conventions allow. No workflow_dispatch upload path is added.

#### Logic / Algorithm

1. Check out the tagged commit and set up Python 3.11.
2. Parse project.version from pyproject.toml with the standard-library tomllib module.
3. Compare the expected tag v{version} with the actual Git ref name; fail on mismatch.
4. Install build and twine in the runner environment.
5. Build source and wheel artifacts into dist/.
6. Validate both with twine check.
7. Create a separate smoke virtual environment, install only the built wheel plus declared dependencies, and run pip check.
8. Change to a directory outside the source checkout and validate importlib.metadata.version("vidbyte-sdk"), vidbyte.__version__, VidbyteSDK, Prompts, and non-empty Prompts().keys().
9. Upload dist/ as a named immutable workflow artifact.
10. Start the publish job only after every prior step passes.
11. Download the artifact in the publish job and invoke the PyPA action with OIDC; omit username and password.
12. Retain the environment deployment and action logs as the release audit trail.

#### Edge Cases & Error Handling

- Tag/version mismatch stops before artifact upload.
- Missing package data stops during installed-wheel import.
- Dependency conflict stops at pip check.
- Missing or incorrect PyPI publisher configuration fails only the publish job and does not rebuild different artifacts.
- A repeated 0.1.0 upload is rejected by PyPI; do not set skip-existing because that could hide a partial or wrong release.
- If the build job passes and publish fails, fix external configuration and rerun the same tagged workflow only when doing so cannot change the commit or artifact inputs.

### 6.4 README and Public Install Surface

**File(s):** README.md
**Type:** Modified

#### What it does

Makes the repository landing page accurately represent the public package and provide an install-verification and support path.

#### Interface / API

README additions/edits include:

- PyPI version, supported Python, license, and Publish to PyPI workflow badges.
- The canonical command pip install vidbyte-sdk and an optional exact first-release command pip install vidbyte-sdk==0.1.0.
- A minimal verification snippet that prints the installed distribution and module versions and loads Prompts.
- Direct links to CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md, issues, releases, and docs.
- Alpha/stability language remains prominent; no production-stability claim is introduced.

#### Logic / Algorithm

1. Place badges immediately below the title without displacing the existing value proposition.
2. Keep the current comprehensive feature and layer documentation.
3. Expand the Status/Install section with the exact supported installation surface.
4. Add a compact Contributing and Support section near the end.
5. Audit all branch links and replace obsolete master links with main.

#### Edge Cases & Error Handling

- The PyPI badge may be unresolved during the short interval after merge and before v0.1.0 publication; the release sequence should minimize that interval.
- Examples that require provider credentials remain examples; the install smoke snippet must not require network credentials.
- The README must not imply that hosted Vidbyte services or proprietary internals are included.

### 6.5 Public Repository Trust Baseline

**File(s):** CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md, .github/ISSUE_TEMPLATE/bug_report.yml, .github/ISSUE_TEMPLATE/feature_request.yml, .github/pull_request_template.md
**Type:** New files

#### What it does

Provides clear contribution mechanics, private vulnerability reporting, behavioral expectations, and structured issue/review intake for a public SDK.

#### Interface / API

- CONTRIBUTING.md: development prerequisites, virtual-environment setup, editable install, branch/PR expectations, documentation expectations, and the existing repository check commands contributors should run.
- SECURITY.md: supported alpha line, private disclosure through hello@vidbyte.ai, requested report details, response expectations, and a warning not to disclose an unpatched vulnerability publicly.
- CODE_OF_CONDUCT.md: Contributor Covenant 2.1 with hello@vidbyte.ai as the enforcement contact.
- bug_report.yml: summary, environment, installed version, reproduction, expected/actual behavior, logs, and checklist.
- feature_request.yml: problem, proposed outcome, alternatives, intended API surface, and willingness to contribute.
- pull_request_template.md: motivation, change summary, compatibility, verification evidence, documentation, and generated-file checklist.

#### Logic / Algorithm

1. Use concise repository-specific language and existing Python 3.11 requirements.
2. Link the documents to each other and from README.md.
3. Configure issue forms with useful labels only if those labels already exist; otherwise omit automatic labels to avoid invalid metadata.
4. Keep vulnerability handling out of public issue forms.
5. Keep contributor verification guidance aligned with commands that actually exist in the repository.

#### Edge Cases & Error Handling

- hello@vidbyte.ai must be actively monitored before SECURITY.md and CODE_OF_CONDUCT.md are merged.
- No response-time service-level guarantee is promised unless the maintainer confirms one.
- Templates must not require secrets, private prompts, customer data, or provider credentials in public issues.
- If Contributor Covenant updates before implementation, use the then-current official 2.x text only after checking compatibility with the enforcement contact.

### 6.6 Live GitHub Repository Metadata and Environment

**File(s):** N/A - GitHub repository settings, topics, and deployment environment
**Type:** External configuration

#### What it does

Makes the repository discoverable and removes the current contradiction between a public SDK and an "Internal Vidbyte tools" description.

#### Interface / API

Target repository settings:

~~~text
Description:
Python SDK for building, evaluating, and debugging reliable AI agent harnesses.

Homepage:
https://vidbyte.ai

Topics:
python
ai-agents
agent-framework
agent-harness
harness-engineering
llm
mcp
context-engineering
ai-evaluation
observability

Environment:
pypi
deployment source restricted to version tags matching v*
required reviewer: repository owner/maintainer, if the GitHub plan permits
no environment secrets
~~~

#### Logic / Algorithm

1. Apply description, homepage, and topics through the GitHub API after design approval.
2. Create or update the pypi environment with version-tag deployment restrictions.
3. Add the maintainer as a required reviewer when supported.
4. Confirm the public repository page shows the intended metadata.
5. Do not enable unrelated repository features or change visibility, default branch, merge policy, or branch protection.

#### Edge Cases & Error Handling

- If required reviewers are unsupported, keep the tag restriction and document the limitation.
- If vidbyte.ai is not the desired SDK landing page, stop before changing the homepage and use the user-approved URL.
- Topic edits are externally visible immediately and are independently reversible.
- GitHub environment configuration does not configure PyPI trust; both sides must match exactly.

### 6.7 PyPI Publisher, Release, and Clean-Machine Acceptance

**File(s):** N/A - PyPI account configuration, GitHub release, workflow run, and ephemeral verification environments
**Type:** External rollout

#### What it does

Registers the one-time publishing trust, creates the first immutable release, and demonstrates that an unrelated consumer can install the package.

#### Interface / API

Pending PyPI publisher values:

~~~text
PyPI project name: vidbyte-sdk
Owner: cerredz
Repository: Vidbyte-SDK
Workflow name: publish.yml
Environment name: pypi
~~~

Release identity:

~~~text
GitHub tag: v0.1.0
GitHub release title: Vidbyte SDK v0.1.0
Target: merged main commit containing this launch work
Release notes: generated changes plus an explicit Alpha warning
~~~

Post-publication consumer command:

~~~text
python -m venv <fresh-environment>
python -m pip install --no-cache-dir vidbyte-sdk==0.1.0
python -m pip check
python -c "<version, import, VidbyteSDK, and Prompts smoke assertions>"
~~~

#### Logic / Algorithm

1. The user signs into PyPI with a 2FA-enabled account.
2. Under the account Publishing page, the user adds the pending GitHub Actions publisher with the exact five values above.
3. The user confirms the pending publisher is displayed; this does not reserve the name until first upload.
4. The implementation pull request is reviewed and merged.
5. Reconfirm that vidbyte-sdk remains unclaimed on PyPI and that main contains the launch commit.
6. Create GitHub release v0.1.0 targeting that exact main commit; creation pushes the tag and triggers publish.yml.
7. Monitor the build and publish jobs through completion.
8. Confirm the PyPI project page, files, metadata, project links, and provenance/attestation.
9. On a clean Python 3.11 environment outside the repository, install from production PyPI with cache disabled and run the acceptance commands.
10. Record the workflow, GitHub release, PyPI project, and smoke output links in the PR/release handoff.

#### Edge Cases & Error Handling

- A pending publisher does not reserve vidbyte-sdk. If the name is claimed first, stop; never upload under an improvised name.
- If OIDC identity fields differ by case or filename, PyPI denies the upload. Correct the publisher values and rerun without moving the tag.
- If publication succeeds but the consumer smoke fails, yank 0.1.0, fix the defect in a new pull request, and release 0.1.1. PyPI files cannot be replaced.
- If only the GitHub release text is wrong, edit the release notes without moving the tag.
- Never delete and recreate a published version to simulate replacement.

---

## 7. Data Model Changes

N/A - this launch gate changes package/repository metadata, generated files, documentation, and release automation only. It does not change database schemas, serialized runtime models, Pydantic contracts, or migrations.

---

## 8. API Changes

N/A - no HTTP, Python, CLI, MCP, or provider API is added, modified, or deprecated. The installed package becomes usable as already documented; the package-data correction restores the existing public import contract.

---

## 9. File Change Manifest

Complete list of files created, modified, or deleted by the implementation:

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | pyproject.toml | Include root prompt Markdown assets; modernize license, discovery metadata, keywords, and project URLs |
| MODIFY | .github/workflows/publish.yml | Split verification from OIDC publish and enforce tag, artifact, dependency, and installed-wheel gates |
| MODIFY | README.md | Add release/install badges, installed-package verification, corrected links, and contribution/support routes |
| CREATE | CONTRIBUTING.md | Public contribution setup and pull-request expectations |
| CREATE | SECURITY.md | Private vulnerability-reporting policy |
| CREATE | CODE_OF_CONDUCT.md | Contributor Covenant and enforcement contact |
| CREATE | .github/ISSUE_TEMPLATE/bug_report.yml | Structured public bug reports |
| CREATE | .github/ISSUE_TEMPLATE/feature_request.yml | Structured feature proposals |
| CREATE | .github/pull_request_template.md | Review and verification checklist |
| DELETE | 238 files listed in Section 9.1 | Remove tracked CPython bytecode/cache artifacts |

**Total: 3 modified, 6 created, 238 deleted.** The design document itself is the Phase 2 planning artifact and is not counted as an implementation change.

### 9.1 Exact Generated-File Deletion Set

This is the complete tracked cache set at origin/main commit 181e8711eced34b0415561307f058f6082dcd939:

~~~text
vidbyte/agents/__pycache__/__init__.cpython-311.pyc
vidbyte/agents/__pycache__/base.cpython-311.pyc
vidbyte/agents/__pycache__/client.cpython-311.pyc
vidbyte/agents/__pycache__/context_algorithms.cpython-311.pyc
vidbyte/agents/__pycache__/mixins.cpython-311.pyc
vidbyte/agents/__pycache__/registry.cpython-311.pyc
vidbyte/agents/__pycache__/runtime.cpython-311.pyc
vidbyte/agents/__pycache__/types.cpython-311.pyc
vidbyte/agents/algorithms/__pycache__/__init__.cpython-311.pyc
vidbyte/agents/algorithms/__pycache__/multi_provider_agentic_grader.cpython-311.pyc
vidbyte/agents/algorithms/__pycache__/reflexion.cpython-311.pyc
vidbyte/agents/runtimes/__pycache__/__init__.cpython-311.pyc
vidbyte/agents/runtimes/__pycache__/actor.cpython-311.pyc
vidbyte/agents/runtimes/__pycache__/linear.cpython-311.pyc
vidbyte/agents/runtimes/__pycache__/search.cpython-311.pyc
vidbyte/agents/runtimes/actor/__pycache__/__init__.cpython-311.pyc
vidbyte/agents/runtimes/actor/__pycache__/actor.cpython-311.pyc
vidbyte/agents/runtimes/actor/__pycache__/broker.cpython-311.pyc
vidbyte/agents/runtimes/actor/__pycache__/inbox.cpython-311.pyc
vidbyte/agents/runtimes/actor/__pycache__/message.cpython-311.pyc
vidbyte/context/__pycache__/__init__.cpython-311.pyc
vidbyte/context/__pycache__/manager.cpython-311.pyc
vidbyte/context/__pycache__/presets.cpython-311.pyc
vidbyte/context/__pycache__/primitives.cpython-311.pyc
vidbyte/context/__pycache__/window.cpython-311.pyc
vidbyte/context/algorithms/__pycache__/__init__.cpython-311.pyc
vidbyte/context/algorithms/__pycache__/multi_provider_agentic_grader.cpython-311.pyc
vidbyte/context/algorithms/__pycache__/reflexion.cpython-311.pyc
vidbyte/context/algorithms/__pycache__/tool_results.cpython-311.pyc
vidbyte/context/templates/__pycache__/__init__.cpython-311.pyc
vidbyte/context/templates/__pycache__/recorder.cpython-311.pyc
vidbyte/evals/__pycache__/__init__.cpython-311.pyc
vidbyte/evals/__pycache__/base.cpython-311.pyc
vidbyte/evals/__pycache__/client.cpython-311.pyc
vidbyte/evals/__pycache__/registry.cpython-311.pyc
vidbyte/evals/__pycache__/runner.cpython-311.pyc
vidbyte/evals/__pycache__/suite.cpython-311.pyc
vidbyte/evals/__pycache__/types.cpython-311.pyc
vidbyte/evals/graders/__pycache__/__init__.cpython-311.pyc
vidbyte/evals/graders/__pycache__/contains.cpython-311.pyc
vidbyte/evals/graders/__pycache__/exact_match.cpython-311.pyc
vidbyte/evals/graders/__pycache__/json_schema.cpython-311.pyc
vidbyte/evals/graders/__pycache__/llm_judge.cpython-311.pyc
vidbyte/evals/graders/__pycache__/regex_match.cpython-311.pyc
vidbyte/evals/graders/__pycache__/rubric.cpython-311.pyc
vidbyte/harnesses/__pycache__/__init__.cpython-311.pyc
vidbyte/harnesses/__pycache__/client.cpython-311.pyc
vidbyte/lib/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/__pycache__/token_usage.cpython-311.pyc
vidbyte/lib/agents/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/agents/__pycache__/modality_detector.cpython-311.pyc
vidbyte/lib/config/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/config/__pycache__/base.cpython-311.pyc
vidbyte/lib/config/__pycache__/constants.cpython-311.pyc
vidbyte/lib/config/__pycache__/mcp_presets.cpython-311.pyc
vidbyte/lib/config/__pycache__/models.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/agents.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/code_search.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/context.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/context_items.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/filesystem.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/mcp.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/middleware.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/model_configs.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/multi_agent.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/sandbox.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/security.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/strategies.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/tool_types.cpython-311.pyc
vidbyte/lib/dataclasses/__pycache__/tools.cpython-311.pyc
vidbyte/lib/enums/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/enums/__pycache__/context.cpython-311.pyc
vidbyte/lib/enums/__pycache__/model_modality.cpython-311.pyc
vidbyte/lib/enums/__pycache__/model_provider.cpython-311.pyc
vidbyte/lib/enums/__pycache__/platform.cpython-311.pyc
vidbyte/lib/enums/__pycache__/prompts.cpython-311.pyc
vidbyte/lib/errors/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/errors/__pycache__/base.cpython-311.pyc
vidbyte/lib/http/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/http/__pycache__/parser.cpython-311.pyc
vidbyte/lib/http/__pycache__/transport.cpython-311.pyc
vidbyte/lib/models/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/models/__pycache__/registry.cpython-311.pyc
vidbyte/lib/runners/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/runners/__pycache__/base.cpython-311.pyc
vidbyte/lib/runners/__pycache__/image.cpython-311.pyc
vidbyte/lib/runners/__pycache__/router.cpython-311.pyc
vidbyte/lib/runners/__pycache__/text.cpython-311.pyc
vidbyte/lib/runners/__pycache__/types.cpython-311.pyc
vidbyte/lib/runners/__pycache__/video.cpython-311.pyc
vidbyte/lib/templates/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/templates/__pycache__/base.cpython-311.pyc
vidbyte/lib/templates/__pycache__/reflexion.cpython-311.pyc
vidbyte/lib/tools/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/tools/__pycache__/formatter.cpython-311.pyc
vidbyte/lib/tools/filesystem/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/tools/filesystem/__pycache__/permissions.cpython-311.pyc
vidbyte/lib/tools/filesystem/backends/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/tools/filesystem/backends/__pycache__/base.cpython-311.pyc
vidbyte/lib/tools/filesystem/backends/__pycache__/local.cpython-311.pyc
vidbyte/lib/tracing/__pycache__/__init__.cpython-311.pyc
vidbyte/lib/tracing/__pycache__/base.cpython-311.pyc
vidbyte/mcp_server/__pycache__/__init__.cpython-311.pyc
vidbyte/mcp_server/__pycache__/__main__.cpython-311.pyc
vidbyte/mcp_server/__pycache__/handlers.cpython-311.pyc
vidbyte/mcp_server/__pycache__/schema.cpython-311.pyc
vidbyte/mcp_server/server/__pycache__/__init__.cpython-311.pyc
vidbyte/mcp_server/server/__pycache__/core.cpython-311.pyc
vidbyte/mcp_server/server/handlers/__pycache__/__init__.cpython-311.pyc
vidbyte/mcp_server/server/handlers/__pycache__/initialize.cpython-311.pyc
vidbyte/mcp_server/server/handlers/__pycache__/prompts_get.cpython-311.pyc
vidbyte/mcp_server/server/handlers/__pycache__/prompts_list.cpython-311.pyc
vidbyte/mcp_server/server/handlers/__pycache__/tools_call.cpython-311.pyc
vidbyte/mcp_server/server/handlers/__pycache__/tools_list.cpython-311.pyc
vidbyte/middleware/__pycache__/__init__.cpython-311.pyc
vidbyte/middleware/__pycache__/base.cpython-311.pyc
vidbyte/middleware/__pycache__/pipeline.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/__init__.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/audit.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/canary_tripwire.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/circuit_breaker.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/confused_deputy.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/cost_budget.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/exponential_backoff_retry.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/honeypot_tool.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/loop_detection.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/rate_limit.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/retry.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/runtime_limits.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/token_budget.cpython-311.pyc
vidbyte/middleware/builtins/__pycache__/tool_policy.cpython-311.pyc
vidbyte/middleware/compaction/__pycache__/__init__.cpython-311.pyc
vidbyte/middleware/compaction/__pycache__/base.cpython-311.pyc
vidbyte/middleware/compaction/__pycache__/context_compaction.cpython-311.pyc
vidbyte/middleware/compaction/__pycache__/engine.cpython-311.pyc
vidbyte/middleware/compaction/__pycache__/strategies.cpython-311.pyc
vidbyte/pipelines/__pycache__/__init__.cpython-311.pyc
vidbyte/pipelines/__pycache__/base.cpython-311.pyc
vidbyte/pipelines/__pycache__/conditional.cpython-311.pyc
vidbyte/pipelines/__pycache__/map_reduce.cpython-311.pyc
vidbyte/pipelines/__pycache__/parallel.cpython-311.pyc
vidbyte/pipelines/__pycache__/sequential.cpython-311.pyc
vidbyte/pipelines/__pycache__/types.cpython-311.pyc
vidbyte/prompts/__pycache__/__init__.cpython-311.pyc
vidbyte/prompts/__pycache__/agentic_loop.cpython-311.pyc
vidbyte/prompts/__pycache__/catalog.cpython-311.pyc
vidbyte/prompts/__pycache__/registry.cpython-311.pyc
vidbyte/prompts/prompts/__pycache__/__init__.cpython-311.pyc
vidbyte/providers/__pycache__/__init__.cpython-311.pyc
vidbyte/providers/__pycache__/anthropic.cpython-311.pyc
vidbyte/providers/__pycache__/base.cpython-311.pyc
vidbyte/providers/__pycache__/client.cpython-311.pyc
vidbyte/providers/__pycache__/compatible.cpython-311.pyc
vidbyte/providers/__pycache__/gemini.cpython-311.pyc
vidbyte/providers/__pycache__/openai.cpython-311.pyc
vidbyte/providers/__pycache__/openrouter.cpython-311.pyc
vidbyte/providers/__pycache__/xai.cpython-311.pyc
vidbyte/providers/tracing/__pycache__/__init__.cpython-311.pyc
vidbyte/providers/tracing/__pycache__/langfuse.cpython-311.pyc
vidbyte/providers/tracing/__pycache__/langsmith.cpython-311.pyc
vidbyte/providers/tracing/__pycache__/phoenix.cpython-311.pyc
vidbyte/shared/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/__pycache__/_internal.cpython-311.pyc
vidbyte/tools/__pycache__/adapters.cpython-311.pyc
vidbyte/tools/__pycache__/agent_tool.cpython-311.pyc
vidbyte/tools/__pycache__/base.cpython-311.pyc
vidbyte/tools/__pycache__/catalog.cpython-311.pyc
vidbyte/tools/__pycache__/client.cpython-311.pyc
vidbyte/tools/__pycache__/decorators.cpython-311.pyc
vidbyte/tools/__pycache__/executor.cpython-311.pyc
vidbyte/tools/__pycache__/function_tool.cpython-311.pyc
vidbyte/tools/__pycache__/mixins.cpython-311.pyc
vidbyte/tools/__pycache__/registry.cpython-311.pyc
vidbyte/tools/__pycache__/types.cpython-311.pyc
vidbyte/tools/builtins/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/builtins/__pycache__/calculator.cpython-311.pyc
vidbyte/tools/builtins/__pycache__/code_execution.cpython-311.pyc
vidbyte/tools/builtins/__pycache__/document_retrieval.cpython-311.pyc
vidbyte/tools/builtins/code_search/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/builtins/code_search/__pycache__/base.cpython-311.pyc
vidbyte/tools/builtins/code_search/__pycache__/glob.cpython-311.pyc
vidbyte/tools/builtins/code_search/__pycache__/grep.cpython-311.pyc
vidbyte/tools/builtins/code_search/__pycache__/semantic.cpython-311.pyc
vidbyte/tools/builtins/context/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/builtins/context/__pycache__/compaction.cpython-311.pyc
vidbyte/tools/builtins/context/__pycache__/types.cpython-311.pyc
vidbyte/tools/builtins/context_primitives/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/builtins/context_primitives/__pycache__/list_tool.cpython-311.pyc
vidbyte/tools/builtins/context_primitives/__pycache__/remove.cpython-311.pyc
vidbyte/tools/builtins/context_primitives/__pycache__/upsert.cpython-311.pyc
vidbyte/tools/builtins/editing/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/builtins/editing/__pycache__/patch.cpython-311.pyc
vidbyte/tools/builtins/handoff/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/builtins/handoff/__pycache__/create.cpython-311.pyc
vidbyte/tools/builtins/mcp/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/builtins/mcp/__pycache__/attach_tool.cpython-311.pyc
vidbyte/tools/builtins/mcp/__pycache__/search.cpython-311.pyc
vidbyte/tools/builtins/memory/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/builtins/memory/__pycache__/base.cpython-311.pyc
vidbyte/tools/builtins/memory/__pycache__/cognee.cpython-311.pyc
vidbyte/tools/builtins/memory/__pycache__/letta.cpython-311.pyc
vidbyte/tools/builtins/memory/__pycache__/mem0.cpython-311.pyc
vidbyte/tools/builtins/memory/__pycache__/supermemory.cpython-311.pyc
vidbyte/tools/builtins/memory/__pycache__/zep.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/_base_tool.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/append_text.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/base.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/checksum.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/copy.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/delete.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/diff.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/exists.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/find.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/list_dir.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/make_dir.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/move.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/read_binary.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/read_lines.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/read_text.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/replace_text.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/stat.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/touch.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/tree.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/write_text.cpython-311.pyc
vidbyte/tools/filesystem/__pycache__/zip_tools.cpython-311.pyc
vidbyte/tools/mcp/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/mcp/__pycache__/attach.cpython-311.pyc
vidbyte/tools/mcp/__pycache__/bridge.cpython-311.pyc
vidbyte/tools/mcp/__pycache__/client.cpython-311.pyc
vidbyte/tools/mcp/__pycache__/presets.cpython-311.pyc
vidbyte/tools/mcp/__pycache__/transport.cpython-311.pyc
vidbyte/tools/mcp/__pycache__/types.cpython-311.pyc
vidbyte/tools/security/__pycache__/__init__.cpython-311.pyc
vidbyte/tools/security/__pycache__/permissions.cpython-311.pyc
vidbyte/tools/security/__pycache__/sandbox.cpython-311.pyc
~~~

Before deletion, implementation must regenerate this inventory from the refreshed base. Any difference requires updating this design manifest or obtaining explicit approval before proceeding.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | 3.11 for release smoke; project remains >=3.11 | Build and clean-install acceptance runtime | A platform-specific import defect may require a follow-up matrix outside this no-tests scope |
| setuptools | >=77.0.3 | PEP 639 metadata and wheel/sdist construction | New backend behavior can change package discovery; artifact inspection and smoke import gate it |
| build | Current release installed in workflow | Standards-based isolated sdist/wheel build | Unpinned installer resolution can change; workflow logs exact resolved version |
| twine | Current release installed in workflow | Distribution metadata validation | Valid metadata does not prove runtime resources; separate wheel smoke is mandatory |
| pip/venv | Python 3.11 standard tooling/current pip | Consumer-like installation and dependency check | Index/network outages can fail rollout without a code defect |
| GitHub Actions | https://github.com/cerredz/Vidbyte-SDK/actions | Release orchestration and OIDC identity | Workflow/tag/environment identity must match PyPI exactly |
| GitHub Environments | pypi | Deployment restriction and optional approval | Plan limitations may affect required reviewers |
| pypa/gh-action-pypi-publish | release/v1 line, pinned to reviewed commit | Exchange GitHub OIDC identity for a short-lived PyPI upload token | Third-party action supply chain; immutable pin and least privilege mitigate it |
| PyPI | https://pypi.org/project/vidbyte-sdk/ | Public package index and immutable release host | Pending publisher does not reserve the package name |
| PyPI Trusted Publishing | https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/ | Create the first project without manual token upload | Exact owner/repo/workflow/environment values are security-sensitive |
| Contributor Covenant | Official 2.1 text | Public conduct policy | Enforcement address must be monitored |

---

## 11. Rollout & Deployment

No feature flags are involved and no runtime API migration is required.

1. **Approval gate:** User reviews this design, confirms the defaults in Section 12, and explicitly approves implementation.
2. **Isolated implementation:** Create a new worktree and branch from freshly fetched origin/main, commit this design document first, then make only the manifest changes. Do not use either dirty existing worktree.
3. **Pre-PR acceptance:** Build from a clean exported source snapshot, run twine check, inspect artifact contents, install the wheel into a fresh environment from an empty directory, run pip check, and validate imports/version/prompt loading. Confirm the Git index is free of caches.
4. **External GitHub metadata:** Apply the approved description, homepage, topics, and pypi environment settings; capture the resulting state.
5. **Draft PR:** Push the branch and open a draft pull request into main with the artifact and smoke evidence. The design-doc-no-tests workflow stops at the draft PR; it does not merge.
6. **User-only PyPI step:** The user registers the pending trusted publisher with the exact values in Section 6.7 and confirms completion.
7. **Review and merge:** User reviews and merges the pull request.
8. **Release:** Reconfirm package-name availability and create GitHub release/tag v0.1.0 against the merged main commit.
9. **Publish monitoring:** Observe both workflow jobs. Do not announce success until the PyPI upload completes.
10. **Post-publish acceptance:** Install 0.1.0 from production PyPI in a new environment with cache disabled and rerun the full smoke gate.

Rollback before publication is a normal revert of the implementation commit plus reversal of GitHub metadata/environment settings. After publication, PyPI artifacts are immutable: if the release is unsafe or broken, yank 0.1.0, document the reason in the GitHub release, fix through a new pull request, and publish 0.1.1. Deleting a GitHub tag or release is not a PyPI rollback.

---

## 12. Open Questions

The following defaults are recommended. Approval of this design is treated as approval of these defaults unless the user overrides one explicitly.

- [ ] Use version 0.1.0 and tag v0.1.0 for the first public release.
- [ ] Use "Python SDK for building, evaluating, and debugging reliable AI agent harnesses." as both the PyPI/GitHub short description.
- [ ] Use https://vidbyte.ai as the repository homepage and the ten topics in Section 6.6.
- [ ] Confirm hello@vidbyte.ai is actively monitored for security and conduct reports.
- [ ] Confirm the user can sign into PyPI with 2FA and create the pending publisher immediately before release.
- [ ] Use the current GitHub repository owner as the pypi environment reviewer when supported.
- [ ] Leave all dirty existing worktrees untouched and create a new isolated worktree directly from origin/main.
- [ ] Add the six community trust files now rather than postponing them until after package launch.

---

## 13. Alternatives Considered

### Alternative 1: Manual First Upload with a PyPI API Token

- What: Create the PyPI project by uploading 0.1.0 manually, then configure automation later.
- Why rejected: It introduces a long-lived secret and a one-off release path that is harder to reproduce and audit. PyPI pending publishers are designed to create a new project on first OIDC use.

### Alternative 2: Publish the Current Artifact and Fix Package Data in 0.1.1

- What: Tag the existing main branch because build and twine validation pass, then repair imports in a patch release.
- Why rejected: A clean consumer cannot import the installed package. Publishing a known-broken first release would damage the exact adoption signal this launch gate is meant to improve.

### Alternative 3: Include Every Markdown and JSON File Recursively

- What: Use broad recursive package-data patterns for all Vidbyte packages.
- Why rejected: It would enlarge the distribution and make unrelated internal documentation part of the runtime artifact. The explicit prompt package boundary fixes the observed defect with a smaller, auditable surface.

### Alternative 4: Keep Build and Publish in One OIDC-Enabled Job

- What: Add smoke commands to the existing single job.
- Why rejected: The build steps would unnecessarily execute in a job allowed to request a PyPI identity token, and there would be no immutable artifact handoff between verification and upload.

### Alternative 5: Clean Existing Local Worktrees in Place

- What: Reset or remove regenerated bytecode from the user's current checkout and main worktree before implementation.
- Why rejected: Those worktrees contain user-owned changes. A fresh origin/main-based worktree provides a trustworthy base without destroying or conflating unrelated work.

### Alternative 6: Defer Community Files Until After Launch

- What: Publish the package with only packaging and workflow changes.
- Why rejected: Promotion will direct developers to a public repository that currently lacks basic contribution, security, conduct, issue, and review routes. Adding the small trust baseline makes the first public impression coherent with the launch.
