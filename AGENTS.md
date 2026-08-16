# Vidbyte SDK

Vidbyte is an agent engineering platform for building, evaluating, instrumenting, and distributing AI workflows. The Vidbyte SDK is the Python package surface for that platform: composable agents, tools, middleware, context management, MCP server integration, prompts, evals, provider adapters, pipelines, validated workflows, durable sessions, artifact sources, and tracing primitives — all reachable from a single `vidbyte` import. The design intent is that a developer builds the agent *itself* — the loop, the tool execution, the context window, the trace artifact, the runtime policy, the multi-agent composition — rather than calling a hosted black box.

The mental model is small and consistent. You create an `Agent` or `BaseAgent`, give it a system prompt plus optional model/provider config, runner, tools, context manager, middleware, trace settings, and runtime choice, then call `run()` or `arun()`. The SDK assembles the message context, appends an agentic-loop prompt, sends tool schemas to the model, executes permitted tool calls, folds results back into ordered history, applies middleware and context-window policy, and repeats until the model signals completion. Everything larger than a single agent — pipelines, paradigms, sessions, MCP exposure — is composition over that same primitive core. This repository is deliberately scoped to reusable, developer-facing abstractions: private Vidbyte service logic, proprietary learning systems, hosted scoring, and database-of-record access stay outside the package. Status is **alpha**, so APIs may change between minor versions.

> **This file is a Map.** It is a lossy compression of what this repository already contains in full — folder topology and what each folder is for, nothing that isn't derivable from the tree itself. It exists to answer *where do I look next*, not to be correct in every detail. It is expected to drift; regenerate it rather than patching it. For a deeper structural index, read [`artifacts/file_index.md`](artifacts/file_index.md); for the code-heavy documentation bundle, read [`llms.txt`](llms.txt).

## File Index

**Root files:** `README.md` — the Layer Guide table is the authority on what each `vidbyte/` subpackage is for. `llms.txt` — the full agent-readable documentation bundle, code-heavy where this Map is code-free. `pyproject.toml` — packaging, the `[dev]` extra, and dependency pins. `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE`, `.gitignore`.

### `.github/`

GitHub-hosted repository configuration: issue templates, the pull request template, and the CI/publish/policy workflows. Everything here runs on the GitHub side rather than in the package, so nothing in it ships to PyPI. Changes to workflow files change the remote gate and should be matched by the local gate in `scripts/run_ci.py`.

#### `.github/ISSUE_TEMPLATE/`

The structured bug-report and feature-request forms contributors fill in when opening an issue. They exist so that reports arrive with the reproduction details, SDK version, and provider context that triage needs. Purely a GitHub UI concern.

#### `.github/workflows/`

Three workflows. `ci.yml` runs the source and package stages across a Python 3.11/3.12 matrix on every pull request and every push to `main`; `static-policy.yml` runs the Semgrep rules from `.semgrep/`; `publish.yml` handles PyPI release. All three run on pull requests with no path filters, so even a docs-only change exercises them.

### `.semgrep/`

Custom static-analysis policy enforced in CI, separate from lint. It currently holds the typed-mapping boundary policy — a rule plus its Python implementation that stops untyped mapping types from leaking across layer boundaries where a dataclass is required. `README.md` explains the rule's intent. This is where architectural constraints get made mechanical rather than left to review.

### `artifacts/`

Generated, code-free reference artifacts about the repository itself. It holds `file_index.md`, a 500-line compressed map of the whole tree: what the SDK is, where every folder lives, and why. Where `llms.txt` is the code-heavy documentation bundle, `file_index.md` is the structural companion, and this `AGENTS.md` is its compressed form. Regenerate rather than hand-patch.

### `docs/`

Design documentation for the SDK, and by volume the largest documentation surface in the repository. Every non-trivial change lands a design doc before implementation, so this folder is the decision history for the whole package. At 146 files it is larger than the test suite, which is a fair description of how this repository is built.

#### `docs/design/`

Roughly 146 design docs, one per feature. This is where to look first when a public API's shape seems arbitrary — the reasoning, alternatives considered, and rejected approaches are recorded here rather than in code comments. Filenames follow the feature name, so `git ls-files docs/design | grep <topic>` is the fastest way to find the rationale behind any subsystem.

### `scripts/`

