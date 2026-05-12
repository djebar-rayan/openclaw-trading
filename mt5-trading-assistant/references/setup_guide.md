# MT5 Trading Assistant — setup guide

## Requirements

- **Python 3.10+** (3.7 minimum, but the feature pipeline expects 3.10+)
- **MetaTrader 5 desktop client** installed, logged in, and connected to your broker
- **MetaTrader5 Python package** — `pip install MetaTrader5`
- Stable internet connection
- AutoTrading enabled in the MT5 client (F7, or click the "AutoTrading" toolbar
  button until it turns green)

## Install

```bash
pip install -r ../../requirements.txt
```

## Configure the MT5 client

1. Launch the MT5 desktop client.
2. Log into your trading account.
3. Enable AutoTrading:
   - Press F7, or click the toolbar's traffic-light icon, or
   - Tools → Options → Expert Advisors → check **Allow algorithmic trading**.
4. Confirm the client shows **Connected** and that the symbol you trade is
   updating in the Market Watch panel.

## Configure credentials

Two equivalent paths — pick whichever you prefer:

### Option A — environment variables (recommended)

Add the variables to `.env` at the repo root:

```bash
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=MetaQuotes-Demo
MT5_SYMBOL=XAUUSD
```

`config.example.py` reads these via `os.getenv`. No local config file is needed.

### Option B — local `config.py`

```bash
cp references/config_template.py config.py
# then edit config.py with your real values
```

`config.py` is gitignored, so it never reaches version control.

## Test the installation

```bash
python scripts/mt5_check.py        # connection + balance + spread + open positions
python scripts/mt5_snapshot.py     # condensed account + market snapshot
```

Then a dry buy (the script will clamp non-0.05 volumes back to 0.05):

```bash
python scripts/mt5_buy.py 0.05 0 0 0 0   # entry/SL/TP omitted -> market order
```

## Common issues

| Error | Likely cause | Fix |
|---|---|---|
| `Initialize failed` | MT5 client not running | Launch the client and log in |
| `Login failed` | wrong account / password / server | Re-check `.env` / `config.py` |
| `AutoTrading disabled by client` | AutoTrading off in the GUI | Press F7 |
| `Invalid symbol` | broker uses a suffix (e.g. `XAUUSDm`) | Update `MT5_SYMBOL` |
| Spread warning in `mt5_check` | wide spread (often outside trading hours) | Wait for liquid session |

## Broker-specific notes

- **MetaQuotes-Demo** — best for first-time setup; identical API surface, no risk.
- **Exness** — gold symbol is typically `XAUUSDm`; servers look like `Exness-MT5Trial5`.
- **IC Markets** — gold symbol is `XAUUSD`; server `ICMarkets-MT5`.

## Security

- Never commit `.env`, `config.py`, or `*.session` files. The repo's `.gitignore`
  already excludes them.
- Demo first. The scripts hard-cap volume at **0.05 lots**; do not bypass it.
- Every buy/sell script always defines a stop-loss when one is provided.
