# -*- coding: utf-8 -*-
"""
Qwen Unified Live Trader - OCPM + Range MR + RSI Swing v6
Combines Trend Following (OCPM), Mean Reversion (Range MR), and RSI Swing
Manages positions independently but executes on shared account
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


def round_order_size(size: float, decimals: int) -> float:
    if size <= 0:
        return 0.0
    quant = Decimal("1").scaleb(-decimals)
    rounded = Decimal(str(size)).quantize(quant, rounding=ROUND_DOWN)
    return float(rounded)


def _hl_float(v: Any) -> float:
    """Hyperliquid API returns many numeric fields as strings."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ==================================================================
# CONFIGURATION
# ==================================================================


@dataclass
class Config:
    # Exchange
    symbol: str = "BTC"
    timeframe: str = "4h"
    use_testnet: bool = False

    # API
    wallet_address: str = field(
        default_factory=lambda: os.getenv("HL_WALLET_ADDRESS", "")
    )
    private_key: str = field(default_factory=lambda: os.getenv("HL_PRIVATE_KEY", ""))

    # Data
    lookback_days: int = 180
    data_csv: str = "btc_usdt_4h_unified.csv"

    # OCPM Params
    ocpm_ema_fast: int = 21
    ocpm_ema_slow: int = 55
    ocpm_donchian_period: int = 20
    ocpm_rsi_period: int = 14
    ocpm_rsi_pullback_long: float = 48.0
    ocpm_rsi_pullback_short: float = 52.0
    ocpm_atr_period: int = 14
    ocpm_hard_regime_enabled: bool = True
    ocpm_ema_regime_period: int = 200
    ocpm_atr_sl_mult: float = 3.0
    ocpm_atr_tp_mult: float = 6.0
    ocpm_max_hold: int = 20

    # Range MR Params
    mr_bb_period: int = 20
    mr_bb_std: float = 2.0
    mr_rsi_period: int = 14
    mr_rsi_oversold: float = 30.0
    mr_rsi_overbought: float = 70.0
    mr_atr_sl_mult: float = 2.0
    mr_max_hold: int = 10
    mr_adx_period: int = 14
    mr_max_adx: float = 25.0
    mr_ema_converge_pct: float = 0.020

    # RSI Swing v6 Params (Balanced config)
    rsi_swing_rsi_period: int = 14
    rsi_swing_rsi_os: float = 30.0
    rsi_swing_rsi_ob: float = 70.0
    rsi_swing_atr_period: int = 14
    rsi_swing_sl_atr: float = 2.0
    rsi_swing_tp_atr: float = 5.0
    rsi_swing_max_hold: int = 20

    # Risk
    risk_pct: float = 0.015
    max_position_pct: float = 0.40
    max_consecutive_losses: int = 5
    cooldown_bars: int = 2
    drawdown_halt_pct: float = 0.15

    # Strategy D: EV Optimization
    trend_filter_enabled: bool = True
    progressive_trail_enabled: bool = True
    progressive_trail_start_bar: int = 10
    progressive_trail_atr_mult: float = 2.0
    confluence_enabled: bool = True
    confluence_size_multiplier: float = 1.5

    # Order
    slippage_pct: float = 0.001
    min_notional: float = 10.0

    # System
    log_dir: str = "logs"
    state_file: str = "trade_state_unified.json"
    check_interval: int = 60

    # Whale / Macro Integration
    whale_signal_file: str = "whale_signal.json"
    macro_state_file: str = "macro_state.json"
    whale_enabled: bool = True
    macro_enabled: bool = True
    whale_signal_max_age_minutes: int = 30
    macro_state_max_age_minutes: int = 120
    whale_align_multiplier_max: float = 1.5
    whale_conflict_multiplier: float = 0.6
    macro_caution_multiplier: float = 0.5
    alignment_log_file: str = "trade_alignment_log.json"

    # On-chain exchange inflow -> supplementary SHORT bias (EV1; see SYSTEM/inflow_short_signal_builder.py)
    inflow_short_enabled: bool = True
    inflow_short_signal_file: str = "inflow_short_signal.json"
    inflow_short_signal_max_age_minutes: int = 120
    inflow_short_boost_max: float = 0.12  # max +12% size on SHORT when strength=1.0

    # Kronos AI Integration
    kronos_signal_file: str = "kronos_signal.json"
    kronos_enabled: bool = True
    kronos_shadow_mode: bool = (
        False  # True = log only, no sizing effect; False = live [PRODUCTION]
    )
    kronos_signal_max_age_minutes: int = 300
    kronos_align_multiplier_max: float = 1.4
    kronos_conflict_multiplier: float = 0.65
    kronos_neutral_band: float = 0.05

    # Contrarian Strategy (Kronos-based, 4h)
    contrarian_enabled: bool = True
    contrarian_signal_file: str = "kronos_contrarian_signal.json"
    contrarian_signal_max_age_minutes: int = 300
    contrarian_sl_atr_mult: float = 2.0
    contrarian_tp_atr_mult: float = 4.0
    contrarian_max_hold: int = 8
    contrarian_vol_filter_enabled: bool = True
    contrarian_min_vol_pct: float = 35.0
    contrarian_max_vol_pct: float = 80.0
    contrarian_risk_pct: float = 0.04
    contrarian_max_position_pct: float = 0.30
    contrarian_max_consecutive_losses: int = 5
    contrarian_cooldown_bars: int = 2
    # flag to enable Kronos multiplier for Contrarian size
    contrarian_use_kronos_multiplier: bool = False
    # Kronos Edge Filter: only trade when contrarian edge is statistically strongest
    # (Kronos accuracy drops to ~46% when RSI>55 & UPTREND => contrarian WR ~54%)
    contrarian_edge_filter_enabled: bool = False
    legacy_capital_pct: float = 0.30
    contrarian_capital_pct: float = 0.70


# ==================================================================
# HYPERLIQUID CLIENT (SDK v0.22)
# ==================================================================