Verification entry points, kept outside the package so they never ship in the wheel. `run_ci.py` is the canonical gate — `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py` — with `--stage source` and `--stage package` available as diagnostics only. The remaining ~45 `test-*.py` scripts are targeted, feature-scoped verifications written alongside their design docs; `check_context_write_paths.py` enforces a structural rule about where context may be written. Targeted scripts diagnose, but they never substitute for a full `run_ci.py` pass.

### `skills/`

Reusable SDK skills and usage guides distributed with the package — instructions an agent or developer loads to work with the SDK correctly, such as `usage/create_agents.md`. This is distinct from the package-internal `vidbyte/skills/` further down, and the name collision is a live source of confusion: this folder is repository-level source, that one is importable package code. Per the Map's own rule, contents are not expanded here.

### `tests/`

The pytest suite, roughly 80 files, organized as one module per subsystem rather than mirroring the package tree. `agent_test_support.py` holds the shared fakes and fixtures — stub providers, recording tracers, deterministic runners — that let agent behavior be asserted without network calls. Coverage runs wide: agent abstractions, runtimes, middleware, context management and compaction, tools, evals, sessions, sources, config validation, and the CLI interface. This suite is the `source` stage of `scripts/run_ci.py`.

#### `tests/multi_agent/`

Tests for compositions that span more than one agent — pipelines, handoffs, actor-model topologies, and multi-agent graders. Split into its own package because these tests need multi-participant fixtures and different timing assumptions than single-agent tests. Small (4 files) but load-bearing for the `pipelines/` and `agents/multi/` layers.

### `vidbyte/`

The installable package — everything that ships. It is layered: `lib/` is the shared substrate, above it sit the user-facing domains (`agents`, `context`, `tools`, `middleware`, `providers`, `prompts`, `evals`, `pipelines`, `sessions`, `sources`, `trace`, `mcp_server`), and above those sit the composition layers (`paradigms`, `harnesses`, `workflows`). `client.py` is the top-level client and `__init__.py` defines the public import surface. Nothing outside this folder is importable by users.

#### `vidbyte/agents/`

Executable agent actors and the runner selection that drives them — `Agent`, `BaseAgent`, sync and async runs, handoffs, and agent registries. This is the primitive everything else composes over, and the place to start reading the package. It owns the agentic loop: build context, call the model, execute permitted tools, fold results back, apply middleware, repeat until completion.

##### `vidbyte/agents/algorithms/`

Reusable multi-agent reasoning algorithms packaged as drop-in agent behaviors: `reflexion.py` (critique-and-revise loops), `independent_critic.py`, `prosecutor_defender_judge.py` (adversarial three-role evaluation), and `multi_provider_agentic_grader.py`. Each is an opinionated composition of agents rather than a new primitive. Reach here before hand-wiring a critic loop.

##### `vidbyte/agents/contracts/`

The invariants an agent configuration must satisfy. `schema.py` defines the structured-output contract and `floors.py` defines the minimum acceptable settings — the floors below which an agent is misconfigured rather than merely unusual. Small, but it is what turns a bad configuration into an error at construction time instead of a confusing failure mid-run.

##### `vidbyte/agents/multi/`

Multi-agent machinery below the pipeline layer: the aggregate agent, dispatcher, and cleanup handling that let several agents participate in one logical run. `agent.py` and `dispatcher.py` carry the routing; `cleanup.py` guarantees resources are released when a participant fails. `README.md` documents the contract. Use `pipelines/` for topology; use this when you need shared-run semantics.

##### `vidbyte/agents/pricing/`

Per-provider token and cost accounting, one module per vendor (`anthropic.py`, `gemini.py`, `compatible.py`) over a shared `base.py`. It converts raw provider usage into normalized token counts and dollar costs so an agent can report `get_usage()` and `get_cost_usd()` regardless of which model ran. This is the layer that makes budget middleware and wallet settlement possible upstream.

##### `vidbyte/agents/runtimes/`

The execution strategies an agent can run under, beyond the default linear loop. Includes the actor-model runtime (`actor/` with its actor, broker, and inbox) supporting point-to-point, broadcast, static, and dynamic topologies, alongside search-based runtimes such as MCTS. Choosing a runtime changes how the agent explores, not what tools it has.

##### `vidbyte/agents/settings/`

