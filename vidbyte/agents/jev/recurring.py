"""FILE: vidbyte/agents/jev/recurring.py

PURPOSE: Defines the fixed Noul questions of JevAgent's recurring preflight preset.
ROLE IN CODEBASE: presets.py registers RECURRING_QUESTIONS under JevPreflightPreset.RECURRING; JevRuntime sends them in the single preflight request.
ARCHITECTURE NOTE: Every question is built from the same five parts (definition, markers, boundary, focus, question) and one true/false rubric, so no question can drift from the house structure in skills/asking-jev-questions/SKILL.md.
COMMON MODIFICATION PATTERNS: Add one _RecurringText entry; keep `true` meaning "supports reuse" because the preset score is the mean true probability.
KNOWN EDGE CASES: Questions name the state field `request`, which JevRuntime always sends; the question key itself is never shown to Jev.
RELATED DOCS: docs/design/jev-preflight-recurring.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.lib.constants.jev import JEV_NOUL_FALSE, JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import JevOption, JevQuestion
from vidbyte.lib.enums.jev import JevQuestionType

RECURRING_QUESTION_PREFIX = "recurring"


@dataclass(frozen=True, slots=True)
class _RecurringText:
    """The five instruction parts and the true/false rubric of one recurring question."""

    key: str
    definition: str
    markers: str
    boundary: str
    focus: str
    question: str
    true_what: str
    true_examples: tuple[str, str]
    false_what: str
    false_examples: tuple[str, str]

    def to_jev_question(self) -> JevQuestion:
        # @intent one-shape-for-every-recurring-question
        # Joining fixed parts in a fixed order makes the definition-first, question-last structure structural rather than a style convention.
        instructions = " ".join((self.definition, self.markers, self.boundary, self.focus, self.question))
        return JevQuestion(
            name=f"{RECURRING_QUESTION_PREFIX}.{self.key}",
            question_type=JevQuestionType.NOUL,
            instructions=instructions,
            options=(
                JevOption(name=JEV_NOUL_TRUE, description={"what": self.true_what, "examples": list(self.true_examples)}),
                JevOption(name=JEV_NOUL_FALSE, description={"what": self.false_what, "examples": list(self.false_examples)}),
            ),
        )


_TEXTS = (
    _RecurringText(
        key="subject_changes",
        definition="A subject changes over time when the facts, values, or situation the work is about will be different next week or next month, so a result produced today goes out of date.",
        markers="This covers prices and markets, metrics and usage numbers, news and announcements, the state of a codebase, a project, or a queue of work, rankings, availability, and anyone's current status.",
        boundary="Settled subjects do not change over time: historical events, definitions, mathematical results, how a finished piece of code works, or the plot of a book.",
        focus="Judge the subject of the work itself, not whether the user mentions a date, and ignore how urgent the request sounds.",
        question="Is the subject of `request` something whose facts change over time?",
        true_what="The result would be different if the same work were done later.",
        true_examples=("What did our competitors ship this month?", "How many open bugs do we have?"),
        false_what="The result would be the same if the same work were done later.",
        false_examples=("Explain how TCP handshakes work.", "What caused the 2008 financial crisis?"),
    ),
    _RecurringText(
        key="has_variants",
        definition="A result has variants when the same kind of result could be made again by changing one aspect of it, such as its audience, subject, length, tone, format, language, time period, or the input it is built from.",
        markers="A cover letter can be rewritten for other jobs, a product description for other products, a lesson plan for other topics, a chart for other metrics, and a sales email for other prospects.",
        boundary="A result that by nature exists only once has no variants, such as the fix for one specific error, a choice between two named options, or the answer to one factual question.",
        focus="Judge the kind of result being asked for, not whether the user asked for more than one copy.",
        question="Could the result that `request` asks for be made again in other versions by changing one aspect of it?",
        true_what="Another version of this kind of result is a natural thing to make.",
        true_examples=("Write a LinkedIn post announcing our launch.", "Make a one-page study guide for chapter 3."),
        false_what="Only one correct result exists.",
        false_examples=("Why does this test fail?", "Which of these two laptops has more RAM?"),
    ),
    _RecurringText(
        key="method_generalizes",
        definition="A general method is a way of doing the work whose steps do not depend on the particular thing being worked on, so the same steps apply to any other thing of the same type.",
        markers="Reviewing a pull request, summarizing a paper, cleaning a spreadsheet, researching a company, grading an essay, and triaging an inbox all follow general methods: the steps stay the same while the pull request, paper, or company changes.",
        boundary="Work whose steps are decided by the unique details of one situation does not follow a general method, such as recovering one corrupted database or untangling one person's specific dispute.",
        focus="Judge the steps the work would need, not the topic it is about.",
        question="Does the work in `request` follow a general method that would apply unchanged to other things of the same type?",
        true_what="The same steps would work on another input of the same type.",
        true_examples=("Summarize this paper's methods and limitations.", "Review this pull request for security issues."),
        false_what="The steps are shaped by one unique situation.",
        false_examples=("Figure out why production went down at 3 a.m.", "Help me settle this argument with my roommate."),
    ),
    _RecurringText(
        key="routine_kind",
        definition="Routine work is a kind of task that people normally do many times as part of their job or their life.",
        markers="Reporting, reviewing, updating, reconciling, following up, scheduling, preparing for a regular meeting, sending outreach, checking status, and planning a week are routine kinds of work.",
        boundary="Work that people do once or rarely is not routine, even when it is hard or important, such as naming a company, writing a wedding speech, planning a move, or choosing a system architecture.",
        focus="Judge the kind of work in general, not this user's situation, and ignore whether the user says they have done it before.",
        question="Is the kind of work in `request` routine work?",
        true_what="People normally do this kind of task many times.",
        true_examples=("Prep my notes for tomorrow's one-on-one.", "Reconcile these expenses against the bank statement."),
        false_what="People do this kind of task once or rarely.",
        false_examples=("Help me name my startup.", "Plan our office move."),
    ),
    _RecurringText(
        key="input_replaceable",
        definition="A replaceable input is the specific thing the work is performed on, such as a document, a dataset, a person, a company, a date range, a web page, or a topic, that could be swapped for another of the same type while the rest of the request still makes sense.",
        markers='"Compare these two vendors\' pricing" still makes sense with two other vendors, "turn this transcript into meeting notes" still makes sense with another transcript, and "find flights to Lisbon in May" still makes sense with another city and month.',
        boundary='A request in which every detail is tied to one situation has no replaceable input, such as "why did my deploy fail after yesterday\'s config change".',
        focus="Judge whether swapping the input leaves a sensible request, not whether the user would actually make that request.",
        question="Does `request` contain an input that could be replaced by another of the same type while the rest of the request stays the same?",
        true_what="Swapping the main input leaves a sensible request.",
        true_examples=("Turn this transcript into meeting notes.", "Compare these two vendors' pricing."),
        false_what="Every detail belongs to one situation.",
        false_examples=("Why did my deploy fail after yesterday's config change?", "Undo the last edit I made."),
    ),
    _RecurringText(
        key="ongoing_goal",
        definition="An ongoing goal is a state the user wants to keep true over time, rather than an end point that is reached once and is then finished.",
        markers="Staying informed about a field, keeping a codebase or a dataset clean, keeping a project on schedule, keeping customers answered, keeping spending under a limit, and keeping a document current are ongoing goals.",
        boundary="A goal that is complete once the work is done is not ongoing, even when it takes a long time, such as shipping one feature, getting one answer, or making one purchase.",
        focus="Judge the purpose behind the request, not the single piece of work it asks for.",
        question="Does `request` serve an ongoing goal?",
        true_what="The work maintains a state over time.",
        true_examples=("Go through the backlog and close stale issues.", "Catch me up on what happened in AI this week."),
        false_what="The work reaches an end point and is then finished.",
        false_examples=("Add dark mode to the settings page.", "Book a table for Friday."),
    ),
    _RecurringText(
        key="value_accumulates",
        definition="Work accumulates value when each time it is done adds to a result that keeps growing, so the result of one run becomes more useful when later runs add to it.",
        markers="Logs, datasets, knowledge bases, lists of leads, reading lists, portfolios, trackers, changelogs, and collections of notes all accumulate value.",
        boundary="Work whose result is complete and useful on its own, and gains nothing from later additions, does not accumulate value, such as a converted file or a single decision.",
        focus="Judge the kind of result, not how large it is now.",
        question="Does the work in `request` produce a result that grows more useful when later runs add to it?",
        true_what="Later runs would add to the same growing result.",
        true_examples=("Find ten more companies like these and add them to the sheet.", "Add today's findings to my research notes."),
        false_what="The result is complete on its own.",
        false_examples=("Convert this PDF to Markdown.", "Pick the better of these two logos."),
    ),
    _RecurringText(
        key="compares_over_time",
        definition="Comparison over time means the result exists to show how something differs from an earlier or a later point, such as a trend, a change, progress toward a target, the difference between two versions, or what is new since last time.",
        markers='Results such as "what changed", "how we are tracking", "growth this quarter", "new since the last release", and "before and after" depend on comparison over time, whether the subject is sales, fitness, a codebase, or a market.',
        boundary="A result that describes one moment or one thing, without reference to another point in time, does not depend on comparison over time.",
        focus="Judge what the result would need to show, not the words the user used.",
        question="Does the result `request` asks for depend on comparing something across points in time?",
        true_what="The result shows a difference between points in time.",
        true_examples=("How did signups move after the pricing change?", "What changed in the API between v2 and v3?"),
        false_what="The result describes one moment or one thing.",
        false_examples=("What is our current pricing?", "Describe this photo."),
    ),
    _RecurringText(
        key="topic_inexhaustible",
        definition="A topic is inexhaustible when a single pass cannot cover everything that could be found, because the set of items, sources, explanations, ideas, or possibilities is very large or keeps growing.",
        markers="Finding leads, collecting research papers, generating ideas, finding bugs, finding similar products, listing possible causes of a broad problem, and gathering examples are inexhaustible topics.",
        boundary="A topic with a small, closed set of answers can be covered in one pass, such as the capital of a country, the output of one function, or the steps to install one tool.",
        focus="Judge the size and openness of the topic, not the amount the user asked for.",
        question="Is the topic of `request` one that a single pass could not cover completely?",
        true_what="More could always be found after one pass.",
        true_examples=("Find papers on retrieval-augmented generation for code.", "Give me startup ideas in climate tech."),
        false_what="One pass can cover the whole topic.",
        false_examples=("What does git rebase --onto do?", "Convert 30 miles to kilometers."),
    ),
    _RecurringText(
        key="refined_in_versions",
        definition="Refinement in versions means this kind of result is normally improved over several rounds, each version built from the last, so preferences learned in early rounds apply to later ones.",
        markers="Drafts of an essay, iterations of a design, versions of a pitch deck, tuning of a prompt, revisions of a plan, and edits of a resume are refined in versions.",
        boundary="A result that is accepted or rejected once and is then finished is not refined in versions, such as a converted file, a computed number, or a direct answer.",
        focus="Judge the usual life of this kind of result, not whether the user has asked for revisions yet.",
        question="Is the result `request` asks for the kind of result that is normally refined over several versions?",
        true_what="This kind of result usually goes through several versions.",
        true_examples=("Draft the first version of our fundraising memo.", "Sketch a landing page layout for the app."),
        false_what="This kind of result is finished in one step.",
        false_examples=("What is 18% of 2,340?", "Rename these files to lowercase."),
    ),
    _RecurringText(
        key="stable_standard",
        definition="A stable standard is a set of rules, criteria, preferences, or a style that the result must meet and that would apply in the same way to every future result of this kind.",
        markers="Brand voice, a code style guide, a grading rubric, a compliance checklist, a report format a team uses, a citation style, and personal preferences about how the user likes things done are stable standards.",
        boundary='A requirement that belongs only to this one result is not a stable standard, such as "keep it under 300 words for this application" or "use the numbers from this sheet".',
        focus="Judge whether the request states or points to rules that outlast this one result.",
        question="Does `request` state or point to a stable standard the result must meet?",
        true_what="The result must meet rules that would apply to future results too.",
        true_examples=("Review this PR against our backend conventions.", "Write it in our usual newsletter voice."),
        false_what="Any requirements belong only to this one result.",
        false_examples=("Make this paragraph shorter.", "Use the numbers from this sheet."),
    ),
    _RecurringText(
        key="useful_to_others",
        definition="Work is useful to others when people or agents other than this user, doing similar work, could use the same method or result without changing much of it.",
        markers="A way of onboarding a new hire, a process for reviewing contracts, an explanation of an internal system, a release checklist, a study method, and a template for incident reports are useful to others.",
        boundary="Work that only makes sense inside this user's private circumstances is not useful to others, such as a personal message to a friend or a decision about the user's own finances.",
        focus="Judge the work and its method, not whether the user plans to share it.",
        question="Would the method or the result of `request` be useful to others doing similar work?",
        true_what="Others doing similar work could reuse the method or result.",
        true_examples=("Write up how we deploy the API so the new hire can do it.", "Make a checklist for reviewing vendor contracts."),
        false_what="The work only makes sense for this user's private situation.",
        false_examples=("Help me reply to my landlord.", "Should I refinance my car loan?"),
    ),
    _RecurringText(
        key="process_centered",
        definition="Process-centered work is work where the way the result is reached matters as much as the result itself, because the same steps must be followed correctly each time.",
        markers="Review procedures, data pipelines, deployments, audits, hiring screens, research methods, lab protocols, and bookkeeping are process-centered.",
        boundary="Answer-centered work is not process-centered, because only the final answer matters and the route to it is not worth keeping, such as a quick fact, a single calculation, or the translation of one sentence.",
        focus="Judge what would be worth keeping once the work is done.",
        question="Is the work in `request` process-centered?",
        true_what="The steps are worth keeping, not only the answer.",
        true_examples=("Screen these applicants against the role requirements.", "Audit our cloud bill for unused resources."),
        false_what="Only the final answer matters.",
        false_examples=("Translate this sentence into Spanish.", "Who won the 1998 World Cup?"),
    ),
    _RecurringText(
        key="tied_to_cycle",
        definition="Work tied to a cycle belongs to a pattern that repeats in time or in a lifecycle, and it can be tied to a cycle even when no date appears in the request.",
        markers="Days, weeks, sprints, months, quarters, seasons, releases, meeting series, reporting periods, billing cycles, and school terms are cycles, and preparing for a standup, closing the books, writing release notes, and planning a sprint are tied to them.",
        boundary="Work tied to one event that will not come back is not tied to a cycle, such as a wedding, a single product launch, or a one-time migration.",
        focus="Judge the kind of work, not whether a date or a period is mentioned.",
        question="Is the work in `request` tied to a repeating cycle?",
        true_what="The work comes around again with a repeating cycle.",
        true_examples=("Write the release notes for 2.4.", "Prepare my agenda for Monday's team sync."),
        false_what="The work belongs to one event that will not come back.",
        false_examples=("Plan the migration off MySQL.", "Write a toast for my sister's wedding."),
    ),
    _RecurringText(
        key="responds_to_arrivals",
        definition="Repeating arrivals are things that come in from outside again and again, and work that responds to one of them handles a single item of a kind that will keep arriving.",
        markers="Messages, tickets, applications, orders, invoices, pull requests, alerts, form submissions, reviews, and new files are repeating arrivals.",
        boundary="Work started by the user's own idea or need, rather than by something arriving, does not respond to arrivals.",
        focus="Judge where the work comes from, not how many items the request names.",
        question="Does the work in `request` respond to something that arrives repeatedly from outside?",
        true_what="The work handles one item of a kind that keeps arriving.",
        true_examples=("Draft a reply to this customer complaint.", "Categorize this incoming invoice."),
        false_what="The work starts from the user's own idea or need.",
        false_examples=("Brainstorm names for our new feature.", "Teach me how binary search works."),
    ),
    _RecurringText(
        key="same_operation_many_items",
        definition="Applying the same operation to many items means the work does one action again and again across a set, and the set may be stated or implied and may grow later.",
        markers="Renaming files, tagging records, summarizing each document, emailing each contact, checking each link, translating each string, and scoring each candidate apply the same operation to many items.",
        boundary="Work that does one action on one thing, or several different actions that each need their own approach, does not apply the same operation to many items.",
        focus="Judge the structure of the work, not how many items are named right now.",
        question="Does the work in `request` apply the same operation to many items?",
        true_what="One action repeats across a set of items.",
        true_examples=("Tag every row in this sheet by industry.", "Check each link on our docs site."),
        false_what="The work is one action on one thing, or many different actions.",
        false_examples=("Rewrite the intro of my essay.", "Design the database schema for the app."),
    ),
    _RecurringText(
        key="needs_lasting_context",
        definition="Lasting context is knowledge about the user that stays true across many tasks and would otherwise have to be explained again each time.",
        markers='Their systems and tools, where their files live, their team, their customers, their conventions, their voice, and their preferences are lasting context, as in "draft our usual investor update" or "clean up the CRM the way we like it".',
        boundary='A request that any capable agent could do well with no knowledge of the user does not need lasting context, such as "explain recursion".',
        focus="Judge what doing the work well requires, not what the request already includes.",
        question="Does doing `request` well depend on lasting context about the user?",
        true_what="Doing it well needs knowledge about the user that stays true across tasks.",
        true_examples=("Write this week's update in my usual format.", "File this bug in our tracker the way the team does it."),
        false_what="Any capable agent could do it well without knowing the user.",
        false_examples=("Explain what a Kalman filter is.", "Convert this table to CSV."),
    ),
    _RecurringText(
        key="no_new_decisions",
        definition="Work needs no new decisions when, once its approach is set, doing it again needs no fresh choice, idea, approval, or material from the user, because its inputs can be fetched and its rules are already known.",
        markers="Producing a status summary from a tracker, checking a site for broken links, sorting incoming email by fixed rules, and pulling this period's numbers into a report need no new decisions.",
        boundary="Work that needs the user's new judgment or new material each time does need new decisions, such as choosing a strategy, writing something personal, deciding between offers, or editing a draft only the user can supply.",
        focus="Judge the kind of work once its approach is set, not this first request.",
        question="Once its approach is set, could the work in `request` be done again without a new decision from the user?",
        true_what="Later runs could proceed without fresh input from the user.",
        true_examples=("Summarize the open tickets in our tracker.", "Check our site for broken links."),
        false_what="Each run needs a new decision or new material from the user.",
        false_examples=("Help me decide between these two job offers.", "Edit the draft I'm about to paste."),
    ),
    _RecurringText(
        key="continuing_effort",
        definition="A continuing effort is a larger piece of work that this request is one part of, and that goes on before and after it.",
        markers="Campaigns, research programs, hiring rounds, product roadmaps, courses of study, job searches, and client engagements are continuing efforts, and requests often show this by referring to what came before or what comes next, or by naming the effort.",
        boundary="A self-contained request with no larger effort around it is not part of a continuing effort.",
        focus="Judge only what `request` says or clearly implies, and do not invent an effort it does not mention.",
        question="Is `request` part of a continuing effort?",
        true_what="The request is one step in a larger ongoing effort.",
        true_examples=("Next step for the Series A: draft outreach to the second batch of funds.", "Continue the literature review from where we left off."),
        false_what="The request stands on its own.",
        false_examples=("What's a good birthday gift for a 10-year-old?", "Fix the typo in this sentence."),
    ),
    _RecurringText(
        key="intent_to_keep",
        definition="Intent to keep or repeat means the user shows they want this work to be available again, to happen again, or to become a standing way of working.",
        markers='They may say so directly, by asking for a template, an automation, a routine, a skill, or a saved version, or indirectly, with phrases such as "every time", "from now on", "going forward", "each week", or "so I don\'t have to do this again".',
        boundary="Asking to save the output of this one run is not intent to keep or repeat the work itself.",
        focus="Judge only what the user says, not what they might want.",
        question="Does `request` show intent to keep or repeat this work?",
        true_what="The user wants the work kept or repeated.",
        true_examples=("Set this up so it runs every Monday.", "Turn this into something I can reuse."),
        false_what="The user wants this one result only.",
        false_examples=("Save the result to notes.md.", "Summarize this article."),
    ),
)

RECURRING_QUESTIONS: tuple[JevQuestion, ...] = tuple(text.to_jev_question() for text in _TEXTS)


__all__ = ["RECURRING_QUESTIONS", "RECURRING_QUESTION_PREFIX"]
