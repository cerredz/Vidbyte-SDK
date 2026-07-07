"""
FILE: vidbyte/agents/runtimes/configs.py

PURPOSE:
    Defines configuration classes for Linear, MCTS Search, and Actor runtimes. Allows developers to cleanly configure runtime settings inside a single structured parameter, avoiding main agent constructor clutter.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/agents layer, which owns agent construction, runtime dispatch, handoff, fork, and execution state.
    It should be read with `vidbyte/agents/runtimes/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.enums: imported by this file.
    - vidbyte.lib.errors: imported by this file.

FUNCTION INVENTORY:
    - LinearRuntime (class): public or navigational symbol owned here.
    - MctsSearchRuntime (class): public or navigational symbol owned here.
    - ActorRuntime (class): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - ConfigurationError: raised, returned, or imported by this file. Keep context safe and grepable.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-agent-behavior.py, scripts/test-new-runners.py, and agent-runtime scripts when changing behavior.

CONCURRENCY MODEL:
    - No explicit concurrency primitive; keep future mutable state local to calls unless documented here.
"""
from __future__ import annotations
from typing import Any, Sequence, TYPE_CHECKING
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.actor.actor import PrebuiltActor


class LinearRuntime:
    """Configurable settings for the Linear execution runtime."""

    def __init__(self) -> None:
        # Initializes a linear runtime configuration.
        self.runtime_type = AgentRuntimeType.LINEAR


class MctsSearchRuntime:
    """Configurable settings for the Branching Search MCTS execution runtime."""

    def __init__(self) -> None:
        # Initializes an MCTS search runtime configuration.
        self.runtime_type = AgentRuntimeType.MCTS_SEARCH


class ActorRuntime:
    """Configurable settings for the Asynchronous Actor Model execution runtime."""

    def __init__(
        self,
        *,
        topology: AgentRuntimeType | str = AgentRuntimeType.ACTOR_MODEL_P2P,
        dynamic_actors: bool = False,
        max_loop: int = 20,
        termination_mode: str = "coordinator",
        worker_model: str | None = None,
        include_actors: Sequence[type[PrebuiltActor]] | None = None,
    ) -> None:
        # Initializes an actor runtime configuration with specific topologies and prebuilt actors.
        from vidbyte.lib.registries.models import ProviderModelRegistry
        self.runtime_type = AgentRuntimeType(topology)
        if max_loop < 1:
            raise ConfigurationError("ActorRuntime max_loop must be at least 1.")
        _valid_termination_modes = ("coordinator", "quiescence")
        if termination_mode not in _valid_termination_modes:
            raise ConfigurationError(
                f"ActorRuntime termination_mode must be one of {_valid_termination_modes}, "
                f"got '{termination_mode}'."
            )
        if worker_model is not None:
            ProviderModelRegistry.validate_model(worker_model)
        self.dynamic_actors = dynamic_actors
        self.max_loop = max_loop
        self.termination_mode = termination_mode
        self.worker_model = worker_model
        self.include_actors = include_actors
