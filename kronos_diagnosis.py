# -*- coding: utf-8 -*-
"""
Kronos Prediction Quality Diagnosis
Measures what Kronos is actually good at, before designing any strategy.
"""

import sys, os, time
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Kronos"))

import torch
from model import Kronos, KronosTokenizer, KronosPredictor


def diagnose():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory/1024**3:.1f} GB")

    print("\nLoading Kronos-base...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)
    print(f"Model params: {sum(p.numel() for p in model.parameters())/1e6:.1f}M")

    print("\nLoading BTC 4h data...")
    df = pd.read_csv("btc_usdt_4h_unified.csv", parse_dates=["datetime"], index_col="datetime").sort_index()
    df.columns = [c.lower() for c in df.columns]
    print(f"Data: {df.index[0]} -> {df.index[-1]} ({len(df)} bars)")

    LOOKBACK = 400
    STEP = 24
    PRED_LEN = 6
    N_SAMPLES = 10

    results = []
    total = 0

    print(f"\nRunning diagnosis: lookback={LOOKBACK}, step={STEP}, pred_len={PRED_LEN}, samples={N_SAMPLES}")
    print(f"Total prediction points: ~{(len(df) - LOOKBACK) // STEP}")
    print()

    for i in range(LOOKBACK, len(df) - PRED_LEN, STEP):
        total += 1
        if total % 50 == 0:
            print(f"  Progress: {total} predictions done (bar {i}/{len(df)})...")

        try:
            start_idx = i - LOOKBACK
            x_df = df.iloc[start_idx:i][["open", "high", "low", "close", "volume"]].copy()
            x_df["amount"] = x_df["volume"] * x_df[["open", "high", "low", "close"]].mean(axis=1)
            x_ts = pd.Series(df.index[start_idx:i])
            future_idx = list(range(i, i + PRED_LEN))
            y_ts = pd.Series([df.index[j] for j in future_idx])

            pred_df = predictor.predict(
                df=x_df.reset_index(drop=True), x_timestamp=x_ts, y_timestamp=y_ts,
                pred_len=PRED_LEN, T=1.0, top_p=0.9, sample_count=N_SAMPLES,
                verbose=False
            )

            prev_close = df.iloc[i - 1]["close"]

            for bar_offset in range(PRED_LEN):
                target_idx = i + bar_offset
                if target_idx >= len(df):
                    continue

                actual_target = df.iloc[target_idx]["close"]
                pred_close = pred_df.iloc[bar_offset]["close"]
                pred_high = pred_df.iloc[bar_offset]["high"]
                pred_low = pred_df.iloc[bar_offset]["low"]

                pred_dir = 1 if pred_close > prev_close else -1
                actual_dir = 1 if actual_target > prev_close else -1

                pred_vol = pred_high - pred_low
                actual_vol = df.iloc[target_idx]["high"] - df.iloc[target_idx]["low"]

                pct_err = abs(pred_close - actual_target) / actual_target * 100

                results.append({
                    "bar": i,
                    "bar_offset": bar_offset,
                    "pred_dir": pred_dir,
                    "actual_dir": actual_dir,
                    "dir_correct": pred_dir == actual_dir,
                    "dir_correct": pred_dir == actual_dir,
                    "pct_err": pct_err,
                    "pred_vol": pred_vol,
                    "actual_vol": actual_vol,
                    "vol_ratio": pred_vol / actual_vol if actual_vol > 0 else np.nan,
                    "close": actual_target,
                })

        except Exception as e:
            if total <= 3:
                print(f"  Error at bar {i}: {e}")
            continue

    print(f"\n{'='*70}")
    print(f"  KRONOS PREDICTION QUALITY DIAGNOSIS")
    print(f"  BTC/USDT 4h | Kronos-base (102.3M) | {total} prediction points")
    print(f"{'='*70}")

    rdf = pd.DataFrame(results)
    n = len(rdf)

    print(f"\n{'='*70}")
    print(f"  1. OVERALL DIRECTION ACCURACY")
    print(f"{'='*70}")
    overall_acc = rdf["dir_correct"].mean() * 100
    print(f"  Overall: {rdf['dir_correct'].sum()}/{n} = {overall_acc:.1f}%")
    print(f"  (50.0% = random coin flip)")

    long_preds = rdf[rdf["pred_dir"] == 1]
    short_preds = rdf[rdf["pred_dir"] == -1]
    print(f"  Predicted UP accuracy:   {long_preds['dir_correct'].mean()*100:.1f}% ({len(long_preds)} preds)")
    print(f"  Predicted DOWN accuracy: {short_preds['dir_correct'].mean()*100:.1f}% ({len(short_preds)} preds)")

    print(f"\n{'='*70}")
    print(f"  2. ACCURACY BY FORECAST HORIZON (bar offset)")
    print(f"{'='*70}")
    print(f"  {'Bar':>5} {'Accuracy':>10} {'Avg Err%':>10} {'Samples':>10}")
    print(f"  {'-'*35}")
    for offset in range(PRED_LEN):
        subset = rdf[rdf["bar_offset"] == offset]
        if len(subset) > 0:
            acc = subset["dir_correct"].mean() * 100
            err = subset["pct_err"].mean()
            print(f"  {offset+1:>5} {acc:>9.1f}% {err:>9.2f}% {len(subset):>10}")

    print(f"\n{'='*70}")
    print(f"  3. ACCURACY BY MARKET REGIME")
    print(f"{'='*70}")

    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()
    df["trend"] = "RANGE"
    df.loc[df["close"] > df["ma50"], "trend"] = "UPTREND"
    df.loc[df["close"] < df["ma50"], "trend"] = "DOWNTREND"
    df["vol_percentile"] = df["close"].pct_change().abs().rolling(50).rank(pct=True) * 100

    rdf["rsi"] = rdf["bar"].map(lambda b: df.iloc[b]["rsi"] if b < len(df) else np.nan)
    rdf["trend"] = rdf["bar"].map(lambda b: df.iloc[b]["trend"] if b < len(df) else "UNKNOWN")
    rdf["vol_pct"] = rdf["bar"].map(lambda b: df.iloc[b]["vol_percentile"] if b < len(df) else np.nan)

    print(f"  {'Regime':<15} {'Accuracy':>10} {'Avg Err%':>10} {'Samples':>10}")
    print(f"  {'-'*45}")
    for trend in ["UPTREND", "RANGE", "DOWNTREND"]:
        subset = rdf[rdf["trend"] == trend]
        if len(subset) > 0:
            acc = subset["dir_correct"].mean() * 100
            err = subset["pct_err"].mean()
            print(f"  {trend:<15} {acc:>9.1f}% {err:>9.2f}% {len(subset):>10}")

    print(f"\n{'='*70}")
    print(f"  4. ACCURACY BY RSI ZONE")
    print(f"{'='*70}")
    print(f"  {'RSI Zone':<20} {'Accuracy':>10} {'Avg Err%':>10} {'Samples':>10}")
    print(f"  {'-'*50}")
    for label, lo, hi in [("Deep OS (<30)", 0, 30), ("OS (30-40)", 30, 40),
                           ("Neutral (40-60)", 40, 60), ("OB (60-70)", 60, 70),
                           ("Deep OB (>70)", 70, 100)]:
        subset = rdf[(rdf["rsi"] >= lo) & (rdf["rsi"] < hi)]
        if len(subset) > 0:
            acc = subset["dir_correct"].mean() * 100
            err = subset["pct_err"].mean()
            print(f"  {label:<20} {acc:>9.1f}% {err:>9.2f}% {len(subset):>10}")

    print(f"\n{'='*70}")
    print(f"  5. ACCURACY BY VOLATILITY PERCENTILE")
    print(f"{'='*70}")
    print(f"  {'Vol Zone':<20} {'Accuracy':>10} {'Avg Err%':>10} {'Samples':>10}")
    print(f"  {'-'*50}")
    for label, lo, hi in [("Low (<25%)", 0, 25), ("Med-Low (25-50%)", 25, 50),
                           ("Med-High (50-75%)", 50, 75), ("High (>75%)", 75, 101)]:
        subset = rdf[(rdf["vol_pct"] >= lo) & (rdf["vol_pct"] < hi)]
        if len(subset) > 0:
            acc = subset["dir_correct"].mean() * 100
            err = subset["pct_err"].mean()
            print(f"  {label:<20} {acc:>9.1f}% {err:>9.2f}% {len(subset):>10}")

    print(f"\n{'='*70}")
    print(f"  6. VOLATILITY PREDICTION QUALITY")
    print(f"{'='*70}")
    valid_vol = rdf.dropna(subset=["vol_ratio"])
    if len(valid_vol) > 0:
        print(f"  Pred vol / Actual vol (mean): {valid_vol['vol_ratio'].mean():.3f}")
        print(f"  Pred vol / Actual vol (median): {valid_vol['vol_ratio'].median():.3f}")
        print(f"  Pred vol correlation with actual: {valid_vol['pred_vol'].corr(valid_vol['actual_vol']):.4f}")
        print(f"  Pred vol direction correct: {(valid_vol['pred_vol'].pct_change().dropna() * valid_vol['actual_vol'].pct_change().dropna() > 0).mean() * 100:.1f}%")

        print(f"\n  By trend:")
        for trend in ["UPTREND", "RANGE", "DOWNTREND"]:
            sub = valid_vol[valid_vol["trend"] == trend]
            if len(sub) > 0:
                print(f"    {trend}: ratio={sub['vol_ratio'].mean():.3f}, corr={sub['pred_vol'].corr(sub['actual_vol']):.4f}")

    print(f"\n{'='*70}")
    print(f"  7. PRICE ERROR DISTRIBUTION")
    print(f"{'='*70}")
    print(f"  Mean error:   {rdf['pct_err'].mean():.2f}%")
    print(f"  Median error: {rdf['pct_err'].median():.2f}%")
    print(f"  Std error:    {rdf['pct_err'].std():.2f}%")
    print(f"  Error < 1%:   {(rdf['pct_err'] < 1).sum()}/{n} ({(rdf['pct_err'] < 1).mean()*100:.1f}%)")
    print(f"  Error < 2%:   {(rdf['pct_err'] < 2).sum()}/{n} ({(rdf['pct_err'] < 2).mean()*100:.1f}%)")
    print(f"  Error < 3%:   {(rdf['pct_err'] < 3).sum()}/{n} ({(rdf['pct_err'] < 3).mean()*100:.1f}%)")
    print(f"  Error > 5%:   {(rdf['pct_err'] > 5).sum()}/{n} ({(rdf['pct_err'] > 5).mean()*100:.1f}%)")

    rdf.to_csv("kronos_diagnosis_raw.csv", index=False)
    print(f"\n{'='*70}")
    print(f"  Raw data saved to kronos_diagnosis_raw.csv ({n} records)")
    print(f"{'='*70}")

    summary = {
        "total_predictions": total,
        "total_records": n,
        "overall_direction_accuracy": overall_acc,
        "avg_price_error_pct": rdf["pct_err"].mean(),
        "vol_ratio_mean": float(valid_vol["vol_ratio"].mean()) if len(valid_vol) > 0 else None,
        "vol_correlation": float(valid_vol["pred_vol"].corr(valid_vol["actual_vol"])) if len(valid_vol) > 0 else None,
    }
    import json
    with open("kronos_diagnosis_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("Summary saved to kronos_diagnosis_summary.json")


if __name__ == "__main__":
    diagnose()
