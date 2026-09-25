"""FILE: vidbyte/agents/jev/preflight/tools.py

PURPOSE: Implements JevPreflightTools, the TOOL_SELECTOR step: one usefulness question per configured tool, and the selection that narrows the catalog the generative agent sees.
ROLE IN CODEBASE: JevPreflight.combine adds these questions to the one preflight Jev request, and the tool-selector case of JevPreflight.pass_ applies the selection to the run.
ARCHITECTURE NOTE: This class never calls Jev itself; the gate owns the single request, so tool questions share the `request` state with every other enabled preset.
COMMON MODIFICATION PATTERNS: Change the question text and its criteria together, following skills/asking-jev-questions/SKILL.md, and keep each as one string literal (lint S062).
KNOWN EDGE CASES: An empty catalog asks nothing and is selected as-is; a missing answer for any tool marks the selection unavailable, which keeps the full original catalog.
RELATED DOCS: docs/design/jev-tool-selector.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_tool_selector.py and scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.lib.constants.jev import (
    JEV_NOUL_FALSE,
    JEV_NOUL_TRUE,
    JEV_TOOL_SELECTOR_QUESTION_PREFIX,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevOption,
    JevQuestion,
    JevToolSelection,
)
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.tools.catalog import Tools

TOOL_USEFUL_WHEN_TRUE = "Choose true when calling the tool could supply information, perform an action, or check a result that some step of `request` needs. The step does not have to be the first one, and the tool does not have to finish the whole request on its own. For example, a search tool is useful for 'Find the architecture notes and summarize them.' because the notes must be found first. A calendar tool is also useful for 'Draft a status email and mention the next team meeting.' because one sentence depends on the meeting date."
TOOL_USEFUL_WHEN_FALSE = "Choose false when nothing the tool does is needed for any step of `request`. A tool whose subject is unrelated to `request` is not useful, even if it could technically run on the request's text. For example, a calendar tool is not useful for 'Explain how a hash map handles collisions.' because no step needs a date or an event. A file-deleting tool is also not useful for 'Summarize the attached report.' because summarizing reads the report and never removes anything."


class JevPreflightTools:
    """The TOOL_SELECTOR step: asks whether each configured tool could help, then keeps the tools that could."""

    def __init__(self, threshold: float) -> None:
        # Retains the validated, caller-selected P(yes) cutoff at or above which a tool is kept.
        self.threshold = threshold

    def questions(self, tools: Tools) -> tuple[JevQuestion, ...]:
        """Build one positive-polarity usefulness question for each tool, in catalog order."""
        return tuple(
            JevQuestion(
                name=f"{JEV_TOOL_SELECTOR_QUESTION_PREFIX}{index}",
                question_type=JevQuestionType.NOUL,
                instructions=f"`request` is the task a user sent to an AI agent, and the tool described below is one the agent may call while working on it. A tool is useful when calling it could supply information, perform an action, or check a result that some step of `request` needs, not only the first step. A tool whose subject is unrelated to `request` is not useful, even when it could technically run on the request's text. Judge only what `request` asks for and what the description below says the tool does. Could this tool be useful at any point in completing `request`?\n\n{tool.spec().to_prompt_str()}",
                options=(JevOption(name=JEV_NOUL_TRUE, description=TOOL_USEFUL_WHEN_TRUE), JevOption(name=JEV_NOUL_FALSE, description=TOOL_USEFUL_WHEN_FALSE)),
            )
            for index, tool in enumerate(tools)
        )

    def select(self, tools: Tools, answers: Mapping[str, JevAnswer] | None) -> JevToolSelection:
        """Return the tools whose P(yes) meets the cutoff, or keep every tool when any answer is missing."""
        # @intent missing-answers-keep-every-tool
        # A Jev outage or an incomplete answer set must never remove a tool the owner configured, so any
        # gap in the answers keeps the full catalog and marks the selection unavailable.
        candidates = tools.names()
        probabilities: dict[str, float] = {}
        for index, name in enumerate(candidates):
            answer = None if answers is None else answers.get(f"{JEV_TOOL_SELECTOR_QUESTION_PREFIX}{index}")
            probability = None if answer is None else answer.probabilities.get(JEV_NOUL_TRUE)
            if probability is None:
                return JevToolSelection(candidates=candidates, selected=candidates, probabilities=probabilities, available=False)
            probabilities[name] = probability
        selected = tuple(name for name in candidates if probabilities[name] >= self.threshold)
        return JevToolSelection(candidates=candidates, selected=selected, probabilities=probabilities)

    @staticmethod
    def narrow(tools: Tools, selection: JevToolSelection) -> Tools:
        """Build a fresh catalog holding only the selected tools, in their original order."""
        return tools.subset(selection.selected)


__all__ = ["JevPreflightTools"]
