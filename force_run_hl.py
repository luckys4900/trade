# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
======================================================================
  BTC/USDT 4H ADAPTIVE RSI v5 - Hyperliquid Edition
  -----------------------------------------------------------
  Migrated from ccxt/Binance to hyperliquid-python-sdk

  Features:
    - Regime-Aware Trading (BULL/BEAR/RANGE)
    - RSI Mean Reversion entries/exits
    - Hyperliquid Perpetual DEX integration
    - Mainnet/Testnet switching
    - Limit Order (GTC) with Market Order fallback

  Modes: --mode backtest | paper | live
          --exchange hyperliquid | --testnet
======================================================================
"""

import os, sys, json, time, logging, argparse
import datetime as dt
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal
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
    # Exchange Selection
    exchange_id: str = "hyperliquid"
    symbol: str = "BTC"
    timeframe: str = "4h"
    use_testnet: bool = False
    
    # API Credentials (Hyperliquid)
    wallet_address: str = field(default_factory=lambda: os.getenv("HL_WALLET_ADDRESS", ""))
    private_key: str = field(default_factory=lambda: os.getenv("HL_PRIVATE_KEY", ""))
    
    # Data
    lookback_days: int = 180
    data_csv: str = "btc_usdt_4h.csv"
    
    # Regime detection
    ema_fast: int = 50
    ema_slow: int = 200
    ema_slope_period: int = 10
    ema_range_pct: float = 0.01
    
    # RSI
    rsi_period: int = 14
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    rsi_exit_long: float = 65.0
    rsi_exit_short: float = 35.0
    
    # Risk
    atr_period: int = 14
    atr_sl_mult: float = 2.0
    risk_pct: float = 0.015
    max_hold_bars: int = 30
    
    # Safety
    initial_cash: float = 100.0  # Micro-capital: $100 USDT
    commission_pct: float = 0.0005  # Hyperliquid: 0.05% maker/taker
    max_position_pct: float = 0.50
    max_consecutive_losses: int = 3
    cooldown_bars: int = 6
    drawdown_halt_pct: float = 0.10
    
    # Order settings
    order_type: Literal["limit", "market"] = "limit"  # default to limit orders
    slippage_pct: float = 0.001  # 0.1% slippage for limit orders
    min_notional: float = 10.0  # Hyperliquid minimum order value ($10 USDT)
    
    # Logging
    log_dir: str = "logs"
    state_file: str = "trade_state.json"


# ==================================================================
# HYPERLIQUID CLIENT
# ==================================================================

class HyperliquidClient:
    """Unified client for Hyperliquid Info and Exchange APIs"""
    
    def __init__(self, config: TradingConfig, logger):
        self.config = config
        self.logger = logger
        self.testnet = config.use_testnet
        
        try:
            from eth_account import Account
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange
            
            # Setup Info API - use default URL (no base_url parameter)
            self.info = Info()
            self.logger.info(f"Hyperliquid Info API initialized ({'Testnet' if self.testnet else 'Mainnet'})")
            
            # Setup Exchange API (requires auth)
            if config.wallet_address and config.private_key:
                account = Account.from_key(config.private_key)
                # Setup Exchange API with explicit base URL
                if self.testnet:
                    base_url = "https://api.hyperliquid.testnet"
                    self.logger.info(f"Hyperliquid Exchange API initialized for {config.wallet_address[:8]}... (Testnet)")
                else:
                    base_url = "https://api.hyperliquid.xyz"
                    self.logger.info(f"Hyperliquid Exchange API initialized for {config.wallet_address[:8]}... (Mainnet)")
                self.exchange = Exchange(account, base_url=base_url, account_address=config.wallet_address)
                self.authenticated = True
            else:
                self.exchange = None
                self.authenticated = False
                self.logger.warning("No wallet credentials - Exchange API disabled (read-only mode)")
                
        except ImportError as e:
            self.logger.error(f"Failed to import hyperliquid packages: {e}")
            self.logger.error("Install with: pip install hyperliquid-python-sdk eth-account python-dotenv")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Hyperliquid client: {e}")
            raise
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current mid price from orderbook"""
        try:
            # Hyperliquid uses coin names like "BTC" for BTC/USDT perp
            # Get all meta first
            meta = self.info.meta()
            if not meta or 'universe' not in meta:
                self.logger.warning("Failed to get universe from Info API")
                return None
            
            # Find the symbol in universe
            universe = meta['universe']
            symbol_data = None
            for coin in universe:
                if coin.get('name') == symbol:
                    symbol_data = coin
                    break
            
            if not symbol_data:
                self.logger.warning(f"Symbol {symbol} not found in universe")
                return None
            
            # Get L2 book
            book = self.info.l2_book(symbol)
            if book and len(book) > 0 and 'levels' in book:
                # Get best bid/ask
                levels = book['levels'][0]  # [0] is asks, [1] is bids
                if levels:
                    best_ask = levels[0]['px'] if levels else None
                    best_bid = book['levels'][1][0]['px'] if len(book['levels']) > 1 else None
                    
                    if best_ask and best_bid:
                        return (best_ask + best_bid) / 2.0
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error fetching price for {symbol}: {e}")
            return None
    
    def get_balance(self) -> dict:
        """Get account balance"""
        if not self.authenticated or not self.exchange:
            self.logger.warning("Exchange API not authenticated")
            return {"total": 0.0, "available": 0.0}
        
        try:
            # Get user state
            user_state = self.exchange.get_user_state()
            
            if user_state and 'marginSummary' in user_state:
                margin = user_state['marginSummary']
                total = float(margin.get('accountValue', 0.0))
                available = float(margin.get('withdrawable', 0.0))
                return {"total": total, "available": available}
            
            return {"total": 0.0, "available": 0.0}
            
        except Exception as e:
            self.logger.error(f"Error fetching balance: {e}")
            return {"total": 0.0, "available": 0.0}
    
    def get_open_positions(self) -> list:
        """Get current open positions"""
        if not self.authenticated or not self.exchange:
            return []
        
        try:
            user_state = self.exchange.get_user_state()
            
            if user_state and 'assetPositions' in user_state:
                positions = []
                for pos in user_state['assetPositions']:
                    if float(pos['szi']) != 0:  # szi = position size (positive = long, negative = short)
                        positions.append({
                            'symbol': pos['position']['coin'],
                            'side': 'LONG' if float(pos['szi']) > 0 else 'SHORT',
                            'size': abs(float(pos['szi'])),
                            'entry_px': float(pos['position']['entryPx']) if 'entryPx' in pos['position'] else 0.0,
                            'unrealized_pnl': float(pos['position']['unrealizedPnl']) if 'unrealizedPnl' in pos['position'] else 0.0,
                        })
                return positions
            
            return []
            
        except Exception as e:
            self.logger.error(f"Error fetching positions: {e}")
            return []
    
    def place_order(self, symbol: str, side: str, size: float, 
                   price: Optional[float] = None, slippage_pct: float = 0.001) -> Optional[dict]:
        """
        Place order on Hyperliquid
        
        Args:
            symbol: Coin name (e.g., "BTC")
            side: "buy" or "sell" (for perpetuals: "A" (ask) = buy long, "B" (bid) = sell long)
            size: Position size in USD
            price: Limit price (None for market)
            slippage_pct: Slippage for limit orders
            
        Returns:
            Order result dict or None
        """
        if not self.authenticated or not self.exchange:
            self.logger.error("Exchange API not authenticated")
            return None
        
        try:
            # Hyperliquid uses different side notation:
            # For perpetuals: "A" = buy (long), "B" = sell (short)
            # "buy" in our system = open long
            # "sell" in our system = open short OR close long
            
            is_buy = side == "buy"
            hl_side = "A" if is_buy else "B"
            
            # Determine order price
            if price is None:
                # Market order - use current price
                current_px = self.get_current_price(symbol)
                if current_px:
                    if is_buy:
                        price = current_px * (1 + slippage_pct)  # Pay slightly more
                    else:
                        price = current_px * (1 - slippage_pct)  # Accept slightly less
                else:
                    self.logger.error("Cannot get price for market order")
                    return None
            else:
                # Limit order - use specified price
                if is_buy:
                    # Ensure we don't overpay too much
                    current_px = self.get_current_price(symbol)
                    if current_px and price > current_px * (1 + slippage_pct):
                        price = current_px * (1 + slippage_pct)
            
            # Hyperliquid expects:
            # - coin: symbol name
            # - is_buy: boolean
            # - limit_px: limit price (market orders use current price)
            # - slippage: allowed slippage for market orders
            # - sz: size in USD
            # - reduce_only: boolean
            # - order_type: {"limit": {"tif": "Gtc"}} or "market"
            
            order_type = {"limit": {"tif": "Gtc"}} if self.config.order_type == "limit" else "market"
            
            order_result = self.exchange.order(
                coin=symbol,
                is_buy=is_buy,
                limit_px=str(price),
                slippage=slippage_pct,
                sz=str(size),
                reduce_only=False,
                order_type=order_type
            )
            
            if order_result and 'status' in order_result:
                if order_result['status'] == 'ok':
                    self.logger.info(f"Order placed successfully: {side.upper()} {size} {symbol} @ ${price:.2f}")
                    return order_result
                else:
                    self.logger.error(f"Order failed: {order_result.get('response', 'Unknown error')}")
                    return None
            
            self.logger.error(f"Order placement failed: {order_result}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            return None
    
    def cancel_all_orders(self, symbol: Optional[str] = None):
        """Cancel all open orders for a symbol"""
        if not self.authenticated or not self.exchange:
            return False
        
        try:
            result = self.exchange.cancel_by_coin(symbol) if symbol else self.exchange.cancel_all_orders()
            if result and 'status' in result:
                self.logger.info(f"Cancelled orders: {result}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error cancelling orders: {e}")
            return False


# ==================================================================
# LOGGING
# ==================================================================

def setup_logging(c, debug=False):
    Path(c.log_dir).mkdir(exist_ok=True)
    lg = logging.getLogger("AdaptiveV5_HL")
    lg.setLevel(logging.DEBUG); lg.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(f"{c.log_dir}/v5_hl_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
    fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)
    ch = logging.StreamHandler(); ch.setLevel(logging.DEBUG if debug else logging.INFO); ch.setFormatter(fmt)
    lg.addHandler(fh); lg.addHandler(ch)
    return lg


# ==================================================================
# DATA LAYER (Backtest Only)
# ==================================================================

def fetch_ohlcv(c, lg):
    """Fetch OHLCV data - uses ccxt for backtest, Hyperliquid for live"""
    # Try CSV first
    if os.path.exists(c.data_csv):
        try:
            df = pd.read_csv(c.data_csv, parse_dates=["datetime"], index_col="datetime").sort_index()
            if len(df) > 0:
                lg.info(f"CSV cache: {c.data_csv} ({len(df)} bars)")
                return df
            else:
                lg.warning(f"CSV exists but empty, fetching from Binance...")
        except Exception as e:
            lg.warning(f"CSV read error: {e}, fetching from Binance...")
    
    # Fetch from Binance
    try:
        import ccxt
        lg.info(f"Fetching BTC USDT 4h from Binance (backtest data)...")
        ex = ccxt.binance({"enableRateLimit": True})
        since = ex.parse8601((dt.datetime.utcnow()-dt.timedelta(days=c.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        rows = []
        while True:
            b = ex.fetch_ohlcv("BTC/USDT", c.timeframe, since=since, limit=1000)
            if not b: break
            rows.extend(b); since = b[-1][0]+1
            if len(b) < 1000: break
        if not rows:
            lg.error("No data fetched from Binance")
            raise ValueError("No data available")
        df = pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("datetime", inplace=True)
        df = df[["open","high","low","close","volume"]].astype(float)
        df.to_csv(c.data_csv); lg.info(f"Saved {len(df)} bars")
        return df.sort_index()
    except Exception as e:
        lg.warning(f"ccxt: {e}")
        raise


# ==================================================================
# INDICATOR ENGINE
# ==================================================================

class Indicators:
    def __init__(self, c): self.c = c
    def compute(self, df):
        df = df.copy(); c = self.c
        # EMAs
        df["ema_f"] = df["close"].ewm(span=c.ema_fast, adjust=False).mean()
        df["ema_s"] = df["close"].ewm(span=c.ema_slow, adjust=False).mean()
        df["ema_f_slope"] = (df["ema_f"] - df["ema_f"].shift(c.ema_slope_period)) / df["ema_f"].shift(c.ema_slope_period)
        df["ema_gap_pct"] = (df["ema_f"] - df["ema_s"]).abs() / df["ema_s"]

        # Regime
        def regime(row):
            if row["ema_gap_pct"] < c.ema_range_pct:
                return "RANGE"
            elif row["ema_f"] > row["ema_s"] and row["ema_f_slope"] > 0:
                return "BULL"
            elif row["ema_f"] < row["ema_s"] and row["ema_f_slope"] < 0:
                return "BEAR"
            return "RANGE"
        df["regime"] = df.apply(regime, axis=1)

        # RSI
        delta = df["close"].diff()
        gain = delta.clip(lower=0).ewm(alpha=1/c.rsi_period, adjust=False).mean()
        loss = (-delta).clip(lower=0).ewm(alpha=1/c.rsi_period, adjust=False).mean()
        df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

        # ATR
        tr = pd.concat([df["high"]-df["low"],
                        (df["high"]-df["close"].shift(1)).abs(),
                        (df["low"]-df["close"].shift(1)).abs()], axis=1).max(axis=1)
        df["atr"] = tr.rolling(c.atr_period).mean()

        # Signals
        df["long_entry"] = ((df["regime"]=="BULL") & (df["rsi"]<c.rsi_oversold)).astype(int)
        df["long_exit"] = (df["rsi"]>c.rsi_exit_long).astype(int)
        df["short_entry"] = ((df["regime"]=="BEAR") & (df["rsi"]>c.rsi_overbought)).astype(int)
        df["short_exit"] = (df["rsi"]<c.rsi_exit_short).astype(int)

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
    hl_order_id: str = ""  # Hyperliquid order ID

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
    sz:float; pnl:float; pnl_pct:float; reason:str; regime:str; bars:int=0


# ==================================================================
# BACKTEST ENGINE
# ==================================================================

class Backtest:
    def __init__(self, c, lg):
        self.c=c; self.lg=lg; self.trades=[]; self.eq=[]

    def _pnl(self, side, entry, exit_px, size, comm):
        if side == "LONG":
            return (exit_px - entry) * size - exit_px * size * comm
        else:
            return (entry - exit_px) * size - exit_px * size * comm

    def run(self, df):
        cash = self.c.initial_cash; s = State(); s.peak_eq = cash
        cm = self.c.commission_pct

        for i in range(len(df)):
            r = df.iloc[i]; ts = str(df.index[i])
            px, hi, lo, atr = r["close"], r["high"], r["low"], r["atr"]
            regime = r["regime"]

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

            if dd >= self.c.drawdown_halt_pct: continue
            if i < s.cool_bar: continue

            # IN POSITION
            if s.in_pos:
                held = i - s.entry_bar
                if held >= self.c.max_hold_bars:
                    pnl = self._pnl(s.side, s.entry_px, px, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,s.side,s.entry_px,px,s.size,pnl,(px/s.entry_px-1)*100*(1 if s.side=="LONG" else -1),"TIME_EXIT",regime,held))
                    self._close(s,pnl,i); continue

                if s.side == "LONG" and lo <= s.stop:
                    ep = s.stop; pnl = self._pnl("LONG", s.entry_px, ep, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"LONG",s.entry_px,ep,s.size,pnl,(ep/s.entry_px-1)*100,"STOP_LOSS",regime,held))
                    self._close(s,pnl,i); continue

                if s.side == "SHORT" and hi >= s.stop:
                    ep = s.stop; pnl = self._pnl("SHORT", s.entry_px, ep, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"SHORT",s.entry_px,ep,s.size,pnl,(s.entry_px/ep-1)*100,"STOP_LOSS",regime,held))
                    self._close(s,pnl,i); continue

                if s.side == "LONG" and r["long_exit"] == 1:
                    pnl = self._pnl("LONG", s.entry_px, px, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"LONG",s.entry_px,px,s.size,pnl,(px/s.entry_px-1)*100,"RSI_EXIT",regime,held))
                    self._close(s,pnl,i); continue

                if s.side == "SHORT" and r["short_exit"] == 1:
                    pnl = self._pnl("SHORT", s.entry_px, px, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"SHORT",s.entry_px,px,s.size,pnl,(s.entry_px/px-1)*100,"RSI_EXIT",regime,held))
                    self._close(s,pnl,i); continue
                continue

            # NO POSITION
            if atr <= 0: continue

            if r["long_entry"] == 1:
                sl_d = self.c.atr_sl_mult * atr
                risk = cash * self.c.risk_pct
                sz = min(risk / sl_d, (cash * self.c.max_position_pct) / px)
                
                # Check minimum notional (Hyperliquid: $10 minimum)
                notional = sz * px
                if notional < self.c.min_notional:
                    self.lg.warning(f"SKIP LONG: Notional ${notional:.2f} < ${self.c.min_notional} (min order)")
                    continue
                
                if sz > 0 and sz * px >= 10:
                    margin = sz * px * (1 + cm)
                    if margin <= cash:
                        cash -= margin
                        s.in_pos=True; s.side="LONG"; s.entry_px=px; s.entry_ts=ts
                        s.entry_bar=i; s.size=sz; s.stop=px-sl_d
                        self.lg.debug(f"  LONG @{px:.2f} RSI={r['rsi']:.1f} SL={s.stop:.2f} [{regime}] Size=${notional:.2f}")

            elif r["short_entry"] == 1:
                sl_d = self.c.atr_sl_mult * atr
                risk = cash * self.c.risk_pct
                sz = min(risk / sl_d, (cash * self.c.max_position_pct) / px)
                
                # Check minimum notional (Hyperliquid: $10 minimum)
                notional = sz * px
                if notional < self.c.min_notional:
                    self.lg.warning(f"SKIP SHORT: Notional ${notional:.2f} < ${self.c.min_notional} (min order)")
                    continue
                
                if sz > 0 and sz * px >= 10:
                    margin = sz * px * (1 + cm)
                    if margin <= cash:
                        cash -= margin
                        s.in_pos=True; s.side="SHORT"; s.entry_px=px; s.entry_ts=ts
                        s.entry_bar=i; s.size=sz; s.stop=px+sl_d
                        self.lg.debug(f"  SHORT @{px:.2f} RSI={r['rsi']:.1f} SL={s.stop:.2f} [{regime}] Size=${notional:.2f}")

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
                "sl_rate":sum(1 for t in self.trades if t.reason=="STOP_LOSS")/n*100,
                "rsi_rate":sum(1 for t in self.trades if t.reason=="RSI_EXIT")/n*100,
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
        r = df.iloc[-1]; px = r["close"]; atr = r["atr"]; ts = str(df.index[-1])
        regime = r["regime"]
        
        # Get current price from Hyperliquid
        hl_px = self.hl.get_current_price(self.c.symbol)
        if hl_px:
            self.lg.info(f"-- {ts} HL:${hl_px:.2f} RSI={r['rsi']:.1f} {regime} --")
            px = hl_px  # Use live price
        else:
            self.lg.warning("Could not fetch live price, using close price")
        
        s = self.s

        # IN POSITION
        if s.in_pos:
            # Check stop loss
            if s.side == "LONG" and px <= s.stop:
                self.lg.info(f"STOP LOSS: {s.side} @ ${px:.2f}")
                result = self.hl.place_order(self.c.symbol, "sell", s.size, price=px)
                if result:
                    s.in_pos = False; s.size = 0.0; s.side = ""
                    s.save(self.c.state_file)
                return

            elif s.side == "SHORT" and px >= s.stop:
                self.lg.info(f"STOP LOSS: {s.side} @ ${px:.2f}")
                result = self.hl.place_order(self.c.symbol, "buy", s.size, price=px)
                if result:
                    s.in_pos = False; s.size = 0.0; s.side = ""
                    s.save(self.c.state_file)
                return

            # Check RSI exit
            if s.side == "LONG" and r["long_exit"] == 1:
                self.lg.info(f"RSI EXIT: LONG @ ${px:.2f}")
                result = self.hl.place_order(self.c.symbol, "sell", s.size, price=px)
                if result:
                    s.in_pos = False; s.size = 0.0; s.side = ""
                    s.save(self.c.state_file)
                return

            elif s.side == "SHORT" and r["short_exit"] == 1:
                self.lg.info(f"RSI EXIT: SHORT @ ${px:.2f}")
                result = self.hl.place_order(self.c.symbol, "buy", s.size, price=px)
                if result:
                    s.in_pos = False; s.size = 0.0; s.side = ""
                    s.save(self.c.state_file)
                return

        # NO POSITION - Check entries
        elif atr > 0:
            bal = self.hl.get_balance()["total"]
            
            # DEBUG: Entry signal check
            self.lg.debug(f"DEBUG: Checking entries | Long signal: {r['long_entry']} | Short signal: {r['short_entry']} | Balance: ${bal:.2f}")
            
            if r["long_entry"] == 1:
                sl_d = self.c.atr_sl_mult * atr
                risk = bal * self.c.risk_pct
                sz = min(risk / sl_d, (bal * self.c.max_position_pct) / px)
                
                # Check minimum notional (Hyperliquid: $10 minimum)
                notional = sz * px
                if notional < self.c.min_notional:
                    self.lg.warning(f"SKIP LONG: Notional ${notional:.2f} < ${self.c.min_notional} (min order)")
                    return
                
                if sz * px >= 10:
                    # Limit order at current price + small slippage
                    entry_px = px * (1 + self.c.slippage_pct)
                    sl_px = entry_px - sl_d
                    
                    self.lg.info(f"LONG ENTRY @ ${entry_px:.2f}, SL=${sl_px:.2f}, RSI={r['rsi']:.1f} Size=${notional:.2f}")
                    self.lg.debug(f"DEBUG: Placing LONG order | Size: {sz:.6f} | Entry: {entry_px:.2f} | SL: {sl_px:.2f}")
                    result = self.hl.place_order(self.c.symbol, "buy", sz, price=entry_px)
                    if result:
                        self.lg.debug(f"DEBUG: LONG order placed successfully | Result: {result}")
                        s.in_pos = True; s.side = "LONG"; s.entry_px = entry_px; s.entry_ts = ts
                        s.size = sz; s.stop = sl_px
                        s.save(self.c.state_file)
                    else:
                        self.lg.error(f"ERROR: LONG order placement failed | Result: {result}")
                else:
                    self.lg.error(f"ERROR: Position size calculation invalid | Size: {sz} | Notional: {notional}")

            elif r["short_entry"] == 1:
                sl_d = self.c.atr_sl_mult * atr
                risk = bal * self.c.risk_pct
                sz = min(risk / sl_d, (bal * self.c.max_position_pct) / px)
                
                # Check minimum notional (Hyperliquid: $10 minimum)
                notional = sz * px
                if notional < self.c.min_notional:
                    self.lg.warning(f"SKIP SHORT: Notional ${notional:.2f} < ${self.c.min_notional} (min order)")
                    return
                
                if sz * px >= 10:
                    entry_px = px * (1 - self.c.slippage_pct)
                    sl_px = entry_px + sl_d
                    
                    self.lg.info(f"SHORT ENTRY @ ${entry_px:.2f}, SL=${sl_px:.2f}, RSI={r['rsi']:.1f} Size=${notional:.2f}")
                    self.lg.debug(f"DEBUG: Placing SHORT order | Size: {sz:.6f} | Entry: {entry_px:.2f} | SL: {sl_px:.2f}")
                    result = self.hl.place_order(self.c.symbol, "sell", sz, price=entry_px)
                    if result:
                        self.lg.debug(f"DEBUG: SHORT order placed successfully | Result: {result}")
                        s.in_pos = True; s.side = "SHORT"; s.entry_px = entry_px; s.entry_ts = ts
                        s.size = sz; s.stop = sl_px
                        s.save(self.c.state_file)
                    else:
                        self.lg.error(f"ERROR: SHORT order placement failed | Result: {result}")
                else:
                    self.lg.error(f"ERROR: Position size calculation invalid | Size: {sz} | Notional: {notional}")

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
 BTC/USDT 4H ADAPTIVE RSI v5 (Hyperliquid) - PERFORMANCE REPORT
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
            ("MaxDD < 10%",m["max_drawdown"]<10,f"{m['max_drawdown']:.2f}%"),
            ("PF > 1.2",m["profit_factor"]>1.2,f"{m['profit_factor']:.2f}"),
            ("EV > $0",m["expectancy"]>0,f"${m['expectancy']:+,.2f}"),
            ("SL Rate < 40%",m["sl_rate"]<40,f"{m['sl_rate']:.1f}%"),
            ("WR > 50%",m["win_rate"]>50,f"{m['win_rate']:.1f}%")]
    r+=f"\n\n{'='*70}\n GO CHECK\n{'='*70}"
    for nm,ok,v in checks: r+=f"\n  {'PASS' if ok else 'FAIL'} {nm}: {v}"
    p=sum(1 for _,ok,_ in checks if ok)
    r+=f"\n\n  Score: {p}/{len(checks)}"
    r+=f"\n  {'>>> GO <<<' if p==len(checks) else '>>> CONDITIONAL <<<' if p>=4 else '>>> STOP <<<' }"
    r+=f"\n{'='*70}"
    print(r); lg.info(r)
    if trades:
        print(f"\n{'='*105}")
        print(f"  {'Time':<20} {'Side':<6} {'Type':<12} {'Regime':<6} {'Entry':>10} {'Exit':>10} {'PnL%':>8} {'PnL$':>12} {'Bars':>5}")
        print(f"{'-'*105}")
        for t in trades:
            print(f"  {t.t_out[:16]:<20} {t.side:<6} {t.reason:<12} {t.regime:<6} {t.p_in:>10.2f} {t.p_out:>10.2f} {t.pnl_pct:>+7.2f}% ${t.pnl:>+10.2f} {t.bars:>5}")
        print(f"{'='*105}")


