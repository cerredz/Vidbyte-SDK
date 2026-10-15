"""FILE: tests/test_lib_config_loader_continual_trace_iterations.py

PURPOSE:
    Regression tests for the descriptor loader exported from vidbyte.lib.config: the
    `max_trace_iterations` value of a continual-trace agent YAML reaches the descriptor's
    own type check unchanged, so a boolean, a float, or a quoted string fails as a
    ConfigurationError instead of being coerced by int(), while a plain integer and an
    omitted key still load.

ROLE IN CODEBASE:
    Exercises YamlLoader._build_continual_trace_agent in vidbyte/lib/config/loader.py
    through the public load_agent entry point.

ARCHITECTURE NOTE:
    Each test writes a small continual-trace YAML into pytest's tmp_path and loads it, so
    the real parse, dispatch, and ContinualTraceAgentDescriptor validation path runs. No
    model calls.

COMMON MODIFICATION PATTERNS:
    Add a case here when the descriptor's accepted range or type rule for
    max_trace_iterations changes.

KNOWN EDGE CASES:
    YAML 1.1 reads `true` as a bool, `2.9` as a float, and `'3'` as a str; each must be
    refused exactly as the descriptor refuses the same value passed directly.

RELATED DOCS:
    vidbyte/lib/dataclasses/continual_trace_descriptor.py (_validate_iterations) owns the
    type and range check.

TESTS:
    python -m pytest tests/test_lib_config_loader_continual_trace_iterations.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vidbyte.lib.config import YamlLoader
from vidbyte.lib.errors import ConfigurationError

HEAD = "agent_type: continual_trace\nname: ticket-tracer\nschema:\n  summary: str\n"


def _write(tmp_path: Path, tail: str) -> Path:
    path = tmp_path / "trace.yaml"
    path.write_text(HEAD + tail, encoding="utf-8")
    return path


@pytest.mark.parametrize("value", ["true", "2.9", "'3'"])
def test_non_integer_iterations_are_refused(tmp_path: Path, value: str) -> None:
    path = _write(tmp_path, f"max_trace_iterations: {value}\n")
    with pytest.raises(ConfigurationError, match="max_trace_iterations must be an integer"):
        YamlLoader().load_agent(path)


def test_integer_iterations_load(tmp_path: Path) -> None:
    path = _write(tmp_path, "max_trace_iterations: 2\n")
    assert YamlLoader().load_agent(path).max_trace_iterations == 2


def test_omitted_iterations_default_to_three(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    assert YamlLoader().load_agent(path).max_trace_iterations == 3
