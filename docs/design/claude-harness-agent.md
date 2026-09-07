# Design Doc: Claude Harness Agent

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

`ClaudeHarnessAgent` is a Vidbyte-shaped facade over Anthropic's provider-owned
Claude Agent SDK loop, built as the sibling of the existing `CodexHarnessAgent`.
It accepts Vidbyte abstractions — a system prompt, a live `ContextManager`, an
`output_schema`, capabilities, metadata — translates them into validated
`ClaudeAgentOptions`, runs one provider turn through `claude_agent_sdk.query()`,
and normalizes the resulting message stream into a typed `AgentMessage` carrying
a `ClaudeMessageData` record. It supports session resume across turns and native
session forking. Claude owns its own planning, tool execution, permissions,
compaction, and subagents; Vidbyte owns the settings contract, the context
rendering, the result vocabulary, and the failure taxonomy.

---

## 2. Goals & Non-Goals

### Goals

- Ship a `vidbyte/agents/claude/` adapter that mirrors the `vidbyte/agents/codex/`
  collaborator decomposition: facade, transport, config translation, context
  translation, result translation, fork.
- Translate every Vidbyte construction abstraction the Codex adapter translates:
  `system_prompt`, `additional_context`, `context_manager`, `output_schema`,
  `description`, `capabilities`, `metadata`, plus provider session identity.
- Expose the declarative half of the Claude Agent SDK as strictly validated frozen
  dataclasses grouped by concern: process, model, loop bounds, tools/permissions,
  session, subagents, sandbox, plugins.
- Support `run`/`arun`, session start, session resume, and native session fork with
  inherit/replace/clear override semantics.
- Normalize the provider message stream into typed records, excluding thinking
  content at the serialization boundary, and publish `total_cost_usd` alongside
  token counters.
- Classify every provider failure through `FailureCode` with a `claude.` prefix and
  a `ClaudeAgentError` carrying the full A003 diagnostic packet.
- Keep the SDK an optional extra: `pip install "vidbyte-sdk[claude]"`. The base
  install must import and run with `claude-agent-sdk` absent.
- Add `skills/claude-harness-roadmap/` recording every deferred feature as a stable,
  checkable task ID, mirroring `skills/codex-harness-roadmap/`.

### Non-Goals

- Callback-shaped controls: `can_use_tool`, `hooks`. Deferred (see 14.2).
- In-process SDK MCP tools via `@tool` / `create_sdk_mcp_server()`. Deferred.
- A persistent `ClaudeSDKClient` connection, and with it `interrupt()`,
  `set_model()`, `set_permission_mode()`, `rewind_files()`, `stop_task()`, and the
  MCP status/reconnect/toggle methods. Deferred (see 14.1).
- Streaming output (`include_partial_messages`), hook-event forwarding
  (`include_hook_events`), and `forward_subagent_text`.
- File checkpointing (`enable_file_checkpointing`).
- `SessionStore` / `session_store_flush` external session persistence.
- The session-registry functions: `list_sessions()`, `get_session_messages()`,
  `get_session_info()`, `rename_session()`, `tag_session()`.
- Streaming input mode (`AsyncIterable[dict]`) and therefore image input.
- Wiring `ClaudeHarnessAgent` into `BaseAgent`, `MultiAgent`, `Harness`,
  `vidbyte.sessions`, `vidbyte.trace`, or the pricing/speed trackers. The Codex
  adapter is not wired into them either; parity is deliberate.
- Any change to `vidbyte/agents/codex/` or to shared code paths the Codex adapter
  depends on, beyond additive enum members and an additive `AgentMessage` field.

---

## 3. Background & Context

**Why now.** `CodexHarnessAgent` landed in PR #409/#411 and established the
repository's pattern for a provider-owned harness adapter: a thin public facade,
constructor-time Vidbyte translation, a separate provider serialization layer,
lifecycle collaborators, and frozen request/result records in
`vidbyte/lib/dataclasses/`. Vidbyte's runtime-primitives direction requires more
than one native agent runtime behind one Vidbyte-shaped surface. Claude is the
second.

**Current state.** `skills/claude-agent-sdk-translation/SKILL.md` and its
`references/feature-matrix.md` already inventory the entire Claude Agent SDK
surface and assign each feature a disposition (`native`, `translated`,
`supervised`, `observe_only`, `emulated`, `unsupported`). That skill states that
implementation files must not be created until an implementation request and a new
design document authorize them. This document is that authorization. No adapter
code exists today; `skills/runtime-primitives/references/claude-agent-sdk.md`
contains only a control inventory.

**Constraints.**

- The package is `claude-agent-sdk`, latest **0.2.152**, `requires-python >=3.10`,
  depending on `anyio`, `jsonschema`, `mcp>=1.23,<3`, `sniffio`. Vidbyte requires
  `>=3.11`, so the SDK's floor is not binding.
- The SDK spawns the bundled Claude Code CLI as a subprocess. A missing CLI is a
  distinct, common, and diagnosable failure that must not look like a model error.
- Anthropic's branding terms forbid third-party products naming themselves "Claude
  Code" or "Claude Code Agent". The package, folder, class, and failure prefix all
  use "Claude".
- Anthropic's terms require API-key authentication for third-party products;
  claude.ai login is not offered. Credentials are supplied through the process
  environment and never persisted into settings, metadata, or trace records.
- `lint/run.py` is a blocking ratchet currently at PASS. New files are held to the
  full A001 header, A002 intent comments, A003 error packets, A006 layering, A007
  operational constants, S005/S027 immutable defaults, S007 annotations, S008/S024
  complexity bounds, S015 export integrity, S016/S017 typed non-disclosing errors,
  and S019 cancellation propagation.

---

## 4. Requirements

### Functional Requirements

1. `ClaudeHarnessAgent(settings: ClaudeHarnessAgentSettings)` resolves every shared
   Vidbyte abstraction at construction, before any subprocess starts, and raises
   `ClaudeAgentError(failure_code="claude.vidbyte_translation_failed")` when that
   resolution fails.
2. `await agent.arun(ClaudeRunInput)` executes exactly one provider query and
   returns an `AgentMessage` whose `.claude` field is a populated
   `ClaudeMessageData`.
3. `agent.run(ClaudeRunInput)` runs `arun` via `asyncio.run` outside an event loop
   and raises `ClaudeAgentError(failure_code="claude.query_failed",
   operation="run_sync_guard")` inside one.
4. The first successful run records the provider `session_id` on the agent; every
   subsequent run passes it as `resume` so the conversation continues.
5. A run that fails **after** the provider emitted a `ResultMessage` still records
   that message's `session_id`, so the caller can resume after `error_max_turns` or
   `error_max_budget_usd`.
6. The message stream is fully drained or explicitly closed on every exit path,
   including cancellation, so no CLI subprocess is leaked.
7. `asyncio.CancelledError` propagates unwrapped from every adapter operation.
8. `agent.fork(ClaudeForkSettings)` returns a new `ClaudeHarnessAgent` whose session
   settings carry `resume=<parent session_id>` and `fork_session=True`, and whose
   own `session_id` is empty until its first successful run. `afork` is the async
   alias and performs no awaitable work.
9. Forking before the parent has a session id raises
   `ClaudeAgentError(failure_code="claude.fork_failed",
   operation="fork_precondition")`.
10. Fork overrides distinguish inherit (`None` / `""`), replace (a value), and clear
    (`clear_context_manager`, `clear_output_schema`). Setting clear and replace for
    the same field is a `ConfigurationError` at settings construction.
11. A fork deep-copies the parent's `ContextManager` so the child cannot mutate the
    parent's registry, and stamps `forked_from_session_id` and an incremented
    `fork_depth` into child metadata.
12. A live `ContextManager` is rendered on every turn, so primitive edits, additions,
    and removals between turns are reflected. Equal text is never deduplicated.
13. Context supplied at construction and context supplied per-run are both rendered;
    when both name the same manager object it is rendered once.
14. The rendered primitives zone is appended to the system prompt; conversation-zone
    placements render as text before and after the current-turn prompt, and the
    adapter states that this is current-turn text, not insertion into Claude-owned
    history.
15. A declared `output_schema` is emitted as
    `output_format={"type": "json_schema", "schema": <draft-07 schema>}`, and a
    Pydantic-derived schema is downgraded from draft 2020-12 to draft-07 before it
    reaches the SDK.
16. A run whose result subtype is `success` **and** whose `structured_output` is
    present yields a validated instance on `AgentMessage.structured`. Any other
    combination, when a schema was declared, raises `OutputSchemaViolationError`.
17. Only `text`, `tool_use`, and `tool_result` blocks become `ClaudeItem` records.
    `thinking` blocks are excluded at the serialization boundary and never copied.
18. `ClaudeUsage` carries `input_tokens`, `output_tokens`,
    `cache_read_input_tokens`, `cache_creation_input_tokens`, and `total_cost_usd`.
    Absent provider values remain distinguishable from zero via `usage_available`.
19. Provider failures map to distinct codes: `claude.sdk_unavailable`,
    `claude.cli_not_found`, `claude.connection_failed`, `claude.process_failed`,
    `claude.vidbyte_translation_failed`, `claude.content_translation_failed`,
    `claude.query_failed`, `claude.session_resume_failed`, `claude.fork_failed`,
    `claude.response_invalid`.
20. Importing `vidbyte`, `vidbyte.agents`, or `vidbyte.agents.claude` succeeds with
    `claude-agent-sdk` absent. The SDK is imported lazily inside the transport, and
    its absence raises `claude.sdk_unavailable`.
