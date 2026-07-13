# Vidbyte SDK — File Index

A compressed, code-free map of the `vidbyte-sdk` repository. Where `llms.txt` is the
full code-heavy documentation bundle, this artifact is the structural companion: read
it to understand what the SDK is, where every folder lives, and why. Paths are
repo-relative. Generated and vendored directories (`.git`, `.github`, `.claude`,
`__pycache__`, `.pytest_cache`, `*.egg-info`, and any nested `worktree-*` checkouts)
are intentionally omitted.

---

## Overview

Vidbyte SDK is the Python package surface of the Vidbyte agent-engineering platform. It
gives developers everything needed to build, instrument, evaluate, and distribute AI
agent workflows from a single import (`vidbyte`): composable agents, agent-local tools,
deterministic runtime middleware, structured context management, context-window
algorithms, prompt libraries, evals, provider adapters, multi-agent pipelines, durable
sessions, artifact sources, tracing primitives, and an MCP Studio server. The design
intent is that a developer builds the agent *itself* — the loop, the tool execution, the
context window, the trace artifact, the runtime policy, and the multi-agent composition
— rather than calling a hosted black box.

The core mental model is small and consistent. You create an `Agent` or `BaseAgent`,
give it a system prompt plus optional model/provider config, runner, tools, context
manager, middleware, trace settings, and runtime choice, and then call `run()` or
`arun()`. From there the SDK assembles the message context, appends an agentic-loop
prompt, sends tool schemas to the model, executes permitted tool calls, folds results
back into ordered history, applies middleware and context-window policy, and repeats
until the model signals completion. Everything larger than a single agent — pipelines,
paradigm harnesses, sessions, MCP exposure — is modeled as composition over that same
primitive core.

The repository is deliberately scoped to reusable, developer-facing abstractions. Public
namespace scaffolding, primitives, and opinionated-but-optional layers ship here; private
Vidbyte service logic, proprietary learning systems, hosted scoring, adaptive sequencing,
and database-of-record access stay outside the package. The SDK is pre-release (alpha,
version `0.1.0`), so APIs may shift between minor versions, and the docs preserve the
boundary between "local Python SDK for agent builders" and "the hosted Vidbyte product"
that lives at vidbyte.pro.

Structurally, the package is layered. `vidbyte/lib` holds the shared substrate —
dataclasses, enums, errors, config, runners, registries, persistence providers, and
low-level tool/HTTP/tracing contracts. On top of that substrate sit the user-facing
domains: `agents`, `context`, `tools`, `middleware`, `providers`, `prompts`, `evals`,
`pipelines`, `sessions`, `sources`, `trace`, and `mcp_server`. Above those sit the
composition layers: `paradigms` for opinionated end-to-end control flows and `harnesses`
as the namespace boundary for custom integrations. This file indexes every one of those
folders so the topology is legible at a glance.

---

## File Index

The index walks the tree top-down. Each entry names a folder path followed by a short
description of its responsibility. Subfolders are grouped under the top-level area they
belong to and ordered to follow the physical tree.

### Package root

#### `vidbyte/`
The importable SDK package and its single public namespace. Its top level holds the
`client.py` entry object (`VidbyteSDK`) plus the flat public re-exports (`Agent`,
`BaseAgent`, `Tools`, `tool`, pipelines, trace, and more) that developers import
directly. Everything else in the repository is a subpackage under here or repo tooling
around it.

### Agents

#### `vidbyte/agents/`
The executable agent actors and the public model-execution surface. Contains `BaseAgent`
and `Agent`, agent input/reply objects, modality routing, agent export/restore state
used by sessions, and the wiring that turns a system prompt plus config into a runnable
loop. This is where "run a model with tools and context" actually lives.

#### `vidbyte/agents/algorithms/`
Context-window reasoning algorithms that periodically pause a direct agent loop to
reflect. Includes the explorer-style problem-space search pass and the auditor-style
error-correction pass, which surface blind spots or prune contradicting context through
managed context primitives. These update the window without rewriting prior conversation
history.

#### `vidbyte/agents/multi/`
Ledger-driven multi-agent team orchestration. Contains the `MultiAgent` facade,
run-local `TaskLedger`, Magentic-One-inspired manager protocol/adapter, and the
developer-controlled transfer seams for dispatch approval, request/report shape,
validation, subtype-preserving forks, and cleanup. Use it for manager-owned progress
and replanning, not fixed pipeline flow or code-owned workflow transitions.

