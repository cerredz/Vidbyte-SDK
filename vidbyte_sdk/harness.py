from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any, Generic, TypeAlias, TypeVar, cast

VIDBYTE_SDK_VERSION = "0.1.0"

InputT = TypeVar("InputT")
ResultT = TypeVar("ResultT")

HarnessContext: TypeAlias = Mapping[str, Any]
HarnessRunFunction: TypeAlias = Callable[[InputT, HarnessContext], ResultT | Awaitable[ResultT]]


class VidbyteSdkError(ValueError):
    def __init__(self, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.details = details


@dataclass(frozen=True, slots=True)
class Harness(Generic[InputT, ResultT]):
    name: str
    run: HarnessRunFunction[InputT, ResultT]
    description: str | None = None


def define_harness(
    *,
    name: str,
    run: HarnessRunFunction[InputT, ResultT],
    description: str | None = None,
) -> Harness[InputT, ResultT]:
    normalized_name = _normalize_name(name)
    if not callable(run):
        raise VidbyteSdkError("Harness definition must include a callable run function.")

    return Harness(name=normalized_name, description=description, run=run)


async def run_harness(
    harness: Harness[InputT, ResultT],
    input: InputT,
    context: HarnessContext | None = None,
) -> ResultT:
    if not isinstance(harness, Harness):
        raise VidbyteSdkError("A valid Harness instance is required.")

    result = harness.run(input, context or {})
    if isawaitable(result):
        return await result
    return cast(ResultT, result)


def _normalize_name(name: str) -> str:
    if not isinstance(name, str):
        raise VidbyteSdkError("Harness name must be a string.")

    normalized_name = name.strip()
    if not normalized_name:
        raise VidbyteSdkError("Harness name must be non-empty.")
    return normalized_name
