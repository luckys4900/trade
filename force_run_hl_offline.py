# -*- coding: utf-8 -*-
"""
BTC/USDT 4H ADAPTIVE RSI v5 - OFFLINE BACKTEST VERSION
Hyperliquid API does not use - this version uses cached CSV data only
"""

import os, sys, json, time, logging, argparse
import datetime as dt
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Literal
import numpy as np
import pandas as pd

@dataclass
class TradingConfig:
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    lookback_days: int = 180
    
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
    initial_cash: float = 100.0
    commission_pct: float = 0.0005
    max_position_pct: float = 0.50
    max_consecutive_losses: int = 3
    cooldown_bars: int = 6
    drawdown_halt_pct: float = 0.10
    
    data_csv: str = "btc_usdt_4h.csv"
    log_dir: str = "logs"


def setup_logging(c):
    Path(c.log_dir).mkdir(exist_ok=True)
    lg = logging.getLogger("AdaptiveV5_Offline")
    lg.setLevel(logging.DEBUG); lg.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(f"{c.log_dir}/offline_test_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
    fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)
    ch = logging.StreamHandler(); ch.setLevel(logging.INFO); ch.setFormatter(fmt)
    lg.addHandler(fh); lg.addHandler(ch)
    return lg


def fetch_ohlcv(c, lg):
    """Fetch OHLCV data from CSV or Binance"""
    if os.path.exists(c.data_csv):
        try:
            df = pd.read_csv(c.data_csv, parse_dates=["datetime"], index_col="datetime").sort_index()
            if len(df) > 0:
                lg.info(f"CSV cache: {c.data_csv} ({len(df)} bars)")
                return df
            else:
                lg.warning("CSV exists but empty, fetching from Binance...")
        except Exception as e:
            lg.warning(f"CSV read error: {e}, fetching from Binance...")
    
    # Fetch from Binance
    try:
        import ccxt
        lg.info(f"Fetching {c.symbol} {c.timeframe} from Binance (backtest data)...")
        ex = ccxt.binance({"enableRateLimit": True})
        since = ex.parse8601((dt.datetime.utcnow()-dt.timedelta(days=c.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        rows = []
        while True:
            b = ex.fetch_ohlcv(c.symbol, c.timeframe, since=since, limit=1000)
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


@dataclass
class Trade:
    t_in:str; t_out:str; side:str; p_in:float; p_out:float
    sz:float; pnl:float; pnl_pct:float; reason:str; regime:str; bars:int=0


class Backtest:
    def __init__(self, c, lg):
        self.c=c; self.lg=lg; self.trades=[]; self.eq=[]

    def _pnl(self, side, entry, exit_px, size, comm):
        if side == "LONG":
            return (exit_px - entry) * size - exit_px * size * comm
        else:
            return (entry - exit_px) * size - exit_px * size * comm

    def run(self, df):
        cash = self.c.initial_cash
        in_pos = False; side = ""; entry_px = 0.0
        entry_bar = 0; size = 0.0; stop = 0.0
        c_loss = 0; cool_bar = 0; peak_eq = cash
        cm = self.c.commission_pct

        for i in range(len(df)):
            r = df.iloc[i]; ts = str(df.index[i])
            px, hi, lo, atr = r["close"], r["high"], r["low"], r["atr"]
            regime = r["regime"]

            if in_pos:
                if side == "LONG":
                    pv = size * px
                else:
                    pv = size * (2 * entry_px - px)
                equity = cash + pv
            else:
                equity = cash

            peak_eq = max(peak_eq, equity)
            dd = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
            self.eq.append(equity)

            if dd >= self.c.drawdown_halt_pct: continue
            if i < cool_bar: continue

            # IN POSITION
            if in_pos:
                held = i - entry_bar
                if held >= self.c.max_hold_bars:
                    pnl = self._pnl(side, entry_px, px, size, cm)
                    cash += size * entry_px + pnl
                    self.trades.append(Trade(str(entry_bar),str(i),side,entry_px,px,size,pnl,(px/entry_px-1)*100*(1 if side=="LONG" else -1),"TIME_EXIT",regime,held))
                    in_pos=False; size=0.0; side=""
                    c_loss = c_loss + 1 if pnl < 0 else 0
                    if c_loss >= self.c.max_consecutive_losses:
                        cool_bar = i + self.c.cooldown_bars
                    else:
                        c_loss = 0
                    continue

                if side == "LONG" and lo <= stop:
                    ep = stop; pnl = self._pnl("LONG", entry_px, ep, size, cm)
                    cash += size * entry_px + pnl
                    self.trades.append(Trade(str(entry_bar),str(i),"LONG",entry_px,ep,size,pnl,(ep/entry_px-1)*100,"STOP_LOSS",regime,held))
                    in_pos=False; size=0.0; side=""
                    c_loss = c_loss + 1 if pnl < 0 else 0
                    if c_loss >= self.c.max_consecutive_losses:
                        cool_bar = i + self.c.cooldown_bars
                    else:
                        c_loss = 0
                    continue

                if side == "SHORT" and hi >= stop:
                    ep = stop; pnl = self._pnl("SHORT", entry_px, ep, size, cm)
                    cash += size * entry_px + pnl
                    self.trades.append(Trade(str(entry_bar),str(i),"SHORT",entry_px,ep,size,pnl,(entry_px/ep-1)*100,"STOP_LOSS",regime,held))
                    in_pos=False; size=0.0; side=""
                    c_loss = c_loss + 1 if pnl < 0 else 0
                    if c_loss >= self.c.max_consecutive_losses:
                        cool_bar = i + self.c.cooldown_bars
                    else:
                        c_loss = 0
                    continue

                if side == "LONG" and r["long_exit"] == 1:
                    pnl = self._pnl("LONG", entry_px, px, size, cm)
                    cash += size * entry_px + pnl
                    self.trades.append(Trade(str(entry_bar),str(i),"LONG",entry_px,px,size,pnl,(px/entry_px-1)*100,"RSI_EXIT",regime,held))
                    in_pos=False; size=0.0; side=""
                    c_loss = c_loss + 1 if pnl < 0 else 0
                    if c_loss >= self.c.max_consecutive_losses:
                        cool_bar = i + self.c.cooldown_bars
                    else:
                        c_loss = 0
                    continue

                if side == "SHORT" and r["short_exit"] == 1:
                    pnl = self._pnl("SHORT", entry_px, px, size, cm)
                    cash += size * entry_px + pnl
                    self.trades.append(Trade(str(entry_bar),str(i),"SHORT",entry_px,px,size,pnl,(entry_px/px-1)*100,"RSI_EXIT",regime,held))
                    in_pos=False; size=0.0; side=""
                    c_loss = c_loss + 1 if pnl < 0 else 0
                    if c_loss >= self.c.max_consecutive_losses:
                        cool_bar = i + self.c.cooldown_bars
                    else:
                        c_loss = 0
                    continue
                continue

            elif atr > 0:
                if r["long_entry"] == 1:
                    sl_d = self.c.atr_sl_mult * atr
                    risk = cash * self.c.risk_pct
                    sz = min(risk / sl_d, (cash * self.c.max_position_pct) / px)
                    
                    if sz > 0 and sz * px >= 10:
                        margin = sz * px * (1 + cm)
                        if margin <= cash:
                            cash -= margin
                            in_pos=True; side="LONG"; entry_px=px; entry_bar=i
                            size=sz; stop=px-sl_d
                            self.lg.debug(f"  LONG @{px:.2f} RSI={r['rsi']:.1f} SL={stop:.2f} [{regime}] Size=${sz*px:.2f}")

                elif r["short_entry"] == 1:
                    sl_d = self.c.atr_sl_mult * atr
                    risk = cash * self.c.risk_pct
                    sz = min(risk / sl_d, (cash * self.c.max_position_pct) / px)
                    
                    if sz > 0 and sz * px >= 10:
                        margin = sz * px * (1 + cm)
                        if margin <= cash:
                            cash -= margin
                            in_pos=True; side="SHORT"; entry_px=px; entry_bar=i
                            size=sz; stop=px+sl_d
                            self.lg.debug(f"  SHORT @{px:.2f} RSI={r['rsi']:.1f} SL={stop:.2f} [{regime}] Size=${sz*px:.2f}")

        if in_pos:
            lp = df.iloc[-1]["close"]
            pnl = self._pnl(side, entry_px, lp, size, cm)
            cash += size * entry_px + pnl
            self.trades.append(Trade(str(entry_bar),str(df.index[-1]),side,entry_px,lp,size,pnl,0,"EOD","",0))

        return self._metrics(cash)

    def _metrics(self, final):
        init=self.c.initial_cash; ret=(final-init)/init*100; n=len(self.trades)
        if n==0: return {"final_value":final,"total_return":ret,"total_trades":0,"win_rate":0,"profit_factor":0,"max_drawdown":0,"sharpe":0,"avg_win":0,"avg_loss":0,"expectancy":0,"avg_bars":0}
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
        
        # Calculate all metrics
        sl_rate = sum(1 for t in self.trades if t.reason=="STOP_LOSS")/n*100 if n > 0 else 0
        rsi_rate = sum(1 for t in self.trades if t.reason=="RSI_EXIT")/n*100 if n > 0 else 0
        
        return {"final_value":final,"total_return":ret,"total_trades":n,"win_rate":len(w)/n*100,
                "profit_factor":gp/gl if gl>0 else float("inf"),"max_drawdown":mdd,"sharpe":sharpe,
                "avg_win":np.mean(w) if w else 0,"avg_loss":np.mean(l) if l else 0,
                "expectancy":np.mean(pnls),"avg_bars":np.mean([t.bars for t in self.trades]),
                "sl_rate":sl_rate,"rsi_rate":rsi_rate,
                "long_trades":len(longs),"short_trades":len(shorts),
                "long_wr":lw/len(longs)*100 if longs else 0,"short_wr":sw/len(shorts)*100 if shorts else 0}


def report(m, trades, lg):
    r=f"""
{'='*70}
 BTC/USDT 4H ADAPTIVE RSI v5 - OFFLINE BACKTEST
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
  RSI Exit rate  : {m.get('rsi_rate', 0):.1f}%
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


def main():
    pa=argparse.ArgumentParser()
    pa.add_argument("--mode",choices=["backtest"],default="backtest")
    pa.add_argument("--days",type=int,default=180)
    args=pa.parse_args()
    
    c=TradingConfig()
    c.lookback_days = args.days
    
    lg=setup_logging(c)
    lg.info(f"Mode: {args.mode} | v5 Adaptive RSI - OFFLINE BACKTEST | Days: {c.lookback_days}")
    
    lg.info("Entering BACKTEST mode")
    df=fetch_ohlcv(c,lg); df=Indicators(c).compute(df)
    lg.info(f"Data: {df.index[0]} -> {df.index[-1]} ({len(df)} bars)")
    regimes=df["regime"].value_counts()
    lg.info(f"Regimes: {dict(regimes)}")
    lg.info(f"Long signals: {df['long_entry'].sum()}, Short signals: {df['short_entry'].sum()}")
    bt=Backtest(c,lg); m=bt.run(df); report(m,bt.trades,lg)


if __name__ == "__main__":
    main()
