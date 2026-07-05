# Design Doc: Tracing Skills (`skills/tracing/`)

## Overview

This feature adds a new top-level `skills/tracing/` folder to the Vidbyte SDK
repository. The folder contains a set of decoupled, context-enriching skill
files that collectively document everything an agent (or human) needs to
understand about tracing inside the Vidbyte SDK.

The skills are derived from the tracing surface introduced/consolidated by PR
#208 (semantic trace profiles, trace components, providers, controller, session,
continual tracing) plus the pre-existing provider adapters and shared tracer
contracts. Each skill is a standalone Markdown file with a Context Protocol
Header, code snippets drawn from the actual implementation, and a precise file
map. Each skill ships as its own pull request so the work is reviewable and
decoupled.

The source of truth for every PR is this design doc. If a change is not
described here, it is not implemented.

## Goals

- Give future agents a single, self-contained `skills/tracing/` area that fully
  explains Vidbyte SDK tracing without requiring them to read source first.
- Decouple tracing knowledge into focused, non-overlapping skill files so an
  agent can load only the context it needs (enablement vs types vs providers vs
  internals vs maintenance).
- Include accurate, copy-pasteable code snippets taken from the real
  implementation on `feat/trace-component-expansion` (PR #208 + #209 + #213).
- Map every tracing file to its responsibility so an agent knows exactly where
  to make a change and what else to update.
- Ship each skill as an independent PR against `main` so reviewers can approve
  one topic at a time.

## Non-Goals

- Do not change any source code under `vidbyte/`. This is a documentation-only
  feature (Markdown skill files + this design doc).
- Do not modify existing skill index files (`skills/vidbyte-sdk/SKILL.md`,
  `skills/sdk/SKILL.md`, `vidbyte/trace/README.md`, `llms.txt`). Registering the
  new folder in those indexes is an explicit open question for the user, not an
  implementation task here.
- Do not duplicate the existing `skills/vidbyte-sdk/continual-tracing.md`. The
  continual-tracing topic is summarized in the tracing skills and points to that
  existing skill for full detail.
- Do not add tests or verification scripts (this is the no-tests design-doc
  workflow).
- Do not invent APIs, libraries, or patterns. Every snippet and file path must
  exist on `origin/main`.

## Background

Tracing in the Vidbyte SDK has two distinct systems, both living under
`vidbyte/trace/`:

1. **Observability tracing** — optional, explicit, safe-by-default span emission
   that makes agent runtime behavior inspectable. Selected via the `trace=`
   (alias `tracer=`) constructor argument on `BaseAgent`/`Agent`. The root trace
   `agent.run` is opened in `BaseAgent.arun()` and child spans
   (`runtime.iteration`, `llm.call`, `tool.call`, `parser.tool_calls`,
   `agent.stop`) are emitted by `vidbyte/agents/runtime.py`.

2. **Continual tracing** — a structured, continually-updated artifact describing
   a running agent's goal, work, mistakes, and status. Selected via the separate
   `trace_option=` argument and realized as runtime middleware
   (`ContinualTraceMiddleware`), not observability spans. Documented in the
   existing `skills/vidbyte-sdk/continual-tracing.md`.

PR #208 layered **semantic trace profiles** above the raw provider adapters: the
SDK defines Vidbyte span concepts once (`SpanSpec`, `SpanKind`, `TraceDetail`),
filters them through a `TraceProfile`, and translates them to provider fields
(such as LangSmith `run_type`) via `ProviderTraceTranslator` implementations.
The semantic layer (`TraceController`) wraps any low-level `TracerBase`
(`DebugTracer`, `LangSmithTracer`, etc.) and never calls external provider SDKs
itself — the legacy adapters under `vidbyte/providers/tracing/` own the
external calls.

### Tracing file inventory (baseline: `feat/trace-component-expansion`, which includes PR #208 + #209 + #213)

> The skill PRs were rebased onto `feat/trace-component-expansion` so the
> documented code exists in each PR's base. When that branch merges to `main`,
> retarget the skill PRs back to `main`.

```text
vidbyte/lib/tracing/
  base.py                 SpanContext, TracerBase (ABC), NullTracer
  __init__.py             re-exports NullTracer, SpanContext, TracerBase

vidbyte/trace/
  __init__.py             public facade exports (Trace, TraceProfile, SpanKind, ...)
  base.py                 Trace facade: off/debug/custom/profile/session/
                          continual/langfuse/langsmith/langsmith_default/
                          langsmith_verbose/langsmith_session/phoenix
                          (Trace.session no longer takes default_name/default_attributes)
  debug.py                DebugTracer (in-memory event recorder)
  schema.py               SpanKind, TraceDetail, ParentPolicy, SpanSpec,
                          SemanticSpanContext
  profiles.py             TraceProfile presets (4 detail + 5 role-oriented) +
                          TraceComponentSettings + safe_trace_value / _is_secret_key
                          (_COMPONENTS now has 19 entries)
  controller.py           TraceController (profile filter + translator +
                          context-local span stack)
  session.py              SessionTraceController only (SessionTracer removed)
  registry.py             TraceComponentRegistry (test/doc span registry)
  components/
    __init__.py           re-exports 16 component factories
    agents.py             AgentTrace (13 spans), AggregateTrace
    runtimes.py           LinearRuntimeTrace, ActorRuntimeTrace, SearchRuntimeTrace
    context.py            ContextTrace (12 spans)
    algorithms.py         AlgorithmTrace
    middleware.py         MiddlewareTrace (decision + 9 per-hook + 4 actions + builtin)
    tools.py              ToolTrace (10 spans)
    parsers.py            ParserTrace (4 spans)
    pipelines.py          PipelineTrace (NEW — pipeline topologies + stage invoke)
    handoff.py            HandoffTrace (NEW — generate/validate/record/sync)
    sources.py            SourceTrace (NEW — fetch/load + cache hit/miss)
    sessions.py           SessionTrace (NEW — start/end + case)
    evals.py              EvalTrace (NEW — run/grade/behavior)
    mcp.py                McpTrace (NEW — attach/search/transport)
  providers/
    __init__.py           re-exports translators
    base.py               ProviderSpanPayload, ProviderTraceTranslator (Protocol)
    generic.py            GenericProviderTranslator (pass-through)
    langsmith.py          LangSmithProviderTranslator (adds run_type)
  continual/
    __init__.py           re-exports ContinualTracer, ActionTrace, agent,
                          middleware (canonical locations moved to agents/,
                          middleware/, tools/)
    base.py               ContinualTracer (DebugTracer subclass)
    prebuilt.py           ActionTrace + ActionTraceModel (Pydantic)
    agent.py              re-export of vidbyte.agents.continual_trace
    middleware.py          re-export of vidbyte.middleware.continual_trace
    tools.py              re-export of vidbyte.tools.continual_trace

vidbyte/providers/tracing/             (external-SDK adapters)
  __init__.py             re-exports LangfuseTracer, LangSmithTracer, PhoenixTracer
  langsmith.py            LangSmithTracer (langsmith.Client, run_type mapping)
  langfuse.py             LangfuseTracer (langfuse.Langfuse)
  phoenix.py              PhoenixTracer (OpenTelemetry / Arize Phoenix)

vidbyte/agents/
  base.py                 BaseAgent: trace=/tracer= wiring, _resolve_tracer,
                          agent.run root trace lifecycle, agent.stop span,
                          _is_semantic_tracer detection
  runtime.py              AgentRuntime: runtime.iteration / llm.call /
                          tool.call / parser.tool_calls / parser.structured_output
                          span emission + _start_semantic_span helper +
                          _safe_trace_value / _is_secret_trace_key payload
                          redaction + _llm_trace_inputs enrichment

vidbyte/lib/dataclasses/trace.py       TraceField, TraceFieldType, TraceMode,
                                       TraceSchema, TraceOption (continual)
vidbyte/lib/errors.py                  ConfigurationError, TracerConfigurationError
```

### Environment variables and install requirements (for the providers skill)

| Provider | Install | Env vars (constructor kwargs override) |
|----------|---------|----------------------------------------|
| LangSmith | `pip install langsmith` | `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` (default `default`), `LANGSMITH_ENDPOINT` |
| Langfuse | `pip install langfuse` | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (default `https://cloud.langfuse.com`) |
| Phoenix | `pip install arize-phoenix opentelemetry-sdk opentelemetry-exporter-otlp-proto-http` | `PHOENIX_COLLECTOR_ENDPOINT` (default `http://localhost:6006/v1/traces`) |

## Requirements

### R1 — New `skills/tracing/` folder with one index skill
Create `skills/tracing/SKILL.md` as the folder index and file map. It must
explain the two tracing systems, the three-folder layout
(`vidbyte/trace/`, `vidbyte/providers/tracing/`, `vidbyte/lib/tracing/`), and
route the reader to each sibling skill by topic. It must include a "when to read
which skill" table.

### R2 — Enabling-tracing skill
Create `skills/tracing/enabling-tracing.md` covering the `trace=` agent
constructor argument, the full `Trace` facade helper catalog, the
`trace=` vs `tracer=` vs `trace_option=` distinction, the `agent.run` root trace
lifecycle in `BaseAgent.arun()`, and the spans emitted by
`vidbyte/agents/runtime.py` (`runtime.iteration`, `llm.call`, `tool.call`,
`parser.tool_calls`, `agent.stop`). Must include runnable code snippets.

### R3 — Trace-types skill
Create `skills/tracing/trace-types.md` enumerating every type of tracing: off
(`NullTracer`), debug (`DebugTracer` in-memory), provider adapters
(LangSmith/Langfuse/Phoenix external SDK), semantic profiles (`TraceController`
wrapping a low-level tracer), session tracing (grouping multiple agent runs),
and continual tracing (structured artifact via middleware). Must enumerate the
`SpanKind` values and the `TraceDetail` levels and explain the
observability-vs-continual boundary.

### R4 — Trace-profiles skill
Create `skills/tracing/trace-profiles.md` documenting `TraceProfile` (the 4
presets `minimal`/`default`/`verbose`/`diagnostic`), `with_components()`, the
`allows()` filtering logic, the component setting values, the 14 component
names, `TraceComponentSettings`, and `safe_trace_value`/`_is_secret_key`
redaction. Must include code snippets.

### R5 — Trace-providers skill
Create `skills/tracing/trace-providers.md` documenting the three integrated
providers (LangSmith, Langfuse, Phoenix) with env vars and install requirements,
the distinction between semantic translators (`vidbyte/trace/providers/`, which
translate and do not call external SDKs) and legacy external adapters
(`vidbyte/providers/tracing/`, which call external SDKs), the `provider=` arg on
`Trace.profile()`/`Trace.session()`, and how to add a new provider. Must include
the LangSmith `run_type` mapping table.

### R6 — Trace-components skill
Create `skills/tracing/trace-components.md` cataloguing every span-spec factory
in `vidbyte/trace/components/` with its span names, `SpanKind`, component, and
`TraceDetail`. Must state the maintenance rule: when adding/changing an agent
runtime, context-window algorithm, middleware, tool, parser, or aggregate-agent
behavior, check whether `vidbyte/trace/components/` needs a new/updated span
spec in the same change. Must cover `TraceComponentRegistry`.

### R7 — Trace-controller-and-session skill
Create `skills/tracing/trace-controller-and-session.md` documenting
`TraceController` internals (profile filtering, provider translation, the
context-local span stack via `ContextVar`, parent resolution via `ParentPolicy`,
`_spec_from_name` name-prefix routing, span suppression, the `as_trace` flag,
and nested `agent.run` handling) and session tracing (`SessionTracer` legacy
path vs `SessionTraceController` semantic path, `begin_session`/`end_session`,
`session()` sync and `async_session()` async context managers, and how child
`agent.run` traces become child spans). Must include code snippets.

### R8 — Updating-the-tracer skill
Create `skills/tracing/updating-the-tracer.md` as a file-by-file maintenance
guide. For each tracing responsibility, state which file to edit and what else
to update (exports in `vidbyte/trace/__init__.py` and `vidbyte/__init__.py`,
`vidbyte/trace/README.md`, `llms.txt`, and the existing skill maintenance rules
in `skills/vidbyte-sdk/SKILL.md` and `skills/sdk/SKILL.md`). Must cover adding a
new facade helper, a new profile preset, a new span kind, a new component span
spec, a new provider translator, a new external provider adapter, and a new
runtime-emitted span.

### R9 — Each skill is its own PR
Ship exactly 8 PRs, one per skill file, each branched from `origin/main` and
targeting `main`. PR 1 also adds this design doc. No PR modifies source code or
existing skill files.

### R10 — Skill file conventions
Every skill file must:
- Open with an HTML-comment Context Protocol Header (Description, Purpose,
  Architecture, Relations) matching the repo's existing skill style (see
  `skills/vidbyte-sdk/middleware.md`, `skills/vidbyte-sdk/continual-tracing.md`).
