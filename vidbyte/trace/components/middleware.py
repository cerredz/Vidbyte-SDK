"""Middleware semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class MiddlewareTrace:
    """Factory for middleware decision spans."""

    @staticmethod
    def decision(**attributes: Any) -> SpanSpec:
        # Describes a middleware decision that may change runtime control flow.
        return SpanSpec("middleware.decision", SpanKind.CHAIN, "middleware", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def hook(**attributes: Any) -> SpanSpec:
        # Describes an individual middleware hook in diagnostic mode.
        return SpanSpec("middleware.hook", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def before_run_ran(**attributes: Any) -> SpanSpec:
        # Describes a before_run middleware hook firing.
        return SpanSpec("middleware.before_run.ran", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def before_iteration_ran(**attributes: Any) -> SpanSpec:
        # Describes a before_iteration middleware hook firing.
        return SpanSpec("middleware.before_iteration.ran", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def before_model_call_ran(**attributes: Any) -> SpanSpec:
        # Describes a before_model_call middleware hook firing.
        return SpanSpec("middleware.before_model_call.ran", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def after_model_response_ran(**attributes: Any) -> SpanSpec:
        # Describes an after_model_response middleware hook firing.
        return SpanSpec("middleware.after_model_response.ran", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def on_model_error_ran(**attributes: Any) -> SpanSpec:
        # Describes an on_model_error middleware hook firing.
        return SpanSpec("middleware.on_model_error.ran", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def before_tool_call_ran(**attributes: Any) -> SpanSpec:
        # Describes a before_tool_call middleware hook firing.
        return SpanSpec("middleware.before_tool_call.ran", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def after_tool_call_ran(**attributes: Any) -> SpanSpec:
        # Describes an after_tool_call middleware hook firing.
        return SpanSpec("middleware.after_tool_call.ran", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def after_iteration_ran(**attributes: Any) -> SpanSpec:
        # Describes an after_iteration middleware hook firing.
        return SpanSpec("middleware.after_iteration.ran", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def after_run_ran(**attributes: Any) -> SpanSpec:
        # Describes an after_run middleware hook firing.
        return SpanSpec("middleware.after_run.ran", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.AGENT, attributes)

    @staticmethod
    def action_sleep(**attributes: Any) -> SpanSpec:
        # Describes a middleware sleep action being applied.
        return SpanSpec("middleware.action.sleep", SpanKind.CHAIN, "middleware", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def action_abort_run(**attributes: Any) -> SpanSpec:
        # Describes a middleware abort_run action terminating the run.
        return SpanSpec("middleware.action.abort_run", SpanKind.CHAIN, "middleware", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def action_deny_tool(**attributes: Any) -> SpanSpec:
        # Describes a middleware deny_tool action blocking a tool call.
        return SpanSpec("middleware.action.deny_tool", SpanKind.CHAIN, "middleware", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def action_retry(**attributes: Any) -> SpanSpec:
        # Describes a middleware retry action re-running an iteration.
        return SpanSpec("middleware.action.retry", SpanKind.CHAIN, "middleware", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def exception(**attributes: Any) -> SpanSpec:
        # Describes a middleware raising an exception with fail_closed/fail_open outcome.
        return SpanSpec("middleware.exception", SpanKind.CHAIN, "middleware", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def transform_applied(**attributes: Any) -> SpanSpec:
        # Describes a MiddlewareTransform modifying model-visible state.
        return SpanSpec("middleware.transform.applied", SpanKind.CHAIN, "middleware", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def builtin(name: str, **attributes: Any) -> SpanSpec:
        # Describes a named builtin middleware firing.
        safe_name = str(name).replace("_", "-")
        return SpanSpec(f"middleware.builtin.{safe_name}", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.CURRENT, attributes)


__all__ = ["MiddlewareTrace"]
