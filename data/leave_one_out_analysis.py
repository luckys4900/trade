"""
イベント除外感応度分析 (Leave-One-Out Analysis)
8イベントのうち、どのイベントが結果を支配しているかを特定する。
"""

import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DATA_PATH = "C:/Users/user/Desktop/cursor/trade/data/clarity_act_v2_results.json"

with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# =========================================================================
# ヘルパー: event_summaries から Leave-One-Out 分析
# =========================================================================
def leave_one_out_analysis(setting_name, event_summaries, aggregate):
    """
    各イベントの total_pnl を使って、1イベント除外時の残り7イベントのEVを計算。

    EV = total_pnl_remaining / n_remaining
    """
    events = list(event_summaries.keys())

    # 各イベントの total_pnl と n (トレード数)
    event_data = {}
    for ev in events:
        m = event_summaries[ev]["metrics"]
        event_data[ev] = {
            "total_pnl": m["total_pnl"],
            "n": m["n"],
            "ev": m["ev"],
            "wr": m["wr"],
            "pf": m["pf"],
            "sharpe": m["sharpe"],
        }

    # ベースライン (全8イベント)
    total_pnl_all = sum(d["total_pnl"] for d in event_data.values())
    n_all = sum(d["n"] for d in event_data.values())
    ev_baseline = total_pnl_all / n_all if n_all > 0 else 0

    # 計算確認: aggregate の total_pnl / n と一致するか
    agg_ev = aggregate["total_pnl"] / aggregate["n"]

    print(f"\n{'='*80}")
    print(f"  設定: {setting_name}")
    print(f"{'='*80}")
    print(f"  Aggregate EV:   {aggregate['ev']:.4f}  (total_pnl={aggregate['total_pnl']:.4f}, n={aggregate['n']})")
    print(f"  計算 EV (sum/N): {agg_ev:.4f}  (total_pnl_sum={total_pnl_all:.4f}, n_sum={n_all})")
    print(f"  差分 (データ不整合等): {abs(agg_ev - aggregate['ev']):.6f}")

    # -----------------------------------------------------------
    # 1) 各イベントの個別EV (そのイベント単体のパフォーマンス)
    # -----------------------------------------------------------
    print(f"\n  --- 各イベントの個別パフォーマンス ---")
    print(f"  {'イベント':<35s} {'N':>3s} {'EV':>8s} {'WR':>7s} {'PF':>7s} {'PnL':>10s}")
    print(f"  {'-'*75}")

    positive_events = []
    negative_events = []

    for ev in events:
        d = event_data[ev]
        marker = " + " if d["ev"] >= 0 else " - "
        print(f"  {marker}{ev:<32s} {d['n']:>3d} {d['ev']:>8.4f} {d['wr']:>7.2f} {d['pf']:>7.4f} {d['total_pnl']:>10.4f}")
        if d["ev"] >= 0:
            positive_events.append((ev, d))
        else:
            negative_events.append((ev, d))

    # -----------------------------------------------------------
    # 2) イベント独立性評価
    # -----------------------------------------------------------
    print(f"\n  --- イベント独立性評価 ---")
    print(f"  正のEVイベント: {len(positive_events)} / {len(events)}")
    print(f"  負のEVイベント: {len(negative_events)} / {len(events)}")

    if positive_events:
        avg_ev_pos = sum(d["ev"] for _, d in positive_events) / len(positive_events)
        avg_pnl_pos = sum(d["total_pnl"] for _, d in positive_events) / len(positive_events)
        print(f"  正のEV平均:     {avg_ev_pos:.4f}")
        print(f"  正のPnL合計:    {sum(d['total_pnl'] for _, d in positive_events):.4f}")
    if negative_events:
        avg_ev_neg = sum(d["ev"] for _, d in negative_events) / len(negative_events)
        avg_pnl_neg = sum(d["total_pnl"] for _, d in negative_events) / len(negative_events)
        print(f"  負のEV平均:     {avg_ev_neg:.4f}")
        print(f"  負のPnL合計:    {sum(d['total_pnl'] for _, d in negative_events):.4f}")

    # -----------------------------------------------------------
    # 3) Leave-One-Out 分析
    # -----------------------------------------------------------
    print(f"\n  --- Leave-One-Out 感応度分析 ---")
    print(f"  {'除外イベント':<35s} {'残N':>4s} {'残EV':>8s} {'残PnL':>10s} {'EV変化':>9s} {'影響度':>9s}")
    print(f"  {'-'*80}")

    loo_results = []

    # ベースライン行
    print(f"  {'(ベースライン: 全8イベント)':<35s} {n_all:>4d} {ev_baseline:>8.4f} {total_pnl_all:>10.4f} {'---':>9s} {'---':>9s}")

    for ev in events:
        d = event_data[ev]
        remaining_pnl = total_pnl_all - d["total_pnl"]
        remaining_n = n_all - d["n"]
        remaining_ev = remaining_pnl / remaining_n if remaining_n > 0 else 0
        ev_change = remaining_ev - ev_baseline
        # 影響度: そのイベントが貢献しているEV (そのイベントのPnL / そのイベントのN - 残りEV)
        contribution = d["ev"] - remaining_ev

        loo_results.append({
            "excluded": ev,
            "remaining_n": remaining_n,
            "remaining_ev": remaining_ev,
            "remaining_pnl": remaining_pnl,
            "ev_change": ev_change,
            "contribution": contribution,
            "individual_ev": d["ev"],
            "individual_pnl": d["total_pnl"],
        })

        direction = "UP" if ev_change > 0 else "DOWN"
        print(f"  {ev:<35s} {remaining_n:>4d} {remaining_ev:>8.4f} {remaining_pnl:>10.4f} {ev_change:>+9.4f} {direction:>9s}")

    # -----------------------------------------------------------
    # 4) 影響度ランキング
    # -----------------------------------------------------------
    # 除外するとEVが下がる = そのイベントがプラスに貢献している
    # 除外するとEVが上がる = そのイベントがマイナスに貢献している
    ranked = sorted(loo_results, key=lambda x: x["ev_change"])  # ev_change が負 = 外すと下がる = プラス貢献

    print(f"\n  --- 影響度ランキング (除外でEVが下がる=プラス貢献が大きい順) ---")
    print(f"  {'順位':>4s} {'イベント':<35s} {'EV変化':>9s} {'個別EV':>8s} {'個別PnL':>10s}")
    print(f"  {'-'*70}")

    for i, r in enumerate(ranked, 1):
        print(f"  {i:>4d}  {r['excluded']:<35s} {r['ev_change']:>+9.4f} {r['individual_ev']:>8.4f} {r['individual_pnl']:>10.4f}")

    # 最も影響の大きいイベント
    most_positive = ranked[0]   # 外すと一番EVが下がる
    most_negative = ranked[-1]  # 外すと一番EVが上がる

    print(f"\n  [最大プラス貢献] {most_positive['excluded']}")
    print(f"    個別EV: {most_positive['individual_ev']:.4f}, 個別PnL: {most_positive['individual_pnl']:.4f}")
    print(f"    除外時EV変化: {most_positive['ev_change']:+.4f} (除外でEVが下がる = プラス貢献)")

    print(f"\n  [最大マイナス貢献] {most_negative['excluded']}")
    print(f"    個別EV: {most_negative['individual_ev']:.4f}, 個別PnL: {most_negative['individual_pnl']:.4f}")
    print(f"    除外時EV変化: {most_negative['ev_change']:+.4f} (除外でEVが上がる = マイナス貢献)")

    # -----------------------------------------------------------
    # 5) 集中度評価 (HHI的な指標)
    # -----------------------------------------------------------
    total_abs_pnl = sum(abs(d["total_pnl"]) for d in event_data.values())
    print(f"\n  --- PnL集中度分析 ---")
    print(f"  総PnL絶対値: {total_abs_pnl:.4f}")
    for ev in events:
        d = event_data[ev]
        share = abs(d["total_pnl"]) / total_abs_pnl * 100 if total_abs_pnl > 0 else 0
        print(f"    {ev:<35s}: PnL={d['total_pnl']:>+10.4f}  (集中度 {share:>5.1f}%)")

    # トップ1/2/3イベントの累積集中度
    sorted_by_abs = sorted(event_data.items(), key=lambda x: abs(x[1]["total_pnl"]), reverse=True)
    cum_share = 0
    print(f"\n  累積集中度:")
    for i, (ev, d) in enumerate(sorted_by_abs[:5], 1):
        share = abs(d["total_pnl"]) / total_abs_pnl * 100
        cum_share += share
        print(f"    トップ{i}: {ev} → 累積 {cum_share:.1f}%")

    return loo_results