#### `vidbyte/agents/runtimes/`
Swappable execution-loop paradigms that decouple `BaseAgent` from a single control flow.
Holds the runtime configs and the non-linear runtimes such as MCTS tree search, letting
a developer pick how the agent explores and terminates at initialization. The default
linear runtime remains the baseline behavior.

#### `vidbyte/agents/runtimes/actor/`
The asynchronous actor-model runtime: concurrent message-passing loops with point-to-point
and broadcast topologies. Supports dynamic actor spawning, worker models, loop caps, and
quiescence-based termination for swarm-style coordination. This is the most concurrent of
the shipped runtimes.

#### `vidbyte/agents/settings/`
Structured settings objects for agent loop behavior. Centralizes tunable knobs such as
iteration and token caps and other loop-level configuration so they are passed as typed
options rather than scattered keyword arguments. Keeps agent construction consistent
across runtimes.

### Context

#### `vidbyte/context/`
The structured context subsystem: context managers, context windows, and the public
context dataclasses (budget, permissions, base context). Use it when you want reusable,
typed context instead of assembling raw prompt strings by hand. It is the developer-facing
front of the lower-level dataclasses in `vidbyte/lib`.

#### `vidbyte/context/algorithms/`
Context-window growth strategies exposed as `ContextWindow` presets. Includes behaviors
like dropping raw tool outputs, writing periodic trajectory checkpoints, and other rules
that change how runtime context evolves between model calls. Attached to an agent as a
single option.

#### `vidbyte/context/handoff/`
Context models and helpers for agent-to-agent handoff artifacts. Captures the structured
state one agent passes to another so work can continue across boundaries without leaking
full histories. Pairs with the handoff tools and prompts elsewhere in the tree.

#### `vidbyte/context/primitives/`
The individual context-item building blocks — file, task, text, and document context
items, among others. These are the atomic units a `ContextManager` composes and that the
runtime renders into the window. `DocumentContextItem` here is the emission target of the
sources layer.

#### `vidbyte/context/templates/`
Reusable context-window template presets. Bundles common context configurations so
developers can start from a named template rather than wiring primitives from scratch.
A convenience layer over the primitives.

### Evals

#### `vidbyte/evals/`
Small building blocks for writing local eval scripts: `EvalCase`, `EvalSuite`,
`EvalRunner`, and the client/registry surface reached through `sdk.evals`. Runs a target
(agent or runner-like object) over cases with concurrency controls and summarizes pass
rate, mean score, and latency. Suites can be loaded from JSON or CSV and filtered by tag.

#### `vidbyte/evals/behavior/`
Behavior-oriented eval building blocks and fixtures. Supports checking how an agent
behaves across prompts, models, and graders rather than only matching a single expected
string. Feeds the same runner and registry as the rest of the eval subsystem.

#### `vidbyte/evals/graders/`
The built-in grader implementations that score each output. Covers exact match, substring
contains, regex, JSON-schema, LLM-judge, and weighted-rubric grading, with judge-backed
graders accepting an injected runner. `grader` remains the low-level escape hatch beneath
templates.

#### `vidbyte/evals/templates/`
Reusable multi-grader bundles applied through `EvalCase.templates`. Ships presets such as
short-answer fact, multiple choice, structured JSON, classification, numeric answer,
concise grounded answer, and safe customer support. Custom templates subclass
`EvalTemplate` and return any grader.

### Harnesses

#### `vidbyte/harnesses/`
The namespace boundary for custom harness integrations. It exposes a client namespace
(also the mount point for sessions) but ships mostly scaffolding: custom harnesses stay
outside the base SDK until their public contracts are explicitly defined. It marks where
higher-level integrations attach without polluting the primitive layers.

### Lib (shared substrate)

#### `vidbyte/lib/`
The shared foundation the rest of the package is built on. Holds the cross-cutting
dataclasses, enums, errors, config, runners, registries, persistence providers, and
low-level tool/HTTP/tracing contracts. Nothing here is a user-facing domain on its own;
it is the substrate the domains compose.

