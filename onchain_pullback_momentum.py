# -*- coding: utf-8 -*-
"""
======================================================================
  BTC/USDT On-Chain Pullback Momentum - Hyperliquid Edition
  ===========================================================
  戦略: EMA 21/55 プルバック + RSIフィルター + 双方向対応
  -----------------------------------------------------------
  プロ目線の改善点:
    - ゴールデンクロス待たず EMA 21/55 でトレンド判定
    - プルバック（押し目・戻り売り）でエントリー → 損益比最大化
    - RSI 50ラインで「押し目終了」「戻り終了」を確認
    - ATR トレーリングストップで利益を伸ばす
    - 双方向（ロング・ショート）対応 → 弱含み相場でも利益

  Modes: --mode backtest | paper | live
======================================================================
"""

import os, sys, json, time, logging, argparse
import datetime as dt
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
import numpy as np
import pandas as pd

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


# ==================================================================
# CONFIGURATION
# ==================================================================

@dataclass
class TradingConfig:
    # Exchange
    exchange_id: str = "hyperliquid"
    symbol: str = "BTC"
    timeframe: str = "4h"
    use_testnet: bool = False
    
    # API Credentials
    wallet_address: str = field(default_factory=lambda: os.getenv("HL_WALLET_ADDRESS", ""))
    private_key: str = field(default_factory=lambda: os.getenv("HL_PRIVATE_KEY", ""))
    
    # Data
    lookback_days: int = 365
    data_csv: str = "btc_usdt_4h_ocpm.csv"
    
    # Strategy: EMA Pullback (Improved v3)
    ema_fast: int = 21
    ema_slow: int = 55
    ema_slope_period: int = 10
    
    # RSI Filter
    rsi_period: int = 14
    rsi_pullback_long: float = 48.0   # ロング: RSIが48以下まで低下
    rsi_pullback_short: float = 52.0  # ショート: RSIが52以上まで上昇
    rsi_overheat: float = 70.0
    rsi_oversold_extreme: float = 25.0
    
    # ADX Filter
    adx_period: int = 14
    min_adx: float = 15.0             # ADX15以上（緩和）
    
    # ATR / Risk
    atr_period: int = 14
    atr_sl_mult: float = 3.0          # ストップロス = ATR × 3.0
    atr_tp_mult: float = 6.0          # 利確目標 = ATR × 6.0（損益比 1:2）
    risk_pct: float = 0.015
    max_hold_bars: int = 20
    
    # Safety
    initial_cash: float = 100.0
    commission_pct: float = 0.0005
    max_position_pct: float = 0.40
    max_consecutive_losses: int = 5
    cooldown_bars: int = 2
    drawdown_halt_pct: float = 0.15
    
    # Order
    order_type: str = "market"
    slippage_pct: float = 0.001
    min_notional: float = 10.0
    
    # Logging
    log_dir: str = "logs"
    state_file: str = "trade_state_ocpm.json"


# ==================================================================
# HYPERLIQUID CLIENT (reuse from force_run_hl.py)
# ==================================================================

