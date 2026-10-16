"""FastAPI app: every HTTP route, grouped by what it serves.

    household   /api/household/*   the conversation with Anyaa (text in, streamed events out)
    state       /api/state         what the UI panels show
    speech      /api/speech/*      Azure token for the browser, cook voice notes, cook STT
    instamart   /api/instamart/*   Swiggy login, addresses, search, cart (never orders)
    telegram    /api/telegram/*    send texts and voice notes to a linked phone number
    cook        /api/cook/*        the cook's conversation; /api/clock/advance runs the next visit event
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import clock, config, cook, db, instamart, queries, speech, swiggy, telegram
from app.agent import run_cook_turn, run_household_turn
from app.flow import household_node
from app.db import db as open_db
from app.instamart import CartLine, CartResult, Product
from app.models import Agent, Message, Model, State

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    poller = asyncio.create_task(telegram.poll_forever(cook.on_telegram_message)) if telegram.enabled() else None
    yield
    if poller:
        poller.cancel()


app = FastAPI(title="Anyaa Kitchen Agent", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm_model": config.LLM_MODEL, "instamart_mode": config.INSTAMART_MODE,
            "speech_configured": bool(config.AZURE_SPEECH_KEY)}


@app.get("/test-onboarding")
def test_onboarding() -> FileResponse:
    """A page for testing just the household agent: onboarding nodes and the meal plan."""
    return FileResponse(config.WEB_DIR / "test-onboarding.html")


# --- household --------------------------------------------------------------------------------


class Turn(Model):
    text: str


def _stream(text: str, *, opener: bool = False) -> StreamingResponse:
    """Server-sent events: {"type": "tool", ...} while Anyaa works, then {"type": "reply", "text"}."""

    async def events():
        async for event in run_household_turn(text, opener=opener):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/api/household/turn")
async def household_turn(body: Turn) -> StreamingResponse:
    return _stream(body.text)


@app.post("/api/household/start")
async def household_start() -> StreamingResponse:
    """The current node speaks first if it hasn't started yet (a fresh household, or a node that just began)."""
    with open_db() as conn:
        node = household_node(conn)
        started = node is not None and queries.get_session(conn, Agent.HOUSEHOLD, node.name) is not None
    if started or node is None or not node.opener:
        return StreamingResponse(iter(()), media_type="text/event-stream")
    return _stream(node.opener, opener=True)


@app.get("/api/household/messages")
def household_messages() -> list[Message]:
    with open_db() as conn:
        return queries.list_messages(conn, Agent.HOUSEHOLD)


@app.post("/api/household/reset")
def household_reset() -> dict:
    """Start over with an empty household (Swiggy login and address are kept)."""
    db.reset()
    return {"ok": True}


@app.get("/api/state")
def state() -> State:
    with open_db() as conn:
        return State(
            household=queries.get_household(conn),
            members=queries.list_members(conn),
            preferences=queries.list_preferences(conn),
            cook=queries.get_cook(conn),
            pantry=queries.list_pantry(conn),
            plan=queries.get_plan(conn),
            escalations=queries.open_escalations(conn),
            instamart_mode=config.INSTAMART_MODE,
            clock=clock.now(conn),
        )


# --- speech -----------------------------------------------------------------------------------


@app.get("/api/speech/token")
def speech_token() -> speech.SpeechToken:
    try:
        return speech.issue_token()
    except speech.SpeechError as error:
        raise HTTPException(503, str(error)) from error


# --- instamart --------------------------------------------------------------------------------

SWIGGY_ERRORS = (swiggy.OAuthError, swiggy.InstamartError)


class ToolCall(Model):
    name: str
    arguments: dict[str, Any] = {}


@app.get("/api/instamart/status")
def instamart_status() -> dict:
    active = "mcp" if config.INSTAMART_MODE == "mcp" and swiggy.logged_in() else "mock"
    return {"mode": config.INSTAMART_MODE, "active": active, "logged_in": swiggy.logged_in(),
            "address_id": swiggy.selected_address()}


@app.get("/api/instamart/login")
def instamart_login(request: Request) -> RedirectResponse:
    try:
        return RedirectResponse(swiggy.login_url(str(request.url_for("instamart_callback"))))
    except swiggy.OAuthError as error:
        raise HTTPException(502, str(error)) from error


