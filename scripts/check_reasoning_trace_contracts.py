"""Validate the public contracts declared by all strategy-specific trace tools."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from vidbyte.context.manager import ContextManager
from vidbyte.tools.builtins.reasoning import (
    REASONING_TRACE_TOOL_CLASSES,
    ReasoningTraceCatalog,
)

EXAMPLE_MARKERS = re.compile(r"\b(?:example|examples|e\.g\.|for instance)\b", re.IGNORECASE)
SENTENCE = re.compile(r"[^.!?]+[.!?](?=\s|$)")
COMMON_PARAMETERS = frozenset({"question", "confidence", "next_action"})


def sentence_count(value: str) -> int:
    return len(SENTENCE.findall(value.strip()))


def main() -> int:
    definitions = ReasoningTraceCatalog.definitions()
    failures: list[str] = []
    if len(definitions) != 182 or len(REASONING_TRACE_TOOL_CLASSES) != 182:
        failures.append(
            f"expected 182 definitions and classes, got {len(definitions)} and {len(REASONING_TRACE_TOOL_CLASSES)}"
        )

    shapes: set[tuple[str, ...]] = set()
    for definition in definitions:
        tool_class = ReasoningTraceCatalog.tool_class(definition.skill_name)
        spec = tool_class(ContextManager()).spec()
        shapes.add(tuple(parameter.name for parameter in spec.parameters))
        if spec.name != definition.skill_name:
            failures.append(f"{definition.skill_name}: spec name is {spec.name!r}")
        if not 6 <= sentence_count(spec.description) <= 8:
            failures.append(f"{definition.skill_name}: tool description has {sentence_count(spec.description)} sentences")
        if EXAMPLE_MARKERS.search(spec.description):
            failures.append(f"{definition.skill_name}: tool description contains an example marker")
        parameter_names = {parameter.name for parameter in spec.parameters}
        if not parameter_names - COMMON_PARAMETERS:
            failures.append(f"{definition.skill_name}: no strategy-specific parameter is declared")
        if len(parameter_names) != len(spec.parameters):
            failures.append(f"{definition.skill_name}: duplicate parameter names")
        for parameter in spec.parameters:
            if not 6 <= sentence_count(parameter.description) <= 8:
                failures.append(
                    f"{definition.skill_name}.{parameter.name}: description has {sentence_count(parameter.description)} sentences"
                )
            if EXAMPLE_MARKERS.search(parameter.description):
                failures.append(f"{definition.skill_name}.{parameter.name}: description contains an example marker")

    if len(shapes) < 12:
        failures.append(f"strategy-specific parameter shapes are not varied enough: {len(shapes)} distinct shapes")
    if failures:
        print("reasoning trace contract check failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print(f"reasoning trace contracts: ok ({len(definitions)} tools, {len(shapes)} shapes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
