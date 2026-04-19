# -*- coding: utf-8 -*-
"""
BTC Inflow OOS (Out-of-Sample) Validation
Splits inflow events into IS (70%) and OOS (30%) by time,
validates whether the short edge found in IS holds in OOS.
"""

import os
import json
import numpy as np
from datetime import datetime, timezone
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def load_data():
    with open(os.path.join(DATA_DIR, "btc_inflow_backtest_results.json"), "r", encoding="utf-8") as f:
        results = json.load(f)
    return results


def split_is_oos(results, split_ratio=0.7):
    timestamps = sorted(set(r["timestamp"] for r in results))
    split_ts = timestamps[int(len(timestamps) * split_ratio)]

    is_data = [r for r in results if r["timestamp"] <= split_ts]
    oos_data = [r for r in results if r["timestamp"] > split_ts]

    split_dt = datetime.utcfromtimestamp(split_ts).strftime("%Y-%m-%d")
    is_start = datetime.utcfromtimestamp(min(timestamps)).strftime("%Y-%m-%d")
    oos_end = datetime.utcfromtimestamp(max(timestamps)).strftime("%Y-%m-%d")

    return is_data, oos_data, is_start, split_dt, oos_end


def calc_short_stats(items):
    if not items:
        return None
    changes = [r["change_pct"] for r in items]
    drops = [c for c in changes if c < 0]
    rises = [c for c in changes if c >= 0]
    n = len(changes)
    wr = len(drops) / n if n > 0 else 0
    avg_win = abs(np.mean(drops)) if drops else 0
    avg_loss = np.mean(rises) if rises else 0
    ev = wr * avg_win - (1 - wr) * avg_loss
    median = float(np.median(changes))
    return {
        "n": n,
        "wr": wr * 100,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "ev": ev,
        "median": median,
        "avg_change": float(np.mean(changes)),
    }


def print_stats(label, stats):
    if stats is None:
        print(f"  {label}: no data")
        return
    print(f"  {label}:")
    print(f"    Events: {stats['n']}")
    print(f"    Drop rate (short WR): {stats['wr']:.1f}%")
    print(f"    Avg short gain: {stats['avg_win']:.3f}% | Avg short loss: {stats['avg_loss']:.3f}%")
    print(f"    EV per trade: {stats['ev']:+.4f}%")
    print(f"    Median change: {stats['median']:+.3f}%")
    print(f"    Avg change: {stats['avg_change']:+.3f}%")


def main():
    results = load_data()
    print("=" * 70)
    print("OOS VALIDATION: BTC INFLOW -> SHORT STRATEGY")
    print("=" * 70)

    h24 = [r for r in results if r["horizon_h"] == 24]
    is_data, oos_data, is_start, split_dt, oos_end = split_is_oos(h24, 0.7)

    print(f"\nSplit point: {split_dt}")
    print(f"  IS period:  {is_start} ~ {split_dt} ({len(is_data)} events)")
    print(f"  OOS period: {split_dt} ~ {oos_end} ({len(oos_data)} events)")

    # === Test 1: OKEx only, 50-500 BTC ===
    print("\n" + "=" * 70)
    print("TEST 1: OKEx inflow 50-500 BTC (best signal from IS)")
    print("=" * 70)

    is_okex = [r for r in is_data if r["exchange"] == "OKEx" and 50 <= r["inflow_btc"] < 500]
    oos_okex = [r for r in oos_data if r["exchange"] == "OKEx" and 50 <= r["inflow_btc"] < 500]

    print(f"\n[IS] OKEx 50-500 BTC:")
    print_stats("IS", calc_short_stats(is_okex))
    print(f"\n[OOS] OKEx 50-500 BTC:")
    print_stats("OOS", calc_short_stats(oos_okex))

    # === Test 2: All exchanges, 50-500 BTC ===
    print("\n" + "=" * 70)
    print("TEST 2: All exchanges 50-500 BTC (broader signal)")
    print("=" * 70)

    is_all = [r for r in is_data if 50 <= r["inflow_btc"] < 500]
    oos_all = [r for r in oos_data if 50 <= r["inflow_btc"] < 500]

    print(f"\n[IS] All 50-500 BTC:")
    print_stats("IS", calc_short_stats(is_all))
    print(f"\n[OOS] All 50-500 BTC:")
    print_stats("OOS", calc_short_stats(oos_all))

    # === Test 3: OKEx only, all sizes ===
    print("\n" + "=" * 70)
    print("TEST 3: OKEx all sizes (strongest exchange)")
    print("=" * 70)

    is_okex_all = [r for r in is_data if r["exchange"] == "OKEx"]
    oos_okex_all = [r for r in oos_data if r["exchange"] == "OKEx"]

    print(f"\n[IS] OKEx all sizes:")
    print_stats("IS", calc_short_stats(is_okex_all))
    print(f"\n[OOS] OKEx all sizes:")
    print_stats("OOS", calc_short_stats(oos_okex_all))

    # === Test 4: By horizon comparison ===
    print("\n" + "=" * 70)
    print("TEST 4: Best horizon for OKEx 50-500 BTC")
    print("=" * 70)

    for h in [4, 8, 12, 24, 48, 72]:
        h_data = [r for r in results if r["horizon_h"] == h and r["exchange"] == "OKEx" and 50 <= r["inflow_btc"] < 500]
        is_h = [r for r in h_data if r["timestamp"] <= int(datetime.strptime(split_dt, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())]
        oos_h = [r for r in h_data if r["timestamp"] > int(datetime.strptime(split_dt, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())]
        is_s = calc_short_stats(is_h)
        oos_s = calc_short_stats(oos_h)
        if is_s and oos_s:
            verdict = "PASS" if oos_s["ev"] > 0 else "FAIL"
            print(f"  {h:>3}h | IS EV: {is_s['ev']:+.4f}% (n={is_s['n']}) | OOS EV: {oos_s['ev']:+.4f}% (n={oos_s['n']}) | {verdict}")
        elif is_s:
            print(f"  {h:>3}h | IS EV: {is_s['ev']:+.4f}% (n={is_s['n']}) | OOS: no data")

    # === Final verdict ===
    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)

    is_stats = calc_short_stats(is_okex)
    oos_stats = calc_short_stats(oos_okex)

    if is_stats and oos_stats:
        print(f"\nStrategy: OKEx 50-500 BTC inflow -> SHORT, hold 24h")
        print(f"  IS  EV: {is_stats['ev']:+.4f}% (n={is_stats['n']}, WR={is_stats['wr']:.0f}%)")
        print(f"  OOS EV: {oos_stats['ev']:+.4f}% (n={oos_stats['n']}, WR={oos_stats['wr']:.0f}%)")

        if oos_stats["ev"] > 0 and oos_stats["n"] >= 5:
            print(f"\n  >>> VERDICT: OOS PASS <<<")
            print(f"  >>> EV positive in unseen data. Edge is likely real. <<<")
        elif oos_stats["ev"] > 0:
            print(f"\n  >>> VERDICT: WEAK PASS <<<")
            print(f"  >>> EV positive but sample too small ({oos_stats['n']} events) <<<")
        else:
            print(f"\n  >>> VERDICT: FAIL <<<")
            print(f"  >>> EV negative in OOS. IS edge was likely overfitting. <<<")
    else:
        print("  Insufficient data for verdict")


if __name__ == "__main__":
    main()
