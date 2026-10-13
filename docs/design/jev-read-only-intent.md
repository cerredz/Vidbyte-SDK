# Design Doc: JevAgent Read-Only Intent

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-12
**Last Updated:** 2026-10-12

---

## 1. Overview

Many agents are asked questions as often as they are asked for changes. Today a JevAgent that holds write or execute tools keeps them for every request, so "why does the login test fail?" runs with the same power to edit files as "fix the login test". This feature adds an opt-in preflight preset, `JevPreflightPreset.READ_ONLY`. Eight fixed Jev questions, asked in the gate's one batched request, recognize a request that asks for an assessment (an explanation, a diagnosis, an opinion, a recommendation, a plan, a review, or a report) and not a change. When every answer reaches the threshold, the run keeps only tools at the `SAFE` and `READ` permission levels. The main agent's catalog is narrowed the way the tool selector already narrows it, keyed on `ToolPermission` instead of relevance. A run-scoped permission ceiling, enforced inside `PermissionPolicy.check`, also refuses every tool above `READ` for the main agent and for every agent the run starts. The agent still answers in full. It just cannot edit, write, or execute anything during that request.

---

## 2. Goals & Non-Goals

### Goals
- Add `JevPreflightPreset.READ_ONLY`, a fixed-question preset that runs in the existing `JevPreflightGate` request, scored by `DecisionModelHelper.score_noul`, and acted on by one commented `case` in `JevPreflightGate.pass_`.
- Write eight positive-polarity Jev questions in the house layout of `skills/asking-jev-questions/SKILL.md`, covering the four signals the request named plus four more pieces of evidence that keep a change request from being misread as an assessment.
- For a read-only run, hide every user tool above `READ` from the main agent with the same per-run narrowing `_select_tools` uses (`Tools.subset`, `with_internal_agent_tools`, `replace(context, tools=...)`, drop `options["tools"]`).
- For a read-only run, guarantee that no tool above `READ` can execute anywhere in the run. This includes the main agent, a chosen specialist, bulk-work agents, CLONE and SWARM helpers, fresh-continuation agents, forks, and tools that join the catalog mid-run. The guarantee comes from a canonical `PermissionCeiling` helper in `vidbyte/lib/` that `PermissionPolicy.check` honors.
- Report the outcome through `JevResponse` into `JevAgent.response` (`read_only: bool`), alongside the per-preset `JevPresetResult`.
- Fail open: a Jev outage, a missing answer, or one answer under the threshold keeps the caller's full catalog and policy, which is today's behavior.

### Non-Goals
- Changing the default permission of `ToolSpec` or `@tool`. A custom tool that writes but declares `SAFE` (the default) or `READ` is not caught. Read-only trusts declared permission levels, as the request specifies.
- Hiding write tools from the catalogs of agents the run starts (specialists, clones, fresh continuations). Those agents are refused at execution, not hidden.
- Adding a system-prompt note telling the main agent it is in read-only mode (see Open Questions).
- A caller-tunable read-only threshold. The preset uses one named constant, as CLARITY does.
- Rewriting the tool selector. `_select_tools` stays byte-identical.
- A generic middleware. See Alternatives.

---

## 3. Background & Context

- **Why now:** JevAgent's preflight gate already recognizes request shape (CLARITY, BULK_WORK, RUN_STATE_RELATION) and narrows the catalog by relevance (TOOL_SELECTOR). Read-only intent is the missing safety-shaped preflight: a question-shaped request should not carry edit power it never needs.
- **The problem:** A question can still lead an agent to "helpfully" change files, run commands, or post results. The caller then has to either strip write tools from the agent entirely or accept that answering a question may change their workspace.
- **Current state:**
  - `JevPreflightGate` (`vidbyte/agents/jev/gate/gate.py`) combines every enabled fixed preset's questions into one `JevDecisionRequest`, scores each preset through `DecisionModelHelper.score_noul(answers, keys, threshold, veto)`, and acts in one `match`.
  - `JevRuntime._select_tools` narrows the run-local catalog (`self.user_tools`, `self.tools`, `context.tools`) and drops a provider `tools` override. `BaseAgent` builds a fresh runtime for every run (`self._runtime().arun(...)`), so these fields are run-local.
  - Permission enforcement happens in exactly two places, and both call `PermissionPolicy.check`: `AgentRuntime._check_permission` (`vidbyte/agents/runtime.py`) and `ToolExecutor.execute_call` (`vidbyte/tools/executor.py`).
  - `run_bulk_work`, `launch_swarm`, and `fork` are declared `SAFE`, but each starts agents that run with the agent-level `settings.permission_policy`. Specialists and fresh-continuation agents carry their own policies and full tool lists. `AgentRuntime._adopt_agent_catalog` adds tools the agent gains mid-run to the live run. So narrowing only the main runtime's catalog or policy cannot guarantee "cannot write".
  - `vidbyte/lib/usage_ledger.py` already solves "reach every agent and task a run starts" with a `ContextVar` scope, because asyncio tasks copy the context in effect when they are created. `JevUsageAccount.scope()` uses it to meter specialists, workers, and helpers.
