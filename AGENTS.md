# Vidbyte SDK

Vidbyte is an agent engineering platform for building, evaluating, instrumenting, and distributing AI workflows. The Vidbyte SDK is the Python package surface for that platform: composable agents, tools, middleware, context management, MCP server integration, prompts, evals, provider adapters, pipelines, validated workflows, durable sessions, artifact sources, and tracing primitives — all reachable from a single `vidbyte` import. The design intent is that a developer builds the agent *itself* — the loop, the tool execution, the context window, the trace artifact, the runtime policy, the multi-agent composition — rather than calling a hosted black box.

The mental model is small and consistent. You create an `Agent` or `BaseAgent`, give it a system prompt plus optional model/provider config, runner, tools, context manager, middleware, trace settings, and runtime choice, then call `run()` or `arun()`. The SDK assembles the message context, appends an agentic-loop prompt, sends tool schemas to the model, executes permitted tool calls, folds results back into ordered history, applies middleware and context-window policy, and repeats until the model signals completion. Everything larger than a single agent — pipelines, paradigms, sessions, MCP exposure — is composition over that same primitive core. This repository is deliberately scoped to reusable, developer-facing abstractions: private Vidbyte service logic, proprietary learning systems, hosted scoring, and database-of-record access stay outside the package. Status is **alpha**, so APIs may change between minor versions.

> **This file is a Map.** It is a lossy compression of what this repository already contains in full — folder topology and what each folder is for, nothing that isn't derivable from the tree itself. It exists to answer *where do I look next*, not to be correct in every detail. It is expected to drift; regenerate it rather than patching it. For a deeper structural index, read [`artifacts/file_index.md`](artifacts/file_index.md); for the code-heavy documentation bundle, read [`llms.txt`](llms.txt).

## File Index

**Root files:** `README.md` — the Layer Guide table is the authority on what each `vidbyte/` subpackage is for. `llms.txt` — the full agent-readable documentation bundle, code-heavy where this Map is code-free. `pyproject.toml` — packaging, the `[dev]` extra, and dependency pins. `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE`, `.gitignore`.

### `.github/`

GitHub-hosted repository configuration that governs contribution and automation, entirely separate from the installable package itself. It holds the structured intake contributors fill in when reporting a problem or proposing a feature, alongside the automated checks that run against every proposed change and the process that publishes new releases. None of it ships to end users; it only shapes how the repository is used, reviewed, and verified on GitHub. Because these checks run on every change with no exceptions, altering this configuration changes what every contribution is measured against.

#### `.github/ISSUE_TEMPLATE/`

Structured forms that contributors fill in when opening a bug report or requesting a feature, rather than starting from a blank text box. They exist so incoming reports arrive with the reproduction detail and environment context that triage actually needs. This is a presentation concern specific to how the repository is used on GitHub, with no bearing on how the package itself behaves at runtime. It is a small, rarely-changed corner of the repository, useful mainly as a reminder that intake quality is a deliberate choice rather than an accident.

#### `.github/workflows/`

The automated checks and release process that run in hosted infrastructure rather than on a contributor's own machine. Every proposed change is verified across multiple versions of the language runtime, checked against a separate static-analysis policy layer, and, on release, published to the public package index. None of these checks are scoped to particular paths, so even a documentation-only change exercises the full verification and policy surface. This is the authoritative definition of what "passing" means for the repository, and it is worth reading before assuming a local check alone is sufficient.

### `.semgrep/`

A custom static-analysis policy layer enforced during automated verification, distinct from ordinary linting. It currently encodes a single architectural boundary: a rule preventing loosely-typed data from crossing between layers where a properly typed structure is required instead. The intent is to make an architectural constraint mechanically enforced rather than something reviewers have to remember and catch by eye during review. Anyone introducing a new layer boundary in the package should consider whether it deserves the same treatment.

### `artifacts/`

Generated, code-free reference material that describes the repository rather than implementing anything in it. It holds a long-form structural map of the entire tree, serving as a deeper and more detailed companion to this file for situations where a short topology summary is not enough. Because it describes derived facts about the tree, it is expected to be regenerated as the repository changes rather than hand-edited over time. Anyone maintaining this folder should keep its content mechanically re-derivable from the tree rather than letting it drift into an independently authored document.

### `docs/`

Design documentation for the package, and by volume the largest documentation surface in the repository. Every non-trivial change lands a design document before implementation begins, which makes this folder the decision history for the whole package rather than an afterthought. It is substantially larger than the automated test suite, which is a fair reflection of how deliberately this repository is built — decisions are argued for in writing before they are coded. Reading here first is usually faster than reverse-engineering intent from the implementation alone.

#### `docs/design/`

One design document per feature, each walking through the problem being solved, the approach chosen, the alternatives that were considered and rejected, and why. This is the first place to look when a public interface's shape seems arbitrary, since the reasoning behind it is recorded here rather than scattered across code comments. Documents are organized so the rationale behind any given subsystem can be found without first reading its implementation. Consulting this folder before proposing a change to an existing interface avoids relitigating a decision that was already made deliberately.

### `scripts/`

