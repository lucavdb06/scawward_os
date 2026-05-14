"""Vision tools — capture and analyze the screen on demand."""
from __future__ import annotations

from .registry import ToolRegistry, ToolResult


def register_vision_tools(reg: ToolRegistry) -> None:

    @reg.tool(
        name="screenshot",
        description="Capture the current screen and return a vision-LLM summary of what's on it.",
        schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Optional focused question (e.g. 'what error is shown?').",
                },
            },
        },
    )
    async def _shot(question: str | None = None) -> ToolResult:
        from ..modules.vision import VisionModule
        v = VisionModule()
        description = await v.describe(question=question)
        return ToolResult.success(description, description=description)
