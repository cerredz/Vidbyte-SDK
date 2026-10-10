"""FILE: vidbyte/lib/jev/preflight/bulk_work.py

PURPOSE: Defines the BULK_WORK preset's eight fixed preflight questions, one dataclass per question, each asking Jev to recognize one separate piece of evidence that a request's work can be split across fresh agents.
ROLE IN CODEBASE: JevPreflightRegistry registers every class in BULK_WORK_QUESTIONS by key, JevPresets.BULK_WORK lists the same keys in the order Jev is asked them, and JevPreflightGate offers the main agent the run_bulk_work tool only when every answer reaches the configured threshold.
ARCHITECTURE NOTE: Each question follows skills/asking-jev-questions/SKILL.md ("Writing a full question") in the layout clarity.py uses: a short introduction, the shared STATE, general definitions, the rules (special cases, the zero, one, and many cases, the no-task side, the focus, then JUDGE_MEANING and IGNORE_CLAIMS), and one positive yes/no question. Every true side is evidence for splitting, so the preset needs no per-question inversion.
COMMON MODIFICATION PATTERNS: Load skills/asking-jev-questions/SKILL.md before editing. Keep each question near 500 tokens with one judgment, one verb, and minimal-pair examples across its two sides; add a question by adding its key to JevPreflightQuestionKey and JevPresets and appending it to BULK_WORK_QUESTIONS. Write every string as one literal (lint S062).
KNOWN EDGE CASES: A request can pass some questions and fail others, for example many items that all change one shared file; each failure stays its own answer, so one clear no keeps the work on one agent. A final overview of per-item results, an order for showing results, and a shared fixed rubric are not evidence against splitting.
RELATED DOCS: docs/design/jev-bulk-work.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/features/jev_bulk_work/test_jev_bulk_work.py and scripts/test-jev-bulk-work.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vidbyte.lib.dataclasses.jev import JevBrief, JevCriterion, JevPreflightQuestion
from vidbyte.lib.enums.jev import JevPreflightQuestionKey
from vidbyte.lib.jev.preflight.clarity import IGNORE_CLAIMS, JUDGE_MEANING

# Every bulk-work question reads the same one-field state and judges the same unit of work, so every brief
# describes both with the same words.
STATE = "The state has one field, `request`: the message a user sent to an AI agent to start a task, with any text, code, or data the user pasted into it, and nothing else."
ITEM = "An item is one separate thing the user wants worked on, such as a file, a document, a record, or a web page."


@dataclass(frozen=True)
class BulkWorkMultipleItemsQuestion(JevPreflightQuestion):
    """Does the request name at least two items to work on?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.BULK_WORK_MULTIPLE_ITEMS
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether a user's request names more than one item to work on. It is one of several checks on whether the work can be split across separate agents.",
        state=STATE,
        definitions=(
            ITEM,
            "A request names an item when its words point to it by name, by description, in a list, as pasted content, or as a member of a clearly bounded group, such as each attached invoice.",
        ),
        rules=(
            "Several actions, outputs, or versions for one thing name one item.",
            "A choice between things, such as one or the other, names only the item that will be chosen.",
            "A request that names no item or one item does not name at least two items; one that names two or more does, even without an exact count.",
            "A request with no task at all, such as an empty message, a greeting, thanks, or a sign-off, does not name at least two items.",
            "Judge only how many items are named; what work they get is a separate check.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `request` name at least two items to work on?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `request` names at least two items to work on. The signs are two or more named things, a list or pasted set of entries, or a group whose members each get work.",
        not_for="One item with several actions or outputs, a choice of one item, and no task at all belong to false.",
        easy=("Translate these three emails into French.",),
        boundary=("Review the billing page and the profile page.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `request` names no item or one item to work on. The signs are one thing with several actions, outputs, or versions, a choice that picks one thing, or no task at all.",
        not_for="Two or more items, named, listed, or in a clearly bounded group, belong to true.",
        easy=("Translate this email into French.",),
        boundary=("Review either the billing page or the profile page.",),
    ))
    gap: str = "The request does not name at least two items to work on; several actions on one item, or a choice of one item, are not several items."


