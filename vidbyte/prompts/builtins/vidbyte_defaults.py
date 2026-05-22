# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the prompt default registration hook for the Vidbyte SDK.
# Purpose: Keeps the class-based registry available without loading translation files.
# Architecture & Functions:
#   - register_defaults(registry): Central function registering standard default prompt classes.
# Codebase Relation:
#   - Automatically called by PromptRegistry or when the client initializes.
# Similar Files:
#   - None (houses built-in registration routines specifically)
# ==============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vidbyte.prompts.registry import PromptRegistry


def register_defaults(registry: PromptRegistry) -> None:
    """No-op until class-based prompt translations are reintroduced."""
    return None
