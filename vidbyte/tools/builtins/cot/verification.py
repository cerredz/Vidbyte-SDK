"""Context Protocol Header

Description:
    Implements the self-verification monitoring tools.
Purpose:
    Lets the model actively check its own claims and outputs — single-claim
    verification, pre-completion self tests, independent re-derivations, and
    re-reads of earlier records — producing the highest-trust telemetry in
    the monitoring family because verification acts are checkable.
Architecture:
    - VerifyTool, SelfTestTool, IndependentlyDerivedTool, ReadBackTool:
      _CotEventToolBase subclasses that validate, upsert a matching
      cot_verification primitive, and return parsed values in ToolResult.metadata.
Relations:
    Reuses CotEventParser and _CotEventToolBase from builtins.cot_events.
    Categorical fields are sourced from vidbyte.lib.enums.cot.
Similar Files:
    - `vidbyte/tools/builtins/cot/context.py`
"""

from __future__ import annotations

from vidbyte.lib.enums.cot import (
    AgreementLevel,
    FixedStatus,
    MatchState,
    Severity,
    Staleness,
    TestCoverage,
    TestRanStatus,
    TestResult,
    VerificationMethod,
    VerificationVerdict,
    YesNo,
)
from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

VERIFY_METHODS = tuple(method.value for method in VerificationMethod)
VERIFY_VERDICTS = tuple(verdict.value for verdict in VerificationVerdict)
SEVERITY_LEVELS = tuple(level.value for level in Severity)
FIXED_OPTIONS = tuple(option.value for option in FixedStatus)
RAN_OPTIONS = tuple(option.value for option in TestRanStatus)
TEST_RESULTS = tuple(result.value for result in TestResult)
COVERAGE_LEVELS = tuple(level.value for level in TestCoverage)
AGREEMENT_LEVELS = tuple(level.value for level in AgreementLevel)
MATCH_STATES = tuple(state.value for state in MatchState)
STALENESS_LEVELS = tuple(level.value for level in Staleness)
BLOCKING_OPTIONS = tuple(option.value for option in YesNo)


