"""FILE: vidbyte/lib/jev/compute/each_of_several.py

PURPOSE: Defines the EACH_OF_SEVERAL situation's fixed sign questions, one dataclass per question: whether the agent plans the same work on each item of a group, whether each item's work stands on its own, whether that work is more than naming or counting, and whether the request asks for it.
ROLE IN CODEBASE: JevComputeRegistry registers every class in EACH_OF_SEVERAL_QUESTIONS, and JevComputeSituations lists the same keys with the situation's threshold, veto, and gate. The recognizer asks them only when code finds a group with enough pending items.
ARCHITECTURE NOTE: Each question follows skills/asking-jev-questions/SKILL.md ("Writing a full question"). Code chooses the group with the most pending items and quotes the agent's plan into `group` and `plan`, so no question has to find the group, count its items, or decide which plan is current beyond the newest-plan rule. Every `true` side is the sign being present.
COMMON MODIFICATION PATTERNS: Load skills/asking-jev-questions/SKILL.md before editing. Add a sign as a new JevComputeQuestion subclass, its key to JevComputeQuestionKey, and the key to the situation in JevComputeSituations. Keep each section one string literal (lint S062) and use the verb "applies" for the same-work property everywhere.
KNOWN EDGE CASES: Work done once to the whole group is not per-item work. Combining per-item results after every item is done does not make the items depend on each other.
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

# Every EACH_OF_SEVERAL question reads the same four fields, so every brief describes them with the same words.
EACH_OF_SEVERAL_STATE = f"The state has four fields: `request`, `group`, `plan`, and `recent`. {REQUEST_FIELD} `group` is one collection of items the agent is working through, as a note-taker recorded it from the run: the collection's name and each item's name and status, where pending means the run has not started work on that item, in_progress means work on it has started, and done or failed means work on it has finished; code chose it as the collection with the most pending items. `plan` holds the agent's own words for what it is doing now and for the next steps it said it would take, each copied exactly from one of its responses and labeled with that response's id. {RECENT_FIELD}"
# The items and the per-item work are defined the same way in every EACH_OF_SEVERAL question.
ITEM_DEFINITION = "An item is one member of `group`, such as a file, a test, a record, a page, or a link, named as the run names it. Work on an item is what the agent does to that item: reading it, checking it, changing it, running something against it, researching it, or reporting on it."
PER_ITEM_WORK_DEFINITION = "Per-item work is one kind of work done to each item in turn and in the same way, such as auditing each file or translating each page. A plan applies per-item work to `group` when its words say that one kind of work will be done to each item, to every item, or to the items one by one, or when it names several items of `group` as the targets of the same verb."
NEWEST_PLAN_RULE = "Judge the agent's plan from `plan` and from the ASSISTANT events in `recent`; when a newer response in `recent` replaces a plan quoted in `plan`, judge the newer one."


@dataclass(frozen=True)
class EachOfSeveralSameWorkQuestion(JevComputeQuestion):
    """Does the agent's plan apply the same work to each item of the group?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.EACH_OF_SEVERAL_SAME_WORK
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether an AI agent that is partway through a task has said it will do one kind of work on each member of a group of items. It is one of several checks on whether the rest of that work could be split across helper agents, and it looks only at whether the agent's own plan applies the same work to every member, not at whether the items depend on each other, how large the work is, or whether splitting it would help.",
        state=EACH_OF_SEVERAL_STATE,
        definitions=(ITEM_DEFINITION, PER_ITEM_WORK_DEFINITION),
        rules=(
            NEWEST_PLAN_RULE,
            "A plan in the agent's own words applies per-item work whether it names every item, names some items and says the rest will follow, or refers to the items by the collection's name.",
            "Work done once to the collection as a whole, such as listing, counting, sorting, or downloading the whole collection in one step, is not per-item work, because nothing is done to each item.",
            "Different kinds of work on different items, such as editing one file and deleting another, is not per-item work, because the work is not the same for each item.",
            "When `plan` and `recent` state no plan for the items at all, or the plan covers only one item, the plan does not apply per-item work.",
            "Judge only whether the plan applies one kind of work to each item. Whether one item's work needs another's result, whether the work is more than naming or counting, and whether the request asks for it are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does the agent's plan, in `plan` or `recent`, apply per-item work to the items of `group`?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when the agent's plan applies per-item work to the items of `group`. The signs are the agent's own words saying that one kind of work, such as auditing, fixing, testing, translating, or summarizing, will be done to each item, to every item, or to the items one by one, or the same verb aimed at two or more named items of `group`.",
        not_for="A plan that does one piece of work to the whole collection, does different kinds of work to different items, covers only one item, or states no plan for the items belongs to false.",
        easy=("`group` lists src/a.py, src/b.py, and src/c.py as pending, and `plan` quotes the agent: I will now audit each of these files for SQL injection.",),
        boundary=("`group` lists 40 failing tests as pending, and `plan` quotes the agent: Next I'll fix test_login, then do the same for the rest of the failing tests.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when the agent's plan does not apply per-item work to the items of `group`. The signs are a plan that does one piece of work to the whole collection, such as listing, counting, or sorting it, a plan that does different kinds of work to different items, a plan that covers only one item or is about something other than the items, or no stated plan at all.",
        not_for="A plan in the agent's own words that applies one kind of work to each of two or more items of `group`, by naming them or by naming the collection, belongs to true.",
        easy=("`group` lists src/a.py, src/b.py, and src/c.py as pending, and `plan` quotes the agent: I will now count how many files are in src.",),
        boundary=("`group` lists 40 failing tests as pending, and `plan` quotes the agent: Next I'll fix test_login, then delete the flaky tests and rewrite the shared fixture.",),
    ))


