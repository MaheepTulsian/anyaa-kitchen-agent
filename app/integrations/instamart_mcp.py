"""Real Instamart via Swiggy's MCP server (streamable HTTP + OAuth bearer token).

Tool names are discovered at runtime. Anything that could place, confirm or pay for an order
is blocked here, so the agent can only search and build a cart.
"""

import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app import config
from app.integrations import swiggy_oauth
from app.integrations.instamart import CartLine, CartResult, Product
from app.models import Model

BLOCKED_TOOL = re.compile(r"order|checkout|place|pay|confirm", re.IGNORECASE)


class ToolInfo(Model):
    name: str
    description: str
    input_schema: dict[str, Any]
    blocked: bool


class BlockedToolError(RuntimeError):
    pass


@asynccontextmanager
async def session() -> AsyncIterator[ClientSession]:
    headers = {"Authorization": f"Bearer {swiggy_oauth.access_token()}"}
    async with (
        httpx2.AsyncClient(headers=headers, timeout=30) as http,
        streamable_http_client(config.SWIGGY_MCP_URL, http_client=http) as (read, write),
        ClientSession(read, write) as mcp_session,
    ):
        await mcp_session.initialize()
        yield mcp_session


async def list_tools() -> list[ToolInfo]:
    async with session() as mcp_session:
        result = await mcp_session.list_tools()
    return [
        ToolInfo(
            name=tool.name,
            description=tool.description or "",
            input_schema=tool.inputSchema,
            blocked=bool(BLOCKED_TOOL.search(tool.name)),
        )
        for tool in result.tools
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Call a non-blocked tool and return its parsed JSON (or text) content."""
    if BLOCKED_TOOL.search(name):
        raise BlockedToolError(f"'{name}' could place or pay for an order; it is blocked")
    async with session() as mcp_session:
        result = await mcp_session.call_tool(name, arguments)
    texts = [block.text for block in getattr(result, "content", []) if hasattr(block, "text")]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return joined


class McpInstamart:
    """Maps the InstamartClient interface onto Swiggy's tools (wired after discovery)."""

    async def search(self, query: str) -> list[Product]:
        raise NotImplementedError("Instamart MCP search mapping pending tool discovery")

    async def build_cart(self, lines: list[CartLine]) -> CartResult:
        raise NotImplementedError("Instamart MCP cart mapping pending tool discovery")