@dataclass(frozen=True)
class BulkWorkKnownItemsQuestion(JevPreflightQuestion):
    """Does the request identify every item it asks to work on?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.BULK_WORK_KNOWN_ITEMS
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether a user's request says exactly which items it wants worked on, so the work could be divided before it starts. It is one of several checks on whether the work can be split across separate agents.",
        state=STATE,
        definitions=(
            ITEM,
            "A fixed rule picks out items without judging their content, such as a named folder; a discovery rule picks them out only after searching or judging content, such as every bug in a codebase.",
            "A request identifies an item when it lists, pastes, or names it, or picks it out with a fixed rule.",
        ),
        rules=(
            "Items picked out by a discovery rule are not identified, because they must be found before the work can be divided.",
            "A request that names no item does not identify every item it asks to work on; one with items does only when every item is identified.",
            "A request with no task at all, such as an empty message, a greeting, thanks, or a sign-off, does not identify every item it asks to work on.",
            "Judge only whether every item is identified; how many items there are is a separate check.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `request` identify every item it asks to work on?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `request` identifies every item it asks to work on. The signs are items that are listed, pasted, or named, or picked out by a fixed rule such as a named folder.",
        not_for="Items that must first be found by searching or judging content, no item, and no task at all belong to false.",
        easy=("Summarize report_a.pdf, report_b.pdf, and report_c.pdf.",),
        boundary=("Add a license header to every Python file in the src folder.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `request` does not identify every item it asks to work on. The signs are items that must first be found by searching or judging content, a vague group such as everything, no item, or no task at all.",
        not_for="Items that are all listed, pasted, named, or picked out by a fixed rule belong to true.",
        easy=("Find and fix the bugs in this codebase.",),
        boundary=("Add a license header to every Python file that has no tests.",),
    ))
    gap: str = "The request does not identify every item it asks to work on; some items must first be found by searching or judging content, so the work cannot be divided before it starts."


@dataclass(frozen=True)
class BulkWorkSameOperationQuestion(JevPreflightQuestion):
    """Does the request ask for the same work on each item?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.BULK_WORK_SAME_OPERATION
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether a user's request asks for the same kind of work on each of its items. It is one of several checks on whether the work can be split across separate agents.",
        state=STATE,
        definitions=(
            ITEM,
            "The work on an item is the action asked for on it and the kind of result it should produce.",
            "Items get the same work when their actions and kinds of result match in meaning, even when the wording differs or a value, such as a target language, changes per item.",
        ),
        rules=(
            "One instruction that covers a group, or a fixed bundle of steps every item gets, asks for the same work on each item.",
            "Different actions or kinds of result for different items are not the same work.",
            "A request that names no item, or leaves some item without an action, does not ask for the same work on each item.",
            "A request with no task at all, such as an empty message, a greeting, thanks, or a sign-off, does not ask for the same work on each item.",
            "Judge only whether the work matches; whether items depend on each other is a separate check.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `request` ask for the same work on each item?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `request` asks for the same work on each item. The signs are one action that covers a group, the same action repeated per item, or one bundle of steps for every item, even when a value changes per item.",
        not_for="Different actions or kinds of result on different items, an item with no action, and no task at all belong to false.",
        easy=("Summarize each of these four reports in three bullet points.",),
        boundary=("Translate each message into the language written beside it.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `request` does not ask for the same work on each item. The signs are different actions or kinds of result per item, an item with no action, a broad instruction such as handle these, or no task at all.",
        not_for="Every item getting the same action and kind of result, even with a value that changes per item, belongs to true.",
        easy=("Summarize the memo, translate the notice, and fix the form.",),
        boundary=("Translate the first message and summarize the second.",),
    ))
    gap: str = "The request does not ask for the same work on each item; it gives different items different actions or results, or leaves some item without an action."


