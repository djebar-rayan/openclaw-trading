---
name: mt5-trading-assistant
description: |
  MetaTrader 5 automation skill. Use when the user asks to connect to MT5,
  execute trades, monitor an account, analyse trade history, or automate
  signal-driven trading.
triggers:
  - MT5
  - MetaTrader
  - XAUUSD
  - GOLD
  - BUY
  - SELL
  - StopLoss
  - Takeprofit
---

# MT5 Trading Assistant

**Safety lock — volume is always 0.05.** Every executor force-clamps any
other value back to 0.05. Do not try to "fix" this; it is intentional.

Complete automation suite for MetaTrader 5: account monitoring, trade
execution with multi-layer safety, market snapshots, daily P&L
reconstruction, nightly ML retraining, and auto-tuned risk thresholds.

## Quick start

### Prerequisites

- Python 3.10+ with `MetaTrader5`, `pandas`, `numpy`, `ta`, `scikit-learn`
  (see the repo-level `requirements.txt`).
- MT5 desktop client running, logged in, with AutoTrading enabled (F7).

### Configure

Either set `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_SYMBOL` in
`.env`, or `cp references/config_template.py config.py` and fill it in.

### Use

```bash
# Account / market health
python scripts/mt5_check.py
python scripts/mt5_snapshot.py

# Market orders (zone form: volume zone_min zone_max SL TP)
python scripts/mt5_buy.py  0.05 2400 2405 2390 2415
python scripts/mt5_sell.py 0.05 2400 2405 2410 2385

# Position management
python scripts/mt5_close_all.py all
python scripts/mt5_close_all.py 12345678        # by ticket
```

## Script reference

### `mt5_buy.py` / `mt5_sell.py`

```
python scripts/mt5_buy.py  <volume> <zone_min> <zone_max> <SL> <TP>
python scripts/mt5_sell.py <volume> <zone_min> <zone_max> <SL> <TP>
```

- Use `0 0` for `zone_min zone_max` when the signal gives a single price.
- Three safety checks run before the order: zone validation, anti-late TP,
  risk/reward minimum. Any failure prints `ABANDON <reason>` and exits 1
  without sending the order.
- `MT5_TRUSTED=1` env var bypasses the three checks (use only for sources
  whose track record you have verified yourself).

### `mt5_close_all.py`

```
python scripts/mt5_close_all.py all          # everything on the configured symbol
python scripts/mt5_close_all.py magic        # only script-managed (magic 100001/100002)
python scripts/mt5_close_all.py <ticket>     # one specific ticket
```

### `mt5_check.py`

Connection + balance + open positions + spread health (warns on wide spread).

### `mt5_snapshot.py`

Condensed one-screen view: live quote, equity, free margin, top open
positions and their PnL.

### `mt5_daily_analyzer.py`

```
python scripts/mt5_daily_analyzer.py [YYYY-MM-DD]
```

Reconstructs the day's trades, classifies them as win / loss / breakeven,
parses signals rejected by the safety checks from the fast-path log, and
writes the result to `trade_history/<date>.json`. Stdout is a
human-readable report suitable for piping to Telegram.

### `mt5_nightly_learner.py`

Idempotent overnight pipeline: ingest closed trades → store features
in `learning.db` → call `mt5_auto_tuner.py` → retrain a
`RandomForestClassifier` (when ≥30 cumulative samples and both classes
present) → record `cv_score` in `model_versions`.

### `mt5_auto_tuner.py`

Reads `trade_history/*.json` over a 7-day window, applies four
deterministic adjustment rules with hard limits and a max delta per
night, and rewrites `risk_config.json`. Each change is appended to
`risk_config.json._history` for audit.

## Fast-path executor

`fastpath/fastpath.py` is a regex-only signal parser (~1 ms parse) that
plugs into MT5 without going through an LLM. `fastpath/fastpath_bot.py`
wraps it as a Telegram bot using long-polling — end-to-end latency from
signal reception to MT5 fill is about 1 second.

## Security

- Never commit `config.py`, `.env`, `learning.db`, or `trade_history/`.
  The repo's `.gitignore` already excludes them.
- Demo first. The scripts default to `MetaQuotes-Demo`; switch only after
  you've watched a full week on demo without surprises.
- The 0.05-lot hard-cap is non-negotiable. Position sizing for higher
  volumes should be implemented through *multiple* trades and additional
  risk modelling, not by editing this constant.