21. `ClaudeSessionSettings` rejects `continue_conversation` together with `resume`,
    and rejects `fork_session` without either.
22. `ClaudeToolSettings` rejects a tool name present in both `allowed_tools` and
    `disallowed_tools`.
23. `skills/claude-harness-roadmap/` records every deferred capability from Section
    2's non-goals and the existing feature matrix as a stable checkable task ID with
    a surface label, an implementation seam, and completion evidence.

### Non-Functional Requirements

- **Performance.** Adapter overhead per turn is bounded by context rendering and
  option construction; both are O(context primitives) with no network or disk I/O.
  Provider latency dominates. The per-turn CLI subprocess spawn is an accepted cost
  of the `query()` mode and is recorded as a known limitation.
- **Scalability.** No shared mutable state between agents. `ClaudeStreamAccumulator`
  is per-run and never escapes the transport. Independent agents run concurrently;
  one agent's `arun` is not re-entrant and is not made so.
- **Security.** No credential ever enters `ClaudeAgentSettings`, `AgentMessage`,
  metadata, or an error message. `ClaudeProcessSettings.env` is a caller-supplied
  passthrough documented as unredacted. Error messages carry a failure code, an
  operation name, and `type(exc).__name__` — never provider exception text (S017).
- **Observability.** Every failure carries `failure_code` and `operation`.
  `ClaudeMessageData` exposes `num_turns`, `duration_ms`, `duration_api_ms`,
  `total_cost_usd`, `terminal_reason`, and `subtype` for downstream accounting.
- **Reliability.** Cancellation is never converted into a provider error. Every
  operation that opens a stream closes it. Result normalization failures are
  distinguishable from query failures.

---

## 5. High-Level Design

The adapter is six collaborators behind one facade, matching the Codex
decomposition file-for-file so a reader who knows one knows the other.

`ClaudeVidbyteTranslator` runs once at construction. It validates cross-record
provider compatibility, strips and normalizes Vidbyte strings, and resolves the
`output_schema` into an annotated draft-07 JSON Schema. Nothing provider-specific
is constructed here, so an invalid Vidbyte configuration can never launch a CLI
subprocess.

`ClaudeContextTranslator` runs once per turn. It renders the live `ContextManager`
into a `ClaudePrompt`: a `developer_context` string appended to the system prompt,
plus text placed before and after the current-turn prompt. Because Claude's
prompt is a single string, the translator concatenates rather than positions —
there are no native input items to anchor around.

`ClaudeContentTranslator` converts validated Claude records into
`ClaudeAgentOptions` keyword arguments, dropping unset sentinels. It is the only
class that names SDK argument keys.

`ClaudeTransport` owns the entire lifetime of one `query()` call. It builds
options, opens the async iterator, drains it into a `ClaudeStreamAccumulator`,
and closes it in a `finally` block. It classifies exceptions into failure codes and
lets `CancelledError` pass through.

`ClaudeResultSerializer` freezes the accumulator into an immutable
`ClaudeRunResult`. `ClaudeResultTranslator` validates structured output at the
Vidbyte boundary and builds the public `AgentMessage`.

`ClaudeFork` is pure settings math with no transport. Claude has no fork wire call,
so a fork is a child whose session settings carry `resume` plus `fork_session`.

```
ClaudeHarnessAgent  (agent.py)
   |  construction: ClaudeVidbyteTranslator      (config.py)
   |  per turn:     ClaudeContextTranslator      (context.py)
   v
ClaudeTransport     (transport.py)
   |  options via  ClaudeContentTranslator       (config.py)
   |  query() -> AsyncIterator[Message]
   |  drained by   ClaudeStreamAccumulator       (result.py)
   v
ClaudeRunResult  ->  ClaudeResultTranslator      (result.py)
   v
AgentMessage(.claude=ClaudeMessageData, .structured=<validated instance>)

ClaudeHarnessAgent.fork() -> ClaudeFork (fork.py) -> child settings
   (resume=parent session_id, fork_session=True, session_id="")
```

**Key decisions.**

1. **`query()` per turn, not a held-open `ClaudeSDKClient`.** This mirrors the Codex
   transport's bounded lifecycle, keeps `session_persistence_supported = False`
   honest, and avoids adding an `aclose()` to a facade that has none. It costs one
   subprocess spawn per turn and forfeits `interrupt()`. Both collaborators sit
   behind `ClaudeTransport.run()`, so a later persistent mode is a swap, not a
   rewrite.
2. **Lazy fork.** Claude materializes a fork on the child's first query. Eagerly
   confirming a fork id would require running a throwaway query, which costs money
   and injects a junk turn into the child's history.
3. **No input-item model.** Claude's prompt is a string. The Codex adapter's five
   input dataclasses, `CodexInputType`, `CodexContextAnchor`, and the anchor index
   arithmetic have no counterpart and are not ported.
4. **Settings grouped by concern, not by lifecycle.** Codex splits client/thread/turn
   because its SDK does. Claude has one flat `ClaudeAgentOptions`, so the grouping
   is process / model / loop / tools / session / subagents / sandbox / plugins.

---

## 6. Detailed Design

### 6.1 Claude option vocabularies

**File(s):** `vidbyte/lib/enums/claude.py`
**Type:** New file

#### What it does

Defines the closed provider vocabularies referenced by validated settings, so no
Claude wire string is written inline anywhere else in the adapter.

#### Interface / API

```python
class ClaudePermissionMode(str, Enum):
    PROVIDER_DEFAULT = ""
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    DONT_ASK = "dontAsk"
    BYPASS_PERMISSIONS = "bypassPermissions"
    AUTO = "auto"


class ClaudeEffortLevel(str, Enum):
    PROVIDER_DEFAULT = ""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class ClaudeSettingSource(str, Enum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class ClaudeThinkingMode(str, Enum):
    PROVIDER_DEFAULT = ""
    ADAPTIVE = "adaptive"
    ENABLED = "enabled"
    DISABLED = "disabled"


class ClaudeThinkingDisplay(str, Enum):
    PROVIDER_DEFAULT = ""
    SUMMARIZED = "summarized"
    OMITTED = "omitted"


class ClaudeSystemPromptKind(str, Enum):
    TEXT = "text"
    PRESET = "preset"
    FILE = "file"


class ClaudeResultSubtype(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    ERROR_MAX_TURNS = "error_max_turns"
    ERROR_MAX_BUDGET_USD = "error_max_budget_usd"
    ERROR_MAX_STRUCTURED_OUTPUT_RETRIES = "error_max_structured_output_retries"


class ClaudeBlockType(str, Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
```

#### Logic / Algorithm

1. Every option enum carries a `PROVIDER_DEFAULT = ""` sentinel so an unset value is
   representable without `None`, matching `vidbyte/lib/enums/codex.py`.
2. `ClaudeContentTranslator._without_empty` drops those sentinels before the SDK
   call, so the provider applies its own default.
3. `ClaudeSettingSource` has no sentinel: an empty tuple already means "declare
   nothing", and each member is a real provider value.
4. `ClaudeBlockType.THINKING` is declared so `result.py` can name the block it
   deliberately excludes rather than matching a bare string.

#### Edge Cases & Error Handling

- Enum values must match `claude-agent-sdk` 0.2.152 wire values exactly; the file
  header records the pin.
- A provider value added in a later SDK version is absent here; the settings
  dataclass rejects a non-enum value rather than passing an unknown string through.

---

### 6.2 Adapter constants

**File(s):** `vidbyte/lib/constants/claude.py`
**Type:** New file

#### What it does

Holds every shared literal the adapter needs: provider label, optional-extra name,
fork depth counters, the JSON Schema draft identifier, and the block-type
vocabularies.

#### Interface / API

```python
CLAUDE_ROOT_FORK_DEPTH = 0
CLAUDE_NEXT_FORK_DEPTH = 1
CLAUDE_PROVIDER_NAME = "claude"
CLAUDE_SDK_EXTRA = "vidbyte-sdk[claude]"
CLAUDE_SDK_DISTRIBUTION = "claude-agent-sdk"
CLAUDE_JSON_SCHEMA_DRAFT = "http://json-schema.org/draft-07/schema#"
CLAUDE_SCHEMA_DRAFT_KEY = "$schema"
CLAUDE_OUTPUT_FORMAT_TYPE = "json_schema"
CLAUDE_SUPPORTED_BLOCK_TYPES = frozenset({"text", "tool_use", "tool_result"})
CLAUDE_SUBAGENT_TOOL_NAMES = frozenset({"Task", "Agent"})
CLAUDE_RESERVED_SUBAGENT_NAMES = frozenset({"general-purpose", "Task", "Agent"})
CLAUDE_MAX_THINKING_BUDGET_TOKENS = 200_000
CLAUDE_MIN_THINKING_BUDGET_TOKENS = 1_024
```

#### Logic / Algorithm

1. Constants live below the agent modules so every collaborator imports them safely
   under A006 layering.
2. Numeric bounds referenced by more than one `__post_init__` live here, per the
   field guide's "keep reusable validation bounds in the shared constants package".

#### Edge Cases & Error Handling

- N/A — this module holds data only and raises nothing.

---

### 6.3 Settings, input, and result records

**File(s):** `vidbyte/lib/dataclasses/claude.py`
**Type:** New file

#### What it does

Owns every validated boundary for the adapter: provider settings grouped by
concern, the run input, the translated prompt, the fork records, the transport
request records, and the result records. All validation lives in `__post_init__`,
so a constructed instance is provably valid and no collaborator re-checks shape.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ClaudeProcessSettings:
    """Subprocess, filesystem, and configuration-loading controls."""
    cwd: str = ""
    cli_path: str = ""
    settings: str = ""
    add_dirs: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    extra_args: Mapping[str, str] = field(default_factory=dict)
    max_buffer_size: int = 0
    load_timeout_ms: int = 0
    setting_sources: tuple[ClaudeSettingSource, ...] = ()
    user: str = ""


