"""Context Protocol Header

Description:
    Implements the meta-monitoring tools — records about the monitoring
    records themselves.
Purpose:
    Lets the model audit its own telemetry: contradictions between records,
    ritualized versus earning tool calls, events no tool could capture,
    direction-changing signals, self-reported calibration, and drift between
    tool descriptions and actual usage.
Architecture:
    - RecordDisputeTool, RitualCheckTool, TelemetryGapTool, SignalHighlightTool,
      CalibrationSelfReportTool, DescriptionDriftTool: _CotEventToolBase
      subclasses that validate, upsert a matching cot_meta primitive, and
      return parsed values in ToolResult.metadata.
Relations:
    Reuses CotEventParser and _CotEventToolBase from builtins.cot_events.
    Categorical fields are sourced from vidbyte.lib.enums.cot.
Similar Files:
    - `vidbyte/tools/builtins/cot/context.py`
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.enums.cot import (
    BiasAssessment,
    CalibrationTrend,
    DirectionChangeLevel,
    DisputeVerdict,
    GapFrequency,
    GapSeverity,
    MonitoringHealth,
    SurpriseLevel,
    YesNo,
)
from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

DISPUTE_VERDICTS = tuple(verdict.value for verdict in DisputeVerdict)
MONITORING_HEALTH_LEVELS = tuple(level.value for level in MonitoringHealth)
GAP_SEVERITIES = tuple(severity.value for severity in GapSeverity)
DIRECTION_CHANGE_LEVELS = tuple(level.value for level in DirectionChangeLevel)
SURPRISE_LEVELS = tuple(level.value for level in SurpriseLevel)
BIAS_ASSESSMENTS = tuple(assessment.value for assessment in BiasAssessment)
GAP_FREQUENCIES = tuple(frequency.value for frequency in GapFrequency)
CALIBRATION_TRENDS = tuple(trend.value for trend in CalibrationTrend)
BLOCKING_OPTIONS = tuple(option.value for option in YesNo)
_MAX_RITUAL_ENTRIES = 5
RITUAL_CHECK_SNAPSHOT_ID = "ritual_check:current"
CALIBRATION_SNAPSHOT_ID = "calibration:current"


class RecordDisputeTool(_CotEventToolBase):
    """Builtin tool that records a contradiction between two of the agent's own records."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="record_dispute",
            description=(
                "When two of the agent's own prior records contradict each "
                "other, flag the dispute explicitly rather than quietly "
                "letting the more recent one win by default. Contradictions "
                "surface in many forms: an assumption marked verified that a "
                "later observation actually undermines, or a prediction "
                "recorded as on-track sitting beside a separate scan that "
                "lists its own premise as likely to fail. An unflagged "
                "contradiction is worse than either record alone, because "
                "every downstream reader, including the agent itself later in "
                "the run, ends up trusting both simultaneously. Adjudicating "
                "honestly means naming which record is actually wrong and why, "
                "or, when the records turn out to be compatible after all, "
                "explaining what reconciles them rather than resolving the "
                "dispute by convenience or by which record happened to come "
                "later."
            ),
            parameters=(
                ToolParameter(
                    name="record_a",
                    type="string",
                    description=(
                        "The first record in the dispute, named and closely "
                        "paraphrased or quoted so a reader can identify "
                        "exactly which prior record this refers to."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="record_b",
                    type="string",
                    description=(
                        "The second record it conflicts with, described with "
                        "the same precision as the first. Labeling them a and "
                        "b carries no ordering judgment; that judgment belongs "
                        "entirely to the verdict field."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="contradiction",
                    type="string",
                    description=(
                        "The exact point of conflict between the two records, "
                        "stated specifically enough that a reader could "
                        "verify the contradiction independently. If the "
                        "conflict cannot be stated this precisely, it may not "
                        "actually be one."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="which_is_wrong",
                    type="string",
                    description=(
                        "The adjudication of the dispute, distinguishing the "
                        "first record being wrong, the second being wrong, "
                        "both having been premature or mistaken in their own "
                        "way, neither actually being wrong because the "
                        "records are reconcilable, and a genuinely "
                        "inconclusive case where the adjudication cannot yet "
                        "be made."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="resolution",
                    type="string",
                    description=(
                        "An optional description of what reconciles the "
                        "dispute or repairs the wrong record, expected "
                        "whenever the verdict indicates the records are "
                        "actually compatible rather than genuinely opposed."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="discovered_via",
                    type="string",
                    description=(
                        "An optional account of how this contradiction was "
                        "actually noticed, such as a routine read-back, an "
                        "unrelated task surfacing the conflict, or a direct "
                        "comparison performed deliberately. This field helps "
                        "distinguish contradictions caught by discipline from "
                        "ones caught by accident."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the dispute primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("record_a", "record_b", "contradiction", "which_is_wrong"))
        if error:
            return ToolResult.error(call.tool_name, error)
        which, which_error = CotEventParser.parse_enum(args.get("which_is_wrong"), DISPUTE_VERDICTS, "which_is_wrong")
        if which_error:
            return ToolResult.error(call.tool_name, which_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_meta import RecordDisputeContextItem

        item = RecordDisputeContextItem(
            primitive_id=self._next_primitive_id(),
            record_a=str(args["record_a"]).strip(),
            record_b=str(args["record_b"]).strip(),
            contradiction=str(args["contradiction"]).strip(),
            which_is_wrong=which or DISPUTE_VERDICTS[3],
            resolution=CotEventParser.optional_text(args.get("resolution")),
            discovered_via=CotEventParser.optional_text(args.get("discovered_via")),
        )
        return await self._record(item, call, {"which_is_wrong": item.which_is_wrong})


class RitualCheckTool(_CotEventToolBase):
    """Builtin tool that snapshots which monitoring calls have become reflexive versus still earning their cost."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="ritual_check",
            description=(
                "Periodically audit the agent's own monitoring calls to see "
                "which have become reflexive habit and which are still "
                "genuinely changing what happens next. This should be used "
                "sparingly, roughly once per long run or per major phase "
                "rather than at every step, since the audit itself has a "
                "cost. The distinction it draws is the entire point: a "
                "monitoring call that never changes an outcome has become a "
                "ritual, and rituals consume attention while producing only "
                "the appearance of vigilance rather than its substance. The "
                "blind spots this audit surfaces matter as much as the two "
                "lists it produces, since the moments where something "
                "important happened and no record captured it are where the "
                "telemetry system is itself failing, and this snapshot "
                "replaces whatever the previous audit found."
            ),
            parameters=(
                ToolParameter(
                    name="reflexive",
                    type="string",
                    description=(
                        "A JSON array of up to five strings naming monitoring "
                        "calls being made on autopilot, where entries tend to "
                        "carry stock phrasing and verdicts that never "
                        "surprise. An empty array is a strong claim and "
                        "should only be given when it is genuinely true."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="still_earning",
                    type="string",
                    description=(
                        "A JSON array of up to five strings naming calls that "
                        "have genuinely changed a decision at some point in "
                        "the run. These are the calls worth actively "
                        "protecting from being trimmed away."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="blind_spots",
                    type="string",
                    description=(
                        "An optional account of moments in the run where "
                        "something important happened and no available tool "
                        "call captured it. Gaps surfaced here are the raw "
                        "material for future tool ideas and should be stated "
                        "concretely rather than as a general sense that "
                        "something might have been missed."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="overall",
                    type="string",
                    description=(
                        "An optional overall verdict on monitoring weight, "
                        "distinguishing a sparse or under-used set of calls, "
                        "a genuinely neglected set, a healthy balance where "
                        "records earn their weight, a heavy set with "
                        "noticeable but uneven cost, and a smothering set "
                        "that is actively crowding out real work."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="sample_size",
                    type="number",
                    description=(
                        "An optional non-negative integer counting how many "
                        "monitoring calls this audit actually reviewed. This "
                        "field lets a reader judge how much of the run's "
                        "telemetry the reflexive and still-earning "
                        "classifications are actually based on."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="time_window",
                    type="string",
                    description=(
                        "An optional description of the span of the run this "
                        "audit covers, such as a phase name or a step range. "
                        "This gives the snapshot a scope beyond the implicit "
                        "'everything so far' default."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the ritual snapshot primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        reflexive, reflexive_error = self._parse_entries(args.get("reflexive"), "reflexive")
        if reflexive_error:
            return ToolResult.error(call.tool_name, reflexive_error)
        earning, earning_error = self._parse_entries(args.get("still_earning"), "still_earning")
        if earning_error:
            return ToolResult.error(call.tool_name, earning_error)
        overall, overall_error = CotEventParser.parse_enum(args.get("overall"), MONITORING_HEALTH_LEVELS, "overall")
        if overall_error:
            return ToolResult.error(call.tool_name, overall_error)
        sample_size = CotEventParser.parse_int(args.get("sample_size"))

        from vidbyte.context.primitives.cot_meta import RitualCheckContextItem

        item = RitualCheckContextItem(
            primitive_id=RITUAL_CHECK_SNAPSHOT_ID,
            reflexive=tuple(reflexive or ()),
            still_earning=tuple(earning or ()),
            blind_spots=CotEventParser.optional_text(args.get("blind_spots")),
            overall=overall,
            sample_size=sample_size,
            time_window=CotEventParser.optional_text(args.get("time_window")),
        )
        return await self._record(
            item,
            call,
            {"reflexive_count": len(item.reflexive), "earning_count": len(item.still_earning), "overall": item.overall},
        )

    def _parse_entries(self, value: Any, field_name: str) -> tuple[list[str] | None, str | None]:
        # Parses one ritual-check JSON array into up to 5 possibly-empty strings.
        parsed, error = CotEventParser.parse_json_strings(value, field_name, _MAX_RITUAL_ENTRIES)
        if error:
            return None, error
        return [entry for entry in parsed or () if entry] or [], None


class TelemetryGapTool(_CotEventToolBase):
    """Builtin tool that records an important event no available tool could capture."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="telemetry_gap",
            description=(
                "When something important happens that none of the available "
                "monitoring tools can actually record, report the gap itself "
                "rather than forcing the event into a tool that does not fit "
                "it. This is the monitoring system's own feedback channel, "
                "reserved for moments such as a shift in understanding too "
                "diffuse for any single existing tool, an interaction between "
                "two records that no field captures, or a judgment that had "
                "no natural home among the available tools. Misfiling an "
                "event into the wrong tool to avoid using this one corrupts "
                "that tool's own telemetry, so the event and the record that "
                "was actually wanted should both be stated plainly here "
                "instead. Collected over time, these records are how the "
                "monitoring tool family learns what it is still missing."
            ),
            parameters=(
                ToolParameter(
                    name="event",
                    type="string",
                    description=(
                        "What actually happened, described specifically "
                        "enough that a reader unfamiliar with the moment "
                        "could understand why no existing tool fit it."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="wanted_to_record",
                    type="string",
                    description=(
                        "The record that was actually wanted for this event, "
                        "described concretely enough that a new tool could "
                        "plausibly be designed from this description alone."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="closest_tool",
                    type="string",
                    description=(
                        "An optional name of the tool considered and rejected "
                        "as a fit for this event, along with why it would "
                        "have distorted the record rather than captured it "
                        "cleanly."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="severity",
                    type="string",
                    description=(
                        "An optional rating of how much this gap actually "
                        "costs, distinguishing a minor and largely cosmetic "
                        "loss, a moderate loss, a notable loss where a real "
                        "signal about the run goes unrecorded, a critical "
                        "loss, and a catastrophic one where a later reader "
                        "would seriously misunderstand the run without it."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="frequency",
                    type="string",
                    description=(
                        "An optional statement of how often this kind of gap "
                        "recurs, distinguishing a one-off occurrence, an "
                        "occasional pattern, a recurring one, and a constant "
                        "one. A recurring or constant gap is a much stronger "
                        "signal that a new tool is actually needed than a "
                        "single isolated instance."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="workaround_used",
                    type="string",
                    description=(
                        "An optional description of how the event was "
                        "recorded in practice despite no tool fitting it "
                        "cleanly, such as forcing it into a loosely related "
                        "tool or leaving it out of structured telemetry "
                        "entirely."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the telemetry gap primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("event", "wanted_to_record"))
        if error:
            return ToolResult.error(call.tool_name, error)
        severity, severity_error = CotEventParser.parse_enum(args.get("severity"), GAP_SEVERITIES, "severity")
        if severity_error:
            return ToolResult.error(call.tool_name, severity_error)
        frequency, frequency_error = CotEventParser.parse_enum(args.get("frequency"), GAP_FREQUENCIES, "frequency")
        if frequency_error:
            return ToolResult.error(call.tool_name, frequency_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_meta import TelemetryGapContextItem

        item = TelemetryGapContextItem(
            primitive_id=self._next_primitive_id(),
            event=str(args["event"]).strip(),
            wanted_to_record=str(args["wanted_to_record"]).strip(),
            closest_tool=CotEventParser.optional_text(args.get("closest_tool")),
            severity=severity,
            frequency=frequency,
            workaround_used=CotEventParser.optional_text(args.get("workaround_used")),
        )
        return await self._record(item, call, {"severity": item.severity})


class SignalHighlightTool(_CotEventToolBase):
    """Builtin tool that records which monitoring record most changed the run's direction."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="signal_highlight",
            description=(
                "Occasionally, a single monitoring record genuinely changes "
                "everything that follows it; identify those moments "
                "explicitly and mark them apart from the ordinary flow of "
                "records. Use this when a specific record can be pointed to "
                "as having altered the course of the run, such as a falsified "
                "hypothesis that ended an approach, a sufficiency declaration "
                "that stopped a spiral of further searching, or a failure "
                "scan entry that reshaped the plan. Most records merely "
                "describe the run as it happens, while a small number "
                "actually steer it, and without this marker the two look "
                "equally causal to a later reader. The counterfactual field "
                "is what keeps this honest: if the run's actual course cannot "
                "be shown to have changed because of the record, it is not a "
                "genuine signal highlight, and inflating this record is the "
                "exact ritualization the ritual_check tool exists to catch."
            ),
            parameters=(
                ToolParameter(
                    name="record",
                    type="string",
                    description=(
                        "The steering record, named and closely paraphrased "
                        "or quoted so a reader can identify exactly which "
                        "prior record actually changed the run's course."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="changed_direction",
                    type="string",
                    description=(
                        "How much the record actually steered the run, "
                        "distinguishing a full change of course, a majorly "
                        "altered approach, a slight tuning of the existing "
                        "approach, confirmation of an existing course with no "
                        "real change, and a case where the record actively "
                        "reversed an earlier decision."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="would_have_happened",
                    type="string",
                    description=(
                        "The counterfactual describing what the run would "
                        "have done without this record. This is the honesty "
                        "check for the whole entry and should be filled in "
                        "with the same care as the record itself, not treated "
                        "as an afterthought."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="surprise",
                    type="string",
                    description=(
                        "An optional rating of how the record compared to "
                        "prior expectations, distinguishing a fully expected "
                        "confirmation, a mildly surprising finding, a "
                        "genuinely surprising one, and one that was outright "
                        "alarming. An alarming record generally deserves a "
                        "follow-up decision beyond simply being highlighted."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="downstream_effect",
                    type="string",
                    description=(
                        "An optional description of the concrete effect this "
                        "steering record had on later work, distinct from the "
                        "counterfactual of what would have happened without "
                        "it. This field completes the picture by stating what "
                        "actually did happen as a result."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="discovered_when",
                    type="string",
                    description=(
                        "An optional statement of when the steering effect of "
                        "this record was actually noticed, which is not "
                        "always the same moment the record itself was made. A "
                        "record can steer the run well before anyone "
                        "recognizes that it did."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the signal highlight primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("record", "changed_direction", "would_have_happened"))
        if error:
            return ToolResult.error(call.tool_name, error)
        changed, changed_error = CotEventParser.parse_enum(
            args.get("changed_direction"), DIRECTION_CHANGE_LEVELS, "changed_direction"
        )
        if changed_error:
            return ToolResult.error(call.tool_name, changed_error)
        surprise, surprise_error = CotEventParser.parse_enum(args.get("surprise"), SURPRISE_LEVELS, "surprise")
        if surprise_error:
            return ToolResult.error(call.tool_name, surprise_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_meta import SignalHighlightContextItem

        item = SignalHighlightContextItem(
            primitive_id=self._next_primitive_id(),
            record=str(args["record"]).strip(),
            changed_direction=changed or DIRECTION_CHANGE_LEVELS[2],
            would_have_happened=str(args["would_have_happened"]).strip(),
            surprise=surprise,
            downstream_effect=CotEventParser.optional_text(args.get("downstream_effect")),
            discovered_when=CotEventParser.optional_text(args.get("discovered_when")),
        )
        return await self._record(item, call, {"changed_direction": item.changed_direction})


class CalibrationSelfReportTool(_CotEventToolBase):
    """Builtin tool that snapshots the agent's self-estimated prediction calibration."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="calibration_self_report",
            description=(
                "Periodically estimate the agent's own track record by asking "
                "how many of the predictions recorded so far in the run are "
                "believed to have come true. This is a self-audit meant to "
                "run once per run or per major phase, not at every step, and "
                "its value comes from the comparison a monitor can make "
                "between this self-estimate and the actual resolved "
                "predictions. Estimating honestly matters more than "
                "estimating favorably: a report that concludes probable "
                "overconfidence is more useful than one that claims good "
                "calibration without having actually checked. Comparing this "
                "report to the previous one also reveals whether calibration "
                "is trending in a useful direction, and when no predictions "
                "have been made at all, honest zeros are the correct input "
                "rather than an invented estimate; each call replaces the "
                "previous snapshot."
            ),
            parameters=(
                ToolParameter(
                    name="predictions_made",
                    type="number",
                    description=(
                        "The total number of prediction records emitted so "
                        "far in the run, as a non-negative integer, counting "
                        "every one regardless of whether it has since been "
                        "resolved."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="estimated_hits",
                    type="number",
                    description=(
                        "The number of those predictions believed to have "
                        "come true, as a non-negative integer no larger than "
                        "predictions_made, counting only predictions that "
                        "have actually been resolved by evidence rather than "
                        "ones simply assumed to be correct."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="estimated_rate",
                    type="number",
                    description=(
                        "The estimated hit rate implied by the two counts "
                        "above, expressed as a number between zero and one "
                        "and kept consistent with them. This is the specific "
                        "figure a monitor will later compare against the "
                        "actual resolved rate."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence_in_estimate",
                    type="number",
                    description=(
                        "How confident the agent is in the estimate itself, "
                        "expressed as a number between zero and one. This "
                        "should be low whenever many predictions remain "
                        "unresolved or the recollection of them is fuzzy, "
                        "since an accurate admission of uncertainty here is "
                        "worth more than a falsely precise guess."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="bias_self_assessment",
                    type="string",
                    description=(
                        "An optional honest self-diagnosis of miscalibration "
                        "direction, distinguishing a pattern where confident "
                        "predictions have tended to miss, a well-calibrated "
                        "track record, a pattern where hedged predictions "
                        "keep turning out true, an erratic pattern with no "
                        "consistent direction, and a genuine unknown when too "
                        "few predictions have resolved to say."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="trend",
                    type="string",
                    description=(
                        "An optional comparison against the previous "
                        "calibration self-report, distinguishing an improving "
                        "trend, a stable one, a worsening one, and an unknown "
                        "trend when no previous report exists to compare "
                        "against. This field turns a single snapshot into a "
                        "trajectory."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the calibration snapshot primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        made = CotEventParser.parse_int(args.get("predictions_made"))
        if made is None:
            return ToolResult.error(call.tool_name, "Field 'predictions_made' must be a non-negative integer.")
        hits = CotEventParser.parse_int(args.get("estimated_hits"))
        if hits is None:
            return ToolResult.error(call.tool_name, "Field 'estimated_hits' must be a non-negative integer.")
        if hits > made:
            return ToolResult.error(call.tool_name, "Field 'estimated_hits' cannot exceed 'predictions_made'.")
        rate = CotEventParser.parse_confidence(args.get("estimated_rate"))
        if rate is None:
            return ToolResult.error(call.tool_name, "Field 'estimated_rate' must be a number between 0.0 and 1.0.")
        estimate_confidence = CotEventParser.parse_confidence(args.get("confidence_in_estimate"))
        if estimate_confidence is None:
            return ToolResult.error(call.tool_name, "Field 'confidence_in_estimate' must be a number between 0.0 and 1.0.")
        bias, bias_error = CotEventParser.parse_enum(args.get("bias_self_assessment"), BIAS_ASSESSMENTS, "bias_self_assessment")
        if bias_error:
            return ToolResult.error(call.tool_name, bias_error)
        trend, trend_error = CotEventParser.parse_enum(args.get("trend"), CALIBRATION_TRENDS, "trend")
        if trend_error:
            return ToolResult.error(call.tool_name, trend_error)

        from vidbyte.context.primitives.cot_meta import CalibrationSelfReportContextItem

        item = CalibrationSelfReportContextItem(
            primitive_id=CALIBRATION_SNAPSHOT_ID,
            predictions_made=made,
            estimated_hits=hits,
            estimated_rate=rate,
            confidence_in_estimate=estimate_confidence,
            bias_self_assessment=bias,
            trend=trend,
        )
        return await self._record(item, call, {"estimated_rate": item.estimated_rate, "bias": item.bias_self_assessment})


class DescriptionDriftTool(_CotEventToolBase):
    """Builtin tool that records a gap between a tool's spec description and its actual usage."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="description_drift",
            description=(
                "When the way a tool is actually used in practice has "
                "drifted from what its description promised, report the "
                "drift so the description itself can eventually be fixed. "
                "This applies whenever a description misleads in practice: it "
                "recommends calling the tool at milestones but the actually "
                "useful trigger differs, a field's stated meaning does not "
                "match what ends up being put into it, or two tools' "
                "descriptions overlap so much that the choice between them "
                "becomes arbitrary. The agent is the only participant who "
                "experiences a description from the consuming side, so this "
                "feedback genuinely cannot originate anywhere else in the "
                "system. Describing the actual usage pattern and exactly "
                "where the description diverges from it is what turns this "
                "record into a usable bug report against the monitoring "
                "system's own interface rather than a vague complaint."
            ),
            parameters=(
                ToolParameter(
                    name="tool",
                    type="string",
                    description=(
                        "The exact call name of the tool whose description "
                        "has drifted from its actual usage."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="actual_usage",
                    type="string",
                    description=(
                        "How the tool is actually being used in practice, "
                        "described specifically enough that the gap against "
                        "the stated description becomes clear on its own."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="description_wrong_about",
                    type="string",
                    description=(
                        "The specific point where the description diverges "
                        "from actual usage, named as precisely as possible "
                        "rather than as a general sense that the description "
                        "feels imprecise."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="suggested_fix",
                    type="string",
                    description=(
                        "An optional replacement for the description text "
                        "itself, phrased as the actual wording that should "
                        "appear. A fix proposed from the consuming side is "
                        "worth more than a diagnosis alone, since it saves "
                        "the eventual fix from having to be reconstructed "
                        "from the complaint."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="frequency",
                    type="string",
                    description=(
                        "An optional statement of how often this specific "
                        "mismatch recurs, distinguishing a one-off "
                        "occurrence, an occasional pattern, a recurring one, "
                        "and a constant one that shows up on nearly every "
                        "call."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="blocking",
                    type="string",
                    description=(
                        "An optional statement of whether this drift is "
                        "actively causing incorrect calls to the tool rather "
                        "than only being a cosmetic inaccuracy, expressed as "
                        "yes or no. This field helps a reader prioritize "
                        "which description-drift reports need attention "
                        "first."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the description drift primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("tool", "actual_usage", "description_wrong_about"))
        if error:
            return ToolResult.error(call.tool_name, error)
        frequency, frequency_error = CotEventParser.parse_enum(args.get("frequency"), GAP_FREQUENCIES, "frequency")
        if frequency_error:
            return ToolResult.error(call.tool_name, frequency_error)
        blocking, blocking_error = CotEventParser.parse_enum(args.get("blocking"), BLOCKING_OPTIONS, "blocking")
        if blocking_error:
            return ToolResult.error(call.tool_name, blocking_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_meta import DescriptionDriftContextItem

        item = DescriptionDriftContextItem(
            primitive_id=self._next_primitive_id(),
            tool=str(args["tool"]).strip(),
            actual_usage=str(args["actual_usage"]).strip(),
            description_wrong_about=str(args["description_wrong_about"]).strip(),
            suggested_fix=CotEventParser.optional_text(args.get("suggested_fix")),
            frequency=frequency,
            blocking=blocking,
        )
        return await self._record(item, call, {"tool": item.tool})


__all__ = [
    "CalibrationSelfReportTool",
    "DescriptionDriftTool",
    "RecordDisputeTool",
    "RitualCheckTool",
    "SignalHighlightTool",
    "TelemetryGapTool",
]
