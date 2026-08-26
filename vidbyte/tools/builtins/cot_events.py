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
      string/object arrays, and required text fields.
    - HypothesisTool, DecisionTool, AssumptionCheckTool, UncertaintyTool,
      BacktrackTool: batch-1 event tools that validate, upsert a matching
      context primitive, and return parsed values in ToolResult.metadata.
    - PredictionTool, GoalCheckTool, CounterfactualTool, AssumptionsTool,
      FailuresTool, WhyTool: batch-2 monitoring tools in the same shape;
      assumptions and failures use fixed snapshot primitive ids. Batch-2's
      categorical fields are sourced from vidbyte.lib.enums.cot; batch-1's
      remain inline pending its own review-comment resolution.
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
    def parse_int(value: Any, minimum: int = 0) -> int | None:
        # Coerces a number or numeric string to an int at or above minimum, or None on failure.
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        try:
            number = int(float(str(value).strip()))
        except (ValueError, TypeError):
            return None
        return max(minimum, number)

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
    def parse_json_strings(value: Any, field_name: str, max_items: int) -> tuple[list[str] | None, str | None]:
        # Parses a JSON string (or list) into a list of at most max_items strings, returning (parsed, error).
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
        if not isinstance(parsed, list) or not all(isinstance(entry, str) for entry in parsed):
            return None, f"Field '{field_name}' must be a JSON array of strings."
        if not parsed:
            return None, f"Field '{field_name}' must contain at least one string."
        return [str(entry).strip() for entry in parsed[:max_items]], None

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


from vidbyte.lib.enums.cot import (
    AssumptionRiskLevel,
    FailureLikelihood,
    FailureScanRisk,
    GoalServiceLevel,
    PredictionCategory,
    ReconsiderLevel,
    Severity as _Severity,
    YesNo as _YesNo,
)

ASSUMPTION_SERVICE_LEVELS = tuple(level.value for level in GoalServiceLevel)
RECONSIDER_LEVELS = tuple(level.value for level in ReconsiderLevel)
FAILURE_LIKELIHOODS = tuple(level.value for level in FailureLikelihood)
PREDICTION_STAKES_LEVELS = tuple(level.value for level in _Severity)
PREDICTION_CATEGORIES = tuple(category.value for category in PredictionCategory)
ASSUMPTION_RISK_LEVELS = tuple(level.value for level in AssumptionRiskLevel)
FAILURE_SCAN_RISK_LEVELS = tuple(level.value for level in FailureScanRisk)
REVERSIBLE_OPTIONS = tuple(option.value for option in _YesNo)
FAILURE_SCAN_BLOCKING_OPTIONS = tuple(option.value for option in _YesNo)
_MAX_ASSUMPTIONS = 10
_MAX_FAILURES = 5
_DEFAULT_FAILURE_LIKELIHOOD = "medium"
ASSUMPTIONS_SNAPSHOT_ID = "assumptions:current"
FAILURE_SCAN_SNAPSHOT_ID = "failures:current"