# =========================================================================
# メイン分析
# =========================================================================

# FIXED_FULL
fixed_full = data["FIXED_FULL"]
loo_ff = leave_one_out_analysis("FIXED_FULL", fixed_full["event_summaries"], fixed_full["aggregate"])

# BASELINE (old logic)
baseline = data["BASELINE (old logic)"]
loo_bl = leave_one_out_analysis("BASELINE (old logic)", baseline["event_summaries"], baseline["aggregate"])

# =========================================================================
# クロス設定比較
# =========================================================================
print(f"\n{'='*80}")
print(f"  クロス設定比較サマリー")
print(f"{'='*80}")

ff_events = list(fixed_full["event_summaries"].keys())
bl_events = list(baseline["event_summaries"].keys())

print(f"\n  {'イベント':<35s} {'FIXED_FULL EV':>14s} {'BASELINE EV':>13s} {'差分':>8s}")
print(f"  {'-'*72}")

for ev in ff_events:
    ff_ev = fixed_full["event_summaries"][ev]["metrics"]["ev"]
    bl_ev = baseline["event_summaries"][ev]["metrics"]["ev"] if ev in baseline["event_summaries"] else None
    if bl_ev is not None:
        diff = ff_ev - bl_ev
        print(f"  {ev:<35s} {ff_ev:>14.4f} {bl_ev:>13.4f} {diff:>+8.4f}")
    else:
        print(f"  {ev:<35s} {ff_ev:>14.4f} {'N/A':>13s}")

