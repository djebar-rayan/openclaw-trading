#!/usr/bin/env python3
"""End-to-end benchmark: regex parse + MT5 script execution timing.

Requires a live MT5 desktop client logged in to the configured account.
On a fresh clone with no MT5 connection, the bench prints the parse
timing but reports MT5 init failure for the exec phase.
"""

import io
import json
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from fastpath import handle  # noqa: E402

TEST_SIGNAL = (
    "Channel C : BUY XAUUSD Zone d'Entree : 4555-4565 "
    "StopLoss : 4550 Takeprofit : 4575"
)

print("Fast-path end-to-end benchmark")
print("=" * 72)
print(f"Signal: {TEST_SIGNAL}")
print()

t0 = time.time()
result = handle(TEST_SIGNAL, dry_run=False)
total_ms = int((time.time() - t0) * 1000)

print(json.dumps(result, ensure_ascii=False, indent=2))
print()
print(f"TOTAL fast-path: {total_ms}ms")
print(f"  - parse:    {result.get('parse_ms', 0)}ms")
print(f"  - exec:     {result.get('exec_ms', 0)}ms")
print(f"  - overhead: {total_ms - result.get('parse_ms', 0) - result.get('exec_ms', 0)}ms")