@dataclass(frozen=True, slots=True)
class ClaudeModelSettings:
    """Model selection and reasoning controls."""
    model: str = ""
    fallback_model: str = ""
    effort: ClaudeEffortLevel = ClaudeEffortLevel.PROVIDER_DEFAULT
    thinking_mode: ClaudeThinkingMode = ClaudeThinkingMode.PROVIDER_DEFAULT
    thinking_budget_tokens: int = 0
    thinking_display: ClaudeThinkingDisplay = ClaudeThinkingDisplay.PROVIDER_DEFAULT
    betas: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClaudeLoopSettings:
    """Provider-enforced ceilings on one run."""
    max_turns: int = 0
    max_budget_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class ClaudeToolSettings:
    """Tool availability, permission posture, MCP, and skills."""
    use_claude_code_preset: bool = True
    tools: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    permission_mode: ClaudePermissionMode = ClaudePermissionMode.PROVIDER_DEFAULT
    permission_prompt_tool_name: str = ""
    skills: tuple[str, ...] = ()
    all_skills: bool = False
    mcp_servers: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    strict_mcp_config: bool = False


@dataclass(frozen=True, slots=True)
class ClaudeAgentDefinition:
    """One provider subagent role; SDK field names are camelCase."""
    description: str
    prompt: str
    tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    model: str = ""
    skills: tuple[str, ...] = ()
    max_turns: int = 0
    background: bool = False
    effort: ClaudeEffortLevel = ClaudeEffortLevel.PROVIDER_DEFAULT
    permission_mode: ClaudePermissionMode = ClaudePermissionMode.PROVIDER_DEFAULT


@dataclass(frozen=True, slots=True)
class ClaudeSubagentSettings:
    roles: Mapping[str, ClaudeAgentDefinition] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClaudeSessionSettings:
    """Provider session identity and branch selection."""
    resume: str = ""
    fork_session: bool = False
    continue_conversation: bool = False
    resume_session_at: str = ""


@dataclass(frozen=True, slots=True)
class ClaudeSandboxSettings:
    enabled: bool = False
    allow_network: bool = False
    allowed_domains: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClaudePluginConfig:
    path: str


@dataclass(frozen=True, slots=True)
class ClaudeSystemPromptSettings:
    """How the system prompt reaches the provider."""
    kind: ClaudeSystemPromptKind = ClaudeSystemPromptKind.TEXT
    path: str = ""
    append_to_preset: bool = True
    exclude_dynamic_sections: bool = False


@dataclass(frozen=True, slots=True)
class ClaudeAgentSettings:
    """Complete provider settings grouped by concern."""
    process: ClaudeProcessSettings = field(default_factory=ClaudeProcessSettings)
    model: ClaudeModelSettings = field(default_factory=ClaudeModelSettings)
    loop: ClaudeLoopSettings = field(default_factory=ClaudeLoopSettings)
    tools: ClaudeToolSettings = field(default_factory=ClaudeToolSettings)
    session: ClaudeSessionSettings = field(default_factory=ClaudeSessionSettings)
    subagents: ClaudeSubagentSettings = field(default_factory=ClaudeSubagentSettings)
    sandbox: ClaudeSandboxSettings = field(default_factory=ClaudeSandboxSettings)
    system_prompt: ClaudeSystemPromptSettings = field(default_factory=ClaudeSystemPromptSettings)
    plugins: tuple[ClaudePluginConfig, ...] = ()


@dataclass(frozen=True, slots=True)
class ClaudeHarnessAgentSettings:
    """Validated Vidbyte-facing construction input for one Claude harness agent.

    ``output_schema`` and ``context_manager`` retain unions because their concrete
    forms are existing Vidbyte abstractions that cannot be resolved until the
    construction translator runs.
    """
    name: str
    system_prompt: str
    claude: ClaudeAgentSettings = field(default_factory=ClaudeAgentSettings)
    additional_context: str = ""
    context_manager: ContextManager | None = None
    output_schema: type | Mapping[str, Any] | None = None
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    session_id: str = ""


@dataclass(frozen=True, slots=True)
class ClaudeRunInput:
    """One typed request for a single Claude turn."""
    prompt: str
    recipient: str = "user"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None

    @classmethod
    def text(cls, prompt: str, *, recipient: str = "user") -> ClaudeRunInput: ...


@dataclass(frozen=True, slots=True)
class ClaudePrompt:
    """Translated provider input plus safe Vidbyte message context."""
    user_prompt: str
    recipient: str
    metadata: Mapping[str, Any]
    developer_context: str = ""


@dataclass(frozen=True, slots=True)
class ClaudeContextSource:
    manager: ContextManager | None


@dataclass(frozen=True, slots=True)
class ClaudeRenderedContext:
    developer_context: str = ""
    before_input: tuple[str, ...] = ()
    after_input: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClaudeContextTranslationRequest:
    input: ClaudeRunInput
    static_context: str
    context_manager: ContextManager | None


@dataclass(frozen=True, slots=True)
class ClaudeAgentTranslation:
    settings: ClaudeHarnessAgentSettings
    output_schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ClaudeForkSettings:
    """Validated overrides for one lazy Claude session fork."""
    name: str = ""
    system_prompt: str = ""
    claude: ClaudeAgentSettings | None = None
    additional_context: str | None = None
    context_manager: ContextManager | None = None
    output_schema: type | Mapping[str, Any] | None = None
    description: str | None = None
    capabilities: tuple[str, ...] | None = None
    clear_context_manager: bool = False
    clear_output_schema: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClaudeForkRequest:
    parent: ClaudeHarnessAgentSettings
    parent_session_id: str
    overrides: ClaudeForkSettings


@dataclass(frozen=True, slots=True)
class ClaudeForkResult:
    settings: ClaudeHarnessAgentSettings


