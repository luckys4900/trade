import json, sys
path='vsrev_enhanced_20260427_005929.json'
with open(path, encoding='utf-8') as f:
    data=json.load(f)
pos=[r for r in data if r.get('ev') and r['ev']['ev']>0]
pos.sort(key=lambda x: x['ev']['ev'], reverse=True)
for r in pos[:30]:
    label=r['label']
    ev=r['ev']['ev']
    ret=r['ret']
    sharpe=r['sharpe']
    dd=r['dd']
    wr=r['wr']
    pf=r['ev']['pf']
    print(f"{label} | EV={ev:.4f} | Ret={ret:.2f}% | Sharpe={sharpe} | DD={dd:.2f}% | WR={wr}% | PF={pf}")