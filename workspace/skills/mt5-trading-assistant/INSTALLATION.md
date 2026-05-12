# Installation — mt5-trading-assistant

This guide assumes you start from the repository root.

## 1. Install Python dependencies

```bash
python -m venv .venv
.\.venv\Scripts\activate           # Windows
# source .venv/bin/activate        # macOS / Linux
pip install -r requirements.txt
```

The skill needs `MetaTrader5`, `pandas`, `numpy`, `ta`, `scikit-learn`,
`python-dotenv`. `ta` is used instead of `pandas_ta` (no Python 3.11
wheel for the latter).

## 2. Configure the MT5 desktop client

1. Launch the **MT5 desktop client**.
2. Log into your trading account.
3. Enable **AutoTrading**:
   - Click the toolbar's traffic-light icon (red → green), or press **F7**, or
   - Tools → Options → Expert Advisors → check **Allow algorithmic trading**.
4. Confirm the symbol you intend to trade is in **Market Watch** and quotes
   are updating.

## 3. Provide credentials

Two equivalent paths. Pick **one**.

### Option A — environment variables (recommended)

Add the values to `.env` at the repo root (`cp .env.example .env` first):

```bash
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=MetaQuotes-Demo
MT5_SYMBOL=XAUUSD
```

`mt5-trading-assistant/config.example.py` reads these via `os.getenv`,
so no extra file is needed. Every script picks them up automatically.

### Option B — local `config.py`

```bash
cd workspace/skills/mt5-trading-assistant
cp references/config_template.py config.py
# edit config.py with your broker details
```

`config.py` is git-ignored.

## 4. Smoke-test

From the repo root:

```bash
python workspace/skills/mt5-trading-assistant/scripts/test_mt5_kline.py
python workspace/skills/mt5-trading-assistant/scripts/mt5_check.py
python workspace/skills/mt5-trading-assistant/scripts/mt5_snapshot.py
```

You should see your balance, equity, the current bid/ask, and any open
positions. If `mt5_check.py` prints `CRITICAL: Login failed`, your
credentials or server name are wrong; if it prints `CRITICAL: MT5
initialization failed`, the MT5 desktop client is not running.

`test_mt5_kline.py` additionally fetches a few M1 / H1 / D1 candles so you
can confirm K-line streaming works (needed by the features pipeline +
nightly learner).

## 5. Run a dry trade on demo

```bash
python workspace/skills/mt5-trading-assistant/scripts/mt5_buy.py 0.05 0 0 0 0
```

This places a 0.05-lot market buy with no SL/TP — useful only on a
**demo account** to confirm the order pipeline works. Close it manually
with `workspace/skills/mt5-trading-assistant/scripts/mt5_close_all.py all`
once you're done.

## 6. Run the parser unit tests (no MT5 needed)

```bash
python workspace/skills/mt5-trading-assistant/fastpath/test_fastpath.py
```

The test suite (22 cases) covers every parsing path and finishes in
under a second.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Initialize failed` | MT5 desktop client not running | Launch and log in |
| `Login failed` | wrong login/password/server | Re-check the values |
| `AutoTrading disabled by client` | toolbar button is red | Press **F7** |
| `Invalid symbol` | broker uses a suffix (e.g. `XAUUSDm`) | Update `MT5_SYMBOL` |

## Security

- `config.py`, `.env`, `learning.db`, `trade_history/`, `*.session`, `*.log`
  are all gitignored. Never commit them.
- The `0.05`-lot hard-cap is intentional and enforced in every executor.
- For production keys, prefer environment variables over `config.py`.
