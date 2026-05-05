# -*- coding: utf-8 -*-
"""
Daily SMA Crossover Trader for Hyperliquid
SMA(5,17) crossover on daily BTC/USDT
Independent bot - runs alongside qwen_unified_live.py
"""

import os, sys, json, time, logging, argparse
import datetime as dt
from pathlib import Path
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional, Tuple
import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_path(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else PROJECT_ROOT / p


def round_order_size(size: float, decimals: int) -> float:
    if size <= 0:
        return 0.0
    quant = Decimal("1").scaleb(-decimals)
    rounded = Decimal(str(size)).quantize(quant, rounding=ROUND_DOWN)
    return float(rounded)


def _hl_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Config:
    symbol: str = "BTC"
    timeframe: str = "1d"
    use_testnet: bool = False
    wallet_address: str = field(default_factory=lambda: os.getenv("HL_WALLET_ADDRESS", ""))
    private_key: str = field(default_factory=lambda: os.getenv("HL_PRIVATE_KEY", ""))
    lookback_days: int = 365
    data_csv: str = "data/btc_price_1d_cache.csv"
    sma_fast: int = 5
    sma_slow: int = 17
    atr_period: int = 14
    trailing_atr_mult: float = 3.0
    risk_pct: float = 0.02
    max_position_pct: float = 0.40
    slippage_pct: float = 0.001
    min_notional: float = 10.0
    log_dir: str = "logs"
    state_file: str = "daily_sma_state.json"
    check_interval: int = 3600


class HyperliquidClient:
    def __init__(self, config: Config, logger):
        self.config = config
        self.logger = logger
        self._size_decimals_cache: dict[str, int] = {}
        try:
            from eth_account import Account
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange

            self.info = Info()
            if config.wallet_address and config.private_key:
                account = Account.from_key(config.private_key)
                base_url = (
                    "https://api.hyperliquid.testnet"
                    if config.use_testnet
                    else "https://api.hyperliquid.xyz"
                )
                self.exchange = Exchange(account, base_url=base_url, account_address=config.wallet_address)
                self.authenticated = True
            else:
                self.exchange = None
                self.authenticated = False
                self.logger.warning("No wallet credentials - Read-only mode")
        except Exception as e:
            self.logger.error(f"Failed to init HL client: {e}")
            raise

    def get_current_price(self, symbol: str) -> Optional[float]:
        try:
            mids = self.info.all_mids()
            if mids and symbol in mids:
                return float(mids[symbol])
            return None
        except Exception as e:
            self.logger.error(f"Price fetch error: {e}")
            return None

    def get_user_state(self) -> Optional[Dict[str, Any]]:
        if not self.authenticated:
            return None
        try:
            return self.info.user_state(self.config.wallet_address)
        except Exception as e:
            self.logger.error(f"user_state error: {e}")
            return None

    def equity_from_state(self, user_state: Optional[Dict[str, Any]]) -> float:
        if not user_state:
            return 0.0
        cms = user_state.get("crossMarginSummary") or {}
        ms = user_state.get("marginSummary") or {}
        if isinstance(cms, dict) and cms.get("accountValue") is not None:
            return _hl_float(cms.get("accountValue"))
        if isinstance(ms, dict) and ms.get("accountValue") is not None:
            return _hl_float(ms.get("accountValue"))
        return 0.0

    def get_balance(self) -> float:
        if not self.authenticated:
            return 0.0
        return self.equity_from_state(self.get_user_state())

    def parse_position(self, user_state: Optional[Dict[str, Any]], symbol: str) -> Optional[dict]:
        if not user_state or "assetPositions" not in user_state:
            return None
        for pos in user_state["assetPositions"]:
            p = pos.get("position", {})
            if (p.get("coin") or "").strip().upper() == symbol.upper():
                szi = _hl_float(p.get("szi"))
                if szi != 0:
                    return {"side": "LONG" if szi > 0 else "SHORT", "size": abs(szi), "entry": _hl_float(p.get("entryPx"))}
        return None

    def get_position(self, symbol: str) -> Optional[dict]:
        if not self.authenticated:
            return None
        try:
            return self.parse_position(self.get_user_state(), symbol)
        except Exception as e:
            self.logger.error(f"Position fetch error: {e}")
            return None

    def get_size_decimals(self, symbol: str) -> int:
        if symbol in self._size_decimals_cache:
            return self._size_decimals_cache[symbol]
        try:
            meta = self.info.meta()
            for coin in meta.get("universe", []):
                if coin.get("name") == symbol:
                    d = int(coin.get("szDecimals", 4))
                    self._size_decimals_cache[symbol] = d
                    return d
        except Exception:
            pass
        self._size_decimals_cache[symbol] = 4
        return 4

    def get_tick_size(self, symbol: str) -> float:
        try:
            import requests as _req
            API = "https://api.hyperliquid.xyz/info"
            now_ms = int(time.time() * 1000)
            payload = {"type": "candleSnapshot", "req": {"coin": symbol, "interval": "1m", "startTime": now_ms - 60000 * 3, "endTime": now_ms}}
            resp = _req.post(API, json=payload, timeout=10)
            candles = resp.json() if resp.status_code == 200 else []
            if candles:
                decimals_set = set()
                for cd in candles:
                    for key in ("o", "h", "l", "c"):
                        val = float(cd[key])
                        frac = val - int(val)
                        if abs(frac) < 1e-9:
                            decimals_set.add(0)
                        else:
                            d = 0
                            while abs(round(frac, d + 1) - frac) > 1e-9 and d < 8:
                                d += 1
                            decimals_set.add(d)
                min_d = min(decimals_set) if decimals_set else 0
                return 10 ** (-min_d)
        except Exception:
            pass
        return 1.0

    def round_price_to_tick(self, price: float, symbol: str) -> float:
        tick = self.get_tick_size(symbol)
        return round(price / tick) * tick

    def place_order(self, symbol: str, side: str, size: float, price: Optional[float] = None, reduce_only: bool = False) -> Optional[dict]:
        if not self.authenticated:
            self.logger.warning(f"DRY RUN: {side} {size} {symbol}")
            return {"status": "ok", "dry_run": True}
        try:
            is_buy = side == "buy"
            if price is None:
                px = self.get_current_price(symbol)
                if not px:
                    return None
                price = px * (1.001 if is_buy else 0.999)
            size = round_order_size(size, self.get_size_decimals(symbol))
            if size <= 0:
                self.logger.error(f"Order size rounded to zero")
                return None
            price = self.round_price_to_tick(float(price), symbol)
            order_type = {"limit": {"tif": "Ioc"}}
            result = self.exchange.order(name=symbol, is_buy=is_buy, sz=size, limit_px=price, order_type=order_type, reduce_only=reduce_only)
            if result:
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    first_status = statuses[0]
                    if "filled" in first_status:
                        self.logger.info(f"Order OK: {side.upper()} {size} {symbol} @ {price:.2f}")
                        return result
                    self.logger.warning(f"Order not filled: {first_status}")
                    return None
                self.logger.info(f"Order OK: {side.upper()} {size} {symbol} @ {price:.2f}")
                return result
            return None
        except Exception as e:
            self.logger.error(f"Order error: {e}")
            return None


def fetch_daily_ohlcv(c: Config, lg) -> pd.DataFrame:
    import requests as _req
    API = "https://api.hyperliquid.xyz/info"
    now_ms = int(time.time() * 1000)
    df = pd.DataFrame()

    csv_path = project_path(c.data_csv)
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, parse_dates=["datetime"], index_col="datetime").sort_index()
        except Exception:
            pass

    try:
        start_ms = int((dt.datetime.utcnow() - dt.timedelta(days=c.lookback_days)).timestamp() * 1000) if len(df) == 0 else int(df.index[-1].timestamp() * 1000)
        rows = []
        batch_start = start_ms
        while True:
            payload = {"type": "candleSnapshot", "req": {"coin": c.symbol, "interval": "1d", "startTime": batch_start, "endTime": now_ms}}
            resp = _req.post(API, json=payload, timeout=30)
            candles = resp.json() if resp.status_code == 200 else []
            if not candles:
                break
            for cd in candles:
                rows.append({"datetime": pd.Timestamp(cd["t"], unit="ms"), "open": float(cd["o"]), "high": float(cd["h"]), "low": float(cd["l"]), "close": float(cd["c"]), "volume": float(cd["v"])})
            if len(candles) < 500:
                break
            batch_start = candles[-1]["T"] + 1

        if rows:
            new_df = pd.DataFrame(rows).set_index("datetime").sort_index()
            new_df = new_df[~new_df.index.duplicated(keep="last")]
            if len(df) > 0:
                df = pd.concat([df, new_df])
                df = df[~df.index.duplicated(keep="last")].sort_index()
            else:
                df = new_df
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(str(csv_path))
            lg.info(f"HL API: fetched {len(rows)} daily candles, total {len(df)} bars")
    except Exception as e:
        lg.error(f"Data fetch error: {e}")

    return df.sort_index()


