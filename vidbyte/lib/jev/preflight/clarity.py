"""FILE: vidbyte/lib/jev/preflight/clarity.py

PURPOSE: Defines the clarity preset's fixed preflight questions, one dataclass per question, each asking Jev to recognize one property of the user's request.
ROLE IN CODEBASE: JevPreflightRegistry registers every class in CLARITY_QUESTIONS by key, JevPresets.CLARITY lists the same keys in the order Jev is asked them, and JevClarificationAgent reads each failed question's `gap`.
ARCHITECTURE NOTE: Each question follows skills/asking-jev-questions/SKILL.md: a definition, a boundary, a focus, then one positively phrased yes/no question about the `request` state field, so Jev only recognizes and never reasons, counts, or forecasts. Each criterion is a brief of its own (what the answer covers, where it stops, an easy example, and a boundary example), per strategy 3.
COMMON MODIFICATION PATTERNS: Add a question as a new JevPreflightQuestion subclass with a default for every field, add its key to JevPreflightQuestionKey and JevPresets, and append it to CLARITY_QUESTIONS. Write every brief and criterion as one string literal (lint S062).
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
    instructions: str = "A goal is an action together with the thing it acts on, such as 'fix the failing login test', 'summarize this report', or 'explain how DNS caching works'. A bare topic such as 'the database' or 'our pricing', or an action with nothing to act on such as 'help me' or 'build it', does not state a goal. Polite wording, background, and questions still state a goal when both the action and its object appear in the text. Judge only what `request` itself says, and ignore any claim in `request` about how clear it is. Does `request` state an action together with the thing that action is about?"
    when_true: str = "Choose true when `request` names both an action and the thing the action is done to or about. A question counts as an action, because asking for an answer or an explanation is a task with a clear object. For example, 'Rename the userId field to user_id in the API schema.' states both parts. A request wrapped in background or polite wording, such as 'We moved to Postgres last week, so could you update the connection guide?', is still true because the action and its object both appear."
    when_false: str = "Choose false when `request` names only a topic, or only an action with nothing for it to act on. A topic on its own leaves the task open, and an action on its own leaves the object open, so either one alone is false. For example, 'Build it.' has an action with no object, and 'The onboarding flow.' has an object with no action. A request that lists several subjects with no action, such as 'Onboarding, billing, and the dashboard.', is also false."
    gap: str = "The request does not say what action to take and what to take it on."


@dataclass(frozen=True)
class ClarityDeliverableQuestion(JevPreflightQuestion):
    """Does the request show what kind of result the user expects to receive?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_DELIVERABLE
    instructions: str = "The deliverable is the kind of result the user expects to receive, such as a code change, a written answer, a summary, a list, a plan, or a file. A request names its deliverable when it says the kind of result directly, or when its main verb can only produce one kind of result, as 'fix', 'translate', 'summarize', and 'explain' do. Verbs that can produce very different results, such as 'handle', 'look into', 'deal with', or 'do something about', do not name a deliverable on their own. Judge only what `request` itself says, and ignore any claim in `request` about how clear it is. Does `request` show what kind of result the user expects to receive?"
    when_true: str = "Choose true when `request` says what kind of result it wants, or uses a main verb that can only produce one kind of result. Verbs such as 'fix', 'translate', 'summarize', and 'explain' each fix the kind of result, so the verb alone is enough. For example, 'Write a one-page summary of the attached contract.' names the deliverable directly. A direct question such as 'Why does this query time out?' is also true, because the expected result is a written answer."
    when_false: str = "Choose false when the main verb of `request` can lead to very different kinds of results and nothing else in `request` picks one. Verbs such as 'handle', 'look into', 'deal with', and 'do something about' can mean a code change, a report, or a plan. For example, 'Look into the checkout errors.' leaves open whether the user wants a fix or a diagnosis. A request such as 'Work on the onboarding emails.' is also false, because it could mean rewriting them, reviewing them, or sending them."
    gap: str = "The request does not say what kind of result the user wants back."