class HyperliquidClient:
    def __init__(self, config: Config, logger):
        self.config = config
        self.logger = logger
        self._size_decimals_cache: dict[str, int] = {}
        try:
            from eth_account import Account
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils.signing import OrderType

            self.OrderType = OrderType
            self.info = Info()

            if config.wallet_address and config.private_key:
                account = Account.from_key(config.private_key)
                base_url = (
                    "https://api.hyperliquid.testnet"
                    if config.use_testnet
                    else "https://api.hyperliquid.xyz"
                )
                self.exchange = Exchange(
                    account, base_url=base_url, account_address=config.wallet_address
                )
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

    def equity_margin_withdrawable_from_state(
        self, user_state: Optional[Dict[str, Any]]
    ) -> Tuple[float, float, float]:
        """
        From clearinghouseState: (account_value_usd, total_margin_used_usd, withdrawable_usd).
        Prefer crossMarginSummary (typical perp UI); fallback marginSummary.
        """
        if not user_state:
            return 0.0, 0.0, 0.0
        wd = _hl_float(user_state.get("withdrawable"))
        cms = user_state.get("crossMarginSummary") or {}
        ms = user_state.get("marginSummary") or {}
        if isinstance(cms, dict) and cms.get("accountValue") is not None:
            return (
                _hl_float(cms.get("accountValue")),
                _hl_float(cms.get("totalMarginUsed")),
                wd,
            )
        if isinstance(ms, dict) and ms.get("accountValue") is not None:
            return (
                _hl_float(ms.get("accountValue")),
                _hl_float(ms.get("totalMarginUsed")),
                wd,
            )
        return 0.0, 0.0, wd

    def get_balance(self) -> float:
        if not self.authenticated:
            return 0.0
        av, _, _ = self.equity_margin_withdrawable_from_state(self.get_user_state())
        return av

    def parse_position_from_state(
        self, user_state: Optional[Dict[str, Any]], symbol: str
    ) -> Optional[dict]:
        """Returns {'side': 'LONG'/'SHORT', 'size': float, 'entry': float} or None"""
        if not user_state or "assetPositions" not in user_state:
            return None
        for pos in user_state["assetPositions"]:
            p = pos.get("position", {})
            if p.get("coin") != symbol:
                continue
            szi = _hl_float(p.get("szi"))
            if szi != 0:
                return {
                    "side": "LONG" if szi > 0 else "SHORT",
                    "size": abs(szi),
                    "entry": _hl_float(p.get("entryPx")),
                }
        return None

    def get_position(self, symbol: str) -> dict:
        """Returns {'side': 'LONG'/'SHORT', 'size': float, 'entry': float} or None"""
        if not self.authenticated:
            return None
        try:
            return self.parse_position_from_state(self.get_user_state(), symbol)
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
                    decimals = int(coin.get("szDecimals", 4))
                    self._size_decimals_cache[symbol] = decimals
                    return decimals
        except Exception as e:
            self.logger.debug(f"Size decimals lookup failed for {symbol}: {e}")
        self._size_decimals_cache[symbol] = 4
        return 4

    def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Optional[dict]:
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
                self.logger.error(f"Order size rounded to zero for {symbol}")
                return None

            price = round(float(price), 1)
            order_type = {"limit": {"tif": "Ioc"}}

            result = self.exchange.order(
                name=symbol,
                is_buy=is_buy,
                sz=size,
                limit_px=price,
                order_type=order_type,
                reduce_only=reduce_only,
            )

            if result:
                statuses = (
                    result.get("response", {}).get("data", {}).get("statuses", [])
                )
                if statuses:
                    first_status = statuses[0]
                    if "filled" in first_status:
                        self.logger.info(
                            f"Order OK: {side.upper()} {size} {symbol} @ {price:.2f}"
                        )
                        return result
                    self.logger.warning(f"Order not filled immediately: {first_status}")
                    return None
                self.logger.info(
                    f"Order OK: {side.upper()} {size} {symbol} @ {price:.2f}"
                )
                return result
            return None
        except Exception as e:
            self.logger.error(f"Order error: {e}")
            return None


# ==================================================================
# DATA & INDICATORS
# ==================================================================


def fetch_ohlcv(c, lg):
    import requests as _req

    API = "https://api.hyperliquid.xyz/info"
    interval_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }
    hl_interval = interval_map.get(c.timeframe, "4h")
    now_ms = int(time.time() * 1000)

    df = pd.DataFrame()
    if os.path.exists(c.data_csv):
        try:
            df = pd.read_csv(
                c.data_csv, parse_dates=["datetime"], index_col="datetime"
            ).sort_index()
        except Exception:
            pass

    try:
        start_ms = (
            int(
                (dt.datetime.utcnow() - dt.timedelta(days=c.lookback_days)).timestamp()
                * 1000
            )
            if len(df) == 0
            else int(df.index[-1].timestamp() * 1000)
        )

        rows = []
        batch_start = start_ms
        while True:
            payload = {
                "type": "candleSnapshot",
                "req": {
                    "coin": c.symbol,
                    "interval": hl_interval,
                    "startTime": batch_start,
                    "endTime": now_ms,
                },
            }
            resp = _req.post(API, json=payload, timeout=30)
            candles = resp.json() if resp.status_code == 200 else []
            if not candles:
                break
            for cd in candles:
                rows.append(
                    {
                        "datetime": pd.Timestamp(cd["t"], unit="ms"),
                        "open": float(cd["o"]),
                        "high": float(cd["h"]),
                        "low": float(cd["l"]),
                        "close": float(cd["c"]),
                        "volume": float(cd["v"]),
                    }
                )
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
            df.to_csv(c.data_csv)
            lg.info(f"HL API: fetched {len(rows)} candles, total {len(df)} bars")
    except Exception as e:
        lg.error(f"Data fetch error: {e}")

    if len(df) == 0:
        lg.warning("No OHLCV data available")

    return df.sort_index()


def compute_indicators(df, c):
    # --- OCPM ---
    df["ocpm_ema_f"] = df["close"].ewm(span=c.ocpm_ema_fast, adjust=False).mean()
    df["ocpm_ema_s"] = df["close"].ewm(span=c.ocpm_ema_slow, adjust=False).mean()
    df["ocpm_ema_regime"] = (
        df["close"].ewm(span=c.ocpm_ema_regime_period, adjust=False).mean()
    )
    df["ocpm_slope"] = df["ocpm_ema_f"].pct_change(10)

    # Donchian Channel for trend confirmation
    donchian_period = getattr(c, "ocpm_donchian_period", 20)
    df["ocpm_donchian_high"] = df["high"].rolling(donchian_period).max()
    df["ocpm_donchian_low"] = df["low"].rolling(donchian_period).min()

    df["ocpm_trend"] = "RANGE"
    df.loc[df["close"] > df["ocpm_ema_s"], "ocpm_trend"] = "UPTREND"
    df.loc[df["close"] < df["ocpm_ema_s"], "ocpm_trend"] = "DOWNTREND"

    # --- Shared RSI/ATR ---
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / c.ocpm_rsi_period, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1 / c.ocpm_rsi_period, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    df["rsi_prev"] = df["rsi"].shift(1)

    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.ewm(
        alpha=1 / c.ocpm_atr_period, min_periods=c.ocpm_atr_period
    ).mean()
    df["vol_pct"] = df["close"].pct_change().abs().rolling(50).rank(pct=True) * 100

    # OCPM Signals with Donchian trend structure confirmation
    donchian_mid = (df["ocpm_donchian_high"] + df["ocpm_donchian_low"]) / 2
    donchian_trend_long = df["close"] > donchian_mid
    donchian_trend_short = df["close"] < donchian_mid

    df["ocpm_long"] = (
        (df["ocpm_trend"] == "UPTREND")
        & donchian_trend_long
        & (df["rsi_prev"] <= c.ocpm_rsi_pullback_long)
        & (df["rsi"] > df["rsi_prev"])
        & (df["rsi"] < 55)
    ).astype(int)
    df["ocpm_short"] = (
        (df["ocpm_trend"] == "DOWNTREND")
        & donchian_trend_short
        & (df["rsi_prev"] >= c.ocpm_rsi_pullback_short)
        & (df["rsi"] < df["rsi_prev"])
        & (df["rsi"] > 45)
    ).astype(int)
    df["ocpm_hard_long_ok"] = (
        (df["close"] > df["ocpm_ema_s"])
        & (df["ocpm_ema_s"] > df["ocpm_ema_regime"])
        & (df["ocpm_ema_f"] > df["ocpm_ema_s"])
        & (df["ocpm_slope"] > 0)
    ).astype(int)
    df["ocpm_hard_short_ok"] = (
        (df["close"] < df["ocpm_ema_s"])
        & (df["ocpm_ema_s"] < df["ocpm_ema_regime"])
        & (df["ocpm_ema_f"] < df["ocpm_ema_s"])
        & (df["ocpm_slope"] < 0)
    ).astype(int)

    # --- Range MR ---
    df["bb_mid"] = df["close"].rolling(c.mr_bb_period).mean()
    bb_std = df["close"].rolling(c.mr_bb_period).std()
    df["bb_upper"] = df["bb_mid"] + c.mr_bb_std * bb_std
    df["bb_lower"] = df["bb_mid"] - c.mr_bb_std * bb_std

    df["ema_f"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_s"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema_conv"] = (df["ema_f"] - df["ema_s"]).abs() / df["close"]

    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()
    plus_dm = plus_dm.clip(lower=0).where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.clip(lower=0).where(minus_dm > plus_dm, 0)
    atr_raw = tr.ewm(alpha=1 / c.mr_adx_period, min_periods=c.mr_adx_period).mean()
    plus_di = 100 * (
        plus_dm.ewm(alpha=1 / c.mr_adx_period, min_periods=c.mr_adx_period).mean()
        / atr_raw
    )
    minus_di = 100 * (
        minus_dm.ewm(alpha=1 / c.mr_adx_period, min_periods=c.mr_adx_period).mean()
        / atr_raw
    )
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = dx.ewm(alpha=1 / c.mr_adx_period, min_periods=c.mr_adx_period).mean()

    df["is_range"] = (df["adx"] < c.mr_max_adx) & (
        df["ema_conv"] < c.mr_ema_converge_pct
    )
    df["mr_long"] = (
        df["is_range"]
        & (df["low"] <= df["bb_lower"])
        & (df["rsi_prev"] <= c.mr_rsi_oversold)
        & (df["rsi"] > df["rsi_prev"])
    ).astype(int)
    df["mr_short"] = (
        df["is_range"]
        & (df["high"] >= df["bb_upper"])
        & (df["rsi_prev"] >= c.mr_rsi_overbought)
        & (df["rsi"] < df["rsi_prev"])
    ).astype(int)

    # --- RSI Swing v6 (Balanced) ---
    df["rsi_swing_long"] = (
        (df["rsi_prev"] <= c.rsi_swing_rsi_os)
        & (df["rsi"] > df["rsi_prev"])
        & (df["rsi"] > c.rsi_swing_rsi_os)
    ).astype(int)
    df["rsi_swing_short"] = (
        (df["rsi_prev"] >= c.rsi_swing_rsi_ob)
        & (df["rsi"] < df["rsi_prev"])
        & (df["rsi"] < c.rsi_swing_rsi_ob)
    ).astype(int)

    return df


