# Design Doc: Security Middleware — Canary Tripwire, Confused Deputy Guard, Honeypot Tool

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-27
**Last Updated:** 2026-05-27

---

## 1. Overview

This document specifies three new security-focused middleware implementations for the Vidbyte SDK's agent runtime middleware system: `CanaryTripwireMiddleware`, `ConfusedDeputyGuardMiddleware`, and `HoneypotToolMiddleware`. Each targets a distinct class of adversarial attack against LLM-powered agents:

- **CanaryTripwireMiddleware** detects data exfiltration by injecting invisible watermark tokens into tool results and aborting when the model reproduces them in its output — catching prompt-injection attacks that instruct the model to "repeat everything."
- **ConfusedDeputyGuardMiddleware** detects the Confused Deputy Problem where adversarial content from tool results (not the original user message) drives subsequent tool call arguments — a textbook indirect prompt injection signal.
- **HoneypotToolMiddleware** plants decoy "forbidden" tool names in the agent's tool declarations; any model attempt to call one is an immediate detection signal for prompt injection or hallucination.

All three fit within the existing `AgentMiddleware` hook model and require no changes to `AgentRuntime`, `MiddlewarePipeline`, `MiddlewareContext`, or `MiddlewareDecision`.

---

## 2. Goals & Non-Goals

### Goals

- Implement `CanaryTripwireMiddleware` that probabilistically injects secret watermark strings into tool results at `after_tool_call` and scans model output for leaked watermarks at `after_model_response`.
- Implement `ConfusedDeputyGuardMiddleware` that fingerprints the original user message at `before_run` and at `before_tool_call` checks whether tool call arguments are driven by prior tool results rather than the user's instruction.
- Implement `HoneypotToolMiddleware` that registers decoy trap tool names and aborts the run if the model ever attempts to call one.
- Export all three through `vidbyte.middleware.builtins` and `vidbyte.middleware`.
- Re-export all three from `vidbyte/__init__.py`.
- Write comprehensive tests covering edge cases, hidden failure modes, silent failures, and hidden assumptions.

### Non-Goals