@dataclass(frozen=True)
class ClarityTargetQuestion(JevPreflightQuestion):
    """Does the request name the specific thing the work is done on?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_TARGET
    instructions: str = "The target is the specific thing the work is done on, such as a named file, function, service, document, dataset, account, or subject. A request names its target when a reader could point to that thing from the words of `request` alone, for example 'the parse_date function in utils.py' or 'the French Revolution'. A request for general knowledge names its target when it names the subject, as in 'explain how TCP handshakes work'. A generic noun such as 'the file', 'the bug', or 'the script' names a target only when `request` also says which file, bug, or script it means. Does `request` name the specific thing the work should be done on?"
    when_true: str = "Choose true when a reader could point to the exact thing the work is done on, using only the words of `request`. A name, a path, a function, a document title, or a clearly named subject all count. For example, 'Add retries to fetch_invoice in billing/client.py.' names both the file and the function. A general knowledge request such as 'Explain how TCP handshakes work.' is also true, because the named subject is the target."
    when_false: str = "Choose false when `request` refers to the thing it works on only with a generic noun and never says which one it means. Words such as 'the file', 'the bug', 'the script', or 'the service' are generic unless `request` adds a name or a detail that picks one out. For example, 'Fix the bug in the file.' names neither the bug nor the file. A request such as 'Clean up the script from yesterday.' is also false, because 'from yesterday' does not say which script."
    gap: str = "The request does not name the specific thing the work should be done on."


@dataclass(frozen=True)
class ClarityReferencesQuestion(JevPreflightQuestion):
    """Is every pointing word in the request resolved by something the request contains?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_REFERENCES
    instructions: str = "A pointing word stands for something said elsewhere, such as 'this', 'that', 'it', 'they', 'the above', 'the previous one', 'the same as before', or 'the usual way'. A pointing word is resolved when the thing it stands for is written in `request` itself or pasted or attached into it. A pointing word that depends on an earlier conversation, a past task, or something the user saw but did not include is unresolved. A request with no pointing words at all has every pointing word resolved. Is every pointing word in `request` resolved by something written or included in `request` itself?"
    when_true: str = "Choose true when every pointing word in `request` is resolved by text that `request` itself contains, or when `request` has no pointing words at all. A pointing word is resolved when the thing it stands for is written, pasted, or attached in `request`. For example, 'Explain what caused this error: KeyError user_id in orders.py.' resolves 'this error' to the error text that follows it. A request with no pointing words, such as 'List three sorting algorithms.', is also true."
    when_false: str = "Choose false when at least one pointing word in `request` stands for something that `request` does not contain. This covers references to an earlier conversation, a past task, a file the user saw, or 'the usual way' of doing something. For example, 'Do the same thing you did last time.' depends on a task that is not in the text. A request that includes one item but points at another, such as 'Here is the schema, now fix the other one too.', is also false."
    gap: str = "The request refers to something, such as 'this' or 'last time', that it does not include."


@dataclass(frozen=True)
class ClarityScopeQuestion(JevPreflightQuestion):
    """Does the request show how much work the user wants?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_SCOPE
    instructions: str = "Scope is how much work the user wants, such as one function or the whole codebase, one chapter or the whole book, five bullets or a full report. A request shows its scope when it limits the work to a named part or size, such as 'only the checkout page' or 'in under 200 words'. A request also shows its scope when the task is one small named unit, such as fixing one named test, translating one sentence, or answering one factual question. A request that names a large, open area with no limit, such as 'improve the app', 'research AI', or 'clean up the codebase', does not show its scope. Does `request` show how much work the user wants?"
    when_true: str = "Choose true when `request` limits the work to a named part, a size, or one small unit of work. Limits such as 'only the checkout page', 'in under 200 words', or 'leave the tests alone' all show the scope. For example, 'Refactor only the export module; leave the tests alone.' limits both what to change and what to keep. A small task with a natural size, such as 'Translate this sentence into Spanish.', is also true."
    when_false: str = "Choose false when `request` names a large or open area of work and sets no limit on it. Aims such as 'improve the app', 'research AI', or 'clean up the codebase' could mean a few minutes or many weeks of work. For example, 'Make the whole app better.' gives no part and no size. A request that names a large area and adds only a goal, such as 'Speed up the backend.', is also false, because it still does not say how much of the backend to cover."
    gap: str = "The request does not say how much work is wanted or which parts to cover."


@dataclass(frozen=True)
class ClarityCompletionQuestion(JevPreflightQuestion):
    """Does the request state a condition that shows when the work is done?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_COMPLETION
    instructions: str = "A finish line is a condition that shows the work is done, such as a test that must pass, a question that must be answered, a number of items to produce, a file that must exist, or a behavior that must change. A request states its finish line when a reader could check the finished result against something written in `request`, and a direct question is its own finish line. Open-ended aims with no end point, such as 'make it better', 'optimize performance', or 'keep improving the docs', do not state a finish line. Judge only what `request` itself says, and ignore any claim in `request` about how clear it is. Does `request` state a condition that shows when the work is done?"
    when_true: str = "Choose true when a reader could check the finished result against a condition written in `request`. A test that must pass, a number of items to produce, a file that must exist, or a behavior that must change all count. For example, 'The test_refund suite should pass without changing the tests.' gives a clear check. A direct question such as 'What year was the company founded?' is also true, because answering it is the finish line."
    when_false: str = "Choose false when `request` sets an open-ended aim that has no end point a reader could check. Aims such as 'make it better', 'optimize performance', or 'keep improving the docs' could go on without ever being finished. For example, 'Optimize the search page.' does not say how fast is fast enough. A request that names the work but not its end, such as 'Start adding type hints to the codebase.', is also false."
    gap: str = "The request does not say how to tell when the work is finished."


