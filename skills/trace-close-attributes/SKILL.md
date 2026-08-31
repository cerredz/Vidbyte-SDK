---
name: trace-close-attributes
description: >-
  Explains the close-time trace attribute feature (translate_end / usage
  wiring): how response text and token usage reach a trace shape's wire
  format after a span already opened. Use when adding a new close-time
  field mapping to a trace shape translator, wiring a new source of
  close-time data (usage, cache stats, evaluation scores) into a span,
  or reviewing a PR that touches end_span/end_trace.
---

<!-- Context Protocol Header
Description:
    Explains the "close-time trace attribute" feature: the translate_end
    hook, the widened end_span/end_trace contract, and the two runtime call
    sites (AgentRuntime's llm.call span, BaseAgent's agent.run trace) that
    feed real response/usage data into it.
Purpose:
    Teaches contributors why open-time attributes alone were never enough,
    how the close-time contract stays symmetric with the open-time one, and
    the checklist for wiring a new source of close-time data.
Architecture:
    SDK Skill Guide (feature explainer + contributor process).
Relations:
    Located in skills/trace-close-attributes/SKILL.md.
    Implementation: vidbyte/trace/providers/base.py (translate_end),
    vidbyte/trace/controller.py (_translate_end dispatch),
    vidbyte/agents/runtime.py (_llm_trace_outputs),
    vidbyte/agents/base.py (_usage_trace_attributes),
    vidbyte/agents/pricing/tracker.py (UsageTracker.preview_call).
    Design: docs/design/trace-output-and-usage-attributes.md.
Similar Files:
    - skills/trace-shape-prebuilts/SKILL.md (the shape/destination system this extends)
    - skills/usage/ (UsageTracker/UsageRollup, the data source this feature reaches into)
    - docs/design/semantic-trace-profiles.md
-->

# Trace Close-Time Attributes Skill Guide

Use this skill when you need to **understand, extend, or review** how data that
only exists *after* a span opens — a model's response text, its token usage,
a finish reason, an evaluation score — reaches a trace shape's wire format.
Shipped as a follow-up to `trace-shape-prebuilts` (PR #390): `translate_end`
plus the widened `end_span`/`end_trace` contract, wired to `AgentRuntime`'s
`llm.call` span and `BaseAgent`'s `agent.run` trace.

Related:

- Design doc: `docs/design/trace-output-and-usage-attributes.md`
- The shape system this extends: `skills/trace-shape-prebuilts/SKILL.md`
- The usage/cost data source this reaches into: `vidbyte/agents/pricing/`

---

## 1. What This Feature Is

`trace-shape-prebuilts` gave `ProviderTraceTranslator` one method,
`translate_start(spec) -> ProviderSpanPayload`, which shapes a span's
attributes at the moment it **opens**. That was never the whole picture: a
model's response text and its token usage are only known after
`handle.invoke(...)` returns — at **close** time — and before this feature,
`end_span`/`end_trace` only ever accepted two fields, `output: str | None`
and `error: BaseException | None`. There was nowhere for anything else to go.

**Close-time attributes** fix that gap the same way `trace-shape-prebuilts`
fixed the open-time one: a second, optional translator method,

```python
def translate_end(self, spec: SpanSpec, attributes: Mapping[str, Any]) -> dict[str, Any]:
    ...
```

mirroring `translate_start`'s exact shape (`SpanSpec` in, plain `dict[str, Any]`
out — no new type), plus `**attributes: Any` added to every tracer's
`end_span`/`end_trace`, mirroring the `**attributes: Any` `start_span`/
`start_trace` already had.

This is still a **translation** feature, not a new **capture** mechanism. It
does not invent new data — it gives already-computed data (a response string,
a `UsageRecord`) somewhere to go that reaches the wire in the shape's real
field names, instead of a generic `output.value` string no spec defines.

---

## 2. Intent — Why This Exists

`trace-shape-prebuilts`'s own design doc flagged this as a known future
direction, and its own `OTelGenAIProviderTranslator`/`OpenInferenceProviderTranslator`
code already *checked* for `input_tokens`/`output_tokens`/`finish_reason` in
`spec.attributes` at open time — but nothing ever populated those keys in a
real run, because `_llm_trace_inputs()` (the only function building those
attributes) only ever has pre-call data. Those checks were dead code in
practice until this feature gave them a real data path.

