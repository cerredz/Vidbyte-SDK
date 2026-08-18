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
Similar Files:
    - `vidbyte/tools/builtins/cot_context.py`
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

EXPECTED_SOURCES = ("docs", "code", "web", "data", "teammate", "memory")
EXPECTED_YIELDS = ("exact_hit", "partial", "exploratory")
FOUND_OUTCOMES = ("exactly", "partially", "nothing", "contradicts_expectation")
PIVOT_MOVES = ("continue", "refine", "change_tool", "abandon_line")
SURPRISE_LEVELS = ("expected", "mild", "major")
MIND_CHANGE_OPTIONS = ("yes", "no")
_MAX_QUERIES_PLANNED = 3
_MIN_SEARCH_BUDGET = 1


class SearchWhyTool(_CotEventToolBase):
    """Builtin tool that records the specific missing fact motivating a search."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="search_why",
            description=(
                "Before you search for anything, name the exact fact that is "
                "missing and why your next step cannot proceed without it. Use "
                "this every time you are about to run a search, open docs, grep "
                "code, or query data — the record converts searching from a "
                "reflex into a plan. The failure mode this prevents is wandering "
                "search: queries launched from a vague itch ('let me look into "
                "the config') that multiply because nothing defined when they "
                "could stop. State the missing fact so precisely that a single "
                "found sentence could satisfy it, state what finding it unlocks, "
                "and state in advance the condition under which you will stop "
                "searching. If you cannot articulate the missing fact, you do "
                "not have a search yet — you have a browsing impulse."
            ),
            parameters=(
                ToolParameter(
                    name="missing_fact",
                    type="string",
                    description=(
                        "The exact fact you lack, phrased so one found sentence "
                        "could satisfy it: 'the name of the env variable that "
                        "sets the batch size', 'whether the API supports cursor "
                        "pagination'. Not 'information about pagination'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="why_needed",
                    type="string",
                    description=(
                        "Which upcoming step is blocked without this fact, one "
                        "sentence: 'cannot write the fetch loop without knowing "
                        "the pagination mechanism'. This ties the search to the "
                        "plan — searches with no dependent step are suspects."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="stop_condition",
                    type="string",
                    description=(
                        "The finding that ends this search, stated before you "
                        "start: 'finding the env var name in the config docs', "
                        "'either a cursor parameter in the API reference or "
                        "confirming the section does not mention one'. A search "
                        "without a stop condition has no way to succeed."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="expected_source",
                    type="string",
                    description=(
                        "Optional: where you expect the fact to live. Use exactly "
                        "one of: 'docs', 'code', 'web', 'data', 'teammate', "
                        "'memory'. Wrong expectations here are cheap signal "
                        "about where knowledge actually lives in this "
                        "environment."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="fallback_if_not_found",
                    type="string",
                    description=(
                        "What you will do if the fact cannot be found, one "
                        "sentence: 'assume offset pagination and verify with a "
                        "probe request', 'ask the user'. Searching forever is "
                        "not a fallback — name a different action."
                    ),
                    required=True,
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

        self._counter += 1
        from vidbyte.context.primitives.cot_foraging import SearchWhyContextItem

        item = SearchWhyContextItem(
            primitive_id=self._next_primitive_id(),
            missing_fact=str(args["missing_fact"]).strip(),
            why_needed=str(args["why_needed"]).strip(),
            stop_condition=str(args["stop_condition"]).strip(),
            expected_source=source,
            fallback_if_not_found=str(args.get("fallback_if_not_found", "")).strip(),
        )
        return await self._record(item, call, {"expected_source": item.expected_source})


class SearchPlanTool(_CotEventToolBase):
    """Builtin tool that records the queries about to run and the rationale for their order."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="search_plan",
            description=(
                "Before executing a search round, lay out the specific queries "
                "you will run, what each is expected to produce, and why they "
                "are in that order. Use this whenever a search will take more "
                "than one query — parallel or sequential — so the round has a "
                "shape you can be held to. The plan is a budget as much as a "
                "prediction: name the maximum queries you will allow before "
                "stopping to reconsider, and the condition under which you "
                "abort early. An unplanned search round is how runs burn ten "
                "steps discovering nothing; a planned one either finds the fact "
                "or fails in an informative way. Keep it to at most three "
                "queries — if you think you need more, your search_why was "
                "probably too vague."
            ),
            parameters=(
                ToolParameter(
                    name="queries",
                    type="string",
                    description=(
                        "A JSON array of 1 to 3 objects, each with keys 'query' "
                        "(the exact query or file you will run), 'target' "
                        "(optional: where it will run — 'config docs', 'src/'), "
                        "and 'expected_yield' (exactly one of 'exact_hit', "
                        "'partial', 'exploratory'). Example: "
                        "[{\"query\": \"rate limit site:docs\", \"target\": \"web\", "
                        "\"expected_yield\": \"exact_hit\"}]."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="order_rationale",
                    type="string",
                    description=(
                        "Why the queries are in this order, one sentence: "
                        "'cheapest most-specific first; exploratory only if "
                        "both miss'. The rationale is what makes the order a "
                        "decision rather than a shuffle."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="max_queries",
                    type="number",
                    description=(
                        "Optional: the hard ceiling on queries for this round "
                        "before you stop and reconsider strategy — a positive "
                        "integer. Default is the number of planned queries; set "
                        "higher only if you can say why."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="abort_if",
                    type="string",
                    description=(
                        "Optional: the condition under which you abandon the "
                        "round early even with budget remaining — 'first result "
                        "contradicts the premise of the search'. Absence of this "
                        "field means run the plan to completion or budget."
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

        self._counter += 1
        from vidbyte.context.primitives.cot_foraging import SearchPlanContextItem

        item = SearchPlanContextItem(
            primitive_id=self._next_primitive_id(),
            queries=tuple(queries or ()),
            order_rationale=str(args["order_rationale"]).strip(),
            max_queries=max_queries,
            abort_if=CotEventParser.optional_text(args.get("abort_if")),
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
                "After a search round completes, report what it actually "
                "produced against what the plan expected. Use this immediately "
                "after every planned search round — it closes the loop that "
                "search_why and search_plan opened, and it is where search "
                "discipline is actually measured. Report the queries spent "
                "honestly, including ones not in the plan. The most valuable "
                "outcome here is 'contradicts_expectation': finding that the "
                "world differs from what you assumed is worth more than a "
                "clean hit, and burying it is how runs stay wrong. Then name "
                "your next move deliberately — continuing without deciding is "
                "how three-query rounds become fifteen."
            ),
            parameters=(
                ToolParameter(
                    name="found",
                    type="string",
                    description=(
                        "Honest yield verdict. Use exactly one of: 'exactly' "
                        "(the stop condition was met — the missing fact is now "
                        "in hand), 'partially' (useful material but the fact is "
                        "still incomplete), 'nothing' (no usable result), "
                        "'contradicts_expectation' (results showed the premise "
                        "of the search itself was wrong)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="queries_spent",
                    type="number",
                    description=(
                        "How many queries the round actually consumed, including "
                        "unplanned ones — a non-negative integer. If this "
                        "exceeds your planned budget, that overrun is the "
                        "telemetry; report it straight."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="best_result",
                    type="string",
                    description=(
                        "Optional: the single most useful thing the round "
                        "produced, one sentence. Omit when found is 'nothing'."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="missing_still",
                    type="string",
                    description=(
                        "Optional: what portion of the original missing fact "
                        "remains unresolved after this round. 'Nothing remains' "
                        "when found is 'exactly'."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="pivot",
                    type="string",
                    description=(
                        "Your deliberate next move. Use exactly one of: "
                        "'continue' (proceed to the blocked step — search "
                        "succeeded), 'refine' (re-query with sharper terms), "
                        "'change_tool' (this source cannot answer; try a "
                        "different one), 'abandon_line' (invoke the fallback "
                        "from search_why). Defaults to 'continue'."
                    ),
                    required=False,
                    default="continue",
                ),
                ToolParameter(
                    name="surprise",
                    type="string",
                    description=(
                        "Optional: how the results compared to your "
                        "expectations. Use exactly one of: 'expected', 'mild' "
                        "(somewhat different), 'major' (the premise shifted). "
                        "Chronic 'major' surprises mean your world model of "
                        "this environment is off — worth knowing."
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
                "Declare, out loud and on the record, that the evidence you "
                "have is sufficient to act — this is the stop rule that ends "
                "searching, deliberating, and second-guessing. Use this before "
                "committing to the action your evidence supports: writing the "
                "conclusion, applying the change, giving the answer. Both "
                "failure modes are expensive: acting before enough (confident "
                "wrong answers) and never declaring enough (research spirals "
                "that outlive the question). This declaration is falsifiable "
                "by design — you must name what would change your mind. If "
                "nothing would change your mind, that is not sufficiency, "
                "that is attachment; say the former only if you mean it. The "
                "weakest_link field is the honesty check: every evidence base "
                "has one, and naming it is the price of the declaration."
            ),
            parameters=(
                ToolParameter(
                    name="acting_on",
                    type="string",
                    description=(
                        "The decision or action this evidence now authorizes, "
                        "one sentence: 'apply the keyset pagination migration', "
                        "'report that the outage cause is the expired token'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="evidence_count",
                    type="number",
                    description=(
                        "How many independent pieces of evidence support the "
                        "action — a non-negative integer. Corroborating slices "
                        "of one source count once; independent confirmations "
                        "count separately."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="would_change_mind",
                    type="string",
                    description=(
                        "Whether any realistically obtainable finding would "
                        "reverse this action: 'yes' or 'no'. 'no' is a strong "
                        "claim — appropriate for tautologies and verified "
                        "facts, suspect everywhere else. An honest 'yes' with "
                        "what_would_reverse filled is the well-calibrated "
                        "default."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="strongest_evidence",
                    type="string",
                    description=(
                        "The single strongest piece of supporting evidence, one "
                        "sentence: 'the repro passes consistently with the fix "
                        "and fails without it'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="weakest_link",
                    type="string",
                    description=(
                        "The shakiest thing the case rests on, one sentence: "
                        "'all confirmation comes from the dev environment, "
                        "never production'. Every evidence base has one; "
                        "refusing to name it converts it from a known risk "
                        "into a hidden one."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="what_would_reverse",
                    type="string",
                    description=(
                        "Optional but expected when would_change_mind is 'yes': "
                        "the concrete finding that would reverse the decision, "
                        "one sentence — 'a single production counter-example'."
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