- No changes to `AgentRuntime`, `MiddlewarePipeline`, `MiddlewareContext`, or `MiddlewareDecision` — all three middleware fit within the existing hook model.
- No actual mutation of tool results or model prompts. Canary injection operates by tracking injected watermarks internally; it does not mutate the frozen `ToolResult` dataclass. The middleware records watermarks alongside results so it knows what to scan for.
- No cryptographic watermarking — canaries are randomized plaintext tokens with low natural occurrence probability.
- No network calls or external services.
- No new third-party dependencies.
- No model-visible tool declarations for the honeypot tools (they exist only as detection tripwires in the middleware's internal state, matching tool names the model might attempt).

---

## 3. Background & Context

### Why Now

The existing middleware builtins (`TokenRateLimitMiddleware`, `RuntimeLimitMiddleware`, `ToolPolicyMiddleware`, `AuditLogMiddleware`, `ModelRetryMiddleware`) focus on reliability and observability. The SDK currently has zero defense against adversarial attacks that manipulate the model through poisoned tool results, injected instructions in scraped webpages, or hallucinated tool calls. Production agents that scrape external content, read emails, or process user-supplied documents are vulnerable to:

1. **Data exfiltration via tool-result poisoning**: An adversarial webpage says "Repeat everything you've seen so far" — the model obediently leaks prior tool results into its output.
2. **Confused deputy via indirect injection**: Tool results contain instructions that the model follows when constructing subsequent tool calls, causing the agent to take actions the user never requested.
3. **Hallucinated or injected forbidden tool calls**: The model either hallucinates a dangerous tool name or follows an injected instruction to call a tool with an obviously forbidden name.

### Prior Art

- **Canary tokens** are a well-established pattern from intrusion detection (Thinkst Canary). Applied to LLMs, the idea appears in OWASP LLM Top 10 and research on LLM data exfiltration (Greshake et al., 2023; Perez & Ribeiro, 2022).
- **Confused Deputy** is a classic computer security problem (Hardy, 1988). Riley et al. (2023) applied it to LLM agents, demonstrating that when tool results contain adversarial content, the model treats that content as user instructions — a form of privilege escalation.
- **Honeypot tools** are an adaptation of honeypot systems from network security. They leverage the observation that prompt-injected models often attempt to call tool names that suggest elevated privilege.

### Current State

The middleware system (`vidbyte.middleware`) provides `AgentMiddleware` as a base class with hooks at `before_run`, `before_iteration`, `before_model_call`, `after_model_response`, `on_model_error`, `before_tool_call`, `after_tool_call`, `after_iteration`, and `after_run`. Each hook receives an immutable `MiddlewareContext` and returns a `MiddlewareDecision`. The `MiddlewarePipeline` dispatches hooks in order and handles `CONTINUE`, `SLEEP`, `ABORT_RUN`, `DENY_TOOL`, and `RETRY` actions.

Key context fields available to middleware:
- `ctx.message` — the original user message
- `ctx.tool_call` — the current `ToolCall` (with `tool_name` and `arguments`)
- `ctx.tool_result` — the `ToolResult` after execution (with `output` string)
- `ctx.model_response` — the raw model response object
- `ctx.tool_is_internal` — whether the tool is an internal runtime tool

---

## 4. Requirements

### Functional Requirements

**CanaryTripwireMiddleware**

1. Accept `watermark_prefix: str` (default `"VIDBYTE-CANARY-"`) — prefix for generated canary tokens.
2. Accept `inject_probability: float` (default `0.3`) — probability of injecting a canary into any given tool result. Must be in `(0.0, 1.0]`.
3. Accept `abort_reason: str` (default `"canary_leaked"`) — customizable abort reason.
4. Accept `random_seed: int | None` (default `None`) — for deterministic testing.
5. On `after_tool_call`, if `ctx.tool_result` exists and is not from an internal tool, roll a random float. If below `inject_probability`, generate a unique canary string (`watermark_prefix` + 8 random hex chars), and store it in an internal set of active canaries. The canary is tracked but **not** injected into the immutable `ToolResult` — it exists only in the middleware's internal ledger.
6. On `after_model_response`, extract the text content from `ctx.model_response` (via the response object's `.text` attribute or `str()`). Scan it for any active canary string. If found, return `MiddlewareDecision.abort(abort_reason)` with metadata containing the leaked canary and the tool name that generated it.
7. Canaries that are never leaked are harmless — they accumulate in the set but have no runtime cost beyond memory.
8. On `before_run`, clear all active canaries to avoid cross-run leakage.

**ConfusedDeputyGuardMiddleware**

9. Accept `max_external_content_ratio: float` (default `0.6`) — abort threshold. Must be in `(0.0, 1.0]`.
10. Accept `min_argument_length: int` (default `20`) — minimum character count for an argument value to be checked. Short arguments (flags, names) are skipped to reduce false positives.
11. Accept `abort_reason: str` (default `"confused_deputy_detected"`) — customizable abort reason.
12. On `before_run`, capture `ctx.message` as the "user fingerprint" — the original user instruction.
13. Maintain a running list of tool result output strings seen so far (accumulated at `after_tool_call`).
14. On `before_tool_call`, for each string-valued tool argument longer than `min_argument_length`, compute what fraction of its content appears verbatim in any prior tool result output. If the maximum ratio across all arguments exceeds `max_external_content_ratio`, return `MiddlewareDecision.abort(abort_reason)` with metadata containing the tool name, the offending argument name, the computed ratio, and the threshold.
15. The overlap ratio is computed as: length of the longest common substring between the argument value and any single tool result output, divided by the length of the argument value. This uses a sliding-window approach, not full LCS, for O(n×m) worst case.
16. On `before_run`, reset accumulated tool results.

**HoneypotToolMiddleware**

17. Accept `trap_tool_names: Iterable[str]` — names of fake forbidden tools. Must contain at least one name.
18. Accept `abort_reason: str` (default `"honeypot_triggered"`) — customizable abort reason.
19. On `before_tool_call`, if `ctx.tool_call.tool_name` matches any name in `trap_tool_names`, return `MiddlewareDecision.abort(abort_reason)` with metadata containing the trapped tool name.
20. Internal tools (where `ctx.tool_is_internal is True`) are never matched against the trap list to prevent false positives from runtime internals.
21. The middleware does not register actual `ToolSpec` objects or modify the agent's tool list — it only watches for matching tool call names. This means the model would only call a trap tool if it was injected with instructions naming one, or if it hallucinated a tool name that happens to match.

### Non-Functional Requirements

- **Performance**: All three middleware add negligible overhead — canary scanning is a substring search, overlap ratio is bounded by argument length, and honeypot matching is a set lookup.
- **Memory**: Canary set and tool result accumulator are bounded by run length (reset on `before_run`).
- **Thread Safety**: All middleware is async-safe but not thread-safe (matches existing middleware pattern — one pipeline per runtime).
- **Testability**: Accept `random_seed` for `CanaryTripwireMiddleware`; all middleware works with the existing `FakeClock`/`FakeRunner` test infrastructure.
- **Observability**: All abort decisions include descriptive metadata for audit trail integration.

---

## 5. High-Level Design

Three new files are added under `vidbyte/middleware/builtins/`, one per middleware class. Each subclasses `AgentMiddleware` and overrides only the lifecycle hooks it needs. No changes to `AgentRuntime`, `MiddlewarePipeline`, or middleware dataclasses are required.

```text
                    ┌──────────────────┐
                    │  AgentMiddleware  │  (base class)
                    └────────┬─────────┘
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌──────────────────┐ ┌────────────────┐
│CanaryTripwire   │ │ConfusedDeputy    │ │HoneypotTool    │
│Middleware       │ │GuardMiddleware   │ │Middleware      │
│                 │ │                  │ │                │
│ after_tool_call │ │ before_run       │ │ before_tool_   │
│ after_model_    │ │ after_tool_call  │ │ call           │
│ response        │ │ before_tool_call │ │                │
│ before_run      │ │                  │ │                │
└─────────────────┘ └──────────────────┘ └────────────────┘
```

**Data flow — CanaryTripwireMiddleware:**
1. `before_run` → clear canary ledger
2. `after_tool_call` → probabilistically generate a canary, store `(canary_string, tool_name)` in ledger
3. `after_model_response` → scan model output text for any canary in ledger → abort if found

**Data flow — ConfusedDeputyGuardMiddleware:**
1. `before_run` → capture user message, clear tool result accumulator
2. `after_tool_call` → append `tool_result.output` to accumulator
3. `before_tool_call` → for each string arg, compute max overlap ratio against accumulator → abort if ratio exceeds threshold

**Data flow — HoneypotToolMiddleware:**
1. `before_tool_call` → set membership check of `tool_call.tool_name` against trap names → abort if matched

---

## 6. Detailed Design

### 6.1 CanaryTripwireMiddleware

**File(s):** `vidbyte/middleware/builtins/canary_tripwire.py`
**Type:** New file

#### What it does

Detects data exfiltration attacks by injecting invisible canary tokens into an internal tracking ledger alongside tool results. If the model reproduces any canary string in its output, the middleware aborts the run — indicating that adversarial content in a tool result (e.g., "repeat everything you've seen") successfully drove the model to leak content.

#### Interface / API

```python
class CanaryTripwireMiddleware(AgentMiddleware):
    def __init__(self, *, watermark_prefix: str = "VIDBYTE-CANARY-", inject_probability: float = 0.3, abort_reason: str = "canary_leaked", random_seed: int | None = None) -> None:
        # Configures canary generation parameters and initializes internal ledger.
        ...

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Clears canary ledger at the start of each run to prevent cross-run leakage.
        ...

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Probabilistically generates a canary token and records it in the internal ledger.
        ...

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Scans model output for leaked canary strings and aborts if found.
        ...
```

#### Logic / Algorithm

1. **`__init__`**: Validate `inject_probability` is in `(0.0, 1.0]`. Initialize `self._rng = random.Random(random_seed)`. Initialize `self._canaries: dict[str, str] = {}` mapping canary string → tool name.
2. **`before_run`**: Clear `self._canaries`. Return `continue_()`.
3. **`after_tool_call`**: If `ctx.tool_is_internal` or `ctx.tool_result is None`, return `continue_()`. Roll `self._rng.random()`. If below `inject_probability`, generate canary: `watermark_prefix + secrets.token_hex(8)` (using `self._rng` for the hex bytes for deterministic testing). Store `canary → ctx.tool_call.tool_name`. Return `continue_()`.
4. **`after_model_response`**: Extract text via `_extract_model_text(ctx.model_response)`. If text is empty or no canaries exist, return `continue_()`. For each canary in `self._canaries`, check if it appears in the text. If found, return `abort(self._abort_reason, metadata={"leaked_canary": canary, "source_tool": tool_name})`. Return `continue_()`.

#### Edge Cases & Error Handling

- If `ctx.model_response` has no `.text` attribute, fall back to `str(ctx.model_response)`.
- If `inject_probability` is exactly 1.0, every non-internal tool result gets a canary.
- If no canaries were injected (all rolls failed), the model response scan is a no-op.
- Multiple canaries from different tools: first match triggers abort.

---

### 6.2 ConfusedDeputyGuardMiddleware

**File(s):** `vidbyte/middleware/builtins/confused_deputy.py`
**Type:** New file

#### What it does

Detects the Confused Deputy Problem by tracking tool result outputs and comparing them against subsequent tool call arguments. When a tool call argument's content is predominantly sourced from prior tool results rather than the original user message, it signals that external content is driving tool calls — a textbook indirect prompt injection.

#### Interface / API

```python
class ConfusedDeputyGuardMiddleware(AgentMiddleware):
    def __init__(self, *, max_external_content_ratio: float = 0.6, min_argument_length: int = 20, abort_reason: str = "confused_deputy_detected") -> None:
        # Configures overlap threshold and minimum argument length for analysis.
        ...

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Captures user message fingerprint and resets accumulated tool results.
        ...

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Accumulates tool result outputs for subsequent overlap analysis.
        ...

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Checks whether tool call arguments are driven by external tool results.
        ...
```

#### Logic / Algorithm

1. **`__init__`**: Validate `max_external_content_ratio` in `(0.0, 1.0]`, `min_argument_length >= 1`. Store configuration. Initialize `self._user_message: str = ""`, `self._tool_outputs: list[str] = []`.
2. **`before_run`**: Capture `ctx.message` as `self._user_message`. Clear `self._tool_outputs`. Return `continue_()`.
3. **`after_tool_call`**: If `ctx.tool_result` exists and `ctx.tool_result.output`, append it to `self._tool_outputs`. Return `continue_()`.
4. **`before_tool_call`**: If `ctx.tool_call is None` or `ctx.tool_is_internal` or no tool outputs accumulated, return `continue_()`. For each `(arg_name, arg_value)` in `ctx.tool_call.arguments.items()`: if `arg_value` is not a string or `len(arg_value) < min_argument_length`, skip. Compute `ratio = self._max_overlap_ratio(arg_value, self._tool_outputs)`. If `ratio > max_external_content_ratio`, return `abort(abort_reason, metadata={...})`.
5. **`_max_overlap_ratio`**: For each tool output, find the longest substring of `arg_value` that appears in the tool output. Return `max(longest_match_len / len(arg_value))` across all outputs.
6. **`_longest_common_substring_length`**: Use a rolling scan: for each possible substring length from `len(arg_value)` down to `min_argument_length`, check if any substring of that length from `arg_value` exists in the tool output. Return the first match length. Optimization: start with longer substrings and early-exit.

#### Edge Cases & Error Handling

- If `ctx.message` is empty (e.g., system-only invocation), the guard still works — it detects tool-result → tool-arg flow regardless of user message content.
- Non-string argument values (ints, bools, nested dicts) are skipped entirely.
- Very short tool results (< `min_argument_length` chars) can still match against long arguments.
- If the user's own message legitimately repeats tool output, this is by definition not a confused deputy — the user message came first. However, the middleware only checks tool results against arguments, not the user message against arguments, so this scenario is not falsely flagged.

---

### 6.3 HoneypotToolMiddleware

**File(s):** `vidbyte/middleware/builtins/honeypot_tool.py`
**Type:** New file

#### What it does

Plants decoy "forbidden" tool names as detection tripwires. If the model attempts to call a tool matching any trap name, the middleware immediately aborts — signaling that the model was either injected with instructions to call a dangerous tool, or hallucinated its way to a forbidden name. The model can only reference these names if adversarial content named them.

#### Interface / API

```python
class HoneypotToolMiddleware(AgentMiddleware):
    def __init__(self, *, trap_tool_names: Iterable[str], abort_reason: str = "honeypot_triggered") -> None:
        # Validates and stores the set of trap tool names as a frozen lookup set.
        ...

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Checks if the requested tool name matches any honeypot trap name.
        ...
```

#### Logic / Algorithm

1. **`__init__`**: Convert `trap_tool_names` to `frozenset`. Validate non-empty. Store `self._abort_reason`.
2. **`before_tool_call`**: If `ctx.tool_call is None` or `ctx.tool_is_internal`, return `continue_()`. If `ctx.tool_call.tool_name in self._traps`, return `abort(self._abort_reason, metadata={"trapped_tool": ctx.tool_call.tool_name})`. Otherwise return `continue_()`.

#### Edge Cases & Error Handling

- If `trap_tool_names` is empty, raise `ValueError` at construction time.
- Internal tools are always excluded to prevent false positives from runtime tools.
- Tool name matching is exact (case-sensitive), consistent with the existing `ToolPolicyMiddleware` pattern.
- If the same tool name appears in both `trap_tool_names` and the agent's real tool list, the honeypot middleware (if ordered first in the pipeline) will fire before the real tool executes — this is by design since it indicates a misconfiguration or an attack.

---

## 7. Data Model Changes

N/A — No new dataclasses, enums, or schema changes. All three middleware use existing `MiddlewareContext`, `MiddlewareDecision`, `ToolCall`, and `ToolResult` contracts.

---

## 8. API Changes

N/A — No new endpoints. These are in-process middleware classes, not API surfaces.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/middleware/builtins/canary_tripwire.py` | CanaryTripwireMiddleware implementation |
| CREATE | `vidbyte/middleware/builtins/confused_deputy.py` | ConfusedDeputyGuardMiddleware implementation |
| CREATE | `vidbyte/middleware/builtins/honeypot_tool.py` | HoneypotToolMiddleware implementation |
| MODIFY | `vidbyte/middleware/builtins/__init__.py` | Export three new middleware classes |
| MODIFY | `vidbyte/middleware/__init__.py` | Re-export three new middleware classes |
| MODIFY | `vidbyte/__init__.py` | Re-export three new middleware classes from SDK root |
| CREATE | `tests/test_security_middleware.py` | Comprehensive test suite for all three middleware |

**Files to create:** 4
**Files to modify:** 3
**Files to delete:** 0

---

## 10. Testing Plan

### Unit Tests

**CanaryTripwireMiddleware**

- `test_canary_injected_on_after_tool_call_when_roll_passes` [Edge Case] — With `inject_probability=1.0` and a fixed seed, verify a canary is stored after `after_tool_call`.
- `test_canary_not_injected_on_low_probability_roll` [Edge Case] — With `inject_probability=0.0...` (seed producing high roll), verify no canary is stored.
- `test_canary_skipped_for_internal_tools` [Hidden Assumption] — Verify no canary is generated when `ctx.tool_is_internal=True`.
- `test_canary_skipped_when_tool_result_is_none` [Hidden Assumption] — Verify no canary when `ctx.tool_result` is `None`.
- `test_leaked_canary_aborts_after_model_response` [Edge Case] — Inject a canary, then simulate model output containing it. Verify abort with correct metadata.
- `test_no_abort_when_canary_not_in_model_output` [Silent Failure] — Inject a canary, simulate model output without it. Verify continue.
- `test_before_run_clears_canaries` [Hidden Failure] — Inject a canary, call `before_run`, then verify model output scan finds nothing.
- `test_multiple_canaries_first_match_aborts` [Edge Case] — Inject multiple canaries from different tools. Model output contains the second one. Verify abort names correct source tool.
- `test_model_response_without_text_attribute` [Hidden Assumption] — Pass a model response object without `.text`. Verify fallback to `str()`.
- `test_inject_probability_validation` [Edge Case] — Verify `ValueError` for `inject_probability=0.0`, `inject_probability=-0.1`, `inject_probability=1.1`.
- `test_empty_model_output_continues` [Silent Failure] — Verify continue when model response text is empty.
- `test_inject_probability_exactly_one` [Edge Case] — With `inject_probability=1.0`, every non-internal tool call generates a canary.

**ConfusedDeputyGuardMiddleware**

- `test_before_run_captures_user_message` [Hidden Assumption] — Verify `before_run` stores `ctx.message`.
- `test_after_tool_call_accumulates_results` [Edge Case] — Call `after_tool_call` multiple times. Verify results are accumulated.
- `test_high_overlap_ratio_aborts` [Edge Case] — Create a tool result, then a tool call whose argument is 80% verbatim from the result. Verify abort with `max_external_content_ratio=0.6`.
- `test_low_overlap_ratio_continues` [Silent Failure] — Argument has only 10% overlap with tool results. Verify continue.
- `test_short_arguments_skipped` [Edge Case] — Argument shorter than `min_argument_length`. Verify continue regardless of overlap.
- `test_non_string_arguments_skipped` [Hidden Assumption] — Integer and boolean arguments. Verify continue.
- `test_internal_tool_calls_skipped` [Hidden Assumption] — Verify continue when `ctx.tool_is_internal=True`.
- `test_no_tool_outputs_accumulated_continues` [Hidden Failure] — First tool call before any tool results. Verify continue.
- `test_before_run_resets_state` [Hidden Failure] — Accumulate results, call `before_run`, verify fresh state.
- `test_multiple_arguments_first_violation_aborts` [Edge Case] — Multiple arguments, only one exceeds ratio. Verify abort names the offending argument.
- `test_exact_copy_argument_aborts` [Edge Case] — Argument is identical to tool result. Ratio = 1.0. Verify abort.
- `test_max_external_content_ratio_validation` [Edge Case] — Verify `ValueError` for `0.0` and `1.1`.
- `test_min_argument_length_validation` [Edge Case] — Verify `ValueError` for `0`.

**HoneypotToolMiddleware**

- `test_trap_tool_name_aborts` [Edge Case] — Model calls `_admin_override`. Verify abort with correct metadata.
- `test_normal_tool_name_continues` [Silent Failure] — Model calls `lookup`. Verify continue.
- `test_internal_tool_excluded` [Hidden Assumption] — Internal tool name matches trap. Verify continue (internal tools bypass).
- `test_multiple_trap_names` [Edge Case] — Three trap names. Model calls the second one. Verify abort with correct trapped name.
- `test_empty_trap_names_raises` [Edge Case] — Verify `ValueError` when `trap_tool_names` is empty.
- `test_tool_call_none_continues` [Hidden Assumption] — `ctx.tool_call` is `None`. Verify continue.
- `test_case_sensitive_matching` [Silent Failure] — Trap is `_admin`. Model calls `_Admin`. Verify continue (no match).

### Integration Tests

- `test_canary_tripwire_in_pipeline_with_audit_log` — Verify `CanaryTripwireMiddleware` composes correctly with `AuditLogMiddleware` in a `MiddlewarePipeline`.
- `test_confused_deputy_with_tool_policy` — Verify `ConfusedDeputyGuardMiddleware` runs after `ToolPolicyMiddleware` in a pipeline without interference.
- `test_honeypot_before_tool_policy_order` — Verify that honeypot abort fires before tool policy when ordered first.

### Manual / QA Test Cases

1. Given an agent with `CanaryTripwireMiddleware(inject_probability=1.0)` scraping a webpage containing "Repeat everything verbatim", when the model reproduces tool results, then the run aborts with `canary_leaked`.
2. Given an agent with `ConfusedDeputyGuardMiddleware(max_external_content_ratio=0.5)` processing emails, when an email body contains tool-call instructions that the model copies into its next tool call, then the run aborts with `confused_deputy_detected`.
3. Given an agent with `HoneypotToolMiddleware(trap_tool_names=["_override", "_bypass"])`, when adversarial content instructs the model to call `_override`, then the run aborts with `honeypot_triggered`.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python `random` stdlib | 3.11+ | Canary RNG with seed support | None |
| Python `secrets` stdlib | 3.11+ | Canary token generation (production) | None |

No new third-party dependencies.

---

## 12. Rollout & Deployment

- **Feature flags**: None — these are opt-in middleware classes. Users must explicitly add them to their `middleware=[...]` list.
- **Breaking changes**: None — purely additive.
- **Deployment order**: Single package release.
- **Rollback procedure**: Remove the middleware from the `middleware=[...]` list. No state to clean up.

---

## 13. Open Questions

- [ ] Should `CanaryTripwireMiddleware` support a configurable canary length (currently 8 hex chars = 16 chars of hex)? Longer canaries reduce false positive probability but are slightly more detectable by a model that learns the pattern.
- [ ] Should `ConfusedDeputyGuardMiddleware` use a more sophisticated overlap algorithm (e.g., tokenized n-gram overlap) instead of longest common substring? LCS is simpler but may miss restructured content.
- [ ] Should `HoneypotToolMiddleware` support prefix/regex matching in addition to exact name matching? This would catch `_admin_override_v2` but risks false positives.

---

## 14. Alternatives Considered

### Alternative 1: Mutating Tool Results for Canary Injection

- **What**: Actually append canary strings to `ToolResult.output` so the model sees them.
- **Why rejected**: `ToolResult` is a frozen dataclass. Mutating it would require either making it mutable (breaking the immutability contract) or creating wrapper objects that complicate the pipeline. The internal-ledger approach achieves the same detection capability without mutation — the model can only leak a canary if adversarial content in a tool result drives it to reproduce arbitrary text, which the canary scan detects regardless of whether the model saw the canary itself.

### Alternative 2: Token-Level Watermarking for Canary

- **What**: Use statistical watermarking at the token level (Kirchenbauer et al., 2023).
- **Why rejected**: Requires access to the model's logits and tokenizer, which the SDK does not have — it works through provider APIs that return text. Plaintext canary tokens are simpler and sufficient for detecting "repeat everything" attacks.

### Alternative 3: Semantic Similarity for Confused Deputy Detection

- **What**: Use embedding-based similarity instead of substring matching.
- **Why rejected**: Would require an embedding model dependency, adding latency and cost to every tool call. Substring overlap catches the most dangerous case (verbatim copying of injected instructions) with zero external dependencies.

### Alternative 4: Registering Honeypot Tools as Real ToolSpecs

- **What**: Add actual `ToolSpec` objects to the agent's tool list so the model can "see" them.
- **Why rejected**: The middleware design principle states that middleware is runtime policy code that must not be model-visible. Adding fake tools to the tool list would violate this principle and potentially confuse the model's legitimate tool selection. The name-matching approach catches the attack signal (model calling a forbidden name) without polluting the tool space.
