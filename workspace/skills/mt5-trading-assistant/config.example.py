"""
MT5 account configuration.

Copy this file to ``config.py`` next to it and fill in your broker details,
**or** export the matching environment variables and let ``os.getenv`` pick
them up. Either path works; the env-var path is preferred so credentials
never live on disk.

config.py is gitignored.
"""

import os

MT5_CONFIG = {
    "login": int(os.getenv("MT5_LOGIN", "0")),
    "password": os.getenv("MT5_PASSWORD", ""),
    "server": os.getenv("MT5_SERVER", "MetaQuotes-Demo"),
    "symbol": os.getenv("MT5_SYMBOL", "XAUUSD"),
    "default_volume": float(os.getenv("VOLUME_PER_TRADE", "0.05")),
    "default_magic": 100000,
    "deviation": 50,
}
