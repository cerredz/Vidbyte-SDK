"""FILE: vidbyte/lib/jev/compute/repeating.py

PURPOSE: Defines the REPEATING situation's fixed sign questions, one dataclass per question: whether the agent's newest attempt on a problem repeats an approach already recorded as failed, whether it ends in the same failure, whether the agent offers no new cause, and whether the requested work needs the problem solved.
ROLE IN CODEBASE: JevComputeRegistry registers every class in REPEATING_QUESTIONS, and JevComputeSituations lists the same keys with the situation's threshold, veto, and gate. The recognizer asks them only when code finds a failed approach whose problem no approach has solved.
ARCHITECTURE NOTE: Each question follows skills/asking-jev-questions/SKILL.md ("Writing a full question"). Code chooses the problem and copies its recorded attempts into `problem` and `attempts`, so no question has to find the problem or decide which approaches belong to it. Every `true` side is the sign of being stuck, so NO_NEW_CAUSE asks whether a new cause is absent.
COMMON MODIFICATION PATTERNS: Load skills/asking-jev-questions/SKILL.md before editing. Add a sign as a new JevComputeQuestion subclass, its key to JevComputeQuestionKey, and the key to the situation in JevComputeSituations. Keep each section one string literal (lint S062).
KNOWN EDGE CASES: A trivial variation of a command, such as a retry flag or quieter output, is the same approach; a new change, a new input, or a different target is a different one. Restating the error is not a cause.
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

# Every REPEATING question reads the same five fields, so every brief describes them with the same words.
REPEATING_STATE = f"The state has five fields: `request`, `problem`, `attempts`, `failures`, and `recent`. {REQUEST_FIELD} `problem` names one problem the agent met during the run, such as an error, a failing test, or a step that does not work, in the run's own words; code chose it because at least one attempt on it failed and none has solved it. `attempts` lists the approaches the agent took against `problem`, as a note-taker recorded them from the run: what the agent did, whether it worked, failed, or is unresolved, and quotes copied exactly from the run events that show it. `failures` lists error text from the run that no later event has resolved, each quoted exactly from the tool output that reported it. {RECENT_FIELD}"
# The approaches and attempts are defined the same way in every REPEATING question.
APPROACH_DEFINITION = "An approach is a way of acting on a problem: the change the agent makes, the command it runs, or the input it tries. An attempt is one time the agent carries out an approach, and an attempt has failed when its result shows the problem still there, such as the same error, the same failing test, or no change."
NEWEST_ATTEMPT_RULE = "The newest attempt on `problem` is the latest tool call or group of tool calls in `recent` that acts on `problem`; when `recent` shows no attempt on `problem`, there is no newest attempt."


@dataclass(frozen=True)
class RepeatingSameApproachQuestion(JevComputeQuestion):
    """Does the newest attempt repeat an approach already recorded as failed?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.REPEATING_SAME_APPROACH
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether an AI agent that is stuck on a problem has just tried, again, something it already tried without success. It is one of several checks on whether the agent is going in circles and would be better served by a fresh start, and it looks only at whether the newest attempt repeats an approach that already failed, not at what the attempt produced or whether the agent understands the problem.",
        state=REPEATING_STATE,
        definitions=(
            APPROACH_DEFINITION,
            "Two attempts use the same approach when they make the same change to the same target, run the same command with the same or trivially different arguments, or try the same input again. A trivial difference does not change what is tried, such as a retry, a flag that only changes how much output is shown, different spacing, or reordered arguments; a new change, a new input, a different target, or a different command makes a different approach.",
        ),
        rules=(
            NEWEST_ATTEMPT_RULE,
            "Compare the newest attempt with every approach `attempts` records as failed; one match is enough.",
            "An attempt that adds a new step before the old one, such as an edit followed by the same command, is a different approach, because the new step changes what is tried.",
            "Reading, searching, or inspecting to find a cause is not an attempt on the problem, so a newest event of that kind gives no newest attempt.",
            "When there is no newest attempt, or `attempts` records no failed approach, the newest attempt does not repeat a failed approach.",
            "Judge only whether the approach repeats. What the newest attempt produced, whether the agent offers a new cause, and whether the request needs the problem solved are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does the newest attempt on `problem` in `recent` use an approach that `attempts` records as failed?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when the newest attempt on `problem` in `recent` uses an approach that `attempts` records as failed. The signs are a newest tool call that makes the same change to the same target, runs the same command with the same or trivially different arguments, or tries the same input as a failed approach in `attempts`.",
        not_for="A newest attempt that makes a new change, tries a new input, acts on a different target, or adds a new step, a newest event that only reads or inspects, or no failed approach in `attempts`, belongs to false.",
        easy=("`attempts` records: ran npm install after deleting node_modules, failed; the newest event in `recent` is E31 TOOL shell with arguments rm -rf node_modules && npm install.",),
        boundary=("`attempts` records: ran pytest tests/test_auth.py, failed; the newest event in `recent` is E40 TOOL shell with arguments pytest tests/test_auth.py -q.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when the newest attempt on `problem` in `recent` does not use an approach that `attempts` records as failed. The signs are a newest attempt that makes a new change, tries a new input, acts on a different target, or adds a new step before an old command, a newest event that only reads, searches, or inspects, no attempt on `problem` in `recent`, or no failed approach in `attempts`.",
        not_for="A newest attempt that makes the same change, runs the same command with the same or trivially different arguments, or tries the same input as a failed approach in `attempts` belongs to true.",
        easy=("`attempts` records: ran npm install after deleting node_modules, failed; the newest event in `recent` is E31 TOOL read_file with arguments package-lock.json.",),
        boundary=("`attempts` records: ran pytest tests/test_auth.py, failed; the newest events in `recent` are E39 TOOL edit_file changing the token expiry check in auth.py and E40 TOOL shell with arguments pytest tests/test_auth.py -q.",),
    ))


