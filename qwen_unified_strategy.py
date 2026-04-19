# -*- coding: utf-8 -*-
"""
Qwen Unified Strategy - OCPM + Range MR Combined Backtest
"""

import os, sys, argparse, datetime as dt, logging, numpy as np, pandas as pd
from pathlib import Path
from dataclasses import dataclass

# ===== OCPM Parameters =====
OCPM_EMA_FAST = 21
OCPM_EMA_SLOW = 55
OCPM_DONCHIAN_PERIOD = 20  # Donchian breakout filter (20-bar high/low)
OCPM_RSI_PERIOD = 14
OCPM_RSI_PULLBACK_LONG = 48.0
OCPM_RSI_PULLBACK_SHORT = 52.0
OCPM_ATR_PERIOD = 14
OCPM_ATR_SL_MULT = 3.0
OCPM_ATR_TP_MULT = 6.0
OCPM_MAX_HOLD = 20

# ===== Range MR Parameters =====
MR_BB_PERIOD = 20
MR_BB_STD = 2.0
MR_RSI_PERIOD = 14
MR_RSI_OVERSOLD = 30.0
MR_RSI_OVERBOUGHT = 70.0
MR_ATR_PERIOD = 14
MR_ATR_SL_MULT = 2.0
MR_MAX_HOLD = 10
MR_ADX_PERIOD = 14
MR_MAX_ADX = 25.0
MR_EMA_CONVERGE_PCT = 0.020

# ===== Shared =====
INITIAL_CASH = 100.0
COMM_PCT = 0.0005
RISK_PCT = 0.015
MAX_POS_PCT = 0.40
MAX_LOSSES = 5
COOLDOWN = 2
DD_HALT = 0.15


@dataclass
class Trade:
    t_in:str; t_out:str; side:str; strat:str; p_in:float; p_out:float
    sz:float; pnl:float; pnl_pct:float; reason:str; bars:int=0


