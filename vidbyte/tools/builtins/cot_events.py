"""Context Protocol Header

Description:
    Implements the deep chain-of-thought event tools — five model-callable
    builtins that decompose reasoning into atomic, observable events.
Purpose:
    Lets the model emit one tool call per cognitive event (hypothesis held,
    decision taken, assumption relied on, uncertainty reading, backtrack) so
    monitors get structured per-event telemetry instead of narrative prose.
Architecture:
    - CotEventParser: Shared static parsers for enums, confidences, JSON
      object arrays, and required text fields.
    - HypothesisTool, DecisionTool, AssumptionCheckTool, UncertaintyTool,
      BacktrackTool: BaseTool subclasses that validate, upsert a matching
      context primitive, and return parsed values in ToolResult.metadata.
Relations:
    Depends on vidbyte.context.manager and vidbyte.context.primitives.cot_events.
    Parallel to builtins.reflexion and builtins.trajectory_checkpoint (the
    narrative forms); shares their upsert lifecycle and SAFE permission.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager

_MAX_CONFIDENCE = 1.0
_MIN_CONFIDENCE = 0.0
_MAX_REJECTED_ALTERNATIVES = 3
_DEFAULT_BASIS_TYPE = "inference"
_DEFAULT_REVERSIBLE = "yes"
_DEFAULT_SALVAGE = "nothing"
_DEFAULT_RETURNABLE = "yes"

HYPOTHESIS_STATUSES = ("proposed", "supported", "weakened", "falsified")
BASIS_TYPES = ("evidence", "inference", "prior")
REVERSIBILITY_LEVELS = ("yes", "no", "costly")
ASSUMPTION_ACTIONS = ("declared", "verified", "falsified")
IMPACT_LEVELS = ("fatal", "major", "minor")
PROGRESS_STATES = ("progressing", "stalled", "regressing")
RETURNABLE_OPTIONS = ("yes", "no")


class CotEventParser:
    """Shared argument parsers for the deep CoT event tools."""

    @staticmethod
    def require_text(args: dict, field_names: tuple[str, ...]) -> str | None:
        # Returns an error string if any required string field is missing or blank.
        for field_name in field_names:
            value = args.get(field_name)
            if not value or not str(value).strip():
                return f"Missing or empty required field: '{field_name}'."
        return None

    @staticmethod
    def parse_enum(value: Any, allowed: tuple[str, ...], field_name: str) -> tuple[str | None, str | None]:
        # Normalizes one enum argument to a canonical lowercase value, returning (parsed, error).
        if value is None or str(value).strip() == "":
            return None, None
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            return None, f"Field '{field_name}' must be one of: {', '.join(allowed)}."
        return normalized, None

    @staticmethod
    def parse_confidence(value: Any) -> float | None:
        # Coerces a number or numeric string to a float clamped to [0.0, 1.0], or None on failure.
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        try:
            number = float(str(value).strip())
        except (ValueError, TypeError):
            return None
        return max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, number))

    @staticmethod
    def parse_json_objects(value: Any, field_name: str, max_items: int) -> tuple[list[dict] | None, str | None]:
        # Parses a JSON string (or list) into at most max_items dicts, returning (parsed, error).
        if value is None:
            return None, None
        if isinstance(value, str):
            if not value.strip():
                return None, None
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None, f"Field '{field_name}' must be valid JSON."
        else:
            parsed = value
        if not isinstance(parsed, list) or not all(isinstance(entry, dict) for entry in parsed):
            return None, f"Field '{field_name}' must be a JSON array of objects."
        if not parsed:
            return None, f"Field '{field_name}' must contain at least one object."
        return [dict(entry) for entry in parsed[:max_items]], None

    @staticmethod
    def optional_text(value: Any) -> str | None:
        # Returns a stripped optional string, or None when absent or blank.
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class _CotEventToolBase(BaseTool):
    """Shared plumbing for the five CoT event tools."""

    def __init__(self, context_manager: "ContextManager") -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def _next_primitive_id(self) -> str:
        # Generates a stable, unique primitive ID based on the instance counter.
        return f"{self.spec().name}:{self._counter}"

    @staticmethod
    def statement_primitive_id(prefix: str, statement: str) -> str:
        # Derives a stable primitive ID from the statement so re-statements update one ledger entry.
        digest = hashlib.sha1(statement.strip().lower().encode("utf-8")).hexdigest()[:12]
        return f"{prefix}:{digest}"

    async def _record(self, item: Any, call: ToolCall, metadata: dict) -> ToolResult:
        # Upserts the built primitive and returns success carrying parsed metadata.
        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))
        return ToolResult.success(call.tool_name, item.to_context_text(), metadata=metadata)


class HypothesisTool(_CotEventToolBase):
    """Builtin tool that records a falsifiable belief, its basis, and its status."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="hypothesis",
            description=(
                "Record one falsifiable belief you currently hold about the task — about how a "
                "system behaves, what an API returns, what a document means, or why a previous "
                "step failed. Use this the moment you adopt a belief you have not directly "
                "confirmed, and call it again with the same statement whenever the evidence "
                "changes its standing. This tool is a belief ledger: each belief progresses "
                "from proposed to supported, weakened, or falsified, and a belief left "
                "'proposed' for many steps is a warning sign you should verify it. Recording "
                "a falsified hypothesis is a success, not a failure — it means you caught the "
                "error before it corrupted the result. Do not record trivial beliefs you "
                "could check in one step; record the load-bearing ones your plan depends on."
            ),
            parameters=(
                ToolParameter(
                    name="statement",
                    type="string",
                    description=(
                        "The belief itself, stated as one sentence that could be proven wrong. "
                        "Write it so a reader with no context could check it: 'The pagination "
                        "endpoint returns at most 100 rows per page', not 'pagination is "
                        "limited'. Reuse the exact same sentence when updating the status of a "
                        "belief you already recorded — matching statements update the ledger "
                        "entry instead of creating a duplicate."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="basis",
                    type="string",
                    description=(
                        "Why you hold this belief right now, in one clause. Name the concrete "
                        "source: 'the API docs say so', 'the error message mentions rate "
                        "limits', 'the last tool result was empty'. Avoid 'it seems likely' — "
                        "if the only basis is your prior expectation, set basis_type to "
                        "'prior' and say so here."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="status",
                    type="string",
                    description=(
                        "Current standing of this belief. Use exactly one of: 'proposed' (first "
                        "time recording it, not yet checked), 'supported' (evidence confirmed "
                        "it), 'weakened' (evidence partially contradicts it), 'falsified' "
                        "(evidence disproved it). Progress beliefs through these states as the "
                        "run continues — do not leave a belief stuck at 'proposed' once you "
                        "have evidence either way."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="basis_type",
                    type="string",
                    description=(
                        "What kind of support the basis provides. Use exactly one of: "
                        "'evidence' (you observed it directly in a tool result, file, or "
                        "message), 'inference' (you deduced it from other facts), 'prior' "
                        "(background knowledge or expectation, nothing task-specific). Be "
                        "honest here — a run leaning on many 'prior' or 'inference' beliefs "
                        "with no 'evidence' behind them is building on sand, and this field "
                        "makes that visible. Defaults to 'inference'."
                    ),
                    required=False,
                    default=_DEFAULT_BASIS_TYPE,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the hypothesis primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("statement", "basis", "status"))
        if error:
            return ToolResult.error(call.tool_name, error)

        status, status_error = CotEventParser.parse_enum(args.get("status"), HYPOTHESIS_STATUSES, "status")
        if status_error:
            return ToolResult.error(call.tool_name, status_error)
        basis_type, basis_error = CotEventParser.parse_enum(args.get("basis_type"), BASIS_TYPES, "basis_type")
        if basis_error:
            return ToolResult.error(call.tool_name, basis_error)

        from vidbyte.context.primitives.cot_events import HypothesisContextItem

        statement = str(args["statement"]).strip()
        item = HypothesisContextItem(
            primitive_id=self.statement_primitive_id("hypothesis", statement),
            statement=statement,
            basis=str(args["basis"]).strip(),
            status=status or HYPOTHESIS_STATUSES[0],
            basis_type=basis_type or _DEFAULT_BASIS_TYPE,
        )
        return await self._record(item, call, {"status": item.status, "basis_type": item.basis_type})


class DecisionTool(_CotEventToolBase):
    """Builtin tool that records one decision, its deciding reason, and rejected alternatives."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="decision",
            description=(
                "Record a genuine choice point: a moment when you selected one path from "
                "multiple plausible ones. Use this whenever you are about to commit to an "
                "approach, a library, a data source, an order of operations, or a "
                "interpretation of an ambiguous requirement — and other real options existed. "
                "The value of this record is the alternatives you rejected, not the choice "
                "you made: the chosen path is visible in your later actions, but the rejected "
                "paths and your reasons for rejecting them are otherwise lost. Do not record "
                "non-decisions (steps with only one sensible option) and do not invent "
                "strawman alternatives to fill the field — one honestly-considered rejected "
                "option is worth more than three fake ones."
            ),
            parameters=(
                ToolParameter(
                    name="decision",
                    type="string",
                    description=(
                        "The choice being made right now, in one sentence phrased as an "
                        "action: 'Store results in a single flattened collection keyed by "
                        "source id', 'Query the audit log first, then reconcile against the "
                        "primary table'. Name the thing being decided, not the task overall."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="chosen_because",
                    type="string",
                    description=(
                        "The single deciding reason this option won, in one clause. State the "
                        "actual tiebreaker, not a generic benefit: 'it is the only option "
                        "that preserves insertion order', 'it fails safe when the upstream "
                        "call hangs', not 'it is better'. If you cannot name a concrete "
                        "deciding reason, the options were probably not meaningfully "
                        "different and this may not need to be a decision record."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="rejected",
                    type="string",
                    description=(
                        "The serious alternatives you considered and did not choose, as a "
                        "JSON array of 1 to 3 objects, each with keys 'option' (what the "
                        "alternative was) and 'reason' (one clause on why it lost). Example: "
                        "[{\"option\": \"Paginate the full list each run\", \"reason\": \"a "
                        "full scan takes 40s and runs every minute\"}]. Only include "
                        "alternatives you genuinely weighed; a decision with no real "
                        "alternatives does not need this tool."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reversible",
                    type="string",
                    description=(
                        "How costly it would be to undo this decision later. Use exactly one "
                        "of: 'yes' (undoing it is cheap — a small refactor or re-query), "
                        "'costly' (undoing it requires rework of finished work but is "
                        "possible), 'no' (this choice is effectively permanent — data "
                        "written, external side effect sent, or downstream systems now "
                        "depend on it). Reserve 'no' for true points of no return; flagging "
                        "everything as irreversible hides the genuinely risky moments. "
                        "Defaults to 'yes'."
                    ),
                    required=False,
                    default=_DEFAULT_REVERSIBLE,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "Your probability that this is the right branch, from 0.0 to 1.0, "
                        "one decimal. This is a forecast, not a feeling: 0.5 means a coin "
                        "flip, 0.8 means you expect to be right four times out of five. Low "
                        "confidence combined with reversible='no' is the riskiest "
                        "combination a run can make — if you find yourself there, say so "
                        "plainly rather than inflating the number."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the decision primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("decision", "chosen_because", "rejected"))
        if error:
            return ToolResult.error(call.tool_name, error)

        rejected, rejected_error = CotEventParser.parse_json_objects(
            args.get("rejected"), "rejected", _MAX_REJECTED_ALTERNATIVES
        )
        if rejected_error:
            return ToolResult.error(call.tool_name, rejected_error)
        reversible, reversible_error = CotEventParser.parse_enum(
            args.get("reversible"), REVERSIBILITY_LEVELS, "reversible"
        )
        if reversible_error:
            return ToolResult.error(call.tool_name, reversible_error)
        confidence = CotEventParser.parse_confidence(args.get("confidence"))

        self._counter += 1
        from vidbyte.context.primitives.cot_events import DecisionContextItem

        item = DecisionContextItem(
            primitive_id=self._next_primitive_id(),
            decision=str(args["decision"]).strip(),
            chosen_because=str(args["chosen_because"]).strip(),
            rejected=tuple(rejected or ()),
            reversible=reversible or _DEFAULT_REVERSIBLE,
            confidence=confidence,
        )
        return await self._record(
            item,
            call,
            {"reversible": item.reversible, "confidence": item.confidence, "rejected_count": len(item.rejected)},
        )


class AssumptionCheckTool(_CotEventToolBase):
    """Builtin tool that records reliance on an unverified assumption or the act of resolving one."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="assumption_check",
            description=(
                "Record the assumptions your current work silently depends on. An assumption "
                "is something you are proceeding as if true without having verified it — the "
                "migration already ran, the API is idempotent, the timestamp is UTC, the "
                "dev dataset resembles production. Call this with action='declared' when you "
                "catch yourself relying on something unverified, and call it again later "
                "with action='verified' or action='falsified' once you have checked it. "
                "Falsified assumptions are the single most common root cause of agent "
                "failures — this ledger makes the risk visible before it becomes an outage. "
                "Declare assumptions freely; a long ledger is diligence, not noise. What is "
                "dangerous is the assumption you never wrote down."
            ),
            parameters=(
                ToolParameter(
                    name="assumption",
                    type="string",
                    description=(
                        "What you are taking as true for now, in one sentence phrased as a "
                        "checkable fact: 'The production index on users.email already "
                        "exists', 'Retrying this endpoint will not duplicate the write'. "
                        "Reuse the exact same sentence when you later verify or falsify it "
                        "so the three records read as one thread."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "What kind of ledger event this is. Use exactly one of: 'declared' "
                        "(you are starting to rely on this assumption — record it before "
                        "building on it), 'verified' (you checked it and it holds — say how "
                        "in verification_step), 'falsified' (you checked it and it is "
                        "wrong — stop and revise the dependent work before continuing). "
                        "A 'falsified' entry is a commitment to change course, not just an "
                        "observation."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="impact_if_wrong",
                    type="string",
                    description=(
                        "How much of the current work breaks if this assumption turns out "
                        "false. Use exactly one of: 'fatal' (the result would be wrong or "
                        "corrupted and must be redone), 'major' (significant rework of some "
                        "finished steps), 'minor' (a small local fix). Judge the blast "
                        "radius honestly — this field is how a reader triages which "
                        "assumptions to verify first, and marking everything 'minor' "
                        "defeats that."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verification_step",
                    type="string",
                    description=(
                        "When action is 'verified' or 'falsified', one sentence on how you "
                        "checked: the query you ran, the file you opened, the call you "
                        "made. 'I am fairly confident' is not a verification step — name "
                        "the observation. Omit this field entirely when action is "
                        "'declared'."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the assumption ledger primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("assumption", "action", "impact_if_wrong"))
        if error:
            return ToolResult.error(call.tool_name, error)

        action, action_error = CotEventParser.parse_enum(args.get("action"), ASSUMPTION_ACTIONS, "action")
        if action_error:
            return ToolResult.error(call.tool_name, action_error)
        impact, impact_error = CotEventParser.parse_enum(args.get("impact_if_wrong"), IMPACT_LEVELS, "impact_if_wrong")
        if impact_error:
            return ToolResult.error(call.tool_name, impact_error)

        from vidbyte.context.primitives.cot_events import AssumptionCheckContextItem

        assumption = str(args["assumption"]).strip()
        item = AssumptionCheckContextItem(
            primitive_id=self.statement_primitive_id("assumption_check", assumption),
            assumption=assumption,
            action=action or ASSUMPTION_ACTIONS[0],
            impact_if_wrong=impact or IMPACT_LEVELS[1],
            verification_step=CotEventParser.optional_text(args.get("verification_step")),
        )
        return await self._record(item, call, {"action": item.action, "impact_if_wrong": item.impact_if_wrong})


class UncertaintyTool(_CotEventToolBase):
    """Builtin tool that records one calibration snapshot of next-step and on-track confidence."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="uncertainty",
            description=(
                "Take a two-second reading of where you stand: how confident are you in the "
                "very next action, and separately, how confident are you that the overall "
                "approach still reaches the goal. These are different questions and they "
                "come apart before failures — you can be certain the next step is executed "
                "correctly while the plan it serves is already doomed. Call this "
                "periodically (every few tool calls or at natural moments), and always call "
                "it when your gut says something is off even if you cannot articulate why. "
                "This call is deliberately cheap: no prose required, just two numbers and "
                "one word. Honest low numbers are more useful here than confident wrong "
                "ones — an inaccurate 0.9 is the most expensive value this tool can record."
            ),
            parameters=(
                ToolParameter(
                    name="next_step",
                    type="number",
                    description=(
                        "Probability the immediate next action you are about to take is the "
                        "correct action, from 0.0 to 1.0, one decimal. This is about "
                        "execution of the step itself — the call you are about to make, the "
                        "edit you are about to write — not about the plan. 0.5 means a coin "
                        "flip between doing this step and doing something else."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="on_track",
                    type="number",
                    description=(
                        "Probability that your overall current approach — the plan, not the "
                        "next step — still leads to a completed goal, from 0.0 to 1.0, one "
                        "decimal. If you have drifted into work you are no longer sure "
                        "serves the original request, this number should fall even while "
                        "next_step stays high. That divergence (high next-step confidence, "
                        "low on-track confidence) is the classic signature of a run that is "
                        "efficiently executing the wrong thing."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="progress",
                    type="string",
                    description=(
                        "One word for your velocity toward the goal. Use exactly one of: "
                        "'progressing' (each step is moving meaningfully closer), 'stalled' "
                        "(working but not getting closer — repeating checks, circling the "
                        "same problem, waiting without progress), 'regressing' (recent work "
                        "made things worse — you are undoing or fixing previously finished "
                        "steps). Be quick to report 'stalled' or 'regressing'; recognizing "
                        "a stall early is the entire point of this field."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="trigger",
                    type="string",
                    description=(
                        "Optional one-clause note on what prompted this reading right now — "
                        "'third failed retry', 'result contradicts the hypothesis', "
                        "'periodic check-in'. Leave empty for routine readings; fill it in "
                        "when something specific moved the numbers."
                    ),
                    required=False,
                    default="",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the uncertainty primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        next_step = CotEventParser.parse_confidence(args.get("next_step"))
        if next_step is None:
            return ToolResult.error(call.tool_name, "Field 'next_step' must be a number between 0.0 and 1.0.")
        on_track = CotEventParser.parse_confidence(args.get("on_track"))
        if on_track is None:
            return ToolResult.error(call.tool_name, "Field 'on_track' must be a number between 0.0 and 1.0.")

        progress, progress_error = CotEventParser.parse_enum(args.get("progress"), PROGRESS_STATES, "progress")
        if progress_error:
            return ToolResult.error(call.tool_name, progress_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_events import UncertaintyContextItem

        item = UncertaintyContextItem(
            primitive_id=self._next_primitive_id(),
            next_step=next_step,
            on_track=on_track,
            progress=progress or PROGRESS_STATES[0],
            trigger=str(args.get("trigger", "")).strip(),
        )
        return await self._record(
            item,
            call,
            {
                "next_step": item.next_step,
                "on_track": item.on_track,
                "divergence": round(item.on_track - item.next_step, 2),
                "progress": item.progress,
            },
        )


class BacktrackTool(_CotEventToolBase):
    """Builtin tool that records the abandonment of an approach and what survives it."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="backtrack",
            description=(
                "Record the moment you abandon an approach, branch, or line of "
                "investigation before it consumes more of the run. Use this immediately "
                "when you decide to change direction — not after. Backtracking is healthy "
                "and expected; what is unhealthy is a silent pivot that leaves no record of "
                "what was tried and why it failed, because the next iteration (or the next "
                "agent) will re-walk the same dead end. Every backtrack you record becomes "
                "a warning sign in the context window. If you notice you are abandoning "
                "something you previously returned to, that is a loop — record it and "
                "deliberately choose a third option instead of oscillating."
            ),
            parameters=(
                ToolParameter(
                    name="abandoning",
                    type="string",
                    description=(
                        "The approach being dropped, in one sentence specific enough to "
                        "recognize later: 'Scraping the HTML table for pricing data', "
                        "'Trying to infer the schema from error messages'. Name the "
                        "approach, not the task — 'the task' cannot be abandoned."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reason",
                    type="string",
                    description=(
                        "Why it is being dropped, in one clause. Use the most precise "
                        "cause you have: 'the endpoint rejects batch sizes above 50', 'two "
                        "hours of parsing produced 12% coverage', 'a simpler path appeared "
                        "in the docs'. 'Not working' is not a reason — say what failed."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="salvage",
                    type="string",
                    description=(
                        "What, if anything, carries forward from the abandoned work — "
                        "known constraints discovered, partial results, ruling out a "
                        "category of solutions. Abandoned approaches often buy "
                        "information; record it here so it is not thrown away with the "
                        "approach. Say 'nothing' only when nothing survives."
                    ),
                    required=False,
                    default=_DEFAULT_SALVAGE,
                ),
                ToolParameter(
                    name="returnable",
                    type="string",
                    description=(
                        "Whether this approach could sensibly be revisited later in this "
                        "run: 'yes' (it may become viable if circumstances change — an "
                        "upstream fix, new information) or 'no' (it is definitively ruled "
                        "out). Marking 'yes' is a note to your future self that the door "
                        "is open; marking 'no' prevents re-walking it. If you are "
                        "recording your second backtrack of the same thing, mark 'no'. "
                        "Defaults to 'yes'."
                    ),
                    required=False,
                    default=_DEFAULT_RETURNABLE,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the backtrack primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("abandoning", "reason"))
        if error:
            return ToolResult.error(call.tool_name, error)

        returnable, returnable_error = CotEventParser.parse_enum(
            args.get("returnable"), RETURNABLE_OPTIONS, "returnable"
        )
        if returnable_error:
            return ToolResult.error(call.tool_name, returnable_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_events import BacktrackContextItem

        item = BacktrackContextItem(
            primitive_id=self._next_primitive_id(),
            abandoning=str(args["abandoning"]).strip(),
            reason=str(args["reason"]).strip(),
            salvage=str(args.get("salvage", "")).strip() or _DEFAULT_SALVAGE,
            returnable=returnable or _DEFAULT_RETURNABLE,
        )
        return await self._record(item, call, {"returnable": item.returnable})


__all__ = [
    "AssumptionCheckTool",
    "BacktrackTool",
    "CotEventParser",
    "DecisionTool",
    "HypothesisTool",
    "UncertaintyTool",
]
