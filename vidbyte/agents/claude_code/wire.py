"""FILE: vidbyte/agents/claude_code/wire.py

PURPOSE: Defines ClaudeCodeWire, which reads one finished Claude Code run (its CliOutcome and the stream-json events it printed) into a ClaudeCodeRunResult, or raises the ClaudeCodeAgentError the outcome means: TIMEOUT, NOT_AUTHENTICATED, EXIT_NONZERO, SCHEMA_VIOLATION or MALFORMED_OUTPUT.
ROLE IN CODEBASE: Called by ClaudeCodeHarnessAgent.arun (agent.py) after CliRunner returns, with a ClaudeCodeWireRequest (vidbyte/lib/dataclasses/claude_code.py) and the run's ClaudeCodeFailures (failures.py). Every wire key it reads is a constant in vidbyte/lib/constants/claude_code.py.
ARCHITECTURE NOTE: The shapes are the ones observed live on Claude Code 2.1.314 (docs/design/claude-code-harness-agent.md section 4): a system/init event, assistant events, and a final result event. A failure is read from is_error, never from subtype, because a login failure reports is_error true with subtype "success". Usage is the result's usage object, which covers this run alone; cost is model_usage_since_last_result (this run alone) because total_cost_usd and modelUsage are cumulative over a resumed session. The init event is checked against the settings, so a Claude Code that ignored --tools= or --strict-mcp-config cannot hand back an answer made with tools or MCP servers nobody allowed.
COMMON MODIFICATION PATTERNS: A new failure condition gets its check in read() in the order of the design doc's table (section 6.6) and, when it needs a new kind, a ClaudeCodeFailureKind member. A new result field is read by one more helper here and set in the ClaudeCodeRunResult at the end of read().
WHAT NOT TO DO IN THIS FILE: 1. Do not trust subtype for success. 2. Do not report total_cost_usd as the run's cost. 3. Do not quote the prompt or the instructions; only Claude Code's own result text and stderr, through ClaudeCodeFailures.
KNOWN EDGE CASES: A schema the model cannot satisfy ends with exit 0, is_error false and no structured_output key, so a missing structured_output is the only sign of SCHEMA_VIOLATION. An unknown resume id exits 1 with only stderr ("No conversation found with session ID"), which is EXIT_NONZERO. When an older Claude Code omits model_usage_since_last_result, the run's cost is the cumulative total minus the total the agent saw last, or None without such a baseline. A timed-out run is TIMEOUT even when it printed a partial result.
RELATED DOCS: docs/design/claude-code-harness-agent.md sections 4 and 6.6; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/test_claude_code_failures.py, tests/features/claude_code_agent/test_claude_code_agent.py
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.claude_code.failures import ClaudeCodeFailures
from vidbyte.lib.constants.claude_code import (
    CLAUDE_CODE_API_ERROR_STATUS_KEY,
    CLAUDE_CODE_ASSISTANT_EVENT,
    CLAUDE_CODE_AUTH_MARKERS,
    CLAUDE_CODE_AUTH_STATUS_CODES,
    CLAUDE_CODE_CACHE_CREATION_FIELD,
    CLAUDE_CODE_CACHE_READ_FIELD,
    CLAUDE_CODE_COST_KEY,
    CLAUDE_CODE_DURATION_KEY,
    CLAUDE_CODE_INIT_SUBTYPE,
    CLAUDE_CODE_INPUT_TOKENS_FIELD,
    CLAUDE_CODE_IS_ERROR_KEY,
    CLAUDE_CODE_MAX_OUTPUT_BYTES,
    CLAUDE_CODE_MCP_SERVERS_KEY,
    CLAUDE_CODE_MESSAGE_KEY,
    CLAUDE_CODE_MODEL_KEY,
    CLAUDE_CODE_NUM_TURNS_KEY,
    CLAUDE_CODE_OUTPUT_TOKENS_FIELD,
    CLAUDE_CODE_OUTPUT_TOKENS_KEY,
    CLAUDE_CODE_RESULT_EVENT,
    CLAUDE_CODE_RESULT_KEY,
    CLAUDE_CODE_RUN_MODEL_USAGE_KEY,
    CLAUDE_CODE_SESSION_ID_KEY,
    CLAUDE_CODE_STRUCTURED_OUTPUT_KEY,
    CLAUDE_CODE_STRUCTURED_OUTPUT_TOOL,
    CLAUDE_CODE_SUBTYPE_KEY,
    CLAUDE_CODE_SUCCESS_EXIT_CODE,
    CLAUDE_CODE_SYSTEM_EVENT,
    CLAUDE_CODE_TOOLS_KEY,
    CLAUDE_CODE_TOTAL_COST_KEY,
    CLAUDE_CODE_TYPE_KEY,
    CLAUDE_CODE_UNKNOWN_OPTION_MARKER,
    CLAUDE_CODE_USAGE_KEY,
)
from vidbyte.lib.dataclasses.claude_code import (
    ClaudeCodeRunResult,
    ClaudeCodeUsage,
    ClaudeCodeWireRequest,
)
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.enums.claude_code import ClaudeCodeFailureKind
from vidbyte.lib.process import CliRunner

_Event = Mapping[str, Any]


class ClaudeCodeWire:
    """Turns one finished Claude Code run into a ClaudeCodeRunResult or the error it means."""

    @staticmethod
    def read(request: ClaudeCodeWireRequest, failures: ClaudeCodeFailures) -> ClaudeCodeRunResult:
        # @intent read-the-run-in-the-order-of-the-failure-table
        # The checks run in the design doc's order (section 6.6), so a run
        # that both timed out and printed an error is reported as the time
        # out, and a login failure is never mistaken for a schema problem.
        outcome = request.outcome
        session_id = request.session_id

        # A run past its time bound was stopped, whatever it printed.
        if outcome.timed_out:
            raise failures.failure(ClaudeCodeFailureKind.TIMEOUT, f"Claude Code did not finish within {request.timeout_seconds:g} seconds, so the SDK stopped its whole process tree.", session_id=session_id, exit_code=outcome.exit_code)

        # Output past the cap cannot be read whole, so nothing in it is trusted.
        if outcome.stdout_truncated:
            raise failures.failure(ClaudeCodeFailureKind.MALFORMED_OUTPUT, f"Claude Code printed more than {CLAUDE_CODE_MAX_OUTPUT_BYTES} bytes, so its output could not be read whole.", session_id=session_id, exit_code=outcome.exit_code)

        # Split the output into its events and find the final result.
        events = CliRunner.json_objects(outcome.stdout)
        result = ClaudeCodeWire._last_event(events, CLAUDE_CODE_RESULT_EVENT)

        # A run Claude Code itself reported as failed is a login problem or
        # another failure; its own words are quoted, scrubbed.
        failed_text = ClaudeCodeWire._failure_text(outcome, result)
        if failed_text is not None:
            kind = ClaudeCodeWire._failure_kind(failed_text, result)
            raise failures.failure(kind, ClaudeCodeWire._failure_sentence(kind, failed_text, outcome.exit_code), session_id=session_id, exit_code=outcome.exit_code, vendor_text=failed_text)

        # A run that ended cleanly must still have printed its result.
        if result is None:
            raise failures.failure(ClaudeCodeFailureKind.MALFORMED_OUTPUT, "Claude Code exited without printing its final result event.", session_id=session_id, exit_code=outcome.exit_code, vendor_text=outcome.stderr)

        # The answer must come from the session asked for, set up only with
        # the tools and MCP servers the settings allow.
        setup_problem = ClaudeCodeWire._setup_problem(request, result, ClaudeCodeWire._init_event(events))
        if setup_problem is not None:
            raise failures.failure(ClaudeCodeFailureKind.MALFORMED_OUTPUT, setup_problem, session_id=session_id, exit_code=outcome.exit_code)

        # With a schema, the structured output must be there and be an object.
        output = result.get(CLAUDE_CODE_STRUCTURED_OUTPUT_KEY) if request.expects_output else None
        if request.expects_output and not isinstance(output, dict):
            raise failures.failure(ClaudeCodeFailureKind.SCHEMA_VIOLATION, "Claude Code finished the run without structured output matching output_schema.", session_id=session_id, exit_code=outcome.exit_code, vendor_text=ClaudeCodeWire._text(result))

        # Read this run's token usage, model and cost.
        usage = ClaudeCodeWire._usage(result)
        model = ClaudeCodeWire._model(result, events)
        if usage is None or not model:
            raise failures.failure(ClaudeCodeFailureKind.MALFORMED_OUTPUT, "Claude Code's result event did not report the run's token usage and model.", session_id=session_id, exit_code=outcome.exit_code)
        cost_usd, session_cost_usd = ClaudeCodeWire._costs(result, request.previous_session_cost_usd)
        return ClaudeCodeRunResult(
            output=output,
            text=ClaudeCodeWire._text(result),
            session_id=session_id,
            usage=usage,
            cost_usd=cost_usd,
            model=model,
            num_turns=ClaudeCodeWire._count(result, CLAUDE_CODE_NUM_TURNS_KEY),
            duration_ms=ClaudeCodeWire._count(result, CLAUDE_CODE_DURATION_KEY),
            session_cost_usd=session_cost_usd,
        )

    @staticmethod
    def _last_event(events: Sequence[_Event], event_type: str) -> _Event | None:
        # The last event of the given type, or None when there is none.
        return next((event for event in reversed(events) if event.get(CLAUDE_CODE_TYPE_KEY) == event_type), None)

    @staticmethod
    def _init_event(events: Sequence[_Event]) -> _Event | None:
        # The session setup event Claude Code prints before the first turn.
        return next((event for event in events if event.get(CLAUDE_CODE_TYPE_KEY) == CLAUDE_CODE_SYSTEM_EVENT and event.get(CLAUDE_CODE_SUBTYPE_KEY) == CLAUDE_CODE_INIT_SUBTYPE), None)

    @staticmethod
    def _failure_text(outcome: CliOutcome, result: _Event | None) -> str | None:
        # None when the run did not fail; otherwise Claude Code's own words,
        # the result text first and then stderr, possibly empty.
        is_error = result is not None and result.get(CLAUDE_CODE_IS_ERROR_KEY) is True
        if not is_error and outcome.exit_code == CLAUDE_CODE_SUCCESS_EXIT_CODE:
            return None
        text = result.get(CLAUDE_CODE_RESULT_KEY) if result is not None else None
        parts = (text if isinstance(text, str) else "", outcome.stderr)
        return "\n".join(part.strip() for part in parts if part.strip())

    @staticmethod
    def _failure_kind(text: str, result: _Event | None) -> ClaudeCodeFailureKind:
        # @intent login-failures-are-named-by-text-or-status
        # Claude Code reports a missing or rejected login with exit 1 and a
        # result text ("Not logged in · Please run /login"), sometimes with an
        # HTTP status; anything else it reports is its own failure.
        status = result.get(CLAUDE_CODE_API_ERROR_STATUS_KEY) if result is not None else None
        lowered = text.lower()
        if status in CLAUDE_CODE_AUTH_STATUS_CODES or any(marker in lowered for marker in CLAUDE_CODE_AUTH_MARKERS):
            return ClaudeCodeFailureKind.NOT_AUTHENTICATED
        return ClaudeCodeFailureKind.EXIT_NONZERO

    @staticmethod
    def _failure_sentence(kind: ClaudeCodeFailureKind, text: str, exit_code: int | None) -> str:
        # The first sentence of the message: what happened, in plain words.
        if kind is ClaudeCodeFailureKind.NOT_AUTHENTICATED:
            return f"Claude Code could not authenticate (exit code {exit_code}), so the run never reached the model."
        if CLAUDE_CODE_UNKNOWN_OPTION_MARKER in text.lower():
            return f"Claude Code exited with code {exit_code} because it does not know a flag this SDK passes, which means the installed Claude Code is older than the one this SDK was checked against (2.1.314)."
        return f"Claude Code reported a failed run (exit code {exit_code})."

    @staticmethod
    def _setup_problem(request: ClaudeCodeWireRequest, result: _Event, init: _Event | None) -> str | None:
        # @intent the-answer-comes-from-the-isolated-session-asked-for
        # A result on another session, or from a session that started with
        # tools or MCP servers the settings did not allow, is not the run the
        # caller configured, so it is refused rather than returned.
        answered = result.get(CLAUDE_CODE_SESSION_ID_KEY)
        if not isinstance(answered, str) or answered.casefold() != request.session_id.casefold():
            return f"Claude Code answered on a different session than the requested {request.session_id}."
        if init is None:
            return "Claude Code printed no session setup event, so the SDK cannot confirm which tools and MCP servers the run had."
        tools = init.get(CLAUDE_CODE_TOOLS_KEY)
        servers = init.get(CLAUDE_CODE_MCP_SERVERS_KEY)
        if not isinstance(tools, list) or not isinstance(servers, list):
            return "Claude Code's session setup event did not list its tools and MCP servers."
        allowed = {*request.allowed_tools, CLAUDE_CODE_STRUCTURED_OUTPUT_TOOL}
        extra = [str(tool) for tool in tools if tool not in allowed]
        if extra or servers:
            names = ", ".join(extra) or "none"
            return f"Claude Code started the session with tools the settings did not allow ({names}) or with {len(servers)} MCP server(s), so its answer was discarded."
        return None

    @staticmethod
    def _usage(result: _Event) -> ClaudeCodeUsage | None:
        # This run's tokens from the result's usage object, or None when any
        # of the four counts is missing or not a whole number.
        usage = result.get(CLAUDE_CODE_USAGE_KEY)
        if not isinstance(usage, Mapping):
            return None
        names = (CLAUDE_CODE_INPUT_TOKENS_FIELD, CLAUDE_CODE_OUTPUT_TOKENS_FIELD, CLAUDE_CODE_CACHE_READ_FIELD, CLAUDE_CODE_CACHE_CREATION_FIELD)
        counts = [usage.get(name) for name in names]
        if not all(isinstance(count, int) and not isinstance(count, bool) and count >= 0 for count in counts):
            return None
        input_tokens, output_tokens, cache_read, cache_creation = counts
        return ClaudeCodeUsage(input_tokens=input_tokens, output_tokens=output_tokens, cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_creation)

    @staticmethod
    def _model(result: _Event, events: Sequence[_Event]) -> str:
        # The model that wrote most of this run's output; else the last
        # assistant message's model; else the session's model; else "".
        run_usage = result.get(CLAUDE_CODE_RUN_MODEL_USAGE_KEY)
        if isinstance(run_usage, Mapping) and run_usage:
            return str(max(run_usage, key=lambda name: _output_tokens(run_usage[name])))
        for event in reversed(events):
            message = event.get(CLAUDE_CODE_MESSAGE_KEY)
            if event.get(CLAUDE_CODE_TYPE_KEY) == CLAUDE_CODE_ASSISTANT_EVENT and isinstance(message, Mapping) and isinstance(message.get(CLAUDE_CODE_MODEL_KEY), str):
                return str(message[CLAUDE_CODE_MODEL_KEY])
        init = next((event for event in events if event.get(CLAUDE_CODE_SUBTYPE_KEY) == CLAUDE_CODE_INIT_SUBTYPE), {})
        model = init.get(CLAUDE_CODE_MODEL_KEY)
        return model if isinstance(model, str) else ""

    @staticmethod
    def _costs(result: _Event, previous_session_cost_usd: float | None) -> tuple[float | None, float | None]:
        # @intent the-run-cost-is-this-run-alone
        # total_cost_usd grows over a resumed session, so a caller summing it
        # per run would count earlier turns again. This run's cost is the sum
        # of model_usage_since_last_result; without it, the growth since the
        # total the agent saw last; without that baseline, unknown.
        session = result.get(CLAUDE_CODE_TOTAL_COST_KEY)
        session_cost = float(session) if _is_amount(session) else None
        run_usage = result.get(CLAUDE_CODE_RUN_MODEL_USAGE_KEY)
        if isinstance(run_usage, Mapping) and run_usage and all(isinstance(entry, Mapping) and _is_amount(entry.get(CLAUDE_CODE_COST_KEY)) for entry in run_usage.values()):
            return math.fsum(float(entry[CLAUDE_CODE_COST_KEY]) for entry in run_usage.values()), session_cost
        if session_cost is not None and previous_session_cost_usd is not None:
            return max(session_cost - previous_session_cost_usd, 0.0), session_cost
        return None, session_cost

    @staticmethod
    def _text(result: _Event) -> str:
        # The final text of the run, or "" when Claude Code printed none.
        text = result.get(CLAUDE_CODE_RESULT_KEY)
        return text if isinstance(text, str) else ""

    @staticmethod
    def _count(result: _Event, key: str) -> int:
        # A whole, non-negative count from the result, or 0 when absent.
        value = result.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _is_amount(value: object) -> bool:
    # A finite, non-negative number that is not a bool.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _output_tokens(entry: object) -> int:
    # The output tokens of one model_usage entry, or 0 when unreadable.
    tokens = entry.get(CLAUDE_CODE_OUTPUT_TOKENS_KEY) if isinstance(entry, Mapping) else None
    return tokens if isinstance(tokens, int) and not isinstance(tokens, bool) else 0


__all__ = ["ClaudeCodeWire"]
