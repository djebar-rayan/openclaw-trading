# Configuration reference

Every knob lives in `.env` (loaded by `python-dotenv`) or in
`mt5-trading-assistant/risk_config.json` (rewritten by the auto-tuner).

## Environment variables

### Telegram user-bot (Telethon)

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_API_ID` | yes | Integer from https://my.telegram.org → API development tools |
| `TELEGRAM_API_HASH` | yes | Companion hex string |
| `TELETHON_SESSION_A` | no (default `session_listener_a`) | File name for listener A's `.session` cache |
| `TELETHON_SESSION_B` | no (default `session_listener_b`) | File name for listener B's `.session` cache |
| `TELEGRAM_LISTENER_A_CHANNELS` | no (empty disables listener A) | `<id>:<name>,<id>:<name>,…` of channels listener A subscribes to |
| `TELEGRAM_LISTENER_B_CHANNELS` | no (empty disables listener B) | Same format for listener B |
| `OPENCLAW_INBOX_BOT` | no (empty disables forwarding) | `@username` to which valid signals are forwarded |

### Telegram bot (Bot API)

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | Token from @BotFather; powers outbound notifications **and** the fast-path bot |
| `TELEGRAM_OWNER_CHAT_ID` | yes | User id that receives confirmation pings from `userbot.py` |
| `FASTPATH_ALLOWED_SENDERS` | yes | Comma-separated user ids allowed to send signals to `fastpath_bot.py` (everyone else is silently dropped) |
| `FASTPATH_LLM_FALLBACK` | no (default `1`) | Set to `0` to disable the LLM fallback path |
| `FASTPATH_OPENCLAW_AGENT` | no (default `main`) | Agent id passed to `openclaw agent --agent …` |
| `FASTPATH_TRUSTED_SOURCES` | no (default empty) | A regex; signals whose text matches bypass the three safety checks. **Use sparingly.** |

### MetaTrader 5

| Variable | Required | Description |
|---|---|---|
| `MT5_LOGIN` | yes | Integer account number |
| `MT5_PASSWORD` | yes | Account password |
| `MT5_SERVER` | yes | Broker server name (e.g. `MetaQuotes-Demo`, `ICMarkets-MT5`) |
| `MT5_SYMBOL` | no (default `XAUUSD`) | Primary symbol |
| `MT5_TRUSTED` | no | Set to `1` when invoking an executor by hand to bypass the three safety checks |

### Model provider

| Variable | Required | Description |
|---|---|---|
| `NVIDIA_API_KEY` | only if LLM fallback is enabled | NIM API key (Mistral Medium 3.5 is exposed via NVIDIA's OpenAI-compatible endpoint) |

### OpenClaw gateway

| Variable | Required | Description |
|---|---|---|
| `GATEWAY_AUTH_TOKEN` | yes if you run the gateway | Bearer token for the local gateway. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `GATEWAY_PORT` | no (default `18789`) | TCP port — keep it loopback-only |

### Risk

| Variable | Required | Description |
|---|---|---|
| `VOLUME_PER_TRADE` | no (default `0.05`) | Volume passed by orchestration code. **Executors clamp anything other than 0.05 back to 0.05 anyway — this is informational.** |

## `risk_config.json`

Lives at `mt5-trading-assistant/risk_config.json`. Re-read on every
invocation of `mt5_buy.py` / `mt5_sell.py`, so the auto-tuner's changes
take effect without a restart.

```json
{
  "_comment": "Signal-validation thresholds. Tunable at runtime …",
  "min_rr": 0.3,
  "zone_tol": 15.0,
  "min_distance": 0.2,
  "volume": 0.05,
  "_history": []
}
```

| Key | Default | Hard limits | Meaning |
|---|---|---|---|
| `min_rr` | `0.3` | `[0.3, 2.0]` | Minimum reward/risk ratio; orders with `reward / risk < min_rr` are abandoned |
| `zone_tol` | `15.0` | `[3, 25]` | Pips of tolerance around the signal zone before refusing entry |
| `min_distance` | `0.2` | `[0.1, 2.0]` | Minimum distance between current market price and TP; smaller distances mean the signal is too late |
| `volume` | `0.05` | hard-cap (not tuned) | Lot size used in every order |
| `_history` | `[]` | capped at 50 entries | Audit log of every adjustment made by `mt5_auto_tuner.py` |

The auto-tuner enforces a **maximum delta per night** of `±0.1` on
`min_rr`, `±1` on `zone_tol`, `±0.1` on `min_distance` to prevent
oscillation; even if rules suggest a bigger move, the change is capped.

## `openclaw.example.json`

Template for the OpenClaw gateway + agent config at the repo root. Copy
to `openclaw.json` (gitignored) and replace every `your_*` placeholder
before starting the gateway. The notable knobs:

- `gateway.auth.token` — bearer token, must match `GATEWAY_AUTH_TOKEN`
- `gateway.bind` — keep `"loopback"` unless you have a Tailscale tunnel
- `channels.telegram.botToken` — same token as `TELEGRAM_BOT_TOKEN`
- `channels.telegram.allowFrom` — owner chat-id allow-list
- `agents.defaults.model.primary` — the model the agent uses by default
- `models.providers.mistralai.baseUrl` — `https://integrate.api.nvidia.com/v1`
  (NVIDIA's OpenAI-compatible endpoint)

## File layout — what's gitignored

The repo ships templates only; real values live in files git refuses to
track:

| Ignored | Template shipped |
|---|---|
| `.env` | `.env.example` |
| `openclaw.json` | `openclaw.example.json` |
| `cron/jobs.json` | `cron/jobs.example.json` |
| `workspace/skills/mt5-trading-assistant/config.py` | `workspace/skills/mt5-trading-assistant/config.example.py` (and `references/config_template.py`) |
| `workspace/USER.md` | `workspace/USER.md.example` |
| `*.session`, `*.session-journal` | — (auto-created by Telethon) |
| `agents/`, `flows/`, `memory/`, `tasks/`, `logs/`, `cron/runs/`, `telegram/`, `canvas/`, `completions/`, `devices/`, `identity/`, `credentials/`, `plugins/`, `plugin-skills/` | — (all auto-created by OpenClaw) |
| `workspace/.clawhub/`, `workspace/.openclaw/`, `workspace/state/` | — (workspace runtime) |
| `workspace/skills/mt5-trading-assistant/learning.db` | — |
| `workspace/skills/mt5-trading-assistant/trade_history/` | — |
| `workspace/skills/mt5-trading-assistant/models/*.pkl` | — |
| `*.log`, `*.bak*`, `*.last-good`, `*.clobbered.*` | — |