The project's local verification entry points, kept outside the installable package so none of them ship to end users. The primary one reproduces the full gate that automated checks run remotely, so a contributor can catch a failure before it ever reaches review. Alongside it sit many smaller, narrowly scoped verification scripts, each written next to the design document for the behavior it proves and useful for fast iteration on one subsystem at a time. One script also enforces a structural rule about where a particular kind of shared state may be written, keeping that invariant mechanical rather than advisory. None of the narrow scripts substitutes for running the full local gate before treating a change as complete.

### `skills/`

Reusable guidance distributed alongside the package that an agent or developer loads to work with the SDK correctly. This is repository-level source material rather than importable code, and it exists to shorten the gap between reading the package and using it correctly on the first attempt. It shares its name with a much smaller, package-internal folder deeper in the tree that holds runtime machinery rather than instructional content, and the two are easy to confuse despite serving entirely different purposes. Consistent with how this Map treats skill libraries generally, its contents are not enumerated further here.

### `tests/`

The automated test suite, organized as one collection per subsystem rather than mirroring the package's own folder structure. A shared layer of fakes and fixtures — stub model providers, recording tracers, deterministic runners — lets agent behavior be asserted without making real network calls. Coverage spans agent abstractions, execution strategies, middleware, context management, tools, evaluation, sessions, external sources, configuration validation, and the command-line interface. This suite is the primary stage of the local verification gate, so a change that cannot pass it is not considered ready.

#### `tests/multi_agent/`

Tests specifically for compositions that involve more than one agent at once — pipelines, handoffs, and topologies where several participants share a single logical run. It is split out from the rest of the suite because these scenarios need shared, multi-participant fixtures and different timing assumptions than a single agent under test. It is a small collection, but it is load-bearing: it is the only place multi-agent composition is exercised end to end. A regression here tends to indicate a problem in how participants coordinate rather than in any one agent's own logic.

### `vidbyte/`

The installable package itself — everything inside it ships to users, and nothing outside it is importable. It is organized in layers: a shared substrate underneath, a set of user-facing domains built on top of that substrate, and a smaller set of composition layers built on top of those domains for assembling larger systems out of the primitives beneath them. This layering is treated as an invariant rather than a convention — code in a lower layer must never depend on a domain or composition layer above it. Understanding which layer a piece of functionality lives in is the fastest way to predict how a change to it will ripple outward.

#### `vidbyte/agents/`

Executable agent actors and the logic that selects how they run — the primitive that most of the rest of the package composes over, and the natural place to start reading the codebase. An agent here owns the full agentic loop: assembling context for the model, making the call, executing whatever tools the model is permitted to use, folding the results back into history, applying any configured middleware, and repeating until the model signals it is done. Both synchronous and asynchronous execution are supported, along with handing a run off between agents and keeping a registry of known agents by name. Everything built on top of this layer — pipelines, paradigms, multi-agent compositions — ultimately calls back into this loop.

##### `vidbyte/agents/algorithms/`

Reusable multi-agent reasoning strategies packaged as ready-to-use agent behaviors rather than one-off scripts. Each strategy is an opinionated composition of existing agent primitives — critique-and-revise cycles, independent critique, adversarial multi-role evaluation, and grading across several model providers are among the patterns covered. None of these introduce a new primitive; they combine what already exists into a named, reusable shape. This is the folder to check before hand-wiring a custom critic or review loop from scratch.

##### `vidbyte/agents/contracts/`

The invariants an agent's configuration must satisfy before it is allowed to run. This spans both the shape a structured output must conform to and the minimum acceptable settings below which a configuration is considered actively misconfigured rather than merely unusual. The folder is small, but its effect is outsized: it turns a bad configuration into an error raised at construction time instead of a confusing failure partway through a run. Anyone adding a new class of agent configuration should consider whether it needs a floor defined here.

##### `vidbyte/agents/multi/`

Multi-agent machinery that sits below the pipeline layer, providing the aggregate-agent behavior, dispatch, and cleanup handling that let several agents participate in a single logical run. Cleanup in particular guarantees that resources are released even when one participant in a shared run fails partway through. This folder is for shared-run semantics specifically — coordinating participants that belong to one run — rather than for defining the shape of a multi-stage topology, which is a separate concern handled elsewhere. Reach here when several agents must share failure and resource semantics, not merely execute in some sequence.

##### `vidbyte/agents/pricing/`

Per-provider token and cost accounting, with one implementation per model vendor built over a shared base contract. It normalizes each provider's raw usage reporting into consistent token counts and dollar costs, so an agent can report its usage and cost regardless of which underlying model actually ran. This normalization is what makes budget-aware middleware and any kind of spend tracking upstream possible at all. Without it, cost accounting would need to be reimplemented per provider everywhere it is needed.

##### `vidbyte/agents/runtimes/`

The execution strategies an agent can run under, beyond the default linear loop. This includes an actor-model runtime supporting point-to-point and broadcast messaging across both static and dynamic topologies, as well as search-based strategies for exploring multiple possible action sequences before committing to one. Choosing a runtime changes how an agent explores its space of possible actions, not what tools or capabilities it has available. This is the layer to extend when a new way of driving an agent's control flow is needed, rather than a new capability for it to use.

