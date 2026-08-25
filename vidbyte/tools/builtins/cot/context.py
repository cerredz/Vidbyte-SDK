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
    Writes vidbyte.context.primitives.cot_context primitives. Categorical
    fields are sourced from vidbyte.lib.enums.cot.
Similar Files:
    - `vidbyte/tools/builtins/cot_events.py`
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.enums.cot import (
    ContextCrowding,
    ContextImbalance,
    Criticality,
    FactVisibility,
    RecallMatchOutcome,
    Recoverability,
    ReloadCost,
    Severity,
    YesNo,
)
from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

CROWDED_LEVELS = tuple(level.value for level in ContextCrowding)
VISIBILITY_LEVELS = tuple(level.value for level in FactVisibility)
IMBALANCE_KINDS = tuple(kind.value for kind in ContextImbalance)
RECOVERABILITY_LEVELS = tuple(level.value for level in Recoverability)
RELOAD_COST_LEVELS = tuple(level.value for level in ReloadCost)
VERIFIED_NOW_OPTIONS = tuple(option.value for option in YesNo)
RECALL_MATCH_OUTCOMES = tuple(outcome.value for outcome in RecallMatchOutcome)
CRITICALITY_LEVELS = tuple(level.value for level in Criticality)
IMPACT_LEVELS = tuple(level.value for level in Severity)
COMPACTION_RECOMMENDED_OPTIONS = tuple(option.value for option in YesNo)
_MAX_OCCUPYING = 3
CONTEXT_LOAD_SNAPSHOT_ID = "context_load:current"


