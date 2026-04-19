# -*- coding: utf-8 -*-
"""
Kronos Contrarian Validation - Optimized for speed
"""
import sys, os, time, json
import numpy as np
import pandas as pd
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Kronos"))
import torch
from model import Kronos, KronosTokenizer, KronosPredictor

INITIAL_CASH = 200.0
COMM_PCT = 0.0005
RISK_PCT = 0.02
MAX_POS_PCT = 0.40

@dataclass
class Trade:
    t_in: str; t_out: str; side: str; strat: str
    p_in: float; p_out: float; sz: float; pnl: float
    pnl_pct: float; reason: str; bars: int = 0

def compute_indicators(df):
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    tr = pd.concat([df["high"]-df["low"],(df["high"]-df["close"].shift(1)).abs(),(df["low"]-df["close"].shift(1)).abs()],axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, min_periods=14).mean()
    df["ma50"] = df["close"].rolling(50).mean()
    df["trend"] = "RANGE"
    df.loc[df["close"]>df["ma50"],"trend"]="UPTREND"
    df.loc[df["close"]<df["ma50"],"trend"]="DOWNTREND"
    df["vol_pct"] = df["close"].pct_change().abs().rolling(50).rank(pct=True)*100
    return df

def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    return (exit_px-entry)*sz - notional*comm if side=="LONG" else (entry-exit_px)*sz - notional*comm

def run_backtest(df, signals, sl_mult=2.0, tp_mult=4.0, max_hold=8):
    cash = INITIAL_CASH; peak_eq = INITIAL_CASH; eq = []; trades = []
    in_pos = False; side = ""; entry = 0; ts_in = ""; bar_in = 0; sz = 0; stop = 0
    for i in range(len(df)):
        r = df.iloc[i]; ts = str(df.index[i]); px,hi,lo,atr = r["close"],r["high"],r["low"],r["atr"]
        pv = sz*px if in_pos and side=="LONG" else sz*(2*entry-px) if in_pos else 0
        equity = cash + pv; peak_eq = max(peak_eq, equity); eq.append(equity)
        if in_pos:
            held = i - bar_in
            if held >= max_hold:
                pnl = _pnl(side,entry,px,sz,COMM_PCT); cash += sz*entry+pnl
                trades.append(Trade(ts_in,ts,side,"",entry,px,sz,pnl,(px/entry-1)*100,"TIME",held)); in_pos=False
            elif atr and atr > 0:
                if side=="LONG":
                    if lo<=stop: pnl=_pnl("LONG",entry,stop,sz,COMM_PCT); cash+=sz*entry+pnl; trades.append(Trade(ts_in,ts,"LONG","",entry,stop,sz,pnl,0,"SL",held)); in_pos=False
                    else:
                        tp=entry+tp_mult*atr
                        if hi>=tp: pnl=_pnl("LONG",entry,tp,sz,COMM_PCT); cash+=sz*entry+pnl; trades.append(Trade(ts_in,ts,"LONG","",entry,tp,sz,pnl,0,"TP",held)); in_pos=False
                else:
                    if hi>=stop: pnl=_pnl("SHORT",entry,stop,sz,COMM_PCT); cash+=sz*entry+pnl; trades.append(Trade(ts_in,ts,"SHORT","",entry,stop,sz,pnl,0,"SL",held)); in_pos=False
                    else:
                        tp=entry-tp_mult*atr
                        if lo<=tp: pnl=_pnl("SHORT",entry,tp,sz,COMM_PCT); cash+=sz*entry+pnl; trades.append(Trade(ts_in,ts,"SHORT","",entry,tp,sz,pnl,0,"TP",held)); in_pos=False
        if not in_pos and atr and atr>0:
            if signals[i]!=0:
                sl_d = sl_mult*atr; risk = cash*RISK_PCT; sz2 = min(risk/sl_d,(cash*MAX_POS_PCT)/px)
                if sz2*px>=10 and sz2*px*(1+COMM_PCT)<=cash:
                    cash -= sz2*px*(1+COMM_PCT); in_pos=True; side="LONG" if signals[i]==1 else "SHORT"
                    entry=px; ts_in=ts; bar_in=i; sz=sz2; stop=px-sl_d if signals[i]==1 else px+sl_d
    if in_pos:
        lp=df.iloc[-1]["close"]; pnl=_pnl(side,entry,lp,sz,COMM_PCT); cash+=sz*entry+pnl
    return _metrics(cash,trades,eq)

