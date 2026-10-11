# Design Doc: CodingAgent verify_command (the run may not finish until a command passes)

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11

---

## 1. Overview

`CodingAgent` gets two new keywords: `verify_command` and `max_verify_attempts`. When `verify_command` is set, each time the model tries to end the run, the agent runs that command once, as `bash -c <command>` in `root_dir`, using the same bash and the same bounds as the `bash` tool. Exit code 0 accepts the finish. Any other outcome rejects it: the model receives "Not done yet: the verification command `<cmd>` failed (exit code N). Its output is below. Fix the problem, then finish again." followed by the output, and the loop continues. After `max_verify_attempts` failed verifications, the run ends without raising. It returns the model's last answer with `stop_reason="contract_unsatisfied"`, and `metadata["verify_command"]` records `passed`, `attempts`, and `last_exit_code`. The feature exists because the most common agent failure is claiming "Done!" while the work does not actually work. With `verify_command=None` (the default), nothing changes.

---

## 2. Goals & Non-Goals

### Goals
- Add `verify_command: str | None = None` and `max_verify_attempts: int = 3` to `CodingAgent`, each as a validated field on `CodingAgentSettings`. A bad value fails at construction with a `ConfigurationError` that names the field.
- Run the command only when the model tries to finish, on both finish paths of the linear runtime: a plain final answer with no tool calls, and the internal `isDone` tool.
- Reuse `BashTool` for the run, so the Git for Windows lookup, the 600 s limit, the 50,000-byte cap, and the kill/grace logic are not duplicated.
- Send the failure (command, exit code or reason, output) back to the model, and stop after `max_verify_attempts` failures with a stop reason and metadata that cannot be mistaken for success.
- Run output contracts first and verification second, so the command never runs for an answer that the contracts reject anyway.
- Keep behavior byte-identical when `verify_command` is `None`, and keep `BaseAgent` unchanged for every agent with no finish review.

### Non-Goals
- Any CLI change. An SDK agent runs from its Python API only (field guide, Prebuilt Agents), so `vidbyte/cli/` is not touched and no CLI flag is listed as a follow-up.
- Sanitizing or restricting the command. The developer writes it, not the model, so it is trusted input. The agent's `PermissionPolicy` governs the model's tool calls, not this command.
- A configurable timeout or output cap for the command. It uses the `BASH_*` constants, as the bash tool does (spec NG-14).
- Running verification between turns, or when the model calls `bash` itself.
- Exporting the verification middleware for use on other agents (Open Question Q-1).
- Showing finish reviews in `AuditLogMiddleware` or in diagnostic hook spans (Open Question Q-2).
- Any change to the context window, AGENTS.md loading, or the sibling `feat/coding-agent-agents-md` work.

---

## 3. Background & Context

- **Why now.** The user asked for this setting by name ("verify_cmd"), calling it "likely the biggest boost to success rate on the list". In their words: "A command, usually the test suite, that must pass before the agent is allowed to end the run. If it fails, the output goes back to the agent with 'not done yet', up to a retry limit (about 3)."
- **The current state.** `CodingAgent` (`vidbyte/agents/coding.py`) only gathers its arguments into `CodingAgentSettings`, builds `CodingAgentTools`, and calls `BaseAgent.__init__`. Its header forbids overriding any `BaseAgent` method, adding a default system prompt, reading keys from the environment, and keeping the settings record on the agent.
- **How a run ends today.** In `AgentRuntime._arun_once` (`vidbyte/agents/runtime.py`) there are two finish points. (1) The model returns text with no tool calls: the output contracts are checked, then the run ends with `FINAL_RESPONSE`. (2) The model calls `isDone`: `after_iteration` runs, then the contracts are checked, then the run ends with `IS_DONE`. At both points, unmet contracts append feedback and continue, and when `max_contract_rejections` is spent they stop with `CONTRACT_UNSATISFIED`. `_continue_finish_attempt` is a subclass seam that only `JevRuntime` overrides.
- **Why the existing middleware hooks cannot do it.** The brief asked whether a middleware can see a finish, run an async command, and turn the finish into "continue with this user message". It cannot.
  - `after_model_response` (`runtime.py:457`) turns any non-`CONTINUE` decision into a `MIDDLEWARE_ABORT` result, and the runtime never applies its transform.
  - `RETRY` is handled only in `on_model_error` (`:682`) and `after_tool_call` (`:1568`), where it re-runs the same model call or tool call.
  - `after_iteration` at a finish point can only abort. On the `isDone` path it also runs before the contracts.
  - `MiddlewareTransform.provider_messages` is applied only in `before_model_call`, as a replacement for that call's messages.
  - No hook can express all three outcomes a verifier needs: accept, reject with feedback and continue, or stop while keeping the model's answer.