Two design decisions carried forward directly from `trace-shape-prebuilts`:

1. **Symmetric with the open-time contract, not a new one.** `translate_end`
   takes the same `SpanSpec` the span opened with (carried on
   `SemanticSpanContext.spec`) plus a plain attributes mapping, and returns a
   plain dict — exactly `translate_start`'s shape. No new abstraction.
2. **Optional by construction, not by convention.** `translate_end` is
   deliberately **not** part of `ProviderTraceTranslator`'s declared Protocol
   interface. Putting it there would make mypy require every structural
   implementer (`GenericProviderTranslator`, `LangSmithProviderTranslator`) to
   define it, defeating the entire point of it being optional. It is
   documented on the Protocol's docstring and detected with
   `getattr(translator, "translate_end", None)` — see Section 7, Invariant 2.

---

## 3. How It Works

```
AgentRuntime._invoke_with_middleware          BaseAgent.generate_reply
  raw_result = await handle.invoke(...)         result = await self._run_direct(...)
  output_text = handle.extract_text(...)
  usage_preview = usage_tracker.preview_call(raw_result)   <- non-mutating, never double-bills
  end_span(llm_span, output=output_text,        end_trace(trace_ctx, output=...,
           **_llm_trace_outputs(...))                    **self._usage_trace_attributes())
        |                                              |
        v                                              v
TraceController.end_span / end_trace   <-- sanitizes attrs the same way _sanitize_spec already does
        |
        v
translator.translate_end(spec, attributes)   <-- the "shape": OTelGenAIProviderTranslator / OpenInferenceProviderTranslator
        |                                        (absent on GenericProviderTranslator / LangSmithProviderTranslator: skipped, not an error)
        v
merged into inner.end_span(context, output=.., error=.., **shaped)   <-- the "destination": OTelTracer, PhoenixTracer, ...
        |
        v
   real gen_ai.output.messages / gen_ai.usage.* / llm.output_messages.*.content on the wire
```

### The two runtime call sites

| Call site | File | What it feeds |
|---|---|---|
| `llm.call` span close | `vidbyte/agents/runtime.py`, `_invoke_with_middleware` | Per-call response text + token usage, via `_llm_trace_outputs` |
| `agent.run` trace close | `vidbyte/agents/base.py`, `generate_reply` | Whole-run `UsageRollup`, via `_usage_trace_attributes` |

### Why usage needed a non-mutating preview, not just moving `record_call` earlier

`AgentRuntime._invoke_with_middleware`'s own docstring states its keyword
signature is frozen — `reflexion.py` and `multi_provider_agentic_grader.py`
call it directly as an external contract, and its return type carries no slot
for a `UsageRecord`. Rather than changing that contract, `UsageTracker` gained
`preview_call(response)` — a twin of `record_call` sharing a private
`_price_call` helper, but which **never appends to the ledger**. The real,
ledger-mutating `record_call` still fires exactly once, one call-frame up,
completely unchanged. Calling `preview_call` any number of times is always
side-effect-free; only `record_call` bills.

### What's implemented today

| Field | Translator | Verified against |
|---|---|---|
| `gen_ai.output.messages`, `.usage.input_tokens`/`.output_tokens`, `.response.finish_reasons` | `OTelGenAIProviderTranslator.translate_end` (LLM spans) | Same `gen-ai-spans.md` fields already verified for open-time use in PR #390 |
| `vidbyte.usage.*` (whole-run rollup) | `OTelGenAIProviderTranslator.translate_end` (`agent.run` by name) | Deliberately **not** `gen_ai.usage.*` — that field is per-call scoped by spec, not whole-run |
| `llm.output_messages.<i>.message.role`/`.content`, `.token_count.completion`/`.total` | `OpenInferenceProviderTranslator.translate_end` (LLM spans) | Same field names already cited in PR #390's design doc alongside the shipped `.token_count.prompt` |