#### `vidbyte/lib/agents/`
Low-level agent-support types shared beneath the public `vidbyte/agents` surface. Keeps
internal agent contracts separate from the executable actors developers import. A
substrate detail rather than a public entry point.

#### `vidbyte/lib/config/`
Centralized configuration constants and defaults, including source-loader limits and
other tunable ceilings. Keeps magic numbers and shared settings in one place so domains
reference named config instead of inlining values. Imported widely across subsystems.

#### `vidbyte/lib/dataclasses/`
The canonical home for structured data types used across the SDK, including context,
sources, and other domain dataclasses. Public context objects re-export from here, keeping
one source of truth for shapes. The largest lib subpackage by file count.

#### `vidbyte/lib/enums/`
Enumerations that key behavior throughout the SDK — provider identities, runtime types,
budget and permission presets, prompt keys, pin policies, and more. Lookups and registries
resolve these enum members rather than raw strings. Central to type-safe dispatch.

#### `vidbyte/lib/errors/`
The SDK's exception hierarchy. Defines the typed errors surfaced by sources, sessions,
providers, and other layers so callers can catch specific failures. Custom constructors
keep error messages consistent.

#### `vidbyte/lib/http/`
Low-level HTTP transport and parsing helpers. Provides the shared client behavior used by
fetchers, providers, and any layer that needs to make or parse network requests. Keeps
transport concerns out of the domain packages.

#### `vidbyte/lib/models/`
Reserved namespace for shared model-related types. Currently minimal, holding little
beyond its package marker, and exists to give model abstractions a stable home as they
stabilize. A placeholder boundary.

#### `vidbyte/lib/providers/`
Persistence-provider backends for durable data such as sessions. Ships adapters for
MongoDB, Postgres, SQLite, and Supabase behind a common base, so higher layers depend on
a port rather than a specific database. This is storage plumbing, distinct from model
providers in `vidbyte/providers`.

#### `vidbyte/lib/registries/`
Discovery and compatibility catalogs. Hosts the agent, provider-model, runtime, tool, and
actor registries used to resolve capabilities, bridge older code, and register local
runtime objects without hardcoded lookups. The go-to place for "what does the SDK support
and how do I find it."

#### `vidbyte/lib/runners/`
The runner implementations that actually drive model calls beneath agents. Encapsulates
the request/response handling an agent delegates to, including the refactored handle logic
and multiple runner variants. Agents accept these as an injectable execution engine.

#### `vidbyte/lib/templates/`
Shared template assets and helpers used by higher layers such as context and prompts.
Provides reusable text/structure scaffolding at the substrate level. A supporting
utility package.

#### `vidbyte/lib/tools/`
Low-level tool infrastructure beneath the public `vidbyte/tools` surface. Holds internal
tool contracts and the filesystem tool substrate that user-facing tools build on. Keeps
tool internals separate from the developer-facing catalog.

#### `vidbyte/lib/tools/filesystem/`
The filesystem tool substrate: the shared logic for reading and writing within a bounded
workspace. Backs the public filesystem tools with a backend-agnostic core. Where sandbox
and path handling are centralized.

#### `vidbyte/lib/tools/filesystem/backends/`
Concrete filesystem backends behind the substrate, including the local-disk backend and a
common base. Abstracts *where* files live so the same tool logic can target different
storage. Extensible for non-local backends.

#### `vidbyte/lib/tracing/`
Low-level tracing contracts shared across the trace subsystem. Defines the base tracing
abstractions that the public `vidbyte/trace` facade and provider exporters implement.
The substrate half of tracing.

### MCP server

#### `vidbyte/mcp_server/`
The stdio MCP Studio server that exposes Vidbyte agents, tools, prompts, strategies, and
pipelines to MCP-capable hosts. Contains the public `McpStudioServer` re-export, the
`python -m vidbyte.mcp_server` entry point, the `McpSchema` JSON-RPC helpers, and the
Studio tool registry. Launched by clients such as Claude Code, Cursor, or Codex over
stdin/stdout.

#### `vidbyte/mcp_server/server/`
The server core: the main I/O loop and dispatch that reads stdin, routes JSON-RPC
requests, and writes responses. Separates the transport/dispatch engine from the
individual method handlers. The heart of the running process.

