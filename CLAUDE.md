# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## What this repository is

A drop-in template for an **OpenClaw** agent runtime configured as a
**Telegram-driven autonomous MetaTrader 5 trade executor** ("Mistral Trader").
The OpenClaw binary itself lives in your local install of the upstream package
(e.g. `%APPDATA%\npm\node_modules\openclaw\dist\index.js`); this repository is
purely configuration, persona, scripts, and per-skill workspace content.

Clone this repo into `%USERPROFILE%\.openclaw\` (Windows) or `~/.openclaw/`
(POSIX), copy `.env.example` → `.env`, copy `openclaw.example.json` →
`openclaw.json`, fill in your credentials, and run `gateway.cmd`.

## Gateway

- Launched via `gateway.cmd` → runs `node openclaw/dist/index.js gateway --port 18789`.
- Bound to loopback only, token auth (`gateway.auth.token` in `openclaw.json`).
- Register as a Windows Task Scheduler entry ("OpenClaw Gateway") for auto-start.

## The Mistral Trader agent

The configured agent is **Mistral Trader**: a Telegram-driven MT5 order
executor. Inbound signals arrive via the Telegram bot (`channels.telegram` in
`openclaw.json`); the agent parses them and shells out to Python scripts under
`workspace/skills/mt5-trading-assistant/scripts/`.

Two hard rules must survive any edit to `workspace/SOUL.md`,
`workspace/TOOLS.md`, or skill files:

1. **Volume is always `0.05`.** Every `mt5_buy.py` / `mt5_sell.py` invocation
   must pass `0.05` as the first argument. There is no scenario where this
   changes — the script clamps any other value back to 0.05 at runtime.
2. **Use TP1 only.** When a signal lists multiple take-profits (TP1/TP2/TP3),
   extract TP1 and discard the rest.

The canonical script signature is the **zone form**:
`mt5_buy.py <volume> <zone_min> <zone_max> <SL> <TP>` (5 args). Both
`SOUL.md` and `TOOLS.md` document this; do not revert to the old single-price
form.

## Editing `openclaw.json` — read this first

Prefer the CLI over direct file edits: `openclaw config set <path> <value>`
validates the schema before writing and won't trigger the last-good
quarantine. Use `openclaw doctor --fix` for auto-detected repairs.

`openclaw.json` is guarded by an auto-healing layer that watches for
"clobbered" writes:

- `openclaw.json.last-good` — promoted snapshot the gateway will roll back to.
- `openclaw.json.bak`, `.bak.1` … — rolling backups.
- `openclaw.json.clobbered.<ISO>` — quarantined writes the watcher rejected.
- `logs/config-health.json` — hash/inode/mtime of the last-known-good state.

After any direct edit, verify the file still matches `openclaw.json.last-good`
content-wise.

## Layout — what ships in this repo

- `openclaw.example.json` — template for the gateway, channels (Telegram), agent
  defaults, model providers, plugin enablement. Copy to `openclaw.json`.
- `.env.example` — template for every credential the agent reads at run-time.
- `userbot.py` — Telethon dual-listener that filters inbound Telegram signals
  before forwarding to the OpenClaw inbox bot.
- `gateway.cmd`, `userbot_start.cmd` — Windows launchers.
- `cron/jobs.example.json` — three scheduled jobs (daily report, hourly
  health-check, nightly learner). Copy to `cron/jobs.json`.
- `workspace/` — the agent's working directory, surfaced as project root.
  - `IDENTITY.md`, `SOUL.md`, `AGENTS.md`, `TOOLS.md`, `USER.md.example`
  - `skills/mt5-trading-assistant/` — the trading executor (`scripts/`,
    `fastpath/`, `features.py`, `risk_config.json`, `references/`,
    `SKILL.md`, `README.md`, `INSTALLATION.md`, `_meta.json`).

## Auto-created on first run (gitignored, not in this repo)

The gateway / `openclaw doctor --fix` creates these:

- `agents/main/agent/{auth-profiles,auth-state,models}.json` — per-agent
  auth state and model cache.
- `agents/main/sessions/*.jsonl` — append-only conversation logs.
- `identity/{device,device-auth}.json` — Ed25519 keypair + operator token.
- `devices/{paired,pending}.json` — pairing state.
- `credentials/telegram-*.json` — channel allow-lists.
- `flows/`, `tasks/`, `memory/` — runtime SQLite stores.
- `cron/runs/<job-id>/*.json` — scheduled-task execution history.
- `telegram/update-offset-default.json` — bot polling cursor.
- `logs/{config-audit.jsonl, config-health.json, gateway-restart.log}`.
- `plugins/installs.json`, `plugin-skills/` — plugin registry cache.
- `canvas/index.html`, `completions/openclaw.{zsh,bash,fish,ps1}` — UI
  + shell-completion files shipped by OpenClaw.
- `workspace/.clawhub/lock.json`, `workspace/.openclaw/workspace-state.json`,
  `workspace/state/` — workspace runtime state.
- `workspace/HEARTBEAT.md` — empty marker the gateway recreates on demand
  (push/reactive event loop is configured; the file stays empty).
- `workspace/BOOTSTRAP.md` — OpenClaw's first-run onboarding template
  (the gateway only writes it on a fresh workspace).

## Common operations

- Test MT5 connectivity:
  `python workspace/skills/mt5-trading-assistant/scripts/mt5_check.py`
- Account/market snapshot:
  `python workspace/skills/mt5-trading-assistant/scripts/mt5_snapshot.py`
- Close everything for the configured symbol:
  `python workspace/skills/mt5-trading-assistant/scripts/mt5_close_all.py all`
- Restart the gateway: stop the `OpenClaw Gateway` Windows Task, then re-run
  `gateway.cmd`.
- Tail config writes: read `logs/config-audit.jsonl`.

## Models / providers

`openclaw.example.json` registers `mistralai/mistral-medium-3.5-128b` via the
**NVIDIA** OpenAI-compatible endpoint (`https://integrate.api.nvidia.com/v1`)
under the `mistralai` provider key, with `compat.requiresStringContent = true`.
The provider key is misleading — auth flows through NVIDIA, not Mistral
directly. This is the agent's primary model. Get a key from
https://build.nvidia.com.
