"""FILE: vidbyte/workflows/state.py
PURPOSE: Defines typed workflow state channels, codecs, reducers, and immutable updates.
ROLE IN CODEBASE: graph.py compiles schemas; machine.py applies candidate and observation updates.

ARCHITECTURE NOTE:
    A StateSchema is the only authority allowed to merge stage updates into StateT.
    Transition channels remain candidates until an edge commits. Immediate channels
    are observations and must be persisted before their reduced value is returned.

PUBLIC API INVENTORY:
    StateCommitMode / StateChannel: Channel declaration and commit semantics.
    StateReducer / StateCodec: Stable extension protocols used in fingerprints.
    ReplaceReducer / AppendReducer / MergeMappingReducer / SetUnionReducer:
        Deterministic built-in merge policies.
    CallableReducer: Named custom deterministic reducer.
    StateSchema: Validation, encode/decode, declared-write enforcement, and reduction.

COMMON MODIFICATION PATTERNS:
    Add a reducer by giving it a stable reducer_id and pure reduce method, then expose
    it through workflows/__init__.py and document its serialization expectations.

WHAT NOT TO DO IN THIS FILE:
    1. Do not append events; machine.py owns canonical ordering.
    2. Do not mutate reducer inputs or state objects in place.
    3. Do not hide reducer identity from definition fingerprints.

KNOWN EDGE CASES:
    Custom object state requires a StateCodec when Pydantic cannot construct it.
    Immediate values survive later stage rejection by design and cannot be rolled back.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke covers every built-in reducer,
    undeclared writes, root compatibility, and invalid decoded state.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar, get_type_hints, is_typeddict, runtime_checkable

from pydantic import BaseModel, TypeAdapter

from .errors import WorkflowStateError


StateT = TypeVar("StateT")


class StateCommitMode(str, Enum):
    """Boundary at which one channel update becomes committed workflow truth."""

    ON_TRANSITION = "on_transition"
    IMMEDIATE = "immediate"


@runtime_checkable
class StateReducer(Protocol):
    """Pure deterministic channel merge operation with a stable public identity."""

    @property
    def reducer_id(self) -> str:
        # Returns the stable identity stored in definition fingerprints.
        ...

    def reduce(self, current: Any, update: Any) -> Any:
        # Produces a new channel value without mutating either input.
        ...


@runtime_checkable
class StateCodec(Protocol[StateT]):
    """Bidirectional StateT serialization contract used by persistence and replay."""

    @property
    def codec_id(self) -> str:
        # Returns the stable identity checked during cold resume.
        ...

    def encode(self, state: StateT) -> Mapping[str, Any]:
        # Converts one validated state value into named channel payloads.
        ...

    def decode(self, payload: Mapping[str, Any]) -> StateT:
        # Reconstructs and validates StateT from named channel payloads.
        ...


class ReplaceReducer:
    """Replaces the channel with an isolated copy of the supplied update."""

    @property
    def reducer_id(self) -> str:
        # Identifies the built-in replacement contract across process restarts.
        return "replace:v1"

    def reduce(self, current: Any, update: Any) -> Any:
        # Returns a deep copy so callers cannot mutate committed state by alias.
        return deepcopy(update)


class AppendReducer:
    """Extends list/tuple channels while preserving their existing container kind."""

    @property
    def reducer_id(self) -> str:
        # Identifies the built-in ordered append contract across process restarts.
        return "append:v1"

    def reduce(self, current: Any, update: Any) -> Any:
        # Appends a sequence as items and a scalar as one item without aliasing inputs.
        existing = list(current or ())
        additions = list(update) if _is_append_sequence(update) else [update]
        merged = deepcopy(existing + additions)
        return tuple(merged) if isinstance(current, tuple) else merged


class MergeMappingReducer:
    """Overlays mapping keys onto an isolated copy of the current mapping."""

    @property
    def reducer_id(self) -> str:
        # Identifies the built-in shallow mapping overlay contract.
        return "merge_mapping:v1"

    def reduce(self, current: Any, update: Any) -> Any:
        # Copies both sides and replaces only keys supplied by the update.
        if not isinstance(current or {}, Mapping) or not isinstance(update, Mapping):
            raise WorkflowStateError("MergeMappingReducer requires mapping values.", details={"current_type": type(current).__name__, "update_type": type(update).__name__})
        merged = deepcopy(dict(current or {}))
        merged.update(deepcopy(dict(update)))
        return merged


class SetUnionReducer:
    """Adds unique values to set-like channels with deterministic reduction semantics."""

    @property
    def reducer_id(self) -> str:
        # Identifies the built-in set-union contract across process restarts.
        return "set_union:v1"

    def reduce(self, current: Any, update: Any) -> Any:
        # Unions iterable updates and preserves frozenset only when already immutable.
        existing = set(current or ())
        additions = set(update) if _is_set_sequence(update) else {update}
        merged = existing | additions
        return frozenset(merged) if isinstance(current, frozenset) else merged


@dataclass(frozen=True, slots=True)
class CallableReducer:
    """Wraps a caller-owned pure reducer under an explicit stable versioned ID."""

    reducer_id: str
    callback: Callable[[Any, Any], Any]

    def __post_init__(self) -> None:
        # Rejects anonymous identities because durable resumes compare reducer IDs.
        object.__setattr__(self, "reducer_id", _required_text(self.reducer_id, "CallableReducer.reducer_id"))
        if not callable(self.callback):
            raise TypeError("CallableReducer.callback must be callable.")

    def reduce(self, current: Any, update: Any) -> Any:
        # Invokes the synchronous reducer and rejects in-place aliasing.
        result = self.callback(deepcopy(current), deepcopy(update))
        if result is current:
            raise WorkflowStateError("CallableReducer returned its current input by identity.", details={"reducer_id": self.reducer_id})
        return result


@dataclass(frozen=True, slots=True)
class StateChannel:
    """One typed state key with reducer, default, commit mode, and sensitivity."""

    reducer: StateReducer = field(default_factory=ReplaceReducer)
    default_factory: Callable[[], Any] = lambda: None
    commit_mode: StateCommitMode = StateCommitMode.ON_TRANSITION
    sensitive: bool = False

    def __post_init__(self) -> None:
        # Validates extension protocols before a graph definition can compile.
        if not isinstance(self.reducer, StateReducer):
            raise TypeError("StateChannel.reducer must satisfy StateReducer.")
        if not callable(self.default_factory):
            raise TypeError("StateChannel.default_factory must be callable.")
        mode = self.commit_mode if isinstance(self.commit_mode, StateCommitMode) else StateCommitMode(self.commit_mode)
        object.__setattr__(self, "commit_mode", mode)
        if not isinstance(self.sensitive, bool):
            raise TypeError("StateChannel.sensitive must be a boolean.")


class _TypeAdapterCodec(Generic[StateT]):
    """Default codec for mappings, Pydantic models, dataclasses, and typed records."""

    def __init__(self, state_type: Any) -> None:
        # Compiles validation once and records a stable type-oriented codec ID.
        self.state_type = state_type
        self.adapter = TypeAdapter(state_type)

    @property
    def codec_id(self) -> str:
        # Includes module/name so checkpoint compatibility follows the state contract.
        return f"type_adapter:v1:{_type_name(self.state_type)}"

    def encode(self, state: StateT) -> Mapping[str, Any]:
        # Converts supported state containers into an isolated named mapping.
        if isinstance(state, BaseModel):
            return deepcopy(state.model_dump(mode="python"))
        if is_dataclass(state) and not isinstance(state, type):
            return deepcopy(asdict(state))
        if isinstance(state, Mapping):
            return deepcopy(dict(state))
        try:
            dumped = self.adapter.dump_python(state, mode="python")
        except Exception as exc:
            raise WorkflowStateError("State codec could not encode the workflow state.", details={"codec_id": self.codec_id, "state_type": type(state).__name__}) from exc
        if not isinstance(dumped, Mapping):
            raise WorkflowStateError("State codec output must be a mapping of channels.", details={"codec_id": self.codec_id, "output_type": type(dumped).__name__})
        return deepcopy(dict(dumped))

    def decode(self, payload: Mapping[str, Any]) -> StateT:
        # Revalidates every reduced payload through Pydantic's compiled adapter.
        try:
            return self.adapter.validate_python(deepcopy(dict(payload)))
        except Exception as exc:
            raise WorkflowStateError("Reduced channel payload does not satisfy StateT.", details={"codec_id": self.codec_id, "channels": sorted(payload)}) from exc


class _TypedDictCodec(Generic[StateT]):
    """Python 3.11 TypedDict codec independent of Pydantic's typing_extensions rule."""

    def __init__(self, state_type: Any) -> None:
        # Compiles one adapter per field so both typing.TypedDict variants validate.
        self.state_type = state_type
        try:
            annotations = get_type_hints(state_type, include_extras=True)
            self.adapters = {name: TypeAdapter(annotation) for name, annotation in annotations.items()}
        except Exception as exc:
            raise WorkflowStateError("TypedDict state annotations could not be compiled.", details={"state_type": _type_name(state_type)}) from exc
        self.required = frozenset(getattr(state_type, "__required_keys__", annotations if getattr(state_type, "__total__", True) else ()))

    @property
    def codec_id(self) -> str:
        # Distinguishes this compatibility codec in durable schema fingerprints.
        return f"typed_dict:v1:{_type_name(self.state_type)}"

    def encode(self, state: StateT) -> Mapping[str, Any]:
        # Validates and isolates a mapping-shaped TypedDict value.
        return self._validate(state)

    def decode(self, payload: Mapping[str, Any]) -> StateT:
        # Revalidates reducer output and returns the runtime dict representation.
        return self._validate(payload)  # type: ignore[return-value]

    def _validate(self, value: Any) -> dict[str, Any]:
        # Rejects missing/unknown fields and validates each declared annotation.
        if not isinstance(value, Mapping):
            raise WorkflowStateError("TypedDict workflow state must be a mapping.", details={"state_type": _type_name(self.state_type), "actual_type": type(value).__name__})
        unknown = set(value) - set(self.adapters)
        missing = set(self.required) - set(value)
        if unknown or missing:
            raise WorkflowStateError("TypedDict workflow state has missing or unknown fields.", details={"state_type": _type_name(self.state_type), "missing": sorted(missing), "unknown": sorted(map(str, unknown))})
        try:
            return {name: self.adapters[name].validate_python(deepcopy(item)) for name, item in value.items()}
        except Exception as exc:
            raise WorkflowStateError("TypedDict workflow state field validation failed.", details={"state_type": _type_name(self.state_type)}) from exc


