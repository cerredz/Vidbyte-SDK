# Design Doc: MCP Preset Expansion — 100 Additional Presets

**Status:** Approved
**Author:** Claude
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

This change adds 100 new `McpPresetDefinition` constants to the vidbyte-sdk MCP preset catalog,
expanding the library from 101 to 201 presets. The new presets cover two brand-new categories
(E-Commerce & Payments; Automation & Workflow) and fill major gaps across all existing categories.
Every new preset follows the identical pattern and naming conventions already established in
`vidbyte/lib/config/mcp_presets.py` and is wired into the `McpPresetRegistry` and all public
`__all__` exports without modifying any other part of the SDK.

---

## 2. Goals & Non-Goals

### Goals
- Add exactly 100 net-new `McpPresetDefinition` constants, each with a unique `name`, `category`,
  `description`, `command`, and `required_env` matching the established schema.
- Introduce two new logical categories: `"E-Commerce & Payments"` and `"Automation & Workflow"`.
- Keep `ALL_PRESETS`, `__all__`, registry class attributes, and re-exports fully in sync.
- Write a verification test script covering structural correctness and uniqueness invariants.

### Non-Goals
- Modifying the `McpPresetDefinition` dataclass schema.
- Adding actual npm/PyPI packages to the project dependencies.
- Implementing or testing real MCP subprocess connections for the new presets.
- Modifying any other SDK layer (agents, pipelines, strategies, providers).

---

## 3. Background & Context

The current preset catalog (101 entries) is the primary value-add of the `vidbyte.tools.mcp.presets`
module — it lets developers attach popular external services to agents with a single line. The
catalog was designed for extension (no hardcoded length limits, a simple list append pattern), but
popular tools like Stripe, Shopify, Elasticsearch, Datadog, Zapier, and many others are missing.
Adding 100 more dramatically widens the SDK's coverage and matches what the community expects from a
production-grade agent framework.

---

## 4. Requirements

### Functional Requirements
1. Every new preset must be a frozen `McpPresetDefinition` dataclass instance.
2. Every new preset must have a globally unique `name` value (kebab-case) not already in `ALL_PRESETS`.
3. Every new preset must be appended to `ALL_PRESETS` so `McpPresetRegistry` auto-registers it.
4. Every new preset must be exported in the `__all__` list of `mcp_presets.py`.
5. Every new preset must be imported and re-exported in `vidbyte/tools/mcp/presets.py`, with a
   matching class attribute on `McpPresetRegistry`.
6. The total `ALL_PRESETS` count after the change must equal 201.
7. No existing preset name, constant name, or registry attribute may be removed or renamed.

### Non-Functional Requirements
- No additional pip/npm dependencies introduced in `pyproject.toml`.
- Verification script must exit 0 only when all structural invariants pass.
- No performance impact — presets are frozen dataclasses loaded at import time.

---

## 5. High-Level Design

Two Python files are touched: the canonical preset catalog
(`vidbyte/lib/config/mcp_presets.py`) and the registry facade
(`vidbyte/tools/mcp/presets.py`). A new test script
(`scripts/test-mcp-preset-expansion.py`) validates structural correctness.

```
vidbyte/lib/config/mcp_presets.py    ← 100 new constants + ALL_PRESETS + __all__
        │
        │ imported by
        ▼
vidbyte/tools/mcp/presets.py         ← 100 new imports + class attrs + __all__
        │
        │ registered in
        ▼
McpPresetRegistry._presets           ← 201 entries total at import time
```

Each new constant follows the existing pattern verbatim. Two new category comment blocks are
inserted inline. The `ALL_PRESETS` list and both `__all__` lists are extended in matching order.

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/config/mcp_presets.py`

**File:** `vidbyte/lib/config/mcp_presets.py`
**Type:** Modified

#### What it does
Canonical source of every preset definition. We append 100 new constants grouped by category,
extend `ALL_PRESETS`, and extend `__all__`.

#### Interface / API
```python
# Pattern is identical for all 100 new entries:
StripeMCP = McpPresetDefinition(
    name="stripe",
    category="E-Commerce & Payments",
    description="...",
    command=("npx", "-y", "stripe-mcp-server"),
    required_env=("STRIPE_SECRET_KEY",),
)
```

#### Logic / Algorithm
1. Append new constants, grouped under the same section-comment style as existing blocks.
2. Extend `ALL_PRESETS` with all 100 new constants in the same order they are declared.
3. Extend `__all__` with all 100 new constant name strings.

#### Edge Cases & Error Handling
- Name collision would cause `McpPresetRegistry.register` to silently overwrite; uniqueness is
  enforced by the test script, not at runtime.

### 6.2 `vidbyte/tools/mcp/presets.py`

**File:** `vidbyte/tools/mcp/presets.py`
**Type:** Modified

#### What it does
Registry facade. We add 100 new imports from the config module, 100 new class attributes on
`McpPresetRegistry`, and extend the module's `__all__`.

#### Interface / API
```python
# New imports
from vidbyte.lib.config.mcp_presets import (
    StripeMCP, ShopifyMCP, ...
)
# New registry class attributes
class McpPresetRegistry:
    Stripe: ClassVar[McpPresetDefinition] = StripeMCP
    Shopify: ClassVar[McpPresetDefinition] = ShopifyMCP
    ...
