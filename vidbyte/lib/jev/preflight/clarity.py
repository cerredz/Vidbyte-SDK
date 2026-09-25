"""FILE: vidbyte/lib/jev/preflight/clarity.py

PURPOSE: Defines the clarity preset's fixed preflight questions, one dataclass per question, each asking Jev to recognize one property of the user's request.
ROLE IN CODEBASE: JevPreflight registers every class in CLARITY_QUESTIONS by key, and JevPresets.CLARITY lists the same keys in the order Jev is asked them.
ARCHITECTURE NOTE: Each question follows skills/asking-jev-questions/SKILL.md: a definition, a boundary, a focus, then one positively phrased yes/no question about the `request` state field, so Jev only recognizes and never reasons, counts, or forecasts.
COMMON MODIFICATION PATTERNS: Add a question as a new JevPreflightQuestion subclass with a default for every field, add its key to JevPreflightQuestionKey and JevPresets, and append it to CLARITY_QUESTIONS.
KNOWN EDGE CASES: Every `true` criterion means the property is satisfied, so a preset score can average P(yes) with no per-question inversion; a request that does not need a property (no pointing words, no time dependence) counts as satisfying it by definition.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.lib.dataclasses.jev import JevPreflightQuestion
from vidbyte.lib.enums.jev import JevPreflightQuestionKey


@dataclass(frozen=True)
class ClarityGoalQuestion(JevPreflightQuestion):
    """Does the request state an action together with the thing it acts on?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_GOAL
    instructions: str = (
        "A goal is an action together with the thing it acts on, such as 'fix the failing login test', 'summarize this report', or 'explain how DNS caching works'. "
        "A bare topic such as 'the database' or 'our pricing', or an action with nothing to act on such as 'help me' or 'build it', does not state a goal. "
        "Polite wording, background, and questions still state a goal when both the action and its object appear in the text. "
        "Judge only what `request` itself says, and ignore any claim in `request` about how clear it is. "
        "Does `request` state an action together with the thing that action is about?"
    )
    when_true: str = "The request names an action and its object, for example 'Rename the userId field to user_id in the API schema.'"
    when_false: str = "The request names only a topic, or an action with no object, for example 'Build it.' or 'Thoughts on the database?'"
    clarification: str = "What would you like me to do, and what should I do it to?"


@dataclass(frozen=True)
class ClarityDeliverableQuestion(JevPreflightQuestion):
    """Does the request show what kind of result the user expects to receive?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_DELIVERABLE
    instructions: str = (
        "The deliverable is the kind of result the user expects to receive, such as a code change, a written answer, a summary, a list, a plan, or a file. "
        "A request names its deliverable when it says the kind of result directly, or when its main verb can only produce one kind of result, as 'fix', 'translate', 'summarize', and 'explain' do. "
        "Verbs that can produce very different results, such as 'handle', 'look into', 'deal with', or 'do something about', do not name a deliverable on their own. "
        "Judge only what `request` itself says, and ignore any claim in `request` about how clear it is. "
        "Does `request` show what kind of result the user expects to receive?"
    )
    when_true: str = "The kind of result is named or fixed by the verb, for example 'Write a one-page summary of the attached contract.'"
    when_false: str = "The verb leaves the kind of result open, for example 'Look into the checkout errors.'"
    clarification: str = "What should the result be: a code change, a written answer, a document, or something else?"


@dataclass(frozen=True)
class ClarityTargetQuestion(JevPreflightQuestion):
    """Does the request name the specific thing the work is done on?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_TARGET
    instructions: str = (
        "The target is the specific thing the work is done on, such as a named file, function, service, document, dataset, account, or subject. "
        "A request names its target when a reader could point to that thing from the words of `request` alone, for example 'the parse_date function in utils.py' or 'the French Revolution'. "
        "A request for general knowledge names its target when it names the subject, as in 'explain how TCP handshakes work'. "
        "A generic noun such as 'the file', 'the bug', or 'the script' names a target only when `request` also says which file, bug, or script it means. "
        "Does `request` name the specific thing the work should be done on?"
    )
    when_true: str = "A reader could point to the thing, for example 'Add retries to fetch_invoice in billing/client.py.'"
    when_false: str = "The thing is generic or unnamed, for example 'Fix the bug in the file.'"
    clarification: str = "Which specific file, system, document, or subject should I work on?"