- **The output-contract loop cannot be reused directly.** `OutputContract.satisfied(counters)` is synchronous and counter-based. Contracts share one `max_contract_rejections` budget, and they are exported and restored by name through `RunState`. A command-backed contract would have to change all three.
- **An unused record already fits.** `FinishReview` / `FinishReviewAction` (`vidbyte/lib/dataclasses/agents.py`) are an existing, exported record that already has exactly these three outcomes: `accept()`, `continue_with(feedback)`, and `stop(feedback)`. It was written for the `review_finish_attempt` seam in `d40829af`. PR #471 replaced that seam with `_continue_finish_attempt`, and nothing has used the record since.
- **Constraints.**
  - CodingAgent overrides no BaseAgent method; JevAgent rejects specialists that replace `generate_reply`.
  - `vidbyte/lib` cannot import `vidbyte.tools`, so `CodingAgentSettings` cannot look for bash.
  - Lint rules S024 (nesting depth 3), A007 (named operational constants), C006 (numeric guards reject bool first), and C016 (the public API contract) all apply.

---

## 4. Requirements

### Functional Requirements
1. `CodingAgent.__init__` accepts the keyword-only `verify_command: str | None = None` and `max_verify_attempts: int = 3`, and passes both into `CodingAgentSettings`.
2. `CodingAgentSettings` rejects a `verify_command` that is neither `None` nor a non-blank `str`, and a `max_verify_attempts` that is not a real `int` (a `bool` is rejected) of at least 1. Each failure is a `ConfigurationError` whose message names the field.
3. With `verify_command=None`, `CodingAgent` passes the caller's keywords to `BaseAgent` unchanged: no extra middleware, no extra model calls, and the same messages, results, and metadata as before.
4. With `verify_command` set, the agent passes the caller's middleware to `BaseAgent` with one `VerifyCommandMiddleware` appended after it.
5. When `verify_command` is set but no bash can be found at construction, construction fails with a `ConfigurationError` naming `verify_command`. `BashTool` resolves its executable once at construction, so no verification could ever pass later.
6. Each time the model tries to finish (a final answer with no tool calls, or an `isDone` call), and after any output contracts have accepted the answer, the runtime asks the middleware to review the finish. Verification runs the command exactly once per review.
7. The command runs through `BashTool.execute` over the resolved `root_dir`, with the module's `BASH_TIMEOUT_SECONDS`, `BASH_MAX_OUTPUT_BYTES`, and `BASH_KILL_GRACE_SECONDS` read at call time.
8. Exit code 0 accepts the finish, and the run ends exactly as it would have without verification (`FINAL_RESPONSE` or `IS_DONE`).
9. A non-zero exit, a timeout, or a spawn failure rejects the finish. The model then reads `Not done yet: the verification command `<cmd>` failed (<reason>). Its output is below. Fix the problem, then finish again.` followed by a blank line and the bash tool's output. `<reason>` is `exit code N`, `it timed out`, or `bash could not start it`.
   - On the text path, the model's answer is appended as an assistant message, followed by the feedback as a user message.
   - On the `isDone` path, the `isDone` call and any later calls in the same turn are answered as they are today before a continuation (`finish attempt not accepted yet; continue with the next message`), and the feedback follows as a user message. It is not the `isDone` error result, because `ToolsFormatter` cuts tool-error text to 1,000 characters, and the end of a test run's output is usually the part that matters.
10. When the `max_verify_attempts`-th verification fails, the run ends without raising. The output is the model's last answer, and `stop_reason` is `contract_unsatisfied`.
11. Once at least one verification has run, `metadata["verify_command"]` is `{"passed": bool, "attempts": int, "last_exit_code": int | None}`, including when the run later stops for another reason (for example `max_iterations`).
12. The model's own `bash` calls never trigger verification and never count as attempts. A verification is not a tool call: it does not appear in `tool_call_states`, `tool_calls`, or usage.
13. Verification runs in `root_dir` even if the process working directory changes after construction.
14. A plain `BaseAgent`, or any agent whose middleware does not override `review_finish`, behaves exactly as before.
15. `CodexAgent` rejects a middleware that overrides `review_finish` at construction, as it already does for every hook it cannot enforce.