print(f"\n{'='*80}")
print(f"  結論")
print(f"{'='*80}")
print()

# FIXED_FULL結論
ff_pos = sum(1 for ev in ff_events if fixed_full["event_summaries"][ev]["metrics"]["ev"] >= 0)
ff_neg = len(ff_events) - ff_pos
ff_pnl_sorted = sorted(ff_events, key=lambda e: fixed_full["event_summaries"][e]["metrics"]["total_pnl"], reverse=True)

print(f"  【FIXED_FULL設定】")
print(f"  - 全{len(ff_events)}イベント中、正のEV: {ff_pos}件、負のEV: {ff_neg}件")
print(f"  - 最大プラスイベント: {ff_pnl_sorted[0]} (EV={fixed_full['event_summaries'][ff_pnl_sorted[0]]['metrics']['ev']:.4f})")
print(f"  - 最大マイナスイベント: {ff_pnl_sorted[-1]} (EV={fixed_full['event_summaries'][ff_pnl_sorted[-1]]['metrics']['ev']:.4f})")

# トップ貢献度
ff_ranked = sorted(loo_ff, key=lambda x: x["ev_change"])
print(f"  - 除外で最もEVが下がる（最も重要）: {ff_ranked[0]['excluded']} (除外時EV変化 {ff_ranked[0]['ev_change']:+.4f})")
print(f"  - 除外で最もEVが上がる（最も有害）: {ff_ranked[-1]['excluded']} (除外時EV変化 {ff_ranked[-1]['ev_change']:+.4f})")

# ベースラインも同様
bl_pos = sum(1 for ev in bl_events if baseline["event_summaries"][ev]["metrics"]["ev"] >= 0)
bl_neg = len(bl_events) - bl_pos
bl_pnl_sorted = sorted(bl_events, key=lambda e: baseline["event_summaries"][e]["metrics"]["total_pnl"], reverse=True)

print(f"\n  【BASELINE設定】")
print(f"  - 全{len(bl_events)}イベント中、正のEV: {bl_pos}件、負のEV: {bl_neg}件")
print(f"  - 最大プラスイベント: {bl_pnl_sorted[0]} (EV={baseline['event_summaries'][bl_pnl_sorted[0]]['metrics']['ev']:.4f})")
print(f"  - 最大マイナスイベント: {bl_pnl_sorted[-1]} (EV={baseline['event_summaries'][bl_pnl_sorted[-1]]['metrics']['ev']:.4f})")

bl_ranked = sorted(loo_bl, key=lambda x: x["ev_change"])
print(f"  - 除外で最もEVが下がる（最も重要）: {bl_ranked[0]['excluded']} (除外時EV変化 {bl_ranked[0]['ev_change']:+.4f})")
print(f"  - 除外で最もEVが上がる（最も有害）: {bl_ranked[-1]['excluded']} (除外時EV変化 {bl_ranked[-1]['ev_change']:+.4f})")