- **Constraints:** AGENTS.md placement rules (enums in `vidbyte/lib/enums/jev.py`, records in `vidbyte/lib/dataclasses/jev.py`, constants in `vidbyte/lib/constants/jev.py`, preset questions in `vidbyte/lib/jev/preflight/<preset>.py`). The field guide's Jev rules: preflight is a gate with one request and one `match`; `JevRuntime.arun` names no preset; 8–10 questions per preset, each a separate piece of evidence, with threshold equal to veto; about 500–700 tokens per question; one literal per section. `vidbyte/lib/` imports nothing above it.

---

## 4. Requirements

### Functional Requirements
1. `JevPreflightPreset.READ_ONLY` (`"read_only"`) is a valid entry in `JevRuntimeSettings.preflight`; unknown or duplicated values still fail at construction.
2. With READ_ONLY enabled, the gate adds exactly eight NOUL questions, keyed `read_only.*`, to its one batched Jev request. With it disabled, none of them is asked.
3. The preset passes only when every one of the eight P(true) values is at least `JEV_READ_ONLY_THRESHOLD`. The threshold is both the mean threshold and the per-question veto.
4. When the preset passes with `available=True`, `JevPreflightGate.read_only_requested` is `True` for that pass and `JevAgent.response.read_only` is `True`. In every other case, including a missing answer, a non-noul answer, a Jev outage, or one answer under the threshold, both are `False`.
5. `read_only_requested` is reset at the start of every `pass_`, so an earlier approval never survives into a later run.
6. On a read-only run, the main agent's catalog holds only user tools whose `spec().permission` is `SAFE` or `READ`, in their original order, plus the internal `isDone` tool. A provider `tools` override in `options` is dropped, as the tool selector does.
7. On a read-only run, every later phase runs inside `PermissionCeiling.scope(PermissionCeiling.READ_ONLY)`. That covers specialist delegation, skill preload, run-state writing, the tool selector, the bulk-work offer, and the main loop with its continuations and compute checkpoints. While the scope is active, `PermissionPolicy.check` returns `DENY` for any tool whose permission is outside the ceiling, whatever the policy itself allows.
8. A tool call refused by the ceiling never executes. In `AgentRuntime` it is recorded as a `DENIED` tool call with `error="permission_denied"`, and the message tells the model the run allows only the ceiling's permissions. `ToolExecutor` returns the same kind of error result.
9. A nested `PermissionCeiling.scope` can only narrow the active ceiling, never widen it. The scope is restored when its block exits normally or by exception.
10. The ceiling never widens a caller's policy. A tool the caller's `PermissionPolicy` denies stays denied.
11. After a read-only run returns or raises, the next run on the same agent sees the full catalog and has no ceiling active.
12. When TOOL_SELECTOR is also enabled, the read-only narrowing runs first, so the selector asks Jev only about the remaining SAFE and READ tools.
13. When BULK_WORK is also enabled and approved, the bulk-work agents receive only the narrowed tools and run under the ceiling.