@app.get("/api/instamart/callback")
def instamart_callback(code: str = "", state: str = "", error: str = "") -> HTMLResponse:
    try:
        if error or not code:
            raise swiggy.OAuthError(error or "no code returned")
        swiggy.exchange_code(code, state)
    except swiggy.OAuthError as exc:
        return HTMLResponse(f"<p>Swiggy login failed: {exc}</p>", 400)
    return HTMLResponse('<p>Instamart connected. Taking you back…</p><script>setTimeout(() => location.href = "/", 800)</script>')


@app.post("/api/instamart/logout")
def instamart_logout() -> dict:
    swiggy.logout()
    return instamart_status()


@app.get("/api/instamart/addresses")
async def instamart_addresses() -> list[swiggy.Address]:
    try:
        return await swiggy.list_addresses()
    except SWIGGY_ERRORS as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/instamart/address")
def instamart_choose_address(address: swiggy.Address) -> dict:
    swiggy.select_address(address)
    return instamart_status()


@app.get("/api/instamart/search")
async def instamart_search(q: str) -> list[Product]:
    try:
        return await instamart.get_client().search(q)
    except SWIGGY_ERRORS as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/instamart/cart")
async def instamart_cart(lines: list[CartLine]) -> CartResult:
    try:
        return await instamart.get_client().build_cart(lines)
    except SWIGGY_ERRORS as error:
        raise HTTPException(400, str(error)) from error


@app.get("/api/instamart/tools")
async def instamart_tools() -> list[swiggy.ToolInfo]:
    """Debug: Swiggy's tools and which ones we allow."""
    try:
        return await swiggy.list_tools()
    except SWIGGY_ERRORS as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/instamart/tools/call")
async def instamart_call_tool(body: ToolCall) -> Any:
    """Debug: call one allowlisted Swiggy tool directly."""
    try:
        return await swiggy.call_tool(body.name, body.arguments)
    except swiggy.BlockedToolError as error:
        raise HTTPException(403, str(error)) from error
    except SWIGGY_ERRORS as error:
        raise HTTPException(400, str(error)) from error


# --- cook -------------------------------------------------------------------------------------


class CookSays(Model):
    text: str


@app.get("/api/cook/messages")
def cook_messages() -> list[Message]:
    with open_db() as conn:
        return queries.list_messages(conn, Agent.COOK)


@app.post("/api/cook/say")
async def cook_say(body: CookSays) -> dict:
    """Simulate the cook replying (for demos without a phone). The reply also goes to their Telegram."""
    reply = await run_cook_turn(body.text)
    with open_db() as conn:
        cook_profile = queries.get_cook(conn)
    if reply and cook_profile and cook_profile.phone and telegram.enabled():
        try:
            await telegram.send(cook_profile.phone, reply)
        except telegram.TelegramError:
            pass
    return {"reply": reply}


@app.post("/api/clock/advance")
async def clock_advance() -> dict:
    """Jump to the cook's next visit event (the brief at the start, the wrap-up at the end) and run it."""
    return await cook.advance()


# --- telegram ---------------------------------------------------------------------------------


class TelegramMessage(Model):
    phone: str
    text: str
    voice: bool = False  # also send it as a voice note


@app.get("/api/telegram/status")
async def telegram_status() -> dict:
    """The bot link to share, and which phone numbers are connected."""
    if not telegram.enabled():
        return {"enabled": False}
    with open_db() as conn:
        contacts = telegram.list_contacts(conn)
    return {"enabled": True, "bot_link": await telegram.bot_link(), "contacts": contacts}


@app.post("/api/telegram/send")
async def telegram_send(body: TelegramMessage) -> dict:
    try:
        if body.voice:
            await telegram.send_voice(body.phone, speech.tts_ogg(body.text, config.AZURE_TTS_VOICE_COOK), caption=body.text)
        else:
            await telegram.send(body.phone, body.text)
    except (telegram.TelegramError, speech.SpeechError) as error:
        raise HTTPException(400, str(error)) from error
    return {"sent": True}


# Static UI last, so the API routes above win.
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
