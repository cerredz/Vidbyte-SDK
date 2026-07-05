# Design Doc: Trace Profile Presets

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-04
**Last Updated:** 2026-07-04
**Base Branch:** `feat/trace-component-expansion` (depends on PR: trace-component-expansion)

---

## 1. Overview

This feature adds 5 role-oriented trace profile presets to `TraceProfile` that are designed for specific debugging personas and operational scenarios. Unlike the existing 4 detail-level presets (`minimal`, `default`, `verbose`, `diagnostic`) which answer "how much detail," these role presets answer "what for" — each one composes component settings non-uniformly to produce a trace tree optimized for a specific use case.

---

## 2. Goals & Non-Goals

### Goals

- Add `TraceProfile.production()` — safe default for live traffic with minimal overhead and error visibility.
- Add `TraceProfile.cost_monitoring()` — focus on token/cost budget middleware and tool usage.
- Add `TraceProfile.developer()` — good local development defaults with runtime iteration visibility.
- Add `TraceProfile.multi_agent()` — verbose aggregate, pipeline, and handoff tracing with minimal tool noise.
- Add `TraceProfile.algorithm_debug()` — verbose algorithm and context spans for in-context learning debugging.
- Each preset must compose component settings non-uniformly (not just set all components to one level).
- Each preset must be a `@classmethod` on `TraceProfile` following the existing pattern.
- Each preset must return an immutable `TraceProfile` instance.

### Non-Goals

- Do not modify the existing `minimal()`, `default()`, `verbose()`, or `diagnostic()` presets.
- Do not modify `TraceProfile.allows()` filtering logic.
- Do not modify the `SpanSpec` dataclass or `SpanKind`/`TraceDetail`/`ParentPolicy` enums.
- Do not modify the `_COMPONENTS` set or `_SETTING_VALUES` set.
- Do not modify the `TraceController` or provider translators.
- Do not add tests or verification scripts (design-doc-no-tests workflow).

---

## 3. Background & Context

PR #198 introduced `TraceProfile` with 4 detail-level presets. The existing presets set all components uniformly to one detail level:

```python
@classmethod
def minimal(cls) -> TraceProfile:
    return cls(detail=TraceDetail.MINIMAL, components=_base_components("minimal"))
```

Where `_base_components(setting)` returns `{component: setting for component in _COMPONENTS}`.

This is useful for controlling overall verbosity, but it does not address role-specific scenarios. A developer debugging the agent loop needs runtime iterations and stop conditions but does not need MCP transport detail. A production deployment needs errors and aborts but not context window builds. A multi-agent orchestration debug session needs aggregate and pipeline spans but not per-tool resolution.

The companion PR (trace-component-expansion) adds new component names (`pipelines`, `handoff`, `sources`, `evals`, `mcp`) and many new span specs with appropriate detail levels. This PR leverages those new components to build role-oriented presets that compose component settings non-uniformly.

The key insight is: **detail presets answer "how much", role presets answer "what for"**. Both coexist. A user can further customize a role preset with `.with_components(...)`.

---

## 4. Requirements

### Functional Requirements

1. `TraceProfile.production()` must return a profile that:
   - Sets `detail=TraceDetail.STANDARD` as the overall threshold.
   - Sets `agents=True` (all agent spans up to STANDARD).
   - Sets `middleware="decisions_only"` (only middleware decisions and non-continue actions).
   - Sets `tools=True` (tool calls up to STANDARD).
   - Sets `context="off"` (no context window spans).
   - Sets `algorithms="off"` (no algorithm spans).
   - Sets `runtimes="off"` (no runtime iteration spans).
   - Sets `parsers="default"` (parser spans up to STANDARD).
   - Sets `aggregate="off"` (no aggregate spans).
   - Sets `pipelines="off"`, `handoff="off"`, `sources="off"`, `evals="off"`, `mcp="off"`.
   - Sets `sessions="off"`, `actor="off"`, `search="off"`.
   - Sets `retrievers="off"`, `embeddings="off"`, `core="default"`.

2. `TraceProfile.cost_monitoring()` must return a profile that:
   - Sets `detail=TraceDetail.STANDARD`.
   - Sets `agents="summary"` (agent run/stop summaries only).
   - Sets `middleware="verbose"` (full middleware visibility for budget/cost/token middleware).
   - Sets `tools="inputs_outputs"` (tool inputs and outputs for cost attribution).
   - Sets `context="off"`.
   - Sets `algorithms="off"`.
   - Sets `runtimes="default"` (runtime stop conditions for iteration counts).
   - Sets `parsers="off"`.
   - Sets `aggregate="off"`.
   - Sets `pipelines="off"`, `handoff="off"`, `sources="off"`, `evals="off"`, `mcp="off"`.
   - Sets `sessions="off"`, `actor="off"`, `search="off"`.
   - Sets `retrievers="off"`, `embeddings="off"`, `core="default"`.

