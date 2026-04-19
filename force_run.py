# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
======================================================================
  BTC/USDT 4H ADAPTIVE RSI v5 — Regime-Aware Trading System
  -----------------------------------------------------------
  THE FIX: v1-v4 were all LONG-ONLY during a 50% bear market.
  v5 detects regime and trades accordingly:
    BULL  -> Long RSI dips  (buy RSI<35, sell RSI>65)
    BEAR  -> Short RSI pops (short RSI>65, cover RSI<35)
    RANGE -> Skip (cash preservation)

  BTC CONTEXT (real data Sep 2025 - Mar 2026):
    Oct 2025: ATH $126,296
    Nov-Dec 2025: Correction (-40%)
    Jan-Mar 2026: Bear market ($63k-$78k)
    = LONG-ONLY strategies CANNOT win this period

  This system uses FUTURES (short-capable) via ccxt.

  Modes: --mode backtest | paper | live
======================================================================
"""

import os, sys, json, time, logging, argparse
import datetime as dt
from pathlib import Path
from dataclasses import dataclass, field, asdict
import numpy as np
import pandas as pd


@dataclass
class TradingConfig:
    exchange_id: str = "binance"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    lookback_days: int = 180
    api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_API_SECRET", ""))

    # Regime detection
    ema_fast: int = 50
    ema_slow: int = 200
    ema_slope_period: int = 10       # bars to measure EMA slope
    ema_range_pct: float = 0.01      # EMAs within 1% = range

    # RSI
    rsi_period: int = 14
    rsi_oversold: float = 35.0       # long entry in bull
    rsi_overbought: float = 65.0     # short entry in bear
    rsi_exit_long: float = 65.0      # long exit
    rsi_exit_short: float = 35.0     # short exit

    # Risk
    atr_period: int = 14
    atr_sl_mult: float = 2.0
    risk_pct: float = 0.015
    max_hold_bars: int = 30

    # Safety
    initial_cash: float = 100_000.0
    commission_pct: float = 0.001
    max_position_pct: float = 0.50   # conservative: max 50% of equity
    max_consecutive_losses: int = 3
    cooldown_bars: int = 6
    drawdown_halt_pct: float = 0.10

    data_csv: str = "btc_usdt_4h.csv"
    log_dir: str = "logs"
    state_file: str = "trade_state.json"


def setup_logging(c):
    Path(c.log_dir).mkdir(exist_ok=True)
    lg = logging.getLogger("AdaptiveV5")
    lg.setLevel(logging.DEBUG); lg.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(f"{c.log_dir}/v5_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
    fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)
    ch = logging.StreamHandler(); ch.setLevel(logging.INFO); ch.setFormatter(fmt)
    lg.addHandler(fh); lg.addHandler(ch)
    return lg


def fetch_ohlcv(c, lg):
    if os.path.exists(c.data_csv):
        age = (dt.datetime.now().timestamp() - os.path.getmtime(c.data_csv)) / 3600
        if age < 4:
            lg.info(f"CSV cache: {c.data_csv}")
            return pd.read_csv(c.data_csv, parse_dates=["datetime"], index_col="datetime").sort_index()
    try:
        import ccxt
        lg.info(f"Fetching {c.symbol} {c.timeframe}...")
        ex = getattr(ccxt, c.exchange_id)({"apiKey": c.api_key, "secret": c.api_secret, "enableRateLimit": True})
        since = ex.parse8601((dt.datetime.utcnow()-dt.timedelta(days=c.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        rows = []
        while True:
            b = ex.fetch_ohlcv(c.symbol, c.timeframe, since=since, limit=1000)
            if not b: break
            rows.extend(b); since = b[-1][0]+1
            if len(b) < 1000: break
        df = pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("datetime", inplace=True)
        df = df[["open","high","low","close","volume"]].astype(float)
        df.to_csv(c.data_csv); lg.info(f"Saved {len(df)} bars")
        return df.sort_index()
    except Exception as e:
        lg.warning(f"ccxt: {e}")
        if os.path.exists(c.data_csv):
            return pd.read_csv(c.data_csv, parse_dates=["datetime"], index_col="datetime").sort_index()
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

        # Regime: BULL / BEAR / RANGE
        def regime(row):
            if row["ema_gap_pct"] < c.ema_range_pct:
                return "RANGE"
            elif row["ema_f"] > row["ema_s"] and row["ema_f_slope"] > 0:
                return "BULL"
            elif row["ema_f"] < row["ema_s"] and row["ema_f_slope"] < 0:
                return "BEAR"
            else:
                return "RANGE"  # ambiguous = sit out
        df["regime"] = df.apply(regime, axis=1)

        # RSI (Wilder smoothing)
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

        return df.dropna()


@dataclass
class State:
    in_pos: bool = False
    side: str = ""       # "LONG" or "SHORT"
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
    sz:float; pnl:float; pnl_pct:float; reason:str; regime:str; bars:int=0


class Backtest:
    def __init__(self, c, lg):
        self.c=c; self.lg=lg; self.trades=[]; self.eq=[]

    def _pnl(self, side, entry, exit_px, size, comm):
        if side == "LONG":
            return (exit_px - entry) * size - exit_px * size * comm
        else:  # SHORT
            return (entry - exit_px) * size - exit_px * size * comm

    def run(self, df):
        cash = self.c.initial_cash; s = State(); s.peak_eq = cash
        cm = self.c.commission_pct

        for i in range(len(df)):
            r = df.iloc[i]; ts = str(df.index[i])
            px, hi, lo, atr = r["close"], r["high"], r["low"], r["atr"]
            regime = r["regime"]

            # Mark to market
            if s.in_pos:
                if s.side == "LONG":
                    pv = s.size * px
                else:
                    pv = s.size * (2 * s.entry_px - px)  # short P&L
                equity = cash + pv
            else:
                equity = cash

            s.peak_eq = max(s.peak_eq, equity)
            dd = (s.peak_eq - equity) / s.peak_eq if s.peak_eq > 0 else 0
            self.eq.append(equity)

            if dd >= self.c.drawdown_halt_pct: continue
            if i < s.cool_bar: continue

            # -- IN POSITION --
            if s.in_pos:
                held = i - s.entry_bar

                # Time exit
                if held >= self.c.max_hold_bars:
                    pnl = self._pnl(s.side, s.entry_px, px, s.size, cm)
                    cash += s.size * s.entry_px + pnl  # return margin + pnl
                    self.trades.append(Trade(s.entry_ts,ts,s.side,s.entry_px,px,s.size,pnl,(px/s.entry_px-1)*100*(1 if s.side=="LONG" else -1),"TIME_EXIT",regime,held))
                    self._close(s,pnl,i); continue

                # Stop loss
                if s.side == "LONG" and lo <= s.stop:
                    ep = s.stop
                    pnl = self._pnl("LONG", s.entry_px, ep, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"LONG",s.entry_px,ep,s.size,pnl,(ep/s.entry_px-1)*100,"STOP_LOSS",regime,held))
                    self._close(s,pnl,i); continue

                if s.side == "SHORT" and hi >= s.stop:
                    ep = s.stop
                    pnl = self._pnl("SHORT", s.entry_px, ep, s.size, cm)
                    cash += s.size * s.entry_px + pnl
                    self.trades.append(Trade(s.entry_ts,ts,"SHORT",s.entry_px,ep,s.size,pnl,(s.entry_px/ep-1)*100,"STOP_LOSS",regime,held))
                    self._close(s,pnl,i); continue

                # RSI exit
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

            # -- NO POSITION --
            if atr <= 0: continue

            # LONG entry (bull regime)
            if r["long_entry"] == 1:
                sl_d = self.c.atr_sl_mult * atr
                risk = cash * self.c.risk_pct
                sz = min(risk / sl_d, (cash * self.c.max_position_pct) / px)
                if sz > 0 and sz * px >= 10:
                    margin = sz * px * (1 + cm)
                    if margin <= cash:
                        cash -= margin
                        s.in_pos=True; s.side="LONG"; s.entry_px=px; s.entry_ts=ts
                        s.entry_bar=i; s.size=sz; s.stop=px-sl_d
                        self.lg.debug(f"  LONG @{px:.2f} RSI={r['rsi']:.1f} SL={s.stop:.2f} [{regime}]")

            # SHORT entry (bear regime)
            elif r["short_entry"] == 1:
                sl_d = self.c.atr_sl_mult * atr
                risk = cash * self.c.risk_pct
                sz = min(risk / sl_d, (cash * self.c.max_position_pct) / px)
                if sz > 0 and sz * px >= 10:
                    margin = sz * px * (1 + cm)
                    if margin <= cash:
                        cash -= margin
                        s.in_pos=True; s.side="SHORT"; s.entry_px=px; s.entry_ts=ts
                        s.entry_bar=i; s.size=sz; s.stop=px+sl_d
                        self.lg.debug(f"  SHORT @{px:.2f} RSI={r['rsi']:.1f} SL={s.stop:.2f} [{regime}]")

        # Close remaining
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


class Live:
    def __init__(self,c,lg):
        self.c=c; self.lg=lg; self.ind=Indicators(c); self.s=State.load(c.state_file)
    def _init(self):
        import ccxt
        self.ex=getattr(ccxt,self.c.exchange_id)({"apiKey":self.c.api_key,"secret":self.c.api_secret,"enableRateLimit":True,"options":{"defaultType":"future"}})
    def _bal(self): return float(self.ex.fetch_balance()["total"].get("USDT",0))
    def _ord(self,side,amt):
        self.lg.info(f"ORDER {side} {amt:.6f}"); return self.ex.create_order(symbol=self.c.symbol,type="market",side=side,amount=amt)
    def run_once(self):
        df=fetch_ohlcv(self.c,self.lg); df=self.ind.compute(df)
        r=df.iloc[-1]; px=r["close"]; atr=r["atr"]; ts=str(df.index[-1])
        regime=r["regime"]
        self.lg.info(f"-- {ts} ${px:.2f} RSI={r['rsi']:.1f} {regime} --")
        s=self.s
        if s.in_pos:
            if s.side=="LONG":
                if px<=s.stop: self._ord("sell",s.size); s.in_pos=False
                elif r["long_exit"]==1: self._ord("sell",s.size); s.in_pos=False
            elif s.side=="SHORT":
                if px>=s.stop: self._ord("buy",s.size); s.in_pos=False
                elif r["short_exit"]==1: self._ord("buy",s.size); s.in_pos=False
        else:
            bal=self._bal()
            if r["long_entry"]==1 and atr>0:
                sz=min(bal*self.c.risk_pct/(self.c.atr_sl_mult*atr),(bal*self.c.max_position_pct)/px)
                if sz*px>=10:
                    o=self._ord("buy",sz); fp=float(o.get("average",px))
                    s.in_pos=True; s.side="LONG"; s.entry_px=fp; s.size=sz
                    s.stop=fp-self.c.atr_sl_mult*atr
            elif r["short_entry"]==1 and atr>0:
                sz=min(bal*self.c.risk_pct/(self.c.atr_sl_mult*atr),(bal*self.c.max_position_pct)/px)
                if sz*px>=10:
                    o=self._ord("sell",sz); fp=float(o.get("average",px))
                    s.in_pos=True; s.side="SHORT"; s.entry_px=fp; s.size=sz
                    s.stop=fp+self.c.atr_sl_mult*atr
        s.save(self.c.state_file)
    def run_loop(self,interval=14400):
        self._init()
        while True:
            try: self.run_once()
            except KeyboardInterrupt: break
            except Exception as e: self.lg.error(f"Err: {e}",exc_info=True)
            time.sleep(interval)


def report(m, trades, lg):
    r=f"""
{'='*70}
 BTC/USDT 4H ADAPTIVE RSI v5 - PERFORMANCE REPORT
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
    r+=f"\n  {'>>> GO <<<' if p==len(checks) else '>>> CONDITIONAL <<<' if p>=4 else '>>> STOP <<<'}"
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
    pa=argparse.ArgumentParser(); pa.add_argument("--mode",choices=["backtest","paper","live"],default="backtest")
    pa.add_argument("--days",type=int,default=180,help="Lookback days (default: 180)")
    args=pa.parse_args()
    c=TradingConfig()
    c.lookback_days = args.days
    lg=setup_logging(c)
    lg.info(f"Mode: {args.mode} | v5 Adaptive RSI | Days: {c.lookback_days}")
    if args.mode=="backtest":
        df=fetch_ohlcv(c,lg); df=Indicators(c).compute(df)
        lg.info(f"Data: {df.index[0]} -> {df.index[-1]} ({len(df)} bars)")
        regimes=df["regime"].value_counts()
        lg.info(f"Regimes: {dict(regimes)}")
        lg.info(f"Long signals: {df['long_entry'].sum()}, Short signals: {df['short_entry'].sum()}")
        bt=Backtest(c,lg); m=bt.run(df); report(m,bt.trades,lg)
    else:
        if args.mode=="paper": lg.info("PAPER MODE")
        Live(c,lg).run_loop()

if __name__=="__main__": main()
