"""Context Protocol Header

Description:
    Built-in image generation tool using AI models.
Purpose:
    Provides agents with the ability to generate images from text prompts
    using the OpenAI DALL-E 3 backend.
Architecture:
    - generate_image: @tool-decorated function wrapping OpenAIDalleBackend.
    - Supports configurable size and style parameters.
Relations:
    Related to vidbyte.lib.providers.image_gen and vidbyte.tools.builtins.
"""

from __future__ import annotations

from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.WRITE)
async def generate_image(prompt: str, size: str = "1024x1024", style: str = "natural") -> str:
    """Generate an image using AI.

    Args:
        prompt: Description of the image to generate.
        size: Image size - '1024x1024', '1792x1024', or '1024x1792'.
        style: Style - 'natural' or 'vivid'.
    """
    from vidbyte.lib.providers.image_gen.openai_dalle_backend import OpenAIDalleBackend

    backend = OpenAIDalleBackend()
    result = await backend.generate(prompt, size, style)
    if not result.url:
        return f"Image generation failed: {result.revised_prompt or 'Unknown error'}"
    lines = [f"Image generated: {result.url}"]
    if result.revised_prompt:
        lines.append(f"Revised prompt: {result.revised_prompt}")
    return "\n".join(lines)


__all__ = ["generate_image"]
