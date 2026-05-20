from __future__ import annotations

from vidbyte.prompts.translations.harnesses.context_remover import (
    CONTEXT_REMOVER_PURIFY_KEY,
    CONTEXT_REMOVER_PURIFY_TEMPLATE,
)


def register_defaults(registry: object) -> None:
    """Register prompt defaults with a compatible prompt registry."""

    register = getattr(registry, "register", None)
    if register is None:
        return
    register(CONTEXT_REMOVER_PURIFY_KEY, CONTEXT_REMOVER_PURIFY_TEMPLATE)


__all__ = ["register_defaults"]
