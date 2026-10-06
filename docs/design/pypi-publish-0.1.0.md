# Design Doc: PyPI Alpha Publish (0.1.0)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-25
**Last Updated:** 2026-06-25

---

## 1. Overview

Publish `vidbyte-sdk` to PyPI at version `0.1.0` with an explicit alpha stability
marker so that `pip install vidbyte-sdk` works from day one. The change converts
the current `UNLICENSED` marker to MIT, adds PyPI-required metadata (classifiers,
project URLs, `__version__`), updates the README to reflect published status, adds
a `LICENSE` file, creates a `.gitignore` to eliminate pycache noise, and wires a
GitHub Actions workflow that publishes automatically on every version tag push.

---

## 2. Goals & Non-Goals

### Goals
- Make `pip install vidbyte-sdk` work from any Python 3.11+ environment
- Claim the `vidbyte-sdk` namespace on PyPI immediately (name-squatting defense)
- Surface the package on the PyPI discovery page with correct metadata (alpha status, MIT license, homepage)
- Provide `__version__` for `importlib.metadata.version("vidbyte-sdk")` support
- Automate future releases via GitHub Actions trusted publisher (no API tokens stored)
- Add a `.gitignore` so `__pycache__` noise disappears from `git status`

### Non-Goals
- Optional dependency groups (audit confirmed all providers use HTTP-only — no provider SDKs required)
- Pinning to a pre-release version string like `0.1.0a1` (the `Development Status :: 3 - Alpha` classifier and README banner are sufficient signals)
- Changing any runtime behavior of the SDK
- Setting up TestPyPI validation (the package is simple enough to publish directly)
- Configuring the PyPI trusted publisher on pypi.org (requires a one-time manual step in the PyPI UI — documented in Section 11)

---

## 3. Background & Context

The `vidbyte-sdk` package has been actively developed and is used in production via
local installs. Its `pyproject.toml` already has a valid `name`, `version`, and
`setuptools` build backend. The only blockers are:

1. `license = { text = "UNLICENSED" }` — enterprise tooling flags unlicensed packages; MIT removes the friction
2. No classifiers or project URLs — the PyPI page would be nearly empty
3. README says "this package is not published" — needs updating to the install command
4. No `LICENSE` file — PyPI won't show a license link without it
5. No `__version__` — `importlib.metadata` can derive it, but explicit is conventional
6. No `.gitignore` — `__pycache__` noise pollutes every `git status`
7. No publish automation — manual publish is error-prone and hard to repeat

The vidbyte-skills npm package is already at v0.3.0 on npm. Every day the Python
SDK is absent from PyPI is a day with zero organic installs.

---

## 4. Requirements

### Functional Requirements
1. `pip install vidbyte-sdk` installs successfully on Python 3.11+
2. `python -c "import vidbyte; print(vidbyte.__version__)"` prints `0.1.0`
3. The PyPI project page shows: name, description, MIT license, alpha classifier, homepage URL, source URL, Python version trove classifiers
4. `git push --tags` triggers the publish workflow and uploads to PyPI without requiring a stored API token
5. `.gitignore` suppresses `__pycache__`, `dist/`, `*.egg-info/`, and `.pytest_cache/` from `git status`

### Non-Functional Requirements
- No changes to import behavior or SDK runtime
- Publish workflow must use PyPI trusted publisher (OIDC) — no `PYPI_TOKEN` secret
- MIT license text must be the standard OSI-approved 21-line form
- README alpha banner must be the first visible content on the PyPI page (i.e., first line of README.md)

---

## 5. High-Level Design

Three categories of change:

**Package metadata** — `pyproject.toml` gains MIT license, trove classifiers, project
URLs, and keeps the existing `name`/`version`/`dependencies` unchanged. A `LICENSE`
file is added to the repo root so PyPI can link it.

**SDK surface** — `vidbyte/__init__.py` gets a single `__version__ = "0.1.0"` line
added. No other SDK code changes.

**Repo hygiene** — `README.md` replaces the "not published" section with an alpha
banner and install instructions. A `.gitignore` is created to suppress pycache,
dist, and egg-info.

**Automation** — `.github/workflows/publish.yml` fires on `push: tags: ["v*"]`,
builds with `python -m build`, and uploads via the official PyPI publish action
using OIDC trusted publisher (no secrets stored in the repo).

```
Developer pushes git tag v0.1.0
         |
         v
GitHub Actions: publish.yml
  1. actions/checkout
  2. actions/setup-python 3.11
  3. pip install build
  4. python -m build  -> dist/vidbyte_sdk-0.1.0.tar.gz + .whl
  5. pypa/gh-action-pypi-publish  (OIDC trusted publisher)
         |
         v
     pypi.org/project/vidbyte-sdk/
```

