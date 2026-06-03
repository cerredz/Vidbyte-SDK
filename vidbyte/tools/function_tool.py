from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from typing import Any, get_type_hints

from pydantic import BaseModel, ValidationError, create_model

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class FunctionTool(BaseTool):
    """Adapter that turns a Python callable into a Vidbyte tool."""

    def __init__(self, func: Callable[..., Any], *, name: str | None = None, description: str | None = None, permission: ToolPermission = ToolPermission.SAFE, output_schema: type | None = None) -> None:
        # Build a tool from a callable with optional name, description, permission, and output schema.
        if not callable(func):
            raise TypeError("FunctionTool requires a callable.")
        self.func = func
        self._name = name or func.__name__
        self._description = description or _docstring_summary(func) or "Custom function tool."
        self._permission = permission
        self._output_schema = output_schema
        self.args_model = _build_args_model(func, self._name)
        self._spec = self._build_spec()
        self.__name__ = self._name
        self.__doc__ = getattr(func, "__doc__", None)
        self.__module__ = getattr(func, "__module__", self.__class__.__module__)

    @classmethod
    def from_function(cls, func: Callable[..., Any], *, name: str | None = None, description: str | None = None, permission: ToolPermission = ToolPermission.SAFE, output_schema: type | None = None) -> "FunctionTool":
        # Alternate constructor that mirrors __init__ for ergonomic one-liner usage.
        return cls(func, name=name, description=description, permission=permission, output_schema=output_schema)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)

    def spec(self) -> ToolSpec:
        return self._spec

    def validate_call(self, call: ToolCall) -> str | None:
        try:
            self.args_model.model_validate(dict(call.arguments))
        except ValidationError as exc:
            return _validation_message(exc)
        return None

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            model = self.args_model.model_validate(dict(call.arguments))
        except ValidationError as exc:
            return ToolResult.failure(self.name, _validation_message(exc), metadata={"error_type": "validation"})

        kwargs = model.model_dump()
        try:
            if inspect.iscoroutinefunction(self.func):
                value = await self.func(**kwargs)
            else:
                value = await asyncio.to_thread(self.func, **kwargs)
        except Exception as exc:
            return ToolResult.failure(self.name, str(exc), metadata={"error_type": exc.__class__.__name__})

        return ToolResult.success(
            self.name,
            _stringify_output(value),
            metadata={
                "function": f"{getattr(self.func, '__module__', '')}.{getattr(self.func, '__name__', self.name)}",
                "is_async": inspect.iscoroutinefunction(self.func),
                "args_model": self.args_model.__name__,
            },
        )

    def _build_spec(self) -> ToolSpec:
        schema = self.args_model.model_json_schema()
        required = set(schema.get("required", []))
        properties = schema.get("properties", {})
        parameters: list[ToolParameter] = []
        signature = inspect.signature(self.func)
        for param_name, parameter in signature.parameters.items():
            prop = properties.get(param_name, {})
            parameters.append(
                ToolParameter(
                    name=param_name,
                    type=str(prop.get("type") or prop.get("anyOf") or "any"),
                    description=str(prop.get("description") or ""),
                    required=param_name in required,
                    default=None if parameter.default is inspect.Parameter.empty else parameter.default,
                )
            )
        return ToolSpec(
            name=self._name,
            description=self._description,
            parameters=tuple(parameters),
            input_schema=schema,
            permission=self._permission,
            output_schema=self._output_schema,
            metadata={
                "source": "function",
                "function": f"{getattr(self.func, '__module__', '')}.{getattr(self.func, '__name__', self._name)}",
            },
        )


def _build_args_model(func: Callable[..., Any], tool_name: str) -> type[BaseModel]:
    signature = inspect.signature(func)
    hints = get_type_hints(func)
    fields: dict[str, tuple[Any, Any]] = {}

    for name, parameter in signature.parameters.items():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise TypeError(f"Tool '{tool_name}' cannot use *args or **kwargs.")
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            raise TypeError(f"Tool '{tool_name}' cannot use positional-only parameter '{name}'.")
        annotation = hints.get(name, Any)
        default = ... if parameter.default is inspect.Parameter.empty else parameter.default
        fields[name] = (annotation, default)

    model_name = "".join(part.capitalize() for part in tool_name.replace("-", "_").split("_") if part) or "Custom"
    return create_model(f"{model_name}Args", **fields)


def _docstring_summary(func: Callable[..., Any]) -> str:
    doc = inspect.getdoc(func) or ""
    paragraphs = [part.strip() for part in doc.split("\n\n") if part.strip()]
    return paragraphs[0] if paragraphs else ""


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        loc = ".".join(str(item) for item in error.get("loc", ())) or "arguments"
        parts.append(f"{loc}: {error.get('msg', 'invalid value')}")
    return "; ".join(parts)


def _stringify_output(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except TypeError:
        return str(value)

