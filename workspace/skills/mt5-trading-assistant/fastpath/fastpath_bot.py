#!/usr/bin/env python3
"""Telegram fast-path bot — sub-1s signal-to-order executor.

For each inbound message:
- Allowed sender + matched signal pattern  -> execute MT5 script directly,
  reply via Telegram Bot API. End-to-end latency ~1 s.
- Allowed sender + unmatched (or LLM-needed) -> forward to OpenClaw via the
  `openclaw agent` CLI so the LLM still handles exotic signals and
  free-form questions.

Run:
    python fastpath_bot.py

All credentials and runtime knobs are loaded from environment variables
(see .env.example).
"""

from __future__ import annotations

import io
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

sys.path.insert(0, str(Path(__file__).parent))
from fastpath import handle  # noqa: E402

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("FASTPATH_BOT_TOKEN")
if not BOT_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN is required. See .env.example.")
    sys.exit(2)

ALLOWED_SENDERS = set(
    s.strip() for s in os.environ.get("FASTPATH_ALLOWED_SENDERS", "").split(",") if s.strip()
)
if not ALLOWED_SENDERS:
    print("WARNING: FASTPATH_ALLOWED_SENDERS is empty — every sender will be rejected.")

LLM_FALLBACK = os.environ.get("FASTPATH_LLM_FALLBACK", "1") == "1"
OPENCLAW_AGENT_ID = os.environ.get("FASTPATH_OPENCLAW_AGENT", "main")

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
LOG_FILE = Path(__file__).parent / "fastpath_bot.log"
SIGNALS_DIR = Path(__file__).resolve().parents[1] / "trade_history"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def record_signal(record: dict) -> None:
    try:
        SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
        path = SIGNALS_DIR / f"signals_{time.strftime('%Y-%m-%d')}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as e:
        log(f"record_signal failed: {e}")


def tg_call(method: str, timeout: int = 60, **params) -> dict:
    url = f"{API_BASE}/{method}"
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log(f"tg_call {method} HTTP {e.code}: {body[:300]}")
        raise
    except Exception as e:  # noqa: BLE001
        log(f"tg_call {method} error: {e}")
        raise


def send_reply(chat_id: int, text: str, reply_to: int | None = None) -> None:
    try:
        tg_call("sendMessage", chat_id=chat_id, text=text, reply_to_message_id=reply_to)
    except Exception as e:  # noqa: BLE001
        log(f"send_reply failed for chat={chat_id}: {e}")


def _resolve_openclaw_cli() -> str:
    candidates = [
        os.path.expandvars(r"%APPDATA%\npm\openclaw.cmd"),
        os.path.expandvars(r"%APPDATA%\npm\openclaw"),
        "openclaw",
    ]
    for c in candidates:
        if c == "openclaw" or os.path.exists(c):
            return c
    return "openclaw"


OPENCLAW_CLI = _resolve_openclaw_cli()


def forward_to_llm(chat_id: int | str, text: str) -> str | None:
    if not LLM_FALLBACK:
        return None
    log(f"LLM fallback for chat={chat_id} text={text[:80]!r}")
    try:
        proc = subprocess.run(
            [OPENCLAW_CLI, "agent", "--agent", OPENCLAW_AGENT_ID,
             "--to", str(chat_id), "--message", text,
             "--thinking", "off", "--json"],
            capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace", shell=False,
        )
        out = proc.stdout.strip()
        if not out:
            return None
        try:
            data = json.loads(out)
            return data.get("reply") or data.get("text") or out[:1000]
        except json.JSONDecodeError:
            return out[:1000]
    except subprocess.TimeoutExpired:
        log("LLM fallback timed out (180s)")
        return "LLM fallback timeout"
    except FileNotFoundError:
        log("openclaw CLI not found — LLM fallback disabled")
        return None
    except Exception as e:  # noqa: BLE001
        log(f"LLM fallback error: {e}")
        return None


def _classify_decision(reply: str | None) -> str:
    if not reply:
        return "no_match"
    if "Order executed" in reply:
        return "executed"
    if "ABANDON" in reply:
        return "abandoned_local"
    if "MT5 failure" in reply:
        return "mt5_failed"
    if reply.startswith("Ignored"):
        return "ignored_noise"
    if "Positions closed" in reply:
        return "closed_positions"
    return "other"


