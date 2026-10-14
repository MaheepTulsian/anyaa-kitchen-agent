"""Events an LLM backend yields while running one turn. Same shape for every backend."""

from typing import Any, Literal

from pydantic import ConfigDict

from app.models import Model


class TextDelta(Model):
    model_config = ConfigDict(str_strip_whitespace=False)  # chunk edges carry the spaces

    type: Literal["delta"] = "delta"
    text: str


class ToolCalled(Model):
    type: Literal["tool"] = "tool"
    name: str
    args: dict[str, Any]


class ToolFinished(Model):
    type: Literal["tool_result"] = "tool_result"
    name: str
    args: dict[str, Any]
    result: dict[str, Any]
    latency_ms: int


class Done(Model):
    type: Literal["done"] = "done"
    stop: str  # "success" | "error_max_turns" | ...
    turns: int
    duration_ms: int
    usage: dict[str, Any] = {}


TurnEvent = TextDelta | ToolCalled | ToolFinished | Done
