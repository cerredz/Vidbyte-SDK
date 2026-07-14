"""Context Protocol Header

Path: vidbyte/tools/builtins/procedures/stage.py
Purpose: Let a curator stage bounded candidate content without verification authority.
Architecture: StageProcedureTool binds provenance and evidence allowlists to one
successful attempt, derives an idempotent operation id, and calls ProcedureLibrary.stage.
Exports: StageProcedureTool.
Invariants: Permission is WRITE; status/version/verification cannot be model supplied;
evidence ids must come from the successful attempt allowlist.
Do not: Promote, reject, retire, or claim that staged candidates are reusable.
Related: vidbyte/procedures/library.py and long_running/verification.py.
Tests: Existing tool verification and inline smoke checks only under no-tests approval.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.procedures import ProcedureCandidate, ProcedureLibrary, ProcedureRef
from vidbyte.procedures.serialization import ProcedureIdentity
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class StageProcedureTool(BaseTool):
    """Stage a non-retrievable procedure candidate for trusted verification."""

    def __init__(self, library: ProcedureLibrary, *, run_id: str, task_id: str, attempt_id: str, namespace: str, environment_fingerprint: str = "", max_body_chars: int = 20000, allowed_evidence_event_ids: Sequence[str] = ()) -> None:
        # Bind immutable provenance and evidence scope to this curator role instance.
        if max_body_chars < 1:
            raise ValueError("StageProcedureTool.max_body_chars must be positive.")
        self.library = library
        self.run_id = run_id
        self.task_id = task_id
        self.attempt_id = attempt_id
        self.namespace = namespace
        self.environment_fingerprint = environment_fingerprint
        self.max_body_chars = max_body_chars
        self.allowed_evidence_event_ids = frozenset(str(item) for item in allowed_evidence_event_ids)
        self._staged: list[ProcedureRef] = []

    @property
    def staged_refs(self) -> tuple[ProcedureRef, ...]:
        # Expose exact successful candidate handles to the trusted controller.
        return tuple(self._staged)

    def spec(self) -> ToolSpec:
        # Declare candidate content only; lifecycle and verification fields are absent.
        return ToolSpec(
            name="procedure_stage",
            description="Stage a reusable procedure candidate for independent verification. Staging does not verify or promote it.",
            permission=ToolPermission.WRITE,
            parameters=(
                ToolParameter("title", "string", "Short reusable procedure title."),
                ToolParameter("summary", "string", "Compact retrieval summary."),
                ToolParameter("body", "string", "Full bounded procedure body."),
                ToolParameter("applicability", "array", "Situations where the procedure applies."),
                ToolParameter("preconditions", "array", "Prerequisites that must hold."),
                ToolParameter("expected_outcomes", "array", "Observable successful outcomes."),
                ToolParameter("tags", "array", "Optional retrieval tags.", required=False),
                ToolParameter("required_tools", "array", "Required tool names.", required=False),
                ToolParameter("source_evidence_event_ids", "array", "Successful-attempt evidence event ids.", required=False),
                ToolParameter("proposed_procedure_id", "string", "Existing stable id for an intentional revision.", required=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate evidence scope, derive replay identity, and stage candidate-only content.
        try:
            body = str(call.arguments["body"])
            if len(body) > self.max_body_chars:
                raise ValueError(f"Procedure body has {len(body)} characters; maximum is {self.max_body_chars}.")
            evidence_ids = self._text_tuple(call.arguments.get("source_evidence_event_ids", ()))
            unknown = tuple(item for item in evidence_ids if item not in self.allowed_evidence_event_ids)
            if unknown:
                raise ValueError(f"Procedure evidence ids are outside the successful attempt allowlist: {', '.join(unknown)}")
            candidate = ProcedureCandidate(
                namespace=self.namespace, title=str(call.arguments["title"]), summary=str(call.arguments["summary"]), body=body,
                applicability=self._text_tuple(call.arguments["applicability"]),
                preconditions=self._text_tuple(call.arguments["preconditions"]),
                expected_outcomes=self._text_tuple(call.arguments["expected_outcomes"]),
                tags=self._text_tuple(call.arguments.get("tags", ())),
                required_tools=self._text_tuple(call.arguments.get("required_tools", ())),
                environment_fingerprint=self.environment_fingerprint,
                source_run_id=self.run_id, source_task_id=self.task_id, source_attempt_id=self.attempt_id,
                source_evidence_event_ids=evidence_ids,
                proposed_procedure_id=str(call.arguments.get("proposed_procedure_id", "")).strip() or None,
            )
            fingerprint = ProcedureIdentity.content_fingerprint(candidate)
            marker = candidate.proposed_procedure_id or "new"
            operation_id = ProcedureIdentity.deterministic_id("stage", self.namespace, self.run_id, self.task_id, self.attempt_id, marker, fingerprint)
            record = self.library.stage(candidate, operation_id=operation_id)
            if record.ref not in self._staged:
                self._staged.append(record.ref)
            return ToolResult.success(
                self.name,
                f"Staged candidate {record.procedure_id} v{record.version}; it is not verified or retrievable until trusted promotion succeeds.",
                metadata={"operation_id": operation_id, "procedure_ref": (record.namespace, record.procedure_id, record.version, record.content_fingerprint), "status": record.status.value},
            )
        except Exception as exc:
            return ToolResult.error(self.name, str(exc), metadata={"error_type": exc.__class__.__name__, "task_id": self.task_id, "attempt_id": self.attempt_id})

    @staticmethod
    def _text_tuple(value: object) -> tuple[str, ...]:
        # Normalize model arrays and tolerate one scalar as one explicit item.
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return tuple(text for item in value if (text := str(item).strip()))
        text = str(value).strip()
        return (text,) if text else ()


__all__ = ["StageProcedureTool"]
