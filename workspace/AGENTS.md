# Agents

## Mistral Trader (primary)

- **Model:** `mistralai/mistral-medium-3.5-128b` (served via NVIDIA's
  OpenAI-compatible NIM endpoint).
- **Role:** Parse Telegram trading signals and shell out to the MT5
  executor scripts.
- **Required capabilities:** must have access to an `exec`-style tool
  that can run local Python.
- **Autonomy:** authorised to invoke `mt5_buy.py`, `mt5_sell.py`, and
  `mt5_close_all.py` without confirmation when a well-formed Telegram
  signal arrives. The hard-cap on volume (0.05) and the three pre-trade
  safety checks live in the executor scripts, not in the prompt — the
  agent cannot override them.