The tunable knobs of an agent run, factored out of the agent class itself: `loop.py` (iteration limits and termination), `tool.py` and `tool_error.py` (tool execution and failure policy), `fallback.py` (what happens when the primary model is unavailable). Keeping these as explicit settings objects is what makes agent behavior inspectable and serializable rather than buried in constructor arguments. Add a knob here rather than another constructor parameter on the agent.

#### `vidbyte/cli/`

The `vidbyte-sdk` console command — the SDK's own developer surface, currently just `vidbyte-sdk skills`. Deliberately minimal: this is *not* the Vidbyte product CLI (that is the separate `Vidbyte-cli` repository, which talks to the backend research API). This one exposes SDK-local developer utilities only.

#### `vidbyte/config/`

Safe YAML parsing into declarative configuration — either agent settings with nested tools and middleware, or a harness spec — plus construction of a working agent from those settings alone. This is the declarative half of the SDK: describe an agent in YAML, get a real `Agent` back, with references resolved from the SDK's own registries rather than from caller-supplied components. Read `README.md` here before adding a new config field.

#### `vidbyte/context/`

Structured context items, context windows, compaction, and handoff models — everything about *what the model sees*. `ContextManager` is the entry point; context is modeled as typed items rather than raw strings so that budgeting, pruning, and permissions can be reasoned about mechanically. This layer is the most common source of surprising agent behavior, and the most worth understanding early.

##### `vidbyte/context/algorithms/`

Context-window algorithms that decide what survives when the window fills: `problem_space_search.py`, `error_correction.py`, `independent_critic.py`, `multi_provider_agentic_grader.py`, and siblings. Each is a named, swappable strategy rather than an implicit heuristic. Pair with `middleware/compaction/` to apply one automatically during a run.

##### `vidbyte/context/handoff/`

Models for transferring context from one agent to another — `minimal.py` (carry the least that still works), `engineering.py`, and `research.py` as domain-shaped variants over `base.py`. A handoff is a lossy compression decision, and this folder is where those decisions are named and made explicit rather than left to whatever the prompt happens to include. Pair with the handoff tools in `tools/builtins/` to let an agent trigger one itself.

##### `vidbyte/context/primitives/`

The composable building blocks of a context window: `base.py`, `checkpoints.py`, `closure.py`, and the rest of the 14-file set. These are the pieces `ContextManager` assembles, and they are what a tool or middleware touches when it needs to read or modify context safely. `README.md` documents the binding rules; `scripts/check_context_write_paths.py` enforces them.

##### `vidbyte/context/templates/`

Prebuilt context-window shapes for common agent patterns, so a caller can pick a template rather than assembling primitives by hand. `recorder.py` is the current member, capturing a run's context for later replay or inspection. Small folder, but it is the ergonomic front door to the primitives layer.

#### `vidbyte/evals/`

Local evaluation: `EvalCase`, `EvalSuite`, a concurrent `EvalRunner`, result summaries, and a SQLite-backed run registry for comparing runs over time. Everything is local — no hosted scoring service is involved, by design. This is how a change to an agent is shown to be an improvement rather than asserted to be one.

##### `vidbyte/evals/behavior/`

Graders that score *how* an agent worked rather than what it returned: `efficiency.py` (iteration and token economy), `handoff.py` (whether context transfer preserved what mattered), `output.py`, and `behavior.py`. These catch the regressions that output-only grading misses — an agent that reaches the right answer after twelve wasteful tool calls scores differently here. Pair these with output graders rather than choosing between the two.

##### `vidbyte/evals/graders/`

The output graders, 15 files spanning cheap deterministic checks to model-driven judgment: `choice_match.py`, `contains.py`, `contains_all.py`, regex and JSON-schema matching, LLM-judge, multi-provider agentic grading, and weighted rubrics, with `composite.py` for combining them. Start with the cheapest grader that can distinguish pass from fail; reach for LLM judgment only when it cannot. Every grader implements the same interface, so swapping one is configuration rather than a rewrite.

##### `vidbyte/evals/templates/`

Reusable eval bundles — prepackaged suites that can be pointed at an agent without authoring cases from scratch. `builtins.py` holds the shipped templates, `registry.py` makes them discoverable by name, and `base.py` defines the contract a template satisfies. Useful for baseline coverage before writing domain-specific cases.

