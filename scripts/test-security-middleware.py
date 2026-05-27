"""Context Protocol Header

Description:
    Verification script for security middleware test plan.
Purpose:
    Runs all test cases from the design doc Section 10 and prints PASS/FAIL
    per test with a final summary. Exits non-zero if any test fails.
Architecture:
    - Imports and instantiates all three middleware directly.
    - Runs every test case from the design doc.
Relations:
    Tests vidbyte.middleware.builtins security middleware implementations.
"""

from __future__ import annotations

import asyncio
import sys
import traceback


async def run_all_tests() -> tuple[int, int]:
    # Runs all test cases and returns (passed, total).
    passed = 0
    total = 0
    results: list[tuple[str, bool, str]] = []

    async def check(name: str, test_fn):
        nonlocal passed, total
        total += 1
        try:
            await test_fn()
            results.append((name, True, ""))
            passed += 1
        except Exception as exc:
            results.append((name, False, f"{type(exc).__name__}: {exc}"))

    from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareHook
    from vidbyte.middleware.builtins import (
        CanaryTripwireMiddleware,
        ConfusedDeputyGuardMiddleware,
        HoneypotToolMiddleware,
        ToolPolicyMiddleware,
    )
    from vidbyte.middleware.pipeline import MiddlewarePipeline
    from vidbyte.tools import ToolCall, ToolResult

    class FakeModelResponse:
        def __init__(self, text: str) -> None:
            self.text = text

    class NoTextResponse:
        def __init__(self, value: str) -> None:
            self.value = value
        def __str__(self) -> str:
            return self.value

    # =====================================================================
    # CanaryTripwireMiddleware
    # =====================================================================

    async def canary_inject_when_roll_passes():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        ctx = MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("scrape"), tool_result=ToolResult.success("scrape", "data"))
        await mw.after_tool_call(ctx)
        assert len(mw._canaries) == 1, f"Expected 1 canary, got {len(mw._canaries)}"

    await check("[Edge Case] canary_injected_on_after_tool_call_when_roll_passes", canary_inject_when_roll_passes)

    async def canary_not_injected_low_prob():
        mw = CanaryTripwireMiddleware(inject_probability=0.001, random_seed=99)
        ctx = MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("scrape"), tool_result=ToolResult.success("scrape", "data"))
        await mw.after_tool_call(ctx)
        assert len(mw._canaries) == 0, f"Expected 0 canaries, got {len(mw._canaries)}"

    await check("[Edge Case] canary_not_injected_on_low_probability_roll", canary_not_injected_low_prob)

    async def canary_skipped_internal():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        ctx = MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("isDone"), tool_result=ToolResult.success("isDone", "done"), tool_is_internal=True)
        await mw.after_tool_call(ctx)
        assert len(mw._canaries) == 0

    await check("[Hidden Assumption] canary_skipped_for_internal_tools", canary_skipped_internal)

    async def canary_skipped_none_result():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        ctx = MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("lookup"), tool_result=None)
        await mw.after_tool_call(ctx)
        assert len(mw._canaries) == 0

    await check("[Hidden Assumption] canary_skipped_when_tool_result_is_none", canary_skipped_none_result)

    async def canary_leaked_aborts():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("scrape"), tool_result=ToolResult.success("scrape", "data")))
        canary = list(mw._canaries.keys())[0]
        d = await mw.after_model_response(MiddlewareContext(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, agent_name="w", model_response=FakeModelResponse(f"output {canary} end")))
        assert d.action.value == "abort_run", f"Expected abort, got {d.action.value}"
        assert d.metadata["leaked_canary"] == canary

    await check("[Edge Case] leaked_canary_aborts_after_model_response", canary_leaked_aborts)

    async def canary_no_leak_continues():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("scrape"), tool_result=ToolResult.success("scrape", "data")))
        d = await mw.after_model_response(MiddlewareContext(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, agent_name="w", model_response=FakeModelResponse("clean output")))
        assert d.action.value == "continue"

    await check("[Silent Failure] no_abort_when_canary_not_in_model_output", canary_no_leak_continues)

    async def canary_before_run_clears():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("scrape"), tool_result=ToolResult.success("scrape", "data")))
        assert len(mw._canaries) == 1
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w"))
        assert len(mw._canaries) == 0

    await check("[Hidden Failure] before_run_clears_canaries", canary_before_run_clears)

    async def canary_multiple_match():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        for t in ("a", "b", "c"):
            await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall(t), tool_result=ToolResult.success(t, "out")))
        target = list(mw._canaries.keys())[1]
        d = await mw.after_model_response(MiddlewareContext(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, agent_name="w", model_response=FakeModelResponse(f"x{target}y")))
        assert d.action.value == "abort_run"

    await check("[Edge Case] multiple_canaries_first_match_aborts", canary_multiple_match)

    async def canary_no_text_attr():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("s"), tool_result=ToolResult.success("s", "d")))
        canary = list(mw._canaries.keys())[0]
        d = await mw.after_model_response(MiddlewareContext(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, agent_name="w", model_response=NoTextResponse(f"out {canary}")))
        assert d.action.value == "abort_run"

    await check("[Hidden Assumption] model_response_without_text_attribute", canary_no_text_attr)

    async def canary_validation():
        ok = True
        for v in (0.0, -0.1, 1.1):
            try:
                CanaryTripwireMiddleware(inject_probability=v)
                ok = False
            except ValueError:
                pass
        assert ok, "Should raise ValueError for invalid probabilities"

    await check("[Edge Case] inject_probability_validation", canary_validation)

    async def canary_empty_output():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("s"), tool_result=ToolResult.success("s", "d")))
        d = await mw.after_model_response(MiddlewareContext(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, agent_name="w", model_response=FakeModelResponse("")))
        assert d.action.value == "continue"

    await check("[Silent Failure] empty_model_output_continues", canary_empty_output)

    async def canary_prob_one():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=7)
        for i in range(5):
            await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall(f"t{i}"), tool_result=ToolResult.success(f"t{i}", "o")))
        assert len(mw._canaries) == 5

    await check("[Edge Case] inject_probability_exactly_one", canary_prob_one)

    # =====================================================================
    # ConfusedDeputyGuardMiddleware
    # =====================================================================

    async def deputy_captures_message():
        mw = ConfusedDeputyGuardMiddleware()
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="user query"))
        assert mw._user_message == "user query"

    await check("[Hidden Assumption] before_run_captures_user_message", deputy_captures_message)

    async def deputy_accumulates():
        mw = ConfusedDeputyGuardMiddleware()
        for o in ("a", "b"):
            await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_result=ToolResult.success("t", o)))
        assert len(mw._tool_outputs) == 2

    await check("[Edge Case] after_tool_call_accumulates_results", deputy_accumulates)

    async def deputy_high_overlap():
        mw = ConfusedDeputyGuardMiddleware(max_external_content_ratio=0.6)
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="q"))
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_result=ToolResult.success("r", "rm -rf /important/data --force --recursive")))
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("exec", {"cmd": "rm -rf /important/data --force --recursive"})))
        assert d.action.value == "abort_run", f"Expected abort, got {d.action.value}"

    await check("[Edge Case] high_overlap_ratio_aborts", deputy_high_overlap)

    async def deputy_low_overlap():
        mw = ConfusedDeputyGuardMiddleware(max_external_content_ratio=0.6)
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="q"))
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_result=ToolResult.success("s", "The weather in NYC is sunny today")))
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("r", {"summary": "A completely different sentence about weather patterns"})))
        assert d.action.value == "continue"

    await check("[Silent Failure] low_overlap_ratio_continues", deputy_low_overlap)

    async def deputy_short_args():
        mw = ConfusedDeputyGuardMiddleware(min_argument_length=20)
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="q"))
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_result=ToolResult.success("t", "short")))
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("e", {"cmd": "short"})))
        assert d.action.value == "continue"

    await check("[Edge Case] short_arguments_skipped", deputy_short_args)

    async def deputy_non_string():
        mw = ConfusedDeputyGuardMiddleware()
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="q"))
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_result=ToolResult.success("t", "12345 data")))
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("a", {"count": 12345, "verbose": True})))
        assert d.action.value == "continue"

    await check("[Hidden Assumption] non_string_arguments_skipped", deputy_non_string)

    async def deputy_internal_skip():
        mw = ConfusedDeputyGuardMiddleware(max_external_content_ratio=0.1)
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="q"))
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_result=ToolResult.success("t", "verbatim content that is very long")))
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("isDone", {"final_answer": "verbatim content that is very long"}), tool_is_internal=True))
        assert d.action.value == "continue"

    await check("[Hidden Assumption] internal_tool_calls_skipped", deputy_internal_skip)

    async def deputy_no_outputs():
        mw = ConfusedDeputyGuardMiddleware()
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="q"))
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("s", {"query": "some very long query string for searching"})))
        assert d.action.value == "continue"

    await check("[Hidden Failure] no_tool_outputs_accumulated_continues", deputy_no_outputs)

    async def deputy_resets():
        mw = ConfusedDeputyGuardMiddleware()
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_result=ToolResult.success("t", "accumulated")))
        assert len(mw._tool_outputs) == 1
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="new"))
        assert len(mw._tool_outputs) == 0

    await check("[Hidden Failure] before_run_resets_state", deputy_resets)

    async def deputy_exact_copy():
        mw = ConfusedDeputyGuardMiddleware(max_external_content_ratio=0.5)
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="q"))
        content = "This is a long piece of adversarial content from a webpage"
        await mw.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_result=ToolResult.success("s", content)))
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("e", {"payload": content})))
        assert d.action.value == "abort_run"
        assert abs(d.metadata["overlap_ratio"] - 1.0) < 0.01

    await check("[Edge Case] exact_copy_argument_aborts", deputy_exact_copy)

    async def deputy_ratio_validation():
        ok = True
        for v in (0.0, 1.1):
            try:
                ConfusedDeputyGuardMiddleware(max_external_content_ratio=v)
                ok = False
            except ValueError:
                pass
        assert ok

    await check("[Edge Case] max_external_content_ratio_validation", deputy_ratio_validation)

    async def deputy_min_len_validation():
        try:
            ConfusedDeputyGuardMiddleware(min_argument_length=0)
            assert False, "Should raise"
        except ValueError:
            pass

    await check("[Edge Case] min_argument_length_validation", deputy_min_len_validation)

    # =====================================================================
    # HoneypotToolMiddleware
    # =====================================================================

    async def honeypot_trap_aborts():
        mw = HoneypotToolMiddleware(trap_tool_names=["_admin_override", "_bypass"])
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("_admin_override")))
        assert d.action.value == "abort_run"
        assert d.metadata["trapped_tool"] == "_admin_override"

    await check("[Edge Case] trap_tool_name_aborts", honeypot_trap_aborts)

    async def honeypot_normal_continues():
        mw = HoneypotToolMiddleware(trap_tool_names=["_admin"])
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("lookup")))
        assert d.action.value == "continue"

    await check("[Silent Failure] normal_tool_name_continues", honeypot_normal_continues)

    async def honeypot_internal_excluded():
        mw = HoneypotToolMiddleware(trap_tool_names=["isDone"])
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("isDone"), tool_is_internal=True))
        assert d.action.value == "continue"

    await check("[Hidden Assumption] internal_tool_excluded", honeypot_internal_excluded)

    async def honeypot_multiple():
        mw = HoneypotToolMiddleware(trap_tool_names=["_override", "_admin", "_bypass"])
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("_admin")))
        assert d.action.value == "abort_run"
        assert d.metadata["trapped_tool"] == "_admin"

    await check("[Edge Case] multiple_trap_names", honeypot_multiple)

    async def honeypot_empty_raises():
        try:
            HoneypotToolMiddleware(trap_tool_names=[])
            assert False, "Should raise"
        except ValueError:
            pass

    await check("[Edge Case] empty_trap_names_raises", honeypot_empty_raises)

    async def honeypot_none_call():
        mw = HoneypotToolMiddleware(trap_tool_names=["_admin"])
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=None))
        assert d.action.value == "continue"

    await check("[Hidden Assumption] tool_call_none_continues", honeypot_none_call)

    async def honeypot_case_sensitive():
        mw = HoneypotToolMiddleware(trap_tool_names=["_admin"])
        d = await mw.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("_Admin")))
        assert d.action.value == "continue"

    await check("[Silent Failure] case_sensitive_matching", honeypot_case_sensitive)

    # =====================================================================
    # Pipeline Integration
    # =====================================================================

    async def pipeline_canary():
        mw = CanaryTripwireMiddleware(inject_probability=1.0, random_seed=42)
        pipeline = MiddlewarePipeline([mw])
        d = await pipeline.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_call=ToolCall("s"), tool_result=ToolResult.success("s", "c")))
        assert d.action.value == "continue"
        assert len(mw._canaries) == 1

    await check("[Integration] canary_tripwire_in_pipeline", pipeline_canary)

    async def pipeline_honeypot_order():
        honeypot = HoneypotToolMiddleware(trap_tool_names=["_admin"])
        policy = ToolPolicyMiddleware(allow_tools={"lookup"})
        pipeline = MiddlewarePipeline([honeypot, policy])
        d = await pipeline.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("_admin")))
        assert d.action.value == "abort_run"
        assert d.reason == "honeypot_triggered"

    await check("[Integration] honeypot_before_tool_policy_order", pipeline_honeypot_order)

    async def pipeline_deputy():
        policy = ToolPolicyMiddleware(allow_tools={"exec", "lookup"})
        deputy = ConfusedDeputyGuardMiddleware(max_external_content_ratio=0.5)
        pipeline = MiddlewarePipeline([policy, deputy])
        await pipeline.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="w", message="q"))
        await pipeline.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="w", tool_result=ToolResult.success("lookup", "injected payload content here for exec")))
        d = await pipeline.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="w", tool_call=ToolCall("exec", {"cmd": "injected payload content here for exec"})))
        assert d.action.value == "abort_run"

    await check("[Integration] confused_deputy_with_tool_policy", pipeline_deputy)

    # =====================================================================
    # Summary
    # =====================================================================

    print("\n" + "=" * 60)
    for name, ok, err in results:
        status = "PASS" if ok else "FAIL"
        line = f"  {status}  {name}"
        if not ok:
            line += f"\n         {err}"
        print(line)
    print("=" * 60)
    print(f"\n{passed}/{total} tests passed\n")
    return passed, total


def main() -> None:
    # Entry point: runs all tests and exits with appropriate code.
    passed, total = asyncio.run(run_all_tests())
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