class HyperliquidClient:
    """Unified client for Hyperliquid Info and Exchange APIs (SDK v0.22)"""
    
    def __init__(self, config: TradingConfig, logger):
        self.config = config
        self.logger = logger
        self.testnet = config.use_testnet
        
        try:
            from eth_account import Account
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils.signing import OrderType
            
            self.OrderType = OrderType
            self.info = Info()
            self.logger.info(f"Hyperliquid Info API initialized ({'Testnet' if self.testnet else 'Mainnet'})")
            
            if config.wallet_address and config.private_key:
                account = Account.from_key(config.private_key)
                base_url = "https://api.hyperliquid.testnet" if self.testnet else "https://api.hyperliquid.xyz"
                self.exchange = Exchange(account, base_url=base_url, account_address=config.wallet_address)
                self.authenticated = True
            else:
                self.exchange = None
                self.authenticated = False
                self.logger.warning("No wallet credentials - Exchange API disabled (read-only mode)")
                
        except ImportError as e:
            self.logger.error(f"Failed to import hyperliquid packages: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Hyperliquid client: {e}")
            raise
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        try:
            mids = self.info.all_mids()
            if mids and symbol in mids:
                return float(mids[symbol])
            return None
        except Exception as e:
            self.logger.error(f"Error fetching price for {symbol}: {e}")
            return None
    
    def get_balance(self) -> dict:
        if not self.authenticated or not self.exchange:
            return {"total": 0.0, "available": 0.0}
        try:
            user_state = self.info.user_state(self.config.wallet_address)
            if user_state and 'marginSummary' in user_state:
                margin = user_state['marginSummary']
                total = float(margin.get('accountValue', 0.0))
                available = float(user_state.get('withdrawable', 0.0))
                return {"total": total, "available": available}
            return {"total": 0.0, "available": 0.0}
        except Exception as e:
            self.logger.error(f"Error fetching balance: {e}")
            return {"total": 0.0, "available": 0.0}
    
    def get_open_positions(self) -> list:
        if not self.authenticated or not self.exchange:
            return []
        try:
            user_state = self.info.user_state(self.config.wallet_address)
            if user_state and 'assetPositions' in user_state:
                positions = []
                for pos in user_state['assetPositions']:
                    p = pos.get('position', {})
                    szi = float(p.get('szi', 0))
                    if szi != 0:
                        positions.append({
                            'symbol': p.get('coin', ''),
                            'side': 'LONG' if szi > 0 else 'SHORT',
                            'size': abs(szi),
                            'entry_px': float(p.get('entryPx', 0)) if p.get('entryPx') else 0.0,
                            'unrealized_pnl': float(p.get('unrealizedPnl', 0)) if p.get('unrealizedPnl') else 0.0,
                        })
                return positions
            return []
        except Exception as e:
            self.logger.error(f"Error fetching positions: {e}")
            return []
    
    def place_order(self, symbol: str, side: str, size: float, 
                   price: Optional[float] = None, slippage_pct: float = 0.001,
                   reduce_only: bool = False) -> Optional[dict]:
        if not self.authenticated or not self.exchange:
            self.logger.error("Exchange API not authenticated")
            return None
        
        try:
            is_buy = side == "buy"
            
            if price is None:
                current_px = self.get_current_price(symbol)
                if current_px:
                    price = current_px * (1 + slippage_pct) if is_buy else current_px * (1 - slippage_pct)
                else:
                    self.logger.error("Cannot get price for market order")
                    return None
            
            # SDK v0.22: Use market order type
            order_type = self.OrderType(market={"slippage": slippage_pct})
            
            order_result = self.exchange.order(
                name=symbol,
                is_buy=is_buy,
                sz=size,
                limit_px=price,
                order_type=order_type,
                reduce_only=reduce_only,
            )
            
            if order_result:
                self.logger.info(f"Order placed: {side.upper()} {size} {symbol} @ ${price:.2f}")
                return order_result
            else:
                self.logger.error(f"Order failed: {order_result}")
                return None
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            return None


# ==================================================================
# LOGGING
# ==================================================================

def setup_logging(c, debug=False):
    Path(c.log_dir).mkdir(exist_ok=True)
    lg = logging.getLogger("OCPM_HL")
    lg.setLevel(logging.DEBUG); lg.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(f"{c.log_dir}/ocpm_hl_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
    fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)
    ch = logging.StreamHandler(); ch.setLevel(logging.DEBUG if debug else logging.INFO); ch.setFormatter(fmt)
    lg.addHandler(fh); lg.addHandler(ch)
    return lg


# ==================================================================
# DATA LAYER
# ==================================================================

