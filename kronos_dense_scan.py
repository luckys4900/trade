import sys, os, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Kronos"))

import torch
from model import Kronos, KronosTokenizer, KronosPredictor

device = "cuda:0" if torch.cuda.is_available() else "cpu"
print("Device:", device)

tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)

df = pd.read_csv("btc_usdt_4h_unified.csv", parse_dates=["datetime"], index_col="datetime").sort_index()
df.columns = [c.lower() for c in df.columns]
print("Data:", len(df), "bars")

delta = df["close"].diff()
gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
df["ma50"] = df["close"].rolling(50).mean()
df["trend"] = "RANGE"
df.loc[df["close"] > df["ma50"], "trend"] = "UPTREND"
df.loc[df["close"] < df["ma50"], "trend"] = "DOWNTREND"
df["vol_pct"] = df["close"].pct_change().abs().rolling(50).rank(pct=True) * 100

LOOKBACK = 400
STEP = 6
PRED_LEN = 6
N_SAMPLES = 10

results = []
total = 0

print("Running dense scan (step={}): {} points".format(STEP, (len(df) - LOOKBACK) // STEP))

for i in range(LOOKBACK, len(df) - PRED_LEN, STEP):
    total += 1
    if total % 100 == 0:
        print("  Progress: {} predictions (bar {}/{})...".format(total, i, len(df)))

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
        rsi_val = df.iloc[i]["rsi"]
        trend_val = df.iloc[i]["trend"]
        vol_pct_val = df.iloc[i]["vol_pct"]

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
                "pct_err": pct_err,
                "pred_vol": pred_vol,
                "actual_vol": actual_vol,
                "rsi": rsi_val,
                "trend": trend_val,
                "vol_pct": vol_pct_val,
                "close": actual_target,
            })

    except Exception as e:
        if total <= 3:
            print("  Error at bar {}: {}".format(i, e))
        continue

rdf = pd.DataFrame(results)
n = len(rdf)
print("\nTotal: {} predictions, {} records".format(total, n))

b0 = rdf[rdf["bar_offset"] == 0].copy()
print("First bar only: {} records".format(len(b0)))

print()
print("=" * 75)
print("  TARGETED CONDITION ANALYSIS (dense scan)")
print("=" * 75)

combos = [
    ("Base: all (bar 1)", b0),
    ("UP pred only", b0[b0["pred_dir"] == 1]),
    ("DOWN pred only", b0[b0["pred_dir"] == -1]),
    ("UP + UPTREND", b0[(b0["pred_dir"] == 1) & (b0["trend"] == "UPTREND")]),
    ("UP + RSI 40-60 + UPTREND", b0[(b0["pred_dir"] == 1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60) & (b0["trend"] == "UPTREND")]),
    ("UP + RSI 35-60 + UPTREND", b0[(b0["pred_dir"] == 1) & (b0["rsi"] >= 35) & (b0["rsi"] < 60) & (b0["trend"] == "UPTREND")]),
    ("UP + RSI 40-65 + UPTREND", b0[(b0["pred_dir"] == 1) & (b0["rsi"] >= 40) & (b0["rsi"] < 65) & (b0["trend"] == "UPTREND")]),
    ("UP + RSI 35-65 + UPTREND", b0[(b0["pred_dir"] == 1) & (b0["rsi"] >= 35) & (b0["rsi"] < 65) & (b0["trend"] == "UPTREND")]),
    ("UP + RSI 40-60", b0[(b0["pred_dir"] == 1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60)]),
    ("UP + Low vol (<30%)", b0[(b0["pred_dir"] == 1) & (b0["vol_pct"] < 30)]),
    ("UP + Low vol + UPTREND", b0[(b0["pred_dir"] == 1) & (b0["vol_pct"] < 30) & (b0["trend"] == "UPTREND")]),
    ("UP + RSI 40-60 + Low vol + UPTREND", b0[(b0["pred_dir"] == 1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60) & (b0["vol_pct"] < 30) & (b0["trend"] == "UPTREND")]),
    ("DOWN + DOWNTREND", b0[(b0["pred_dir"] == -1) & (b0["trend"] == "DOWNTREND")]),
    ("DOWN + RSI 40-60 + DOWNTREND", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60) & (b0["trend"] == "DOWNTREND")]),
    ("DOWN + RSI 35-65 + DOWNTREND", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 35) & (b0["rsi"] < 65) & (b0["trend"] == "DOWNTREND")]),
]

hdr = "{:<50} {:>9} {:>9} {:>8}".format("Condition", "Accuracy", "Samples", "Err%")
print()
print(hdr)
print("-" * 78)
for name, sub in combos:
    if len(sub) > 0:
        acc = sub["dir_correct"].mean() * 100
        err = sub["pct_err"].mean()
        marker = " ***" if acc >= 60 and len(sub) >= 20 else (" **" if acc >= 55 and len(sub) >= 15 else "")
        print("{:<50} {:>8.1f}% {:>9} {:>7.2f}%{}".format(name, acc, len(sub), err, marker))

print()
print("=== Bar 2 (2nd predicted candle) ===")
b1 = rdf[rdf["bar_offset"] == 1].copy()
combos2 = [
    ("Base: all (bar 2)", b1),
    ("UP + RSI 40-60 + UPTREND", b1[(b1["pred_dir"] == 1) & (b1["rsi"] >= 40) & (b1["rsi"] < 60) & (b1["trend"] == "UPTREND")]),
    ("UP + RSI 35-65 + UPTREND", b1[(b1["pred_dir"] == 1) & (b1["rsi"] >= 35) & (b1["rsi"] < 65) & (b1["trend"] == "UPTREND")]),
    ("DOWN + RSI 40-60 + DOWNTREND", b1[(b1["pred_dir"] == -1) & (b1["rsi"] >= 40) & (b1["rsi"] < 60) & (b1["trend"] == "DOWNTREND")]),
]
print(hdr)
print("-" * 78)
for name, sub in combos2:
    if len(sub) > 0:
        acc = sub["dir_correct"].mean() * 100
        err = sub["pct_err"].mean()
        print("{:<50} {:>8.1f}% {:>9} {:>7.2f}%".format(name, acc, len(sub), err))

rdf.to_csv("kronos_diagnosis_dense.csv", index=False)
print("\nSaved to kronos_diagnosis_dense.csv")
