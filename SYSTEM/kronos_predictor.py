#!/usr/bin/env python3
"""
Kronos Contrarian Predictor
Uses Kronos-base (Tsinghua, 102M params) to predict BTC direction.
Contrarian logic: reverse the prediction (community-validated edge).
Outputs kronos_contrarian_signal.json for qwen_unified_live.py
"""

import os, sys, json, time, logging, argparse
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "Kronos"))

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logger = logging.getLogger("KronosContrarian")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
file_handler = logging.FileHandler(LOG_DIR / "kronos_predictor_live.log", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

SIGNAL_FILE = "kronos_contrarian_signal.json"
DIRECT_SIGNAL_FILE = "kronos_signal.json"
DATA_CSV = "btc_usdt_4h_unified.csv"
KRONOS_LOOKBACK = 400
N_SAMPLES = 30
T_VALUE = 0.8
TOP_P = 0.6
PRED_LEN = 1


def fetch_latest_bars(n_bars=401):
    import requests
    API = "https://api.hyperliquid.xyz/info"
    now_ms = int(time.time() * 1000)
    step_ms = 4 * 3600 * 1000
    start_ms = now_ms - (n_bars * step_ms)
    payload = {
        "type": "candleSnapshot",
        "req": {"coin": "BTC", "interval": "4h", "startTime": int(start_ms), "endTime": now_ms}
    }
    resp = requests.post(API, json=payload, timeout=30)
    if resp.status_code != 200:
        return None
    candles = resp.json()
    if not candles:
        return None
    rows = []
    for c in candles:
        rows.append({
            "datetime": pd.Timestamp(c["t"], unit="ms"),
            "open": float(c["o"]), "high": float(c["h"]),
            "low": float(c["l"]), "close": float(c["c"]),
            "volume": float(c["v"])
        })
    df = pd.DataFrame(rows).set_index("datetime").sort_index()
    return df


def load_cached_data():
    if os.path.exists(DATA_CSV):
        try:
            return pd.read_csv(DATA_CSV, parse_dates=["datetime"], index_col="datetime").sort_index()
        except:
            pass
    return None


def get_ohlcv_window(lookback=KRONOS_LOOKBACK):
    df_cache = load_cached_data()
    df_live = fetch_latest_bars(lookback + 1)
    if df_live is not None and len(df_live) >= lookback:
        if df_cache is not None and len(df_cache) > len(df_live):
            df = pd.concat([df_cache, df_live])
            df = df[~df.index.duplicated(keep="last")].sort_index()
        else:
            df = df_live
        df.to_csv(DATA_CSV)
    elif df_cache is not None and len(df_cache) >= lookback:
        df = df_cache
    else:
        logger.error("Insufficient data")
        return None
    return df.iloc[-lookback:].copy()


def run_prediction(predictor, df):
    x_df = df[["open", "high", "low", "close", "volume"]].copy()
    x_df["amount"] = x_df["volume"] * x_df[["open", "high", "low", "close"]].mean(axis=1)
    x_ts = pd.Series(df.index)
    last_time = df.index[-1]
    next_time = last_time + pd.Timedelta(hours=4)
    y_ts = pd.Series([next_time])
    pred_df = predictor.predict(
        df=x_df.reset_index(drop=True), x_timestamp=x_ts, y_timestamp=y_ts,
        pred_len=PRED_LEN, T=T_VALUE, top_p=TOP_P, sample_count=N_SAMPLES, verbose=False
    )
    return pred_df


def compute_signal(pred_df, current_close):
    pred_close = pred_df.iloc[0]["close"]
    kronos_dir = 1 if pred_close > current_close else -1
    contrarian_dir = -kronos_dir
    return {
        "kronos_direction": "UP" if kronos_dir == 1 else "DOWN",
        "contrarian_direction": "LONG" if contrarian_dir == 1 else "SHORT",
        "contrarian_signal": contrarian_dir,
        "pred_close": float(pred_close),
        "current_close": float(current_close),
        "valid": True,
        "timestamp": int(time.time() * 1000),
        "samples": N_SAMPLES,
    }


def compute_direct_signal(pred_df, current_close):
    pred_close = float(pred_df.iloc[0]["close"])
    delta_pct = ((pred_close - current_close) / current_close) if current_close else 0.0
    strength = min(abs(delta_pct) / 0.02, 1.0)
    direction = "LONG" if delta_pct >= 0 else "SHORT"
    align_mult = min(1.0 + (strength * 0.4), 1.4)
    conflict_mult = 0.65
    return {
        "direction": direction,
        "prob_up": 0.5 + max(min(delta_pct * 10.0, 0.49), -0.49),
        "strength": round(strength, 4),
        "multiplier_long": align_mult if direction == "LONG" else conflict_mult,
        "multiplier_short": align_mult if direction == "SHORT" else conflict_mult,
        "pred_close": pred_close,
        "current_close": float(current_close),
        "valid": True,
        "timestamp": int(time.time() * 1000),
    }


def write_signal(signal, output_dir="."):
    path = Path(output_dir) / SIGNAL_FILE
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(signal, f, indent=2)
    tmp.replace(path)
    logger.info(f"Signal written: {signal['kronos_direction']} -> CONTRARIAN {signal['contrarian_direction']}")


def write_direct_signal(signal, output_dir="."):
    path = Path(output_dir) / DIRECT_SIGNAL_FILE
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(signal, f, indent=2)
    tmp.replace(path)
    logger.info(
        f"Direct Kronos signal written: {signal['direction']} "
        f"(long={signal['multiplier_long']:.2f}, short={signal['multiplier_short']:.2f})"
    )


def main():
    import torch
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    logger.info(f"Device: {device}")

    from model import Kronos, KronosTokenizer, KronosPredictor
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)
    logger.info("Kronos-base loaded")

    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=14400, help="Seconds between predictions (default: 4h)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    if args.once:
        df = get_ohlcv_window()
        if df is None or len(df) < KRONOS_LOOKBACK:
            logger.error("Not enough data")
            return
        current_close = df.iloc[-1]["close"]
        pred_df = run_prediction(predictor, df)
        signal = compute_signal(pred_df, current_close)
        direct_signal = compute_direct_signal(pred_df, current_close)
        write_signal(signal)
        write_direct_signal(direct_signal)
        return

    logger.info(f"Starting Contrarian predictor loop (interval={args.interval}s)")
    while True:
        try:
            df = get_ohlcv_window()
            if df is None or len(df) < KRONOS_LOOKBACK:
                logger.warning("Data insufficient, retrying next cycle")
                time.sleep(60)
                continue
            current_close = df.iloc[-1]["close"]
            t0 = time.time()
            pred_df = run_prediction(predictor, df)
            elapsed = time.time() - t0
            signal = compute_signal(pred_df, current_close)
            direct_signal = compute_direct_signal(pred_df, current_close)
            signal["inference_time_s"] = round(elapsed, 1)
            direct_signal["inference_time_s"] = round(elapsed, 1)
            write_signal(signal)
            write_direct_signal(direct_signal)
            logger.info(f"Kronos: {signal['kronos_direction']} -> Contrarian: {signal['contrarian_direction']} | pred={signal['pred_close']:.0f} vs current={signal['current_close']:.0f} | {elapsed:.1f}s")
        except Exception as e:
            logger.error(f"Cycle error: {e}", exc_info=True)
        logger.info(f"Sleeping {args.interval}s...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