def fetch_ohlcv(c, lg):
    """Fetch OHLCV data - uses ccxt/Binance for backtest"""
    if os.path.exists(c.data_csv):
        try:
            df = pd.read_csv(c.data_csv, parse_dates=["datetime"], index_col="datetime").sort_index()
            if len(df) > 0:
                lg.info(f"CSV cache: {c.data_csv} ({len(df)} bars)")
                return df
        except Exception as e:
            lg.warning(f"CSV read error: {e}")
    
    try:
        import ccxt
        lg.info(f"Fetching BTC USDT {c.timeframe} from Binance ({c.lookback_days} days)...")
        ex = ccxt.binance({"enableRateLimit": True})
        since = ex.parse8601((dt.datetime.utcnow()-dt.timedelta(days=c.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        rows = []
        while True:
            b = ex.fetch_ohlcv("BTC/USDT", c.timeframe, since=since, limit=1000)
            if not b: break
            rows.extend(b); since = b[-1][0]+1
            if len(b) < 1000: break
        if not rows:
            raise ValueError("No data available")
        df = pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("datetime", inplace=True)
        df = df[["open","high","low","close","volume"]].astype(float)
        df.to_csv(c.data_csv); lg.info(f"Saved {len(df)} bars")
        return df.sort_index()
    except Exception as e:
        lg.error(f"Data fetch failed: {e}")
        raise


# ==================================================================
# INDICATOR ENGINE
# ==================================================================

class Indicators:
    """On-Chain Pullback Momentum 専用インジケーター v2"""
    
    def __init__(self, c): self.c = c
    
    def compute(self, df):
        df = df.copy(); c = self.c
        
        # EMA 21/55
        df["ema_fast"] = df["close"].ewm(span=c.ema_fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=c.ema_slow, adjust=False).mean()
        
        # EMA Slope (fast EMA の傾き)
        df["ema_fast_slope"] = df["ema_fast"].pct_change(c.ema_slope_period)
        
        # ADX (Average Directional Index)
        plus_dm = df["high"].diff()
        minus_dm = -df["low"].diff()
        plus_dm = plus_dm.clip(lower=0).where(plus_dm > minus_dm, 0)
        minus_dm = minus_dm.clip(lower=0).where(minus_dm > plus_dm, 0)
        atr_raw = pd.concat([df["high"]-df["low"],
                             (df["high"]-df["close"].shift(1)).abs(),
                             (df["low"]-df["close"].shift(1)).abs()], axis=1).max(axis=1)
        atr_smooth = atr_raw.ewm(alpha=1/c.atr_period, min_periods=c.atr_period).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/c.adx_period, min_periods=c.adx_period).mean() / atr_smooth)
        minus_di = 100 * (minus_dm.ewm(alpha=1/c.adx_period, min_periods=c.adx_period).mean() / atr_smooth)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        df["adx"] = dx.ewm(alpha=1/c.adx_period, min_periods=c.adx_period).mean()
        
        # トレンド判定: EMA + slope（ADXはエントリー条件でのみ使用）
        df["trend"] = "RANGE"
        uptrend_mask = (
            (df["close"] > df["ema_slow"]) &
            (df["ema_fast"] > df["ema_slow"]) &
            (df["ema_fast_slope"] > 0)
        )
        downtrend_mask = (
            (df["close"] < df["ema_slow"]) &
            (df["ema_fast"] < df["ema_slow"]) &
            (df["ema_fast_slope"] < 0)
        )
        df.loc[uptrend_mask, "trend"] = "UPTREND"
        df.loc[downtrend_mask, "trend"] = "DOWNTREND"
        
        # RSI
        delta = df["close"].diff()
        gain = delta.clip(lower=0).ewm(alpha=1/c.rsi_period, adjust=False).mean()
        loss = (-delta).clip(lower=0).ewm(alpha=1/c.rsi_period, adjust=False).mean()
        df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        
        # RSI の前足との変化
        df["rsi_prev"] = df["rsi"].shift(1)
        df["rsi_prev2"] = df["rsi"].shift(2)  # 2足前も確認（より確実な転換）
        
        # ATR
        df["atr"] = atr_smooth
        
        # ========================================
        # エントリーシグナル（双方向 v2）
        # ========================================
        
        # ロング: UPTREND + RSIが48以下まで低下 + RSIが上向き転換
        df["long_entry"] = (
            (df["trend"] == "UPTREND") &
            (df["rsi_prev"] <= c.rsi_pullback_long) &
            (df["rsi"] > df["rsi_prev"]) &
            (df["rsi"] < 55)
        ).astype(int)
        
        # ショート: DOWNTREND + RSIが52以上まで上昇 + RSIが下向き転換
        df["short_entry"] = (
            (df["trend"] == "DOWNTREND") &
            (df["rsi_prev"] >= c.rsi_pullback_short) &
            (df["rsi"] < df["rsi_prev"]) &
            (df["rsi"] > 45)
        ).astype(int)
        
        # イグジットシグナル
        df["long_exit_rsi"] = (df["rsi"] > c.rsi_overheat).astype(int)
        df["short_exit_rsi"] = (df["rsi"] < (100 - c.rsi_overheat)).astype(int)
        
        # 緊急イグジット
        df["long_emergency_exit"] = (df["rsi"] < c.rsi_oversold_extreme).astype(int)
        df["short_emergency_exit"] = (df["rsi"] > (100 - c.rsi_oversold_extreme)).astype(int)
        
        return df


# ==================================================================
# STATE & TRADE
# ==================================================================

@dataclass
class State:
    in_pos: bool = False
    side: str = ""
    entry_px: float = 0.0
    entry_ts: str = ""
    entry_bar: int = 0
    size: float = 0.0
    stop: float = 0.0
    c_loss: int = 0
    cool_bar: int = 0
    peak_eq: float = 0.0
    
    def save(self, p):
        with open(p,"w") as f: json.dump(asdict(self),f,indent=2)
    @classmethod
    def load(cls, p):
        if os.path.exists(p):
            with open(p) as f:
                d=json.load(f)
                return cls(**{k:v for k,v in d.items() if k in cls.__dataclass_fields__})
        return cls()


@dataclass
class Trade:
    t_in:str; t_out:str; side:str; p_in:float; p_out:float
    sz:float; pnl:float; pnl_pct:float; reason:str; trend:str; bars:int=0


# ==================================================================
# BACKTEST ENGINE
# ==================================================================

class Backtest:
    def __init__(self, c, lg):
        self.c=c; self.lg=lg; self.trades=[]; self.eq=[]

    def _pnl(self, side, entry, exit_px, size, comm):
        """手数料込みPnL計算"""
        notional = size * exit_px
        comm_cost = notional * comm
        if side == "LONG":
            return (exit_px - entry) * size - comm_cost
        else:
            return (entry - exit_px) * size - comm_cost

    def run(self, df):
        cash = self.c.initial_cash; s = State(); s.peak_eq = cash
        cm = self.c.commission_pct

        for i in range(len(df)):
            r = df.iloc[i]; ts = str(df.index[i])
            px, hi, lo, atr = r["close"], r["high"], r["low"], r["atr"]
            trend = r["trend"]

            # 資産計算
            if s.in_pos:
                if s.side == "LONG":
                    pv = s.size * px
                else:
                    pv = s.size * (2 * s.entry_px - px)
                equity = cash + pv
            else:
                equity = cash

            s.peak_eq = max(s.peak_eq, equity)
            dd = (s.peak_eq - equity) / s.peak_eq if s.peak_eq > 0 else 0
            self.eq.append(equity)

            # ドローダウン停止
            if dd >= self.c.drawdown_halt_pct: continue
            if i < s.cool_bar: continue

            # ============================
            # IN POSITION
            # ============================
            if s.in_pos:
                held = i - s.entry_bar
                
                # 時間ストップ
                if held >= self.c.max_hold_bars:
                    pnl = self._pnl(s.side, s.entry_px, px, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,s.side,s.entry_px,px,s.size,pnl,(px/s.entry_px-1)*100*(1 if s.side=="LONG" else -1),"TIME_EXIT",trend,held))
                    self._close(s,pnl,i); continue

                # ATR トレーリングストップの更新
                if atr and atr > 0:
                    if s.side == "LONG":
                        new_stop = px - (self.c.atr_sl_mult * atr)
                        if new_stop > s.stop:
                            s.stop = new_stop
                        if lo <= s.stop:
                            pnl = self._pnl("LONG", s.entry_px, s.stop, s.size, cm)
                            cash += s.size * s.entry_px + pnl
                            self.trades.append(Trade(s.entry_ts,ts,"LONG",s.entry_px,s.stop,s.size,pnl,(s.stop/s.entry_px-1)*100,"TRAILING_STOP",trend,held))
                            self._close(s,pnl,i); continue
                    else:
                        new_stop = px + (self.c.atr_sl_mult * atr)
                        if new_stop < s.stop:
                            s.stop = new_stop
                        if hi >= s.stop:
                            pnl = self._pnl("SHORT", s.entry_px, s.stop, s.size, cm)
                            cash += s.size * s.entry_px + pnl
                            self.trades.append(Trade(s.entry_ts,ts,"SHORT",s.entry_px,s.stop,s.size,pnl,(s.entry_px/s.stop-1)*100,"TRAILING_STOP",trend,held))
                            self._close(s,pnl,i); continue

                # ATR 利確目標（TP）
                if atr and atr > 0:
                    if s.side == "LONG":
                        tp_price = s.entry_px + (self.c.atr_tp_mult * atr)
                        if hi >= tp_price:
                            pnl = self._pnl("LONG", s.entry_px, tp_price, s.size, cm)
                            cash += s.size * s.entry_px + pnl
                            self.trades.append(Trade(s.entry_ts,ts,"LONG",s.entry_px,tp_price,s.size,pnl,(tp_price/s.entry_px-1)*100,"ATR_TP",trend,held))
                            self._close(s,pnl,i); continue
                    else:
                        tp_price = s.entry_px - (self.c.atr_tp_mult * atr)
                        if lo <= tp_price:
                            pnl = self._pnl("SHORT", s.entry_px, tp_price, s.size, cm)
                            cash += s.size * s.entry_px + pnl
                            self.trades.append(Trade(s.entry_ts,ts,"SHORT",s.entry_px,tp_price,s.size,pnl,(s.entry_px/tp_price-1)*100,"ATR_TP",trend,held))
                            self._close(s,pnl,i); continue

                # RSI イグジット
                if s.side == "LONG" and r["long_exit_rsi"] == 1:
                    pnl = self._pnl("LONG", s.entry_px, px, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"LONG",s.entry_px,px,s.size,pnl,(px/s.entry_px-1)*100,"RSI_OVERHEAT",trend,held))
                    self._close(s,pnl,i); continue

                if s.side == "SHORT" and r["short_exit_rsi"] == 1:
                    pnl = self._pnl("SHORT", s.entry_px, px, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"SHORT",s.entry_px,px,s.size,pnl,(s.entry_px/px-1)*100,"RSI_OVERHEAT",trend,held))
                    self._close(s,pnl,i); continue

                # 緊急イグジット
                if s.side == "LONG" and r["long_emergency_exit"] == 1:
                    pnl = self._pnl("LONG", s.entry_px, px, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"LONG",s.entry_px,px,s.size,pnl,(px/s.entry_px-1)*100,"EMERGENCY_EXIT",trend,held))
                    self._close(s,pnl,i); continue

                if s.side == "SHORT" and r["short_emergency_exit"] == 1:
                    pnl = self._pnl("SHORT", s.entry_px, px, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"SHORT",s.entry_px,px,s.size,pnl,(s.entry_px/px-1)*100,"EMERGENCY_EXIT",trend,held))
                    self._close(s,pnl,i); continue

                continue

            # ============================
            # NO POSITION
            # ============================
            if atr is None or atr <= 0: continue

            # ロングエントリー
            if r["long_entry"] == 1:
                sl_d = self.c.atr_sl_mult * atr
                risk = cash * self.c.risk_pct
                sz = min(risk / sl_d, (cash * self.c.max_position_pct) / px)
                
                notional = sz * px
                if notional < self.c.min_notional:
                    continue
                
                margin = sz * px * (1 + cm)
                if margin <= cash:
                    cash -= margin
                    s.in_pos=True; s.side="LONG"; s.entry_px=px; s.entry_ts=ts
                    s.entry_bar=i; s.size=sz; s.stop=px-sl_d
                    self.lg.debug(f"  LONG @{px:.2f} RSI={r['rsi']:.1f} SL={s.stop:.2f} ADX={r['adx']:.1f} [{trend}]")

            # ショートエントリー
            elif r["short_entry"] == 1:
                sl_d = self.c.atr_sl_mult * atr
                risk = cash * self.c.risk_pct
                sz = min(risk / sl_d, (cash * self.c.max_position_pct) / px)
                
                notional = sz * px
                if notional < self.c.min_notional:
                    continue
                
                margin = sz * px * (1 + cm)
                if margin <= cash:
                    cash -= margin
                    s.in_pos=True; s.side="SHORT"; s.entry_px=px; s.entry_ts=ts
                    s.entry_bar=i; s.size=sz; s.stop=px+sl_d
                    self.lg.debug(f"  SHORT @{px:.2f} RSI={r['rsi']:.1f} SL={s.stop:.2f} ADX={r['adx']:.1f} [{trend}]")

        # 最終ポジション決済
        if s.in_pos:
            lp = df.iloc[-1]["close"]
            pnl = self._pnl(s.side, s.entry_px, lp, s.size, cm)
            cash += s.size * s.entry_px + pnl
            self.trades.append(Trade(s.entry_ts,str(df.index[-1]),s.side,s.entry_px,lp,s.size,pnl,0,"EOD","",0))

        return self._metrics(cash)

    def _close(self, s, pnl, i):
        if pnl < 0:
            s.c_loss += 1
            if s.c_loss >= self.c.max_consecutive_losses:
                s.cool_bar = i + self.c.cooldown_bars
        else:
            s.c_loss = 0
        s.in_pos = False; s.size = 0.0; s.side = ""

    def _metrics(self, final):
        init=self.c.initial_cash; ret=(final-init)/init*100; n=len(self.trades)
        if n==0: return {"final_value":final,"total_return":ret,"total_trades":0,"win_rate":0,"profit_factor":0,"max_drawdown":0,"sharpe":0,"avg_win":0,"avg_loss":0,"expectancy":0,"avg_bars":0,"sl_rate":0,"rsi_rate":0,"long_trades":0,"short_trades":0,"long_wr":0,"short_wr":0}
        pnls=[t.pnl for t in self.trades]; w=[p for p in pnls if p>0]; l=[p for p in pnls if p<=0]
        gp,gl=sum(w),abs(sum(l))
        eq=np.array(self.eq); pk=np.maximum.accumulate(eq); mdd=float(((pk-eq)/pk*100).max())
        deq=eq[::6]
        sharpe = 0
        if len(deq)>1:
            dr=np.diff(deq)/deq[:-1]; rf=0.045/365
            sharpe=float((np.mean(dr)-rf)/np.std(dr)*np.sqrt(365)) if np.std(dr)>0 else 0
        longs=[t for t in self.trades if t.side=="LONG"]; shorts=[t for t in self.trades if t.side=="SHORT"]
        lw=sum(1 for t in longs if t.pnl>0); sw=sum(1 for t in shorts if t.pnl>0)
        return {"final_value":final,"total_return":ret,"total_trades":n,"win_rate":len(w)/n*100,
                "profit_factor":gp/gl if gl>0 else float("inf"),"max_drawdown":mdd,"sharpe":sharpe,
                "avg_win":np.mean(w) if w else 0,"avg_loss":np.mean(l) if l else 0,
                "expectancy":np.mean(pnls),"avg_bars":np.mean([t.bars for t in self.trades]),
                "sl_rate":sum(1 for t in self.trades if "STOP" in t.reason)/n*100,
                "rsi_rate":sum(1 for t in self.trades if "RSI" in t.reason or "ATR_TP" in t.reason)/n*100,
                "long_trades":len(longs),"short_trades":len(shorts),
                "long_wr":lw/len(longs)*100 if longs else 0,"short_wr":sw/len(shorts)*100 if shorts else 0}


