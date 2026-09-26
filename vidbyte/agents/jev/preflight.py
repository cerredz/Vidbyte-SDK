"""FILE: vidbyte/agents/jev/preflight.py

PURPOSE: Defines the Jev preflight contract and the tool-selection implementation.
ROLE IN CODEBASE: JevRuntime applies enabled preflights before the ordinary model/tool loop.
ARCHITECTURE NOTE: Tool questions and selection policy stay internal; callers choose the named TOOL_SELECTOR capability. The question text is the JevPrompt.TOOL_SELECTOR_QUESTION asset in vidbyte/prompts/jev/.
COMMON MODIFICATION PATTERNS: Implement a JevPreflight subclass and keep request shaping, filtering, and catalog building as separate methods.
KNOWN EDGE CASES: Missing credentials, provider failures, and incomplete answers keep the full original tool catalog.
RELATED DOCS: docs/design/jev-tool-selector.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_tool_selector.py and scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from vidbyte.agents.jev.prompts import JevPrompt, JevPrompts
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevQuestion
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
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
                    instructions=f"{JevPrompts.get(JevPrompt.TOOL_SELECTOR_QUESTION)}\n\n{tool.spec().to_prompt_str()}",
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


__all__ = ["JevPreflight", "JevPreflightTools"]
