"""Context Protocol Header

Description:
    Central registry of the SDK-owned components a configuration document may declare.
Purpose:
    Gives the declarative YAML surface one place that turns a ``{ref, options}`` entry into a real
    tool, middleware, or context item, so the loader resolves references through a registry instead
    of hand-rolled per-kind lookups and every document sees the same reference vocabulary.
Architecture:
    - ComponentRegistry: Lazily discovered reference-name-to-class catalogs per component kind.
Key Functions:
    - build_tools/build_middleware/build_context_items: Build every declared entry in document order.
    - build: Instantiates one registered component from a reference name and its options.
    - names: Returns the reference names a document may declare for one component kind.
Relations:
    Consumed by vidbyte.config.loader.YamlLoader.build_agent. Discovers classes from the public
    exports of vidbyte.tools.builtins, vidbyte.middleware, and vidbyte.context.primitives.
Non-Goals:
    Never imports a module, attribute, or callable named by a document. The packages scanned here
    are fixed in this file, and a reference is only ever a key looked up in the resulting mapping.
Similar Files:
    - vidbyte/lib/registries/runtimes.py: Same lazy-import registry shape for runtime classes.
    - vidbyte/lib/registries/actors.py: Name-keyed registry of prebuilt actor classes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import ModuleType
from typing import TYPE_CHECKING, Any, ClassVar

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.tools.catalog import Tools

# Document field name mapped to the singular label used when naming a reference in an error.
_LABELS: Mapping[str, str] = {"tools": "tool", "middleware": "middleware", "context_items": "context item"}


class ComponentRegistry:
    """Registry of the tool, middleware, and context-item classes a document may name."""

    # Reference-name-to-class catalogs, discovered once per kind and shared by every loader.
    _CATALOGS: ClassVar[dict[str, dict[str, type]]] = {}

    @classmethod
    def build_tools(cls, definitions: Sequence[Any]) -> "Tools":
        # Builds every declared tool entry into one agent-local catalog, in document order.
        from vidbyte.tools.catalog import Tools

        return Tools(cls._build_all(definitions, "tools"))

    @classmethod
    def build_middleware(cls, definitions: Sequence[Any]) -> tuple[Any, ...]:
        # Builds every declared middleware entry in document order.
        return cls._build_all(definitions, "middleware")

    @classmethod
    def build_context_items(cls, definitions: Sequence[Any]) -> tuple[Any, ...]:
        # Builds every declared context-item entry in document order.
        return cls._build_all(definitions, "context_items")

    @classmethod
    def build(cls, kind: str, ref: str, options: Mapping[str, Any]) -> Any:
        # Instantiates one registered component, passing the entry's validated options as keyword arguments.
        catalog = cls._catalog(kind)
        component = catalog.get(ref)
        if component is None:
            raise ConfigurationError(f"'{ref}' is not a {_LABELS[kind]} this SDK registers, so a document cannot name it.", details={"reference": ref, "kind": kind, "available": sorted(catalog)})
        try:
            return component(**dict(options))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(f"Registered {_LABELS[kind]} '{ref}' rejected the options the document declared: {error}", details={"reference": ref, "kind": kind, "options": sorted(options)}) from error

    @classmethod
    def names(cls, kind: str) -> tuple[str, ...]:
        # Returns every reference name a document may declare for one component kind.
        return tuple(sorted(cls._catalog(kind)))

    @classmethod
    def _build_all(cls, definitions: Sequence[Any], kind: str) -> tuple[Any, ...]:
        # Builds each declared entry, re-pointing any failure at the document position it came from.
        built: list[Any] = []
        for index, definition in enumerate(definitions):
            try:
                built.append(cls.build(kind, definition.ref, definition.options))
            except ConfigurationError as error:
                error.details.setdefault("field", definition.path or f"agent.{kind}[{index}]")
                raise
        return tuple(built)

    @classmethod
    def _catalog(cls, kind: str) -> dict[str, type]:
        # Returns one kind's catalog, discovering it on first use so importing this module stays cheap.
        if kind not in cls._CATALOGS:
            cls._CATALOGS[kind] = cls._discover(kind)
        return cls._CATALOGS[kind]

    @classmethod
    def _discover(cls, kind: str) -> dict[str, type]:
        # @intent fixed-scan-targets
        # The packages scanned here are written in this file, never taken from a document, so a
        # reference can only select a class the SDK already exports; it can never name an import.
        from vidbyte.context import primitives
        from vidbyte.middleware import AgentMiddleware
        from vidbyte.tools import builtins
        from vidbyte.tools.base import BaseTool
        import vidbyte.middleware as middleware

        match kind:
            case "tools":
                return cls._classes(builtins, lambda value: issubclass(value, BaseTool) and value is not BaseTool)
            case "middleware":
                return cls._classes(middleware, lambda value: issubclass(value, AgentMiddleware) and value is not AgentMiddleware)
            case "context_items":
                return cls._classes(primitives, lambda value: callable(getattr(value, "to_context_text", None)) and not getattr(value, "_is_protocol", False))
            case other:
                raise ConfigurationError(f"'{other}' is not a registered component kind.", details={"kind": other, "available": sorted(_LABELS)})

    @staticmethod
    def _classes(module: ModuleType, accepted: Callable[[type], bool]) -> dict[str, type]:
        # Collects the module's public classes that pass one kind's own membership test.
        return {name: value for name, value in vars(module).items() if not name.startswith("_") and isinstance(value, type) and accepted(value)}


__all__ = ["ComponentRegistry"]