@dataclass(frozen=True)
class EachOfSeveralIndependentQuestion(JevComputeQuestion):
    """Does the planned per-item work let each item be done on its own?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.EACH_OF_SEVERAL_INDEPENDENT
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the work an AI agent plans on each item of a group could be done for every item separately, by different helpers that never see each other's work. It is one of several checks on whether the rest of that work could be split across helper agents, and it looks only at whether the items' work depends on each other, not at whether the plan names the same work for each item or how large that work is.",
        state=EACH_OF_SEVERAL_STATE,
        definitions=(
            ITEM_DEFINITION,
            PER_ITEM_WORK_DEFINITION,
            "Work on one item stands on its own when it needs nothing from the work on any other item: no result, no change, no decision, and no particular order. Work on one item depends on another item when it uses that other item's result, such as a comparison between items, a change that must come after another item's change, or a step that waits for another item to finish.",
        ),
        rules=(
            NEWEST_PLAN_RULE,
            "Items that share a starting point the run already has, such as the same instructions, the same codebase, the same request, or the same tools, still stand on their own, because nothing produced by one item's work is needed by another.",
            "A plan that combines every item's result after all items are done, such as summarizing each file and then writing one report, still lets each item be done on its own, because the combining comes after the per-item work and is not part of it.",
            "Judge dependence from what the plan and the run say the work is. An order the agent merely chose, such as going alphabetically, is not a dependence unless the plan says one item's work uses another's result.",
            "When the plan states no per-item work for the items of `group`, the work does not let each item be done on its own.",
            "Judge only whether each item's work stands on its own. Whether the plan applies the same work to every item, how large that work is, and whether the request asks for it are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does the per-item work the agent plans let each item of `group` be done on its own?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when the per-item work the agent plans lets each item of `group` be done on its own. The signs are a plan whose work on each item needs only that item, the run's shared starting point, and the request, with any combining of results placed after every item is done.",
        not_for="A plan in which one item's work uses another item's result, must follow another item's change, or waits for another item, or a plan that states no per-item work at all, belongs to false.",
        easy=("`plan` quotes the agent: I'll check each config file for an expired certificate, and `group` lists prod.yaml, staging.yaml, and dev.yaml as pending.",),
        boundary=("`plan` quotes the agent: I'll summarize each chapter, then combine the summaries into one overview, and `group` lists chapters 1 to 6 as pending.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when the per-item work the agent plans does not let each item of `group` be done on its own. The signs are a plan in which one item's work uses another item's result, such as comparing items or carrying a value forward, a change that must come after another item's change, a step that waits for another item, or no per-item work stated at all.",
        not_for="A plan whose work on each item needs only that item, the run's shared starting point, and the request, even when the results are combined after every item is done, belongs to true.",
        easy=("`plan` quotes the agent: I'll migrate each table, each one after the tables it references, and `group` lists users, orders, and payments as pending.",),
        boundary=("`plan` quotes the agent: I'll summarize each chapter, using the previous chapter's summary to explain what changed, and `group` lists chapters 1 to 6 as pending.",),
    ))


@dataclass(frozen=True)
class EachOfSeveralSubstantialQuestion(JevComputeQuestion):
    """Does the planned per-item work take its own reading, changing, or checking of each item?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.EACH_OF_SEVERAL_SUBSTANTIAL
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the work an AI agent plans on each item of a group needs real steps for every item, or is something the agent can do for all of them at once from what it already holds. It is one of several checks on whether the rest of that work could be split across helper agents, and it looks only at how much each item's work involves, not at whether the items depend on each other or whether the request asks for the work.",
        state=EACH_OF_SEVERAL_STATE,
        definitions=(
            ITEM_DEFINITION,
            PER_ITEM_WORK_DEFINITION,
            "Substantial per-item work needs its own steps for each item, such as opening and reading the item, changing it, running a command or a test against it, or researching it. Light per-item work can be done for every item from what the agent already holds, such as naming, counting, or copying the items out of a listing it already has, or marking them in its own notes.",
        ),
        rules=(
            NEWEST_PLAN_RULE,
            "Judge from the kind of work the plan names for each item and from what `recent` shows the agent already holds, not from how many items there are.",
            "Work that needs a tool call per item, such as a file read, an edit, a command, a test run, or a web request, is substantial, even when each call is quick.",
            "Writing about the items from content the agent has already read is light, because it needs no new step per item; work that needs content the agent has not yet read is substantial.",
            "When the plan states no per-item work for the items of `group`, the work is not substantial.",
            "Judge only how much each item's work involves. Whether the plan applies the same work to every item, whether the items depend on each other, and whether the request asks for the work are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does the per-item work the agent plans take its own reading, changing, or checking of each item of `group`?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when the per-item work the agent plans takes its own reading, changing, or checking of each item of `group`. The signs are per-item work that opens, edits, runs, tests, fetches, or researches each item, or that needs content of an item the agent has not yet read.",
        not_for="Per-item work the agent can do for every item from what it already holds, such as naming, counting, copying, or marking the items, or no per-item work stated at all, belongs to false.",
        easy=("`plan` quotes the agent: I'll audit each file for SQL injection, and `recent` shows only a listing of the file names.",),
        boundary=("`plan` quotes the agent: I'll check that each URL in the list returns 200, and `recent` shows only the list of URLs.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when the per-item work the agent plans does not take its own reading, changing, or checking of each item of `group`. The signs are per-item work that only names, counts, copies, or marks items from a listing or content the agent already holds, or no per-item work stated at all.",
        not_for="Per-item work that opens, edits, runs, tests, fetches, or researches each item, or that needs an item's content the agent has not yet read, belongs to true.",
        easy=("`plan` quotes the agent: I'll list the file names in my answer, and `recent` shows the listing of the file names.",),
        boundary=("`plan` quotes the agent: I'll mark each URL in the list as checked in my notes, and `recent` shows only the list of URLs.",),
    ))