class VerifyTool(_CotEventToolBase):
    """Builtin tool that records one actively executed check on a single claim."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="verify",
            description=(
                "Select one specific, load-bearing claim and actively check "
                "it rather than merely feeling confident about it, recording "
                "the method used, the evidence the check produced, and the "
                "resulting verdict. This tool is reserved for claims that "
                "genuinely matter to what happens next: an identifier that "
                "must be exact, a number feeding a downstream decision, an "
                "asserted behavior of some system. A failing verdict is the "
                "single most valuable outcome this tool can record, since a "
                "caught error here is an error that stops before it "
                "propagates further, and asserting a verification that was "
                "never actually performed is the one dishonest answer this "
                "tool has no room for. A run that verifies its load-bearing "
                "claims as a matter of course fails differently, and much "
                "more cheaply, than one that does not."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The single claim under check, stated exactly as it "
                        "was or will be asserted. One claim should be checked "
                        "per call; a composite claim bundling several "
                        "assertions together should be split so that each "
                        "piece can be verified and scored independently."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="method",
                    type="string",
                    description=(
                        "The verification act actually performed, chosen from "
                        "re-deriving the claim from first principles, re-"
                        "running the underlying operation, cross-checking "
                        "against an independent source, reading back the "
                        "claim's original source, running a static-analysis "
                        "pass over it, or having it reviewed by a separate "
                        "party. This should name the method genuinely used, "
                        "not the one that would sound most rigorous in "
                        "retrospect."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description=(
                        "The outcome of the check, distinguishing a full "
                        "pass, a pass with a caveat, an outright failure, and "
                        "a case where no check was actually feasible. When "
                        "verification could not be completed, that reason "
                        "should be captured in the evidence field rather than "
                        "left implicit."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="evidence",
                    type="string",
                    description=(
                        "A concrete account of what the check actually "
                        "showed, grounding the verdict in something "
                        "observable rather than leaving it as an unsupported "
                        "assertion. A verdict recorded without accompanying "
                        "evidence carries little more weight than the "
                        "original unverified claim."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="severity_if_wrong",
                    type="string",
                    description=(
                        "An optional assessment of the blast radius had this "
                        "claim gone unchecked and turned out to be wrong, "
                        "ranging from purely cosmetic through minor, major, "
                        "critical, and fatal. This field is useful for "
                        "triaging which claims most deserve active "
                        "verification in the first place, and for weighing "
                        "how much attention a failing verdict deserves after "
                        "the fact."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="fixed",
                    type="string",
                    description=(
                        "Required whenever the verdict is a failure: whether "
                        "the underlying issue was fixed within this same "
                        "step, is still pending, was deliberately left "
                        "unaddressed, no longer needs fixing because the "
                        "claim was simply retracted, or was fixed in a "
                        "deferred later step. This field turns a caught error "
                        "into a tracked one rather than a dead end."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the verification primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("claim", "method", "verdict", "evidence"))
        if error:
            return ToolResult.error(call.tool_name, error)
        method, method_error = CotEventParser.parse_enum(args.get("method"), VERIFY_METHODS, "method")
        if method_error:
            return ToolResult.error(call.tool_name, method_error)
        verdict, verdict_error = CotEventParser.parse_enum(args.get("verdict"), VERIFY_VERDICTS, "verdict")
        if verdict_error:
            return ToolResult.error(call.tool_name, verdict_error)
        severity, severity_error = CotEventParser.parse_enum(args.get("severity_if_wrong"), SEVERITY_LEVELS, "severity_if_wrong")
        if severity_error:
            return ToolResult.error(call.tool_name, severity_error)
        fixed, fixed_error = CotEventParser.parse_enum(args.get("fixed"), FIXED_OPTIONS, "fixed")
        if fixed_error:
            return ToolResult.error(call.tool_name, fixed_error)
        if verdict == "fails" and fixed is None:
            return ToolResult.error(call.tool_name, "Field 'fixed' is required when verdict is 'fails'.")

        self._counter += 1
        from vidbyte.context.primitives.cot_verification import VerifyContextItem

        item = VerifyContextItem(
            primitive_id=self._next_primitive_id(),
            claim=str(args["claim"]).strip(),
            method=method or VERIFY_METHODS[0],
            verdict=verdict or VERIFY_VERDICTS[0],
            evidence=str(args["evidence"]).strip(),
            severity_if_wrong=severity,
            fixed=fixed,
        )
        return await self._record(item, call, {"method": item.method, "verdict": item.verdict, "fixed": item.fixed})


class SelfTestTool(_CotEventToolBase):
    """Builtin tool that records the test that would fail if the agent is wrong, and whether it ran."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="self_test",
            description=(
                "Before declaring a unit of work complete, name the specific "
                "test that would fail if the work is actually wrong, then "
                "state plainly whether that test was executed. Naming the "
                "test first, before assessing the work, is a pre-commitment "
                "against the natural drift toward tests quietly designed to "
                "pass; a genuine test has an input, an execution, and an "
                "observable pass or fail, not merely an impression that the "
                "result looks right. Choosing not to run the named test is a "
                "recordable answer as long as the reason is given, but "
                "declaring completion while silently skipping the very test "
                "just named is the exact failure this tool exists to expose. "
                "A self test that fails before a reviewer ever sees the work "
                "is this system functioning as intended, not a mark against "
                "it."
            ),
            parameters=(
                ToolParameter(
                    name="test",
                    type="string",
                    description=(
                        "The concrete test that would fail if this work turns "
                        "out to be wrong, described with enough of the input "
                        "and the expected observation that it reads as a "
                        "genuine test rather than a restated topic."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="ran",
                    type="string",
                    description=(
                        "Whether the named test was actually executed before "
                        "declaring the work done, distinguishing a full run, "
                        "a partial run, a deliberate decision to defer it, a "
                        "deliberate decision not to run it at all, and a case "
                        "where no executable form of the test exists in this "
                        "environment."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="result",
                    type="string",
                    description=(
                        "Required whenever the test ran: its outcome, "
                        "distinguishing a clean pass, an intermittent or "
                        "flaky result, an outright failure meaning the work "
                        "is not actually done, a result that turned out "
                        "inconclusive, and a case where the test could not "
                        "produce a real pass or fail after all."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="if_skipped_why",
                    type="string",
                    description=(
                        "Required whenever the test did not fully run: the "
                        "reason it was not executed. A stated reason turns "
                        "the omission into a visible decision rather than a "
                        "silent gap in coverage."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="coverage",
                    type="string",
                    description=(
                        "An optional characterization of how much of the "
                        "work this test actually exercises, ranging from a "
                        "quick smoke check through a spot sample, a targeted "
                        "probe of the specific risk, a regression check "
                        "against prior behavior, and a fully exhaustive pass "
                        "over the whole surface. Most self tests are modest "
                        "in scope, and this field should reflect that "
                        "honestly rather than defaulting to the broadest "
                        "label."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="blocking",
                    type="string",
                    description=(
                        "An optional statement of whether a failing result on "
                        "this specific test should block declaring the "
                        "broader work done, expressed as yes or no. This "
                        "field distinguishes a test whose failure is "
                        "disqualifying from one that surfaces a secondary "
                        "concern worth noting but not fatal to completion."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the self-test primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("test", "ran"))
        if error:
            return ToolResult.error(call.tool_name, error)
        ran, ran_error = CotEventParser.parse_enum(args.get("ran"), RAN_OPTIONS, "ran")
        if ran_error:
            return ToolResult.error(call.tool_name, ran_error)
        result, result_error = CotEventParser.parse_enum(args.get("result"), TEST_RESULTS, "result")
        if result_error:
            return ToolResult.error(call.tool_name, result_error)
        coverage, coverage_error = CotEventParser.parse_enum(args.get("coverage"), COVERAGE_LEVELS, "coverage")
        if coverage_error:
            return ToolResult.error(call.tool_name, coverage_error)
        blocking, blocking_error = CotEventParser.parse_enum(args.get("blocking"), BLOCKING_OPTIONS, "blocking")
        if blocking_error:
            return ToolResult.error(call.tool_name, blocking_error)
        skipped_why = CotEventParser.optional_text(args.get("if_skipped_why"))
        if ran != "yes" and skipped_why is None:
            return ToolResult.error(call.tool_name, "Field 'if_skipped_why' is required when ran is not 'yes'.")
        if ran == "yes" and result is None:
            return ToolResult.error(call.tool_name, "Field 'result' is required when ran is 'yes'.")

        self._counter += 1
        from vidbyte.context.primitives.cot_verification import SelfTestContextItem

        item = SelfTestContextItem(
            primitive_id=self._next_primitive_id(),
            test=str(args["test"]).strip(),
            ran=ran or RAN_OPTIONS[1],
            result=result,
            if_skipped_why=skipped_why,
            coverage=coverage,
            blocking=blocking,
        )
        return await self._record(item, call, {"ran": item.ran, "result": item.result})


class IndependentlyDerivedTool(_CotEventToolBase):
    """Builtin tool that records reaching one conclusion through two independent paths."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="independently_derived",
            description=(
                "For conclusions that genuinely matter, derive them twice "
                "through routes that share no inputs, and record both paths "
                "alongside the verdict on whether they agree. This is "
                "double-entry bookkeeping applied to reasoning: a single "
                "derivation path can be wrong for reasons invisible from "
                "inside it, while two paths that share nothing and still "
                "arrive at the same place are considerably harder to break. "
                "The paths must be genuinely independent rather than the same "
                "underlying source restated in different words, and this tool "
                "asks explicitly what actually makes them independent so that "
                "a superficial second pass cannot masquerade as a real check. "
                "Disagreement between the two paths is not a failure of the "
                "method — it is the method doing its job — and it must be "
                "recorded honestly rather than resolved by quietly picking "
                "whichever answer was preferred beforehand."
            ),
            parameters=(
                ToolParameter(
                    name="conclusion",
                    type="string",
                    description=(
                        "The conclusion both paths are being used to reach or "
                        "fail to reach, stated as a single checkable claim "
                        "rather than a loosely bounded topic."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="path_a",
                    type="string",
                    description=(
                        "The first derivation route, describing the inputs it "
                        "drew on and the reasoning steps that connect them to "
                        "the conclusion. This should read as a self-contained "
                        "argument that a reader could evaluate on its own "
                        "terms."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="path_b",
                    type="string",
                    description=(
                        "The second derivation route, sharing no inputs with "
                        "the first. If the two routes turn out to draw on the "
                        "same underlying source, they are in substance one "
                        "route, and that should be acknowledged here rather "
                        "than presented as independent confirmation."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="agree",
                    type="string",
                    description=(
                        "Whether the two paths support the same conclusion, "
                        "distinguishing full agreement, a partial overlap "
                        "that only supports part of the conclusion, outright "
                        "conflict between the paths, and a case where they "
                        "address different aspects and cannot be directly "
                        "compared."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="if_disagree",
                    type="string",
                    description=(
                        "Required whenever the paths do not fully agree: what "
                        "the disagreement means for the conclusion, including "
                        "which path is trusted more and why, or what "
                        "additional evidence would settle the conflict. A "
                        "conflict recorded without this field is simply an "
                        "unresolved contradiction given a formal name."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="independence_basis",
                    type="string",
                    description=(
                        "An optional statement of what specifically makes the "
                        "two paths independent of each other, such as drawing "
                        "on different data sources, different methods, or "
                        "different reasoning strategies entirely. This field "
                        "exists so that independence is a stated, checkable "
                        "property of the pair rather than an unexamined "
                        "assumption."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the independent-derivation primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("conclusion", "path_a", "path_b", "agree"))
        if error:
            return ToolResult.error(call.tool_name, error)
        agree, agree_error = CotEventParser.parse_enum(args.get("agree"), AGREEMENT_LEVELS, "agree")
        if agree_error:
            return ToolResult.error(call.tool_name, agree_error)
        if_disagree = CotEventParser.optional_text(args.get("if_disagree"))
        if agree != "yes" and if_disagree is None:
            return ToolResult.error(call.tool_name, "Field 'if_disagree' is required when agree is not 'yes'.")

        self._counter += 1
        from vidbyte.context.primitives.cot_verification import IndependentlyDerivedContextItem

        item = IndependentlyDerivedContextItem(
            primitive_id=self._next_primitive_id(),
            conclusion=str(args["conclusion"]).strip(),
            path_a=str(args["path_a"]).strip(),
            path_b=str(args["path_b"]).strip(),
            agree=agree or AGREEMENT_LEVELS[0],
            if_disagree=if_disagree,
            independence_basis=CotEventParser.optional_text(args.get("independence_basis")),
        )
        return await self._record(item, call, {"agree": item.agree})


class ReadBackTool(_CotEventToolBase):
    """Builtin tool that records re-reading an earlier output and whether it matches memory."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="read_back",
            description=(
                "Go back and re-read something written or recorded earlier in "
                "the run, then compare it directly to what is currently "
                "believed about it, before building further work on top of "
                "it. Earlier findings can silently paraphrase themselves into "
                "stronger or weaker versions as a run continues, and the "
                "drifted version can go on to propagate uncorrected; this "
                "tool exists to catch that drift while it is still cheap to "
                "fix. A drifted match means the record now says something "
                "subtly different from how it has been treated, while a "
                "contradicting match means work has been proceeding directly "
                "against the agent's own record. Both outcomes are valuable "
                "when caught here and considerably more expensive when caught "
                "later by someone else."
            ),
            parameters=(
                ToolParameter(
                    name="record",
                    type="string",
                    description=(
                        "The earlier output or record being re-read, named "
                        "precisely enough that a reader can tell exactly "
                        "which prior artifact this refers to, along with a "
                        "close paraphrase of what it actually says."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="matches_memory",
                    type="string",
                    description=(
                        "The comparison verdict, distinguishing a full match "
                        "against current belief, a match that has since been "
                        "superseded by later information, a small drift where "
                        "the record has been paraphrased slightly, an outright "
                        "contradiction between the record and current belief, "
                        "and a case where the comparison could not actually be "
                        "made."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="drift_detail",
                    type="string",
                    description=(
                        "Required whenever the record does not fully match "
                        "current belief: the precise difference between what "
                        "the record says and what has been assumed. Precision "
                        "here is what lets a later reader judge exactly how "
                        "much damage the drift may have caused."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="corrective_action",
                    type="string",
                    description=(
                        "An optional description of what will be fixed as a "
                        "result of the mismatch just found. This should "
                        "generally be filled in whenever the drift touched "
                        "downstream work, since a drift caught but left "
                        "uncorrected provides little benefit over not having "
                        "caught it at all."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="staleness",
                    type="string",
                    description=(
                        "An optional characterization of how long it had been "
                        "since this record was last checked, ranging from "
                        "freshly written through aging and outright stale. "
                        "This field helps a reader judge whether drift is an "
                        "isolated anomaly or the predictable result of a "
                        "record that had simply gone unchecked for too long."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="reread_trigger",
                    type="string",
                    description=(
                        "An optional description of what prompted this "
                        "specific re-read, such as an approaching decision "
                        "that depends on the record or a scheduled periodic "
                        "check. Knowing the trigger helps a reader "
                        "distinguish routine verification from a re-read "
                        "prompted by a specific suspicion."
                    ),
                    required=False,
                    default=None,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the read-back primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = CotEventParser.require_text(args, ("record", "matches_memory"))
        if error:
            return ToolResult.error(call.tool_name, error)
        matches, matches_error = CotEventParser.parse_enum(args.get("matches_memory"), MATCH_STATES, "matches_memory")
        if matches_error:
            return ToolResult.error(call.tool_name, matches_error)
        drift_detail = CotEventParser.optional_text(args.get("drift_detail"))
        if matches != "yes" and drift_detail is None:
            return ToolResult.error(
                call.tool_name,
                "Field 'drift_detail' is required when matches_memory is not 'yes'.",
            )
        staleness, staleness_error = CotEventParser.parse_enum(args.get("staleness"), STALENESS_LEVELS, "staleness")
        if staleness_error:
            return ToolResult.error(call.tool_name, staleness_error)

        self._counter += 1
        from vidbyte.context.primitives.cot_verification import ReadBackContextItem

        item = ReadBackContextItem(
            primitive_id=self._next_primitive_id(),
            record=str(args["record"]).strip(),
            matches_memory=matches or MATCH_STATES[0],
            drift_detail=drift_detail,
            corrective_action=CotEventParser.optional_text(args.get("corrective_action")),
            staleness=staleness,
            reread_trigger=CotEventParser.optional_text(args.get("reread_trigger")),
        )
        return await self._record(item, call, {"matches_memory": item.matches_memory})


__all__ = [
    "IndependentlyDerivedTool",
    "ReadBackTool",
    "SelfTestTool",
    "VerifyTool",
]