# ==================================================================
# LIVE ENGINE (Hyperliquid)
# ==================================================================

class LiveEngine:
    def __init__(self, c, lg):
        self.c = c; self.lg = lg
        self.ind = Indicators(c)
        self.s = State.load(c.state_file)
        self.hl = HyperliquidClient(c, lg)

    def run_once(self):
        df = fetch_ohlcv(self.c, self.lg)
        df = self.ind.compute(df)
        r = df.iloc[-1]; atr = r["atr"]; ts = str(df.index[-1])
        trend = r["trend"]
        
        # Hyperliquidから現在価格を取得
        hl_px = self.hl.get_current_price(self.c.symbol)
        if hl_px:
            px = hl_px
        else:
            px = r["close"]
            self.lg.warning("Using close price (live price unavailable)")
        
        s = self.s

        # ============================
        # IN POSITION
        # ============================
        if s.in_pos:
            # トレーリングストップ更新
            if atr and atr > 0:
                if s.side == "LONG":
                    new_stop = px - (self.c.atr_sl_mult * atr)
                    if new_stop > s.stop:
                        s.stop = new_stop
                        s.save(self.c.state_file)
                        self.lg.info(f"Trailing SL updated: ${s.stop:.2f}")
                    
                    # ストップヒット
                    if px <= s.stop:
                        self.lg.info(f"TRAILING STOP: {s.side} @ ${px:.2f}")
                        result = self.hl.place_order(self.c.symbol, "sell", s.size, price=px, reduce_only=True)
                        if result:
                            s.in_pos = False; s.size = 0.0; s.side = ""
                            s.save(self.c.state_file)
                        return

                elif s.side == "SHORT":
                    new_stop = px + (self.c.atr_sl_mult * atr)
                    if new_stop < s.stop:
                        s.stop = new_stop
                        s.save(self.c.state_file)
                        self.lg.info(f"Trailing SL updated: ${s.stop:.2f}")
                    
                    if px >= s.stop:
                        self.lg.info(f"TRAILING STOP: {s.side} @ ${px:.2f}")
                        result = self.hl.place_order(self.c.symbol, "buy", s.size, price=px, reduce_only=True)
                        if result:
                            s.in_pos = False; s.size = 0.0; s.side = ""
                            s.save(self.c.state_file)
                        return

            # RSI イグジット
            if s.side == "LONG" and r["long_exit_rsi"] == 1:
                self.lg.info(f"RSI EXIT: LONG @ ${px:.2f} (RSI={r['rsi']:.1f})")
                result = self.hl.place_order(self.c.symbol, "sell", s.size, price=px, reduce_only=True)
                if result:
                    s.in_pos = False; s.size = 0.0; s.side = ""
                    s.save(self.c.state_file)
                return

            elif s.side == "SHORT" and r["short_exit_rsi"] == 1:
                self.lg.info(f"RSI EXIT: SHORT @ ${px:.2f} (RSI={r['rsi']:.1f})")
                result = self.hl.place_order(self.c.symbol, "buy", s.size, price=px, reduce_only=True)
                if result:
                    s.in_pos = False; s.size = 0.0; s.side = ""
                    s.save(self.c.state_file)
                return

            # 緊急イグジット
            if s.side == "LONG" and r["long_emergency_exit"] == 1:
                self.lg.info(f"EMERGENCY EXIT: LONG @ ${px:.2f}")
                result = self.hl.place_order(self.c.symbol, "sell", s.size, price=px, reduce_only=True)
                if result:
                    s.in_pos = False; s.size = 0.0; s.side = ""
                    s.save(self.c.state_file)
                return

            elif s.side == "SHORT" and r["short_emergency_exit"] == 1:
                self.lg.info(f"EMERGENCY EXIT: SHORT @ ${px:.2f}")
                result = self.hl.place_order(self.c.symbol, "buy", s.size, price=px, reduce_only=True)
                if result:
                    s.in_pos = False; s.size = 0.0; s.side = ""
                    s.save(self.c.state_file)
                return

            return

        # ============================
        # NO POSITION
        # ============================
        if atr is None or atr <= 0:
            return

        bal = self.hl.get_balance()["total"]
        if bal < 10:
            self.lg.warning(f"Balance too low: ${bal:.2f}")
            return

        # ロングエントリー
        if r["long_entry"] == 1:
            sl_d = self.c.atr_sl_mult * atr
            risk = bal * self.c.risk_pct
            sz = min(risk / sl_d, (bal * self.c.max_position_pct) / px)
            
            notional = sz * px
            if notional < self.c.min_notional:
                self.lg.warning(f"SKIP LONG: Notional ${notional:.2f} < ${self.c.min_notional}")
                return
            
            entry_px = px * (1 + self.c.slippage_pct)
            sl_px = entry_px - sl_d
            
            self.lg.info(f"LONG ENTRY @ ${entry_px:.2f}, SL=${sl_px:.2f}, RSI={r['rsi']:.1f} [{trend}] Size=${notional:.2f}")
            result = self.hl.place_order(self.c.symbol, "buy", sz, price=entry_px)
            if result:
                s.in_pos = True; s.side = "LONG"; s.entry_px = entry_px; s.entry_ts = ts
                s.size = sz; s.stop = sl_px
                s.save(self.c.state_file)

        # ショートエントリー
        elif r["short_entry"] == 1:
            sl_d = self.c.atr_sl_mult * atr
            risk = bal * self.c.risk_pct
            sz = min(risk / sl_d, (bal * self.c.max_position_pct) / px)
            
            notional = sz * px
            if notional < self.c.min_notional:
                self.lg.warning(f"SKIP SHORT: Notional ${notional:.2f} < ${self.c.min_notional}")
                return
            
            entry_px = px * (1 - self.c.slippage_pct)
            sl_px = entry_px + sl_d
            
            self.lg.info(f"SHORT ENTRY @ ${entry_px:.2f}, SL=${sl_px:.2f}, RSI={r['rsi']:.1f} [{trend}] Size=${notional:.2f}")
            result = self.hl.place_order(self.c.symbol, "sell", sz, price=entry_px)
            if result:
                s.in_pos = True; s.side = "SHORT"; s.entry_px = entry_px; s.entry_ts = ts
                s.size = sz; s.stop = sl_px
                s.save(self.c.state_file)

    def run_loop(self, interval=60):
        self.lg.info(f"Starting live loop (interval={interval}s)")
        self.lg.info(f"Exchange: {'Hyperliquid Testnet' if self.c.use_testnet else 'Hyperliquid Mainnet'}")
        
        iteration = 0
        while True:
            iteration += 1
            try:
                self.lg.info(f"--- Iteration {iteration} ---")
                self.run_once()
            except KeyboardInterrupt:
                self.lg.info("Stopped by user")
                break
            except Exception as e:
                self.lg.error(f"Error in loop: {e}", exc_info=True)

            self.lg.info(f"Sleeping {interval}s until next bar...")
            sys.stdout.flush()
            time.sleep(interval)


