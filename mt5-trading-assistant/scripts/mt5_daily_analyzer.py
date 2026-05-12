#!/usr/bin/env python3
"""Daily trade analyzer.

Pulls every deal/order MT5 produced for the day, reconstructs each trade
(entry + exit pair), classifies win / loss / breakeven, factors in signals
rejected by the ABANDON safety checks (parsed from the fast-path log), and
writes a structured summary to:

    trade_history/YYYY-MM-DD.json

The same payload is rendered as a human-readable report on stdout, so a
scheduled job can pipe it straight to Telegram.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5

ACCOUNT_CONFIG = {
    "login": int(os.getenv("MT5_LOGIN", "0")),
    "password": os.getenv("MT5_PASSWORD", ""),
    "server": os.getenv("MT5_SERVER", "MetaQuotes-Demo"),
    "symbol": os.getenv("MT5_SYMBOL", "XAUUSD"),
    "magic": 100000,
}

try:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import MT5_CONFIG  # type: ignore
    ACCOUNT_CONFIG.update(MT5_CONFIG)
except ImportError:
    pass

SKILL_DIR = Path(__file__).resolve().parents[1]
HISTORY_DIR = SKILL_DIR / "trade_history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
FASTPATH_LOG = SKILL_DIR / "fastpath" / "fastpath_bot.log"


def init_mt5() -> bool:
    if not mt5.initialize():
        return False
    if not mt5.login(
        ACCOUNT_CONFIG["login"],
        ACCOUNT_CONFIG["password"],
        server=ACCOUNT_CONFIG["server"],
    ):
        mt5.shutdown()
        return False
    return True


def get_day_window(target_date: datetime | None = None) -> tuple[datetime, datetime]:
    if target_date is None:
        target_date = datetime.now()
    start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def fetch_deals(start: datetime, end: datetime) -> list[dict]:
    deals = mt5.history_deals_get(start, end)
    return [d._asdict() for d in deals] if deals else []


def fetch_orders(start: datetime, end: datetime) -> list[dict]:
    orders = mt5.history_orders_get(start, end)
    return [o._asdict() for o in orders] if orders else []


def reconstruct_trades(deals: list[dict], orders: list[dict]) -> list[dict]:
    """Group deals into closed trades by position_id."""
    by_position: dict[int, list[dict]] = {}
    for d in deals:
        pid = d.get("position_id")
        if not pid:
            continue
        by_position.setdefault(pid, []).append(d)

    orders_by_position = {o.get("position_id"): o for o in orders if o.get("position_id")}

    trades = []
    for pid, dlist in by_position.items():
        dlist.sort(key=lambda d: d.get("time", 0))
        entry = next((d for d in dlist if d.get("entry") == mt5.DEAL_ENTRY_IN), None)
        exit_ = next((d for d in dlist if d.get("entry") == mt5.DEAL_ENTRY_OUT), None)
        if not entry:
            continue
        order = orders_by_position.get(pid, {})

        deal_type = entry.get("type")
        side = (
            "BUY" if deal_type == mt5.DEAL_TYPE_BUY
            else "SELL" if deal_type == mt5.DEAL_TYPE_SELL
            else f"type{deal_type}"
        )
        entry_time = datetime.fromtimestamp(entry.get("time", 0)).isoformat()
        exit_time = datetime.fromtimestamp(exit_.get("time", 0)).isoformat() if exit_ else None
        duration_min = round((exit_.get("time", 0) - entry.get("time", 0)) / 60.0, 1) if exit_ else None

        profit = sum(d.get("profit", 0.0) for d in dlist)
        swap = sum(d.get("swap", 0.0) for d in dlist)
        commission = sum(d.get("commission", 0.0) for d in dlist)
        net = profit + swap + commission

        exit_reason = "open"
        if exit_:
            comment = (exit_.get("comment") or "").lower()
            if "sl" in comment or "stop" in comment:
                exit_reason = "sl_hit"
            elif "tp" in comment:
                exit_reason = "tp_hit"
            else:
                exit_reason = "manual_or_other"

        trades.append({
            "position_id": pid,
            "ticket_entry": entry.get("ticket"),
            "ticket_exit": exit_.get("ticket") if exit_ else None,
            "symbol": entry.get("symbol"),
            "side": side,
            "volume": entry.get("volume"),
            "entry_time": entry_time,
            "entry_price": entry.get("price"),
            "exit_time": exit_time,
            "exit_price": exit_.get("price") if exit_ else None,
            "sl": order.get("sl") or 0.0,
            "tp": order.get("tp") or 0.0,
            "duration_min": duration_min,
            "exit_reason": exit_reason,
            "gross_profit": round(profit, 2),
            "swap": round(swap, 2),
            "commission": round(commission, 2),
            "net_profit": round(net, 2),
            "magic": entry.get("magic"),
            "comment_entry": entry.get("comment"),
            "comment_exit": exit_.get("comment") if exit_ else None,
            "is_closed": exit_ is not None,
        })

    trades.sort(key=lambda t: t["entry_time"])
    return trades


REJECT_RE = re.compile(
    r"\[(?P<ts>[\d-]+ [\d:]+)\] FAST-PATH .* -> . (?P<reason>ABANDON \S+|MT5 failure).*?"
    r"(?:Risk=(?P<risk>[\d.]+).*?Reward=(?P<reward>[\d.]+))?",
    re.UNICODE,
)


def parse_rejected_today(target_date: datetime) -> list[dict]:
    if not FASTPATH_LOG.exists():
        return []
    day = target_date.strftime("%Y-%m-%d")
    out: list[dict] = []
    try:
        with FASTPATH_LOG.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if day not in line:
                    continue
                m = REJECT_RE.search(line)
                if not m:
                    continue
                out.append({
                    "ts": m.group("ts"),
                    "reason": m.group("reason"),
                    "risk": float(m.group("risk")) if m.group("risk") else None,
                    "reward": float(m.group("reward")) if m.group("reward") else None,
                    "raw": line.rstrip(),
                })
    except OSError:
        pass
    return out


def aggregate(trades, rejected, starting_balance, ending_balance) -> dict:
    closed = [t for t in trades if t["is_closed"]]
    open_ = [t for t in trades if not t["is_closed"]]
    wins = [t for t in closed if t["net_profit"] > 0]
    losses = [t for t in closed if t["net_profit"] < 0]
    breakeven = [t for t in closed if t["net_profit"] == 0]

    total_pnl = sum(t["net_profit"] for t in closed)
    win_rate = round(len(wins) / len(closed), 3) if closed else 0.0
    avg_win = round(sum(t["net_profit"] for t in wins) / len(wins), 2) if wins else 0.0
    avg_loss = round(sum(t["net_profit"] for t in losses) / len(losses), 2) if losses else 0.0
    profit_factor = (
        round(abs(sum(t["net_profit"] for t in wins) / sum(t["net_profit"] for t in losses)), 2)
        if losses else None
    )

    rejection_breakdown: dict[str, int] = {}
    for r in rejected:
        rejection_breakdown[r["reason"]] = rejection_breakdown.get(r["reason"], 0) + 1

    return {
        "trades_total": len(trades),
        "trades_closed": len(closed),
        "trades_open": len(open_),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate": win_rate,
        "total_pnl": round(total_pnl, 2),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "starting_balance": starting_balance,
        "ending_balance": ending_balance,
        "rejected_signals": len(rejected),
        "rejection_breakdown": rejection_breakdown,
    }


def format_report(date_str, summary, trades, rejected) -> str:
    lines = [f"Trading report — {date_str}", ""]
    pnl = summary["total_pnl"]
    pnl_sign = "+" if pnl >= 0 else ""
    lines.append(f"Net PnL: {pnl_sign}${pnl:.2f}")
    if summary["starting_balance"] is not None and summary["ending_balance"] is not None:
        lines.append(f"Balance: ${summary['starting_balance']:.2f} -> ${summary['ending_balance']:.2f}")
    lines.append("")
    lines.append(
        f"Trades: {summary['trades_closed']} closed "
        f"({summary['wins']}W / {summary['losses']}L / {summary['breakeven']}BE) | "
        f"win rate {summary['win_rate'] * 100:.0f}%"
    )
    if summary["trades_open"]:
        lines.append(f"Still open: {summary['trades_open']}")
    if summary["profit_factor"] is not None:
        lines.append(f"Profit factor: {summary['profit_factor']}")

    if trades:
        lines.append("")
        lines.append("Trades detail:")
        for t in trades[:10]:
            if t["is_closed"]:
                marker = "[W]" if t["net_profit"] > 0 else ("[L]" if t["net_profit"] < 0 else "[BE]")
                lines.append(
                    f"  {marker} {t['side']} {t['symbol']} {t['volume']} "
                    f"{t['entry_price']} -> {t['exit_price']} ({t['exit_reason']}) "
                    f"= ${t['net_profit']:+.2f} in {t['duration_min']}min"
                )
            else:
                lines.append(f"  [open] {t['side']} {t['symbol']} {t['volume']} @ {t['entry_price']}")
        if len(trades) > 10:
            lines.append(f"  … +{len(trades) - 10} more")

    if rejected:
        lines.append("")
        lines.append(f"Rejected signals: {summary['rejected_signals']}")
        for reason, count in summary["rejection_breakdown"].items():
            lines.append(f"  - {reason}: {count}")

    return "\n".join(lines)


def main():
    target_date = datetime.now()
    if len(sys.argv) > 1:
        try:
            target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: invalid date {sys.argv[1]}, expected YYYY-MM-DD")
            sys.exit(2)

    if not init_mt5():
        print("ERROR: MT5 connection failed")
        sys.exit(1)

    try:
        start, end = get_day_window(target_date)
        deals = fetch_deals(start, end)
        orders = fetch_orders(start, end)
        trades = reconstruct_trades(deals, orders)
        rejected = parse_rejected_today(target_date)

        ai = mt5.account_info()
        ending_balance = ai.balance if ai else None
        day_pnl = sum(t["net_profit"] for t in trades if t["is_closed"])
        starting_balance = round(ending_balance - day_pnl, 2) if ending_balance is not None else None

        summary = aggregate(trades, rejected, starting_balance, ending_balance)
        date_str = target_date.strftime("%Y-%m-%d")
        record = {
            "date": date_str,
            "account": ACCOUNT_CONFIG["login"],
            "summary": summary,
            "trades": trades,
            "rejected_signals": rejected,
            "generated_at": datetime.now().isoformat(),
        }

        out_path = HISTORY_DIR / f"{date_str}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2, default=str)

        print(format_report(date_str, summary, trades, rejected))
        print()
        print(f"Saved: {out_path}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