- Use GitHub-flavored Markdown with code fences.
- Include at least one code snippet per skill where applicable.
- Reference real file paths that exist on the PR base branch
  (`feat/trace-component-expansion`).
- Not duplicate `skills/vidbyte-sdk/continual-tracing.md`; instead link to it for
  continual-tracing deep detail.

## High-Level Design

The new `skills/tracing/` folder mirrors the structure of other top-level skill
folders in the repo (`skills/agent-runtimes/`, `skills/paradigm/`,
`skills/sources/`, `skills/mcp-server/`): a `SKILL.md` index plus topical
sub-skills. The decomposition follows the user's stated decoupling examples
(enable tracing on agents, types of tracing, providers, which files do what /
where to update) and extends them to cover the semantic layer introduced by PR
#208.

### Skill decomposition (8 files → 8 PRs)

| # | File | Topic | PR |
|---|------|-------|----|
| 1 | `skills/tracing/SKILL.md` | Folder index + file map + "which skill to read" routing | PR 1 (also adds this design doc) |
| 2 | `skills/tracing/enabling-tracing.md` | How to enable tracing on agents (`trace=`, facade, lifecycle) | PR 2 |
| 3 | `skills/tracing/trace-types.md` | All tracing types + span kinds + detail levels | PR 3 |
| 4 | `skills/tracing/trace-profiles.md` | Semantic trace profiles + component settings + redaction | PR 4 |
| 5 | `skills/tracing/trace-providers.md` | Integrated providers + translators vs adapters + run_type | PR 5 |
| 6 | `skills/tracing/trace-components.md` | Span-spec factories catalog + maintenance rule | PR 6 |
| 7 | `skills/tracing/trace-controller-and-session.md` | TraceController internals + session grouping | PR 7 |
| 8 | `skills/tracing/updating-the-tracer.md` | File-by-file maintenance guide | PR 8 |