def _metrics(final, trades, eq):
    ret = (final-INITIAL_CASH)/INITIAL_CASH*100; n = len(trades)
    if n==0: return {"ret":ret,"trades":0,"wr":0,"pf":0,"mdd":0,"sharpe":0}
    pnls=[t.pnl for t in trades]; w=[p for p in pnls if p>0]; l=[p for p in pnls if p<=0]
    gp,gl=sum(w),abs(sum(l))
    eq_a=np.array(eq); pk=np.maximum.accumulate(eq_a); mdd=float(((pk-eq_a)/pk*100).max())
    return {"ret":ret,"trades":n,"wr":len(w)/n*100,"pf":gp/gl if gl>0 else 99,"mdd":mdd,"sharpe":0}

def fmt(m):
    return "{:+.1f}% | PF {:.2f} | WR {:.1f}% | DD {:.1f}% | {}t".format(m["ret"],m["pf"],m["wr"],m["mdd"],m["trades"])

def run_preds(df, predictor, lookback, step, nsamples):
    preds=[]; last=-999; total=0
    for i in range(lookback, len(df)):
        if i-last<step: continue
        last=i; total+=1
        if total%200==0: print("    p{} b{}/{}".format(total,i,len(df)))
        try:
            s=i-lookback
            x=df.iloc[s:i][["open","high","low","close","volume"]].copy()
            x["amount"]=x["volume"]*x[["open","high","low","close"]].mean(axis=1)
            xt=pd.Series(df.index[s:i])
            fi=list(range(i,min(i+1,len(df))))
            if len(fi)<1: continue
            yt=pd.Series([df.index[j] for j in fi])
            p=predictor.predict(df=x.reset_index(drop=True),x_timestamp=xt,y_timestamp=yt,pred_len=1,T=0.8,top_p=0.6,sample_count=nsamples,verbose=False)
            pc=p.iloc[0]["close"]; prev=df.iloc[i-1]["close"]
            preds.append({"bar":i,"dir":1 if pc>prev else -1})
        except: continue
    return pd.DataFrame(preds)