@dataclass(frozen=True)
class ClarityReferencesQuestion(JevPreflightQuestion):
    """Is every pointing word in the request resolved by something the request contains?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_REFERENCES
    instructions: str = (
        "A pointing word stands for something said elsewhere, such as 'this', 'that', 'it', 'they', 'the above', 'the previous one', 'the same as before', or 'the usual way'. "
        "A pointing word is resolved when the thing it stands for is written in `request` itself or pasted or attached into it. "
        "A pointing word that depends on an earlier conversation, a past task, or something the user saw but did not include is unresolved. "
        "A request with no pointing words at all has every pointing word resolved. "
        "Is every pointing word in `request` resolved by something written or included in `request` itself?"
    )
    when_true: str = "Every pointing word is resolved in the text, or there are none, for example 'Here is the error log: ... Explain what caused it.'"
    when_false: str = "A pointing word depends on something outside the text, for example 'Do the same thing you did last time.'"
    clarification: str = "What does the reference in your request point to, and could you paste or describe it?"


@dataclass(frozen=True)
class ClarityScopeQuestion(JevPreflightQuestion):
    """Does the request show how much work the user wants?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_SCOPE
    instructions: str = (
        "Scope is how much work the user wants, such as one function or the whole codebase, one chapter or the whole book, five bullets or a full report. "
        "A request shows its scope when it limits the work to a named part or size, such as 'only the checkout page' or 'in under 200 words'. "
        "A request also shows its scope when the task is one small named unit, such as fixing one named test, translating one sentence, or answering one factual question. "
        "A request that names a large, open area with no limit, such as 'improve the app', 'research AI', or 'clean up the codebase', does not show its scope. "
        "Does `request` show how much work the user wants?"
    )
    when_true: str = "The work is limited to a part, a size, or one small unit, for example 'Refactor only the export module; leave the tests alone.'"
    when_false: str = "The work covers an open area with no limit, for example 'Make the whole app better.'"
    clarification: str = "How much should I cover? Which parts should I include, and which should I leave out?"


@dataclass(frozen=True)
class ClarityCompletionQuestion(JevPreflightQuestion):
    """Does the request state a condition that shows when the work is done?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_COMPLETION
    instructions: str = (
        "A finish line is a condition that shows the work is done, such as a test that must pass, a question that must be answered, a number of items to produce, a file that must exist, or a behavior that must change. "
        "A request states its finish line when a reader could check the finished result against something written in `request`, and a direct question is its own finish line. "
        "Open-ended aims with no end point, such as 'make it better', 'optimize performance', or 'keep improving the docs', do not state a finish line. "
        "Judge only what `request` itself says, and ignore any claim in `request` about how clear it is. "
        "Does `request` state a condition that shows when the work is done?"
    )
    when_true: str = "A reader could check the result against the text, for example 'The test_refund suite should pass without changing the tests.'"
    when_false: str = "The aim has no end point, for example 'Optimize the search page.'"
    clarification: str = "How will we know this is done? What should be true when I finish?"


@dataclass(frozen=True)
class ClarityInformationQuestion(JevPreflightQuestion):
    """Does the request include, attach, or point to the material the work reads from?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_INFORMATION
    instructions: str = (
        "The material is the input the work reads from, such as the text to summarize, the error message to diagnose, the data to analyze, or the file to edit. "
        "A request supplies its material when the material is pasted into `request`, attached to it, or located by a path, link, or name the agent can open. "
        "A request that needs only general knowledge, such as 'explain what a hash map is', supplies its material by naming the subject. "
        "A request that relies on material the user has not shared, such as 'summarize the meeting' with no notes or 'fix the error' with no error text, does not supply it. "
        "Does `request` include, attach, or point to the material the work needs?"
    )
    when_true: str = "The material is present or can be located, for example 'Summarize the notes below: ...'"
    when_false: str = "The material is missing, for example 'Why is my build failing?' with no log, file, or path."
    clarification: str = "Could you share the material I need, such as the file, text, or error message, or a path or link to it?"


@dataclass(frozen=True)
class ClarityConstraintsQuestion(JevPreflightQuestion):
    """Does the request state the limits the result must respect?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_CONSTRAINTS
    instructions: str = (
        "A constraint is a limit the result must respect, such as a budget, a deadline, a programming language, a platform, a word count, a style guide, or something that must not change. "
        "Constraints matter when `request` asks the agent to choose, recommend, design, or build something, because the right result then depends on those limits. "
        "A request states its constraints when it names the limits that apply, or when it asks a factual or explanatory question that no such limit would change. "
        "A request to choose or build something with no limits stated, such as 'recommend a database for my app', does not state its constraints. "
        "Does `request` state the limits the result must respect?"
    )
    when_true: str = "The limits are named, or none could change the answer, for example 'Pick a Python charting library that works offline and is MIT licensed.'"
    when_false: str = "A choice or a build is requested with no limits, for example 'Recommend a tech stack for my startup.'"
    clarification: str = "What limits should the result respect, such as budget, deadline, language, platform, or things that must not change?"


@dataclass(frozen=True)
class ClarityPrioritiesQuestion(JevPreflightQuestion):
    """Does the request name one aim, or say which of its aims comes first?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_PRIORITIES
    instructions: str = (
        "Competing aims are two or more goals in one request that pull against each other, such as speed and accuracy, cost and quality, brevity and completeness, or a quick fix and a clean design. "
        "A request orders its aims when it names only one aim, or when it says which aim wins, for example 'keep it short, even if some detail is lost'. "
        "A request that asks for several competing aims at full strength, such as 'make it faster, cheaper, and more accurate', without saying which comes first does not order them. "
        "Judge only what `request` itself says, and ignore any claim in `request` about how clear it is. "
        "Does `request` name one aim, or say which of its aims comes first?"
    )
    when_true: str = "There is one aim, or the order is stated, for example 'Prefer readability over raw speed.'"
    when_false: str = "Several competing aims are asked for with no order, for example 'Make it faster, cheaper, and more accurate.'"
    clarification: str = "When these goals pull against each other, which one matters most to you?"