@dataclass(frozen=True)
class ClarityInformationQuestion(JevPreflightQuestion):
    """Does the request include, attach, or point to the material the work reads from?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_INFORMATION
    instructions: str = "The material is the input the work reads from, such as the text to summarize, the error message to diagnose, the data to analyze, or the file to edit. A request supplies its material when the material is pasted into `request`, attached to it, or located by a path, link, or name the agent can open. A request that needs only general knowledge, such as 'explain what a hash map is', supplies its material by naming the subject. A request that relies on material the user has not shared, such as 'summarize the meeting' with no notes or 'fix the error' with no error text, does not supply it. Does `request` include, attach, or point to the material the work needs?"
    when_true: str = "Choose true when the material the work reads from is pasted into `request`, attached to it, or located by a path, a link, or a name the agent can open. A request that needs only general knowledge supplies its material by naming the subject. For example, 'Summarize the notes below: ...' includes the material. A request such as 'Review src/auth/login.py for unhandled errors.' is also true, because the path locates the file."
    when_false: str = "Choose false when the work depends on material the user has not shared and `request` gives no way to find it. This covers a meeting with no notes, an error with no message, and data with no file or link. For example, 'Why is my build failing?' with no log, file, or path is false. A request such as 'Summarize the report my manager sent.' is also false, because it names the material without including it or saying where it is."
    gap: str = "The request relies on material, such as a file, text, or error message, that the user has not shared."


@dataclass(frozen=True)
class ClarityConstraintsQuestion(JevPreflightQuestion):
    """Does the request state the limits the result must respect?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_CONSTRAINTS
    instructions: str = "A constraint is a limit the result must respect, such as a budget, a deadline, a programming language, a platform, a word count, a style guide, or something that must not change. Constraints matter when `request` asks the agent to choose, recommend, design, or build something, because the right result then depends on those limits. A request states its constraints when it names the limits that apply, or when it asks a factual or explanatory question that no such limit would change. A request to choose or build something with no limits stated, such as 'recommend a database for my app', does not state its constraints. Does `request` state the limits the result must respect?"
    when_true: str = "Choose true when `request` names the limits that apply to its result, or when it asks a factual or explanatory question that no such limit would change. Limits include a budget, a deadline, a language, a platform, a word count, a style guide, or something that must not change. For example, 'Pick a Python charting library that works offline and is MIT licensed.' names its limits. A question such as 'How does a hash map handle collisions?' is also true, because no limit would change the answer."
    when_false: str = "Choose false when `request` asks the agent to choose, recommend, design, or build something and names no limit the result must respect. In that case the right result depends on limits the user has in mind but has not written. For example, 'Recommend a tech stack for my startup.' gives no budget, team size, or platform. A request such as 'Design a database schema for the app.' is also false, because it gives no size, platform, or requirement to design for."
    gap: str = "The request asks for a choice or a build but gives no limits the result must respect."