### Content sources (baseline: `feat/trace-component-expansion` = PR #208 + #209 + #213)

- `vidbyte/trace/README.md` — the canonical module README (profiles, helpers,
  session usage, key modules).
- `vidbyte/trace/base.py` — the `Trace` facade and `_TraceFactory`.
- `vidbyte/trace/{schema,profiles,controller,session,registry,debug}.py`.
- `vidbyte/trace/components/*.py` and `vidbyte/trace/providers/*.py`.
- `vidbyte/trace/continual/{base,prebuilt}.py`.
- `vidbyte/providers/tracing/{langsmith,langfuse,phoenix}.py`.
- `vidbyte/lib/tracing/base.py`.
- `vidbyte/agents/{base,runtime}.py` (trace wiring + span emission).
- Existing skill style references: `skills/vidbyte-sdk/middleware.md`,
  `skills/vidbyte-sdk/continual-tracing.md`, `skills/sdk/SKILL.md`,
  `skills/vidbyte-sdk/SKILL.md`.

## Detailed Design

### Skill 1 — `skills/tracing/SKILL.md` (index + file map)

Context Protocol Header describing the folder as the entry point for all
tracing knowledge. Sections:

1. **Two tracing systems** — one-paragraph summary: observability tracing
   (`trace=`) vs continual tracing (`trace_option=`), with the rule that
   continual deep detail lives in `skills/vidbyte-sdk/continual-tracing.md`.