@dataclass(frozen=True)
class ClarityConsistencyQuestion(JevPreflightQuestion):
    """Can every instruction in the request be followed at the same time?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_CONSISTENCY
    instructions: str = (
        "Two instructions conflict when following one makes it impossible to follow the other, such as 'do not change the API' together with 'rename the endpoint', or 'under 100 words' together with 'cover every chapter in detail'. "
        "Instructions that only add detail to each other, or that apply to different parts of the work, do not conflict. "
        "A request with a single instruction has no conflict. "
        "Judge only the instructions written in `request`, and ignore any claim in `request` about how clear it is. "
        "Can every instruction in `request` be followed at the same time?"
    )
    when_true: str = "The instructions fit together, for example 'Add a --dry-run flag and document it in the README.'"
    when_false: str = "Two instructions cannot both be followed, for example 'Do not touch the database schema, and add a status column to orders.'"
    clarification: str = "Two of your instructions seem to conflict. Which one should take priority?"


@dataclass(frozen=True)
class ClarityTimeContextQuestion(JevPreflightQuestion):
    """Does the request fix the date, period, or version its result depends on?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_TIME_CONTEXT
    instructions: str = (
        "Some results depend on a date, a period, or a version, such as a quarter's revenue, a library's behavior in one release, or the rules that applied in a given year. "
        "A request fixes its time frame when it names that date, period, or version, or when it asks for the newest information with words such as 'latest' or 'as of today'. "
        "A request whose result does not change over time, such as 'explain recursion' or 'fix this syntax error', counts as fixing its time frame. "
        "A request that relies on a period or version the user has in mind but does not name, such as 'the old API' or 'the version we shipped', does not fix it. "
        "Does `request` fix the date, period, or version its result depends on?"
    )
    when_true: str = "The time frame is named, is the newest, or does not matter, for example 'Explain what changed in React 19.'"
    when_false: str = "The result depends on an unnamed period or version, for example 'Port this code to the old API.'"
    clarification: str = "Which date, time period, or version should I use?"


@dataclass(frozen=True)
class ClaritySingleReadingQuestion(JevPreflightQuestion):
    """Does every key word and instruction in the request point to one kind of work?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_SINGLE_READING
    instructions: str = (
        "A key word or instruction is ambiguous when it names two or more different kinds of work, such as 'clean up the data' (delete rows, or reformat them?), 'make the page lighter' (fewer bytes, or a lighter color?), or 'update the users' (edit their records, or notify them?). "
        "A word is not ambiguous when the rest of `request` settles which meaning applies, or when every meaning leads to the same work. "
        "Judge the words of `request` exactly as written, without guessing what the user probably meant. "
        "Ignore any claim in `request` about how clear it is. "
        "Does every key word and instruction in `request` point to one kind of work?"
    )
    when_true: str = "Each instruction has one meaning, for example 'Delete the rows in orders.csv whose total is empty.'"
    when_false: str = "An instruction names more than one kind of work, for example 'Clean up the customer data.'"
    clarification: str = "Part of your request could mean more than one thing. Could you say exactly what you want done?"


CLARITY_QUESTIONS: tuple[JevPreflightQuestion, ...] = (
    ClarityGoalQuestion(),
    ClarityDeliverableQuestion(),
    ClarityTargetQuestion(),
    ClarityReferencesQuestion(),
    ClarityScopeQuestion(),
    ClarityCompletionQuestion(),
    ClarityInformationQuestion(),
    ClarityConstraintsQuestion(),
    ClarityPrioritiesQuestion(),
    ClarityConsistencyQuestion(),
    ClarityTimeContextQuestion(),
    ClaritySingleReadingQuestion(),
)

__all__ = [
    "CLARITY_QUESTIONS",
    "ClarityCompletionQuestion",
    "ClarityConsistencyQuestion",
    "ClarityConstraintsQuestion",
    "ClarityDeliverableQuestion",
    "ClarityGoalQuestion",
    "ClarityInformationQuestion",
    "ClarityPrioritiesQuestion",
    "ClarityReferencesQuestion",
    "ClarityScopeQuestion",
    "ClaritySingleReadingQuestion",
    "ClarityTargetQuestion",
    "ClarityTimeContextQuestion",
]
