"""Base model and reusable field types."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class Model(BaseModel):
    """Project-wide base: unknown fields are rejected so LLM drift fails loudly."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ItemId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+$")]
"""Canonical ingredient or dish id, e.g. `oil_groundnut`, `rajma_chawal`."""
