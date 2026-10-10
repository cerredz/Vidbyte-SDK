"""FILE: vidbyte/lib/jev/compute/plan.py

PURPOSE: Defines the fixed questions Jev answers about each assignment of a SWARM plan and the registry that expands them per assignment.
ROLE IN CODEBASE: The agent-side plan check asks every question once per assignment id in one Jev request and turns failed questions into gap text for the main agent.
ARCHITECTURE NOTE: Question content and lookup live here in vidbyte/lib, while asking Jev and rejecting or launching the plan stays in vidbyte/agents/jev/compute/.
COMMON MODIFICATION PATTERNS: Keep each question about one property of a single assignment, name that assignment through the item placeholder, and give it a gap the main agent can act on.
KNOWN EDGE CASES: Instructions are formatted with str.format, so question text must not contain braces other than the item placeholder.
RELATED DOCS: docs/design/jev-compute-swarm.md and skills/asking-jev-dynamic-compute-questions/SKILL.md.
TESTS: tests/test_jev_compute_swarm.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.dataclasses.jev import JevQuestion, JevSwarmPlanQuestion
from vidbyte.lib.enums.jev import JevSwarmPlanQuestionKey
from vidbyte.lib.errors import ConfigurationError

SWARM_PLAN_QUESTIONS = (
    JevSwarmPlanQuestion(
        key=JevSwarmPlanQuestionKey.SELF_CONTAINED,
        instructions="A helper starts with no memory of the main agent's run, so its assignment must carry everything it needs. A self-contained assignment states its objective, names its inputs, and relies only on the original task, the verified notes, and the shared conventions it will receive. Phrases that point to earlier discussion, such as the file mentioned before or the approach agreed earlier, leave a fresh helper guessing. Can the assignment with id {item} be carried out from its own fields plus the shared conventions alone? Does it name its inputs precisely enough to locate without the main agent's history? Did the main agent leave out a decision, source, or constraint that only its own earlier work contains? Do the assignment's objective and verification agree with each other about what the work is? Would a capable agent reading only this assignment produce the result the main task needs? The signal is an assignment that a fresh agent could start on immediately. References to unseen history or missing inputs do not establish it.",
        when_true="True when the assignment's objective, inputs, and deliverable can be understood without the main agent's history. Every source, target, and constraint it relies on is named in the assignment, the shared conventions, or the original task. A fresh agent could begin the work immediately from what it will receive.",
        when_false='False when the assignment depends on context only the main agent has, such as an unnamed file or an unstated decision. Inputs described so vaguely that a helper would have to search for which item is meant are not self-contained. If essential parts of the work are left implicit, the assignment is not self-contained.',
        gap='This assignment relies on context a fresh helper will not have. Name every input, source, and decision it needs inside the assignment or the shared conventions.',
    ),
    JevSwarmPlanQuestion(
        key=JevSwarmPlanQuestionKey.DISJOINT,
        instructions='Assignments that overlap make helpers duplicate effort and return conflicting results for the same items. An assignment is disjoint when no item, source, file, or question in its inputs or objective also appears in another assignment of the plan. Overlap is common when assignments are divided by theme, so two themes reach into the same material. Does the assignment with id {item} cover only items that no other assignment covers? Do its stated boundaries exclude the material that other assignments own? Did the plan divide the work by concrete items rather than by overlapping themes? Would this assignment and any other assignment change or examine the same target? Would the plan still cover each item once if this assignment were completed as written? The signal is an assignment with its own exclusive share of the work. Shared items or targets with any other assignment do not establish it.',
        when_true="True when the assignment's inputs, objective, and targets share no item with any other assignment in the plan. Its boundaries exclude the material other assignments cover. Completing it would not repeat or interfere with another helper's work.",
        when_false='False when another assignment covers some of the same items, sources, files, or questions. Assignments split by theme that would examine or change the same material overlap even when their wording differs. If the plan leaves it unclear which assignment owns an item this one touches, disjointness is not established.',
        gap='This assignment overlaps another assignment. Redraw the boundaries so every item, source, and file belongs to exactly one assignment.',
    ),
    JevSwarmPlanQuestion(
        key=JevSwarmPlanQuestionKey.IN_SCOPE,
        instructions="Every helper's work should advance what the user actually asked for and nothing beyond it. An in-scope assignment does part of the original task, follows its constraints, and does not add goals, features, or changes the user did not ask for. Assignments that drift into adjacent improvements or that reinterpret the task spend effort and can introduce unwanted changes. Does the assignment with id {item} serve a part of the original task? Does its objective respect the constraints and limits the user stated? Did the main agent add a goal that came from its own ideas rather than from the user? Does the assignment avoid deciding the overall direction that should stay with the main agent? Would its result be needed to complete the original task? The signal is an assignment that is a faithful piece of the requested work. New scope, ignored constraints, or a decision reserved for the main agent does not establish it.",
        when_true="True when the assignment performs a part of the original task within the user's stated constraints. Its result is needed for the task and adds no goal the user did not ask for. It supports the main agent's direction without deciding that direction itself.",
        when_false="False when the assignment adds work the user did not ask for or ignores a stated constraint. An assignment that chooses the task's overall approach takes a decision away from the main agent. If its connection to the original task cannot be seen, it is not shown to be in scope.",
        gap="This assignment goes beyond or against the user's task. Limit it to a needed part of the original task, within the user's constraints, and keep decisions about the whole task with yourself.",
    ),
    JevSwarmPlanQuestion(
        key=JevSwarmPlanQuestionKey.CHECKABLE_DELIVERABLE,
        instructions="The main agent can only merge results it can recognize and check, so each assignment must say what comes back and how it is verified. A checkable deliverable names the exact result and its form, and the verification gives a concrete way to confirm it. A deliverable described only as findings or progress, or a check described only as reviewing the work, leaves no clear way to accept or reject the result. Does the assignment with id {item} name a concrete result and the form it should take? Does its verification describe a check that could actually be carried out, such as running a test or comparing against a source? Does the deliverable's form follow the shared conventions so it can be merged with the other results? Is the result small and structured enough for the main agent to read alongside the others? Would the main agent know whether the returned result is correct and complete? The signal is a named, checkable result in a form that can be merged. Vague outputs or checks that cannot be performed do not establish it.",
        when_true='True when the assignment names the exact result to return and the form it should take. Its verification describes a concrete check that the helper can carry out before returning. The result follows the shared conventions so the main agent can merge it with the others.',
        when_false='False when the deliverable is vague, such as general findings or progress, or has no stated form. A verification that only says to review or double-check the work gives no concrete check. If the main agent could not tell a correct result from a flawed one, the deliverable is not checkable.',
        gap="This assignment's result or check is too vague. Name the exact result and form to return, and a concrete check the helper can run before returning it.",
    ),
)


class JevSwarmPlanRegistry:
    """Registry of the questions Jev answers about every assignment of a SWARM plan."""

    _questions: Mapping[JevSwarmPlanQuestionKey, JevSwarmPlanQuestion] = MappingProxyType({question.key: question for question in SWARM_PLAN_QUESTIONS})

    @classmethod
    def question_keys(cls) -> tuple[JevSwarmPlanQuestionKey, ...]:
        """Return the plan question keys in the order they are asked about each assignment."""
        return tuple(cls._questions)

    @classmethod
    def get(cls, key: JevSwarmPlanQuestionKey) -> JevSwarmPlanQuestion:
        """Return the registered plan question for a key, or raise when none is registered."""
        found = cls._questions.get(key)
        if found is None:
            raise ConfigurationError(f"Jev swarm plan question {key.value!r} has no registered record.", details={"key": key.value, "registered": [item.value for item in cls._questions]})
        return found

    @classmethod
    def questions(cls, ids: Iterable[str]) -> tuple[JevQuestion, ...]:
        """Return every plan question for every assignment id, grouped by assignment, for one shared Jev request."""
        return tuple(question.to_question(item) for item in ids for question in cls._questions.values())


__all__ = ["SWARM_PLAN_QUESTIONS", "JevSwarmPlanRegistry"]
