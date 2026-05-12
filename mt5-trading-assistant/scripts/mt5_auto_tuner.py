#!/usr/bin/env python3
"""Auto-tuner — adjusts risk_config.json based on recent trade history.

Reads trade_history/*.json over a sliding window, applies four
deterministic rules with hard guard-rails, and writes the new config back.
Each adjustment is appended to risk_config.json._history for auditability.

Rules (evaluated in order):
1. Win rate < 40% over >= 8 closed trades -> raise MIN_RR by +0.1.
2. Win rate > 60% AND rejection_rate > 30% -> lower MIN_RR by -0.05.
3. ABANDON_ZONE > 40% of rejections -> raise ZONE_TOL by +1.
4. ABANDON_SAFETY > 40% of rejections -> lower MIN_DISTANCE by -0.1.

Hard limits:
    MIN_RR        in [0.3, 2.0]
    ZONE_TOL      in [3,  25]
    MIN_DISTANCE  in [0.1, 2.0]

Max change per night: +/-0.1 on MIN_RR, +/-1 on ZONE_TOL, +/-0.1 on
MIN_DISTANCE. Prevents oscillation; favours gradual learning.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

SKILL_DIR = Path(__file__).resolve().parents[1]
HISTORY_DIR = SKILL_DIR / "trade_history"
RISK_CONFIG = SKILL_DIR / "risk_config.json"

WINDOW_DAYS = 7
MIN_TRADES_FOR_TIGHTENING = 8

LIMITS = {
    "min_rr": (0.3, 2.0),
    "zone_tol": (3.0, 25.0),
    "min_distance": (0.1, 2.0),
}

MAX_DELTA = {
    "min_rr": 0.1,
    "zone_tol": 1.0,
    "min_distance": 0.1,
}


def load_history(window_days: int = WINDOW_DAYS) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=window_days)
    out: list[dict] = []
    if not HISTORY_DIR.exists():
        return out
    for path in sorted(HISTORY_DIR.glob("*.json")):
        try:
            day = datetime.strptime(path.stem, "%Y-%m-%d")
        except ValueError:
            continue
        if day < cutoff:
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                out.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def aggregate_window(records: list[dict]) -> dict:
    total_closed = 0
    total_wins = 0
    total_losses = 0
    total_pnl = 0.0
    total_rejected = 0
    rejection_breakdown: dict[str, int] = {}

    for r in records:
        s = r.get("summary", {})
        total_closed += s.get("trades_closed", 0)
        total_wins += s.get("wins", 0)
        total_losses += s.get("losses", 0)
        total_pnl += s.get("total_pnl", 0)
        total_rejected += s.get("rejected_signals", 0)
        for k, v in (s.get("rejection_breakdown") or {}).items():
            rejection_breakdown[k] = rejection_breakdown.get(k, 0) + v

    win_rate = total_wins / total_closed if total_closed else 0.0
    total_signals = total_closed + total_rejected
    rejection_rate = total_rejected / total_signals if total_signals else 0.0
    return {
        "days": len(records),
        "closed": total_closed,
        "wins": total_wins,
        "losses": total_losses,
        "pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 3),
        "rejected": total_rejected,
        "rejection_rate": round(rejection_rate, 3),
        "rejection_breakdown": rejection_breakdown,
    }


def clamp(value: float, key: str) -> float:
    lo, hi = LIMITS[key]
    return max(lo, min(hi, value))


def cap_delta(current: float, target: float, key: str) -> float:
    delta = target - current
    cap = MAX_DELTA[key]
    if delta > cap:
        return current + cap
    if delta < -cap:
        return current - cap
    return target


def propose_changes(current: dict, agg: dict) -> tuple[dict, list[str]]:
    new = dict(current)
    reasons: list[str] = []

    win_rate = agg["win_rate"]
    closed = agg["closed"]
    rej_rate = agg["rejection_rate"]
    breakdown = agg["rejection_breakdown"]
    total_rej = max(1, agg["rejected"])

    if closed >= MIN_TRADES_FOR_TIGHTENING and win_rate < 0.40:
        target = current["min_rr"] + 0.1
        capped = clamp(cap_delta(current["min_rr"], target, "min_rr"), "min_rr")
        if capped != current["min_rr"]:
            new["min_rr"] = round(capped, 3)
            reasons.append(
                f"win_rate {win_rate * 100:.0f}% < 40% on {closed} trades -> "
                f"MIN_RR {current['min_rr']} -> {new['min_rr']} (stricter)"
            )
    elif closed >= 4 and win_rate > 0.60 and rej_rate > 0.30:
        target = current["min_rr"] - 0.05
        capped = clamp(cap_delta(current["min_rr"], target, "min_rr"), "min_rr")
        if capped != current["min_rr"]:
            new["min_rr"] = round(capped, 3)
            reasons.append(
                f"win_rate {win_rate * 100:.0f}% > 60% but rejection {rej_rate * 100:.0f}% > 30% -> "
                f"MIN_RR {current['min_rr']} -> {new['min_rr']} (more permissive)"
            )

    zone_rejections = sum(v for k, v in breakdown.items() if "ZONE" in k)
    if zone_rejections / total_rej > 0.40 and zone_rejections >= 3:
        target = current["zone_tol"] + 1.0
        capped = clamp(cap_delta(current["zone_tol"], target, "zone_tol"), "zone_tol")
        if capped != current["zone_tol"]:
            new["zone_tol"] = round(capped, 2)
            reasons.append(
                f"ABANDON ZONE = {zone_rejections}/{total_rej} rejections "
                f"({zone_rejections * 100 // total_rej}%) -> "
                f"ZONE_TOL {current['zone_tol']} -> {new['zone_tol']} (zone widened)"
            )

    sec_rejections = sum(v for k, v in breakdown.items() if "SAFETY" in k or "SECURITE" in k)
    if sec_rejections / total_rej > 0.40 and sec_rejections >= 3:
        target = current["min_distance"] - 0.1
        capped = clamp(cap_delta(current["min_distance"], target, "min_distance"), "min_distance")
        if capped != current["min_distance"]:
            new["min_distance"] = round(capped, 3)
            reasons.append(
                f"ABANDON SAFETY = {sec_rejections}/{total_rej} rejections -> "
                f"MIN_DISTANCE {current['min_distance']} -> {new['min_distance']}"
            )

    return new, reasons


def apply_changes(current: dict, new: dict, agg: dict, reasons: list[str]) -> bool:
    keys = ("min_rr", "zone_tol", "min_distance")
    has_change = any(current.get(k) != new.get(k) for k in keys)
    if not has_change:
        return False

    history = current.get("_history", [])
    history.append({
        "ts": datetime.now().isoformat(),
        "window_days": agg["days"],
        "win_rate": agg["win_rate"],
        "closed": agg["closed"],
        "rejected": agg["rejected"],
        "before": {k: current.get(k) for k in keys},
        "after": {k: new.get(k) for k in keys},
        "reasons": reasons,
    })
    history = history[-50:]

    payload = {
        "_comment": current.get("_comment", "Auto-tuned thresholds"),
        "min_rr": new["min_rr"],
        "zone_tol": new["zone_tol"],
        "min_distance": new["min_distance"],
        "volume": new.get("volume", 0.05),
        "_history": history,
    }
    with RISK_CONFIG.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return True


def format_report(agg, current, new, reasons, applied) -> str:
    lines = [f"Auto-tuner — {agg['days']}-day window", ""]
    lines.append(
        f"Stats: {agg['closed']} closed trades ({agg['wins']}W / {agg['losses']}L), "
        f"win rate {agg['win_rate'] * 100:.0f}%, PnL ${agg['pnl']:+.2f}"
    )
    lines.append(f"Rejections: {agg['rejected']} ({agg['rejection_rate'] * 100:.0f}%)")
    if agg["rejection_breakdown"]:
        for k, v in agg["rejection_breakdown"].items():
            lines.append(f"  - {k}: {v}")
    lines.append("")
    if not reasons:
        lines.append("No adjustment required — config stable.")
    elif not applied:
        lines.append("Adjustments proposed but not applied (delta = 0 after clamp/cap).")
    else:
        lines.append("Config adjusted:")
        for r in reasons:
            lines.append(f"  - {r}")
    lines.append("")
    lines.append(
        f"Current: MIN_RR={new['min_rr']} ZONE_TOL={new['zone_tol']} "
        f"MIN_DISTANCE={new['min_distance']}"
    )
    return "\n".join(lines)


def main():
    if not RISK_CONFIG.exists():
        print(f"ERROR: {RISK_CONFIG} not found")
        sys.exit(1)

    with RISK_CONFIG.open("r", encoding="utf-8") as f:
        current = json.load(f)

    records = load_history()
    if not records:
        print("No history available — nothing to analyse.")
        sys.exit(0)

    agg = aggregate_window(records)
    new, reasons = propose_changes(current, agg)
    applied = apply_changes(current, new, agg, reasons) if reasons else False
    print(format_report(agg, current, new, reasons, applied))


if __name__ == "__main__":
    main()