class _RootCodec(Generic[StateT]):
    """Compatibility codec for PR #268 whole-state replacement graphs."""

    def __init__(self, state_type: Any, validator: Callable[[Any], StateT] | None, cloner: Callable[[StateT], StateT]) -> None:
        # Stores the existing graph validation and isolation hooks without widening them.
        self.state_type = state_type
        self.validator = validator
        self.cloner = cloner
        self.adapter = _optional_adapter(state_type)

    @property
    def codec_id(self) -> str:
        # Marks the compatibility root boundary in durable fingerprints.
        return f"root:v1:{_type_name(self.state_type)}"

    def encode(self, state: StateT) -> Mapping[str, Any]:
        # Validates and isolates the entire state as one implicit root channel.
        return {"__root__": self._validate(self.cloner(state))}

    def decode(self, payload: Mapping[str, Any]) -> StateT:
        # Reconstructs the whole state from the required implicit root channel.
        if "__root__" not in payload:
            raise WorkflowStateError("Root state payload is missing __root__.", details={"channels": sorted(payload)})
        return self._validate(self.cloner(payload["__root__"]))

    def _validate(self, value: Any) -> StateT:
        # Applies custom validation first, then Pydantic or runtime type validation.
        try:
            if self.validator is not None:
                return self.validator(value)
            if self.adapter is not None:
                return self.adapter.validate_python(value)
            if not isinstance(value, self.state_type):
                raise TypeError(f"Expected {_type_name(self.state_type)}, got {type(value).__name__}.")
            return value
        except WorkflowStateError:
            raise
        except Exception as exc:
            raise WorkflowStateError("Workflow state does not satisfy the root contract.", details={"expected": _type_name(self.state_type), "actual": type(value).__name__}) from exc