3. `TraceProfile.developer()` must return a profile that:
   - Sets `detail=TraceDetail.VERBOSE`.
   - Sets `agents=True` (all agent spans up to VERBOSE).
   - Sets `middleware="decisions_only"` (middleware decisions without per-hook noise).
   - Sets `tools=True` (tool lifecycle up to VERBOSE).
   - Sets `context="summary"` (context window build summaries).
   - Sets `algorithms="default"` (algorithm spans up to STANDARD).
   - Sets `runtimes=True` (runtime iterations and stop conditions).
   - Sets `parsers="default"`.
   - Sets `aggregate="default"`.
   - Sets `pipelines="default"`, `handoff="default"`, `sources="off"`, `evals="off"`, `mcp="off"`.
   - Sets `sessions="default"`, `actor="off"`, `search="off"`.
   - Sets `retrievers="off"`, `embeddings="off"`, `core="default"`.

4. `TraceProfile.multi_agent()` must return a profile that:
   - Sets `detail=TraceDetail.VERBOSE`.
   - Sets `agents=True`.
   - Sets `middleware="decisions_only"`.
   - Sets `tools="minimal"` (only tool.call spans, no lifecycle detail).
   - Sets `context="off"`.
   - Sets `algorithms="off"`.
   - Sets `runtimes="default"` (runtime stop conditions for loop visibility).
   - Sets `parsers="off"`.
   - Sets `aggregate=True` (full aggregate phase visibility).
   - Sets `pipelines=True` (full pipeline visibility).
   - Sets `handoff=True` (full handoff lifecycle visibility).
   - Sets `sources="off"`, `evals="off"`, `mcp="off"`.
   - Sets `sessions=True` (session grouping visibility).
   - Sets `actor="default"`, `search="default"`.
   - Sets `retrievers="off"`, `embeddings="off"`, `core="default"`.

5. `TraceProfile.algorithm_debug()` must return a profile that:
   - Sets `detail=TraceDetail.VERBOSE`.
   - Sets `agents=True`.
   - Sets `middleware="decisions_only"`.
   - Sets `tools="default"` (tool calls up to STANDARD).
   - Sets `context=True` (full context window and compaction visibility).
   - Sets `algorithms=True` (full algorithm visibility including reflexion, grader, checkpoints).
   - Sets `runtimes=True` (runtime iterations for algorithm loop visibility).
   - Sets `parsers="default"`.
   - Sets `aggregate="off"`.
   - Sets `pipelines="off"`, `handoff="off"`, `sources="off"`, `evals="off"`, `mcp="off"`.
   - Sets `sessions="off"`, `actor="off"`, `search="off"`.
   - Sets `retrievers="off"`, `embeddings="off"`, `core="default"`.

6. All 5 presets must be `@classmethod` methods on `TraceProfile`.
7. All 5 presets must return `TraceProfile` instances constructed via `cls(detail=..., components={...})`.
8. All 5 presets must include a 1-line comment describing the preset's purpose.
9. All 5 presets must use valid component names from `_COMPONENTS` and valid setting values from `_SETTING_VALUES`.
10. All 5 presets must set `redact=True` and `max_chars=12000` (the existing defaults).

### Non-Functional Requirements

- Compatibility: No existing preset behavior may change.
- Maintainability: Each preset must be self-documenting via its method name and comment.
- Performance: Preset construction is a one-time cost; no runtime overhead.

---

## 5. High-Level Design

The 5 new presets are `@classmethod` methods on `TraceProfile` that construct profiles with non-uniform component settings. Each preset starts from a base `detail` threshold and then selectively enables or disables specific components using the existing `components` mapping.

The design follows the existing preset pattern:

```python
@classmethod
def production(cls) -> TraceProfile:
    # Safe default for live traffic: errors and aborts without internal noise.
    return cls(
        detail=TraceDetail.STANDARD,
        components={
            "agents": True,
            "middleware": "decisions_only",
            "tools": True,
            "parsers": "default",
            "core": "default",
            "context": "off",
            "algorithms": "off",
            "runtimes": "off",
            "aggregate": "off",
            "pipelines": "off",
            "handoff": "off",
            "sources": "off",
            "evals": "off",
            "mcp": "off",
            "sessions": "off",
            "actor": "off",
            "search": "off",
            "retrievers": "off",
            "embeddings": "off",
        },
    )
```

