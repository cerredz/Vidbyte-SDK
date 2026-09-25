"""FILE: vidbyte/agents/jev/compaction/steps.py

PURPOSE: Collects a run's steps (one per completed iteration) from the loop state and renders them for Jev, for the record writer, and as the deterministic fallback record.
ROLE IN CODEBASE: JevDynamicCompaction builds the unit-of-work Jev state and the writer input from these renderings; triggers read JevRunStep values.
ARCHITECTURE NOTE: Steps come from loop state (iteration_outputs and call_contexts tagged with their iteration), never from provider messages, so rendering does not depend on any vendor's message shape.
COMMON MODIFICATION PATTERNS: Change what Jev sees in render_for_jev and what the writer sees in render_for_writer; keep tool outputs out of the Jev rendering.
KNOWN EDGE CASES: isDone calls are skipped; a step whose model reply had no text shows only its tool calls; long units keep their first and last steps with an explicit omission marker.
RELATED DOCS: docs/design/jev-dynamic-compaction.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_dynamic_compaction.py.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.constants.jev_compaction import (
    JEV_COMPACTION_STEP_TEXT_CHARS,
    JEV_COMPACTION_TOOL_ARGUMENT_CHARS,
    JEV_COMPACTION_UNIT_HEAD_STEPS,
    JEV_COMPACTION_UNIT_TAIL_STEPS,
    JEV_COMPACTION_WRITER_OUTPUT_CHARS,
)
from vidbyte.tools._internal import IS_DONE_TOOL_NAME
from vidbyte.tools.types import ToolCallContext


@dataclass(frozen=True, slots=True)
class JevRunStep:
    """One completed iteration: the model's text and the tool calls it made."""

    iteration: int
    text: str
    calls: tuple[ToolCallContext, ...]


class JevRunSteps:
    """Builds and renders JevRunStep values for Jev, the record writer, and the fallback record."""

    @staticmethod
    def collect(state: BaseAgentRuntimeLoopState, first: int, last: int) -> tuple[JevRunStep, ...]:
        """Return the steps for iterations first..last inclusive, in order."""
        calls: dict[int, list[ToolCallContext]] = {}
        for context in state.call_contexts:
            if context.tool_name != IS_DONE_TOOL_NAME and context.iteration_count is not None and first <= context.iteration_count <= last:
                calls.setdefault(context.iteration_count, []).append(context)
        steps: list[JevRunStep] = []
        for iteration in range(first, last + 1):
            index = iteration - 1
            text = state.iteration_outputs[index] if 0 <= index < len(state.iteration_outputs) else ""
            steps.append(JevRunStep(iteration=iteration, text=(text or "").strip(), calls=tuple(calls.get(iteration, ()))))
        return tuple(steps)

    @classmethod
    def render_for_jev(cls, steps: Sequence[JevRunStep]) -> str:
        """Render steps without tool outputs, keeping the first and last steps of a long unit."""
        # @intent goals-not-outputs
        # Jev judges what each step is working toward; the agent's words and the tool arguments carry that goal,
        # while raw outputs are large and mostly irrelevant, so leaving them out keeps the state small (strategy 17).
        head, tail = JEV_COMPACTION_UNIT_HEAD_STEPS, JEV_COMPACTION_UNIT_TAIL_STEPS
        if len(steps) <= head + tail:
            return "\n\n".join(cls._step_for_jev(step) for step in steps)
        omitted = len(steps) - head - tail
        kept = [cls._step_for_jev(step) for step in steps[:head]]
        kept.append(f"[... {omitted} steps omitted ...]")
        kept.extend(cls._step_for_jev(step) for step in steps[-tail:])
        return "\n\n".join(kept)

    @classmethod
    def render_for_writer(cls, steps: Sequence[JevRunStep]) -> str:
        """Render steps with clipped tool outputs, because the record must keep what the steps found."""
        return "\n\n".join(cls._step_lines(step, outputs=True, text_limit=None) for step in steps)

    @classmethod
    def render_fallback(cls, steps: Sequence[JevRunStep]) -> str:
        """Render the deterministic record: every step's text and tool calls, without outputs."""
        return "\n\n".join(cls._step_lines(step, outputs=False, text_limit=JEV_COMPACTION_STEP_TEXT_CHARS) for step in steps)

    @classmethod
    def _step_for_jev(cls, step: JevRunStep) -> str:
        # Renders one step the way the unit-of-work question reads it.
        return cls._step_lines(step, outputs=False, text_limit=JEV_COMPACTION_STEP_TEXT_CHARS)

    @classmethod
    def _step_lines(cls, step: JevRunStep, *, outputs: bool, text_limit: int | None) -> str:
        # Renders a step heading, the agent's text, and one line per tool call.
        lines = [f"Step {step.iteration}"]
        if step.text:
            text = step.text if text_limit is None else _clip(step.text, text_limit)
            lines.append(f"Agent said: {text}")
        for context in step.calls:
            lines.append(cls._call_line(context, outputs=outputs))
        if len(lines) == 1:
            lines.append("(no text and no tool calls)")
        return "\n".join(lines)

    @staticmethod
    def _call_line(context: ToolCallContext, *, outputs: bool) -> str:
        # Renders one tool call as name, clipped arguments, final status, and optionally its clipped output.
        status = context.result.status.value if context.result is not None else context.state.value
        arguments = _clip(json.dumps(dict(context.arguments), default=str, sort_keys=True), JEV_COMPACTION_TOOL_ARGUMENT_CHARS)
        line = f"- called {context.tool_name} {arguments} ({status})"
        if outputs:
            line = f"{line}\n  output: {_clip(context.output or '', JEV_COMPACTION_WRITER_OUTPUT_CHARS)}"
        return line


def _clip(text: str, limit: int) -> str:
    # Cuts text to the limit and says how much was hidden, never silently.
    if len(text) <= limit:
        return text
    return f"{text[:limit]} [... {len(text) - limit} more characters]"


__all__ = ["JevRunStep", "JevRunSteps"]