2. **Three-folder layout** — table mapping `vidbyte/trace/`,
   `vidbyte/providers/tracing/`, `vidbyte/lib/tracing/` to their roles.
3. **Which skill to read** — routing table: goal → skill file.
4. **Tracing file map** — the full inventory from the Background section above,
   condensed, so an agent can locate any file by responsibility.
5. **Quick start** — the two canonical snippets from `vidbyte/trace/README.md`
   (`Trace.debug(events)` and `Trace.langsmith_default(project=...)`).
6. **Maintenance rule** — pointer to `updating-the-tracer.md` and the repo rule
   that tracing behavior changes require updating `vidbyte/trace/README.md` or
   `llms.txt`.

### Skill 2 — `skills/tracing/enabling-tracing.md`

Context Protocol Header. Sections:

1. **The `trace=` argument** — `BaseAgent.__init__(..., trace=..., tracer=...)`,
   the `_resolve_tracer` normalization, the "pass either, not both" rule, and the
   `NullTracer` default.
2. **The `Trace` facade catalog** — a table of every `Trace.*` helper with
   signature and one-line purpose: `off`, `debug`, `custom`, `profile`,
   `session`, `continual`, `langfuse`, `langsmith`, `langsmith_default`,
   `langsmith_verbose`, `langsmith_session`, `phoenix`.