def handle_message(msg: dict) -> None:
    text = msg.get("text") or msg.get("caption") or ""
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type", "?")
    chat_title = chat.get("title") or chat.get("username") or "?"
    msg_id = msg.get("message_id")
    sender = msg.get("from", {}) or {}
    sender_chat = msg.get("sender_chat", {}) or {}
    from_id = str(sender.get("id", "") or sender_chat.get("id", ""))
    from_name = sender.get("username") or sender.get("first_name") or sender_chat.get("title") or "?"

    base_record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "chat_id": chat_id,
        "chat_type": chat_type,
        "chat_title": chat_title,
        "message_id": msg_id,
        "from_id": from_id,
        "from_name": from_name,
        "text": text,
    }

    log(f"INBOUND chat={chat_id} from_id={from_id} from={from_name!r} text={text[:120]!r}")

    if not text:
        record_signal({**base_record, "decision": "no_text"})
        return

    if from_id and from_id not in ALLOWED_SENDERS:
        log(f"  -> REJECTED (sender {from_id} not in allowlist)")
        record_signal({**base_record, "decision": "sender_rejected"})
        return

    t0 = time.time()
    result = handle(text)
    total_ms = int((time.time() - t0) * 1000)

    sig = result.get("sig") or {}
    decision = _classify_decision(result.get("reply"))
    if not result.get("matched"):
        decision = "no_match_llm_fallback" if LLM_FALLBACK else "no_match"

    record_signal({
        **base_record,
        "decision": decision,
        "matched": result.get("matched", False),
        "action": sig.get("action"),
        "zmin": sig.get("zmin"),
        "zmax": sig.get("zmax"),
        "sl": sig.get("sl"),
        "tp": sig.get("tp"),
        "trusted": sig.get("trusted"),
        "parse_ms": result.get("parse_ms"),
        "exec_ms": result.get("exec_ms"),
        "total_ms": total_ms,
        "exit_code": result.get("exit_code"),
        "reply": result.get("reply"),
    })

    if result.get("matched"):
        reply = result["reply"]
        log(f"FAST-PATH parse={result['parse_ms']}ms exec={result.get('exec_ms', 0)}ms "
            f"total={total_ms}ms -> {reply[:120]}")
        send_reply(chat_id, f"{reply}\n[fast-path {total_ms}ms]", reply_to=msg_id)
        return

    log(f"NO MATCH -> LLM fallback")
    if LLM_FALLBACK:
        llm_reply = forward_to_llm(chat_id, text)
        if llm_reply:
            send_reply(chat_id, llm_reply, reply_to=msg_id)


def main_loop() -> None:
    log(f"fastpath_bot starting; allowed senders={ALLOWED_SENDERS} llm_fallback={LLM_FALLBACK}")
    try:
        tg_call("deleteWebhook", drop_pending_updates="false", timeout=10)
    except Exception:
        pass
    while True:
        try:
            me = tg_call("getMe", timeout=10)
            log(f"connected as @{me.get('result', {}).get('username', '?')}")
            break
        except Exception as e:  # noqa: BLE001
            log(f"getMe failed (retrying in 30s): {e}")
            time.sleep(30)

    offset = 0
    consecutive_errors = 0
    while True:
        try:
            r = tg_call("getUpdates", offset=offset, timeout=25)
            consecutive_errors = 0
            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("channel_post") or upd.get("edited_message")
                if not msg:
                    continue
                try:
                    handle_message(msg)
                except Exception as e:  # noqa: BLE001
                    log(f"handle_message error: {e}")
        except KeyboardInterrupt:
            log("shutting down")
            return
        except urllib.error.HTTPError as e:
            consecutive_errors += 1
            if e.code == 409:
                wait = min(60, 5 * consecutive_errors)
                log(f"409 conflict; backoff {wait}s")
                time.sleep(wait)
            elif e.code == 429:
                try:
                    body = json.loads(e.read().decode())
                    retry = body.get("parameters", {}).get("retry_after", 5)
                except Exception:
                    retry = 5
                log(f"429 rate-limited; sleep {retry}s")
                time.sleep(retry + 1)
            elif e.code in (502, 503, 504):
                log(f"telegram {e.code}; backoff 10s")
                time.sleep(10)
            else:
                log(f"HTTP {e.code}; backoff 5s")
                time.sleep(5)
        except Exception as e:  # noqa: BLE001
            consecutive_errors += 1
            backoff = min(60, 3 * consecutive_errors)
            log(f"poll loop error ({consecutive_errors}): {e} -> sleep {backoff}s")
            time.sleep(backoff)


if __name__ == "__main__":
    main_loop()
