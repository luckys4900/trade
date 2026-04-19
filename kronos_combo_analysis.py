import pandas as pd
import numpy as np

rdf = pd.read_csv("kronos_diagnosis_raw.csv")
print("Total records:", len(rdf))

b0 = rdf[rdf["bar_offset"] == 0].copy()
print("First bar only:", len(b0), "records")
print()

combos = [
    ("Base: all", b0),
    ("DOWN pred only", b0[b0["pred_dir"] == -1]),
    ("RSI 40-60", b0[(b0["rsi"] >= 40) & (b0["rsi"] < 60)]),
    ("DOWN + RSI 40-60", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60)]),
    ("DOWN + RSI 40-60 + UPTREND", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60) & (b0["trend"] == "UPTREND")]),
    ("DOWN + RSI 40-60 + DOWNTREND", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60) & (b0["trend"] == "DOWNTREND")]),
    ("DOWN + RSI 40-55", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 40) & (b0["rsi"] < 55)]),
    ("DOWN + RSI 45-60", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 45) & (b0["rsi"] < 60)]),
    ("DOWN + RSI 45-55", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 45) & (b0["rsi"] < 55)]),
    ("DOWN + Low vol (<50%)", b0[(b0["pred_dir"] == -1) & (b0["vol_pct"] < 50)]),
    ("DOWN + RSI 40-60 + Low vol", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60) & (b0["vol_pct"] < 50)]),
    ("DOWN + RSI 40-60 + High vol", b0[(b0["pred_dir"] == -1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60) & (b0["vol_pct"] >= 50)]),
]

hdr = "{:<45} {:>9} {:>9} {:>8}".format("Condition", "Accuracy", "Samples", "Err%")
print(hdr)
print("-" * 73)
for name, sub in combos:
    if len(sub) > 0:
        acc = sub["dir_correct"].mean() * 100
        err = sub["pct_err"].mean()
        print("{:<45} {:>8.1f}% {:>9} {:>7.2f}%".format(name, acc, len(sub), err))
    else:
        print("{:<45} {:>9} {:>9}".format(name, "N/A", 0))

print()
print("=== UP prediction conditions ===")
up_combos = [
    ("UP pred only", b0[b0["pred_dir"] == 1]),
    ("UP + DOWNTREND", b0[(b0["pred_dir"] == 1) & (b0["trend"] == "DOWNTREND")]),
    ("UP + RSI 40-60", b0[(b0["pred_dir"] == 1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60)]),
    ("UP + RSI 40-60 + DOWNTREND", b0[(b0["pred_dir"] == 1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60) & (b0["trend"] == "DOWNTREND")]),
    ("UP + RSI 40-60 + UPTREND", b0[(b0["pred_dir"] == 1) & (b0["rsi"] >= 40) & (b0["rsi"] < 60) & (b0["trend"] == "UPTREND")]),
]
print(hdr)
print("-" * 73)
for name, sub in up_combos:
    if len(sub) > 0:
        acc = sub["dir_correct"].mean() * 100
        err = sub["pct_err"].mean()
        print("{:<45} {:>8.1f}% {:>9} {:>7.2f}%".format(name, acc, len(sub), err))
    else:
        print("{:<45} {:>9} {:>9}".format(name, "N/A", 0))
