"""Telegram: send messages and voice notes to a phone number, and receive replies.

A Telegram bot can't message a number cold. The person opens the bot once, taps Start and shares
their phone number with one button; from then on we can message that number:

    await telegram.send("98xxxxxx21", "Raju bhaiya, today is rajma chawal for four.")
    await telegram.send_voice("98xxxxxx21", ogg_bytes, caption="Today's plan")

Replies come in by long polling (no public URL needed): `poll_forever()` runs in the background,
links phone numbers, and hands every other message to `on_message`.
"""

import asyncio
import re
import traceback
import sqlite3
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app import clock, config
from app.db import db
from app.models import Model

API = "https://api.telegram.org"


class TelegramError(RuntimeError):
    pass


class Contact(Model):
    phone: str  # last 10 digits, e.g. "9876543210"
    chat_id: int
    name: str | None = None


class Incoming(Model):
    contact: Contact
    text: str | None = None
    voice_file_id: str | None = None


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN)


def normalize(phone: str) -> str:
    """Compare phone numbers by their last 10 digits (+91 98765 43210 == 9876543210)."""
    return re.sub(r"\D", "", phone)[-10:]


async def _call(method: str, files: dict[str, Any] | None = None, wait: float = 30, **params: Any) -> Any:
    """`params` go to Telegram as-is (including getUpdates' own `timeout`); `wait` is how long we wait."""
    if not enabled():
        raise TelegramError("TELEGRAM_BOT_TOKEN is not set")
    async with httpx.AsyncClient(timeout=wait + 10) as http:
        response = await http.post(f"{API}/bot{config.TELEGRAM_BOT_TOKEN}/{method}", data=params, files=files)
    body = response.json()
    if not body.get("ok"):
        raise TelegramError(f"{method} failed: {body.get('description', response.text[:200])}")
    return body["result"]


# --- contacts (phone ↔ chat) ------------------------------------------------------------------


def save_contact(conn: sqlite3.Connection, contact: Contact) -> None:
    conn.execute(
        "INSERT INTO telegram_contact (phone, chat_id, name, linked_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (phone) DO UPDATE SET chat_id = excluded.chat_id, name = excluded.name",
        (contact.phone, contact.chat_id, contact.name, clock.real_now().isoformat()),
    )
    conn.commit()


def find_contact(conn: sqlite3.Connection, *, phone: str | None = None, chat_id: int | None = None) -> Contact | None:
    if phone is not None:
        row = conn.execute("SELECT * FROM telegram_contact WHERE phone = ?", (normalize(phone),)).fetchone()
    else:
        row = conn.execute("SELECT * FROM telegram_contact WHERE chat_id = ?", (chat_id,)).fetchone()
    return Contact(phone=row["phone"], chat_id=row["chat_id"], name=row["name"]) if row else None


def list_contacts(conn: sqlite3.Connection) -> list[Contact]:
    rows = conn.execute("SELECT * FROM telegram_contact ORDER BY linked_at")
    return [Contact(phone=r["phone"], chat_id=r["chat_id"], name=r["name"]) for r in rows]


def _chat_for(phone: str) -> int:
    with db() as conn:
        contact = find_contact(conn, phone=phone)
    if contact is None:
        raise TelegramError(f"{phone} hasn't opened the bot yet; send them the link from bot_link()")
    return contact.chat_id


# --- sending ----------------------------------------------------------------------------------


async def bot_link() -> str:
    """The link to share: opening it and tapping Start connects that person's number."""
    me = await _call("getMe")
    return f"https://t.me/{me['username']}"


async def send(phone: str, text: str) -> None:
    await _call("sendMessage", chat_id=_chat_for(phone), text=text)


async def send_voice(phone: str, ogg_opus: bytes, caption: str | None = None) -> None:
    """A voice note (Telegram plays OGG/Opus as a voice message)."""
    params = {"chat_id": _chat_for(phone)} | ({"caption": caption} if caption else {})
    await _call("sendVoice", files={"voice": ("note.ogg", ogg_opus, "audio/ogg")}, **params)


async def download(file_id: str) -> bytes:
    """Download a file someone sent (e.g. a voice reply)."""
    info = await _call("getFile", file_id=file_id)
    async with httpx.AsyncClient(timeout=60) as http:
        response = await http.get(f"{API}/file/bot{config.TELEGRAM_BOT_TOKEN}/{info['file_path']}")
    return response.content


# --- receiving --------------------------------------------------------------------------------

SHARE_PHONE = '{"keyboard": [[{"text": "Share my phone number", "request_contact": true}]], "one_time_keyboard": true, "resize_keyboard": true}'


async def _handle(update: dict[str, Any], on_message: Callable[[Incoming], Awaitable[None]] | None) -> None:
    message = update.get("message")
    if not message:
        return
    chat_id = message["chat"]["id"]

    if shared := message.get("contact"):  # they tapped "Share my phone number"
        contact = Contact(phone=normalize(shared["phone_number"]), chat_id=chat_id, name=shared.get("first_name"))
        with db() as conn:
            save_contact(conn, contact)
        await _call("sendMessage", chat_id=chat_id, text="Thank you! You're connected to Anyaa. 🙏",
                    reply_markup='{"remove_keyboard": true}')
        return

    with db() as conn:
        contact = find_contact(conn, chat_id=chat_id)
    if contact is None or message.get("text", "").startswith("/start"):
        await _call("sendMessage", chat_id=chat_id, reply_markup=SHARE_PHONE,
                    text="Namaste! I'm Anyaa, I help run the kitchen at home. Please tap the button below to share your phone number.")
        return

    if on_message:
        voice = message.get("voice") or message.get("audio")
        await on_message(Incoming(contact=contact, text=message.get("text"), voice_file_id=voice["file_id"] if voice else None))


async def poll_forever(on_message: Callable[[Incoming], Awaitable[None]] | None = None) -> None:
    """Long-poll Telegram for new messages. Runs as a background task while the app is up."""
    offset = 0
    while True:
        try:
            updates = await _call("getUpdates", wait=30, offset=offset, timeout=25, allowed_updates='["message"]')
        except asyncio.CancelledError:
            raise
        except Exception:  # a network blip shouldn't stop the bot
            print(f"telegram poll failed:\n{traceback.format_exc(limit=3)}")
            await asyncio.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                await _handle(update, on_message)
            except Exception:  # one bad message must not stop the others
                print(f"telegram message failed:\n{traceback.format_exc(limit=5)}")
