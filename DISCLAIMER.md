# Trading Disclaimer

This software is provided **for educational and research purposes only**.

Trading financial instruments — including but not limited to spot gold
(`XAUUSD`), foreign exchange, indices, and CFDs — carries a substantial risk
of loss and is not suitable for every investor. Past performance of any
trading system or methodology is not necessarily indicative of future results.

The author and any contributors:

- make **no representation or warranty** regarding the accuracy, completeness,
  or fitness for purpose of the strategies, signals, scripts, or any output
  produced by this software;
- accept **no liability** for any direct, indirect, incidental, or
  consequential financial loss arising from the use of this software, even if
  advised of the possibility of such loss;
- do **not** provide financial, investment, or tax advice.

## Required precautions before live use

1. **Always test on a demo account first.** The default configuration targets
   `MetaQuotes-Demo` precisely so the smoke-tests cannot reach a live account.
2. **Run for at least two consecutive months on demo** with the full automation
   pipeline (signal relay + fast-path + nightly learner + auto-tuner) before
   switching to a live broker.
3. **Understand every line of the safety checks** in `mt5_buy.py` /
   `mt5_sell.py` before disabling any of them (the `MT5_TRUSTED` env var
   bypasses all three — use it sparingly).
4. **Never deposit more than you can afford to lose** into the connected
   broker account.
5. **Verify your broker's regulatory status** in your jurisdiction.

By using this software you acknowledge that you have read, understood, and
accepted the above terms.