##### `vidbyte/agents/settings/`

The tunable knobs of an agent run, deliberately factored out of the agent class itself rather than buried in constructor arguments. This covers iteration limits and termination conditions, tool execution and failure policy, and what happens when the primary model becomes unavailable. Keeping these as explicit, structured settings objects is what makes an agent's behavior inspectable and serializable rather than implicit in code. A new configurable behavior for agents should be added as a setting here rather than as another constructor parameter.

#### `vidbyte/cli/`

The package's own developer-facing command-line surface, deliberately minimal and currently limited to a single small area of functionality. This is not the separate product command-line tool that end users interact with to run research against the backend — that lives entirely outside this repository. This one exposes only local, SDK-specific developer utilities, and it is not intended to grow into a general-purpose interface. Anyone looking for the product's user-facing command-line tool should look elsewhere in the wider workspace.

#### `vidbyte/config/`

Safe parsing of declarative configuration into either full agent settings — with nested tools and middleware — or a harness specification, plus construction of a working, runnable agent from that configuration alone. This is the declarative half of the SDK: an agent can be described entirely in configuration and get a real, executable object back, with every reference resolved against the SDK's own internal registries rather than requiring the caller to supply components directly. This is what makes it possible to define an agent without writing any code at all. Understanding this folder is worthwhile before adding any new configurable field to an agent.

#### `vidbyte/context/`

Structured context items, context windows, compaction behavior, and handoff models — everything concerned with what the underlying model actually sees during a run. Context is modeled as typed, structured items rather than raw strings specifically so that budgeting, pruning, and permissions around it can be reasoned about mechanically instead of by convention. This is consistently the most common source of surprising agent behavior in practice, which makes it worth understanding early rather than treating as an implementation detail. A change here has a way of rippling into behavior that looks unrelated on the surface.

##### `vidbyte/context/algorithms/`

Named, swappable strategies that decide what survives when a context window fills up, rather than leaving that decision to an implicit heuristic buried in code. Several independent strategies are provided side by side so that the eviction or summarization policy for a given agent is a deliberate, visible choice. These strategies are meant to be paired with a middleware component that applies one automatically during a live run, rather than invoked directly. Adding a new eviction strategy belongs here rather than as a one-off change to how context is trimmed elsewhere.

##### `vidbyte/context/handoff/`

Models for transferring context from one agent to another when work moves between participants. Several domain-shaped variants exist over a shared base, ranging from a minimal handoff that carries the least context that still works to richer variants suited to specific kinds of work. A handoff is fundamentally a lossy compression decision, and this folder is where those decisions are made explicit and named rather than left to whatever happens to be in the prompt at handoff time. It is meant to be paired with corresponding tools that let an agent trigger a handoff itself during a run.

##### `vidbyte/context/primitives/`

The composable low-level building blocks that make up a context window, assembled together by the higher-level context manager. These are the pieces a tool or a middleware component touches directly when it needs to read or safely modify context during a run. Keeping them as small, well-defined primitives rather than one large structure is what makes safe, partial modification of context possible at all. A binding contract governs how these primitives may be touched, and a separate mechanism enforces that contract structurally rather than leaving it to convention.

##### `vidbyte/context/templates/`

Prebuilt context-window shapes for common agent patterns, so a caller can select an existing template rather than assembling primitives from scratch every time. It currently holds one such template, oriented around capturing a run's context for later replay or inspection. This is a small folder, but it functions as the ergonomic front door to the lower-level primitives layer beneath it. New common patterns belong here once they have proven themselves as hand-assembled combinations of primitives elsewhere.

#### `vidbyte/evals/`

Local evaluation infrastructure: defining a single evaluation case, grouping cases into a suite, running them concurrently, summarizing results, and keeping a durable local registry of runs for comparison over time. Everything here runs locally with no hosted scoring service involved, by deliberate design choice. This is the mechanism by which a change to an agent is demonstrated to be an improvement with evidence, rather than merely asserted to be one. Any nontrivial change to agent behavior should be accompanied by evidence produced through this layer.

##### `vidbyte/evals/behavior/`

Graders that score how an agent worked during a run rather than only what it ultimately returned. This includes measuring iteration and token efficiency, whether a context handoff actually preserved what mattered, and other process-level qualities distinct from final output correctness. These catch a class of regression that output-only grading structurally cannot: an agent that reaches a correct answer only after many wasteful or redundant steps looks identical to an efficient one under output grading alone. They are meant to be used alongside output graders rather than as a replacement for them.

##### `vidbyte/evals/graders/`

The output graders themselves, spanning a wide range from cheap deterministic checks to model-driven judgment, including exact and pattern matching, structural validation, language-model-based judging, grading across multiple providers for robustness, and weighted combinations of several signals into one score. A shared mechanism exists for combining several graders into a single composite judgment. The intended discipline is to start with the cheapest grader capable of distinguishing pass from fail, and reach for model-driven judgment only when cheaper checks cannot make that distinction. Every grader in this folder implements the same interface, so swapping one for another is a configuration change rather than a rewrite.

