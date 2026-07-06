# Design Doc: Tool Error Taxonomy & Tool-Authored Errors

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

> **Doc 1 of 3** in the tool-error initiative. Read order and dependency:
> 1. **`tool-error-taxonomy-and-authoring`** (this doc) — the *author* layer. Defines the structured error type tools raise and the pipeline that preserves it. Foundation; no provider or settings concerns.
> 2. `provider-aware-tool-error-rendering` — the *render* layer. Turns a structured error into a per-provider model-visible message.
> 3. `tool-error-policy-and-retry` — the *decide* layer. Settings + middleware that retry / continue / abort based on the error.
>
> Docs 2 and 3 both depend on the `ToolError` / `ToolErrorKind` / `retryable` contract established here. Build this one first.

---

## 1. Overview

Today tool failures are classified with free-form strings stuffed into `ToolResult.metadata["error"]` (e.g. `"execution_error"`, `"validation_error"`) at a handful of `try/except` sites in the agent runtime. Tools themselves cannot express *what kind* of error occurred or attach a human-authored remediation hint — every raised exception is flattened to a generic `execution_error` with `f"Tool execution failed: {exc}"`. This doc promotes the taxonomy to a first-class `ToolErrorKind` enum, introduces a `ToolError` exception that tool authors raise to carry `(kind, message, hint, retryable)`, and threads that structured error faithfully through the runtime pipeline onto `ToolResult`. It also fixes an existing bug where argument/validation errors are mislabeled as execution errors. This is the foundation the other two docs build on.

---

## 2. Original User Prompts

**Prompt 1:** question for the vidbyte-sdk/ repo, in regards to our tools (vidbyte/tools). right now what is the lifecycle behind tooling errors during the agent runtime. For example, how do we handle schema/arguements errors, execution errors, etc, and what are some other types of tools errors that could potentially occur?

**Prompt 2:** well before we get to exact implementation I want to express my intent. I basically first want each error tool to have its own tool errors (argeument errors, execution error, etc). I seems like we have these already, and if there are any more error classes we could define for our tools please briefly describe these (also I think it is a very good idea for each tool to potentially come with like a custom string message just incase there is some very nuonced detail about the error, ex: like a terminal command tool would come with like a 'make sure you are running the terminal commands on the right operations system' or something like that, and we could add these first class error messages to the tools themselves). Then, with these tool error messages I want make it so that these error messages actually get propagated to the agent and get filled within the context window so that if we have a tool error the run doesnt just stop and the agent can actually see information about tool error. How can we add this and what is the cleanest entry point. The idea that I had was we add like some "tool policy" settings to the vidbyte/agent/settings (agent loop settings), and then with these settings we can derive the tool error/execution logic in the agent class (tool settings like retry_number, include full error message, etc, I feel like you could do a better job of deriving exact settings for this). What do you think about all of this?

**Prompt 3:** great, can you decompose all of this into like 2-3 design docs and one thing that I want you to remember is to take into considers that each providers takes in tools in a specific way, so just make sure you take this into consideration in your design docs

---

## 3. Structured Conversation Notes

### Key Decisions

