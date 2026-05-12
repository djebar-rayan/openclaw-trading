#!/usr/bin/env python3
"""Unit tests for the fast-path parser. No MT5 calls; pure regex.

Run: python test_fastpath.py
"""

import sys
import time

from fastpath import parse_signal


# (label, signal_text, expected_action, expected_zmin, expected_zmax, expected_sl, expected_tp)
VALID_CASES = [
    (
        "Channel A — BUY range (coherent)",
        "Channel A : BUY XAUUSD Zone d'Entree : 4567-4575 StopLoss : 4559 Takeprofit : 4583 TP2 : 4596",
        "buy", 4567, 4575, 4559, 4583,
    ),
    (
        "Channel A — SELL range",
        "Channel A : SELL XAUUSD Zone d'Entree : 2662-2667 StopLoss : 2683 Takeprofit : 2641 TP2 : 2620",
        "sell", 2662, 2667, 2683, 2641,
    ),
    (
        "Channel B — BUY single price (French label)",
        "Channel B : ACHAT XAUUSD Entree : 2467 SL : 2455 TP1 : 2469 TP2 : 2471",
        "buy", 2467, 2467, 2455, 2469,
    ),
    (
        "Channel B — SELL single price (coherent)",
        "Channel B : VENTE XAUUSD Entree : 5614 SL : 5630 TP1 : 5590 TP2 : 5570",
        "sell", 5614, 5614, 5630, 5590,
    ),
    (
        "Channel C — BUY single",
        "Channel C : BUY XAUUSD Zone d'Entree : 4585 StopLoss : 4575 Takeprofit : 4604 TP2 : 4595",
        "buy", 4585, 4585, 4575, 4604,
    ),
    (
        "Channel C — BUY range",
        "Channel C : BUY XAUUSD Zone d'Entree : 4560-4570 StopLoss : 4555 Takeprofit : 4585",
        "buy", 4560, 4570, 4555, 4585,
    ),
    (
        "Lower-case format",
        "channel c buy xauusd zone d'entree 4560-4570 stoploss 4555 takeprofit 4585",
        "buy", 4560, 4570, 4555, 4585,
    ),
    (
        "Comma decimals",
        "Channel A : BUY XAUUSD Zone : 4567,5-4570,0 SL : 4559,5 TP : 4583,5",
        "buy", 4567.5, 4570.0, 4559.5, 4583.5,
    ),
]

NOISE_CASES = [
    ("TP1 touched (follow-up)", "TP1 TOUCHE +30 PIPS"),
    ("Move SL BE",              "Mettez votre SL BE"),
    ("Bilan (daily summary)",   "BILAN DU MATIN +200 PIPS"),
]

INVALID_CASES = [
    ("Missing SL",               "BUY XAUUSD zone 4585 TP 4604"),
    ("Missing TP",               "BUY XAUUSD zone 4585 SL 4575"),
    ("Out-of-range price",       "BUY XAUUSD zone 50 SL 40 TP 60"),
    ("Pure analysis (no SL/TP)", "I think gold will rise to 2600 next week."),
    ("Both BUY and SELL",        "BUY XAUUSD then SELL when reaches TP zone 4585 SL 4575 TP 4604"),
]

# Label says SELL but SL/TP layout is BUY (typo by source) → parser should auto-flip.
AUTOFLIP_CASES = [
    ("SELL with SL<entry → flip to BUY",          "SELL XAUUSD zone 4585 SL 4575 TP 4604", "buy"),
    ("BUY with SL>entry and TP<entry → flip to SELL", "BUY XAUUSD zone 4585 SL 4604 TP 4575", "sell"),
]

# No direction keyword — parser infers from SL/TP layout.
INFERRED_CASES = [
    ("No action — SL<entry<TP → BUY inferred",  "XAUUSD zone 4585 SL 4575 TP 4604", "buy"),
    ("No action — TP<entry<SL → SELL inferred", "XAUUSD entree 4585 SL 4604 TP 4575", "sell"),
]

