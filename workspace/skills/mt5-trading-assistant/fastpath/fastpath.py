#!/usr/bin/env python3
"""Fast-path signal parser + MT5 executor.

Bypasses the LLM for known signal formats. Falls back gracefully (returns
None) on unrecognized formats so the LLM path can still handle exotic
phrasings.

Public API:
    parse_signal(text) -> dict | None
    exec_signal(sig)   -> (raw_output, exit_code, elapsed_s)
    format_reply(out)  -> str
    handle(text, dry_run=False) -> dict   # full pipeline with timing
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
SCRIPTS = WORKSPACE / "mt5-trading-assistant" / "scripts"
SCRIPT_BUY = SCRIPTS / "mt5_buy.py"
SCRIPT_SELL = SCRIPTS / "mt5_sell.py"
SCRIPT_CLOSE = SCRIPTS / "mt5_close_all.py"

NUM = r"(\d{3,5}(?:[.,]\d+)?)"
GAP = r"[^\d\n]{0,15}"  # tolerate **, :, spaces, emojis, punctuation between keyword and number

# Comma-separated regex of trusted signal sources whose entries bypass the
# RR/zone/distance checks. Configurable via env var so this code stays
# generic on a public repo.
_TRUSTED_RAW = os.environ.get("FASTPATH_TRUSTED_SOURCES", "")
TRUSTED_SOURCES = re.compile(_TRUSTED_RAW, re.I) if _TRUSTED_RAW else None

ACTION_BUY = re.compile(r"\b(BUY|ACHAT|J'ACH[EÈ]TE)\b", re.I)
ACTION_SELL = re.compile(r"\b(SELL|VENTE|JE VENDS)\b", re.I)
CLOSE_ALL = re.compile(r"(FERMEZ.*TRADES?|CLOSE\s+ALL|FERMER\s+TOUT)", re.I)

ZONE_RANGE = re.compile(
    rf"(?:ZONE\s*D[''']?\s*ENTR[EÉ]E|ZONE|ENTR[EÉ]E){GAP}{NUM}\s*[-–à]\s*{NUM}",
    re.I,
)
ZONE_SINGLE = re.compile(
    rf"(?:ZONE\s*D[''']?\s*ENTR[EÉ]E|ZONE|ENTR[EÉ]E|BUY|SELL|ACHAT|VENTE|GOLD){GAP}{NUM}\b",
    re.I,
)
SL = re.compile(rf"(?:STOP\s*LOSS|STOPLOSS|SL)\b{GAP}{NUM}", re.I)
TP_FIRST = re.compile(rf"(?:TAKE\s*PROFIT|TAKEPROFIT|TP\d?)\b{GAP}{NUM}", re.I)

NOISE_PATTERNS = [
    re.compile(r"TP\d?\s*(TOUCH[EÉ]|HIT)", re.I),
    re.compile(r"\bSL\s+BE\b", re.I),
    re.compile(r"BILAN\s+(JOURNALIER|DU\s+(MATIN|JOUR))", re.I),
    re.compile(r"^[\s\W]*(\+|-)\s*\d+\s*PIPS\s*[\s\W]*$", re.I | re.M),
]


def _to_float(s: str) -> float:
    return float(s.replace(",", ".").replace(" ", ""))


def parse_signal(text: str) -> dict | None:
    """Return {action, zmin, zmax, sl, tp, trusted} for valid signals; None otherwise.

    Returns {"action": "close"} for close-all signals.
    Returns {"action": "ignore", "reason": "..."} for known noise.
    Returns None if format is unrecognized so the caller can fall back to LLM.
    """
    if not text or not text.strip():
        return None

    if CLOSE_ALL.search(text):
        return {"action": "close"}

    for pat in NOISE_PATTERNS:
        if pat.search(text):
            return {"action": "ignore", "reason": "follow-up/management"}

    is_buy = bool(ACTION_BUY.search(text))
    is_sell = bool(ACTION_SELL.search(text))
    if is_buy and is_sell:
        return None  # ambiguous — let LLM disambiguate
    action: str | None = "buy" if is_buy else ("sell" if is_sell else None)

    zone_match = ZONE_RANGE.search(text)
    if zone_match:
        zmin = _to_float(zone_match.group(1))
        zmax = _to_float(zone_match.group(2))
    else:
        single = ZONE_SINGLE.search(text)
        if not single:
            return None
        zmin = zmax = _to_float(single.group(1))

    sl_match = SL.search(text)
    tp_match = TP_FIRST.search(text)
    if not sl_match or not tp_match:
        return None
    sl = _to_float(sl_match.group(1))
    tp = _to_float(tp_match.group(1))

    entry = (zmin + zmax) / 2
    if not (1000 <= entry <= 10000):
        return None
    if not (1000 <= sl <= 10000) or not (1000 <= tp <= 10000):
        return None

    # Infer direction from SL/TP layout when keyword is missing.
    if action is None:
        if sl < entry < tp:
            action = "buy"
        elif tp < entry < sl:
            action = "sell"
        else:
            return None

    # Auto-flip on label/SL-TP mismatch (typo in the source message).
    if action == "sell" and sl < entry and tp > entry:
        action = "buy"
    elif action == "buy" and sl > entry and tp < entry:
        action = "sell"

    if action == "buy" and not (sl < entry < tp):
        return None
    if action == "sell" and not (tp < entry < sl):
        return None

    trusted = bool(TRUSTED_SOURCES and TRUSTED_SOURCES.search(text))
    return {
        "action": action, "zmin": zmin, "zmax": zmax,
        "sl": sl, "tp": tp, "trusted": trusted,
    }


def exec_signal(sig: dict, timeout: int = 30) -> tuple[str, int, float]:
    """Run the corresponding MT5 script. Returns (output, exit_code, elapsed_s)."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if sig.get("trusted"):
        env["MT5_TRUSTED"] = "1"

    if sig["action"] == "close":
        cmd = [sys.executable, str(SCRIPT_CLOSE), "all"]
    else:
        script = SCRIPT_BUY if sig["action"] == "buy" else SCRIPT_SELL
        cmd = [
            sys.executable,
            str(script),
            "0.05",
            f"{sig['zmin']:.2f}",
            f"{sig['zmax']:.2f}",
            f"{sig['sl']:.2f}",
            f"{sig['tp']:.2f}",
        ]

    t0 = time.time()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(WORKSPACE),
        timeout=timeout,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.time() - t0
    return (proc.stdout + proc.stderr, proc.returncode, elapsed)


