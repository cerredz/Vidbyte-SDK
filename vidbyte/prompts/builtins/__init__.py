# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines package exports for prompts builtins.
# Purpose: Exposes default prompt registration helpers.
# Architecture & Functions:
#   - Exports register_defaults.
# Codebase Relation:
#   - Entry point for loading built-in prompts inside the SDK.
# ==============================================================================

from __future__ import annotations

from vidbyte.prompts.builtins.vidbyte_defaults import register_defaults

__all__ = [
    "register_defaults",
]
