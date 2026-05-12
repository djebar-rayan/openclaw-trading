"""Close MT5 positions in bulk or by ticket.

Usage:
    python mt5_close_all.py all              # all positions for configured symbol
    python mt5_close_all.py magic            # script-managed only (magic 100001/100002)
    python mt5_close_all.py <ticket>         # one specific ticket
"""

import os
import sys
import time

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


def close_all_positions(symbol=None, magic_numbers=None):
    config = ACCOUNT_CONFIG
    if symbol is None:
        symbol = config.get("symbol", "XAUUSD")

    if not mt5.initialize():
        print("ERROR: MT5 initialization failed")
        return False
    if not mt5.login(config["login"], config["password"], server=config["server"]):
        print("ERROR: Login failed")
        mt5.shutdown()
        return False

    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        print(f"INFO: no open positions for {symbol}")
        mt5.shutdown()
        return True

    print(f"Found {len(positions)} open position(s) for {symbol}")
    total_profit = 0.0
    closed_count = 0

    for pos in positions:
        if magic_numbers and pos.magic not in magic_numbers:
            print(f"Skipping ticket {pos.ticket} (magic: {pos.magic})")
            continue
        close_type = mt5.ORDER_TYPE_BUY if pos.type == 1 else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            print(f"ERROR: no price for {symbol}, skipping {pos.ticket}")
            continue
        close_price = tick.ask if close_type == mt5.ORDER_TYPE_BUY else tick.bid

        print(f"Closing ticket {pos.ticket}: {'Buy' if pos.type == 0 else 'Sell'} "
              f"{pos.volume} @ open={pos.price_open:.3f} current={pos.price_current:.3f} "
              f"close={close_price:.3f} PnL=${pos.profit:.2f}")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": pos.ticket,
            "price": close_price,
            "deviation": 50,
            "magic": pos.magic,
            "comment": "Batch close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"  → Closed at {result.price:.3f}")
            total_profit += pos.profit
            closed_count += 1
        else:
            print(f"  → Failed: {result.comment} (code {result.retcode})")
        time.sleep(0.5)

    print(f"\nSummary: closed {closed_count}/{len(positions)}, total PnL ${total_profit:.2f}")
    account = mt5.account_info()
    if account:
        print(f"Balance: ${account.balance:.2f}  Equity: ${account.equity:.2f}")

    mt5.shutdown()
    return True


def close_by_magic(symbol=None, magic_numbers=(100001, 100002)):
    config = ACCOUNT_CONFIG
    if symbol is None:
        symbol = config.get("symbol", "XAUUSD")
    print(f"Closing {symbol} positions with magic={magic_numbers}")
    return close_all_positions(symbol, set(magic_numbers))


def close_specific_ticket(ticket_id):
    config = ACCOUNT_CONFIG
    if not mt5.initialize():
        print("ERROR: MT5 initialization failed")
        return False
    if not mt5.login(config["login"], config["password"], server=config["server"]):
        print("ERROR: Login failed")
        mt5.shutdown()
        return False

    positions = mt5.positions_get(ticket=ticket_id)
    if not positions:
        print(f"Ticket {ticket_id} not found")
        mt5.shutdown()
        return False

    pos = positions[0]
    symbol = pos.symbol
    print(f"Closing ticket {ticket_id}: {'Buy' if pos.type == 0 else 'Sell'} "
          f"{pos.volume} {symbol} @ {pos.price_current:.3f} (PnL ${pos.profit:.2f})")

    close_type = mt5.ORDER_TYPE_BUY if pos.type == 1 else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"ERROR: no price for {symbol}")
        mt5.shutdown()
        return False
    close_price = tick.ask if close_type == mt5.ORDER_TYPE_BUY else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": pos.volume,
        "type": close_type,
        "position": ticket_id,
        "price": close_price,
        "deviation": 50,
        "magic": pos.magic,
        "comment": "Close by ticket",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"Closed at {result.price:.3f}")
        success = True
    else:
        print(f"Failed: {result.comment} (code {result.retcode})")
        success = False
    mt5.shutdown()
    return success


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("usage:")
        print("  python mt5_close_all.py all          # all positions for configured symbol")
        print("  python mt5_close_all.py magic        # script-managed (magic 100001/100002)")
        print("  python mt5_close_all.py <ticket>     # close a specific ticket")
        return

    command = sys.argv[1]
    try:
        if command == "all":
            success = close_all_positions()
        elif command == "magic":
            success = close_by_magic()
        elif command.isdigit():
            success = close_specific_ticket(int(command))
        else:
            print(f"Unknown command: {command}")
            success = False
        sys.exit(0 if success else 1)
    except Exception as e:
        import traceback
        print(f"Execution error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
