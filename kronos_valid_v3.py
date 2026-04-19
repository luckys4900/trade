import numpy as np, pandas as pd, json

INITIAL_CASH = 200.0; COMM_PCT = 0.0005; RISK_PCT = 0.02; MAX_POS_PCT = 0.40

def prep_df(path):
    df=pd.read_csv(path,parse_dates=["datetime"],index_col="datetime").sort_index()
    df.columns=[c.lower() for c in df.columns]
    df=df.reset_index(drop=False)
    delta=df["close"].diff(); g=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    l=(-delta).clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    df["rsi"]=100-100/(1+g/l.replace(0,np.nan))
    tr=pd.concat([df["high"]-df["low"],(df["high"]-df["close"].shift(1)).abs(),(df["low"]-df["close"].shift(1)).abs()],axis=1).max(axis=1)
    df["atr"]=tr.ewm(alpha=1/14,min_periods=14).mean()
    df["ma50"]=df["close"].rolling(50).mean()
    df["trend"]="RANGE"; df.loc[df["close"]>df["ma50"],"trend"]="UPTREND"; df.loc[df["close"]<df["ma50"],"trend"]="DOWNTREND"
    df["vol_pct"]=df["close"].pct_change().abs().rolling(50).rank(pct=True)*100
    return df

def _pnl(s,e,x,sz,c):
    n=sz*x; return (x-e)*sz-n*c if s=="LONG" else (e-x)*sz-n*c

def bt(df,sig,sl=2.0,tp=4.0,hd=8):
    cash=INITIAL_CASH; pk_=INITIAL_CASH; eq=[]; trades=[]
    inp=False; side=""; ent=0; bi=0; sz=0; st=0
    for i in range(len(df)):
        r=df.iloc[i]; px,hi,lo,atr=r["close"],r["high"],r["low"],r["atr"]
        pv=sz*px if inp and side=="LONG" else sz*(2*ent-px) if inp else 0
        eq_=cash+pv; pk_=max(pk_,eq_); eq.append(eq_)
        if inp:
            h=i-bi
            if h>=hd:
                p=_pnl(side,ent,px,sz,COMM_PCT); cash+=sz*ent+p; trades.append({"pnl":p,"reason":"TIME"}); inp=False
            elif atr and atr>0:
                if side=="LONG":
                    if lo<=st: p=_pnl("LONG",ent,st,sz,COMM_PCT); cash+=sz*ent+p; trades.append({"pnl":p,"reason":"SL"}); inp=False
                    elif hi>=ent+tp*atr: p=_pnl("LONG",ent,ent+tp*atr,sz,COMM_PCT); cash+=sz*ent+p; trades.append({"pnl":p,"reason":"TP"}); inp=False
                else:
                    if hi>=st: p=_pnl("SHORT",ent,st,sz,COMM_PCT); cash+=sz*ent+p; trades.append({"pnl":p,"reason":"SL"}); inp=False
                    elif lo<=ent-tp*atr: p=_pnl("SHORT",ent,ent-tp*atr,sz,COMM_PCT); cash+=sz*ent+p; trades.append({"pnl":p,"reason":"TP"}); inp=False
        if not inp and atr and atr>0 and i<len(sig) and sig[i]!=0:
            sld=sl*atr; risk=cash*RISK_PCT; sz2=min(risk/sld,(cash*MAX_POS_PCT)/px)
            if sz2*px>=10 and sz2*px*(1+COMM_PCT)<=cash:
                cash-=sz2*px*(1+COMM_PCT); inp=True
                side="LONG" if sig[i]==1 else "SHORT"; ent=px; bi=i; sz=sz2
                st=px-sld if sig[i]==1 else px+sld
    if inp: p=_pnl(side,ent,df.iloc[-1]["close"],sz,COMM_PCT); cash+=sz*ent+p
    return met(cash,trades,eq)

