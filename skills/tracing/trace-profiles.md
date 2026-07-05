<!--
Context Protocol Header

Description:
    Skill for semantic trace profiles in the Vidbyte SDK.
Purpose:
    Documents TraceProfile presets, per-component overrides, the allows()
    filtering logic, the component and setting vocabularies, and payload
    redaction/truncation.
Architecture:
    - Covers vidbyte/trace/profiles.py (TraceProfile, TraceComponentSettings,
      safe_trace_value, _is_secret_key).
    - References vidbyte/trace/schema.py for SpanSpec and TraceDetail.
Relations:
    Sub-skill of skills/tracing/SKILL.md. Pairs with trace-types.md (detail
    levels) and trace-controller-and-session.md (how allows() is applied).
-->

# Trace Profiles

A **trace profile** controls which semantic spans survive filtering and how
payloads are sanitized before they reach a provider. Profiles live in
`vidbyte/trace/profiles.py`; the `TraceController` calls `profile.allows(spec)`
on every span (see `trace-controller-and-session.md`).

## `TraceProfile` Dataclass

`TraceProfile` is an immutable (`frozen=True`, `slots=True`) dataclass:

```python
@dataclass(frozen=True, slots=True)
class TraceProfile:
    detail: TraceDetail = TraceDetail.STANDARD
    components: Mapping[str, str | bool] = field(default_factory=dict)
    redact: bool = True
    max_chars: int = 12000
```

- `detail` — the overall detail threshold (`MINIMAL`/`STANDARD`/`VERBOSE`/`DIAGNOSTIC`).
- `components` — per-component overrides keyed by component name.
- `redact` — whether `safe_trace_value` strips credential-like keys.
- `max_chars` — string truncation limit (must be > 0).

`__post_init__` validates `max_chars > 0` and that every component/setting in
`components` is known, raising `ConfigurationError` otherwise.

## The Detail Presets

Each detail preset is a classmethod that builds a profile with a uniform
component setting across all 19 components:

| Preset | `detail` | Component setting | Keeps |
|--------|----------|-------------------|-------|
| `TraceProfile.minimal()` | `MINIMAL` | `"minimal"` | `agent.run`, `llm.call`, `tool.call` |
| `TraceProfile.default()` | `STANDARD` | `"default"` | Minimal plus parser spans, tool input/output, `agent.stop`, retriever/embedding categories, session roots |
| `TraceProfile.verbose()` | `VERBOSE` | `"verbose"` | Default plus `runtime.iteration`, context-window summaries, algorithm phases, aggregate phases, middleware decisions |
| `TraceProfile.diagnostic()` | `DIAGNOSTIC` | `"diagnostic"` | Verbose plus diagnostic spans (e.g. `middleware.hook`) and fuller metadata |

```python
from vidbyte import TraceProfile

profile = TraceProfile.default()
profile = TraceProfile.verbose()
profile = TraceProfile.diagnostic()
```

## The Role-Oriented Presets

Role-oriented presets hand-tune per-component settings for a specific use case
instead of applying one setting uniformly. They are still immutable
`TraceProfile` instances and support `with_components(...)` overrides.

| Preset | `detail` | Tuned for |
|--------|----------|-----------|
| `TraceProfile.production()` | `STANDARD` | Live traffic: keeps agents/middleware-decisions/tools/parsers/core, turns off context/algorithms/runtimes/aggregate/pipelines/handoff/sources/evals/mcp/sessions. |
| `TraceProfile.cost_monitoring()` | `STANDARD` | Cost attribution: `middleware` verbose, `tools` inputs/outputs, `runtimes` default; algorithms/context/parsers off. |
| `TraceProfile.developer()` | `VERBOSE` | Local development: `agents`/`tools`/`runtimes` on, `context` summary, `algorithms` default, `middleware` decisions-only; sources/evals/mcp off. |
| `TraceProfile.multi_agent()` | `VERBOSE` | Multi-agent workflows: `aggregate`/`pipelines`/`handoff`/`sessions` verbose, `tools` minimal, `middleware` decisions-only. |
| `TraceProfile.algorithm_debug()` | `VERBOSE` | In-context learning debugging: `algorithms`/`context`/`runtimes` verbose, aggregate/pipelines/handoff/sources/evals/mcp off. |

```python
from vidbyte import Trace, TraceProfile

# Live traffic with only the high-signal spans.
trace = Trace.profile(inner=Trace.langsmith(...), profile=TraceProfile.production())

# Cost attribution across a multi-agent workflow, then tuned further.
profile = TraceProfile.cost_monitoring().with_components(aggregate="default")
```

## `with_components(**components)`

Returns a copy with selected components overridden, leaving the rest untouched.
Each override is validated against the component and setting vocabularies.

```python
from vidbyte import TraceProfile

# Default profile, but turn middleware decisions on and tools down to minimal.
profile = TraceProfile.default().with_components(
    middleware="decisions_only",
    tools="minimal",
)
```

## `allows(spec)` Filtering Logic

`TraceController` calls `profile.allows(span_spec)` to decide whether a span is
emitted or suppressed. The logic resolves the per-component setting first, then
applies it:

```python
def allows(self, spec: SpanSpec) -> bool:
    setting = dict(self.components).get(spec.component, "default")
    if setting is False or setting == "off":
        return False
    if setting is True:
        return _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[self.detail]
    if setting == "minimal":
        return spec.detail is TraceDetail.MINIMAL
    if setting == "decisions_only":
        return spec.name == "middleware.decision" or _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[TraceDetail.STANDARD]
    if setting in {"default", "summary", "inputs_outputs"}:
        return _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[TraceDetail.STANDARD]
    if setting == "verbose":
        return _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[TraceDetail.VERBOSE]
    if setting == "diagnostic":
        return True
    return _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[self.detail]
```