# ==================================================================
# REPORTING
# ==================================================================

def report(m, trades, lg):
    r=f"""
{'='*70}
  On-Chain Pullback Momentum - PERFORMANCE REPORT
{'='*70}
  Final Value    : ${m['final_value']:,.2f}
  Total Return   : {m['total_return']:+.2f}%
  Max Drawdown   : {m['max_drawdown']:.2f}%
  Sharpe (ann.)  : {m['sharpe']:.4f}
{'-'*70}
  Trades         : {m['total_trades']}
  Win Rate       : {m['win_rate']:.1f}%
  Profit Factor  : {m['profit_factor']:.2f}
  Avg Win        : ${m['avg_win']:+,.2f}
  Avg Loss       : ${m['avg_loss']:+,.2f}
  Expectancy     : ${m['expectancy']:+,.2f}
  Avg Hold       : {m['avg_bars']:.1f} bars
{'-'*70}
  RSI Exit rate  : {m['rsi_rate']:.1f}%
  Stop Loss rate : {m['sl_rate']:.1f}%
{'-'*70}
  LONG trades    : {m['long_trades']} (WR {m['long_wr']:.0f}%)
  SHORT trades   : {m['short_trades']} (WR {m['short_wr']:.0f}%)
{'='*70}"""
    
    checks=[("Return > 0%",m["total_return"]>0,f"{m['total_return']:+.2f}%"),
            ("MaxDD < 15%",m["max_drawdown"]<15,f"{m['max_drawdown']:.2f}%"),
            ("PF > 1.2",m["profit_factor"]>1.2,f"{m['profit_factor']:.2f}"),
            ("EV > $0",m["expectancy"]>0,f"${m['expectancy']:+,.2f}"),
            ("WR > 40%",m["win_rate"]>40,f"{m['win_rate']:.1f}%")]
    
    r+=f"\n\n{'='*70}\n GO CHECK\n{'='*70}"
    for nm,ok,v in checks: r+=f"\n  {'PASS' if ok else 'FAIL'} {nm}: {v}"
    p=sum(1 for _,ok,_ in checks if ok)
    r+=f"\n\n  Score: {p}/{len(checks)}"
    r+=f"\n  {'>>> GO <<<' if p==len(checks) else '>>> CONDITIONAL <<<' if p>=3 else '>>> STOP <<<' }"
    r+=f"\n{'='*70}"
    print(r); lg.info(r)
    
    if trades:
        print(f"\n{'='*105}")
        print(f"  {'Time':<20} {'Side':<6} {'Type':<15} {'Trend':<10} {'Entry':>10} {'Exit':>10} {'PnL%':>8} {'PnL$':>12} {'Bars':>5}")
        print(f"{'-'*105}")
        for t in trades:
            print(f"  {t.t_out[:16]:<20} {t.side:<6} {t.reason:<15} {t.trend:<10} {t.p_in:>10.2f} {t.p_out:>10.2f} {t.pnl_pct:>+7.2f}% ${t.pnl:>+10.2f} {t.bars:>5}")
        print(f"{'='*105}")