##### `vidbyte/evals/templates/`

Reusable, prepackaged evaluation suites that can be pointed at an agent without authoring cases from scratch. A registry makes these bundles discoverable by name, and a shared contract defines what every template must satisfy to qualify as one. These exist to give a new agent or a new behavior a baseline of coverage immediately, before anyone has written a single domain-specific case for it. Reach here first when starting evaluation work on something new.

#### `vidbyte/harnesses/`

The base abstraction for wrapping an existing agent workflow so that every run produces a durable, structured record suitable for use as reinforcement-learning training data — the task given, the full trajectory taken, the resolved configuration used, and a scalar reward. Configuration is treated as the source of truth for a harness's identity, and every run is captured through the session layer rather than through ad hoc logging. Consent and redaction are part of the contract rather than an afterthought bolted on separately. This is the shared contract that executed harnesses elsewhere in the workspace, and example harnesses built for demonstration, both build against.

##### `vidbyte/harnesses/stores/`

Persistence backends for captured trajectory data, all implementing one common interface so the storage mechanism can be swapped without touching the harness itself. One backend is intended for use in tests, another for local export to disk, and additional backends can be added following the same pattern. Keeping the store swappable behind one interface is what lets a harness behave identically whether it is run in a notebook or in production. A new storage destination should be added as a backend here rather than taught to the harness abstraction directly.

#### `vidbyte/lib/`

The shared substrate that every other layer of the package depends on, and which is not permitted to depend back on any of them. It provides the foundational data structures, enumerated value sets, the exception hierarchy, configuration loading, execution runners, name-based registries, persistence providers, and the low-level contracts for tools, HTTP, and tracing that higher layers build on. The one-directional dependency rule — nothing here may import from a domain layer above it — is treated as an invariant rather than a convention, and is what keeps the package's layering meaningful rather than aspirational. Anything genuinely foundational and used across multiple domains belongs here rather than duplicated in each domain that needs it.

##### `vidbyte/lib/agents/`

Agent-support utilities that must live below the main agent layer specifically to avoid a circular dependency between them. This includes logic for routing a request to the right modality — text, image, video, audio, or embedding — based on the model involved, along with a small amount of supporting logic for one of the multi-role evaluation strategies. It is intentionally small and slightly awkward by nature: it exists as the overflow valve for logic the agent layer needs but the shared substrate must own for dependency reasons. Anything that can legitimately live in the agent layer instead should be moved there rather than added here.

##### `vidbyte/lib/config/`

Configuration loading and resolution that sits beneath the higher-level declarative configuration layer above it. It reads and merges configuration from multiple sources, defines the underlying shapes and defaults those sources populate, and holds the built-in presets for external server integrations along with the environment metadata each preset requires. This is the layer that answers the question of what the effective value of any given setting actually is, once every source has been merged together. Anything about how configuration is combined or defaulted belongs here rather than in the layer that consumes the result.

##### `vidbyte/lib/configs/`

Narrow, single-purpose configuration objects that do not belong in the general-purpose configuration loader. It currently holds one such object, describing how a model's structured output is requested and subsequently validated. These are kept separate from the general loader because they represent per-feature contracts rather than settings a user is expected to edit directly. A new narrow, feature-specific configuration shape belongs here rather than folded into the general-purpose loader.

##### `vidbyte/lib/constants/`

Values declared exactly once because more than one part of the package needs to refer to the same thing. It currently holds shared runner identifiers and their defaults, referenced both by the low-level execution layer and by the agent layer that selects among them. The guiding rule for this folder is simple: if a literal value would otherwise need to appear in two places, it belongs here instead. This keeps values that must stay synchronized from silently drifting apart over time.

##### `vidbyte/lib/dataclasses/`

The typed vocabulary shared across the entire package, and its largest single folder by file count. It defines the shapes used to describe agents themselves, along with the structures for context, tools, runs, usage, and results that cross between layers. These are exactly the types the package's static-analysis policy exists to protect, since they are what is meant to flow across layer boundaries instead of loosely-typed alternatives. Adding a new typed shape here before passing an untyped structure between layers is the expected discipline.

##### `vidbyte/lib/enums/`

Closed sets of values used consistently across multiple layers of the package, covering things like execution runtime choice, model modality, and other configuration dimensions. Representing these as enumerations rather than free-form strings is what makes an invalid state structurally unrepresentable, and lets registries key lookups on something checkable rather than an arbitrary string. Extending an existing enumeration is treated as an interface change with its own weight, since code elsewhere may be matching against it exhaustively. Anywhere a value is drawn from a small, closed set, it belongs here rather than as a plain string.

##### `vidbyte/lib/errors/`

The package's exception hierarchy, rooted in a single common base so every failure the package can raise ultimately descends from one ancestor. This lets a caller catch every SDK-originated error as one class, without also catching unrelated errors that happen to share a built-in exception type. The hierarchy is kept deliberately shallow and small on purpose — the discipline enforced here is a small number of well-named error types with informative messages, not a dedicated class for every possible failure mode. A new failure mode should usually reuse an existing error type with a clear message rather than growing the hierarchy.