Every other span kind, and every attribute neither branch explicitly maps
(e.g. `cached_input_tokens` — see Section 5), falls back to the same
namespaced `vidbyte.*` passthrough `trace-shape-prebuilts` already
established for open-time attributes — never an invented field name.

---

## 4. Where Things Live

| Path | Role |
|---|---|
| `vidbyte/trace/providers/base.py` | `translate_end`'s optional-by-construction documentation on `ProviderTraceTranslator` |
| `vidbyte/trace/providers/otel_genai.py` | `translate_end` for LLM spans and the `agent.run` whole-run rollup |
| `vidbyte/trace/providers/openinference.py` | `translate_end` for LLM spans |
| `vidbyte/trace/controller.py` | `TraceController._translate_end` — sanitizes, detects `translate_end` via `getattr`, dispatches |
| `vidbyte/agents/pricing/tracker.py` | `UsageTracker.preview_call` / shared `_price_call` — the no-double-billing mechanism |
| `vidbyte/agents/runtime.py` | `_llm_trace_outputs` — builds the `llm.call` span's close-time payload |
| `vidbyte/agents/base.py` | `_usage_trace_attributes` — builds the `agent.run` trace's close-time payload |
| `vidbyte/trace/profiles.py` | `_is_secret_key` — fixed to a word-boundary match on `TOKEN` so `input_tokens`/`output_tokens` survive redaction (see Section 6) |
| `tests/test_trace_close_attributes.py` | Golden-fixture tests for both translators' `translate_end`, plus `TraceController`/tracer wiring |
| `tests/test_usage_preview_and_trace_wiring.py` | `preview_call` no-double-billing unit tests + full-agent-run integration tests |
| `scripts/test-trace-output-and-usage-attributes.py` | Standalone verification script for both test files |
| `docs/design/trace-output-and-usage-attributes.md` | Full design doc: requirements, failure modes, alternatives considered |

---

## 5. Known Gaps (Not Committed Work Beyond This)

**`finish_reason` is mapped but never populated.** Both translators correctly
map a `finish_reason` key when present (tested directly), but no runner
response type in `vidbyte/lib/runners` currently parses a finish/stop reason
at all — checked directly during this feature's implementation, zero matches.
`gen_ai.response.finish_reasons` will not appear on a real span until a
follow-up adds finish-reason parsing to the runner response layer.

**Cached-token field name is unverified.** `cached_input_tokens` is passed
through the generic `vidbyte.` namespace rather than a `gen_ai.*` field,
because whether OTel GenAI defines a real spec field for cache-read tokens
was not re-verified live against the spec during this feature. Verify before
promoting it out of the namespace — do not guess the field name.

**A pre-existing custom `TracerBase` subclass can break.** Any tracer written
before this feature with a narrow `end_span`/`end_trace` signature (no
`**attributes`) raises `TypeError` the first time a caller sends real
close-time attributes through it. Every tracer this repo ships was widened;
an external one wasn't, because it isn't visible to this repo. If you are
debugging a `TypeError: end_span() got an unexpected keyword argument`, this
is almost certainly why — widen the custom tracer's signature the same way
every SDK-shipped tracer in this feature was.

**MLflow may already be covered for free.** Databricks' own "third-party OTel
span attributes" documentation indicates MLflow already remaps raw `gen_ai.*`
attributes on ingestion (including `gen_ai.output.messages` ->
`mlflow.spanOutputs`), so `Trace.otel_genai(...)` may already render
correctly in MLflow's UI without any MLflow-specific translator. Not
empirically confirmed against a real MLflow tracking server yet — do that
before starting a dedicated `Trace.mlflow(...)` translator.

---

## 6. A Bug This Feature's Own Tests Uncovered

`TraceProfile._is_secret_key` (`vidbyte/trace/profiles.py`) matched `"TOKEN"`
as a raw substring — which also matches `"TOKENS"`, silently redacting
`input_tokens`/`output_tokens`/`total_tokens`/`cached_input_tokens` before
they could ever reach a translator. This was inert before this feature
because nothing populated those attribute keys in practice; it became a real,
fully-reproducing bug the moment this feature's own integration tests tried
to exercise it. Fixed to a word-boundary match (`re.search(r"(?:^|_)TOKEN(?:$|_)", upper)`)
so `api_key`/`auth_token`/`secret`/`password`/`credential`/`auth` are still
redacted, but a plural "tokens" count field is not. If you add a new
attribute key anywhere in the trace system whose name happens to contain a
sensitive-sounding word as a substring rather than a whole word, check this
function before assuming redaction dropped it by design.

