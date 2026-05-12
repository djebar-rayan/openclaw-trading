# Installation

This walkthrough assumes a fresh Windows 10/11 machine. Linux / macOS
work too; the only Windows-specific piece is the MT5 desktop client.

## 1. Prerequisites

- **Python 3.10+** — `winget install Python.Python.3.12` (or python.org installer)
- **Git** — `winget install Git.Git`
- **MetaTrader 5 desktop client** — download from your broker, or from
  https://www.metatrader5.com if you only need the demo server.
- **A Telegram account** (for the user-bot) and **a Telegram bot** created
  via @BotFather (for outbound notifications).
- **An NVIDIA NIM API key** if you want the LLM fallback. Sign up at
  https://build.nvidia.com.

## 2. Clone & install Python packages

```powershell
git clone https://github.com/djebar-rayan/openclaw-trading.git
cd openclaw-trading
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Acquire Telegram credentials

1. Go to https://my.telegram.org → **API development tools**.
2. Copy `api_id` and `api_hash`.
3. In Telegram, talk to **@BotFather**, create a new bot, copy its token.
4. Get your own user id with **@userinfobot** (you will use it as the
   owner allow-list).

## 4. Configure `.env`

```powershell
copy .env.example .env
notepad .env
```

Fill in every value. Required:

- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_OWNER_CHAT_ID`
- `FASTPATH_ALLOWED_SENDERS` (your user id, possibly comma-separated)
- `TELEGRAM_LISTENER_A_CHANNELS` / `TELEGRAM_LISTENER_B_CHANNELS` — the
  signal channels each user-bot account subscribes to. Format:
  `-1001234567890:Channel Name,-1009876543210:Other Channel`
- `OPENCLAW_INBOX_BOT` — the `@username` your validated signals get
  forwarded to (typically your own fast-path bot)
- `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_SYMBOL`
- `NVIDIA_API_KEY` (optional, only if you want LLM fallback)
- `GATEWAY_AUTH_TOKEN` — `python -c "import secrets; print(secrets.token_hex(32))"`

## 5. MT5 desktop setup

1. Launch the MT5 client.
2. Log into your broker with the credentials you just put in `.env`.
3. Press **F7** to enable AutoTrading (the toolbar icon must be green).
4. Right-click the symbol you trade (e.g. `XAUUSD`) in Market Watch →
   **Chart Window** — this ensures the symbol is "selected" for the API.

## 6. Smoke-test

```powershell
python mt5-trading-assistant\scripts\mt5_check.py
```

Expected output: connection OK, login OK, balance, equity, current
bid/ask, any open positions. If you see `CRITICAL: Login failed`, your
`.env` is wrong; if `CRITICAL: MT5 initialization failed`, the desktop
client is not running.

## 7. Start the signal relay

```powershell
python userbot.py
```

The first run prompts for the phone number and an OTP **for each user-bot
account**. The OTP arrives inside Telegram itself, not by SMS. Sessions
are persisted as `*.session` files (gitignored — never share them).

## 8. Start the fast-path bot

In a second terminal:

```powershell
.\.venv\Scripts\activate
python mt5-trading-assistant\fastpath\fastpath_bot.py
```

You should see `connected as @your_bot_username`, then `INBOUND …` lines
each time a signal is forwarded. Replies appear in the same Telegram
chat as the originating signal.

## 9. Optional: scheduled tasks

The daily reconstruction and nightly retrain are designed to run from
Windows Task Scheduler (or cron on Linux):

| Task | Schedule | Command |
|---|---|---|
| Daily analyzer | 23:30 local | `python mt5-trading-assistant\scripts\mt5_daily_analyzer.py` |
| Nightly learner | 23:45 local | `python mt5-trading-assistant\scripts\mt5_nightly_learner.py` |

Both tasks are idempotent and safe to retry.

## Troubleshooting

If anything misbehaves, the logs are your friend:
- `mt5-trading-assistant/fastpath/fastpath_bot.log` — every Telegram update
  and fast-path decision
- `mt5-trading-assistant/trade_history/signals_<date>.jsonl` — structured
  record of each inbound signal (parse + exec timings, decision)
- `mt5-trading-assistant/trade_history/<date>.json` — daily aggregate