##### `vidbyte/lib/http/`

The low-level HTTP substrate used for making outbound requests and reading their responses, supporting both synchronous and asynchronous call styles. Provider adapters and integrations with external protocol clients both build on top of this layer rather than reaching for a general-purpose HTTP client library directly. Centralizing this is what lets retry behavior, timeouts, and streaming be decided in exactly one place instead of reimplemented per integration. Nothing else in the package should reach for an HTTP client directly outside of this layer.

##### `vidbyte/lib/models/`

A namespace reserved for model metadata that currently holds no real content. It is listed here specifically so that its emptiness is a documented, known fact rather than something a reader has to go looking for and wonder if they are missing. Model discovery and configuration actually live in a registries layer elsewhere in the shared substrate today. This folder exists as a placeholder for where that responsibility may eventually move.

##### `vidbyte/lib/providers/`

Persistence providers behind a single common interface, covering a small number of different underlying database backends. These back the evaluation run registry, session storage, and anything else in the package that needs durable local state. There is a naming collision worth being careful about: this folder is about database providers specifically, while a similarly-named folder elsewhere in the package is about model providers instead, and the two are unrelated. Confusing the two is a common and easy mistake to make when navigating the package for the first time.

##### `vidbyte/lib/registries/`

Name-to-implementation lookup for everything the package needs to resolve dynamically by string — agents, execution strategies, and other pluggable components. Registries are what let a declarative configuration name a component by string and receive back a real, working object, which is also what makes it possible to construct an agent from configuration alone without the caller supplying components directly. The general pattern followed throughout is to register an implementation at import time and resolve it later at construction time. A new pluggable component type should generally get its own registry following this same pattern.

##### `vidbyte/lib/runners/`

The layer that actually issues a call to a model for a given modality, with one implementation per supported modality sitting over a shared base contract. A runner owns the request and response shape for exactly one modality, and an agent selects the appropriate one automatically based on shared constants and modality-detection logic elsewhere in the shared substrate. Supporting a new modality means adding a new runner here, rather than adding conditional branching inside the agent itself. This keeps modality-specific request handling isolated from the agent's own control flow.

##### `vidbyte/lib/templates/`

The shared substrate underneath both the multi-agent reasoning algorithms and the evaluation template layers described elsewhere in the package. It exists specifically so those two higher layers can share a common definition of certain reasoning strategies rather than each maintaining its own separate copy. A change made here is felt in both of the layers that depend on it, which is exactly the point of factoring the logic out to begin with. This is the folder to change when a reasoning strategy used in more than one place needs to change everywhere at once.

##### `vidbyte/lib/tools/`

Low-level tool contracts that must sit below the package's user-facing tools layer, chiefly an abstraction over different filesystem backends a tool can execute against. Separating the backend from the tool itself is what allows the same filesystem-facing tools to run unmodified against a local disk or a sandboxed remote environment, without the tool needing to know which one it is actually talking to. A new backend belongs here; a new user-facing tool belongs in the higher layer instead. This split is what keeps tool behavior portable across very different execution environments.

##### `vidbyte/lib/tracing/`

The tracing contract that both the package's own in-process tracing facade and its external provider adapters implement. Keeping this interface defined in the shared substrate is what lets middleware and execution runners emit tracing spans without needing to import any specific tracing implementation directly. It is a very small folder, but it effectively defines the shape of all observability across the entire package. Any new tracing backend, internal or external, is expected to satisfy this same contract.

#### `vidbyte/mcp_server/`

A server exposing the package's agents, tools, prompts, strategies, and pipelines to any compatible external host over a standard protocol. This is the outbound direction of that protocol — the package acting as a server that something else connects to — as distinct from the inbound direction of attaching third-party servers to one of this package's own agents, which is a separate concern handled elsewhere. Keeping the two directions straight is essential when debugging a problem that looks like a protocol issue. This folder should be the first place to look when the package itself needs to expose something to an external agent host.

##### `vidbyte/mcp_server/server/`

The protocol implementation itself: a core request-handling loop plus one handler per supported method, each responsible for translating an incoming protocol request into an internal call and translating the result back into a protocol-safe response. Adding a new capability to the server means adding a new handler following this pattern, rather than adding a new conditional branch to the core loop. This separation is what keeps the core loop simple as the set of supported methods grows over time. It is the layer to read when trying to understand exactly what the server does with an incoming request.

#### `vidbyte/middleware/`

Deterministic hooks that run around a full run, around individual iterations, around model calls, around tool calls, around errors, and around completion. This is deliberately where policy lives — behavior that must happen regardless of what the underlying model decides to do — which is exactly why it is implemented as deterministic code rather than expressed as an instruction to the model. Application-defined authorization and policy logic plug into the same interface used by everything built into the package, so custom policy is never a second-class citizen. This is the layer to reach for whenever behavior needs to be guaranteed rather than merely requested.

##### `vidbyte/middleware/builtins/`

