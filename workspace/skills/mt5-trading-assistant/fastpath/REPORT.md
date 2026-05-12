# Report — Fast-Path Trade Execution

## TL;DR

Replaced OpenClaw's LLM-driven signal-to-order pipeline with a regex
fast-path. End-to-end latency from Telegram message to MT5 fill dropped
from **30–118 seconds** to **0.84 seconds** (a 35–140× speed-up). LLM
token spend per signal: ~22 000 in / 309 out → **0**.

## Measured results

| Metric | Before (LLM via OpenClaw) | After (fast-path) | Gain |
|---|---|---|---|
| Signal → order placed | 30 s (morning) up to 49–118 s (afternoon) | **0.84 s** | 35–140× |
| Parser | LLM 25–100 s | 200 µs | ~125 000× |
| Python script (init + login + check + order) | 5.7 s | 0.84 s | 6.8× |
| Tokens per signal | 22 000 in / 309 out | 0 | ∞ |

A real-trade measurement: ticket opened at 4 560.92 in **839 ms total**
via the fast-path; closed at 4 574.14 for a $11.30 PnL.

## Architecture

```
Telegram (signal channel) ───▶ fastpath_bot.py (Python sidecar)
                                       │
                              regex parser + sanity checks
                                       │
                       ┌───────────────┴────────────────┐
                       │                                │
                Signal matched?                         │
                       │                                │
              YES: exec MT5 script direct    NO: forward to `openclaw agent`
              (~0.8 s end-to-end)            (LLM fallback, ~30–50 s)
                       │                                │
                       └────────────────┬───────────────┘
                                        │
                          sendMessage Telegram (reply)
```

The Python sidecar replaces OpenClaw's built-in Telegram poller.
OpenClaw stays active for:

- Cron scheduling (daily report, hourly health check, nightly learner).
- LLM fallback on unrecognised signal phrasings.

## Files delivered

```
workspace/skills/mt5-trading-assistant/fastpath/
├── fastpath.py             # importable parser + executor
├── test_fastpath.py        # 22 test cases (run: python test_fastpath.py)
├── bench.py                # end-to-end benchmark
├── fastpath_bot.py         # Telegram-side sidecar bot
├── start_fastpath_bot.cmd  # Windows launcher (single-instance guard)
└── REPORT.md               # this file
```

## Unit tests (all green)

**Valid signals detected**:

- Range form (`Zone d'Entrée : 4567–4575`).
- Single-price form (`Entrée : 4585`).
- Lower-case, comma-decimal, mixed FR/EN keywords.

**Noise correctly ignored** (returns `{action: "ignore", reason: ...}`):

- `TP1 TOUCHE +30 PIPS`
- `Mettez votre SL BE`
- `BILAN DU MATIN +200 PIPS`

**Invalid → LLM fallback** (returns `None`, OpenClaw takes over):

- SL or TP missing.
- SL / TP layout incoherent (wrong side of entry).
- Price out of the symbol's plausible range (`1000–10000`).
- No direction keyword.
- Ambiguous (both BUY and SELL mentioned).

**Close-all detected**:

- `Fermez tous vos trades`
- `Close all positions`

**Auto-flip & direction inference**:

- Label says SELL but SL/TP layout describes a BUY → parser flips
  silently (handles typos in upstream signals).
- No direction keyword + clear SL/TP layout → action inferred.

## Safety checks (unchanged vs. the original pipeline)

Everything is delegated to `mt5_buy.py` / `mt5_sell.py`, which:

- Force volume to 0.05.
- Reject if market price is outside the signal zone (`ABANDON ZONE`).
- Reject if Risk/Reward < `risk_config.min_rr` (`ABANDON RR`).
- Reject if market is closer than `risk_config.min_distance` to the TP
  (`ABANDON SAFETY` — signal arrived too late).
- Surface MT5 broker errors as `Buy failed` / `Sell failed`.

The fast-path bypasses **none** of these checks — it only replaces the
LLM as the text parser.

## OpenClaw configuration applied

```bash
openclaw config set channels.telegram.enabled false
openclaw config set agents.defaults.thinkingDefault off
openclaw config set models.providers.mistralai.models[0].reasoning false
openclaw config set channels.telegram.streaming.mode off
openclaw config set channels.telegram.ackReaction ""
```

The sidecar takes ownership of Telegram polling. OpenClaw keeps the cron
scheduler and remains available as an LLM fallback through
`openclaw agent`.

## Running the bot

### Manually (test)

```cmd
cd %USERPROFILE%\.openclaw\workspace\skills\mt5-trading-assistant\fastpath
start_fastpath_bot.cmd
```

### As a Windows Scheduled Task (production)

```powershell
schtasks /create /tn "OpenClaw FastPath Bot" `
  /tr "%USERPROFILE%\.openclaw\workspace\skills\mt5-trading-assistant\fastpath\start_fastpath_bot.cmd" `
  /sc onstart /rl highest
```

### Tail the log

```bash
tail -f workspace/skills/mt5-trading-assistant/fastpath/fastpath_bot.log
```

## Related optimisations applied at the same time

1. **`SOUL.md`**: 154 → 60 lines. Kept only the currently-subscribed
   channels; dropped legacy formats.
2. **`TOOLS.md`**: 39 → 18 lines.
3. **MT5 scripts**: removed an unnecessary `time.sleep(1)` after
   `order_send` (saved ~1 s per trade).
4. **Unicode `−` (U+2212)** bug in `mt5_buy.py` fixed (was crashing
   Python with `charmap` codec on Windows console).

## Watch-outs

1. **Telegram polling conflict**: only one process can poll a bot
   token at a time. The sidecar and OpenClaw can't both run against the
   same bot — that's why
   `channels.telegram.enabled = false` is required.
2. **SSL chain**: the sidecar uses `certifi` for the `api.telegram.org`
   TLS chain. `pip install certifi` if missing.
3. **Easy rollback**: to revert to LLM-only behaviour,
   `openclaw config set channels.telegram.enabled true` and stop the
   sidecar.
4. **LLM fallback**: unrecognised signals still take ~30–50 s — that's
   the original pipeline, deliberately untouched. No regression.
