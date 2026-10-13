from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
from collections.abc import Callable, Mapping
from typing import Annotated, Any, get_type_hints

from pydantic import BaseModel, TypeAdapter, ValidationError, create_model
from pydantic_core import to_jsonable_python

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


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
        self._null_means_default = _null_means_default_fields(self.args_model)
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
            _validate_arguments(self.args_model, self._arguments(call))
        except ValidationError as exc:
            return _validation_message(exc)
        return None

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            model = _validate_arguments(self.args_model, self._arguments(call))
        except ValidationError as exc:
            return ToolResult.failure(self.name, _validation_message(exc), metadata={"error_type": "validation"})

        # Read validated attributes directly: model_dump would turn nested models and dataclasses back into dicts.
        kwargs = {name: getattr(model, name) for name in type(model).model_fields}
        try:
            if inspect.iscoroutinefunction(self.func):
                value = await self.func(**kwargs)
            else:
                value = await asyncio.to_thread(self.func, **kwargs)
                # A sync wrapper around an async function hands back a coroutine; finish it here so its work happens.
                if inspect.isawaitable(value):
                    value = await value
        except Exception as exc:
            # @intent function-tool-errors-share-the-runtime-error-kind
            # A raising function tool reports the same error kind the runtime gives a raising BaseTool, so the
            # model and ToolErrorPolicy treat both ways of writing a tool alike: a raised ToolExecutionError keeps
            # the kind it declares in its details (rate_limited, timeout, ...), and every other exception is
            # execution_error.
            if isinstance(exc, ToolExecutionError):
                metadata = {
                    "error": str(exc.details.get("error", "execution_error")),
                    "error_type": exc.details.get("error_type", exc.__class__.__name__),
                }
            else:
                metadata = {"error": "execution_error", "error_type": exc.__class__.__name__}
            return ToolResult.failure(self.name, str(exc), metadata=metadata)

        return ToolResult.success(
            self.name,
            _stringify_output(value),
            metadata={
                "function": f"{getattr(self.func, '__module__', '')}.{getattr(self.func, '__name__', self.name)}",
                "is_async": inspect.iscoroutinefunction(self.func),
                "args_model": self.args_model.__name__,
            },
        )

    def _arguments(self, call: ToolCall) -> dict[str, Any]:
        # @intent null-optional-arg-means-default
        # Models often send JSON null for an optional argument they mean to leave out; treat it exactly like an
        # omitted key so the function's default applies instead of failing validation. A parameter whose type
        # accepts None still receives None, and a required parameter still rejects null.
        return {
            name: value
            for name, value in call.arguments.items()
            if not (value is None and name in self._null_means_default)
        }

    def _build_spec(self) -> ToolSpec:
        schema = self.args_model.model_json_schema()
        required = set(schema.get("required", []))
        properties = schema.get("properties", {})
        parameters: list[ToolParameter] = []
        signature = inspect.signature(self.func)
        for param_name, parameter in signature.parameters.items():
            prop = properties.get(param_name, {})
            # Label each argument with a readable type name for the tool docs the model reads with every request.
            parameters.append(
                ToolParameter(
                    name=param_name,
                    type=_parameter_type_label(prop),
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
    hints = get_type_hints(func, include_extras=True)
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


def _null_means_default_fields(args_model: type[BaseModel]) -> frozenset[str]:
    # Parameters with a default whose type rejects None; a null for one of them means "use the default".
    names = set()
    for name, field in args_model.model_fields.items():
        if field.is_required():
            continue
        annotation: Any = Annotated[(field.annotation, *field.metadata)] if field.metadata else field.annotation
        try:
            TypeAdapter(annotation).validate_python(None)
        except ValidationError:
            names.add(name)
    return frozenset(names)


def _parameter_type_label(prop: Mapping[str, Any]) -> str:
    # @intent function-tool-parameter-type-is-a-name
    # The label is a type name, never a Python repr of the schema: Optional[str] reads "string | null", and a
    # $ref, enum or model argument reads "any", as it does for a tool declared only by input_schema.
    if isinstance(prop.get("type"), str):
        return prop["type"]
    branches = prop.get("anyOf")
    if isinstance(branches, list) and branches and all(isinstance(branch, Mapping) and isinstance(branch.get("type"), str) for branch in branches):
        return " | ".join(branch["type"] for branch in branches)
    return "any"


def _validate_arguments(args_model: type[BaseModel], arguments: dict[str, Any]) -> BaseModel:
    # @intent tool-arguments-validate-in-json-mode
    # A model sends its arguments as JSON, so they validate in Pydantic's JSON mode: a strict=True model's Python mode
    # rejects the JSON spellings of enums, dates and tuples. A call built in code may hold values JSON cannot (a model
    # instance, a datetime, NaN); those arguments keep Python-mode validation.
    try:
        text = json.dumps(arguments, allow_nan=False)
    except (TypeError, ValueError):
        return args_model.model_validate(arguments)
    return args_model.model_validate_json(text)


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
    # @intent tool-output-keeps-non-ascii-readable
    # The model and the tool-output predicates read this text, so non-ASCII stays as characters, like a str return
    # and like the SDK's other JSON (isDone answer, session/harness stores); the HTTP transport still escapes the
    # wire body itself.
    try:
        return json.dumps(value, default=_json_default, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        pass
    # @intent tool-model-output-is-json
    # default= never sees dict keys, so Enum/date keys and mixed int/str keys raise above; normalize keys the way
    # the equivalent model's JSON mode does, letting _json_default turn read-only mappings into objects and other
    # unknown leaves into str(), and fall back to a repr only if that still fails. Nested models dump by alias here
    # too (see _json_default).
    try:
        return json.dumps(to_jsonable_python(value, by_alias=True, fallback=_json_default), sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _json_default(value: object) -> object:
    # @intent tool-model-output-is-json
    # Models and dataclass instances become JSON objects so output_schema validation sees fields, not a repr string.
    # Other leaves (Enum, datetime, UUID, set) take pydantic's JSON-mode value, so a dict or dataclass return
    # serializes exactly like the equivalent model; only types pydantic cannot serialize fall back to str().
    # @intent tool-model-output-round-trips
    # A model dumps by alias, its own JSON form (the one model_json_schema describes and model_validate accepts), so a
    # tool returning its declared output_schema type passes its own output check; models without aliases are unchanged.
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    # @intent read-only-mappings-are-json-objects
    # A frozen record often holds a MappingProxyType; asdict cannot deep-copy one and pydantic cannot serialize one,
    # so read fields shallowly and turn any non-dict Mapping into a dict, letting json.dumps recurse through both.
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return dict(value)
    try:
        return to_jsonable_python(value)
    except ValueError:  # PydanticSerializationError and UnicodeDecodeError are both ValueErrors.
        return str(value)