The shipped set of policy middleware available out of the box, covering a wide range of concerns: audit logging, retry handling around transient failures, enforcing token and runtime budget limits, detecting unproductive repetition, enforcing tool-use policy, and a set of security-focused safeguards against certain classes of prompt manipulation. These represent the guardrails available for free without writing any custom middleware. Reading through this folder before writing new custom middleware is worthwhile, since the needed behavior may already exist here in some form. Each one plugs into the same general middleware interface described in the parent folder.

##### `vidbyte/middleware/compaction/`

Middleware that applies context-window policy continuously during a live run, rather than only after the fact once a run has already completed. Several strategies are available and selectable — trimming by message history, by individual tool results, by summarization, by selective pruning, by relevance or salience, or driven by trace data — and a single entry point applies whichever strategy is configured. This is the bridge that connects the standalone context-window algorithms elsewhere in the package to an actual live agent run. Configuring compaction here is what makes a chosen eviction strategy actually take effect during execution rather than remaining a strategy that is merely defined but never applied.

#### `vidbyte/paradigms/`

Thin, fully runnable end-to-end control flows assembled out of agents, tools, context, prompts, middleware, tracing, pipelines, and evaluation all together. A paradigm is an opinionated but entirely optional composition of the package's primitives — effectively the package's answer to a request for a working system to look at, rather than only a set of primitives to assemble one from scratch. Each one is self-contained enough to actually run on its own and small enough to read in full in one sitting. This is the folder to look at for a complete worked example rather than a piece of one.

##### `vidbyte/paradigms/context_minimal_fanout/`

The one paradigm currently shipped: a minimal-context fan-out shape, where a coordinator dispatches narrowly scoped subtasks to a set of worker agents that each receive only the minimum context needed to complete their piece, after which the coordinator folds the individual results back together. It carries its own dedicated prompt material alongside the control flow itself, since the prompts needed for this shape are specific to it. This pattern is chiefly useful when the cost of context given to each worker dominates the overall cost of the run. It is a good reference to read before hand-building a similar fan-out shape from lower-level primitives.

#### `vidbyte/pipelines/`

Multi-agent pipeline topologies that all share a simple string-in, string-out contract at the boundary between stages: sequential, parallel, conditional, and map-reduce shapes are all supported. Stages nest inside one another, and each individual stage's agent retains its own tools, middleware, context, and history rather than having them flattened together across the whole pipeline. This folder is for defining the topology — the shape of how stages relate to one another — as distinct from a separate area of the package meant for participants that need to share run-level semantics like resource cleanup. Reach here when the problem is naturally expressed as a sequence or composition of stages.

#### `vidbyte/prompts/`

A repository-backed prompt library: prompt content stored as versioned assets, looked up through an enumerated key rather than a filesystem path, imported directly where needed, and organized into families by the subsystem that uses them. Storing prompts as separate versioned assets rather than inline strings is what makes them diffable, reviewable, and reusable across multiple agents rather than duplicated per call site. The enumerated lookup is specifically what lets a prompt be referenced from declarative configuration without needing to know anything about where it physically lives. Any new prompt should be added as an asset here and exposed through the lookup, not written inline at its point of use.

##### `vidbyte/prompts/prompts/`

The prompt assets themselves, organized into families grouped by the specific subsystem each family of prompts supports. Each family bundles together every prompt a given subsystem needs, generally alongside a small manifest describing the family. This organization is what keeps prompt content for a given subsystem discoverable as a group rather than scattered across the codebase near wherever it happens to be used. Adding a new prompt means adding a new asset within the appropriate family and exposing it through the lookup layer above, rather than inlining it at a call site.

##### `vidbyte/prompts/skills/`

Skill documents shipped specifically as prompt assets — instruction sets meant to be handed to an agent at runtime as part of its prompt material. These are distributed through the prompt layer rather than through the repository-level skills folder, which serves a different purpose and audience. This folder is also distinct from a similarly-named folder deeper in the package that holds runtime machinery rather than content, and the distinction between all three similarly-named locations is worth being deliberate about before adding to any of them. Anyone adding a new skill document should first decide which of these surfaces is actually the right one.

#### `vidbyte/providers/`

Provider adapter factories covering text, image, video, audio, embeddings, and streaming — the layer that turns a request to call a particular model into a concrete call against that vendor's actual API. Adapters normalize request and response shapes across vendors, which is what lets an agent switch which underlying model or vendor it uses without any change to the agent's own code. Model discovery and configuration for a given vendor are handled by a separate registry layer alongside this one rather than duplicated here. This is the folder to extend when adding support for a new model vendor.

##### `vidbyte/providers/tracing/`

Adapters that ship the package's traces out to external observability platforms, each implementing the same shared tracing contract defined in the shared substrate. Because every adapter implements the same contract, enabling a given observability platform is a configuration choice rather than a code change. This folder is specifically about exporting traces to external platforms, which is a different concern from a similarly-named folder elsewhere in the package that holds the SDK's own internal tracer implementations rather than external export adapters. Confusing the two is an easy mistake given how similar their names are.

#### `vidbyte/sessions/`