#### `vidbyte/harnesses/`

The `Harness` base class: config-as-source-of-truth identity, Session-backed capture, and consented, redacted trajectory export. A harness wraps an agent workflow so that each run emits a `TrajectoryRecord` — task, full trajectory, resolved config, scalar reward — suitable as RL training data. This is the SDK-side contract that the Vidbyte backend's executed harnesses and the Cookbook's harness examples both build on.

##### `vidbyte/harnesses/stores/`

Persistence backends for captured trajectories, behind one interface: `memory.py` for tests, `file.py` for local JSONL export, over `base.py`. Keeping the store swappable is what lets a harness run identically in a notebook and in production. Add a backend here rather than teaching `Harness` about storage.

#### `vidbyte/lib/`

The shared substrate every other layer depends on and none of them may bypass — dataclasses, enums, errors, config, runners, registries, persistence providers, and low-level tool, HTTP, and tracing contracts. Nothing here should import from a domain layer above it; that direction of dependency is the invariant that keeps the package layered. `README.md` documents the boundary.

##### `vidbyte/lib/agents/`

Agent-support utilities that must live below the `agents/` layer to avoid a circular import: `modality_detector.py` (routing a request to text, image, video, audio, or embedding based on the model) and a `prosecutor_defender_judge.py` support module. Small and slightly awkward by nature — this is the overflow valve for logic `agents/` needs but `lib/` must own. Keep it minimal � anything that can live in `agents/` should.

##### `vidbyte/lib/config/`

Configuration loading and resolution below the declarative `vidbyte/config/` layer. `loader.py` reads and merges sources, `base.py` and `constants.py` define the shapes and defaults, and `mcp_presets.py` holds the built-in MCP server presets with their required-environment metadata. This is where "what is the effective value of this setting" gets answered.

##### `vidbyte/lib/configs/`

Narrow, single-purpose configuration objects that do not belong to the general loader. Currently `structured_output.py`, describing how a model's structured output is requested and validated. Kept separate from `lib/config/` because these are per-feature contracts, not user-editable settings.

##### `vidbyte/lib/constants/`

Values declared once because they are needed in more than one place. Currently `runners.py`, holding runner identifiers and defaults shared between `lib/runners/` and the agent layer that selects among them. If a literal appears twice, it belongs here.

##### `vidbyte/lib/dataclasses/`

The typed vocabulary of the whole SDK, and its largest single folder at 30 files — agent descriptors (`agent_descriptor.py`, `aggregate_agent_descriptor.py`, `adversarial_agent_descriptor.py`), plus the shapes for context, tools, runs, usage, and results. These are the types that cross every layer boundary, which is exactly what the `.semgrep/` typed-mapping policy exists to protect. Add a type here before passing a dict.

##### `vidbyte/lib/enums/`

Closed value sets used across layers: `agent_runtime.py`, `model_modality.py`, `config.py`, `context.py`, and others. Enums rather than strings is what makes invalid states unrepresentable and lets registries key on something checkable. Extending an enum is an API change — check for exhaustive matches on it before adding a member.

##### `vidbyte/lib/errors/`

The SDK's exception hierarchy, rooted in `base.py`. Every failure the package raises descends from here, so a caller can catch SDK errors as a class without catching unrelated `ValueError`s. Deliberately tiny — the discipline is a shallow hierarchy with informative messages, not a class per failure mode.

##### `vidbyte/lib/http/`

The low-level HTTP substrate: `transport.py` for making requests (sync and async) and `parser.py` for reading responses. Provider adapters and MCP clients both sit on top of this rather than reaching for a client library directly, so retry, timeout, and streaming behavior are decided in one place. Do not reach for an HTTP client directly elsewhere in the package.

##### `vidbyte/lib/models/`

A namespace reserved for model metadata, currently holding only its `__init__.py`. Listed here so its emptiness is a known fact rather than something to go looking for. Model discovery and configuration currently live in `lib/registries/models.py`.

##### `vidbyte/lib/providers/`

Persistence providers behind one interface — `sqlite.py`, `postgres.py`, and `mongodb.py` over `base.py`. These back the eval run registry, session stores, and anything else that needs durable local state. Note the naming collision with `vidbyte/providers/`, which is about *model* providers; this folder is about *databases*.