# ==================================================================
# STRATEGY LOGIC
# ==================================================================


@dataclass
class StratState:
    name: str
    in_pos: bool = False
    side: str = ""
    size: float = 0.0
    entry_px: float = 0.0
    stop: float = 0.0
    tp: float = 0.0
    entry_bar: int = 0
    entry_ts: str = ""
    c_loss: int = 0
    cool_bar: int = 0
    last_signal_ts: int = 0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if "name" not in d:
            d["name"] = "Unknown"
        return cls(**d)


class UnifiedEngine:
    def __init__(self, c, lg):
        self.c = c
        self.lg = lg
        self.hl = HyperliquidClient(c, lg)
        self.ocpm = StratState("OCPM")
        self.mr = StratState("RangeMR")
        self.rsi_swing = StratState("RSISwing")
        self.contrarian = StratState("Contrarian")
        self.current_bar = 0
        self.last_processed_bar_ts = 0
        self._current_eval_bar_ts = 0
        self._confluence_direction = None
        self.load_state()

    def load_state(self):
        if os.path.exists(self.c.state_file):
            try:
                with open(self.c.state_file) as f:
                    data = json.load(f)
                self.ocpm = StratState.from_dict(data.get("ocpm", {}))
                self.mr = StratState.from_dict(data.get("mr", {}))
                self.rsi_swing = StratState.from_dict(data.get("rsi_swing", {}))
                self.contrarian = StratState.from_dict(
                    data.get("contrarian", {"name": "Contrarian"})
                )
                if self.contrarian.name == "Unknown":
                    self.contrarian.name = "Contrarian"
                self.current_bar = data.get("current_bar", 0)
                self.last_processed_bar_ts = data.get("last_processed_bar_ts", 0)
                self.lg.info(
                    f"State loaded: OCPM={'Yes' if self.ocpm.in_pos else 'No'}, MR={'Yes' if self.mr.in_pos else 'No'}, RSISwing={'Yes' if self.rsi_swing.in_pos else 'No'}, Contrarian={'Yes' if self.contrarian.in_pos else 'No'}"
                )
            except Exception as e:
                self.lg.warning(f"State load error: {e}")

    def _save_account_state(self, px: float, user_state: Optional[Dict[str, Any]]):
        try:
            av, mu, wd = self.hl.equity_margin_withdrawable_from_state(user_state)
            pos = self.hl.parse_position_from_state(user_state, self.c.symbol)
            account_state = {
                "timestamp": dt.datetime.utcnow().isoformat(),
                "account": {
                    "wallet": self.c.wallet_address,
                    "balance": round(av, 4),
                    "equity": round(av, 4),
                    "margin_used": round(mu, 4),
                    "withdrawable": round(wd, 4),
                    "available_margin": round(wd, 4),
                    "currency": "USD",
                },
                "positions": [],
                "status": "ready",
            }
            if pos and pos.get("size", 0) > 0:
                account_state["positions"].append(
                    {
                        "symbol": self.c.symbol,
                        "size": pos["size"],
                        "entry_price": pos["entry"],
                        "current_price": px,
                        "unrealized_pnl": (px - pos["entry"])
                        * pos["size"]
                        * (1 if pos["side"] == "LONG" else -1),
                        "side": pos["side"],
                    }
                )
            else:
                account_state["positions"].append(
                    {
                        "symbol": self.c.symbol,
                        "size": 0.0,
                        "entry_price": 0.0,
                        "current_price": px,
                        "unrealized_pnl": 0.0,
                        "side": "NONE",
                    }
                )
            os.makedirs("logs", exist_ok=True)
            with open("logs/account_state.json", "w") as f:
                json.dump(account_state, f, indent=2)
        except Exception as e:
            self.lg.debug(f"Account state save skipped: {e}")

    def save_state(self):
        data = {
            "ocpm": self.ocpm.to_dict(),
            "mr": self.mr.to_dict(),
            "rsi_swing": self.rsi_swing.to_dict(),
            "contrarian": self.contrarian.to_dict(),
            "current_bar": self.current_bar,
            "last_processed_bar_ts": self.last_processed_bar_ts,
        }
        with open(self.c.state_file, "w") as f:
            json.dump(data, f, indent=2)

    def _get_eval_bar(self, df: pd.DataFrame) -> tuple[pd.Series, int, bool]:
        if len(df) >= 2:
            eval_idx = -2
        else:
            eval_idx = -1
        eval_bar = df.iloc[eval_idx]
        eval_bar_ts = int(pd.Timestamp(df.index[eval_idx]).timestamp() * 1000)
        is_new_bar = eval_bar_ts > self.last_processed_bar_ts
        return eval_bar, eval_bar_ts, is_new_bar

    def run_once(self):
        df = fetch_ohlcv(self.c, self.lg)
        df = compute_indicators(df, self.c)
        r, eval_bar_ts, is_new_bar = self._get_eval_bar(df)
        self._current_eval_bar_ts = eval_bar_ts
        if is_new_bar:
            self.current_bar += 1
            self.last_processed_bar_ts = eval_bar_ts

        px = self.hl.get_current_price(self.c.symbol)
        if not px:
            px = r["close"]

        us = self.hl.get_user_state() if self.hl.authenticated else None
        av, mu, wd = self.hl.equity_margin_withdrawable_from_state(us)
        bal = av
        self.lg.info(
            f"Bar {self.current_bar} | Price: ${px:,.2f} | Equity: ${bal:,.2f} "
            f"(margin_used ${mu:,.2f}, withdrawable ${wd:,.2f}) | RSI: {r['rsi']:.1f} | Trend: {r['ocpm_trend']}"
        )

        self._save_account_state(px, us)

        self._detect_confluence(r)

        # 1. Manage Exits
        self._manage_ocpm_exit(r, px)
        self._manage_mr_exit(r, px)
        self._manage_rsi_swing_exit(r, px)
        self._manage_contrarian_exit(r, px)

        # 2. Check Entries
        if is_new_bar:
            if not self.ocpm.in_pos and self.current_bar >= self.ocpm.cool_bar:
                self._check_ocpm_entry(r, px, bal)

            if not self.mr.in_pos and self.current_bar >= self.mr.cool_bar:
                self._check_mr_entry(r, px, bal)

            if (
                not self.rsi_swing.in_pos
                and self.current_bar >= self.rsi_swing.cool_bar
            ):
                self._check_rsi_swing_entry(r, px, bal)

            if (
                self.c.contrarian_enabled
                and not self.contrarian.in_pos
                and self.current_bar >= self.contrarian.cool_bar
            ):
                self._check_contrarian_entry(r, px, bal)

        # 3. Sync with Exchange
        self._sync_positions()
        self.save_state()

    def _manage_ocpm_exit(self, r, px):
        if not self.ocpm.in_pos:
            return
        s = self.ocpm
        held = self.current_bar - s.entry_bar

        # Time Stop
        if held >= self.c.ocpm_max_hold:
            self.lg.info(f"OCPM TIME EXIT: {s.side}")
            self._close_strat(s, px, "TIME_EXIT")
            return

        # Trailing Stop
        if r["atr"] > 0:
            trail_mult = self.c.ocpm_atr_sl_mult
            if (
                self.c.progressive_trail_enabled
                and held >= self.c.progressive_trail_start_bar
            ):
                trail_mult = self.c.progressive_trail_atr_mult
                if held == self.c.progressive_trail_start_bar:
                    self.lg.info(
                        f"OCPM trailing tightened to {trail_mult}x ATR at bar {held}"
                    )
            if s.side == "LONG":
                new_sl = px - trail_mult * r["atr"]
                if new_sl > s.stop:
                    s.stop = new_sl
                if px <= s.stop:
                    self._close_strat(s, s.stop, "TRAILING_STOP")
                    return
                tp = s.entry_px + self.c.ocpm_atr_tp_mult * r["atr"]
                if px >= tp:
                    self._close_strat(s, tp, "ATR_TP")
                    return
            else:
                new_sl = px + trail_mult * r["atr"]
                if new_sl < s.stop:
                    s.stop = new_sl
                if px >= s.stop:
                    self._close_strat(s, s.stop, "TRAILING_STOP")
                    return
                tp = s.entry_px - self.c.ocpm_atr_tp_mult * r["atr"]
                if px <= tp:
                    self._close_strat(s, tp, "ATR_TP")
                    return

        # RSI Exit
        if s.side == "LONG" and r["rsi"] > 70:
            self._close_strat(s, px, "RSI_EXIT")
        elif s.side == "SHORT" and r["rsi"] < 30:
            self._close_strat(s, px, "RSI_EXIT")

    def _manage_mr_exit(self, r, px):
        if not self.mr.in_pos:
            return
        s = self.mr
        held = self.current_bar - s.entry_bar

        if held >= self.c.mr_max_hold:
            self.lg.info(f"MR TIME EXIT: {s.side}")
            self._close_strat(s, px, "TIME_EXIT")
            return

        if r["atr"] > 0:
            if s.side == "LONG":
                if px <= s.stop:
                    self._close_strat(s, s.stop, "STOP_LOSS")
                    return
                if px >= r["bb_mid"]:
                    self._close_strat(s, r["bb_mid"], "BB_MID_TP")
                    return
            else:
                if px >= s.stop:
                    self._close_strat(s, s.stop, "STOP_LOSS")
                    return
                if px <= r["bb_mid"]:
                    self._close_strat(s, r["bb_mid"], "BB_MID_TP")
                    return

    def _manage_rsi_swing_exit(self, r, px):
        if not self.rsi_swing.in_pos:
            return
        s = self.rsi_swing
        held = self.current_bar - s.entry_bar

        if held >= self.c.rsi_swing_max_hold:
            self.lg.info(f"RSISwing TIME EXIT: {s.side}")
            self._close_strat(s, px, "TIME_EXIT")
            return

        if r["atr"] > 0:
            if s.side == "LONG":
                new_sl = px - self.c.rsi_swing_sl_atr * r["atr"]
                if new_sl > s.stop:
                    s.stop = new_sl
                if px <= s.stop:
                    self._close_strat(s, s.stop, "TRAILING_STOP")
                    return
                tp = s.entry_px + self.c.rsi_swing_tp_atr * r["atr"]
                if px >= tp:
                    self._close_strat(s, tp, "ATR_TP")
                    return
            else:
                new_sl = px + self.c.rsi_swing_sl_atr * r["atr"]
                if new_sl < s.stop:
                    s.stop = new_sl
                if px >= s.stop:
                    self._close_strat(s, s.stop, "TRAILING_STOP")
                    return
                tp = s.entry_px - self.c.rsi_swing_tp_atr * r["atr"]
                if px <= tp:
                    self._close_strat(s, tp, "ATR_TP")
                    return

        if s.side == "LONG" and r["rsi"] > 70:
            self._close_strat(s, px, "RSI_EXIT")
        elif s.side == "SHORT" and r["rsi"] < 30:
            self._close_strat(s, px, "RSI_EXIT")

    def _manage_contrarian_exit(self, r, px):
        if not self.contrarian.in_pos:
            return
        s = self.contrarian
        held = self.current_bar - s.entry_bar

        if held >= self.c.contrarian_max_hold:
            self.lg.info(f"Contrarian TIME EXIT: {s.side}")
            self._close_strat(s, px, "TIME_EXIT")
            return

        if s.side == "LONG":
            if s.stop > 0 and px <= s.stop:
                self._close_strat(s, s.stop, "STOP_LOSS")
                return
            if s.tp > 0 and px >= s.tp:
                self._close_strat(s, s.tp, "TAKE_PROFIT")
                return
        else:
            if s.stop > 0 and px >= s.stop:
                self._close_strat(s, s.stop, "STOP_LOSS")
                return
            if s.tp > 0 and px <= s.tp:
                self._close_strat(s, s.tp, "TAKE_PROFIT")
                return

    def _get_legacy_strategies(self):
        return [self.ocpm, self.mr, self.rsi_swing]

    def _strategy_pool_total(self, strategy_name: str, balance: float) -> float:
        if strategy_name == "Contrarian":
            return balance * self.c.contrarian_capital_pct
        return balance * self.c.legacy_capital_pct

    def _strategy_pool_used_notional(self, strategy_name: str, price: float) -> float:
        if strategy_name == "Contrarian":
            strategies = [self.contrarian]
        else:
            strategies = self._get_legacy_strategies()
        return sum(s.size * price for s in strategies if s.in_pos)

    def _strategy_available_notional(
        self, strategy_name: str, balance: float, price: float
    ) -> float:
        pool_total = self._strategy_pool_total(strategy_name, balance)
        pool_used = self._strategy_pool_used_notional(strategy_name, price)
        return max(0.0, pool_total - pool_used)

    def _strategy_risk_budget(self, strategy_name: str, balance: float) -> float:
        pool_total = self._strategy_pool_total(strategy_name, balance)
        if strategy_name == "Contrarian":
            return pool_total * self.c.contrarian_risk_pct
        return pool_total * self.c.risk_pct

    def _strategy_position_cap(self, strategy_name: str, balance: float) -> float:
        pool_total = self._strategy_pool_total(strategy_name, balance)
        if strategy_name == "Contrarian":
            return pool_total * self.c.contrarian_max_position_pct
        return pool_total * self.c.max_position_pct

    def _strategy_max_losses(self, strategy_name: str) -> int:
        if strategy_name == "Contrarian":
            return self.c.contrarian_max_consecutive_losses
        return self.c.max_consecutive_losses

    def _strategy_cooldown(self, strategy_name: str) -> int:
        if strategy_name == "Contrarian":
            return self.c.contrarian_cooldown_bars
        return self.c.cooldown_bars

    def _check_rsi_swing_entry(self, r, px, bal):
        risk = self._strategy_risk_budget("RSISwing", bal)
        sl_d = self.c.rsi_swing_sl_atr * r["atr"]
        if sl_d <= 0 or np.isnan(sl_d):
            return
        available_notional = self._strategy_available_notional("RSISwing", bal, px)
        sz = min(
            risk / sl_d,
            self._strategy_position_cap("RSISwing", bal) / px,
            available_notional / px,
        )
        if sz * px < self.c.min_notional:
            return

        # Read whale/macro/kronos signals
        whale_sig = self._read_whale_signal()
        macro_state = self._read_macro_state()
        kronos_sig = self._read_kronos_signal()

        if r["rsi_swing_long"] == 1:
            if not self._trend_filter_pass("LONG", r):
                self.lg.debug("RSISwing LONG skipped - counter-trend (DOWNTREND)")
                return
            multiplier = self._compute_whale_multiplier("LONG", whale_sig, macro_state)
            multiplier = self._apply_inflow_short_multiplier("LONG", multiplier)
            if multiplier == 0.0:
                self.lg.info(f"RSISwing LONG skipped - EXTREME macro regime")
                return
            kronos_mult = self._compute_kronos_multiplier("LONG", kronos_sig)
            conf_mult = self._get_confluence_multiplier("LONG")
            final_sz = sz * multiplier * kronos_mult * conf_mult
            final_sz = max(final_sz, sz * 0.25)  # Floor: never below 25% of base
            if final_sz * px < self.c.min_notional:
                return
            self.lg.info(
                f"RSISwing LONG SIGNAL @ {px:.2f} (RSI={r['rsi']:.1f}) | whale={multiplier:.2f} kronos={kronos_mult:.2f} conf={conf_mult:.2f} | sz={sz:.4f}→{final_sz:.4f}"
            )
            if self._open_strat(self.rsi_swing, "LONG", final_sz, px, px - sl_d):
                self._log_trade_alignment(
                    "RSISwing",
                    "LONG",
                    whale_sig,
                    macro_state,
                    multiplier,
                    sz,
                    final_sz,
                    px,
                    kronos_sig,
                )
        elif r["rsi_swing_short"] == 1:
            if not self._trend_filter_pass("SHORT", r):
                self.lg.debug("RSISwing SHORT skipped - counter-trend (UPTREND)")
                return
            multiplier = self._compute_whale_multiplier("SHORT", whale_sig, macro_state)
            multiplier = self._apply_inflow_short_multiplier("SHORT", multiplier)
            if multiplier == 0.0:
                self.lg.info(f"RSISwing SHORT skipped - EXTREME macro regime")
                return
            kronos_mult = self._compute_kronos_multiplier("SHORT", kronos_sig)
            conf_mult = self._get_confluence_multiplier("SHORT")
            final_sz = sz * multiplier * kronos_mult * conf_mult
            final_sz = max(final_sz, sz * 0.25)  # Floor: never below 25% of base
            if final_sz * px < self.c.min_notional:
                return
            self.lg.info(
                f"RSISwing SHORT SIGNAL @ {px:.2f} (RSI={r['rsi']:.1f}) | whale={multiplier:.2f} kronos={kronos_mult:.2f} conf={conf_mult:.2f} | sz={sz:.4f}→{final_sz:.4f}"
            )
            if self._open_strat(self.rsi_swing, "SHORT", final_sz, px, px + sl_d):
                self._log_trade_alignment(
                    "RSISwing",
                    "SHORT",
                    whale_sig,
                    macro_state,
                    multiplier,
                    sz,
                    final_sz,
                    px,
                    kronos_sig,
                )

    def _close_strat(self, s, px, reason):
        self.lg.info(f"[{s.name}] CLOSING {s.side} @ {px:.2f} ({reason})")
        side = "sell" if s.side == "LONG" else "buy"
        self.hl.place_order(self.c.symbol, side, s.size, price=px, reduce_only=True)
        pnl_sign = (px - s.entry_px) if s.side == "LONG" else (s.entry_px - px)
        if pnl_sign <= 0:
            s.c_loss += 1
            if s.c_loss >= self._strategy_max_losses(s.name):
                s.cool_bar = self.current_bar + self._strategy_cooldown(s.name)
                self.lg.warning(f"[{s.name}] Cooldown triggered until bar {s.cool_bar}")
        else:
            s.c_loss = 0
        # Backfill outcome in alignment log for EV measurement
        self._backfill_alignment_outcome(s.name, s.side, px)
        s.in_pos = False
        s.size = 0.0
        s.side = ""
        s.entry_px = 0.0
        s.stop = 0.0
        s.tp = 0.0
        s.entry_bar = 0
        s.entry_ts = ""

    def _backfill_alignment_outcome(
        self, strategy_name: str, side: str, exit_px: float
    ) -> None:
        """Write outcome to last open trade record in alignment log"""
        try:
            log_path = self.c.alignment_log_file
            if not os.path.exists(log_path):
                return
            with open(log_path) as f:
                records = json.load(f)
            # Find last None-outcome record for this strategy
            for i in range(len(records) - 1, -1, -1):
                if (
                    records[i].get("strategy") == strategy_name
                    and records[i].get("outcome") is None
                ):
                    entry_px = records[i].get("entry_px")
                    if entry_px and entry_px > 0:
                        pnl_pct = ((exit_px - entry_px) / entry_px) * 100.0
                        if side == "SHORT":
                            pnl_pct = -pnl_pct
                        records[i]["outcome"] = round(pnl_pct, 4)
                        records[i]["exit_px"] = exit_px
                    with open(log_path, "w") as f:
                        json.dump(records, f, indent=2)
                    return
        except Exception as e:
            self.lg.warning(f"Alignment backfill error: {e}")

    def _read_whale_signal(self) -> dict:
        """
        Read whale_signal.json safely.
        Returns None if file missing, stale, or invalid.
        Never raises.
        """
        if not self.c.whale_enabled:
            return None
        try:
            if not os.path.exists(self.c.whale_signal_file):
                return None
            with open(self.c.whale_signal_file) as f:
                sig = json.load(f)
            if not sig.get("valid", False):
                return None
            age_ms = int(time.time() * 1000) - sig.get("timestamp", 0)
            max_age_ms = self.c.whale_signal_max_age_minutes * 60 * 1000
            if age_ms > max_age_ms:
                self.lg.debug(f"Whale signal stale ({age_ms / 60000:.1f}min old)")
                return None
            return sig
        except Exception as e:
            self.lg.debug(f"Whale signal read error: {e}")
            return None

    def _read_inflow_short_signal(self) -> Optional[dict]:
        """Read inflow_short_signal.json (EV1 supplementary). None if disabled/stale/missing."""
        if not self.c.inflow_short_enabled:
            return None
        try:
            path = self.c.inflow_short_signal_file
            p = Path(path)
            if not p.is_absolute():
                root = Path(__file__).resolve().parent.parent
                cand = root / path
                path = str(cand if cand.exists() else p)
            if not os.path.exists(path):
                return None
            with open(path, encoding="utf-8") as f:
                sig = json.load(f)
            ts = int(sig.get("timestamp", 0))
            age_ms = int(time.time() * 1000) - ts
            max_age_ms = self.c.inflow_short_signal_max_age_minutes * 60 * 1000
            if ts <= 0 or age_ms > max_age_ms:
                self.lg.debug("inflow_short signal stale or missing timestamp")
                return None
            return sig
        except Exception as e:
            self.lg.debug(f"inflow_short read error: {e}")
            return None

    def _apply_inflow_short_multiplier(self, trade_direction: str, base_mult: float) -> float:
        """Boost SHORT size when EV1 inflow short-bias is active (LONG unchanged)."""
        if trade_direction != "SHORT":
            return base_mult
        sig = self._read_inflow_short_signal()
        if not sig or not sig.get("valid"):
            return base_mult
        if sig.get("signal") != "SHORT_BIAS":
            return base_mult
        st = float(sig.get("strength", 0.0))
        factor = 1.0 + st * float(self.c.inflow_short_boost_max)
        return base_mult * factor

    def _read_macro_state(self) -> dict:
        """
        Read macro_state.json safely.
        Returns None if file missing, stale, or invalid.
        """
        if not self.c.macro_enabled:
            return None
        try:
            if not os.path.exists(self.c.macro_state_file):
                return None
            with open(self.c.macro_state_file) as f:
                state = json.load(f)
            if not state.get("valid", False):
                return None
            age_ms = int(time.time() * 1000) - state.get("timestamp", 0)
            max_age_ms = self.c.macro_state_max_age_minutes * 60 * 1000
            if age_ms > max_age_ms:
                self.lg.debug(f"Macro state stale ({age_ms / 60000:.1f}min old)")
                return None
            return state
        except Exception as e:
            self.lg.debug(f"Macro state read error: {e}")
            return None

    def _read_kronos_signal(self) -> dict:
        """
        Read kronos_signal.json safely.
        Returns None if file missing, stale, or invalid.
        Never raises.
        """
        if not self.c.kronos_enabled:
            return None
        try:
            if not os.path.exists(self.c.kronos_signal_file):
                return None
            with open(self.c.kronos_signal_file) as f:
                sig = json.load(f)
            if not sig.get("valid", False):
                return None
            age_ms = int(time.time() * 1000) - sig.get("timestamp", 0)
            max_age_ms = self.c.kronos_signal_max_age_minutes * 60 * 1000
            if age_ms > max_age_ms:
                self.lg.debug(f"Kronos signal stale ({age_ms / 60000:.1f}min old)")
                return None
            return sig
        except Exception as e:
            self.lg.debug(f"Kronos signal read error: {e}")
            return None

    def _read_contrarian_signal(self) -> dict:
        """
        Read kronos_contrarian_signal.json safely.
        Returns None if file missing, stale, or invalid.
        """
        if not self.c.contrarian_enabled:
            return None
        try:
            if not os.path.exists(self.c.contrarian_signal_file):
                return None
            with open(self.c.contrarian_signal_file) as f:
                sig = json.load(f)
            if not sig.get("valid", False):
                return None
            age_ms = int(time.time() * 1000) - sig.get("timestamp", 0)
            max_age_ms = self.c.contrarian_signal_max_age_minutes * 60 * 1000
            if age_ms > max_age_ms:
                self.lg.debug(f"Contrarian signal stale ({age_ms / 60000:.1f}min old)")
                return None
            direction = sig.get("contrarian_direction")
            if direction not in ("LONG", "SHORT"):
                return None
            return sig
        except Exception as e:
            self.lg.debug(f"Contrarian signal read error: {e}")
            return None

    def _compute_whale_multiplier(
        self, trade_direction: str, whale_sig: dict, macro_state: dict
    ) -> float:
        """
        Compute position size multiplier [0.5 to 1.5].
        1.0 = baseline (no whale/macro info).
        Returns 0.0 to skip entry entirely.
        """
        multiplier = 1.0

        # Macro override first (highest priority)
        if macro_state:
            if macro_state.get("regime") == "EXTREME":
                return 0.0  # Signal to skip entry

        # Whale alignment
        if whale_sig and whale_sig.get("direction") not in ("NONE", None):
            whale_dir = whale_sig["direction"]
            strength = float(whale_sig.get("strength", 0.0))
            if whale_dir == trade_direction:
                multiplier = 1.0 + strength * 0.5  # max 1.5x
                multiplier = min(multiplier, self.c.whale_align_multiplier_max)
            else:
                multiplier = self.c.whale_conflict_multiplier  # 0.6x

        # Macro caution (applied on top of whale adjustment)
        if macro_state and macro_state.get("caution_mode", False):
            multiplier *= self.c.macro_caution_multiplier

        return multiplier

    def _compute_kronos_multiplier(
        self, trade_direction: str, kronos_sig: dict
    ) -> float:
        """
        Compute Kronos AI multiplier [0.65 to 1.4].
        1.0 = neutral (no Kronos effect or unavailable).
        In shadow mode, always returns 1.0 (logging only, no effect).
        """
        if self.c.kronos_shadow_mode:
            return 1.0

        if kronos_sig is None:
            return 1.0

        # Use pre-computed multipliers from kronos_signal.json
        if trade_direction == "LONG":
            return float(kronos_sig.get("multiplier_long", 1.0))
        else:
            return float(kronos_sig.get("multiplier_short", 1.0))

    def _log_trade_alignment(
        self,
        strategy: str,
        direction: str,
        whale_sig: dict,
        macro_state: dict,
        multiplier: float,
        base_sz: float,
        final_sz: float,
        entry_px: float = 0.0,
        kronos_sig: dict = None,
    ) -> None:
        """
        Append one record to trade_alignment_log.json.
        Used for self-validation: did whale/kronos alignment improve EV?
        """
        try:
            record = {
                "ts": dt.datetime.utcnow().isoformat(),
                "strategy": strategy,
                "direction": direction,
                "entry_px": entry_px,
                "whale_direction": whale_sig.get("direction") if whale_sig else None,
                "whale_strength": whale_sig.get("strength") if whale_sig else None,
                "whale_wallet_count": whale_sig.get("wallet_count")
                if whale_sig
                else None,
                "whale_aligned": (
                    whale_sig is not None and whale_sig.get("direction") == direction
                ),
                "macro_regime": macro_state.get("regime") if macro_state else None,
                "caution_mode": macro_state.get("caution_mode")
                if macro_state
                else None,
                "multiplier": multiplier,
                "base_sz": base_sz,
                "final_sz": final_sz,
                "outcome": None,  # filled in by close handler on trade completion
                "exit_px": None,
                # Kronos fields
                "kronos_direction": kronos_sig.get("direction") if kronos_sig else None,
                "kronos_prob_up": kronos_sig.get("prob_up") if kronos_sig else None,
                "kronos_strength": kronos_sig.get("strength") if kronos_sig else None,
                "kronos_multiplier": self._compute_kronos_multiplier(
                    direction, kronos_sig
                ),
                "kronos_aligned": (
                    kronos_sig is not None and kronos_sig.get("direction") == direction
                ),
            }
            log_path = self.c.alignment_log_file
            existing = []
            if os.path.exists(log_path):
                with open(log_path) as f:
                    existing = json.load(f)
            existing.append(record)
            # Keep last 500 records
            if len(existing) > 500:
                existing = existing[-500:]
            with open(log_path, "w") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            self.lg.warning(f"Alignment log write error: {e}")

    def _trend_filter_pass(self, side: str, r) -> bool:
        if not self.c.trend_filter_enabled:
            return True
        trend = r.get("ocpm_trend", "RANGE")
        if side == "LONG" and trend == "DOWNTREND":
            return False
        if side == "SHORT" and trend == "UPTREND":
            return False
        return True

    def _detect_confluence(self, r):
        self._confluence_direction = None
        if not self.c.confluence_enabled:
            return
        longs = sum(
            [
                1 if r.get("ocpm_long", 0) == 1 else 0,
                1 if r.get("mr_long", 0) == 1 else 0,
                1 if r.get("rsi_swing_long", 0) == 1 else 0,
            ]
        )
        shorts = sum(
            [
                1 if r.get("ocpm_short", 0) == 1 else 0,
                1 if r.get("mr_short", 0) == 1 else 0,
                1 if r.get("rsi_swing_short", 0) == 1 else 0,
            ]
        )
        if longs >= 2:
            self._confluence_direction = "LONG"
            self.lg.info(f"CONFLUENCE detected: {longs} strategies agree LONG")
        elif shorts >= 2:
            self._confluence_direction = "SHORT"
            self.lg.info(f"CONFLUENCE detected: {shorts} strategies agree SHORT")

    def _get_confluence_multiplier(self, side: str) -> float:
        if not self.c.confluence_enabled:
            return 1.0
        if self._confluence_direction == side:
            return self.c.confluence_size_multiplier
        return 1.0

    def _check_ocpm_entry(self, r, px, bal):
        risk = self._strategy_risk_budget("OCPM", bal)
        sl_d = self.c.ocpm_atr_sl_mult * r["atr"]
        if sl_d <= 0:
            return
        available_notional = self._strategy_available_notional("OCPM", bal, px)
        sz = min(
            risk / sl_d,
            self._strategy_position_cap("OCPM", bal) / px,
            available_notional / px,
        )
        if sz * px < self.c.min_notional:
            return

        # Read whale/macro/kronos signals
        whale_sig = self._read_whale_signal()
        macro_state = self._read_macro_state()
        kronos_sig = self._read_kronos_signal()

        # Debug: log why signal is or isn't triggered
        donchian_mid = (
            r.get("ocpm_donchian_high", 0) + r.get("ocpm_donchian_low", 0)
        ) / 2
        self.lg.debug(
            f"OCPM check: trend={r['ocpm_trend']}, close={px:.0f}, donchian_mid={donchian_mid:.0f}, "
            f"rsi_prev={r.get('rsi_prev', 0):.1f}, rsi={r['rsi']:.1f}, "
            f"ocpm_long={r['ocpm_long']}, ocpm_short={r['ocpm_short']}"
        )

        if r["ocpm_long"] == 1:
            if self.c.ocpm_hard_regime_enabled and r.get("ocpm_hard_long_ok", 0) != 1:
                self.lg.debug("OCPM LONG skipped - hard regime filter not satisfied")
                return
            if not self._trend_filter_pass("LONG", r):
                self.lg.debug("OCPM LONG skipped - counter-trend (DOWNTREND)")
                return
            multiplier = self._compute_whale_multiplier("LONG", whale_sig, macro_state)
            multiplier = self._apply_inflow_short_multiplier("LONG", multiplier)
            if multiplier == 0.0:
                self.lg.info(f"OCPM LONG skipped - EXTREME macro regime")
                return
            kronos_mult = self._compute_kronos_multiplier("LONG", kronos_sig)
            conf_mult = self._get_confluence_multiplier("LONG")
            final_sz = sz * multiplier * kronos_mult * conf_mult
            final_sz = max(final_sz, sz * 0.25)  # Floor: never below 25% of base
            if final_sz * px < self.c.min_notional:
                return
            self.lg.info(
                f"OCPM LONG SIGNAL @ {px:.2f} | whale={multiplier:.2f} kronos={kronos_mult:.2f} conf={conf_mult:.2f} | sz={sz:.4f}→{final_sz:.4f}"
            )
            if self._open_strat(self.ocpm, "LONG", final_sz, px, px - sl_d):
                self._log_trade_alignment(
                    "OCPM",
                    "LONG",
                    whale_sig,
                    macro_state,
                    multiplier,
                    sz,
                    final_sz,
                    px,
                    kronos_sig,
                )
        elif r["ocpm_short"] == 1:
            if self.c.ocpm_hard_regime_enabled and r.get("ocpm_hard_short_ok", 0) != 1:
                self.lg.debug("OCPM SHORT skipped - hard regime filter not satisfied")
                return
            if not self._trend_filter_pass("SHORT", r):
                self.lg.debug("OCPM SHORT skipped - counter-trend (UPTREND)")
                return
            multiplier = self._compute_whale_multiplier("SHORT", whale_sig, macro_state)
            multiplier = self._apply_inflow_short_multiplier("SHORT", multiplier)
            if multiplier == 0.0:
                self.lg.info(f"OCPM SHORT skipped - EXTREME macro regime")
                return
            kronos_mult = self._compute_kronos_multiplier("SHORT", kronos_sig)
            conf_mult = self._get_confluence_multiplier("SHORT")
            final_sz = sz * multiplier * kronos_mult * conf_mult
            final_sz = max(final_sz, sz * 0.25)  # Floor: never below 25% of base
            if final_sz * px < self.c.min_notional:
                return
            self.lg.info(
                f"OCPM SHORT SIGNAL @ {px:.2f} | whale={multiplier:.2f} kronos={kronos_mult:.2f} conf={conf_mult:.2f} | sz={sz:.4f}→{final_sz:.4f}"
            )
            if self._open_strat(self.ocpm, "SHORT", final_sz, px, px + sl_d):
                self._log_trade_alignment(
                    "OCPM",
                    "SHORT",
                    whale_sig,
                    macro_state,
                    multiplier,
                    sz,
                    final_sz,
                    px,
                    kronos_sig,
                )

    def _check_mr_entry(self, r, px, bal):
        risk = self._strategy_risk_budget("RangeMR", bal)
        sl_d = self.c.mr_atr_sl_mult * r["atr"]
        if sl_d <= 0:
            return
        available_notional = self._strategy_available_notional("RangeMR", bal, px)
        sz = min(
            risk / sl_d,
            self._strategy_position_cap("RangeMR", bal) / px,
            available_notional / px,
        )
        if sz * px < self.c.min_notional:
            return

        # Read whale/macro/kronos signals
        whale_sig = self._read_whale_signal()
        macro_state = self._read_macro_state()
        kronos_sig = self._read_kronos_signal()

        if r["mr_long"] == 1:
            if not self._trend_filter_pass("LONG", r):
                self.lg.debug("MR LONG skipped - counter-trend (DOWNTREND)")
                return
            multiplier = self._compute_whale_multiplier("LONG", whale_sig, macro_state)
            multiplier = self._apply_inflow_short_multiplier("LONG", multiplier)
            if multiplier == 0.0:
                self.lg.info(f"MR LONG skipped - EXTREME macro regime")
                return
            kronos_mult = self._compute_kronos_multiplier("LONG", kronos_sig)
            conf_mult = self._get_confluence_multiplier("LONG")
            final_sz = sz * multiplier * kronos_mult * conf_mult
            final_sz = max(final_sz, sz * 0.25)  # Floor: never below 25% of base
            if final_sz * px < self.c.min_notional:
                return
            self.lg.info(
                f"MR LONG SIGNAL @ {px:.2f} | whale={multiplier:.2f} kronos={kronos_mult:.2f} conf={conf_mult:.2f} | sz={sz:.4f}→{final_sz:.4f}"
            )
            if self._open_strat(self.mr, "LONG", final_sz, px, px - sl_d):
                self._log_trade_alignment(
                    "MR",
                    "LONG",
                    whale_sig,
                    macro_state,
                    multiplier,
                    sz,
                    final_sz,
                    px,
                    kronos_sig,
                )
        elif r["mr_short"] == 1:
            if not self._trend_filter_pass("SHORT", r):
                self.lg.debug("MR SHORT skipped - counter-trend (UPTREND)")
                return
            multiplier = self._compute_whale_multiplier("SHORT", whale_sig, macro_state)
            multiplier = self._apply_inflow_short_multiplier("SHORT", multiplier)
            if multiplier == 0.0:
                self.lg.info(f"MR SHORT skipped - EXTREME macro regime")
                return
            kronos_mult = self._compute_kronos_multiplier("SHORT", kronos_sig)
            conf_mult = self._get_confluence_multiplier("SHORT")
            final_sz = sz * multiplier * kronos_mult * conf_mult
            final_sz = max(final_sz, sz * 0.25)  # Floor: never below 25% of base
            if final_sz * px < self.c.min_notional:
                return
            self.lg.info(
                f"MR SHORT SIGNAL @ {px:.2f} | whale={multiplier:.2f} kronos={kronos_mult:.2f} conf={conf_mult:.2f} | sz={sz:.4f}→{final_sz:.4f}"
            )
            if self._open_strat(self.mr, "SHORT", final_sz, px, px + sl_d):
                self._log_trade_alignment(
                    "MR",
                    "SHORT",
                    whale_sig,
                    macro_state,
                    multiplier,
                    sz,
                    final_sz,
                    px,
                    kronos_sig,
                )

    def _check_contrarian_entry(self, r, px, bal):
        sig = self._read_contrarian_signal()
        if sig is None:
            return
        signal_ts = int(sig.get("timestamp", 0))
        if self._current_eval_bar_ts > 0 and signal_ts < self._current_eval_bar_ts:
            self.lg.debug("Contrarian skipped - signal predates latest closed 4h bar")
            return
        if signal_ts > 0 and signal_ts <= self.contrarian.last_signal_ts:
            self.lg.debug("Contrarian skipped - signal already consumed")
            return

        # Kronos Edge Filter: only enter when contrarian edge is statistically strongest
        # Real Kronos accuracy drops to ~46% when RSI>55 & UPTREND => contrarian WR ~54%
        if getattr(self.c, "contrarian_edge_filter_enabled", False):
            rsi_val = r.get("rsi", 0)
            trend = r.get("ocpm_trend", "")
            if not (rsi_val > 55 and trend == "UPTREND"):
                self.lg.debug(
                    f"Contrarian skipped - edge filter: RSI={rsi_val:.1f}, trend={trend}"
                )
                return

        if self.c.contrarian_vol_filter_enabled:
            vol_pct = r.get("vol_pct")
            if pd.isna(vol_pct):
                self.lg.debug("Contrarian skipped - volatility percentile unavailable")
                return
            if (
                vol_pct < self.c.contrarian_min_vol_pct
                or vol_pct > self.c.contrarian_max_vol_pct
            ):
                self.lg.debug(
                    "Contrarian skipped - volatility percentile %.1f outside %.1f-%.1f"
                    % (
                        vol_pct,
                        self.c.contrarian_min_vol_pct,
                        self.c.contrarian_max_vol_pct,
                    )
                )
                return

        sl_d = self.c.contrarian_sl_atr_mult * r["atr"]
        tp_d = self.c.contrarian_tp_atr_mult * r["atr"]
        if sl_d <= 0 or tp_d <= 0 or np.isnan(sl_d) or np.isnan(tp_d):
            return

        risk = self._strategy_risk_budget("Contrarian", bal)
        available_notional = self._strategy_available_notional("Contrarian", bal, px)
        if available_notional <= 0:
            return

        sz = min(
            risk / sl_d,
            self._strategy_position_cap("Contrarian", bal) / px,
            available_notional / px,
        )
        if sz * px < self.c.min_notional:
            return

        side = sig["contrarian_direction"]
        stop = px - sl_d if side == "LONG" else px + sl_d
        tp = px + tp_d if side == "LONG" else px - tp_d
        # Kronos multiplier (optional)
        kronos_mult = 1.0
        if getattr(self.c, "contrarian_use_kronos_multiplier", True):
            kronos_sig = self._read_kronos_signal()
            kronos_mult = self._compute_kronos_multiplier(side, kronos_sig)
        final_sz = sz * kronos_mult
        self.lg.info(
            f"Contrarian {side} SIGNAL @ {px:.2f} | kronos={sig.get('kronos_direction')} "
            f"-> contra={side} | sz={sz:.4f} x mult={kronos_mult:.2f} = {final_sz:.4f} SL={stop:.2f} TP={tp:.2f}"
        )
        if self._open_strat(self.contrarian, side, final_sz, px, stop, tp=tp):
            self._log_trade_alignment(
                "Contrarian", side, None, None, kronos_mult, sz, final_sz, px, None
            )
            if signal_ts > 0:
                self.contrarian.last_signal_ts = signal_ts

    def _open_strat(self, s, side, sz, px, stop, tp=0.0):
        actual_sz = round_order_size(sz, self.hl.get_size_decimals(self.c.symbol))
        self.lg.info(
            f"[{s.name}] OPENING {side} {actual_sz:.4f} @ {px:.2f} SL: {stop:.2f}"
        )
        order_side = "buy" if side == "LONG" else "sell"
        res = self.hl.place_order(self.c.symbol, order_side, actual_sz, price=px)
        if res:
            s.in_pos = True
            s.side = side
            s.size = actual_sz
            s.entry_px = px
            s.stop = stop
            s.tp = tp
            s.entry_bar = self.current_bar
            s.entry_ts = str(dt.datetime.now())
            return True
        else:
            self.lg.error(f"[{s.name}] Order failed")
            return False

    def _sync_positions(self):
        target_long = 0.0
        target_short = 0.0
        if self.ocpm.in_pos:
            if self.ocpm.side == "LONG":
                target_long += self.ocpm.size
            else:
                target_short += self.ocpm.size
        if self.mr.in_pos:
            if self.mr.side == "LONG":
                target_long += self.mr.size
            else:
                target_short += self.mr.size
        if self.rsi_swing.in_pos:
            if self.rsi_swing.side == "LONG":
                target_long += self.rsi_swing.size
            else:
                target_short += self.rsi_swing.size
        if self.contrarian.in_pos:
            if self.contrarian.side == "LONG":
                target_long += self.contrarian.size
            else:
                target_short += self.contrarian.size

        # Note: This is a simplified sync. In a real netting account,
        # if we have Long OCPM and Short MR, they net out.
        # The bot executes deltas. The logic above assumes we execute
        # the entry/exit orders immediately, so the exchange should match.
        # This function is mainly for logging/warning if drift occurs.
        pos = self.hl.get_position(self.c.symbol)
        if pos:
            net_sz = pos["size"] if pos["side"] == "LONG" else -pos["size"]
            target_net = target_long - target_short
            if abs(net_sz - target_net) > 0.0001:
                self.lg.warning(
                    f"Position Drift! Exchange: {net_sz}, Target: {target_net}"
                )

    def run_loop(self):
        self.lg.info("Starting Unified Live Loop...")
        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                self.lg.info("Stopped by user")
                break
            except Exception as e:
                self.lg.error(f"Loop error: {e}", exc_info=True)
            time.sleep(self.c.check_interval)


