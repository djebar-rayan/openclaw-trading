"""MT5 K-line connectivity smoke test.

Confirms that:
1. MT5 desktop client is reachable.
2. Login credentials in env / config.py are valid.
3. The configured symbol is selectable.
4. K-line data can be pulled at M1, H1, and D1 timeframes.

Run on a fresh setup after `openclaw doctor --fix` and before launching
the agent — quickest way to catch a misconfigured MT5 install.
"""

import os
import sys
from datetime import datetime

import MetaTrader5 as mt5

ACCOUNT_CONFIG = {
    "login": int(os.getenv("MT5_LOGIN", "0")),
    "password": os.getenv("MT5_PASSWORD", ""),
    "server": os.getenv("MT5_SERVER", "MetaQuotes-Demo"),
    "symbol": os.getenv("MT5_SYMBOL", "XAUUSD"),
}

try:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import MT5_CONFIG
    ACCOUNT_CONFIG.update(MT5_CONFIG)
except ImportError:
    pass


config = ACCOUNT_CONFIG
symbol = config["symbol"]

print("MT5 K-line data read test")
print("=" * 50)

if not mt5.initialize():
    print("ERROR: MT5 initialization failed")
    sys.exit(1)
print("OK: MT5 initialization successful")

if not mt5.login(config["login"], config["password"], server=config["server"]):
    print("ERROR: Login failed")
    mt5.shutdown()
    sys.exit(1)
print("OK: Login successful")

if not mt5.symbol_select(symbol, True):
    print(f"ERROR: Unable to select symbol {symbol}")
    mt5.shutdown()
    sys.exit(1)
print(f"OK: Symbol {symbol} selected")

print("\n" + "-" * 50)
print("Test 1: Live price")
print("-" * 50)

tick = mt5.symbol_info_tick(symbol)
if tick:
    print("OK: live tick retrieved")
    print(f"  Bid:  {tick.bid:.3f}")
    print(f"  Ask:  {tick.ask:.3f}")
    print(f"  Last: {tick.last}")
    print(f"  Time: {datetime.fromtimestamp(tick.time)}")
else:
    print("ERROR: no live tick")

for tf_name, tf_const, n in (("M1", mt5.TIMEFRAME_M1, 10),
                              ("H1", mt5.TIMEFRAME_H1, 5),
                              ("D1", mt5.TIMEFRAME_D1, 3)):
    print("\n" + "-" * 50)
    print(f"Test: K-line data ({tf_name})")
    print("-" * 50)
    rates = mt5.copy_rates_from(symbol, tf_const, datetime.now(), n)
    if rates is not None:
        print(f"OK: retrieved {len(rates)} {tf_name} candles")
        for i in range(min(2, len(rates))):
            idx = len(rates) - 1 - i
            rate = rates[idx]
            time_str = datetime.fromtimestamp(rate[0]).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  [{i + 1}] {time_str}  open={rate[1]:.3f}  close={rate[4]:.3f}")
    else:
        print(f"ERROR: cannot get {tf_name} K-lines")

print("\n" + "=" * 50)
print("Test complete")
mt5.shutdown()
