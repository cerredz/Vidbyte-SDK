"""Context Protocol Header

Path: vidbyte/paradigms/long_running/paradigm.py
Purpose: Expose the public construction, start, and resume API for durable execution.
Architecture: LongRunningParadigm validates authority/tool policy once and delegates
each run to LongRunningController over injected procedure and ledger stores.
Exports: LongRunningParadigm.
Invariants: Execution-critical inputs use typed option objects, unknown kwargs fail,
and non-read worker tools require isolation or an explicit unsafe construction opt-in.
Do not: Hide per-run overrides in loose kwargs or silently create write authority.
Related: docs/design/long-running-paradigm.md section 6.10 and controller.py.
Tests: Existing paradigm import/sync-bridge verification; no new tests under the
approved design-doc-no-tests workflow.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from vidbyte.paradigms.base import ParadigmHarness
from vidbyte.paradigms.long_running.controller import LongRunningController
from vidbyte.paradigms.long_running.errors import LongRunningConfigurationError
from vidbyte.paradigms.long_running.execution import AttemptIsolator
from vidbyte.paradigms.long_running.ledger import InMemoryRunLedgerStore, RunLedgerStore
from vidbyte.paradigms.long_running.types import LongRunningResult, LongRunningResumeOptions, LongRunningRunOptions, LongRunningSettings
from vidbyte.paradigms.long_running.verification import ProcedureValidator, TaskValidator
from vidbyte.procedures import InMemoryProcedureStore, ProcedureLibrary
from vidbyte.tools.types import ToolPermission


class LongRunningParadigm(ParadigmHarness):
    """Durable dependency-aware harness with verified reusable procedure learning."""

    def __init__(self, settings: LongRunningSettings | None = None, *, procedure_library: ProcedureLibrary | None = None, ledger_store: RunLedgerStore | None = None, validators: Sequence[TaskValidator] = (), procedure_validators: Sequence[ProcedureValidator] = (), attempt_isolator: AttemptIsolator | None = None, **kwargs: Any) -> None:
        # Resolve immutable settings, default stores, and construction-time safety policy.
        try:
            self.settings = settings.with_overrides(**kwargs) if settings is not None else LongRunningSettings(**kwargs)
        except (TypeError, ValueError) as exc:
            raise LongRunningConfigurationError("Long-running settings are invalid.", details={"error_type": type(exc).__name__, "message": str(exc)}) from exc
        self.procedure_library = procedure_library or ProcedureLibrary(InMemoryProcedureStore())
        self.ledger_store = ledger_store or InMemoryRunLedgerStore()
        self.validators = tuple(validators)
        self.procedure_validators = tuple(procedure_validators)
        self.attempt_isolator = attempt_isolator
        self._validate_side_effect_policy()
        self._controller = LongRunningController(self.settings, self.procedure_library, self.ledger_store, validators=self.validators, procedure_validators=self.procedure_validators, attempt_isolator=self.attempt_isolator)

    async def arun(self, prompt: str, *, run_options: LongRunningRunOptions | None = None, **options: Any) -> LongRunningResult:
        # Start one new run from typed immutable contract inputs only.
        self._reject_options(options, operation="arun")
        if run_options is not None and not isinstance(run_options, LongRunningRunOptions):
            raise LongRunningConfigurationError("run_options must be a LongRunningRunOptions instance.")
        return await self._controller.start(prompt, run_options or LongRunningRunOptions())

    async def aresume(self, run_id: str, *, resume_options: LongRunningResumeOptions | None = None, **options: Any) -> LongRunningResult:
        # Continue one durable non-terminal run from its latest validated ledger head.
        self._reject_options(options, operation="aresume")
        if resume_options is not None and not isinstance(resume_options, LongRunningResumeOptions):
            raise LongRunningConfigurationError("resume_options must be a LongRunningResumeOptions instance.", run_id=run_id)
        return await self._controller.resume(run_id, resume_options or LongRunningResumeOptions())

    def resume(self, run_id: str, *, resume_options: LongRunningResumeOptions | None = None, **options: Any) -> LongRunningResult:
        # Bridge durable continuation for synchronous callers outside active event loops.
        self._reject_options(options, operation="resume")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aresume(run_id, resume_options=resume_options))
        raise LongRunningConfigurationError("LongRunningParadigm.resume() cannot run inside an active event loop; use await aresume().", run_id=run_id)

    def _validate_side_effect_policy(self) -> None:
        # Reject effective non-read tools without isolation unless unsafe mode is explicit.
        side_effects = self.settings.worker_include_execution or self.settings.worker_include_write
        names: list[str] = []
        for role in (self.settings.worker, self.settings.repairer):
            for tool in role.tools:
                spec = getattr(tool, "spec", None)
                if not callable(spec):
                    side_effects = True
                    names.append(type(tool).__name__)
                    continue
                tool_spec = spec()
                if tool_spec.permission not in {ToolPermission.READ, ToolPermission.SAFE}:
                    side_effects = True
                    names.append(tool_spec.name)
        if side_effects and self.attempt_isolator is None and not self.settings.unsafe_allow_unisolated_side_effects:
            raise LongRunningConfigurationError("Non-read worker/repair tools require attempt_isolator= or unsafe_allow_unisolated_side_effects=True.", details={"configured_tools": tuple(names), "worker_include_execution": self.settings.worker_include_execution, "worker_include_write": self.settings.worker_include_write})

    @staticmethod
    def _reject_options(options: dict[str, Any], *, operation: str) -> None:
        # Prevent untyped per-run flags from changing resumable behavior invisibly.
        if options:
            raise LongRunningConfigurationError("Unknown untyped long-running options; use the typed option object.", details={"operation": operation, "option_keys": tuple(sorted(options))})


__all__ = ["LongRunningParadigm"]