Durable, checkpoint-based persistence for long-running work: sessions that can checkpoint, resume, fork, batch-fork, be tagged, be exported and re-imported, and roll usage up across an extended piece of work. A session is modeled as a directed graph rather than a single linear log, which is specifically what makes forking a session and comparing alternative continuations against one another possible. This is the layer that the harness abstraction elsewhere in the package builds on to actually capture a trajectory during a run. Anything requiring resumable, long-running, branchable state belongs on top of this layer rather than reimplemented independently.

##### `vidbyte/sessions/stores/`

Storage backends for session state, sitting behind one common interface so the backend can be swapped without touching session semantics themselves. This follows the identical pattern used for trajectory storage elsewhere in the package: an in-memory backend for use in tests, a file-based backend for local use, and the option to add a database-backed store later following the same interface. Swapping the backend changes only where data physically lives, never how a session behaves. A new durable backend belongs here rather than taught to the session abstraction directly.

#### `vidbyte/shared/`

A reserved namespace intended for genuinely cross-cutting shared code, currently holding no stable public symbols. It is listed here explicitly so that its emptiness is a documented, deliberate fact rather than a gap that looks like missing work. The reason it stays empty is that most code that might seem like a natural fit for a generic shared folder actually belongs in the shared substrate layer instead, which already serves that role. Adding real content here should not happen without first writing a design document explaining why the substrate layer is not the right place instead.

#### `vidbyte/skills/`

Package-internal, importable code that lets an agent load and make use of a skill document at runtime as part of its own execution. This is intentionally small, and it is easily confused with two other similarly-named locations elsewhere in the package and repository — one holding the distributed skill source content itself, and another holding skill documents packaged specifically as prompt assets. This folder is the machinery that loads and applies a skill; the other two are the content that gets loaded. Keeping the distinction clear matters because all three share a name that invites confusion.

#### `vidbyte/sources/`

The artifact-to-context layer: loaders that turn some external public artifact into a typed structure an agent can directly reason about as part of its context. The first fully supported path takes a documentation site's structured text manifest and turns it into typed context items; turning an API specification directly into callable tools is planned as a future addition to this layer. This is the mechanism by which external documentation enters an agent's context without needing a bespoke, one-off scraper written for every different site or source. New artifact formats are expected to be added here as this layer grows over time.

##### `vidbyte/sources/cache/`

Caching backends for artifacts that have already been fetched, sitting behind a shared interface so a repeated load of the same artifact does not repeatedly hit the network unnecessarily. One backend deliberately implements no caching at all, which exists to make "no caching" an explicit, intentional, and testable choice rather than simply the absence of one. Cache keys are derived from a hash of the fetched content itself rather than from the location it was fetched from, so identical content is recognized as identical regardless of where it came from. A new caching strategy belongs here behind the same shared interface.

##### `vidbyte/sources/fetches/`

The retrieval half of the source layer, separate from parsing: fetching a local artifact directly, falling back through a chain of alternative fetch strategies when the first one fails, and addressing content by a hash of what was actually retrieved. Keeping fetching separate from parsing is what lets the same parser for a given format run identically against a remote location, a local file, or something already sitting in cache. A new way of retrieving an artifact belongs here as a new fetch strategy, not folded into a parser. This separation is part of what keeps adding a new artifact format to this layer manageable.

##### `vidbyte/sources/llms_txt/`

The reference implementation of one specific documentation artifact format supported by the source layer, including the grammar for parsing it, the types the parsed result takes, and the logic that assembles those pieces into a final loaded result. This format is the first one the package supports completely end to end, and this folder is meant to be used as the template when modeling support for a new format. Reading through this implementation is the fastest way to understand what supporting a brand-new source format actually requires. Anyone adding a second format should structure it the same way this one is structured.

##### `vidbyte/sources/loaders/`

The top-level entry points that callers actually use directly: one for loading a generic document, and one specifically for the documentation-manifest format described elsewhere in this layer. A loader is what composes a fetch strategy, a cache, and a parser together into a single call that returns typed context items ready to hand to an agent. This is the folder to read first when actually using the source layer, rather than any of the lower-level pieces it is built from. Most callers should only ever need to interact with this folder directly.

##### `vidbyte/sources/regex/`

Shared pattern definitions used across more than one source-parsing implementation, factored out specifically so the same expressions are not redeclared separately in every format that happens to need them. It is a very small folder. Its value is really about consistency rather than size — it is what keeps parsing behavior aligned across formats as a second and third artifact format are eventually added. A pattern needed by more than one parser belongs here rather than duplicated per format.

#### `vidbyte/tools/`

Tool contracts, the decorator used to define one, agent-local tool catalogs, automatic generation of vendor-native tool schemas, execution, bridges to external tool-serving protocols, and permissions — the largest single domain layer in the package by file count. A tool is conceptually a function paired with a schema and a permission, and this layer is responsible for turning that combination into something a model can actually call and a result the model can read back. Permissions default to the safest possible setting, with anything that mutates state or executes code requiring an explicit, deliberate grant of authorization. This is the layer to understand before writing any new tool, custom or otherwise.

