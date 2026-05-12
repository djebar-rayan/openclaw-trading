# Contributing

Thanks for considering a contribution. This project is a personal trading
automation stack — small, focused, opinionated. Issues and PRs are welcome,
especially around broker portability and signal-parser coverage.

## Development setup

```bash
git clone https://github.com/djebar-rayan/openclaw-trading.git
cd openclaw-trading
python -m venv .venv
.\.venv\Scripts\activate         # Windows
# source .venv/bin/activate      # macOS / Linux
pip install -r requirements.txt
cp .env.example .env             # fill in your credentials
```

You also need:
- **MetaTrader 5 desktop client** running and logged in, with AutoTrading enabled (F7).
- A **Telegram bot** (via @BotFather) and a **Telegram api_id / api_hash** from
  https://my.telegram.org.

## Code style

- Python 3.10+, formatted with `ruff format` (line length 100).
- Type hints encouraged but not required outside public APIs.
- Comments only when the *why* is non-obvious. Identifier names carry the *what*.
- Do not commit `.env`, `config.py`, `*.session`, `*.db`, or any file the
  `.gitignore` already excludes. The repo intentionally ships only templates.

## Pull-request checklist

- [ ] `pip install -r requirements.txt` succeeds from a clean venv.
- [ ] No real credentials, account numbers, or session files in the diff.
- [ ] If you touched a parser or executor, a worked example is added under
      `workspace/skills/mt5-trading-assistant/fastpath/` or referenced in `docs/`.
- [ ] Volume parameter stays at `0.05` — the risk guard is intentional.
- [ ] If you added a new env var, document it in `.env.example` **and**
      `docs/CONFIGURATION.md`.

## Reporting security issues

Do **not** open a public issue. Email the maintainer instead. Credentials
that leak through a contributed PR will be force-rotated before the PR is
merged.