def fetch_ohlcv(days, tf, cache):
    import ccxt
    ex = ccxt.binance({"enableRateLimit": True})
    df = pd.DataFrame()
    
    if os.path.exists(cache):
        try:
            df = pd.read_csv(cache, parse_dates=["datetime"], index_col="datetime").sort_index()
        except: pass

    try:
        if len(df) > 0:
            last_ts = int(df.index[-1].timestamp() * 1000)
            print(f"Updating data from {df.index[-1]}")
            b = ex.fetch_ohlcv("BTC/USDT", tf, since=last_ts)
            if b:
                new_df = pd.DataFrame(b, columns=["ts","o","h","l","c","v"])
                new_df["datetime"] = pd.to_datetime(new_df["ts"], unit="ms")
                new_df.set_index("datetime", inplace=True)
                new_df = new_df[["o","h","l","c","v"]].astype(float)
                new_df.columns = ["open","high","low","close","volume"]
                df = pd.concat([df, new_df])
                df = df[~df.index.duplicated(keep='last')].sort_index()
                df.to_csv(cache)
                print(f"Total bars: {len(df)}")
        else:
            print(f"Fetching BTC USDT {tf} ({days}d)...")
            since = ex.parse8601((dt.datetime.utcnow()-dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            rows = []
            while True:
                b = ex.fetch_ohlcv("BTC/USDT", tf, since=since, limit=1000)
                if not b: break
                rows.extend(b); since = b[-1][0]+1
                if len(b) < 1000: break
            df = pd.DataFrame(rows, columns=["ts","o","h","l","c","v"])
            df["datetime"] = pd.to_datetime(df["ts"], unit="ms")
            df.set_index("datetime", inplace=True)
            df = df[["o","h","l","c","v"]].astype(float)
            df.columns = ["open","high","low","close","volume"]
            df.to_csv(cache); print(f"Saved {len(df)} bars")
    except Exception as e:
        print(f"Data fetch error: {e}")
        
    return df.sort_index()


def compute_all(df):
    # OCPM indicators
    df["ocpm_ema_f"] = df["close"].ewm(span=OCPM_EMA_FAST, adjust=False).mean()
    df["ocpm_ema_s"] = df["close"].ewm(span=OCPM_EMA_SLOW, adjust=False).mean()
    df["ocpm_ema_slope"] = df["ocpm_ema_f"].pct_change(10)

    # Donchian Channel for trend confirmation
    df["ocpm_donchian_high"] = df["high"].rolling(OCPM_DONCHIAN_PERIOD).max()
    df["ocpm_donchian_low"] = df["low"].rolling(OCPM_DONCHIAN_PERIOD).min()

    df["ocpm_trend"] = "RANGE"
    df.loc[df["close"]>df["ocpm_ema_s"],"ocpm_trend"]="UPTREND"
    df.loc[df["close"]<df["ocpm_ema_s"],"ocpm_trend"]="DOWNTREND"

    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/OCPM_RSI_PERIOD, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/OCPM_RSI_PERIOD, adjust=False).mean()
    df["rsi"] = 100 - 100/(1+gain/loss.replace(0,np.nan))
    df["rsi_prev"] = df["rsi"].shift(1)

    tr = pd.concat([df["high"]-df["low"],(df["high"]-df["close"].shift(1)).abs(),(df["low"]-df["close"].shift(1)).abs()],axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/OCPM_ATR_PERIOD, min_periods=OCPM_ATR_PERIOD).mean()

    # OCPM entry signals with Donchian breakout trend confirmation
    # Donchian filter: price is above Donchian midline (trend structure is bullish)
    # This is a structural filter, not a simultaneous breakout requirement
    donchian_mid = (df["ocpm_donchian_high"] + df["ocpm_donchian_low"]) / 2
    donchian_trend_long = df["close"] > donchian_mid
    donchian_trend_short = df["close"] < donchian_mid

    df["ocpm_long"] = ((df["ocpm_trend"]=="UPTREND")
                       & donchian_trend_long
                       & (df["rsi_prev"]<=OCPM_RSI_PULLBACK_LONG)
                       & (df["rsi"]>df["rsi_prev"])
                       & (df["rsi"]<55)).astype(int)
    df["ocpm_short"] = ((df["ocpm_trend"]=="DOWNTREND")
                        & donchian_trend_short
                        & (df["rsi_prev"]>=OCPM_RSI_PULLBACK_SHORT)
                        & (df["rsi"]<df["rsi_prev"])
                        & (df["rsi"]>45)).astype(int)

    # Range MR indicators
    df["bb_mid"] = df["close"].rolling(MR_BB_PERIOD).mean()
    bb_std = df["close"].rolling(MR_BB_PERIOD).std()
    df["bb_upper"] = df["bb_mid"]+MR_BB_STD*bb_std
    df["bb_lower"] = df["bb_mid"]-MR_BB_STD*bb_std
    df["ema_f"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_s"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema_conv"] = (df["ema_f"]-df["ema_s"]).abs()/df["close"]

    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()
    plus_dm = plus_dm.clip(lower=0).where(plus_dm>minus_dm, 0)
    minus_dm = minus_dm.clip(lower=0).where(minus_dm>plus_dm, 0)
    atr_raw = tr.ewm(alpha=1/MR_ADX_PERIOD, min_periods=MR_ADX_PERIOD).mean()
    plus_di = 100*(plus_dm.ewm(alpha=1/MR_ADX_PERIOD, min_periods=MR_ADX_PERIOD).mean()/atr_raw)
    minus_di = 100*(minus_dm.ewm(alpha=1/MR_ADX_PERIOD, min_periods=MR_ADX_PERIOD).mean()/atr_raw)
    dx = 100*(plus_di-minus_di).abs()/(plus_di+minus_di).replace(0,np.nan)
    df["adx"] = dx.ewm(alpha=1/MR_ADX_PERIOD, min_periods=MR_ADX_PERIOD).mean()

    df["is_range"] = (df["adx"]<MR_MAX_ADX)&(df["ema_conv"]<MR_EMA_CONVERGE_PCT)
    df["mr_long"] = (df["is_range"]&(df["low"]<=df["bb_lower"])&(df["rsi_prev"]<=MR_RSI_OVERSOLD)&(df["rsi"]>df["rsi_prev"])).astype(int)
    df["mr_short"] = (df["is_range"]&(df["high"]>=df["bb_upper"])&(df["rsi_prev"]>=MR_RSI_OVERBOUGHT)&(df["rsi"]<df["rsi_prev"])).astype(int)

    return df


def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    if side == "LONG": return (exit_px-entry)*sz - notional*comm
    else: return (entry-exit_px)*sz - notional*comm


def run_unified_backtest(df, lg):
    """Run both strategies simultaneously with shared capital"""
    cash = INITIAL_CASH
    peak_eq = INITIAL_CASH
    eq = []
    trades = []
    cm = COMM_PCT

    # OCPM state
    o_in = False; o_side=""; o_entry=0; o_ts=""; o_bar=0; o_sz=0; o_stop=0
    o_loss=0; o_cool=0

    # MR state
    m_in = False; m_side=""; m_entry=0; m_ts=""; m_bar=0; m_sz=0; m_stop=0
    m_loss=0; m_cool=0

    for i in range(len(df)):
        r = df.iloc[i]; ts = str(df.index[i])
        px, hi, lo, atr = r["close"], r["high"], r["low"], r["atr"]

        # Total equity
        o_pv = 0
        if o_in:
            o_pv = o_sz * px if o_side=="LONG" else o_sz*(2*o_entry-px)
        m_pv = 0
        if m_in:
            m_pv = m_sz * px if m_side=="LONG" else m_sz*(2*m_entry-px)
        equity = cash + o_pv + m_pv
        peak_eq = max(peak_eq, equity)
        dd = (peak_eq-equity)/peak_eq if peak_eq > 0 else 0
        eq.append(equity)

        if dd >= DD_HALT:
            continue

        # ===== OCPM Management =====
        if o_in:
            held = i - o_bar
            if held >= OCPM_MAX_HOLD:
                pnl = _pnl(o_side, o_entry, px, o_sz, cm)
                cash += o_sz*o_entry + pnl
                trades.append(Trade(o_ts,ts,o_side,"OCPM",o_entry,px,o_sz,pnl,(px/o_entry-1)*100*(1 if o_side=="LONG" else -1),"TIME_EXIT",held))
                if pnl < 0:
                    o_loss += 1
                    if o_loss >= MAX_LOSSES: o_cool = i + COOLDOWN
                else: o_loss = 0
                o_in = False
            elif atr and atr > 0:
                if o_side == "LONG":
                    new_sl = px - OCPM_ATR_SL_MULT*atr
                    if new_sl > o_stop: o_stop = new_sl
                    if lo <= o_stop:
                        pnl = _pnl("LONG",o_entry,o_stop,o_sz,cm)
                        cash += o_sz*o_entry + pnl
                        trades.append(Trade(o_ts,ts,"LONG","OCPM",o_entry,o_stop,o_sz,pnl,(o_stop/o_entry-1)*100,"TRAILING_STOP",held))
                        if pnl < 0:
                            o_loss += 1
                            if o_loss >= MAX_LOSSES: o_cool = i + COOLDOWN
                        else: o_loss = 0
                        o_in = False
                else:
                    new_sl = px + OCPM_ATR_SL_MULT*atr
                    if new_sl < o_stop: o_stop = new_sl
                    if hi >= o_stop:
                        pnl = _pnl("SHORT",o_entry,o_stop,o_sz,cm)
                        cash += o_sz*o_entry + pnl
                        trades.append(Trade(o_ts,ts,"SHORT","OCPM",o_entry,o_stop,o_sz,pnl,(o_entry/o_stop-1)*100,"TRAILING_STOP",held))
                        if pnl < 0:
                            o_loss += 1
                            if o_loss >= MAX_LOSSES: o_cool = i + COOLDOWN
                        else: o_loss = 0
                        o_in = False

                # ATR TP
                tp_px = o_entry + (OCPM_ATR_TP_MULT*atr) if o_side=="LONG" else o_entry - (OCPM_ATR_TP_MULT*atr)
                if (o_side=="LONG" and hi>=tp_px) or (o_side=="SHORT" and lo<=tp_px):
                    pnl = _pnl(o_side,o_entry,tp_px,o_sz,cm)
                    cash += o_sz*o_entry + pnl
                    trades.append(Trade(o_ts,ts,o_side,"OCPM",o_entry,tp_px,o_sz,pnl,(tp_px/o_entry-1)*100*(1 if o_side=="LONG" else -1),"ATR_TP",held))
                    if pnl < 0:
                        o_loss += 1
                        if o_loss >= MAX_LOSSES: o_cool = i + COOLDOWN
                    else: o_loss = 0
                    o_in = False

                # RSI exit
                if o_side=="LONG" and r["rsi"] > 70:
                    pnl = _pnl("LONG",o_entry,px,o_sz,cm)
                    cash += o_sz*o_entry + pnl
                    trades.append(Trade(o_ts,ts,"LONG","OCPM",o_entry,px,o_sz,pnl,(px/o_entry-1)*100,"RSI_EXIT",held))
                    o_in = False; o_loss = 0
                elif o_side=="SHORT" and r["rsi"] < 30:
                    pnl = _pnl("SHORT",o_entry,px,o_sz,cm)
                    cash += o_sz*o_entry + pnl
                    trades.append(Trade(o_ts,ts,"SHORT","OCPM",o_entry,px,o_sz,pnl,(o_entry/px-1)*100,"RSI_EXIT",held))
                    o_in = False; o_loss = 0

        # OCPM Entry
        if not o_in and i >= o_cool and atr and atr > 0:
            if r["ocpm_long"] == 1:
                sl_d = OCPM_ATR_SL_MULT*atr
                risk = cash*RISK_PCT
                sz = min(risk/sl_d, (cash*MAX_POS_PCT)/px)
                if sz*px >= 10 and sz*px*(1+cm) <= cash:
                    cash -= sz*px*(1+cm)
                    o_in=True; o_side="LONG"; o_entry=px; o_ts=ts; o_bar=i; o_sz=sz; o_stop=px-sl_d
            elif r["ocpm_short"] == 1:
                sl_d = OCPM_ATR_SL_MULT*atr
                risk = cash*RISK_PCT
                sz = min(risk/sl_d, (cash*MAX_POS_PCT)/px)
                if sz*px >= 10 and sz*px*(1+cm) <= cash:
                    cash -= sz*px*(1+cm)
                    o_in=True; o_side="SHORT"; o_entry=px; o_ts=ts; o_bar=i; o_sz=sz; o_stop=px+sl_d

        # ===== MR Management =====
        if m_in:
            held = i - m_bar
            if held >= MR_MAX_HOLD:
                pnl = _pnl(m_side, m_entry, px, m_sz, cm)
                cash += m_sz*m_entry + pnl
                trades.append(Trade(m_ts,ts,m_side,"RangeMR",m_entry,px,m_sz,pnl,(px/m_entry-1)*100*(1 if m_side=="LONG" else -1),"TIME_EXIT",held))
                if pnl < 0:
                    m_loss += 1
                    if m_loss >= MAX_LOSSES: m_cool = i + COOLDOWN
                else: m_loss = 0
                m_in = False
            elif atr and atr > 0:
                if m_side == "LONG":
                    if lo <= m_stop:
                        pnl = _pnl("LONG",m_entry,m_stop,m_sz,cm)
                        cash += m_sz*m_entry + pnl
                        trades.append(Trade(m_ts,ts,"LONG","RangeMR",m_entry,m_stop,m_sz,pnl,(m_stop/m_entry-1)*100,"STOP_LOSS",held))
                        if pnl < 0:
                            m_loss += 1
                            if m_loss >= MAX_LOSSES: m_cool = i + COOLDOWN
                        else: m_loss = 0
                        m_in = False
                else:
                    if hi >= m_stop:
                        pnl = _pnl("SHORT",m_entry,m_stop,m_sz,cm)
                        cash += m_sz*m_entry + pnl
                        trades.append(Trade(m_ts,ts,"SHORT","RangeMR",m_entry,m_stop,m_sz,pnl,(m_entry/m_stop-1)*100,"STOP_LOSS",held))
                        if pnl < 0:
                            m_loss += 1
                            if m_loss >= MAX_LOSSES: m_cool = i + COOLDOWN
                        else: m_loss = 0
                        m_in = False

                # TP at BB mid
                if m_side=="LONG" and hi >= r["bb_mid"]:
                    pnl = _pnl("LONG",m_entry,r["bb_mid"],m_sz,cm)
                    cash += m_sz*m_entry + pnl
                    trades.append(Trade(m_ts,ts,"LONG","RangeMR",m_entry,r["bb_mid"],m_sz,pnl,(r["bb_mid"]/m_entry-1)*100,"BB_MID_TP",held))
                    if pnl < 0:
                        m_loss += 1
                        if m_loss >= MAX_LOSSES: m_cool = i + COOLDOWN
                    else: m_loss = 0
                    m_in = False
                elif m_side=="SHORT" and lo <= r["bb_mid"]:
                    pnl = _pnl("SHORT",m_entry,r["bb_mid"],m_sz,cm)
                    cash += m_sz*m_entry + pnl
                    trades.append(Trade(m_ts,ts,"SHORT","RangeMR",m_entry,r["bb_mid"],m_sz,pnl,(m_entry/r["bb_mid"]-1)*100,"BB_MID_TP",held))
                    if pnl < 0:
                        m_loss += 1
                        if m_loss >= MAX_LOSSES: m_cool = i + COOLDOWN
                    else: m_loss = 0
                    m_in = False

        # MR Entry
        if not m_in and i >= m_cool and atr and atr > 0:
            if r["mr_long"] == 1:
                sl_d = MR_ATR_SL_MULT*atr
                risk = cash*RISK_PCT
                sz = min(risk/sl_d, (cash*MAX_POS_PCT)/px)
                if sz*px >= 10 and sz*px*(1+cm) <= cash:
                    cash -= sz*px*(1+cm)
                    m_in=True; m_side="LONG"; m_entry=px; m_ts=ts; m_bar=i; m_sz=sz; m_stop=px-sl_d
            elif r["mr_short"] == 1:
                sl_d = MR_ATR_SL_MULT*atr
                risk = cash*RISK_PCT
                sz = min(risk/sl_d, (cash*MAX_POS_PCT)/px)
                if sz*px >= 10 and sz*px*(1+cm) <= cash:
                    cash -= sz*px*(1+cm)
                    m_in=True; m_side="SHORT"; m_entry=px; m_ts=ts; m_bar=i; m_sz=sz; m_stop=px+sl_d

    # Close final positions
    if o_in:
        lp = df.iloc[-1]["close"]
        pnl = _pnl(o_side, o_entry, lp, o_sz, cm)
        cash += o_sz*o_entry + pnl
        trades.append(Trade(o_ts, str(df.index[-1]), o_side, "OCPM", o_entry, lp, o_sz, pnl, 0, "EOD", 0))
    if m_in:
        lp = df.iloc[-1]["close"]
        pnl = _pnl(m_side, m_entry, lp, m_sz, cm)
        cash += m_sz*m_entry + pnl
        trades.append(Trade(m_ts, str(df.index[-1]), m_side, "RangeMR", m_entry, lp, m_sz, pnl, 0, "EOD", 0))

    return _calc_metrics(cash, trades, eq), trades


def _calc_metrics(final, trades, eq):
    init = INITIAL_CASH
    ret = (final-init)/init*100
    n = len(trades)
    if n == 0:
        return {"final_value":final,"total_return":ret,"total_trades":0,"win_rate":0,"profit_factor":0,
                "max_drawdown":0,"sharpe":0,"avg_win":0,"avg_loss":0,"expectancy":0,"avg_bars":0,
                "sl_rate":0,"tp_rate":0,"long_trades":0,"short_trades":0,"long_wr":0,"short_wr":0,
                "ocpm_trades":0,"ocpm_wr":0,"mr_trades":0,"mr_wr":0}
    pnls = [t.pnl for t in trades]
    w = [p for p in pnls if p>0]; l = [p for p in pnls if p<=0]
    gp, gl = sum(w), abs(sum(l))
    eq_arr = np.array(eq); pk = np.maximum.accumulate(eq_arr)
    mdd = float(((pk-eq_arr)/pk*100).max())
    deq = eq_arr[::6]; sharpe = 0
    if len(deq)>1:
        dr = np.diff(deq)/deq[:-1]; rf = 0.045/365
        sharpe = float((np.mean(dr)-rf)/np.std(dr)*np.sqrt(365)) if np.std(dr)>0 else 0
    longs = [t for t in trades if t.side=="LONG"]; shorts = [t for t in trades if t.side=="SHORT"]
    lw = sum(1 for t in longs if t.pnl>0); sw = sum(1 for t in shorts if t.pnl>0)
    ocpm = [t for t in trades if t.strat=="OCPM"]; mr = [t for t in trades if t.strat=="RangeMR"]
    ow = sum(1 for t in ocpm if t.pnl>0); mw = sum(1 for t in mr if t.pnl>0)
    return {"final_value":final,"total_return":ret,"total_trades":n,"win_rate":len(w)/n*100,
            "profit_factor":gp/gl if gl>0 else float("inf"),"max_drawdown":mdd,"sharpe":sharpe,
            "avg_win":np.mean(w) if w else 0,"avg_loss":np.mean(l) if l else 0,
            "expectancy":np.mean(pnls),"avg_bars":np.mean([t.bars for t in trades]),
            "sl_rate":sum(1 for t in trades if "STOP" in t.reason)/n*100,
            "tp_rate":sum(1 for t in trades if "TP" in t.reason or "BB" in t.reason)/n*100,
            "long_trades":len(longs),"short_trades":len(shorts),
            "long_wr":lw/len(longs)*100 if longs else 0,"short_wr":sw/len(shorts)*100 if shorts else 0,
            "ocpm_trades":len(ocpm),"ocpm_wr":ow/len(ocpm)*100 if ocpm else 0,
            "mr_trades":len(mr),"mr_wr":mw/len(mr)*100 if mr else 0}


def report(m, trades, lg):
    r = f"""
{'='*70}
  Qwen UNIFIED (OCPM + Range MR) - PERFORMANCE REPORT
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
  TP rate        : {m['tp_rate']:.1f}%
  Stop Loss rate : {m['sl_rate']:.1f}%
{'-'*70}
  LONG           : {m['long_trades']} (WR {m['long_wr']:.0f}%)
  SHORT          : {m['short_trades']} (WR {m['short_wr']:.0f}%)
{'='*70}
  OCPM trades    : {m['ocpm_trades']} (WR {m['ocpm_wr']:.0f}%)
  RangeMR trades : {m['mr_trades']} (WR {m['mr_wr']:.0f}%)
{'='*70}"""

    checks = [("Return > 0%",m["total_return"]>0,f"{m['total_return']:+.2f}%"),
              ("MaxDD < 15%",m["max_drawdown"]<15,f"{m['max_drawdown']:.2f}%"),
              ("PF > 1.2",m["profit_factor"]>1.2,f"{m['profit_factor']:.2f}"),
              ("EV > $0",m["expectancy"]>0,f"${m['expectancy']:+,.2f}"),
              ("WR > 50%",m["win_rate"]>50,f"{m['win_rate']:.1f}%")]

    r += f"\n\n{'='*70}\n GO CHECK\n{'='*70}"
    for nm,ok,v in checks: r += f"\n  {'PASS' if ok else 'FAIL'} {nm}: {v}"
    p = sum(1 for _,ok,_ in checks if ok)
    r += f"\n\n  Score: {p}/{len(checks)}"
    r += f"\n  {'>>> GO <<<' if p==len(checks) else '>>> CONDITIONAL <<<' if p>=3 else '>>> STOP <<<' }"
    r += f"\n{'='*70}"
    print(r); lg.info(r)

    if trades:
        print(f"\n{'='*110}")
        print(f"  {'Time':<20} {'Strat':<8} {'Side':<6} {'Type':<14} {'Entry':>10} {'Exit':>10} {'PnL%':>8} {'PnL$':>12} {'Bars':>5}")
        print(f"{'-'*110}")
        for t in trades:
            print(f"  {t.t_out[:16]:<20} {t.strat:<8} {t.side:<6} {t.reason:<14} {t.p_in:>10.2f} {t.p_out:>10.2f} {t.pnl_pct:>+7.2f}% ${t.pnl:>+10.2f} {t.bars:>5}")
        print(f"{'='*110}")
        
        # Save trades to JSON for lightweight-charts
        import json
        from dataclasses import asdict
        trades_data = [asdict(t) for t in trades]
        with open('backtest_trades_history.json', 'w') as f:
            json.dump(trades_data, f, indent=2)


def setup_logging(debug=False):
    Path("logs").mkdir(exist_ok=True)
    lg = logging.getLogger("Unified")
    lg.setLevel(logging.DEBUG); lg.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(f"logs/unified_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
    fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)
    ch = logging.StreamHandler(); ch.setLevel(logging.DEBUG if debug else logging.INFO); ch.setFormatter(fmt)
    lg.addHandler(fh); lg.addHandler(ch)
    return lg


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument("--days", type=int, default=730)
    pa.add_argument("--timeframe", type=str, default="4h")
    pa.add_argument("--debug", action="store_true")
    args = pa.parse_args()

    lg = setup_logging(args.debug)
    lg.info(f"Qwen Unified Backtest (OCPM + RangeMR) | Days: {args.days}")

    cache = f"btc_usdt_{args.timeframe}_unified.csv"
    df = fetch_ohlcv(args.days, args.timeframe, cache)
    df = compute_all(df)

    lg.info(f"Data: {df.index[0]} -> {df.index[-1]} ({len(df)} bars)")
    lg.info(f"OCPM signals: L={df['ocpm_long'].sum()} S={df['ocpm_short'].sum()}")
    lg.info(f"MR signals: L={df['mr_long'].sum()} S={df['mr_short'].sum()}")

    m, trades = run_unified_backtest(df, lg)
    report(m, trades, lg)

if __name__ == "__main__":
    main()