3. **`trace=` vs `tracer=` vs `trace_option=`** — three-column table clarifying
   which is observability, which is legacy alias, which is continual artifact.
4. **The `agent.run` root trace lifecycle** — excerpt from `BaseAgent.arun()`:
   `start_trace("agent.run", ...)` → run → `_record_agent_stop` →
   `end_trace(...)`; error/finally paths always finalize the root trace.
5. **Spans emitted by the runtime** — table of `runtime.iteration`, `llm.call`,
   `tool.call`, `parser.tool_calls`, `agent.stop` with the file:line and the
   attributes each carries (provider, model, tool_name, token counts, etc.).
6. **Secret redaction at the agent layer** — `_safe_trace_value` /
   `_is_secret_trace_key` / `_trace_text` truncation (max 12000 chars) before
   payloads reach trace backends.
7. **Code snippets** — debug tracer example, LangSmith default example, semantic
   profile wrapping a debug tracer, session example.

### Skill 3 — `skills/tracing/trace-types.md`

Context Protocol Header. Sections:

1. **Observability vs continual** — the boundary and why they are separate
   subsystems.
2. **Observability tracer types** — `NullTracer` (off), `DebugTracer` (in-memory
   `events` list), external provider adapters (`LangSmithTracer`,
   `LangfuseTracer`, `PhoenixTracer`), semantic `TraceController` (wraps any of
   the above), `SessionTraceController`/`SessionTracer` (session grouping).
3. **`SpanKind` enum** — `chain`, `llm`, `tool`, `retriever`, `embedding`,
   `prompt`, `parser` with provider-neutral meaning.
4. **`TraceDetail` levels** — `minimal`, `standard`, `verbose`, `diagnostic`
   with what each threshold includes, mapped to the four `TraceProfile` presets.
5. **Continual tracing type** — `ContinualTracer` (`DebugTracer` subclass) +
   `ActionTrace` schema + `ContinualTraceAgent`/`ContinualTraceMiddleware`;
   pointer to `skills/vidbyte-sdk/continual-tracing.md`.
6. **Decision flowchart** — text/box diagram: "want spans?" → observability;
   "want a live handoff artifact?" → continual; "want multiple agents under one
   root?" → session.

### Skill 4 — `skills/tracing/trace-profiles.md`

Context Protocol Header. Sections:

1. **`TraceProfile` dataclass** — fields (`detail`, `components`, `redact`,
   `max_chars`), immutability, `__post_init__` validation.
2. **The four presets** — `TraceProfile.minimal()`, `.default()`, `.verbose()`,
   `.diagnostic()` and exactly which spans each keeps (from
   `vidbyte/trace/README.md`).
3. **`with_components(**components)`** — override example.
4. **`allows(spec)` filtering** — the setting-value resolution logic
   (`off`/`False`, `True`, `minimal`, `decisions_only`, `default`/`summary`/
   `inputs_outputs`, `verbose`, `diagnostic`) and the detail-order threshold.
