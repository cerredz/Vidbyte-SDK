"""Context Protocol Header

Description:
    Implements the information-foraging monitoring tools.
Purpose:
    Lets the model record its search discipline — why a search was launched,
    what it was planned to cover, what it actually yielded, and when evidence
    was declared sufficient to stop searching and act.
Architecture:
    - SearchWhyTool, SearchPlanTool, SearchYieldTool, EnoughTool:
      _CotEventToolBase subclasses that validate, upsert a matching
      cot_foraging primitive, and return parsed values in ToolResult.metadata.
Relations:
    Reuses CotEventParser and _CotEventToolBase from builtins.cot_events.
    Categorical fields are sourced from vidbyte.lib.enums.cot.
Similar Files:
    - `vidbyte/tools/builtins/cot/context.py`
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.enums.cot import (
    ExpectedSource,
    SearchExpectedYield,
    SearchFoundOutcome,
    SearchPivot,
    SearchUrgency,
    SurpriseLevel,
    YesNo,
)
from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

EXPECTED_SOURCES = tuple(source.value for source in ExpectedSource)
EXPECTED_YIELDS = tuple(yield_.value for yield_ in SearchExpectedYield)
FOUND_OUTCOMES = tuple(outcome.value for outcome in SearchFoundOutcome)
PIVOT_MOVES = tuple(move.value for move in SearchPivot)
SURPRISE_LEVELS = tuple(level.value for level in SurpriseLevel)
MIND_CHANGE_OPTIONS = tuple(option.value for option in YesNo)
SEARCH_URGENCY_LEVELS = tuple(level.value for level in SearchUrgency)
PARALLELIZABLE_OPTIONS = tuple(option.value for option in YesNo)
_MAX_QUERIES_PLANNED = 3
_MIN_SEARCH_BUDGET = 1


class SearchWhyTool(_CotEventToolBase):
    """Builtin tool that records the specific missing fact motivating a search."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="search_why",
            description=(
                "Convert the impulse to search into a stated plan before any "
                "query runs, naming the precise fact that is missing and the "
                "step that cannot proceed without it. Searching without this "
                "discipline tends to wander: queries launched from a vague "
                "sense that more information would help multiply because "
                "nothing defined the condition under which they could stop. "
                "This tool asks for that stop condition up front, in addition "
                "to where the answer is expected to live and what will happen "
                "if it cannot be found there, so that the search has a shape "
                "before it begins rather than only a direction. An inability to "
                "state the missing fact this precisely is itself informative: "
                "it usually means the underlying need is not yet a search, only "
                "a general curiosity."
            ),
            parameters=(
                ToolParameter(
                    name="missing_fact",
                    type="string",
                    description=(
                        "The exact fact currently lacking, phrased narrowly "
                        "enough that a single located sentence could resolve "
                        "it. A description this specific is what allows the "
                        "stop condition and the eventual yield report to be "
                        "meaningful, since a vaguely scoped gap has no clean "
                        "way to be declared closed."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="why_needed",
                    type="string",
                    description=(
                        "The upcoming step that is blocked without this fact, "
                        "tying the search directly to the plan it serves. A "
                        "search with no dependent step named here is worth "
                        "questioning before it runs, since it may be curiosity "
                        "rather than a genuine blocker."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="stop_condition",
                    type="string",
                    description=(
                        "The finding that would end this search, decided "
                        "before the first query runs rather than improvised "
                        "afterward. A search without a stop condition defined "
                        "in advance has no honest way to declare itself "
                        "finished, which is exactly the condition that leads "
                        "to search rounds drifting well past their useful "
                        "point."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="expected_source",
                    type="string",
                    description=(
                        "An optional statement of where the fact is expected "
                        "to live, chosen from documentation, source code, the "
                        "open web, structured data, a teammate or collaborator, "
                        "prior memory, or a local cache. Recording this "
                        "expectation before searching lets a mismatch between "
                        "expectation and reality — discovering the fact lived "
                        "somewhere else entirely — become useful signal about "
                        "how this environment is actually organized."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="fallback_if_not_found",
                    type="string",
                    description=(
                        "The action to take if the search does not turn up the "
                        "fact, described as a genuine alternative course of "
                        "action rather than an open-ended intention to keep "
                        "looking. Continued unbounded searching is not a valid "
                        "fallback here; this field should name a different, "
                        "concrete path forward."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="urgency",
                    type="string",
                    description=(
                        "An optional rating of how urgently this gap needs to "
                        "close, ranging from background curiosity through "
                        "exploratory interest and near-term need up to a fully "
                        "blocking dependency. This field helps a reader "
                        "distinguish a search that can be deferred from one "
                        "that is actively holding up progress, which the "
                        "missing fact and stop condition alone do not always "
                        "make clear."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the search-why primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("missing_fact", "why_needed", "stop_condition", "fallback_if_not_found"))
        if error:
            return ToolResult.error(call.tool_name, error)

        source, source_error = CotEventParser.parse_enum(args.get("expected_source"), EXPECTED_SOURCES, "expected_source")
        if source_error:
            return ToolResult.error(call.tool_name, source_error)
        urgency, urgency_error = CotEventParser.parse_enum(args.get("urgency"), SEARCH_URGENCY_LEVELS, "urgency")
        if urgency_error:
            return ToolResult.error(call.tool_name, urgency_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_foraging import SearchWhyContextItem

        item = SearchWhyContextItem(
            primitive_id=self._next_primitive_id(),
            missing_fact=str(args["missing_fact"]).strip(),
            why_needed=str(args["why_needed"]).strip(),
            stop_condition=str(args["stop_condition"]).strip(),
            expected_source=source,
            fallback_if_not_found=str(args.get("fallback_if_not_found", "")).strip(),
            urgency=urgency,
        )
        return await self._record(item, call, {"expected_source": item.expected_source})


class SearchPlanTool(_CotEventToolBase):
    """Builtin tool that records the queries about to run and the rationale for their order."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="search_plan",
            description=(
                "Lay out the shape of a search round before executing it "
                "whenever that round will involve more than one query, whether "
                "run sequentially or in parallel. An unplanned round is how "
                "runs burn many steps discovering nothing in particular: the "
                "plan recorded here functions as a budget as much as a "
                "prediction, naming the maximum number of queries allowed "
                "before the agent must stop and reconsider, and the condition "
                "under which the round should be abandoned early even with "
                "budget remaining. A round with a stated plan either finds the "
                "target fact or fails in an informative way, and keeping the "
                "plan small is itself a discipline — needing many queries "
                "usually means the underlying missing fact was defined too "
                "broadly."
            ),
            parameters=(
                ToolParameter(
                    name="queries",
                    type="string",
                    description=(
                        "A JSON array of one to three objects describing each "
                        "planned query, where every object names the query "
                        "itself, optionally where it will run, and the kind of "
                        "result it is expected to produce. Together these "
                        "entries make the round's coverage explicit before "
                        "execution rather than something reconstructed "
                        "afterward from whatever happened to be run."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="order_rationale",
                    type="string",
                    description=(
                        "The reasoning behind the sequence the queries are "
                        "planned in, explaining what governs which one runs "
                        "first and why. This field is what makes the ordering "
                        "a deliberate decision rather than an arbitrary list, "
                        "and it should reflect genuine prioritization such as "
                        "cost, specificity, or dependency between the queries."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="max_queries",
                    type="number",
                    description=(
                        "An optional hard ceiling, as a positive integer, on "
                        "how many queries this round is allowed to consume "
                        "before the agent must stop and reconsider strategy "
                        "rather than continuing indefinitely. When omitted, "
                        "the number of planned queries serves as the implicit "
                        "ceiling, and any higher explicit value should be "
                        "justified by the order rationale."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="abort_if",
                    type="string",
                    description=(
                        "An optional condition under which the round should be "
                        "abandoned early even with budget remaining, such as an "
                        "early result contradicting the round's premise. When "
                        "this field is left empty, the plan is understood to "
                        "run to completion or to its budget rather than being "
                        "subject to an early exit."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="parallelizable",
                    type="string",
                    description=(
                        "An optional statement of whether the planned queries "
                        "could reasonably execute in parallel rather than "
                        "strictly in sequence, expressed as yes or no. This "
                        "field distinguishes a round genuinely constrained by "
                        "dependency between its queries from one that is "
                        "simply being run sequentially by default, which "
                        "affects how much a monitor should expect the round's "
                        "wall-clock cost to reflect its query count."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="fallback_strategy",
                    type="string",
                    description=(
                        "An optional description of what happens if the entire "
                        "planned round comes back empty, distinct from the "
                        "per-query expectations already captured in queries. "
                        "This field lets the plan anticipate total failure of "
                        "the approach, not only partial shortfalls in "
                        "individual query results."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the search plan primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        queries, queries_error = self._parse_queries(args.get("queries"))
        if queries_error:
            return ToolResult.error(call.tool_name, queries_error)
        max_queries = CotEventParser.parse_int(args.get("max_queries"), minimum=_MIN_SEARCH_BUDGET)
        parallelizable, parallelizable_error = CotEventParser.parse_enum(
            args.get("parallelizable"), PARALLELIZABLE_OPTIONS, "parallelizable"
        )
        if parallelizable_error:
            return ToolResult.error(call.tool_name, parallelizable_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_foraging import SearchPlanContextItem

        item = SearchPlanContextItem(
            primitive_id=self._next_primitive_id(),
            queries=tuple(queries or ()),
            order_rationale=str(args["order_rationale"]).strip(),
            max_queries=max_queries,
            abort_if=CotEventParser.optional_text(args.get("abort_if")),
            parallelizable=parallelizable,
            fallback_strategy=CotEventParser.optional_text(args.get("fallback_strategy")),
        )
        return await self._record(item, call, {"query_count": len(item.queries)})

    def _parse_queries(self, value: Any) -> tuple[list[dict] | None, str | None]:
        # Parses the queries JSON array, validating each query string and expected_yield enum.
        parsed, error = CotEventParser.parse_json_objects(value, "queries", _MAX_QUERIES_PLANNED)
        if error:
            return None, error
        entries: list[dict] = []
        for index, entry in enumerate(parsed or ()):
            query = str(entry.get("query", "") or "").strip()
            if not query:
                return None, f"Entry {index} in 'queries' is missing a non-empty 'query' key."
            yield_value, yield_error = CotEventParser.parse_enum(
                entry.get("expected_yield"), EXPECTED_YIELDS, f"queries[{index}].expected_yield"
            )
            if yield_error:
                return None, yield_error
            normalized = dict(entry)
            normalized["query"] = query
            normalized["expected_yield"] = yield_value or EXPECTED_YIELDS[2]
            entries.append(normalized)
        if not entries:
            return None, "Field 'queries' must contain at least one object."
        return entries, None


class SearchYieldTool(_CotEventToolBase):
    """Builtin tool that records what a search round actually produced."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="search_yield",
            description=(
                "Report what a completed search round actually produced "
                "against what it was planned to find, immediately after every "
                "planned round concludes. This is where search discipline is "
                "actually measured, closing the loop that the earlier "
                "why-and-plan pair opened; queries spent should be reported "
                "honestly, including any that ran outside the original plan. "
                "The most valuable possible outcome here is discovering that "
                "results contradict the premise the search was launched under, "
                "since that finding is worth more than a clean hit and burying "
                "it is how a run stays wrong for longer than necessary. The "
                "call closes with a deliberate next move, because continuing "
                "without deciding is how a small, bounded round quietly turns "
                "into an unbounded one."
            ),
            parameters=(
                ToolParameter(
                    name="found",
                    type="string",
                    description=(
                        "An honest verdict on what the round yielded, "
                        "distinguishing a full match against the stop "
                        "condition, a partial or alternative result, a "
                        "genuinely empty outcome, an overwhelming volume of "
                        "unfiltered material, and a result that actively "
                        "contradicts the premise of the search. This field "
                        "should reflect the actual result rather than the "
                        "closest comfortable category, since the honest "
                        "distinction between these outcomes is the entire "
                        "point of reporting yield separately from the plan."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="queries_spent",
                    type="number",
                    description=(
                        "The total number of queries the round actually "
                        "consumed, as a non-negative integer, including any run "
                        "outside the original plan. When this exceeds the "
                        "planned budget, that overrun is itself useful "
                        "telemetry and should be reported exactly as it "
                        "happened rather than rounded down to match "
                        "expectations."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="best_result",
                    type="string",
                    description=(
                        "An optional description of the single most useful "
                        "thing the round produced. This field should generally "
                        "be omitted when the found verdict indicates nothing "
                        "was produced, since forcing a value here in that case "
                        "would misrepresent the round's actual outcome."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="missing_still",
                    type="string",
                    description=(
                        "An optional description of what portion of the "
                        "original missing fact remains unresolved after this "
                        "round. When the found verdict indicates a full match, "
                        "this field should state plainly that nothing remains "
                        "rather than being left ambiguous."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="pivot",
                    type="string",
                    description=(
                        "The deliberate next move chosen in response to this "
                        "round's outcome, distinguishing proceeding to the "
                        "originally blocked step, narrowing the search, "
                        "refining the query terms, broadening the search, "
                        "switching to a different source entirely, or invoking "
                        "the fallback named when the search was first "
                        "declared. Choosing this deliberately, rather than "
                        "defaulting to another attempt, is what keeps a small "
                        "planned round from silently expanding."
                    ),
                    required=False,
                    default="continue",
                ),
                ToolParameter(
                    name="surprise",
                    type="string",
                    description=(
                        "An optional rating of how much the results diverged "
                        "from what was expected when the search was planned, "
                        "ranging from fully expected through mild and moderate "
                        "divergence up to results that were surprising or "
                        "outright alarming. A pattern of consistently high "
                        "surprise across many search rounds is itself a signal "
                        "that the agent's working model of this environment "
                        "needs revisiting."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the search yield primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        found, found_error = CotEventParser.parse_enum(args.get("found"), FOUND_OUTCOMES, "found")
        if found_error:
            return ToolResult.error(call.tool_name, found_error)
        queries_spent = CotEventParser.parse_int(args.get("queries_spent"))
        if queries_spent is None:
            return ToolResult.error(call.tool_name, "Field 'queries_spent' must be a non-negative integer.")
        pivot, pivot_error = CotEventParser.parse_enum(args.get("pivot"), PIVOT_MOVES, "pivot")
        if pivot_error:
            return ToolResult.error(call.tool_name, pivot_error)
        surprise, surprise_error = CotEventParser.parse_enum(args.get("surprise"), SURPRISE_LEVELS, "surprise")
        if surprise_error:
            return ToolResult.error(call.tool_name, surprise_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_foraging import SearchYieldContextItem

        item = SearchYieldContextItem(
            primitive_id=self._next_primitive_id(),
            found=found or FOUND_OUTCOMES[0],
            queries_spent=queries_spent,
            best_result=CotEventParser.optional_text(args.get("best_result")),
            missing_still=CotEventParser.optional_text(args.get("missing_still")),
            pivot=pivot or PIVOT_MOVES[0],
            surprise=surprise,
        )
        return await self._record(
            item,
            call,
            {"found": item.found, "queries_spent": item.queries_spent, "pivot": item.pivot},
        )


class EnoughTool(_CotEventToolBase):
    """Builtin tool that records the declaration that existing evidence is sufficient to act."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="enough",
            description=(
                "Declare explicitly, on the record, that the evidence "
                "currently in hand is sufficient to act, functioning as the "
                "stop rule that ends further searching, deliberating, and "
                "second-guessing. This declaration should be made before "
                "committing to whatever action the evidence supports, since "
                "both failure modes on either side of it are costly: acting "
                "before evidence is actually sufficient produces confidently "
                "wrong outcomes, while never declaring sufficiency produces "
                "research that outlives the question it was meant to answer. "
                "The declaration is deliberately falsifiable, requiring a "
                "statement of what would change the verdict, because a "
                "sufficiency claim that nothing could ever overturn is not "
                "genuine confidence but attachment to a conclusion. Naming the "
                "weakest point the case rests on is the honesty check built "
                "into this tool, since every body of evidence has one and "
                "refusing to name it does not make it disappear."
            ),
            parameters=(
                ToolParameter(
                    name="acting_on",
                    type="string",
                    description=(
                        "The decision or action this evidence now authorizes, "
                        "stated concretely enough that a reader can tell "
                        "exactly what is about to happen as a result of this "
                        "declaration."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="evidence_count",
                    type="number",
                    description=(
                        "The number of independent pieces of evidence "
                        "supporting the action, as a non-negative integer. "
                        "Multiple observations drawn from the same underlying "
                        "source should be counted once, since this field is "
                        "meant to reflect genuine independent corroboration "
                        "rather than the raw volume of supporting material."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="would_change_mind",
                    type="string",
                    description=(
                        "Whether any realistically obtainable finding could "
                        "still reverse this action, expressed as yes or no. A "
                        "no answer is a strong claim that should be reserved "
                        "for cases that are genuinely settled, since applying "
                        "it broadly undermines the honesty this declaration "
                        "depends on; an honest yes paired with a stated "
                        "reversing condition is the well-calibrated default."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="strongest_evidence",
                    type="string",
                    description=(
                        "The single strongest piece of evidence supporting the "
                        "action, described specifically enough that a reader "
                        "could judge its weight independently rather than "
                        "having to trust the sufficiency verdict at face "
                        "value."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="weakest_link",
                    type="string",
                    description=(
                        "The shakiest point the case for sufficiency actually "
                        "rests on, named plainly. Every body of evidence has "
                        "one, and stating it here converts it from a hidden "
                        "risk into a known and reviewable one, which is the "
                        "central purpose of this field within the "
                        "declaration."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="what_would_reverse",
                    type="string",
                    description=(
                        "The concrete finding that would overturn this "
                        "decision, expected whenever would_change_mind is yes. "
                        "This field is what makes the declaration genuinely "
                        "falsifiable rather than only nominally so, since it "
                        "gives a later reader something specific to check the "
                        "decision against if new information arrives."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the sufficiency declaration primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("acting_on", "would_change_mind", "strongest_evidence", "weakest_link"))
        if error:
            return ToolResult.error(call.tool_name, error)
        evidence_count = CotEventParser.parse_int(args.get("evidence_count"))
        if evidence_count is None:
            return ToolResult.error(call.tool_name, "Field 'evidence_count' must be a non-negative integer.")
        would_change, change_error = CotEventParser.parse_enum(args.get("would_change_mind"), MIND_CHANGE_OPTIONS, "would_change_mind")
        if change_error:
            return ToolResult.error(call.tool_name, change_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_foraging import EnoughContextItem

        item = EnoughContextItem(
            primitive_id=self._next_primitive_id(),
            acting_on=str(args["acting_on"]).strip(),
            evidence_count=evidence_count,
            would_change_mind=would_change or MIND_CHANGE_OPTIONS[1],
            strongest_evidence=str(args["strongest_evidence"]).strip(),
            weakest_link=str(args["weakest_link"]).strip(),
            what_would_reverse=CotEventParser.optional_text(args.get("what_would_reverse")),
        )
        return await self._record(
            item,
            call,
            {"evidence_count": item.evidence_count, "would_change_mind": item.would_change_mind},
        )


__all__ = [
    "EnoughTool",
    "SearchPlanTool",
    "SearchWhyTool",
    "SearchYieldTool",
]