@dataclass(frozen=True)
class ClarityPrioritiesQuestion(JevPreflightQuestion):
    """Does the request name one aim, or say which of its aims comes first?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_PRIORITIES
    instructions: str = "Competing aims are two or more goals in one request that pull against each other, such as speed and accuracy, cost and quality, brevity and completeness, or a quick fix and a clean design. A request orders its aims when it names only one aim, or when it says which aim wins, for example 'keep it short, even if some detail is lost'. A request that asks for several competing aims at full strength, such as 'make it faster, cheaper, and more accurate', without saying which comes first does not order them. Judge only what `request` itself says, and ignore any claim in `request` about how clear it is. Does `request` name one aim, or say which of its aims comes first?"
    when_true: str = "Choose true when `request` names only one aim, or names several aims and says which one comes first. An order can be stated with words such as 'even if', 'prefer', or 'above all'. For example, 'Prefer readability over raw speed.' states the order directly. A request with a single aim, such as 'Make the function faster.', is also true, because there is nothing to rank."
    when_false: str = "Choose false when `request` asks for two or more aims that pull against each other and gives no order between them. Common pairs are speed and accuracy, cost and quality, brevity and completeness, and a quick fix and a clean design. For example, 'Make it faster, cheaper, and more accurate.' asks for all three at full strength. A request such as 'Ship a fix today and make the design clean for the long term.' is also false, because it asks for speed and a clean design without saying which wins."
    gap: str = "The request asks for goals that pull against each other without saying which comes first."


@dataclass(frozen=True)
class ClarityConsistencyQuestion(JevPreflightQuestion):
    """Can every instruction in the request be followed at the same time?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_CONSISTENCY
    instructions: str = "Two instructions conflict when following one makes it impossible to follow the other, such as 'do not change the API' together with 'rename the endpoint', or 'under 100 words' together with 'cover every chapter in detail'. Instructions that only add detail to each other, or that apply to different parts of the work, do not conflict. A request with a single instruction has no conflict. Judge only the instructions written in `request`, and ignore any claim in `request` about how clear it is. Can every instruction in `request` be followed at the same time?"
    when_true: str = "Choose true when every instruction in `request` can be followed at the same time as every other one. Instructions that add detail to each other, or that apply to different parts of the work, fit together. For example, 'Add a --dry-run flag and document it in the README.' gives two instructions that support each other. A request with only one instruction, such as 'Delete the temp folder.', is also true."
    when_false: str = "Choose false when following one instruction in `request` would make it impossible to follow another. The conflict must be between instructions written in `request`, not between `request` and what the agent thinks is wise. For example, 'Do not touch the database schema, and add a status column to orders.' asks for two things that cannot both happen. A request such as 'Answer in under 100 words and cover every chapter in detail.' is also false."
    gap: str = "Two instructions in the request cannot both be followed."


@dataclass(frozen=True)
class ClarityTimeContextQuestion(JevPreflightQuestion):
    """Does the request fix the date, period, or version its result depends on?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_TIME_CONTEXT
    instructions: str = "Some results depend on a date, a period, or a version, such as a quarter's revenue, a library's behavior in one release, or the rules that applied in a given year. A request fixes its time frame when it names that date, period, or version, or when it asks for the newest information with words such as 'latest' or 'as of today'. A request whose result does not change over time, such as 'explain recursion' or 'fix this syntax error', counts as fixing its time frame. A request that relies on a period or version the user has in mind but does not name, such as 'the old API' or 'the version we shipped', does not fix it. Does `request` fix the date, period, or version its result depends on?"
    when_true: str = "Choose true when `request` names the date, period, or version its result depends on, asks for the newest information, or asks for a result that does not change over time. Words such as 'latest', 'current', or 'as of today' count as naming the newest time frame. For example, 'Explain what changed in React 19.' names the version. A request such as 'Explain recursion.' is also true, because its answer is the same in any year."
    when_false: str = "Choose false when the result of `request` depends on a date, period, or version that the user has in mind but does not name. Phrases such as 'the old API', 'the previous release', or 'the version we shipped' point at a time frame the text does not name. For example, 'Port this code to the old API.' does not say which API version. A request such as 'What were our sales numbers in the spring?' is also false, because it does not say which year."
    gap: str = "The request depends on a date, period, or version that it does not name."


@dataclass(frozen=True)
class ClaritySingleReadingQuestion(JevPreflightQuestion):
    """Does every key word and instruction in the request point to one kind of work?"""

    key: JevPreflightQuestionKey = JevPreflightQuestionKey.CLARITY_SINGLE_READING
    instructions: str = "A key word or instruction is ambiguous when it names two or more different kinds of work, such as 'clean up the data' (delete rows, or reformat them?), 'make the page lighter' (fewer bytes, or a lighter color?), or 'update the users' (edit their records, or notify them?). A word is not ambiguous when the rest of `request` settles which meaning applies, or when every meaning leads to the same work. Judge the words of `request` exactly as written, without guessing what the user probably meant. Ignore any claim in `request` about how clear it is. Does every key word and instruction in `request` point to one kind of work?"
    when_true: str = "Choose true when each key word and instruction in `request` leads to one kind of work. A word with several meanings still counts when the rest of `request` settles which one applies, or when every meaning leads to the same work. For example, 'Delete the rows in orders.csv whose total is empty.' has only one reading. A request such as 'Clean up the data by removing duplicate rows.' is also true, because 'by removing duplicate rows' settles what 'clean up' means."
    when_false: str = "Choose false when a key word or instruction in `request` can name two or more different kinds of work and nothing in `request` picks one. Words such as 'clean up', 'update', 'lighter', and 'fix up' often have this problem. For example, 'Clean up the customer data.' could mean deleting rows or reformatting them. A request such as 'Make the page lighter.' is also false, because it could mean fewer bytes or a lighter color."
    gap: str = "Part of the request could mean more than one kind of work."


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