##### `vidbyte/lib/registries/`

Name-to-implementation lookup for everything the SDK can resolve by string: `agents.py`, `actors.py`, `components.py`, `models.py`, and siblings. Registries are what let a YAML config name a tool or a runtime and get a real object back, and they are the reason declarative agent construction does not need caller-supplied components. Register at import time, resolve at construction time.

##### `vidbyte/lib/runners/`

The per-modality execution layer that actually calls a model: `image.py`, `audio.py`, `embedding.py`, and their siblings over `base.py`. A runner owns the request/response shape for one modality; the agent selects one via `lib/constants/runners.py` and the modality detector. Adding a modality means adding a runner here, not branching inside the agent.

##### `vidbyte/lib/templates/`

The substrate behind the algorithm and eval template layers above — `base.py` plus shared implementations such as `error_correction.py`, `independent_critic.py`, and `problem_space_search.py`. It exists so `context/algorithms/` and `agents/algorithms/` can share a definition rather than each carrying its own copy. Change here affects both.

##### `vidbyte/lib/tools/`

Low-level tool contracts that must sit below `vidbyte/tools/`, chiefly the filesystem backend abstraction (`filesystem/backends/base.py`, `filesystem/backends/local.py`). Separating the *backend* from the *tool* is what allows the same filesystem tools to run against a local disk or a sandboxed remote without the tool knowing which. Add a backend here; add a tool above.

##### `vidbyte/lib/tracing/`

The tracing contract — `base.py` — that both the in-package `trace/` facade and the external provider adapters implement. Keeping the interface in `lib/` is what lets middleware and runners emit spans without importing a tracing implementation. Two files, but they define the shape of all observability in the SDK.

#### `vidbyte/mcp_server/`

The stdio MCP Studio server that exposes Vidbyte agents, tools, prompts, strategies, and pipelines to any MCP-compatible host. This is the outbound direction of MCP — the SDK *as* a server. The inbound direction, attaching third-party MCP servers to an agent, lives in `vidbyte/tools/mcp/`; keeping the two straight is essential when debugging.

##### `vidbyte/mcp_server/server/`

The JSON-RPC implementation itself: `core.py` for the protocol loop and `handlers/` for one module per method (`initialize.py`, `prompts_get.py`, and siblings). Handlers translate MCP requests into SDK calls and SDK results back into protocol-safe responses. Add a capability by adding a handler, not by branching in `core.py`.

#### `vidbyte/middleware/`

Deterministic hooks around runs, iterations, model calls, tool calls, errors, and completion. Middleware is where policy lives — the things that must happen regardless of what the model decides — which is exactly why it is deterministic code rather than prompt instruction. Application-defined authorization and policy middleware plug in through the same interface as the built-ins.

##### `vidbyte/middleware/builtins/`

The shipped policy set, 16 files: `audit.py` (audit logging), `circuit_breaker.py` and retry handling, token and runtime budget limits, loop detection, tool policy enforcement, and the security-flavored `canary_tripwire.py` and `confused_deputy.py`. These are the guardrails you get for free. Read this folder before writing custom middleware — the behavior you need may already exist.

##### `vidbyte/middleware/compaction/`

Middleware that applies context-window policy during a run rather than after it. `engine.py` drives compaction, `strategies.py` selects among message-history, tool-result, summary, selective-pruning, relevance, salience, snapshot, and trace-backed approaches, and `context_compaction.py` is the middleware entry point. This is the bridge between `context/algorithms/` and a live agent loop.

#### `vidbyte/paradigms/`

Thin, runnable end-to-end control flows assembled from agents, tools, context, prompts, middleware, trace, pipelines, and evals. A paradigm is an opinionated but optional composition — the SDK's answer to "show me a working system, not just primitives". Each is self-contained enough to run and small enough to read.

##### `vidbyte/paradigms/context_minimal_fanout/`

The one shipped paradigm: minimal-context fan-out, where a coordinator dispatches narrowly scoped subtasks to workers that each receive the least context that still works, then folds the results back. `client.py` and `paradigm.py` carry the flow, with its own `prompts/` alongside. `README.md` explains when this shape wins — chiefly when per-worker context cost dominates.

#### `vidbyte/pipelines/`

