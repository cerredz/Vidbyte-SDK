"""Context Protocol Header

FILE: vidbyte/tools/builtins/cot_events.py

PURPOSE: Implements the five model-callable deep chain-of-thought event tools.
Each tool validates a structured cognitive event, builds one bounded context
primitive, upserts it into the injected ContextManager, and returns the
rendered event plus parsed observability metadata. This file owns tool-facing
validation and orchestration, not the shared event vocabulary or primitive
rendering.

ROLE IN CODEBASE: Agents register these tools through
`vidbyte/tools/builtins/__init__.py`. The tool classes call
`vidbyte/lib/enums/cot_events.py` for categorical values,
`vidbyte/lib/constants/cot_events.py` for bounds and defaults, and
`vidbyte/context/primitives/cot_events.py` for the immutable records they
upsert. The ContextManager owns registry placement and frozen-record policy.

ARCHITECTURE NOTE: This is the model-facing boundary for atomic reasoning
telemetry. `CotEventParser` centralizes coercion so the five event tools share
one validation contract, while `_CotEventToolBase` centralizes ledger identity,
counter IDs, and ContextManager error handling. The design rationale is in
`docs/design/deep-cot-tools.md`.

FUNCTION INVENTORY: `CotEventParser` validates required text, enum values,
confidence values, optional text, and rejected-alternative JSON. The five
`*Tool.spec()` methods return ToolSpec declarations; the five `*Tool.execute()`
methods accept ToolCall and return ToolResult after one upsert or a diagnostic
error. `_CotEventToolBase.statement_primitive_id()` creates deterministic
ledger IDs, `_next_primitive_id()` creates append-only IDs, and `_record()`
performs the ContextManager write. No method intentionally raises for ordinary
bad model input; ContextManager ValueError is converted into ToolResult.error.

COMMON MODIFICATION PATTERNS: Add categorical values in
`vidbyte/lib/enums/cot_events.py`, shared defaults in
`vidbyte/lib/constants/cot_events.py`, fields in both the matching tool spec
and primitive dataclass, then update the design document and smoke checks.
Keep ledger identity fields stable when adding optional descriptive fields.

WHAT NOT TO DO IN THIS FILE:
1. Do not define a second copy of an enum, default, or numeric bound; the
   `vidbyte.lib` modules are the shared source of truth.
2. Do not render primitive text here; renderers belong to
   `vidbyte/context/primitives/cot_events.py`.
3. Do not place persistence, provider calls, or agent-loop scheduling in a
   model-facing builtin.
4. Do not silently accept malformed rejected-alternative entries; the parser
   must preserve the structured contract exposed by the tool description.

KNOWN EDGE CASES: Enum input is normalized case-insensitively to its canonical
serialized value. Optional confidence values that cannot be parsed become
None, while required uncertainty confidences return a ToolResult.error. The
hypothesis and assumption ledgers hash normalized statements so repeated
statements update one context slot; decisions, uncertainty readings, and
backtracks use per-tool counters.

RELATED DOCS: `https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/deep-cot-tools.md`
defines the event contracts. `https://github.com/cerredz/Vidbyte-SDK/pull/328`
and `https://github.com/cerredz/Vidbyte-SDK/pull/329` document the shared-helper
convention that keeps the parser class-bound.

AUTO-GENERATED FLAG: No; maintained source code.

TESTS: No dedicated feature test file exists in the source PR. Resolver
verification covers import/export, specification shape, parser boundaries,
primitive rendering, and async execution smoke paths.

CONCURRENCY MODEL: Tool instances own independent counters and share the
injected ContextManager. The manager's registry is in-memory and has no lock;
callers must serialize concurrent writes to one manager when ordering matters.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import TYPE_CHECKING, Any

from vidbyte.lib.constants.cot_events import (
    DEFAULT_ASSUMPTION_ACTION,
    DEFAULT_BASIS_TYPE,
    DEFAULT_IMPACT_IF_WRONG,
    DEFAULT_RETURNABLE,
    DEFAULT_REVERSIBLE,
    DEFAULT_SALVAGE,
    MAX_CONFIDENCE,
    MAX_REJECTED_ALTERNATIVES,
    MIN_CONFIDENCE,
)
from vidbyte.lib.enums.cot_events import (
    AssumptionAction,
    BasisType,
    CotEventEnum,
    HypothesisStatus,
    ImpactLevel,
    ProgressState,
    ReturnableOption,
    Reversibility,
)
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class CotEventParser:
    """Shared coercion and validation helpers for deep CoT event tools."""

    @staticmethod
    def require_text(args: dict[str, Any], field_names: tuple[str, ...]) -> str | None:
        """Return an error for the first missing or blank required text field."""
        for field_name in field_names:
            value = args.get(field_name)
            if not value or not str(value).strip():
                return f"Missing or empty required field: '{field_name}'."
        return None

    @staticmethod
    def parse_enum(
        value: Any,
        allowed: type[CotEventEnum],
        field_name: str,
    ) -> tuple[str | None, str | None]:
        """Normalize an enum argument or return an error naming allowed values."""
        if value is None or str(value).strip() == "":
            return None, None
        raw_value = value.value if isinstance(value, CotEventEnum) else str(value)
        normalized = raw_value.strip().lower()
        allowed_values = allowed.values()
        if normalized not in allowed_values:
            return None, f"Field '{field_name}' must be one of: {', '.join(allowed_values)}."
        return normalized, None

    @staticmethod
    def parse_confidence(value: Any) -> float | None:
        """Coerce a finite number to a confidence clamped to the inclusive SDK bounds."""
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (ValueError, TypeError):
            return None
        if not math.isfinite(number):
            return None
        return max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, number))

    @staticmethod
    def parse_json_objects(
        value: Any,
        field_name: str,
        max_items: int,
        required_keys: tuple[str, ...] = (),
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Parse and validate a bounded JSON array of objects."""
        if value is None:
            return None, None
        parsed: Any = value
        if isinstance(value, str):
            if not value.strip():
                return None, None
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None, f"Field '{field_name}' must be valid JSON."
        if not isinstance(parsed, list) or not all(isinstance(entry, dict) for entry in parsed):
            return None, f"Field '{field_name}' must be a JSON array of objects."
        if not parsed:
            return None, f"Field '{field_name}' must contain at least one object."
        entries = [dict(entry) for entry in parsed[:max_items]]
        for index, entry in enumerate(entries):
            missing = [
                key
                for key in required_keys
                if not entry.get(key) or not str(entry[key]).strip()
            ]
            if missing:
                names = ", ".join(f"'{key}'" for key in missing)
                return None, f"Field '{field_name}' entry {index} is missing non-empty keys: {names}."
        return entries, None

    @staticmethod
    def optional_text(value: Any) -> str | None:
        """Return stripped optional text or None when absent or blank."""
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class _CotEventToolBase(BaseTool):
    """Shared ContextManager lifecycle for the five event tools."""

    def __init__(self, context_manager: ContextManager) -> None:
        self._manager = context_manager
        self._counter = 0

    def _next_primitive_id(self) -> str:
        """Return the next append-only ID for this tool instance."""
        return f"{self.spec().name}:{self._counter}"

    @staticmethod
    def statement_primitive_id(prefix: str, statement: str) -> str:
        """Return a normalized content-keyed ID for a ledger statement."""
        # @intent stable_ledger_identity
        # Repeated statements must overwrite one ledger record so updates remain visible rather
        # than allowing stale and current versions to compete in the context window.
        digest = hashlib.sha256(statement.strip().lower().encode("utf-8")).hexdigest()[:12]
        return f"{prefix}:{digest}"

    async def _record(self, item: Any, call: ToolCall, metadata: dict[str, Any]) -> ToolResult:
        """Upsert one primitive and convert manager validation failures into a tool result."""
        try:
            self._manager.upsert(item)
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "The reasoning event could not be stored because its context values were invalid.",
                metadata={"error": "invalid_reasoning_event_context"},
            )
        return ToolResult.success(call.tool_name, item.to_context_text(), metadata=metadata)


