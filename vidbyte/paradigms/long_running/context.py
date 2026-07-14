"""Context Protocol Header

Path: vidbyte/paradigms/long_running/context.py
Purpose: Build fresh, bounded, role-specific model contexts from committed run state.
Architecture: LongRunningContextBroker projects immutable state into frozen primitives;
StateVerifiedContextSource revalidates one exact result/artifact expansion; RoleAgentBundle
retains role-local load tools for authoritative audit accounting.
Exports: LongRunningContextBroker, RoleAgentBundle, StateVerifiedContextSource.
Invariants: Every role gets a new ContextManager, exact contracts are never clipped,
full procedures/results require bounded one-item loads, and inspection roles are read-only.
Do not: Reuse agent history, expose raw ledger history, trust handles without revalidation,
or let caller middleware remove the final provider-boundary trim.
Related: docs/design/long-running-paradigm.md section 6.6 and execution.py.
Tests: Existing context/tool verification plus inline smoke checks; no new tests under the
approved design-doc-no-tests workflow.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vidbyte.agents import BaseAgent
from vidbyte.context import ContextManager
from vidbyte.context.primitives import MemoryContextItem, PlanContextItem, ProgressContextItem, TaskContextItem
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.middleware.compaction import MessageHistoryCompactionMiddleware, ToolResultCompactionMiddleware
from vidbyte.paradigms.long_running.errors import LongRunningConfigurationError, LongRunningPlanError
from vidbyte.paradigms.long_running.types import LongRunningSettings, LongRunningState, LongRunningTask, LongRunningTaskStatus, TaskAttempt, TaskGraph, VerificationResult
from vidbyte.paradigms.types import AgentRoleSettings
from vidbyte.procedures import ProcedureLibrary, ProcedureMatch, ProcedureRecord
from vidbyte.prompts import Prompts
from vidbyte.tools.builtins.output_schema import AppendOutputTool, DeclareOutputSchemaTool, ExtendOutputSchemaTool, OutputSchemaBuilder
from vidbyte.tools.builtins.procedures import ProcedureLoadTool, ProcedureSearchTool
from vidbyte.tools.builtins.verified_context import VerifiedContextLoadTool, VerifiedContextRef, VerifiedContextSource
from vidbyte.tools.toolsets import ParadigmMinimalToolset
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolPermission


@dataclass(frozen=True, slots=True)
class RoleAgentBundle:
    """Fresh role agent plus authoritative role-local expansion records."""

    agent: BaseAgent
    procedure_load: ProcedureLoadTool | None = None
    verified_context_load: VerifiedContextLoadTool | None = None


class LongRunningContextManager(ContextManager):
    """Context manager whose frozen registry projection survives BaseAgent merging."""

    def items(self) -> tuple[Any, ...]:
        # Project managed primitives as ordinary immutable items for each model iteration.
        return (*super().items(), *(item for _, item in self.registry_items()))


class LongRunningRoleAgent(BaseAgent):
    """BaseAgent adapter that honors the shared role's optional injected runner."""

    def __init__(self, *args: Any, configured_runner: object | None = None, **kwargs: Any) -> None:
        # Preserve current BaseAgent construction while retaining one explicit runner seam.
        self._configured_runner = configured_runner
        super().__init__(*args, **kwargs)

    def _runner_for_model(self) -> tuple[object, str]:
        # Use the caller's role runner when supplied, otherwise normal provider inference.
        if self._configured_runner is not None:
            return self._configured_runner, "text"
        return super()._runner_for_model()