#### `vidbyte/mcp_server/server/handlers/`
The protocol-level JSON-RPC method handlers — `initialize`, `tools/list`, `tools/call`,
`prompts/list`, and `prompts/get`. The `tools/call` handler is the one that delegates into
the Studio tools. These are distinct from the Studio tool implementations they dispatch to.

### Middleware

#### `vidbyte/middleware/`
Deterministic runtime hooks for direct text agents. Defines the `AgentMiddleware` base and
`MiddlewareDecision` so developers can gate, retry, rate-limit, audit, and shape a run
without the model ever seeing the middleware. Middleware never appears in tool specs or
agent cards.

#### `vidbyte/middleware/builtins/`
The shipped middleware implementations. Includes token-budget and rate-limit guards,
runtime limits, tool policy, audit logging, model retry, and the compaction middlewares
that keep working context bounded. Import these to compose policy without writing hooks by
hand.

#### `vidbyte/middleware/compaction/`
The compaction engine behind the compaction middlewares. Provides deterministic
provider-message pruning strategies — token-budget trimming, boundary-aware trims, sliding
windows, salience eviction, query-relevance filtering, and trace-backed replacement —
without hidden model calls. This is how history stays small without a summarizer round
trip.

### Paradigms

#### `vidbyte/paradigms/`
The namespace for thin runnable paradigm harnesses: high-level agentic patterns that
compose agents, tools, context, middleware, prompts, trace, pipelines, and evals into one
opinionated control flow. It currently ships scaffolding only — `ParadigmHarness` and
`ParadigmClient` — with no concrete paradigm harness published from this namespace yet.
It sits above raw primitives as the "whole strategy in a box" layer.

### Pipelines

#### `vidbyte/pipelines/`
Multi-agent pipeline topologies with a string-in/string-out contract, where one stage's
output becomes the next stage's prompt. Ships sequential, parallel, conditional, and
map-reduce pipelines, and because every pipeline is itself a valid stage, they nest
freely. The pipeline layer deliberately adds no shared context, budgets, retries, or
voting — each agent keeps its own tools, middleware, context, and history.

### Prompts

#### `vidbyte/prompts/`
The prompt subsystem: repository-backed text assets exposed through an enum-keyed
accessor (`Prompts`) and direct Python imports. Provides discovery methods for keys,
descriptions, families, import names, and full text, with lookups keyed by `Prompt` enum
members rather than raw strings. The catalog is a static asset collection, not a runtime
override mechanism.

#### `vidbyte/prompts/prompts/`
The actual prompt asset files, organized into families. Families include `actor_runtime`,
`agentic_engineering`, `continual_trace`, `goals`, `handoff`, `mimic_behavior`,
`multi_provider_agentic_grader`, `multi_provider_aggregator`, `multi_agent_orchestrator`, `reflexion`, and `templates`,
covering personas, reflexion loops, eval judging, handoff, and trajectory-checkpoint text.
Each family groups related prompt text that the accessor loads and exposes by enum key.

#### `vidbyte/prompts/skills/`
Prompt-adjacent skill assets bundled with the prompt subsystem. Holds skill-style guidance
that ships alongside the prompt catalog. A supporting asset folder for the prompts domain.

### Providers (models)

#### `vidbyte/providers/`
Model-vendor adapters that translate a common provider selection layer into vendor-specific
request, response, modality, and tool-schema handling. Ships adapters for OpenAI,
Anthropic, Gemini, xAI, OpenRouter, ElevenLabs, PlayAI, and OpenAI-compatible endpoints,
plus the `ModelProviders` factory and structured-output schema handling. Providers are
selected by capability and model, so vendor conditionals do not leak into agents and tools.

#### `vidbyte/providers/tracing/`
Optional observability exporters that plug provider-backed tracing into agent runs. Wraps
Langfuse, LangSmith, and Phoenix behind the `Trace` provider presets. These are the
adapters `Trace.langfuse(...)` and friends resolve to.

### Sessions

#### `vidbyte/sessions/`
The durable-sessions primitive: attach an agent to a `Session` in one line and reconstruct
runs via continue, resume, fork, and rewind over a checkpoint DAG. Owns the session
wrapper and verbs, the `SessionClient` namespace (also reachable via
`sdk.harnesses.sessions`), contracts, checkpoint/run-state types, scope, serialization,
portable bundle export/import, and typed errors. It is built on the agent
export-state/restore contract and a pluggable `SessionStore` port.

