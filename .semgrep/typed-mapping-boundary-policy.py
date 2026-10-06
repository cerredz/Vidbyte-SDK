from collections.abc import Mapping
from typing import Any


# ruleid: no-untyped-mapping-fallback
def rejects_untyped_mapping_fallback(values: object) -> int:
    if not isinstance(values, Mapping):
        return 0
    return len(values)


def accepts_explicit_optional_mapping(values: Mapping[str, object] | None) -> int:
    if values is None:
        return 0
    return len(values)


# ruleid: no-untyped-mapping-fallback
def rejects_any_mapping_fallback(values: Any) -> int:
    if not isinstance(values, dict):
        return 0
    return len(values)
