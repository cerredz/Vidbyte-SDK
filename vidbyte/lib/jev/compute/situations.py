"""FILE: vidbyte/lib/jev/compute/situations.py

PURPOSE: Defines the fixed evidence questions for fresh-agent, fork-agent, and subagent compute options.
ROLE IN CODEBASE: JevComputeRegistry gathers these question objects into one request for every enabled option.
ARCHITECTURE NOTE: Each question reads the same request, brief, facts, and recent-event state and scores one observable signal.
COMMON MODIFICATION PATTERNS: Keep exactly twelve independent questions per option and use the dynamic-compute question-writing guide.
KNOWN EDGE CASES: Missing evidence may score false; question text must not ask Jev to predict whether an action should launch.
RELATED DOCS: docs/design/jev-compute-situations.md and skills/asking-jev-dynamic-compute-questions/SKILL.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.jev import JevComputeQuestion
from vidbyte.lib.enums.jev import JevComputeQuestionKey


FRESH_AGENT_QUESTIONS = (
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_ERROR_RATE_RISING,
        instructions="Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant evidence is tool errors becoming denser near the run's current end. Compare later error events with earlier activity that remains visible. One isolated error does not establish a rising rate. If the state lacks a comparable time span, treat the rise as absent. Look for the described pattern across visible actions and their results. Has the rate of tool errors risen late in the run? The signal is present when visible recent events show tool errors becoming more frequent toward the run's end. The signal is absent when they do not show an increase or do not allow an earlier-to-later comparison.",
        when_true="True when visible recent events show tool errors becoming more frequent toward the run's end.",
        when_false='False when they do not show an increase or do not allow an earlier-to-later comparison.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_SAME_FAILURE_PERSISTS,
        instructions='Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant pattern is recurrence of one unresolved failure across attempts. Match attempts to the same underlying failure rather than the same broad task. A retry counts only when the state shows a new attempt after that failure. A failure followed by evidence of resolution is not persistent. If events do not identify the same failure, treat recurrence as absent. Is the same failure still occurring across multiple attempts? The signal is present when multiple visible attempts encounter the same unresolved failure. The signal is absent when the failure is different, resolved, or not clearly repeated in the state.',
        when_true='True when multiple visible attempts encounter the same unresolved failure.',
        when_false='False when the failure is different, resolved, or not clearly repeated in the state.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_REPEATED_ACTION_NO_INFORMATION,
        instructions='Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant evidence is an unchanged tool action repeated without useful new information. Compare the action and its arguments across the repeated calls. Then compare their results for information relevant to the requested work. A repeated signature alone is insufficient when its result adds useful information. When the state cannot show both repetition and its results, treat the signal as absent. Has the same tool action been repeated without adding relevant information? The signal is present when a repeated action has the same effective inputs and adds no relevant information. The signal is absent when the action differs, adds useful information, or the state cannot establish both facts.',
        when_true='True when a repeated action has the same effective inputs and adds no relevant information.',
        when_false='False when the action differs, adds useful information, or the state cannot establish both facts.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_DRIFT_FROM_USER_GOAL,
        instructions="Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant comparison is between the current work and the outcome the user requested. Trace whether those actions advance the requested outcome or a necessary substep. A changed method can still remain aligned with the same goal. Unrelated work is different from an ordinary delay or supporting investigation. If the state does not establish a mismatch, treat drift as absent. Are recent actions drifting away from the user's original goal? The signal is present when visible work pursues an outcome with no supported connection to the requested goal. The signal is absent when the work remains connected to the goal or the state does not establish a mismatch.",
        when_true='True when visible work pursues an outcome with no supported connection to the requested goal.',
        when_false='False when the work remains connected to the goal or the state does not establish a mismatch.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_USER_CONSTRAINT_OMITTED,
        instructions="Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant evidence is an explicit user constraint missing from current work. Identify a constraint stated directly in the request. Check whether the visible plan or completed work addresses that constraint. Silence about a constraint does not by itself prove that it was omitted. If the state cannot connect an explicit constraint to a current omission, treat it as absent. Does current work omit an explicit constraint from the user's request? The signal is present when the request states a constraint and the visible plan or work leaves it unaddressed. The signal is absent when constraints are addressed or the state does not establish a specific omission.",
        when_true='True when the request states a constraint and the visible plan or work leaves it unaddressed.',
        when_false='False when constraints are addressed or the state does not establish a specific omission.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_CLAIM_CONTRADICTS_EVIDENCE,
        instructions='Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant comparison is between a recent agent claim and verified tool evidence. Locate a recent claim about what happened or what a tool established. Compare that claim with the relevant returned result in the shared state. A difference in wording is not a contradiction when the meaning agrees. A claim with no corresponding evidence cannot establish a contradiction by itself. If both sides of the comparison are not visible, treat this signal as absent. Does a recent agent claim contradict verified tool evidence? The signal is present when a visible recent claim conflicts with the result of the relevant tool call. The signal is absent when the claim agrees with the result or the state lacks both sides of the comparison.',
        when_true='True when a visible recent claim conflicts with the result of the relevant tool call.',
        when_false='False when the claim agrees with the result or the state lacks both sides of the comparison.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_DISPROVEN_ASSUMPTION_CONTINUES,
        instructions='Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant evidence is continued action based on an assumption already disproven in the run. Find an assumption that the visible evidence directly rules out. Then check whether later activity still relies on that same assumption. A new test of an uncertain idea does not show continued reliance after disproof. The assumption and later action must refer to the same premise. If the state does not show disproof followed by reliance, treat the signal as absent. Does the agent keep acting on an assumption the run has disproven? The signal is present when later visible work still relies on a premise already contradicted by run evidence. The signal is absent when no disproof and continued reliance are both visible in the state.',
        when_true='True when later visible work still relies on a premise already contradicted by run evidence.',
        when_false='False when no disproof and continued reliance are both visible in the state.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_EARLIER_EVIDENCE_IGNORED,
        instructions='Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant evidence is an earlier finding that later work fails to use. Identify evidence that bears directly on the current step or unresolved problem. Check whether later actions or claims account for that evidence. Not repeating an old detail is not the same as losing or ignoring it. The evidence must remain relevant to the work now underway. If the state does not expose relevant evidence and later omission, treat this signal as absent. Is relevant earlier evidence being lost or ignored by the current work? The signal is present when later visible work overlooks earlier verified evidence relevant to its current step. The signal is absent when the evidence is accounted for, no longer relevant, or not visible enough to compare.',
        when_true='True when later visible work overlooks earlier verified evidence relevant to its current step.',
        when_false='False when the evidence is accounted for, no longer relevant, or not visible enough to compare.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_FIX_INTRODUCES_FAILURE,
        instructions='Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant question is whether an attempted fix is followed by a new failure. Separate the original problem from a failure that appears after a fix attempt. The later problem must be tied by the visible sequence to that attempted change. A failure that was already present is not newly introduced by the fix. A successful change followed by an unrelated error does not establish this signal. If the state cannot identify a new failure after a fix, treat it as absent. Have attempted fixes introduced new failures in the run? The signal is present when a visible fix attempt is followed by a newly reported failure attributable to that change. The signal is absent when no new failure follows a fix or the state cannot connect the two.',
        when_true='True when a visible fix attempt is followed by a newly reported failure attributable to that change.',
        when_false='False when no new failure follows a fix or the state cannot connect the two.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_PLAN_OSCILLATES,
        instructions='Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant evidence is a plan that repeatedly changes direction without measurable progress. Look for repeated returns between competing directions rather than one considered revision. Check whether each change produces a verified result or advances a named item. A justified plan update after new evidence is not unproductive oscillation. If repeated reversals or lack of progress are not visible, treat this signal as absent. Is the plan oscillating between directions without measurable progress? The signal is present when repeated direction changes are visible without verified progress on the requested work. The signal is absent when the plan is stable, changes for evidence-based reasons, or makes visible progress.',
        when_true='True when repeated direction changes are visible without verified progress on the requested work.',
        when_false='False when the plan is stable, changes for evidence-based reasons, or makes visible progress.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_LOST_CONTINUITY,
        instructions='Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant evidence is observable confusion linked to accumulated run activity. Look for visible loss of continuity, such as repeated uncertainty about established state. A large count alone does not show confusion or lost context. A single correction can be ordinary learning rather than a continuity failure. If accumulated activity and a continuity problem are not both supported, treat the signal as absent. Does the growing run show lost continuity or confused state? The signal is present when later events show confusion or loss of established state as the run grows. The signal is absent when only run size is visible or the events do not establish a continuity problem.',
        when_true='True when later events show confusion or loss of established state as the run grows.',
        when_false='False when only run size is visible or the events do not establish a continuity problem.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FRESH_AGENT_BRIEF_SUPPORTS_RESUME,
        instructions='Long agent runs can make earlier evidence and the original goal harder to keep in view. A fresh context becomes relevant when the current run shows a concrete loss of progress, accuracy, or continuity. The relevant issue is whether the verified brief preserves enough state to resume the task. It can also retain named items, approaches, and unresolved failures. A useful handoff makes clear what has been done and what remains. Do not fill gaps with assumptions that the shared state does not support. If the brief omits essential goal or progress context, treat resume readiness as absent. Does the verified brief contain enough state for a fresh agent to resume? The signal is present when the brief supports the goal, verified progress, current position, and an actionable next step. The signal is absent when essential context is missing, unclear, or only inferable from unsupported assumptions.',
        when_true='True when the brief supports the goal, verified progress, current position, and an actionable next step.',
        when_false='False when essential context is missing, unclear, or only inferable from unsupported assumptions.',
    ),
)


FORK_AGENT_QUESTIONS = (
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_DISTINCT_APPROACHES,
        instructions='An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant evidence is multiple plausible approaches to one unresolved goal. Find at least two approaches that address the same unresolved goal. They must differ in their central action, not merely in wording. If the state does not support two such approaches, treat them as absent. Look for the described pattern across visible actions and their results. Are there two or more genuinely distinct plausible approaches to the same unresolved goal? The signal is present when the state supports at least two different, plausible approaches to one unresolved requested goal. The signal is absent when fewer than two such approaches are supported or they address different goals.',
        when_true='True when the state supports at least two different, plausible approaches to one unresolved requested goal.',
        when_false='False when fewer than two such approaches are supported or they address different goals.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_SAME_VERIFIED_STATE,
        instructions="An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant question is whether the alternative paths share one current starting point. Compare what each path requires before it can begin. Both paths must use the same already verified facts and completed work. A path that depends on the other path's result starts from a different state. If one shared starting state is not supported, treat the signal as absent. Can the alternative paths start from the same verified state? The signal is present when both paths can use the same verified progress, facts, and current position. The signal is absent when either path requires a different or not-yet-established starting state.",
        when_true='True when both paths can use the same verified progress, facts, and current position.',
        when_false='False when either path requires a different or not-yet-established starting state.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_INDEPENDENT_PATHS,
        instructions="An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant evidence is approaches that can progress without depending on one another. Trace each approach through its stated next actions. An independent path does not need the other path's intermediate output. Shared purpose does not make paths dependent when their work can proceed separately. If a dependency is unclear, do not infer independence from the option names. Can the alternative paths proceed independently of each other's intermediate results? The signal is present when the described next actions on each path do not require the other's output. The signal is absent when one path depends on the other's result or the state cannot establish independence.",
        when_true="True when the described next actions on each path do not require the other's output.",
        when_false="False when one path depends on the other's result or the state cannot establish independence.",
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_BOUNDED_EXPERIMENTS,
        instructions='An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant issue is whether each approach can be tested as a bounded experiment. A bounded experiment has a stated action and an observable stopping point. Each path must be testable without expanding into an open-ended task. The proposed test must leave a result that can be inspected in the run. An approach label without an action or endpoint is not a bounded experiment. If either path lacks a testable bound, treat this signal as absent. Can each alternative path be tested as a bounded experiment? The signal is present when each path has a bounded action and an observable result or stopping point. The signal is absent when either path is open-ended or has no inspectable result.',
        when_true='True when each path has a bounded action and an observable result or stopping point.',
        when_false='False when either path is open-ended or has no inspectable result.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_COMMON_SUCCESS_CONDITION,
        instructions='An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant question is whether both paths can be judged against the same success condition. Name the requested condition that would count as success for each path. The path-specific steps may differ while the outcome test remains common. Two outcomes that cannot be compared under one condition do not share this signal. If the request and brief do not support a common test, treat it as absent. Can outcomes from both paths be compared against the same success condition? The signal is present when one request-grounded success condition applies to both paths. The signal is absent when their outcomes require unrelated success conditions or no common condition is stated.',
        when_true='True when one request-grounded success condition applies to both paths.',
        when_false='False when their outcomes require unrelated success conditions or no common condition is stated.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_NO_CLEAR_WINNER,
        instructions='An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant evidence is unresolved evidence between the plausible paths. A clear winner requires relevant evidence that favors one path over the alternatives. A difference in how much each path has been tried is not itself proof. Do not treat missing evidence as evidence that paths are equally good. If the state does not establish whether a winner is clear, treat this signal as absent. Does the current evidence leave the plausible paths without a clear winner? The signal is present when available relevant evidence does not establish one path as the clear choice. The signal is absent when the evidence clearly favors one path or is too incomplete to compare them.',
        when_true='True when available relevant evidence does not establish one path as the clear choice.',
        when_false='False when the evidence clearly favors one path or is too incomplete to compare them.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_NON_FORECLOSING,
        instructions='An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant question is whether trying one path leaves the alternatives available. Consider whether one path consumes a resource needed by another. Also check for order requirements that make later alternatives impossible. A reversible trial can preserve options even if it produces a different result. A path that permanently rules out another is foreclosing it. If the state does not show whether alternatives remain available, treat this signal as absent. Does the current state show that trying one path leaves the other plausible paths available? The signal is present when visible actions and constraints allow the alternatives to remain open after a trial. The signal is absent when one path forecloses another or the state cannot establish that options remain open.',
        when_true='True when visible actions and constraints allow the alternatives to remain open after a trial.',
        when_false='False when one path forecloses another or the state cannot establish that options remain open.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_ISOLATED_SIDE_EFFECTS,
        instructions="An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant evidence is side effects that can be kept separate across paths. Compare the targets each path would read or change. Isolation means one path's effects do not silently alter the other's inputs. Separate names alone do not prove that underlying state is independent. If the state cannot identify bounded effects, treat isolation as absent. Can writes or other side effects from the paths be isolated from one another? The signal is present when the state supports separate targets or controlled effects for each path. The signal is absent when effects overlap in an uncontrolled way or the state cannot establish isolation.",
        when_true='True when the state supports separate targets or controlled effects for each path.',
        when_false='False when effects overlap in an uncontrolled way or the state cannot establish isolation.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_PARALLEL_EVIDENCE,
        instructions="An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant evidence is independent trial results that can become visible without serial dependency. Compare whether each path can produce its own inspectable result. The result must not wait on the other path's intermediate output. A shared final comparison is compatible with independently gathered evidence. The question concerns available parallel evidence, not whether extra agents should be launched. If the paths are sequentially dependent, treat this signal as absent. Can each path's outcome be inspected before another path supplies an intermediate result? The signal is present when each path can yield an inspectable result without waiting on the other path. The signal is absent when results depend on serial handoffs or the state does not show separate outcomes.",
        when_true='True when each path can yield an inspectable result without waiting on the other path.',
        when_false='False when results depend on serial handoffs or the state does not show separate outcomes.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_DIFFERENT_HYPOTHESES,
        instructions='An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant question is whether the paths test different meaningful explanations or mechanisms. Identify the distinct claim each path would test against the shared goal. Different commands that test the same claim do not establish different hypotheses. The difference must matter to what the run would conclude or do next. If no distinct request-relevant hypotheses are visible, treat this signal as absent. Does each path test a different meaningful hypothesis about the unresolved goal? The signal is present when the paths test distinct, request-relevant explanations or mechanisms. The signal is absent when they test the same claim or their difference has no bearing on the goal.',
        when_true='True when the paths test distinct, request-relevant explanations or mechanisms.',
        when_false='False when they test the same claim or their difference has no bearing on the goal.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_SELECTABLE_RESULT,
        instructions='An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant evidence is a result from one path that can be selected or integrated. A usable result can be compared and then chosen or incorporated into the main work. The paths may produce competing answers if the shared goal still guides selection. A result with no route back into requested work is not selectable in this sense. If the state does not show how a result could be used, treat this signal as absent. Can a result from one path be selected or integrated into the main work? The signal is present when the state supports comparing a path result and using it toward the requested outcome. The signal is absent when results cannot guide a choice or connect back to the requested work.',
        when_true='True when the state supports comparing a path result and using it toward the requested outcome.',
        when_false='False when results cannot guide a choice or connect back to the requested work.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.FORK_AGENT_REQUEST_ALIGNED_PATHS,
        instructions="An unresolved goal can sometimes support several plausible approaches. Separate paths are useful when their outcomes can be compared from a common starting point. The relevant comparison is between the alternative paths and the user's requested goal. Trace each path to work that advances or verifies the requested outcome. A different method can remain aligned when it serves the same requested result. Unrequested side work does not become relevant merely because it is technically interesting. If the state does not connect an alternative to the request, treat it as unaligned. Do the alternative paths address the requested goal rather than unrelated work? The signal is present when each path has a supported connection to the user's requested outcome. The signal is absent when a path pursues unrelated work or its connection to the request is unsupported.",
        when_true="True when each path has a supported connection to the user's requested outcome.",
        when_false='False when a path pursues unrelated work or its connection to the request is unsupported.',
    ),
)


SUBAGENT_QUESTIONS = (
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_BOUNDED_SUBTASK,
        instructions='A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant evidence is a bounded subtask that can stand on its own. Identify work already grounded in the task rather than inventing extra scope. The subtask needs a clear boundary and a result or stopping point. It must not require the main agent to supply missing decisions as it proceeds. If scope or completion cannot be identified, treat the subtask as absent. Is there a bounded, independently executable subtask in the current work? The signal is present when the state shows a scoped unit of work with a clear result or stopping point. The signal is absent when the work is open-ended, dependent on missing decisions, or unsupported by the state.',
        when_true='True when the state shows a scoped unit of work with a clear result or stopping point.',
        when_false='False when the work is open-ended, dependent on missing decisions, or unsupported by the state.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_EXPLICIT_DELIVERABLE,
        instructions='A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant issue is whether the separate work has a clear deliverable. Name what a helper would return when its work is complete. The deliverable must be inspectable by the main agent. Activity without an identifiable result is not a deliverable. If the shared state does not specify an output or completion result, treat it as absent. Does the independent subtask have an explicit deliverable? The signal is present when the state identifies a concrete output or finding the helper would return. The signal is absent when the expected result is unspecified, uninspectable, or not distinct from activity.',
        when_true='True when the state identifies a concrete output or finding the helper would return.',
        when_false='False when the expected result is unspecified, uninspectable, or not distinct from activity.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_PACKAGED_INPUTS,
        instructions="A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant question is whether the subtask's starting information can be packaged from shared state. Identify the inputs needed to complete the bounded work. Those inputs must be visible without relying on hidden conversation history. A missing decision or source cannot be supplied by assuming what the main agent knows. If essential inputs are not present in the shared state, treat packaging as absent. Can the subtask's required inputs be packaged from the request and verified brief? The signal is present when the required starting context is present in the original task, verified run notes, or relevant recent events. The signal is absent when essential context depends on unavailable history, assumptions, or new decisions.",
        when_true='True when the required starting context is visible in the original task, verified notes, or recent work.',
        when_false='False when essential context depends on unavailable history, assumptions, or new decisions.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_OWN_TOOL_INTERACTIONS,
        instructions="A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant evidence is a work unit with its own necessary tool interactions. Identify the bounded actions needed to finish that work unit. They should be separable from the main agent's central reasoning steps. A subtask that only repeats a judgment already visible in the brief has no independent tool work. If separate tool interactions are not supported by the state, treat this signal as absent. Does the subtask require its own bounded tool interactions? The signal is present when the work unit requires distinct tool actions that can be performed within its scope. The signal is absent when it needs no separate interactions or its actions are inseparable from the main path.",
        when_true='True when the work unit requires distinct tool actions that can be performed within its scope.',
        when_false='False when it needs no separate interactions or its actions are inseparable from the main path.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_NO_MIDTASK_DECISIONS,
        instructions='A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant question is whether the subtask can proceed without decisions from the main agent midway. Follow the proposed work from its starting inputs to its stated deliverable. The helper must have enough direction to finish that bounded path independently. A need to choose among new user-facing or task-defining options breaks independence. If an intervening decision is required or the state is unclear, treat this signal as absent. Can the subtask proceed without the main agent making decisions midway? The signal is present when its scope, inputs, and stopping condition let the helper finish without an intervening choice. The signal is absent when the path depends on a new decision or the shared state does not settle that question.',
        when_true='True when its scope, inputs, and stopping condition let the helper finish without an intervening choice.',
        when_false='False when the path depends on a new decision or the shared state does not settle that question.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_SEPARATE_FROM_CENTRAL_PATH,
        instructions="A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant distinction is between separate work and the main agent's central decision path. Compare the proposed subtask with those central choices. Separate work can inform the main path without making its core choice on the main agent's behalf. A step that determines the main path's next action is not separate in this sense. If the state does not show this distinction, treat separation as absent. Is the subtask separate from the main agent's central decision path? The signal is present when it produces supporting work without owning a decision reserved for the main path. The signal is absent when it performs the central choice itself or the relationship is unclear.",
        when_true='True when it produces supporting work without owning a decision reserved for the main path.',
        when_false='False when it performs the central choice itself or the relationship is unclear.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_INTEGRATABLE_RESULT,
        instructions="A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant issue is whether the subtask's result has a route back into the run. Connect the proposed result to a specific next step or requested item. The main agent must be able to inspect and use the returned result. A detached artifact with no relation to remaining work is not integratable. If the state does not show a usable connection, treat integration as absent. Can the subtask's result be handed back and integrated into the main work? The signal is present when the result can be inspected and applied to a current request or unresolved step. The signal is absent when there is no supported route to use the result in the main work.",
        when_true='True when the result can be inspected and applied to a current request or unresolved step.',
        when_false='False when there is no supported route to use the result in the main work.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_PARALLEL_PROGRESS,
        instructions="A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant evidence is a separate work unit that can proceed while the main work continues. Compare the subtask's inputs with the main path's outstanding actions. The two units must be able to advance without waiting for each other's intermediate result. A common final integration point does not make their earlier work dependent. If one unit must pause for the other, treat parallel progress as absent. Can this subtask proceed while the main agent continues another active step? The signal is present when the state shows independent work that does not wait on the main path's intermediate result. The signal is absent when the subtask and main step are sequentially dependent or the dependency is unclear.",
        when_true="True when the state shows independent work that does not wait on the main path's intermediate result.",
        when_false='False when the subtask and main step are sequentially dependent or the dependency is unclear.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_FOCUSED_CONTEXT,
        instructions="A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant evidence is a focused body of evidence or material that forms its own work unit. Identify a coherent evidence set that can be examined within the subtask's boundary. Its relevant inputs should be distinguishable from the main agent's other active material. A separate topic label alone does not establish a focused body of evidence. If the state does not identify such a set, treat this signal as absent. Does the state identify a distinct evidence set that can be examined in a focused context? The signal is present when the state identifies a bounded evidence set distinct from other active run material. The signal is absent when the material is not separable or no focused evidence set is shown.",
        when_true='True when the state identifies a bounded evidence set distinct from other active run material.',
        when_false='False when the material is not separable or no focused evidence set is shown.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_PARTITIONABLE_ITEMS,
        instructions='A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant question is whether multiple independent requested items can be partitioned. Compare the unfinished items for dependencies on one another. Partitioning applies when each unit can be handled from its own stated inputs. A numbered list is not independent when its items rely on shared intermediate decisions. If multiple independent items are not visible, treat this signal as absent. Are multiple independent items present that can be partitioned into separate work units? The signal is present when the state shows at least two unfinished items with separable inputs and outcomes. The signal is absent when fewer than two such items are supported or their work is interdependent.',
        when_true='True when the state shows at least two unfinished items with separable inputs and outcomes.',
        when_false='False when fewer than two such items are supported or their work is interdependent.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_ISOLATED_WRITES,
        instructions='A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant evidence is subtask work that avoids conflicting writes or shared mutable state. Identify which shared targets the subtask would change. Compare those targets with ongoing main-agent actions in the run. Separate read-only work or disjoint targets can avoid competing mutations. If writes overlap or their isolation is not shown, treat this signal as absent. Can the subtask avoid conflicting writes and shared mutable state? The signal is present when visible scope permits read-only work or changes to isolated targets. The signal is absent when mutable targets overlap or the state does not establish safe separation.',
        when_true='True when visible scope permits read-only work or changes to isolated targets.',
        when_false='False when mutable targets overlap or the state does not establish safe separation.',
    ),
    JevComputeQuestion(
        key=JevComputeQuestionKey.SUBAGENT_SUBSTANTIVE_WORK,
        instructions="A larger task can contain a piece of work that stands on its own. A separate helper is useful when that piece has clear boundaries and returns something the main work can use. The relevant question is whether the independent work contains enough substantive activity. Estimate the bounded actions needed from the state rather than from an invented plan. The unit should involve meaningful investigation, transformation, or verification. A tiny isolated action is not substantive merely because it can be delegated. If the state does not support meaningful independent work, treat this signal as absent. Is there enough substantive work for an independent helper? The signal is present when the bounded unit contains meaningful investigation, transformation, or verification. The signal is absent when it is trivial, unsupported, or inseparable from the main agent's work.",
        when_true='True when the bounded unit contains meaningful investigation, transformation, or verification.',
        when_false="False when it is trivial, unsupported, or inseparable from the main agent's work.",
    ),
)

__all__ = ["FORK_AGENT_QUESTIONS", "FRESH_AGENT_QUESTIONS", "SUBAGENT_QUESTIONS"]