def setup_logging(c, debug=False):
    Path(c.log_dir).mkdir(exist_ok=True)
    lg = logging.getLogger("UnifiedLive")
    lg.setLevel(logging.DEBUG)
    lg.handlers.clear()
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(
        f"{c.log_dir}/unified_live_{dt.datetime.now():%Y%m%d_%H%M%S}.log"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if debug else logging.INFO)
    ch.setFormatter(fmt)
    lg.addHandler(fh)
    lg.addHandler(ch)
    return lg


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument("--mode", choices=["live", "paper"], default="live")
    pa.add_argument("--interval", type=int, default=60)
    pa.add_argument("--debug", action="store_true")
    args = pa.parse_args()

    c = Config()
    c.check_interval = args.interval
    lg = setup_logging(c, args.debug)

    lg.info(f"Qwen Unified Trader ({args.mode})")
    lg.info(f"Wallet: {c.wallet_address}")

    engine = UnifiedEngine(c, lg)
    if args.mode == "live":
        lg.warning("REAL MONEY TRADING - Be careful!")
        engine.run_loop()
    else:
        lg.info("Paper mode - logging signals only")
        # Simplified paper loop logic would go here
        # For now, just run live but orders are dry run if not authed
        engine.run_loop()


if __name__ == "__main__":
    main()
