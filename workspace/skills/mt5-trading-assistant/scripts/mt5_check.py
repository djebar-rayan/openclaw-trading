"""Quick MT5 account status check: connection, balance, positions, spread."""

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


def quick_check():
    config = ACCOUNT_CONFIG
    symbol = config.get("symbol", "XAUUSD")

    print("MT5 quick account check")
    print("=" * 50)

    if not mt5.initialize():
        print("CRITICAL: MT5 initialization failed. Terminal unreachable.")
        return False
    print("OK: MT5 connection established")

    if not mt5.login(config["login"], config["password"], server=config["server"]):
        print("CRITICAL: Login failed. Check credentials or server.")
        mt5.shutdown()
        return False
    print("OK: Login successful")

    account = mt5.account_info()
    if account:
        print("[Account]")
        print(f"   Login: {account.login}")
        print(f"   Server: {account.server}")
        print(f"   Balance: ${account.balance:.2f}")
        print(f"   Equity: ${account.equity:.2f}")
        print(f"   Free margin: ${account.margin_free:.2f}")
        print(f"   Leverage: 1:{account.leverage}")
        print(f"   Trade mode: {'Demo' if account.trade_mode == 1 else 'Real'}")
    else:
        print("CRITICAL: Unable to get account information")

    if not mt5.symbol_select(symbol, True):
        print(f"CRITICAL: Unable to select symbol {symbol}")
    else:
        print(f"\n[Symbol] {symbol}")
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            spread_value = tick.ask - tick.bid
            print(f"   Bid: {tick.bid:.2f}")
            print(f"   Ask: {tick.ask:.2f}")
            print(f"   Spread: {spread_value:.2f}")
            if spread_value > 0.40:
                print(f"   WARNING: spread is unusually wide ({spread_value:.2f}).")
            print(f"   Time: {datetime.fromtimestamp(tick.time)}")
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            print(f"   Contract size: {symbol_info.trade_contract_size}")
            print(f"   Min lot: {symbol_info.volume_min}")
            print(f"   Max lot: {symbol_info.volume_max}")

    positions = mt5.positions_get(symbol=symbol)
    if positions is not None:
        if positions:
            print(f"\n[Positions] {len(positions)} open")
            total_profit = 0.0
            for i, pos in enumerate(positions[:5]):
                pos_type = "Buy" if pos.type == 0 else "Sell"
                sign = "+" if pos.profit > 0 else ""
                print(f"   {i + 1}. Ticket {pos.ticket} {pos_type} {pos.volume} lot")
                print(f"      Open: {pos.price_open:.2f}  Current: {pos.price_current:.2f}  PnL: {sign}${pos.profit:.2f}")
                total_profit += pos.profit
            if len(positions) > 5:
                print(f"   … +{len(positions) - 5} more")
            print(f"   Total PnL: ${total_profit:.2f}")
        else:
            print("\n[Positions] None")
    else:
        print("\n[Positions] CRITICAL: cannot retrieve positions")

    print("\n[System]")
    print(f"   API version: {mt5.__version__ if hasattr(mt5, '__version__') else 'unknown'}")
    err = mt5.last_error()
    if err[0] != 1:
        print(f"   Last error: {err}")

    print("\n" + "=" * 50)
    print("Check completed. OK.")
    mt5.shutdown()
    return True


def main():
    try:
        sys.exit(0 if quick_check() else 1)
    except Exception as e:
        import traceback
        print(f"CRITICAL: check error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
