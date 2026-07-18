"""Context Protocol Header

Description:
    Implements the developer-controlled boundary between the controller and workers.
Purpose:
    Defines how dispatches are approved, rendered, parsed, validated, forked,
    retried, and closed without hard-coding an agent-to-agent payload schema.
Architecture:
    - AgentTransfer owns callback execution and default request/report policies.
    - AgentBinding owns subtype-preserving worker lifecycle behavior.
Relations:
    Called by dispatcher and cleanup collaborators; consumes shared vidbyte.lib contracts.
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
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.multi_agent import (
    AgentDispatch,
    AgentReport,
    BeforeDispatch,
    ReportParser,
    ReportValidator,
    RequestBuilder,
    TaskBlocker,
    TaskEvidence,
    TaskLedgerSnapshot,
    WorkerCloser,
    WorkerForkFactory,
)
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
        # Validate extension points before a run can consume a task attempt.
        self._validate_callbacks()
        self._validate_fork_settings()
        self._validate_reset_policy()
        self._validate_timeout()
        self._validate_retry_budget()

    async def approve_dispatch(self, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> TaskBlocker | None:
        # A policy gate fails closed and may deny dispatch with one structured blocker.
        if self.before_dispatch is None:
            return None
        result = await self._call_boundary("before_dispatch", dispatch, self.before_dispatch, dispatch, ledger)
        if result is not None and not isinstance(result, TaskBlocker):
            raise AgentTransferError("before_dispatch must return None or TaskBlocker.", details={"task_id": dispatch.task_id})
        return result

    async def build_request(self, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> str | AgentInput:
        # The request builder receives the exact snapshot used to approve this dispatch.
        builder = self.request_builder or self.default_request_builder
        request = await self._call_boundary("request_builder", dispatch, builder, dispatch, ledger)
        if not isinstance(request, (str, AgentInput)):
            raise AgentTransferError("request_builder must return str or AgentInput.", details={"task_id": dispatch.task_id, "actual_type": type(request).__name__})
        return request

    async def parse_report(self, reply: AgentMessage, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> AgentReport:
        # Parsing converts untrusted worker output into the stable report contract.
        parser = self.report_parser or self.default_report_parser
        report = await self._call_boundary("report_parser", dispatch, parser, reply, dispatch, ledger)
        self._validate_report_identity(report, dispatch, "report_parser")
        return report

    async def validate_report(self, report: AgentReport, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> AgentReport:
        # An optional developer gate may enrich or reject the parsed report before commit.
        if self.report_validator is None:
            return report
        validated = await self._call_boundary("report_validator", dispatch, self.report_validator, report, dispatch, ledger)
        self._validate_report_identity(validated, dispatch, "report_validator")
        return validated

    async def _call_boundary(self, label: str, dispatch: AgentDispatch, callback: Any, *args: Any) -> Any:
        # Boundary failures use one safe error shape so the ledger can close the attempt.
        try:
            return await self.maybe_await(callback(*args))
        except AgentTransferError:
            raise
        except Exception as exc:
            raise AgentTransferError(f"AgentTransfer.{label} failed.", details={"task_id": dispatch.task_id, "error_type": type(exc).__name__}) from exc

    def _validate_callbacks(self) -> None:
        # Each configured extension seam must remain directly callable.
        callbacks = (("before_dispatch", self.before_dispatch), ("request_builder", self.request_builder), ("report_parser", self.report_parser), ("report_validator", self.report_validator))
        for label, callback in callbacks:
            if callback is not None and not callable(callback):
                raise AgentTransferError(f"AgentTransfer.{label} must be callable when provided.", details={"actual_type": type(callback).__name__})

    def _validate_fork_settings(self) -> None:
        # Worker isolation depends on the standard AgentForkSettings contract.
        if not isinstance(self.fork_settings, AgentForkSettings):
            raise AgentTransferError("AgentTransfer.fork_settings must be AgentForkSettings.", details={"actual_type": type(self.fork_settings).__name__})

    def _validate_reset_policy(self) -> None:
        # Replan reset is intentionally explicit rather than truthy/falsy configuration.
        if not isinstance(self.reset_on_replan, bool):
            raise AgentTransferError("AgentTransfer.reset_on_replan must be bool.")

    def _validate_timeout(self) -> None:
        # Reject booleans and non-positive worker timeout overrides.
        value = self.timeout_seconds
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
            raise AgentTransferError("AgentTransfer.timeout_seconds must be positive when provided.")

    def _validate_retry_budget(self) -> None:
        # Invocation retries are finite and do not consume additional ledger attempts.
        value = self.max_invocation_retries
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AgentTransferError("AgentTransfer.max_invocation_retries must be non-negative.")

    @classmethod
    def _validate_report_identity(cls, report: Any, dispatch: AgentDispatch, label: str) -> None:
        # Only a task-bound AgentReport may cross the commit boundary.
        if not isinstance(report, AgentReport):
            raise AgentTransferError(f"{label} must return AgentReport.", details={"task_id": dispatch.task_id, "actual_type": type(report).__name__})
        if report.task_id != dispatch.task_id:
            raise AgentTransferError("Worker report task_id does not match its dispatch.", details={"expected_task_id": dispatch.task_id, "actual_task_id": report.task_id})

    @staticmethod
    async def maybe_await(value: Any) -> Any:
        # Developer callbacks may be synchronous or asynchronous at each extension seam.
        return await value if inspect.isawaitable(value) else value

    @classmethod
    def default_request_builder(cls, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> str:
        # Assignment-only deterministic JSON avoids leaking the full ledger into workers.
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
            normalized = cls._normalize_json_value(body)
            return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise AgentTransferError("Default worker requests require a JSON-safe payload.", details={"task_id": dispatch.task_id, "payload_type": type(dispatch.payload).__name__}) from exc

    @classmethod
    def _normalize_json_value(cls, value: Any) -> Any:
        # Only explicit JSON values cross the default transfer boundary.
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("JSON numbers must be finite.")
            return value
        if isinstance(value, (list, tuple)):
            return [cls._normalize_json_value(item) for item in value]
        if isinstance(value, Mapping):
            if not all(isinstance(key, str) for key in value):
                raise TypeError("JSON mappings require string keys.")
            return {key: cls._normalize_json_value(item) for key, item in value.items()}
        raise TypeError("Unsupported JSON payload type.")

    @classmethod
    def default_report_parser(cls, reply: AgentMessage, dispatch: AgentDispatch, ledger: TaskLedgerSnapshot) -> AgentReport:
        # Non-blank text is usable output, but it is never promoted to verified evidence.
        content = reply.content.strip()
        if content:
            evidence = TaskEvidence(source=dispatch.owner, value=content, verified=False)
            return AgentReport(task_id=dispatch.task_id, status=TaskStatus.COMPLETED, result=reply.content, evidence=(evidence,))
        blocker = TaskBlocker(code="empty_reply", message="Worker returned a blank reply.", retryable=True)
        return AgentReport(task_id=dispatch.task_id, status=TaskStatus.FAILED, blockers=(blocker,))


@dataclass(frozen=True, slots=True)
class AgentBinding:
    """Worker template paired with transfer and subtype-preserving lifecycle hooks."""

    agent: BaseAgent
    transfer: AgentTransfer = field(default_factory=AgentTransfer)
    fork_factory: WorkerForkFactory | None = None
    closer: WorkerCloser | None = None

    def __post_init__(self) -> None:
        # Validate worker lifecycle dependencies before the controller starts.
        self._validate_agent()
        self._validate_transfer()
        self._validate_callbacks()

    async def fork(self) -> BaseAgent:
        # Every run receives a distinct worker with the configured behavioral subtype.
        try:
            child = self.agent.fork(self.transfer.fork_settings) if self.fork_factory is None else self.fork_factory(self.agent, self.transfer.fork_settings)
        except AgentTransferError:
            raise
        except Exception as exc:
            raise AgentTransferError("Worker fork factory failed.", details={"worker": self.agent.name, "error_type": type(exc).__name__}) from exc
        self._validate_fork_result(child)
        return child

    async def close(self, worker: BaseAgent) -> None:
        # Compound workers may supply a custom closer; plain agents close MCP resources.
        if self.closer is None:
            await worker.close_mcp_servers()
            return
        await AgentTransfer.maybe_await(self.closer(worker))

    def fork_template(self) -> "AgentBinding":
        # Team forks clone templates synchronously so no run-local state is shared.
        child = self.agent.fork(self.transfer.fork_settings) if self.fork_factory is None else self.fork_factory(self.agent, self.transfer.fork_settings)
        self._validate_fork_result(child)
        return AgentBinding(agent=child, transfer=self.transfer, fork_factory=self.fork_factory, closer=self.closer)

    def _validate_agent(self) -> None:
        # A binding always wraps a concrete BaseAgent template.
        if not isinstance(self.agent, BaseAgent):
            raise AgentTransferError("AgentBinding.agent must be a BaseAgent instance.")

    def _validate_transfer(self) -> None:
        # Transfer policy remains an immutable AgentTransfer value.
        if not isinstance(self.transfer, AgentTransfer):
            raise AgentTransferError("AgentBinding.transfer must be AgentTransfer.", details={"actual_type": type(self.transfer).__name__})

    def _validate_callbacks(self) -> None:
        # Lifecycle hooks must be directly callable when configured.
        for label, callback in (("fork_factory", self.fork_factory), ("closer", self.closer)):
            if callback is not None and not callable(callback):
                raise AgentTransferError(f"AgentBinding.{label} must be callable when provided.", details={"actual_type": type(callback).__name__})

    def _validate_fork_result(self, child: Any) -> None:
        # Async, subtype-erasing, or identity-reusing factories violate run isolation.
        if inspect.isawaitable(child):
            if inspect.iscoroutine(child):
                child.close()
            raise AgentTransferError("Worker fork factories must synchronously return an isolated BaseAgent.", details={"worker": self.agent.name})
        if not isinstance(child, BaseAgent) or not isinstance(child, type(self.agent)):
            raise AgentTransferError("Worker fork erased or changed the configured behavioral subtype.", details={"worker": self.agent.name, "expected_type": type(self.agent).__name__, "actual_type": type(child).__name__})
        if child is self.agent:
            raise AgentTransferError("Worker fork must return an isolated agent instance, not the configured template.", details={"worker": self.agent.name})


default_request_builder: RequestBuilder = AgentTransfer.default_request_builder
default_report_parser: ReportParser = AgentTransfer.default_report_parser


__all__ = ["AgentBinding", "AgentTransfer", "default_report_parser", "default_request_builder"]