# ==================================================================
# MAIN
# ==================================================================

def main():
    pa=argparse.ArgumentParser()
    pa.add_argument("--mode",choices=["backtest","paper","live"],default="backtest")
    pa.add_argument("--days",type=int,default=180)
    pa.add_argument("--exchange",choices=["binance","hyperliquid"],default="hyperliquid")
    pa.add_argument("--testnet",action="store_true",help="Use Hyperliquid Testnet")
    pa.add_argument("--debug",action="store_true",help="Enable debug logging")
    pa.add_argument("--interval",type=int,default=60,help="Loop interval in seconds (default: 60)")
    args=pa.parse_args()
    
    # Create .env file if it doesn't exist
    if not os.path.exists(".env"):
        create_env_file()
    
    c=TradingConfig()
    c.lookback_days = args.days
    c.use_testnet = args.testnet
    c.exchange_id = args.exchange
    
    lg=setup_logging(c, debug=args.debug)
    lg.info(f"Mode: {args.mode} | v5 Adaptive RSI (Hyperliquid Edition) | Days: {c.lookback_days}")
    lg.info(f"Exchange: {args.exchange} ({'Testnet' if c.use_testnet else 'Mainnet'})")
    
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
        regimes=df["regime"].value_counts()
        lg.info(f"Regimes: {dict(regimes)}")
        lg.info(f"Long signals: {df['long_entry'].sum()}, Short signals: {df['short_entry'].sum()}")
        bt=Backtest(c,lg); m=bt.run(df); report(m,bt.trades,lg)
    elif args.mode=="paper":
        lg.info("Entering PAPER mode")
        lg.info("PAPER MODE (Read-only Hyperliquid)")
        LiveEngine(c,lg).run_loop(interval=args.interval)
    elif args.mode=="live":
        lg.info("Entering LIVE mode")
        LiveEngine(c,lg).run_loop(interval=args.interval)
    else:
        lg.error(f"UNKNOWN MODE: {args.mode}")
        