### Non-Functional Requirements
- **Performance.** One extra `await` per middleware per finish attempt when no review is configured, and none between turns. With verification on, the cost is one bash process per finish attempt.
- **Bounds.** Each verification returns within `BASH_TIMEOUT_SECONDS + BASH_KILL_GRACE_SECONDS`. The output the model sees is capped at `BASH_MAX_OUTPUT_BYTES` and carries the bash tool's truncation marker.
- **Cancellation.** A cancelled run cancels the verification. `BashTool` kills the command and re-raises `CancelledError`, and nothing on this path catches it.
- **Security.** The command inherits the parent environment and is not confined to `root_dir`, exactly like the `bash` tool. It runs even under a read-only `PermissionPolicy`, because it is the developer's command, not the model's.
- **Observability.** `metadata["verify_command"]` and `stop_reason` make the outcome visible. The session failure router already maps `contract_unsatisfied` to `FailureCode.CONTRACT_UNSATISFIED` (`EXHAUSTED`, `ROUTE`), so a failed verification is recorded as a failure with no router change.
- **Reliability.** An exception raised inside `review_finish` propagates, as an exception from an output contract or a Jev continuation does at the same point. Accepting would report an unreviewed answer as finished, and the decision hooks' "abort" would throw the answer away.

---

## 5. High-Level Design

The runtime gains one middleware hook, `review_finish`. The verification command is a middleware that implements it, and `CodingAgent` appends that middleware to the caller's own when `verify_command` is set. The middleware list is the only channel `CodingAgent` has into the runtime without overriding a `BaseAgent` method. It also gives forks and sessions the expected behavior for free: `fork()` copies `agent.middleware`, and `export_state()` never includes middleware, so exported state stays identical to a plain `BaseAgent` with the same tools and policy.

`review_finish` returns the existing `FinishReview` record rather than a `MiddlewareDecision`. A finish review needs three outcomes: accept; reject, send feedback, and continue; and reject and stop while keeping the model's answer. `MiddlewareDecision` cannot express the third, because its abort replaces the output with "Agent runtime stopped by middleware" and stops with `MIDDLEWARE_ABORT`. `FinishReview` was written for exactly this purpose and is currently unused. `MiddlewarePipeline.review_finish` asks each middleware in order, and the first review that does not accept decides. The default `AgentMiddleware.review_finish` accepts, so every existing middleware is a no-op reviewer.

In `_arun_once`, the review sits immediately after the output-contract block on both finish paths. The order is therefore contracts first, then verification, then `JevRuntime`'s `_continue_finish_attempt`. A `CONTINUE` review appends feedback the way a contract rejection does. A `STOP` review ends the run with the candidate answer and `CONTRACT_UNSATISFIED`, the way contract exhaustion does. `CONTRACT_UNSATISFIED` is reused because it already means "a condition required before finishing was never met within its attempt budget", and the session failure router already classifies it as a routable failure. The unused `FINISH_REVIEW_REJECTED` value is unmapped there, so it would surface as `RUNTIME_ERROR`.

`VerifyCommandMiddleware` builds one `BashTool(root_dir)` at construction and fails there if that tool found no bash. At each review it runs `BashTool.execute(ToolCall("bash", {"command": cmd}))`, records a validated `CodingVerification(attempts, last_exit_code)` in the run's `run_state`, and publishes `metadata["verify_command"]` through `AgentRuntimeStateKey.RESULT_METADATA`, the generic channel `_with_run_state_metadata` already lifts into the result. It then returns `accept`, `continue_with(feedback)`, or, on the last allowed attempt, `stop(feedback)`.

```
CodingAgent.__init__ ──► CodingAgentSettings (validates verify_command, max_verify_attempts)
        │                         │
        │  verify_command set     ▼
        ├──────────────► VerifyCommandMiddleware(cmd, root_dir, max) ── BashTool(root_dir)
        ▼                                         (no bash → ConfigurationError)
BaseAgent(middleware=(*caller, verifier)) ──► AgentRuntime._arun_once
                                                   │ model finishes (text or isDone)
                                                   ▼
                                      output contracts (unchanged)
                                                   │ accepted
                                                   ▼
                                MiddlewarePipeline.review_finish(ctx)
                                                   │
                     ┌──────────── accept ─────────┼──── continue_with ─────┐──── stop ───────────┐
                     ▼                             │                        ▼                     ▼
          (Jev continuation) → finish        bash -c cmd in root_dir   feedback → model    answer + CONTRACT_UNSATISFIED
          FINAL_RESPONSE / IS_DONE           metadata["verify_command"]   loop continues
```

---

## 6. Detailed Design

### 6.1 Finish-review hook on middleware

**File(s):** `vidbyte/lib/dataclasses/middleware.py`, `vidbyte/middleware/base.py`, `vidbyte/middleware/pipeline.py`
**Type:** Modified