Multi-agent pipeline topologies with a string-in/string-out contract: sequential, parallel, conditional, and map-reduce. Stages nest, and each stage's agent keeps its own tools, middleware, context, and history — composition does not flatten the participants. Use this for topology; use `agents/multi/` when participants need shared-run semantics instead.

#### `vidbyte/prompts/`

The repository-backed prompt library: static prompt assets, enum-keyed lookup, direct imports, and prompt families. Prompts are versioned files rather than inline strings so they can be diffed, reviewed, and reused across agents. The enum keying is what lets a prompt be referenced from config without a filesystem path.

##### `vidbyte/prompts/prompts/`

The prompt assets themselves, 75 files organized by family — for example `actor_runtime/` with its `coder.md`, `critic.md`, and `decomposer.md` alongside a JSON manifest. Each family groups the prompts one subsystem needs. Add a prompt as a file here and expose it through the enum; do not inline it at a call site.

##### `vidbyte/prompts/skills/`

Skill documents shipped as prompt assets — currently `agentic-engineering.md` and `prompt-bucket.md`. These are instruction sets an agent can be handed at runtime, distributed through the prompt layer rather than the repository-root `skills/` folder. Distinct from both `vidbyte/skills/` and the root `skills/`; check which surface you actually mean.

#### `vidbyte/providers/`

Provider adapter factories for text, image, video, audio, embeddings, and streaming — the layer that turns "call this model" into a concrete vendor API call. Adapters normalize request and response shapes so an agent can switch vendors without changing its own code. Model discovery and configuration registries sit alongside in `lib/registries/models.py`.

##### `vidbyte/providers/tracing/`

Adapters that ship SDK traces to external observability platforms: `langsmith.py`, `langfuse.py`, and `phoenix.py`. Each implements the `lib/tracing/base.py` contract, so enabling one is configuration rather than code change. Note this is provider-*tracing*, distinct from `vidbyte/trace/providers/` which holds the in-package tracer implementations.

#### `vidbyte/sessions/`

Durable checkpoint-DAG persistence: sessions that checkpoint, resume, fork, batch-fork, tag, export/import, and roll up usage across long-running work. A session is a DAG rather than a linear log, which is what makes forking and comparing alternative continuations possible. This is the layer harnesses use to capture a trajectory.

##### `vidbyte/sessions/stores/`

Storage backends for sessions — `memory.py` and `file.py` — behind a common interface. Same pattern as `harnesses/stores/`: swap the backend, keep the semantics. Use memory in tests and file locally; a database-backed store would be added here.

#### `vidbyte/shared/`

A reserved shared namespace with no stable public symbols at present. It is listed so that its emptiness is a documented fact rather than a gap to investigate. Do not add to it without a design doc — the reason it is empty is that most "shared" code belongs in `lib/`.

#### `vidbyte/skills/`

Package-internal skill support: the importable code that lets an agent load and use a skill document at runtime. Three files, and easily confused with both the repository-root `skills/` (distributed skill sources) and `vidbyte/prompts/skills/` (skill documents shipped as prompt assets). This one is the machinery; those two are the content.

#### `vidbyte/sources/`

The artifact-to-context layer: `Source[T]` loaders that turn a public artifact into a typed SDK primitive. The first supported path is a documentation site's `llms.txt` becoming `DocumentContextItem`s an agent can reason over; OpenAPI-to-tools is the planned next one. This is how external documentation enters an agent's context without a bespoke scraper per site.

##### `vidbyte/sources/cache/`

Caching backends for fetched artifacts — `memory.py`, `file.py`, and `null.py` over `base.py` — so repeated loads do not repeatedly hit the network. `null.py` exists to make "no caching" an explicit, testable choice rather than an absence. Cache keys derive from the fetch hash, not the URL.

##### `vidbyte/sources/fetches/`

The retrieval half of the source layer: `file.py` for local artifacts, `chained.py` for fallback chains, and `hash.py` for content addressing, over `base.py`. Separating fetch from parse is what lets the same `llms.txt` parser run against a URL, a local file, or a cached blob. Add a transport here, not in a loader.

##### `vidbyte/sources/llms_txt/`

The `llms.txt` format specifically: `parser.py` for the grammar, `types.py` for the parsed shapes, `loader.py` for assembly. `llms.txt` is the first artifact format the SDK supports end to end, and this folder is the reference implementation of a source format. Model a new format on it.

