"""FILE: vidbyte/lib/jev/compute/self_contained_step.py

PURPOSE: Defines the SELF_CONTAINED_STEP situation's fixed sign questions, one dataclass per question: whether the agent's next stated step takes its own tool calls, whether its words with the request state everything a new helper needs, whether its result can be handed back, and whether the request asks for it.
ROLE IN CODEBASE: JevComputeRegistry registers every class in SELF_CONTAINED_STEP_QUESTIONS, and JevComputeSituations lists the same keys with the situation's threshold, veto, and gate. The recognizer asks them only when the run brief records a next step.
ARCHITECTURE NOTE: Each question follows skills/asking-jev-questions/SKILL.md ("Writing a full question"). Code copies the brief's soonest next step into `next_step`, so no question has to choose among steps. The helper is defined as an agent that starts with no memory of the run, so STATES_ALL is judged against `request` and `next_step` alone.
COMMON MODIFICATION PATTERNS: Load skills/asking-jev-questions/SKILL.md before editing. Add a sign as a new JevComputeQuestion subclass, its key to JevComputeQuestionKey, and the key to the situation in JevComputeSituations. Keep each section one string literal (lint S062).
KNOWN EDGE CASES: A step that refers to something found only during the run, such as "the bug above", does not state everything a helper needs. A step that finishes the task or reports to the user takes no tool calls of its own.
RELATED DOCS: docs/design/jev-compute-situations.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vidbyte.lib.dataclasses.jev import JevBrief, JevComputeQuestion, JevCriterion
from vidbyte.lib.enums.jev import JevComputeQuestionKey
from vidbyte.lib.jev.compute.state import (
    IGNORE_CLAIMS,
    JUDGE_MEANING,
    RECENT_FIELD,
    REQUEST_FIELD,
)

# Every SELF_CONTAINED_STEP question reads the same four fields, so every brief describes them with the same words.
SELF_CONTAINED_STEP_STATE = f"The state has four fields: `request`, `next_step`, `brief`, and `recent`. {REQUEST_FIELD} `next_step` is the soonest step the agent said it would take and has not yet taken, copied exactly from one of the agent's responses and labeled with that response's id. `brief` is a note-taker's record of the run so far, as JSON: the agent's current goal, its stated steps, the items it works through, the approaches it tried, and errors still open, each backed by quotes copied exactly from the run. {RECENT_FIELD}"
# The step and the helper are defined the same way in every SELF_CONTAINED_STEP question.
STEP_DEFINITION = "A step is one piece of work the agent said it would do next, such as researching a question, building or changing something, running or testing something, or investigating an error. A helper is another AI agent that starts with no memory of this run: it receives only the step's words and `request`, does the step with its own tools, and hands its result back to the agent."


@dataclass(frozen=True)
class SelfContainedStepSubstantialQuestion(JevComputeQuestion):
    """Does the next step take its own tool calls to do?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.SELF_CONTAINED_STEP_SUBSTANTIAL
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the next thing an AI agent said it would do is a real piece of work, one that needs the agent to go and read, search, run, or change something. It is one of several checks on whether that step could be handed to a helper agent, and it looks only at how much the step involves, not at whether its words are complete or whether the user asked for it.",
        state=SELF_CONTAINED_STEP_STATE,
        definitions=(
            STEP_DEFINITION,
            "A step takes its own tool calls when doing it needs the agent to read, search, fetch, run, test, or change something it does not already hold, such as opening files, querying a service, or running a test suite. A step the agent can complete by writing from what it already holds, such as summarizing what it found, answering the user, or deciding between options already in front of it, takes no tool calls of its own.",
        ),
        rules=(
            "Judge `next_step` by the work its words describe, using `brief` and `recent` only to tell what the agent already holds.",
            "A step that finishes the task, reports to the user, or writes the final answer takes no tool calls of its own.",
            "A step whose work is one quick call the agent has effectively already made, such as reading a file whose content `recent` already shows in full, takes no tool calls of its own.",
            "When `next_step` is empty or names no work, it takes no tool calls of its own.",
            "Judge only whether the step takes its own tool calls. Whether its words state everything a helper needs, whether its result can be handed back, and whether the request asks for it are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `next_step` describe work that takes its own tool calls to do?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `next_step` describes work that takes its own tool calls to do. The signs are a step that needs the agent to read, search, fetch, run, test, or change something it does not already hold, such as researching a question, investigating an error, or building or changing part of the work.",
        not_for="A step the agent can complete by writing from what it already holds, such as summarizing, answering the user, or choosing between options in front of it, a step that finishes the task, or an empty step, belongs to false.",
        easy=("`next_step` quotes the agent: Next I'll find out which versions of the library support async sessions.",),
        boundary=("`next_step` quotes the agent: Next I'll check whether the retry setting in settings.py is read anywhere else in the codebase, and `recent` shows only settings.py was opened.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `next_step` describes no work that takes its own tool calls to do. The signs are a step the agent can complete by writing from what it already holds, such as summarizing findings, answering the user, deciding between options in front of it, or finishing the task, or a step that is empty or names no work.",
        not_for="A step that needs the agent to read, search, fetch, run, test, or change something it does not already hold belongs to true.",
        easy=("`next_step` quotes the agent: Next I'll summarize what I found for the user.",),
        boundary=("`next_step` quotes the agent: Next I'll explain whether the retry setting in settings.py is used, and `recent` shows a full search of the codebase for that setting.",),
    ))


