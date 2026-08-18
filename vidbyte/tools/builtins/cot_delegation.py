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
Similar Files:
    - `vidbyte/tools/builtins/cot_context.py`
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

CONTEXT_ATTACH_LEVELS = ("minimal", "moderate", "full")
TRUST_LEVELS = ("verified", "spot_checked", "assumed")
CRITERIA_OUTCOMES = ("met", "partially_met", "missed", "gamed")
RECHECK_COST_LEVELS = ("cheap", "expensive", "impossible")
HANDOFF_REASONS = ("specialization", "capacity", "context_limit", "parallelism")
READINESS_LEVELS = ("yes", "no", "unclear")
COMPLETENESS_GAPS = ("nothing", "context", "constraints", "format", "success_criteria")
FAILURE_OWNERS = ("brief", "capability", "context", "luck")
SEVERITY_LEVELS = ("fatal", "major", "minor")
RECOVERABILITY_LEVELS = ("yes", "costly", "no")
BLOCKED_RESPONSES = ("wait", "nudge", "take_back", "escalate")
_MAX_PASSED_ASSUMPTIONS = 5


class DelegationBriefTool(_CotEventToolBase):
    """Builtin tool that records what was sent to a subagent and under which assumptions."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="delegation_brief",
            description=(
                "Record the brief you are sending to a subagent before it "
                "goes: the task, the success criteria, and — most "
                "importantly — the assumptions you are passing along inside "
                "your framing of the task. Use this every time you delegate "
                "or hand work to another agent. Delegation failures are "
                "usually born in the brief: the receiver cannot read your "
                "mind, so everything you baked into the phrasing — 'fix the "
                "login bug' quietly assumes the bug is in the login code — "
                "travels as invisible cargo. Naming your passed assumptions "
                "and what you deliberately withheld makes the boundary "
                "auditable: when the result comes back wrong, the question "
                "'was it the brief or the receiver?' has an answer. Success "
                "criteria must be checkable by the receiver without asking "
                "you again."
            ),
            parameters=(
                ToolParameter(
                    name="task",
                    type="string",
                    description=(
                        "The task as the receiver will see it, one or two "
                        "sentences. Phrase it as an outcome, not a procedure, "
                        "unless the procedure is the point."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="success_criteria",
                    type="string",
                    description=(
                        "The conditions under which the receiver's result "
                        "counts as done — concrete and checkable by the "
                        "receiver without further input from you: 'the "
                        "migration script runs to completion on the staging "
                        "dataset and row counts match'. Vague criteria "
                        "('make it better') manufacture disputes."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="assumptions_passed",
                    type="string",
                    description=(
                        "Optional: a JSON array of up to 5 strings, each an "
                        "assumption embedded in your framing of the task: "
                        "[\"the staging dataset mirrors production shape\", "
                        "\"the script may create collections but not delete "
                        "any\"]. List them even though the receiver will not "
                        "see this record — they are for the audit trail."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="withheld",
                    type="string",
                    description=(
                        "Optional: what you deliberately did not include in "
                        "the brief and why — 'omitted the pricing context; "
                        "irrelevant to the schema task'. Withholding is a "
                        "decision; record it so it is distinguishable from "
                        "an oversight."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="context_attached",
                    type="string",
                    description=(
                        "Optional: how much context traveled with the task. "
                        "Use exactly one of: 'minimal' (task statement only), "
                        "'moderate' (task plus key constraints), 'full' "
                        "(everything relevant you have). Minimal briefs are "
                        "cheap but fragile; full ones burn the receiver's "
                        "window. Say which trade you made."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="fallback_on_failure",
                    type="string",
                    description=(
                        "Optional: what happens if the receiver fails or "
                        "returns garbage — 're-do it myself', 'try a "
                        "different decomposition'. A brief without a fallback "
                        "makes failure a dead end."
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
                "Record what came back across the agent boundary and — the "
                "core question — how much you verified it before letting it "
                "into your own reasoning. Use this every time you receive a "
                "delegated result. Trust transferred without verification is "
                "how multi-agent systems compound errors: receiver A assumed "
                "receiver B checked, who assumed the orchestrator would. "
                "'assumed' is a legal answer and sometimes the right one — "
                "but it must be visible, because assumed results should fail "
                "differently in your downstream confidence than verified "
                "ones. Check the result against the brief's success criteria "
                "explicitly; 'gamed' — criteria nominally met, spirit "
                "violated — is a real outcome and naming it early keeps a "
                "subtle failure from masquerading as success."
            ),
            parameters=(
                ToolParameter(
                    name="result_summary",
                    type="string",
                    description=(
                        "What the receiver actually returned, one or two "
                        "sentences summarizing the substance — not just "
                        "'completed as requested', which carries no "
                        "information."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="trust",
                    type="string",
                    description=(
                        "How much you verified before relying on it. Use "
                        "exactly one of: 'verified' (you independently "
                        "confirmed the key claims), 'spot_checked' (you "
                        "confirmed a sample), 'assumed' (you accepted it on "
                        "the receiver's word). Answer by what you did after "
                        "receiving it, not what you intend to do."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="criteria_met",
                    type="string",
                    description=(
                        "The result against the brief's success criteria. Use "
                        "exactly one of: 'met', 'partially_met', 'missed', "
                        "'gamed' (criteria nominally satisfied while the "
                        "evident intent was not — flag this loudly)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="discrepancies",
                    type="string",
                    description=(
                        "Optional: differences between what was asked and "
                        "what arrived — scope quietly added or dropped, "
                        "format deviations, unexplained choices. None is a "
                        "fine answer; unexamined is not."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="recheck_cost",
                    type="string",
                    description=(
                        "Optional: what full re-verification would cost you "
                        "now. Use exactly one of: 'cheap', 'expensive', "
                        "'impossible'. This is the input to the trust "
                        "decision a monitor will want to audit — assumed "
                        "plus cheap-to-recheck is a laziness signature."
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

        self._counter += 1
        from vidbyte.context.primitives.cot_delegation import DelegationReceiptContextItem

        item = DelegationReceiptContextItem(
            primitive_id=self._next_primitive_id(),
            result_summary=str(args["result_summary"]).strip(),
            trust=trust or TRUST_LEVELS[2],
            criteria_met=criteria or CRITERIA_OUTCOMES[0],
            discrepancies=CotEventParser.optional_text(args.get("discrepancies")),
            recheck_cost=recheck,
        )
        return await self._record(item, call, {"trust": item.trust, "criteria_met": item.criteria_met})


class HandoffWhyTool(_CotEventToolBase):
    """Builtin tool that records why a unit of work left this agent for another."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="handoff_why",
            description=(
                "Record why work is crossing an agent boundary — not the "
                "mechanics of the handoff, the reason for it. Use this when "
                "you send work out, especially when the decision to hand off "
                "was yours. Handoffs are often load-bearing decisions "
                "disguised as logistics: work leaves because your context is "
                "polluted, or because the receiver genuinely knows better, "
                "or because it was simply expedient — and these have very "
                "different risk profiles. The receiver's readiness matters "
                "too: handing work to an agent that lacks the context to "
                "succeed is delegation theater. Naming the take-back trigger "
                "protects against the worst handoff failure, which is work "
                "sitting with a receiver who is quietly not doing it."
            ),
            parameters=(
                ToolParameter(
                    name="work",
                    type="string",
                    description=(
                        "The unit of work being handed off, scoped precisely: "
                        "'writing the integration tests for the auth flow', "
                        "not 'the auth work'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reason",
                    type="string",
                    description=(
                        "The primary reason work is leaving. Use exactly one "
                        "of: 'specialization' (the receiver is better suited "
                        "to this work), 'capacity' (you have too much "
                        "parallel work), 'context_limit' (your window is "
                        "spent or polluted for this work), 'parallelism' "
                        "(splitting for speed)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="rationale",
                    type="string",
                    description=(
                        "One or two sentences making the reason concrete: "
                        "'my window is 80% consumed by the pricing analysis; "
                        "fresh eyes on the test file will be faster than my "
                        "context-switch cost'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="receiver_ready",
                    type="string",
                    description=(
                        "Optional: does the receiver have what it needs to "
                        "start? Use exactly one of: 'yes', 'no' (a known gap — "
                        "say it in rationale), 'unclear' (you have not "
                        "verified). 'no' and 'unclear' handoffs deserve extra "
                        "receipt scrutiny later."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="take_back_trigger",
                    type="string",
                    description=(
                        "Optional: the condition under which you would "
                        "reclaim this work — 'no result after two iterations' "
                        "or 'receiver reports blocked twice'. A handoff with "
                        "no take-back condition can silently become "
                        "abandonment."
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
        )
        return await self._record(item, call, {"reason": item.reason})


class HandoffCompletenessTool(_CotEventToolBase):
    """Builtin tool that audits whether a handoff brief contained everything the receiver needs."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="handoff_completeness",
            description=(
                "Audit a handoff brief — yours or one you received — for "
                "what it is missing. Use this before sending a brief you "
                "care about, or on receiving one that feels thin. The "
                "classic delegation failure is a structurally perfect brief "
                "that omits one thing the receiver had no way to know: the "
                "constraint, the format expectation, the definition of "
                "done. Walk the categories honestly — context, constraints, "
                "format, success criteria — and name the gap if there is "
                "one. Finding a gap after sending is a follow-up message; "
                "finding it before is this tool doing its job. If you mark "
                "'nothing' missing, the record should survive review — this "
                "attestation is exactly the kind that gets checked when the "
                "handoff later fails."
            ),
            parameters=(
                ToolParameter(
                    name="brief",
                    type="string",
                    description=(
                        "The brief being audited, summarized in one or two "
                        "sentences — enough that a reader can tell which "
                        "handoff this was."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="missing",
                    type="string",
                    description=(
                        "The audit verdict. Use exactly one of: 'nothing', "
                        "'context' (receiver lacks background they need), "
                        "'constraints' (rules the receiver could violate "
                        "unknowingly), 'format' (output shape/medium "
                        "unspecified), 'success_criteria' (no checkable "
                        "definition of done)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="fix_applied",
                    type="string",
                    description=(
                        "Optional: whether you fixed the gap — amended the "
                        "brief, added the constraint. 'yes' or 'no'. A named "
                        "gap left unfixed is a transferred risk; say so "
                        "rather than leaving it implicit."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="risk_if_unfixed",
                    type="string",
                    description=(
                        "Optional: the cost if the gap goes unaddressed. Use "
                        "exactly one of: 'fatal' (receiver will produce "
                        "unusable or harmful work), 'major' (significant "
                        "rework on return), 'minor' (small friction)."
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
        fix, fix_error = CotEventParser.parse_enum(args.get("fix_applied"), ("yes", "no"), "fix_applied")
        if fix_error:
            return ToolResult.error(call.tool_name, fix_error)
        risk, risk_error = CotEventParser.parse_enum(args.get("risk_if_unfixed"), SEVERITY_LEVELS, "risk_if_unfixed")
        if risk_error:
            return ToolResult.error(call.tool_name, risk_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_delegation import HandoffCompletenessContextItem

        item = HandoffCompletenessContextItem(
            primitive_id=self._next_primitive_id(),
            brief=str(args["brief"]).strip(),
            missing=missing or COMPLETENESS_GAPS[0],
            fix_applied=fix,
            risk_if_unfixed=risk,
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
                "before retrying. Use this every time a subagent result is "
                "unusable. Attribution matters because it changes the fix: a "
                "brief failure means you fix your instructions, a capability "
                "failure means you change who or how you delegate, a "
                "context failure means the receiver lacked something only "
                "you could supply, and luck means retry as-is. The common "
                "and corrosive pattern is attributing everything to the "
                "receiver ('capability') when the brief was the problem — "
                "that produces repeated failures with rewritten-but-"
                "identical briefs. Be as hard on your own brief as on the "
                "receiver's work; the record is most useful when the "
                "attribution would embarrass you slightly."
            ),
            parameters=(
                ToolParameter(
                    name="failure",
                    type="string",
                    description=(
                        "What actually failed, concretely: 'returned code "
                        "that compiles but ignores the pagination "
                        "constraint'. The observable failure, not your "
                        "reaction to it."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="owner",
                    type="string",
                    description=(
                        "The true owner of the failure. Use exactly one of: "
                        "'brief' (your instructions were ambiguous, "
                        "incomplete, or wrong), 'capability' (the receiver "
                        "could not do the work as briefed), 'context' (the "
                        "receiver lacked information it had no way to "
                        "obtain), 'luck' (transient — timeout, flake, race)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="analysis",
                    type="string",
                    description=(
                        "One or two sentences of evidence for the "
                        "attribution — why owner and not the alternatives. "
                        "'It ignored the constraint' alone proves nothing "
                        "about whose fault that is."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="recoverable",
                    type="string",
                    description=(
                        "Optional: whether the situation is recoverable "
                        "within this run. Use exactly one of: 'yes' (retry "
                        "with corrections), 'costly' (recoverable but "
                        "expensive), 'no' (work is lost or deadline gone)."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="retry_differently",
                    type="string",
                    description=(
                        "Optional: how the next attempt differs because of "
                        "this attribution — 'same receiver, brief rewritten "
                        "with the constraint stated first'. Required in "
                        "spirit whenever recoverable is 'yes'; retrying "
                        "identically after a failure is the loop this tool "
                        "exists to break."
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

        self._counter += 1
        from vidbyte.context.primitives.cot_delegation import SubagentFailuresContextItem

        item = SubagentFailuresContextItem(
            primitive_id=self._next_primitive_id(),
            failure=str(args["failure"]).strip(),
            owner=owner or FAILURE_OWNERS[1],
            analysis=str(args["analysis"]).strip(),
            recoverable=recoverable,
            retry_differently=CotEventParser.optional_text(args.get("retry_differently")),
        )
        return await self._record(item, call, {"owner": item.owner})


class BlockedOnTool(_CotEventToolBase):
    """Builtin tool that records a current blocking dependency and the chosen response."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="blocked_on",
            description=(
                "Record it the moment you are blocked — what you are "
                "waiting on, and what you have decided to do about it. Use "
                "this whenever progress on your critical path stops: "
                "awaiting a subagent, a user answer, an external system, a "
                "resource that is not there. Blocking silently is the most "
                "expensive thing a run can do — every step spent idle is "
                "wasted, and the waste is invisible unless declared. Name "
                "the unblock condition precisely ('the subagent's schema "
                "extraction', not 'other work'). Update the same record as "
                "the situation changes rather than stacking new ones. The "
                "response field is a commitment: 'wait' with no unblock "
                "condition and no time bound is not patience, it is "
                "stalling with paperwork. If steps_wasted is growing "
                "across updates, the correct response is usually "
                "'escalate', and deep down you know it."
            ),
            parameters=(
                ToolParameter(
                    name="blocked_on",
                    type="string",
                    description=(
                        "The specific thing you are waiting for, named "
                        "precisely: 'the subagent extracting the pricing "
                        "schema', 'user confirmation of the destructive "
                        "migration'. Reuse the same phrasing when updating "
                        "an existing block — it updates the ledger entry."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="response",
                    type="string",
                    description=(
                        "Your chosen response. Use exactly one of: 'wait' "
                        "(productive: there is other work to do or the "
                        "unblock is imminent), 'nudge' (poke the blocker), "
                        "'take_back' (reclaim the work and do it "
                        "yourself), 'escalate' (raise it to the user or "
                        "orchestrator now)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="unblock_condition",
                    type="string",
                    description=(
                        "The precise condition that ends the block: 'the "
                        "receipt from the schema subagent arrives', 'the "
                        "user answers the migration prompt'. A block "
                        "without an unblock condition cannot be detected "
                        "as over."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="blocking_since_step",
                    type="number",
                    description=(
                        "Optional: the step number at which the block "
                        "began — a non-negative integer. Set on first "
                        "declaration; keep it stable on updates."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="steps_wasted",
                    type="number",
                    description=(
                        "Optional: how many steps have been consumed while "
                        "blocked without productive work — a non-negative "
                        "integer. Honesty here is what makes escalating in "
                        "time possible."
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

        from vidbyte.context.primitives.cot_delegation import BlockedOnContextItem

        blocked_on = str(args["blocked_on"]).strip()
        item = BlockedOnContextItem(
            primitive_id=self.statement_primitive_id("blocked_on", blocked_on),
            blocked_on=blocked_on,
            response=response or BLOCKED_RESPONSES[0],
            unblock_condition=str(args["unblock_condition"]).strip(),
            blocking_since_step=since_step,
            steps_wasted=wasted,
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