#### `vidbyte/sessions/stores/`
The local session store backends. Provides in-memory and file-backed stores implementing
the `SessionStore` port; database-backed stores live under `vidbyte/lib/providers`. This
is where session state physically persists for local development.

### Shared

#### `vidbyte/shared/`
A reserved shared namespace with no stable public symbols yet. It exists to hold
cross-domain utilities that graduate into a stable home, and its README documents the
placeholder status. Intentionally near-empty today.

### Sources (artifact loaders)

#### `vidbyte/sources/`
The artifact-source primitive layer: it compiles public, machine-readable documents into
`DocumentContextItem` primitives deterministically and pinned-by-hash by default. Owns the
`Source[T]` lifecycle substrate (fetch, pin, parse, emit, cache), trust handling for
untrusted content, and a URL allowlist security gate. It turns a public artifact such as
an `llms.txt` file into a typed context primitive an agent can consume.

#### `vidbyte/sources/cache/`
Snapshot caches for fetched source content. Ships in-memory, file-backed, and null cache
implementations behind a common base so pinned snapshots can be reused across loads.
Keeps deterministic, hash-pinned fetches cheap.

#### `vidbyte/sources/fetches/`
The fetcher implementations that retrieve raw source bytes. Covers HTTP, file, in-memory,
and chained fetchers, plus a SHA-256 hashing helper used for content pinning. This is the
"go get the bytes" half of the source lifecycle.

#### `vidbyte/sources/llms_txt/`
The dedicated parser for the `llms.txt` document format. Turns an `llms.txt` file into
typed document, link, and section structures via `LlmsTxtParser` / `parse_llms_txt`.
Powers the `llms.txt` source loader.

#### `vidbyte/sources/loaders/`
The concrete `Source` loaders that map a fetched artifact to an emitted primitive. Ships
the generic `DocumentSource` and the `LlmsTxtSource`, each running the shared lifecycle to
produce a `DocumentContextItem`. The developer-facing entry points of the sources package.

#### `vidbyte/sources/regex/`
Regex helpers used to select and slice content within source documents. Provides document,
llms.txt, and general sources regex utilities for extracting the relevant portion of a
fetched artifact. A parsing-support utility for the loaders.

### Tools

#### `vidbyte/tools/`
The developer-facing tool subsystem. Defines the tool contract and `@tool` decorator, the
`Tools` catalog/inspection helper, provider-schema formatting, execution, and the
compatibility registry/executor. The tool path is agent-local: create or import tools,
pass them to an agent, and let the agent describe, format, and execute them on model
request.

#### `vidbyte/tools/builtins/`
The catalog of ready-made tools grouped by capability. Aggregates code search, editing,
context, memory, handoff, MCP, provider, and session tool families so developers can pull
production-ready tools instead of writing their own. Each capability lives in its own
subfolder below.

#### `vidbyte/tools/builtins/code_search/`
Repository search tools: `GlobTool`, `GrepTool`, and `SemanticSearchTool`. Let an agent
locate files and code by pattern or meaning within a workspace. Common building blocks for
repository-analyst and coding agents.

#### `vidbyte/tools/builtins/context/`
The manual/legacy context-compaction tool (`ContextCompactionTool`) for tool-driven
compaction. New agent code is steered toward compaction middleware instead, but this
remains for backward compatibility. A bridge for older examples.

#### `vidbyte/tools/builtins/context_primitives/`
Tools that let an agent read and write managed context primitives directly. Expose the
context-primitive layer as callable tools so a runtime can update its own window. Support
the context-window algorithms that inject bounded notes.

#### `vidbyte/tools/builtins/editing/`
Code-editing tools, principally `PatchTool`. Lets an agent apply structured edits to files
within its permitted workspace. The mutation counterpart to the read-only code-search
tools.

#### `vidbyte/tools/builtins/handoff/`
Tools for creating and consuming agent handoff artifacts. Give an agent an explicit action
to package state for a successor agent. Pair with the context handoff models and handoff
prompt family.