class HypothesisTool(_CotEventToolBase):
    """Record and update a falsifiable, load-bearing belief."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="hypothesis",
            description=(
                "Use this tool when you adopt a load-bearing belief that may be true or false. "
                "It records the claim, its scope, its support, and the observation that would "
                "change it so future reasoning can distinguish evidence from assumption. "
                "Reuse the same statement when new evidence changes the belief's status, which "
                "updates one ledger entry instead of creating a competing record. "
                "Keep entries focused on beliefs that influence the plan, interpretation, or "
                "next action."
            ),
            parameters=(
                ToolParameter(
                    name="statement",
                    type="string",
                    description=(
                        "State one belief that can be shown to be true or false. "
                        "Keep the wording stable across later updates so the ledger can track "
                        "one belief over time. "
                        "Make the statement precise enough for a later observation to support "
                        "or contradict it. "
                        "Do not use this field for a task description, preference, or vague "
                        "intuition."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="scope",
                    type="string",
                    description=(
                        "Identify the part of the current work to which the belief applies. "
                        "Keep the scope short and bounded so readers know what downstream "
                        "reasoning inherits it. "
                        "Use the same scope when updating the statement unless the evidence "
                        "shows that the boundary itself was wrong. "
                        "Do not broaden the scope merely to make one observation appear to "
                        "support more work."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="basis",
                    type="string",
                    description=(
                        "Summarize the immediate support for holding the belief. "
                        "Name the observation, source, or reasoning step that currently gives "
                        "the belief weight. "
                        "Keep the basis separate from the claim so later updates can replace "
                        "the support without changing identity. "
                        "Do not describe confidence alone; the basis must identify why the "
                        "belief exists."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="basis_type",
                    type="string",
                    description=(
                        "Classify the support using exactly one canonical value: "
                        "`evidence`, `inference`, or `prior`. "
                        "Use `evidence` for a direct observation, `inference` for a conclusion "
                        "derived from facts, and `prior` for background expectation. "
                        "This classification lets monitors distinguish observed support from "
                        "reasoning that still needs verification. "
                        "The default is `inference` when the field is omitted."
                    ),
                    required=False,
                    default=DEFAULT_BASIS_TYPE,
                ),
                ToolParameter(
                    name="status",
                    type="string",
                    description=(
                        "Describe the current standing using exactly one canonical value: "
                        "`proposed`, `supported`, `weakened`, or `falsified`. "
                        "Use `proposed` before a meaningful check, `supported` when evidence "
                        "strengthens the claim, `weakened` when evidence creates doubt, and "
                        "`falsified` when the claim no longer holds. "
                        "Update this field when the evidence changes rather than appending a "
                        "second statement. "
                        "A falsified status is useful telemetry because it prevents the failed "
                        "belief from silently guiding later work."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="falsifier",
                    type="string",
                    description=(
                        "State the observation that would make the belief unacceptable. "
                        "Make the condition concrete enough that another agent can recognize "
                        "it without reconstructing your reasoning. "
                        "A good falsifier defines the boundary between a weakened belief and a "
                        "belief that must be abandoned. "
                        "Do not use a general instruction to investigate; name the evidence "
                        "that changes the decision."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "Give the current probability that the belief is correct as a number "
                        "from 0.0 through 1.0. "
                        "The parser accepts numeric strings and clamps values outside the "
                        "inclusive range. "
                        "Treat this as a forecast that can move independently from the "
                        "categorical status. "
                        "Omit it when the evidence does not support a meaningful estimate."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="next_check",
                    type="string",
                    description=(
                        "Describe the next action that would most efficiently test or refine "
                        "the belief. "
                        "Keep it focused on an observable check rather than a broad plan. "
                        "This field gives the next agent a direct route from recorded belief to "
                        "evidence. "
                        "Leave it empty only when the belief has already been resolved or no "
                        "safe check is currently available."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate, build, and upsert one hypothesis ledger entry."""
        args = dict(call.arguments)
        error = CotEventParser.require_text(args, ("statement", "scope", "basis", "status", "falsifier"))
        if error:
            return ToolResult.error(call.tool_name, error)
        status, status_error = CotEventParser.parse_enum(args.get("status"), HypothesisStatus, "status")
        if status_error:
            return ToolResult.error(call.tool_name, status_error)
        basis_type, basis_error = CotEventParser.parse_enum(args.get("basis_type"), BasisType, "basis_type")
        if basis_error:
            return ToolResult.error(call.tool_name, basis_error)
        from vidbyte.context.primitives.cot_events import HypothesisContextItem

        statement = str(args["statement"]).strip()
        item = HypothesisContextItem(
            primitive_id=self.statement_primitive_id("hypothesis", statement),
            statement=statement,
            scope=str(args["scope"]).strip(),
            basis=str(args["basis"]).strip(),
            status=status or HypothesisStatus.PROPOSED.value,
            basis_type=basis_type or DEFAULT_BASIS_TYPE,
            falsifier=str(args["falsifier"]).strip(),
            confidence=CotEventParser.parse_confidence(args.get("confidence")),
            next_check=CotEventParser.optional_text(args.get("next_check")),
        )
        return await self._record(
            item,
            call,
            {"status": item.status, "basis_type": item.basis_type, "confidence": item.confidence},
        )


