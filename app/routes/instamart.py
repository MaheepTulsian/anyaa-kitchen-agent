"""Instamart endpoints: Swiggy login, tool discovery, product search and cart building."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import config
from app.integrations import instamart_mcp, swiggy_oauth
from app.integrations.instamart import CartLine, CartResult, Product, get_client
from app.models import Model

router = APIRouter(prefix="/api/instamart")


class InstamartStatus(Model):
    mode: str  # configured mode
    active: str  # what search/cart will actually use right now
    logged_in: bool
    address_id: str | None = None


class ToolCall(Model):
    name: str
    arguments: dict[str, Any] = {}


@router.get("/status")
def status() -> InstamartStatus:
    logged_in = swiggy_oauth.load_token() is not None
    active = "mcp" if config.INSTAMART_MODE == "mcp" and logged_in else "mock"
    return InstamartStatus(
        mode=config.INSTAMART_MODE,
        active=active,
        logged_in=logged_in,
        address_id=instamart_mcp.selected_address(),
    )


@router.get("/login")
def login(request: Request) -> RedirectResponse:
    redirect_uri = str(request.url_for("callback"))
    try:
        return RedirectResponse(swiggy_oauth.login_url(redirect_uri))
    except swiggy_oauth.OAuthError as error:
        raise HTTPException(502, str(error)) from error


@router.get("/callback", name="callback")
def callback(code: str = "", state: str = "", error: str = "") -> HTMLResponse:
    if error or not code:
        return HTMLResponse(f"<p>Swiggy login failed: {error or 'no code returned'}</p>", 400)
    try:
        swiggy_oauth.exchange_code(code, state)
    except swiggy_oauth.OAuthError as exc:
        return HTMLResponse(f"<p>Swiggy login failed: {exc}</p>", 400)
    return HTMLResponse('<p>Logged in to Swiggy. <a href="/instamart-lab.html">Back</a></p>')


@router.post("/logout")
def logout() -> InstamartStatus:
    swiggy_oauth.logout()
    return status()


@router.get("/tools")
async def tools() -> list[instamart_mcp.ToolInfo]:
    try:
        return await instamart_mcp.list_tools()
    except swiggy_oauth.OAuthError as error:
        raise HTTPException(401, str(error)) from error


@router.post("/tools/call")
async def call_tool(body: ToolCall) -> Any:
    """Debug: call one allowlisted tool directly (no orders, payments or address edits)."""
    try:
        return await instamart_mcp.call_tool(body.name, body.arguments)
    except instamart_mcp.BlockedToolError as error:
        raise HTTPException(403, str(error)) from error
    except (swiggy_oauth.OAuthError, instamart_mcp.InstamartError) as error:
        raise HTTPException(400, str(error)) from error


@router.get("/addresses")
async def addresses() -> list[instamart_mcp.Address]:
    try:
        return await instamart_mcp.list_addresses()
    except (swiggy_oauth.OAuthError, instamart_mcp.InstamartError) as error:
        raise HTTPException(400, str(error)) from error


@router.post("/address")
def choose_address(address: instamart_mcp.Address) -> InstamartStatus:
    instamart_mcp.select_address(address)
    return status()


@router.get("/search")
async def search(q: str) -> list[Product]:
    try:
        return await get_client().search(q)
    except (swiggy_oauth.OAuthError, instamart_mcp.InstamartError) as error:
        raise HTTPException(400, str(error)) from error


@router.post("/cart")
async def build_cart(lines: list[CartLine]) -> CartResult:
    try:
        return await get_client().build_cart(lines)
    except (swiggy_oauth.OAuthError, instamart_mcp.InstamartError) as error:
        raise HTTPException(400, str(error)) from error
