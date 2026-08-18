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
      assumptions and failures use fixed snapshot primitive ids.
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


ASSUMPTION_SERVICE_LEVELS = ("directly", "indirectly", "no")
RECONSIDER_LEVELS = ("none", "some", "core")
FAILURE_LIKELIHOODS = ("high", "medium", "low")
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
                "Commit to a falsifiable forecast about what will happen next in this run. "
                "Use this before taking an action whose outcome you are not certain of: "
                "call the endpoint and predict the response shape, run the migration and "
                "predict whether it completes, apply the fix and predict whether the test "
                "passes. A prediction is only useful when it could come out wrong — pair "
                "it with a trigger that will settle it, and give your honest probability, "
                "because the value of this record is calibration: a run whose confident "
                "predictions keep missing is drifting even while its outputs look busy. "
                "Do not predict certainties ('the tool will return'), and do not hedge "
                "with vague triggers ('at some point'). This is the cheapest self-check "
                "available to you: state the future, then watch it arrive."
            ),
            parameters=(
                ToolParameter(
                    name="predicts",
                    type="string",
                    description=(
                        "What you predict will happen, in one sentence phrased so it can "
                        "clearly come true or false: 'The search endpoint returns an empty "
                        "result set for this query', 'The test suite still fails after "
                        "this patch', 'The document does not mention rate limits'. Avoid "
                        "'may', 'might', or 'could' — commit to the outcome you actually "
                        "expect."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="by_when",
                    type="string",
                    description=(
                        "The observable trigger that resolves this prediction — the "
                        "specific action or moment after which anyone can judge it hit or "
                        "miss: 'when I call the endpoint in the next step', 'after running "
                        "the test suite this iteration', 'by the end of this run'. A "
                        "prediction without a resolution point is untestable and will not "
                        "help you; tie it to something concrete and near-term."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "Your probability the prediction comes true, from 0.0 to 1.0, one "
                        "decimal. This is a forecast, not a mood: 0.5 means a genuine coin "
                        "flip, 0.9 means you would be surprised to be wrong. If you catch "
                        "yourself writing 0.9 for everything, you are not forecasting — "
                        "reserve high numbers for outcomes whose failure would genuinely "
                        "surprise you."
                    ),
                    required=True,
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

        self._counter += 1
        from vidbyte.context.primitives.cot_events import PredictionContextItem

        item = PredictionContextItem(
            primitive_id=self._next_primitive_id(),
            predicts=str(args["predicts"]).strip(),
            by_when=str(args["by_when"]).strip(),
            confidence=confidence,
        )
        return await self._record(item, call, {"confidence": item.confidence})


class GoalCheckTool(_CotEventToolBase):
    """Builtin tool that records one attestation of whether current work still serves the original goal."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="goal_check",
            description=(
                "Stop for a moment and restate, word for word from the original request, "
                "what you were asked to do — then compare it to what you are actually "
                "doing right now. Use this when you notice you have been heads-down in "
                "detail for a while, when a subtask started growing its own subtasks, or "
                "any time you cannot remember the last time you looked at the actual "
                "request. Restating the goal verbatim is the test: if you cannot "
                "reproduce it exactly, you have already drifted, because detail work "
                "quietly rewrites your memory of the objective. Answer the alignment "
                "question honestly — 'indirectly' covers legitimate setup work, but a "
                "chain of three 'indirectly' answers in a row usually means 'no'. This "
                "check is the single cheapest defense against efficiently completing "
                "the wrong task."
            ),
            parameters=(
                ToolParameter(
                    name="original_goal",
                    type="string",
                    description=(
                        "The original request, restated word for word as it was given — "
                        "not summarized, not as currently understood, not narrowed to the "
                        "part you are working on. Copy it from the original message. If "
                        "you feel the urge to paraphrase, that urge is the drift signal "
                        "this tool exists to catch."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="current_activity",
                    type="string",
                    description=(
                        "What you are actually doing right now, in one sentence — the "
                        "specific step, not the nominal task: 'Refactoring the pagination "
                        "helper for the third time', 'Reading the fifth documentation "
                        "page about authentication'. Name it plainly, even if it sounds "
                        "small next to the goal."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="still_serves",
                    type="string",
                    description=(
                        "Whether the current activity still serves the original goal. Use "
                        "exactly one of: 'directly' (this activity produces part of the "
                        "requested result), 'indirectly' (it is setup or enabling work "
                        "the result depends on — be honest about how long the chain is), "
                        "'no' (it no longer moves toward the goal at all). When in doubt "
                        "between 'indirectly' and 'no', ask whether finishing this "
                        "activity would change anything the requester asked for."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="pivot_to",
                    type="string",
                    description=(
                        "When still_serves is 'no', one sentence on what you will do "
                        "instead — the activity that does serve the goal. This is a "
                        "commitment to change course, not a suggestion; leave it empty "
                        "only when still_serves is 'directly' or 'indirectly'."
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

        self._counter += 1
        from vidbyte.context.primitives.cot_events import GoalCheckContextItem

        item = GoalCheckContextItem(
            primitive_id=self._next_primitive_id(),
            original_goal=str(args["original_goal"]).strip(),
            current_activity=str(args["current_activity"]).strip(),
            still_serves=still_serves or ASSUMPTION_SERVICE_LEVELS[0],
            pivot_to=CotEventParser.optional_text(args.get("pivot_to")),
        )
        return await self._record(item, call, {"still_serves": item.still_serves})


class CounterfactualTool(_CotEventToolBase):
    """Builtin tool that records hindsight about a branch not taken."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="counterfactual",
            description=(
                "After an outcome arrives, record what you think would have happened on "
                "the branch you did not take. Use this when a result is informative "
                "either way — the fix worked and you want to note the cheaper path you "
                "skipped, or the approach failed and you want to record whether the "
                "alternative would have done better. One honest caveat belongs up front: "
                "this is your hindsight, not ground truth. You did not observe the other "
                "branch, so say what you actually believe and mark your confidence "
                "rather than presenting the guess as fact. These records are how later "
                "readers (and you, later in the run) learn whether your branch choices "
                "are systematically good — a pattern of 'the alternative would have "
                "failed too' claims that later prove wrong is itself a finding. Record "
                "the interesting branches, not every fork."
            ),
            parameters=(
                ToolParameter(
                    name="outcome",
                    type="string",
                    description=(
                        "What actually happened on the path you took, in one sentence "
                        "with the concrete result: 'The migration completed in 40 "
                        "minutes', 'The retry loop exhausted all six attempts'. State "
                        "the observed fact, not your evaluation of it."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="alternative",
                    type="string",
                    description=(
                        "The specific branch you did not take, named precisely enough to "
                        "recognize: 'Writing the batch migration script instead of "
                        "per-document updates', 'Asking the user for the schema up "
                        "front'. A vague 'trying something else' is not a branch."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="would_have",
                    type="string",
                    description=(
                        "Your honest prediction of what the alternative would have "
                        "produced, one sentence — including the possibility that it "
                        "would have been worse. This is a guess by definition; make it "
                        "a specific one and let confidence carry the uncertainty."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "How much you trust your would_have claim, 0.0 to 1.0, one "
                        "decimal. Most counterfactuals deserve modest numbers — you are "
                        "reasoning about something you never observed. A run full of "
                        "0.9-confidence counterfactuals is overconfident about its "
                        "unlived paths."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="lesson",
                    type="string",
                    description=(
                        "Optional one-clause takeaway that changes future branch "
                        "choices: 'prefer the scripted path when volume exceeds 10k'. "
                        "Leave empty when the counterfactual changes nothing going "
                        "forward — not every comparison needs a moral."
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

        self._counter += 1
        from vidbyte.context.primitives.cot_events import CounterfactualContextItem

        item = CounterfactualContextItem(
            primitive_id=self._next_primitive_id(),
            outcome=str(args["outcome"]).strip(),
            alternative=str(args["alternative"]).strip(),
            would_have=str(args["would_have"]).strip(),
            confidence=confidence,
            lesson=CotEventParser.optional_text(args.get("lesson")),
        )
        return await self._record(item, call, {"confidence": item.confidence})


class AssumptionsTool(_CotEventToolBase):
    """Builtin tool that snapshots every assumption the run currently proceeds under."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="assumptions",
            description=(
                "Dump the complete set of assumptions you are currently proceeding "
                "under — everything you are treating as true without having verified it. "
                "Use this at the start of a stage, after a significant discovery, or any "
                "time you suspect your mental load-bearing walls have quietly changed. "
                "List them all, not just the comfortable ones: environment facts ('the "
                "dev database resembles production'), tool behavior ('retries are "
                "idempotent'), scope judgments ('the user wants all endpoints, not just "
                "one'). The act of listing is the point — assumptions do their damage "
                "when they stay implicit, and a reader comparing consecutive snapshots "
                "can see exactly when your unverified foundation shifted. This tool "
                "replaces the previous snapshot, so it always reflects the current set."
            ),
            parameters=(
                ToolParameter(
                    name="assumptions",
                    type="string",
                    description=(
                        "A JSON array of 1 to 10 strings, each one assumption stated as "
                        "a single checkable fact: [\"The production index on users.email "
                        "exists\", \"Retrying this write will not duplicate the row\", "
                        "\"The dev fixture data is representative\"]. Do not pad the "
                        "list to look thorough and do not hide risky ones — an "
                        "assumption you are embarrassed to list is exactly the one that "
                        "belongs here most."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="scope",
                    type="string",
                    description=(
                        "Optional one-clause note on what part of the run these "
                        "assumptions concern — 'the migration stage', 'the whole run', "
                        "'the third-party API integration'. Leave empty for whole-run "
                        "snapshots."
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

        from vidbyte.context.primitives.cot_events import AssumptionsSnapshotContextItem

        item = AssumptionsSnapshotContextItem(
            primitive_id=ASSUMPTIONS_SNAPSHOT_ID,
            assumptions=tuple(entries),
            scope=CotEventParser.optional_text(args.get("scope")),
        )
        return await self._record(item, call, {"count": len(item.assumptions)})

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
                "Run a premortem on the current stage: assume your next few steps have "
                "already failed, and list the concrete things that could have caused it. "
                "Use this before committing to an approach, before an irreversible "
                "action, or whenever the run has been smooth for suspiciously long — "
                "complacency is where the expensive failures hide. Name specific "
                "mechanisms, not vague worries: 'the batch write times out because the "
                "collection has no covering index', not 'something might break'. The "
                "high-likelihood entries with no mitigation are your action items; the "
                "act of writing them down is what turns them from surprises into "
                "choices. This tool replaces the previous scan, so it always reflects "
                "the current stage's risks."
            ),
            parameters=(
                ToolParameter(
                    name="failures",
                    type="string",
                    description=(
                        "A JSON array of 1 to 5 objects, each with keys 'failure' (the "
                        "specific thing that could go wrong), 'likelihood' (exactly one "
                        "of 'high', 'medium', 'low'), and optionally 'mitigation' (one "
                        "clause on what prevents or limits it). Example: "
                        "[{\"failure\": \"Rate limit hits during backfill\", "
                        "\"likelihood\": \"high\", \"mitigation\": \"throttle to 100 "
                        "writes/sec\"}]. Rank honestly — listing everything as 'low' to "
                        "stay comfortable defeats the entire purpose."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="stage",
                    type="string",
                    description=(
                        "Optional one-clause description of the stage this scan covers: "
                        "'backfilling the audit collection', 'final output assembly'. "
                        "Leave empty if the scan covers the immediate next steps "
                        "generally."
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

        from vidbyte.context.primitives.cot_events import FailureScanContextItem

        item = FailureScanContextItem(
            primitive_id=FAILURE_SCAN_SNAPSHOT_ID,
            failures=tuple(entries),
            stage=CotEventParser.optional_text(args.get("stage")),
        )
        likelihoods = tuple(str(entry.get("likelihood", _DEFAULT_FAILURE_LIKELIHOOD)) for entry in item.failures)
        return await self._record(item, call, {"failure_count": len(item.failures), "likelihoods": likelihoods})

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
                "Stop and reconstruct the reasoning behind what you have done so far — "
                "not what you did (the tool log already shows that), but why each "
                "meaningful step seemed necessary at the time. Use this at natural "
                "milestones, when the run feels like it is accumulating steps without a "
                "spine, or when you catch yourself unable to say why the last three "
                "actions were needed. Explain the actual rationale: what problem each "
                "choice solved and what it was guarding against. Then answer the "
                "reconsider question honestly — examining your own why sometimes "
                "reveals that a step (or the whole direction) no longer makes sense, "
                "and saying so here is the point of the tool, not a failure. A run that "
                "cannot reconstruct its own reasons has been operating on momentum."
            ),
            parameters=(
                ToolParameter(
                    name="why",
                    type="string",
                    description=(
                        "The rationale for the actions taken so far, as connected prose: "
                        "the goal each meaningful step served, why it came before the "
                        "next one, and what each choice traded away. Do not re-list the "
                        "actions — a reader can see those. Explain the reasons. If you "
                        "find a step you cannot justify, describe the honest gap "
                        "instead of papering over it."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reconsider",
                    type="string",
                    description=(
                        "What examining your rationale revealed. Use exactly one of: "
                        "'none' (the rationale holds — every step still serves the "
                        "goal), 'some' (one named step should change or be dropped), "
                        "'core' (the foundational rationale is wrong — the overall "
                        "approach needs rethinking, not just a step). Be quick to say "
                        "'some'; it is cheap. Reserve 'core' for when the reasoning "
                        "genuinely collapses — and when it does, say it plainly."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="change",
                    type="string",
                    description=(
                        "When reconsider is 'some' or 'core', one to two sentences on "
                        "what you will do differently now that the rationale has been "
                        "re-examined. This is a commitment to act on the finding. Leave "
                        "empty when reconsider is 'none'."
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

        self._counter += 1
        from vidbyte.context.primitives.cot_events import WhyContextItem

        item = WhyContextItem(
            primitive_id=self._next_primitive_id(),
            why=str(args["why"]).strip(),
            reconsider=reconsider or RECONSIDER_LEVELS[0],
            change=CotEventParser.optional_text(args.get("change")),
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