5. **The 14 component names** — `agents`, `aggregate`, `runtimes`, `actor`,
   `search`, `context`, `algorithms`, `middleware`, `tools`, `parsers`,
   `retrievers`, `embeddings`, `sessions`, `core`.
6. **`TraceComponentSettings`** — the `.resolve(component)` helper.
7. **`safe_trace_value` / `_is_secret_key`** — recursive redaction of
   credential-like keys (`API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`,
   `CREDENTIAL`, `AUTH`, `LANGSMITH_`) and string truncation.

### Skill 5 — `skills/tracing/trace-providers.md`

Context Protocol Header. Sections:

1. **Two layers of provider code** — translators
   (`vidbyte/trace/providers/`, no external calls) vs adapters
   (`vidbyte/providers/tracing/`, external SDK calls). This distinction is the
   most important concept in the skill.
2. **Integrated providers table** — LangSmith, Langfuse, Phoenix with install
   commands, env vars, defaults (from the Background table).
3. **LangSmith `run_type` mapping** — `SpanKind` → `run_type` table from
   `LangSmithProviderTranslator._run_type`.
4. **The `provider=` argument** — on `Trace.profile()` and `Trace.session()`;
   accepted values `"generic"`, `"langsmith"`, a translator instance, or `None`;
   `_TraceFactory.resolve_translator` resolution.
5. **Provider adapter behavior** — how `LangSmithTracer` resolves credentials,
   `strict` mode, `last_error` diagnostics, `_redact` of `lsv2_`/`xai-` keys;
   how `LangfuseTracer` maps `llm.` spans to `.generation()`; how
   `PhoenixTracer` sets `openinference.span.kind`.
6. **Adding a new provider** — add an external adapter under
   `vidbyte/providers/tracing/`, optionally add a translator under
   `vidbyte/trace/providers/`, expose a `Trace.<name>(...)` helper in
   `vidbyte/trace/base.py`, and register the translator name in
   `_TraceFactory.resolve_translator`.

### Skill 6 — `skills/tracing/trace-components.md`

Context Protocol Header. Sections:

1. **What a span spec is** — `SpanSpec` fields (`name`, `kind`, `component`,
   `detail`, `parent_policy`, `attributes`, `metadata`) and `with_attributes`.
2. **Component factory catalog** — one table per component file listing every
   span name, `SpanKind`, component, and `TraceDetail`:
   - `agents.py`: `agent.run`, `agent.stop`, `aggregate.run`,
     `aggregate.proposer`, `aggregate.synthesis`, `aggregate.failure`.
   - `runtimes.py`: `runtime.iteration`, `runtime.stop`, `runtime.actor.run`,
     `runtime.actor.spawn`, `runtime.actor.message`, `runtime.actor.completion`,
     `runtime.search.run`, `runtime.search.node`, `runtime.search.rollback`.
   - `context.py`: `context.window.build`, `context.primitive.render`,
     `context.compaction`, `context.update`.
   - `algorithms.py`: `algorithm.<name>` plus `reflexion.trial`,
     `reflexion.reflection`, `multi_provider_agentic_grader`,
     `trajectory_checkpoints`, `problem_space_search`, `error_correction`.
   - `middleware.py`: `middleware.decision`, `middleware.hook`.
   - `tools.py`: `tool.call`, `tool.permission`.
   - `parsers.py`: `parser.tool_calls`, `parser.structured_output`.
3. **`TraceComponentRegistry`** — `register`/`get`/`all`, duplicate-name
   rejection, use by tests and docs.
4. **Maintenance rule** — when adding/changing an agent runtime, context-window
   algorithm, middleware, tool, parser, or aggregate-agent behavior, check
   whether `vidbyte/trace/components/` needs a new/updated span spec in the same
   change; update `vidbyte/trace/README.md` or `llms.txt` when public tracing
   behavior changes.

### Skill 7 — `skills/tracing/trace-controller-and-session.md`

Context Protocol Header. Sections:

1. **`TraceController` role** — filters semantic spans via the profile,
   translates them via the provider translator, delegates the actual span
   lifecycle to the wrapped `inner` tracer.
2. **The context-local span stack** — `_SPAN_STACK` `ContextVar`, push/pop on
   start/end, async-local isolation.