def met(final,trades,eq):
    ret=(final-INITIAL_CASH)/INITIAL_CASH*100; n=len(trades)
    if n==0: return {"ret":ret,"trades":0,"wr":0,"pf":0,"mdd":0}
    pnls=[t["pnl"] for t in trades]; w=[p for p in pnls if p>0]; l=[p for p in pnls if p<=0]
    gp,gl=sum(w),abs(sum(l))
    ea=np.array(eq); pk=np.maximum.accumulate(ea); mdd=float(((pk-ea)/pk*100).max())
    return {"ret":ret,"trades":n,"wr":len(w)/n*100,"pf":gp/gl if gl>0 else 99,"mdd":mdd}

def fm(m):
    return "{:+.1f}% | PF {:.2f} | WR {:.1f}% | DD {:.1f}% | {}t".format(m["ret"],m["pf"],m["wr"],m["mdd"],m["trades"])

def make_sig(len_df, pdf, rsi_col=None, rsi_lo=0, rsi_hi=100, trend_f=None):
    sig=np.zeros(len_df,dtype=int)
    for _,r in pdf.iterrows():
        i=int(r["bar"])
        if i>=len_df: continue
        sig[i]=-int(r["dir"])
    return sig

def main():
    df4=prep_df("btc_usdt_4h_unified.csv")
    pdf=pd.read_csv("kronos_4h_preds_full.csv")
    n4=len(df4)
    mid=n4//2
    print("4h: {} bars, {} preds, mid={}".format(n4,len(pdf),mid))

    df4a=df4.iloc[:mid].copy().reset_index(drop=True)
    df4b=df4.iloc[mid:].copy().reset_index(drop=True)
    pdf_a=pdf[pdf["bar"]<mid].copy()
    pdf_b=pdf[(pdf["bar"]>=mid)].copy()
    pdf_b_shifted=pdf_b.copy()
    pdf_b_shifted["bar"]=pdf_b_shifted["bar"]-mid
    print("H1: {} bars, {} preds".format(len(df4a),len(pdf_a)))
    print("H2: {} bars, {} preds".format(len(df4b),len(pdf_b_shifted)))

    # Full
    sf=make_sig(n4,pdf)
    mf=bt(df4,sf)
    print("\n=== 4h FULL ===")
    print("  {}".format(fm(mf)))

    # H1
    s1=make_sig(len(df4a),pdf_a)
    m1=bt(df4a,s1)
    print("\n=== 4h H1 ({} to {}) ===".format(df4.iloc[0].get("datetime","?"),df4.iloc[mid-1].get("datetime","?")))
    print("  {}".format(fm(m1)))

    # H2
    s2=make_sig(len(df4b),pdf_b_shifted)
    m2=bt(df4b,s2)
    print("\n=== 4h H2 ({} to {}) ===".format(df4.iloc[mid].get("datetime","?"),df4.iloc[-1].get("datetime","?")))
    print("  {}".format(fm(m2)))

    # Param sweep
    print("\n=== PARAM SWEEP ===")
    best_ret=-999; best_p=(2,4,8)
    for sl,tp,hd in [(1.5,3,6),(2,4,8),(2.5,5,10),(3,6,12),(1.5,4,8),(2,3,6)]:
        m=bt(df4,sf,sl,tp,hd)
        print("  SL={} TP={} H={} | {}".format(sl,tp,hd,fm(m)))
        if m["ret"]>best_ret: best_ret=m["ret"]; best_p=(sl,tp,hd)
    print("  Best: SL={} TP={} H={}".format(*best_p))

    # Filter sweep with best params
    print("\n=== FILTER SWEEP (best params) ===")
    for name,rl,rh,tf in [("No filter",0,100,None),("RSI 30-70",30,70,None),("RSI 35-65",35,65,None),
                           ("UPTREND",0,100,"UPTREND"),("DOWNTREND",0,100,"DOWNTREND"),
                           ("RSI30-70+DOWN",30,70,"DOWNTREND")]:
        sig=np.zeros(n4,dtype=int)
        for _,r in pdf.iterrows():
            i=int(r["bar"]); rsi=df4.iloc[i]["rsi"]; t=df4.iloc[i]["trend"]
            if rsi<rl or rsi>=rh: continue
            if tf and t!=tf: continue
            sig[i]=-int(r["dir"])
        m=bt(df4,sig,best_p[0],best_p[1],best_p[2])
        print("  {:<20} | {}".format(name,fm(m)))

    # 1h last 6 months
    print("\n=== 1h LAST 6 MONTHS ===")
    import sys,os; sys.path.insert(0,"Kronos")
    import torch
    from model import Kronos,KronosTokenizer,KronosPredictor
    dev="cuda:0" if torch.cuda.is_available() else "cpu"
    tok=KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    mod=Kronos.from_pretrained("NeoQuasar/Kronos-base")
    predictor=KronosPredictor(mod,tok,device=dev,max_context=512)

    df1=prep_df("btc_usdt_1h_kronos.csv")
    cutoff_idx=df1.index[-1]-pd.Timedelta(days=180)
    # Find the iloc index for cutoff
    cutoff_iloc=df1.index.get_indexer([cutoff_idx],method="nearest")[0]
    df1s=df1.iloc[cutoff_iloc:].copy().reset_index(drop=True)
    print("1h: {} bars".format(len(df1s)))

    preds_1h=[]; last=-999
    for i in range(400,len(df1s)):
        if i-last<8: continue
        last=i
        try:
            s=i-400
            x=df1s.iloc[s:i][["open","high","low","close","volume"]].copy()
            x["amount"]=x["volume"]*x[["open","high","low","close"]].mean(axis=1)
            xt=pd.Series(range(len(x)))
            yt=pd.Series([len(x)])
            # Need actual timestamps
            dt_series=df1s["datetime"].iloc[s:i]
            yt_ts=pd.Series([df1s["datetime"].iloc[i]])
            p=predictor.predict(df=x.reset_index(drop=True),x_timestamp=pd.to_datetime(dt_series).reset_index(drop=True),
                               y_timestamp=pd.to_datetime(yt_ts),pred_len=1,T=0.8,top_p=0.6,sample_count=10,verbose=False)
            pc=p.iloc[0]["close"]; prev=df1s.iloc[i-1]["close"]
            preds_1h.append({"bar":i,"dir":1 if pc>prev else -1})
        except: continue
    print("  1h preds: {}".format(len(preds_1h)))
    p1h=pd.DataFrame(preds_1h)
    s1h=np.zeros(len(df1s),dtype=int)
    for _,r in p1h.iterrows(): s1h[int(r["bar"])]=-int(r["dir"])
    m1h=bt(df1s,s1h,best_p[0],best_p[1],best_p[2])
    print("  1h: {}".format(fm(m1h)))

    # Summary
    print("\n"+"="*70)
    print("  FINAL VALIDATION SUMMARY")
    print("="*70)
    print("  OCPM+MR (existing): +6.5% | PF 1.23 | WR 55.6%")
    print("  4h Full:  {}".format(fm(mf)))
    print("  4h H1:    {}".format(fm(m1)))
    print("  4h H2:    {}".format(fm(m2)))
    print("  1h 6mo:   {}".format(fm(m1h)))

    robust=m1["ret"]>0 and m2["ret"]>0 and m1h["ret"]>0
    if robust:
        print("\n  >>> ROBUST: All splits positive <<<")
    else:
        fails=[]
        if m1["ret"]<=0: fails.append("H1({:+.1f}%)".format(m1["ret"]))
        if m2["ret"]<=0: fails.append("H2({:+.1f}%)".format(m2["ret"]))
        if m1h["ret"]<=0: fails.append("1h({:+.1f}%)".format(m1h["ret"]))
        print("\n  >>> NOT ROBUST: {} <<<".format(", ".join(fails)))

    json.dump({"full":mf,"h1":m1,"h2":m2,"1h":m1h,"best":list(best_p),"robust":robust},
              open("kronos_validation_final.json","w"),indent=2)

if __name__=="__main__":
    main()