class StateVerifiedContextSource(VerifiedContextSource):
    """Resolve advertised handles from one committed, currently verified state."""

    def __init__(self, state: LongRunningState, workspace_root: str | Path) -> None:
        # Pin resolution to one committed state and a contained artifact root.
        self.state = state
        self.workspace_root = Path(workspace_root).resolve()

    def refs(self, allowed_task_ids: Sequence[str]) -> tuple[VerifiedContextRef, ...]:
        # Advertise result and artifact handles only for currently verified tasks.
        allowed = set(allowed_task_ids)
        verified = {item.task_id for item in self.state.task_states if item.status is LongRunningTaskStatus.VERIFIED}
        refs: list[VerifiedContextRef] = []
        selected = {item.verified_result_id for item in self.state.task_states if item.status is LongRunningTaskStatus.VERIFIED and item.verified_result_id}
        for result in self.state.task_results:
            if result.result_id not in selected:
                continue
            if result.task_id not in allowed or result.task_id not in verified:
                continue
            refs.append(VerifiedContextRef("result", self.state.run_id, result.task_id, result.result_id, result.content_hash, result.summary))
            refs.extend(VerifiedContextRef("artifact", self.state.run_id, result.task_id, artifact.artifact_id, artifact.content_hash, artifact.summary) for artifact in result.artifacts)
        return tuple(refs)

    def load_verified(self, ref: VerifiedContextRef, *, allowed_task_ids: tuple[str, ...]) -> str:
        # Recheck run, status, allowlist, identity, and content hash before expansion.
        if ref.run_id != self.state.run_id or ref.task_id not in allowed_task_ids:
            raise ValueError("Verified context reference is outside the active run/task scope.")
        task_state = next((item for item in self.state.task_states if item.task_id == ref.task_id), None)
        if task_state is None or task_state.status is not LongRunningTaskStatus.VERIFIED:
            raise ValueError("Verified context source task is no longer VERIFIED.")
        if not task_state.verified_result_id:
            raise ValueError("Verified context source task does not identify a current result.")
        result = next((item for item in self.state.task_results if item.result_id == task_state.verified_result_id), None)
        if result is None:
            raise ValueError("Verified context source result is missing from committed state.")
        if ref.kind == "result" and ref.item_id == result.result_id:
            content = self._result_content(result.summary, result.detail, result.evidence)
            if ref.content_hash != result.content_hash:
                raise ValueError("Verified result handle fingerprint no longer matches committed state.")
            return content
        artifact = next((item for item in result.artifacts if item.artifact_id == ref.item_id), None)
        if ref.kind != "artifact" or artifact is None or artifact.content_hash != ref.content_hash:
            raise ValueError("Verified artifact handle does not match a committed artifact.")
        return self._artifact_content(artifact.uri, artifact.content_hash)

    @staticmethod
    def _result_content(summary: str, detail: str, evidence: Sequence[str]) -> str:
        # Render exact committed result fields without ledger or transcript expansion.
        return "\n".join((f"Summary: {summary}", "Detail:", detail, "Evidence:", *(f"- {item}" for item in evidence)))

    def _artifact_content(self, uri: str, content_hash: str) -> str:
        # Read only contained local files and verify bytes against the advertised hash.
        raw_path = Path(uri[7:]) if uri.startswith("file://") else Path(uri)
        path = raw_path if raw_path.is_absolute() else self.workspace_root / raw_path
        resolved = path.resolve()
        if resolved != self.workspace_root and self.workspace_root not in resolved.parents:
            raise ValueError("Verified artifact path escapes the configured workspace root.")
        data = resolved.read_bytes()
        if hashlib.sha256(data).hexdigest() != content_hash:
            raise ValueError("Verified artifact bytes do not match the committed content hash.")
        return data.decode("utf-8")