#### `vidbyte/tools/builtins/mcp/`
Built-in tools related to MCP usage from the tool side. Complement the MCP client/transport
layer by exposing MCP capabilities as agent-callable tools. Part of the "attach external
MCP servers to an agent" direction.

#### `vidbyte/tools/builtins/memory/`
Memory tools that let an agent store and recall information across a run. Provide a simple
scratch/recall surface distinct from durable sessions. Useful for agents that accumulate
findings over many iterations.

#### `vidbyte/tools/builtins/providers/`
Tools that expose persistence-provider access (for example MongoDB and row-oriented
queries) as agent-callable actions. Bridge the `vidbyte/lib/providers` backends into the
tool layer with descriptions and a common base. Let an agent read structured data through
a governed tool.

#### `vidbyte/tools/builtins/sessions/`
Agent-facing session tools that reuse the sessions primitive: session, checkpoint, fork,
batch-fork, rewind, and the resume-replace/append/output variants. They let an agent
branch, checkpoint, and resume its own run over the checkpoint DAG. Thin tool wrappers over
the classes in `vidbyte/sessions`.

#### `vidbyte/tools/filesystem/`
The public filesystem tools for reading, writing, and navigating a bounded workspace. The
largest builtin tool group, backed by the filesystem substrate in `vidbyte/lib/tools`.
Where coding agents get their file access.

#### `vidbyte/tools/mcp/`
The MCP client bridge: `McpClient`, `McpStdioTransport`, `McpBridgedTool`, and the preset
registry. Lets an agent attach third-party MCP servers — by preset name or raw command —
and use their tools as if native. Presets define command templates and required env vars
without storing secrets.

#### `vidbyte/tools/security/`
Tool permission and sandboxing. Defines `PermissionPolicy`, `ToolPermission`, and sandbox
transport protocols so mutating or executable tools require explicit authorization. The
default policy allows only `SAFE` and `READ` tools; anything more needs an explicit policy
on the agent.

### Trace

#### `vidbyte/trace/`
The public tracing facade. Exposes the `Trace` presets (`off`, `debug`, provider-backed,
and `continual`) and the debug tracer that keeps an in-memory event list for local
inspection. It is the single knob developers set to make a run emit spans without wiring
adapters by hand.

#### `vidbyte/trace/components/`
Per-subsystem trace component extractors and parsers. Break a run into traceable pieces for
agents, algorithms, context, middleware, runtimes, and tools so traces carry structured
detail per layer. Support richer trace profiles than a flat event log.

#### `vidbyte/trace/continual/`
The structured continual-trace artifact system. A dedicated `ContinualTraceAgent` fills a
developer-supplied schema (including the prebuilt `ActionTrace`) during a run via a
validating update tool, appending arrays, deep-merging objects, and replacing scalars. The
artifact is returned on the reply metadata and is fail-open, never written into the main
agent's context window.

#### `vidbyte/trace/providers/`
The trace exporter implementations behind the facade. Ships a generic exporter and a
LangSmith exporter over a common base. These realize the provider-backed tracing the
`Trace` presets select.

### Repository tooling

#### `skills/`
Agent-usable skill guides for working with the SDK, one folder per skill. Each is a
documentation-and-workflow asset (mostly `SKILL.md` plus supporting how-to pages), not
shipped Python. The subfolders below cover runtimes, loop settings, the MCP server,
paradigms, sources, usage recipes, and the SDK reference itself.

#### `skills/agent-runtimes/`
Skill reference for the swappable agent runtimes. Explains selecting and configuring the
linear, MCTS search, and actor-model loops at agent initialization. The guide behind the
runtime examples in the README.

#### `skills/agentic-loop-settings/`
Ground-truth reference for every agentic loop setting in the SDK. Documents the knobs that
shape the agent loop — iteration and token caps and related controls — in one place.
Keeps loop configuration authoritative and consistent.

#### `skills/docs/`
Longer-form documentation and worked prose rather than a single skill file. Holds
reference material such as a map-reduce pipeline write-up and a prompt-engineering master
prompt. Supporting docs surfaced through the skills tree.

#### `skills/mcp-server/`
Guide to building on the MCP Studio server. Covers adding protocol handlers, adding Studio
tools, and the tool request/response shapes, distinguishing Studio tools from JSON-RPC
handlers. The companion to the `vidbyte/mcp_server` package.