@dataclass(frozen=True)
class SelfContainedStepStatesAllQuestion(JevComputeQuestion):
    """Do the next step's words, with the request, state everything a helper needs?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.SELF_CONTAINED_STEP_STATES_ALL
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the next thing an AI agent said it would do is described fully enough that a helper with no memory of the run could do it from the words alone. It is one of several checks on whether that step could be handed to a helper agent, and it looks only at whether the step's words and the user's request together say everything needed, not at how much work the step is or whether the user asked for it.",
        state=SELF_CONTAINED_STEP_STATE,
        definitions=(
            STEP_DEFINITION,
            "A step states everything a helper needs when its words, read together with `request`, name what the work acts on, the information the work starts from, and what result to produce, and every reference in them points to something they themselves state. A reference relies on the run when it points to something found, decided, or named only during the run, such as the bug above, those three files, the approach that failed, or a value that appears only in `brief` or `recent`.",
        ),
        rules=(
            "Judge `next_step` together with `request` only; use `brief` and `recent` to tell which of its references point to things found only during the run.",
            "A reference to something `request` states, such as a file or a feature the user named, does not rely on the run.",
            "Shared knowledge a capable helper brings, such as how a common library or language works, is not something the step must state.",
            "When `next_step` relies on the run for its target, its starting information, or its result, it does not state everything a helper needs, even when the rest is clear.",
            "When `next_step` is empty or names no work, it does not state everything a helper needs.",
            "Judge only whether the words state everything a helper needs. How much work the step takes, whether its result can be handed back, and whether the request asks for it are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `next_step`, read together with `request`, state everything a helper needs to do it?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `next_step`, read together with `request`, states everything a helper needs to do it. The signs are step words that name what the work acts on, what it starts from, and what result to produce, with every reference pointing to something the step or `request` states, or to shared knowledge a capable helper brings.",
        not_for="A step whose target, starting information, or result relies on something found, decided, or named only during the run, such as the bug above or those files, or an empty step, belongs to false.",
        easy=("`request` says: Add rate limiting to our public API, and `next_step` quotes the agent: Next I'll find out which rate limiting libraries support Redis-backed counters in Python and compare their licenses.",),
        boundary=("`request` says: Speed up the reports endpoint in api/reports.py, and `next_step` quotes the agent: Next I'll profile api/reports.py under 1,000 rows and list the slowest functions.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `next_step`, read together with `request`, does not state everything a helper needs to do it. The signs are step words whose target, starting information, or expected result points to something found, decided, or named only during the run, such as the bug above, those three files, the approach that failed, or a value only `brief` or `recent` holds, or an empty step.",
        not_for="A step whose words, with `request`, name what the work acts on, what it starts from, and what result to produce, with every reference pointing to something they state or to shared knowledge, belongs to true.",
        easy=("`request` says: Add rate limiting to our public API, and `next_step` quotes the agent: Next I'll check whether that library handles the problem I found earlier.",),
        boundary=("`request` says: Speed up the reports endpoint in api/reports.py, and `next_step` quotes the agent: Next I'll profile the three slow functions I spotted and list the slowest.",),
    ))


@dataclass(frozen=True)
class SelfContainedStepHandsBackQuestion(JevComputeQuestion):
    """Does the next step ask for a result a helper can hand back when done?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.SELF_CONTAINED_STEP_HANDS_BACK
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the next thing an AI agent said it would do produces something that can be finished separately and handed back, rather than being one strand of work the agent is in the middle of. It is one of several checks on whether that step could be handed to a helper agent, and it looks only at the kind of result the step produces, not at how much work it is or whether its words are complete.",
        state=SELF_CONTAINED_STEP_STATE,
        definitions=(
            STEP_DEFINITION,
            "A step's result can be handed back when the step ends in something complete that the agent can take and use: an answer, a finding, a list, a comparison, a new file, or a finished change to a part of the work the agent is not itself changing. A step cannot be handed back when it is interleaved with the agent's own unfinished work: a change to the same thing the agent is changing now, or work that needs the agent's decisions while it is underway.",
        ),
        rules=(
            "Judge from what `next_step` says it produces and from what `recent` shows the agent is changing now.",
            "A step that only reads, researches, or tests and reports what it found can be handed back, because its result is a finding.",
            "A step that edits the same file, function, or document the agent's newest events are editing cannot be handed back, because the two changes would collide.",
            "When `next_step` is empty or names no work, its result cannot be handed back.",
            "Judge only whether the result can be handed back. How much work the step takes, whether its words state everything a helper needs, and whether the request asks for it are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `next_step` ask for a result that a helper can hand back to the agent when it is done?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `next_step` asks for a result that a helper can hand back to the agent when it is done. The signs are a step that ends in an answer, a finding, a list, a comparison, a new file, or a finished change to a part of the work the agent is not changing now.",
        not_for="A step that changes the same thing the agent's newest events are changing, needs the agent's decisions while it is underway, or is empty belongs to false.",
        easy=("`next_step` quotes the agent: Next I'll research which browsers support the View Transitions API and list them.",),
        boundary=("`next_step` quotes the agent: Next I'll write unit tests for utils/dates.py, and `recent` shows the agent editing api/handlers.py.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `next_step` asks for no result that a helper can hand back to the agent when it is done. The signs are a step that changes the same file, function, or document the agent's newest events are changing, a step that needs the agent's own decisions while it is underway, or an empty step.",
        not_for="A step that ends in an answer, a finding, a list, a comparison, a new file, or a finished change to a part of the work the agent is not changing now belongs to true.",
        easy=("`next_step` quotes the agent: Next I'll keep editing this function until the types line up, and `recent` shows the agent editing that function.",),
        boundary=("`next_step` quotes the agent: Next I'll write unit tests for utils/dates.py, and `recent` shows the agent editing utils/dates.py.",),
    ))