class ContextLoadTool(_CotEventToolBase):
    """Builtin tool that snapshots what currently occupies the context window."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_load",
            description=(
                "Take periodic stock of your own context window so that crowding "
                "is caught by inspection rather than discovered by failure. This "
                "tool asks you to judge fullness by consequence rather than raw "
                "size: a window is only concerning once something load-bearing is "
                "at genuine risk of being pushed out or buried under later "
                "content, not simply because a great deal has accumulated in it. "
                "Alongside the fullness verdict, the call records what kind of "
                "content currently dominates and which single item would be the "
                "best candidate to release from active attention. Each call "
                "replaces the previous snapshot, so the record always reflects "
                "present state rather than an accumulating history, and a "
                "downstream monitor can use the compaction recommendation as a "
                "direct signal for whether to intervene before the next major "
                "step."
            ),
            parameters=(
                ToolParameter(
                    name="occupying",
                    type="string",
                    description=(
                        "A JSON array of one to three strings identifying the "
                        "largest consumers of attention in the window at this "
                        "moment, ranked by how much of the window they occupy "
                        "rather than by how many there are. This field exists to "
                        "make the abstract notion of 'crowding' concrete: a "
                        "reader should be able to tell from these entries alone "
                        "what would have to shrink for the window to feel lighter. "
                        "Prefer naming the category of content over a narrow "
                        "instance when several similar items are contributing "
                        "together, since the goal is an accurate map of where the "
                        "space is going rather than an exhaustive inventory."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="crowded",
                    type="string",
                    description=(
                        "An honest fullness verdict describing how much risk the "
                        "current window state poses to load-bearing information, "
                        "ranging across spaciousness, comfortable headroom, "
                        "tightness, overflow, and a critical state where facts "
                        "are already being lost. The scale is deliberately about "
                        "consequence rather than volume, since a large window "
                        "full of low-value content is not crowded in the sense "
                        "this field cares about. Choosing a comfortable rating to "
                        "avoid confronting an uncomfortable one defeats the "
                        "purpose of the check, so this field should be answered "
                        "from the actual state of retrieval and recall rather "
                        "than from a general sense that things are probably "
                        "fine."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="what_to_forget",
                    type="string",
                    description=(
                        "The single item the agent would most benefit from "
                        "releasing from active attention right now, described "
                        "concretely enough that a reader could identify it "
                        "without further context. This field forces the "
                        "crowdedness judgment to produce an actionable "
                        "recommendation rather than stopping at a bare severity "
                        "label. When nothing meaningfully deserves to be "
                        "dropped, that conclusion should be stated directly "
                        "along with the reasoning, since an honest 'nothing' is "
                        "more useful to a reader than a forced or arbitrary "
                        "candidate."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="oldest_unreferenced",
                    type="string",
                    description=(
                        "An optional identification of the oldest item still "
                        "resident in the window that no recent step has actually "
                        "used or referenced. This field surfaces the strongest "
                        "compaction candidate independently of the crowding "
                        "verdict, since staleness and severity are related but "
                        "distinct signals — an item can be old and unreferenced "
                        "well before the window as a whole becomes tight. Name it "
                        "precisely enough that a compaction pass could locate and "
                        "act on it without additional investigation."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="imbalance",
                    type="string",
                    description=(
                        "An optional characterization of what kind of content "
                        "currently dominates the window, distinguishing a "
                        "balanced mixture from one skewed toward raw tool "
                        "output, monitoring records, conversational dialogue, "
                        "attached documents, or an unclassifiable mixture of "
                        "several at once. This field is diagnostic rather than "
                        "evaluative: an imbalance is not inherently bad, but "
                        "knowing its shape helps a compaction strategy target "
                        "the right category instead of trimming indiscriminately "
                        "across the whole window."
                    ),
                    required=False,
                    default="none",
                ),
                ToolParameter(
                    name="compaction_recommended",
                    type="string",
                    description=(
                        "An optional recommendation addressed to the harness "
                        "about whether the current window state justifies "
                        "compaction before the next major step, expressed as "
                        "yes or no. This field is a decision input rather than a "
                        "restatement of the crowding verdict, so it should "
                        "weigh the cost of compacting now against the risk of "
                        "waiting, not simply mirror whatever the fullness rating "
                        "already said. Treat it as advice a downstream process "
                        "may act on automatically, which is why it deserves its "
                        "own deliberate judgment rather than a reflexive "
                        "default."
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
            args.get("compaction_recommended"), COMPACTION_RECOMMENDED_OPTIONS, "compaction_recommended"
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
                "Perform a pre-flight check immediately before any step whose "
                "correctness depends on a fact established earlier in the run, "
                "confirming that fact is genuinely visible in context rather "
                "than merely assumed to still be there. Long runs fail silently "
                "when a step is built on a detail that scrolled out of the "
                "window several phases earlier, and this check exists to catch "
                "that condition before it becomes an incorrect action rather "
                "than after. When the dependency is not visible, the call also "
                "records how it will be recovered, so the check produces a "
                "concrete next action rather than only a diagnosis. Recording "
                "that a dependency has gone missing is a successful use of this "
                "tool, not a failure of it; the actual failure this tool exists "
                "to prevent is proceeding without ever checking at all."
            ),
            parameters=(
                ToolParameter(
                    name="next_step",
                    type="string",
                    description=(
                        "A description of the action about to be taken, specific "
                        "enough that the reasoning behind the dependency check is "
                        "self-evident to a reader. This field anchors the check "
                        "to a concrete forthcoming action rather than a vague "
                        "intention, which is what makes the visibility "
                        "assessment that follows meaningful rather than "
                        "abstract."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="depends_on",
                    type="string",
                    description=(
                        "The single prior fact this step's correctness actually "
                        "depends on, stated precisely enough that its presence "
                        "or absence in the window could be verified "
                        "unambiguously. One dependency should be named per call; "
                        "when a step genuinely depends on several facts, check "
                        "the riskiest one here and note the remainder in the "
                        "recovery field rather than diluting the check across "
                        "multiple loosely-specified dependencies."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="still_visible",
                    type="string",
                    description=(
                        "Whether the named dependency is currently visible in "
                        "the context window, distinguished across full "
                        "visibility, partial visibility such as a summary or "
                        "excerpt, a genuine uncertainty about whether it is "
                        "still present, visibility only through a cached or "
                        "derived form, and outright absence. This judgment "
                        "should be made from what can actually be observed in "
                        "the window at the moment of the call, not from a "
                        "recollection of having seen the fact at some earlier "
                        "point in the run."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="if_no_recover_how",
                    type="string",
                    description=(
                        "Required whenever the dependency is not fully visible: "
                        "a description of the concrete action that will restore "
                        "the full fact before the dependent step proceeds. This "
                        "field is what turns a visibility gap into a resolved "
                        "situation instead of an acknowledged but unaddressed "
                        "risk, so it should name an actual recovery action "
                        "rather than an expression of confidence that the "
                        "detail is probably still correct."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="criticality",
                    type="string",
                    description=(
                        "An optional rating of how much the correctness of the "
                        "next step actually hinges on this dependency, ranging "
                        "from low through medium and high up to fully blocking. "
                        "This field lets a reader triage a run's attention "
                        "checks at a glance, since a missed low-criticality "
                        "dependency and a missed blocking one carry very "
                        "different consequences even though both would be "
                        "recorded the same way without this distinction."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="could_state_from_memory",
                    type="number",
                    description=(
                        "An optional estimate, expressed as a probability "
                        "between zero and one, of whether the fact could be "
                        "stated correctly from memory alone without consulting "
                        "the window. This field separates two related but "
                        "distinct questions: whether the fact is present in the "
                        "window, and whether it is actually held with "
                        "confidence independent of that presence, which "
                        "together describe how load-bearing the underlying "
                        "recall truly is."
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
        criticality, criticality_error = CotEventParser.parse_enum(args.get("criticality"), CRITICALITY_LEVELS, "criticality")
        if criticality_error:
            return ToolResult.error(call.tool_name, criticality_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_context import AttentionCheckContextItem

        item = AttentionCheckContextItem(
            primitive_id=self._next_primitive_id(),
            next_step=str(args["next_step"]).strip(),
            depends_on=str(args["depends_on"]).strip(),
            still_visible=visible or VISIBILITY_LEVELS[0],
            if_no_recover_how=recover_how,
            criticality=criticality,
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
                "Measure the reliability of memory before relying on it by "
                "stating a fact from earlier in the run purely from recollection "
                "and recording a confidence level, ideally before its original "
                "source is re-consulted. Runs commonly drift when an agent acts "
                "confidently on a misremembered version of something it "
                "observed earlier, and this tool converts that risk into "
                "measurable data rather than leaving it invisible. When the "
                "claim is checked against its source in the same call, the "
                "outcome and, where relevant, the consequence of having been "
                "wrong are recorded alongside the original claim. A low "
                "confidence result is a perfectly good outcome, since it signals "
                "that the source should be re-read; the only genuinely poor "
                "outcome this tool exists to expose is high confidence paired "
                "with an incorrect claim."
            ),
            parameters=(
                ToolParameter(
                    name="claimed_fact",
                    type="string",
                    description=(
                        "The fact exactly as currently recalled, stated before "
                        "any check against the source and without adjusting the "
                        "wording afterward to better match what the source "
                        "turns out to say. Precision matters here specifically "
                        "because the value of this record depends on capturing "
                        "the claim as memory actually produced it, not a "
                        "cleaned-up version informed by hindsight."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="number",
                    description=(
                        "A probability between zero and one that the stated "
                        "memory is exactly correct, calibrated against how "
                        "willing the agent would be to act on it without "
                        "checking. A value near one should be reserved for "
                        "facts used or confirmed very recently, while a value "
                        "near a coin flip is an honest admission that the claim "
                        "is genuinely uncertain rather than a hedge to avoid "
                        "commitment."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="source_step",
                    type="string",
                    description=(
                        "An optional pointer to where the fact originally came "
                        "from, described precisely enough that a later reader "
                        "could locate and re-verify it independently. This "
                        "field exists to make the claim auditable rather than a "
                        "bare assertion, which matters most for facts a "
                        "downstream decision will lean on."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="verified_now",
                    type="string",
                    description=(
                        "Whether the claim was actually checked against its "
                        "source within this same call, expressed as yes or no. "
                        "When the answer is no, the claim is being recorded for "
                        "later resolution rather than being settled "
                        "immediately, and the outcome fields describing the "
                        "comparison should be left empty until that later "
                        "verification actually happens."
                    ),
                    required=False,
                    default="no",
                ),
                ToolParameter(
                    name="matches",
                    type="string",
                    description=(
                        "Required whenever the claim was verified in this call: "
                        "the outcome of comparing the recalled claim against its "
                        "source, distinguishing an exact match, a fully wrong "
                        "recollection, a recollection that was correct at the "
                        "time but has since been superseded, a partially "
                        "correct recollection, and a case where the source "
                        "could not actually be checked. This field is what "
                        "converts the confidence estimate from a prediction "
                        "into a scored one."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="impact_if_wrong",
                    type="string",
                    description=(
                        "An optional assessment of how much damage an incorrect "
                        "recollection would have caused had it gone unchecked, "
                        "ranging from purely cosmetic through minor, major, "
                        "critical, and fatal. This field lets a reader "
                        "prioritize which recall tests actually mattered, since "
                        "a low-confidence claim about a trivial detail and a "
                        "high-confidence claim about a load-bearing one warrant "
                        "very different levels of attention even when both are "
                        "recorded by this same tool."
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
        impact, impact_error = CotEventParser.parse_enum(args.get("impact_if_wrong"), IMPACT_LEVELS, "impact_if_wrong")
        if impact_error:
            return ToolResult.error(call.tool_name, impact_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_context import RecallTestContextItem

        item = RecallTestContextItem(
            primitive_id=self._next_primitive_id(),
            claimed_fact=str(args["claimed_fact"]).strip(),
            confidence=confidence,
            verified_now=verified or VERIFIED_NOW_OPTIONS[1],
            matches=matches,
            source_step=CotEventParser.optional_text(args.get("source_step")),
            impact_if_wrong=impact,
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
                "Record the deliberate decision to release something from "
                "active tracking, distinguishing intentional pruning from the "
                "kind of forgetting that happens by neglect, where information "
                "falls out of attention without anyone having decided that was "
                "safe. Good context hygiene depends on the former and is "
                "undermined by the latter, and this tool exists to make every "
                "instance of the former explicit and auditable. Before "
                "recording the drop, the call requires naming what still "
                "depends on the information being released, which is the "
                "safety check that keeps the decision honest rather than "
                "convenient. Recoverability and reload cost are recorded "
                "alongside the decision so that a later reader can judge how "
                "consequential the drop actually was without having to "
                "reconstruct that judgment independently."
            ),
            parameters=(
                ToolParameter(
                    name="what",
                    type="string",
                    description=(
                        "A description of the information being dropped from "
                        "active tracking, specific enough that a reader could "
                        "recognize exactly what is no longer being carried "
                        "forward. Vague descriptions undermine the audit value "
                        "of this record, since a later reader relies on this "
                        "field to know precisely what was released."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="why",
                    type="string",
                    description=(
                        "The reason it is currently safe to stop tracking this "
                        "information, stated as an actual justification rather "
                        "than an assertion. If a clear reason cannot be "
                        "articulated, that is itself a signal the information "
                        "is not actually safe to drop yet, and the decision "
                        "should be reconsidered rather than recorded anyway."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="recoverable",
                    type="string",
                    description=(
                        "Whether the information could be brought back if it "
                        "turns out to be needed later, distinguishing full "
                        "recoverability, a pending or not-yet-determined state, "
                        "recovery that would require real additional work, "
                        "genuine uncertainty about recoverability, and cases "
                        "where the source itself is gone for good. The "
                        "irreversible end of this scale should be used "
                        "sparingly and only when it is actually accurate."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reload_cost",
                    type="string",
                    description=(
                        "An optional estimate of what recovering this "
                        "information would cost if it becomes necessary later, "
                        "ranging from negligible and cheap through moderate and "
                        "expensive up to practically impossible. This field is "
                        "the practical companion to the recoverability field: "
                        "something can be recoverable in principle while still "
                        "being expensive enough in practice that the drop "
                        "carries real risk."
                    ),
                    required=False,
                    default="moderate",
                ),
                ToolParameter(
                    name="what_still_depends_on_it",
                    type="string",
                    description=(
                        "An account of what, if anything, in the remaining plan "
                        "still relies on this information, answered candidly "
                        "rather than optimistically. This is the field that "
                        "actually enforces deliberateness: if something in the "
                        "remaining plan still leans on the information being "
                        "dropped, that dependency should be stated here plainly "
                        "rather than the drop being recorded regardless."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="trigger",
                    type="string",
                    description=(
                        "An optional description of what prompted this "
                        "forgetting decision, such as reaching a natural "
                        "milestone, one artifact being superseded by another, "
                        "or a deliberate cleanup pass. Recording the trigger "
                        "helps a later reader distinguish routine, low-risk "
                        "pruning from a drop made under pressure, which "
                        "generally deserves closer scrutiny."
                    ),
                    required=False,
                    default=None,
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
            trigger=CotEventParser.optional_text(args.get("trigger")),
        )
        return await self._record(item, call, {"recoverable": item.recoverable, "reload_cost": item.reload_cost})


__all__ = [
    "AttentionCheckTool",
    "ContextLoadTool",
    "ForgetDecisionTool",
    "RecallTestTool",
]
