# Vidbyte SDK

Vidbyte is an agent engineering platform for building, evaluating, instrumenting, and distributing AI workflows. The Vidbyte SDK is the Python package surface for that platform: composable agents, tools, middleware, context management, MCP server integration, prompts, evals, provider adapters, pipelines, validated workflows, durable sessions, artifact sources, and tracing primitives — all reachable from a single `vidbyte` import. The design intent is that a developer builds the agent *itself* — the loop, the tool execution, the context window, the trace artifact, the runtime policy, the multi-agent composition — rather than calling a hosted black box.

The mental model is small and consistent. You create an `Agent` or `BaseAgent`, give it a system prompt plus optional model/provider config, runner, tools, context manager, middleware, trace settings, and runtime choice, then call `run()` or `arun()`. The SDK assembles the message context, appends an agentic-loop prompt, sends tool schemas to the model, executes permitted tool calls, folds results back into ordered history, applies middleware and context-window policy, and repeats until the model signals completion. Everything larger than a single agent — pipelines, paradigms, sessions, MCP exposure — is composition over that same primitive core. This repository is deliberately scoped to reusable, developer-facing abstractions: private Vidbyte service logic, proprietary learning systems, hosted scoring, and database-of-record access stay outside the package. Status is **alpha**, so APIs may change between minor versions.

## Repository Map

The folder-by-folder map of this repository lives in [`REPO_MAP.md`](REPO_MAP.md), not in this file. It has two parts: the **File Index**, which covers every top-level folder and each subpackage of `vidbyte/` with what it is for and which way its dependencies may point, and **JEV File Locations**, a file-by-file table for `JevAgent` and the Jev decision model. Read it before you create a file, move code, or search for where something lives, and put new code where it says that kind of code belongs. The map is a lossy compression of the tree that answers *where do I look next* rather than every detail; it is expected to drift, so regenerate a wrong entry from the tree instead of patching around it. For a deeper structural index, read [`artifacts/file_index.md`](artifacts/file_index.md); for the code-heavy documentation bundle, read [`llms.txt`](llms.txt).

Each folder's own `README.md` documents that folder in more depth, so read it to the end before you change anything inside the folder. Its closing `## Notes for agents` section, where one exists, records mistakes that review has already caught there, so that you do not repeat them. The `@claude` review workflow appends to those notes after every review, and lint rule A009 keeps every folder README at or under 40,000 characters; two long READMEs that predate the rule keep a fixed, higher ceiling of their own, and the root `README.md`, the package's page on PyPI, is exempt.

Two rules from the map apply to every change. **Do not grep, glob, or read files under `docs/` as part of ordinary work:** those design documents are large and not kept in sync with the implementation, so treat the folder as opaque unless a human names a specific document and asks you to read it. Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it.