##### `vidbyte/tools/builtins/`

The shipped tool library available out of the box, covering calculation, code execution, code search, document retrieval, direct context manipulation, handoff and trajectory-related actions, and integration with external memory providers. These cover the great majority of capabilities most agents actually need, and they arrive already schema-correct and already tagged with the appropriate permission level. Checking here before writing a new custom tool is worthwhile, since an equivalent capability likely already exists. This is, by file count, one of the largest folders in the entire package.

##### `vidbyte/tools/filesystem/`

Filesystem-facing tools organized as their own dedicated family, all built over a small set of shared base contracts. They execute against the swappable filesystem backends defined in the shared substrate layer, which is what lets the exact same tool run unmodified against a local disk or inside a sandboxed remote environment. This is, in practice, the surface where a coding-oriented agent spends the large majority of its tool calls. A new filesystem operation belongs here, built against the existing shared base contracts rather than reimplemented independently.

##### `vidbyte/tools/mcp/`

The inbound direction of a standard external tool-serving protocol: attaching a third-party server implementing that protocol to one of this package's own agents so its capabilities appear as ordinary tools. This includes the translation logic between the external protocol and the package's internal tool representation, a single entry point for actually attaching a server, and a set of searchable, preconfigured presets along with the environment metadata each one requires. The outbound direction — this package acting as a server that something else attaches to — is a separate concern handled elsewhere in the package. Keeping which direction is which straight matters when debugging a protocol-related issue.

##### `vidbyte/tools/security/`

The authorization boundary that all tool execution passes through: the policy model that defines what is and is not permitted, and the contract that any sandboxed execution transport must satisfy. This is what makes the package's safe-by-default, mutation-only-on-explicit-grant posture something mechanically enforced rather than merely a documented convention reviewers have to remember to check for. Any tool that writes data, deletes something, or executes code passes through this boundary before it is allowed to act. A new category of potentially unsafe tool behavior should be modeled here rather than checked ad hoc inside the tool itself.

##### `vidbyte/tools/toolsets/`

Named, pre-assembled bundles of tools that ship together for a particular use case, so a caller can attach a coherent, related set of capabilities in a single call rather than assembling them one at a time. It currently holds one such bundle, assembled for a specific paradigm shipped elsewhere in the package. A new toolset is worth adding whenever the same combination of individual tools keeps being assembled by hand across more than one place. This folder is about convenience and consistency rather than introducing any new tool capability itself.

#### `vidbyte/trace/`

The package's tracing facade, along with a continually-updated, schema-validated trace artifact system that goes beyond conventional point-in-time spans. This trace artifact is deliberately kept separate from an agent's main context throughout a run, unless a compaction middleware component explicitly folds relevant parts of it back in — which is what lets a very long run stay fully inspectable afterward without the trace itself ever consuming space in the model's context window during execution. This is the layer to start with when trying to reconstruct exactly what an agent actually did during a run after the fact. Understanding the distinction between ordinary spans and this continual trace artifact is important before extending either one.

##### `vidbyte/trace/components/`

Per-subsystem trace emitters, with each major layer of the package responsible for recording its own lifecycle events in a shape consistent with every other layer's emitter. Splitting emission out by component in this way is specifically what makes a captured trace filterable by subsystem after a run has completed. A new layer that needs its own visibility into a trace should get its own emitter here, following the same shape as the existing ones. This keeps trace output structured and consistent even as the number of instrumented subsystems grows.

##### `vidbyte/trace/continual/`

The continually-updated trace artifact itself, along with the agent responsible for maintaining it, the hook that keeps it current throughout a run, and a set of ready-made starting configurations for common cases. This is the concrete mechanism underlying the schema-validated, continually-updated trace artifacts described at the parent level of this folder. Reading through this folder is worthwhile before wiring up any trace-backed context compaction elsewhere in the package, since compaction that references the trace depends directly on how this mechanism behaves. It represents one of the more architecturally distinctive pieces of the tracing system as a whole.

##### `vidbyte/trace/providers/`

The package's own in-process tracer implementations, including a generic implementation, an implementation for one specific external observability platform, and an in-memory tracer meant for debugging. This is distinct from a similarly-named folder elsewhere in the package that holds adapters exporting traces to external platforms generally — this folder is the SDK's own tracers, while that one is the export path outward to other systems. The in-memory debug tracer specifically is what both the automated test suite and local development rely on day to day. The naming similarity between this folder and its counterpart is a common point of confusion worth being deliberate about.

#### `vidbyte/workflows/`

Typed state graphs with validate-before-commit stages, conditional branching, cycles, guard conditions, retry behavior, explicitly declared jumps between states, and a durable record of what happened during execution. A workflow represents deterministic control flow over typed state, in contrast to a pipeline's simpler string-in, string-out composition of stages or an agent's own model-driven, non-deterministic loop. This is the layer to reach for specifically when the overall sequence of steps is known in advance and the actual requirement is that an invalid state can never be allowed to advance. It sits at the opposite end of the spectrum from an agent's loop, trading flexibility for guaranteed structural correctness.