3. **Parent resolution** — `ParentPolicy` enum (`explicit`, `current`, `agent`,
   `runtime_iteration`, `aggregate`, `session`, `root`) and
   `_provider_parent` resolution from the stack.
4. **Name-prefix routing** — `_spec_from_name` maps `llm.`/`tool.`/`parser.`/
   `context.`/`algorithm.`/`runtime.`/`middleware.`/`aggregate.`/`session.`/
   `agent.` prefixes to component + kind + detail.
5. **Suppression and `as_trace`** — spans rejected by the profile return a
   suppressed `SemanticSpanContext`; `start_trace` vs `start_span` and the
   `as_trace` flag controlling `inner.start_trace` vs `inner.start_span`.
6. **Nested `agent.run`** — when an `agent.run` arrives while a provider parent
   is already active, it opens as a child span instead of a new root.
7. **Session tracing** — `SessionTracer` (legacy `default_name`/
   `default_attributes`, `begin_session`/`end_session`, `TraceSession` sync+async
   context manager) vs `SessionTraceController` (semantic, `session()` sync +
   `async_session()` async, converts child `agent.run` into child spans while
   the session root is open). `Trace.session()` and `Trace.langsmith_session()`
   dispatch rules (cannot mix `default_name`/`default_attributes` with semantic
   options).
8. **Code snippets** — `Trace.session(...)` + `with trace.session(...)` example,
   `Trace.langsmith_session(...)` example.

### Skill 8 — `skills/tracing/updating-the-tracer.md`

Context Protocol Header. Sections:

1. **Responsibility matrix** — table of "if you want to change X, edit file Y and
   also update Z". Rows:
   - New facade helper → `vidbyte/trace/base.py` + export in
     `vidbyte/trace/__init__.py` + `vidbyte/__init__.py` + README/llms.txt.
   - New profile preset → `vidbyte/trace/profiles.py` + export + README.
   - New span kind → `vidbyte/trace/schema.py` (`SpanKind`) + any translator
     that maps kinds (`vidbyte/trace/providers/langsmith.py`) + README.
   - New detail level → `vidbyte/trace/schema.py` (`TraceDetail`) +
     `_DETAIL_ORDER` in `profiles.py`.
   - New component span spec → `vidbyte/trace/components/<area>.py` + export in
     `vidbyte/trace/components/__init__.py` + check the maintenance rule.
   - New parent policy → `vidbyte/trace/schema.py` (`ParentPolicy`) +
     `controller.py` `_provider_parent`.
   - New provider translator → `vidbyte/trace/providers/<name>.py` + export +
     register the name in `_TraceFactory.resolve_translator`.
   - New external provider adapter → `vidbyte/providers/tracing/<name>.py` +
     export + a `Trace.<name>(...)` helper in `vidbyte/trace/base.py`.
   - New runtime-emitted span → `vidbyte/agents/runtime.py` (or `base.py` for
     `agent.stop`) + a matching component spec in `vidbyte/trace/components/`.
   - New continual schema → `vidbyte/trace/continual/prebuilt.py` + exports
     (follow `skills/vidbyte-sdk/continual-tracing.md`).
2. **Export checklist** — the three export layers: module `__init__.py`, package
   `vidbyte/trace/__init__.py`, top-level `vidbyte/__init__.py`.
3. **Docs checklist** — `vidbyte/trace/README.md`, `llms.txt`, and the skill
   maintenance rules in `skills/vidbyte-sdk/SKILL.md` and `skills/sdk/SKILL.md`
   (the "Semantic Trace Components" section that already exists).
4. **Do-not-cross lines** — translators must not call external SDKs; the runtime
   must not import trace feature code; continual trace must never enter the main
   context window (see `skills/vidbyte-sdk/continual-tracing.md` invariants).

## Data Model Changes

N/A - This feature adds Markdown documentation files only. No Python data
models, schemas, migrations, or runtime contracts are changed.

## API Changes

