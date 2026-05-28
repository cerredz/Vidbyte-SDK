"""Context Protocol Header

Description:
    Internal library helpers for the vidbyte.evals subsystem.
Purpose:
    Exposes TemplatesRegistry for managing and overriding judge prompt templates.
Architecture:
    Re-exports TemplatesRegistry from template_registry module.
Relations:
    Used by all judge files in vidbyte/evals/llm_as_a_judge/.
"""

from __future__ import annotations

from vidbyte.lib.eval.template_registry import TemplatesRegistry

__all__ = ["TemplatesRegistry"]
