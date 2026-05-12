# Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Telegram                                │
│                                                                  │
│   signal channel A ─┐                                            │
│   signal channel B ─┼──▶ userbot.py (Telethon dual-listener)     │
│   signal channel … ─┘                                            │
│                                                                  │
└──────────────────────────────────┬───────────────────────────────┘
                                   │ valid signals only
                                   │ (direction + entry + SL + TP)
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                       OpenClaw inbox bot                         │
│                                                                  │
│   fastpath/fastpath_bot.py ──▶ fastpath/fastpath.py              │
│           │                          │ regex match?              │
│           │                          ▼                           │
│           │                    yes ─────▶ MT5 executor scripts   │
│           │                                                      │
│           └──── no ────▶  Mistral Medium 3.5 (LLM fallback)      │
│                            via NVIDIA NIM endpoint               │
│                                  │                               │
│                                  ▼                               │
│                            MT5 executor scripts                  │
└──────────────────────────────────┬───────────────────────────────┘
                                   │
                          three safety checks
                          (zone / anti-late TP / min RR)
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                   MetaTrader 5 desktop client                    │
│                                                                  │
│   order_send  ◀── mt5_buy.py / mt5_sell.py                       │
│                                                                  │
│   history ──▶ mt5_daily_analyzer.py ─▶ trade_history/YYYY-MM-DD  │
│                                                                  │
│   trade_history ──▶ mt5_nightly_learner.py                       │
│                       │                                          │
│                       ├── ingest features (M15/H1/H4)            │
│                       ├── retrain RandomForestClassifier         │
│                       └── invoke mt5_auto_tuner.py               │
│                                              │                   │
│                                              ▼                   │
│                                    rewrite risk_config.json      │
│                                    (within hard limits +         │
│                                     per-night max delta)         │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### `userbot.py` — Telethon dual-listener

A pair of Telethon user clients run in parallel, each on a different
account. This is intentional: each Telegram account can only see the
channels it actually joined, so two listeners can cover two disjoint
groups of signal channels without sharing membership.

Every inbound message goes through `is_valid_signal()` — four regexes
that demand a direction keyword, an entry, a stop-loss, and at least one
take-profit. Anything else (analysis, "TP1 hit", advertising) is logged
and dropped.

Survivors are forwarded to the `OPENCLAW_INBOX_BOT` chat with a short
header that names the source channel, plus a confirmation ping to the
owner via the Bot API.

### `mt5-trading-assistant/fastpath/`

Two files. `fastpath.py` is the regex parser, a pure-function module
exposing `parse_signal`, `exec_signal`, `format_reply` and `handle`.
`fastpath_bot.py` wraps it as a long-polling Telegram bot with
allow-listed senders, exponential backoff on Telegram errors, and an
optional LLM fallback through the local `openclaw agent` CLI.

The parser handles:
- `Zone: 4538-4545` → `zone_min=4538 zone_max=4545`
- `Entry 4585` → `zone_min=zone_max=4585`
- Direction inferred from SL/TP layout if the keyword is missing
- "Auto-flip": when the label and SL/TP layout disagree (a common typo
  in source signals), the SL/TP layout wins.

### `mt5-trading-assistant/scripts/`

Nine entry points, all stdout-driven so the same scripts work under cron,
Telegram, and a human terminal:

| Script | Purpose |
|---|---|
| `mt5_buy.py` | Zone-form buy with three safety checks |
| `mt5_sell.py` | Zone-form sell with three safety checks |
| `mt5_close_all.py` | Bulk close by `all` / `magic` / `<ticket>` |
| `mt5_check.py` | Account / positions / spread health check |
| `mt5_snapshot.py` | One-shot account + market snapshot |
| `mt5_daily_analyzer.py` | Rebuilds the day's trades into `trade_history/<date>.json` |
| `mt5_nightly_learner.py` | Idempotent overnight: ingest, retrain, tune |
| `mt5_auto_tuner.py` | Rewrites `risk_config.json` from rolling 7-day stats |

### `features.py`

Shared feature extractor used by both retrospective learning and the
real-time scorer. Pulls 250-bar windows on M15, H1, and H4, computes
SMA(20/50/200), RSI(14), MACD, Bollinger bands, ATR(14), and packages
them into ~30 numeric columns plus signal-specific metadata
(`sl_distance_atr`, `rr_ratio`, `current_spread`).

### `risk_config.json`

The live risk-knob file. Re-read on every executor invocation, so the
auto-tuner's changes take effect immediately without a restart. Keys:

| Key | Type | Default | Range |
|---|---|---|---|
| `min_rr` | float | 0.3 | [0.3, 2.0] |
| `zone_tol` | float | 15.0 | [3, 25] |
| `min_distance` | float | 0.2 | [0.1, 2.0] |
| `volume` | float | 0.05 | (hard-cap, not tuned) |
| `_history` | list | [] | capped at 50 entries |

## Data flow under load

1. Channel message arrives in Telethon → `is_valid_signal()` → drop or pass.
2. Forwarded to inbox bot → `fastpath_bot.handle_message()` (≈2 ms).
3. `fastpath.parse_signal()` returns a `{action, zmin, zmax, sl, tp, trusted}`
   dict or `None`.
4. Match → `exec_signal()` shells out to `mt5_buy.py` / `mt5_sell.py`.
   No match + `FASTPATH_LLM_FALLBACK=1` → `openclaw agent --json`
   round-trip (≈3 s).
5. Executor reads `risk_config.json`, runs zone / anti-late-TP / RR checks,
   sends `order_send` to MT5.
6. Result line returned to the bot, which sends a Telegram reply
   referencing the ticket id and total parse+exec latency (typically
   under 1.2 s end-to-end).

## Failure modes and how they're handled

| Failure | Detector | Behaviour |
|---|---|---|
| MT5 desktop client down | `mt5.initialize()` returns False | `ERROR: MT5 initialization failed` on stdout; exit 1 |
| Wrong credentials | `mt5.login()` returns False | `ERROR: Login failed`; exit 1 |
| Symbol not in Market Watch | `mt5.symbol_select()` returns False | `ERROR: Unable to select symbol …`; exit 1 |
| Signal arrives stale (entry far from zone) | `mt5_buy/sell` zone check | `ABANDON ZONE: …`; no order sent |
| TP too close (signal arrived late) | `mt5_buy/sell` distance check | `ABANDON SAFETY: …`; no order sent |
| Risk/reward below `min_rr` | `mt5_buy/sell` RR check | `ABANDON RR: …`; no order sent |
| Telegram 429 rate-limit | `fastpath_bot.main_loop` | Sleep `retry_after + 1` then retry |
| Telegram 409 conflict (two pollers) | `fastpath_bot.main_loop` | Linear backoff up to 60 s |
| LLM fallback timeout | `forward_to_llm()` | Reply `"LLM fallback timeout"`; signal dropped |
| Auto-tuner pushes a threshold out of range | `LIMITS` clamp in `mt5_auto_tuner.py` | Value clamped to the hard limit |
| Auto-tuner oscillation | `MAX_DELTA` cap | Per-night delta limited; gradual drift only |
