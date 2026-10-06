"""Context Protocol Header

Description:
    Pure, side-effect-free helper functions for the prosecutor/defender/judge
    context-window algorithm runtime adapter.
Purpose:
    Keeps deterministic serialization, provenance extraction, and content-free
    error mapping out of the runtime adapter module so the orchestration file
    holds only stage classes and protocol logic.
Architecture:
    Module-level free functions with no vidbyte runtime dependencies. Every
    helper is total, deterministic, and safe to call on untrusted stage output.
Key Functions:
    - dump_payload: Deterministically encode an exact stage payload as JSON.
    - runner_model_name: Read a provenance model label off a runner instance.
    - safe_tool_call_summary: Strip arguments/results from a tool-call record.
    - optional_int: Coerce accounting values to int, rejecting booleans.
    - json_safe_mapping: Produce a deterministic JSON-safe metadata copy.
    - safe_error_category: Map an exception into a stable public category.
    - safe_trace_error: Replace an exception body with its type name for tracing.
Relations:
    Imported by vidbyte/agents/algorithms/prosecutor_defender_judge.py.
Similar Files:
    - vidbyte/lib/agents/modality_detector.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from vidbyte.lib.errors import ConfigurationError


def dump_payload(payload: Mapping[str, Any]) -> str:
    # Encodes exact values deterministically without normalizing their contents.
    return json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"))


def runner_model_name(runner: object) -> str | None:
    # Reads a model label for provenance without copying runner configuration.
    config = getattr(runner, "config", None)
    value = getattr(config, "model", None) or getattr(config, "model_name", None) or getattr(runner, "model", None)
    return str(value) if value is not None else None


def safe_tool_call_summary(call: object) -> dict[str, Any]:
    # Removes arguments/results while retaining only tool identity and lifecycle state.
    state = getattr(getattr(call, "state", None), "value", getattr(call, "state", None))
    return {"tool_name": str(getattr(call, "tool_name", "unknown")), "state": str(state) if state is not None else "unknown"}


def optional_int(value: object) -> int | None:
    # Converts accounting values to integers without accepting booleans.
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    # Produces a deterministic JSON-safe copy for public metadata provenance.
    serialized = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, default=str)
    parsed = json.loads(serialized)
    return dict(parsed) if isinstance(parsed, dict) else {}


def safe_error_category(exc: Exception) -> str:
    # Maps failures into stable categories without exposing provider response text.
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, (ConfigurationError, ValueError, ValidationError)):
        return "validation"
    return "execution"


def safe_trace_error(exc: BaseException) -> RuntimeError:
    # Replaces a potentially sensitive exception body with its type for tracing.
    return RuntimeError(type(exc).__name__)


__all__ = [
    "dump_payload",
    "json_safe_mapping",
    "optional_int",
    "runner_model_name",
    "safe_error_category",
    "safe_tool_call_summary",
    "safe_trace_error",
]