- **Promote the stringly-typed taxonomy to a real enum.** Today error categories live only as strings in `ToolResult.metadata["error"]`. They will become a `ToolErrorKind(str, Enum)` so downstream code (rendering in Doc 2, retry policy in Doc 3) can branch on stable values instead of matching strings.
- **Tools *raise* structured errors; they do not return metadata strings.** The cleanest mechanism for the user's "each tool comes with a custom nuanced message" requirement is a `ToolError` exception a tool author raises from inside `execute()`, carrying `kind`, `message`, `hint`, and `retryable`. The runtime catches it *specifically* and preserves those fields. Rationale: the nuance lives next to the code that produces it, the hint can be contextual to the actual failure (exit code 127 → "command not found" hint vs. a permission error → a different hint), and tools that don't care keep raising plain exceptions with zero migration cost.
- **`retryable` is a first-class axis, not a category.** The single most decision-relevant attribute of an error is whether retrying the identical call could succeed. `permission_denied` / `invalid_arguments` are terminal; `timeout` / `rate_limited` / `upstream_error` are transient. This is a field on the error and on `ToolResult.metadata`, orthogonal to `kind`. Doc 3's retry loop branches on it.
- **Split `INVALID_ARGUMENTS` out of `EXECUTION_FAILED`.** The user explicitly wants argument errors to be their own class. They already *conceptually* are (validation runs before execution) but the runtime currently collapses them — see the bug below.
- **Add a static per-tool fallback hint on `ToolSpec`.** For failures where a tool raises a *bare* exception (not a `ToolError`), an optional `ToolSpec.default_error_hint` provides the general nuance (e.g. a terminal tool's OS caveat) even without per-failure authoring. When a raised `ToolError` carries its own hint, that wins; the spec hint is the fallback.
- **This doc keeps the pipeline change minimal and provider-agnostic.** The structured error must *survive onto `ToolResult`*; how it is rendered into a provider message is entirely Doc 2's job. Do not touch `ToolsFormatter` here.

### Rejected Alternatives

- **Bolting a single `error_hint: str` onto every `ToolSpec` and nothing else.** Rejected as the primary mechanism: a blanket string can't adapt to the actual failure and duplicates poorly. Kept only as the *fallback* (`default_error_hint`) for bare exceptions.
- **A separate exception subclass per category** (`ToolTimeoutError`, `ToolRateLimitError`, …). Rejected: explodes the type surface and forces tool authors to import many symbols. One `ToolError` carrying a `kind` enum is simpler and covers every case. (The existing MCP hierarchy in `lib/errors/base.py` stays as-is; see Implementation Hints.)
- **Encoding error kind purely in the output string for the model to parse.** Rejected: the runtime and policy layers (Docs 2–3) need machine-readable classification; prose is for the model, not for control flow.
- **Introducing a `PARTIAL_SUCCESS` state now.** Deferred (Non-Goal). `ToolStatus` is binary today; adding a third semantic status ripples through every provider formatter and the primitive-binding path. Out of scope for v1.

### Constraints & Assumptions

- **Backward compatibility:** existing tools return `ToolResult` and raise plain exceptions today. Nothing may break for a tool that never adopts `ToolError`. The generic `except Exception` fallback path must remain and must produce a `ToolErrorKind.EXECUTION_FAILED` result identical in spirit to today's.
- **`metadata["error"]` string keys are currently consumed** in at least the executor and runtime paths and possibly evals (`vidbyte/evals/behavior/tool.py`). New enum values must keep string-compatible values (`ToolErrorKind` subclasses `str, Enum` with values equal to the current strings where they already exist, e.g. `"permission_denied"`, `"unknown_tool"`) so existing string comparisons keep working.
- **Two execution surfaces exist and diverge** (`vidbyte/tools/executor.py` `ToolExecutor.execute_call` and `vidbyte/agents/runtime.py` `AgentRuntime.execute_tool_call`). The runtime one is the authoritative agent path. This doc updates both, or extracts a shared helper, to stop them drifting further.
- Python 3.10+ (`X | None` syntax throughout). `slots=True` frozen dataclasses are the house style for data contracts. Every module carries a "Context Protocol Header" docstring — match it.

### Clarifications & Answers

- **Q: Does the run stop on a tool error today?** A (established in conversation): **No.** `runtime.py:1339-1343` already appends the error `ToolResult.output` to `messages` via `ToolsFormatter.format_tool_result` and the loop continues. `execute_tool_call` never raises — it always returns a `ToolResult`. So the missing pieces are *richness* (Doc 1–2) and *retry* (Doc 3), not "make it not stop."
- **Q: Do we already have per-tool error classes?** A: Partially — there's an exception hierarchy in `lib/errors/base.py` (`ToolRegistryError`, `PermissionDeniedError`, `ToolExecutionError`, plus the `Mcp*` family) and stringly-typed metadata codes. What's missing is a tool-authorable, `kind`-tagged error with a hint and retryable flag.

### Terminology / Glossary

- **`ToolErrorKind`** — new enum of tool failure categories (resolution, permission, arguments, execution, timeout, etc.).
- **`ToolError`** — new exception a tool raises to carry structured failure info `(kind, message, hint, retryable)`.
- **retryable** — boolean: could re-invoking the *identical* call plausibly succeed? Property of the error.
- **hint / remediation hint** — a human-authored string giving nuanced guidance to the model (e.g. "commands run in a POSIX sandbox; use forward slashes"). Either per-failure (on `ToolError`) or per-tool fallback (`ToolSpec.default_error_hint`).
- **The pipeline** — the resolve → authorize → validate → execute → output-schema stages inside `AgentRuntime.execute_tool_call`.

### Implementation Hints for the Downstream Model

- **Core files to change:**
  - `vidbyte/lib/dataclasses/tools.py` — add `ToolErrorKind` enum; add `default_error_hint: str | None = None` field to `ToolSpec`; consider adding `error_kind`/`retryable`/`hint` convenience accessors on `ToolResult` (or standardize the metadata keys). `ToolResult` and `ToolStatus` live here.
  - `vidbyte/tools/base.py` — `BaseTool` and its `validate_call`. Add the `ToolError` exception here or in a new `vidbyte/tools/errors.py` (prefer a new module to avoid import cycles; `base.py` already imports from `types`).
  - `vidbyte/agents/runtime.py` — the authoritative pipeline. Key anchors:
    - `execute_tool_call` at **`runtime.py:955`** — the whole `try/except` ladder (`:968-1013`).
    - `_validate_tool_call` at **`runtime.py:1087`** — raises `ToolExecutionError` with `details={"error": "validation_error"}`.
    - `_execute_tool` at **`runtime.py:1096`** — wraps any `Exception` into `ToolExecutionError`. **Add an `except ToolError` clause here (above the generic `except Exception`)** that preserves `kind`/`hint`/`retryable`.
    - The output-schema check inline at **`runtime.py:974-981`** already produces `output_schema_violation`.
  - `vidbyte/tools/executor.py` — `ToolExecutor.execute_call` at **`executor.py:42`**, the leaner second pipeline. Mirror the changes or delegate.
  - `vidbyte/lib/errors/base.py` — the SDK exception hierarchy. `ToolError` should extend `VidbyteSdkError` (like the others) so its `.details` mechanism is available and it's safe to expose.
- **THE BUG to fix (called out explicitly by the analysis):** `_validate_tool_call` (`runtime.py:1091`) raises `ToolExecutionError(..., details={"error": "validation_error"})`, but the `except ToolExecutionError` handler at **`runtime.py:997-1004`** only reads `details["error_type"]` and hardcodes `metadata["error"] = "execution_error"`. The `"validation_error"` label is **thrown away** — a schema/argument error reaches history mislabeled as `execution_error`. Note `ToolExecutor.execute_call` (`executor.py:59-65`) does *not* have this bug (it labels validation correctly), so the two surfaces disagree. Fix: give validation its own `except` path or map `details["error"]` through to `metadata["error"]`, producing `ToolErrorKind.INVALID_ARGUMENTS`.
- **`FunctionTool` validates twice** (`function_tool.py:44` in `validate_call` and `:53` inside `execute`) via Pydantic; `_validation_message` at `:131` formats the message. It returns a `ToolResult.failure(..., metadata={"error_type": "validation"})` from inside `execute` rather than raising. Align this with the new taxonomy: it should produce `ToolErrorKind.INVALID_ARGUMENTS`.
- **Do NOT modify the `Mcp*` exception hierarchy** in `lib/errors/base.py` (`McpConnectionError`, `McpInitializeError`, `McpToolDiscoveryError`, `McpToolExecutionError`). Those fire at attach/discovery time. But DO note: at *runtime*, a bridged MCP tool raising `McpToolExecutionError` inside `.execute()` is currently caught by the generic `except Exception` and flattened. Map `McpToolExecutionError` → `ToolErrorKind.UPSTREAM_ERROR` (retryable) in the new `except` ladder so MCP execution failures keep their meaning.
- **`ToolCallState`** (`lib/dataclasses/tools.py:44`) is the richer 4-state internal lifecycle (`REQUESTED/SUCCEEDED/FAILED/DENIED`) carried on `ToolCallContext`. `ToolStatus` (binary `SUCCESS/ERROR`) is what rides on `ToolResult`. Keep both; the new `kind` lives in `ToolResult.metadata` (and optionally a typed accessor), not as a new `ToolStatus`.
- **Match house style:** frozen `slots=True` dataclasses, `from __future__ import annotations`, Context Protocol Header docstring on every new module, methods documented with a one-line docstring. Look at `custom-exception-constructors.md` and `custom-function-tools.md` in `docs/design/` for prior art on how this repo shapes error/tool changes.

### Open Questions

- Should `ToolError`'s `retryable` default to `None` (meaning "let policy decide based on `kind`") or to a concrete `False`? Recommendation: `None`, so Doc 3's policy owns the default mapping (`kind → retryable`) and a tool can override per-call. Confirm with user.
- Do we expose typed accessors (`ToolResult.error_kind`, `.hint`, `.retryable`) or keep everything in `metadata` with well-known keys? Recommendation: add read-only convenience properties that read from `metadata`, so the storage stays one dict but call-sites are type-safe.
- Should `NOT_FOUND` and `CONFLICT` ship in v1 or be deferred? They're most relevant to filesystem/write tools. Recommendation: define the enum members now (cheap), let tools adopt them incrementally.

---

## 4. Goals & Non-Goals

### Goals

- Define a first-class `ToolErrorKind` enum covering the current categories plus the newly identified ones.
- Introduce a `ToolError` exception tool authors raise to carry `(kind, message, hint, retryable)`.
- Preserve that structured error faithfully onto `ToolResult` (metadata + typed accessors) through both execution pipelines.
- Add an optional `ToolSpec.default_error_hint` per-tool fallback hint.
- Fix the validation-labeled-as-execution bug and align `FunctionTool`'s validation with the new taxonomy.
- Map `McpToolExecutionError` raised at runtime to `UPSTREAM_ERROR` instead of the generic flatten.

### Non-Goals

- Rendering errors into provider-specific model messages (Doc 2).
- Retry, backoff, circuit-breaking, settings, or middleware (Doc 3).
- `PARTIAL_SUCCESS` / non-binary `ToolStatus` (deferred).
- Per-tool execution timeouts (flagged as a real gap, but the `asyncio.wait_for` wrapper is out of scope here; `TIMEOUT` kind is defined so Doc 3 can wire it).
- Changing the MCP attach/discovery error hierarchy.

---

## 5. Background & Context

The agent runtime's tool pipeline normalizes every failure into a `ToolResult` so the loop never crashes on a bad tool call. That normalization currently loses information: category is a hand-written string, there's no way for a tool to attach guidance, and validation vs. execution is conflated in the runtime path. The user's intent is that tools own rich, nuanced error messages that then reach the model so it can recover. That requires, first, a structured error the tool can produce and the pipeline can carry — which is this doc. Without it, Docs 2 and 3 would be rendering and retrying on top of unstructured strings.

Current state established by code audit: `execute_tool_call` (`runtime.py:955`) has a five-stage pipeline with a `try/except` ladder mapping `ToolRegistryError → unknown_tool`, `PermissionDeniedError → permission_denied`, `ToolExecutionError → execution_error`, and a catch-all `Exception → execution_error`; plus an inline output-schema check producing `output_schema_violation`, and a middleware-deny path producing `middleware_denied`.

---

## 6. Requirements

1. A `ToolErrorKind(str, Enum)` MUST exist with members: `UNKNOWN_TOOL`, `PERMISSION_DENIED`, `INVALID_ARGUMENTS`, `EXECUTION_FAILED`, `OUTPUT_SCHEMA`, `TIMEOUT`, `RATE_LIMITED`, `UPSTREAM_ERROR`, `NOT_FOUND`, `CONFLICT`, `CANCELLED`, `MIDDLEWARE_DENIED`. Values MUST be string-compatible with existing metadata strings where those already exist (`"permission_denied"`, `"unknown_tool"`, `"output_schema_violation"`, `"middleware_denied"`).
2. A `ToolError` exception MUST carry `kind: ToolErrorKind`, `message: str`, `hint: str | None`, and `retryable: bool | None`, and MUST extend `VidbyteSdkError`.
3. `AgentRuntime._execute_tool` MUST catch `ToolError` specifically and produce a `ToolResult` whose metadata contains the error's `kind`, `hint`, and `retryable`, preserving the author's message.
4. A tool raising a *plain* `Exception` MUST still yield `ToolErrorKind.EXECUTION_FAILED` (backward compatible), falling back to `ToolSpec.default_error_hint` if present.
5. Argument/schema validation failures MUST be labeled `INVALID_ARGUMENTS`, not `EXECUTION_FAILED`, in BOTH pipelines. (Fixes the runtime bug.)
6. `McpToolExecutionError` raised during `.execute()` MUST map to `UPSTREAM_ERROR` with `retryable=True`.
7. `ToolSpec` MUST gain an optional `default_error_hint: str | None = None` field; per-`ToolError` hints take precedence over it.
8. `ToolResult` MUST expose the error `kind`, `hint`, and `retryable` in a stable, documented way (metadata keys and/or typed accessors) for Docs 2 and 3 to consume.
9. Existing string-based consumers of `metadata["error"]` MUST continue to work unchanged.

---

## 7. Non-Functional Requirements

- **Performance:** negligible; adds a dataclass construction and dict writes on the error path only. No hot-path change on success.
- **Security:** the raw-exception-string leak (`f"Tool execution failed: {exc}"` at `runtime.py:1009` / `:1102`) is *not fully fixed here* — redaction is a Doc 3 policy concern — but this doc MUST NOT widen the leak. When a `ToolError` is raised, prefer the author's `message` over the raw exception repr.
- **Observability:** the tracer already records tool spans (`runtime.py:963-1013` calls `end_span(..., error=exc)`). The new `kind` SHOULD be added to span metadata so LangSmith traces show the classified error.
- **Reliability:** the pipeline MUST remain non-raising — every path still returns a `ToolResult`. Adding an `except ToolError` above `except Exception` must not let anything escape.
- **Compatibility:** no breaking change to the public `ToolResult`, `ToolSpec`, or `BaseTool` constructors (all new fields optional/defaulted).

---

## 8. High-Level Design

Introduce a structured error contract in the tools layer and thread it through the two execution pipelines without changing their control flow shape. The new `ToolErrorKind` enum and `ToolError` exception live in `vidbyte/tools/errors.py` (new module) re-exported from `vidbyte/tools/__init__.py`; `ToolError` extends `VidbyteSdkError`. `ToolSpec` gains `default_error_hint`. `ToolResult` gains read-only accessors (`error_kind`, `hint`, `retryable`) backed by well-known metadata keys, so storage stays a single dict while call-sites are type-safe.

The runtime pipeline (`AgentRuntime.execute_tool_call`) is modified at three points: (a) `_execute_tool` gains an `except ToolError` clause above the generic `except Exception`, translating the structured fields into `ToolResult.error(...)` metadata; (b) the `except Exception` fallback additionally injects `ToolSpec.default_error_hint`; (c) the validation path is corrected so `INVALID_ARGUMENTS` survives to `metadata["error"]` instead of being overwritten with `execution_error`. `McpToolExecutionError` gets a dedicated branch mapping to `UPSTREAM_ERROR`. The leaner `ToolExecutor.execute_call` receives the same treatment (or both delegate to a shared `_normalize_tool_error(exc, spec) -> ToolResult` helper to end the drift between the two surfaces). `FunctionTool`'s Pydantic validation is aligned to emit `INVALID_ARGUMENTS`.

Data flow end-to-end for this doc: a tool raises `ToolError(kind=..., hint=..., retryable=...)` (or a plain exception) → the pipeline's `except` ladder classifies it → a `ToolResult` with `status=ERROR` and structured metadata (`error`=kind value, `hint`, `retryable`) is returned to the loop. **This doc stops there** — the `ToolResult` sitting in the loop is the hand-off point to Doc 2 (which renders it per provider) and Doc 3 (which decides whether to retry). Crucially, nothing in `ToolsFormatter` or `AgentLoopSettings` is touched here.

```
  Tool body
     |  raise ToolError(kind, message, hint, retryable)   (or plain Exception)
     v
  AgentRuntime._execute_tool  (runtime.py:1096)
     |  except ToolError  -> preserve kind/hint/retryable      [NEW]
     |  except McpToolExecutionError -> UPSTREAM_ERROR          [NEW]
     |  except Exception  -> EXECUTION_FAILED + default_error_hint
     v
  ToolResult(status=ERROR, metadata={error: kind, hint, retryable})
     |
     +--> [handed to Doc 2: provider-aware rendering]
     +--> [handed to Doc 3: retry / continue / abort policy]

  Validation stage (runtime.py:1087) -> INVALID_ARGUMENTS  [FIX: no longer mislabeled]
```

---