#### What it does
It adds the `review_finish` hook point. The default implementation accepts, and the pipeline returns the first review that does not accept.

#### Interface / API
```python
class MiddlewareHook(str, Enum):
    ...
    REVIEW_FINISH = "review_finish"

class AgentMiddleware(ABC):
    async def review_finish(self, ctx: MiddlewareContext) -> FinishReview:
        """Review a finish attempt after the output contracts accept it; the default accepts."""

class MiddlewarePipeline:
    async def review_finish(self, ctx: MiddlewareContext) -> FinishReview:
        """Ask each middleware in order to review a finish attempt; the first review that does not accept it decides."""
```

#### Logic / Algorithm
1. For each middleware in configured order, `await middleware.review_finish(ctx)`.
2. If `review.action is not FinishReviewAction.ACCEPT`, return that review.
3. If every middleware accepts (or there are none), return `FinishReview.accept()`.

#### Edge Cases & Error Handling
- Exceptions propagate (see the Reliability NFR). The docstrings say so, because the decision hooks handle exceptions through `fail_closed`.
- The hook records no `MiddlewareEvent` and no hook-invocation span, because it is not a decision hook. A reviewer reports through result metadata (Q-2).

### 6.2 `FinishReview` made live

**File(s):** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified (in place)

#### What it does
The record already exists. Its docstrings now point at `AgentMiddleware.review_finish` instead of the removed `AgentRuntime.review_finish_attempt`. `stop` now documents `CONTRACT_UNSATISFIED` and that its feedback is not shown to the model. A `__post_init__` makes the record validate itself (AGENTS.md rule 4).

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class FinishReview:
    action: FinishReviewAction = FinishReviewAction.ACCEPT
    feedback: str = ""
    def __post_init__(self) -> None: ...  # action is a FinishReviewAction; feedback is str; CONTINUE needs non-blank feedback
```

#### Edge Cases & Error Handling
- `continue_with("")` raises `ValueError`, matching the `MiddlewareDecision` decision record. A blank feedback would send the model an empty message, a silent failure.

### 6.3 Runtime: review at both finish points

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### Logic / Algorithm
- **Text path**, after the output-contract block:
  1. `review = await self.middleware.review_finish(self._middleware_context(MiddlewareHook.REVIEW_FINISH, state))`.
  2. On `STOP`, return `_finish_result(self._unverified_finish_result(last_assistant_output or "", state), state)`.
  3. On `CONTINUE`, append `self._assistant_message(last_assistant_output or "")`, then `{"role": "user", "content": review.feedback}`, and `continue`.
  4. On `ACCEPT`, fall through to the existing code unchanged.
- **`isDone` path**, after the existing lines that answer `isDone` (`finish attempt not accepted yet; continue with the next message`) and the turn's later calls, and before `_continue_finish_attempt`:
  1. The same call, with `tool_call=call` and `tool_result=result`.
  2. On `STOP`, return `_finish_result(self._unverified_finish_result(result.output or "", state), state)`.
  3. On `CONTINUE`, append `{"role": "user", "content": review.feedback}`, set `finish_attempt_continued = True`, and `break`. This is the message order a `JevRuntime` continuation already produces at the same spot.
  4. On `ACCEPT`, nothing changes.
  - Why not the `isDone` error result, as a contract rejection uses: `ToolsFormatter._clean_text` cuts every tool-error message to 1,000 characters, so a test run's summary at the end of its output would never reach the model. A user message is not cut. (This replaced the first draft of this section during implementation, when the output-cap test caught it.)
- **New helper** `_unverified_finish_result(output, state) -> AgentResult` returns `self._final_result(output=output, runner_metadata={}, contexts=state.call_contexts, iteration_count=state.iteration_count, tokens_used=state.tokens_used, stop_reason=AgentStopReason.CONTRACT_UNSATISFIED)`. This is the same shape contract exhaustion builds.

#### Edge Cases & Error Handling
- No new control-flow statement is nested deeper than the contract block's own `if`s, so S024 gains no findings.
- With an inner context-window algorithm, a plain final answer does not end the run. Like the output contracts, the review still treats it as a finish attempt. This is documented as an edge case.
- A `STOP` or `CONTINUE` review skips `after_iteration` on the text path, as a contract rejection does.
- With an `output_schema`, an answer that does not match the schema still raises `OutputSchemaViolationError` (with `stop_reason` `contract_unsatisfied` after a `STOP`), exactly as after contract exhaustion. That is the schema's own rule in `BaseAgent`; the verification itself never raises.

### 6.4 `VerifyCommandMiddleware`

**File(s):** `vidbyte/middleware/builtins/verify_command.py`
**Type:** New file (not re-exported from `vidbyte.middleware.builtins`; Q-1)

#### Interface / API
```python
class VerifyCommandMiddleware(AgentMiddleware):
    def __init__(self, command: str, root_dir: Path, max_attempts: int) -> None: ...
    async def review_finish(self, ctx: MiddlewareContext) -> FinishReview: ...
    def _record_attempt(self, run_state: dict[Any, Any], result: ToolResult) -> CodingVerification: ...
    @staticmethod
    def _publish(run_state: dict[Any, Any], verification: CodingVerification) -> None: ...
    def _feedback(self, result: ToolResult) -> str: ...