@dataclass(frozen=True)
class RepeatingSameResultQuestion(JevComputeQuestion):
    """Does the newest attempt end in the same failure as an earlier one?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.REPEATING_SAME_RESULT
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the latest thing an AI agent tried against a problem produced nothing new: the same failure it had already seen. It is one of several checks on whether the agent is going in circles and would be better served by a fresh start, and it looks only at the newest attempt's result, not at which approach produced it or whether the agent understands the problem.",
        state=REPEATING_STATE,
        definitions=(
            APPROACH_DEFINITION,
            "A failure is the result that shows a problem is still there: an error message, a failing test or check, a wrong output, or no change. Two failures are the same when they report the same error, the same failing test or check, or the same wrong result, even when line numbers, timestamps, ids, paths in a stack trace, or the order of lines differ.",
        ),
        rules=(
            NEWEST_ATTEMPT_RULE,
            "Compare the newest attempt's result with the failures that `attempts` quotes and that `failures` lists; matching one earlier failure is enough.",
            "A different error, a failure that moved to a different test or step, or a partial improvement is new information, so it is not the same failure, even when the problem is not yet solved.",
            "A newest attempt that succeeded, or whose result `recent` does not show, does not end in the same failure.",
            "When there is no newest attempt, it does not end in the same failure.",
            "Judge only whether the result repeats. Which approach the attempt used, whether the agent offers a new cause, and whether the request needs the problem solved are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does the newest attempt on `problem` in `recent` end in a failure that is the same as one in `attempts` or `failures`?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when the newest attempt on `problem` in `recent` ends in a failure that is the same as one in `attempts` or `failures`. The signs are a newest result that reports the same error, the same failing test or check, or the same wrong output as an earlier failure, allowing for different line numbers, timestamps, ids, or line order.",
        not_for="A newest result with a different error, a failure moved to another test or step, a partial improvement, a success, no shown result, or no newest attempt belongs to false.",
        easy=("`failures` quotes ModuleNotFoundError: No module named 'yaml', and the newest event in `recent` is E52 TOOL shell, state error, output ModuleNotFoundError: No module named 'yaml'.",),
        boundary=("`attempts` quotes FAILED tests/test_auth.py::test_refresh at line 88, and the newest event in `recent` is E61 TOOL shell, state error, output FAILED tests/test_auth.py::test_refresh at line 91 with the same assertion message.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when the newest attempt on `problem` in `recent` does not end in a failure that is the same as one in `attempts` or `failures`. The signs are a newest result with a different error, a failure that moved to a different test or step, a partial improvement, a success, a result `recent` does not show, or no attempt on `problem` in `recent`.",
        not_for="A newest result that reports the same error, the same failing test or check, or the same wrong output as an earlier failure, with only line numbers, timestamps, ids, or line order changed, belongs to true.",
        easy=("`failures` quotes ModuleNotFoundError: No module named 'yaml', and the newest event in `recent` is E52 TOOL shell, state success, output 12 passed.",),
        boundary=("`attempts` quotes FAILED tests/test_auth.py::test_refresh at line 88, and the newest event in `recent` is E61 TOOL shell, state error, output FAILED tests/test_auth.py::test_logout at line 40.",),
    ))


@dataclass(frozen=True)
class RepeatingNoNewCauseQuestion(JevComputeQuestion):
    """Do the agent's newest responses give no new cause for the problem?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.REPEATING_NO_NEW_CAUSE
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether an AI agent that keeps failing on a problem has stopped offering new explanations of it and is only trying again. It is one of several checks on whether the agent is going in circles and would be better served by a fresh start, and it looks only at whether the agent's newest words name a new cause, not at which approach it tried or what that attempt produced.",
        state=REPEATING_STATE,
        definitions=(
            APPROACH_DEFINITION,
            "A cause is a statement of why a problem happens: what is wrong, where it is, or why the earlier attempts did not fix it. A cause is new when no approach in `attempts` already acted on it. Restating the error, saying the attempt failed, or announcing another try names no cause.",
        ),
        rules=(
            "Read the agent's newest responses: the ASSISTANT events in `recent` after the last attempt that `attempts` records, or the last ASSISTANT event in `recent` when none comes after it.",
            "A cause offered as a guess, such as a stale cache or a wrong version, counts as a cause, and it is new when no approach in `attempts` acted on it.",
            "A cause that an approach in `attempts` already acted on is not new, even when the agent words it differently.",
            "When the newest responses name no cause at all, including when `recent` holds no ASSISTANT event, they give no new cause.",
            "Judge only whether a new cause is named. Which approach the agent tried, what the attempt produced, and whether the request needs the problem solved are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Do the agent's newest responses in `recent` give no new cause for `problem`?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when the agent's newest responses in `recent` give no new cause for `problem`. The signs are newest responses that only restate the error, say the attempt failed, announce another try, or name a cause that an approach in `attempts` already acted on, or no newest response at all.",
        not_for="Newest responses that name a cause, even as a guess, that no approach in `attempts` has acted on belong to false.",
        easy=("`attempts` records two reinstalls of the package, both failed, and the newest ASSISTANT event in `recent` says: Still failing. Let me try installing it again.",),
        boundary=("`attempts` records two reinstalls of the package, both failed, and the newest ASSISTANT event in `recent` says: The error says the module is missing, so I'll install it once more.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when the agent's newest responses in `recent` give a new cause for `problem`. The signs are newest responses that name what is wrong, where it is, or why the earlier attempts did not fix it, even as a guess, in a way no approach in `attempts` has acted on yet.",
        not_for="Newest responses that only restate the error, say the attempt failed, announce another try, or repeat a cause an approach in `attempts` already acted on, or no newest response at all, belong to true.",
        easy=("`attempts` records two reinstalls of the package, both failed, and the newest ASSISTANT event in `recent` says: The import fails because the package is installed for Python 3.9 but the tests run on 3.11.",),
        boundary=("`attempts` records two reinstalls of the package, both failed, and the newest ASSISTANT event in `recent` says: Maybe the test runner uses a cached environment; I'll check which interpreter it runs.",),
    ))