---

## 6. Detailed Design

### 6.1 `pyproject.toml`

**File:** `pyproject.toml`
**Type:** Modified

#### What it does
Adds MIT license, trove classifiers, project URL table, and `keywords` field.
Everything else (`name`, `version`, `description`, `dependencies`, `requires-python`,
`scripts`, `package-data`) is unchanged.

#### Interface / API
```toml
[project]
name = "vidbyte-sdk"
version = "0.1.0"
description = "Python SDK for building, evaluating, and distributing AI agent workflows."
readme = "README.md"
requires-python = ">=3.11"
license = { file = "LICENSE" }
authors = [
  { name = "Vidbyte", email = "hello@vidbyte.ai" }
]
keywords = ["ai", "agents", "llm", "sdk", "mcp", "pipelines", "evals"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Topic :: Software Development :: Libraries :: Python Modules",
  "Topic :: Scientific/Engineering :: Artificial Intelligence",
]
dependencies = [
  "pydantic>=2,<3",
  "httpx>=0.27",
]

[project.urls]
Homepage = "https://vidbyte.ai"
Source = "https://github.com/cerredz/Vidbyte-SDK"
"Bug Tracker" = "https://github.com/cerredz/Vidbyte-SDK/issues"
```

#### Logic / Algorithm
Replace the `license` field from `{ text = "UNLICENSED" }` to `{ file = "LICENSE" }`.
Add `keywords`, `classifiers`, and extended `[project.urls]`. Keep all other fields as-is.

#### Edge Cases & Error Handling
- `license = { file = "LICENSE" }` requires `LICENSE` to exist at the repo root; Section 6.2 creates it
- `twine check dist/*` must pass before upload; the classifiers and README format must be valid reStructuredText or CommonMark

---

### 6.2 `LICENSE`

**File:** `LICENSE`
**Type:** New file

#### What it does
Standard MIT license text. Required for PyPI to show a license badge and link.

#### Interface / API
```
MIT License

Copyright (c) 2026 Vidbyte

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

#### Edge Cases & Error Handling
N/A — static file with no logic.

---

### 6.3 `vidbyte/__init__.py`

**File:** `vidbyte/__init__.py`
**Type:** Modified

#### What it does
Adds a module-level `__version__` string so callers can do
`importlib.metadata.version("vidbyte-sdk")` or `vidbyte.__version__`.

#### Interface / API
```python
__version__ = "0.1.0"
```

#### Logic / Algorithm
Insert `__version__ = "0.1.0"` as the first non-comment, non-import line — immediately
before the `from __future__ import annotations` line at the top of the file (after the
docstring block), so it's visible at module level without importing anything.

#### Edge Cases & Error Handling
- Must stay in sync with `version` in `pyproject.toml` on future releases; this is a
  known manual sync requirement common to all Python packages without `importlib.metadata`
  auto-derive patterns

---

### 6.4 `README.md`

**File:** `README.md`
**Type:** Modified

#### What it does
Replaces the "Status" section that says "This package is not published. It is marked
`UNLICENSED` until Vidbyte's release..." with an alpha banner and install instructions.
The rest of the README is unchanged.

#### Interface / API
New "Status" section content:
```markdown
## Status

> **Alpha — active development.** APIs may change between minor versions.

Install from PyPI:

```bash
pip install vidbyte-sdk
```

#### Logic / Algorithm
Find the existing `## Status` section and replace its body (the paragraph starting
"This package is not published...") with the alpha banner and install command.

#### Edge Cases & Error Handling
- The install command must appear early enough in the README that it renders on the
  PyPI project page without truncation (PyPI renders the full README, so placement
  within the file is fine)

---

### 6.5 `.gitignore`

**File:** `.gitignore`
**Type:** New file

#### What it does
Prevents `__pycache__`, `dist/`, `*.egg-info/`, `.pytest_cache/`, and common editor
artifacts from appearing in `git status`.

#### Interface / API
```gitignore
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.pytest_cache/
.env
*.egg
```

#### Edge Cases & Error Handling
N/A — static file. Must not ignore `vidbyte/prompts/prompts/` JSON assets which are
package data.

---

### 6.6 `.github/workflows/publish.yml`

**File:** `.github/workflows/publish.yml`
**Type:** New file

#### What it does
GitHub Actions workflow that triggers on any `v*` tag push, builds the sdist + wheel,
and publishes to PyPI via OIDC trusted publisher (no API token required).

