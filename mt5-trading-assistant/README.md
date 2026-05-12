# mt5-trading-assistant

Self-contained MetaTrader 5 automation suite: order execution, account
monitoring, daily P&L reporting, nightly machine-learning retraining,
and auto-tuned risk thresholds.

## Layout

```
mt5-trading-assistant/
├── config.example.py            # env-var-driven config (copy to config.py if you prefer a file)
├── features.py                  # ~30-column indicator pipeline used by the scorer
├── risk_config.json             # live risk thresholds (auto-tuner rewrites this)
├── scripts/
│   ├── mt5_buy.py               # zone-form buy: volume zone_min zone_max SL TP
│   ├── mt5_sell.py              # zone-form sell: same signature
│   ├── mt5_close_all.py         # bulk close by symbol / magic / ticket
│   ├── mt5_check.py             # account / position / spread health check
│   ├── mt5_snapshot.py          # one-shot account snapshot
│   ├── mt5_daily_analyzer.py    # reconstructs trades, writes trade_history/<date>.json
│   ├── mt5_nightly_learner.py   # ingests history, retrains a RandomForest scorer
│   └── mt5_auto_tuner.py        # adjusts risk_config.json from rolling stats
├── fastpath/
│   ├── fastpath.py              # regex-only signal parser + executor (~1 ms parse)
│   └── fastpath_bot.py          # Telegram bot using fastpath, sub-1s end-to-end latency
└── references/
    ├── config_template.py
    └── setup_guide.md
```

## Order signature — zone form

Every executor takes five arguments:

```
python scripts/mt5_buy.py  <volume> <zone_min> <zone_max> <SL> <TP>
python scripts/mt5_sell.py <volume> <zone_min> <zone_max> <SL> <TP>
```

`volume` is **always clamped to 0.05** — this is a hard safety lock; passing
anything else logs a warning and continues at 0.05. Pass `0 0` for the zone
when the signal gives a single price instead of a range.

## Three safety checks before any order

Each executor short-circuits the order with an `ABANDON …` line if any of:

1. **Zone validation** — refuse if market price is outside the signal zone
   by more than `zone_tol` (default 15 pips).
2. **Anti-late TP** — refuse if the TP is closer than `min_distance`
   (default 0.20 of the symbol's quote unit). Late signals frequently hit
   the SL before reaching their TP.
3. **Risk/reward** — refuse if `reward / risk < min_rr` (default 0.3).

All three thresholds live in `risk_config.json` and are re-read on every
invocation. The auto-tuner adjusts them nightly within hard limits.

Set `MT5_TRUSTED=1` in the environment to bypass checks 1–3 for a trusted
source (use sparingly — these are the safety net, not friction).

## Auto-improvement loop

```
mt5_daily_analyzer  ─▶ trade_history/<date>.json
       │
       ▼
mt5_nightly_learner ─▶ learning.db (features + outcomes)
       │
       ├── RandomForestClassifier retrain (>=30 samples)
       │
       ▼
mt5_auto_tuner      ─▶ risk_config.json  (delta-capped adjustments)
```

`mt5_auto_tuner` enforces hard limits (`MIN_RR ∈ [0.3, 2.0]`,
`ZONE_TOL ∈ [3, 25]`, `MIN_DISTANCE ∈ [0.1, 2.0]`) and a max delta per
night, so the system cannot drift catastrophically.

## Run the fast-path bot

```bash
python fastpath/fastpath_bot.py
```

Reads `TELEGRAM_BOT_TOKEN`, `FASTPATH_ALLOWED_SENDERS`,
`FASTPATH_LLM_FALLBACK` from the environment. Replies inline to allowed
senders; everything else is silently dropped and logged.

See [`references/setup_guide.md`](references/setup_guide.md) for the full
broker / credential / AutoTrading setup.
