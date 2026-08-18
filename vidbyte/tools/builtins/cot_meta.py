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
Similar Files:
    - `vidbyte/tools/builtins/cot_context.py`
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

DISPUTE_VERDICTS = ("a", "b", "both", "neither")
MONITORING_HEALTH_LEVELS = ("healthy", "heavy", "smothering")
GAP_SEVERITIES = ("minor", "notable", "critical")
DIRECTION_CHANGE_LEVELS = ("yes", "slightly", "no")
SURPRISE_LEVELS = ("expected", "surprising", "alarming")
BIAS_ASSESSMENTS = ("overconfident", "calibrated", "underconfident", "unknown")
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
                "When two of your own records contradict each other, flag "
                "the dispute explicitly — do not quietly let the newer one "
                "win. Use this the moment you notice it: an assumption "
                "marked verified that a later observation undermines, a "
                "prediction recorded as on-track beside a failure scan "
                "listing its premise as high-likelihood failure. Unflagged "
                "contradictions are worse than either record alone, because "
                "every downstream reader (including future you) trusts "
                "both. Adjudicate honestly: which record is wrong, and "
                "why? 'both' means both were premature; 'neither' means "
                "they are actually compatible and the contradiction was "
                "apparent — say what reconciles them. The discipline here "
                "is refusing to resolve disputes by recency or by "
                "convenience."
            ),
            parameters=(
                ToolParameter(
                    name="record_a",
                    type="string",
                    description=(
                        "The first record in the dispute, named and quoted "
                        "or closely paraphrased: 'hypothesis: retries are "
                        "idempotent — status supported'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="record_b",
                    type="string",
                    description=(
                        "The second record it conflicts with, same "
                        "precision. Labeling them a and b is not an ordering "
                        "judgment — the verdict field does that work."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="contradiction",
                    type="string",
                    description=(
                        "The exact point of conflict, one sentence: 'a "
                        "asserts writes are safe to repeat; b observed "
                        "duplicate rows on retry'. If you cannot state the "
                        "conflict precisely, it may not be one."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="which_is_wrong",
                    type="string",
                    description=(
                        "Your adjudication. Use exactly one of: 'a', 'b', "
                        "'both' (each was wrong or premature in its own "
                        "way), 'neither' (reconcilable — see resolution)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="resolution",
                    type="string",
                    description=(
                        "Optional: what reconciles the dispute or repairs "
                        "the wrong record — 'b stands; re-verify a with a "
                        "direct duplicate-write test'. Required in spirit "
                        "when which_is_wrong is 'neither'."
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
        )
        return await self._record(item, call, {"which_is_wrong": item.which_is_wrong})


class RitualCheckTool(_CotEventToolBase):
    """Builtin tool that snapshots which monitoring calls have become reflexive versus still earning their cost."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="ritual_check",
            description=(
                "Periodically audit your own monitoring calls: which ones "
                "have you been making by habit — at every milestone, "
                "filling the same fields with boilerplate — and which ones "
                "are still changing what you do next? Use this sparingly, "
                "once per long run or per major phase, not per step. The "
                "distinction is the whole point: a monitoring call that "
                "never changes anything is a ritual, and rituals cost "
                "tokens and attention while producing the appearance of "
                "vigilance rather than the substance. Be unsentimental — "
                "listing a call as reflexive is not disloyalty to it, and "
                "the blind_spots field matters as much as the lists: the "
                "moments where something important happened and no record "
                "captured it are where the telemetry itself is failing. "
                "This snapshot replaces the previous one."
            ),
            parameters=(
                ToolParameter(
                    name="reflexive",
                    type="string",
                    description=(
                        "A JSON array of up to 5 strings naming monitoring "
                        "calls you have been making on autopilot — entries "
                        "filled with stock phrases, verdicts that never "
                        "surprise you. \"uncertainty readings that always "
                        "say progressing\". An empty array is a strong "
                        "claim; make it only if it is true."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="still_earning",
                    type="string",
                    description=(
                        "A JSON array of up to 5 strings naming calls that "
                        "have genuinely changed decisions — \"assumption_check "
                        "falsified the index assumption, saved a migration\". "
                        "These are the ones worth protecting."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="blind_spots",
                    type="string",
                    description=(
                        "Optional: moments in the run where something "
                        "important happened and no tool call captured it — "
                        "\"the moment the approach quietly became obsolete "
                        "went unrecorded\". Gaps here seed future tool ideas."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="overall",
                    type="string",
                    description=(
                        "Optional: overall verdict on monitoring weight. Use "
                        "exactly one of: 'healthy' (records pull their "
                        "weight), 'heavy' (noticeable cost, uneven value), "
                        "'smothering' (records crowd out real work — cut "
                        "back deliberately)."
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

        from vidbyte.context.primitives.cot_meta import RitualCheckContextItem

        item = RitualCheckContextItem(
            primitive_id=RITUAL_CHECK_SNAPSHOT_ID,
            reflexive=tuple(reflexive or ()),
            still_earning=tuple(earning or ()),
            blind_spots=CotEventParser.optional_text(args.get("blind_spots")),
            overall=overall,
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
                "When something important happens that none of your "
                "monitoring tools can record, report the gap itself. Use "
                "this for the moments you find yourself wishing a record "
                "existed: a shift in your understanding too diffuse for "
                "any single tool, an interaction between records no field "
                "captures, a judgment you had to make with no home. This "
                "is the feedback channel for the monitoring system itself "
                "— the tool whose only job is to say what the other tools "
                "cannot. Do not force-fit events into the wrong tool; a "
                "misfiled record corrupts its own telemetry. Name the "
                "event plainly and describe the record you wanted. These "
                "records are how the tool family learns what it is "
                "missing."
            ),
            parameters=(
                ToolParameter(
                    name="event",
                    type="string",
                    description=(
                        "What happened, one or two sentences: 'realized the "
                        "two sub-problems are actually one problem with two "
                        "symptoms — no tool records a reframing moment'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="wanted_to_record",
                    type="string",
                    description=(
                        "The record you wished existed, described as if "
                        "specifying it: 'a reframing event: old frame, new "
                        "frame, what evidence forced the change'. Concrete "
                        "enough that a tool could be designed from it."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="closest_tool",
                    type="string",
                    description=(
                        "Optional: the tool you considered using instead "
                        "and rejected — 'why almost fit but would have "
                        "distorted it'. Explains the misfit, not the event."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="severity",
                    type="string",
                    description=(
                        "Optional: how much the gap costs. Use exactly one "
                        "of: 'minor' (cosmetic loss), 'notable' (a real "
                        "signal about the run is lost), 'critical' (future "
                        "readers will misunderstand the run without it)."
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

        self._counter += 1
        from vidbyte.context.primitives.cot_meta import TelemetryGapContextItem

        item = TelemetryGapContextItem(
            primitive_id=self._next_primitive_id(),
            event=str(args["event"]).strip(),
            wanted_to_record=str(args["wanted_to_record"]).strip(),
            closest_tool=CotEventParser.optional_text(args.get("closest_tool")),
            severity=severity,
        )
        return await self._record(item, call, {"severity": item.severity})


class SignalHighlightTool(_CotEventToolBase):
    """Builtin tool that records which monitoring record most changed the run's direction."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="signal_highlight",
            description=(
                "Occasionally, one record genuinely changes everything "
                "after it — identify those moments and mark them. Use this "
                "when you notice a monitoring record altered your course: "
                "the falsified hypothesis that killed the approach, the "
                "enough declaration that stopped the spiral, the failure "
                "scan entry that reshaped the plan. Most records describe "
                "the run; a few steer it, and without this tool the two "
                "are indistinguishable in the trace — every record looks "
                "equally causal to a later reader. The counterfactual "
                "field is what makes this honest: state what would have "
                "happened without the record. If you cannot say the record "
                "changed the run, it is not a signal highlight, and "
                "inflating this record is exactly the ritualization "
                "ritual_check exists to catch."
            ),
            parameters=(
                ToolParameter(
                    name="record",
                    type="string",
                    description=(
                        "The steering record, named and quoted or closely "
                        "paraphrased: 'failures entry: rate limit during "
                        "backfill, likelihood high — no mitigation'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="changed_direction",
                    type="string",
                    description=(
                        "How much it steered. Use exactly one of: 'yes' "
                        "(the run changed course because of it), 'slightly' "
                        "(tuned the approach), 'no' (confirmed an existing "
                        "course — still worth noting once in a while, "
                        "sparingly)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="would_have_happened",
                    type="string",
                    description=(
                        "The counterfactual: what the run would have done "
                        "without this record, one sentence — 'would have "
                        "run the backfill unthrottled and hit the limit "
                        "mid-migration'. This field is the honesty check; "
                        "fill it as carefully as the record itself."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="surprise",
                    type="string",
                    description=(
                        "Optional: how the record compared to expectations. "
                        "Use exactly one of: 'expected' (the record "
                        "confirmed what you suspected), 'surprising' (new "
                        "information), 'alarming' (contradicted your "
                        "working model). 'alarming' records deserve a "
                        "follow-up decision, not just a highlight."
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
        )
        return await self._record(item, call, {"changed_direction": item.changed_direction})


class CalibrationSelfReportTool(_CotEventToolBase):
    """Builtin tool that snapshots the agent's self-estimated prediction calibration."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="calibration_self_report",
            description=(
                "Periodically estimate your own track record: of the "
                "predictions you have recorded this run, how many do you "
                "believe came true? Use this once per run or per major "
                "phase — it is a self-audit, not a per-step tool. The "
                "value is in the comparison: this estimate is checked "
                "against actual resolved predictions by the monitor, and "
                "the gap between your self-image and your record is the "
                "finding. Estimate honestly, including the uncomfortable "
                "direction — a run that reports 'probably overconfident' "
                "is more useful than one that reports 'calibrated' "
                "without checking. If you made no predictions, zeros are "
                "the honest inputs. This snapshot replaces the previous "
                "one."
            ),
            parameters=(
                ToolParameter(
                    name="predictions_made",
                    type="number",
                    description=(
                        "How many prediction records you have emitted this "
                        "run — a non-negative integer. Count all of them, "
                        "resolved or not."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="estimated_hits",
                    type="number",
                    description=(
                        "How many of those predictions you believe came "
                        "true — a non-negative integer, no larger than "
                        "predictions_made. Include resolved-by-evidence "
                        "only; exclude ones you never checked."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="estimated_rate",
                    type="number",
                    description=(
                        "Your estimated hit rate, 0.0 to 1.0, one decimal — "
                        "consistent with the two counts above. This is the "
                        "number that gets compared to reality."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence_in_estimate",
                    type="number",
                    description=(
                        "How confident you are in the estimate itself, 0.0 "
                        "to 1.0 — low when many predictions remain "
                        "unresolved or your memory of them is fuzzy. An "
                        "accurate 'I am not sure' is worth more than a "
                        "precise guess."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="bias_self_assessment",
                    type="string",
                    description=(
                        "Optional: your honest self-diagnosis. Use exactly "
                        "one of: 'overconfident' (your confident "
                        "predictions have been missing), 'calibrated', "
                        "'underconfident' (your hedged ones keep coming "
                        "true), 'unknown' (not enough resolved "
                        "predictions to say)."
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

        from vidbyte.context.primitives.cot_meta import CalibrationSelfReportContextItem

        item = CalibrationSelfReportContextItem(
            primitive_id=CALIBRATION_SNAPSHOT_ID,
            predictions_made=made,
            estimated_hits=hits,
            estimated_rate=rate,
            confidence_in_estimate=estimate_confidence,
            bias_self_assessment=bias,
        )
        return await self._record(item, call, {"estimated_rate": item.estimated_rate, "bias": item.bias_self_assessment})


class DescriptionDriftTool(_CotEventToolBase):
    """Builtin tool that records a gap between a tool's spec description and its actual usage."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="description_drift",
            description=(
                "When you notice that the way you actually use a tool has "
                "drifted from what its description told you it was for, "
                "report the drift. Use this whenever a tool's description "
                "misleads in practice: it says to call the tool at "
                "milestones but the useful trigger is different, a "
                "field's stated meaning does not match what you find "
                "yourself putting in it, two tools' descriptions overlap "
                "so much you choose arbitrarily. You are the only "
                "participant who experiences the description from the "
                "consuming side, so this feedback cannot come from "
                "anywhere else. Describe what you actually do with the "
                "tool and where the description diverges — this record is "
                "a bug report against the monitoring system's own "
                "interface, and it is how descriptions get fixed."
            ),
            parameters=(
                ToolParameter(
                    name="tool",
                    type="string",
                    description=(
                        "The tool whose description has drifted, by its "
                        "exact call name: 'assumption_check'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="actual_usage",
                    type="string",
                    description=(
                        "How you actually use it, one or two sentences: "
                        "'I call it only when entering a new stage, not "
                        "per-assumption as the description implies; the "
                        "statement field ends up holding stage-level "
                        "summaries'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="description_wrong_about",
                    type="string",
                    description=(
                        "The specific divergence, one or two sentences: "
                        "'description says reuse the same statement to "
                        "update a ledger entry, but re-stating exactly is "
                        "unnatural when evidence changes the wording'. "
                        "Name the sentence-level mismatch where you can."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="suggested_fix",
                    type="string",
                    description=(
                        "Optional: what the description should say "
                        "instead, phrased as a replacement instruction — "
                        "'say: re-statements within N words match the "
                        "same ledger entry'. Fixes from the consuming "
                        "side are worth more than diagnoses."
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

        self._counter += 1
        from vidbyte.context.primitives.cot_meta import DescriptionDriftContextItem

        item = DescriptionDriftContextItem(
            primitive_id=self._next_primitive_id(),
            tool=str(args["tool"]).strip(),
            actual_usage=str(args["actual_usage"]).strip(),
            description_wrong_about=str(args["description_wrong_about"]).strip(),
            suggested_fix=CotEventParser.optional_text(args.get("suggested_fix")),
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