@dataclass(frozen=True)
class SelfContainedStepRequestedQuestion(JevComputeQuestion):
    """Is the next step part of the work the request asks for?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.SELF_CONTAINED_STEP_REQUESTED
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the next thing an AI agent said it would do is part of what the user asked for. It is one of several checks on whether that step could be handed to a helper agent, and it looks only at whether the user's request covers the step, not at how much work the step is or how it should be done.",
        state=SELF_CONTAINED_STEP_STATE,
        definitions=(
            STEP_DEFINITION,
            "A step is part of the requested work when `request` asks for it in any wording, or when the requested result cannot be produced, finished, or shown to work without it, such as researching an API the user asked the agent to integrate or testing a change the user asked for.",
        ),
        rules=(
            "Judge `next_step` against `request`, using `brief` and `recent` only to understand what the step is for.",
            "A step the agent added on its own that the requested result does not need, such as an optional cleanup, an unrequested refactor, or a side investigation, is not part of the requested work, even when it would be useful.",
            "When `next_step` is empty or names no work, it is not part of the requested work.",
            "Judge only whether the request covers the step. How much work the step takes, whether its words state everything a helper needs, and whether its result can be handed back are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Is `next_step` part of the work `request` asks for?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `next_step` is part of the work `request` asks for. The signs are a step the request asks for in any wording, or a step without which the requested result cannot be produced, finished, or shown to work.",
        not_for="A step the agent added on its own that the requested result does not need, such as an optional cleanup, an unrequested refactor, or a side investigation, or an empty step, belongs to false.",
        easy=("`request` says: Integrate Stripe checkout into the store, and `next_step` quotes the agent: Next I'll look up how Stripe Checkout sessions report a completed payment.",),
        boundary=("`request` says: Make the signup form accessible, and `next_step` quotes the agent: Next I'll run an accessibility audit on the signup page and list the violations.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `next_step` is not part of the work `request` asks for. The signs are a step the request never asks for and the requested result does not need, such as an optional cleanup, an unrequested refactor, a side investigation, or work on something the request does not mention, or an empty step.",
        not_for="A step the request asks for in any wording, or one the requested result cannot be produced, finished, or shown to work without, belongs to true.",
        easy=("`request` says: Integrate Stripe checkout into the store, and `next_step` quotes the agent: Next I'll migrate the whole project to TypeScript.",),
        boundary=("`request` says: Make the signup form accessible, and `next_step` quotes the agent: Next I'll run a performance audit on the signup page and list the slow requests.",),
    ))


SELF_CONTAINED_STEP_QUESTIONS: tuple[JevComputeQuestion, ...] = (
    SelfContainedStepSubstantialQuestion(),
    SelfContainedStepStatesAllQuestion(),
    SelfContainedStepHandsBackQuestion(),
    SelfContainedStepRequestedQuestion(),
)

__all__ = [
    "SELF_CONTAINED_STEP_QUESTIONS",
    "SELF_CONTAINED_STEP_STATE",
    "SelfContainedStepHandsBackQuestion",
    "SelfContainedStepRequestedQuestion",
    "SelfContainedStepStatesAllQuestion",
    "SelfContainedStepSubstantialQuestion",
]