class DecisionTool(_CotEventToolBase):
    """Record a meaningful choice, its alternatives, and its review conditions."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="decision",
            description=(
                "Use this tool when you commit to one meaningful path among multiple plausible "
                "options. It records the choice, the criterion that selected it, the serious "
                "alternatives rejected, and the consequence you expect from following it. "
                "The record preserves risk and reversibility so later agents can decide whether "
                "to continue, review, or undo the branch. "
                "Do not use it for routine steps with no genuine choice point or for invented "
                "alternatives that were never considered."
            ),
            parameters=(
                ToolParameter(
                    name="decision",
                    type="string",
                    description=(
                        "State the choice being committed to in one concise sentence. "
                        "Describe the selected path rather than the larger task it serves. "
                        "Keep the wording specific enough that later context can identify the "
                        "same decision. "
                        "Do not turn this field into a justification or a retrospective result."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="chosen_because",
                    type="string",
                    description=(
                        "State the decisive reason this path won. "
                        "Name the actual tradeoff or constraint that separated it from the "
                        "alternatives. "
                        "Keep this distinct from the expected outcome so the motivation remains "
                        "visible if the outcome changes. "
                        "Do not replace the deciding reason with a generic quality claim."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="criterion",
                    type="string",
                    description=(
                        "Identify the primary criterion used to compare the options. "
                        "The criterion should explain what the decision optimized or protected. "
                        "Keep it narrow enough that a later reviewer can judge whether it was "
                        "applied consistently. "
                        "Do not list every consideration; reserve this field for the main "
                        "decision rule."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="rejected",
                    type="string",
                    description=(
                        "Provide a JSON array containing one to three serious rejected "
                        "alternatives. "
                        "Each object must contain non-empty `option` and `reason` keys so the "
                        "record preserves both the alternative and why it lost. "
                        "Only include alternatives that materially competed with the selected "
                        "path. "
                        "The parser caps the retained array at the shared SDK limit and rejects "
                        "malformed entries."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="expected_outcome",
                    type="string",
                    description=(
                        "Describe the result you expect this choice to produce. "
                        "Tie the outcome to the current goal and keep it observable enough for "
                        "later review. "
                        "This is a forward-looking forecast, not a claim that the result has "
                        "already happened. "
                        "Do not use it to restate the chosen path without its expected effect."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="main_risk",
                    type="string",
                    description=(
                        "Name the most important way this choice could fail or create unwanted "
                        "cost. "
                        "Focus on the risk that would change the branch, not every minor "
                        "uncertainty. "
                        "Keep the risk concrete enough that a later agent can look for its "
                        "signal. "
                        "Do not omit a material risk merely because confidence is high."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reversible",
                    type="string",
                    description=(
                        "Classify the cost of undoing the choice using exactly one canonical "
                        "value: `yes`, `costly`, or `no`. "
                        "Use `yes` when reversal is cheap, `costly` when reversal requires "
                        "substantial rework, and `no` when the effect is effectively permanent. "
                        "This field helps the next agent weigh uncertainty against the cost of "
                        "continuing. "
                        "The default is `yes` when omitted."
                    ),
                    required=False,
                    default=DEFAULT_REVERSIBLE,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "Give the probability that this is the right branch as a number from "
                        "0.0 through 1.0. "
                        "The parser accepts numeric strings and clamps values outside the "
                        "inclusive range. "
                        "Treat the value as a forecast tied to the available evidence rather "
                        "than as a rhetorical confidence signal. "
                        "Omit it when the decision has not been calibrated."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="review_trigger",
                    type="string",
                    description=(
                        "State the observation or condition that should cause this decision to "
                        "be reconsidered. "
                        "Make the trigger specific enough to guide monitoring without requiring "
                        "a full reconstruction of the choice. "
                        "This field turns a static decision record into an explicit review "
                        "boundary. "
                        "Leave it empty only when no meaningful review condition is known."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate, build, and upsert one decision record."""
        args = dict(call.arguments)
        error = CotEventParser.require_text(
            args,
            ("decision", "chosen_because", "criterion", "rejected", "expected_outcome", "main_risk"),
        )
        if error:
            return ToolResult.error(call.tool_name, error)
        rejected, rejected_error = CotEventParser.parse_json_objects(
            args.get("rejected"), "rejected", MAX_REJECTED_ALTERNATIVES, required_keys=("option", "reason")
        )
        if rejected_error:
            return ToolResult.error(call.tool_name, rejected_error)
        reversible, reversible_error = CotEventParser.parse_enum(
            args.get("reversible"), Reversibility, "reversible"
        )
        if reversible_error:
            return ToolResult.error(call.tool_name, reversible_error)
        self._counter += 1
        from vidbyte.context.primitives.cot_events import DecisionContextItem

        item = DecisionContextItem(
            primitive_id=self._next_primitive_id(),
            decision=str(args["decision"]).strip(),
            chosen_because=str(args["chosen_because"]).strip(),
            criterion=str(args["criterion"]).strip(),
            rejected=tuple(rejected or ()),
            expected_outcome=str(args["expected_outcome"]).strip(),
            main_risk=str(args["main_risk"]).strip(),
            reversible=reversible or DEFAULT_REVERSIBLE,
            confidence=CotEventParser.parse_confidence(args.get("confidence")),
            review_trigger=CotEventParser.optional_text(args.get("review_trigger")),
        )
        return await self._record(
            item,
            call,
            {
                "reversible": item.reversible,
                "confidence": item.confidence,
                "rejected_count": len(item.rejected),
            },
        )