```

#### Logic / Algorithm
1. `__init__` stores the command and the limit, and builds `BashTool(root_dir)`. If `bash.executable is None`, it raises `ConfigurationError("CodingAgent verify_command needs bash, but none was found. …", details={"parameter": "verify_command"})`. Its inputs come from a validated `CodingAgentSettings` and are not re-checked.
2. `review_finish` (the narrated main function) runs four steps:
   1. Run `await self._bash.execute(ToolCall("bash", {"command": self._command}))`.
   2. Call `_record_attempt`: read the previous `CodingVerification` under `run_state[type(self)]`, build a new one with `attempts + 1` and the result's `metadata["exit_code"]` (or `None`), store it, and return it.
   3. Call `_publish`: merge `{"verify_command": {"passed", "attempts", "last_exit_code"}}` into `run_state[AgentRuntimeStateKey.RESULT_METADATA.value]`.
   4. Decide the review: `accept()` if `passed`. Otherwise build the feedback, then return `stop(feedback)` if `attempts >= max_attempts`, else `continue_with(feedback)`.
3. `_feedback` fills `VERIFY_COMMAND_FEEDBACK` with the command, the reason (`exit code N`, `it timed out`, or `bash could not start it`), and the bash tool's `result.output`. That output already carries the truncation marker and either the `exit code:` line or the timeout line.

#### Edge Cases & Error Handling
- The command is not validated as a tool call. Settings already guarantee non-blank text, and the permission policy does not apply (trusted input).
- `run_state` is new for every runtime attempt, so attempts never leak across runs or between a parent agent and its fork. They share the middleware instance, which holds no per-run state.
- Cancellation propagates, because `BashTool.execute` re-raises `CancelledError` after the kill.

### 6.5 `CodingVerification` record and constants

**File(s):** `vidbyte/lib/dataclasses/coding.py` (record), `vidbyte/lib/constants/coding.py` (new)
**Type:** Modified / New file

#### Interface / API
```python
CODING_DEFAULT_MAX_VERIFY_ATTEMPTS = 3
CODING_MIN_VERIFY_ATTEMPTS = 1

@dataclass(frozen=True, slots=True)
class CodingVerification:
    """How many times one run's verification command ran, and the exit code of the last run."""
    attempts: int
    last_exit_code: int | None
    @property
    def passed(self) -> bool: return self.last_exit_code == 0
```
- `passed` is derived from the data, never stored, so it cannot contradict `last_exit_code`. This follows field guide C002.
- `__post_init__` checks two things: `attempts` is an int (not a bool) of at least `CODING_MIN_VERIFY_ATTEMPTS`, and `last_exit_code` is `None` or an int (not a bool).

### 6.6 `CodingAgentSettings` fields

**File(s):** `vidbyte/lib/dataclasses/coding.py`
**Type:** Modified

```python
verify_command: str | None = None
max_verify_attempts: int = CODING_DEFAULT_MAX_VERIFY_ATTEMPTS
def _check_verification(self) -> None: ...  # called from __post_init__
```
- `verify_command` must be `None` or a non-blank str. The error is `"CodingAgent verify_command must be None or a non-blank string."` with `details={"parameter": "verify_command", "verify_command_type": ...}`.
- `max_verify_attempts` must be an int, not a bool, and at least 1. The error is `"CodingAgent max_verify_attempts must be a whole number of at least 1."` with `details={"parameter": "max_verify_attempts", "max_verify_attempts": repr(value)}`.
- `max_verify_attempts` is validated even when `verify_command` is `None`, because a bad argument fails at the boundary.

### 6.7 `CodingAgent` wiring

**File(s):** `vidbyte/agents/coding.py`
**Type:** Modified

```python
def __init__(self, *, root_dir, firecrawl_api_key=None, browserbase_api_key=None, parallel_api_key=None, tavily_api_key=None,
             verify_command: str | None = None, max_verify_attempts: int = CODING_DEFAULT_MAX_VERIFY_ATTEMPTS,
             tools=(), permission_policy=None, **kwargs) -> None:
```
1. Pass both values into `CodingAgentSettings`.
2. After `CodingAgentTools`, if `settings.verify_command is not None`, set `kwargs["middleware"] = (*kwargs.get("middleware", ()), VerifyCommandMiddleware(settings.verify_command, self.root_dir, settings.max_verify_attempts))`.
3. Otherwise leave `kwargs` untouched.

There is still no `raise` in `__init__` and no method other than `__init__`.

### 6.8 `BashTool.executable`

**File(s):** `vidbyte/tools/builtins/bash.py`
**Type:** Modified

```python
@property
def executable(self) -> str | None:
    """Return the bash executable resolved at construction, or None when this platform has none."""
```
This is a read-only view of the lookup the tool already does once. The middleware needs it to fail at construction without reaching into a private attribute.

### 6.9 Codex unsupported hook

**File(s):** `vidbyte/lib/constants/codex.py`, `vidbyte/agents/codex/README.md`
**Type:** Modified

Add `"review_finish"` to `CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS`. The constant's own comment requires it: "Declaring one must fail at construction rather than load successfully and never run". Codex owns its loop, so it has no finish point to review.

---

## 7. Data Model Changes

### 7.1 `CodingAgentSettings`
**Change type:** Modified. It gains two fields, `verify_command: str | None = None` and `max_verify_attempts: int = 3`. Construction is in memory only, with no persistence and no migration.

### 7.2 `CodingVerification`
**Change type:** New frozen record (§6.5). It lives only in `run_state` for the duration of one run.

### 7.3 `FinishReview`
**Change type:** Modified in place. It gains validation and corrected docstrings, with no new fields.

### 7.4 `MiddlewareHook`
**Change type:** Modified. One new member, `REVIEW_FINISH = "review_finish"`.

### 7.5 Result metadata
**Change type:** New key `metadata["verify_command"] = {"passed": bool, "attempts": int, "last_exit_code": int | None}`. It is present once at least one verification has run.

**Migration strategy:** N/A. These are in-memory records with no stored schema. Rollback is reverting the PR.

---

## 8. API Changes

N/A for HTTP: the SDK is an in-process library, and no endpoint changes. Python API changes:

| Symbol | Change |
|---|---|
| `CodingAgent.__init__` | New keyword-only `verify_command`, `max_verify_attempts` |
| `CodingAgentSettings` | New fields `verify_command`, `max_verify_attempts` |
| `AgentMiddleware.review_finish(ctx) -> FinishReview` | New hook; default accepts |
| `MiddlewarePipeline.review_finish(ctx) -> FinishReview` | New dispatcher |
| `MiddlewareHook.REVIEW_FINISH` | New member |
| `BashTool.executable` | New read-only property |
| `FinishReview` | Now validated; documented as the hook's return type |

No root export is added, so `contracts/sdk-public-api.json` and C016 do not change.

**Error cases:**
| Error | Condition |
|--------|-----------|
| `ConfigurationError` (names `verify_command`) | blank or non-str `verify_command`, or no bash found at construction |
| `ConfigurationError` (names `max_verify_attempts`) | bool, non-int, or < 1 |
| `ConfigurationError` (existing) | `verify_command` with a non-linear runtime (BaseAgent rejects middleware there) |
| `ValueError` | `FinishReview` with a non-enum action, a non-str feedback, or a blank `CONTINUE` feedback |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/coding-agent-verify-command.md` | This design doc |
| CREATE | `vidbyte/lib/constants/coding.py` | Named bounds for `max_verify_attempts` (A007, field guide) |
| MODIFY | `vidbyte/lib/dataclasses/coding.py` | Two settings fields + checks; `CodingVerification` record |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | `FinishReview` validation and docstrings |
| MODIFY | `vidbyte/lib/dataclasses/middleware.py` | `MiddlewareHook.REVIEW_FINISH` |
| MODIFY | `vidbyte/middleware/base.py` | `AgentMiddleware.review_finish` default |
| MODIFY | `vidbyte/middleware/pipeline.py` | `MiddlewarePipeline.review_finish` |
| CREATE | `vidbyte/middleware/builtins/verify_command.py` | `VerifyCommandMiddleware` |
| MODIFY | `vidbyte/agents/runtime.py` | Review at both finish points; `_unverified_finish_result` |
| MODIFY | `vidbyte/agents/coding.py` | Two keywords; append the middleware |
| MODIFY | `vidbyte/tools/builtins/bash.py` | `BashTool.executable` property |
| MODIFY | `vidbyte/lib/constants/codex.py` | `"review_finish"` is unsupported on Codex |
| MODIFY | `vidbyte/agents/README.md` | Coding Agent section: the setting |
| MODIFY | `vidbyte/middleware/README.md` | The `review_finish` hook |
| MODIFY | `vidbyte/agents/codex/README.md` | Unsupported-hook table row |
| MODIFY | `skills/vidbyte-sdk/middleware.md`, `skills/sdk/SKILL.md`, `skills/usage/available_features.md` | Hook tables would be wrong without the new hook (`skills/sdk/update-skill-files.md`: "you must update the corresponding skill files so documentation stays accurate") |
| CREATE | `tests/features/coding_agent/test_coding_agent_verify_command.py` | Feature tests (source of truth) |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | `EXPECTED_SIGNATURE` gains the two keywords (that file's own modification rule) |
| MODIFY | `tests/features/coding_agent/FEATURE.md`, `tests/features/coding_agent/README.md` | Pack contract, failure modes, and index |
| CREATE | `scripts/test-coding-agent-verify-command.py` | Thin Phase-5 runner over the pytest file |

---

## 10. Testing Plan

Everything runs offline. A scripted model plays the model turns, and the commands are real bash processes (Git for Windows bash locally, Linux bash on CI). Commands are portable between the two.

### Unit Tests
- `test_coding_agent_verify_command.py` → `test_invalid_verify_arguments_fail_at_construction_naming_the_field` (blank, whitespace, int, bytes command; `max_verify_attempts` 0, -1, `True`, 2.5, "3") — [Edge Case] [Hidden Assumption]
- → `test_missing_bash_with_verify_command_fails_at_construction` (PATH emptied) — [Hidden Assumption]
- → `test_finish_review_requires_feedback_to_continue` (`FinishReview.continue_with("  ")`, bad action, non-str feedback) — [Silent Failure]
- → `test_pipeline_without_reviewers_accepts_every_finish` (empty pipeline and a middleware that overrides nothing) — [Hidden Failure]
- → `test_pipeline_stops_at_the_first_review_that_refuses` (a later reviewer is never asked) — [Hidden Failure]
- → `test_verifier_goes_after_the_caller_middleware_only_when_set` (and `export_state()` is unchanged by it) — [Hidden Assumption]

### Integration Tests
These drive the real `BaseAgent` loop, real `AgentRuntime`, and real `BashTool`.
- **Passes on the first finish.** One verification, normal `is_done` stop, `{"passed": True, "attempts": 1, "last_exit_code": 0}`, one model call, and `tool_call_states == ("succeeded",)`, so verification is not a tool call. — [Silent Failure]
- **Fails, gets feedback, is fixed, then passes.** The command is `test -f done.txt || { echo "missing done.txt"; exit 3; }`. The model reads feedback that contains the command, `exit code 3`, and `missing done.txt`, writes `done.txt` with `write_text`, and finishes again. Result: `attempts == 2`, `passed`. — [Hidden Failure]
- **The same flow on the plain-text finish path.** The feedback arrives as a user message after the model's own answer. — [Hidden Assumption: only `isDone` finishes]
- **Never fixed.** Parametrized over both finish paths: exactly `max_verify_attempts` command runs (counted by a log file), `stop_reason == "contract_unsatisfied"`, the output is the last answer, `passed False`, `last_exit_code` set, and no exception. — [Silent Failure: must not report success]
- **`verify_command=None`.** The caller's middleware passes through as-is, there are no extra model calls, `is_done`, and there is no `verify_command` key. — [Hidden Failure]
- **Output over the real 50,000-byte cap.** The feedback holds exactly 50,000 kept bytes and `[output truncated: N bytes not shown]`. — [Edge Case]
- **Timeout.** With `BASH_TIMEOUT_SECONDS` patched to 1 s, the first verification times out (`it timed out` plus the bash timeout line), the second also times out, and the run stops with `last_exit_code None`. — [Hidden Failure]
- **The working directory changes after construction.** Verification still runs in `root_dir`; a decoy folder with the same name is ignored. — [Hidden Assumption]
- **The model's own `bash` calls do not trigger verification**, even when they run the same command. — [Hidden Assumption]
- **Output contracts run first.** With `MinToolCalls(1)`, a premature `isDone` is rejected by the contract without running the command, and the command runs only after the contract passes. — [Hidden Failure]
- **Another limit ends the run first.** With `max_iterations=2`, the run stops as `max_iterations` and `metadata["verify_command"]` still reports two failed attempts (FR11). — [Silent Failure]
- **The default limit is three attempts.** — [Edge Case]
- **Each run counts its own attempts.** A second run on the same agent starts again at one. — [Hidden Failure: per-instance counters]
- **A plain `BaseAgent` with no finish review** finishes exactly as before on both paths: one model call, `final_response` / `is_done`, the same reply, and no extra messages. — [Hidden Failure]

### Manual / QA Test Cases
1. Given a repo with a failing test and `verify_command="python -m pytest -q"`, when a real model claims it fixed it but did not, then it gets the pytest output and keeps going. — [Silent Failure]
2. Given `verify_command="sleep 700"`, when the model finishes, then the call returns after about 600 s with the timeout text, and on POSIX the sleep is killed. — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| bash (Git for Windows `bin/bash.exe` on Windows) | system | Runs the command | Missing bash fails construction (by design) |
| `BashTool` | in repo | Process bounds and output cap | None; reused unchanged except a read-only property |

---

## 12. Rollout & Deployment

- No feature flag: the feature is off unless `verify_command` is passed.
- Not a breaking change. Two new keywords with defaults, and a new middleware hook with an accepting default.
- Rollback: revert the PR.

---

## 13. Open Questions

These are optional, and none of them is built in this PR.
- [ ] Q-1: Export `VerifyCommandMiddleware` from `vidbyte.middleware.builtins` (and the skill catalog) so any `BaseAgent` can gate its finish on a command? Default: no; it is CodingAgent's setting.
- [ ] Q-2: Record finish reviews as `MiddlewareEvent`s and diagnostic hook spans, or let `AuditLogMiddleware` see them? Default: no; the reviewer's own result metadata reports the outcome.
- [ ] Q-3: Put the last failed output (or the `stop` feedback) in result metadata, so a caller can see why verification failed without re-running it? Default: no; the user asked for passed, attempts, and the last exit code.
- [ ] Q-4: Honor `fail_closed=False` for `review_finish` (accept and record an event when a reviewer raises)? Default: no; exceptions propagate.

---

## 14. Alternatives Considered

### Alternative 1: Existing middleware hooks only (no runtime change)
- What: detect a final answer in `after_model_response` or `after_iteration` and turn it into a continuation.
- Why rejected: no existing hook can turn a finish into a continuation. A non-`CONTINUE` decision at those points aborts the run, and their transforms are not applied (§3).

### Alternative 2: An async output contract
- What: give `OutputContract` an async evaluation and add a command contract to the caller's `AgentLoopSettings`.
- Why rejected:
  - `CodingAgent` would have to rebuild the caller's loop settings from loose keywords.
  - The attempt budget would be the shared `max_contract_rejections`, not `max_verify_attempts`.
  - `report()` re-evaluates synchronously.
  - `export_state` / `restore` rebuild contracts by name and minimum, which a command contract does not have.

### Alternative 3: A `CodingRuntime` subclass over `_continue_finish_attempt`
- What: add `AgentRuntimeType.CODING` and override the existing finish seam.
- Why rejected:
  - The runtime's settings reach it only through `BaseAgent._runtime_extension_kwargs`, which CodingAgent may not override.
  - The seam returns only continue or finish, so it cannot stop with a failure.
  - It would take over the caller's `runtime=` keyword.

### Alternative 4: `review_finish` returning `MiddlewareDecision`
- What: keep the pipeline's uniform decision type, with `RETRY` meaning "reject and continue" and the feedback carried in `reason`.
- Why rejected: an abort cannot keep the model's answer or stop with `CONTRACT_UNSATISFIED` without special-casing one hook. The full command output would also be copied into `metadata["middleware"]["events"]` on every rejection.

### Alternative 5: Stop with `FINISH_REVIEW_REJECTED`
- What: use the existing, unused stop reason that `FinishReview.stop` once documented.
- Why rejected: the session failure router has no mapping for it, so it would be classified as `RUNTIME_ERROR`. `CONTRACT_UNSATISFIED` is already "the finish condition was never met within its budget", and the user leaned toward it.

### Alternative 6: Fail at the first verification when bash is missing
- What: let `BashTool` report `bash_not_found` per call, as it does for the model's own calls.
- Why rejected: `BashTool` fixes its executable at construction, so such a run could only end `contract_unsatisfied` after wasting `max_verify_attempts` model turns. Failing at construction matches the settings record's rule that a bad configuration fails before `BaseAgent` builds anything.
