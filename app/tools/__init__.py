"""Turns a plain Python function into a Claude Agent SDK tool, with a Pydantic input model.

    @anyaa_tool("set_household_meals", "Which meals to plan.", SetMealsInput)
    def set_household_meals(args: SetMealsInput) -> dict: ...

Input is validated by Pydantic. Errors never crash the turn: they go back to the model as
{"ok": false, "error", "fix"} so it can correct itself and call again.
"""

import inspect
import json
from collections.abc import Callable
from typing import Any

from claude_agent_sdk import SdkMcpTool, tool
from pydantic import BaseModel, ValidationError


class ToolError(Exception):
    def __init__(self, error: str, fix: str) -> None:
        super().__init__(error)
        self.error, self.fix = error, fix


def _reply(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "is_error": not payload["ok"],
    }


def anyaa_tool(name: str, description: str, input_model: type[BaseModel]) -> Callable[..., SdkMcpTool[Any]]:
    def wrap(fn: Callable[[Any], Any]) -> SdkMcpTool[Any]:
        @tool(name, description, input_model.model_json_schema())
        async def handler(raw: dict[str, Any]) -> dict[str, Any]:
            try:
                args = input_model.model_validate(raw)
            except ValidationError as error:
                problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}" for e in error.errors())
                return _reply({"ok": False, "error": f"invalid input: {problems}", "fix": "Correct the fields and call again."})
            try:
                result = fn(args)
                if inspect.isawaitable(result):
                    result = await result
                return _reply({"ok": True, **result})
            except ToolError as error:
                return _reply({"ok": False, "error": error.error, "fix": error.fix})

        return handler

    return wrap