`_DETAIL_ORDER` is `MINIMAL=0 < STANDARD=1 < VERBOSE=2 < DIAGNOSTIC=3`.

## The 19 Component Names

A component name identifies a group of spans. Unknown names raise
`ConfigurationError` from `_validate_component_setting`.

| Component | Spans it governs (examples) |
|-----------|------------------------------|
| `agents` | `agent.run`, `agent.stop`, `agent.loop_settings.*`, `agent.output_contract.*`, `agent.handoff.*`, `agent.modality.resolved`, `agent.algorithm.resolved`, `agent.mcp.attached`, `agent.runner.created` |
| `aggregate` | `aggregate.run`, `aggregate.proposer`, `aggregate.synthesis`, `aggregate.failure` |
| `runtimes` | `runtime.iteration`, `runtime.stop`, `runtime.linear.model_call/tool_batch/stop_condition` |
| `actor` | `runtime.actor.run/spawn/message/completion/quiescence/compile_prompt` |
| `search` | `runtime.search.run/node/rollback/expand/evaluate/select` |
| `context` | `context.window.build`, `context.compaction.*`, `context.manager.*`, `context.primitive.*`, `context.template.record`, `context.handoff.sync` |
| `algorithms` | `algorithm.<name>` |
| `middleware` | `middleware.decision`, `middleware.hook`, `middleware.<hook>.ran`, `middleware.action.*`, `middleware.exception`, `middleware.transform.applied`, `middleware.builtin.<name>` |
| `tools` | `tool.call`, `tool.permission`, `tool.resolve`, `tool.validate`, `tool.deny`, `tool.error`, `tool.compact`, `tool.parallel_batch`, `tool.mcp.*` |
| `parsers` | `parser.tool_calls`, `parser.structured_output`, `parser.is_done`, `parser.response_format_built` |
| `pipelines` | `pipeline.{sequential,parallel,conditional,map_reduce}.run`, `pipeline.stage.invoke` |
| `handoff` | `handoff.generate`, `handoff.validate`, `handoff.record`, `handoff.sync` |
| `sources` | `source.fetch`, `source.load`, `source.cache.hit`, `source.cache.miss` |
| `evals` | `eval.run`, `eval.grade`, `eval.behavior` |
| `mcp` | `mcp.attach`, `mcp.search`, `mcp.transport` |
| `sessions` | `session.start`, `session.end`, `session.case` |
| `retrievers` | retriever-category spans |
| `embeddings` | embedding-category spans |
| `core` | fallback for spans without a specific component |

See `trace-components.md` for the full span-spec catalog.

## The Setting Values

A component setting is a string from this set or a boolean:

| Setting | Effect |
|---------|--------|
| `False` / `"off"` | Suppress all spans for this component. |
| `True` | Allow spans whose detail is at or below the profile's `detail`. |
| `"minimal"` | Allow only `MINIMAL`-detail spans. |
| `"default"` / `"summary"` / `"inputs_outputs"` | Allow spans at or below `STANDARD`. |
| `"decisions_only"` | Allow `middleware.decision` plus spans at or below `STANDARD`. |
| `"verbose"` | Allow spans at or below `VERBOSE`. |
| `"diagnostic"` | Allow everything. |

`_SETTING_VALUES = {"off", "minimal", "default", "summary", "decisions_only", "inputs_outputs", "verbose", "diagnostic"}`.

## `TraceComponentSettings`

A small helper dataclass wrapping a component map with a safe default:

```python
@dataclass(frozen=True, slots=True)
class TraceComponentSettings:
    components: Mapping[str, str | bool] = field(default_factory=dict)

    def resolve(self, component: str) -> str | bool:
        return dict(self.components).get(component, "default")
```

It is the lower-level container `TraceProfile` builds on top of.

## Payload Redaction and Truncation

`safe_trace_value(value, *, max_chars=12000, redact=True)` recursively sanitizes
a payload **before it leaves the semantic layer**. This is independent of the
agent layer's own `_safe_trace_value` (see `enabling-tracing.md`); both run, so
redaction happens at two layers.

- **Mappings**: drops any key whose uppercased name is credential-like (when
  `redact=True`), and recurses into surviving values.
- **Tuples / lists**: recurses element-wise.
- **Long strings**: truncates to `max_chars` with a `"...[truncated]"` suffix.
- **Other values**: returned unchanged.

`_is_secret_key(key)` flags a key when its uppercased form starts with
`LANGSMITH_` or contains any of `API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`,
`CREDENTIAL`, or `AUTH`.

```python
from vidbyte.trace.profiles import safe_trace_value

safe_trace_value({"api_key": "sk-...", "prompt": "x" * 20000}, max_chars=12000, redact=True)
# -> {"prompt": "<first 12000 chars>...[truncated]"}   (api_key dropped)
```

## Putting It Together

```python
from vidbyte import Trace, TraceProfile

events = []
trace = Trace.profile(
    inner=Trace.debug(events),
    profile=TraceProfile.verbose().with_components(
        middleware="decisions_only",
        context="off",
    ),
    provider="langsmith",
)
```

This wraps a debug tracer in a verbose profile that keeps middleware decisions
only and suppresses all context-window spans, with LangSmith `run_type`
translation applied to whatever survives.
