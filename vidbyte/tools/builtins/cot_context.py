"""Context Protocol Header

Description:
    Implements the context-window awareness monitoring tools.
Purpose:
    Lets the model observe and record the state of its own working memory —
    what occupies the window, whether load-bearing facts are still visible,
    how reliable recall from memory is, and what is deliberately dropped.
Architecture:
    - ContextLoadTool, AttentionCheckTool, RecallTestTool, ForgetDecisionTool:
      _CotEventToolBase subclasses that validate, upsert a matching cot_context
      primitive, and return parsed values in ToolResult.metadata.
Relations:
    Reuses CotEventParser and _CotEventToolBase from builtins.cot_events.
    Writes vidbyte.context.primitives.cot_events-style primitives in
    vidbyte.context.primitives.cot_context.
Similar Files:
    - `vidbyte/tools/builtins/cot_events.py`
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

CROWDED_LEVELS = ("comfortable", "tight", "overflowing")
VISIBILITY_LEVELS = ("yes", "no", "partially")
IMBALANCE_KINDS = ("none", "tool_heavy", "primitive_heavy", "conversation_heavy")
RECOVERABILITY_LEVELS = ("yes", "costly", "no")
RELOAD_COST_LEVELS = ("cheap", "moderate", "expensive", "impossible")
VERIFIED_NOW_OPTIONS = ("yes", "no")
RECALL_MATCH_OUTCOMES = ("correct", "wrong", "could_not_verify")
_MAX_OCCUPYING = 3
CONTEXT_LOAD_SNAPSHOT_ID = "context_load:current"


class ContextLoadTool(_CotEventToolBase):
    """Builtin tool that snapshots what currently occupies the context window."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_load",
            description=(
                "Take stock of your own context window: what is occupying it, how "
                "crowded it feels, and what deserves to give way. Use this at "
                "natural milestones or whenever you notice yourself hunting for a "
                "fact you know you saw earlier — that hunt is the symptom of a "
                "window that filled up silently. Judge crowdedness by consequence, "
                "not raw size: 'overflowing' means important facts are at risk of "
                "being pushed out or drowned, not merely that there is a lot here. "
                "Name what you would forget without sentiment — a stale tool "
                "result you can re-derive cheaply is the right thing to drop; a "
                "load-bearing constraint is not. This snapshot replaces the "
                "previous one, so it always reflects the current window state."
            ),
            parameters=(
                ToolParameter(
                    name="occupying",
                    type="string",
                    description=(
                        "A JSON array of 1 to 3 strings naming the biggest consumers "
                        "of attention in the window right now — 'the 4,000-line file "
                        "read', 'eleven monitoring records', 'the original spec'. "
                        "Rank by how much they dominate, not by count."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="crowded",
                    type="string",
                    description=(
                        "Honest fullness verdict. Use exactly one of: 'comfortable' "
                        "(everything load-bearing is visible and findable), 'tight' "
                        "(you are managing, but one more large result would push "
                        "something out), 'overflowing' (you have already lost track "
                        "of facts you previously had). Do not report 'comfortable' "
                        "to avoid dealing with the answer."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="what_to_forget",
                    type="string",
                    description=(
                        "The single thing you would most benefit from dropping from "
                        "active attention, one sentence: 'the intermediate diffs — "
                        "the final result supersedes them'. If genuinely nothing, "
                        "say so and why."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="oldest_unreferenced",
                    type="string",
                    description=(
                        "Optional: the oldest item still sitting in the window that "
                        "no recent step has referenced. This is the prime compaction "
                        "candidate — name it precisely."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="imbalance",
                    type="string",
                    description=(
                        "Optional: what kind of content dominates. Use exactly one "
                        "of: 'none' (balanced), 'tool_heavy' (raw tool results "
                        "dominate), 'primitive_heavy' (monitoring records "
                        "dominate), 'conversation_heavy' (dialogue dominates). "
                        "Defaults to 'none'."
                    ),
                    required=False,
                    default="none",
                ),
                ToolParameter(
                    name="compaction_recommended",
                    type="string",
                    description=(
                        "Optional: whether the window state warrants compaction "
                        "before the next major step — 'yes' or 'no'. Answer as a "
                        "recommendation to the harness, not a description of your "
                        "feelings. Defaults to 'no'."
                    ),
                    required=False,
                    default="no",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the load snapshot primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("crowded", "what_to_forget"))
        if error:
            return ToolResult.error(call.tool_name, error)

        occupying, occupying_error = self._parse_occupying(args.get("occupying"))
        if occupying_error:
            return ToolResult.error(call.tool_name, occupying_error)
        crowded, crowded_error = CotEventParser.parse_enum(args.get("crowded"), CROWDED_LEVELS, "crowded")
        if crowded_error:
            return ToolResult.error(call.tool_name, crowded_error)
        imbalance, imbalance_error = CotEventParser.parse_enum(args.get("imbalance"), IMBALANCE_KINDS, "imbalance")
        if imbalance_error:
            return ToolResult.error(call.tool_name, imbalance_error)
        compaction, compaction_error = CotEventParser.parse_enum(
            args.get("compaction_recommended"), ("yes", "no"), "compaction_recommended"
        )
        if compaction_error:
            return ToolResult.error(call.tool_name, compaction_error)

        from vidbyte.context.primitives.cot_context import ContextLoadContextItem

        item = ContextLoadContextItem(
            primitive_id=CONTEXT_LOAD_SNAPSHOT_ID,
            occupying=tuple(occupying or ()),
            crowded=crowded or CROWDED_LEVELS[0],
            what_to_forget=str(args["what_to_forget"]).strip(),
            oldest_unreferenced=CotEventParser.optional_text(args.get("oldest_unreferenced")),
            imbalance=imbalance or IMBALANCE_KINDS[0],
            compaction_recommended=compaction or "no",
        )
        return await self._record(
            item,
            call,
            {"crowded": item.crowded, "imbalance": item.imbalance, "compaction_recommended": item.compaction_recommended},
        )

    def _parse_occupying(self, value: Any) -> tuple[list[str] | None, str | None]:
        # Parses the occupying JSON array into 1-3 non-empty strings.
        parsed, error = CotEventParser.parse_json_strings(value, "occupying", _MAX_OCCUPYING)
        if error:
            return None, error
        entries = [entry for entry in parsed or () if entry]
        if not entries:
            return None, "Field 'occupying' must contain at least one non-empty string."
        return entries, None


class AttentionCheckTool(_CotEventToolBase):
    """Builtin tool that checks whether the fact the next step depends on is still visible."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="attention_check",
            description=(
                "Before taking a step, name the one prior fact it depends on and "
                "confirm that fact is still actually visible in your context — not "
                "assumed, not remembered-as-probably-there. Use this before any "
                "step whose correctness hinges on an earlier detail: an edit that "
                "must respect a constraint, a query that must reuse an exact "
                "identifier, a conclusion that leans on an earlier measurement. "
                "The silent killer of long runs is a step built on a fact that "
                "scrolled out of the window three phases ago; this check catches "
                "that before it becomes a wrong action. If the fact is not "
                "visible, say how you will recover it — re-read, re-derive, or "
                "ask. Checking and finding it gone is a success; skipping the "
                "check is the failure."
            ),
            parameters=(
                ToolParameter(
                    name="next_step",
                    type="string",
                    description=(
                        "The action you are about to take, one sentence: 'Write the "
                        "update using the schema field names from the earlier read'. "
                        "Be specific enough that the dependency is obvious."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="depends_on",
                    type="string",
                    description=(
                        "The single prior fact this step's correctness depends on, "
                        "stated precisely: 'the exact field name list from the "
                        "third tool result'. One dependency per call — if the step "
                        "has several, check the riskiest one and mention the "
                        "others in if_no_recover_how."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="still_visible",
                    type="string",
                    description=(
                        "Whether that fact is currently visible in your context "
                        "window. Use exactly one of: 'yes' (you can see it now), "
                        "'partially' (you can see part of it or a summary of it), "
                        "'no' (it is gone or you cannot locate it). Answer from "
                        "what you can actually see, not what you remember seeing."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="if_no_recover_how",
                    type="string",
                    description=(
                        "Required when still_visible is 'no' or 'partially': one "
                        "sentence on how you will recover the full fact before "
                        "acting — 're-read the third tool result', 're-run the "
                        "schema query'. 'I think I remember it' is not recovery."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="could_state_from_memory",
                    type="number",
                    description=(
                        "Optional: probability you could state the fact correctly "
                        "from memory alone, without looking, 0.0 to 1.0. This "
                        "measures how load-bearing your recall is — a 'yes' on "
                        "visibility paired with 0.5 here means the window holds "
                        "it but your grasp does not."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the attention check primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("next_step", "depends_on", "still_visible"))
        if error:
            return ToolResult.error(call.tool_name, error)

        visible, visible_error = CotEventParser.parse_enum(args.get("still_visible"), VISIBILITY_LEVELS, "still_visible")
        if visible_error:
            return ToolResult.error(call.tool_name, visible_error)
        recover_how = CotEventParser.optional_text(args.get("if_no_recover_how"))
        if visible != "yes" and recover_how is None:
            return ToolResult.error(
                call.tool_name,
                "Field 'if_no_recover_how' is required when still_visible is not 'yes'.",
            )

        self._counter += 1
        from vidbyte.context.primitives.cot_context import AttentionCheckContextItem

        item = AttentionCheckContextItem(
            primitive_id=self._next_primitive_id(),
            next_step=str(args["next_step"]).strip(),
            depends_on=str(args["depends_on"]).strip(),
            still_visible=visible or VISIBILITY_LEVELS[0],
            if_no_recover_how=recover_how,
            could_state_from_memory=CotEventParser.parse_confidence(args.get("could_state_from_memory")),
        )
        return await self._record(item, call, {"still_visible": item.still_visible})


class RecallTestTool(_CotEventToolBase):
    """Builtin tool that tests recall of an earlier fact from memory before re-reading it."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="recall_test",
            description=(
                "State a fact from earlier in the run from memory — before "
                "re-reading its source — and record how confident you are. Use "
                "this when you are about to rely on a remembered detail and the "
                "source is still available to check against. The point is to "
                "measure your own memory honestly: state the claim, give your "
                "confidence, then optionally verify and record whether memory "
                "was right. Runs drift when agents act confidently on misquotes "
                "of their own earlier observations; this tool turns that drift "
                "into data. Low confidence is a fine answer — it means re-read "
                "the source. Wrong-but-confident is the only bad outcome here."
            ),
            parameters=(
                ToolParameter(
                    name="claimed_fact",
                    type="string",
                    description=(
                        "The fact exactly as you currently remember it — verbatim "
                        "where you can be, including exact identifiers, numbers, "
                        "and names: 'the pagination limit was 100', 'the function "
                        "was named build_context'. State it before checking; do "
                        "not refine it using the source."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "Probability your stated memory is exactly right, 0.0 to "
                        "1.0, one decimal. 1.0 means you would act on it without "
                        "checking; 0.5 means a coin flip. Most recall deserves "
                        "0.6–0.9 — reserve 1.0 for facts you just used."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="source_step",
                    type="string",
                    description=(
                        "Optional: where the fact came from — 'the schema read "
                        "two steps ago', 'the user's second message'. Helps a "
                        "later reader re-verify."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="verified_now",
                    type="string",
                    description=(
                        "Whether you re-checked against the source in this same "
                        "call: 'yes' or 'no'. If 'no', you are recording the "
                        "claim for later resolution — fine, but then matches must "
                        "be omitted. Defaults to 'no'."
                    ),
                    required=False,
                    default="no",
                ),
                ToolParameter(
                    name="matches",
                    type="string",
                    description=(
                        "Required when verified_now is 'yes'. Use exactly one of: "
                        "'correct' (memory matched the source), 'wrong' (memory "
                        "was mistaken — say the correct version in the next "
                        "step), 'could_not_verify' (source no longer available)."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the recall test primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("claimed_fact",))
        if error:
            return ToolResult.error(call.tool_name, error)

        confidence = CotEventParser.parse_confidence(args.get("confidence"))
        if confidence is None:
            return ToolResult.error(call.tool_name, "Field 'confidence' must be a number between 0.0 and 1.0.")
        verified, verified_error = CotEventParser.parse_enum(args.get("verified_now"), VERIFIED_NOW_OPTIONS, "verified_now")
        if verified_error:
            return ToolResult.error(call.tool_name, verified_error)
        matches, matches_error = CotEventParser.parse_enum(args.get("matches"), RECALL_MATCH_OUTCOMES, "matches")
        if matches_error:
            return ToolResult.error(call.tool_name, matches_error)
        if verified == "yes" and matches is None:
            return ToolResult.error(call.tool_name, "Field 'matches' is required when verified_now is 'yes'.")

        self._counter += 1
        from vidbyte.context.primitives.cot_context import RecallTestContextItem

        item = RecallTestContextItem(
            primitive_id=self._next_primitive_id(),
            claimed_fact=str(args["claimed_fact"]).strip(),
            confidence=confidence,
            verified_now=verified or VERIFIED_NOW_OPTIONS[1],
            matches=matches,
            source_step=CotEventParser.optional_text(args.get("source_step")),
        )
        return await self._record(
            item,
            call,
            {"confidence": item.confidence, "verified_now": item.verified_now, "matches": item.matches},
        )


class ForgetDecisionTool(_CotEventToolBase):
    """Builtin tool that records deliberately dropping information from active consideration."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="forget_decision",
            description=(
                "Record the deliberate decision to stop tracking something — to "
                "release it from your active working set. Use this when you "
                "consciously set information aside: an intermediate result "
                "superseded by a final one, an error message resolved three steps "
                "ago, a file whose contents you have already extracted what you "
                "needed from. Forgetting on purpose is good hygiene; the danger "
                "is forgetting by neglect, where something falls out of attention "
                "without anyone deciding it was safe. This record makes the "
                "decision explicit and reversible-in-principle: before you drop "
                "something, name what still depends on it. If the answer is "
                "'the remaining plan', do not drop it."
            ),
            parameters=(
                ToolParameter(
                    name="what",
                    type="string",
                    description=(
                        "The information being dropped from active tracking, one "
                        "sentence specific enough to recognize: 'the raw HTML of "
                        "the pricing page — the extracted table supersedes it'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="why",
                    type="string",
                    description=(
                        "Why it is safe to stop tracking it, one clause: "
                        "'superseded by the normalized result', 'error resolved "
                        "and fix verified'. If you cannot state why it is safe, "
                        "it is not safe."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="recoverable",
                    type="string",
                    description=(
                        "Whether it can come back if needed later. Use exactly one "
                        "of: 'yes' (still in window or trivially re-derivable), "
                        "'costly' (re-derivable with real work), 'no' (gone for "
                        "good — the source was volatile). Mark 'no' sparingly; it "
                        "is the only irreversible option."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reload_cost",
                    type="string",
                    description=(
                        "Optional: what recovery would cost if it becomes "
                        "necessary. Use exactly one of: 'cheap' (one call), "
                        "'moderate' (a few calls), 'expensive' (redo a phase), "
                        "'impossible' (source no longer exists). Defaults to "
                        "'moderate'."
                    ),
                    required=False,
                    default="moderate",
                ),
                ToolParameter(
                    name="what_still_depends_on_it",
                    type="string",
                    description=(
                        "What, if anything, in the remaining plan still leans on "
                        "this information — 'nothing; the plan uses only the "
                        "extracted table' or 'the final report cites these exact "
                        "numbers'. Answer honestly; this is the safety check that "
                        "makes forgetting deliberate instead of accidental."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the forget decision primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("what", "why", "recoverable", "what_still_depends_on_it"))
        if error:
            return ToolResult.error(call.tool_name, error)

        recoverable, recoverable_error = CotEventParser.parse_enum(
            args.get("recoverable"), RECOVERABILITY_LEVELS, "recoverable"
        )
        if recoverable_error:
            return ToolResult.error(call.tool_name, recoverable_error)
        reload_cost, reload_error = CotEventParser.parse_enum(args.get("reload_cost"), RELOAD_COST_LEVELS, "reload_cost")
        if reload_error:
            return ToolResult.error(call.tool_name, reload_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_context import ForgetDecisionContextItem

        item = ForgetDecisionContextItem(
            primitive_id=self._next_primitive_id(),
            what=str(args["what"]).strip(),
            why=str(args["why"]).strip(),
            recoverable=recoverable or RECOVERABILITY_LEVELS[0],
            reload_cost=reload_cost or RELOAD_COST_LEVELS[1],
            what_still_depends_on_it=str(args["what_still_depends_on_it"]).strip(),
        )
        return await self._record(item, call, {"recoverable": item.recoverable, "reload_cost": item.reload_cost})


__all__ = [
    "AttentionCheckTool",
    "ContextLoadTool",
    "ForgetDecisionTool",
    "RecallTestTool",
]