def main():
    dev="cuda:0" if torch.cuda.is_available() else "cpu"
    print("Dev:",dev)
    tok=KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    mod=Kronos.from_pretrained("NeoQuasar/Kronos-base")
    pred=KronosPredictor(mod,tok,device=dev,max_context=512)

    df4=pd.read_csv("btc_usdt_4h_unified.csv",parse_dates=["datetime"],index_col="datetime").sort_index()
    df4.columns=[c.lower() for c in df4.columns]; df4=compute_indicators(df4)
    print("4h: {} bars".format(len(df4)))

    mid=len(df4)//2
    df4a=df4.iloc[:mid].copy(); df4b=df4.iloc[mid:].copy()
    print("H1: {} bars, H2: {} bars".format(len(df4a),len(df4b)))

    # --- 4h full ---
    print("\n=== 4h FULL ===")
    t0=time.time(); pf=run_preds(df4,pred,400,2,30); print("  {:.0f}s".format(time.time()-t0))
    sf=np.zeros(len(df4),dtype=int)
    for _,r in pf.iterrows(): sf[int(r["bar"])]=-int(r["dir"])
    mf=run_backtest(df4,sf); print("  Full: {}".format(fmt(mf)))

    # --- 4h H1 ---
    print("\n=== 4h FIRST HALF ===")
    t0=time.time(); p1=run_preds(df4a,pred,400,2,30); print("  {:.0f}s".format(time.time()-t0))
    s1=np.zeros(len(df4a),dtype=int)
    for _,r in p1.iterrows(): s1[int(r["bar"])]=-int(r["dir"])
    m1=run_backtest(df4a,s1); print("  H1: {}".format(fmt(m1)))

    # --- 4h H2 ---
    print("\n=== 4h SECOND HALF ===")
    t0=time.time(); p2=run_preds(df4b,pred,400,2,30); print("  {:.0f}s".format(time.time()-t0))
    s2=np.zeros(len(df4b),dtype=int)
    for _,r in p2.iterrows(): s2[int(r["bar"])]=-int(r["dir"])
    m2=run_backtest(df4b,s2); print("  H2: {}".format(fmt(m2)))

    # --- Param sweep ---
    print("\n=== PARAM SWEEP ===")
    best_ret=-999; best_p=None
    for sl,tp,hd in [(1.5,3,6),(2,4,8),(2.5,5,10),(3,6,12),(1.5,4,8),(2,3,6)]:
        m=run_backtest(df4,sf,sl,tp,hd)
        print("  SL={} TP={} H={} | {}".format(sl,tp,hd,fmt(m)))
        if m["ret"]>best_ret: best_ret=m["ret"]; best_p=(sl,tp,hd)
    print("  Best: SL={} TP={} H={}".format(*best_p))

    # --- Filter sweep ---
    print("\n=== FILTER SWEEP ===")
    filters=[
        ("No filter",0,100,None),
        ("RSI 30-70",30,70,None),
        ("RSI 35-65",35,65,None),
        ("RSI 40-60",40,60,None),
        ("UPTREND",0,100,["UPTREND"]),
        ("DOWNTREND",0,100,["DOWNTREND"]),
        ("RSI30-70+UP",30,70,["UPTREND"]),
    ]
    for name,rsi_lo,rsi_hi,trend_f in filters:
        sig=np.zeros(len(df4),dtype=int)
        for _,r in pf.iterrows():
            i=int(r["bar"]); rsi=df4.iloc[i]["rsi"]; t=df4.iloc[i]["trend"]
            if rsi<rsi_lo or rsi>=rsi_hi: continue
            if trend_f and t not in trend_f: continue
            sig[i]=-int(r["dir"])
        m=run_backtest(df4,sig,best_p[0],best_p[1],best_p[2])
        print("  {:<20} | {}".format(name,fmt(m)))

    # --- 1h last 6 months ---
    print("\n=== 1h LAST 6 MONTHS ===")
    df1=pd.read_csv("btc_usdt_1h_kronos.csv",parse_dates=["datetime"],index_col="datetime").sort_index()
    df1.columns=[c.lower() for c in df1.columns]
    cutoff=df1.index[-1]-pd.Timedelta(days=180)
    df1s=df1[df1.index>=cutoff].copy()
    df1s=compute_indicators(df1s)
    print("1h subset: {} -> {} ({} bars)".format(df1s.index[0],df1s.index[-1],len(df1s)))
    t0=time.time(); p1h=run_preds(df1s,pred,400,8,10); print("  {:.0f}s".format(time.time()-t0))
    s1h=np.zeros(len(df1s),dtype=int)
    for _,r in p1h.iterrows(): s1h[int(r["bar"])]=-int(r["dir"])
    m1h=run_backtest(df1s,s1h,best_p[0],best_p[1],best_p[2])
    print("  1h: {}".format(fmt(m1h)))

    # --- Summary ---
    print("\n"+"="*70)
    print("  VALIDATION SUMMARY")
    print("="*70)
    print("  OCPM+MR (existing): +6.5% | PF 1.23 | WR 55.6%")
    print("  4h Full:            {}".format(fmt(mf)))
    print("  4h H1 (early):      {}".format(fmt(m1)))
    print("  4h H2 (recent):     {}".format(fmt(m2)))
    print("  1h 6mo:             {}".format(fmt(m1h)))
    print("  Best params: SL={} TP={} Hold={}".format(*best_p))

    robust = m1["ret"]>0 and m2["ret"]>0 and m1h["ret"]>0
    if robust:
        print("\n  >>> ROBUST: All periods positive <<<")
    else:
        fails=[]
        if m1["ret"]<=0: fails.append("H1")
        if m2["ret"]<=0: fails.append("H2")
        if m1h["ret"]<=0: fails.append("1h")
        print("\n  >>> NOT ROBUST: {} negative <<<".format(",".join(fails)))

    json.dump({"full":mf,"h1":m1,"h2":m2,"1h":m1h,"best_params":best_p,"robust":robust},
              open("kronos_validation_final.json","w"),indent=2)


if __name__=="__main__":
    main()