Each preset explicitly sets every component in `_COMPONENTS` to make its intent clear and to avoid implicit behavior from unset components defaulting to `"default"` in `TraceProfile.resolve()`.

The key design decision is **which components to enable at which level for each role**. The principle is: enable only what the persona needs to see, disable everything else, and use the minimum detail level that provides useful information.

---

## 6. Detailed Design

### 6.1 production()

**File(s):** `vidbyte/trace/profiles.py`
**Type:** Modified

#### What it does

Returns a profile optimized for live production traffic: agent run/stop, tool calls, middleware aborts/denials, and parser errors — without context window, algorithm, runtime iteration, or orchestration noise.

#### Interface / API

```python
@classmethod
def production(cls) -> TraceProfile: ...
```

#### Logic / Algorithm

1. Set `detail=TraceDetail.STANDARD`.
2. Enable `agents=True`, `tools=True`, `parsers="default"`, `core="default"`.
3. Enable `middleware="decisions_only"` to capture abort_run, deny_tool, and exceptions without per-hook noise.
4. Disable all other components (`context`, `algorithms`, `runtimes`, `aggregate`, `pipelines`, `handoff`, `sources`, `evals`, `mcp`, `sessions`, `actor`, `search`, `retrievers`, `embeddings`).
5. Return `cls(detail=..., components={...})`.

#### Edge Cases & Error Handling

- The profile uses `True` for `agents` and `tools` which means `allows()` checks detail threshold against the profile's `STANDARD` detail. This is correct: production needs STANDARD-level agent and tool spans.

### 6.2 cost_monitoring()

**File(s):** `vidbyte/trace/profiles.py`
**Type:** Modified

#### What it does

Returns a profile focused on cost and token budget monitoring: full middleware visibility (for TokenBudgetMiddleware, CostBudgetMiddleware, TokenRateLimitMiddleware), tool inputs/outputs for cost attribution, and runtime stop conditions for iteration counts.

#### Interface / API

```python
@classmethod
def cost_monitoring(cls) -> TraceProfile: ...
```

#### Logic / Algorithm

1. Set `detail=TraceDetail.STANDARD`.
2. Enable `agents="summary"` for agent run/stop summaries.
3. Enable `middleware="verbose"` for full middleware decision visibility (budget/cost/token middleware emit decisions at VERBOSE).
4. Enable `tools="inputs_outputs"` for tool call inputs and outputs (cost attribution).
5. Enable `runtimes="default"` for runtime stop conditions (iteration counts).
6. Enable `core="default"`.
7. Disable all other components.
8. Return `cls(detail=..., components={...})`.

### 6.3 developer()

**File(s):** `vidbyte/trace/profiles.py`
**Type:** Modified

#### What it does

Returns a profile with good local development defaults: agent enforcement events, middleware decisions, tool lifecycle, context window summaries, runtime iterations, algorithm spans, and pipeline/handoff/session visibility — without per-hook middleware noise or source/eval/MCP detail.

#### Interface / API

```python
@classmethod
def developer(cls) -> TraceProfile: ...
```

#### Logic / Algorithm

1. Set `detail=TraceDetail.VERBOSE`.
2. Enable `agents=True`, `tools=True`, `context="summary"`, `algorithms="default"`, `runtimes=True`, `parsers="default"`, `aggregate="default"`, `pipelines="default"`, `handoff="default"`, `sessions="default"`, `core="default"`.
3. Enable `middleware="decisions_only"` (decisions without per-hook noise).
4. Disable `sources`, `evals`, `mcp`, `actor`, `search`, `retrievers`, `embeddings`.
5. Return `cls(detail=..., components={...})`.

### 6.4 multi_agent()

**File(s):** `vidbyte/trace/profiles.py`
**Type:** Modified

#### What it does

Returns a profile optimized for multi-agent orchestration debugging: full aggregate, pipeline, handoff, and session visibility with minimal tool noise. Shows runtime stop conditions for loop visibility but suppresses context window and algorithm detail.

#### Interface / API

```python
@classmethod
def multi_agent(cls) -> TraceProfile: ...
```

#### Logic / Algorithm

1. Set `detail=TraceDetail.VERBOSE`.
2. Enable `agents=True`, `aggregate=True`, `pipelines=True`, `handoff=True`, `sessions=True`, `runtimes="default"`, `actor="default"`, `search="default"`, `core="default"`.
3. Enable `middleware="decisions_only"`.
4. Enable `tools="minimal"` (only `tool.call` spans, no lifecycle detail).
5. Disable `context`, `algorithms`, `parsers`, `sources`, `evals`, `mcp`, `retrievers`, `embeddings`.
6. Return `cls(detail=..., components={...})`.

