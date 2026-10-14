---
slug: prebuilt-agent-tools
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-14 02:46
flags: none
---

# Request: A library of 250+ prebuilt agent tools in vidbyte-sdk

## A. Every user prompt in this conversation, verbatim and in order

The pipeline was invoked cold (the conversation was cleared immediately before), so there is exactly one prompt.

**Prompt 1** (the invoking prompt, `/spec-pipeline` argument string):

````
straight into spec for vidbyte-sdk/. Implement 250+ simple, easy to under, and useful prebuilt tools int the vidbyte-sdk/, dont really care what they are but they should expand the capability of the agent in some way (can ground your ideas in recent agentic research on some of the tools that people were giving to agents).
````

## B. Handoff block and decision ledger (verbatim, if present)

none

## C. Structured conversation notes

### Key decisions
- Target repository is `vidbyte-sdk` (`C:/Users/422mi/vidbyte-repos/vidbyte-sdk`) — named explicitly by the user ("for vidbyte-sdk/", "int the vidbyte-sdk/").
- "straight into spec" — the user wants no design conversation first; the spec author decides the catalogue and the design from the repo and from research.
- The count is a floor: **250 or more** tools ship in this PR. Not "about 250", not "a framework that could host 250".
- The user explicitly delegates the choice of tools: "dont really care what they are". The spec author picks them.
- Every tool must "expand the capability of the agent in some way" — a tool the agent could trivially do by itself in-context with no gain (e.g. "echo the input back") does not qualify. A tool qualifies when it gives the agent something it does badly or cannot do natively: exact computation, deterministic transformation, parsing/validation of a format, reliable counting/sorting/diffing, time and date arithmetic, encoding, structured data manipulation, text statistics, etc.
- Each tool must be **simple** and **easy to understand** (the user typed "easy to under", meaning "easy to understand"): small, single-purpose, obvious name, obvious inputs and outputs.
- Each tool must be **useful** to an agent.
- Ideas may be grounded in recent agentic research on the tools people give to agents (the user offered this as an option: "can ground your ideas in ..."). It is permission, not a requirement to cite papers in code.

### Rejected alternatives
- none stated by the user.

### Constraints and assumptions
- The tools are "prebuilt" — they ship inside the SDK, ready to use, alongside the SDK's existing built-in tools (the SDK already has `vidbyte/tools/builtins/` with tools such as `calculator.py`, `bash.py`, `code_execution.py`, `document_retrieval.py`, and toolsets in `vidbyte/tools/toolsets/`, plus a tool catalog in `vidbyte/tools/catalog.py`). Orchestrator observation, not a user statement: the new tools should follow the existing tool-authoring patterns of the SDK rather than invent a new tool mechanism.
- Assumption (orchestrator, flag as A- item): "simple" implies the tools should be deterministic, local, and dependency-free where possible (Python standard library), so that 250+ of them can be tested and do not need API keys, network, or new third-party dependencies. The spec author must confirm or refute this against the repo and research, and record it as an assumption.
- The repo's AGENTS.md rules apply to every file (placement of dataclasses/enums in `vidbyte/lib/`, narrated main functions, validated dataclasses, files well under 1,000 lines, canonical helpers in `lib/`), and the full CI gate must pass.

### Clarifications and answers
- none (no questions were asked; the user asked to go straight into the spec).

### Terminology
- "prebuilt tools" — tools that ship with the SDK and that an agent built with the SDK can be given without the developer writing them.
- "expand the capability of the agent" — the tool lets the agent do something more reliably, more exactly, or at all, compared with reasoning in tokens alone.
- "easy to under" — typo for "easy to understand".
- "int the vidbyte-sdk/" — typo for "into the vidbyte-sdk/".

### Implementation hints
- Existing tool infrastructure lives in `vidbyte/tools/` (`base.py`, `function_tool.py`, `decorators.py`, `catalog.py`, `builtins/`, `toolsets/`). Existing tool tests include `tests/test_tools_catalog.py`, `tests/test_tool_core.py`, `tests/test_custom_function_tools.py`, `tests/test_function_tool_parameter_types.py`.
- The field guide for this repo (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/init.md`) has entries including `model-facing-tool-contracts.md`, `prebuilt-agents.md`, `strict-config-dataclasses.md`, `blocking-lint-invariants.md`, `local-ci-verification.md`, `review-scope.md` that are likely to apply.
- `docs/` is opaque in this repo (AGENTS.md); no agent browses it.

### Open questions
- How are 250+ tools organized so that each stays simple, files stay well under 1,000 lines, and a developer can find and attach them (by category / toolset / catalog entry)? The spec author decides.
- How does a developer attach one tool, a category of tools, or all of them to an agent? The spec author decides from the existing patterns (toolsets, catalog).
- Which tool categories? The spec author decides, optionally grounded in research on tools commonly given to agents.
- Do any tools need network access or third-party dependencies? Default assumption: no (see Constraints).

## D. Weighted words

- "Implement 250+ simple, easy to under, and useful prebuilt tools" — Prompt 1 (the count is a floor of 250; "simple", "easy to understand", "useful" apply to every tool)
- "they should expand the capability of the agent in some way" — Prompt 1 (applies to every tool: none may be a no-op or something the agent does trivially in-context)
- "dont really care what they are" — Prompt 1 (the choice of tools is delegated; it is not a request for any specific tool)
- "straight into spec" — Prompt 1 (no pre-spec questions)
