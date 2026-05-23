# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the abstract BasePrompt class and prompt-related exceptions.
# Purpose: Formalizes prompt structures, handles interpolation rendering,
#          and validates dynamic inputs in the Vidbyte SDK.
# Architecture & Functions:
#   - PromptError (class): Base exception class for prompts namespace.
#   - PromptRenderError (class): Error thrown during rendering failures.
#   - PromptNotFoundError (class): Error thrown during lookup failures.
#   - BasePrompt (ABC): Defines key, version, template, variables, and render logic.
# Codebase Relation:
#   - Parent interface for concrete prompt classes and overrides.
# Similar Files:
#   - vidbyte/tools/base.py (abstract class for tools subsystem)
# ==============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from vidbyte.prompts.types import PromptKey, PromptVersion, RenderedPrompt


class PromptError(Exception):
    """Base exception class for all prompt registry operations."""
    pass


class PromptRenderError(PromptError):
    """Raised when rendering a prompt fails due to missing or invalid variables."""
    pass


class PromptNotFoundError(PromptError):
    """Raised when a requested prompt key is not registered."""
    pass


class BasePrompt(ABC):
    """
    Abstract Base Class for every SDK prompt.
    Encapsulates identifiers, semver tags, prompt templates, and variables.
    """

    @abstractmethod
    def key(self) -> PromptKey:
        """Returns the unique PromptKey identifying this prompt."""
        pass

    @abstractmethod
    def version(self) -> str:
        """Returns the semver version string (e.g. '1.0.0')."""
        pass

    @abstractmethod
    def template(self) -> str:
        """Returns the unrendered raw prompt template with {variable} placeholders."""
        pass

    @abstractmethod
    def variables(self) -> Dict[str, str]:
        """Returns a dict of variable_name -> description for template parameters."""
        pass

    def render(self, **kwargs) -> RenderedPrompt:
        """
        Interpolates parameters into the raw prompt template.
        Validates that all declared variables are supplied.
        """
        declared_vars = self.variables()
        missing = [v for v in declared_vars if v not in kwargs]
        if missing:
            raise PromptRenderError(
                f"Missing required rendering variables for prompt {self.key()}: {missing}"
            )
        try:
            rendered_text = self.template().format(**kwargs)
        except KeyError as e:
            raise PromptRenderError(
                f"Formatting failed for prompt {self.key()}: missing key {e} in provided values."
            )
        except Exception as e:
            raise PromptRenderError(
                f"Unexpected rendering error for prompt {self.key()}: {str(e)}"
            )

        return RenderedPrompt(
            key=self.key(),
            version=self.version(),
            text=rendered_text
        )

    def as_version(self) -> PromptVersion:
        """Converts the prompt class details into a PromptVersion metadata container."""
        return PromptVersion(
            key=self.key(),
            version=self.version(),
            template=self.template(),
            variables=self.variables(),
            description=self.__doc__ or ""
        )