---

## 7. Invariants (Do Not Break)

1. **Symmetric with `translate_start`.** `translate_end(spec, attributes) -> dict[str, Any]` —
   same `SpanSpec` input shape, same plain-dict output shape, no new type.
2. **Optional by construction.** Never add `translate_end` back to
   `ProviderTraceTranslator`'s declared Protocol interface. Detect it with
   `getattr(translator, "translate_end", None)`, exactly as
   `TraceController._translate_end` does — a static attribute access or
   `isinstance` check would force every translator to implement it.
3. **Never invent an unverified field name.** Same rule as `trace-shape-prebuilts`:
   an unmapped or unverified attribute gets the namespaced `vidbyte.` fallback,
   never a guess.
4. **`preview_call` never mutates the ledger.** If you add a new close-time
   data source that needs pricing/usage data, read it through `preview_call`
   (or an equivalent non-mutating accessor), never a second `record_call` —
   calling `record_call` twice for one response double-bills the run.
5. **Attributes reaching `translate_end` are already redacted.**
   `TraceController._translate_end` sanitizes through the same
   `safe_trace_value` `_sanitize_spec` uses for open-time attributes, before
   any translator sees them — a translator must not need its own redaction.
6. **Every tracer's `end_span`/`end_trace` must accept `**attributes: Any`.**
   Adding a new tracer without it will raise `TypeError` the first time real
   close-time data flows through it — see Section 5's compatibility note.
7. **Fail open, never break a run.** A `translate_end` implementation must
   never raise on a missing key (omit the field, exactly like `translate_start`
   already does) — a trace feature must never be the reason an agent run fails.

---

## 8. Process: Wire a New Close-Time Data Source

### Step 1 — Confirm the data doesn't already exist by open time

If the data is knowable before the model call / before the run starts, it
belongs in `translate_start`/`_llm_trace_inputs`-style open-time attributes
(`skills/trace-shape-prebuilts/SKILL.md`), not here. Close-time attributes
exist specifically for data only known after something completes.

### Step 2 — Find or build a non-mutating accessor for the data

If the data comes from a stateful tracker (usage, cost, cache hits), check
whether reading it would have a side effect (like `record_call` does). If so,
add a non-mutating twin (like `preview_call`) rather than reordering the
stateful call — respect any frozen external-caller signature the way
`_invoke_with_middleware`'s docstring required here.

### Step 3 — Feed it into the right span close

Add the data to the relevant `end_span`/`end_trace` call as `**kwargs`, built
by a small helper mirroring `_llm_trace_outputs`/`_usage_trace_attributes` —
omit fields entirely when the data is unavailable, never emit a zero/None
placeholder.

### Step 4 — Add or extend `translate_end` per shape

For each verified span kind, map the new key to its real spec field name
(re-verify live against the spec, don't assume) inside `translate_end`; add
the key to that branch's consumed-keys set so it doesn't also get
double-emitted through the `vidbyte.` fallback.

### Step 5 — Golden-fixture and no-double-mutation tests

Mirror `tests/test_trace_close_attributes.py`'s pattern: exact field-name
assertions, an omit-when-absent test, and — if the data source has any
mutating twin — an explicit test proving the close-time read never mutates it.

---

## 9. Related Files

| Path | Role |
|---|---|
| `docs/design/trace-output-and-usage-attributes.md` | Full design doc for this feature |
| `skills/trace-shape-prebuilts/SKILL.md` | The shape/destination system this extends; read first |
| `docs/design/otel-genai-and-openinference-trace-shapes.md` | The open-time shape design this feature completes |
| `docs/design/semantic-trace-profiles.md` | The underlying `TraceController`/`TraceProfile`/`SpanSpec` system both features build on |
| `skills/vidbyte-sdk/SKILL.md` | Root SDK structure reference |