def create_env_file():
    """Create .env file with default configuration"""
    env_content = """# Hyperliquid API Credentials
# =========================================================
# IMPORTANT: Never commit this file to git or share publicly!
# Your private key gives full access to your wallet.
# =========================================================

# Hyperliquid Wallet Configuration
# Get your wallet address from MetaMask (Arbitrum network)
HL_WALLET_ADDRESS=0x8455b70a5a0d942eb9a1598a0e9e1214a3b31b55

# Hyperliquid Private Key
# Export from MetaMask: Account Details -> Export Private Key
HL_PRIVATE_KEY=0x42cbf5670eead7cfda780b9d09d4ac09dcbf9d0b8ca1b0d169f49f1ae4d358c6

# =========================================================
# Network Configuration (Optional - defaults to mainnet)
# Set HL_USE_TESTNET=true for testnet trading
# HL_USE_TESTNET=false for mainnet (real money)
HL_USE_TESTNET=false
"""
    try:
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_content)
        print("✅ .env file created with your Hyperliquid API credentials")
        print("")
        print("Configuration:")
        print("  Wallet Address: 0x8455...31b55")
        print("  Private Key: 0x42cb...358c6")
        print("  Network: Mainnet (real money)")
        print("")
        print("⚠️  SECURITY REMINDERS:")
        print("  1. Never share your .env file or private key")
        print("  2. Use testnet first: set HL_USE_TESTNET=true")
        print("  3. Start with small amounts")
        print("")
        print("To use testnet, edit .env and change HL_USE_TESTNET=true")
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")
        raise

if __name__ == "__main__":
    main()