def format_reply(output: str, sig: dict) -> str:
    """Reduce raw MT5 output to a user-facing one-liner."""
    if "Buy successful!" in output or "Sell successful!" in output:
        order = re.search(r"Order ID:\s*(\d+)", output)
        price = re.search(r"Fill price:\s*([\d.]+)", output)
        return (
            f"Order executed — ticket #{order.group(1) if order else '?'}, "
            f"price {price.group(1) if price else '?'}, "
            f"SL {sig.get('sl', '?')}, TP {sig.get('tp', '?')}"
        )
    for marker in ("ABANDON ZONE", "ABANDON RR", "ABANDON SAFETY"):
        if marker in output:
            line = next((l for l in output.splitlines() if marker in l), output[:300])
            return line.strip()
    if "Buy failed" in output or "Sell failed" in output:
        code = re.search(r"Error code:\s*(\S+)", output)
        desc = re.search(r"Description:\s*(.+)", output)
        return f"MT5 failure: {code.group(1) if code else '?'} — {desc.group(1).strip() if desc else '?'}"
    if "ERROR" in output:
        line = next((l for l in output.splitlines() if "ERROR" in l), output[:300])
        return line.strip()
    if "closed" in output.lower():
        return f"Positions closed\n{output[:300]}"
    return output[:300]


def handle(text: str, dry_run: bool = False) -> dict:
    """Full pipeline: parse -> execute -> format. Returns timing breakdown."""
    t0 = time.time()
    sig = parse_signal(text)
    parse_ms = int((time.time() - t0) * 1000)

    if sig is None:
        return {"matched": False, "parse_ms": parse_ms, "reply": None,
                "sig": None, "fallback_to_llm": True}

    if sig["action"] == "ignore":
        return {"matched": True, "parse_ms": parse_ms, "exec_ms": 0,
                "reply": f"Ignored: {sig['reason']}", "sig": sig,
                "fallback_to_llm": False}

    if dry_run:
        return {"matched": True, "parse_ms": parse_ms, "exec_ms": 0,
                "reply": f"[DRY-RUN] would exec: {sig}", "sig": sig,
                "fallback_to_llm": False}

    output, code, exec_s = exec_signal(sig)
    reply = format_reply(output, sig)
    return {
        "matched": True,
        "parse_ms": parse_ms,
        "exec_ms": int(exec_s * 1000),
        "exit_code": code,
        "reply": reply,
        "raw_output": output,
        "sig": sig,
        "fallback_to_llm": False,
    }


if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print("usage: fastpath.py <signal text> [--dry-run]")
        sys.exit(2)
    dry = "--dry-run" in sys.argv
    text = " ".join(a for a in sys.argv[1:] if a != "--dry-run")
    print(json.dumps(handle(text, dry_run=dry), ensure_ascii=False, indent=2))
