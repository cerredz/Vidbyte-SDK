"""Context Protocol Header

Description:
    Defines the Environment contract, the TaskGenerator protocol, and the
    StaticTaskSet adapter for hand-written task lists.
Purpose:
    Encodes the five-part environment anatomy (world, action surface, task
    generator, verifier, difficulty) with seeded deterministic materialization
    and the environment-authority rule over the agent tool surface.
Architecture:
    - TaskGenerator: Protocol minting EnvTasks from a seed and knobs.
    - StaticTaskSet: TaskGenerator over a fixed sequence of prebuilt tasks.
    - Environment: ABC with setup/verify/teardown plus the tools() authority filter.
Relations:
    Consumed by vidbyte.environments.runner, resolver, audit, and registry.
Similar Files:
    - vidbyte/evals/suite.py: Equivalent aggregate for stateless eval cases.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from vidbyte.environments.types import EnvSession, EnvTask, Reward
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.catalog import Tools


@runtime_checkable
class TaskGenerator(Protocol):
    """Protocol for objects that mint EnvTasks deterministically from a seed."""

    def generate(self, seed: int, **knobs: Any) -> EnvTask:
        """Mint one task; equal seeds and knobs must produce equal tasks."""
        ...


class StaticTaskSet:
    """TaskGenerator over a fixed sequence of prebuilt EnvTasks."""

    def __init__(self, tasks: Sequence[EnvTask]) -> None:
        # Stores the fixed task tuple and rejects empty sets up front.
        self._tasks = tuple(tasks)
        if not self._tasks:
            raise ConfigurationError("StaticTaskSet requires at least one EnvTask.")

    def generate(self, seed: int, **knobs: Any) -> EnvTask:
        """Return the task at seed modulo the set size, keeping the seeded convention valid."""
        del knobs
        return self._tasks[seed % len(self._tasks)]

    def __iter__(self) -> Iterator[EnvTask]:
        # Iterates the fixed tasks in declaration order.
        return iter(self._tasks)

    def __len__(self) -> int:
        # Returns the number of fixed tasks.
        return len(self._tasks)


class Environment(ABC):
    """Resettable world plus tool surface, seeded task generator, and verifier."""

    name: str = "environment"
    version: str = "0.1.0"
    generator: TaskGenerator

    @abstractmethod
    def setup(self, task: EnvTask) -> EnvSession:
        """Materialize the world deterministically from task.seed and return a session."""
        ...

    @abstractmethod
    async def verify(self, session: EnvSession, trajectory: Sequence[Mapping[str, Any]]) -> Reward:
        """Score the final world state out-of-band and return a Reward."""
        ...

    @abstractmethod
    def teardown(self, session: EnvSession) -> None:
        """Release the session's materialized world resources."""
        ...

    def permitted_tool_names(self, session: EnvSession) -> tuple[str, ...] | None:
        """Return the pinned action-surface names, or None to permit any requested tool."""
        del session
        return None

    def tools(self, session: EnvSession, requested: Tools | None = None) -> Tools:
        """Apply the authority rule: environment tools first, permitted requests second."""
        # The environment owns the action surface; requests only select within it.
        catalog = session.tools
        if requested is None:
            return catalog
        permitted = self.permitted_tool_names(session)
        dropped: list[str] = []
        for tool in requested:
            if tool.name in catalog.names():
                dropped.append(tool.name)
                continue
            if permitted is not None and tool.name not in permitted:
                dropped.append(tool.name)
                continue
            catalog = catalog.add(tool)
        if dropped:
            session.metadata.setdefault("dropped_tools", []).extend(dropped)
        return catalog


__all__ = [
    "Environment",
    "StaticTaskSet",
    "TaskGenerator",
]