@dataclass(frozen=True)
class BulkWorkSeparateResultsQuestion(JevPreflightQuestion):
    """Does the request ask for a result for each item?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.BULK_WORK_SEPARATE_RESULTS
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether a user's request asks for a result for each item rather than one result about the group. It is one of several checks on whether the work can be split across separate agents.",
        state=STATE,
        definitions=(
            ITEM,
            "A result for an item can be produced from that item alone, such as its summary or its translation.",
            "A group result can only be produced by looking at all the items together, such as a ranking, a comparison, a merge, or the choice of the best item.",
        ),
        rules=(
            "A result for each item followed by a short overview of those results still asks for a result for each item.",
            "A request whose main output is a group result does not ask for a result for each item, even when it names every item.",
            "A request that names no item or asks for no output does not ask for a result for each item.",
            "A request with no task at all, such as an empty message, a greeting, thanks, or a sign-off, does not ask for a result for each item.",
            "Judge only the shape of the requested results; whether the work is the same for each item is a separate check.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `request` ask for a result for each item?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `request` asks for a result for each item. The signs are words such as each, every, or separately tied to an output that belongs to one item, possibly followed by a short overview.",
        not_for="One ranking, comparison, merge, or choice of the best item as the main output, and no task at all, belong to false.",
        easy=("Write a short summary of each of these five articles.",),
        boundary=("Summarize each of these five articles, then list the summaries together.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `request` does not ask for a result for each item. The signs are one ranking, comparison, merge, or choice of the best item as the main output, or no task at all.",
        not_for="An output that belongs to each item, even with a short overview at the end, belongs to true.",
        easy=("Rank these five articles from best to worst.",),
        boundary=("Combine these five articles into one summary.",),
    ))
    gap: str = "The request asks for one result about the items as a group, such as a ranking, a comparison, or a merge, rather than a result for each item."


@dataclass(frozen=True)
class BulkWorkIndependentItemsQuestion(JevPreflightQuestion):
    """Does the request describe work on each item that needs no other item's result?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.BULK_WORK_INDEPENDENT_ITEMS
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the work on each item can be done without the result of the work on another item. It is one of several checks on whether separate agents could work on the items at the same time.",
        state=STATE,
        definitions=(
            ITEM,
            "Work on an item needs another item's result when the request makes it use, follow from, or depend on what the work on another item produced.",
        ),
        rules=(
            "A fixed input every item uses, such as one rubric or one style guide, is not another item's result.",
            "Wording such as based on the result of, if the first one passes, or then apply it to shows that one item needs another item's result.",
            "A request that names no item, or leaves the link between items unclear, does not describe work that needs no other item's result.",
            "A request with no task at all, such as an empty message, a greeting, thanks, or a sign-off, does not describe work that needs no other item's result.",
            "Judge only whether one item needs another item's result; shared changes and order are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `request` describe work on each item that needs no other item's result?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `request` describes work on each item that needs no other item's result. The signs are work that uses only its own item and inputs every item shares, with no result carried from one item to another.",
        not_for="One item's result choosing, changing, or allowing another item's work, an unclear link, and no task at all belong to false.",
        easy=("Check each of these five tickets against this priority rubric.",),
        boundary=("Grade each of these essays with this rubric.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `request` describes work on some item that needs another item's result. The signs are wording that uses another item's result, a step allowed only if another item passes, an unclear link, or no task at all.",
        not_for="Work on each item that uses only that item and inputs every item shares belongs to true.",
        easy=("Use the first account's result to decide what to check in the second.",),
        boundary=("Grade each of these essays with a rubric you write from the first essay.",),
    ))
    gap: str = "The request makes the work on some item need the result of another item, or leaves unclear whether it does, so the items cannot be worked on at the same time."


@dataclass(frozen=True)
class BulkWorkSeparateChangesQuestion(JevPreflightQuestion):
    """Does the request keep the changes for each item inside that item?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.BULK_WORK_SEPARATE_CHANGES
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the work on each item changes only that item, because agents working at the same time must not change the same thing. It is one of several checks on whether the work can be split across separate agents.",
        state=STATE,
        definitions=(
            ITEM,
            "A change is any edit, write, update, or deletion; reading, reviewing, summarizing, and answering make no change.",
            "A shared target is one thing the work on two or more items would change, such as one output file or one setting.",
        ),
        rules=(
            "Work that makes no change, or changes only the item it is about, keeps the changes for each item inside that item.",
            "Work that makes two or more items change one shared target does not, even when each item's part is small.",
            "A request that names no item does not keep the changes for each item inside that item.",
            "A request with no task at all, such as an empty message, a greeting, thanks, or a sign-off, does not keep the changes for each item inside that item.",
            "Judge only what the work changes; whether items need each other's results is a separate check.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `request` keep the changes for each item inside that item?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `request` keeps the changes for each item inside that item. The signs are work that only reads, reviews, summarizes, or answers, or work that edits each item in its own place.",
        not_for="Two or more items changing one shared file, record, or setting, and no task at all, belong to false.",
        easy=("Review each of these four pull requests and list any problems.",),
        boundary=("Fix the typos in each of these three files.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `request` does not keep the changes for each item inside that item. The signs are two or more items whose work changes one shared file, record, or setting, or no task at all.",
        not_for="Work that makes no change, or changes each item only in its own place, belongs to true.",
        easy=("Add each of these four services to the one shared config file.",),
        boundary=("Fix the typos in each of these three files and log every fix in changelog.md.",),
    ))
    gap: str = "The request has the work on two or more items change the same file, record, or setting, so agents working at the same time could overwrite each other."


@dataclass(frozen=True)
class BulkWorkAnyOrderQuestion(JevPreflightQuestion):
    """Does the request let the items be worked on in any order?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.BULK_WORK_ANY_ORDER
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether a user's request lets its items be worked on in any order, because agents working at once finish in no fixed order. It is one of several checks on whether the work can be split across separate agents.",
        state=STATE,
        definitions=(
            ITEM,
            "A required order says some item must be done before another, such as one at a time; an order for showing the results is not an order for doing the work.",
        ),
        rules=(
            "Listing items in some order, or asking for the results in that order, still lets the items be worked on in any order.",
            "Saying to work on the items one at a time, in sequence, or one after another does not let them be worked on in any order.",
            "A request that names no item does not let the items be worked on in any order.",
            "A request with no task at all, such as an empty message, a greeting, thanks, or a sign-off, does not let the items be worked on in any order.",
            "Judge only whether the work has a required order; whether items need each other's results is a separate check.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `request` let the items be worked on in any order?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `request` lets the items be worked on in any order. The signs are no instruction about the order of the work, or an order only for showing the results.",
        not_for="An instruction to go one at a time, in sequence, or with some item first, and no task at all, belong to false.",
        easy=("Translate these four letters into Spanish.",),
        boundary=("Translate these four letters and show the translations in the order listed.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `request` does not let the items be worked on in any order. The signs are an instruction to go one at a time, in sequence, or with some item first, or no task at all.",
        not_for="No instruction about the order of the work, or an order only for showing the results, belongs to true.",
        easy=("Translate these four letters one at a time, starting with the oldest.",),
        boundary=("Translate these four letters in the order listed.",),
    ))
    gap: str = "The request requires the items to be worked on in a set order, such as one at a time, so they cannot be worked on at the same time."