CLOSE_CASES = [
    ("Close-all FR", "Fermez tous vos trades en cours sur XAUUSD immediatement !"),
    ("Close-all EN", "Close all positions now"),
]


def _eq(a, b):
    return a is not None and b is not None and abs(a - b) < 0.01


def run():
    passed = failed = 0

    print("=" * 72)
    print("VALID SIGNAL CASES")
    print("=" * 72)
    for label, text, action, zmin, zmax, sl, tp in VALID_CASES:
        sig = parse_signal(text)
        ok = (
            sig is not None
            and sig.get("action") == action
            and _eq(sig.get("zmin"), zmin)
            and _eq(sig.get("zmax"), zmax)
            and _eq(sig.get("sl"), sl)
            and _eq(sig.get("tp"), tp)
        )
        flag = "PASS" if ok else "FAIL"
        passed += int(ok); failed += int(not ok)
        print(f"  [{flag}] {label}")
        if not ok:
            print(f"         expected action={action} zmin={zmin} zmax={zmax} sl={sl} tp={tp}")
            print(f"         got      {sig}")

    print()
    print("=" * 72)
    print("NOISE CASES (must be ignored, not None)")
    print("=" * 72)
    for label, text in NOISE_CASES:
        sig = parse_signal(text)
        ok = sig is not None and sig.get("action") == "ignore"
        flag = "PASS" if ok else "FAIL"
        passed += int(ok); failed += int(not ok)
        print(f"  [{flag}] {label} -> {sig}")

    print()
    print("=" * 72)
    print("INVALID / AMBIGUOUS CASES (must return None for LLM fallback)")
    print("=" * 72)
    for label, text in INVALID_CASES:
        sig = parse_signal(text)
        ok = sig is None
        flag = "PASS" if ok else "FAIL"
        passed += int(ok); failed += int(not ok)
        print(f"  [{flag}] {label} -> {sig}")

    print()
    print("=" * 72)
    print("AUTO-FLIP CASES (label wrong, layout correct -> flip to the right action)")
    print("=" * 72)
    for label, text, expected in AUTOFLIP_CASES:
        sig = parse_signal(text)
        ok = sig is not None and sig.get("action") == expected
        flag = "PASS" if ok else "FAIL"
        passed += int(ok); failed += int(not ok)
        print(f"  [{flag}] {label} -> action={sig.get('action') if sig else None}")

    print()
    print("=" * 72)
    print("INFERRED CASES (no direction keyword -> inferred from SL/TP layout)")
    print("=" * 72)
    for label, text, expected in INFERRED_CASES:
        sig = parse_signal(text)
        ok = sig is not None and sig.get("action") == expected
        flag = "PASS" if ok else "FAIL"
        passed += int(ok); failed += int(not ok)
        print(f"  [{flag}] {label} -> action={sig.get('action') if sig else None}")

    print()
    print("=" * 72)
    print("CLOSE-ALL CASES")
    print("=" * 72)
    for label, text in CLOSE_CASES:
        sig = parse_signal(text)
        ok = sig is not None and sig.get("action") == "close"
        flag = "PASS" if ok else "FAIL"
        passed += int(ok); failed += int(not ok)
        print(f"  [{flag}] {label} -> {sig}")

    print()
    print("=" * 72)
    print("PARSER TIMING (1000 iterations on a representative signal)")
    print("=" * 72)
    sample = VALID_CASES[0][1]
    iters = 1000
    t0 = time.time()
    for _ in range(iters):
        parse_signal(sample)
    elapsed_ms = (time.time() - t0) * 1000
    per_call_us = (elapsed_ms / iters) * 1000
    print(f"  Total {elapsed_ms:.1f}ms for {iters} calls = {per_call_us:.1f}us / call")

    print()
    print("=" * 72)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 72)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