N/A - This feature adds Markdown documentation files only. No public or
internal Python APIs are added, removed, or modified. All documented APIs are
already present on `feat/trace-component-expansion` (PR #208 + #209 + #213).

## File Change Manifest

All files are CREATED. None are modified or deleted. Each row is its own PR
against `main`; PR 1 also carries this design doc.

| PR | Action | Path | Lines (est.) |
|----|--------|------|--------------|
| 1 | CREATE | `docs/design/tracing-skills.md` | (this file) |
| 1 | CREATE | `skills/tracing/SKILL.md` | ~120 |
| 2 | CREATE | `skills/tracing/enabling-tracing.md` | ~180 |
| 3 | CREATE | `skills/tracing/trace-types.md` | ~150 |
| 4 | CREATE | `skills/tracing/trace-profiles.md` | ~160 |
| 5 | CREATE | `skills/tracing/trace-providers.md` | ~170 |
| 6 | CREATE | `skills/tracing/trace-components.md` | ~190 |
| 7 | CREATE | `skills/tracing/trace-controller-and-session.md` | ~200 |
| 8 | CREATE | `skills/tracing/updating-the-tracer.md` | ~170 |

Totals: **9 files created, 0 modified, 0 deleted.**

The `skills/tracing/` directory is created implicitly by the first file written
into it (PR 1).

## Dependencies

N/A - No new runtime, library, or build dependencies. The skill files are
Markdown only and depend solely on the existing tracing implementation already
on `origin/main`.

## Rollout

Each of the 8 PRs is independent and targets `main`:

1. Create a worktree branch `feat/tracing-skills-<skill>` off `origin/main`.
2. Add the single skill file (PR 1 also adds this design doc).
3. Commit with `docs(tracing): add <skill> skill`.
4. Push and open a draft PR titled `docs(tracing): add <skill> skill` with the
   relevant section of this design doc as the PR body.
5. Move to the next skill.

Because the PRs are pure additions of independent Markdown files, they cannot
conflict with each other regardless of merge order. PR 1 (`SKILL.md`) links to
sibling files that may not yet exist on `main` until their PRs merge; those
links resolve once the sibling PRs land. This is acceptable for docs.

No lint/typecheck/test commands apply (Markdown only).

## Open Questions

1. **Index registration.** Should PR 1 also add a row pointing to
   `skills/tracing/SKILL.md` in the existing "SDK Developer Reference" table in
   `skills/sdk/SKILL.md` and/or the "Usage Skill Files" / "SDK Developer
   Reference" tables in `skills/vidbyte-sdk/SKILL.md`? This would couple PR 1 to
   edits in existing files. Default decision: do NOT modify existing indexes
   (keeps each PR a pure addition); leave registration as a follow-up for the
   user to request. Awaiting confirmation.

2. **PR count.** This design proposes 8 skills / 8 PRs. The user said "make
   however many skills you need." If the user prefers fewer PRs, skills 6 and 7
   (components + controller/session) could be merged, or all could ship as one
   PR. Default: 8 PRs as specified. Awaiting confirmation on whether 8 is
   acceptable or should be consolidated.

3. **Draft vs ready PRs.** The workflow default is `--draft`. Confirm whether all
   8 PRs should open as drafts or as ready-for-review.

## Alternatives Considered

- **Single PR with all 8 skills.** Rejected because the user explicitly asked
  for each skill to be its own PR for decoupled review.
- **One mega `SKILL.md` instead of 8 files.** Rejected because the user asked
  for decoupled, focused skills so an agent can load only the context it needs;
  a single file would force loading the entire tracing surface at once.
- **Modifying source code to "improve" tracing while documenting it.** Rejected
  — scope creep. This is a documentation-only feature; any source change is a
  separate design doc.
- **Duplicating continual-tracing detail into `skills/tracing/`.** Rejected —
  `skills/vidbyte-sdk/continual-tracing.md` already exists and is
  comprehensive. The tracing skills summarize continual tracing and link to it
  to avoid drift.
- **Placing skills under `skills/vidbyte-sdk/` instead of a new
  `skills/tracing/` folder.** Rejected because the user explicitly asked for a
  `skills/tracing` folder, and the repo already uses top-level skill folders for
  cross-cutting subsystems (`skills/agent-runtimes/`, `skills/sources/`,
  `skills/mcp-server/`, `skills/paradigm/`).
