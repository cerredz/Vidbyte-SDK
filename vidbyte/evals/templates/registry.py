"""Registry and resolver for eval template specs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.graders import AllOfGrader
from vidbyte.evals.templates.base import EvalTemplate


class EvalTemplateRegistry:
    """Registry that resolves template names and specs into concrete template instances."""

    def __init__(self) -> None:
        # Initializes an empty template factory mapping.
        self._factories: dict[str, Callable[..., EvalTemplate]] = {}

    def register(self, name: str, factory: Callable[..., EvalTemplate]) -> None:
        # Registers a named template factory and rejects accidental duplicates.
        if name in self._factories:
            raise ValueError(f"Eval template '{name}' is already registered.")
        self._factories[name] = factory

    def create(self, spec: str | Mapping[str, Any] | EvalTemplate) -> EvalTemplate:
        # Resolves a string, mapping, or existing template into an EvalTemplate.
        if isinstance(spec, EvalTemplate):
            return spec
        if isinstance(spec, str):
            return self._create_from_name(spec, {})
        if isinstance(spec, Mapping):
            return self._create_from_mapping(spec)
        raise TypeError(f"Unsupported eval template spec type: {type(spec).__name__}")

    def build_grader(self, templates: Sequence[EvalTemplate]) -> BaseGrader:
        # Builds one concrete grader from a sequence of templates.
        if not templates:
            raise ValueError("At least one eval template is required.")
        graders = [self._build_single_grader(template) for template in templates]
        return graders[0] if len(graders) == 1 else AllOfGrader(graders)

    def _create_from_mapping(self, spec: Mapping[str, Any]) -> EvalTemplate:
        # Resolves a mapping with name and optional options fields.
        name = spec.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Eval template spec requires a non-empty string 'name'.")
        options = spec.get("options", {})
        if not isinstance(options, Mapping):
            raise ValueError("Eval template spec 'options' must be an object.")
        return self._create_from_name(name, dict(options))

    def _create_from_name(self, name: str, options: Mapping[str, Any]) -> EvalTemplate:
        # Instantiates a registered template by name.
        factory = self._factories.get(name)
        if factory is None:
            raise ValueError(f"Unknown eval template: {name}")
        try:
            return factory(**options)
        except TypeError as exc:
            raise ValueError(f"Invalid options for eval template '{name}': {exc}") from exc

    def _build_single_grader(self, template: EvalTemplate) -> BaseGrader:
        # Builds and validates one grader from one template.
        grader = template.build_grader()
        if not isinstance(grader, BaseGrader):
            raise TypeError(f"Eval template '{template.name}' returned {type(grader).__name__}, not BaseGrader.")
        return grader
