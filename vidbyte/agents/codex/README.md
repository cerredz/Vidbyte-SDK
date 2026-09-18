# `vidbyte/agents/codex`

## Folder Description / Intent

This folder holds `CodexHarnessAgent`, a Vidbyte agent in which **Codex runs the agent loop**. Codex handles the model calls, shell commands, file edits, sandboxing, approvals, and its own subagents. Vidbyte handles everything around that loop: the agent's settings, typed input, context rendering, structured output, custom Python tools, turn-level middleware, a model fallback chain, usage accounting, failure records, and the `AgentMessage` result.

Use it when you want Codex's coding agent to do the work and still get a normal Vidbyte agent back, with the same `run()`/`arun()` call, `AgentMessage` reply, and `@tool` functions that the rest of the SDK uses.

Every class in this folder translates between the two sides. Each Vidbyte setting that Codex can carry out is translated before any Codex process starts. Each setting it cannot carry out is rejected when you build the agent, so it never fails silently mid-run. The rest of this README is a cookbook of common ways to use the agent, with notes on where each feature stops working.

> The root [`README.md`](../../../README.md#codex-harness-agent) has a short overview. This page is the detailed developer guide.

---

## Install

```bash
python -m pip install "vidbyte-sdk[codex]"   # pins openai-codex>=0.147.0,<0.148.0
```

The extra installs the `openai-codex` Python SDK, which starts the Codex app-server. If the extra is missing, you can still construct the agent. The first `run()` then raises `CodexAgentError` with `failure_code="codex.sdk_unavailable"`.

## Quick start

```python
from vidbyte import CodexHarnessAgent, CodexHarnessAgentSettings

agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="repo-helper",
        system_prompt="You are a careful engineer. Explain what you changed and what you verified.",
    )
)

reply = agent.run("Summarize what this repository does in three bullet points.")
print(reply.content)             # Codex's final answer
print(reply.codex.thread_id)     # native Codex thread id, reused by the next run
```

The same call from async code:

```python
import asyncio

from vidbyte import CodexHarnessAgent, CodexHarnessAgentSettings


async def main() -> None:
    agent = CodexHarnessAgent(
        CodexHarnessAgentSettings(name="repo-helper", system_prompt="Be concise.")
    )
    reply = await agent.arun("List the top-level folders and what each one is for.")
    print(reply.content)


asyncio.run(main())
```

> `run()` is a synchronous wrapper around `arun()`. It raises `CodexAgentError` when called inside a running event loop, such as FastAPI, Jupyter, or any `async def`. Use `await agent.arun(...)` there.

---

## Use-case index

| # | I want to… | Recipe |
|---|---|---|
| 1 | Send text, images, skills, or mentions | [Input shapes](#1-input-shapes-str-agentinput-codexruninput) |
| 2 | Choose the model, reasoning effort, sandbox, and working directory | [Configure Codex](#2-configure-codex-client-thread-and-turn-settings) |
| 3 | Run a read-only reviewer or a code-writing implementer | [Sandbox and approval presets](#3-sandbox-and-approval-presets) |
| 4 | Get typed JSON back instead of prose | [Structured outputs](#4-structured-outputs) |
| 5 | Let Codex call my own Python functions | [Custom tools](#5-custom-tools) |
| 6 | Add policy, audit, or guardrails around a run | [Middleware](#6-middleware) |
| 7 | Pass Vidbyte context (documents, tasks, diffs, memory) | [Vidbyte context translation](#7-vidbyte-context-translation) |
| 8 | Hold a multi-turn conversation or resume one later | [Threads](#8-multi-turn-conversations-and-resuming-threads) |
| 9 | Explore alternatives from the same starting point | [Forks](#9-forking-a-thread-to-explore-alternatives) |
| 10 | Let Codex spawn its own helper agents | [Subagents](#10-codex-subagents) |
| 11 | Fall back to another model when a turn fails | [Fallback chains](#11-model-fallback-chains) |
| 12 | Track tokens and estimated cost | [Usage and cost](#12-usage-and-cost) |
| 13 | Handle failures correctly | [Error handling](#13-error-handling) |
| 14 | Put Codex into a pipeline or fan work out | [Composition](#14-composition-pipelines-and-parallel-fan-out) |
| 15 | Call it from a web server | [Async apps](#15-using-it-from-an-async-web-app) |
| 16 | Use a custom binary, gateway, or environment | [Custom provider and process settings](#16-custom-provider-binary-and-environment) |
| 17 | Inspect everything Codex did | [Reading the result](#17-reading-the-result) |
| 18 | Reuse a pattern from another Vidbyte agent | [What translates and what doesn't](#18-what-translates-and-what-doesnt) |

---

## 1. Input shapes (`str`, `AgentInput`, `CodexRunInput`)

`run()` and `arun()` accept any `CodexAgentInput`, which is one of three shapes. Pick the smallest one that fits.

```python
from vidbyte import (
    AgentInput,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
    CodexImageInput,
    CodexLocalImageInput,
    CodexRunInput,
    CodexSkillInput,
    CodexTextInput,
    DocumentContextItem,
)

agent = CodexHarnessAgent(CodexHarnessAgentSettings(name="ui-fixer", system_prompt="Fix UI bugs."))

# 1) Plain string: the common case.
agent.run("Fix the failing lint in src/")

# 2) AgentInput: the generic Vidbyte shape, as used by pipelines and other agents.
#    Metadata is copied onto reply.metadata; context items are rendered before the prompt.
agent.run(
    AgentInput(
        prompt="Apply the style guide to the header component.",
        metadata={"ticket": "UI-142"},
        context_items=(DocumentContextItem(source="STYLE.md", content="Use 8px spacing."),),
    )
)

# 3) CodexRunInput: native Codex input items in a set order. Use it for screenshots,
#    remote images, explicit skills, and mentions.
agent.run(
    CodexRunInput(
        items=(
            CodexTextInput("The button in this screenshot overflows on mobile. Fix it."),
            CodexLocalImageInput("./screenshots/mobile-header.png"),
            CodexImageInput("https://example.com/design/expected-header.png"),
            CodexSkillInput(name="frontend-review", path="./.codex/skills/frontend-review/SKILL.md"),
        ),
        recipient="design-team",           # becomes reply.recipient
        metadata={"source": "bug-bash"},
    )
)
```

- `CodexRunInput.text("...")` is shorthand for a single text item.
- `CodexMentionInput(name=..., path=...)` passes a Codex mention through unchanged. Codex resolves it.
- Bad input, such as an empty string, `None`, or a bare list, raises `CodexAgentError(failure_code="codex.vidbyte_translation_failed")` **before** any Codex process starts. The agent's state is unchanged.

---

## 2. Configure Codex: client, thread, and turn settings

Codex settings are split into the layers where Codex applies them. The layers are grouped under `CodexAgentSettings`, which you pass as `codex=`.

| Layer | Class | Applied when | Typical fields |
|---|---|---|---|
| Process | `CodexClientSettings` | Each time the app-server process starts | `codex_bin`, `cwd`, `env`, `config_overrides`, `experimental_api` |
| Thread | `CodexThreadSettings` | Thread start, resume, or fork | `model`, `model_provider`, `sandbox`, `approval_mode`, `base_instructions`, `personality`, `ephemeral`, `config` |
| Turn | `CodexTurnSettings` | Every `run()`; overrides thread values | `model`, `effort`, `sandbox`, `approval_mode`, `summary`, `personality`, `service_tier`, `cwd` |
| Subagents | `CodexSubagentSettings` | Thread start | See [recipe 10](#10-codex-subagents) |

```python
from vidbyte import (
    CodexAgentSettings,
    CodexClientSettings,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
    CodexPersonality,
    CodexReasoningEffort,
    CodexReasoningSummary,
    CodexSandbox,
    CodexThreadSettings,
    CodexTurnSettings,
)

agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="backend-implementer",
        system_prompt="Implement the requested change with tests. Never touch migrations.",
        description="Implements scoped backend changes.",
        capabilities=("python", "fastapi"),
        codex=CodexAgentSettings(
            client=CodexClientSettings(cwd="/work/my-service"),
            thread=CodexThreadSettings(
                model="gpt-5.5",
                sandbox=CodexSandbox.WORKSPACE_WRITE,
                personality=CodexPersonality.PRAGMATIC,
            ),
            turn=CodexTurnSettings(
                effort=CodexReasoningEffort.HIGH,
                summary=CodexReasoningSummary.CONCISE,
            ),
        ),
    )
)
```

Things to know:

- Every enum has a `PROVIDER_DEFAULT` member, and every string field defaults to `""`. Those values are **left out** of the Codex request, so Codex's own defaults and `~/.codex/config.toml` still apply.
- `system_prompt` is sent as Codex **developer instructions**. `base_instructions` *replaces* Codex's built-in base prompt, so set it only when you mean to.
- If you set `cwd` on more than one layer, the values must match. Otherwise `CodexHarnessAgent(...)` raises `CodexAgentError(failure_code="codex.vidbyte_translation_failed")`, with a `ConfigurationError` as its cause.
- Settings dataclasses are frozen and validated when created. A wrong type or an empty required string fails immediately, not during the run.

---

## 3. Sandbox and approval presets

Codex enforces the sandbox. Pick the narrowest mode that lets the job finish.

```python
from vidbyte import (
    CodexAgentSettings,
    CodexApprovalMode,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
    CodexSandbox,
    CodexThreadSettings,
)

# Reviewer: can read the repository, cannot change it, and never asks for approval.
reviewer = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="reviewer",
        system_prompt="Review the working tree for bugs. Do not modify files.",
        codex=CodexAgentSettings(
            thread=CodexThreadSettings(
                sandbox=CodexSandbox.READ_ONLY,
                approval_mode=CodexApprovalMode.DENY_ALL,
            )
        ),
    )
)

# Implementer: can write inside the workspace; Codex reviews escalations automatically.
implementer = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="implementer",
        system_prompt="Make the smallest change that fixes the bug, then run the tests.",
        codex=CodexAgentSettings(
            thread=CodexThreadSettings(
                sandbox=CodexSandbox.WORKSPACE_WRITE,
                approval_mode=CodexApprovalMode.AUTO_REVIEW,
            )
        ),
    )
)
```

`CodexSandbox.FULL_ACCESS` turns the sandbox off. Use it only inside a disposable container or VM. A [fallback chain](#11-model-fallback-chains) changes only the turn **model** and never widens the sandbox.

---

## 4. Structured outputs

Set `output_schema` to a Pydantic model or a JSON-schema mapping. Codex receives the schema for the turn, and Vidbyte validates the final answer before returning it.

### With a Pydantic model

```python
from pydantic import BaseModel

from vidbyte import CodexHarnessAgent, CodexHarnessAgentSettings


class Finding(BaseModel):
    file: str
    line: int
    severity: str
    message: str


class ReviewReport(BaseModel):
    summary: str
    findings: list[Finding]
    safe_to_merge: bool


agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="pr-reviewer",
        system_prompt="Review the current diff and report concrete findings only.",
        output_schema=ReviewReport,
    )
)

reply = agent.run("Review the staged changes.")
report = reply.structured          # the validated structured value
print(report)
print(reply.codex.structured)      # the same value, next to the native Codex data
```

### With a JSON-schema mapping

```python
from vidbyte import CodexHarnessAgent, CodexHarnessAgentSettings

agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="changelog",
        system_prompt="Write a changelog entry for the latest commit.",
        output_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "breaking": {"type": "boolean"},
                "bullets": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "breaking", "bullets"],
            "additionalProperties": False,
        },
    )
)

entry = agent.run("Draft the entry.").structured   # decoded JSON (a dict)
```

### Handling a bad answer

```python
from vidbyte import OutputSchemaViolationError

try:
    reply = agent.run("Draft the entry.")
except OutputSchemaViolationError as exc:
    print("Codex answered, but not in the declared shape:")
    print(exc.raw_output)          # the raw final text, for logging or a repair prompt
    print(exc.validation_error)
```

Notes:

- Pydantic schemas are validated against the model locally. Mapping schemas are sent to Codex and decoded as JSON locally, but they are **not** validated against the JSON Schema a second time.
- Only a `completed` turn is validated. An interrupted turn returns `structured=None` with its status set, and does not raise.
- To change or drop the schema for a branch of the conversation, fork with `CodexForkSettings(output_schema=Other)` or `CodexForkSettings(clear_output_schema=True)`.

---

## 5. Custom tools

Pass `@tool` functions, `BaseTool` subclasses, or plain callables in `tools=`. Codex registers them as *dynamic tools* when the thread starts. When the model calls one, **your Python runs in your own process** through the same `ToolExecutor` and `PermissionPolicy` that the direct Vidbyte runtime uses.

### A `@tool` function, sync or async

```python
import httpx

from vidbyte import CodexHarnessAgent, CodexHarnessAgentSettings, tool

FEATURE_FLAGS = {"new-checkout": True, "dark-mode": False}


@tool
def get_feature_flag(flag: str) -> str:
    """Return whether a feature flag is enabled in production."""
    return str(FEATURE_FLAGS.get(flag, "unknown"))


@tool
async def fetch_service_health(service: str) -> str:
    """Return the /health payload for one internal service."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"https://status.internal.example/{service}/health")
        return response.text


agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="oncall",
        system_prompt="Diagnose incidents. Check flags and service health before editing code.",
        tools=(get_feature_flag, fetch_service_health),
    )
)
```

### A `BaseTool` subclass with explicit permissions

```python
from vidbyte import BaseTool, CodexHarnessAgent, CodexHarnessAgentSettings, ToolPermission
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


class CreateTicketTool(BaseTool):
    """Opens a tracker ticket. It writes to an external system."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="create_ticket",
            description="Open a tracker ticket for follow-up work that is out of scope for this change.",
            parameters=(
                ToolParameter(name="title", type="string", description="One-line summary.", required=True),
                ToolParameter(name="body", type="string", description="Details and repro steps.", required=True),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        ticket_id = "TCK-1042"  # call your tracker's API here
        return ToolResult.success(self.name, f"Created {ticket_id}: {call.arguments['title']}")


agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="implementer",
        system_prompt="Implement the change; file tickets for anything out of scope.",
        tools=(CreateTicketTool(),),
        # The default policy allows SAFE and READ only. Allow WRITE explicitly:
        tool_permission_policy=PermissionPolicy(
            allowed=frozenset({ToolPermission.SAFE, ToolPermission.READ, ToolPermission.WRITE})
        ),
    )
)
```

### Better descriptions the model can read

`@tool` builds the schema from the function signature. Use `customize()` to give the model clearer wording without changing how the tool runs:

```python
lookup = get_feature_flag.customize(
    description="Check a production feature flag before assuming a code path is live.",
    parameter_descriptions={"flag": "Flag key, e.g. 'new-checkout'."},
)
# tools=(lookup,)
```

Rules and limits:

- Tool names must match `^[A-Za-z0-9_-]+$`, be at most 128 characters, and must not be `mcp` or start with `mcp__`. These are checked when the agent is constructed.
- Tools need `CodexClientSettings(experimental_api=True)`. That is the default. Setting it to `False` while passing tools fails at construction.
- A call the policy denies goes back to the model as a failed tool result. It does not raise in your code.
- Tool calls run one at a time. A call still running after **300 seconds** is cancelled and reported to the model as a failure.
- Codex registers tools **only when a thread starts**. A resumed `thread_id` or a fork keeps the tools the thread started with, so changing `tools=` has no effect on an existing thread.
- Codex's built-in shell and file tools are separate from these. Codex still owns them, and the [sandbox](#3-sandbox-and-approval-presets) governs them.

---

## 6. Middleware

Codex runs its own loop, so Vidbyte can enforce middleware only at the **turn boundaries** it controls:

| Hook | Supported | When it runs |
|---|---|---|
| `before_run` | ✅ | Before Codex is started. An abort here costs nothing. |
| `after_run` | ✅ | After the turn finished. An abort here cannot undo the turn. |
| `on_model_error` | ✅ (observe only) | When a turn attempt raised. Its decision is ignored, and the real error is re-raised. |
| `before_iteration`, `before_model_call`, `after_model_response`, `before_tool_call`, `after_tool_call`, `after_iteration` | ❌ | These run inside Codex's loop. A middleware that overrides any of them is **rejected at construction**. |

### A guard that blocks a run before it starts

```python
from vidbyte import (
    AgentMiddleware,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
    MiddlewareContext,
    MiddlewareDecision,
)


class ProtectedPathGuard(AgentMiddleware):
    """Refuses prompts that ask to touch protected paths."""

    name = "protected-path-guard"

    def __init__(self, protected: tuple[str, ...]) -> None:
        self.protected = protected

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        hits = [path for path in self.protected if path in ctx.message]
        if hits:
            return MiddlewareDecision.abort(f"protected paths requested: {hits}")
        return MiddlewareDecision.continue_(metadata={"guard": "passed"})
```

### An audit step and an error observer

```python
import logging

log = logging.getLogger("codex.audit")


class TurnAudit(AgentMiddleware):
    """Logs each turn and tags the reply with a request id."""

    name = "turn-audit"
    fail_closed = False   # an audit bug should never block real work

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        log.info("codex turn start agent=%s request=%s", ctx.agent_name, self.request_id)
        return MiddlewareDecision.continue_(metadata={"request_id": self.request_id})

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        log.info("codex turn done agent=%s request=%s", ctx.agent_name, self.request_id)
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        log.warning("codex turn failed: %r", ctx.error)
        return MiddlewareDecision.continue_()


agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="guarded-implementer",
        system_prompt="Implement the requested change.",
        middleware=(ProtectedPathGuard(("migrations/", ".github/")), TurnAudit("req-81")),
    )
)
reply = agent.run("Rename the helper in utils/strings.py")
print(reply.metadata["guard"], reply.metadata["request_id"])   # decision metadata merged into the reply
print(reply.metadata["middleware"])                            # pipeline events and event count
```

What each decision does at a Codex boundary:

- `continue_(metadata=...)` continues the run, and the metadata is merged into `reply.metadata`.
- `abort(reason)` raises `CodexAgentError(failure_code="codex.middleware_aborted")`. A fallback model never runs after an abort.
- `retry(...)` and `deny_tool(...)` raise `CodexAgentError(failure_code="codex.middleware_unsupported")`, because nothing in a Codex turn can carry them out. Use [fallback chains](#11-model-fallback-chains) for retries and `tool_permission_policy` for tool denial.
- A `MiddlewareTransform` may carry `metadata`. Its `system`, `provider_messages`, and `model_visible_tool_result` fields raise, because they have no Codex equivalent.
- An exception inside a middleware with `fail_closed = True` (the default) aborts the turn. With `fail_closed = False`, the exception is recorded and the run continues.

Built-in middleware: most of the shipped policies (`ToolPolicyMiddleware`, `TokenBudgetMiddleware`, `RuntimeLimitMiddleware`, `LoopDetectionMiddleware`, `AuditLogMiddleware`, compaction, and others) use inner-loop hooks, so construction rejects them. `ModelRetryMiddleware` and `ExponentialBackoffRetryMiddleware` load, but their retry decision comes from `on_model_error`, which Codex only observes. **They never retry a Codex turn.** Use `fallback=` instead.

---

## 7. Vidbyte context translation

Vidbyte context is re-rendered on every `run()`/`arun()` from the objects you pass, so edits to a `ContextManager` between turns show up on the next turn. It is placed at the turn boundary. Vidbyte cannot write into Codex's hidden prompt or saved history.

| Vidbyte source | Where it lands in the Codex turn |
|---|---|
| `system_prompt` | Codex developer instructions |
| Manager primitives at `TOP_OF_CONTEXT` / `END_OF_CONTEXT` | Appended to the developer instructions, in zone order |
| `additional_context`, unmanaged `manager.add(...)` items, per-turn `context_items` | Text blocks before the current input |
| Primitives at `TOP_OF_CONVERSATION` | Text before the current input |
| Primitives at `END_OF_CONVERSATION`, `manager.recite(...)` | Text after the current input |
| `CodexContextPlacement` anchors | Text just before or after the turn's image or skill items |
| `ContextManager(metadata=...)` | Merged into `reply.metadata` (per-turn input metadata wins) |

### Static rules and a live, editable context

```python
from vidbyte import (
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
    ContextManager,
    ContextWindowPlacement,
    GitDiffContextItem,
    TaskContextItem,
    TextContextItem,
)

manager = ContextManager(metadata={"repo": "payments-api"})
manager.upsert(
    TextContextItem(
        title="House rules",
        content="Use structured logging. No new dependencies without approval.",
        primitive_id="house-rules",
        primitive_frozen=True,          # cannot be overwritten later
    ),
    placement=ContextWindowPlacement.TOP_OF_CONTEXT,
)
manager.upsert(
    TaskContextItem(
        goal="Add idempotency keys to POST /charges",
        next_steps=("add column", "add check"),
        primitive_id="task",                                 # upsert() needs a stable id
    ),
    placement=ContextWindowPlacement.END_OF_CONVERSATION,   # rendered right after the prompt
)

agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="payments",
        system_prompt="You maintain the payments API.",
        additional_context="The main branch deploys automatically; keep changes small.",
        context_manager=manager,
    )
)

agent.run("Start on the task.")

# Between turns, update the managed primitives; the next run renders the new state.
manager.upsert_preserving_placement(                       # same id replaces, placement kept
    TaskContextItem(
        goal="Add idempotency keys to POST /charges",
        status="in_progress",
        completed=("add column",),
        next_steps=("add check", "write tests"),
        primitive_id="task",
    )
)
manager.upsert(
    GitDiffContextItem(diff="--- a/models.py\n+++ b/models.py\n+idempotency_key = ...", primitive_id="current-diff"),
    placement=ContextWindowPlacement.TOP_OF_CONVERSATION,
)
agent.run("Continue.")
```

### Per-turn context without a manager

```python
from vidbyte import AgentInput, DocumentContextItem, MemoryContextItem

agent.run(
    AgentInput(
        prompt="Update the retry logic to match the spec.",
        context_items=(
            DocumentContextItem(source="docs/retry-spec.md", content="Retry 3x with jitter; never retry 4xx."),
            MemoryContextItem(content="Last time, the flaky test was test_backoff_ceiling."),
        ),
        metadata={"trace_id": "abc123"},
    )
)
```

### Anchoring context next to a screenshot or skill

```python
from vidbyte import (
    CodexContextAnchor,
    CodexContextPlacement,
    CodexLocalImageInput,
    CodexRunInput,
    CodexTextInput,
    ContextManager,
    TextContextItem,
)

notes = ContextManager()
notes.upsert(
    TextContextItem(title="Screenshot notes", content="Red box = overflow. Ignore the cursor.", primitive_id="shot-notes")
)

agent.run(
    CodexRunInput(
        items=(CodexTextInput("Fix the layout bug."), CodexLocalImageInput("./bug.png")),
        context_manager=notes,
        context_placements=(CodexContextPlacement("shot-notes", CodexContextAnchor.AFTER_IMAGES),),
    )
)
```

### Preview the translated turn without starting Codex

The translators are plain classes, so you can see exactly what Codex would receive. This helps with debugging placements, or with snapshot-testing your prompt assembly offline:

```python
from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.lib.dataclasses.codex import CodexContextTranslationRequest

settings = agent.settings                                   # the already-translated agent settings
run_input = CodexVidbyteTranslator.translate_input("Continue.")
prompt = CodexContextTranslator.translate(
    CodexContextTranslationRequest(
        input=run_input,
        static_context=settings.additional_context,
        context_manager=settings.context_manager,
        context_placements=settings.context_placements,
    )
)

print(settings.system_prompt + "\n\n" + prompt.developer_context)   # Codex developer instructions
for item in prompt.items:                                            # turn input, in order
    print(type(item).__name__, getattr(item, "text", "")[:80])
print(prompt.metadata)                                               # merged into reply.metadata
```

- A request-scoped `context_manager` renders **alongside** the agent's manager. If you pass the *same* manager object at both scopes, it renders once, and request placements override agent placements by primitive id.
- A placement that names a missing primitive, or an anchor with no matching image or skill item, fails before Codex starts. It never falls back to another position silently.
- Removing a primitive changes *future* turns only. Text Codex already saw stays in the thread.
- Context-window algorithms and compaction middleware do **not** run inside Codex's loop. Codex manages its own window.

---

## 8. Multi-turn conversations and resuming threads

A `CodexHarnessAgent` instance remembers its Codex `thread_id`. Every later `run()` on the same instance resumes that thread, so Codex keeps the whole conversation.

```python
agent = CodexHarnessAgent(CodexHarnessAgentSettings(name="pair", system_prompt="Pair-program with me."))

agent.run("Read src/billing/ and explain the invoice flow.")
agent.run("Now add a unit test for the proration branch you described.")   # same thread
print(agent.thread_id)                    # save this to resume later
print(len(agent.history), agent.last_reply.content)
```

Resume a saved thread in a new process, for example after a deploy or on a different worker:

```python
saved_thread_id = "thr_0123"             # the value you stored from agent.thread_id

agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="pair",
        system_prompt="Pair-program with me.",
        thread_id=saved_thread_id,
    )
)
agent.run("Where did we leave off?")
```

- Each `run()` starts a fresh Codex app-server process, opens (or resumes) the thread, runs one turn, and shuts the process down. The conversation lives in Codex's thread storage, not in the Python object.
- `CodexThreadSettings(ephemeral=True)` asks Codex not to persist the thread. Because every turn starts a new app-server and resumes by id, use ephemeral threads for single-turn agents only.
- `agent.history` holds only the `AgentMessage` replies this instance produced. It is not a transcript Codex can reload. `CodexHarnessAgent.session_persistence_supported` is `False`, so do not attach it to `vidbyte.sessions`.
- One instance holds one conversation. Do not call `arun()` concurrently on the same instance. Create one agent per conversation.

---

## 9. Forking a thread to explore alternatives

`fork()`/`afork()` creates a native Codex branch from the agent's current thread and returns a **new agent** bound to it. The parent is unchanged.

```python
import asyncio

from vidbyte import (
    CodexAgentSettings,
    CodexForkSettings,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
    CodexSandbox,
    CodexThreadSettings,
)


async def main() -> None:
    base = CodexHarnessAgent(
        CodexHarnessAgentSettings(name="designer", system_prompt="Propose and implement designs.")
    )
    await base.arun("Study the caching layer and summarize its weaknesses.")   # a fork needs an existing thread

    lru = await base.afork(CodexForkSettings(name="lru", system_prompt="Implement an LRU-based fix."))
    ttl = await base.afork(
        CodexForkSettings(
            name="ttl",
            system_prompt="Implement a TTL-based fix.",
            metadata={"experiment": "ttl"},
            codex=CodexAgentSettings(thread=CodexThreadSettings(sandbox=CodexSandbox.WORKSPACE_WRITE)),
        )
    )

    a, b = await asyncio.gather(lru.arun("Go."), ttl.arun("Go."))
    for reply in (a, b):
        print(reply.sender, reply.codex.forked_from_thread_id, reply.codex.fork_depth)


asyncio.run(main())
```

- Forking **before** the first successful run raises `CodexAgentError(failure_code="codex.fork_failed")`.
- Any `CodexForkSettings` field you leave unset is inherited from the parent. `clear_context_manager=True` and `clear_output_schema=True` drop the inherited values. `context_placements=()` clears inherited anchors.
- A fork always inherits the parent's `tools` and `tool_permission_policy`, because the native branch keeps the parent's tool definitions.
- Lineage is recorded in `reply.metadata["forked_from_thread_id"]` and `["fork_depth"]`, and mirrored on `reply.codex`.
- If forks write files concurrently in one `cwd`, they can overwrite each other. Give each fork its own worktree through `CodexForkSettings(codex=...)` with a different `cwd`.

---

## 10. Codex subagents

Codex can spawn its own helper agents inside a turn. Configure them with `CodexSubagentSettings`. Vidbyte passes the configuration through and reports the resulting activity.

```python
from vidbyte import (
    CodexAgentSettings,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
    CodexReasoningEffort,
    CodexSubagentSettings,
)

agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="lead",
        system_prompt="Split large tasks and delegate independent parts to subagents.",
        codex=CodexAgentSettings(
            subagents=CodexSubagentSettings(
                max_concurrent_threads=3,
                default_model="gpt-5.4-mini",
                default_reasoning_effort=CodexReasoningEffort.MEDIUM,
                roles={
                    "test-writer": {"description": "Writes focused unit tests for a named module."},
                    "doc-writer": {
                        "description": "Updates docstrings and READMEs.",
                        "config_file": "./.codex/roles/doc-writer.toml",
                    },
                },
            )
        ),
    )
)

reply = agent.run("Add input validation to every public function in src/api/ and document it.")
for item in reply.codex.subagents:          # collabAgentToolCall / subAgentActivity items
    print(item.type, item.fields)
```

- Set `CodexSubagentSettings(enabled=False)` to stop Codex from delegating.
- A role supports only `description` and `config_file`. Role names must not clash with reserved keys such as `enabled`, `max_threads`, and similar.

---

## 11. Model fallback chains

A fallback chain retries a failed turn on another model **from the same provider**. Each attempt is a complete new turn on the same thread. Only the turn's `model` changes. The sandbox, approval mode, and every thread setting stay the same.

```python
from vidbyte import (
    CodexAgentError,
    CodexAgentSettings,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
    CodexTurnSettings,
)
from vidbyte.agents import AgentFallbackSettings

agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="resilient",
        system_prompt="Implement the change.",
        codex=CodexAgentSettings(turn=CodexTurnSettings(model="gpt-5.5")),   # the primary model
        fallback=AgentFallbackSettings(
            models=["gpt-5.4-mini"],
            fallback_on=(CodexAgentError,),   # required: the default filter matches only provider errors
        ),
    )
)

reply = agent.run("Fix the flaky test.")
print(reply.metadata.get("answering_model"))     # which model answered
print(reply.metadata.get("fallback_attempts"))   # CodexFallbackAttempt records (no credentials)
print(reply.metadata.get("failures"))            # failures survived along the way
```

> **Common mistake:** if you leave `fallback_on` at its default, the chain never advances. The default filter covers provider exceptions such as `ProviderRequestError` and `TimeoutError`, and Codex raises `CodexAgentError`.

- The primary model is read from `turn.model` or, if that is empty, `thread.model`. A chain with neither fails at construction.
- Every entry must use the thread's provider (`openai`, or your `thread.model_provider`), because a Codex thread cannot move to another provider. Entries for other providers fail at construction. Run another provider as a separate agent.
- Only `codex.thread_start_failed` and `codex.turn_failed` move to the next model. Translation errors, a missing SDK, middleware aborts, and resume or fork failures raise right away.
- Codex may already have edited files during a failed attempt, and the next model continues from that state on the same thread.

---

## 12. Usage and cost

```python
reply = agent.run("Refactor the parser.")

usage = agent.get_usage()               # UsageRollup for the most recent turn
print(usage.input_tokens, usage.cached_input_tokens, usage.output_tokens, usage.total_tokens)
print(agent.get_cost_usd(), usage.cost_complete)   # local estimate; None when unpriced

print(reply.metadata["usage_rollup"])   # the same rollup, attached to the reply
print(reply.codex.last_usage)           # Codex's native per-turn snapshot
print(reply.codex.usage)                # CUMULATIVE for the whole thread
print(reply.codex.usage_available)      # False means Codex reported nothing, which is not the same as zero
```

- The cost is an **estimate** from Vidbyte's OpenAI rate table. Codex may bill against subscription credits instead. `cost_complete` tells you whether every call was priced.
- Set `turn.model` or `thread.model` so that usage can be priced by model name. A model missing from Vidbyte's OpenAI rate table (`vidbyte.PROVIDER_PRICING["openai"]`) still records tokens, but `cost_usd` is `None`.
- With a custom `thread.model_provider`, no usage is recorded, because no trusted rate exists for it.
- The rollup is reset at the start of each turn. To total several turns, sum the per-turn rollups yourself.

---

## 13. Error handling

Every runtime failure is a `CodexAgentError` with a stable `failure_code` and the `operation` that failed. The original exception is chained as `__cause__`.

```python
from vidbyte import CodexAgentError, OutputSchemaViolationError

try:
    reply = agent.run("Ship it.")
except OutputSchemaViolationError as exc:
    handle_bad_shape(exc.raw_output)
except CodexAgentError as exc:
    if exc.failure_code == "codex.sdk_unavailable":
        raise SystemExit('pip install "vidbyte-sdk[codex]"') from exc
    if exc.failure_code == "codex.middleware_aborted":
        notify_policy_block(exc)
    else:
        for failure in agent.failures:   # canonical Failure records from this turn
            print(failure.code, failure.phase, failure.severity, failure.summary)
        raise
```

| `failure_code` | Meaning | Falls back to the next model? |
|---|---|---|
| `codex.sdk_unavailable` | `openai-codex` is not installed, or the installed version is incompatible | No |
| `codex.vidbyte_translation_failed` | Settings, input, or context could not be translated (bad input, unsupported middleware, bad tool name, missing anchor) | No |
| `codex.content_translation_failed` | The Codex SDK rejected the translated input or settings | No |
| `codex.thread_start_failed` | The app-server or thread could not start | Yes |
| `codex.turn_failed` | The turn raised inside Codex | Yes |
| `codex.thread_resume_failed` | The saved `thread_id` could not be resumed | No |
| `codex.fork_failed` | The fork precondition or native fork failed | No |
| `codex.response_invalid` | Codex completed without a usable final response | No |
| `codex.middleware_aborted` | A middleware returned `abort` | No |
| `codex.middleware_unsupported` | A middleware returned a decision Codex cannot carry out | No |

Construction errors come earlier. Invalid settings raise `ConfigurationError` from the settings dataclass itself. Problems found while translating to Codex, such as an unsupported middleware hook, a bad tool name, or `experimental_api=False` with tools, raise `CodexAgentError(failure_code="codex.vidbyte_translation_failed")` from `CodexHarnessAgent(...)`, with the `ConfigurationError` as the cause. A fallback chain Codex cannot reach raises `ConfigurationError` directly.

Cancellation (`asyncio.CancelledError`) is never wrapped. Cancelling an `arun()` task cancels the turn and shuts the app-server down.

---

## 14. Composition: pipelines and parallel fan-out

`CodexHarnessAgent` is not a `BaseAgent`, so a pipeline cannot use it directly as a stage. Wrap it in a small `BasePipeline`. Any pipeline accepts a `BasePipeline` as a stage.

```python
from vidbyte import CodexHarnessAgent, CodexHarnessAgentSettings, SequentialPipeline
from vidbyte.pipelines.base import BasePipeline


class CodexStage(BasePipeline):
    """Runs one Codex turn as a string-in, string-out pipeline stage."""

    def __init__(self, agent: CodexHarnessAgent) -> None:
        self.agent = agent

    async def run(self, prompt: str) -> str:
        return (await self.agent.arun(prompt)).content


implement = CodexStage(CodexHarnessAgent(CodexHarnessAgentSettings(name="impl", system_prompt="Implement it.")))
review = CodexStage(CodexHarnessAgent(CodexHarnessAgentSettings(name="review", system_prompt="Review the change above.")))

pipeline = SequentialPipeline([implement, review])   # mix freely with ordinary BaseAgent stages
result = pipeline.run_sync("Add pagination to GET /users.")
```

To fan out independent tasks, run separate agents concurrently. Give each one its own `cwd` if they write files:

```python
import asyncio

from vidbyte import (
    CodexAgentSettings,
    CodexClientSettings,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
)


def worker(name: str, cwd: str) -> CodexHarnessAgent:
    return CodexHarnessAgent(
        CodexHarnessAgentSettings(
            name=name,
            system_prompt="Complete exactly the assigned task.",
            codex=CodexAgentSettings(client=CodexClientSettings(cwd=cwd)),
        )
    )


async def fan_out() -> None:
    jobs = {
        "api": ("Add rate limiting to the API.", "/work/wt-api"),
        "web": ("Add a loading skeleton to the dashboard.", "/work/wt-web"),
    }
    replies = await asyncio.gather(*(worker(n, cwd).arun(task) for n, (task, cwd) in jobs.items()))
    for reply in replies:
        print(reply.sender, reply.codex.status)


asyncio.run(fan_out())
```

---

## 15. Using it from an async web app

```python
from fastapi import FastAPI
from pydantic import BaseModel

from vidbyte import CodexAgentError, CodexHarnessAgent, CodexHarnessAgentSettings

app = FastAPI()
threads: dict[str, str] = {}   # conversation id -> Codex thread id (use a real store in production)


class Ask(BaseModel):
    conversation_id: str
    prompt: str


@app.post("/ask")
async def ask(body: Ask) -> dict:
    agent = CodexHarnessAgent(                           # one lightweight agent per request
        CodexHarnessAgentSettings(
            name="assistant",
            system_prompt="Answer questions about this codebase.",
            thread_id=threads.get(body.conversation_id, ""),
        )
    )
    try:
        reply = await agent.arun(body.prompt)            # never agent.run() inside the event loop
    except CodexAgentError as exc:
        return {"error": exc.failure_code}
    threads[body.conversation_id] = agent.thread_id
    return {"answer": reply.content, "cost_usd": agent.get_cost_usd()}
```

Constructing an agent is cheap. Settings are validated, but no process starts until `arun()`. Custom tool coroutines run on the request's event loop.

---

## 16. Custom provider, binary, and environment

```python
import os

from vidbyte import (
    CodexAgentSettings,
    CodexClientSettings,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
    CodexThreadSettings,
)

agent = CodexHarnessAgent(
    CodexHarnessAgentSettings(
        name="gateway-agent",
        system_prompt="Implement the change.",
        codex=CodexAgentSettings(
            client=CodexClientSettings(
                codex_bin="/opt/codex/bin/codex",                        # pin a specific Codex build
                env={"OPENAI_API_KEY": os.environ["GATEWAY_API_KEY"]},   # never hard-code secrets
                config_overrides=("sandbox_workspace_write.network_access=true",),
                client_name="my-platform",
            ),
            thread=CodexThreadSettings(
                model_provider="my-gateway",          # a provider defined in your Codex config
                model="my-org/codex-large",
                service_name="billing-bot",
                config={"model_verbosity": "low"},    # JSON-compatible thread config
            ),
        ),
    )
)
```

- `config_overrides` and `launch_args_override` are passed to the Codex process as given, so check them yourself.
- With a custom `model_provider`, usage is not priced (see [recipe 12](#12-usage-and-cost)), and fallback entries must name that same provider.

---

## 17. Reading the result

`run()` returns a frozen `AgentMessage`:

```python
reply = agent.run("Explain the build.")

reply.sender, reply.recipient       # agent name, and "user" or your CodexRunInput.recipient
reply.content                       # final text ("" for an interrupted turn)
reply.structured                    # validated output_schema value, or None
reply.metadata                      # provider, provider_item_count, your metadata, usage_rollup,
                                    # failures / fallback_attempts / answering_model when present,
                                    # middleware decision metadata and the "middleware" event log

codex = reply.codex                 # CodexMessageData: typed native data
codex.thread_id, codex.turn_id, codex.status          # status: "completed", "interrupted", ...
codex.started_at, codex.completed_at, codex.duration_ms
codex.error                         # CodexTurnError(message, additional_details, codex_error_info) or None
for item in codex.items:            # commands, file changes, tool calls, messages, ...
    print(item.type, item.fields)   # private reasoning content is never included
```

Item payloads include only item types Vidbyte has reviewed. An unknown item type keeps its `id` and `type`, and its `fields` is left empty.

---

## 18. What translates and what doesn't

| Vidbyte feature | Codex support |
|---|---|
| `system_prompt`, `additional_context`, `ContextManager`, `context_items` | ✅ Rendered at the turn boundary ([recipe 7](#7-vidbyte-context-translation)) |
| `output_schema` (Pydantic or mapping) | ✅ ([recipe 4](#4-structured-outputs)) |
| `@tool`, `BaseTool`, callables, `PermissionPolicy` | ✅ As Codex dynamic tools, registered at thread start ([recipe 5](#5-custom-tools)) |
| Middleware `before_run`, `after_run`, `on_model_error` | ✅ ([recipe 6](#6-middleware)) |
| Inner-loop middleware hooks, compaction middleware | ❌ Rejected at construction |
| `AgentFallbackSettings` | ✅ Same provider only, with `fallback_on=(CodexAgentError,)` ([recipe 11](#11-model-fallback-chains)) |
| Usage and cost accounting | ✅ OpenAI-priced estimate ([recipe 12](#12-usage-and-cost)) |
| Forks | ✅ Native Codex thread forks ([recipe 9](#9-forking-a-thread-to-explore-alternatives)) |
| Pipelines | ⚠️ Through a `BasePipeline` wrapper ([recipe 14](#14-composition-pipelines-and-parallel-fan-out)) |
| `vidbyte.sessions` durable sessions | ❌ `session_persistence_supported = False`; persist `thread_id` instead |
| Vidbyte iteration limits and per-tool middleware | ❌ Codex owns the loop; use sandbox, approval mode, and `tool_permission_policy` |

---

## Blast Radius

The public surface is re-exported from `vidbyte.agents.codex`, `vidbyte.agents`, and the root `vidbyte` namespace. The settings, request, and result records live in `vidbyte/lib/dataclasses/codex.py`. Enums live in `vidbyte/lib/enums/codex.py`, and wire constants and failure classification in `vidbyte/lib/constants/codex.py`. The adapter reuses shared layers without changing them: `vidbyte/context` for rendering, `vidbyte/tools` (`Tools`, `ToolExecutor`, `ToolsFormatter.to_codex_tool`) for tools, `vidbyte/middleware` (`MiddlewarePipeline`) for hooks, `vidbyte/agents/fallback.py` for the switch policy, `vidbyte/agents/pricing` for usage, and `vidbyte/providers/output_schema.py` for schemas. `openai-codex` is an optional dependency and is imported only inside the transport. The tool bridge touches private `openai-codex` client attributes that are valid only under the `<0.148` pin.

## Non-Goals

- Do not reimplement Codex's agent loop, sandbox, or approvals here. Codex owns them.
- Do not add middleware hooks that Vidbyte cannot enforce at a turn boundary. An unenforceable hook must fail at construction.
- Do not switch models or providers in the middle of a turn. A running turn may already have edited files.
- Do not persist Codex conversations through `vidbyte.sessions`. The thread id is the durable handle.
- Do not serialize private reasoning content or unreviewed item payloads into results.

## File Index

- `__init__.py` - Re-exports the public Codex surface: the agent, settings, input records, and enums. Keep it in step with `vidbyte/agents/__init__.py` and the root exports.
- `agent.py` - `CodexHarnessAgent`, the facade. It translates input and context, runs middleware around the turn, walks the fallback chain, records usage and failures, and builds the `AgentMessage`. Open it to change the turn lifecycle.
- `config.py` - `CodexVidbyteTranslator` (Vidbyte settings and input into validated Codex requests) and `CodexContentTranslator` (validated records into `openai-codex` keyword arguments). Open it to add a Codex setting.
- `context.py` - `CodexContextTranslator`. It renders `ContextManager` zones, conversation placements, unmanaged items, anchors, and metadata into turn input. Open it to translate another context surface.
- `failures.py` - Sorts `CodexAgentError` codes into canonical `Failure` records and keeps the per-turn failure ledger. Open it for failure vocabulary changes.
- `fallback.py` - `CodexFallbackCoordinator`. It resolves the chain, rejects providers the thread cannot reach, and overrides only the turn model for each attempt.
- `fork.py` - `CodexFork`. It checks fork preconditions, merges child settings, records lineage, and runs the native thread fork.
- `metrics.py` - `CodexMetricsTranslator`. It files one priced usage record per turn from Codex's per-turn usage snapshot.
- `middleware.py` - `CodexMiddlewareValidator`, which rejects inner-loop hooks, and `CodexMiddlewareRunner`, which runs `before_run`, `after_run`, and `on_model_error` and applies their decisions.
- `result.py` - `CodexResultSerializer` (SDK result into typed snapshot) and `CodexResultTranslator` (snapshot into `AgentMessage`, with structured-output validation).
- `tools.py` - `CodexToolTranslator`, `CodexToolBridge`, and `CodexToolCallHandler`. They register Vidbyte tools as Codex dynamic tools and answer tool calls on the agent's event loop.
- `transport.py` - `CodexTransport`. It owns the app-server process and the thread start, resume, turn, and fork operations, and it is the only place `openai-codex` is imported.

## Logs

- 2026-09-18 - Added this cookbook README after auditing the adapter at `d8483257`, against `openai-codex>=0.147,<0.148`. Documented that the fallback chain needs `fallback_on=(CodexAgentError,)`, that retry built-ins load but never retry, and that pipelines need a `BasePipeline` wrapper, because none of these is obvious from the public signatures.
