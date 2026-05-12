"""
MT5 account configuration template.

Two recommended setups:

1. Environment variables (preferred — credentials never sit on disk):
   Export MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_SYMBOL and
   ``../config.example.py`` picks them up automatically.

2. Local file:
   Copy this file to ``../config.py`` and fill in your broker details.
   The fallback ``ACCOUNT_CONFIG.update(MT5_CONFIG)`` in each script
   will then take effect. ``config.py`` is gitignored.
"""

MT5_CONFIG = {
    "login": 12345678,                  # your MT5 account number
    "password": "your_password_here",   # your MT5 password
    "server": "Your-Broker-Server",     # MT5 server name (e.g. MetaQuotes-Demo)
    "symbol": "XAUUSD",                 # primary trading symbol
    "default_volume": 0.05,             # DO NOT raise — every script clamps it back
    "default_deviation": 50,            # acceptable slippage in points
    "default_magic": 100000,            # order magic number
    "max_risk_per_trade": 0.02,         # informational; not enforced by scripts
    "max_daily_loss": 0.10,             # informational; not enforced by scripts
    "refresh_interval": 5,              # seconds, used by monitoring scripts
}

# Broker-specific examples — pick the one that matches your account.

EXNESS_CONFIG = {
    "symbol_suffix": "m",                # e.g. XAUUSDm
    "server_prefix": "Exness-MT5Trial",
}

ICMARKETS_CONFIG = {
    "symbol": "XAUUSD",
    "server": "ICMarkets-MT5",
}
