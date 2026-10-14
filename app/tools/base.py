"""Tool plumbing shared by every agent: Pydantic-validated input, compact JSON output.

Errors never raise into the agent loop. They come back as {"ok": false, "error", "fix"} so the
model can read what went wrong and try again.
"""

import inspect
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


@dataclass
class ToolContext:
    conn: sqlite3.Connection
    household_id: int


class ToolError(Exception):
    def __init__(self, error: str, fix: str) -> None:
        super().__init__(error)
        self.error = error
        self.fix = fix


Handler = Callable[[ToolContext, Any], dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Handler

    def json_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()


async def run_tool(tool: Tool, ctx: ToolContext, raw_args: dict[str, Any]) -> dict[str, Any]:
    try:
        args = tool.input_model.model_validate(raw_args)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}" for e in error.errors()
        )
        return {"ok": False, "error": f"invalid input: {problems}", "fix": "Correct the fields and call again."}
    try:
        result = tool.handler(ctx, args)
        if inspect.isawaitable(result):
            result = await result
        return {"ok": True, **result}
    except ToolError as error:
        return {"ok": False, "error": error.error, "fix": error.fix}