# ==================================================================
# MAIN
# ==================================================================

def main():
    pa=argparse.ArgumentParser()
    pa.add_argument("--mode",choices=["backtest","paper","live"],default="backtest")
    pa.add_argument("--days",type=int,default=365)
    pa.add_argument("--timeframe",type=str,default="4h")
    pa.add_argument("--testnet",action="store_true",help="Use Hyperliquid Testnet")
    pa.add_argument("--debug",action="store_true",help="Enable debug logging")
    pa.add_argument("--interval",type=int,default=60,help="Loop interval in seconds")
    args=pa.parse_args()
    
    c=TradingConfig()
    c.lookback_days = args.days
    c.timeframe = args.timeframe
    c.use_testnet = args.testnet
    
    lg=setup_logging(c, debug=args.debug)
    lg.info(f"Mode: {args.mode} | On-Chain Pullback Momentum | Days: {c.lookback_days}")
    lg.info(f"Timeframe: {c.timeframe} | Exchange: {'Testnet' if c.use_testnet else 'Mainnet'}")
    
    if args.mode=="backtest":
        lg.info("Entering BACKTEST mode")
        df=fetch_ohlcv(c,lg)
        if len(df) == 0:
            lg.error("No data available for backtest")
            return
        df=Indicators(c).compute(df)
        if len(df) == 0:
            lg.error("No data after indicators computation")
            return
        lg.info(f"Data: {df.index[0]} -> {df.index[-1]} ({len(df)} bars)")
        regimes=df["trend"].value_counts()
        lg.info(f"Trend Regimes: {dict(regimes)}")
        lg.info(f"Long signals: {df['long_entry'].sum()}, Short signals: {df['short_entry'].sum()}")
        bt=Backtest(c,lg); m=bt.run(df); report(m,bt.trades,lg)
        
    elif args.mode=="paper":
        lg.info("Entering PAPER mode (read-only, no orders)")
        lg.info("Watching signals without placing orders...")
        # Paper mode: just log signals without executing
        while True:
            try:
                df = fetch_ohlcv(c, lg)
                df = Indicators(c).compute(df)
                r = df.iloc[-1]
                hl_px = HyperliquidClient(c, lg).get_current_price(c.symbol)
                px = hl_px if hl_px else r["close"]
                lg.info(f"[PAPER] Price: ${px:.2f} | RSI: {r['rsi']:.1f} | Trend: {r['trend']} | "
                       f"Long Signal: {r['long_entry']} | Short Signal: {r['short_entry']}")
            except KeyboardInterrupt:
                lg.info("Stopped by user")
                break
            except Exception as e:
                lg.error(f"Error: {e}", exc_info=True)
            time.sleep(args.interval)
            
    elif args.mode=="live":
        lg.info("Entering LIVE mode")
        lg.warning("REAL MONEY TRADING - Be careful!")
        LiveEngine(c,lg).run_loop(interval=args.interval)
    else:
        lg.error(f"UNKNOWN MODE: {args.mode}")


if __name__ == "__main__":
    main()