class StateSchema(Generic[StateT]):
    """Validated channel schema and deterministic reducer application boundary."""

    def __init__(self, state_type: Any, *, channels: Mapping[str, StateChannel], codec: StateCodec[StateT] | None = None, version: str = "1") -> None:
        # Compiles one immutable schema after validating channel identities and modes.
        if not isinstance(channels, Mapping) or not channels:
            raise ValueError("StateSchema.channels must be a non-empty mapping.")
        normalized = {_required_text(name, "StateSchema channel"): channel for name, channel in channels.items()}
        if any(not isinstance(channel, StateChannel) for channel in normalized.values()):
            raise TypeError("Every StateSchema channel must be a StateChannel.")
        self.state_type = state_type
        self.channels = MappingProxyType(dict(normalized))
        self.codec = codec or (_TypedDictCodec(state_type) if is_typeddict(state_type) else _TypeAdapterCodec(state_type))
        if not isinstance(self.codec, StateCodec):
            raise TypeError("StateSchema.codec must satisfy StateCodec.")
        self.version = _required_text(version, "StateSchema.version")

    @classmethod
    def root(cls, state_type: Any, *, validator: Callable[[Any], StateT] | None = None, cloner: Callable[[StateT], StateT] = deepcopy, version: str = "1") -> "StateSchema[StateT]":
        # Builds whole-state replacement compatibility for existing StageResult graphs.
        channel = StateChannel(ReplaceReducer(), lambda: None, StateCommitMode.ON_TRANSITION)
        return cls(state_type, channels={"__root__": channel}, codec=_RootCodec(state_type, validator, cloner), version=version)

    @property
    def root_compatible(self) -> bool:
        # Reports whether StageResult(state=...) may use the implicit root update path.
        return tuple(self.channels) == ("__root__",)

    @property
    def immediate_channels(self) -> frozenset[str]:
        # Returns names that must append and reduce before a stage continues.
        return frozenset(name for name, channel in self.channels.items() if channel.commit_mode is StateCommitMode.IMMEDIATE)

    def validate(self, state: StateT) -> StateT:
        # Round-trips state through the codec to enforce the current schema contract.
        return self.decode(self.encode(state))

    def apply(self, state: StateT, updates: Mapping[str, Any], *, allowed_writes: Collection[str]) -> StateT:
        # Applies transition-bound reducer updates after enforcing declared write access.
        payload = dict(self.encode(state))
        allowed = set(allowed_writes)
        for name in sorted(updates):
            self._assert_writable(name, allowed, StateCommitMode.ON_TRANSITION)
            payload[name] = self._reduce(name, payload.get(name, self.channels[name].default_factory()), updates[name])
        return self.decode(payload)

    def apply_observation(self, observations: Mapping[str, Any], channel: str, value: Any) -> Mapping[str, Any]:
        # Reduces one immediate observation into a new read-only projection mapping.
        self._assert_writable(channel, {channel}, StateCommitMode.IMMEDIATE)
        current = observations.get(channel, self.channels[channel].default_factory())
        reduced = self._reduce(channel, current, value)
        updated = deepcopy(dict(observations))
        updated[channel] = reduced
        return MappingProxyType(updated)

    def initialize_observations(self, values: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        # Creates defaults and reduces caller-provided values only for immediate channels.
        observations: Mapping[str, Any] = MappingProxyType({name: deepcopy(self.channels[name].default_factory()) for name in self.immediate_channels})
        for name, value in (values or {}).items():
            observations = self.apply_observation(observations, name, value)
        return observations

    def encode(self, state: StateT) -> Mapping[str, Any]:
        # Returns an isolated mapping after rejecting undeclared codec channels.
        payload = dict(self.codec.encode(state))
        unknown = set(payload) - set(self.channels)
        if unknown:
            raise WorkflowStateError("State codec emitted undeclared channels.", details={"unknown_channels": sorted(unknown)})
        return MappingProxyType(deepcopy(payload))

    def decode(self, payload: Mapping[str, Any]) -> StateT:
        # Delegates reconstruction after confirming payload keys are declared.
        unknown = set(payload) - set(self.channels)
        if unknown:
            raise WorkflowStateError("State payload contains undeclared channels.", details={"unknown_channels": sorted(unknown)})
        return self.codec.decode(payload)

    def fingerprint(self) -> Mapping[str, Any]:
        # Produces stable JSON-ready schema identity for definition hashing and resume.
        return {
            "version": self.version,
            "codec_id": self.codec.codec_id,
            "channels": [
                {"name": name, "reducer_id": channel.reducer.reducer_id, "commit_mode": channel.commit_mode.value, "sensitive": channel.sensitive}
                for name, channel in sorted(self.channels.items())
            ],
        }

    @property
    def fingerprint_id(self) -> str:
        # Hashes canonical schema identity for compact checkpoint compatibility checks.
        encoded = json.dumps(self.fingerprint(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"wfschema_{sha256(encoded).hexdigest()}"

    def _assert_writable(self, name: str, allowed: set[str], mode: StateCommitMode) -> None:
        # Rejects unknown, undeclared, or wrong-boundary writes before any reducer runs.
        if name not in self.channels:
            raise WorkflowStateError("Workflow update names an unknown state channel.", details={"channel": name, "known_channels": sorted(self.channels)})
        if name not in allowed:
            raise WorkflowStateError("Workflow stage attempted an undeclared channel write.", details={"channel": name, "allowed_writes": sorted(allowed)})
        if self.channels[name].commit_mode is not mode:
            raise WorkflowStateError("Workflow channel was written at the wrong commit boundary.", details={"channel": name, "expected_mode": self.channels[name].commit_mode.value, "actual_mode": mode.value})

    def _reduce(self, name: str, current: Any, update: Any) -> Any:
        # Isolates reducer inputs and validates that the output is a fresh value.
        reducer = self.channels[name].reducer
        current_copy = deepcopy(current)
        update_copy = deepcopy(update)
        try:
            reduced = reducer.reduce(current_copy, update_copy)
        except WorkflowStateError:
            raise
        except Exception as exc:
            raise WorkflowStateError("State reducer failed.", details={"channel": name, "reducer_id": reducer.reducer_id}) from exc
        if reduced is current_copy:
            raise WorkflowStateError("State reducer returned its current input by identity.", details={"channel": name, "reducer_id": reducer.reducer_id})
        return deepcopy(reduced)


def _optional_adapter(state_type: Any) -> TypeAdapter[Any] | None:
    # Creates a Pydantic adapter when the declared type is representable.
    try:
        return TypeAdapter(state_type)
    except Exception:
        return None


def _is_append_sequence(value: Any) -> bool:
    # Treats text and mappings as scalar values rather than collections of parts.
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _is_set_sequence(value: Any) -> bool:
    # Treats text and mappings as one set item while accepting ordinary iterables.
    return isinstance(value, (set, frozenset, list, tuple))


def _required_text(value: str, field_name: str) -> str:
    # Normalizes a stable identifier and reports the precise empty field.
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


def _type_name(value: Any) -> str:
    # Returns a stable module-qualified type identity for fingerprints and errors.
    module = getattr(value, "__module__", "")
    name = getattr(value, "__qualname__", repr(value))
    return f"{module}.{name}" if module else str(name)


__all__ = [
    "AppendReducer",
    "CallableReducer",
    "MergeMappingReducer",
    "ReplaceReducer",
    "SetUnionReducer",
    "StateChannel",
    "StateCodec",
    "StateCommitMode",
    "StateReducer",
    "StateSchema",
]