def compute_sma_signals(df: pd.DataFrame, c: Config) -> pd.DataFrame:
    if len(df) < c.sma_slow + 2:
        return df

    df["sma_fast"] = df["close"].rolling(c.sma_fast).mean()
    df["sma_slow"] = df["close"].rolling(c.sma_slow).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift(1)).abs(), (df["low"] - df["close"].shift(1)).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / c.atr_period, min_periods=c.atr_period).mean()

    df["sma_cross_long"] = ((df["sma_fast"] > df["sma_slow"]) & (df["sma_fast"].shift(1) <= df["sma_slow"].shift(1))).astype(int)
    df["sma_cross_short"] = ((df["sma_fast"] < df["sma_slow"]) & (df["sma_fast"].shift(1) >= df["sma_slow"].shift(1))).astype(int)

    return df


def load_state(c: Config) -> dict:
    sp = project_path(c.state_file)
    if sp.exists():
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"in_pos": False, "side": "", "size": 0.0, "entry_px": 0.0, "entry_ts": "", "stop": 0.0, "highest_since_entry": 0.0, "lowest_since_entry": 0.0, "trade_count": 0, "win_count": 0, "loss_count": 0, "total_pnl": 0.0, "last_signal_ts": 0}


def save_state(state: dict, c: Config):
    sp = project_path(c.state_file)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def run_bot(c: Config):
    log_dir = project_path(c.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = str(log_dir / f"daily_sma_{ts}.log")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()])
    lg = logging.getLogger("DailySMA")
    lg.info("=" * 60)
    lg.info("Daily SMA Crossover Bot starting")
    lg.info(f"Strategy: SMA({c.sma_fast},{c.sma_slow}) on daily")
    lg.info(f"Symbol: {c.symbol} | Check interval: {c.check_interval}s")
    lg.info("=" * 60)

    try:
        hl = HyperliquidClient(c, lg)
    except Exception:
        lg.error("Cannot init HL client. Exiting.")
        return

    state = load_state(c)
    lg.info(f"Loaded state: in_pos={state['in_pos']}, side={state['side']}, trades={state['trade_count']}")

    last_bar_date = None

    while True:
        try:
            df = fetch_daily_ohlcv(c, lg)
            if len(df) < c.sma_slow + 2:
                lg.warning(f"Not enough data ({len(df)} bars), waiting...")
                time.sleep(c.check_interval)
                continue

            df = compute_sma_signals(df, c)
            last = df.iloc[-1]
            prev = df.iloc[-2]
            current_date = df.index[-1].strftime("%Y-%m-%d")

            if current_date == last_bar_date:
                price = hl.get_current_price(c.symbol)
                equity = hl.get_balance()
                lg.info(f"Bar {current_date} already processed | Price: ${price:,.2f} | Equity: ${equity:,.2f} | SMA{c.sma_fast}={last['sma_fast']:.0f} SMA{c.sma_slow}={last['sma_slow']:.0f} | in_pos={state['in_pos']}")
                time.sleep(c.check_interval)
                continue

            last_bar_date = current_date
            price_now = hl.get_current_price(c.symbol) or last["close"]
            equity = hl.get_balance() or 100.0

            close_px = last["close"]
            atr_val = last["atr"] if not np.isnan(last["atr"]) else close_px * 0.03
            sma_f = last["sma_fast"]
            sma_s = last["sma_slow"]
            cross_long = int(last["sma_cross_long"]) if not np.isnan(last["sma_fast"]) else 0
            cross_short = int(last["sma_cross_short"]) if not np.isnan(last["sma_fast"]) else 0

            lg.info(f"NEW BAR {current_date} | Close: ${close_px:,.2f} | ATR: {atr_val:.0f} | SMA{c.sma_fast}={sma_f:.0f} SMA{c.sma_slow}={sma_s:.0f} | LongCross={cross_long} ShortCross={cross_short} | Equity: ${equity:,.2f}")

            if state["in_pos"]:
                if state["side"] == "LONG":
                    state["highest_since_entry"] = max(state["highest_since_entry"], close_px)
                    trail_stop = state["highest_since_entry"] - c.trailing_atr_mult * atr_val
                    should_exit = cross_short == 1 or close_px < trail_stop
                    exit_reason = "SMA cross SHORT" if cross_short == 1 else f"Trailing stop ({trail_stop:.0f})"
                else:
                    state["lowest_since_entry"] = min(state["lowest_since_entry"], close_px)
                    trail_stop = state["lowest_since_entry"] + c.trailing_atr_mult * atr_val
                    should_exit = cross_long == 1 or close_px > trail_stop
                    exit_reason = "SMA cross LONG" if cross_long == 1 else f"Trailing stop ({trail_stop:.0f})"

                if should_exit:
                    lg.info(f"EXIT SIGNAL: {exit_reason}")
                    exit_side = "buy" if state["side"] == "SHORT" else "sell"
                    result = hl.place_order(c.symbol, exit_side, state["size"], reduce_only=True)
                    if result:
                        pnl = (close_px - state["entry_px"]) / state["entry_px"] * 100 if state["side"] == "LONG" else (state["entry_px"] - close_px) / state["entry_px"] * 100
                        state["trade_count"] += 1
                        if pnl > 0:
                            state["win_count"] += 1
                        else:
                            state["loss_count"] += 1
                        state["total_pnl"] += pnl
                        lg.info(f"CLOSED {state['side']} @ ${close_px:,.2f} | PnL: {pnl:+.2f}% | Total: {state['trade_count']} trades ({state['win_count']}W/{state['loss_count']}L) | CumPnL: {state['total_pnl']:+.2f}%")
                        state["in_pos"] = False
                        state["side"] = ""
                        state["size"] = 0.0
                        state["entry_px"] = 0.0
                        state["stop"] = 0.0
                        state["highest_since_entry"] = 0.0
                        state["lowest_since_entry"] = float("inf")
                        save_state(state, c)
                    else:
                        lg.error("Exit order failed - will retry next bar")

            if not state["in_pos"]:
                entry_signal = None
                if cross_long == 1:
                    entry_signal = "LONG"
                elif cross_short == 1:
                    entry_signal = "SHORT"

                if entry_signal:
                    risk_amount = equity * c.risk_pct
                    position_value = min(equity * c.max_position_pct, risk_amount * 10)
                    order_size = position_value / close_px

                    if position_value < c.min_notional:
                        lg.warning(f"Position too small (${position_value:.2f} < ${c.min_notional})")
                        save_state(state, c)
                        time.sleep(c.check_interval)
                        continue

                    entry_side = "buy" if entry_signal == "LONG" else "sell"
                    result = hl.place_order(c.symbol, entry_side, order_size)
                    if result:
                        state["in_pos"] = True
                        state["side"] = entry_signal
                        state["size"] = order_size
                        state["entry_px"] = close_px
                        state["entry_ts"] = current_date
                        state["highest_since_entry"] = close_px
                        state["lowest_since_entry"] = close_px
                        lg.info(f"ENTERED {entry_signal} @ ${close_px:,.2f} | Size: {order_size:.6f} | Value: ${position_value:.2f}")
                        save_state(state, c)
                    else:
                        lg.error("Entry order failed")

            save_state(state, c)

        except Exception as e:
            lg.error(f"Main loop error: {e}", exc_info=True)

        time.sleep(c.check_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily SMA Crossover Trader")
    parser.add_argument("--interval", type=int, default=3600, help="Check interval in seconds")
    parser.add_argument("--testnet", action="store_true", help="Use testnet")
    args = parser.parse_args()

    cfg = Config(check_interval=args.interval, use_testnet=args.testnet)
    run_bot(cfg)