class AssumptionCheckTool(_CotEventToolBase):
    """Record an assumption, its blast radius, and its verification state."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="assumption_check",
            description=(
                "Use this tool when current work depends on something you are treating as true "
                "without complete verification. It records the assumption's scope, basis, "
                "dependent work, impact, and the condition that would invalidate it. "
                "Update the same statement as it is declared, verified, or falsified so the "
                "ledger exposes unresolved load-bearing assumptions instead of hiding them in "
                "later prose. "
                "Prioritize assumptions whose failure would force rework, corrupt an outcome, "
                "or change the current plan."
            ),
            parameters=(
                ToolParameter(
                    name="assumption",
                    type="string",
                    description=(
                        "State one condition the current work is treating as true. "
                        "Keep the sentence stable across declared, verified, and falsified "
                        "updates so the ledger identifies one assumption. "
                        "Make it checkable rather than describing a general hope or preference. "
                        "Do not combine independent assumptions into one field."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="scope",
                    type="string",
                    description=(
                        "Identify the part of the current work that relies on this assumption. "
                        "The scope should show where the assumption enters the plan or result. "
                        "Keep it bounded so the impact assessment does not become vague. "
                        "Do not use the entire task as scope unless every step truly depends on "
                        "the condition."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="basis",
                    type="string",
                    description=(
                        "State why the assumption is currently being treated as plausible. "
                        "Identify the observation, prior knowledge, or inference that supports "
                        "proceeding. "
                        "Keep this separate from the dependency so the record distinguishes "
                        "support from consequence. "
                        "Do not present confidence alone as a basis."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "Classify the ledger event using exactly one canonical value: "
                        "`declared`, `verified`, or `falsified`. "
                        "Use `declared` when reliance is first made visible, `verified` when "
                        "an observation confirms the condition, and `falsified` when the "
                        "condition no longer holds. "
                        "A falsified action signals that dependent work must be reconsidered, "
                        "not merely documented. "
                        "The action is required for every record."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="impact_if_wrong",
                    type="string",
                    description=(
                        "Classify the blast radius using exactly one canonical value: `fatal`, "
                        "`major`, or `minor`. "
                        "Use `fatal` when the result becomes invalid or corrupted, `major` "
                        "when significant work must be redone, and `minor` when the consequence "
                        "is localized. "
                        "This value helps prioritize verification before the assumption fails. "
                        "The shared default is `major` when a caller omits the value, although "
                        "the model-facing field is required."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="dependency",
                    type="string",
                    description=(
                        "State the decision, artifact, or next action that depends on this "
                        "assumption. "
                        "Keep the dependency concrete enough that a falsified record identifies "
                        "what must be revisited. "
                        "This field describes the downstream consequence rather than repeating "
                        "the assumption itself. "
                        "Do not leave it implicit in the scope."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verification_step",
                    type="string",
                    description=(
                        "Describe how the assumption was checked when action is `verified` or "
                        "`falsified`. "
                        "Name the observation or procedure that supports the action so another "
                        "agent can assess the evidence. "
                        "This field is required for resolved actions and may be omitted while "
                        "the assumption is only declared. "
                        "Do not substitute a confidence statement for a verification step."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="falsifier",
                    type="string",
                    description=(
                        "State the observation that would prove the assumption unsafe to keep. "
                        "Make the condition specific enough to trigger a change in dependent "
                        "work. "
                        "Keep it valid for both an unresolved declaration and a later update. "
                        "Do not describe an open-ended investigation with no decision boundary."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "Give the probability that the assumption currently holds as a number "
                        "from 0.0 through 1.0. "
                        "The parser accepts numeric strings and clamps values outside the "
                        "inclusive range. "
                        "Use this as a calibrated estimate that can change before the action "
                        "moves to verified or falsified. "
                        "Omit it when no defensible estimate is available."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate, build, and upsert one assumption ledger entry."""
        args = dict(call.arguments)
        error = CotEventParser.require_text(
            args,
            ("assumption", "scope", "basis", "action", "impact_if_wrong", "dependency", "falsifier"),
        )
        if error:
            return ToolResult.error(call.tool_name, error)
        action, action_error = CotEventParser.parse_enum(args.get("action"), AssumptionAction, "action")
        if action_error:
            return ToolResult.error(call.tool_name, action_error)
        impact, impact_error = CotEventParser.parse_enum(args.get("impact_if_wrong"), ImpactLevel, "impact_if_wrong")
        if impact_error:
            return ToolResult.error(call.tool_name, impact_error)
        verification_step = CotEventParser.optional_text(args.get("verification_step"))
        if action in {AssumptionAction.VERIFIED.value, AssumptionAction.FALSIFIED.value} and not verification_step:
            return ToolResult.error(
                call.tool_name,
                "Field 'verification_step' is required when action is 'verified' or 'falsified'.",
            )
        from vidbyte.context.primitives.cot_events import AssumptionCheckContextItem

        assumption = str(args["assumption"]).strip()
        item = AssumptionCheckContextItem(
            primitive_id=self.statement_primitive_id("assumption_check", assumption),
            assumption=assumption,
            scope=str(args["scope"]).strip(),
            basis=str(args["basis"]).strip(),
            action=action or DEFAULT_ASSUMPTION_ACTION,
            impact_if_wrong=impact or DEFAULT_IMPACT_IF_WRONG,
            dependency=str(args["dependency"]).strip(),
            verification_step=verification_step,
            falsifier=str(args["falsifier"]).strip(),
            confidence=CotEventParser.parse_confidence(args.get("confidence")),
        )
        return await self._record(
            item,
            call,
            {
                "action": item.action,
                "impact_if_wrong": item.impact_if_wrong,
                "confidence": item.confidence,
            },
        )


