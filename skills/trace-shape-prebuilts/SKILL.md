---
name: trace-shape-prebuilts
description: >-
  Explains the OTel GenAI and OpenInference trace shape prebuilts (PR #390):
  what they are, why they exist, and how to extend them. Use when adding a
  new external trace shape/company, wiring a new destination tracer, mapping
  a new span kind's standard field names, or reviewing a trace-shape PR.
---

<!-- Context Protocol Header
Description:
    Explains the "trace shape prebuilt" feature: exporting Vidbyte's existing
    semantic trace spans into an external company's exact published wire format.
Purpose:
    Teaches contributors why this feature exists, how shape and destination
    stay decoupled, what is and is not implemented today, and the checklist
    for adding a new shape.
Architecture:
    SDK Skill Guide (feature explainer + contributor process).
Relations:
    Located in skills/trace-shape-prebuilts/SKILL.md.
    Implementation: vidbyte/trace/providers/{otel_genai,openinference}.py,
    vidbyte/providers/tracing/otel.py, vidbyte/trace/base.py.
    Design: docs/design/otel-genai-and-openinference-trace-shapes.md.
Similar Files:
    - skills/tool-settings/SKILL.md
    - skills/vidbyte-sdk/SKILL.md (Semantic Trace Components section)
    - docs/design/semantic-trace-profiles.md
    - docs/design/trace-facade.md
-->

# Trace Shape Prebuilts Skill Guide

Use this skill when you need to **understand, extend, or review** a "trace
shape prebuilt" — a `ProviderTraceTranslator` that maps Vidbyte's existing
semantic trace spans into one external company's exact published wire format
(field names, span-naming rules, required attributes). Shipped in PR #390 as
the OTel GenAI and OpenInference shapes.

Related:

- Design doc: `docs/design/otel-genai-and-openinference-trace-shapes.md`
- The underlying semantic tracing system this builds on: `docs/design/semantic-trace-profiles.md`
- The `Trace` facade this adds to: `docs/design/trace-facade.md`
- The close-time follow-up (response text, usage data) this feature enabled: `skills/trace-close-attributes/SKILL.md`

---

## 1. What This Feature Is

Vidbyte agents already emit a rich, provider-neutral semantic trace —
`agent.run`, `llm.call`, `tool.call`, and more — through `TraceController`
(`vidbyte/trace/controller.py`). Before this feature, that trace could only be
translated into one external shape: LangSmith's `run_type`. **Trace shape
prebuilts** are the same idea generalized: a small, focused translator that
takes the exact same internal recording and re-labels it into a *different*
company's exact field names, so a user can point an agent at a real buyer's
tooling — AWS Bedrock AgentCore, Datadog LLM Observability, Arize Phoenix —
with a one-line config change, not a rewrite.

```python
from vidbyte import Agent, Trace

agent = Agent(..., trace=Trace.otel_genai(endpoint="https://<adot-collector>/v1/traces"))
# or
agent = Agent(..., trace=Trace.openinference(endpoint="http://localhost:6006/v1/traces"))
```

This is a **translation** feature, not a **capture** feature. It does not
change what the runtime records — only how an already-recorded span gets
relabeled and delivered. If a piece of information was never turned into a
semantic span attribute in the first place (see [Section 5](#5-future-directions)),
no shape translator can invent it.

---

## 2. Intent — Why This Exists

Outside feedback on Vidbyte's research harness identified a concrete,
buildable gap: the harness tracks its own steps internally (for crash-resume
reliability), but had no way to export a run in the shape an outside buyer's
tooling actually reads. AWS Bedrock AgentCore's Evaluate API is built to
import OpenTelemetry traces using the GenAI semantic conventions
(`gen_ai.*`); without that shape, "sell trace data to AWS" had no concrete
implementation path.

Two design decisions follow directly from that intent:

1. **Shape and destination are two different axes, kept fully decoupled.**
   "Which field names does the span use" (the *shape* — a
   `ProviderTraceTranslator`) is independent from "which OTLP endpoint
   receives it" (the *destination* — an `OTelTracer` endpoint). One
   `OTelTracer`, pointed at different URLs, reaches Phoenix, a Datadog Agent,
   an AWS ADOT collector, or a self-hosted OTel Collector — no
   destination-specific tracer needed per shape.
2. **Only verify, never guess, a field name.** Both companies' semantic
   conventions are still pre-1.0 and actively evolving. Each translator only
   maps the span kinds whose field names were verified against the live spec
   document at implementation time (agent/LLM/tool spans, for both shapes
   today). Everything else falls back to a namespaced (`vidbyte.*`)
   passthrough rather than inventing a plausible-looking but unverified
   field — a wrong invented field silently produces a trace that looks
   compliant to a human reviewer but isn't, which defeats the entire point
   of shipping a "standard-shaped" export.

---

## 3. How It Works

```
Agent / AgentRuntime
  self._tracer.start_span("llm.call", model=..., tool_name=..., ...)
        |
        v
TraceController  (profile filter -> redact/truncate -> SpanSpec)
        |
        v
ProviderTraceTranslator   <-- the "shape": OTelGenAIProviderTranslator / OpenInferenceProviderTranslator
        |                       (also: GenericProviderTranslator, LangSmithProviderTranslator)
        v
ProviderSpanPayload(name, attributes)
        |
        v
inner: TracerBase   <-- the "destination": OTelTracer (endpoint=any OTLP collector)
        |                 (also: LangSmithTracer, LangfuseTracer, PhoenixTracer)
        v
   OTLP/HTTP  -->  Phoenix  |  Datadog Agent  |  AWS ADOT collector (-> AgentCore/CloudWatch)  |  self-hosted OTel Collector
```

A translator never touches a transport. `OTelTracer.start_span` never
inspects a span's name or kind — it forwards every attribute the translator
produced exactly as given. This is what makes a shape reusable across
destinations, and (via `Trace.phoenix_default`) even across two different
inner tracers for the same shape.

### What's implemented today

| Shape | Translator | `provider=` string | Facade helpers |
|---|---|---|---|
| OTel GenAI (`gen_ai.*`) | `OTelGenAIProviderTranslator` — `vidbyte/trace/providers/otel_genai.py` | `"otel-genai"` | `Trace.otel_genai(...)`, `Trace.otel_genai_session(...)` |
| OpenInference (`llm.*`/`tool.*`/`openinference.span.kind`) | `OpenInferenceProviderTranslator` — `vidbyte/trace/providers/openinference.py` | `"openinference"` | `Trace.openinference(...)`, `Trace.openinference_session(...)`, `Trace.phoenix_default(...)` |
| LangSmith `run_type` (pre-existing) | `LangSmithProviderTranslator` | `"langsmith"` | `Trace.langsmith_default(...)`, `Trace.langsmith_session(...)` |

Verified field mappings exist only for **agent invocation, LLM/chat calls,
and tool execution** spans — the three concretely tied to the AWS
AgentCore / Datadog motivation. Every other span kind (`retriever`,
`embedding`, `parser`, `prompt`, and Vidbyte-specific concepts like
`aggregate.*`, `algorithm.*`, `middleware.*`, `runtime.*`, `multi_agent.*`,
`session.*`) currently falls back to a namespaced passthrough — see
[Section 5](#5-future-directions).

### Destination transport

`OTelTracer` (`vidbyte/providers/tracing/otel.py`) is the one transport both
new shapes ride on. It resolves an endpoint from the `endpoint=` argument or
the standard `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` /
`OTEL_EXPORTER_OTLP_ENDPOINT` env vars, accepts `headers=` for
collector auth, and coerces every attribute value for OTel's wire format:
primitives pass through unchanged, `None` is skipped, everything else is
JSON-encoded (`json.dumps(..., default=str)`) — never a raw Python `repr`.
The pre-existing `PhoenixTracer` also works as a destination for the
OpenInference shape, since it too builds real OTel spans; it needed one
1-line compatibility fix (respect an explicit `openinference.span.kind`
instead of always overwriting it) documented in the design doc.

---

## 4. Where Things Live

| Path | Role |
|---|---|
| `vidbyte/trace/providers/otel_genai.py` | OTel GenAI shape translator |
| `vidbyte/trace/providers/openinference.py` | OpenInference shape translator |
| `vidbyte/trace/providers/base.py` | `ProviderTraceTranslator` protocol, `ProviderSpanPayload` (pre-existing, unchanged) |
| `vidbyte/providers/tracing/otel.py` | `OTelTracer` — destination-agnostic OTLP transport |
| `vidbyte/providers/tracing/phoenix.py` | Existing Phoenix adapter; carries the `openinference.span.kind` compatibility fix |
| `vidbyte/trace/base.py` | `Trace.otel*`/`Trace.openinference*`/`Trace.phoenix_default` facade helpers; `_TraceFactory.resolve_translator` string registry |
| `tests/test_otel_tracer_transport.py` | Transport-layer tests (construction, attribute coercion, lifecycle) shared by both shapes |
| `tests/test_otel_genai_trace_shape.py` | OTel GenAI golden-fixture, redaction, profile-composition, and cross-provider tests |
| `tests/test_openinference_trace_shape.py` | OpenInference golden-fixture and Phoenix-interop tests |
| `scripts/test-trace-shape-prebuilts.py` | Standalone verification script for all of the above |
| `docs/design/otel-genai-and-openinference-trace-shapes.md` | Full design doc: requirements, failure modes, alternatives considered |

---

## 5. Future Directions

These are ideas under active consideration, **not committed work** — recorded
here so the next contributor (human or agent) touching this area has the
context instead of re-deriving it. Update this section as decisions get made.

**Deeper field coverage (extending this feature as-is).**
`RETRIEVER`, `EMBEDDING`, and `PARSER` span kinds don't have verified
`gen_ai.*`/OpenInference mappings yet — that requires re-checking the live
spec documents for those span types specifically (both specs are pre-1.0 and
add fields over time) before writing a mapping, per the "never guess a field
name" rule in Section 2. A third shape is also plausible: Datadog's own docs
say it accepts OTel GenAI and OpenInference directly, so no dedicated
Datadog translator is currently needed — but if a future buyer speaks a third
distinct wire format, the same translator + `OTelTracer` pattern applies.

**Wiring existing SDK data into span attributes — done, see `trace-close-attributes`.**
This section previously described this as future work, assuming it would be
a pure *capture* change requiring no translator change. That assumption was
wrong in one important way: `end_span`/`end_trace` had no attribute channel
at all before that feature, since usage/response data is only known *after*
a span opens, at close time, not before. Closing that gap needed a small,
symmetric addition to the translator contract itself (`translate_end`,
mirroring `translate_start`), not just a capture-layer change. See
`skills/trace-close-attributes/SKILL.md` for the full design — both
translators now carry real response text and token usage on `llm.call`
spans, plus a whole-run rollup on the `agent.run` trace.

**A richer, SOTA-signal-quality tracing initiative (a larger, separate,
not-yet-scoped idea).** A broader conversation (not yet a design doc)
considered two intertwined but distinct problems worth keeping separate when
this resumes:

- *Shape* (this feature) — one canonical internal recording, many output
  encoders. Already has the right abstraction (`TraceController` +
  `ProviderTraceTranslator`); extending it is mostly translator work.
- *Capture quality* — what gets turned into a span attribute in the first
  place, independent of any external shape. `TraceProfile.diagnostic()` is
  the existing "capture everything" mode, but several of the SDK's own
  richer signals (tool-selection space — which tools were *available*, not
  just which was called; reflexion self-critique; outcome grounding from a
  harness's own state machine, not just "no exception was thrown") aren't
  fully wired into semantic spans yet. This is capture work in
  `vidbyte/trace/components/`, prerequisite to any shape being able to
  export it.

An open question from that conversation, still unresolved: whether "how much
do we capture" (`TraceProfile`) and "how much of that is safe to hand an
external OTLP endpoint" should become two independently controllable knobs,
rather than the one `TraceProfile.redact`/`max_chars` pair today. Richer
capture and safe external export are in tension — worth deciding
deliberately before diagnostic-level capture becomes routinely exported.

---

## 6. Process: Add a New Trace Shape

### Step 1 — Verify the spec, don't assume it

Fetch the company's own published field-name documentation live (specs
drift). Note the exact URLs and field tables you verified — future
maintainers need to know what was actually checked versus inherited.
Only map span kinds you've verified this way.

### Step 2 — Write the translator

**File:** `vidbyte/trace/providers/<company>.py`

1. Implement `ProviderTraceTranslator`: a `provider: str` class attribute and
   `translate_start(spec: SpanSpec) -> ProviderSpanPayload`.
2. Dispatch on `spec.kind`/`spec.name` to per-span-kind private methods
   (`_translate_llm`, `_translate_tool`, ...), one per verified span kind.
3. Every branch must fall back to placeholders instead of raising when
   expected attributes are missing (`model` → `"unknown"`, etc.) — a
   translator must never be the reason a trace call fails.
4. Add a `_translate_generic` fallback for every unverified span kind:
   preserve the semantic span name, namespace every attribute under a
   `<company>.` or `vidbyte.` prefix. Never invent a field name you haven't
   verified.
5. Never mutate `spec.attributes` — always build a new dict.
6. This file must not import or call any external provider SDK — that
   belongs in `vidbyte/providers/tracing/`, not here (existing repo rule,
   see `skills/vidbyte-sdk/SKILL.md`).

### Step 3 — Reuse `OTelTracer` unless the shape needs a non-OTLP transport

Most shapes will ride on the existing `OTelTracer` — if the destination
accepts OTLP, you need zero new transport code, only a new translator. Only
add a new file under `vidbyte/providers/tracing/` if the destination
genuinely requires a different wire protocol.

### Step 4 — Wire the facade

**File:** `vidbyte/trace/base.py`

1. Add the string to `_TraceFactory.resolve_translator`.
2. Add `Trace.<company>(...)` — a profiled `TraceController` wrapping
   `Trace.otel(...)` (or the relevant tracer) with the new translator and
   `TraceProfile.default()`, mirroring `Trace.otel_genai`/`Trace.openinference`.
3. Add `Trace.<company>_session(...)` for parity with the existing session
   helpers.

### Step 5 — Golden-fixture tests

**Files:** `tests/test_<company>_trace_shape.py`

1. Hardcode the verified required/recommended field-name sets as constants,
   sourced from the URLs you checked in Step 1 — cite them in a comment.
2. Assert exact field names for every verified span kind (`assertEqual`,
   never a loose "contains some gen_ai key" check — silent field-name drift
   is exactly the failure mode this feature exists to prevent).
3. Assert the generic-fallback branch namespaces attributes and never
   invents a field for an unverified span kind.
4. Add a redaction integration test: a secret-shaped attribute key must
   never survive from `TraceController` through the translator.
5. Prove the shape survives at least one non-OTel existing inner tracer
   (e.g. `LangSmithTracer`, with its client mocked) without raising, not
   only the new transport — "works for all providers" is a real
   requirement, not just a slogan.

### Step 6 — Update this skill and the matrix

Update Section 3's table above, and add/extend the entry in
`skills/sdk/update-skill-files.md`.

---

## 7. Invariants (Do Not Break)

1. **Shape and destination stay decoupled.** A translator only ever returns
   `ProviderSpanPayload(name, attributes)`; it never touches transport.
2. **Never invent an unverified field name.** Unverified span kinds get the
   namespaced generic fallback, not a guess.
3. **Translators don't call external SDKs.** That's the transport
   (`vidbyte/providers/tracing/`) layer's job.
4. **Fail loud at construction, fail open at every call.** A destination
   tracer raises `TracerConfigurationError` if misconfigured, but every
   `start_trace`/`end_trace`/`start_span`/`end_span` degrades safely —
   tracing must never break agent execution.
5. **Attributes reaching a translator are already redacted.**
   `TraceController._sanitize_spec` strips credential-like keys and
   truncates long values *before* any translator runs; a translator must
   not need to re-implement this, and must not read from any other,
   unsanitized source.
6. **Structured values are JSON, never a Python `repr`.** Tool arguments,
   message lists, and similar must serialize as valid JSON so a downstream
   parser can actually read them.

---

## 8. Related Files

| Path | Role |
|---|---|
| `docs/design/otel-genai-and-openinference-trace-shapes.md` | Full design doc for this feature |
| `docs/design/semantic-trace-profiles.md` | The underlying `TraceController`/`TraceProfile`/`SpanSpec` system this builds on |
| `docs/design/trace-facade.md` | The `Trace` public facade this adds new methods to |
| `skills/vidbyte-sdk/SKILL.md` | Root SDK structure reference; "Semantic Trace Components" section |
| `skills/sdk/update-skill-files.md` | Change-type → skill matrix |
| `skills/trace-close-attributes/SKILL.md` | The close-time attribute follow-up: `translate_end`, usage wiring, the `_is_secret_key` redaction fix |