@dataclass(frozen=True, slots=True)
class ClaudeUsage:
    """Provider token counters plus the provider's own cost figure."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    total_cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class ClaudeItem:
    """One accumulated content block with its stable type and serialized fields."""
    id: str
    type: str
    fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClaudeRunResult:
    """Native snapshot; the result translator populates ``structured`` after validation."""
    session_id: str
    subtype: str
    terminal_reason: str
    result: str | None
    duration_ms: int | None
    duration_api_ms: int | None
    num_turns: int | None
    usage: ClaudeUsage
    items: tuple[ClaudeItem, ...]
    structured_output: Mapping[str, Any] | None = None
    usage_available: bool = False
    result_available: bool = False
    structured: Any = None


@dataclass(frozen=True, slots=True)
class ClaudeMessageData:
    """Typed Claude result attached to ``AgentMessage.claude``."""
    session_id: str
    subtype: str
    terminal_reason: str
    usage: ClaudeUsage
    items: tuple[ClaudeItem, ...]
    subagents: tuple[ClaudeItem, ...]
    forked_from_session_id: str = ""
    fork_depth: int = CLAUDE_ROOT_FORK_DEPTH
    duration_ms: int | None = None
    duration_api_ms: int | None = None
    num_turns: int | None = None
    usage_available: bool = False
    result: str | None = None
    structured: Any = None


@dataclass(frozen=True, slots=True)
class ClaudeResultTranslationRequest:
    result: ClaudeRunResult
    agent: ClaudeHarnessAgentSettings
    input_metadata: Mapping[str, Any]
    recipient: str


@dataclass(frozen=True, slots=True)
class ClaudeTransportRunRequest:
    session_id: str
    system_prompt: str
    prompt: ClaudePrompt
    settings: ClaudeAgentSettings
    output_schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ClaudeSdkTypes:
    """Lazily imported SDK classes needed by transport and result normalization."""
    query: Callable[..., Any]
    options: type
    assistant_message: type
    system_message: type
    result_message: type
    text_block: type
    thinking_block: type
    tool_use_block: type
    tool_result_block: type
    sdk_error: type
    cli_not_found_error: type
    cli_connection_error: type
    process_error: type
    cli_json_decode_error: type
```

#### Logic / Algorithm

1. Module-private validators `_require_text`, `_optional_text`, `_require_bool`,
   `_require_non_negative_int`, `_is_json_value` mirror
   `vidbyte/lib/dataclasses/codex.py` exactly, so both adapters report identically
   shaped `ConfigurationError` messages.
2. `ClaudeSessionSettings.__post_init__` rejects `continue_conversation` with
   `resume` (ambiguous parent) and `fork_session` without either (nothing to fork).
3. `ClaudeToolSettings.__post_init__` rejects a name in both `allowed_tools` and
   `disallowed_tools`, and rejects `skills` non-empty together with
   `all_skills=True`.
4. `ClaudeModelSettings.__post_init__` requires `thinking_budget_tokens` in
   `[CLAUDE_MIN_THINKING_BUDGET_TOKENS, CLAUDE_MAX_THINKING_BUDGET_TOKENS]` when
   `thinking_mode is ENABLED`, and requires it to be `0` otherwise.
5. `ClaudeSubagentSettings.__post_init__` rejects a role name in
   `CLAUDE_RESERVED_SUBAGENT_NAMES`.
6. `ClaudeSystemPromptSettings.__post_init__` requires `path` when
   `kind is FILE` and forbids it otherwise.
7. `ClaudeForkSettings.__post_init__` rejects clear-and-replace pairs for both the
   context manager and the output schema.
8. `__all__ = [name for name in globals() if name.startswith("Claude")]`, matching
   the Codex module.

#### Edge Cases & Error Handling

- Every violation raises `ConfigurationError` at construction, before any provider
  process exists — the field guide's "validate inherited provider settings before
  creating a native fork" rule applied to every record.
- `ClaudeHarnessAgentSettings.output_schema` and `.context_manager` keep unions; the
  docstring records the exception the field guide requires for structurally
  necessary unions.
- Mappings are stored as given and copied at translation time, never mutated in
  place.

---

### 6.4 Vidbyte and SDK translation

**File(s):** `vidbyte/agents/claude/config.py`
**Type:** New file

#### What it does

Two class-bound helpers with one concern each. `ClaudeVidbyteTranslator` resolves
shared Vidbyte abstractions once at construction. `ClaudeContentTranslator`
converts validated Claude records into SDK keyword arguments and is the only place
that names SDK argument keys.

#### Interface / API

```python
class ClaudeSettingsValidator:
    @staticmethod
    def validate(settings: ClaudeAgentSettings) -> None: ...


class ClaudeVidbyteTranslator:
    def translate_agent(self, settings: ClaudeHarnessAgentSettings) -> ClaudeAgentTranslation: ...
    def output_schema(self, schema: type | Mapping[str, Any] | None) -> Mapping[str, Any]: ...
    @staticmethod
    def system_prompt(value: str) -> str: ...
    @staticmethod
    def additional_context(value: str) -> str: ...


class ClaudeContentTranslator:
    @classmethod
    def option_kwargs(cls, system_prompt: str, session_id: str, settings: ClaudeAgentSettings, output_schema: Mapping[str, Any]) -> dict[str, Any]: ...
    @classmethod
    def system_prompt_value(cls, system_prompt: str, settings: ClaudeSystemPromptSettings) -> str | dict[str, Any]: ...
    @classmethod
    def agent_definitions(cls, settings: ClaudeSubagentSettings) -> dict[str, dict[str, Any]]: ...
    @classmethod
    def thinking_config(cls, settings: ClaudeModelSettings) -> dict[str, Any] | None: ...
    @classmethod
    def output_format(cls, schema: Mapping[str, Any]) -> dict[str, Any] | None: ...
    @staticmethod
    def _enum(value: object) -> str | None: ...
    @staticmethod
    def _without_empty(values: Mapping[str, Any]) -> dict[str, Any]: ...
```

#### Logic / Algorithm

`ClaudeVidbyteTranslator.translate_agent`:
1. Call `ClaudeSettingsValidator.validate` for cross-record rules that no single
   dataclass can see: a `sandbox.allowed_domains` without `sandbox.enabled` is
   rejected, and `session.resume` conflicting with a caller-supplied `session_id`
   is rejected.
2. `dataclasses.replace` the settings with stripped `name`, `system_prompt`,
   `additional_context`, `description`, stripped `capabilities`, a copied
   `metadata` dict, and a stripped `session_id`.
3. Resolve `output_schema` through `OutputSchemaFormatter.resolve_schema` and
   `.annotate`, then downgrade the `$schema` key to `CLAUDE_JSON_SCHEMA_DRAFT`.
4. Return `ClaudeAgentTranslation(settings, output_schema)`.

`ClaudeContentTranslator.option_kwargs` builds one flat dict:
1. Session fields: `resume` is `session_id` when non-empty, else
   `settings.session.resume`; plus `fork_session`, `continue_conversation`,
   `resume_session_at`.
2. Model fields via `ClaudeModelSettings`, with `thinking` built by
   `thinking_config` and effort/betas passed through.
3. Loop fields `max_turns`, `max_budget_usd`, dropped when zero.
4. Tool fields, with `tools` set to `{"type": "preset", "preset": "claude_code"}`
   when `use_claude_code_preset` and no explicit list, `skills` set to `"all"` when
   `all_skills`, and MCP config copied.
5. Process fields, with `setting_sources` rendered as a list of enum values —
   an empty tuple emits `[]` explicitly, because omitting the key means "load
   everything" and that is not a default this adapter takes silently.
6. `agents` from `agent_definitions`, `sandbox`, `plugins`.
7. `system_prompt` from `system_prompt_value`, `output_format` from `output_format`.
8. `_without_empty` drops `None` and `""` so provider defaults apply.

`system_prompt_value` dispatches on `ClaudeSystemPromptKind` with a dict lookup, not
an if/else ladder: `TEXT` returns the string; `PRESET` returns
`{"type": "preset", "preset": "claude_code", "append": <string>}` plus
`exclude_dynamic_sections` when set; `FILE` returns `{"type": "file", "path": ...}`.

`agent_definitions` converts each `ClaudeAgentDefinition` into the SDK's camelCase
dict (`disallowedTools`, `maxTurns`, `permissionMode`), dropping empties.

#### Edge Cases & Error Handling

- `option_kwargs` never raises on its own; the transport wraps its call and reports
  `claude.content_translation_failed` when the SDK's own constructors reject a
  value.
- `ClaudeSettingsValidator` raises `ConfigurationError`, which the agent facade
  converts to `claude.vidbyte_translation_failed`.
- A schema declaring a `$schema` other than draft-07 is rewritten rather than
  rejected, because `OutputSchemaFormatter` produces the 2020-12 default for every
  Pydantic model and rejecting it would make the common case unusable.

---

### 6.5 Context translation

**File(s):** `vidbyte/agents/claude/context.py`
**Type:** New file

#### What it does

Renders the live `ContextManager` primitives and per-run `ContextItem`s into a
`ClaudePrompt`: a developer-context block appended to the system prompt, plus text
placed before and after the current-turn prompt.

#### Interface / API

```python
class ClaudeContextTranslator:
    @classmethod
    def translate(cls, translation: ClaudeContextTranslationRequest) -> ClaudePrompt: ...
    @staticmethod
    def _sources(translation: ClaudeContextTranslationRequest) -> tuple[ClaudeContextSource, ...]: ...
    @classmethod
    def _render_manager(cls, source: ClaudeContextSource) -> ClaudeRenderedContext: ...
    @staticmethod
    def _blocks(values: Sequence[str]) -> tuple[str, ...]: ...
```

#### Logic / Algorithm

1. `_sources` compares the construction manager and the run manager **by identity**.
   The same object supplied at both scopes is one source rendered once; two
   different objects are two sources rendered in construction-then-run order.
2. `_render_manager` calls `manager.render_primitives_zone()` for developer context,
   `render_conversation_messages(TOP_OF_CONVERSATION)` for `before_input`, and
   `render_conversation_messages(END_OF_CONVERSATION)` for `after_input`, plus
   `manager.items()` rendered through `to_context_text()`.
3. `translate` assembles `user_prompt` as `"\n\n".join` of: static
   `additional_context`, every source's `before_input`, the run's
   `context_items` rendered text, the run's `prompt`, then every source's
   `after_input`.
4. `developer_context` is the `"\n\n".join` of every source's primitives zone.
5. Empty and whitespace-only blocks are dropped; equal non-empty blocks are kept,
   because a recitation is intentional.

#### Edge Cases & Error Handling

- A `None` manager renders an empty `ClaudeRenderedContext` and contributes nothing.
- The caller's manager is never mutated; the translator only reads.
- No `ConfigurationError` path exists here, because without anchors there is no
  unresolvable placement. This is the deliberate simplification recorded in 14.3.

---

### 6.6 Transport

**File(s):** `vidbyte/agents/claude/transport.py`
**Type:** New file

#### What it does

Owns one complete `query()` lifetime: lazy SDK import, option construction, stream
drain, teardown, and failure classification.

#### Interface / API

```python
class ClaudeTransport:
    async def run(self, request: ClaudeTransportRunRequest) -> ClaudeRunResult: ...
    async def _drain(self, sdk: ClaudeSdkTypes, options: object, request: ClaudeTransportRunRequest) -> ClaudeRunResult: ...
    @staticmethod
    async def _close(stream: object) -> None: ...
    @staticmethod
    def _failure_code(exc: Exception, sdk: ClaudeSdkTypes, resumed: bool) -> FailureCode: ...
    @staticmethod
    def _load_sdk() -> ClaudeSdkTypes: ...
```

#### Logic / Algorithm

1. `_load_sdk` imports `claude_agent_sdk` inside a `try`, raising
   `claude.sdk_unavailable` on `ImportError`, and returns a `ClaudeSdkTypes` record.
2. `run` builds options through `ClaudeContentTranslator.option_kwargs`, wrapping
   that call to report `claude.content_translation_failed`.
3. `_drain` creates the iterator, consumes it into a `ClaudeStreamAccumulator`, and
   returns `ClaudeResultSerializer.from_stream(accumulator)`.
4. `except asyncio.CancelledError: raise` comes first, before any broad handler.
5. On any other exception, if the accumulator already holds a `ResultMessage` the
   drain returns normally, because the provider reported a terminal result and the
   session id must survive. Otherwise it raises `ClaudeAgentError` with the code
   from `_failure_code`.
6. `finally: await self._close(stream)` runs on every path.
7. `_failure_code` maps SDK error classes to codes through a dict, defaulting to
   `claude.query_failed`. A run that supplied `resume` and failed before any result
   maps to `claude.session_resume_failed` instead, so a stale session id is
   distinguishable from a model failure.

#### Edge Cases & Error Handling

- A stream with no `ResultMessage` and no exception (provider closed early) yields
  `claude.response_invalid` from the serializer.
- `_close` tolerates an iterator without `aclose`.
- Error text never includes provider exception content — only `failure_code`,
  `operation`, and `type(exc).__name__` (S017).

---

### 6.7 Result normalization and translation

**File(s):** `vidbyte/agents/claude/result.py`
**Type:** New file

#### What it does

Accumulates the provider stream, freezes it into `ClaudeRunResult`, and builds the
public `AgentMessage` with validated structured output.

#### Interface / API

```python
class ClaudeStreamAccumulator:
    def consume(self, message: object, sdk: ClaudeSdkTypes) -> None: ...
    @property
    def has_result(self) -> bool: ...
    @property
    def session_id(self) -> str: ...


class ClaudeResultSerializer:
    @classmethod
    def from_stream(cls, accumulator: ClaudeStreamAccumulator) -> ClaudeRunResult: ...
    @classmethod
    def _item(cls, block: object, sdk: ClaudeSdkTypes) -> ClaudeItem | None: ...
    @classmethod
    def _usage(cls, result: object) -> ClaudeUsage: ...


class ClaudeResultTranslator:
    def translate(self, request: ClaudeResultTranslationRequest) -> AgentMessage: ...
    def normalize(self, request: ClaudeResultTranslationRequest) -> ClaudeRunResult: ...
    def _structured_output(self, result: ClaudeRunResult, schema, agent_name: str) -> Any: ...
```

#### Logic / Algorithm

`ClaudeStreamAccumulator.consume` dispatches on message class:
1. `SystemMessage` — record `session_id` when the payload carries one.
2. `AssistantMessage` — append each content block through `_item`.
3. `ResultMessage` — record `session_id`, `subtype`, `terminal_reason`, `result`,
   durations, `num_turns`, usage counters, `structured_output`, and set
   `has_result`.
4. Any other message type is ignored; the adapter does not opt into partial,
   hook, or task messages in this version.

`ClaudeResultSerializer._item` returns `None` for a block whose type is not in
`CLAUDE_SUPPORTED_BLOCK_TYPES`. `ThinkingBlock` therefore never produces a record,
and its `thinking` text is never read — the exclusion happens before serialization,
matching `vidbyte/agents/codex/result.py`.

`ClaudeResultSerializer.from_stream` raises `claude.response_invalid` when the
stream produced no `ResultMessage`, and when a `success` subtype carries neither
`result` text nor `structured_output`.

`ClaudeResultTranslator.normalize`:
1. When the agent declared no schema, return the result with `structured=None`.
2. When the subtype is not `SUCCESS`, return with `structured=None` — a failed run
   is a diagnostic outcome, not a schema-compliant answer.
3. When the subtype is `SUCCESS` but `structured_output` is absent, raise
   `OutputSchemaViolationError`. This is the documented hole in the provider's
   success case.
4. Otherwise serialize `structured_output` with `json.dumps` and validate it through
   `OutputSchemaFormatter.validate`, so a Pydantic schema yields a model instance
   rather than a raw dict.

`ClaudeResultTranslator.translate` builds `ClaudeMessageData`, filters
`subagents` by `CLAUDE_SUBAGENT_TOOL_NAMES`, reads `forked_from_session_id` and
`fork_depth` from agent metadata, and returns an `AgentMessage` whose `metadata`
merges agent lineage, run metadata, `provider="claude"`, and
`provider_item_count`.

#### Edge Cases & Error Handling

- Absent usage keeps `usage_available=False` so zero is distinguishable from unknown.
- `error_max_structured_output_retries` reaches the caller as a populated
  `ClaudeMessageData` with `structured=None` when no schema was declared, and as an
  `OutputSchemaViolationError` when one was.
- A `ToolResultBlock` whose `content` is a nested block list is serialized by type
  name only; its nested content is not copied, keeping the record bounded.

---

### 6.8 Fork

**File(s):** `vidbyte/agents/claude/fork.py`
**Type:** New file

#### What it does

Produces validated child settings for a lazy provider fork. No transport, no
awaitable work.

#### Interface / API

```python
class ClaudeFork:
    def fork(self, request: ClaudeForkRequest) -> ClaudeForkResult: ...
    async def afork(self, request: ClaudeForkRequest) -> ClaudeForkResult: ...
    @staticmethod
    def _prepare_child(request: ClaudeForkRequest) -> ClaudeHarnessAgentSettings: ...
    @staticmethod
    def _child_session(parent_session_id: str, settings: ClaudeAgentSettings) -> ClaudeAgentSettings: ...
    @staticmethod
    def _child_metadata(request: ClaudeForkRequest) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. Raise `claude.fork_failed` / `fork_precondition` when `parent_session_id` is
   empty — a fork with nothing to resume from is unrecoverable later.
2. `_prepare_child` resolves each override with inherit / replace / clear semantics
   identical to `CodexFork._prepare_child`, and deep-copies the context manager.
3. `_child_session` replaces the child's `ClaudeSessionSettings` with
   `resume=parent_session_id`, `fork_session=True`, `continue_conversation=False`,
   `resume_session_at=""`.
4. `_child_metadata` stamps `forked_from_session_id` and
   `fork_depth = parent_depth + CLAUDE_NEXT_FORK_DEPTH`.
5. The child's own `session_id` is `""`, so its first run starts from the fork.
6. `_prepare_child` returns `ClaudeVidbyteTranslator().translate_agent(child).settings`,
   so an invalid child is rejected before it is handed back.

#### Edge Cases & Error Handling

- `clear_context_manager` with a replacement manager, and `clear_output_schema` with
  a replacement schema, are rejected by `ClaudeForkSettings.__post_init__`.
- Any non-`ClaudeAgentError` exception during preparation is wrapped as
  `claude.fork_failed` / `prepare_fork`.
- `afork` performs no I/O; it exists so the two harness adapters expose the same
  method set.

---

### 6.9 Public agent facade

**File(s):** `vidbyte/agents/claude/agent.py`
**Type:** New file

#### What it does

The one class users construct. Holds settings, session identity, and history;
delegates every step to a collaborator.

#### Interface / API

```python
class ClaudeHarnessAgent:
    session_persistence_supported = False

    def __init__(self, settings: ClaudeHarnessAgentSettings) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def system_prompt(self) -> str: ...
    async def arun(self, request: ClaudeRunInput) -> AgentMessage: ...
    def run(self, request: ClaudeRunInput) -> AgentMessage: ...
    async def afork(self, settings: ClaudeForkSettings = ...) -> ClaudeHarnessAgent: ...
    def fork(self, settings: ClaudeForkSettings = ...) -> ClaudeHarnessAgent: ...
```

#### Logic / Algorithm

`__init__`: construct `ClaudeVidbyteTranslator`, translate settings (wrapping any
failure as `claude.vidbyte_translation_failed`), store `settings`, `session_id`,
empty `history`, `last_prompt`, `last_reply`, and construct `ClaudeTransport`,
`ClaudeResultTranslator`, `ClaudeFork`.

`arun`:
1. Translate context, wrapping any failure as
   `claude.vidbyte_translation_failed` / `translate_context`.
2. Join `system_prompt` and `developer_context` with a blank line, dropping empties.
3. Await `self._transport.run(...)` with the current `session_id`.
4. Adopt `result.session_id`.
5. Translate the result into an `AgentMessage`, append to `history`, record
   `last_prompt` and `last_reply`, return.

`run`: the Codex `no-nested-event-loop` guard, verbatim in shape — try
`asyncio.get_running_loop()`, `asyncio.run` on `RuntimeError`, otherwise raise.

`fork` / `afork`: delegate to `ClaudeFork` and construct a new
`ClaudeHarnessAgent` from the returned child settings.

#### Edge Cases & Error Handling

- `session_persistence_supported = False`: Vidbyte durable sessions are not wired to
  provider sessions in this version.
- `history` grows unbounded across turns exactly as `CodexHarnessAgent.history`
  does; callers own its lifetime. Recorded as a known limitation, not a new bound.

---

### 6.10 Package exports and dependency

**File(s):** `vidbyte/agents/claude/__init__.py`, `vidbyte/agents/__init__.py`,
`vidbyte/__init__.py`, `vidbyte/lib/dataclasses/__init__.py`, `pyproject.toml`
**Type:** New file + Modified

#### What it does

Publishes the adapter's public names at the same three levels the Codex adapter
uses, and adds the optional dependency.

#### Interface / API

```toml
[project.optional-dependencies]
claude = [
  "claude-agent-sdk>=0.2.152,<0.3.0",
]
```

#### Logic / Algorithm

1. `vidbyte/agents/claude/__init__.py` re-exports `ClaudeHarnessAgent` plus the
   public settings, input, enum, and result records, with an explicit `__all__`.
2. `vidbyte/agents/__init__.py` and `vidbyte/__init__.py` add the same names, in the
   alphabetical position their existing `Codex*` neighbors occupy.
3. `vidbyte/lib/dataclasses/__init__.py` re-exports the `claude` records beside the
   `codex` ones.
4. The pin is narrow — one minor series — because the adapter reads concrete SDK
   field names.

#### Edge Cases & Error Handling

- S015 requires every `__all__` entry to be statically bound; the SDK import stays
  lazy inside `transport.py`, so no export depends on the extra being installed.
- Importing `vidbyte` without the extra must succeed; the verification script
  asserts this explicitly.

---

### 6.11 Failure vocabulary and error class

**File(s):** `vidbyte/lib/enums/failure.py`, `vidbyte/lib/errors/base.py`
**Type:** Modified

#### What it does

Adds ten `claude.`-prefixed codes and the `ClaudeAgentError` that carries them.

#### Interface / API

```python
CLAUDE_SDK_UNAVAILABLE = "claude.sdk_unavailable"
CLAUDE_CLI_NOT_FOUND = "claude.cli_not_found"
CLAUDE_CONNECTION_FAILED = "claude.connection_failed"
CLAUDE_PROCESS_FAILED = "claude.process_failed"
CLAUDE_VIDBYTE_TRANSLATION_FAILED = "claude.vidbyte_translation_failed"
CLAUDE_CONTENT_TRANSLATION_FAILED = "claude.content_translation_failed"
CLAUDE_QUERY_FAILED = "claude.query_failed"
CLAUDE_SESSION_RESUME_FAILED = "claude.session_resume_failed"
CLAUDE_FORK_FAILED = "claude.fork_failed"
CLAUDE_RESPONSE_INVALID = "claude.response_invalid"


class ClaudeAgentError(AgentExecutionError):
    """Carries one safe, vocabulary-backed Claude adapter failure."""
    DIAGNOSTIC_FIELDS = (
        "error_kind", "expected", "actual", "safe_runtime_details",
        "likely_causes", "repair_approaches", "related_docs", "relevant_tests",
    )
    def __init__(self, message: str, *, failure_code: str, operation: str, error_type: str = "") -> None: ...
```

#### Logic / Algorithm

1. Codes are inserted after the `CODEX_*` block, preserving that block unchanged.
2. `ClaudeAgentError` mirrors `CodexAgentError`'s exact shape: eight
   `DIAGNOSTIC_FIELDS`, eight `self.<field>` assignments, and the same keys in the
   `details={...}` mapping passed to `super().__init__`.
3. `related_docs` points at the Claude Agent SDK overview and Python reference.
4. `relevant_tests` is `("python scripts/run_ci.py",)`.

#### Edge Cases & Error Handling

- A003 is a ratchet, so a new class missing any of the eight fields is a REGRESSED
  finding. The field guide records this exact trap.
- `safe_runtime_details` carries only `operation` and `error_type`; no provider
  exception text, per S017.

---

### 6.12 Roadmap skill

**File(s):** `skills/claude-harness-roadmap/SKILL.md`,
`skills/claude-harness-roadmap/references/checklist.md`,
`skills/claude-harness-roadmap/references/sources.md`,
`skills/claude-harness-roadmap/references/translation-map.md`
**Type:** New file

#### What it does

Records every capability this version does not ship as a stable, checkable task, so
a later session can pick up the next increment without re-deriving the gap. It
mirrors `skills/codex-harness-roadmap/` in structure, labels, and discipline.

#### Interface / API

```markdown
---
name: claude-harness-roadmap
description: Plan future ClaudeHarnessAgent features and Vidbyte abstraction
  translations using a versioned implementation baseline and official Claude
  Agent SDK documentation. Use for capability gaps, roadmap checklists, or
  selecting the next Claude harness increment.
---
```

`references/checklist.md` groups tasks by domain with stable IDs:

| Group | Domain |
|---|---|
| `C` | Capability and version contracts |
| `L` | Connection lifecycle and persistent client |
| `T` | Live turns, streaming, and intervention |
| `R` | Messages, blocks, and artifacts |
| `S` | Provider session management |
| `F` | Forks and file checkpointing |
| `D` | Vidbyte durable sessions |
| `X` | Context, prompts, and compaction |
| `U` | Vidbyte tools and output contracts |
| `M` | MCP lifecycle and in-process servers |
| `P` | Permissions and approvals |
| `H` | Hooks and middleware |
| `K` | Skills, plugins, and settings sources |
| `A` | Authentication and model discovery |
| `G` | Typed configuration and precedence |
| `N` | Native subagents and tasks |
| `O` | Tracing, accounting, and speed |
| `B` | Budgets, failures, and recovery |
| `V` | Composition and evaluation |

Surface labels reuse the Codex roadmap's meanings: `N` public Python SDK method,
`P` protocol/CLI-level operation without an established Python wrapper, `E`
experimental, `CFG` native configuration surface, `V` proposed Vidbyte behavior.

#### Logic / Algorithm

1. `SKILL.md` states the baseline: this PR, the pinned SDK version, and the review
   date, and instructs a reader to reconcile newer implementation before presenting
   gaps.
2. `references/checklist.md` opens with "What this PR already supplies" so shipped
   behavior is never re-proposed as new work.
3. Each task states the user-visible outcome, the Claude surface, the Vidbyte
   abstraction, and the implementation seam; each group ends with completion
   evidence.
4. `references/sources.md` indexes the official documentation pages behind stable
   `S##` anchors that checklist groups cite.
5. `references/translation-map.md` maps each Vidbyte abstraction to its Claude
   counterpart and its disposition from the existing feature matrix.

#### Edge Cases & Error Handling

- The skill states explicitly that reading a backlog item does not authorize
  implementing it, matching the Codex roadmap's guard.
- Proposed class names are marked as proposals, not exported SDK symbols, so no
  reader emits a runnable import for them.
- `skills/claude-agent-sdk-translation/SKILL.md` is updated to point at the shipped
  baseline and at this roadmap, so the two skills do not disagree about what exists.

---

## 7. Data Model Changes

### 7.1 `AgentMessage`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class AgentMessage:
    sender: str
    recipient: str
    content: str
    message_type: str = "response"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    structured: Any = None
    # Provider-specific deterministic result data; absent for non-Codex agents.
    codex: CodexMessageData | None = None
    # Provider-specific deterministic result data; absent for non-Claude agents.
    claude: ClaudeMessageData | None = None
```

**Migration strategy:**
- Forward: purely additive with a `None` default. Every existing construction site
  remains valid, and `slots=True` tolerates the new field because the class is
  rebuilt at import.
- Rollback: remove the field; no persisted data depends on it, because
  `AgentMessage` is an in-process record with no serialized store.

### 7.2 `FailureCode`

**Change type:** Modified — ten additive members. No existing value changes.

**Migration strategy:** Additive to a `str, Enum`; a consumer matching on unknown
codes already has a default path. No rollback concern.

### 7.3 Claude adapter records

**Change type:** New — every dataclass in Section 6.3.

**Migration strategy:** N/A — new in-process records with no persistence.

There are no database, collection, or index changes. **N/A — this SDK package has
no datastore; it is a library, not a service.**

---

## 8. API Changes

No HTTP endpoints exist in this package. **N/A — `vidbyte-sdk` is a Python library
with no served API.** The public Python surface added is:

### 8.1 `ClaudeHarnessAgent`

**Change type:** New

**Construction:**
```python
from vidbyte import (
    ClaudeHarnessAgent, ClaudeHarnessAgentSettings, ClaudeAgentSettings,
    ClaudeToolSettings, ClaudeLoopSettings, ClaudePermissionMode, ClaudeRunInput,
)

agent = ClaudeHarnessAgent(
    ClaudeHarnessAgentSettings(
        name="reviewer",
        system_prompt="You review Python diffs for correctness bugs.",
        claude=ClaudeAgentSettings(
            tools=ClaudeToolSettings(
                allowed_tools=("Read", "Grep", "Glob"),
                permission_mode=ClaudePermissionMode.PLAN,
            ),
            loop=ClaudeLoopSettings(max_turns=12, max_budget_usd=1.50),
        ),
        output_schema=ReviewFindings,
    )
)
```

**Run:**
```python
reply = await agent.arun(ClaudeRunInput.text("Review the diff on this branch."))
reply.content                       # str  - final assistant text
reply.structured                    # ReviewFindings instance
reply.claude.session_id             # str  - resume identity
reply.claude.usage.total_cost_usd   # float
reply.claude.num_turns              # int | None
```

**Fork:**
```python
branch = agent.fork(ClaudeForkSettings(system_prompt="Now audit for performance."))
branch.session_id                   # "" until its first successful run
```

**Error cases:**

| Failure code | Condition |
|---|---|
| `claude.sdk_unavailable` | `claude-agent-sdk` not installed |
| `claude.cli_not_found` | SDK installed, bundled CLI missing |
| `claude.connection_failed` | CLI process could not be reached |
| `claude.process_failed` | CLI subprocess exited with an error |
| `claude.vidbyte_translation_failed` | Vidbyte settings or context invalid |
| `claude.content_translation_failed` | SDK rejected a translated option |
| `claude.query_failed` | Provider run failed with no terminal result |
| `claude.session_resume_failed` | A resumed session id could not be loaded |
| `claude.fork_failed` | Fork precondition or child preparation failed |
| `claude.response_invalid` | Stream produced no usable terminal result |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/claude-harness-agent.md` | This design doc |
| CREATE | `vidbyte/agents/claude/__init__.py` | Adapter public exports |
| CREATE | `vidbyte/agents/claude/agent.py` | `ClaudeHarnessAgent` facade |
| CREATE | `vidbyte/agents/claude/config.py` | Vidbyte and SDK translation |
| CREATE | `vidbyte/agents/claude/context.py` | Per-turn context rendering |
| CREATE | `vidbyte/agents/claude/fork.py` | Lazy fork settings collaborator |
| CREATE | `vidbyte/agents/claude/result.py` | Stream accumulation and result translation |
| CREATE | `vidbyte/agents/claude/transport.py` | Bounded `query()` lifecycle |
| CREATE | `vidbyte/lib/constants/claude.py` | Shared adapter constants |
| CREATE | `vidbyte/lib/dataclasses/claude.py` | Validated settings, input, result records |
| CREATE | `vidbyte/lib/enums/claude.py` | Closed provider vocabularies |
| CREATE | `scripts/test-claude-harness-agent.py` | Section 10 verification script |
| CREATE | `tests/test_claude_harness_agent.py` | Offline pytest suite |
| CREATE | `skills/claude-harness-roadmap/SKILL.md` | Future-work planning skill |
| CREATE | `skills/claude-harness-roadmap/references/checklist.md` | Stable deferred-task IDs |
| CREATE | `skills/claude-harness-roadmap/references/sources.md` | Official documentation index |
| CREATE | `skills/claude-harness-roadmap/references/translation-map.md` | Vidbyte-to-Claude abstraction map |
| MODIFY | `vidbyte/lib/enums/failure.py` | Add ten `CLAUDE_*` codes |
| MODIFY | `vidbyte/lib/errors/base.py` | Add `ClaudeAgentError` with the A003 packet |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentMessage.claude` |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Re-export Claude records |
| MODIFY | `vidbyte/agents/__init__.py` | Export Claude adapter names |
| MODIFY | `vidbyte/__init__.py` | Export Claude adapter names at package root |
| MODIFY | `pyproject.toml` | Add the `claude` optional dependency |
| MODIFY | `skills/claude-agent-sdk-translation/SKILL.md` | Record the shipped baseline; link the roadmap |

---

## 10. Testing Plan

Every test runs offline against a fake SDK module injected into `sys.modules`. No
test requires `claude-agent-sdk`, an API key, or a CLI binary.

### Unit Tests

**Settings validation**
- `ClaudeSessionSettings` -> `rejects continue_conversation together with resume` — [Hidden Assumption]
- `ClaudeSessionSettings` -> `rejects fork_session without resume or continue_conversation` — [Hidden Assumption]
- `ClaudeToolSettings` -> `rejects a tool name in both allowed_tools and disallowed_tools` — [Silent Failure]
- `ClaudeToolSettings` -> `rejects skills and all_skills set together` — [Edge Case]
- `ClaudeModelSettings` -> `rejects thinking_budget_tokens below the minimum when mode is ENABLED` — [Edge Case]
- `ClaudeModelSettings` -> `rejects a non-zero thinking budget when mode is DISABLED` — [Silent Failure]
- `ClaudeSubagentSettings` -> `rejects a reserved role name` — [Hidden Assumption]
- `ClaudeSystemPromptSettings` -> `requires path when kind is FILE and forbids it otherwise` — [Edge Case]
- `ClaudeForkSettings` -> `rejects clear_context_manager with a replacement manager` — [Hidden Assumption]
- `ClaudeHarnessAgentSettings` -> `rejects an empty and a whitespace-only name` — [Edge Case]
- `ClaudeRunInput` -> `rejects an empty prompt` — [Edge Case]

**Option translation**
- `ClaudeContentTranslator` -> `omits every PROVIDER_DEFAULT sentinel from the emitted kwargs` — [Silent Failure]
- `ClaudeContentTranslator` -> `emits setting_sources as an explicit empty list rather than omitting the key` — [Silent Failure]
- `ClaudeContentTranslator` -> `emits resume from the agent session_id in preference to settings.session.resume` — [Silent Failure]
- `ClaudeContentTranslator` -> `emits the claude_code preset when use_claude_code_preset and no explicit tool list` — [Edge Case]
- `ClaudeContentTranslator` -> `emits skills as the literal "all" when all_skills is set` — [Edge Case]
- `ClaudeContentTranslator` -> `emits camelCase subagent keys disallowedTools, maxTurns, permissionMode` — [Silent Failure]
- `ClaudeContentTranslator` -> `emits no thinking key when mode is PROVIDER_DEFAULT` — [Edge Case]
- `ClaudeVidbyteTranslator` -> `rewrites a Pydantic draft-2020-12 $schema to draft-07` — [Silent Failure]
- `ClaudeVidbyteTranslator` -> `strips whitespace from name, system_prompt, and session_id` — [Edge Case]

**Context translation**
- `ClaudeContextTranslator` -> `renders an empty prompt body for a None manager and no context items` — [Edge Case]
- `ClaudeContextTranslator` -> `renders the same manager once when supplied at both construction and run scope` — [Silent Failure]
- `ClaudeContextTranslator` -> `renders two distinct managers in construction-then-run order` — [Edge Case]
- `ClaudeContextTranslator` -> `preserves two identical context blocks without deduplicating them` — [Silent Failure]
- `ClaudeContextTranslator` -> `reflects a primitive removed from the manager between two turns` — [Hidden Failure]
- `ClaudeContextTranslator` -> `does not mutate the caller's manager registry` — [Hidden Failure]
- `ClaudeContextTranslator` -> `drops whitespace-only blocks but keeps interior whitespace of real blocks` — [Edge Case]

**Transport**
- `ClaudeTransport` -> `raises claude.sdk_unavailable when the SDK module is absent` — [Hidden Assumption]
- `ClaudeTransport` -> `maps CLINotFoundError to claude.cli_not_found` — [Hidden Failure]
- `ClaudeTransport` -> `maps ProcessError to claude.process_failed` — [Hidden Failure]
- `ClaudeTransport` -> `maps a failure on a resumed session to claude.session_resume_failed` — [Silent Failure]
- `ClaudeTransport` -> `returns the result when the SDK raises after yielding a ResultMessage` — [Silent Failure]
- `ClaudeTransport` -> `preserves the session_id from a ResultMessage whose subtype is error_max_turns` — [Silent Failure]
- `ClaudeTransport` -> `raises claude.response_invalid when the stream ends with no ResultMessage` — [Hidden Failure]
- `ClaudeTransport` -> `calls aclose on the iterator on the success path` — [Hidden Failure]
- `ClaudeTransport` -> `calls aclose on the iterator when the drain raises` — [Hidden Failure]
- `ClaudeTransport` -> `tolerates an iterator with no aclose attribute` — [Edge Case]
- `ClaudeTransport` -> `re-raises CancelledError unwrapped rather than as a provider error` — [Hidden Failure]
- `ClaudeTransport` -> `excludes provider exception text from the raised message` — [Silent Failure]

**Result normalization**
- `ClaudeResultSerializer` -> `never emits an item for a ThinkingBlock` — [Silent Failure]
- `ClaudeResultSerializer` -> `never reads the thinking attribute of a ThinkingBlock` — [Silent Failure]
- `ClaudeResultSerializer` -> `emits items for text, tool_use, and tool_result blocks` — [Edge Case]
- `ClaudeResultSerializer` -> `keeps usage_available False when the result carries no token fields` — [Silent Failure]
- `ClaudeResultSerializer` -> `distinguishes a zero token count from an absent one` — [Silent Failure]
- `ClaudeResultSerializer` -> `handles an assistant message with an empty content list` — [Edge Case]
- `ClaudeResultSerializer` -> `handles a stream with zero assistant messages and one result` — [Edge Case]
- `ClaudeResultTranslator` -> `returns structured None for a failed subtype even when a schema was declared` — [Hidden Assumption]
- `ClaudeResultTranslator` -> `raises OutputSchemaViolationError when subtype is success and structured_output is None` — [Silent Failure]
- `ClaudeResultTranslator` -> `raises OutputSchemaViolationError when structured_output violates the schema` — [Edge Case]
- `ClaudeResultTranslator` -> `returns a Pydantic instance rather than a dict for a model schema` — [Silent Failure]
- `ClaudeResultTranslator` -> `accepts a structured_output whose only field value is False` — [Silent Failure]
- `ClaudeResultTranslator` -> `filters subagent items by the Task and Agent tool names` — [Edge Case]
- `ClaudeResultTranslator` -> `sets metadata provider to claude` — [Edge Case]

**Fork**
- `ClaudeFork` -> `raises claude.fork_failed before the parent has a session id` — [Hidden Assumption]
- `ClaudeFork` -> `sets child resume to the parent session id and fork_session True` — [Edge Case]
- `ClaudeFork` -> `leaves the child session_id empty` — [Silent Failure]
- `ClaudeFork` -> `clears continue_conversation and resume_session_at on the child` — [Silent Failure]
- `ClaudeFork` -> `deep-copies the context manager so a child edit does not reach the parent` — [Hidden Failure]
- `ClaudeFork` -> `increments fork_depth from the parent metadata` — [Edge Case]
- `ClaudeFork` -> `defaults fork_depth to the root value when parent metadata has none` — [Edge Case]
- `ClaudeFork` -> `treats a None override as inherit and an empty tuple as replace` — [Silent Failure]
- `ClaudeFork` -> `clears the output schema when clear_output_schema is set` — [Edge Case]
- `ClaudeFork.afork` -> `returns the same result as fork without awaiting provider work` — [Edge Case]

**Facade**
- `ClaudeHarnessAgent` -> `raises claude.vidbyte_translation_failed for invalid construction settings` — [Hidden Assumption]
- `ClaudeHarnessAgent` -> `adopts the session id from the first successful run` — [Edge Case]
- `ClaudeHarnessAgent` -> `passes the adopted session id as resume on the second run` — [Silent Failure]
- `ClaudeHarnessAgent` -> `appends the developer context to the system prompt with a blank line` — [Edge Case]
- `ClaudeHarnessAgent.run` -> `raises the sync guard inside a running event loop` — [Hidden Failure]
- `ClaudeHarnessAgent` -> `imports successfully when claude-agent-sdk is not installed` — [Hidden Assumption]

**Errors and exports**
- `ClaudeAgentError` -> `exposes all eight DIAGNOSTIC_FIELDS as attributes and in details` — [Hidden Assumption]
- `FailureCode` -> `contains all ten claude-prefixed codes with no value collisions` — [Edge Case]
- `vidbyte` -> `exports every name in the Claude adapter __all__` — [Silent Failure]

### Integration Tests

Flows tested end-to-end against the fake SDK:

1. **Two-turn conversation.** Turn one starts a session; turn two must pass
   `resume=<turn one session id>`. Silent failure guarded against: the second turn
   silently starting a fresh session, which looks identical from the reply text.
2. **Fork divergence.** Parent runs, forks, child runs. The child's first options
   must carry `resume=<parent id>` and `fork_session=True`; the child's second
   options must carry `resume=<child's own id>` and `fork_session=False`. Silent
   failure guarded against: the child re-forking the parent on every turn.
3. **Structured output round trip.** A Pydantic schema reaches the SDK as draft-07
   `output_format`, and the returned dict becomes a model instance. Silent failure
   guarded against: a dict returned where callers expect an instance.
4. **Recovery after `error_max_turns`.** A run raises after yielding an error
   result; the agent must still hold the session id and the next run must resume it.
5. **Context mutation between turns.** A primitive removed from the manager between
   turns must be absent from the second turn's prompt.
6. **Missing extra.** With `claude_agent_sdk` absent from `sys.modules` and
   unimportable, `import vidbyte` succeeds and `arun` raises
   `claude.sdk_unavailable`.

External dependencies: `claude_agent_sdk` is always faked. Nothing else is mocked;
`ContextManager`, `OutputSchemaFormatter`, and the error classes are real.

Hidden assumptions the integration surfaces that unit tests cannot: that the option
dict actually reaching the SDK constructor carries the session id (a unit test on
the translator can pass while the transport passes the wrong value), and that the
accumulator's session id survives the exception path end to end.

### Manual / QA Test Cases

1. Given `claude-agent-sdk` installed and `ANTHROPIC_API_KEY` set, when a
   `ClaudeHarnessAgent` runs `"List the Python files in this directory"` with
   `allowed_tools=("Glob",)`, then the reply names real files and
   `reply.claude.usage.total_cost_usd` is greater than zero — [Edge Case]
2. Given the same agent after one successful run, when a second run asks
   `"What did you just list?"`, then the answer references the first run's output,
   confirming the session resumed — [Silent Failure]
3. Given a parent with a session id, when `fork()` is called and the child runs a
   divergent prompt, then the parent's next run still continues its own thread —
   [Silent Failure]
4. Given `max_turns=1` on a task requiring several turns, when the run executes,
   then it raises after an error result and `agent.session_id` is still populated
   and resumable with a higher ceiling — [Hidden Failure]
5. Given `claude-agent-sdk` uninstalled, when `import vidbyte` runs, then it
   succeeds, and constructing plus running a `ClaudeHarnessAgent` raises
   `claude.sdk_unavailable` naming `vidbyte-sdk[claude]` — [Hidden Assumption]
6. Given the CLI binary removed from `PATH` with the SDK installed, when a run
   executes, then the failure code is `claude.cli_not_found`, not
   `claude.query_failed` — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| `claude-agent-sdk` | `>=0.2.152,<0.3.0`, optional extra `claude` | Provider agent loop | Field names are read concretely; a minor bump can drift. Mitigated by the narrow pin and by offline tests that assert the exact option keys. |
| Bundled Claude Code CLI | Ships with the SDK | Runs the agent loop as a subprocess | Absent or unlaunchable binary; mitigated by the dedicated `claude.cli_not_found` code. |
| Anthropic API | `ANTHROPIC_API_KEY` from process env | Model access | Credentials are never read, stored, or logged by the adapter. Anthropic's terms require API-key auth for third-party products. |
| `pydantic` | `>=2,<3`, already required | Schema resolution and validation | None new. |

---

## 12. Rollout & Deployment

- **Feature flags:** None. The adapter is inert until a caller constructs it, and
  the SDK import is lazy, so the code path cannot execute for an existing user.
- **Breaking change:** No. Every change to shared code is additive: ten enum
  members, one `AgentMessage` field with a `None` default, one error class, new
  exports. No existing signature, value, or behavior changes.
- **Deployment order:** Single package; no ordering constraint.
- **Rollback:** Revert the branch. No migration, no persisted state, no external
  resource is created by merging.
- **Install path:** `pip install "vidbyte-sdk[claude]"`. The base install is
  unaffected and the package stage of `scripts/run_ci.py` verifies a wheel installs
  and imports without the extra.

---

## 13. Open Questions

- [ ] Are the exact `ResultMessage` field names confirmed against the installed
      `claude-agent-sdk==0.2.152` stubs? The public docs are internally
      inconsistent — the sessions page uses `message.session_id` while the Python
      reference's field table omits it. **Resolution: inspect the installed package
      during implementation and correct Section 6.7 before writing the serializer.**
      Until then the accumulator reads fields defensively via `getattr` with typed
      defaults, so a renamed field degrades to "absent", never to a crash.
- [ ] Is `claude_agent_sdk._errors` the supported import path for the error classes,
      or are they re-exported from the package root? **Resolution: prefer the root
      import and fall back to `_errors`; record the resolved path in the module
      header.**
- [ ] Should `ClaudeProcessSettings.setting_sources` default to an explicit empty
      tuple (load nothing) or to `("project",)`? This doc chooses empty, because a
      harness whose instructions silently change with the contents of a CLAUDE.md on
      disk is not reproducible. Confirm this is the intended default.
- [ ] Does `AgentMessage` gaining a second provider field argue for a single
      `provider_data` union instead of one field per provider? Not in this PR —
      two fields is not yet a pattern. Flagged for the third provider.

---

## 14. Alternatives Considered

### Alternative 1: Hold a persistent `ClaudeSDKClient` open across turns

- **What:** Construct one `ClaudeSDKClient` in `__init__`, connect on first use,
  and reuse it for every turn. This is the only way to reach `interrupt()`,
  `set_model()`, `set_permission_mode()`, `rewind_files()`, and `stop_task()`, and
  it removes the per-turn subprocess spawn.
- **Why rejected:** It turns the agent into a resource owner with a connection
  lifetime. `CodexHarnessAgent` has no `aclose()`, and adding one to only one of the
  two adapters breaks the parity that makes them learnable together. It also makes
  `session_persistence_supported = False` misleading. Both modes sit behind
  `ClaudeTransport.run()`, so this is a later swap rather than a rewrite. **Flips
  when:** mid-turn interrupt is required, or the spawn cost is measured and matters.

### Alternative 2: Materialize forks eagerly with a throwaway query

- **What:** On `fork()`, run a minimal query with `resume` + `fork_session=True` to
  obtain the child's session id immediately, matching Codex's eager
  `thread_fork()` and its provider-confirmed identity.
- **Why rejected:** It costs a real model call and real dollars on every fork, and
  it injects a junk turn into the child's history that every later turn carries. The
  guarantee purchased — early detection of an unresumable parent — is available one
  turn later for free.

### Alternative 3: Port the Codex input-item model and context anchors

- **What:** Recreate `CodexTextInput`/`ImageInput`/`SkillInput`/`MentionInput`,
  `ClaudeInputType`, and `ClaudeContextAnchor` so the two adapters have identical
  input surfaces.
- **Why rejected:** Claude's prompt is a single string, so there are no interior
  positions to anchor against. The five dataclasses would each wrap one string, and
  `_anchor_index` would have no matching items to find — every anchor would raise.
  That is roughly 200 lines that cannot do anything. **Flips when:** streaming input
  mode is added for images, at which point content blocks become real positions.

### Alternative 4: Follow the module decomposition proposed in `claude-agent-sdk-translation`

- **What:** That skill proposes `config.py`/`capabilities.py`, `compiler.py`,
  `client.py`, `messages.py`/`events.py`, `tools.py`/`permissions.py`/`hooks.py`,
  `sessions.py`/`checkpointing.py`, `subagents.py`, `usage.py`/`tracing.py`/
  `errors.py`.
- **Why rejected for this version:** That decomposition is sized for the complete
  feature set. With hooks, permission callbacks, in-process MCP tools, streaming,
  and checkpointing all deferred, `hooks.py`, `permissions.py`, `checkpointing.py`,
  and `events.py` would be empty or near-empty modules — the exact "abstraction with
  one implementation" cost this repo's conventions warn against. The skill itself
  calls its list "a planning seam, not an implementation manifest" and permits
  another placement with justification. The Codex decomposition is the repo's proven
  shape for exactly this problem, and reusing it means one reader model covers both
  adapters. The roadmap skill records the fuller decomposition as the target for
  when those features land.

### Alternative 5: Validate structured output locally instead of trusting the provider

- **What:** Ignore `structured_output` and run `OutputSchemaFormatter.validate` over
  `ResultMessage.result` text, exactly as the Codex adapter does.
- **Why rejected:** The provider already validated and re-prompted on mismatch, so
  re-parsing the free text discards that work and would fail whenever the model put
  prose around the JSON. The chosen middle path — feed `json.dumps(structured_output)`
  back through the existing formatter — reuses the shared validator unchanged while
  keeping the provider's retry benefit, and is the only way to hand a caller a
  Pydantic instance rather than a dict.

### Alternative 6: Put the future-features list in the existing `claude-agent-sdk-translation` skill

- **What:** Append a deferred-work checklist to the existing translation skill
  instead of creating `skills/claude-harness-roadmap/`.
- **Why rejected:** The two have different jobs and different lifetimes. The
  translation skill answers "how should any Claude capability map onto Vidbyte" and
  is stable. A roadmap answers "what is not built yet relative to this commit" and
  changes with every increment. `skills/codex-harness-roadmap/` already established
  the separation for the Codex adapter; matching it keeps the two providers
  navigable the same way. The translation skill is updated to link the roadmap so
  neither goes stale independently.