@dataclass(frozen=True)
class BulkWorkSubstantialItemsQuestion(JevPreflightQuestion):
    """Does the request ask for substantial work on each item?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.BULK_WORK_SUBSTANTIAL_ITEMS
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether each item needs enough work to be worth its own agent, because starting an agent costs more than writing a short answer. It is one of several checks on whether the work should be split across separate agents.",
        state=STATE,
        definitions=(
            ITEM,
            "Substantial work on an item needs its own reading, writing, editing, or use of tools, such as reviewing a file; small work is covered by a short answer, such as one word or one fact.",
        ),
        rules=(
            "Work on short values, such as single words, numbers, or names, is small even when there are many of them.",
            "A request that names no item, or whose items need only small work, does not ask for substantial work on each item.",
            "A request with no task at all, such as an empty message, a greeting, thanks, or a sign-off, does not ask for substantial work on each item.",
            "Judge only the size of the work on each item; how many items there are is a separate check.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `request` ask for substantial work on each item?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `request` asks for substantial work on each item. The signs are items with their own content to read or change, or a request for research, a review, a rewrite, or a fix for each item.",
        not_for="Short values such as single words, numbers, or names that a short answer covers, and no task at all, belong to false.",
        easy=("Review each of these three pull requests for security problems.",),
        boundary=("Translate each of these three product descriptions into German.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `request` asks only for small work on each item. The signs are short values such as single words, numbers, or names, answers of one word or one fact, or no task at all.",
        not_for="Items with their own content to read or change, or research, a review, a rewrite, or a fix for each item, belong to true.",
        easy=("Give me the capitals of France, Spain, and Italy.",),
        boundary=("Translate each of these three product names into German.",),
    ))
    gap: str = "The request asks only for small work on each item, such as single words or facts, so separate agents would cost more than doing it in one pass."


BULK_WORK_QUESTIONS: tuple[JevPreflightQuestion, ...] = (
    BulkWorkMultipleItemsQuestion(),
    BulkWorkKnownItemsQuestion(),
    BulkWorkSameOperationQuestion(),
    BulkWorkSeparateResultsQuestion(),
    BulkWorkIndependentItemsQuestion(),
    BulkWorkSeparateChangesQuestion(),
    BulkWorkAnyOrderQuestion(),
    BulkWorkSubstantialItemsQuestion(),
)

__all__ = [
    "BULK_WORK_QUESTIONS",
    "BulkWorkAnyOrderQuestion",
    "BulkWorkIndependentItemsQuestion",
    "BulkWorkKnownItemsQuestion",
    "BulkWorkMultipleItemsQuestion",
    "BulkWorkSameOperationQuestion",
    "BulkWorkSeparateChangesQuestion",
    "BulkWorkSeparateResultsQuestion",
    "BulkWorkSubstantialItemsQuestion",
]
