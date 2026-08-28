"""FILE: vidbyte/workflows/validation.py
PURPOSE: Adapts deterministic checks, eval graders, and verifier agents to one gate protocol.
ROLE IN CODEBASE: Constructed by SDK users and invoked only by machine.py at stage or transition boundaries.

ARCHITECTURE NOTE:
    Validators return semantic results and never choose graph destinations.
    Declaration order is preserved so callers can place cheap deterministic
    checks before model-backed verification. Agent verdicts require a Pydantic
    model and remain probabilistic even though their invocation is enforced.

PUBLIC API INVENTORY:
    CallableValidator: Adapts a sync/async callback returning bool or ValidationResult.
    SchemaValidator: Applies Pydantic TypeAdapter to a selected candidate value.
    GraderValidator: Maps an existing BaseGrader result to a workflow gate.
    AgentValidator: Runs a structured-output BaseAgent verifier with bounded attempts.
    AllOfValidator: Passes only when every ordered child passes.
    AnyOfValidator: Passes when the first ordered child passes.
    WeightedValidator: Compares a positive-weight score mean with a threshold.

COMMON MODIFICATION PATTERNS:
    Add an adapter when an existing SDK decision type needs workflow semantics.
    Keep destination mapping in graph.py and non-decision normalization in
    machine.py so every validator remains reusable at either validation phase.

WHAT NOT TO DO IN THIS FILE:
    1. Do not map a verdict to a stage name; return a semantic code only.
    2. Do not hide unbounded retries or fallback model calls inside validators.
    3. Do not treat an LLM grader or agent verdict as deterministic truth.
    4. Do not record raw candidate state in failure details.

KNOWN EDGE CASES:
    fail_closed=False on AgentValidator returns ERROR; the machine's global
    ValidatorErrorPolicy still decides whether that error may pass. Composite
    validators preserve child outcomes in details but expose one top-level record.

COMMON ERRORS:
    WorkflowDefinitionError for invalid adapter construction. Runtime callback
    exceptions are normalized by machine.py according to validator policy.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/validated-state-machine-workflows.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Inline smoke covers callable, schema, composite, and fail-closed behavior.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from math import isfinite
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from vidbyte.agents import AgentForkSettings, AgentInput, BaseAgent
from vidbyte.evals import BaseGrader, EvalCase, GraderResult
from vidbyte.workflows.contracts import (
    StateT,
    ValidationContext,
    ValidationResult,
    ValidationStatus,
    Validator,
)
from vidbyte.workflows.errors import WorkflowDefinitionError

VerdictT = TypeVar("VerdictT", bound=BaseModel)


class CallableValidator(Generic[StateT]):
    """Adapts one synchronous or asynchronous validation callback."""

    def __init__(self, callback: Callable[[ValidationContext[StateT]], ValidationResult | bool | Awaitable[ValidationResult | bool]], *, name: str | None = None, reject_code: str = "validation_failed", reject_feedback: str = "Validator returned false.") -> None:
        # Stores one callback and the deterministic false-result mapping.
        if not callable(callback):
            raise WorkflowDefinitionError("CallableValidator callback must be callable.", details={"actual_type": type(callback).__name__})
        if not isinstance(reject_feedback, str):
            raise WorkflowDefinitionError("CallableValidator.reject_feedback must be a string.", details={"actual_type": type(reject_feedback).__name__})
        self._callback = callback
        self._name = _resolved_name(name, callback, "callable_validator")
        self._reject_code = _required_code(reject_code, "CallableValidator.reject_code")
        self._reject_feedback = reject_feedback.strip()

    @property
    def name(self) -> str:
        # Returns the stable identifier used by validation records.
        return self._name

    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult:
        # Invokes the callback and converts a boolean into a structured decision.
        value = await _resolve_awaitable(self._callback(context))
        if isinstance(value, ValidationResult):
            return value
        if isinstance(value, bool):
            return ValidationResult.passed() if value else ValidationResult.rejected(self._reject_code, self._reject_feedback)
        raise TypeError(f"CallableValidator '{self.name}' must return bool or ValidationResult, got {type(value).__name__}.")


class SchemaValidator(Generic[StateT]):
    """Validates a selected candidate value through Pydantic TypeAdapter."""

    def __init__(self, schema: Any, *, selector: Callable[[ValidationContext[StateT]], Any] | None = None, strict: bool = True, name: str | None = None, reject_code: str = "invalid_schema") -> None:
        # Compiles the schema once and stores an optional candidate selector.
        if selector is not None and not callable(selector):
            raise WorkflowDefinitionError("SchemaValidator.selector must be callable when provided.", details={"actual_type": type(selector).__name__})
        if not isinstance(strict, bool):
            raise WorkflowDefinitionError("SchemaValidator.strict must be a boolean.", details={"actual_type": type(strict).__name__})
        try:
            self._adapter = TypeAdapter(schema)
        except Exception as exc:
            raise WorkflowDefinitionError("SchemaValidator could not compile the provided schema.", details={"schema_type": type(schema).__name__, "error_type": type(exc).__name__}) from exc
        self._selector = selector
        self._strict = strict
        self._name = _resolved_name(name, schema, "schema_validator")
        self._reject_code = _required_code(reject_code, "SchemaValidator.reject_code")

    @property
    def name(self) -> str:
        # Returns the stable identifier used by validation records.
        return self._name

    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult:
        # Validates the selected value and converts Pydantic evidence to safe details.
        value = self._selector(context) if self._selector is not None else context.candidate_state
        try:
            self._adapter.validate_python(value, strict=self._strict)
        except ValidationError as exc:
            details = {"error_count": exc.error_count(), "errors": tuple(exc.errors(include_input=False))}
            return ValidationResult.rejected(self._reject_code, "Candidate value did not satisfy the declared schema.", score=0.0, details=details)
        return ValidationResult.passed(score=1.0)


class GraderValidator(Generic[StateT]):
    """Adapts a Vidbyte eval grader to a workflow validation gate."""

    def __init__(self, grader: BaseGrader, case_builder: Callable[[ValidationContext[StateT]], EvalCase], actual_builder: Callable[[ValidationContext[StateT]], str], *, name: str | None = None, reject_code: str = "grader_rejected") -> None:
        # Stores builders that project workflow context into the eval contract.
        self._grader = grader
        self._case_builder = case_builder
        self._actual_builder = actual_builder
        self._name = _resolved_name(name, grader, getattr(grader, "name", "grader_validator"))
        self._reject_code = _required_code(reject_code, "GraderValidator.reject_code")

    @property
    def name(self) -> str:
        # Returns the stable identifier used by validation records.
        return self._name

    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult:
        # Grades the projected candidate and preserves score and reason.
        result = await self._grader.agrade(self._case_builder(context), self._actual_builder(context))
        if not isinstance(result, GraderResult):
            raise TypeError(f"GraderValidator '{self.name}' expected GraderResult, got {type(result).__name__}.")
        details = {"grader": getattr(self._grader, "name", type(self._grader).__name__)}
        if result.passed:
            return ValidationResult.passed(feedback=result.reason, score=result.score, details=details)
        return ValidationResult.rejected(self._reject_code, result.reason or "Grader rejected the candidate.", score=result.score, details=details)


class AgentValidator(Generic[StateT, VerdictT]):
    """Runs a structured-output agent as a bounded probabilistic verifier."""

    def __init__(self, agent: BaseAgent | Callable[[ValidationContext[StateT]], BaseAgent], prompt_builder: Callable[[ValidationContext[StateT]], str | AgentInput], verdict_schema: type[VerdictT], verdict_mapper: Callable[[VerdictT, ValidationContext[StateT]], ValidationResult], *, fresh_fork: bool = True, max_attempts: int = 1, timeout_seconds: float | None = None, fail_closed: bool = True, error_code: str = "agent_validator_error", name: str | None = None) -> None:
        # Validates verifier policy and stores the agent-to-result mapping boundary.
        if not isinstance(agent, BaseAgent) and not callable(agent):
            raise WorkflowDefinitionError("AgentValidator agent must be BaseAgent or a callable factory.", details={"actual_type": type(agent).__name__})
        if not callable(prompt_builder) or not callable(verdict_mapper):
            raise WorkflowDefinitionError("AgentValidator prompt_builder and verdict_mapper must be callable.", details={"prompt_builder_type": type(prompt_builder).__name__, "verdict_mapper_type": type(verdict_mapper).__name__})
        if not isinstance(verdict_schema, type) or not issubclass(verdict_schema, BaseModel):
            raise WorkflowDefinitionError("AgentValidator.verdict_schema must be a Pydantic BaseModel subclass.", details={"schema_type": type(verdict_schema).__name__})
        if not isinstance(fresh_fork, bool) or not isinstance(fail_closed, bool):
            raise WorkflowDefinitionError("AgentValidator fresh_fork and fail_closed must be booleans.", details={"fresh_fork_type": type(fresh_fork).__name__, "fail_closed_type": type(fail_closed).__name__})
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts <= 0:
            raise WorkflowDefinitionError("AgentValidator.max_attempts must be an integer greater than zero.", details={"actual_type": type(max_attempts).__name__})
        if timeout_seconds is not None and (not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise WorkflowDefinitionError("AgentValidator.timeout_seconds must be a finite number greater than zero when provided.", details={"actual_type": type(timeout_seconds).__name__})
        self._agent_source = agent
        self._prompt_builder = prompt_builder
        self._verdict_schema = verdict_schema
        self._verdict_mapper = verdict_mapper
        self._fresh_fork = fresh_fork
        self._max_attempts = max_attempts
        self._timeout_seconds = float(timeout_seconds) if timeout_seconds is not None else None
        self._fail_closed = fail_closed
        self._error_code = _required_code(error_code, "AgentValidator.error_code")
        self._name = _resolved_name(name, agent, "agent_validator")

    @property
    def name(self) -> str:
        # Returns the stable identifier used by validation records.
        return self._name

    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult:
        # Retries verifier infrastructure failures within the declared attempt bound.
        last_error: Exception | None = None
        for _ in range(self._max_attempts):
            try:
                return await self._validate_once(context)
            except Exception as exc:
                last_error = exc
        error_type = type(last_error).__name__ if last_error is not None else "UnknownVerifierError"
        feedback = f"Agent validator '{self.name}' failed after {self._max_attempts} attempt(s)."
        details = {"attempts": self._max_attempts, "error_type": error_type}
        if self._fail_closed:
            return ValidationResult.rejected(self._error_code, feedback, score=0.0, details=details)
        return ValidationResult.errored(self._error_code, feedback, details=details)

    async def _validate_once(self, context: ValidationContext[StateT]) -> ValidationResult:
        # Runs one isolated verifier call and maps only a revalidated model verdict.
        agent = self._resolve_agent(context)
        prompt = self._prompt_builder(context)
        reply = await self._run_agent(agent, prompt)
        structured = reply.metadata.get("structured")
        if structured is None:
            raise ValueError("Verifier reply did not include metadata['structured'].")
        verdict = self._verdict_schema.model_validate(structured)
        result = self._verdict_mapper(verdict, context)
        if not isinstance(result, ValidationResult):
            raise TypeError(f"AgentValidator verdict_mapper must return ValidationResult, got {type(result).__name__}.")
        return result

    def _resolve_agent(self, context: ValidationContext[StateT]) -> BaseAgent:
        # Resolves a fixed verifier or a context-aware verifier factory per attempt.
        agent = self._agent_source if isinstance(self._agent_source, BaseAgent) else self._agent_source(context)
        if not isinstance(agent, BaseAgent):
            raise TypeError(f"AgentValidator agent factory must return BaseAgent, got {type(agent).__name__}.")
        if not self._fresh_fork:
            return agent
        return agent.fork(AgentForkSettings(include_history=False, output_schema=self._verdict_schema))

    async def _run_agent(self, agent: BaseAgent, prompt: str | AgentInput) -> Any:
        # Applies the verifier-local timeout without changing the machine timeout.
        if self._timeout_seconds is None:
            return await agent.arun(prompt)
        return await asyncio.wait_for(agent.arun(prompt), timeout=self._timeout_seconds)


class AllOfValidator(Generic[StateT]):
    """Passes only when every ordered child validator passes."""

    def __init__(self, validators: Sequence[Validator[StateT]], *, name: str | None = None) -> None:
        # Stores a non-empty ordered validator conjunction.
        self._validators = _required_validators(validators, "AllOfValidator")
        self._name = _required_code(name, "AllOfValidator.name") if name is not None else "all_of"

    @property
    def name(self) -> str:
        # Returns the stable identifier used by validation records.
        return self._name

    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult:
        # Stops at the first non-pass while preserving evaluated child evidence.
        children: list[Mapping[str, Any]] = []
        for validator in self._validators:
            result = await _invoke_child(validator, context)
            children.append(_result_payload(validator, result))
            if result.status is not ValidationStatus.PASS:
                return _with_children(result, children)
        return ValidationResult.passed(score=_mean_score(children, 1.0), details={"children": tuple(children)})


class AnyOfValidator(Generic[StateT]):
    """Passes when the first ordered child validator passes."""

    def __init__(self, validators: Sequence[Validator[StateT]], *, name: str | None = None, reject_code: str = "no_validator_passed") -> None:
        # Stores a non-empty ordered validator disjunction.
        self._validators = _required_validators(validators, "AnyOfValidator")
        self._name = _required_code(name, "AnyOfValidator.name") if name is not None else "any_of"
        self._reject_code = _required_code(reject_code, "AnyOfValidator.reject_code")

    @property
    def name(self) -> str:
        # Returns the stable identifier used by validation records.
        return self._name

    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult:
        # Returns the first pass or a deterministic aggregate non-pass result.
        results: list[ValidationResult] = []
        children: list[Mapping[str, Any]] = []
        for validator in self._validators:
            result = await _invoke_child(validator, context)
            results.append(result)
            children.append(_result_payload(validator, result))
            if result.status is ValidationStatus.PASS:
                return ValidationResult.passed(feedback=result.feedback, score=result.score, details={"children": tuple(children)})
        return self._aggregate_non_pass(results, children)

    def _aggregate_non_pass(self, results: Sequence[ValidationResult], children: Sequence[Mapping[str, Any]]) -> ValidationResult:
        # Gives errors precedence, then all-abstain, then aggregate rejection.
        if any(result.status is ValidationStatus.ERROR for result in results):
            return ValidationResult.errored("child_validator_error", "At least one child validator errored and none passed.", details={"children": tuple(children)})
        if all(result.status is ValidationStatus.ABSTAIN for result in results):
            return ValidationResult.abstained("all_validators_abstained", "Every child validator abstained.", details={"children": tuple(children)})
        return ValidationResult.rejected(self._reject_code, "No child validator passed.", score=0.0, details={"children": tuple(children)})


class WeightedValidator(Generic[StateT]):
    """Passes when the ordered child score mean meets a fixed threshold."""

    def __init__(self, validators: Sequence[tuple[float, Validator[StateT]]], *, threshold: float, name: str | None = None, reject_code: str = "weighted_threshold_not_met") -> None:
        # Validates positive child weights and a unit-interval threshold.
        try:
            weighted = tuple((float(weight), validator) for weight, validator in validators)
        except (TypeError, ValueError) as exc:
            raise WorkflowDefinitionError("WeightedValidator entries must be (numeric weight, validator) pairs.") from exc
        if not weighted or any(not isfinite(weight) or weight <= 0 for weight, _ in weighted):
            raise WorkflowDefinitionError("WeightedValidator requires one or more positive validator weights.", details={"validator_count": len(weighted)})
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise WorkflowDefinitionError("WeightedValidator.threshold must be a finite number between 0.0 and 1.0.", details={"actual_type": type(threshold).__name__})
        self._validators = weighted
        self._threshold = float(threshold)
        self._name = _required_code(name, "WeightedValidator.name") if name is not None else "weighted"
        self._reject_code = _required_code(reject_code, "WeightedValidator.reject_code")

    @property
    def name(self) -> str:
        # Returns the stable identifier used by validation records.
        return self._name

    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult:
        # Evaluates every child and compares the normalized weighted mean.
        evaluated = [(weight, validator, await _invoke_child(validator, context)) for weight, validator in self._validators]
        children = tuple(_result_payload(validator, result, weight=weight) for weight, validator, result in evaluated)
        if any(result.status is ValidationStatus.ERROR for _, _, result in evaluated):
            return ValidationResult.errored("child_validator_error", "A weighted child validator errored.", details={"children": children})
        if any(result.status is ValidationStatus.ABSTAIN for _, _, result in evaluated):
            return ValidationResult.abstained("child_validator_abstained", "A weighted child validator abstained.", details={"children": children})
        score = self._weighted_score(evaluated)
        if score >= self._threshold:
            return ValidationResult.passed(score=score, details={"threshold": self._threshold, "children": children})
        return ValidationResult.rejected(self._reject_code, f"Weighted validation score {score:.3f} is below threshold {self._threshold:.3f}.", score=score, details={"threshold": self._threshold, "children": children})

    def _weighted_score(self, evaluated: Sequence[tuple[float, Validator[StateT], ValidationResult]]) -> float:
        # Computes a normalized mean using pass=1 and reject=0 when score is absent.
        total_weight = sum(weight for weight, _, _ in evaluated)
        weighted_score = sum(weight * _effective_score(result) for weight, _, result in evaluated)
        return weighted_score / total_weight


async def _invoke_child(validator: Validator[StateT], context: ValidationContext[StateT]) -> ValidationResult:
    # Converts child exceptions and invalid returns into explicit ERROR decisions.
    try:
        result = await validator.validate(context)
    except Exception as exc:
        return ValidationResult.errored("validator_exception", f"Child validator '{_validator_name(validator)}' raised {type(exc).__name__}.", details={"error_type": type(exc).__name__})
    if not isinstance(result, ValidationResult):
        return ValidationResult.errored("invalid_validator_result", f"Child validator '{_validator_name(validator)}' returned {type(result).__name__}.")
    return result


async def _resolve_awaitable(value: Any) -> Any:
    # Awaits callback results only when the returned object is awaitable.
    return await value if inspect.isawaitable(value) else value


def _required_validators(validators: Sequence[Validator[StateT]], owner: str) -> tuple[Validator[StateT], ...]:
    # Freezes a non-empty validator sequence for deterministic evaluation order.
    resolved = tuple(validators)
    if not resolved:
        raise WorkflowDefinitionError(f"{owner} requires at least one child validator.", details={"owner": owner})
    return resolved


def _resolved_name(name: str | None, source: Any, fallback: str) -> str:
    # Derives one stable adapter name from an explicit value or source metadata.
    if name is not None:
        return _required_code(name, "validator name")
    candidate = getattr(source, "name", None) or getattr(source, "__name__", None)
    return str(candidate).strip() if candidate and str(candidate).strip() else fallback


def _required_code(value: str, field_name: str) -> str:
    # Normalizes a semantic code and reports its exact configuration field.
    if not isinstance(value, str):
        raise WorkflowDefinitionError(f"{field_name} must be a string.", details={"field": field_name, "actual_type": type(value).__name__})
    code = value.strip()
    if not code:
        raise WorkflowDefinitionError(f"{field_name} cannot be empty.", details={"field": field_name})
    return code


def _validator_name(validator: Validator[Any]) -> str:
    # Reads a validator name defensively for composite failure diagnostics.
    try:
        name = validator.name
    except Exception:
        return type(validator).__name__
    return str(name).strip() or type(validator).__name__


def _result_payload(validator: Validator[Any], result: ValidationResult, *, weight: float | None = None) -> Mapping[str, Any]:
    # Builds compact ordered child evidence without candidate inputs.
    payload: dict[str, Any] = {"validator": _validator_name(validator), "status": result.status.value, "code": result.code, "feedback": result.feedback, "score": result.score, "details": dict(result.details)}
    if weight is not None:
        payload["weight"] = weight
    return payload


def _with_children(result: ValidationResult, children: Sequence[Mapping[str, Any]]) -> ValidationResult:
    # Returns the same semantic decision with composite child evidence attached.
    details = {**dict(result.details), "children": tuple(children)}
    return ValidationResult(result.status, code=result.code, feedback=result.feedback, score=result.score, details=details)


def _effective_score(result: ValidationResult) -> float:
    # Uses explicit scores first, then maps pass to one and reject to zero.
    if result.score is not None:
        return result.score
    return 1.0 if result.status is ValidationStatus.PASS else 0.0


def _mean_score(children: Sequence[Mapping[str, Any]], default: float) -> float:
    # Computes a diagnostic mean from child scores with a caller-provided default.
    scores = [float(child["score"]) for child in children if child.get("score") is not None]
    return sum(scores) / len(scores) if scores else default


__all__ = [
    "AgentValidator",
    "AllOfValidator",
    "AnyOfValidator",
    "CallableValidator",
    "GraderValidator",
    "SchemaValidator",
    "WeightedValidator",
]
