"""Context Protocol Header

Description:
    Implements EvalClient, the public developer-facing namespace client.
Purpose:
    Serves as the root endpoint mapping construction patterns for suites, runners,
    and history logs on VidbyteSDK.evals.
Architecture:
    - EvalClient: Factory client returning EvalSuite, EvalRunner, and wrapping EvalRegistry.
Functions:
    - runner: Instantiates an EvalRunner bound to a target and grader.
    - suite: Instantiates a named EvalSuite holding test cases.
    - registry: Exposes the shared persisted EvalRegistry instance.
Relations:
    Related to VidbyteSDK (instantiated on sdk.evals) and coordinates all child evals submodules.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.registry import EvalRegistry
from vidbyte.evals.runner import EvalRunner
from vidbyte.evals.suite import EvalSuite
from vidbyte.evals.types import EvalCase


class EvalClient:
    """The public client exposing the evaluation registry, runner, and suite constructor primitives."""

    def __init__(self, db_path: str | Path = ".vidbyte_evals.db") -> None:
        # Instantiates the EvalClient and hooks it to a SQLite-backed registry database path.
        self._registry = EvalRegistry(db_path)

    def runner(self, target: object, *, grader: BaseGrader, **kwargs: Any) -> EvalRunner:
        # Instantiates and returns an EvalRunner configured for the specified execution target.
        return EvalRunner(target, default_grader=grader, **kwargs)

    def suite(self, name: str, cases: Sequence[EvalCase]) -> EvalSuite:
        # Instantiates and returns a named EvalSuite carrying a list of evaluation cases.
        return EvalSuite(name=name, cases=cases)

    @property
    def registry(self) -> EvalRegistry:
        # Returns the underlying active EvalRegistry instance.
        return self._registry
