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
Similar Files:
    - `vidbyte/tools/builtins/cot_context.py`
"""

from __future__ import annotations

from vidbyte.tools.builtins.cot_events import CotEventParser, _CotEventToolBase
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

VERIFY_METHODS = ("re-derive", "re-run", "cross-check", "read-back")
VERIFY_VERDICTS = ("passes", "fails", "cannot_verify")
SEVERITY_LEVELS = ("fatal", "major", "minor")
FIXED_OPTIONS = ("yes", "no", "not_needed")
RAN_OPTIONS = ("yes", "no", "not_possible")
TEST_RESULTS = ("passed", "failed", "n_a")
COVERAGE_LEVELS = ("targeted", "spot", "exhaustive")
AGREEMENT_LEVELS = ("yes", "no", "unclear")
MATCH_STATES = ("yes", "drifted", "contradicts")


class VerifyTool(_CotEventToolBase):
    """Builtin tool that records one actively executed check on a single claim."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="verify",
            description=(
                "Pick one specific claim you have made or are about to rely on, "
                "and actively check it — not by feeling good about it, by "
                "executing a verification act. Use this whenever a claim is "
                "load-bearing: an identifier that must be exact, a number that "
                "feeds a decision, a behavior you asserted about a system. "
                "State the method you actually used, the evidence the check "
                "produced, and the verdict — including 'fails', which is the "
                "most valuable outcome this tool can record, because a caught "
                "error is a caught error. 'cannot_verify' is also legitimate; "
                "claiming verification you did not perform is the only "
                "dishonest answer here. A run that verifies its load-bearing "
                "claims fails differently than a run that does not: cheaply "
                "and early."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The claim being checked, verbatim as you made or will "
                        "make it: 'the endpoint returns at most 100 rows', "
                        "'the constant is defined in config, not hardcoded'. "
                        "One claim per call — split composites."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="method",
                    type="string",
                    description=(
                        "The verification act you performed. Use exactly one of: "
                        "'re-derive' (recomputed from first principles), "
                        "'re-run' (executed the operation again), 'cross-check' "
                        "(compared against an independent source), 'read-back' "
                        "(re-read the original source of the claim). Choose the "
                        "method you actually used, not the one that sounds "
                        "strongest."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description=(
                        "The check's outcome. Use exactly one of: 'passes' "
                        "(evidence confirms the claim), 'fails' (evidence "
                        "contradicts it), 'cannot_verify' (no check was "
                        "feasible — say why in evidence)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="evidence",
                    type="string",
                    description=(
                        "What the check concretely showed, one or two sentences: "
                        "'re-ran the query with limit=101; response contained "
                        "100 rows'. A verdict without its evidence is an "
                        "assertion wearing a costume."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="severity_if_wrong",
                    type="string",
                    description=(
                        "Optional: blast radius had this claim gone unchecked "
                        "and been wrong. Use exactly one of: 'fatal' (the "
                        "final result would be incorrect), 'major' (significant "
                        "rework), 'minor' (small local fix). Triage which "
                        "claims deserve verification using this."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="fixed",
                    type="string",
                    description=(
                        "Required when verdict is 'fails': did you fix the "
                        "underlying issue in this step? Use exactly one of: "
                        "'yes', 'no' (not yet — the fix is pending and named "
                        "in evidence), 'not_needed' (the claim was speculative "
                        "and is simply retracted)."
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
                "Before declaring a unit of work done, name the test that would "
                "fail if you are wrong — then say whether you actually ran it. "
                "Use this at every completion claim: a finished function, a "
                "settled answer, a resolved bug. The test is a pre-commitment: "
                "stating it first prevents the all-too-human slide into tests "
                "designed to pass. 'It looks right' is not a test; a test has "
                "an input, an execution, and a pass/fail you could observe. "
                "Not running the test is a recordable answer — with a reason — "
                "but declaring done while silently skipping the test you "
                "yourself named is the exact failure this tool exists to "
                "expose. When the test fails, record that too; a failing "
                "self-test before the reviewer sees it is the system working."
            ),
            parameters=(
                ToolParameter(
                    name="test",
                    type="string",
                    description=(
                        "The concrete test that would fail if this work is "
                        "wrong: 'run the CLI with the sample input and diff "
                        "against the expected output', 'query the collection "
                        "and confirm the index is used'. Include input and "
                        "expected observation, not just a topic."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="ran",
                    type="string",
                    description=(
                        "Whether you executed the test before declaring done. "
                        "Use exactly one of: 'yes', 'no' (chose not to — give "
                        "the reason), 'not_possible' (no executable form "
                        "exists in this environment)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="result",
                    type="string",
                    description=(
                        "Required when ran is 'yes'. Use exactly one of: "
                        "'passed', 'failed' (the work is not done — record the "
                        "fix as the next step), 'n_a' (the test could not "
                        "produce a pass/fail after all)."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="if_skipped_why",
                    type="string",
                    description=(
                        "Required when ran is 'no' or 'not_possible': one "
                        "sentence on why the named test was not executed — "
                        "'no test runner available; deferred to the "
                        "reviewer's suite'. Skipping with a stated reason is "
                        "a decision; skipping silently is a gap."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="coverage",
                    type="string",
                    description=(
                        "Optional: how much of the work this test touches. Use "
                        "exactly one of: 'targeted' (probes the specific "
                        "risk), 'spot' (samples one path among many), "
                        "'exhaustive' (covers the full surface). Be modest — "
                        "most self-tests are 'spot'."
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
        )
        return await self._record(item, call, {"ran": item.ran, "result": item.result})


class IndependentlyDerivedTool(_CotEventToolBase):
    """Builtin tool that records reaching one conclusion through two independent paths."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="independently_derived",
            description=(
                "For conclusions that matter, derive them twice — by two routes "
                "that do not share inputs — and record both paths. Use this "
                "for the load-bearing numbers and verdicts of the run: the "
                "estimate that sizes the migration, the identification of the "
                "root cause, the claim that the fix is complete. Independent "
                "derivation is double-entry bookkeeping for reasoning: a "
                "single path can be wrong for reasons invisible from inside "
                "it, but two paths that agree while sharing no inputs are "
                "much harder to break. The paths must be genuinely "
                "independent — deriving from the same source twice with "
                "different vocabulary is one path wearing two hats. "
                "Disagreement is not a failure of the method; it is the "
                "method working, and it must be recorded, not resolved by "
                "picking the answer you prefer."
            ),
            parameters=(
                ToolParameter(
                    name="conclusion",
                    type="string",
                    description=(
                        "The conclusion both paths arrive at (or fail to), "
                        "stated as one checkable sentence: 'the query cost "
                        "comes from the missing index, not the join order'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="path_a",
                    type="string",
                    description=(
                        "The first derivation route: what inputs it used and "
                        "the reasoning steps, one or two sentences — 'from the "
                        "query plan: full scan on users before the join'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="path_b",
                    type="string",
                    description=(
                        "The second route, sharing no inputs with path A: "
                        "'from timing: query latency scales with users table "
                        "size alone, constant with join complexity'. If the "
                        "routes share a source, they are one route — say so "
                        "and pick a different second path."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="agree",
                    type="string",
                    description=(
                        "Whether the paths support the same conclusion. Use "
                        "exactly one of: 'yes' (both arrive at it), 'no' (they "
                        "conflict), 'unclear' (they address different aspects "
                        "and cannot be directly compared)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="if_disagree",
                    type="string",
                    description=(
                        "Required when agree is 'no' or 'unclear': what this "
                        "disagreement does to the conclusion — which path you "
                        "trust more and why, or what evidence would break the "
                        "tie. 'No' without this field is just an unresolved "
                        "contradiction with a fancy name."
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
        )
        return await self._record(item, call, {"agree": item.agree})


class ReadBackTool(_CotEventToolBase):
    """Builtin tool that records re-reading an earlier output and whether it matches memory."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="read_back",
            description=(
                "Go back and re-read something you wrote or recorded earlier "
                "in this run, and compare it to what you currently believe it "
                "says. Use this before building on your own prior work — the "
                "earlier finding you are about to cite, the plan you are "
                "still executing, the numbers already entered in a draft "
                "answer. Self-drift is real: earlier records get silently "
                "paraphrased into stronger or weaker versions as the run "
                "continues, and the wrong version propagates. 'drifted' "
                "means the record says something slightly different than you "
                "have been treating it as; 'contradicts' means you have been "
                "acting against your own record. Both are gold when caught "
                "here and expensive when caught by the user."
            ),
            parameters=(
                ToolParameter(
                    name="record",
                    type="string",
                    description=(
                        "Which earlier output or record you re-read, named "
                        "precisely: 'the schema field list from step four', "
                        "'the assumption ledger entry about the index'. Quote "
                        "or closely paraphrase what it actually says."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="matches_memory",
                    type="string",
                    description=(
                        "Comparison verdict. Use exactly one of: 'yes' (the "
                        "record matches what you believed), 'drifted' (small "
                        "differences — you had been paraphrasing it "
                        "slightly), 'contradicts' (the record says something "
                        "materially different from your working belief)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="drift_detail",
                    type="string",
                    description=(
                        "Required when matches_memory is 'drifted' or "
                        "'contradicts': the exact difference between record "
                        "and memory — 'record said cursor pagination; I had "
                        "been acting as if offset'. Precision here is what "
                        "lets a later reader judge the damage."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="corrective_action",
                    type="string",
                    description=(
                        "Optional: what you will now fix because of the "
                        "mismatch — 'redo the fetch loop against cursor "
                        "semantics'. Required in spirit whenever the drift "
                        "touched downstream work."
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

        self._counter += 1
        from vidbyte.context.primitives.cot_verification import ReadBackContextItem

        item = ReadBackContextItem(
            primitive_id=self._next_primitive_id(),
            record=str(args["record"]).strip(),
            matches_memory=matches or MATCH_STATES[0],
            drift_detail=drift_detail,
            corrective_action=CotEventParser.optional_text(args.get("corrective_action")),
        )
        return await self._record(item, call, {"matches_memory": item.matches_memory})


__all__ = [
    "IndependentlyDerivedTool",
    "ReadBackTool",
    "SelfTestTool",
    "VerifyTool",
]