```

### 6.3 `scripts/test-mcp-preset-expansion.py`

**File:** `scripts/test-mcp-preset-expansion.py`
**Type:** New file

#### What it does
Standalone Python script that imports the registry, runs structural assertions, and prints
PASS/FAIL per test case.

---

## 7. Data Model Changes

N/A — `McpPresetDefinition` schema is unchanged.

---

## 8. API Changes

N/A — no HTTP endpoints modified.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/config/mcp_presets.py` | Add 100 new preset constants, extend ALL_PRESETS and __all__ |
| MODIFY | `vidbyte/tools/mcp/presets.py` | Import + register 100 new presets, extend class attrs and __all__ |
| CREATE | `scripts/test-mcp-preset-expansion.py` | Verification test script |
| CREATE | `docs/design/mcp-preset-expansion-100.md` | This design doc |

---

## 10. Testing Plan

### Unit Tests
- `describe('ALL_PRESETS')` → `it('has exactly 201 entries after expansion')` — [Hidden Assumption]
- `describe('ALL_PRESETS')` → `it('contains no duplicate name values')` — [Silent Failure]
- `describe('McpPresetRegistry')` → `it('registers all 201 presets by name')` — [Hidden Failure]
- `describe('McpPresetRegistry')` → `it('raises McpPresetNotFoundError for unknown preset')` — [Edge Case]
- `describe('McpPresetDefinition')` → `it('every preset has non-empty name and command')` — [Hidden Assumption]
- `describe('McpPresetDefinition')` → `it('every preset command tuple has at least one element')` — [Edge Case]
- `describe('McpPresetDefinition')` → `it('every preset category is a known string')` — [Silent Failure]
- `describe('ALL_PRESETS __all__')` → `it('__all__ length matches ALL_PRESETS + 1 (McpPresetDefinition)')` — [Silent Failure]

### Integration Tests
- The existing `test_mcp_attachment.py` suite must continue to pass without modification.
- The existing `test_config_validation.py` must pass.

### Manual / QA Test Cases
1. Given a fresh Python environment, when `from vidbyte.lib.config.mcp_presets import StripeMCP` is
   executed, then the import succeeds and `StripeMCP.name == "stripe"` — [Hidden Assumption]
2. Given `McpPresetRegistry.list_presets()`, when called with no category filter, then it returns
   a tuple of 201 items — [Silent Failure]
3. Given `McpPresetRegistry.list_presets(category="E-Commerce & Payments")`, when called, then it
   returns the 5 e-commerce presets — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | — | No new runtime dependencies | None |

---

## 12. Rollout & Deployment

- No feature flags required — presets are pure data constants.
- Not a breaking change — existing presets unchanged, new ones additive.
- No deployment ordering — single library, single pip package version bump.
- Rollback: revert the two modified files; no DB migrations or state to undo.

---

## 13. Open Questions

- [ ] Should `command` tuples for presets that have no official MCP package use a stable PyPI
  package name or a placeholder? (Current approach: follow the `python -m mcp_server_<name>` pattern
  already established in the codebase for community servers.)

---

## 14. Alternatives Considered

### Alternative 1: Split into multiple files by category
- What: Each category gets its own `mcp_presets_<category>.py` file.
- Why rejected: The existing design centralises all presets in one file with a single `ALL_PRESETS`
  list. Splitting adds import complexity with no benefit at 201 entries.

### Alternative 2: Generate presets from a YAML/JSON manifest
- What: Define presets in a data file and generate Python at build time.
- Why rejected: Over-engineering for a list of frozen dataclasses; the current inline approach is
  readable, type-safe, and consistent with what already exists.