### 6.5 algorithm_debug()

**File(s):** `vidbyte/trace/profiles.py`
**Type:** Modified

#### What it does

Returns a profile optimized for in-context learning algorithm debugging: full algorithm and context visibility, runtime iterations for algorithm loop visibility, and agent enforcement events. Suppresses aggregate, pipeline, handoff, and all non-essential components.

#### Interface / API

```python
@classmethod
def algorithm_debug(cls) -> TraceProfile: ...
```

#### Logic / Algorithm

1. Set `detail=TraceDetail.VERBOSE`.
2. Enable `agents=True`, `tools="default"`, `context=True`, `algorithms=True`, `runtimes=True`, `parsers="default"`, `core="default"`.
3. Enable `middleware="decisions_only"`.
4. Disable `aggregate`, `pipelines`, `handoff`, `sources`, `evals`, `mcp`, `sessions`, `actor`, `search`, `retrievers`, `embeddings`.
5. Return `cls(detail=..., components={...})`.

---

## 7. Data Model Changes

N/A - No data model changes. All new presets return existing `TraceProfile` instances.

---

## 8. API Changes

### 8.1 Python API: New TraceProfile Presets

**Change type:** New

```python
from vidbyte import TraceProfile

profile = TraceProfile.production()
profile = TraceProfile.cost_monitoring()
profile = TraceProfile.developer()
profile = TraceProfile.multi_agent()
profile = TraceProfile.algorithm_debug()

# Further customization
profile = TraceProfile.developer().with_components(mcp="verbose")
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | All presets use valid component names and setting values |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/trace-profile-presets.md` | Design doc for trace profile presets |
| MODIFY | `vidbyte/trace/profiles.py` | Add 5 new preset classmethods to TraceProfile |

Summary: 1 file to create, 1 file to modify, 0 files to delete.

---

## 10. Testing Plan

N/A - Design-doc-no-tests workflow. Verification will be done via lint and typecheck.

---

## 11. Dependencies

- **Depends on:** PR: trace-component-expansion — adds the `pipelines`, `handoff`, `sources`, `evals`, `mcp` component names to `_COMPONENTS` that these presets reference.
- **Depends on:** PR #198 (`feat/semantic-trace-profiles`) — provides `TraceProfile` and the existing preset pattern.
- **No new external dependencies.**

---

## 12. Rollout

1. Merge PR #198 (`feat/semantic-trace-profiles`) to main.
2. Merge PR: trace-component-expansion to main.
3. Merge this PR to main.
4. The new presets are immediately available via `TraceProfile.production()`, etc.

---

## 13. Open Questions

1. **Should `production()` set `sessions="default"` instead of `"off"`?** Current design: off. Rationale: production traces usually use one agent per trace, not sessions. If session grouping is needed, `Trace.langsmith_session()` already handles it.

2. **Should `developer()` enable `actor` and `search` by default?** Current design: off. Rationale: most developers use the linear runtime. Actor/search developers can enable via `.with_components(actor=True, search=True)`.

3. **Should `cost_monitoring()` use `runtimes="verbose"` instead of `"default"`?** Current design: default. Rationale: runtime stop conditions (STANDARD detail) are sufficient for iteration counts. Verbose would add per-iteration spans which is more noise than needed for cost monitoring.

---

## 14. Alternatives Considered

### Alternative 1: Builder pattern instead of classmethods

Instead of `TraceProfile.production()`, use `TraceProfile.builder().for_production().build()`.

**Rejected because:** The existing pattern uses `@classmethod` presets (`minimal()`, `default()`, `verbose()`, `diagnostic()`). The new presets follow the same pattern for consistency.

### Alternative 2: String-based preset selection

Instead of `TraceProfile.production()`, use `TraceProfile.preset("production")`.

**Rejected because:** String-based selection loses type safety and IDE autocomplete. The classmethod approach is self-documenting and matches the existing pattern.

### Alternative 3: Compose presets from existing presets

Instead of building each preset from scratch, compose them: `TraceProfile.developer() = TraceProfile.default().with_components(runtimes=True, context="summary", ...)`.

**Rejected because:** The existing `default()` preset sets all components uniformly to `"default"`. Starting from it and overriding would leave unwanted components at `"default"` instead of explicitly disabling them. Building from scratch with explicit settings is clearer and more maintainable.
