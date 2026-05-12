"""Shared feature extraction for trade learning + autonomous scoring.

extract_features(symbol, entry_time, side) -> dict of ~30 numeric columns,
computed from MT5 klines (M15 + H1 + H4) at the moment of trade entry.

Used by:
- mt5_nightly_learner.py (retrospective on closed trades)
- a real-time scoring path (same code, same column names)

Returns None if MT5 is unreachable or insufficient klines are available.
Callers must handle None and skip the row.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

try:
    import pandas as pd
    from ta.trend import SMAIndicator, MACD
    from ta.momentum import RSIIndicator
    from ta.volatility import AverageTrueRange, BollingerBands
    _TA_OK = True
except ImportError:
    pd = None
    _TA_OK = False

from config import MT5_CONFIG

TIMEFRAMES = {
    "m15": getattr(mt5, "TIMEFRAME_M15", 15) if mt5 else 15,
    "h1": getattr(mt5, "TIMEFRAME_H1", 16385) if mt5 else 16385,
    "h4": getattr(mt5, "TIMEFRAME_H4", 16388) if mt5 else 16388,
}

LOOKBACK_BARS = 250


_mt5_initialized = False


def _ensure_mt5() -> bool:
    global _mt5_initialized
    if mt5 is None:
        return False
    if _mt5_initialized:
        return True
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"],
    ):
        return False
    _mt5_initialized = True
    return True


def _fetch_klines(symbol: str, timeframe: int, end_time: datetime, bars: int):
    if not _ensure_mt5() or pd is None:
        return None
    rates = mt5.copy_rates_from(symbol, timeframe, end_time, bars)
    if rates is None or len(rates) < 50:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def _add_indicators(df):
    close = df["close"]
    df["sma20"] = SMAIndicator(close, window=20).sma_indicator()
    df["sma50"] = SMAIndicator(close, window=50).sma_indicator()
    df["sma200"] = SMAIndicator(close, window=200).sma_indicator()
    df["rsi14"] = RSIIndicator(close, window=14).rsi()
    macd = MACD(close, window_fast=12, window_slow=26, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()
    bb = BollingerBands(close, window=20, window_dev=2)
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_upper"] = bb.bollinger_hband()
    df["atr14"] = AverageTrueRange(df["high"], df["low"], close, window=14).average_true_range()
    return df


def _row_at(df, t: datetime):
    """Return the last fully-closed candle strictly before t."""
    mask = df["time"] <= t
    if not mask.any():
        return None
    return df[mask].iloc[-1]


def extract_features(
    entry_time: datetime,
    side: str,
    entry_price: float,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    symbol: Optional[str] = None,
) -> Optional[dict]:
    """Return a flat dict of features at entry_time, or None on failure."""
    if pd is None or not _TA_OK:
        return None
    sym = symbol or MT5_CONFIG["symbol"]

    out = {
        "symbol": sym,
        "side": side.lower(),
        "entry_price": float(entry_price),
        "entry_hour": entry_time.hour,
        "entry_weekday": entry_time.weekday(),
        "entry_ts": entry_time.isoformat(),
    }

    end = entry_time + timedelta(minutes=1)
    timeframes_fetched = 0
    for tf_name, tf_const in TIMEFRAMES.items():
        df = _fetch_klines(sym, tf_const, end, LOOKBACK_BARS)
        if df is None:
            continue
        df = _add_indicators(df)
        row = _row_at(df, entry_time)
        if row is None:
            continue
        timeframes_fetched += 1
        close = float(row["close"])
        for col in ("sma20", "sma50", "sma200", "rsi14",
                    "macd", "macd_signal", "macd_hist",
                    "bb_lower", "bb_mid", "bb_upper", "atr14"):
            val = row.get(col)
            out[f"{tf_name}_{col}"] = float(val) if pd.notna(val) else None
        if pd.notna(row.get("sma20")):
            out[f"{tf_name}_dist_sma20_pct"] = (close - row["sma20"]) / close * 100
        if pd.notna(row.get("atr14")) and row["atr14"]:
            out[f"{tf_name}_atr_pct"] = row["atr14"] / close * 100

    if timeframes_fetched == 0:
        return None

    if sl is not None and tp is not None and out.get("h1_atr14"):
        atr = out["h1_atr14"]
        out["sl_distance_atr"] = abs(entry_price - sl) / atr if atr else None
        out["tp_distance_atr"] = abs(entry_price - tp) / atr if atr else None
        risk = abs(entry_price - sl)
        reward = abs(entry_price - tp)
        out["rr_ratio"] = reward / risk if risk else None

    tick = mt5.symbol_info_tick(sym) if _ensure_mt5() else None
    if tick:
        out["current_spread"] = float(tick.ask - tick.bid)

    return out


FEATURE_COLUMNS = [
    "entry_price", "entry_hour", "entry_weekday",
    "current_spread", "sl_distance_atr", "tp_distance_atr", "rr_ratio",
]
for _tf in ("m15", "h1", "h4"):
    FEATURE_COLUMNS += [
        f"{_tf}_sma20", f"{_tf}_sma50", f"{_tf}_sma200", f"{_tf}_rsi14",
        f"{_tf}_macd", f"{_tf}_macd_signal", f"{_tf}_macd_hist",
        f"{_tf}_bb_lower", f"{_tf}_bb_mid", f"{_tf}_bb_upper", f"{_tf}_atr14",
        f"{_tf}_dist_sma20_pct", f"{_tf}_atr_pct",
    ]
