"""FILE: vidbyte/tools/classifier/jev_decide.py

PURPOSE: Implements jev_decide, a model-callable tool that asks TypeSafe's calibrated Jev decision model to pick among options and returns a probability for every option.
ROLE IN CODEBASE: The bolt-on Jev integration: an agent adds JevDecideTool to its tools and calls it for quick judgments. Its Jev usage is reported through ModelBackedTool so AgentRuntime records it in the agent's UsageTracker.
ARCHITECTURE NOTE: The tool composes three private collaborators (argument parsing, state scrubbing, rendering) around DecisionModelRunner; it never raises from execute(), failing open with a stable metadata.error code so the agent can decide on its own.
COMMON MODIFICATION PATTERNS: Keep the model-facing spec, _JevDecideArguments parsing, and the provider's question contract in sync; keep thresholds application-owned via JevDecideSettings.
KNOWN EDGE CASES: A blank state falls back to the question text; options may arrive as a JSON string, plain strings, or {name, description} objects; a 401 or a missing key disables the instance for the rest of its life; a malformed answer is still billed.
RELATED DOCS: docs/design/jev-decide-tool.md, vidbyte/tools/classifier/README.md, and field-guide/vidbyte-sdk/model-facing-tool-contracts.md.
TESTS: tests/test_jev_decide_tool.py and scripts/test_jev_decide_tool.py.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

from vidbyte.lib.constants.jev import (
    JEV_DECIDE_ANSWER_TYPES,
    JEV_DECIDE_QUESTION_NAME,
    JEV_MAX_OPTIONS,
    JEV_MIN_OPTIONS,
    JEV_REDACTED,
    JEV_RETRY_STATUS_CODES,
    JEV_STATUS_UNAUTHORIZED,
    JEV_STATUS_UNPROCESSABLE,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRecord,
    JevDecisionRequest,
    JevOption,
    JevQuestion,
)
from vidbyte.lib.dataclasses.jev_settings import JevDecideSettings
from vidbyte.lib.dataclasses.tool_model_usage import ToolModelCall
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.tools.model_backed import ModelBackedTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

_DECIDE_YOURSELF = "Make this judgment yourself and continue."


class _JevDecideArguments:
    """Parses jev_decide call arguments into one Jev question plus the state it is judged against."""

    @staticmethod
    def parse(arguments: Mapping[str, Any]) -> tuple[JevQuestion, str]:
        # Returns the validated question and state, raising ConfigurationError on any bad argument.
        question = arguments.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ConfigurationError("'question' must be a non-empty string.")
        answer_type = arguments.get("answer_type") or JevQuestionType.CHOICE.value
        if answer_type not in JEV_DECIDE_ANSWER_TYPES:
            raise ConfigurationError(f"'answer_type' must be one of {JEV_DECIDE_ANSWER_TYPES}.")
        options = _JevDecideArguments._options(arguments.get("options"))
        state = arguments.get("state")
        state_text = state.strip() if isinstance(state, str) and state.strip() else question.strip()
        parsed = JevQuestion(name=JEV_DECIDE_QUESTION_NAME, question_type=JevQuestionType(answer_type), instructions=question.strip(), options=options)
        return parsed, state_text

    @staticmethod
    def _options(raw: object) -> tuple[JevOption, ...]:
        # Accepts a JSON-encoded string or a list of strings / {name, description} objects.
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ConfigurationError("'options' must be an array or a JSON-encoded array.") from exc
        if not isinstance(raw, list):
            raise ConfigurationError("'options' must be an array.")
        if not JEV_MIN_OPTIONS <= len(raw) <= JEV_MAX_OPTIONS:
            raise ConfigurationError(f"'options' must contain between {JEV_MIN_OPTIONS} and {JEV_MAX_OPTIONS} entries; received {len(raw)}.")
        return tuple(_JevDecideArguments._option(entry) for entry in raw)

    @staticmethod
    def _option(entry: object) -> JevOption:
        # Converts one option entry into a JevOption, stripping surrounding whitespace.
        if isinstance(entry, str):
            return JevOption(name=entry.strip())
        if isinstance(entry, Mapping) and isinstance(entry.get("name"), str):
            description = entry.get("description")
            return JevOption(name=entry["name"].strip(), description=description.strip() if isinstance(description, str) and description.strip() else None)
        raise ConfigurationError("Each option must be a string or an object with a string 'name'.")


class _JevStateScrubber:
    """Redacts credentials from text before it leaves the process for TypeSafe."""

    _ASSIGNMENT = re.compile(r"(?i)\b(api[_-]?key|private[_-]?key|secret[_-]?key|access[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|credential|authorization)(\s*[:=]\s*)(?:bearer\s+)?([^\s,;\"']+)")

    def __init__(self, secrets: tuple[str, ...]) -> None:
        # Keeps the exact secret strings (such as the configured API key) to mask verbatim.
        self._secrets = tuple(secret for secret in secrets if secret)

    def scrub(self, text: str) -> str:
        # Masks credential assignments and every known secret string.
        # @intent state-never-carries-credentials
        # State is sent to a third-party API, so credential-looking assignments and the
        # configured key are masked here, the last point before the request is built.
        scrubbed = self._ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}{JEV_REDACTED}", text)
        for secret in self._secrets:
            scrubbed = scrubbed.replace(secret, JEV_REDACTED)
        return scrubbed


class _JevDecisionRenderer:
    """Builds the model-facing text for a Jev decision or a fail-open error."""

    @staticmethod
    def decision(answer: JevAnswer, record: JevDecisionRecord) -> str:
        # Renders the verdict, the full ranked distribution, and any threshold note.
        lines = [f"jev_decide: {answer.choice} (probability {answer.probabilities[answer.choice]:.3f}, confidence {answer.confidence:.3f})", "probabilities:"]
        lines.extend(f"- {name}: {probability:.3f}" for name, probability in answer.ranked())
        if not record.passed_threshold and record.min_confidence is not None:
            lines.append(f"Confidence {answer.confidence:.3f} is below the configured threshold {record.min_confidence:.3f}; treat this as uncertain. {_DECIDE_YOURSELF}")
        return "\n".join(lines)

    @staticmethod
    def unavailable(reason: str) -> str:
        # Renders a fail-open message that tells the agent to proceed without Jev.
        return f"jev_decide is unavailable: {reason} {_DECIDE_YOURSELF}"


class JevDecideTool(ModelBackedTool):
    """Model-callable tool that asks TypeSafe's Jev model for a calibrated decision among options."""

    def __init__(self, *, settings: JevDecideSettings | None = None, runner: DecisionModelRunner | None = None, on_decision: Callable[[JevDecisionRecord], None] | None = None) -> None:
        # Stores settings and an optional pre-built runner; the runner is otherwise built lazily.
        self._settings = settings or JevDecideSettings()
        self._runner = runner
        self._on_decision = on_decision
        self._disabled_reason: str | None = None

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="jev_decide",
            description=(
                "Use this tool when you need a quick, well-calibrated judgment that picks one answer from a fixed set of options. "
                "A fast decision model reads the question and the supporting state, then returns a probability for every option instead of a single guess. "
                "Read the full distribution rather than only the top option, because a close split means the judgment is genuinely uncertain. "
                "The tool cannot write text, so it only helps when the answer is one of the options you supply. "
                "If the tool reports that it is unavailable or uncertain, make the judgment yourself and continue."
            ),
            parameters=(
                ToolParameter(
                    name="question",
                    type="string",
                    description=(
                        "State the single judgment you want made, phrased as a clear question with one correct answer among the options. "
                        "Keep it narrow so every option maps to a distinct next step you would take. "
                        "Broad or evaluative questions produce flat distributions that do not help you decide. "
                        "Provide the question as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="options",
                    type="array",
                    description=(
                        f"List between {JEV_MIN_OPTIONS} and {JEV_MAX_OPTIONS} mutually exclusive answers the decision model may choose from. "
                        "Each entry is either a short option name or an object with a name and a description that says when that option is correct. "
                        "Option names must be unique, and descriptions help when a name alone is ambiguous. "
                        "For an ordered scale, list the levels from lowest to highest and set the answer type accordingly. "
                        "Provide a JSON array or a JSON-encoded array string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="state",
                    type="string",
                    description=(
                        "Supply the evidence the judgment should be based on, such as the relevant excerpt, result, or situation summary. "
                        "Include only the slice the question needs, because noisy or oversized state lowers both speed and accuracy. "
                        "Never include credentials or secrets, since this text is sent to an external decision service. "
                        "When omitted, the question text itself is judged as the state."
                    ),
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="answer_type",
                    type="string",
                    description=(
                        f"Choose how the options are interpreted, using one of {', '.join(repr(value) for value in JEV_DECIDE_ANSWER_TYPES)}. "
                        "The choice type treats options as unordered alternatives and picks the best fit. "
                        "The score type treats options as ordered levels and picks the level that best matches the state. "
                        "It defaults to the choice type when omitted."
                    ),
                    required=False,
                    default=JevQuestionType.CHOICE.value,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Parse arguments, ask Jev, record the decision, and fail open on any provider problem."""
        # @intent execute-never-raises
        # Every path returns a ToolResult: bad arguments are rejected before any network call,
        # and provider failures become stable error codes that tell the agent to decide itself.
        try:
            question, state = _JevDecideArguments.parse(call.arguments)
        except ConfigurationError as exc:
            return ToolResult.error(call.tool_name, f"jev_decide rejected its arguments: {exc.message}", metadata={"error": "invalid_arguments"})
        runner = self._resolve_runner()
        if runner is None:
            return self._unavailable(call, self._disabled_reason or "no decision model is configured.", error="jev_unavailable")
        try:
            request = JevDecisionRequest(state=self._scrubber().scrub(state), questions=(question,))
        except ConfigurationError as exc:
            return ToolResult.error(call.tool_name, f"jev_decide rejected its arguments: {exc.message}", metadata={"error": "invalid_arguments"})
        started = time.perf_counter()
        try:
            response = await runner.arun(request)
        except ProviderRequestError as exc:
            return self._request_failed(call, exc)
        except ProviderResponseError as exc:
            usage = exc.details.get("usage")
            metadata = self._usage_metadata(usage if isinstance(usage, Mapping) else None, runner.model_name())
            return self._unavailable(call, "the decision model returned an answer that could not be read.", error="jev_bad_response", extra=metadata)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return self._decided(call, question, request, response, latency_ms)

    def _resolve_runner(self) -> DecisionModelRunner | None:
        # Returns the bound runner, building it once; a build failure disables the tool.
        # @intent missing-key-disables-not-fails
        # A decision tool without credentials must leave the agent running exactly as if the
        # tool were absent, so construction errors disable this instance instead of raising.
        if self._disabled_reason is not None:
            return None
        if self._runner is None:
            try:
                self._runner = DecisionModelRunner(self._settings.decision)
            except ConfigurationError:
                self._disabled_reason = "no TypeSafe API key is configured."
                return None
        return self._runner

    def _scrubber(self) -> _JevStateScrubber:
        # Builds a scrubber that also masks the configured API key verbatim.
        try:
            key = self._settings.decision.resolved_api_key()
        except ConfigurationError:
            key = ""
        return _JevStateScrubber((key,))

    def _request_failed(self, call: ToolCall, exc: ProviderRequestError) -> ToolResult:
        # Maps an HTTP-level failure onto a stable error code; a 401 disables the tool.
        # @intent jev-failures-fail-open
        # Every provider failure returns a tool error the agent can read, never an exception:
        # 401 disables the instance for its lifetime, 429/529 and timeouts leave it enabled.
        status = exc.status_code
        if status == JEV_STATUS_UNAUTHORIZED:
            self._disabled_reason = "the TypeSafe API key was rejected."
            return self._unavailable(call, self._disabled_reason, error="jev_unauthorized")
        if status in JEV_RETRY_STATUS_CODES:
            return self._unavailable(call, "the decision model is rate limited or overloaded.", error="jev_rate_limited")
        if status == JEV_STATUS_UNPROCESSABLE:
            return self._unavailable(call, "the decision service rejected the request shape.", error="jev_invalid_request")
        return self._unavailable(call, "the decision service could not be reached.", error="jev_request_failed")

    def _decided(self, call: ToolCall, question: JevQuestion, request: JevDecisionRequest, response: DecisionModelResponse, latency_ms: float) -> ToolResult:
        # Builds the decision record, notifies the observer, and returns the rendered success result.
        # @intent every-decision-is-recorded
        # The record keeps a state hash rather than the raw state so decision logs can be kept
        # for calibration and threshold tuning without retaining the text sent to TypeSafe.
        answer = response.answer(question.name)
        threshold = self._settings.min_confidence
        record = JevDecisionRecord(
            question=question.instructions,
            answer_type=question.question_type,
            options=question.option_names(),
            choice=answer.choice,
            probabilities=answer.probabilities,
            confidence=answer.confidence,
            min_confidence=threshold,
            passed_threshold=threshold is None or answer.confidence >= threshold,
            model=response.model,
            state_sha256=hashlib.sha256(request.state.encode("utf-8")).hexdigest(),
            latency_ms=latency_ms,
        )
        self._notify(record)
        metadata = self._usage_metadata(response.usage, response.model)
        metadata["jev_decision"] = record
        return ToolResult.success(call.tool_name, _JevDecisionRenderer.decision(answer, record), metadata=metadata)

    def _notify(self, record: JevDecisionRecord) -> None:
        # Delivers the record to the optional observer; an observer error never fails the call.
        if self._on_decision is None:
            return
        try:
            self._on_decision(record)
        except Exception:
            return

    def _usage_metadata(self, usage: Mapping[str, Any] | None, model: str) -> dict[str, Any]:
        # Wraps the provider's raw usage as one ToolModelCall, or reports no calls without usage.
        if usage is None:
            return self._model_usage_metadata(())
        return self._model_usage_metadata((ToolModelCall(provider=ModelProvider.TYPESAFE, model=model, usage=usage),))

    def _unavailable(self, call: ToolCall, reason: str, *, error: str, extra: Mapping[str, Any] | None = None) -> ToolResult:
        # Returns a fail-open error result with a stable error code and any billed usage.
        metadata = dict(extra or {})
        metadata["error"] = error
        return ToolResult.error(call.tool_name, _JevDecisionRenderer.unavailable(reason), metadata=metadata)


__all__ = ["JevDecideTool"]
