#!/usr/bin/env python3
"""MT5 buy order with three layered safety checks.

Usage:
    python mt5_buy.py <volume> <zone_min> <zone_max> <SL> <TP>

Volume is force-clamped to 0.05. Use 0 0 for zone_min/zone_max when the
signal gives a single price instead of a range.

Safety checks (in order, each can short-circuit with ABANDON):
1. Zone validation — refuse if market price is outside the signal zone
   by more than ``zone_tol`` (from risk_config.json).
2. Anti-late TP (sniper) — refuse if the TP is closer than ``min_distance``;
   such signals usually arrive too late and hit the SL before the TP.
3. Risk/reward — refuse if RR < ``min_rr``.

Set MT5_TRUSTED=1 in the environment to bypass checks 1–3 for sources
whose track record is already trusted.
"""

import json
import os
import sys
from datetime import datetime

import MetaTrader5 as mt5

# Default config, overridden by config.py if present.
ACCOUNT_CONFIG = {
    "login": int(os.getenv("MT5_LOGIN", "0")),
    "password": os.getenv("MT5_PASSWORD", ""),
    "server": os.getenv("MT5_SERVER", "MetaQuotes-Demo"),
    "symbol": os.getenv("MT5_SYMBOL", "XAUUSD"),
    "deviation": 50,
    "magic": 100000,
    "comment_prefix": "MT5-Buy",
}

try:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import MT5_CONFIG
    ACCOUNT_CONFIG.update(MT5_CONFIG)
except ImportError:
    pass


_RISK_CFG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "risk_config.json"
)
_RISK_DEFAULTS = {"min_rr": 0.5, "zone_tol": 5.0, "min_distance": 0.5, "volume": 0.05}
try:
    with open(_RISK_CFG_PATH, "r", encoding="utf-8") as _f:
        _RISK_CFG = {**_RISK_DEFAULTS, **json.load(_f)}
except (OSError, ValueError):
    _RISK_CFG = _RISK_DEFAULTS


def buy_order(volume=0.05, zone_min=None, zone_max=None, sl=None, tp=None):
    config = ACCOUNT_CONFIG
    symbol = config.get("symbol", "XAUUSD")

    if not mt5.initialize():
        print("ERROR: MT5 initialization failed")
        return False

    if not mt5.login(config["login"], config["password"], server=config["server"]):
        print("ERROR: Login failed")
        mt5.shutdown()
        return False

    if not mt5.symbol_select(symbol, True):
        print(f"ERROR: Unable to select symbol {symbol}")
        mt5.shutdown()
        return False

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print("ERROR: Unable to get live price")
        mt5.shutdown()
        return False

    current_ask = tick.ask
    trusted = os.environ.get("MT5_TRUSTED") == "1"
    if trusted:
        print("[TRUSTED SOURCE] Bypassing RR / zone / distance checks.")

    zone_tol = _RISK_CFG["zone_tol"]
    if not trusted and zone_min and zone_max and zone_min > 0 and zone_max > 0:
        zlow, zhigh = sorted((zone_min, zone_max))
        if current_ask > zhigh + zone_tol:
            print(f"ABANDON ZONE: market price {current_ask:.2f} above signal zone "
                  f"[{zlow:.2f}-{zhigh:.2f}]. Expected bearish retrace risks the SL "
                  f"before the TP.")
            mt5.shutdown()
            return False
        if current_ask < zlow - zone_tol:
            print(f"ABANDON ZONE: market price {current_ask:.2f} below signal zone "
                  f"[{zlow:.2f}-{zhigh:.2f}] - {zone_tol} pips. Too early to buy, "
                  f"wait for the retrace.")
            mt5.shutdown()
            return False

    min_distance = _RISK_CFG["min_distance"]
    if not trusted and tp:
        if tp - current_ask < min_distance:
            print(f"ABANDON SAFETY: signal arrived too late. Market {current_ask:.2f} "
                  f"is too close to TP {tp}; risk of hitting SL first is excessive.")
            mt5.shutdown()
            return False

    min_rr = _RISK_CFG["min_rr"]
    if not trusted and sl and tp:
        risk = current_ask - sl
        reward = tp - current_ask
        if risk <= 0 or reward <= 0:
            print(f"ABANDON RR: SL ({sl}) or TP ({tp}) inconsistent with market "
                  f"entry {current_ask:.2f}.")
            mt5.shutdown()
            return False
        rr = reward / risk
        if rr < min_rr:
            print(f"ABANDON RR: risk/reward degraded to {rr:.2f} (min {min_rr}). "
                  f"Risk={risk:.2f} Reward={reward:.2f}. Signal stale.")
            mt5.shutdown()
            return False

    price = current_ask
    print(f"Buy {symbol} {volume} lot")
    print(f"Execution price: {price:.2f}")
    if sl:
        print(f"Stop loss: {sl:.2f}")
    if tp:
        print(f"Take profit: {tp:.2f}")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "deviation": config.get("deviation", 50),
        "magic": config.get("magic", 100001),
        "comment": f"{config.get('comment_prefix', 'MT5')}-Buy {volume}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    if sl:
        request["sl"] = sl
    if tp:
        request["tp"] = tp

    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print("Buy successful!")
        print(f"   Order ID: {result.order}")
        print(f"   Fill price: {result.price:.2f}")
        print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        positions = mt5.positions_get(ticket=result.order)
        if positions:
            pos = positions[0]
            print(f"   Open price: {pos.price_open:.2f}")
            print(f"   Current price: {pos.price_current:.2f}")
            print(f"   PnL: ${pos.profit:.2f}")
    else:
        print("Buy failed")
        print(f"   Error code: {result.retcode}")
        print(f"   Description: {result.comment}")

    mt5.shutdown()
    return result.retcode == mt5.TRADE_RETCODE_DONE


def main():
    if len(sys.argv) < 2:
        print("usage: mt5_buy.py <volume> <zone_min> <zone_max> <SL> <TP>")
        sys.exit(2)
    try:
        volume = float(sys.argv[1])
        if volume != 0.05:
            print(f"WARNING: trade volume {volume} clamped to 0.05 (safety lock).")
            volume = 0.05
        zone_min = float(sys.argv[2]) if len(sys.argv) > 2 and float(sys.argv[2]) > 0 else None
        zone_max = float(sys.argv[3]) if len(sys.argv) > 3 and float(sys.argv[3]) > 0 else None
        sl = float(sys.argv[4]) if len(sys.argv) > 4 and float(sys.argv[4]) > 0 else None
        tp = float(sys.argv[5]) if len(sys.argv) > 5 and float(sys.argv[5]) > 0 else None
        success = buy_order(volume, zone_min, zone_max, sl, tp)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Execution error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
