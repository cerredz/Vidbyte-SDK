# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Top-level initializer for the Vidbyte SDK prompts package.
# Purpose: Dynamically registers and exports all registered prompt assets.
# Architecture & Functions:
#   - Exposes Prompt and Prompts catalog models.
#   - Automatically inspects the Prompt catalog to populate globals with direct imports.
# Codebase Relation:
#   - Canonical entrance for fetching prompt templates or raw prompt strings.
# Similar Files:
#   - vidbyte/prompts/catalog.py (prompt catalog implementation)
# ==============================================================================

from __future__ import annotations

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import PromptRecord, Prompts
from vidbyte.prompts.prompts import VMAOPrompts

_prompts = Prompts()

for _prompt_key, _import_name in _prompts.import_names().items():
    globals()[_import_name] = _prompts.get(_prompt_key)

_direct_prompt_exports = tuple(sorted(_prompts.import_names().values()))

__all__ = [
    "Prompt",
    "PromptRecord",
    "Prompts",
    "VMAOPrompts",
] + list(_direct_prompt_exports)
