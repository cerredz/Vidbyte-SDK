"""Context Protocol Header

Description:
    Implements IdentityTool — a model-callable builtin for recording an
    identity judgment into the active ContextManager.
Purpose:
    Lets the model force the two referents, the properties they share, the one
    property that splits them, the grounds, and a verdict into a checkable
    shape — premature identity judgments are how models conflate distinct
    things or refuse to unify the same thing.
Architecture:
    - IdentityTool: BaseTool that constructs an IdentityContextItem from model-
      provided arguments and upserts it into the injected ContextManager.
Relations:
    Depends on vidbyte.context.manager, vidbyte.context.primitives, and the
    shared vidbyte.tools.builtins.reasoning._parsing.ReasoningToolInput helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.reasoning._parsing import ReasoningToolInput
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager

_REQUIRED_FIELDS = ("entity_a", "entity_b", "shared_properties", "distinguishing_property", "grounds", "verdict")
_VERDICT_VALUES = ("same", "different", "indeterminate")


class IdentityTool(BaseTool):
    """Builtin tool that records an identity judgment into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="identity",
            description=(
                "Judge whether two referents are the same thing: list what they share, name "
                "the property that distinguishes them (or confirm none exists), state the "
                "grounds, and commit to a verdict. Use this before merging two concepts, "
                "treating two occurrences as the same object, or claiming two things "
                "differ. Identity is cheap to assert and expensive to retract."
            ),
            parameters=(
                ToolParameter(
                    name="entity_a",
                    type="string",
                    description=(
                        "The first referent, named exactly as it appears in context — e.g. "
                        "'the event on line 42'. Ambiguous referents are themselves the "
                        "problem; name the precise thing."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="entity_b",
                    type="string",
                    description=(
                        "The second referent, named exactly as it appears in context. If "
                        "the two names are identical, the judgment is trivially 'same' — "
                        "the tool is for cases where the names or appearances differ."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="shared_properties",
                    type="array",
                    description=(
                        "What both referents are known to share — attributes, behaviors, "
                        "location, provenance, each as its own string. If the shared "
                        "properties are weak ('both are mentioned in the same file'), "
                        "say so; the grounds must be strong enough to bear the verdict. "
                        "May be passed as a JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="distinguishing_property",
                    type="string",
                    description=(
                        "The property that holds of one and not the other, if any. For a "
                        "'same' verdict this is often 'none found' — but 'none found' is a "
                        "search result, not an identity proof, so say what was searched. "
                        "Naming a real distinguisher is what forces a 'different' verdict."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="grounds",
                    type="string",
                    description=(
                        "The evidence or criteria on which the identity claim rests — "
                        "Leibniz's law, source of both descriptions, causal continuity, "
                        "the criterion the domain actually uses. A verdict without grounds "
                        "is a guess wearing a verdict's clothes."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description=(
                        "One of: 'same', 'different', 'indeterminate'. 'indeterminate' is "
                        "for when available evidence cannot settle identity — it is a "
                        "legitimate verdict, not a failure."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the identity primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"identity:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field or a bad verdict enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "verdict"), _VERDICT_VALUES, "verdict"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the IdentityContextItem from validated call arguments.
        from vidbyte.context.primitives import IdentityContextItem
        return IdentityContextItem(
            primitive_id=primitive_id,
            entity_a=ReasoningToolInput.text(args, "entity_a"),
            entity_b=ReasoningToolInput.text(args, "entity_b"),
            shared_properties=ReasoningToolInput.string_list(args.get("shared_properties")),
            distinguishing_property=ReasoningToolInput.text(args, "distinguishing_property"),
            grounds=ReasoningToolInput.text(args, "grounds"),
            verdict=ReasoningToolInput.text(args, "verdict"),
            title=ReasoningToolInput.text(args, "title", "Identity Check") or "Identity Check",
        )