class UncertaintyTool(_CotEventToolBase):
    """Record calibrated confidence, uncertainty sources, and the next response."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="uncertainty",
            description=(
                "Use this tool when you need a structured reading of immediate execution "
                "confidence and confidence in the overall approach. It separates uncertainty "
                "about the next step from uncertainty about whether the plan remains on track. "
                "The record also captures the source of doubt, blockers, and the action that "
                "should follow a weak reading so a monitor can distinguish drift from ordinary "
                "progress. "
                "Take a reading at meaningful changes in direction or whenever the current "
                "numbers no longer feel well supported."
            ),
            parameters=(
                ToolParameter(
                    name="next_step",
                    type="number",
                    description=(
                        "Give the probability that the immediate next action is correct as a "
                        "number from 0.0 through 1.0. "
                        "This measures execution confidence in the step itself, not confidence "
                        "in the larger plan. "
                        "The parser accepts numeric strings and clamps values outside the "
                        "inclusive range. "
                        "This field is required because the divergence from on-track confidence "
                        "is part of the event's meaning."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="on_track",
                    type="number",
                    description=(
                        "Give the probability that the overall current approach still leads to "
                        "the goal as a number from 0.0 through 1.0. "
                        "This measures plan confidence independently from execution of the next "
                        "step. "
                        "The parser accepts numeric strings and clamps values outside the "
                        "inclusive range. "
                        "A large difference between this value and next-step confidence is a "
                        "signal for review rather than an error."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="progress",
                    type="string",
                    description=(
                        "Classify directional movement using exactly one canonical value: "
                        "`progressing`, `stalled`, or `regressing`. "
                        "Use `progressing` when work is materially closer to the goal, "
                        "`stalled` when effort is not changing the distance, and `regressing` "
                        "when recent work increased the distance or invalidated completed work. "
                        "This is a compact velocity signal that complements the two confidence "
                        "numbers. "
                        "The field is required for every reading."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="trigger",
                    type="string",
                    description=(
                        "State what prompted this reading in one short clause. "
                        "Use it to distinguish a routine checkpoint from a reading caused by a "
                        "new contradiction, failure, or change in plan. "
                        "Keep the trigger observational rather than speculating about the final "
                        "cause. "
                        "Leave it empty for a routine reading when no event prompted it."
                    ),
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="uncertainty_source",
                    type="string",
                    description=(
                        "Identify the main source of uncertainty behind the numbers. "
                        "Separate the unknown or conflicting signal from the confidence estimate "
                        "it produces. "
                        "Keep the source narrow enough that the next action can address it. "
                        "Do not use a generic statement that the task is difficult."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="blocker",
                    type="string",
                    description=(
                        "Describe the external or internal condition currently preventing a "
                        "clearer reading or faster progress. "
                        "Use this field only for a real constraint, missing observation, or "
                        "unresolved dependency. "
                        "Leave it empty when uncertainty has no active blocker. "
                        "A blocker should explain why the next action cannot simply resolve the "
                        "doubt immediately."
                    ),
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="next_action",
                    type="string",
                    description=(
                        "State the next action that responds to this uncertainty reading. "
                        "Choose an action that can increase information, restore progress, or "
                        "reconsider the approach. "
                        "Keep it concrete enough that another agent can continue without "
                        "repeating the calibration exercise. "
                        "This field is required even when the current confidence is high so the "
                        "reading remains operational."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reassessment_condition",
                    type="string",
                    description=(
                        "State what future observation should cause another uncertainty reading. "
                        "Use this to define the boundary for rechecking confidence after the next "
                        "action. "
                        "Keep it tied to a change in evidence, progress, or plan rather than a "
                        "fixed narrative schedule. "
                        "Leave it empty when the next action itself is the only meaningful review "
                        "point."
                    ),
                    required=False,
                    default="",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate, build, and upsert one uncertainty snapshot."""
        args = dict(call.arguments)
        error = CotEventParser.require_text(args, ("progress", "uncertainty_source", "next_action"))
        if error:
            return ToolResult.error(call.tool_name, error)
        next_step = CotEventParser.parse_confidence(args.get("next_step"))
        if next_step is None:
            return ToolResult.error(call.tool_name, "Field 'next_step' must be a number between 0.0 and 1.0.")
        on_track = CotEventParser.parse_confidence(args.get("on_track"))
        if on_track is None:
            return ToolResult.error(call.tool_name, "Field 'on_track' must be a number between 0.0 and 1.0.")
        progress, progress_error = CotEventParser.parse_enum(args.get("progress"), ProgressState, "progress")
        if progress_error:
            return ToolResult.error(call.tool_name, progress_error)
        self._counter += 1
        from vidbyte.context.primitives.cot_events import UncertaintyContextItem

        item = UncertaintyContextItem(
            primitive_id=self._next_primitive_id(),
            next_step=next_step,
            on_track=on_track,
            progress=progress or ProgressState.PROGRESSING.value,
            trigger=str(args.get("trigger", "")).strip(),
            uncertainty_source=str(args["uncertainty_source"]).strip(),
            blocker=str(args.get("blocker", "")).strip(),
            next_action=str(args["next_action"]).strip(),
            reassessment_condition=str(args.get("reassessment_condition", "")).strip(),
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
    """Record an abandoned path, retained learning, and the replacement route."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="backtrack",
            description=(
                "Use this tool when you abandon an approach, branch, or line of investigation "
                "before it consumes more of the run. It records what was attempted, the "
                "evidence that caused the pivot, the useful result that survives, and the path "
                "that replaces the abandoned work. "
                "The returnability and loop-guard fields distinguish a deliberate pause from a "
                "dead end that must not be revisited. "
                "Record the event at the pivot so later agents inherit the reasoning instead of "
                "silently repeating the failed path."
            ),
            parameters=(
                ToolParameter(
                    name="abandoning",
                    type="string",
                    description=(
                        "Identify the approach being dropped in one concise statement. "
                        "Name the branch or method rather than the entire task so later context "
                        "can distinguish a local pivot from stopping work. "
                        "Keep the wording stable if the same path is encountered again. "
                        "Do not describe only the failure; the abandoned approach is the object "
                        "being recorded."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reason",
                    type="string",
                    description=(
                        "State the direct reason the approach is being abandoned. "
                        "Connect the pivot to a failed constraint, insufficient result, or better "
                        "route that changed the decision. "
                        "Keep it causal rather than using a generic statement that the approach "
                        "did not work. "
                        "This field should let a later agent understand why continuing would be "
                        "wasteful or unsafe."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="evidence",
                    type="string",
                    description=(
                        "State the observation that supports the decision to pivot. "
                        "Use the strongest direct signal available from the work already done. "
                        "Keep evidence separate from the reason so the record distinguishes what "
                        "was observed from the conclusion drawn. "
                        "Do not leave this as an unsupported change of preference."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="attempted_result",
                    type="string",
                    description=(
                        "Summarize what the abandoned work actually established before the pivot. "
                        "Include partial progress, constraints, or the absence of a usable result "
                        "when that affects the replacement path. "
                        "Keep this retrospective result distinct from salvage, which names what "
                        "will be carried forward. "
                        "Do not imply success that the abandoned approach did not achieve."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="salvage",
                    type="string",
                    description=(
                        "State the knowledge or artifact that carries forward from the abandoned "
                        "work. "
                        "Include constraints, observations, or partial outputs that should not be "
                        "discarded with the approach. "
                        "Use the shared default `nothing` only when no useful result survives. "
                        "Keep this field focused on reusable value rather than repeating the full "
                        "attempt history."
                    ),
                    required=False,
                    default=DEFAULT_SALVAGE,
                ),
                ToolParameter(
                    name="returnable",
                    type="string",
                    description=(
                        "Classify whether the abandoned path may be revisited using exactly one "
                        "canonical value: `yes` or `no`. "
                        "Use `yes` when new information or a changed condition could make it "
                        "viable, and `no` when the evidence rules it out. "
                        "This value controls whether future context treats the path as an open "
                        "option or a closed branch. "
                        "The default is `yes` when omitted."
                    ),
                    required=False,
                    default=DEFAULT_RETURNABLE,
                ),
                ToolParameter(
                    name="replacement_plan",
                    type="string",
                    description=(
                        "State the path that will replace the abandoned approach. "
                        "Describe the next direction and its immediate purpose so the pivot "
                        "produces forward motion. "
                        "Keep it narrower than the whole task and connect it to the salvage and "
                        "evidence fields. "
                        "Do not leave the record as a rejection without a way to continue."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="loop_guard",
                    type="string",
                    description=(
                        "State how future work will avoid silently repeating the abandoned path. "
                        "Use a recognizable condition, record, or decision boundary that a later "
                        "agent can check before returning. "
                        "Make the guard specific to the failure captured here. "
                        "Do not use a generic instruction to be careful or remember this event."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate, build, and upsert one backtrack record."""
        args = dict(call.arguments)
        error = CotEventParser.require_text(
            args,
            ("abandoning", "reason", "evidence", "attempted_result", "replacement_plan", "loop_guard"),
        )
        if error:
            return ToolResult.error(call.tool_name, error)
        returnable, returnable_error = CotEventParser.parse_enum(
            args.get("returnable"), ReturnableOption, "returnable"
        )
        if returnable_error:
            return ToolResult.error(call.tool_name, returnable_error)
        self._counter += 1
        from vidbyte.context.primitives.cot_events import BacktrackContextItem

        item = BacktrackContextItem(
            primitive_id=self._next_primitive_id(),
            abandoning=str(args["abandoning"]).strip(),
            reason=str(args["reason"]).strip(),
            evidence=str(args["evidence"]).strip(),
            attempted_result=str(args["attempted_result"]).strip(),
            salvage=str(args.get("salvage", "")).strip() or DEFAULT_SALVAGE,
            returnable=returnable or DEFAULT_RETURNABLE,
            replacement_plan=str(args["replacement_plan"]).strip(),
            loop_guard=str(args["loop_guard"]).strip(),
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
