"""Context Protocol Header

Description:
    Defines AgentKeys, the content-addressed store for the five keys a
    BaseAgent tracks throughout its runtime: settings, latest response,
    toolset, latest tool call, and caller-recorded steps.
Purpose:
    Gives every BaseAgent a bounded, decodable record of its own runtime
    state, constructed eagerly and updated by BaseAgent (and the runtime loop,
    for tool calls) pushing data in as things happen — never by AgentKeys
    reaching back into the agent to pull state on demand.
Architecture:
    - AgentKeys: owns one validated AgentIdentity set once at construction,
      plus a bounded FIFO-evictable content-addressed store shared by all
      five kinds.
Relations:
    Constructed by vidbyte.agents.base.BaseAgent.__init__ and assigned to
    self.keys, from an AgentIdentity it builds. Built on vidbyte.lib.hashing's
    pure canonicalize/hash primitives. Raises vidbyte.lib.errors.
    AgentKeyNotFoundError on unknown digests.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping
from typing import Any

from vidbyte.lib.constants import AGENT_KEYS_SCHEMA_VERSION, DEFAULT_MAX_STORE_ENTRIES
from vidbyte.lib.dataclasses.agent_keys import AgentIdentity, AgentSettingsSnapshot
from vidbyte.lib.enums import AgentKeyKind
from vidbyte.lib.errors import AgentKeyNotFoundError, ConfigurationError
from vidbyte.lib.hashing import CanonicalJsonInput, Hashing, HexDigestInput


def _settings_snapshot_payload(settings_snapshot: AgentSettingsSnapshot) -> dict[str, Any]:
    # Flattens a validated AgentSettingsSnapshot into the JSON-safe payload AgentKeys hashes and stores.
    identity = settings_snapshot.identity
    return {
        "identity": {
            "agent_name": identity.agent_name,
            "provider": identity.provider.value if identity.provider is not None else None,
            "model_name": identity.model_name,
            "runtime_type": identity.runtime_type.value,
            "run_id": identity.run_id,
        },
        "temperature": settings_snapshot.temperature,
        "runtime_config": dict(settings_snapshot.runtime_config),
        "algorithm": settings_snapshot.algorithm,
        "capabilities": list(settings_snapshot.capabilities),
        "description": settings_snapshot.description,
        "metadata": dict(settings_snapshot.metadata),
        "loop_settings": dict(settings_snapshot.loop_settings),
        "output_schema": dict(settings_snapshot.output_schema),
        "tool_settings": settings_snapshot.tool_settings_repr,
        "tool_error_policy": settings_snapshot.tool_error_policy_repr,
        "output_contracts": list(settings_snapshot.output_contracts),
        "max_contract_rejections": settings_snapshot.max_contract_rejections,
        "permission_policy": {"allowed": list(settings_snapshot.permission_policy_allowed)},
    }


class AgentKeys:
    """Owns and hashes the five tracked keys for one BaseAgent instance."""

    def __init__(
        self,
        *,
        identity: AgentIdentity,
        max_store_entries: int = DEFAULT_MAX_STORE_ENTRIES,
    ) -> None:
        # Stores the validated, write-once identity directly; precomputes identity_key() since nothing it depends on can change.
        if max_store_entries <= 0:
            raise ConfigurationError(f"AgentKeys.max_store_entries must be greater than zero, got {max_store_entries}.")
        self.identity = identity
        self.max_store_entries = max_store_entries
        self._store: OrderedDict[str, Mapping[str, Any]] = OrderedDict()
        self._latest_settings_digest: str | None = None
        self._latest_response_digest: str | None = None
        self._latest_toolset_digest: str | None = None
        self._latest_tool_call_digest: str | None = None
        self._identity_key = self._remember(
            AgentKeyKind.IDENTITY,
            {
                "agent_name": identity.agent_name,
                "provider": identity.provider.value if identity.provider is not None else None,
                "model_name": identity.model_name,
                "runtime_type": identity.runtime_type.value,
                "system_prompt_hash": Hashing.hex_digest(HexDigestInput(text=identity.system_prompt)).digest,
            },
        )

    def identity_key(self) -> str:
        # Returns the cached digest of this agent's write-once identity fields.
        return self._identity_key

    def record_settings(self, settings_snapshot: AgentSettingsSnapshot) -> str:
        # Hashes and stores a full settings snapshot; updates latest_settings_key.
        digest = self._remember(AgentKeyKind.SETTINGS, _settings_snapshot_payload(settings_snapshot))
        self._latest_settings_digest = digest
        return digest

    def record_response(self, message: Mapping[str, Any]) -> str:
        # Hashes and stores one serialized AgentMessage; updates latest_response_key.
        digest = self._remember(AgentKeyKind.RESPONSE, dict(message))
        self._latest_response_digest = digest
        return digest

    def record_toolset(self, tool_names: Iterable[str], mcp_tool_names: Iterable[str] = ()) -> str:
        # Hashes and stores the current bound tool-name set (local + MCP); updates latest_toolset_key.
        names = sorted(set(tool_names) | set(mcp_tool_names))
        digest = self._remember(AgentKeyKind.TOOLSET, {"tool_names": names})
        self._latest_toolset_digest = digest
        return digest

    def record_tool_call(self, tool_name: str, arguments: Mapping[str, Any] | None, output: str) -> str:
        # Hashes and stores one tool call's input and output together; updates latest_tool_call_key.
        payload = {"tool_name": tool_name, "arguments": dict(arguments or {}), "output": output}
        digest = self._remember(AgentKeyKind.TOOL_CALL, payload)
        self._latest_tool_call_digest = digest
        return digest

    def record_step(self, name: str, *, version: int, run_id: str | None = None) -> str:
        # Hashes and stores a caller-named, caller-versioned, run-scoped step key. Never auto-triggered by BaseAgent.
        resolved_run_id = self._resolve_step_run_id(name, version, run_id)
        payload = {"identity_key": self._identity_key, "run_id": resolved_run_id, "name": name, "version": version}
        return self._remember(AgentKeyKind.STEP, payload)

    def decode(self, digest: str) -> Mapping[str, Any]:
        # Returns the stored envelope for digest, or raises AgentKeyNotFoundError.
        envelope = self._store.get(digest)
        if envelope is None:
            raise AgentKeyNotFoundError(
                f"No AgentKeys entry for digest {digest!r}; it was never recorded or has been evicted.",
            )
        return envelope

    @property
    def latest_settings_key(self) -> str | None:
        # Returns the most recently recorded settings digest, or None before the first record.
        return self._latest_settings_digest

    @property
    def latest_response_key(self) -> str | None:
        # Returns the most recently recorded response digest, or None before the first record.
        return self._latest_response_digest

    @property
    def latest_toolset_key(self) -> str | None:
        # Returns the most recently recorded toolset digest, or None before the first record.
        return self._latest_toolset_digest

    @property
    def latest_tool_call_key(self) -> str | None:
        # Returns the most recently recorded tool-call digest, or None before the first record.
        return self._latest_tool_call_digest

    def _resolve_step_run_id(self, name: str, version: int, run_id: str | None) -> str:
        # Validates version and resolves run scoping before any store write happens.
        if version < 1:
            raise ConfigurationError(f"AgentKeys.record_step version must be >= 1, got {version} for step {name!r}.")
        resolved = run_id if run_id is not None else self.identity.run_id
        if not resolved:
            raise ConfigurationError(
                f"AgentKeys.record_step({name!r}) requires a run_id (pass one explicitly, or set BaseAgent(run_id=...)); "
                "a step key with no run scope would collide across every run of this agent."
            )
        return resolved

    def _remember(self, kind: AgentKeyKind, payload: Mapping[str, Any]) -> str:
        # Envelopes payload, hashes it, stores it (refreshing eviction order on repeat content), and evicts past the cap.
        envelope = {"schema": AGENT_KEYS_SCHEMA_VERSION, "kind": kind.value, **payload}
        serialized = Hashing.canonical_json(CanonicalJsonInput(value=envelope)).text
        digest = Hashing.hex_digest(HexDigestInput(text=serialized)).digest
        if digest in self._store:
            self._store.move_to_end(digest)
        else:
            self._store[digest] = envelope
            while len(self._store) > self.max_store_entries:
                self._store.popitem(last=False)
        return digest


__all__ = ["AgentKeys"]
