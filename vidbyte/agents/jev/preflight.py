"""FILE: vidbyte/agents/jev/preflight.py

PURPOSE: Defines the Jev preflight contract, the tool-selection implementation, and the sensitive-data security policy.
ROLE IN CODEBASE: JevRuntime applies enabled preflights before the ordinary model/tool loop.
ARCHITECTURE NOTE: Tool questions and selection policy stay internal; security questions live in `vidbyte/lib/jev/preflight/` and this module only maps their answers to flags and an action.
COMMON MODIFICATION PATTERNS: Implement a JevPreflight subclass for catalog-shaping preflights; add a policy class like JevPreflightSecurity for preflights that gate the run.
KNOWN EDGE CASES: Missing credentials, provider failures, and incomplete answers keep the full original tool catalog; the same failures make the security result unavailable, which stops BLOCK and PAUSE runs and contains CONTAIN runs.
RELATED DOCS: docs/design/jev-tool-selector.md, docs/design/jev-preflight-sensitive-data.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_tool_selector.py, tests/test_jev_sensitive_preflight.py, and scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_NOUL_TRUE,
    JEV_SECURITY_DETECTION_THRESHOLD,
    JEV_SECURITY_STOP_BLOCKED,
    JEV_SECURITY_STOP_REVIEW,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevPreflightQuestion,
    JevQuestion,
    JevSecurityResult,
)
from vidbyte.lib.enums.jev import JevPreflightPreset, JevQuestionType, JevSecurityAction
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev.preflight import JevPreflightRegistry
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.tools.catalog import Tools


class JevPreflight(ABC):
    """Base contract for a run-local Jev preflight policy."""

    @abstractmethod
    async def run(self, message: str, tools: Tools) -> Tools:
        """Return the catalog the generative agent should use for this request."""


class JevPreflightTools(JevPreflight):
    """Selects the tools likely to help with one user request."""

    def __init__(self, decision: DecisionModelConfig, threshold: float) -> None:
        # Retains the validated decision config and caller-selected probability cutoff.
        self._decision = decision
        self._threshold = threshold
        self.usage: JevUsage | None = None
        self.available: bool | None = None

    async def run(self, message: str, tools: Tools) -> Tools:
        """Ask Jev about every user tool in one request, then build the selected catalog."""
        if not len(tools):
            self.available = True
            return tools
        questions = self.build_tool_questions(tools)
        try:
            response = await DecisionModelRunner(self._decision).arun(
                JevDecisionRequest(state=message, questions=questions)
            )
            self.usage = JevUsage.from_usage_payload(response.usage or {})
            selected_names = self.filter_tools(tools, response.answers)
        except VidbyteSdkError:
            # A Jev outage or malformed answer must not remove tools from the agent.
            self.available = False
            return tools
        self.available = True
        return self.build_tools(tools, selected_names)

    @staticmethod
    def build_tool_questions(tools: Tools) -> tuple[JevQuestion, ...]:
        """Build one positive-polarity usefulness question for each tool in catalog order."""
        questions: list[JevQuestion] = []
        for index, tool in enumerate(tools):
            questions.append(
                JevQuestion(
                    name=f"tool_selector.{index}",
                    question_type=JevQuestionType.NOUL,
                    instructions=(
                        "Could this tool be useful at any point in completing the user's request? "
                        "Answer true if it could materially help, even if it is not the first tool needed.\n\n"
                        f"{tool.spec().to_prompt_str()}"
                    ),
                )
            )
        return tuple(questions)

    def filter_tools(self, tools: Tools, answers: Mapping[str, JevAnswer]) -> tuple[str, ...]:
        """Return tool names whose normalized Jev P(true) meets the configured cutoff."""
        selected: list[str] = []
        for index, tool in enumerate(tools):
            answer = answers.get(f"tool_selector.{index}")
            probability = None if answer is None else answer.probabilities.get(JEV_NOUL_TRUE)
            if probability is None:
                raise ConfigurationError(f"Missing true probability for tool {tool.name!r}.")
            if probability >= self._threshold:
                selected.append(tool.name)
        return tuple(selected)

    @staticmethod
    def build_tools(tools: Tools, selected_names: Sequence[str]) -> Tools:
        """Build a fresh catalog containing the selected tools in their original order."""
        return tools.subset(selected_names)


class JevPreflightSecurity:
    """Classifies one request's sensitive-data categories and decides whether and how JevAgent may start."""

    def __init__(self, decision: DecisionModelConfig, action: JevSecurityAction) -> None:
        # Retains the validated decision config and the caller's action for detected sensitive data.
        self._decision = decision
        self.action = action
        self.usage: JevUsage | None = None

    async def run(self, message: str) -> JevSecurityResult:
        """Ask every security question in one Jev request and return per-category flags, never the text."""
        questions = JevPreflightRegistry.questions(JevPreflightPreset.SECURITY)
        try:
            response = await JevPreflightRegistry.run(JevPreflightPreset.SECURITY, message, self._decision)
        except VidbyteSdkError:
            # @intent security-outage-is-unknown-not-clean
            # A missing key or provider failure must not read as "no sensitive data"; every flag stays
            # unknown so BLOCK and PAUSE fail closed and CONTAIN restricts the run.
            return self.build_result({question.key: None for question in questions})
        self.usage = JevUsage.from_usage_payload(response.usage or {})
        return self.build_result(self.flags(questions, response.answers))

    @staticmethod
    def flags(questions: Sequence[JevPreflightQuestion], answers: Mapping[str, JevAnswer]) -> dict[str, bool | None]:
        """Map each answer's P(true) to a flag; a missing answer or probability becomes None."""
        flags: dict[str, bool | None] = {}
        for question in questions:
            answer = answers.get(JevPreflightRegistry.wire_name(JevPreflightPreset.SECURITY, question.key))
            probability = None if answer is None else answer.probabilities.get(JEV_NOUL_TRUE)
            flags[question.key] = None if probability is None else probability >= JEV_SECURITY_DETECTION_THRESHOLD
        return flags

    def build_result(self, flags: Mapping[str, bool | None]) -> JevSecurityResult:
        """Build the frozen result, where a known positive wins over missing answers."""
        values = tuple(flags.values())
        if any(value is True for value in values):
            any_sensitive: bool | None = True
        elif any(value is None for value in values):
            any_sensitive = None
        else:
            any_sensitive = False
        return JevSecurityResult(
            action=self.action,
            available=all(value is not None for value in values),
            flags=flags,
            any_sensitive=any_sensitive,
            input_tokens=None if self.usage is None else self.usage.input_tokens,
            output_tokens=None if self.usage is None else self.usage.output_tokens,
        )

    @staticmethod
    def needs_protection(result: JevSecurityResult) -> bool:
        """Return True when data was detected or the check could not finish."""
        return result.any_sensitive is True or not result.available

    def must_stop(self, result: JevSecurityResult) -> bool:
        """Return True when BLOCK or PAUSE must end the run before the generative loop."""
        return self.action in (JevSecurityAction.BLOCK, JevSecurityAction.PAUSE) and self.needs_protection(result)

    def must_contain(self, result: JevSecurityResult) -> bool:
        """Return True when CONTAIN must run the generative loop with restricted tools and tracing."""
        return self.action is JevSecurityAction.CONTAIN and self.needs_protection(result)

    def stop_reason(self) -> str:
        """Return the stable metadata stop reason for a stopped run."""
        return JEV_SECURITY_STOP_BLOCKED if self.action is JevSecurityAction.BLOCK else JEV_SECURITY_STOP_REVIEW

    def stop_message(self, result: JevSecurityResult) -> str:
        """Name the detected categories without echoing any value from the request."""
        detected = ", ".join(name.replace("_", " ") for name in result.detected())
        if detected and self.action is JevSecurityAction.BLOCK:
            return f"This request appears to contain sensitive data in these categories: {detected}. The request was blocked before the agent started."
        if detected:
            return f"This request appears to contain sensitive data in these categories: {detected}. Review is required before the agent can continue."
        if self.action is JevSecurityAction.BLOCK:
            return "The request could not be checked for sensitive data, so it was blocked before the agent started."
        return "The request could not be checked for sensitive data. Review it before starting the agent."


__all__ = ["JevPreflight", "JevPreflightSecurity", "JevPreflightTools"]