class LongRunningContextBroker:
    """Construct fresh role agents from compact projections of committed state."""

    _PROMPTS = {
        "planner": Prompt.LONG_RUNNING_PLANNER,
        "worker": Prompt.LONG_RUNNING_WORKER,
        "repairer": Prompt.LONG_RUNNING_REPAIR,
        "verifier": Prompt.LONG_RUNNING_VERIFIER,
        "curator": Prompt.LONG_RUNNING_PROCEDURE_CURATOR,
        "procedure_verifier": Prompt.LONG_RUNNING_PROCEDURE_VERIFIER,
        "synthesizer": Prompt.LONG_RUNNING_SYNTHESIZER,
        "auditor": Prompt.LONG_RUNNING_AUDITOR,
    }

    def __init__(self, settings: LongRunningSettings, procedure_library: ProcedureLibrary) -> None:
        # Bind immutable bounds and durable procedure lookup; role state remains per-call.
        self.settings = settings
        self.procedure_library = procedure_library
        self.prompts = Prompts()

    def build_planner(self, state: LongRunningState, builder: OutputSchemaBuilder, *, validation_errors: Sequence[str] = ()) -> BaseAgent:
        # Build a fresh read-only planner with root-relevant procedure cards.
        matches = self._search(state.contract.original_prompt)
        manager = self._manager(state, None, matches, validation_errors=validation_errors)
        return self._build_bundle("planner", state, manager, builder=builder, matches=matches).agent

    def build_worker(self, state: LongRunningState, task: LongRunningTask, matches: Sequence[ProcedureMatch], builder: OutputSchemaBuilder) -> BaseAgent:
        # Build the public worker surface while keeping bundle access available internally.
        return self.build_worker_bundle(state, task, matches, builder).agent

    def build_worker_bundle(self, state: LongRunningState, task: LongRunningTask, matches: Sequence[ProcedureMatch], builder: OutputSchemaBuilder) -> RoleAgentBundle:
        # Build one fresh worker with dependency expansion and optional side-effect tools.
        manager = self._manager(state, task, matches)
        return self._build_bundle("worker", state, manager, builder=builder, task=task, matches=matches)

    def build_repairer(self, state: LongRunningState, task: LongRunningTask, latest_attempt: TaskAttempt, verification: VerificationResult, matches: Sequence[ProcedureMatch], builder: OutputSchemaBuilder) -> BaseAgent:
        # Build the public repair surface with exact bounded failure evidence.
        return self.build_repairer_bundle(state, task, latest_attempt, verification, matches, builder).agent

    def build_repairer_bundle(self, state: LongRunningState, task: LongRunningTask, latest_attempt: TaskAttempt, verification: VerificationResult, matches: Sequence[ProcedureMatch], builder: OutputSchemaBuilder) -> RoleAgentBundle:
        # Build one fresh repairer without inheriting the failed agent conversation.
        repair = self._repair_evidence(latest_attempt, verification)
        manager = self._manager(state, task, matches, repair_evidence=repair)
        return self._build_bundle("repairer", state, manager, builder=builder, task=task, matches=matches)

    def build_verifier(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, builder: OutputSchemaBuilder) -> BaseAgent:
        # Build a fresh read-only verifier from the public attempt record.
        manager = self._manager(state, task, (), repair_evidence=self._attempt_evidence(attempt))
        return self._build_bundle("verifier", state, manager, builder=builder, task=task).agent

    def build_procedure_verifier(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, candidate: ProcedureRecord, builder: OutputSchemaBuilder) -> BaseAgent:
        # Build an inspection-only fidelity role pinned to one staged fingerprint.
        manager = self._manager(state, task, (), repair_evidence=self._candidate_evidence(attempt, candidate))
        return self._build_bundle("procedure_verifier", state, manager, builder=builder, task=task).agent

    def build_auditor(self, state: LongRunningState, builder: OutputSchemaBuilder, latest: VerificationResult | None = None) -> BaseAgent:
        # Build a fresh global auditor with handles for all valid verified results.
        evidence = "" if latest is None else self._verification_text(latest)
        manager = self._manager(state, None, (), repair_evidence=evidence)
        return self._build_bundle("auditor", state, manager, builder=builder, allow_all_verified=True).agent

    def build_synthesizer(self, state: LongRunningState, builder: OutputSchemaBuilder, critique: VerificationResult | None = None) -> BaseAgent:
        # Build a fresh finalizer over verified result summaries and optional prior critique.
        evidence = "" if critique is None else self._verification_text(critique)
        manager = self._manager(state, None, (), repair_evidence=evidence)
        return self._build_bundle("synthesizer", state, manager, builder=builder, allow_all_verified=True).agent

    def build_curator_bundle(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, builder: OutputSchemaBuilder, extra_tools: Sequence[object]) -> RoleAgentBundle:
        # Build a fresh curator; its caller supplies the constructor-bound staging tool.
        manager = self._manager(state, task, (), repair_evidence=self._attempt_evidence(attempt))
        return self._build_bundle("curator", state, manager, builder=builder, task=task, extra_tools=extra_tools)

    def build_role(self, role: str, state: LongRunningState, manager: ContextManager, builder: OutputSchemaBuilder | None = None, extra_tools: Sequence[object] = ()) -> BaseAgent:
        # Expose the generic fresh-agent factory for advanced orchestration roles.
        return self._build_bundle(role, state, manager, builder=builder, extra_tools=extra_tools).agent

    def _build_bundle(self, role: str, state: LongRunningState, manager: ContextManager, *, builder: OutputSchemaBuilder | None = None, task: LongRunningTask | None = None, matches: Sequence[ProcedureMatch] = (), extra_tools: Sequence[object] = (), allow_all_verified: bool = False) -> RoleAgentBundle:
        # Compose role-local tools, validate permissions/names, and append mandatory guards.
        role_settings = self._role_settings(role)
        if role in {"planner", "verifier", "curator", "procedure_verifier", "auditor", "synthesizer"}:
            invalid_caller = tuple(self._tool_name(tool) for tool in role_settings.tools if self._permission(tool) is not ToolPermission.READ)
            if invalid_caller:
                raise LongRunningConfigurationError("Inspection-role caller tools must declare READ permission.", details={"role": role, "tools": invalid_caller})
        base_tools = list(self._minimal_tools(role))
        base_tools.extend(role_settings.tools)
        available_names = tuple(self._tool_name(tool) for tool in base_tools)
        procedure_search = ProcedureSearchTool(self.procedure_library, namespace=self.settings.procedure_namespace, environment_fingerprint=self.settings.environment_fingerprint, available_tools=available_names, max_results=self.settings.procedure_search_limit)
        procedure_load: ProcedureLoadTool | None = None
        if role in {"planner", "worker", "repairer"}:
            procedure_load = ProcedureLoadTool(self.procedure_library, manager, namespace=self.settings.procedure_namespace, environment_fingerprint=self.settings.environment_fingerprint, available_tools=available_names, max_body_chars=self.settings.max_procedure_body_chars, max_loaded_records=self.settings.max_loaded_procedures_per_role, max_total_loaded_chars=self.settings.max_loaded_procedure_chars_per_role)
            base_tools.extend((procedure_search, procedure_load))
        verified_load: VerifiedContextLoadTool | None = None
        allowed_ids = self._allowed_task_ids(state, task, allow_all_verified)
        if role in {"worker", "repairer", "auditor", "synthesizer", "planner"} and allowed_ids:
            source = StateVerifiedContextSource(state, self.settings.default_tool_root)
            refs = source.refs(allowed_ids)
            verified_load = VerifiedContextLoadTool(source, manager, allowed_task_ids=allowed_ids, available_refs=refs, max_loaded_items=self.settings.max_loaded_verified_context_items_per_role, max_total_loaded_chars=self.settings.max_loaded_verified_context_chars_per_role, max_item_chars=max(self.settings.max_task_result_detail_chars, self.settings.max_artifact_excerpt_chars))
            base_tools.append(verified_load)
        base_tools.extend(extra_tools)
        if builder is not None:
            base_tools.extend((DeclareOutputSchemaTool(builder), ExtendOutputSchemaTool(builder), AppendOutputTool(builder)))
        tools = self._deduplicate_tools(base_tools)
        if role in {"planner", "verifier", "procedure_verifier", "auditor", "synthesizer"}:
            self._require_read_only(role, tools)
        middleware = (*role_settings.middleware, ToolResultCompactionMiddleware.truncate(self.settings.max_visible_tool_result_chars), MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_messages=self.settings.max_role_messages, max_tokens=self.settings.max_visible_context_tokens, max_chars=self.settings.max_role_history_chars))
        options = self._agent_options(role_settings)
        if role in {"worker", "repairer", "curator"} and any(self._permission(tool) not in {ToolPermission.READ, ToolPermission.SAFE} for tool in tools) and "permission_policy" not in options:
            options["permission_policy"] = PermissionPolicy.allow_all()
        agent = LongRunningRoleAgent(name=role_settings.name, system_prompt=role_settings.system_prompt or self.prompts.get(self._PROMPTS[role]), configured_runner=role_settings.runner, tools=tools, middleware=middleware, api_key=role_settings.api_key, provider=role_settings.provider, model_name=role_settings.model_name, temperature=role_settings.temperature, context_manager=manager, metadata={"paradigm": "long_running", "role": role, "run_id": state.run_id, "graph_version": state.graph.version, "task_id": "" if task is None else task.task_id, "attempt_number": 0 if task is None else self._attempt_number(state, task.task_id)}, **options)
        return RoleAgentBundle(agent, procedure_load, verified_load)

    def _manager(self, state: LongRunningState, task: LongRunningTask | None, matches: Sequence[ProcedureMatch], *, validation_errors: Sequence[str] = (), repair_evidence: str = "") -> ContextManager:
        # Project exact mandatory inputs and compact optional cards into a new manager.
        contract_text = self._contract_text(state)
        if len(contract_text) > self.settings.max_contract_chars:
            raise LongRunningConfigurationError("Exact root contract exceeds max_contract_chars; increase the bound explicitly.", run_id=state.run_id, details={"contract_chars": len(contract_text), "maximum": self.settings.max_contract_chars})
        if task is not None and len(self._task_text(task)) > self.settings.max_task_instructions_chars:
            raise LongRunningConfigurationError("Exact current task exceeds max_task_instructions_chars; revise the plan or increase the bound.", run_id=state.run_id, task_id=task.task_id)
        manager = LongRunningContextManager(metadata={"run_id": state.run_id, "graph_version": state.graph.version})
        manager.place_after_system_prompt(TaskContextItem(goal=contract_text if task is None else f"{contract_text}\n\nCurrent task:\n{self._task_text(task)}", status=state.status.value, deterministic_checks=state.contract.success_criteria if task is None else task.acceptance_criteria, primitive_id="long-running:contract", primitive_frozen=True))
        steps = tuple(f"{item.task_id}: {item.title} [{self._status(state, item.task_id).value}]" for item in state.graph.tasks)
        current_index = next((index for index, item in enumerate(state.graph.tasks) if task is not None and item.task_id == task.task_id), 0)
        manager.place_after_tools(PlanContextItem(steps=steps, current_step=current_index, status=state.status.value, primitive_id="long-running:plan", primitive_frozen=True))
        refs = StateVerifiedContextSource(state, self.settings.default_tool_root).refs(self._allowed_task_ids(state, task, task is None))
        manager.place_after_tools(ProgressContextItem(completed_tasks=tuple(f"{result.task_id}: {self._clip(result.summary, self.settings.max_dependency_summary_chars)}" for result in state.task_results if self._status(state, result.task_id) is LongRunningTaskStatus.VERIFIED), decisions=tuple(f"verified-context {ref.handle()}: {self._clip(ref.summary, self.settings.max_dependency_summary_chars)}" for ref in refs), errors=tuple(self._clip(item, self.settings.max_latest_evidence_chars) for item in (*validation_errors, repair_evidence) if item), next_steps=(f"cycle {state.cycle_count}/{self.settings.max_cycles}",), primitive_id="long-running:progress", primitive_frozen=True))
        cards = self._cards(matches)
        if cards:
            manager.place_after_tools(MemoryContextItem(content=cards, source="verified-procedure-index", metadata={"untrusted_reference": True}, primitive_id="long-running:procedure-cards", primitive_frozen=True))
        visible = manager.render_primitives_zone()
        if len(visible) > self.settings.max_context_capsule_chars and cards:
            manager.remove_by_id("long-running:procedure-cards")
            visible = manager.render_primitives_zone()
        if len(visible) > self.settings.max_context_capsule_chars:
            raise LongRunningConfigurationError("Mandatory role context exceeds max_context_capsule_chars; exact inputs were not clipped.", run_id=state.run_id, task_id="" if task is None else task.task_id, details={"capsule_chars": len(visible), "maximum": self.settings.max_context_capsule_chars})
        return manager

    def _minimal_tools(self, role: str) -> tuple[object, ...]:
        # Build the universal role toolset with side effects enabled only for workers.
        if not self.settings.include_minimal_toolset:
            return ()
        mutating = role in {"worker", "repairer"}
        return ParadigmMinimalToolset(self.settings.default_tool_root, include_execution=mutating and self.settings.worker_include_execution, include_write=mutating and self.settings.worker_include_write).all()

    def _search(self, query: str) -> tuple[ProcedureMatch, ...]:
        # Retrieve cards using the same namespace/environment constraints as load tools.
        return self.procedure_library.search(query, namespace=self.settings.procedure_namespace, environment_fingerprint=self.settings.environment_fingerprint, available_tools=(), limit=self.settings.procedure_search_limit)

    def available_tool_names(self, role: str) -> tuple[str, ...]:
        # Describe effective caller/minimal tools for compatibility retrieval and evidence.
        settings = self._role_settings(role)
        return tuple(dict.fromkeys(self._tool_name(tool) for tool in (*self._minimal_tools(role), *settings.tools)))

    def ensure_task_fits(self, state: LongRunningState, task: LongRunningTask) -> None:
        # Reject oversized exact task definitions immediately after planning.
        task_chars = len(self._task_text(task))
        if task_chars > self.settings.max_task_instructions_chars:
            raise LongRunningPlanError("Planned task exceeds max_task_instructions_chars; exact task text was not clipped.", run_id=state.run_id, task_id=task.task_id, details={"task_chars": task_chars, "maximum": self.settings.max_task_instructions_chars})

    def ensure_graph_fits(self, state: LongRunningState, graph: TaskGraph) -> None:
        # Enforce per-task and aggregate plan-summary ceilings before graph commit.
        for task in graph.tasks:
            self.ensure_task_fits(state, task)
        plan_chars = sum(len(task.task_id) + len(task.title) + 4 for task in graph.tasks)
        if plan_chars > self.settings.max_plan_summary_chars:
            raise LongRunningPlanError("Planned graph summary exceeds max_plan_summary_chars; exact titles were not clipped.", run_id=state.run_id, details={"plan_chars": plan_chars, "maximum": self.settings.max_plan_summary_chars})

    def _cards(self, matches: Sequence[ProcedureMatch]) -> str:
        # Render stable handles and individually bounded summaries, never full bodies.
        cards: list[str] = []
        for match in tuple(matches)[:self.settings.procedure_search_limit]:
            ref = match.summary.ref
            card = json.dumps({"ref": {"namespace": ref.namespace, "procedure_id": ref.procedure_id, "version": ref.version, "content_fingerprint": ref.content_fingerprint}, "title": match.summary.title, "summary": match.summary.summary, "applicability": match.summary.applicability, "score": match.score}, ensure_ascii=False, sort_keys=True)
            cards.append(self._clip(card, self.settings.max_procedure_card_chars))
        return "\n".join(cards)

    def _allowed_task_ids(self, state: LongRunningState, task: LongRunningTask | None, all_verified: bool) -> tuple[str, ...]:
        # Limit workers to transitive dependencies and global roles to current verified work.
        verified = {item.task_id for item in state.task_states if item.status is LongRunningTaskStatus.VERIFIED}
        if all_verified or task is None:
            return tuple(item.task_id for item in state.graph.tasks if item.task_id in verified)
        dependencies = set(task.dependencies)
        changed = True
        while changed:
            changed = False
            for item in state.graph.tasks:
                if item.task_id in dependencies:
                    before = len(dependencies)
                    dependencies.update(item.dependencies)
                    changed = changed or len(dependencies) != before
        return tuple(item.task_id for item in state.graph.tasks if item.task_id in dependencies and item.task_id in verified)

    def _role_settings(self, role: str) -> AgentRoleSettings:
        # Resolve only declared role names so typos cannot inherit broad defaults.
        try:
            return getattr(self.settings, role)
        except AttributeError as exc:
            raise LongRunningConfigurationError(f"Unknown long-running role: {role!r}.") from exc

    @staticmethod
    def _agent_options(settings: AgentRoleSettings) -> dict[str, Any]:
        # Reject constructor collisions before they become ambiguous TypeErrors.
        reserved = {"name", "system_prompt", "tools", "middleware", "api_key", "provider", "model_name", "temperature", "context_manager", "metadata"}
        collisions = sorted(reserved.intersection(settings.agent_options))
        if collisions:
            raise LongRunningConfigurationError("Role agent_options contain reserved BaseAgent fields.", details={"fields": collisions})
        return dict(settings.agent_options)

    @staticmethod
    def _deduplicate_tools(tools: Sequence[object]) -> tuple[object, ...]:
        # Keep identical instances once and reject distinct tools claiming one name.
        by_name: dict[str, object] = {}
        for tool in tools:
            name = LongRunningContextBroker._tool_name(tool)
            prior = by_name.get(name)
            if prior is not None and prior is not tool:
                raise LongRunningConfigurationError("Distinct tools expose the same model-visible name.", details={"tool_name": name})
            by_name[name] = tool
        return tuple(by_name.values())

    @staticmethod
    def _require_read_only(role: str, tools: Sequence[object]) -> None:
        # Allow SAFE internal schema tools and READ inspection tools only.
        invalid = tuple(LongRunningContextBroker._tool_name(tool) for tool in tools if LongRunningContextBroker._permission(tool) not in {ToolPermission.READ, ToolPermission.SAFE})
        if invalid:
            raise LongRunningConfigurationError("Inspection role received non-read tools.", details={"role": role, "tools": invalid})

    @staticmethod
    def _permission(tool: object) -> ToolPermission:
        # Fail closed when a configured tool does not expose a valid ToolSpec permission.
        spec = getattr(tool, "spec", None)
        if not callable(spec):
            raise LongRunningConfigurationError("Configured tool does not expose spec().", details={"tool_type": type(tool).__name__})
        permission = getattr(spec(), "permission", None)
        if not isinstance(permission, ToolPermission):
            raise LongRunningConfigurationError("Configured tool has an unknown permission.", details={"tool_type": type(tool).__name__})
        return permission

    @staticmethod
    def _tool_name(tool: object) -> str:
        # Read the canonical model-visible name through ToolSpec.
        spec = getattr(tool, "spec", None)
        if not callable(spec):
            raise LongRunningConfigurationError("Configured tool does not expose spec().", details={"tool_type": type(tool).__name__})
        return str(spec().name)

    @staticmethod
    def _status(state: LongRunningState, task_id: str) -> LongRunningTaskStatus:
        # Join definition ids to compact successor-state records.
        item = next((candidate for candidate in state.task_states if candidate.task_id == task_id), None)
        return LongRunningTaskStatus.PENDING if item is None else item.status

    @staticmethod
    def _attempt_number(state: LongRunningState, task_id: str) -> int:
        # Advertise the next bounded attempt number in role metadata.
        item = next((candidate for candidate in state.task_states if candidate.task_id == task_id), None)
        return 1 if item is None else item.attempt_count + 1

    @staticmethod
    def _contract_text(state: LongRunningState) -> str:
        # Preserve the exact prompt and caller criterion text inside explicit data tags.
        return "\n".join(("<exact_root_contract>", state.contract.original_prompt, "Success criteria:", *(f"- {item}" for item in state.contract.success_criteria), "Invariants:", *(f"- {item}" for item in state.contract.invariants), "Non-goals:", *(f"- {item}" for item in state.contract.non_goals), "</exact_root_contract>"))

    @staticmethod
    def _task_text(task: LongRunningTask) -> str:
        # Render immutable current-task fields without prior conversational reasoning.
        return "\n".join((f"ID: {task.task_id}", f"Title: {task.title}", "Instructions:", task.instructions, "Acceptance criteria:", *(f"- {item}" for item in task.acceptance_criteria), "Expected artifacts:", *(f"- {item}" for item in task.expected_artifacts), "Owned paths:", *(f"- {item}" for item in task.owned_paths), "Read-only paths:", *(f"- {item}" for item in task.read_only_paths)))

    @staticmethod
    def _attempt_evidence(attempt: TaskAttempt) -> str:
        # Render the prior public attempt, not hidden chain-of-thought or raw full history.
        return "\n".join((f"Attempt {attempt.attempt_id}", f"Strategy: {attempt.strategy}", f"Summary: {attempt.summary}", "Evidence:", *(f"- {item}" for item in attempt.evidence), "Blockers:", *(f"- {item}" for item in attempt.blockers)))

    @classmethod
    def _repair_evidence(cls, attempt: TaskAttempt, verification: VerificationResult) -> str:
        # Pair the last public attempt with exact verifier repair instructions/signature.
        return "\n".join((cls._attempt_evidence(attempt), cls._verification_text(verification)))

    @staticmethod
    def _verification_text(verification: VerificationResult) -> str:
        # Render bounded verification outputs for repair/global review.
        return "\n".join((f"Verification passed: {verification.passed}", f"Failure signature: {verification.failure_signature}", "Violations:", *(f"- {item}" for item in verification.violations), "Repair instructions:", *(f"- {item}" for item in verification.repair_instructions)))

    @classmethod
    def _candidate_evidence(cls, attempt: TaskAttempt, candidate: ProcedureRecord) -> str:
        # Pin fidelity review to one exact candidate fingerprint and source attempt.
        return "\n".join((cls._attempt_evidence(attempt), f"Candidate: {candidate.procedure_id} v{candidate.version}", f"Fingerprint: {candidate.content_fingerprint}", f"Title: {candidate.title}", f"Summary: {candidate.summary}", "Body:", candidate.body))

    @staticmethod
    def _clip(value: str, maximum: int) -> str:
        # Deterministically bound optional summaries while making omission visible.
        text = str(value)
        return text if len(text) <= maximum else text[:maximum] + "…[bounded]"


__all__ = ["LongRunningContextBroker", "RoleAgentBundle", "StateVerifiedContextSource"]
