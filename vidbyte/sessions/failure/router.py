"""FILE: vidbyte/sessions/failure/router.py

PURPOSE: Normalizes runtime outcomes and routes exhausted Session failures to explicit handlers.
ROLE IN CODEBASE: Owns the bounded per-Session ledger, metadata adapter, middleware bridge, and recovery lifecycle.
ARCHITECTURE NOTE: Existing local retries, fallbacks, policies, and contracts remain first recovery owners.
    FailureMiddleware lives in vidbyte.middleware.builtins.session_failure_router, the shared home for
    every other built-in policy middleware. This module cannot import it directly: vidbyte/lib's A006
    dependency-graph policy treats vidbyte.sessions as a lower layer than vidbyte.middleware, so the
    orchestration-tier caller (vidbyte.agents.base._runtime_middleware) constructs FailureMiddleware(router)
    itself instead of calling a router.middleware() convenience method.
COMMON MODIFICATION PATTERNS: Add a stable metadata adapter or recovery transition with a focused integration test.
KNOWN EDGE CASES: Preserve bounded history, route each failure once, and keep fail-open/closed errors distinct.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/vocabulary.md.
TESTS: python scripts/test-session-failure-vocabulary.py.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar

from vidbyte.lib.dataclasses.failure import Failure, RecoveryAttempt, RecoveryBinding, RecoveryHandler, RecoveryResult
from vidbyte.lib.dataclasses.failure_recovery import FailureRouterSettings
from vidbyte.lib.enums.failure import FailureCode, FailureDisposition, FailurePhase, FailureStatus, RuleErrorMode
from vidbyte.lib.errors import FailureRaisedError
from vidbyte.sessions.failure.rules import FailureRule

_EMPTY_COUNT = 0


class FailureMetadataNormalizer:
    """Translate existing runtime metadata into canonical deterministic failures."""

    _STOP_CODES: ClassVar[dict[str, FailureCode]] = {
        "max_iterations": FailureCode.RUNTIME_MAX_ITERATIONS,
        "max_tokens": FailureCode.RUNTIME_MAX_TOKENS,
        "max_tool_calls": FailureCode.RUNTIME_MAX_TOOL_CALLS,
        "max_calls_per_iteration": FailureCode.TOOL_CALLS_PER_ITERATION_LIMIT,
        "max_identical_calls": FailureCode.TOOL_IDENTICAL_CALL_LIMIT,
        "max_consecutive_failures": FailureCode.TOOL_CONSECUTIVE_FAILURE_LIMIT,
        "max_error_calls": FailureCode.TOOL_ERROR_LIMIT,
        "sliding_window_max_calls": FailureCode.TOOL_SLIDING_WINDOW_LIMIT,
        "tool_settings_denied": FailureCode.TOOL_PERMISSION_DENIED,
        "tool_loop_limit": FailureCode.TOOL_LOOP_LIMIT,
        "timeout": FailureCode.RUNTIME_TIMEOUT,
        "middleware_abort": FailureCode.RUNTIME_MIDDLEWARE_ABORT,
        "contract_unsatisfied": FailureCode.CONTRACT_UNSATISFIED,
        "error": FailureCode.RUNTIME_ERROR,
    }
    # @intent stop-codes-cover-agentstopreason
    # Every vidbyte.lib.dataclasses.agents.AgentStopReason member is accounted for here except
    # FINAL_RESPONSE and IS_DONE, which _append_stop_failure excludes as non-failure terminal states.
    _TOOL_ERROR_CODES: ClassVar[dict[str, FailureCode]] = {
        "unknown_tool": FailureCode.TOOL_NOT_FOUND,
        "permission_denied": FailureCode.TOOL_PERMISSION_DENIED,
        "middleware_denied": FailureCode.TOOL_PERMISSION_DENIED,
        "timeout": FailureCode.TOOL_TIMEOUT,
        "validation_error": FailureCode.TOOL_ARGUMENTS_INVALID,
        "invalid_arguments": FailureCode.TOOL_ARGUMENTS_INVALID,
        "output_schema_violation": FailureCode.TOOL_RESULT_INVALID,
        "missing_result": FailureCode.TOOL_RESULT_MISSING,
        "execution_error": FailureCode.TOOL_EXECUTION_FAILED,
        "mcp_error": FailureCode.DATA_SOURCE_UNAVAILABLE,
    }
    # @intent tool-error-codes-cover-known-metadata-error-tokens
    # "mcp_error" (vidbyte/tools/mcp/client.py) is mapped alongside the vidbyte/tools/executor.py
    # and vidbyte/agents/runtime.py ToolResult.metadata["error"] tokens; a token with no entry here
    # is simply left uncounted by _append_tool_context_failures rather than misclassified.

    @classmethod
    def from_reply(cls, reply: object) -> tuple[Failure, ...]:
        # @intent normalize-after-local-recovery
        # Session observes the runtime only after local retries, fallbacks, and
        # contract handling have published their bounded outcome metadata.
        """Extract canonical failures from one AgentMessage-like reply."""
        metadata = getattr(reply, "metadata", {})
        if not isinstance(metadata, Mapping):
            return ()
        failures: list[Failure] = []
        cls._append_explicit_failures(failures, metadata)
        cls._append_stop_failure(failures, metadata)
        cls._append_contract_failures(failures, metadata)
        cls._append_tool_failures(failures, metadata)
        cls._append_tool_context_failures(failures, metadata)
        cls._append_middleware_failures(failures, metadata)
        cls._append_fallback_failure(failures, metadata)
        cls._append_integrity_failures(failures, metadata)
        return cls._deduplicate(failures)

    @classmethod
    def _append_explicit_failures(cls, failures: list[Failure], metadata: Mapping[str, Any]) -> None:
        # Accept already-normalized records from future runtime producers without trusting their identity blindly.
        raw = metadata.get("failures", ())
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return
        for item in raw:
            if isinstance(item, Failure):
                failures.append(item)
            elif isinstance(item, Mapping) and item.get("code"):
                try:
                    failures.append(Failure(code=str(item["code"]), source=str(item.get("source", "runtime")), phase=str(item.get("phase", FailurePhase.RUNTIME.value)), status=str(item.get("status", FailureStatus.OBSERVED.value)), disposition=str(item.get("disposition", FailureDisposition.RECORD.value)), details=item.get("details", {})))
                except (TypeError, ValueError):
                    continue

    @classmethod
    def _append_stop_failure(cls, failures: list[Failure], metadata: Mapping[str, Any]) -> None:
        # Map the runtime's stable AgentStopReason value to one canonical code.
        stop_reason = metadata.get("stop_reason")
        if stop_reason is None or str(stop_reason) in {"final_response", "is_done"}:
            return
        code = cls._STOP_CODES.get(str(stop_reason), FailureCode.RUNTIME_ERROR)
        status = FailureStatus.EXHAUSTED if code is not FailureCode.RUNTIME_MIDDLEWARE_ABORT else FailureStatus.TERMINAL
        failures.append(Failure(code=code, source="agent_runtime", phase=FailurePhase.LOOP, status=status, disposition=FailureDisposition.ROUTE if status is FailureStatus.EXHAUSTED else FailureDisposition.STOP, details={"stop_reason": str(stop_reason), "iteration_count": metadata.get("iteration_count"), "tokens_used": metadata.get("tokens_used")}))

    @classmethod
    def _append_contract_failures(cls, failures: list[Failure], metadata: Mapping[str, Any]) -> None:
        # Record unmet output contracts as one grouped deterministic failure.
        rows = metadata.get("contract_evaluations", ())
        if not isinstance(rows, Sequence) or not any(isinstance(row, Mapping) and row.get("satisfied") is False for row in rows):
            return
        unmet = tuple(str(row.get("name")) for row in rows if isinstance(row, Mapping) and row.get("satisfied") is False)
        failures.append(Failure(code=FailureCode.CONTRACT_UNSATISFIED, source="output_contract", phase=FailurePhase.OUTPUT, status=FailureStatus.EXHAUSTED if metadata.get("stop_reason") == "contract_unsatisfied" else FailureStatus.OBSERVED, disposition=FailureDisposition.ROUTE if metadata.get("stop_reason") == "contract_unsatisfied" else FailureDisposition.RECORD, details={"unmet": unmet}))

    @classmethod
    def _append_tool_failures(cls, failures: list[Failure], metadata: Mapping[str, Any]) -> None:
        # @intent preserve-action-boundary-signal
        # Tool denials and execution failures teach future agents what action
        # was attempted without conflating it with transport or model errors.
        # Convert failed and denied ToolCallContext states into action-level records.
        states = metadata.get("tool_call_states", ())
        if isinstance(states, Sequence) and not isinstance(states, (str, bytes)):
            failed = sum(1 for state in states if str(getattr(state, "value", state)) == "failed")
            denied = sum(1 for state in states if str(getattr(state, "value", state)) == "denied")
            if failed:
                failures.append(Failure(code=FailureCode.TOOL_EXECUTION_FAILED, source="agent_runtime", phase=FailurePhase.TOOL, details={"failed_calls": failed}))
            if denied:
                failures.append(Failure(code=FailureCode.TOOL_PERMISSION_DENIED, source="agent_runtime", phase=FailurePhase.TOOL, details={"denied_calls": denied}))
        budget = metadata.get("tool_settings_budget")
        if budget:
            code = cls._STOP_CODES.get(str(budget), FailureCode.TOOL_CALL_LIMIT_REACHED)
            failures.append(Failure(code=code, source="tool_settings", phase=FailurePhase.TOOL, status=FailureStatus.EXHAUSTED, disposition=FailureDisposition.ROUTE, details={"budget": str(budget)}))

    @classmethod
    def _append_tool_context_failures(cls, failures: list[Failure], metadata: Mapping[str, Any]) -> None:
        # @intent classify-tool-result-remediation
        # Result metadata carries the most specific deterministic tool cause;
        # classify it before the generic failed/denied state aggregate.
        calls = metadata.get("tool_calls", ())
        if not isinstance(calls, Sequence) or isinstance(calls, (str, bytes)):
            return
        counts: dict[FailureCode, int] = {}
        for call in calls:
            result = getattr(call, "result", None)
            result_metadata = getattr(result, "metadata", {})
            error = str(result_metadata.get("error", "")) if isinstance(result_metadata, Mapping) else ""
            code = cls._TOOL_ERROR_CODES.get(error)
            if code is not None:
                counts[code] = counts.get(code, _EMPTY_COUNT) + 1
        for code, count in counts.items():
            failures.append(Failure(code=code, source="tool_runtime", phase=FailurePhase.TOOL, details={"failed_calls": count}))

    @classmethod
    def _append_middleware_failures(cls, failures: list[Failure], metadata: Mapping[str, Any]) -> None:
        # Normalize abort and middleware-error events while leaving ordinary retries local.
        events = metadata.get("middleware", {}).get("events", ()) if isinstance(metadata.get("middleware"), Mapping) else metadata.get("events", ())
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            return
        for event in events:
            if not isinstance(event, Mapping):
                continue
            action = str(event.get("action", ""))
            reason = str(event.get("reason", ""))
            if action == "abort_run":
                failures.append(Failure(code=FailureCode.RUNTIME_MIDDLEWARE_ERROR if reason == "middleware_error" else FailureCode.RUNTIME_MIDDLEWARE_ABORT, source=str(event.get("middleware_name", "middleware")), phase=FailurePhase.RUNTIME, status=FailureStatus.TERMINAL, disposition=FailureDisposition.STOP, details={"hook": event.get("hook"), "reason": reason}))

    @classmethod
    def _append_fallback_failure(cls, failures: list[Failure], metadata: Mapping[str, Any]) -> None:
        # @intent fallback-remains-local-owner
        # A successful model fallback is recorded as recovered evidence, never
        # replayed as a second Session-level fallback attempt.
        # Record a successful local fallback as recovered learning signal without routing it again.
        fallback = metadata.get("fallback")
        if not isinstance(fallback, Mapping) or not fallback.get("used"):
            return
        attempts = fallback.get("attempts", ())
        failures.append(Failure(code=FailureCode.MODEL_REQUEST_FAILED, source="agent_fallback", phase=FailurePhase.MODEL, status=FailureStatus.RECOVERED, disposition=FailureDisposition.RECORD, handled_by="agent_fallback", details={"attempt_count": len(attempts) if isinstance(attempts, Sequence) else _EMPTY_COUNT, "final_model": fallback.get("final_model")}))

    @classmethod
    def _append_integrity_failures(cls, failures: list[Failure], metadata: Mapping[str, Any]) -> None:
        # @intent observability-fails-open
        # Persistence and usage markers remain actionable training signals but
        # do not silently become a run-ending policy decision.
        # Surface intentionally fail-open persistence and usage/trace integrity markers.
        if metadata.get("__session_error__"):
            failures.append(Failure(code=FailureCode.SESSION_PERSISTENCE_FAILED, source="session", phase=FailurePhase.SESSION, disposition=FailureDisposition.CONTINUE, details={"error_type": cls._error_type(metadata["__session_error__"])}))
        usage = metadata.get("usage_rollup")
        if getattr(usage, "recording_corrupted", False) or (isinstance(usage, Mapping) and usage.get("recording_corrupted")):
            failures.append(Failure(code=FailureCode.USAGE_RECORDING_CORRUPTED, source="usage_tracker", phase=FailurePhase.OBSERVABILITY, disposition=FailureDisposition.CONTINUE, details={"recording_corrupted": True}))

    @staticmethod
    def _error_type(value: Any) -> str:
        # Keep only the stable exception type from a legacy marker string.
        return str(value).split(":", 1)[0][:120]

    @staticmethod
    def _deduplicate(failures: Sequence[Failure]) -> tuple[Failure, ...]:
        # Deduplicate code/source pairs when runtime metadata exposes the same stop twice.
        seen: set[tuple[FailureCode, str]] = set()
        result: list[Failure] = []
        for failure in failures:
            key = (FailureCode.from_value(failure.code), failure.source)
            if key in seen:
                continue
            seen.add(key)
            result.append(failure)
        return tuple(result)


class FailureRouter:
    """Session-scoped bounded ledger that escalates only exhausted failures."""

    def __init__(self, session: object, *, max_history: int = 512, enabled: bool = True, on_capture: Callable[[Failure], object] | None = None) -> None:
        """Bind a router to one Session and validate its bounded ledger settings."""
        self.session = session
        self._settings = FailureRouterSettings(max_history=max_history, enabled=enabled, on_capture=on_capture)
        self._history: list[Failure] = []
        self._rules: list[FailureRule] = []
        self._bindings: dict[FailureCode, RecoveryBinding] = {}
        self._recovery_attempts: list[RecoveryAttempt] = []
        self._routed_ids: set[str] = set()

    @property
    def max_history(self) -> int:
        """Return the validated bound on failure and recovery-attempt history."""
        return self._settings.max_history

    @property
    def enabled(self) -> bool:
        """Return whether this router currently records and routes failures."""
        return self._settings.enabled

    @property
    def recovery_attempts(self) -> tuple[RecoveryAttempt, ...]:
        """Return immutable records for all attempted Session recoveries."""
        return tuple(self._recovery_attempts)

    @property
    def has_rules(self) -> bool:
        """Return whether this Session has any developer rules to evaluate."""
        return bool(self._rules)

    def record(self, failure: Failure) -> Failure:
        """Append one canonical failure to bounded history without routing it."""
        if not isinstance(failure, Failure):
            raise TypeError("FailureRouter.record requires a Failure instance.")
        if not self.enabled:
            return failure
        self._history.append(failure)
        if len(self._history) > self.max_history:
            evicted = self._history[: len(self._history) - self.max_history]
            del self._history[: len(evicted)]
            self._routed_ids.difference_update(item.id for item in evicted)
        if self._settings.on_capture is not None:
            # Fire-and-forget product-facing observability hook; a broken sink must never affect routing.
            try:
                self._settings.on_capture(failure)
            except Exception:
                pass
        return failure

    def emit(self, code: FailureCode, *, phase: FailurePhase, source: str, status: FailureStatus = FailureStatus.OBSERVED, disposition: FailureDisposition = FailureDisposition.RECORD, details: Mapping[str, Any] | None = None, handled_by: str | None = None, summary: str | None = None) -> Failure:
        """Construct and record one canonical failure from concise runtime facts."""
        return self.record(Failure(code=code, phase=phase, source=source, status=status, disposition=disposition, details=details or {}, handled_by=handled_by, summary=summary))

    def history(self, *, code: FailureCode | None = None, status: FailureStatus | None = None) -> tuple[Failure, ...]:
        """Return history in insertion order, optionally filtered by code/status."""
        code_filter = FailureCode.from_value(code) if code is not None else None
        status_filter = FailureStatus(status) if status is not None else None
        return tuple(failure for failure in self._history if (code_filter is None or failure.code is code_filter) and (status_filter is None or failure.status is status_filter))

    def add_rule(self, rule: Callable[..., Any] | FailureRule) -> FailureRule:
        """Register one decorated or explicit rule for this Session."""
        resolved = rule if isinstance(rule, FailureRule) else FailureRule.from_callable(rule)
        if not any(existing.callback is resolved.callback for existing in self._rules):
            self._rules.append(resolved)
            self._rules.sort(key=lambda item: -item.priority)
        return resolved

    def remove_rule(self, rule: Callable[..., Any] | FailureRule) -> None:
        """Remove a previously registered rule by descriptor or callback identity."""
        callback = rule.callback if isinstance(rule, FailureRule) else rule
        self._rules = [item for item in self._rules if item.callback is not callback]

    def on(self, code: FailureCode, recovery: RecoveryHandler, *, include_recovered: bool = False) -> None:
        """Bind one recovery handler to a canonical code."""
        resolved = FailureCode.from_value(code)
        if not callable(getattr(recovery, "recover", None)):
            raise TypeError("FailureRouter.on requires a recovery handler with recover().")
        self._bindings[resolved] = RecoveryBinding(handler=recovery, include_recovered=include_recovered)

    async def evaluate(self, hook: str, context: object) -> tuple[Failure, ...]:
        """Evaluate matching rules, record their failures, and apply dispositions."""
        if not self.enabled:
            return ()
        matched: list[Failure] = []
        for current in tuple(self._rules):
            if current.on != hook:
                continue
            failure = await self._invoke_rule(current, context)
            if failure is None:
                continue
            if failure.code is FailureCode.RULE_EVALUATION_FAILED:
                matched.append(failure)
                break
            effective = self._with_rule_disposition(failure, current)
            self.record(effective)
            matched.append(effective)
            should_stop = await self._apply_rule_disposition(effective, matched)
            if should_stop:
                break
        return tuple(matched)

    async def _invoke_rule(self, current: FailureRule, context: object) -> Failure | None:
        # Isolate detector exception policy from the ordered rule loop.
        try:
            return await current.invoke(context)
        except Exception as exc:
            failure = self._rule_error(current, exc)
            self.record(failure)
            if current.on_error is RuleErrorMode.CLOSED and failure.disposition is FailureDisposition.RAISE:
                raise FailureRaisedError(failure) from exc
            return failure if current.on_error is RuleErrorMode.CLOSED else None

    async def _apply_rule_disposition(self, failure: Failure, matched: list[Failure]) -> bool:
        # Apply one detector's action and report whether the hook must stop.
        if failure.disposition is FailureDisposition.ROUTE:
            await self.route(failure)
            # route() may have replaced the ledger entry (status/handled_by); reflect that back to the caller.
            matched[-1] = next((item for item in reversed(self._history) if item.id == failure.id), failure)
            return False
        if failure.disposition is FailureDisposition.RAISE:
            raise FailureRaisedError(failure)
        return failure.disposition is FailureDisposition.STOP

    def capture_reply(self, reply: object) -> tuple[Failure, ...]:
        """Normalize and record failures emitted by one completed agent reply."""
        if not self.enabled:
            return ()
        failures = FailureMetadataNormalizer.from_reply(reply)
        return tuple(self.record(failure) for failure in failures)

    def capture_exception(self, exc: BaseException, *, phase: FailurePhase = FailurePhase.RUNTIME, source: str = "session") -> Failure:
        """Record one SDK exception once, deduplicating Session and agent boundaries."""
        exception_ids: set[int] = set()
        current: BaseException | None = exc
        while current is not None:
            exception_ids.add(id(current))
            current = current.__cause__ or current.__context__
        existing = next((failure for failure in reversed(self._history) if failure.details.get("exception_id") in exception_ids), None)
        if existing is not None:
            return existing
        failure = Failure.from_exception(exc, phase=phase, source=source, details={"exception_id": id(exc)})
        return self.record(failure)

    async def route(self, failure: Failure) -> RecoveryResult | None:
        """Run the configured handler once when a failure is eligible for escalation."""
        if not self.enabled:
            return None
        binding = self._bindings.get(FailureCode.from_value(failure.code))
        if binding is None:
            return None
        if failure.status is FailureStatus.RECOVERED and not binding.include_recovered:
            return None
        if failure.id in self._routed_ids:
            return None
        self._routed_ids.add(failure.id)
        recovering = Failure(code=failure.code, source=failure.source, phase=failure.phase, status=FailureStatus.RECOVERING, disposition=failure.disposition, severity=failure.severity, summary=failure.summary, details=failure.details, handled_by=binding.handler.name, parent_id=failure.parent_id, iteration=failure.iteration, step=failure.step, id=failure.id, occurred_at=failure.occurred_at)
        self._replace(recovering)
        try:
            result = binding.handler.recover(recovering, session=self.session)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, RecoveryResult):
                raise TypeError(f"Recovery handler {binding.handler.name!r} must return RecoveryResult, got {type(result).__name__}.")
        except FailureRaisedError:
            # A handler explicitly escalating to raise still gets a terminal ledger entry before re-raising,
            # so history reflects what actually happened even though the caller never sees a RecoveryResult.
            self._replace(Failure(code=failure.code, source=failure.source, phase=failure.phase, status=FailureStatus.TERMINAL, disposition=FailureDisposition.RAISE, severity=failure.severity, summary=failure.summary, details=failure.details, handled_by=binding.handler.name, parent_id=failure.parent_id, iteration=failure.iteration, step=failure.step, id=failure.id, occurred_at=failure.occurred_at))
            raise
        except Exception as exc:
            return await self._handle_recovery_error(recovering, binding, exc)
        self._recovery_attempts.append(RecoveryAttempt(failure_id=failure.id, handler=binding.handler.name, succeeded=result.succeeded, disposition=result.disposition, details=result.details))
        if len(self._recovery_attempts) > self.max_history:
            del self._recovery_attempts[: len(self._recovery_attempts) - self.max_history]
        final_status = FailureStatus.RECOVERED if result.succeeded else FailureStatus.EXHAUSTED
        self._replace(Failure(code=failure.code, source=failure.source, phase=failure.phase, status=final_status, disposition=result.disposition, severity=failure.severity, summary=failure.summary, details={**dict(failure.details), **dict(result.details)}, handled_by=binding.handler.name, parent_id=failure.parent_id, iteration=failure.iteration, step=failure.step, id=failure.id, occurred_at=failure.occurred_at))
        return result

    async def route_pending(self) -> tuple[RecoveryResult, ...]:
        """Route each recorded exhausted or explicitly routed failure at most once."""
        if not self.enabled:
            return ()
        results: list[RecoveryResult] = []
        for failure in tuple(self._history):
            eligible = failure.status is FailureStatus.EXHAUSTED or failure.disposition is FailureDisposition.ROUTE
            if not eligible or failure.id in self._routed_ids:
                continue
            result = await self.route(failure)
            if result is not None:
                results.append(result)
        return tuple(results)

    async def _handle_recovery_error(self, failure: Failure, binding: RecoveryBinding, exc: BaseException) -> RecoveryResult | None:
        # Record handler failure separately so one broken strategy cannot recurse into itself:
        # this emits a distinct RECOVERY_HANDLER_FAILED record rather than re-routing the
        # original failure code back through the same (evidently broken) binding.
        error_mode = self._handler_error_mode(binding.handler)
        handler_failure = self.emit(FailureCode.RECOVERY_HANDLER_FAILED, phase=FailurePhase.RECOVERY, source=binding.handler.name, status=FailureStatus.TERMINAL if error_mode is RuleErrorMode.CLOSED else FailureStatus.OBSERVED, disposition=FailureDisposition.RAISE if error_mode is RuleErrorMode.CLOSED else FailureDisposition.CONTINUE, details={"failure_id": failure.id, "error_type": type(exc).__name__})
        self._recovery_attempts.append(RecoveryAttempt(failure_id=failure.id, handler=binding.handler.name, succeeded=False, disposition=handler_failure.disposition, details=handler_failure.details, error_type=type(exc).__name__))
        if len(self._recovery_attempts) > self.max_history:
            del self._recovery_attempts[: len(self._recovery_attempts) - self.max_history]
        self._replace(Failure(code=failure.code, source=failure.source, phase=failure.phase, status=FailureStatus.TERMINAL if error_mode is RuleErrorMode.CLOSED else FailureStatus.EXHAUSTED, disposition=handler_failure.disposition, severity=failure.severity, summary=failure.summary, details={**dict(failure.details), **dict(handler_failure.details)}, handled_by=binding.handler.name, parent_id=failure.parent_id, iteration=failure.iteration, step=failure.step, id=failure.id, occurred_at=failure.occurred_at))
        if error_mode is RuleErrorMode.CLOSED:
            raise FailureRaisedError(handler_failure) from exc
        return RecoveryResult(succeeded=False, disposition=FailureDisposition.CONTINUE, details={"error_type": type(exc).__name__})

    @staticmethod
    def _handler_error_mode(handler: RecoveryHandler) -> RuleErrorMode:
        # Normalize custom handler error posture while defaulting unknown/invalid values to fail closed,
        # since a third-party RecoveryHandler is not guaranteed to expose a valid RuleErrorMode.
        try:
            return RuleErrorMode(getattr(handler, "on_error", RuleErrorMode.CLOSED))
        except (TypeError, ValueError):
            return RuleErrorMode.CLOSED

    def _rule_error(self, current: FailureRule, exc: Exception) -> Failure:
        # Convert a detector exception into a canonical open/closed failure record. A closed rule
        # escalates using its own on_match (raise if it was going to raise, stop otherwise); an open
        # rule is recorded but never blocks the run, matching its declared telemetry-only intent.
        closed = current.on_error is RuleErrorMode.CLOSED
        disposition = FailureDisposition.CONTINUE
        if closed:
            disposition = FailureDisposition.RAISE if current.on_match is FailureDisposition.RAISE else FailureDisposition.STOP
        return Failure(code=FailureCode.RULE_EVALUATION_FAILED, source=current.name, phase=FailurePhase.RUNTIME, status=FailureStatus.TERMINAL if closed else FailureStatus.OBSERVED, disposition=disposition, details={"rule": current.name, "hook": current.on, "error_type": type(exc).__name__})

    @staticmethod
    def _with_rule_disposition(failure: Failure, current: FailureRule) -> Failure:
        # Apply decorator policy while retaining the rule's richer returned details. A rule that
        # matched successfully always uses its own declared code/on_match, never the raw failure's.
        status = FailureStatus.TERMINAL if current.on_match in (FailureDisposition.STOP, FailureDisposition.RAISE) else FailureStatus.EXHAUSTED if current.on_match is FailureDisposition.ROUTE else failure.status
        return Failure(code=current.code, source=failure.source, phase=failure.phase, status=status, disposition=current.on_match, severity=failure.severity, summary=failure.summary, details=failure.details, handled_by=failure.handled_by, parent_id=failure.parent_id, iteration=failure.iteration, step=failure.step, id=failure.id, occurred_at=failure.occurred_at)

    def _replace(self, failure: Failure) -> None:
        # Replace an in-progress record in place so one failure id has one current lifecycle state,
        # instead of accumulating a new history row per lifecycle transition (observed -> recovering
        # -> recovered/exhausted/terminal). Falls back to record() only if the id was already evicted.
        for index, existing in enumerate(self._history):
            if existing.id == failure.id:
                self._history[index] = failure
                return
        self.record(failure)


__all__ = ["FailureMetadataNormalizer", "FailureRouter"]