### Non-Functional Requirements
- **Performance:** No added Jev call. The eight questions ride in the existing batched gate request. Catalog narrowing is O(number of tools). `PermissionPolicy.check` adds one `ContextVar.get()`.
- **Scalability / concurrency:** The ceiling is a `ContextVar`, so concurrent runs and their tasks stay isolated. A task created inside the scope inherits it, and a task created outside does not.
- **Security:** Read-only is enforced at execution, not only by hiding tools, so a model that names a hidden tool, a tool added mid-run, or a spawned agent with its own policy still cannot run anything above `READ`.
- **Observability:** `JevAgent.response.results[READ_ONLY]` carries the score and every answer. `JevAgent.response.read_only` says whether the ceiling applied. A refused call appears as a `DENIED` tool-call context with the permission in its metadata.
- **Reliability:** Fail open on any Jev failure (today's behavior). Fail closed only for managed credential or access denials, exactly as the gate already does.

---

## 5. High-Level Design

The feature has two halves: recognition in the gate, and enforcement in the runtime plus `vidbyte/lib/`. Recognition follows the established preset recipe: a new enum member and eight keys, eight question dataclasses in `vidbyte/lib/jev/preflight/read_only.py`, one `JevPresetDefinition` in `JevPresets`, registration in `JevPreflightRegistry`, and one `case` in `JevPreflightGate.pass_`. Because `combine` and `_score` already read every fixed preset from `JevPresets`, the questions join the existing single request and are scored through `DecisionModelHelper` with no new scoring code.

Enforcement uses two levers. The visible lever is the one the request names: JevRuntime narrows the main agent's run-local catalog to SAFE and READ tools, exactly the way `_select_tools` narrows it by relevance. The binding lever is a new canonical helper, `PermissionCeiling` in `vidbyte/lib/permission_ceiling.py`. It is a `ContextVar`-backed scope that caps tool permissions for the current run and every task it starts. `PermissionPolicy.check`, the single decision both enforcement points already call, consults it. JevRuntime opens the scope right after the gate passes and keeps it open for every later phase. Each agent the run starts runs in a task created inside that scope, so all of them inherit it with no per-path plumbing.

```
JevAgent.arun(message)
  └─ JevRuntime._arun_metered
       ├─ JevPreflightGate.pass_  ──one Jev request──►  [clarity…, bulk_work…, read_only.* ×8, specialist]
       │     match: case READ_ONLY passed ─► read_only_requested = True; JevResponse.read_only(True)
       └─ with JevReadOnly.ceiling(read_only_requested):          # PermissionCeiling.scope({SAFE, READ}) or nullcontext
            ├─ specialist.agent.arun(...)        ─► its PermissionPolicy.check ─► ceiling DENY above READ
            ├─ _keep_read_only_tools             ─► user_tools = JevReadOnly.tools(user_tools)   (hide)
            ├─ _select_tools  (unchanged)        ─► asks Jev only about SAFE/READ tools
            ├─ _offer_bulk_work                  ─► workers get the narrowed tools, run inside the scope
            └─ AgentRuntime.arun loop
                 └─ _run_tool_call ─► _check_permission ─► PermissionPolicy.check ─► ceiling DENY above READ
```

Key decisions. (1) Enforce in `PermissionPolicy.check` rather than in a middleware, because it is the one function every executor already calls, and a `ContextVar` reaches spawned agents that a per-agent middleware never sees. (2) Hide tools as well as refuse them, so the main agent does not plan around tools it can never use. (3) Narrow before the tool selector, so Jev is never asked about tools the run will discard. (4) Keep the gate as the only decision-maker: the runtime reads one gate flag, `read_only_requested`, the same way it reads `bulk_work_requested`, and names no preset in `arun`.

---

## 6. Detailed Design

### 6.1 PermissionCeiling (canonical helper)

**File(s):** `vidbyte/lib/permission_ceiling.py`
**Type:** New file

#### What it does
Names the highest tool permissions the current run, and every agent and task it starts, may use. It is the permission counterpart of `vidbyte/lib/usage_ledger.py`.

#### Interface / API
```python
class PermissionCeiling:
    """The tool permissions the current run, and every agent and task it starts, may still use."""

    READ_ONLY: ClassVar[frozenset[ToolPermission]] = frozenset({ToolPermission.SAFE, ToolPermission.READ})
    _active: ClassVar[ContextVar[frozenset[ToolPermission] | None]] = ContextVar("vidbyte_permission_ceiling", default=None)

    @classmethod
    def current(cls) -> frozenset[ToolPermission] | None: ...
    @classmethod
    def allows(cls, permission: ToolPermission) -> bool: ...
    @classmethod
    def denial_note(cls, permission: ToolPermission) -> str: ...
    @classmethod
    @contextmanager
    def scope(cls, allowed: Iterable[ToolPermission | str]) -> Iterator[frozenset[ToolPermission]]: ...
    @staticmethod
    def _normalize(allowed: Iterable[ToolPermission | str]) -> frozenset[ToolPermission]: ...
```

#### Logic / Algorithm
1. `scope(allowed)`: normalize `allowed` to a non-empty frozenset of `ToolPermission`; intersect it with the current ceiling when one is active; set the `ContextVar`; yield the effective ceiling; reset the token in `finally`.
2. `allows(permission)`: `True` when no ceiling is active or the permission is in it.
3. `denial_note(permission)`: `""` when `allows(permission)`, otherwise `"; this run allows only <sorted values> tools"`, appended to existing denial messages.
4. `_normalize`: reject a bare `str`/`bytes`, a non-iterable, an unknown value, or an empty set with `ConfigurationError` carrying the received value.

#### Edge Cases & Error Handling
- A nested scope whose permissions do not overlap yields an empty ceiling, which refuses everything, including `isDone`. That is the strict meaning of "narrow only" and is documented in the header.
- Context is copied into asyncio tasks when they are created. A thread started without `contextvars.copy_context()` does not inherit the ceiling. No SDK run path does this today.
- `READ_ONLY` lives on the class rather than in `lib/constants/jev.py`. It is a generic tool-permission constant, and importing `ToolPermission` into the JEV constants module would create a `lib.constants.jev ↔ lib.dataclasses` import cycle.

### 6.2 PermissionPolicy.check honors the ceiling

**File(s):** `vidbyte/lib/dataclasses/security.py`
**Type:** Modified

#### What it does
The allow-list decision also requires the run's active ceiling to allow the permission.

#### Interface / API
```python
def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision:
    """Return whether the tool call is allowed by this policy and by the run's active permission ceiling."""
```

#### Logic / Algorithm
1. `ALLOW` only when `spec.permission in self.allowed` and `PermissionCeiling.allows(spec.permission)`; otherwise `DENY`.

#### Edge Cases & Error Handling
- Outside any scope, behavior is byte-for-byte unchanged.
- `allow_all()` cannot override the ceiling.

### 6.3 Denial messages name the ceiling

**File(s):** `vidbyte/agents/runtime.py`, `vidbyte/tools/executor.py`
**Type:** Modified (one expression each)

#### What it does
When the ceiling is why a call was refused, the model-facing message says so, so a spawned agent stops retrying write tools.

#### Logic / Algorithm
1. Append `PermissionCeiling.denial_note(spec.permission)` to the existing `f"Permission denied for tool '{spec.name}' requiring {spec.permission.value}"`. Details and metadata are unchanged.

### 6.4 Enum members, keys, and threshold

**File(s):** `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`
**Type:** Modified

#### Interface / API
```python
class JevPreflightPreset(str, Enum):
    READ_ONLY = "read_only"

class JevPreflightQuestionKey(str, Enum):
    READ_ONLY_ASSESSMENT = "read_only.assessment"
    READ_ONLY_SOLE_RESULT = "read_only.sole_result"
    READ_ONLY_UNCHANGED = "read_only.unchanged"
    READ_ONLY_DESCRIBED = "read_only.described"
    READ_ONLY_USER_DECIDES = "read_only.user_decides"
    READ_ONLY_IN_REPLY = "read_only.in_reply"
    READ_ONLY_READING = "read_only.reading"
    READ_ONLY_ANSWER_MEETS_GOAL = "read_only.answer_meets_goal"

# vidbyte/lib/constants/jev.py
JEV_READ_ONLY_THRESHOLD: float = 0.75
```

### 6.5 The eight READ_ONLY questions

**File(s):** `vidbyte/lib/jev/preflight/read_only.py`
**Type:** New file

#### What it does
Eight `JevPreflightQuestion` dataclasses, one per question, plus `READ_ONLY_QUESTIONS`. Each reads the one-field state `request`, defines its terms, ends its rules with the shared `JUDGE_MEANING` and `IGNORE_CLAIMS` text, and asks one positive yes/no question. Every `true` side is evidence for a read-only run, so the preset needs no per-question inversion. A request with no task at all belongs to `false` on every question, as in BULK_WORK, so a greeting keeps today's behavior.

#### Mapping the request's four signals to questions

| Request's signal | Question | How it is carried |
|---|---|---|
| asks for an explanation, diagnosis, or opinion | `read_only.assessment` | The defined term "assessment" covers explanation, diagnosis, opinion, recommendation, plan, review, report, and an answer to a question. |
| asks for a change to be made | `read_only.unchanged` | Inverted to positive polarity: "Does `request` ask only for work that leaves everything as it is?" |
| says explicitly to change nothing or only to report | `read_only.user_decides` | Its easy-true example and a rule: an instruction to change nothing, only report, or wait for approval keeps every decision with the user. Delegation such as "handle it" or "go ahead" is the false side. |
| asks for a recommendation or plan rather than its execution | `read_only.described` | Judges how the request frames the actions it mentions: described (how, whether, which steps) or wanted done (commands, polite requests, wishes, bare problem statements). |

The four added questions close the false-positive holes the first four leave open:

| Question | Evidence it adds | A change request it catches |
|---|---|---|
| `read_only.sole_result` | The assessment is the only result asked for. | "Explain the parser and write a date validator." |
| `read_only.in_reply` | The result is given in the reply, not saved, posted, or sent. | "Summarize the logs into summary.md." |
| `read_only.reading` | The work needs only reading, not running commands, tests, or programs (EXECUTE tools would be hidden). | "Run the test suite and tell me what fails." |
| `read_only.answer_meets_goal` | Any goal the request states is met by an answer alone. | "Why does the build fail? I need it green before the release." |

#### Interface / API
```python
STATE = "The state has one field, `request`: the message a user sent to an AI agent to start a task, with any text, code, or data the user pasted into it, and nothing else."

@dataclass(frozen=True)
class ReadOnlyAssessmentQuestion(JevPreflightQuestion):
    key: JevPreflightQuestionKey = JevPreflightQuestionKey.READ_ONLY_ASSESSMENT
    instructions: JevBrief = field(default_factory=lambda: JevBrief(...))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(...))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(...))
    gap: str = "..."
# … ReadOnlySoleResultQuestion, ReadOnlyUnchangedQuestion, ReadOnlyDescribedQuestion,
#   ReadOnlyUserDecidesQuestion, ReadOnlyInReplyQuestion, ReadOnlyReadingQuestion, ReadOnlyAnswerMeetsGoalQuestion

READ_ONLY_QUESTIONS: tuple[JevPreflightQuestion, ...] = (...eight instances in key order...)
```

#### Logic / Algorithm
1. Each question follows "Writing a full question": a 2–3 sentence introduction ending "It is one of several checks on whether a request only asks for an assessment.", the shared `STATE`, one definitions string (parts before the whole, no examples), one rules string (special cases, the zero/one/many cases, the no-task side, the focus naming the separate check, then `JUDGE_MEANING` and `IGNORE_CLAIMS`), and one question starting "Does `request` ".
2. Each criterion opens with "Choose true/false when `request` …", uses the question's one verb, mirrors the other side in `not_for`, and gives one easy and one boundary example that form minimal pairs across the two sides.
3. Every section is one standalone literal (S062), wrapped in `field(default_factory=lambda: ...)` (S028). Each full question lands between 500 and 700 cl100k tokens.

#### Edge Cases & Error Handling
- Mixed requests ("explain X and fix Y") pass `assessment` but fail `unchanged`, `sole_result`, and `described`, so the run keeps its full catalog.
- Ambiguous verbs ("look into the flaky test") fail `assessment` unless the request says it wants findings back, so ambiguity keeps today's behavior.
- The `gap` text is required by `JevPreflightQuestion` and written to stand alone, though READ_ONLY never routes to the clarifier.

### 6.6 JevPresets and JevPreflightRegistry

**File(s):** `vidbyte/lib/jev/presets.py`, `vidbyte/lib/jev/preflight/preflight.py`, `vidbyte/lib/jev/preflight/__init__.py`
**Type:** Modified

#### Logic / Algorithm
1. Add `JevPresetDefinition(preset=READ_ONLY, question_keys=<eight keys in order>, threshold=JEV_READ_ONLY_THRESHOLD, veto=JEV_READ_ONLY_THRESHOLD)` with a comment that one clear no keeps the full catalog.
2. Register `*READ_ONLY_QUESTIONS` in `JevPreflightRegistry._questions`; export `READ_ONLY_QUESTIONS` from the preflight package.

### 6.7 JevPreflightGate: one commented case

**File(s):** `vidbyte/agents/jev/gate/gate.py`
**Type:** Modified

#### Interface / API
```python
self.read_only_requested: bool  # set by pass_, reset at its start
```

#### Logic / Algorithm
1. `__init__`: `self.read_only_requested = False`.
2. `pass_`: reset `self.read_only_requested = False` with the other run-local outcomes; keep a local `read_only_passed = False`.
3. Add `case JevPresetResult(preset=JevPreflightPreset.READ_ONLY, available=True, passed=True): read_only_passed = True`, commented: every read-only question reached the threshold, so the run keeps only SAFE and READ tools and still answers in full.
4. After the loop: `self.read_only_requested = read_only_passed` and `self.response.read_only(read_only_passed)`.

#### Edge Cases & Error Handling
- The existing first case (`available=False`) already fails open for outages and missing answers.
- A CLARITY stop returns before step 4, so a stopped run never records read-only.

### 6.8 JevReadOnly: the step the case triggers

**File(s):** `vidbyte/agents/jev/gate/read_only.py`, `vidbyte/agents/jev/gate/__init__.py`
**Type:** New file / Modified

#### Interface / API
```python
class JevReadOnly:
    """The action READ_ONLY's gate case turns on for one run: a SAFE/READ ceiling over every agent the run starts, and a main-agent catalog of only SAFE and READ tools."""

    @staticmethod
    def ceiling(read_only: bool) -> AbstractContextManager[object]: ...
    @staticmethod
    def tools(tools: Tools) -> Tools: ...
```

#### Logic / Algorithm
1. `ceiling(read_only)`: `PermissionCeiling.scope(PermissionCeiling.READ_ONLY)` when `read_only`, otherwise `contextlib.nullcontext()`.
2. `tools(tools)`: `tools.subset(tool.name for tool in tools if tool.spec().permission in PermissionCeiling.READ_ONLY)`.

### 6.9 JevRuntime: open the ceiling, then narrow the catalog

**File(s):** `vidbyte/agents/jev/runtime.py`
**Type:** Modified

#### Interface / API
```python
def _keep_read_only_tools(self, context: BaseAgentContext, options: Mapping[str, Any] | None) -> tuple[BaseAgentContext, Mapping[str, Any] | None]: ...
```

#### Logic / Algorithm
1. In `_arun_metered`, after the gate passes and `require_accounted()`, wrap every later step in `with JevReadOnly.ceiling(self.preflight.read_only_requested):`. That covers specialist delegation, skill preload, compute begin, run-state begin, the read-only narrowing, the tool selector, the bulk-work offer, the inherited loop, and `response.finished`.
2. `_keep_read_only_tools` (called immediately before `_select_tools`): when `read_only_requested` is false, return the inputs unchanged; otherwise set `self.user_tools = JevReadOnly.tools(self.user_tools)` and `self.tools = with_internal_agent_tools(self.user_tools)`, drop `options["tools"]`, and return `replace(context, tools=self.tools.specs())`.

#### Edge Cases & Error Handling
- The runtime is built per run, so narrowing `self.user_tools` cannot leak into the next run. A test asserts it anyway.
- `_adopt_agent_catalog` diffs against the agent's catalog, so hidden tools are never re-added. A tool the agent gains mid-run can join, and the ceiling refuses it if it is above `READ`.
- An exception inside the block resets the ceiling through the scope's `finally`.

### 6.10 Response reporting

**File(s):** `vidbyte/lib/dataclasses/jev.py`, `vidbyte/agents/jev/response.py`
**Type:** Modified

#### Interface / API
```python
@dataclass(slots=True)
class JevAgentResponse:
    read_only: bool = False   # True when the gate limited this run to SAFE and READ tools

class JevResponse:
    def read_only(self, applied: bool) -> None: ...
```

### 6.11 Public re-export

**File(s):** `vidbyte/tools/security/permissions.py` (and its package `__init__` if it re-exports)
**Type:** Modified

`PermissionCeiling` is re-exported beside `PermissionPolicy`, so any caller can run an agent under a ceiling: `with PermissionCeiling.scope(PermissionCeiling.READ_ONLY): await agent.arun(...)`. `vidbyte.__all__` is unchanged.

---

## 7. Data Model Changes

### 7.1 JevAgentResponse

**Change type:** Modified

```python
read_only: bool = False
```

**Migration strategy:** N/A. It is an in-memory record that `JevResponse.start()` rebuilds each run, with a default value.

### 7.2 JevPreflightPreset / JevPreflightQuestionKey

**Change type:** Modified (new members; see 6.4)

**Migration strategy:** Additive enum members. Serialized settings that never name `read_only` are unaffected.

---

## 8. API Changes

N/A for HTTP: the SDK exposes no endpoints. The public Python surface changes are additive:

| Surface | Change |
|---|---|
| `JevPreflightPreset.READ_ONLY` | New opt-in preset value (`"read_only"`). |
| `JevAgent.response.read_only` | New `bool`, `False` unless the gate limited the run. |
| `JevAgent.response.results[JevPreflightPreset.READ_ONLY]` | The preset's `JevPresetResult` (score and eight answers). |
| `vidbyte.tools.security.PermissionCeiling` | New run-scoped permission cap usable around any agent run. |
| `PermissionPolicy.check` | Also denies anything above an active ceiling (no change outside a scope). |

Error cases:

| Condition | Result |
|---|---|
| `PermissionCeiling.scope("read")` (bare string) | `ConfigurationError` |
| `PermissionCeiling.scope(())` (empty) | `ConfigurationError` |
| `PermissionCeiling.scope({"admin"})` (unknown) | `ConfigurationError` |
| A tool above the ceiling is called | `DENIED` tool result, `error="permission_denied"`, message names the ceiling |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-read-only-intent.md` | This design doc |
| CREATE | `vidbyte/lib/permission_ceiling.py` | `PermissionCeiling`, the run-scoped permission cap |
| MODIFY | `vidbyte/lib/dataclasses/security.py` | `PermissionPolicy.check` honors the ceiling |
| MODIFY | `vidbyte/agents/runtime.py` | Denial message names the ceiling |
| MODIFY | `vidbyte/tools/executor.py` | Denial message names the ceiling |
| MODIFY | `vidbyte/tools/security/permissions.py` | Re-export `PermissionCeiling` |
| MODIFY | `vidbyte/lib/enums/jev.py` | `READ_ONLY` preset and eight question keys |
| MODIFY | `vidbyte/lib/constants/jev.py` | `JEV_READ_ONLY_THRESHOLD` |
| CREATE | `vidbyte/lib/jev/preflight/read_only.py` | The eight fixed questions |
| MODIFY | `vidbyte/lib/jev/preflight/__init__.py` | Export `READ_ONLY_QUESTIONS` |
| MODIFY | `vidbyte/lib/jev/preflight/preflight.py` | Register the questions |
| MODIFY | `vidbyte/lib/jev/presets.py` | `READ_ONLY` definition |
| MODIFY | `vidbyte/lib/jev/preflight/README.md` | Where things live: `read_only.py` |
| CREATE | `vidbyte/agents/jev/gate/read_only.py` | `JevReadOnly`, the step the case triggers |
| MODIFY | `vidbyte/agents/jev/gate/__init__.py` | Export `JevReadOnly` |
| MODIFY | `vidbyte/agents/jev/gate/gate.py` | `read_only_requested` and one `case` |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Ceiling scope and `_keep_read_only_tools` |
| MODIFY | `vidbyte/lib/dataclasses/jev.py` | `JevAgentResponse.read_only` |
| MODIFY | `vidbyte/agents/jev/response.py` | `JevResponse.read_only` |
| MODIFY | `vidbyte/agents/jev/README.md` | Document the preset |
| MODIFY | `REPO_MAP.md` | JEV File Locations rows |
| MODIFY | `skills/jev-agent/SKILL.md` | Mention READ_ONLY in the scaffold |
| CREATE | `tests/features/jev_read_only/FEATURE.md` | Feature contract |
| CREATE | `tests/features/jev_read_only/README.md` | Feature pack index |
| CREATE | `tests/features/jev_read_only/test_jev_read_only.py` | Unit and integration tests |
| CREATE | `scripts/test-jev-read-only.py` | Focused verification script |

---

## 10. Testing Plan

All tests are offline. Jev is replaced by a scripted `DecisionModelHelper`, and models are replaced by scripted runners routed through `BaseAgent._runner_for_model`, as in the bulk-work pack. Tool execution, permission checks, and the runtime stay real.

### Unit Tests
- `PermissionCeilingTests` → `test_no_scope_allows_every_permission` — [Edge Case]
- `PermissionCeilingTests` → `test_scope_denies_write_and_execute_and_restores_on_exit` — [Hidden Failure]
- `PermissionCeilingTests` → `test_scope_restores_after_an_exception` — [Hidden Failure]
- `PermissionCeilingTests` → `test_a_nested_scope_cannot_widen_the_ceiling` — [Silent Failure]
- `PermissionCeilingTests` → `test_rejects_a_bare_string_an_empty_set_and_an_unknown_value` — [Hidden Assumption]
- `PermissionCeilingTests` → `test_tasks_created_inside_inherit_and_concurrent_runs_stay_isolated` — [Hidden Failure]
- `PermissionCeilingTests` → `test_allow_all_policy_and_tool_executor_are_capped_with_a_named_reason` — [Silent Failure]
- `PermissionCeilingTests` → `test_the_ceiling_never_widens_a_narrower_caller_policy` — [Hidden Assumption]
- `ReadOnlyQuestionTests` → `test_preset_registers_eight_ordered_questions_with_threshold_as_veto` — [Edge Case]
- `ReadOnlyQuestionTests` → `test_each_question_asks_one_positive_question_in_the_house_layout` — [Hidden Assumption]
- `ReadOnlyQuestionTests` → `test_every_section_is_one_standalone_literal` — [Hidden Assumption]
- `ReadOnlyQuestionTests` → `test_each_full_question_stays_between_500_and_700_tokens` — [Edge Case]
- `ReadOnlyQuestionTests` → `test_the_request_signals_map_to_their_questions` (key set includes the four mapped keys; `unchanged` asks positively) — [Silent Failure]
- `ReadOnlyGateTests` → `test_every_answer_at_the_threshold_requests_read_only` — [Edge Case]
- `ReadOnlyGateTests` → `test_one_answer_below_the_threshold_vetoes_a_high_mean` (each key) — [Hidden Failure]
- `ReadOnlyGateTests` → `test_a_missing_answer_fails_open` — [Silent Failure]
- `ReadOnlyGateTests` → `test_a_jev_outage_fails_open` — [Hidden Failure]
- `ReadOnlyGateTests` → `test_the_gate_resets_its_flag_between_passes` — [Hidden Assumption]
- `ReadOnlyGateTests` → `test_disabled_preset_asks_no_read_only_question` — [Edge Case]
- `ReadOnlyGateTests` → `test_read_only_and_bulk_work_share_one_request` — [Hidden Assumption]
- `ReadOnlyToolsTests` → `test_keeps_only_safe_and_read_tools_in_order` and `test_an_empty_catalog_stays_empty` — [Edge Case]
- `ReadOnlyToolsTests` → `test_the_ceiling_switch_opens_a_scope_only_for_a_read_only_run` — [Silent Failure]

### Integration Tests
- `ReadOnlyRuntimeTests` → `test_a_read_only_run_offers_only_safe_and_read_tools` (main runner's tool schemas) — [Silent Failure]
- `ReadOnlyRuntimeTests` → `test_a_provider_tools_override_is_dropped_on_a_read_only_run` (FR 6; a vetoed run keeps it) — [Silent Failure]
- `ReadOnlyRuntimeTests` → `test_a_hidden_tool_named_by_the_model_never_executes` — [Hidden Failure]
- `ReadOnlyRuntimeTests` → `test_a_write_tool_added_mid_run_is_denied_by_the_ceiling` (proves the second layer, and that the refusal is recorded as a `DENIED` call, FR 8) — [Hidden Failure]
- `ReadOnlyRuntimeTests` → `test_a_vetoed_request_keeps_the_full_catalog_and_writes` — [Edge Case]
- `ReadOnlyRuntimeTests` → `test_the_next_run_gets_the_full_catalog_and_no_ceiling` — [Hidden Assumption]
- `ReadOnlyRuntimeTests` → `test_a_chosen_specialist_cannot_write` — [Hidden Failure]
- `ReadOnlyRuntimeTests` → `test_bulk_work_agents_receive_only_read_tools` — [Hidden Failure]
- `ReadOnlyRuntimeTests` → `test_the_tool_selector_is_asked_only_about_read_tools` — [Silent Failure]
- `ReadOnlyRuntimeTests` → `test_the_ceiling_is_gone_after_a_run_raises` — [Hidden Failure]
- `ReadOnlyRuntimeTests` → `test_response_reports_read_only_and_resets_each_run` — [Silent Failure]

What is mocked: only Jev's decision transport and the model runners. What is real: settings validation, registry, gate scoring, `PermissionPolicy`, `AgentRuntime` tool execution and denial, `ParallelPipeline` for bulk work, and specialist delegation. Silent paths between components: a ceiling opened after delegation (the specialist writes), a narrowed catalog that leaks into the next run, the selector asking about discarded tools, and a ceiling left active after an exception. Each has a dedicated test above.

### Manual / QA Test Cases
1. Given a JevAgent with `write_text`, `read_text`, and `bash` and READ_ONLY enabled, when asked "Why does tests/test_x.py fail? Don't change anything.", then the run offers only `read_text` (plus `isDone`), `response.read_only` is True, and no file changes. — [Edge Case]
2. Given the same agent, when asked "Fix the failing test in tests/test_x.py.", then at least one read-only answer falls below 0.75, the full catalog is offered, and `response.read_only` is False. — [Hidden Failure]
3. Given a read-only run with a specialist whose agent has `write_text`, when Jev picks the specialist, then its `write_text` call is denied with a message naming the read-only ceiling. — [Hidden Assumption]
4. Given TypeSafe unreachable, when any request runs, then the full catalog is kept (fail open). — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| TypeSafe Jev (via Vidbyte-managed decisions) | existing `DecisionModelConfig.vidbyte_managed()` | Answers the eight questions in the existing gate request | Mis-calibration may restrict a change request; mitigated by the all-question veto and fail-open |
| `contextvars` (stdlib) | Python ≥ 3.10 | Run-scoped ceiling | A thread started without copying context would not inherit the ceiling |
| `tiktoken` (dev, optional) | existing | Token-length test | The test is skipped when it is not installed, as in bulk work |

---

## 12. Rollout & Deployment

- **Feature flag:** The preset is opt-in. Nothing changes until a caller adds `JevPreflightPreset.READ_ONLY` to `JevRuntimeSettings.preflight`.
- **Breaking change:** No. `PermissionPolicy.check` is unchanged outside a ceiling scope, and no SDK code opens one except JevRuntime on a read-only run.
- **Deployment order:** SDK only. A later backend pin bump picks it up.
- **Rollback:** Revert the PR. No persisted data depends on it.

---

## 13. Open Questions

- [ ] **Four requested signals → eight questions.** The request listed four signals. The repository's preset rule (8–10 questions, each separate evidence, threshold = veto) and the question-writing skill (positive polarity, one judgment each) shaped them into eight questions: "asks for a change" is inverted, and "says explicitly to change nothing" becomes the strongest-yes case of a necessary question, because as worded it would veto most ordinary questions. Confirm this reading.
- [ ] **Threshold 0.75** matches BULK_WORK, the other all-veto preset. It should be tuned on a labeled set of 50–100 real requests.
- [ ] **System-prompt note.** Should a read-only run also tell the main agent that it is answering without changes, so it does not say "I can't edit"? That would add a Jev prompt family; it is left out here.
- [ ] **Spawned agents' catalogs.** Specialists and fresh-continuation agents are refused at execution but still see their write tools. Hiding those tools too would need a runtime-level catalog filter keyed on the ceiling.

---

## 14. Alternatives Considered

### Alternative 1: A `ToolPermissionMiddleware` in `vidbyte/middleware/builtins/`
- What: A `before_tool_call` middleware that denies calls above `READ`, added per run by JevRuntime.
- Why rejected: Middleware is per agent. The specialist, bulk-work agents, clones, swarm helpers, fresh continuations, and forks each build their own pipeline, so they would never see it, and the request's "cannot edit/write anything" would fail through any of them. A middleware also only runs in `AgentRuntime`, not in `ToolExecutor`, it needs the catalog to map a call's name to its permission, and JevRuntime would have to rebuild the `MiddlewarePipeline` per run. The ceiling reaches all of them through the one function they already call.

### Alternative 2: Narrow `JevRuntime.permission_policy` for the run
- What: Replace the run-local runtime's policy with `PermissionPolicy()` (SAFE, READ).
- Why rejected: It binds only the main loop. Every spawned agent above reads the agent-level policy, so writes would still be possible.

### Alternative 3: Skip spawning paths on a read-only run
- What: Do not delegate to specialists, do not offer bulk work, and disable compute and fresh continuations when read-only.
- Why rejected: It needs several preset-aware branches in `JevRuntime.arun`, which review has rejected before. It also removes legitimate read-only uses such as parallel reviews, and it still misses tools added mid-run and `fork`.

### Alternative 4: Four questions with a plain mean
- What: Ask the four signals as written and pass on their mean.
- Why rejected: The signals point in different directions and are rarely all present. A plain "why does X fail?" scores about 0.5, while "explain X and fix Y" can still clear a low bar. This contradicts the repository's all-veto preset rule and the skill's polarity and one-judgment rules.
