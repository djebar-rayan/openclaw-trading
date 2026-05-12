#!/usr/bin/env python3
"""Run the daily analyzer and send the report directly to Telegram.

Used by the "OpenClaw Daily Report" Windows scheduled task at 23:55
every day. Zero LLM cost, ~10 s end-to-end.

Reads its credentials from the environment:
    TELEGRAM_BOT_TOKEN     — the same bot token used by fastpath_bot.py
    TELEGRAM_OWNER_CHAT_ID — the chat to which the report is posted
"""

from __future__ import annotations

import io
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
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

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("FASTPATH_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_OWNER_CHAT_ID") or os.environ.get("REPORT_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_CHAT_ID are required.")
    sys.exit(2)

ANALYZER = Path(__file__).parent / "mt5_daily_analyzer.py"
TUNER = Path(__file__).parent / "mt5_auto_tuner.py"
WORKSPACE = Path(__file__).resolve().parents[3]


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # Telegram caps message length at 4096 characters
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]
    for chunk in chunks:
        data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": chunk}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
                r.read()
        except Exception as e:
            print(f"send_telegram error: {e}", flush=True)
            return


def main():
    target_date = datetime.now().strftime("%Y-%m-%d")
    if len(sys.argv) > 1:
        target_date = sys.argv[1]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(ANALYZER), target_date],
            capture_output=True, text=True, cwd=str(WORKSPACE), timeout=120,
            env=env, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        send_telegram(f"Daily report {target_date}: analyzer timed out after 120s.")
        sys.exit(1)
    elapsed = round(time.time() - t0, 1)

    if proc.returncode != 0:
        msg = (
            f"Daily report {target_date} failed (exit {proc.returncode})\n\n"
            f"stdout:\n{proc.stdout[-1500:] or '(empty)'}\n\n"
            f"stderr:\n{proc.stderr[-1500:] or '(empty)'}"
        )
        send_telegram(msg)
        print(msg, flush=True)
        sys.exit(proc.returncode)

    report = proc.stdout.strip() + f"\n\nGenerated in {elapsed}s"

    # Run auto-tuner after the analyzer (analyzer writes today's history first)
    tuner_output = ""
    try:
        tuner_proc = subprocess.run(
            [sys.executable, str(TUNER)],
            capture_output=True, text=True, cwd=str(WORKSPACE), timeout=30,
            env=env, encoding="utf-8", errors="replace",
        )
        if tuner_proc.returncode == 0 and tuner_proc.stdout.strip():
            tuner_output = "\n\n" + tuner_proc.stdout.strip()
    except Exception as e:
        tuner_output = f"\n\nTuner error: {e}"

    full_report = report + tuner_output
    send_telegram(full_report)
    print(full_report, flush=True)


if __name__ == "__main__":
    main()
