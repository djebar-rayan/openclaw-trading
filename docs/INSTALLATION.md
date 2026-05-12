# Installation

This walkthrough assumes a fresh Windows 10/11 machine. Linux / macOS
work too; the only Windows-specific piece is the MT5 desktop client.

## 1. Prerequisites

- **Python 3.10+** — `winget install Python.Python.3.12` (or python.org installer)
- **Node.js 20+** — required by the OpenClaw gateway
- **Git** — `winget install Git.Git`
- **MetaTrader 5 desktop client** — from your broker, or
  https://www.metatrader5.com for the free demo.
- **A Telegram account** and **a Telegram bot** via @BotFather.
- **An NVIDIA NIM API key** (optional, for the LLM fallback) —
  https://build.nvidia.com.

## 2. Install OpenClaw upstream

```powershell
npm install -g openclaw
openclaw setup           # creates ~/.openclaw with the framework default
```

This installs the gateway binary, the bundled plugins, and the CLI.

## 3. Replace the default `~/.openclaw` with this repo

```powershell
# Optionally back up the empty default
Move-Item $env:USERPROFILE\.openclaw $env:USERPROFILE\.openclaw.backup

# Clone my setup in its place
git clone https://github.com/djebar-rayan/openclaw-trading.git $env:USERPROFILE\.openclaw
cd $env:USERPROFILE\.openclaw
```

## 4. Python dependencies for the skill + the userbot

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 5. Telegram credentials

1. Go to https://my.telegram.org → **API development tools**. Copy
   `api_id` and `api_hash`.
2. Talk to **@BotFather**, create a new bot, copy its token.
3. Get your own Telegram user-id via **@userinfobot**.

## 6. MT5 desktop setup

1. Launch the MT5 client.
2. Log into your broker.
3. Press **F7** to enable AutoTrading (toolbar icon must turn green).
4. Right-click `XAUUSD` in **Market Watch** → **Chart Window**.

## 7. Fill in the templates

```powershell
copy .env.example .env
copy openclaw.example.json openclaw.json
copy cron\jobs.example.json cron\jobs.json
copy workspace\skills\mt5-trading-assistant\references\config_template.py `
     workspace\skills\mt5-trading-assistant\config.py
notepad .env                                          # fill every value
notepad openclaw.json                                 # gateway token + bot token
notepad cron\jobs.json                                # your Telegram chat-id
notepad workspace\skills\mt5-trading-assistant\config.py
```

Generate the gateway auth token:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

## 8. Generate the device identity

```powershell
openclaw doctor --fix
```

OpenClaw creates `identity/device.json` (Ed25519 keypair) and
`identity/device-auth.json` (operator token). Both are gitignored.

## 9. Smoke-test the MT5 wiring

```powershell
python workspace\skills\mt5-trading-assistant\scripts\mt5_check.py
```

Expected output: connection OK, login OK, balance, equity, current
bid/ask, any open positions.

## 10. Launch the gateway + userbot

```powershell
gateway.cmd                                           # in one terminal
python userbot.py                                     # in another (first run prompts for OTP)
```

The userbot's first launch prompts for the phone number + OTP **for each
listener account**. Sessions persist as `*.session` files (gitignored).

## 11. Optional: scheduled tasks

Register the launchers with Windows Task Scheduler so the gateway and
userbot auto-start at boot and auto-restart on crash:

- `OpenClaw Gateway` → action `gateway.cmd`, trigger `at logon`, restart on failure.
- `OpenClaw UserBot` → action `userbot_start.cmd`, trigger `at logon`,
  restart on failure (the script also has its own 10-second
  auto-restart loop).

## Troubleshooting

If anything misbehaves, the relevant logs are:

- `workspace/skills/mt5-trading-assistant/fastpath/fastpath_bot.log` —
  every Telegram update + fast-path decision.
- `workspace/skills/mt5-trading-assistant/trade_history/signals_<date>.jsonl` —
  one structured record per inbound signal.
- `workspace/skills/mt5-trading-assistant/trade_history/<date>.json` —
  daily reconstructed P&L.
- `logs/gateway-restart.log` — gateway restart trail.
- `openclaw logs tail` — live gateway log.