#### `skills/paradigm/`
Explains what a paradigm is in the SDK — a thin, runnable, high-level harness that composes
primitives into one opinionated control flow — and how to build one. Pairs with the
scaffolding in `vidbyte/paradigms`. Conceptual guidance more than API reference.

#### `skills/sdk/`
The meta index of the skills tree plus rules for maintaining it. Catalogs the available
skills and documents how to update skill files. A directory-of-directories for
contributors.

#### `skills/sources/`
Development rules for the artifact-sources layer. Documents the conventions and guardrails
for adding fetchers, loaders, caches, and parsers under `vidbyte/sources`. The design
contract behind that subsystem.

#### `skills/usage/`
Task-oriented usage recipes for common SDK operations. Includes create-agent,
create-agent-with-tools, create-tool, create-pipeline, import-prompt, and agent-behavior
walkthroughs, plus lists of available features and tools. The quickest path to a working
snippet.

#### `skills/vidbyte-sdk/`
The master directory rule file and layout reference for the SDK, and the largest skill.
Bundles per-subsystem how-to pages spanning context algorithms, prompts, agent behavior,
context primitives, continual tracing, evals, handoff, memory tools, middleware, pipelines,
sessions, and ledger-driven multi-agent teams. The broadest single entry point into SDK skills.

#### `skills/vidbyte-sdk-doc/`
A comprehensive reference for the repository as a whole. Covers public APIs, package layout,
design docs, subsystem responsibilities, contribution guardrails, and verification commands
in one place. The doc-index counterpart to this file index.

#### `docs/`
Repository design documentation. Holds the engineering records that precede non-trivial
features; its contents are internal notes, not public API surface. See the `design/`
subfolder below.

#### `docs/design/`
The concrete design docs written before implementing SDK features, including this artifact's
own design doc (`artifact-file-index.md`). Each captures goals, requirements, detailed
design, and a file-change manifest for one change; `magentic-one-multi-agent.md`
specifies the shared-ledger team primitive. They are historical engineering
artifacts rather than user-facing documentation.

#### `scripts/`
Standalone verification and demonstration scripts, largely `test-*.py` and `test_*.py`
files exercising specific features end-to-end. They serve as runnable checks and worked
examples alongside the formal test suite. Useful for reproducing a feature's behavior in
isolation.

#### `tests/`
The formal automated test suite for the package, discovered via `python -m unittest
discover -s tests`. Validates the SDK's public behavior across its subsystems. The primary
guardrail for changes.

#### `artifacts/`
The repository's artifact folder, holding curated repo-level artifacts. This `file_index.md`
is its first entry: a compressed, code-free structural map complementing `llms.txt`. Future
artifacts of the same "map, not tutorial" character belong here.

---

## General Principles

The SDK is built around four principles that explain why the tree looks the way it does.

### Ship every primitive a harness needs, out of the box
The SDK aims to provide, ready to use, all the primitives an agent harness requires: the
agent loop, tool declaration and execution, context windows, middleware, tracing, prompts,
evals, pipelines, sessions, sources, and provider adapters. A developer should be able to
assemble a working agent without first building the missing foundational pieces
themselves.

### Bring our own unique abstractions
Beyond wrapping model calls, the SDK contributes first-party abstractions you will not find
assembled the same way elsewhere — swappable agent runtimes, deterministic non-model
middleware and compaction, managed context primitives with reflection algorithms,
structured continual-trace artifacts, durable checkpoint-DAG sessions, and hash-pinned
artifact sources. These opinions are the value the SDK adds on top of raw providers.

### Be highly extensible and customizable
The harness is designed to be reshaped. Runtimes, middleware, graders, context-window
algorithms, tools, providers, session stores, sources, and trace exporters are all pluggable
behind registries and common bases, so nearly every part of the loop can be swapped or
extended. The customizable surface is deliberately large.

### Be easy for the developer to use
Despite that depth, the common path stays a few lines: import from `vidbyte`, create an
`Agent`, pass a system prompt and optional tools/context/middleware, and call `run()` or
`arun()`. Sensible defaults, enum-keyed lookups, catalog helpers, and one-line presets keep
the simple case simple while the extensibility stays available when it is needed.
