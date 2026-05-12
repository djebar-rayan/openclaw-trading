"""One-shot account + market snapshot for the configured MT5 symbol."""

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

print("=" * 70)
print("MT5 account snapshot")
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Account: {config['login']} | Server: {config['server']}")
print(f"Symbol: {symbol}")
print("=" * 70)

if not mt5.initialize():
    print("ERROR: MT5 initialization failed")
    sys.exit(1)

if not mt5.login(config["login"], config["password"], server=config["server"]):
    print("ERROR: Login failed")
    mt5.shutdown()
    sys.exit(1)

if not mt5.symbol_select(symbol, True):
    print(f"ERROR: Unable to select symbol {symbol}")
    mt5.shutdown()
    sys.exit(1)

tick = mt5.symbol_info_tick(symbol)
if tick:
    print("[Market] Live quote")
    print(f"   Bid: {tick.bid:.3f}")
    print(f"   Ask: {tick.ask:.3f}")
    print(f"   Spread: {tick.ask - tick.bid:.3f}")
    print(f"   Time: {datetime.fromtimestamp(tick.time)}")
else:
    print("[Market] No quote available")

account = mt5.account_info()
if account:
    print("\n[Account]")
    print(f"   Balance: ${account.balance:.2f}")
    print(f"   Equity: ${account.equity:.2f}")
    print(f"   Free margin: ${account.margin_free:.2f}")
    print(f"   Leverage: 1:{account.leverage}")

positions = mt5.positions_get(symbol=symbol)
if positions:
    total = sum(pos.profit for pos in positions)
    print(f"\n[Positions] {len(positions)} open")
    for i, pos in enumerate(positions[:3]):
        pos_type = "Buy" if pos.type == 0 else "Sell"
        sign = "+" if pos.profit > 0 else ""
        print(f"   {i + 1}. {pos.ticket} {pos_type} {pos.volume} lot")
        print(f"      Open: {pos.price_open:.3f}  Current: {pos.price_current:.3f}  PnL: {sign}${pos.profit:.2f}")
    if len(positions) > 3:
        print(f"   … +{len(positions) - 3} more")
    print(f"   Total PnL: ${total:.2f}")
else:
    print("\n[Positions] None")

print("\n" + "=" * 70)
mt5.shutdown()