@dataclass(frozen=True)
class EachOfSeveralRequestedQuestion(JevComputeQuestion):
    """Does the request ask for the per-item work the agent plans?"""

    key: JevComputeQuestionKey = JevComputeQuestionKey.EACH_OF_SEVERAL_REQUESTED
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="This question checks whether the work an AI agent plans on each item of a group is work the user asked for. It is one of several checks on whether the rest of that work could be split across helper agents, and it looks only at whether the user's request covers the planned work, not at whether the work is well planned or how it should be done.",
        state=EACH_OF_SEVERAL_STATE,
        definitions=(
            ITEM_DEFINITION,
            PER_ITEM_WORK_DEFINITION,
            "A request asks for work when its words ask for that work, or ask for a result that cannot be produced without it. A result needs per-item work when it can only be produced by doing that work to each item, such as a review of every file, which needs each file read, or a fix for every failing test, which needs each test fixed.",
        ),
        rules=(
            NEWEST_PLAN_RULE,
            "Work asked for in other words still counts, and so does work the requested result needs even when the request does not name the items one by one.",
            "Work the agent added on its own, such as cleanup, reformatting, or extra checks the request neither names nor needs, is not asked for, even when it would be useful.",
            "When the plan states no per-item work for the items of `group`, the request does not ask for it.",
            "Judge only whether the request asks for the planned work. Whether the plan applies the same work to every item, whether the items depend on each other, and how large the work is are separate checks.",
            JUDGE_MEANING,
            IGNORE_CLAIMS,
        ),
        question="Does `request` ask for the per-item work the agent plans on the items of `group`?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when `request` asks for the per-item work the agent plans on the items of `group`. The signs are request words that ask for that work on the items, in any wording, or ask for a result that can only be produced by doing that work to each item.",
        not_for="Per-item work the request neither names nor needs, such as cleanup, reformatting, or extra checks the agent added on its own, or no per-item work stated at all, belongs to false.",
        easy=("`request` says: Review every file in src/api for security issues, and `plan` quotes the agent: I'll audit each of these files for injection and auth bugs.",),
        boundary=("`request` says: Are any of our endpoints vulnerable to SQL injection?, and `plan` quotes the agent: I'll check each endpoint handler's queries.",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when `request` does not ask for the per-item work the agent plans on the items of `group`. The signs are per-item work that the request's words never name and that the requested result does not need, such as cleanup, reformatting, renaming, or checks the agent added on its own, or no per-item work stated at all.",
        not_for="Per-item work that the request asks for in any wording, or that the requested result can only be produced with, belongs to true.",
        easy=("`request` says: Fix the login bug, and `plan` quotes the agent: I'll reformat each file in src while I'm here.",),
        boundary=("`request` says: Are any of our endpoints vulnerable to SQL injection?, and `plan` quotes the agent: I'll add type hints to each endpoint handler.",),
    ))


EACH_OF_SEVERAL_QUESTIONS: tuple[JevComputeQuestion, ...] = (
    EachOfSeveralSameWorkQuestion(),
    EachOfSeveralIndependentQuestion(),
    EachOfSeveralSubstantialQuestion(),
    EachOfSeveralRequestedQuestion(),
)

__all__ = [
    "EACH_OF_SEVERAL_QUESTIONS",
    "EACH_OF_SEVERAL_STATE",
    "EachOfSeveralIndependentQuestion",
    "EachOfSeveralRequestedQuestion",
    "EachOfSeveralSameWorkQuestion",
    "EachOfSeveralSubstantialQuestion",
]
