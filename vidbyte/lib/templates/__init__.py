"""Context Protocol Header

Description:
    Exports the context window template validation infrastructure.
Purpose:
    Provides a single import path for all template types used by test harnesses
    and algorithm validation scripts.
Architecture:
    - ContextWindowTemplate and TemplateViolation from base module.
    - ReflexionContextWindowTemplate from reflexion module.
Relations:
    Consumed by tests and scripts. Imports RecorderBase from
    vidbyte.context.templates.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate, TemplateViolation
from vidbyte.lib.templates.reflexion import ReflexionContextWindowTemplate

__all__ = [
    "ContextWindowTemplate",
    "ReflexionContextWindowTemplate",
    "TemplateViolation",
]