> **The [Placement Rules](#placement-rules) below are not part of the map.** That section is prescriptive, not descriptive: it is binding for all new code, and the `AGENTS.md placement` workflow enforces it on every pull request by moving misplaced code to the location it names.

## General Coding Style Guidelines

These four principles describe how code in this repository should be shaped. They apply to new code and to code you change. Do not rewrite untouched code just to make it conform; that belongs in its own pull request.

### 1. Keep Call Chains One Level Deep

Inside a class, or a module of plain functions, a function may call another of its own functions, but that second function should not call a third. The shape to aim for is one main function that calls a flat list of helpers, where each helper does its job and returns without calling further helpers of its own. When a helper starts to need another helper, lift that call up into the main function so the whole sequence of steps stays visible in one place. Calls out to another class, a lower layer, or the standard library do not count toward this limit. Avoid defining functions inside other functions as well, unless an API requires a callback or a decorator. A reader should be able to understand any feature from its main function plus one level of helpers, without following a chain of calls down through the file.

### 2. Narrate Main Functions in Plain English

Every class or feature has a main function: the top-level method that carries out the feature by calling its helpers in order. Inside that function, place short plain-English comments throughout the body, so that a reader can follow the whole feature by reading only the comments. Each comment translates the next step, or the next few lines, into everyday words, such as `# Send the tool schemas with the request so the model knows what it may call.`, and says why the step exists when that is not obvious. Write for a reader who knows the product but not this code: avoid jargon and abbreviations, and do not restate the code symbol by symbol. Small helpers that do one obvious thing need little or no inline commentary, because the main function is where the narration matters. When you change the steps of a main function, update its comments in the same edit so they never describe behavior that is gone.

### 3. Build in Layers of Small, Single-Purpose Classes

Organize each feature as layers, and inside each layer split a large feature into several small classes and files, using subclasses or composition, rather than growing one large class. Data and dependencies flow in one direction only: a higher layer may import and call a lower one, a lower layer never imports a higher one, and no two modules depend on each other in a cycle. In this repository `vidbyte/lib/` is the bottom layer, domain packages such as `agents/`, `tools/`, and `context/` build on it, and composition layers such as `pipelines/` and `paradigms/` build on those; nothing in `vidbyte/lib/` may import from a layer above it. Each class owns one subsystem of the larger feature, and each function does exactly one thing, except the main function, whose one job is to coordinate its helpers. Keep files well below 1,000 lines; when a file heads toward four digits, split it into smaller modules along subsystem lines before adding more. If describing the job of a function or a class needs the word "and", it is probably two functions or two classes.

### 4. Use Validated Dataclasses for Core Inputs and Outputs

Functions that carry core business logic take a dataclass as input and return a dataclass as output, rather than loose dicts, tuples, or long lists of primitive arguments. Each dataclass validates itself strictly when it is created, in `__post_init__`: it checks types, ranges, required fields, and allowed values, and raises a clear error that names the field and the bad value. Invalid data then fails at the boundary where it enters, not deep inside the logic that uses it, and the function body can trust every field it reads. Prefer `@dataclass(frozen=True, slots=True)` so a validated record cannot later be changed into an invalid one, and type any field whose value comes from a small, closed set as an enum. Small private helpers do not need dataclasses of their own; the rule is for the functions that hold a feature's real logic and for the data passed between layers. Define each new dataclass in `vidbyte/lib/dataclasses/<domain>.py` and each new enum in `vidbyte/lib/enums/<domain>.py`, as the [Placement Rules](#placement-rules) below require.

## Placement Rules

### Dataclasses go in `vidbyte/lib/dataclasses/`

**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`**, where `<domain>` names the feature or subsystem it belongs to (`jev.py`, `sessions.py`, `tools.py`). This holds no matter which layer uses the dataclass, and whether it is public or underscore-prefixed.

- Add to the existing domain module when there is one; create a new `<domain>.py` only for a new domain. Do not create `types.py`, `records.py`, `models.py`, or `schemas.py` modules next to the code that uses the dataclass.
- Import it from its domain module, `vidbyte.lib.dataclasses.<domain>`. A feature package may re-export it from its own `__init__.py` as part of its public API, as `vidbyte/agents/jev/__init__.py` does, but the definition stays in `vidbyte/lib/dataclasses/`.
- Validation of the record itself (`__post_init__`, field checks) lives with the dataclass. Behavior that acts on the record lives in the layer that owns that behavior.
- `vidbyte/lib/` must never import from a layer above it. If a dataclass seems to need a type from a higher layer, move the contract down (a `Protocol` or a smaller record in `vidbyte/lib/`). Do not define the dataclass in the higher layer instead.

There are exactly two exceptions:

1. **Agent settings objects.** A `*Settings` class that configures an agent lives in `vidbyte/agents/settings/`, or in the owning agent's own `settings.py` (for example `vidbyte/agents/jev/settings.py`).
2. **JEV preflight questions.** The `JevPreflightQuestion` subclasses, one dataclass per question, live in `vidbyte/lib/jev/preflight/<preset>.py`. See [JEV File Locations](REPO_MAP.md#jev-file-locations).

### Enums go in `vidbyte/lib/enums/`

**Every new enum (any `Enum` subclass, including `str, Enum`, `StrEnum`, and `IntEnum`) is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions. An enum does not go in a domain module, a settings module, or a `vidbyte/lib/dataclasses/` module beside the dataclass that uses it.

Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`.

### New JEV code

The file-by-file table of existing JEV code is [JEV File Locations](REPO_MAP.md#jev-file-locations). New JEV code goes here:

- **A record** goes in `vidbyte/lib/dataclasses/jev.py`, **an enum or enum member** in `vidbyte/lib/enums/jev.py`, and **a constant** in `vidbyte/lib/constants/jev.py`. Never create a `types.py`, `enums.py`, or `constants.py` under `vidbyte/agents/jev/` or `vidbyte/lib/jev/`.
- **A new dynamic-compute option** adds its enum member and question keys, twelve fixed `JevComputeQuestion` instances in `vidbyte/lib/jev/compute/situations.py`, and one option mapping in `JevComputeRegistry`. Questions share `{request, brief, facts, recent}` and the common mean P(true) threshold; do not add eligibility gates or per-question vetoes. Read `skills/asking-jev-dynamic-compute-questions/SKILL.md` first.
- **A new fixed-question preset** needs four things:
  - its flag on `JevPreflightPreset` and its keys on `JevPreflightQuestionKey`;
  - its definition in `JevPresets`;
  - its questions in a new `vidbyte/lib/jev/preflight/<preset>.py`, registered in `JevPreflightRegistry`;
  - one case in the `match` in `JevPreflightGate.pass_()`. Never add preset checks to `JevRuntime`.
- **A new JevAgent capability** is a named, validated field on `JevAgentSettings`. Its questions and actions stay inside `vidbyte/agents/jev/` and `vidbyte/lib/jev/`.
- **A new Jev-facing prompt** is a new family under `vidbyte/prompts/prompts/`, with its key in `vidbyte/lib/enums/prompts.py`.

### Existing code

Many modules on `main` still define dataclasses or enums outside these two folders; they predate these rules. Do not copy them as precedent. Editing one in place (adding a field or a member) is fine. Moving it to `vidbyte/lib/` is a change of its own and belongs in its own pull request, not folded into unrelated work. These rules govern newly defined dataclasses and enums.