##### `vidbyte/sources/loaders/`

The top-level entry points callers actually use: `document.py` for generic documents and `llms_txt.py` for the format above. A loader composes a fetch, a cache, and a parser into one call that returns typed context items. This is the folder to read first when using the sources layer.

##### `vidbyte/sources/regex/`

Shared pattern definitions used across source parsing, factored out so the same expressions are not redeclared per format. Two files. Small, but it is what keeps parsing behavior consistent when a second artifact format arrives.

#### `vidbyte/tools/`

Tool contracts, the `@tool` decorator, agent-local catalogs, provider-native schema generation, execution, MCP bridges, and permissions — the largest domain layer at 125 files. A tool is a Python function plus a schema plus a permission; the SDK handles turning that into something a model can call and a result it can read. Permissions default to safe/read, with mutation and execution requiring explicit authorization.

##### `vidbyte/tools/builtins/`

The shipped tool library, 75 files: `calculator.py`, `code_execution.py`, `code_search/`, document retrieval, context manipulation, handoff, trajectory, reflexion, and memory-provider tools. These cover the capabilities most agents need, already schema-correct and permission-tagged. Check here before writing a custom tool.

##### `vidbyte/tools/filesystem/`

Filesystem tools as a dedicated family, 22 files — `append_text.py`, `checksum.py`, and siblings over `_base_tool.py` and `base.py`. They execute against the swappable backends defined in `lib/tools/filesystem/backends/`, so the same tool works on local disk or in a sandbox. This is the surface a coding agent spends most of its tool calls in.

##### `vidbyte/tools/mcp/`

The inbound MCP direction: attaching third-party MCP servers to an agent as tools. `client.py` and `bridge.py` do the translation, `attach.py` is the entry point, and `presets.py` provides searchable preset servers with their required-environment metadata. The outbound direction — exposing this SDK as a server — is `vidbyte/mcp_server/`.

##### `vidbyte/tools/security/`

The authorization boundary for tool execution: `permissions.py` defines the policy model and `sandbox.py` defines the sandbox transport contract. This is what makes "safe by default, mutation on explicit grant" mechanical rather than advisory. Any tool that writes, deletes, or executes passes through here.

##### `vidbyte/tools/toolsets/`

Named bundles of tools that ship together for a given use case, so a caller can attach a coherent set in one call. Currently `paradigm_minimal.py`, the toolset the minimal-fanout paradigm needs. Add a toolset when a combination of tools is repeatedly assembled by hand.

#### `vidbyte/trace/`

The tracing facade and the continual-trace artifact system. Beyond conventional spans, the SDK maintains a continually updated, schema-validated trace artifact that stays *separate from the main agent context* unless compaction middleware explicitly folds it back in — which is what lets a long run stay inspectable without the trace itself consuming the window. Start in `continual/` if you are trying to reconstruct what an agent actually did.

##### `vidbyte/trace/components/`

Per-subsystem trace emitters — `agents.py`, `algorithms.py`, `context.py`, `middleware.py` — so each layer records its own lifecycle in a consistent shape. Splitting by component is what makes a trace filterable by subsystem after the fact. Add an emitter here when a new layer needs visibility.

##### `vidbyte/trace/continual/`

The continual trace artifact itself: `agent.py` (the tracing agent), `middleware.py` (the hook that keeps it current), `prebuilt.py` (ready-made configurations), over `base.py`. This is the mechanism behind schema-validated, continually updated trace artifacts. Read this before wiring trace-backed compaction.

##### `vidbyte/trace/providers/`

In-package tracer implementations: `generic.py`, `langsmith.py`, and the in-memory debug tracer, over `base.py`. Distinct from `vidbyte/providers/tracing/`, which holds the external platform adapters — this folder is the SDK's own tracers, that one is the export path. The debug tracer is what tests and local development use.

#### `vidbyte/workflows/`

Typed state graphs with validate-before-commit stages, conditional branches, cycles, guards, retries, declared jumps, and execution records. A workflow is deterministic control flow with typed state, as opposed to a pipeline's string-in/string-out composition or an agent's model-driven loop. Reach for it when the sequence is known in advance and the requirement is that invalid state cannot advance.