class PredictionTool(_CotEventToolBase):
    """Builtin tool that records one forward-looking, falsifiable forecast with a resolution trigger."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="prediction",
            description=(
                "Commit to a falsifiable forecast about what will happen next in the "
                "run, before taking an action whose outcome is not yet certain. A "
                "prediction is only useful when it could turn out wrong, so it should "
                "be paired with an observable trigger that will settle it and an "
                "honest probability rather than a vague hedge. The value of this "
                "record is calibration over time: a run whose confident predictions "
                "keep missing is drifting even while its outputs look busy, and that "
                "pattern is invisible without a running record of what was predicted "
                "versus what actually happened. State the future plainly and commit "
                "to it, then let the trigger settle the matter rather than revisiting "
                "the wording after the fact."
            ),
            parameters=(
                ToolParameter(
                    name="predicts",
                    type="string",
                    description=(
                        "What is predicted to happen, phrased as a single statement "
                        "that could clearly turn out true or false. A prediction "
                        "hedged with qualifiers like 'may' or 'might' is not "
                        "committing to anything checkable, so this field should "
                        "commit to the outcome actually expected rather than "
                        "describing a range of possibilities."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="by_when",
                    type="string",
                    description=(
                        "The observable trigger that resolves this prediction — the "
                        "specific action or moment after which the outcome can be "
                        "judged a hit or a miss. A prediction without a concrete, "
                        "near-term resolution point is effectively untestable, so "
                        "this field should tie the forecast to something that will "
                        "actually happen rather than an indefinite future."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "The probability the prediction comes true, expressed as a "
                        "number between zero and one. This should function as a "
                        "genuine forecast rather than a mood: a value near a coin "
                        "flip reflects real uncertainty, and reserving high values "
                        "for outcomes whose failure would be genuinely surprising is "
                        "what keeps this number meaningful across many predictions."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="stakes",
                    type="string",
                    description=(
                        "An optional rating of the consequence if this prediction "
                        "turns out wrong, ranging from purely cosmetic through minor, "
                        "major, critical, and fatal. This field lets a reader "
                        "prioritize which predictions most deserve attention when "
                        "they resolve, since a missed high-stakes prediction and a "
                        "missed low-stakes one carry very different weight."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="basis",
                    type="string",
                    description=(
                        "An optional statement of what the prediction is actually "
                        "grounded in, such as a pattern observed earlier in the run "
                        "or a stated assumption about how a system behaves. This "
                        "field separates a forecast rooted in evidence from one "
                        "rooted in general expectation, which matters when judging "
                        "calibration after the fact."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="category",
                    type="string",
                    description=(
                        "An optional classification of what kind of outcome this "
                        "prediction concerns, distinguishing a tool result, a test "
                        "result, a user response, a broader system behavior, and an "
                        "uncategorized other. Grouping predictions by category makes "
                        "it possible to see whether calibration differs across kinds "
                        "of forecast rather than only in the aggregate."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the prediction primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("predicts", "by_when"))
        if error:
            return ToolResult.error(call.tool_name, error)

        confidence = CotEventParser.parse_confidence(args.get("confidence"))
        if confidence is None:
            return ToolResult.error(call.tool_name, "Field 'confidence' must be a number between 0.0 and 1.0.")
        stakes, stakes_error = CotEventParser.parse_enum(args.get("stakes"), PREDICTION_STAKES_LEVELS, "stakes")
        if stakes_error:
            return ToolResult.error(call.tool_name, stakes_error)
        category, category_error = CotEventParser.parse_enum(args.get("category"), PREDICTION_CATEGORIES, "category")
        if category_error:
            return ToolResult.error(call.tool_name, category_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_events import PredictionContextItem

        item = PredictionContextItem(
            primitive_id=self._next_primitive_id(),
            predicts=str(args["predicts"]).strip(),
            by_when=str(args["by_when"]).strip(),
            confidence=confidence,
            stakes=stakes,
            basis=CotEventParser.optional_text(args.get("basis")),
            category=category,
        )
        return await self._record(item, call, {"confidence": item.confidence})


class GoalCheckTool(_CotEventToolBase):
    """Builtin tool that records one attestation of whether current work still serves the original goal."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="goal_check",
            description=(
                "Restate the original request word for word and compare it directly "
                "against what is actually being done right now. This is worth doing "
                "whenever a subtask has been growing its own subtasks, or whenever it "
                "has been a while since the actual request was last looked at rather "
                "than a working summary of it. Restating the goal verbatim is itself "
                "the test: an inability to reproduce it exactly is a sign that drift "
                "has already occurred, since detail work quietly rewrites memory of "
                "the objective over time. The alignment verdict should be answered "
                "honestly rather than charitably, since a string of indirect answers "
                "in a row usually amounts to a no in practice, and this check is one "
                "of the cheapest available defenses against efficiently completing "
                "the wrong task."
            ),
            parameters=(
                ToolParameter(
                    name="original_goal",
                    type="string",
                    description=(
                        "The original request, restated word for word as it was given "
                        "rather than summarized, reinterpreted, or narrowed to the "
                        "part currently being worked on. Any urge to paraphrase while "
                        "filling in this field is itself the drift signal this tool "
                        "exists to catch."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="current_activity",
                    type="string",
                    description=(
                        "The specific step actually being performed right now, named "
                        "plainly rather than described as the nominal task it "
                        "notionally belongs to. This should reflect the real, "
                        "granular activity even when it sounds small next to the "
                        "stated goal."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="still_serves",
                    type="string",
                    description=(
                        "Whether the current activity still serves the original goal, "
                        "distinguishing activity that directly produces part of the "
                        "requested result, activity that is legitimate setup or "
                        "enabling work the result depends on, activity only "
                        "tangentially related to the goal, a genuinely unclear case, "
                        "and activity that no longer moves toward the goal at all. "
                        "When uncertain between adjacent categories, the deciding "
                        "question is whether finishing the activity would change "
                        "anything the requester actually asked for."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="pivot_to",
                    type="string",
                    description=(
                        "Required whenever the current activity no longer serves the "
                        "goal: a description of what will be done instead. This is a "
                        "commitment to change course rather than a suggestion, and "
                        "should be left empty only when the activity is still "
                        "assessed as serving the goal in some form."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="drift_cause",
                    type="string",
                    description=(
                        "An optional account of what actually caused the drift, when "
                        "the alignment verdict indicates any. Naming the cause, such "
                        "as an ambiguous instruction that got over-interpreted or an "
                        "interesting tangent that was followed too far, is what "
                        "prevents the same drift pattern from recurring later in the "
                        "same run."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="steps_since_last_check",
                    type="number",
                    description=(
                        "An optional non-negative integer counting how many steps "
                        "have elapsed since the previous goal check. A large or "
                        "growing gap between checks is itself informative, since "
                        "drift compounds the longer it goes unexamined."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the goal check primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("original_goal", "current_activity", "still_serves"))
        if error:
            return ToolResult.error(call.tool_name, error)

        still_serves, serves_error = CotEventParser.parse_enum(
            args.get("still_serves"), ASSUMPTION_SERVICE_LEVELS, "still_serves"
        )
        if serves_error:
            return ToolResult.error(call.tool_name, serves_error)
        steps_since_last_check = CotEventParser.parse_int(args.get("steps_since_last_check"))

        self._counter += 1
        from vidbyte.context.primitives.cot_events import GoalCheckContextItem

        item = GoalCheckContextItem(
            primitive_id=self._next_primitive_id(),
            original_goal=str(args["original_goal"]).strip(),
            current_activity=str(args["current_activity"]).strip(),
            still_serves=still_serves or ASSUMPTION_SERVICE_LEVELS[0],
            pivot_to=CotEventParser.optional_text(args.get("pivot_to")),
            drift_cause=CotEventParser.optional_text(args.get("drift_cause")),
            steps_since_last_check=steps_since_last_check,
        )
        return await self._record(item, call, {"still_serves": item.still_serves})


class CounterfactualTool(_CotEventToolBase):
    """Builtin tool that records hindsight about a branch not taken."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="counterfactual",
            description=(
                "After an outcome arrives, record what would likely have happened on "
                "the branch that was not taken. This is worth doing whenever the "
                "result is informative either way, whether an approach succeeded and "
                "a cheaper skipped path is worth noting, or an approach failed and "
                "the alternative might plausibly have done better. The central "
                "caveat is that this is hindsight rather than ground truth, since the "
                "other branch was never actually observed, so the claim should be "
                "stated as a genuine belief and paired with a confidence level rather "
                "than presented as settled fact. Read across many of these records, "
                "the pattern reveals whether branch choices have been systematically "
                "good, which is not visible from any single instance; only the "
                "interesting branches deserve a record, not every fork encountered."
            ),
            parameters=(
                ToolParameter(
                    name="outcome",
                    type="string",
                    description=(
                        "What actually happened on the path that was taken, stated as "
                        "the observed, concrete result rather than an evaluation of "
                        "whether it was good or bad."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="alternative",
                    type="string",
                    description=(
                        "The specific branch that was not taken, named precisely "
                        "enough to be recognizable as a genuine alternative rather "
                        "than a vague notion of trying something else."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="would_have",
                    type="string",
                    description=(
                        "An honest prediction of what the alternative branch would "
                        "have produced, including the genuine possibility that it "
                        "would have been worse than the path actually taken. This is "
                        "a guess by definition, so it should be a specific one, with "
                        "the accompanying confidence field carrying the actual "
                        "uncertainty rather than the wording being hedged."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "How much this counterfactual claim is actually trusted, "
                        "expressed as a number between zero and one. Most "
                        "counterfactuals deserve modest values, since they reason "
                        "about a path that was never directly observed, and a "
                        "pattern of consistently high confidence across many of these "
                        "records is itself a sign of overconfidence about unlived "
                        "paths."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="lesson",
                    type="string",
                    description=(
                        "An optional takeaway that would change future branch "
                        "choices in similar situations. This should be left empty "
                        "when the counterfactual does not actually change anything "
                        "going forward, since not every comparison needs a moral "
                        "attached to it."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="reversible",
                    type="string",
                    description=(
                        "An optional statement of whether the untaken alternative is "
                        "still reachable now, expressed as yes or no. This "
                        "distinguishes a purely retrospective comparison from one "
                        "where switching to the alternative is still a live option "
                        "worth actually considering."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the counterfactual primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("outcome", "alternative", "would_have"))
        if error:
            return ToolResult.error(call.tool_name, error)

        confidence = CotEventParser.parse_confidence(args.get("confidence"))
        reversible, reversible_error = CotEventParser.parse_enum(args.get("reversible"), REVERSIBLE_OPTIONS, "reversible")
        if reversible_error:
            return ToolResult.error(call.tool_name, reversible_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_events import CounterfactualContextItem

        item = CounterfactualContextItem(
            primitive_id=self._next_primitive_id(),
            outcome=str(args["outcome"]).strip(),
            alternative=str(args["alternative"]).strip(),
            would_have=str(args["would_have"]).strip(),
            confidence=confidence,
            lesson=CotEventParser.optional_text(args.get("lesson")),
            reversible=reversible,
        )
        return await self._record(item, call, {"confidence": item.confidence})


class AssumptionsTool(_CotEventToolBase):
    """Builtin tool that snapshots every assumption the run currently proceeds under."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="assumptions",
            description=(
                "Record the complete set of assumptions currently being treated as "
                "true without having actually been verified. This is worth doing at "
                "the start of a stage, after a significant discovery, or any time "
                "there is a suspicion that the mental load-bearing walls of the run "
                "have quietly changed. Every assumption should be listed, not only "
                "the comfortable ones, since environment facts, tool behavior, and "
                "scope judgments all belong in the same net; listing is the entire "
                "point, because assumptions do their damage while they remain "
                "implicit. A reader comparing two consecutive snapshots can see "
                "exactly when the unverified foundation shifted, which is the "
                "primary value of this tool over time. Each call replaces the "
                "previous snapshot, so it always reflects the current set."
            ),
            parameters=(
                ToolParameter(
                    name="assumptions",
                    type="string",
                    description=(
                        "A JSON array of one to ten strings, each one assumption "
                        "stated as a single checkable fact rather than a vague area "
                        "of uncertainty. The list should not be padded to look "
                        "thorough, and it should not omit the assumptions that would "
                        "be uncomfortable to admit to, since those are exactly the "
                        "ones most worth surfacing."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="scope",
                    type="string",
                    description=(
                        "An optional note on what part of the run these assumptions "
                        "concern, such as a particular stage rather than the run as "
                        "a whole. This should be left empty when the snapshot is "
                        "meant to cover the entire run rather than one bounded "
                        "portion of it."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="risk_level",
                    type="string",
                    description=(
                        "An optional overall risk rating for the current set of "
                        "assumptions taken together, ranging from negligible through "
                        "low, medium, high, and critical. This field summarizes the "
                        "combined exposure of the list rather than any single "
                        "assumption, which the individual entries do not capture on "
                        "their own."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="verified_count",
                    type="number",
                    description=(
                        "An optional non-negative integer counting how many of the "
                        "listed assumptions have actually been checked rather than "
                        "simply carried forward unexamined. A low ratio of verified "
                        "to total assumptions is itself a useful signal about how "
                        "much of the run's foundation remains untested."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="confidence_in_completeness",
                    type="number",
                    description=(
                        "An optional number between zero and one expressing "
                        "confidence that this list actually captures every active "
                        "assumption rather than missing some. A low value here is an "
                        "honest signal that further reflection before acting may be "
                        "warranted."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="last_changed",
                    type="string",
                    description=(
                        "An optional description of what changed in this list "
                        "relative to the previous snapshot, such as an assumption "
                        "being dropped once it was verified or a new one being "
                        "added after a discovery. This turns a single snapshot into "
                        "a visible trajectory rather than an isolated point."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the assumptions snapshot primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        entries, entries_error = self._parse_assumption_entries(args.get("assumptions"))
        if entries_error:
            return ToolResult.error(call.tool_name, entries_error)
        risk_level, risk_level_error = CotEventParser.parse_enum(args.get("risk_level"), ASSUMPTION_RISK_LEVELS, "risk_level")
        if risk_level_error:
            return ToolResult.error(call.tool_name, risk_level_error)
        verified_count = CotEventParser.parse_int(args.get("verified_count"))
        confidence_in_completeness = CotEventParser.parse_confidence(args.get("confidence_in_completeness"))

        from vidbyte.context.primitives.cot_events import AssumptionsSnapshotContextItem

        item = AssumptionsSnapshotContextItem(
            primitive_id=ASSUMPTIONS_SNAPSHOT_ID,
            assumptions=tuple(entries),
            scope=CotEventParser.optional_text(args.get("scope")),
            risk_level=risk_level,
            verified_count=verified_count,
            confidence_in_completeness=confidence_in_completeness,
            last_changed=CotEventParser.optional_text(args.get("last_changed")),
        )
        return await self._record(item, call, {"count": len(item.assumptions), "risk_level": item.risk_level})

    def _parse_assumption_entries(self, value: Any) -> tuple[list[str] | None, str | None]:
        # Parses the assumptions JSON array into 1-10 non-empty stripped strings.
        parsed, error = CotEventParser.parse_json_strings(value, "assumptions", _MAX_ASSUMPTIONS)
        if error:
            return None, error
        entries = [str(entry).strip() for entry in parsed or ()]
        entries = [entry for entry in entries if entry]
        if not entries:
            return None, "Field 'assumptions' must contain at least one non-empty string."
        return entries, None


class FailuresTool(_CotEventToolBase):
    """Builtin tool that snapshots what could currently go wrong at this stage of the run."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="failures",
            description=(
                "Run a premortem on the current stage by assuming the next few steps "
                "have already failed and listing the concrete things that could have "
                "caused it. This is worth doing before committing to an approach, "
                "before an irreversible action, or whenever the run has been smooth "
                "for a suspiciously long stretch, since complacency is exactly where "
                "expensive failures tend to hide. Specific mechanisms should be named "
                "rather than vague worries, since a named mechanism can actually be "
                "mitigated while a vague worry cannot. The high-likelihood entries "
                "left without mitigation are the real action items here, and the act "
                "of writing them down is what turns them from surprises into "
                "choices. Each call replaces the previous scan, so it always "
                "reflects the current stage's risks rather than an earlier one."
            ),
            parameters=(
                ToolParameter(
                    name="failures",
                    type="string",
                    description=(
                        "A JSON array of one to five objects, each with a 'failure' "
                        "key naming the specific thing that could go wrong, a "
                        "'likelihood' key rating how probable it is, and an optional "
                        "'mitigation' key describing what prevents or limits it. "
                        "Ranking should be honest; marking everything as low "
                        "likelihood to stay comfortable defeats the purpose of "
                        "running a premortem in the first place."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="stage",
                    type="string",
                    description=(
                        "An optional description of the stage this scan covers. This "
                        "should be left empty when the scan is meant to cover the "
                        "immediate next steps generally rather than one specifically "
                        "named phase of the run."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="overall_risk",
                    type="string",
                    description=(
                        "An optional overall risk verdict for the current scan taken "
                        "as a whole, ranging from healthy through watchful, elevated, "
                        "severe, and critical. This summarizes the combined exposure "
                        "of the listed failures rather than describing any single "
                        "entry."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="blocking",
                    type="string",
                    description=(
                        "An optional statement of whether any high-likelihood entry "
                        "in this scan still lacks a mitigation, expressed as yes or "
                        "no. A yes here identifies an actual action item rather than "
                        "a scan that has been reviewed and accepted as is."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "An optional number between zero and one expressing "
                        "confidence that this scan actually covers the real risks of "
                        "the current stage rather than missing significant ones. A "
                        "low value here is an honest signal that the scan may be "
                        "incomplete."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="previous_delta",
                    type="string",
                    description=(
                        "An optional description of what changed in this scan "
                        "relative to the previous one, such as a risk being retired "
                        "after mitigation or a new one surfacing after a discovery. "
                        "This turns a single scan into a visible trajectory rather "
                        "than an isolated snapshot."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the failure scan primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        entries, entries_error = self._parse_failure_entries(args.get("failures"))
        if entries_error:
            return ToolResult.error(call.tool_name, entries_error)
        overall_risk, overall_risk_error = CotEventParser.parse_enum(
            args.get("overall_risk"), FAILURE_SCAN_RISK_LEVELS, "overall_risk"
        )
        if overall_risk_error:
            return ToolResult.error(call.tool_name, overall_risk_error)
        blocking, blocking_error = CotEventParser.parse_enum(args.get("blocking"), FAILURE_SCAN_BLOCKING_OPTIONS, "blocking")
        if blocking_error:
            return ToolResult.error(call.tool_name, blocking_error)
        confidence = CotEventParser.parse_confidence(args.get("confidence"))

        from vidbyte.context.primitives.cot_events import FailureScanContextItem

        item = FailureScanContextItem(
            primitive_id=FAILURE_SCAN_SNAPSHOT_ID,
            failures=tuple(entries),
            stage=CotEventParser.optional_text(args.get("stage")),
            overall_risk=overall_risk,
            blocking=blocking,
            confidence=confidence,
            previous_delta=CotEventParser.optional_text(args.get("previous_delta")),
        )
        likelihoods = tuple(str(entry.get("likelihood", _DEFAULT_FAILURE_LIKELIHOOD)) for entry in item.failures)
        return await self._record(
            item,
            call,
            {"failure_count": len(item.failures), "likelihoods": likelihoods, "overall_risk": item.overall_risk},
        )

    def _parse_failure_entries(self, value: Any) -> tuple[list[dict] | None, str | None]:
        # Parses the failures JSON array, validating each entry's failure key and likelihood.
        parsed, error = CotEventParser.parse_json_objects(value, "failures", _MAX_FAILURES)
        if error:
            return None, error
        entries: list[dict] = []
        for index, entry in enumerate(parsed or ()):
            failure = str(entry.get("failure", "") or "").strip()
            if not failure:
                return None, f"Entry {index} in 'failures' is missing a non-empty 'failure' key."
            likelihood, likelihood_error = CotEventParser.parse_enum(
                entry.get("likelihood"), FAILURE_LIKELIHOODS, f"failures[{index}].likelihood"
            )
            if likelihood_error:
                return None, likelihood_error
            normalized = dict(entry)
            normalized["failure"] = failure
            normalized["likelihood"] = likelihood or _DEFAULT_FAILURE_LIKELIHOOD
            entries.append(normalized)
        if not entries:
            return None, "Field 'failures' must contain at least one object."
        return entries, None


class WhyTool(_CotEventToolBase):
    """Builtin tool that records a retrospective on why the actions taken so far were taken."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="why",
            description=(
                "Reconstruct the reasoning behind the actions taken so far, focusing "
                "on why each meaningful step seemed necessary at the time rather than "
                "restating what was done, which the tool log already shows. This is "
                "worth doing at natural milestones, whenever the run feels like it is "
                "accumulating steps without a clear spine, or upon noticing an "
                "inability to say why the last few actions were actually needed. The "
                "rationale should explain what problem each choice actually solved "
                "and what it was guarding against, not merely narrate the sequence of "
                "events. Examining a rationale honestly can reveal that a step, or "
                "the whole direction, no longer makes sense, and surfacing that "
                "finding is the entire point of this tool rather than a mark against "
                "it; a run that cannot reconstruct its own reasons has been operating "
                "on momentum alone."
            ),
            parameters=(
                ToolParameter(
                    name="why",
                    type="string",
                    description=(
                        "The rationale for the actions taken so far, written as "
                        "connected reasoning about the goal each meaningful step "
                        "served and what it traded away, rather than a re-listing of "
                        "the actions themselves. A step that genuinely cannot be "
                        "justified should be described as an honest gap rather than "
                        "papered over with a plausible-sounding reason."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reconsider",
                    type="string",
                    description=(
                        "What examining the rationale actually revealed, "
                        "distinguishing a rationale that fully holds, one with a "
                        "minor issue worth noting, one where a specific named step "
                        "should change or be dropped, one where the foundational "
                        "reasoning itself is wrong, and one where the entire approach "
                        "needs rethinking from the ground up. Naming a smaller issue "
                        "should not be avoided out of reluctance to admit it; the "
                        "more severe categories should be reserved for cases where "
                        "the reasoning genuinely collapses."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="change",
                    type="string",
                    description=(
                        "Required whenever reconsider indicates anything short of a "
                        "fully holding rationale: what will actually be done "
                        "differently now that the rationale has been re-examined. "
                        "This field is a commitment to act on the finding, not merely "
                        "an acknowledgment of it."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="trigger",
                    type="string",
                    description=(
                        "An optional description of what actually prompted this "
                        "retrospective, such as reaching a natural milestone or "
                        "noticing an inability to justify recent steps. Knowing the "
                        "trigger helps a later reader distinguish routine reflection "
                        "from a retrospective prompted by a specific concern."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="steps_covered",
                    type="number",
                    description=(
                        "An optional non-negative integer counting how many prior "
                        "steps this retrospective actually accounts for. This gives "
                        "the rationale an explicit scope rather than leaving it "
                        "ambiguous how far back the reasoning extends."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="confidence_in_rationale",
                    type="number",
                    description=(
                        "An optional number between zero and one expressing "
                        "confidence in the reconstructed rationale itself. A low "
                        "value here is an honest signal that the reasoning behind "
                        "recent steps is not actually well understood, even before "
                        "the reconsider verdict is reached."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the why retrospective primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("why", "reconsider"))
        if error:
            return ToolResult.error(call.tool_name, error)

        reconsider, reconsider_error = CotEventParser.parse_enum(
            args.get("reconsider"), RECONSIDER_LEVELS, "reconsider"
        )
        if reconsider_error:
            return ToolResult.error(call.tool_name, reconsider_error)
        steps_covered = CotEventParser.parse_int(args.get("steps_covered"))
        confidence_in_rationale = CotEventParser.parse_confidence(args.get("confidence_in_rationale"))

        self._counter += 1
        from vidbyte.context.primitives.cot_events import WhyContextItem

        item = WhyContextItem(
            primitive_id=self._next_primitive_id(),
            why=str(args["why"]).strip(),
            reconsider=reconsider or RECONSIDER_LEVELS[0],
            change=CotEventParser.optional_text(args.get("change")),
            trigger=CotEventParser.optional_text(args.get("trigger")),
            steps_covered=steps_covered,
            confidence_in_rationale=confidence_in_rationale,
        )
        return await self._record(item, call, {"reconsider": item.reconsider})


__all__ = [
    "AssumptionCheckTool",
    "AssumptionsTool",
    "BacktrackTool",
    "CotEventParser",
    "CounterfactualTool",
    "DecisionTool",
    "FailuresTool",
    "GoalCheckTool",
    "HypothesisTool",
    "PredictionTool",
    "UncertaintyTool",
    "WhyTool",
]
