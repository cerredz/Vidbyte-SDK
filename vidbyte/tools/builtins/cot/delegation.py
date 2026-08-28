"""Context Protocol Header

Description:
    Implements the inter-agent delegation epistemics monitoring tools.
Purpose:
    Lets the model record what crosses agent boundaries with how much trust —
    delegation briefs and receipts, why work was handed off, whether briefs
    were complete, subagent failure attribution, and current blocking
    dependencies.
Architecture:
    - DelegationBriefTool, DelegationReceiptTool, HandoffWhyTool,
      HandoffCompletenessTool, SubagentFailuresTool, BlockedOnTool:
      _CotEventToolBase subclasses that validate, upsert a matching
      cot_delegation primitive, and return parsed values in ToolResult.metadata.
Relations:
    Reuses CotEventParser and _CotEventToolBase from builtins.cot_events.
    Categorical fields are sourced from vidbyte.lib.enums.cot.
Similar Files:
    - `vidbyte/tools/builtins/cot/context.py`
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.enums.cot import (
    BlockedResponse,
    ContextAttachLevel,
    CriteriaOutcome,
    FailureOwner,
    HandoffCompletenessGap,
    HandoffReason,
    PatternSeenBefore,
    ReadinessLevel,
    RecheckCost,
    Recoverability,
    ReviewSource,
    Severity,
    TrustLevel,
    YesNo,
)
from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

CONTEXT_ATTACH_LEVELS = tuple(level.value for level in ContextAttachLevel)
TRUST_LEVELS = tuple(level.value for level in TrustLevel)
CRITERIA_OUTCOMES = tuple(outcome.value for outcome in CriteriaOutcome)
RECHECK_COST_LEVELS = tuple(level.value for level in RecheckCost)
HANDOFF_REASONS = tuple(reason.value for reason in HandoffReason)
READINESS_LEVELS = tuple(level.value for level in ReadinessLevel)
COMPLETENESS_GAPS = tuple(gap.value for gap in HandoffCompletenessGap)
FAILURE_OWNERS = tuple(owner.value for owner in FailureOwner)
SEVERITY_LEVELS = tuple(level.value for level in Severity)
RECOVERABILITY_LEVELS = tuple(level.value for level in Recoverability)
BLOCKED_RESPONSES = tuple(response.value for response in BlockedResponse)
FOLLOW_UP_OPTIONS = tuple(option.value for option in YesNo)
REVIEW_SOURCES = tuple(source.value for source in ReviewSource)
PATTERN_SEEN_OPTIONS = tuple(option.value for option in PatternSeenBefore)
ALTERNATIVE_WORK_OPTIONS = tuple(option.value for option in YesNo)
_MAX_PASSED_ASSUMPTIONS = 5


class DelegationBriefTool(_CotEventToolBase):
    """Builtin tool that records what was sent to a subagent and under which assumptions."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="delegation_brief",
            description=(
                "Record the brief being sent to a subagent before it goes, "
                "capturing the task, the success criteria, and — most "
                "importantly — the assumptions carried inside the framing of "
                "the task rather than stated openly. Delegation failures are "
                "usually born in the brief rather than in the receiver's "
                "execution, because the receiver cannot read the delegator's "
                "mind and everything baked into the phrasing travels as "
                "invisible cargo. Naming the assumptions passed along and what "
                "was deliberately withheld makes the boundary auditable, so "
                "that when a result comes back wrong there is an actual answer "
                "to whether the brief or the receiver was at fault. Success "
                "criteria recorded here must be checkable by the receiver "
                "without needing to circle back and ask for clarification."
            ),
            parameters=(
                ToolParameter(
                    name="task",
                    type="string",
                    description=(
                        "The task as the receiver will actually see it, "
                        "phrased as an outcome to achieve rather than a "
                        "procedure to follow unless the procedure itself is "
                        "the point of the delegation."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="success_criteria",
                    type="string",
                    description=(
                        "The conditions under which the receiver's result "
                        "counts as done, stated concretely enough to be "
                        "checked by the receiver without further input from "
                        "the delegator. Vague criteria manufacture disputes "
                        "later, since both sides can honestly disagree about "
                        "whether an ambiguous bar was cleared."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="assumptions_passed",
                    type="string",
                    description=(
                        "An optional JSON array of up to five strings, each "
                        "naming one assumption embedded in the framing of the "
                        "task that the receiver will not see stated "
                        "explicitly. These entries exist purely for the audit "
                        "trail, letting a later reader see exactly what the "
                        "delegator was taking for granted when the brief was "
                        "written."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="withheld",
                    type="string",
                    description=(
                        "An optional account of what was deliberately left "
                        "out of the brief and why. Recording withholding as a "
                        "decision distinguishes it from an oversight, which "
                        "matters when a result comes back missing exactly the "
                        "thing that was withheld on purpose."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="context_attached",
                    type="string",
                    description=(
                        "An optional statement of how much supporting context "
                        "traveled with the task, ranging from none through "
                        "minimal, a curated selection, a moderate amount "
                        "including key constraints, and the full context "
                        "available. A minimal brief is cheap to produce but "
                        "fragile, while a full one is thorough but consumes "
                        "the receiver's own window, and this field names "
                        "which trade-off was actually made."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="fallback_on_failure",
                    type="string",
                    description=(
                        "An optional description of what happens if the "
                        "receiver fails outright or returns something "
                        "unusable. A brief that has no answer here treats "
                        "receiver failure as a dead end rather than a "
                        "planned-for contingency."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the delegation brief primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("task", "success_criteria"))
        if error:
            return ToolResult.error(call.tool_name, error)
        assumptions, assumptions_error = self._parse_passed_assumptions(args.get("assumptions_passed"))
        if assumptions_error:
            return ToolResult.error(call.tool_name, assumptions_error)
        context_attached, context_error = CotEventParser.parse_enum(
            args.get("context_attached"), CONTEXT_ATTACH_LEVELS, "context_attached"
        )
        if context_error:
            return ToolResult.error(call.tool_name, context_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_delegation import DelegationBriefContextItem

        item = DelegationBriefContextItem(
            primitive_id=self._next_primitive_id(),
            task=str(args["task"]).strip(),
            success_criteria=str(args["success_criteria"]).strip(),
            assumptions_passed=tuple(assumptions or ()),
            withheld=CotEventParser.optional_text(args.get("withheld")),
            context_attached=context_attached,
            fallback_on_failure=CotEventParser.optional_text(args.get("fallback_on_failure")),
        )
        return await self._record(
            item,
            call,
            {"context_attached": item.context_attached, "assumptions_passed_count": len(item.assumptions_passed)},
        )

    def _parse_passed_assumptions(self, value: Any) -> tuple[list[str] | None, str | None]:
        # Parses the passed-assumptions JSON array into up to 5 non-empty strings.
        parsed, error = CotEventParser.parse_json_strings(value, "assumptions_passed", _MAX_PASSED_ASSUMPTIONS)
        if error:
            return None, error
        return [entry for entry in parsed or () if entry] or [], None


class DelegationReceiptTool(_CotEventToolBase):
    """Builtin tool that records what came back from a subagent and how much it was trusted."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="delegation_receipt",
            description=(
                "Record what came back across an agent boundary and, most "
                "importantly, how much of it was actually verified before it "
                "was allowed into further reasoning. Trust that transfers "
                "across a chain of delegations without anyone actually "
                "checking it is how multi-agent systems compound small errors "
                "into large ones, since each link assumes the previous one "
                "already did the checking. Accepting a result on the "
                "receiver's word alone is a legitimate answer and sometimes "
                "the correct one, but it must be visible as such, because an "
                "assumed result should carry different downstream confidence "
                "than a verified one. The result should also be checked "
                "explicitly against the originating brief's success criteria, "
                "since criteria nominally satisfied while the evident intent "
                "was not met is a real and easily overlooked outcome."
            ),
            parameters=(
                ToolParameter(
                    name="result_summary",
                    type="string",
                    description=(
                        "A substantive summary of what the receiver actually "
                        "returned, specific enough to convey real information "
                        "rather than a bare acknowledgment that something was "
                        "completed."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="trust",
                    type="string",
                    description=(
                        "How much verification actually happened before "
                        "relying on the result, distinguishing independent "
                        "confirmation of the key claims, a spot check of a "
                        "sample, trust extended further along a delegation "
                        "chain without direct verification, acceptance on the "
                        "receiver's word alone, and active distrust of the "
                        "result. This should reflect what was actually done "
                        "after receiving the result, not an intention to "
                        "check later."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="criteria_met",
                    type="string",
                    description=(
                        "The result judged against the originating brief's "
                        "success criteria, distinguishing a result that "
                        "exceeded expectations, one that fully met them, one "
                        "that only partially met them, one that missed them "
                        "outright, one where the criteria were nominally "
                        "satisfied while the evident intent was not, and one "
                        "where the criteria could not actually be evaluated."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="discrepancies",
                    type="string",
                    description=(
                        "An optional account of differences between what was "
                        "asked for and what arrived, such as scope quietly "
                        "added or dropped, format deviations, or unexplained "
                        "choices. A genuine absence of discrepancies is a "
                        "fine answer here; an unexamined result is not the "
                        "same thing."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="recheck_cost",
                    type="string",
                    description=(
                        "An optional estimate of what fully re-verifying this "
                        "result would cost right now, ranging from free "
                        "through cheap, moderate, and expensive up to "
                        "practically impossible. This is a direct input to "
                        "the trust decision a monitor will want to audit, "
                        "since an assumed result that would have been cheap "
                        "to recheck is a meaningfully different situation "
                        "than one that would have been expensive."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="follow_up_needed",
                    type="string",
                    description=(
                        "An optional statement of whether this receipt "
                        "requires a follow-up action before the result can be "
                        "fully relied on, expressed as yes or no. This field "
                        "lets a reader distinguish a receipt that closes the "
                        "delegation loop from one that leaves an open thread "
                        "still requiring attention."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the delegation receipt primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("result_summary", "trust", "criteria_met"))
        if error:
            return ToolResult.error(call.tool_name, error)
        trust, trust_error = CotEventParser.parse_enum(args.get("trust"), TRUST_LEVELS, "trust")
        if trust_error:
            return ToolResult.error(call.tool_name, trust_error)
        criteria, criteria_error = CotEventParser.parse_enum(args.get("criteria_met"), CRITERIA_OUTCOMES, "criteria_met")
        if criteria_error:
            return ToolResult.error(call.tool_name, criteria_error)
        recheck, recheck_error = CotEventParser.parse_enum(args.get("recheck_cost"), RECHECK_COST_LEVELS, "recheck_cost")
        if recheck_error:
            return ToolResult.error(call.tool_name, recheck_error)
        follow_up, follow_up_error = CotEventParser.parse_enum(args.get("follow_up_needed"), FOLLOW_UP_OPTIONS, "follow_up_needed")
        if follow_up_error:
            return ToolResult.error(call.tool_name, follow_up_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_delegation import DelegationReceiptContextItem

        item = DelegationReceiptContextItem(
            primitive_id=self._next_primitive_id(),
            result_summary=str(args["result_summary"]).strip(),
            trust=trust or TRUST_LEVELS[2],
            criteria_met=criteria or CRITERIA_OUTCOMES[0],
            discrepancies=CotEventParser.optional_text(args.get("discrepancies")),
            recheck_cost=recheck,
            follow_up_needed=follow_up,
        )
        return await self._record(item, call, {"trust": item.trust, "criteria_met": item.criteria_met})


class HandoffWhyTool(_CotEventToolBase):
    """Builtin tool that records why a unit of work left this agent for another."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="handoff_why",
            description=(
                "Record why work is crossing an agent boundary, focusing on "
                "the actual reason rather than the mechanics of the handoff "
                "itself. Handoffs frequently disguise a load-bearing decision "
                "as mere logistics: work can leave because the sender's own "
                "context has become polluted, because the receiver genuinely "
                "has better standing to do it, or simply because it was "
                "convenient, and these carry very different risk profiles that "
                "deserve to be distinguished. The receiver's actual readiness "
                "to take the work on matters as much as the reason for "
                "sending it, since handing work to a receiver who lacks the "
                "context to succeed is delegation in name only. Naming the "
                "take-back trigger in advance protects against the worst "
                "handoff failure, which is work quietly sitting with a "
                "receiver who is not making progress on it."
            ),
            parameters=(
                ToolParameter(
                    name="work",
                    type="string",
                    description=(
                        "The unit of work being handed off, scoped precisely "
                        "enough that a reader can tell exactly what is and is "
                        "not included rather than only the general area it "
                        "falls under."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reason",
                    type="string",
                    description=(
                        "The primary reason the work is leaving, "
                        "distinguishing the receiver being genuinely better "
                        "suited to the work, the sender having too much "
                        "parallel work in flight, the sender's own context "
                        "window being spent or polluted for this particular "
                        "work, a permission or access boundary that the "
                        "sender cannot cross, the work being split "
                        "specifically to run in parallel, and a deliberate "
                        "cost-optimization choice."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="rationale",
                    type="string",
                    description=(
                        "A concrete elaboration of the chosen reason, "
                        "grounding it in the specific circumstances of this "
                        "handoff rather than restating the reason category in "
                        "different words."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="receiver_ready",
                    type="string",
                    description=(
                        "An optional assessment of whether the receiver "
                        "actually has what it needs to start, distinguishing "
                        "full readiness, partial readiness with a known gap, "
                        "a pending state not yet resolved, genuine "
                        "uncertainty about readiness, and an outright lack of "
                        "readiness. Anything short of full readiness deserves "
                        "closer scrutiny when the corresponding receipt "
                        "arrives."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="take_back_trigger",
                    type="string",
                    description=(
                        "An optional condition under which this work would be "
                        "reclaimed rather than left with the receiver "
                        "indefinitely. A handoff with no take-back condition "
                        "defined has no built-in defense against silently "
                        "becoming abandonment."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="expected_duration",
                    type="string",
                    description=(
                        "An optional statement of how long this work is "
                        "expected to take before a result comes back. This "
                        "field gives the take-back trigger a natural time "
                        "reference, since 'longer than expected' is otherwise "
                        "undefined without a stated baseline."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the handoff-why primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("work", "reason", "rationale"))
        if error:
            return ToolResult.error(call.tool_name, error)
        reason, reason_error = CotEventParser.parse_enum(args.get("reason"), HANDOFF_REASONS, "reason")
        if reason_error:
            return ToolResult.error(call.tool_name, reason_error)
        ready, ready_error = CotEventParser.parse_enum(args.get("receiver_ready"), READINESS_LEVELS, "receiver_ready")
        if ready_error:
            return ToolResult.error(call.tool_name, ready_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_delegation import HandoffWhyContextItem

        item = HandoffWhyContextItem(
            primitive_id=self._next_primitive_id(),
            work=str(args["work"]).strip(),
            reason=reason or HANDOFF_REASONS[0],
            rationale=str(args["rationale"]).strip(),
            receiver_ready=ready,
            take_back_trigger=CotEventParser.optional_text(args.get("take_back_trigger")),
            expected_duration=CotEventParser.optional_text(args.get("expected_duration")),
        )
        return await self._record(item, call, {"reason": item.reason})


class HandoffCompletenessTool(_CotEventToolBase):
    """Builtin tool that audits whether a handoff brief contained everything the receiver needs."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="handoff_completeness",
            description=(
                "Audit a handoff brief, whether sent or received, for what it "
                "is missing before that gap becomes the receiver's problem to "
                "discover on its own. The classic delegation failure is a "
                "brief that is structurally sound in every respect except one "
                "thing the receiver had no way to infer: a constraint, a "
                "format expectation, or the actual definition of done. Walking "
                "through the standard categories deliberately — context, "
                "constraints, format, audience, and success criteria — turns "
                "a vague sense that a brief 'feels thin' into a specific, "
                "actionable finding. Recording nothing as missing is a valid "
                "outcome, but that attestation should be able to survive "
                "later review, since it is exactly the kind of claim that "
                "gets checked once a handoff goes wrong."
            ),
            parameters=(
                ToolParameter(
                    name="brief",
                    type="string",
                    description=(
                        "The brief under audit, summarized concisely enough "
                        "that a reader can identify which specific handoff "
                        "this record refers to."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="missing",
                    type="string",
                    description=(
                        "The audit's verdict, distinguishing a brief with "
                        "nothing missing from one lacking background context "
                        "the receiver needs, rules the receiver could violate "
                        "unknowingly, an unspecified output format or medium, "
                        "an unclear sense of who the output is actually for, "
                        "or a checkable definition of done."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="fix_applied",
                    type="string",
                    description=(
                        "An optional statement of whether the identified gap "
                        "was actually fixed, such as by amending the brief or "
                        "adding the missing constraint, expressed as yes or "
                        "no. A named gap left unfixed represents a "
                        "transferred risk and should be stated as such rather "
                        "than left implicit."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="risk_if_unfixed",
                    type="string",
                    description=(
                        "An optional estimate of the cost if the identified "
                        "gap goes unaddressed, ranging from purely cosmetic "
                        "friction through minor rework, major rework, a "
                        "critical outcome where the receiver produces "
                        "unusable or harmful work, up to a fully fatal "
                        "outcome for the handoff."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="reviewed_by",
                    type="string",
                    description=(
                        "An optional statement of who actually performed this "
                        "audit, distinguishing a self-review by the sender, a "
                        "review performed by the receiver after the fact, and "
                        "a review performed by an uninvolved third party. This "
                        "field lets a reader weigh how much independent "
                        "scrutiny the completeness verdict actually received."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="follow_up_sent",
                    type="string",
                    description=(
                        "An optional statement of whether a follow-up "
                        "correction was actually sent to the receiver after "
                        "this audit, expressed as yes or no. This is distinct "
                        "from fix_applied, since a gap can be fixed in the "
                        "sender's own understanding without that correction "
                        "ever reaching the receiver."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the completeness audit primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("brief", "missing"))
        if error:
            return ToolResult.error(call.tool_name, error)
        missing, missing_error = CotEventParser.parse_enum(args.get("missing"), COMPLETENESS_GAPS, "missing")
        if missing_error:
            return ToolResult.error(call.tool_name, missing_error)
        fix, fix_error = CotEventParser.parse_enum(args.get("fix_applied"), FOLLOW_UP_OPTIONS, "fix_applied")
        if fix_error:
            return ToolResult.error(call.tool_name, fix_error)
        risk, risk_error = CotEventParser.parse_enum(args.get("risk_if_unfixed"), SEVERITY_LEVELS, "risk_if_unfixed")
        if risk_error:
            return ToolResult.error(call.tool_name, risk_error)
        reviewed_by, reviewed_by_error = CotEventParser.parse_enum(args.get("reviewed_by"), REVIEW_SOURCES, "reviewed_by")
        if reviewed_by_error:
            return ToolResult.error(call.tool_name, reviewed_by_error)
        follow_up_sent, follow_up_sent_error = CotEventParser.parse_enum(
            args.get("follow_up_sent"), FOLLOW_UP_OPTIONS, "follow_up_sent"
        )
        if follow_up_sent_error:
            return ToolResult.error(call.tool_name, follow_up_sent_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_delegation import HandoffCompletenessContextItem

        item = HandoffCompletenessContextItem(
            primitive_id=self._next_primitive_id(),
            brief=str(args["brief"]).strip(),
            missing=missing or COMPLETENESS_GAPS[0],
            fix_applied=fix,
            risk_if_unfixed=risk,
            reviewed_by=reviewed_by,
            follow_up_sent=follow_up_sent,
        )
        return await self._record(item, call, {"missing": item.missing})


class SubagentFailuresTool(_CotEventToolBase):
    """Builtin tool that records a subagent failure and whose failure it actually was."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="subagent_failures",
            description=(
                "When delegated work fails, attribute the failure honestly "
                "before retrying, since the attribution is what determines "
                "whether the retry has any chance of succeeding differently. "
                "A brief failure calls for rewriting the instructions, a "
                "capability failure calls for changing who or how work is "
                "delegated, a context failure means the receiver was missing "
                "something only the delegator could have supplied, and pure "
                "bad luck calls for a plain retry as-is. The most corrosive "
                "pattern this tool guards against is defaulting every failure "
                "to the receiver's capability when the brief itself was the "
                "actual problem, since that produces repeated failures behind "
                "briefs that look rewritten but remain functionally "
                "identical. This record is most valuable exactly when the "
                "honest attribution would be slightly uncomfortable for the "
                "delegator to admit."
            ),
            parameters=(
                ToolParameter(
                    name="failure",
                    type="string",
                    description=(
                        "What actually failed, described as an observable "
                        "outcome rather than a reaction to it, specific "
                        "enough that a reader could recognize the same "
                        "failure if it recurred."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="owner",
                    type="string",
                    description=(
                        "The true owner of the failure once attributed "
                        "honestly, distinguishing the brief being ambiguous, "
                        "incomplete, or wrong, the receiver's capability "
                        "falling short of what the work required, the "
                        "receiver lacking context it had no way to obtain on "
                        "its own, an environmental factor outside anyone's "
                        "direct control, unfortunate timing such as a race or "
                        "an expired resource, and simple transient bad luck."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="analysis",
                    type="string",
                    description=(
                        "The evidence supporting this specific attribution "
                        "rather than one of the alternatives. Observing that "
                        "something went wrong proves nothing on its own about "
                        "whose fault it was; this field should make the case "
                        "for the chosen owner explicitly."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="recoverable",
                    type="string",
                    description=(
                        "An optional assessment of whether the situation can "
                        "still be recovered within this run, distinguishing "
                        "full recoverability through a corrected retry, a "
                        "pending or not-yet-determined state, recovery that "
                        "would require real additional cost, genuine "
                        "uncertainty, and a situation where the work is lost "
                        "or the deadline has passed."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="retry_differently",
                    type="string",
                    description=(
                        "An optional description of what will actually change "
                        "on the next attempt because of this attribution. "
                        "Retrying with an identical brief and an identical "
                        "receiver after a failure is the exact loop this tool "
                        "exists to break, so whenever recovery is attempted "
                        "this field should name a real difference."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="pattern_seen_before",
                    type="string",
                    description=(
                        "An optional statement of whether this specific "
                        "attribution matches a failure pattern already seen "
                        "earlier in the run, distinguishing a confirmed "
                        "repeat, genuine uncertainty, and a first occurrence. "
                        "A recurring pattern is a stronger signal than any "
                        "single failure and deserves a correspondingly "
                        "stronger response."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the failure attribution primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("failure", "owner", "analysis"))
        if error:
            return ToolResult.error(call.tool_name, error)
        owner, owner_error = CotEventParser.parse_enum(args.get("owner"), FAILURE_OWNERS, "owner")
        if owner_error:
            return ToolResult.error(call.tool_name, owner_error)
        recoverable, recoverable_error = CotEventParser.parse_enum(
            args.get("recoverable"), RECOVERABILITY_LEVELS, "recoverable"
        )
        if recoverable_error:
            return ToolResult.error(call.tool_name, recoverable_error)
        pattern_seen, pattern_seen_error = CotEventParser.parse_enum(
            args.get("pattern_seen_before"), PATTERN_SEEN_OPTIONS, "pattern_seen_before"
        )
        if pattern_seen_error:
            return ToolResult.error(call.tool_name, pattern_seen_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_delegation import SubagentFailuresContextItem

        item = SubagentFailuresContextItem(
            primitive_id=self._next_primitive_id(),
            failure=str(args["failure"]).strip(),
            owner=owner or FAILURE_OWNERS[1],
            analysis=str(args["analysis"]).strip(),
            recoverable=recoverable,
            retry_differently=CotEventParser.optional_text(args.get("retry_differently")),
            pattern_seen_before=pattern_seen,
        )
        return await self._record(item, call, {"owner": item.owner})


class BlockedOnTool(_CotEventToolBase):
    """Builtin tool that records a current blocking dependency and the chosen response."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="blocked_on",
            description=(
                "Record it at the moment of being blocked, capturing what is "
                "being waited on and what has been decided in response. "
                "Blocking silently is one of the most expensive things a run "
                "can do, since idle steps are wasted and the waste stays "
                "invisible unless it is declared explicitly. Restating the "
                "same block with the same phrasing updates one ledger entry "
                "rather than creating a new record each time, which lets a "
                "reader see how long a given block has actually persisted. "
                "The chosen response is a real commitment rather than a "
                "formality: waiting with no unblock condition, no time bound, "
                "and no escalation path is not patience, it is stalling "
                "dressed up as process, and a growing count of wasted steps "
                "is usually a sign that escalating is overdue."
            ),
            parameters=(
                ToolParameter(
                    name="blocked_on",
                    type="string",
                    description=(
                        "The specific thing currently being waited for, named "
                        "precisely enough that its resolution would be "
                        "unambiguous. Reusing the exact same phrasing across "
                        "calls updates the existing ledger entry for this "
                        "block rather than creating a duplicate."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="response",
                    type="string",
                    description=(
                        "The chosen response to being blocked, distinguishing "
                        "productive waiting because other work exists or the "
                        "unblock is imminent, reprioritizing toward other "
                        "available work, actively nudging whatever is "
                        "blocking, reclaiming the work to do it directly, and "
                        "escalating to a user or orchestrator immediately."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="unblock_condition",
                    type="string",
                    description=(
                        "The precise condition that ends this block, stated "
                        "specifically enough that its arrival could be "
                        "detected without ambiguity. A block recorded without "
                        "an unblock condition has no way to be recognized as "
                        "over."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="blocking_since_step",
                    type="number",
                    description=(
                        "An optional non-negative integer marking the step at "
                        "which this block began. This should be set on the "
                        "first declaration of the block and kept stable "
                        "across subsequent updates to the same ledger entry."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="steps_wasted",
                    type="number",
                    description=(
                        "An optional non-negative integer counting how many "
                        "steps have been consumed while blocked without "
                        "productive work happening in parallel. Reporting "
                        "this honestly is what makes escalating in time "
                        "possible, since a silently growing count is exactly "
                        "the pattern this field is meant to surface."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="escalation_path",
                    type="string",
                    description=(
                        "An optional description of who or what this block "
                        "would be escalated to if it persists beyond a "
                        "reasonable point. Naming this in advance turns "
                        "escalation into a prepared action rather than "
                        "something improvised under the pressure of a "
                        "worsening block."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="alternative_work_available",
                    type="string",
                    description=(
                        "An optional statement of whether productive "
                        "alternative work actually exists to fill the time "
                        "while blocked, expressed as yes or no. This field "
                        "distinguishes a wait response that is genuinely "
                        "productive from one that only looks that way on the "
                        "surface."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the blocked-on primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("blocked_on", "response", "unblock_condition"))
        if error:
            return ToolResult.error(call.tool_name, error)
        response, response_error = CotEventParser.parse_enum(args.get("response"), BLOCKED_RESPONSES, "response")
        if response_error:
            return ToolResult.error(call.tool_name, response_error)
        since_step = CotEventParser.parse_int(args.get("blocking_since_step"))
        wasted = CotEventParser.parse_int(args.get("steps_wasted"))
        alternative_work, alternative_work_error = CotEventParser.parse_enum(
            args.get("alternative_work_available"), ALTERNATIVE_WORK_OPTIONS, "alternative_work_available"
        )
        if alternative_work_error:
            return ToolResult.error(call.tool_name, alternative_work_error)

        from vidbyte.context.primitives.cot_delegation import BlockedOnContextItem

        blocked_on = str(args["blocked_on"]).strip()
        item = BlockedOnContextItem(
            primitive_id=self.statement_primitive_id("blocked_on", blocked_on),
            blocked_on=blocked_on,
            response=response or BLOCKED_RESPONSES[0],
            unblock_condition=str(args["unblock_condition"]).strip(),
            blocking_since_step=since_step,
            steps_wasted=wasted,
            escalation_path=CotEventParser.optional_text(args.get("escalation_path")),
            alternative_work_available=alternative_work,
        )
        return await self._record(item, call, {"response": item.response})


__all__ = [
    "BlockedOnTool",
    "DelegationBriefTool",
    "DelegationReceiptTool",
    "HandoffCompletenessTool",
    "HandoffWhyTool",
    "SubagentFailuresTool",
]
