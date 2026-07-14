"""FILE: vidbyte/harnesses/config.py

PURPOSE:
    Loads the common harness behavior envelope from mappings, JSON, or safe YAML;
    validates its stable fields; resolves local text references; and computes the
    deterministic content-addressed HarnessSpec. It never constructs credentials,
    implementations, stores, or runs.

ROLE IN CODEBASE:
    Called by HarnessClient.load before registry or execution work. It depends on
    harness contracts, typed configuration errors, the shared secret-key policy,
    and PyYAML. Harness factories consume the resulting resolved HarnessSpec.

ARCHITECTURE NOTE:
    Specification identity is a pure function of resolved behavior config. Store,
    capture, persistence, metadata, and timestamps stay outside this file so they
    cannot fragment behavior identity. See the approved design document.

PUBLIC API INVENTORY:
    HarnessConfigLoader.load(source, base_path=None) -> HarnessSpec.
    HarnessConfigLoader.canonical_json(value) -> str.

COMMON MODIFICATION PATTERNS:
    Extend common config only by updating validation, canonical examples, README,
    and the versioning policy together. Per-agent hyperparameters belong in each
    agents[] entry (params/tools); between-agent knobs belong under orchestration.

WHAT NOT TO DO IN THIS FILE:
    1. Do not instantiate harness implementations; registry.py owns that seam.
    2. Do not read environment credentials or preserve credential-like keys.
    3. Do not include operational load options in the specification digest.
    4. Do not fetch remote references; $file is local UTF-8 content only.

KNOWN EDGE CASES:
    Mapping inputs resolve relative $file paths from base_path or the current
    directory. File inputs resolve from their parent. Requested reference paths
    are preserved, while resolved identity contains content and its digest.

COMMON ERRORS:
    HarnessConfigurationError for shape/value failures;
    HarnessCredentialConfigError for secret-like keys;
    HarnessFileReferenceError for invalid local references;
    HarnessVersionError for unsupported config schemas.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline mapping/JSON/YAML/$file/identity smoke verification; no
    dedicated test file was added under the approved no-tests workflow.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from vidbyte.harnesses.contracts import HARNESS_SCHEMA_VERSION, HarnessSpec
from vidbyte.harnesses.errors import (
    HarnessConfigurationError,
    HarnessCredentialConfigError,
    HarnessFileReferenceError,
    HarnessVersionError,
)
from vidbyte.harnesses.serialization import HarnessSecretPolicy

# schema_version, harness, and agents are required; metadata and orchestration are
# optional (absent => {}). `params` is gone at the top level: per-agent params now
# live inside each agents[] entry and between-agent knobs live under orchestration.
_REQUIRED_TOP_LEVEL = frozenset({"schema_version", "harness", "agents"})
_OPTIONAL_TOP_LEVEL = frozenset({"metadata", "orchestration"})
_ALLOWED_TOP_LEVEL = _REQUIRED_TOP_LEVEL | _OPTIONAL_TOP_LEVEL


@dataclass(frozen=True, slots=True)
class _LoadedConfigSource:
    """Parsed requested mapping paired with its reference-resolution base."""

    requested: dict[str, Any]
    base_path: Path


class HarnessConfigLoader:
    """Parser, validator, resolver, and fingerprinter for harness behavior config."""

    def load(self, source: Mapping[str, Any] | str | Path, *, base_path: str | Path | None = None, code_version: str | None = None) -> HarnessSpec:
        # Orchestrates parsing, validation, reference resolution, and deterministic identity.
        # `code_version` is supplied by the Harness subclass / factory (code identity); it is
        # folded into spec_id so two code versions with identical config never collide.
        loaded = self._load_source(source, base_path)
        requested = self._validate_config(loaded.requested)
        self._reject_credential_keys(requested, path="$", active=set())
        resolved_value = self._resolve_value(requested, loaded.base_path, path="$", active=set())
        if not isinstance(resolved_value, dict):
            raise HarnessConfigurationError("Resolved harness config must remain an object.", details={"field": "$"})
        resolved = self._validate_config(resolved_value)
        return self._build_spec(requested, resolved, code_version)

    def canonical_json(self, value: Mapping[str, Any]) -> str:
        # Produces the portable normalized JSON string used by specification hashing.
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise HarnessConfigurationError("Harness config cannot be rendered as canonical JSON.", details={"actual_type": type(value).__name__}) from exc

    def _load_source(self, source: Mapping[str, Any] | str | Path, base_path: str | Path | None) -> _LoadedConfigSource:
        # Dispatches mapping and filesystem inputs to their dedicated parsing paths.
        if isinstance(source, Mapping):
            resolved_base = Path(base_path).expanduser().resolve() if base_path is not None else Path.cwd().resolve()
            return _LoadedConfigSource(requested=self._normalize_mapping(source, path="$", active=set()), base_path=resolved_base)
        if isinstance(source, (str, Path)):
            return self._load_path(Path(source))
        raise HarnessConfigurationError("Harness config source must be a mapping or JSON/YAML path.", details={"actual_type": type(source).__name__})

    def _load_path(self, path: Path) -> _LoadedConfigSource:
        # Reads and parses one supported UTF-8 config file.
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise HarnessConfigurationError("Harness config file does not exist.", details={"path": str(resolved)})
        suffix = resolved.suffix.lower()
        if suffix not in {".json", ".yaml", ".yml"}:
            raise HarnessConfigurationError("Harness config file extension is unsupported.", details={"path": str(resolved), "extension": suffix})
        text = self._read_config_text(resolved)
        parsed = self._parse_config_text(text, suffix, resolved)
        if not isinstance(parsed, Mapping):
            raise HarnessConfigurationError("Harness config document must contain an object.", details={"path": str(resolved), "actual_type": type(parsed).__name__})
        return _LoadedConfigSource(requested=self._normalize_mapping(parsed, path="$", active=set()), base_path=resolved.parent)

    def _read_config_text(self, path: Path) -> str:
        # Reads one config file while converting OS/encoding failures into typed context.
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise HarnessConfigurationError("Harness config file is not readable UTF-8 text.", details={"path": str(path)}) from exc

    def _parse_config_text(self, text: str, suffix: str, path: Path) -> Any:
        # Parses JSON or safe YAML without executing application-specific constructors.
        try:
            return json.loads(text) if suffix == ".json" else yaml.safe_load(text)
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise HarnessConfigurationError("Harness config file contains malformed JSON or YAML.", details={"path": str(path), "format": suffix.lstrip(".")}) from exc

    def _validate_config(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        # Validates and normalizes the stable common envelope while preserving open fields.
        config = {str(key): value for key, value in raw.items()}
        self._validate_top_level_keys(config)
        self._validate_schema_version(config)
        config["harness"] = self._validate_harness(config["harness"])
        config["agents"] = self._validate_agents(config["agents"])
        # metadata and orchestration are optional; default absent ones to {} so a
        # single-agent harness stays terse while identity/exports have a stable shape.
        config["metadata"] = self._validate_object_field(config.get("metadata", {}), "metadata")
        config["orchestration"] = self._validate_object_field(config.get("orchestration", {}), "orchestration")
        return config

    def _validate_top_level_keys(self, config: Mapping[str, Any]) -> None:
        # Rejects missing and misspelled top-level behavior fields before hashing.
        unknown = sorted(set(config) - _ALLOWED_TOP_LEVEL)
        missing = sorted(_REQUIRED_TOP_LEVEL - set(config))
        if unknown or missing:
            raise HarnessConfigurationError("Harness config top-level fields do not match the public envelope.", details={"unknown": unknown, "missing": missing, "required": sorted(_REQUIRED_TOP_LEVEL), "optional": sorted(_OPTIONAL_TOP_LEVEL)})

    def _validate_schema_version(self, config: Mapping[str, Any]) -> None:
        # Requires the exact supported schema instead of guessing compatibility.
        version = config.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int) or version != HARNESS_SCHEMA_VERSION:
            raise HarnessVersionError("Unsupported harness configuration schema version.", details={"found": version, "expected": HARNESS_SCHEMA_VERSION})

    def _validate_harness(self, value: Any) -> dict[str, Any]:
        # Validates the implementation *kind* and keeps additional descriptor fields.
        # Version identifies implementation *code*, not behavior config, so it is not
        # read here; it is supplied by the Harness subclass / factory and folded into
        # spec_id by _build_spec. Requiring it here would hard-fail the new schema.
        if not isinstance(value, Mapping):
            raise HarnessConfigurationError("Harness config field 'harness' must be an object.", details={"field": "harness", "actual_type": type(value).__name__})
        harness = {str(key): item for key, item in value.items()}
        harness["type"] = self._required_text(harness.get("type"), "harness.type")
        return harness

    def _validate_agents(self, value: Any) -> list[dict[str, Any]]:
        # Validates the full per-agent shape so the YAML is a trustworthy single source
        # of truth: an invalid hyperparameter fails at load(), not three agents deep.
        if not isinstance(value, list):
            raise HarnessConfigurationError("Harness config field 'agents' must be an array.", details={"field": "agents", "actual_type": type(value).__name__})
        agents: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(value):
            agent = self._validate_agent(item, index)
            name = agent["name"]
            if name in seen:
                raise HarnessConfigurationError("Harness agent names must be unique.", details={"field": f"agents[{index}].name", "name": name})
            seen.add(name)
            agents.append(agent)
        return agents

    def _validate_agent(self, item: Any, index: int) -> dict[str, Any]:
        # Validates one agent entry: required unique name plus optional, open-leaf fields.
        if not isinstance(item, Mapping):
            raise HarnessConfigurationError("Every harness agent entry must be an object.", details={"field": f"agents[{index}]", "actual_type": type(item).__name__})
        agent = {str(key): child for key, child in item.items()}
        agent["name"] = self._required_text(agent.get("name"), f"agents[{index}].name")
        for text_field in ("provider", "model"):
            if text_field in agent:
                agent[text_field] = self._required_text(agent.get(text_field), f"agents[{index}].{text_field}")
        if "system_prompt" in agent:
            self._validate_system_prompt(agent["system_prompt"], index)
        if "params" in agent:
            agent["params"] = self._validate_object_field(agent["params"], f"agents[{index}].params")
        if "tools" in agent:
            agent["tools"] = self._validate_tools(agent["tools"], index)
        return agent

    def _validate_system_prompt(self, value: Any, index: int) -> None:
        # Accepts either inline prompt text or an unresolved {$file: ...} reference.
        if isinstance(value, str):
            return
        if isinstance(value, Mapping) and set(value) == {"$file"}:
            return
        raise HarnessConfigurationError("Harness agent system_prompt must be a string or a {$file: ...} reference.", details={"field": f"agents[{index}].system_prompt", "actual_type": type(value).__name__})

    def _validate_tools(self, value: Any, index: int) -> list[Any]:
        # Requires a list of tool names or tool specs; leaves the spec shape open.
        if not isinstance(value, list):
            raise HarnessConfigurationError("Harness agent tools must be an array.", details={"field": f"agents[{index}].tools", "actual_type": type(value).__name__})
        for tool_index, tool in enumerate(value):
            if not isinstance(tool, (str, Mapping)):
                raise HarnessConfigurationError("Harness agent tool entries must be names or objects.", details={"field": f"agents[{index}].tools[{tool_index}]", "actual_type": type(tool).__name__})
        return list(value)

    def _validate_object_field(self, value: Any, field: str) -> dict[str, Any]:
        # Copies one open mapping field (top-level orchestration or per-agent params).
        if not isinstance(value, Mapping):
            raise HarnessConfigurationError("Harness config field must be an object.", details={"field": field, "actual_type": type(value).__name__})
        return {str(key): item for key, item in value.items()}

    def _required_text(self, value: Any, field: str) -> str:
        # Returns normalized required text and names the invalid config field.
        if not isinstance(value, str) or not value.strip():
            raise HarnessConfigurationError("Harness config field must be a non-empty string.", details={"field": field, "actual_type": type(value).__name__})
        return value.strip()

    # @intent never-fingerprint-credentials
    # Harness specifications are persisted and exported as future training data.
    # Credentials therefore cannot be treated as ordinary hyperparameters, even
    # when a harness factory could technically consume them from this mapping.
    # Rejecting at load keeps secrets out of requested config, resolved config,
    # hashes, local stores, JSONL exports, and error diagnostics in every path.
    # Credentials belong in environment/provider injection outside behavior identity.
    def _reject_credential_keys(self, value: Any, *, path: str, active: set[int]) -> None:
        # Walks config recursively and fails before any credential-like key is retained.
        if isinstance(value, Mapping):
            self._reject_mapping_credentials(value, path=path, active=active)
            return
        if isinstance(value, list):
            self._reject_sequence_credentials(value, path=path, active=active)

    def _reject_mapping_credentials(self, value: Mapping[str, Any], *, path: str, active: set[int]) -> None:
        # Checks one mapping and then descends into its values with cycle protection.
        identity = self._enter_container(value, path, active)
        try:
            for key, child in value.items():
                if HarnessSecretPolicy.is_secret_key(str(key)):
                    raise HarnessCredentialConfigError("Harness config contains a credential-like key.", details={"path": path, "key": str(key)})
                self._reject_credential_keys(child, path=f"{path}.{key}", active=active)
        finally:
            active.remove(identity)

    def _reject_sequence_credentials(self, value: list[Any], *, path: str, active: set[int]) -> None:
        # Descends through one list while rejecting recursive config structures.
        identity = self._enter_container(value, path, active)
        try:
            for index, child in enumerate(value):
                self._reject_credential_keys(child, path=f"{path}[{index}]", active=active)
        finally:
            active.remove(identity)

    def _resolve_value(self, value: Any, base_path: Path, *, path: str, active: set[int]) -> Any:
        # Resolves exact $file mappings and recursively copies all other safe values.
        if isinstance(value, Mapping):
            if "$file" in value:
                return self._resolve_file_reference(value, base_path, path)
            return self._resolve_mapping(value, base_path, path=path, active=active)
        if isinstance(value, list):
            return self._resolve_sequence(value, base_path, path=path, active=active)
        return value

    def _resolve_mapping(self, value: Mapping[str, Any], base_path: Path, *, path: str, active: set[int]) -> dict[str, Any]:
        # Resolves every child in a non-reference mapping with cycle protection.
        identity = self._enter_container(value, path, active)
        try:
            return {str(key): self._resolve_value(child, base_path, path=f"{path}.{key}", active=active) for key, child in value.items()}
        finally:
            active.remove(identity)

    def _resolve_sequence(self, value: list[Any], base_path: Path, *, path: str, active: set[int]) -> list[Any]:
        # Resolves every child in a list with cycle protection.
        identity = self._enter_container(value, path, active)
        try:
            return [self._resolve_value(child, base_path, path=f"{path}[{index}]", active=active) for index, child in enumerate(value)]
        finally:
            active.remove(identity)

    def _resolve_file_reference(self, value: Mapping[str, Any], base_path: Path, path: str) -> dict[str, str]:
        # Replaces one exact local file reference with content and its SHA-256 digest.
        if len(value) != 1:
            raise HarnessFileReferenceError("A $file reference cannot have sibling fields.", details={"path": path, "fields": sorted(str(key) for key in value)})
        reference = value.get("$file")
        if not isinstance(reference, str) or not reference.strip():
            raise HarnessFileReferenceError("A $file reference must be a non-empty string.", details={"path": path, "actual_type": type(reference).__name__})
        candidate = Path(reference).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (base_path / candidate).resolve()
        content = self._read_reference_text(resolved, path)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {"content": content, "sha256": digest}

    def _read_reference_text(self, resolved: Path, path: str) -> str:
        # Reads one referenced regular file as UTF-8 while preserving safe diagnostics.
        if not resolved.is_file():
            raise HarnessFileReferenceError("A $file reference does not point to a regular file.", details={"path": path, "reference": str(resolved)})
        try:
            return resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise HarnessFileReferenceError("A $file reference is not readable UTF-8 text.", details={"path": path, "reference": str(resolved)}) from exc

    def _normalize_mapping(self, value: Mapping[Any, Any], *, path: str, active: set[int]) -> dict[str, Any]:
        # Copies a caller mapping into deterministic JSON-compatible containers.
        identity = self._enter_container(value, path, active)
        try:
            return {str(key): self._normalize_value(child, path=f"{path}.{key}", active=active) for key, child in value.items()}
        finally:
            active.remove(identity)

    def _normalize_value(self, value: Any, *, path: str, active: set[int]) -> Any:
        # Accepts JSON-compatible config values and rejects unstable Python objects.
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float):
            if math.isfinite(value):
                return value
            raise HarnessConfigurationError("Harness config contains a non-finite float.", details={"path": path})
        if isinstance(value, Mapping):
            return self._normalize_mapping(value, path=path, active=active)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return self._normalize_sequence(value, path=path, active=active)
        raise HarnessConfigurationError("Harness config contains a non-JSON value.", details={"path": path, "actual_type": type(value).__name__})

    def _normalize_sequence(self, value: Sequence[Any], *, path: str, active: set[int]) -> list[Any]:
        # Copies one sequence to a JSON array while detecting recursive inputs.
        identity = self._enter_container(value, path, active)
        try:
            return [self._normalize_value(child, path=f"{path}[{index}]", active=active) for index, child in enumerate(value)]
        finally:
            active.remove(identity)

    def _enter_container(self, value: Any, path: str, active: set[int]) -> int:
        # Adds one container identity or rejects a recursive configuration graph.
        identity = id(value)
        if identity in active:
            raise HarnessConfigurationError("Harness config contains a recursive container.", details={"path": path})
        active.add(identity)
        return identity

    # @intent behavior-identity-not-run-identity
    # Small behavior changes must produce a new reusable specification, while
    # repeated executions of that same specification must remain distinct runs.
    # Identity folds the code-supplied version together with the resolved
    # agents/orchestration behavior (including resolved prompt-file contents), so a
    # code change and a config change each fork a new variant. Descriptive metadata
    # is excluded so renaming a harness never silently forks its identity, exactly
    # like run metadata is excluded. Do not reuse this digest as run_id: doing so
    # would overwrite repeated trials and destroy dataset/eval cardinality.
    def _build_spec(self, requested: Mapping[str, Any], resolved: Mapping[str, Any], code_version: str | None) -> HarnessSpec:
        # Builds the immutable specification using SHA-256 canonical behavior identity.
        harness_type = str(resolved["harness"]["type"])
        harness_version = (code_version or "").strip()
        identity_view = {
            "type": harness_type,
            "version": harness_version,
            "agents": resolved["agents"],
            "orchestration": resolved["orchestration"],
        }
        canonical = self.canonical_json(identity_view)
        spec_id = f"hspec_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
        return HarnessSpec(
            schema_version=HARNESS_SCHEMA_VERSION,
            spec_id=spec_id,
            harness_type=harness_type,
            harness_version=harness_version,
            agents=tuple(dict(item) for item in resolved["agents"]),
            orchestration=dict(resolved["orchestration"]),
            metadata=dict(resolved["metadata"]),
            requested_config=dict(requested),
            resolved_config=dict(resolved),
        )


__all__ = ["HarnessConfigLoader"]