@dataclass(frozen=True)
class RepeatingBlocksRequestQuestion(JevComputeQuestion):
    """Does the requested work need the problem solved?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.REPEATING_BLOCKS_REQUEST
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether a problem an AI agent is stuck on stands in the way of what the user asked for. It is one of several checks on whether the agent's being stuck is worth spending extra effort to break, and it looks only at whether the requested work needs the problem solved, not at how the agent has tried to solve it.",
        state=REPEATING_STATE,
        definitions=(
            "The requested work is what `request` asks the agent to do or produce, in any wording, together with what that result plainly needs, such as running the code the user asked to fix.",
            "Requested work needs a problem solved when the requested result cannot be produced, finished, or shown to work while the problem remains, such as a build error that stops the requested feature from running, or a failing test the user asked to fix. A problem off that path, such as a warning in an unrelated file, or a step the request never asked for, does not stand in the way.",
        ),
        rules=(
            "Judge from `request` and from what `problem` is, using `attempts` and `recent` only to understand what the problem affects.",
            "A problem that only blocks checking the requested result, such as a test runner that will not start, stands in the way, because the result cannot be shown to work.",
            "A problem in work the agent chose on its own, such as an extra refactor or an optional deploy the request does not ask for, does not stand in the way of the requested work.",
            "Judge only whether the requested work needs the problem solved. Whether the agent is repeating itself and whether it offers a new cause are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does the work `request` asks for need `problem` solved?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when the work `request` asks for needs `problem` solved. The signs are a problem that stops the requested result from being produced, finished, or shown to work, such as an error in the code the user asked to change, a failing test the user asked to fix, or a broken step the requested result depends on.",
        not_for="A problem in work the request neither asks for nor needs, such as a warning in an unrelated file, an optional cleanup, or a step the agent chose on its own, belongs to false.",
        easy=("`request` says: Get the test suite passing, and `problem` is: ImportError in tests/conftest.py stops every test from loading.",),
        boundary=("`request` says: Add a CSV export to the reports page, and `problem` is: the dev server crashes on start, so the reports page cannot be opened.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when the work `request` asks for does not need `problem` solved. The signs are a problem that the requested result can be produced, finished, and shown to work without, such as a warning in an unrelated file, a failure in an optional step, or a problem in work the agent added on its own.",
        not_for="A problem that stops the requested result from being produced, finished, or shown to work, including one that only blocks checking it, belongs to true.",
        easy=("`request` says: Get the test suite passing, and `problem` is: a lint warning about line length in docs/conf.py.",),
        boundary=("`request` says: Add a CSV export to the reports page, and `problem` is: the deploy script fails to upload to staging, which the request never mentions.",),
    ))


REPEATING_QUESTIONS: tuple[JevComputeQuestion, ...] = (
    RepeatingSameApproachQuestion(),
    RepeatingSameResultQuestion(),
    RepeatingNoNewCauseQuestion(),
    RepeatingBlocksRequestQuestion(),
)

__all__ = [
    "REPEATING_QUESTIONS",
    "REPEATING_STATE",
    "RepeatingBlocksRequestQuestion",
    "RepeatingNoNewCauseQuestion",
    "RepeatingSameApproachQuestion",
    "RepeatingSameResultQuestion",
]
