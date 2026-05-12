"""
Telegram dual-listener signal relay.

Architecture
------------
Two Telethon clients run in parallel under different user accounts so each
account only subscribes to the channels it is actually a member of:

  Listener A  ── reads signal channels group A  ─┐
                                                 ├─→ filter (direction + entry + SL + TP)
  Listener B  ── reads signal channels group B  ─┘            │
                                                              ▼
                                  forwards valid signals to OPENCLAW_INBOX_BOT
                                  + posts a confirmation via the Bot API

A valid signal must contain a direction keyword (BUY / SELL / ACHAT / VENTE),
an entry zone or price, a stop-loss, and at least one take-profit. Anything
else (analysis, trade-management chatter, advertising) is dropped early so
the downstream agent never sees noise.

Credentials are loaded from the environment (see .env.example).
"""

import asyncio
import html
import os
import re
import sys

import aiohttp
from dotenv import load_dotenv
from telethon import TelegramClient, events

load_dotenv()


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        print(f"ERROR: environment variable {name} is not set. See .env.example.")
        sys.exit(2)
    return val


def _parse_channel_map(raw: str) -> dict[int, str]:
    """Parse '<id>:<name>,<id>:<name>' into {int_id: display_name}."""
    out: dict[int, str] = {}
    if not raw:
        return out
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        chan_id, _, name = chunk.partition(":")
        try:
            out[int(chan_id.strip())] = name.strip()
        except ValueError:
            continue
    return out


API_ID = int(_require_env("TELEGRAM_API_ID"))
API_HASH = _require_env("TELEGRAM_API_HASH")
BOT_TOKEN = _require_env("TELEGRAM_BOT_TOKEN")
OWNER_CHAT_ID = _require_env("TELEGRAM_OWNER_CHAT_ID")
OPENCLAW_INBOX_BOT = os.getenv("OPENCLAW_INBOX_BOT", "")

CHANNELS_A = _parse_channel_map(os.getenv("TELEGRAM_LISTENER_A_CHANNELS", ""))
CHANNELS_B = _parse_channel_map(os.getenv("TELEGRAM_LISTENER_B_CHANNELS", ""))

SESSION_A = os.getenv("TELETHON_SESSION_A", "session_listener_a")
SESSION_B = os.getenv("TELETHON_SESSION_B", "session_listener_b")


# ---------------------------------------------------------------------------
# Signal filter — direction + entry + SL + TP all required
# ---------------------------------------------------------------------------
_DIRECTION_RE = re.compile(r"\b(VENTE|ACHAT|SELL|BUY)\b", re.IGNORECASE)
_ENTRY_RE = re.compile(r"(ENTR[EÉ]E?|ENTRY|ZONE)[^\d]*\d{3,}", re.IGNORECASE)
_SL_RE = re.compile(r"\b(SL|STOPLOSS|STOP[\s\-]?LOSS)[^\d]*\d{3,}", re.IGNORECASE)
_TP_RE = re.compile(r"\b(TP[\d]?|TAKEPROFIT|TAKE[\s\-]?PROFIT)[^\d]*\d{3,}", re.IGNORECASE)


def is_valid_signal(text: str) -> bool:
    """True if text contains a direction, entry, SL and at least one TP."""
    return bool(
        _DIRECTION_RE.search(text)
        and _ENTRY_RE.search(text)
        and _SL_RE.search(text)
        and _TP_RE.search(text)
    )


# ---------------------------------------------------------------------------
# Telethon clients
# ---------------------------------------------------------------------------
client_a = TelegramClient(SESSION_A, API_ID, API_HASH)
client_b = TelegramClient(SESSION_B, API_ID, API_HASH)


async def send_notification(text: str) -> None:
    """Confirmation ping to the owner via Bot API (best-effort, never blocks)."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": OWNER_CHAT_ID, "text": text, "parse_mode": "HTML"}
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(url, json=payload, timeout=timeout)
        except Exception:
            pass


async def handle_signal(message_text: str, channel_name: str) -> None:
    if not is_valid_signal(message_text):
        print(f"[skip] {channel_name}: missing direction / entry / SL / TP → {message_text!r}")
        return

    print(f"\n[ok] valid signal from {channel_name}")

    payload = f"{channel_name}:\n\n{message_text}"
    if OPENCLAW_INBOX_BOT:
        try:
            await client_b.send_message(OPENCLAW_INBOX_BOT, payload)
            print(f"[fwd] forwarded to {OPENCLAW_INBOX_BOT}")
        except Exception as e:
            print(f"[err] forward failed: {e}")
            return

    asyncio.create_task(send_notification(
        f"<b>Signal forwarded</b>\nChannel: <b>{html.escape(channel_name)}</b>\n\n"
        f"{html.escape(message_text)}"
    ))


# ---------------------------------------------------------------------------
# Per-listener handlers
# ---------------------------------------------------------------------------
if CHANNELS_A:
    @client_a.on(events.NewMessage(chats=list(CHANNELS_A.keys())))
    async def _handler_a(event):
        text = event.message.text or ""
        if not text.strip():
            return
        await handle_signal(text, CHANNELS_A.get(event.chat_id, "unknown"))


if CHANNELS_B:
    @client_b.on(events.NewMessage(chats=list(CHANNELS_B.keys())))
    async def _handler_b(event):
        text = event.message.text or ""
        if not text.strip():
            return
        await handle_signal(text, CHANNELS_B.get(event.chat_id, "unknown"))


async def main() -> None:
    print("=" * 62)
    print("OpenClaw Trading — Telegram dual-listener signal relay")
    print("=" * 62)

    print(f"\nStarting listener A ({SESSION_A})…")
    print("  First run will prompt for phone number + OTP.")
    await client_a.start()
    me_a = await client_a.get_me()
    print(f"  Listener A logged in as {me_a.first_name} (id={me_a.id})")
    print(f"  Channels: {list(CHANNELS_A.values()) or '[none configured]'}")

    print(f"\nStarting listener B ({SESSION_B})…")
    print("  First run will prompt for phone number + OTP.")
    await client_b.start()
    me_b = await client_b.get_me()
    print(f"  Listener B logged in as {me_b.first_name} (id={me_b.id})")
    print(f"  Channels: {list(CHANNELS_B.values()) or '[none configured]'}")

    print("\n" + "=" * 62)
    print("Filter: direction + entry + SL + TP all required.")
    print(f"Forward target: {OPENCLAW_INBOX_BOT or '[disabled]'}")
    print("=" * 62)
    print("\nListening for signals…\n")

    await asyncio.gather(
        client_a.run_until_disconnected(),
        client_b.run_until_disconnected(),
    )


if __name__ == "__main__":
    asyncio.run(main())
