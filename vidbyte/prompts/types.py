# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the core dataclasses for the Vidbyte SDK Prompt Registry.
# Purpose: Establishes unique identification, versioning metadata, and rendering
#          outputs for SDK prompts.
# Architecture & Functions:
#   - PromptKey (dataclass): Namespaced prompt identifier (namespace, name) with custom __str__ and __hash__.
#   - PromptVersion (dataclass): Full versioned prompt metadata schema.
#   - RenderedPrompt (dataclass): Final text representation post variable interpolation.
# Codebase Relation:
#   - Forms the data modeling backbone for `vidbyte.prompts`.
# Similar Files:
#   - vidbyte/tools/types.py (dataclasses for tools subsystem)
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class PromptKey:
    """
    Uniquely identifies a prompt in the registry.
    Combines a namespace (e.g. 'strategies.react') and a name (e.g. 'system').
    """
    namespace: str
    name: str

    def __str__(self) -> str:
        return f"{self.namespace}.{self.name}"

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PromptKey):
            return False
        return self.namespace == other.namespace and self.name == other.name


@dataclass(frozen=True, slots=True)
class PromptVersion:
    """Metadata specification of a registered prompt template."""
    key: PromptKey
    version: str  # Semver format (e.g. '1.0.0')
    template: str
    variables: Dict[str, str]  # Mappings of variable_name -> description
    description: str


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """The outcome of injecting variables into a prompt template."""
    key: PromptKey
    version: str
    text: str
