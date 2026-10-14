"""Base model and reusable field types."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class Model(BaseModel):
    """Project-wide base: unknown fields are rejected so LLM drift fails loudly."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ItemId = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1)]
"""Ingredient or dish name as plain lowercase text, e.g. `groundnut oil`, `rajma chawal`."""
