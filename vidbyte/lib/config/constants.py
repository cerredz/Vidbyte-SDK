"""Context Protocol Header

Description:
    Shared configuration constants for model providers and API endpoints.
Purpose:
    Exposes central configuration maps for backward compatibility by delegating to ProviderModelRegistry.
Architecture:
    - Exposes API_KEY_ENV_VARS and DEFAULT_ENDPOINTS dicts.
Key Functions:
    None.
Relations:
    Imported by configuration base modules, dataclasses, and tests. Delegated to ProviderModelRegistry.
Similar Files:
    - vidbyte/lib/models/registry.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vidbyte.lib.enums import ModelProvider

from vidbyte.lib.registries.models import ProviderModelRegistry

API_KEY_ENV_VARS: dict[ModelProvider, str] = ProviderModelRegistry.API_KEY_ENV_VARS
DEFAULT_ENDPOINTS: dict[ModelProvider, str] = ProviderModelRegistry.DEFAULT_ENDPOINTS

__all__ = [
    "API_KEY_ENV_VARS",
    "DEFAULT_ENDPOINTS",
]

