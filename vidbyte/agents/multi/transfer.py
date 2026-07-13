"""Context Protocol Header

Description:
    Implements the developer-controlled boundary between the controller and workers.
Purpose:
    Defines how task dispatches are approved, rendered, parsed, validated, forked,
    retried, and closed without hard-coding an agent-to-agent payload schema.
Architecture:
    - AgentTransfer: Immutable callback and retry policy bundle.
    - AgentBinding: Worker template plus subtype-aware lifecycle hooks.
    - Helper functions: Await sync/async callbacks and enforce safe defaults.
Relations:
    Called by vidbyte.agents.multi.agent; consumes contracts from vidbyte.lib.dataclasses.multi_agent.
"""

from __future__ import annotations

import inspect
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.agents.multi.types import BeforeDispatch, ReportParser, ReportValidator, RequestBuilder, WorkerCloser, WorkerForkFactory
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.multi_agent import AgentDispatch, AgentReport, TaskBlocker, TaskEvidence, TaskLedgerSnapshot
from vidbyte.lib.enums.multi_agent import TaskStatus
from vidbyte.lib.errors import AgentTransferError


@dataclass(frozen=True, slots=True)
class AgentTransfer:
    """Callbacks and bounded retry policy for one worker boundary."""

    before_dispatch: BeforeDispatch | None = None
    request_builder: RequestBuilder | None = None
    report_parser: ReportParser | None = None
    report_validator: ReportValidator | None = None
    fork_settings: AgentForkSettings = field(default_factory=AgentForkSettings)
    reset_on_replan: bool = True
    timeout_seconds: float | None = None
    max_invocation_retries: int = 0

    def __post_init__(self) -> None:
        # Keeps transfer retries finite and timeout behavior explicit at configuration time.
        for label, callback in (("before_dispatch", self.before_dispatch), ("request_builder", self.request_builder), ("report_parser", self.report_parser), ("report_validator", self.report_validator)):
            if callback is not None and not callable(callback):
                raise AgentTransferError(f"AgentTransfer.{label} must be callable when provided.", details={"actual_type": type(callback).__name__})
        if not isinstance(self.fork_settings, AgentForkSettings):
            raise AgentTransferError("AgentTransfer.fork_settings must be AgentForkSettings.", details={"actual_type": type(self.fork_settings).__name__})
        if not isinstance(self.reset_on_replan, bool):
            raise AgentTransferError("AgentTransfer.reset_on_replan must be bool.")
        if self.timeout_seconds is not None and (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float)) or self.timeout_seconds <= 0):
            raise AgentTransferError("AgentTransfer.timeout_seconds must be positive when provided.")
        if isinstance(self.max_invocation_retries, bool) or not isinstance(self.max_invocation_retries, int) or self.max_invocation_retries < 0:
            raise AgentTransferError("AgentTransfer.max_invocation_retries must be non-negative.")

    async def approve_dispatch(self, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> TaskBlocker | None:
        # Runs the optional fail-closed policy gate and validates its explicit denial shape.
        if self.before_dispatch is None:
            return None
        try:
            result = await maybe_await(self.before_dispatch(dispatch, ledger))
        except AgentTransferError:
            raise
        except Exception as exc:
            raise AgentTransferError("AgentTransfer.before_dispatch failed.", details={"task_id": dispatch.task_id, "error_type": type(exc).__name__}) from exc
        if result is not None and not isinstance(result, TaskBlocker):
            raise AgentTransferError("before_dispatch must return None or TaskBlocker.", details={"task_id": dispatch.task_id})
        return result

    async def build_request(self, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> str | AgentInput:
        # Builds the exact worker input and rejects unsupported callback output types.
        builder = self.request_builder or default_request_builder
        try:
            request = await maybe_await(builder(dispatch, ledger))
        except AgentTransferError:
            raise
        except Exception as exc:
            raise AgentTransferError("AgentTransfer.request_builder failed.", details={"task_id": dispatch.task_id, "error_type": type(exc).__name__}) from exc
        if not isinstance(request, (str, AgentInput)):
            raise AgentTransferError("request_builder must return str or AgentInput.", details={"task_id": dispatch.task_id, "actual_type": type(request).__name__})
        return request

    async def parse_report(self, reply: AgentMessage, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> AgentReport:
        # Converts a worker reply into a task-bound report without trusting prose as verification.
        parser = self.report_parser or default_report_parser
        try:
            report = await maybe_await(parser(reply, dispatch, ledger))
        except AgentTransferError:
            raise
        except Exception as exc:
            raise AgentTransferError("AgentTransfer.report_parser failed.", details={"task_id": dispatch.task_id, "error_type": type(exc).__name__}) from exc
        if not isinstance(report, AgentReport):
            raise AgentTransferError("report_parser must return AgentReport.", details={"task_id": dispatch.task_id, "actual_type": type(report).__name__})
        if report.task_id != dispatch.task_id:
            raise AgentTransferError("Worker report task_id does not match its dispatch.", details={"expected_task_id": dispatch.task_id, "actual_task_id": report.task_id})
        return report

    async def validate_report(self, report: AgentReport, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> AgentReport:
        # Applies the optional acceptance filter and rechecks task identity before commit.
        if self.report_validator is None:
            return report
        try:
            validated = await maybe_await(self.report_validator(report, dispatch, ledger))
        except AgentTransferError:
            raise
        except Exception as exc:
            raise AgentTransferError("AgentTransfer.report_validator failed.", details={"task_id": dispatch.task_id, "error_type": type(exc).__name__}) from exc
        if not isinstance(validated, AgentReport):
            raise AgentTransferError("report_validator must return AgentReport.", details={"task_id": dispatch.task_id, "actual_type": type(validated).__name__})
        if validated.task_id != dispatch.task_id:
            raise AgentTransferError("Validated report task_id does not match its dispatch.", details={"expected_task_id": dispatch.task_id, "actual_task_id": validated.task_id})
        return validated


@dataclass(frozen=True, slots=True)
class AgentBinding:
    """Worker template paired with transfer and subtype-preserving lifecycle hooks."""

    agent: BaseAgent
    transfer: AgentTransfer = field(default_factory=AgentTransfer)
    fork_factory: WorkerForkFactory | None = None
    closer: WorkerCloser | None = None

    def __post_init__(self) -> None:
        # Rejects non-agent templates before a run can partially initialize.
        if not isinstance(self.agent, BaseAgent):
            raise AgentTransferError("AgentBinding.agent must be a BaseAgent instance.")
        if not isinstance(self.transfer, AgentTransfer):
            raise AgentTransferError("AgentBinding.transfer must be AgentTransfer.", details={"actual_type": type(self.transfer).__name__})
        for label, callback in (("fork_factory", self.fork_factory), ("closer", self.closer)):
            if callback is not None and not callable(callback):
                raise AgentTransferError(f"AgentBinding.{label} must be callable when provided.", details={"actual_type": type(callback).__name__})


async def maybe_await(value: Any) -> Any:
    # Normalizes developer callbacks so each extension seam may be synchronous or asynchronous.
    return await value if inspect.isawaitable(value) else value


async def approve_dispatch(transfer: AgentTransfer, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> TaskBlocker | None:
    # Preserves the functional helper while delegating validation to the transfer object.
    return await transfer.approve_dispatch(dispatch, ledger)


async def build_worker_request(transfer: AgentTransfer, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> str | AgentInput:
    # Preserves the functional helper while exposing the current immutable snapshot to builders.
    return await transfer.build_request(dispatch, ledger)


async def parse_worker_report(transfer: AgentTransfer, reply: AgentMessage, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> AgentReport:
    # Preserves the functional helper while exposing the current immutable snapshot to parsers.
    return await transfer.parse_report(reply, dispatch, ledger)


async def validate_worker_report(transfer: AgentTransfer, report: AgentReport, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> AgentReport:
    # Preserves the functional helper while delegating acceptance policy to the transfer object.
    return await transfer.validate_report(report, dispatch, ledger)


async def fork_worker(binding: AgentBinding) -> BaseAgent:
    # Creates run-local worker state while preserving the template's behavioral subtype.
    try:
        child = binding.agent.fork(binding.transfer.fork_settings) if binding.fork_factory is None else binding.fork_factory(binding.agent, binding.transfer.fork_settings)
    except AgentTransferError:
        raise
    except Exception as exc:
        raise AgentTransferError("Worker fork factory failed.", details={"worker": binding.agent.name, "error_type": type(exc).__name__}) from exc
    if inspect.isawaitable(child):
        if inspect.iscoroutine(child):
            child.close()
        raise AgentTransferError("Worker fork factories must be synchronous so run and team forks share one lifecycle contract.", details={"worker": binding.agent.name})
    if not isinstance(child, BaseAgent) or not isinstance(child, type(binding.agent)):
        raise AgentTransferError("Worker fork erased or changed the configured behavioral subtype.", details={"worker": binding.agent.name, "expected_type": type(binding.agent).__name__, "actual_type": type(child).__name__})
    if child is binding.agent:
        raise AgentTransferError("Worker fork must return an isolated agent instance, not the configured template.", details={"worker": binding.agent.name})
    return child


async def close_worker(binding: AgentBinding, worker: BaseAgent) -> None:
    # Closes one run-local worker through its compound closer or the standard MCP lifecycle.
    if binding.closer is not None:
        await maybe_await(binding.closer(worker))
        return
    await worker.close_mcp_servers()


def default_request_builder(dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> str:
    # Emits only the documented task fields as deterministic JSON and rejects unsafe payloads.
    body = {
        "acceptance_criteria": list(dispatch.acceptance_criteria),
        "attempt": dispatch.attempt,
        "goal": dispatch.goal,
        "instruction": dispatch.instruction,
        "owner": dispatch.owner,
        "payload": dispatch.payload,
        "task_id": dispatch.task_id,
    }
    try:
        normalized = _normalize_json_value(body)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise AgentTransferError("Default worker requests require a JSON-safe payload.", details={"task_id": dispatch.task_id, "payload_type": type(dispatch.payload).__name__}) from exc


def _normalize_json_value(value: Any) -> Any:
    # Copies only JSON primitives, sequences, and string-keyed mappings without stringifying opaque objects.
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite.")
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JSON mappings require string keys.")
        return {key: _normalize_json_value(item) for key, item in value.items()}
    raise TypeError("Unsupported JSON payload type.")


def default_report_parser(reply: AgentMessage, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> AgentReport:
    # Treats non-blank text as accepted output while leaving evidence explicitly unverified.
    content = reply.content.strip()
    if content:
        evidence = TaskEvidence(source=dispatch.owner, value=content, verified=False)
        return AgentReport(task_id=dispatch.task_id, status=TaskStatus.COMPLETED, result=reply.content, evidence=(evidence,))
    blocker = TaskBlocker(code="empty_reply", message="Worker returned a blank reply.", retryable=True)
    return AgentReport(task_id=dispatch.task_id, status=TaskStatus.FAILED, blockers=(blocker,))


__all__ = [
    "AgentBinding",
    "AgentTransfer",
    "approve_dispatch",
    "build_worker_request",
    "close_worker",
    "default_report_parser",
    "default_request_builder",
    "fork_worker",
    "maybe_await",
    "parse_worker_report",
    "validate_worker_report",
]