#### Interface / API
```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - "v*"

jobs:
  publish:
    name: Build and publish
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Build
        run: |
          pip install build
          python -m build
      - name: Publish
        uses: pypa/gh-action-pypi-publish@release/v1
```

#### Logic / Algorithm
1. Checkout the tagged commit
2. Set up Python 3.11
3. Install `build` and run `python -m build` → produces `dist/vidbyte_sdk-*.tar.gz` and `.whl`
4. `pypa/gh-action-pypi-publish` uploads to PyPI using OIDC (`id-token: write` permission)

#### Edge Cases & Error Handling
- If the trusted publisher is not configured on pypi.org, the publish step will fail
  with a 403 — see Section 11 for the one-time setup step
- If the tag version does not match `pyproject.toml` version, PyPI will reject the
  upload with a version conflict error — the tag must always match the declared version

---

## 7. Data Model Changes

N/A — no database or schema changes.

---

## 8. API Changes

N/A — no HTTP endpoints changed.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `pyproject.toml` | MIT license, classifiers, keywords, project URLs |
| MODIFY | `vidbyte/__init__.py` | Add `__version__ = "0.1.0"` |
| MODIFY | `README.md` | Replace "not published" status with alpha banner + install command |
| CREATE | `LICENSE` | MIT license text required for PyPI license link |
| CREATE | `.gitignore` | Suppress pycache/dist/egg-info noise from git status |
| CREATE | `.github/workflows/publish.yml` | Automated publish on version tag via OIDC |

**Total: 3 modified, 3 created, 0 deleted.**

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `build` (PyPI) | `>=1.0` | sdist + wheel builder; install-time only | Low — standard tool |
| `pypa/gh-action-pypi-publish` | `release/v1` | GitHub Action for OIDC upload | Low — official PyPA action |
| pypi.org | trusted publisher OIDC endpoint | Upload destination | Low — stable API |
| GitHub Actions | ubuntu-latest | CI runner | Low |

No new runtime dependencies are added to the SDK itself.

---

## 11. Rollout & Deployment

### One-time manual step (before first tag push)

Configure a **PyPI trusted publisher** on https://pypi.org/manage/account/publishing/:

| Field | Value |
|-------|-------|
| PyPI project name | `vidbyte-sdk` |
| GitHub owner | `cerredz` |
| GitHub repository | `Vidbyte-SDK` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

Then create a `pypi` environment in the GitHub repo settings
(`Settings → Environments → New environment → pypi`).

### Publish flow (after setup)

```bash
# From vidbyte-sdk/ root
git tag v0.1.0
git push origin v0.1.0
# → GitHub Actions picks up the tag → builds → uploads to PyPI
```

### No feature flags
This is a pure publish change — no feature flags, no migration path, no rollback
needed beyond "don't push the tag."

### Breaking changes
None. Existing local installs continue to work. PyPI adds a new distribution slot.

---

## 12. Open Questions

- [ ] Should the author email be `hello@vidbyte.ai` or left blank? (Current `pyproject.toml` has no email)
- [ ] Is the GitHub repo URL `https://github.com/cerredz/Vidbyte-SDK` correct for the Source link?
- [ ] Should a `CHANGELOG.md` be created alongside this? (Not required for publish but common convention)

---

## 13. Alternatives Considered

### Alternative 1: Pre-release version string (`0.1.0a1`)
- What: Use PEP 440 pre-release suffix so `pip install vidbyte-sdk` skips it by default (requires `--pre` flag)
- Why rejected: Forces every tutorial and comparison page to use `pip install --pre vidbyte-sdk`. The `Development Status :: 3 - Alpha` classifier plus README banner already signals alpha without hiding the package from default installs.

### Alternative 2: Optional dependency groups per provider
- What: Add `[project.optional-dependencies]` with `anthropic`, `openai`, `gemini` groups
- Why rejected: Audit confirmed all providers use HTTP directly via `httpx` — no third-party provider SDKs are imported anywhere in the package. Optional groups would be empty and misleading.

### Alternative 3: Manual twine upload instead of GitHub Actions
- What: `pip install twine && twine upload dist/*` with a stored API token
- Why rejected: OIDC trusted publisher is more secure (no long-lived credential), more repeatable, and the workflow is the standard approach for new packages in 2024+.

### Alternative 4: Keep `UNLICENSED` and add a note
- What: Keep the license as-is, rely on README to explain
- Why rejected: Enterprise dependency scanners (Snyk, Dependabot, pip-audit) flag UNLICENSED packages. MIT removes the friction and is the standard choice for developer-facing SDKs.
