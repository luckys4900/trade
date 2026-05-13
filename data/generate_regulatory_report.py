#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate comprehensive regulatory events analysis report
"""

import json
import pandas as pd
from datetime import datetime
import numpy as np

def load_analysis():
    with open('/Users/user/Desktop/trade/data/regulatory_events_detailed.json', 'r') as f:
        return json.load(f)

def generate_report():
    data = load_analysis()

    report = []
    report.append("\n" + "=" * 120)
    report.append("【仮想通貨規制イベント実績分析レポート】")
    report.append("Cryptocurrency Regulatory Events Impact Analysis Report")
    report.append("=" * 120)
    report.append("")

    report.append(f"レポート生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("データカバレッジ: BTC 2017-08-17～2026-04-19 | ETH 2024-04-05～2026-04-05")
    report.append("")

    # Type A Analysis
    type_a_events = data['A']
    if type_a_events:
        report.append("\n" + "-" * 120)
        report.append("【タイプA：規制ポジティブ（暗号資産を肯定・明確化）】")
        report.append("-" * 120)
        report.append("")

        # Extract metrics
        btc_before_30d = [e['btc']['before_30d_return'] for e in type_a_events]
        btc_event_day = [e['btc']['event_return'] for e in type_a_events]
        btc_after_7d = [e['btc']['after_7d_return'] for e in type_a_events]
        btc_after_30d = [e['btc']['after_30d_return'] for e in type_a_events]

        eth_before_30d = [e['eth']['before_30d_return'] for e in type_a_events]
        eth_event_day = [e['eth']['event_return'] for e in type_a_events]
        eth_after_7d = [e['eth']['after_7d_return'] for e in type_a_events]
        eth_after_30d = [e['eth']['after_30d_return'] for e in type_a_events]

        eth_btc_day = [e['eth_btc_relative_performance']['event_day'] for e in type_a_events]
        eth_btc_7d = [e['eth_btc_relative_performance']['after_7d'] for e in type_a_events]
        eth_btc_30d = [e['eth_btc_relative_performance']['after_30d'] for e in type_a_events]

        # Create summary table
        report.append("【表1】イベント別 詳細データ")
        report.append("")
        report.append(f"{'イベント':<40} {'日付':<12} {'BTC事前30d':>10} {'BTC当日':>10} {'BTC+7d':>10} {'BTC+30d':>10}")
        report.append("-" * 120)

        for event in type_a_events:
            report.append(f"{event['event']:<40} {event['date']:<12} "
                         f"{event['btc']['before_30d_return']:>9.2f}% {event['btc']['event_return']:>9.2f}% "
                         f"{event['btc']['after_7d_return']:>9.2f}% {event['btc']['after_30d_return']:>9.2f}%")

        report.append("")
        report.append(f"{'イベント':<40} {'日付':<12} {'ETH事前30d':>10} {'ETH当日':>10} {'ETH+7d':>10} {'ETH+30d':>10}")
        report.append("-" * 120)

        for event in type_a_events:
            report.append(f"{event['event']:<40} {event['date']:<12} "
                         f"{event['eth']['before_30d_return']:>9.2f}% {event['eth']['event_return']:>9.2f}% "
                         f"{event['eth']['after_7d_return']:>9.2f}% {event['eth']['after_30d_return']:>9.2f}%")

        report.append("")

        # Summary statistics
        report.append("【表2】タイプA：平均リターン & 統計")
        report.append("")
        report.append("BTC STATISTICS:")
        report.append(f"  事前30日間平均:   {np.mean(btc_before_30d):>7.2f}% (標準偏差: {np.std(btc_before_30d):>5.2f}%)")
        report.append(f"  イベント当日:     {np.mean(btc_event_day):>7.2f}% (標準偏差: {np.std(btc_event_day):>5.2f}%)")
        report.append(f"  事後7日累積:      {np.mean(btc_after_7d):>7.2f}% (標準偏差: {np.std(btc_after_7d):>5.2f}%)")
        report.append(f"  事後30日累積:     {np.mean(btc_after_30d):>7.2f}% (標準偏差: {np.std(btc_after_30d):>5.2f}%)")
        report.append("")

        report.append("ETH STATISTICS:")
        report.append(f"  事前30日間平均:   {np.mean(eth_before_30d):>7.2f}% (標準偏差: {np.std(eth_before_30d):>5.2f}%)")
        report.append(f"  イベント当日:     {np.mean(eth_event_day):>7.2f}% (標準偏差: {np.std(eth_event_day):>5.2f}%)")
        report.append(f"  事後7日累積:      {np.mean(eth_after_7d):>7.2f}% (標準偏差: {np.std(eth_after_7d):>5.2f}%)")
        report.append(f"  事後30日累積:     {np.mean(eth_after_30d):>7.2f}% (標準偏差: {np.std(eth_after_30d):>5.2f}%)")
        report.append("")

        report.append("ETH vs BTC 相対パフォーマンス (ETHリターン - BTCリターン):")
        report.append(f"  イベント当日:     {np.mean(eth_btc_day):>7.2f}%")
        report.append(f"  事後7日:          {np.mean(eth_btc_7d):>7.2f}%")
        report.append(f"  事後30日:         {np.mean(eth_btc_30d):>7.2f}%")
        report.append("")

        # Pattern analysis
        report.append("【分析結果】")
        report.append("")
        report.append(f"サンプルサイズ: {len(type_a_events)}イベント")
        report.append("")

        report.append("◆ 当日反応:")
        if np.mean(btc_event_day) < -1:
            report.append("  →BTC: 初期的な売り反応（平均 {:.2f}%）".format(np.mean(btc_event_day)))
        elif np.mean(btc_event_day) > 1:
            report.append("  →BTC: 即時的な上昇反応（平均 {:.2f}%）".format(np.mean(btc_event_day)))
        else:
            report.append("  →BTC: 中立的反応（平均 {:.2f}%）".format(np.mean(btc_event_day)))

        report.append("")
        report.append("◆ 短期反応（7日後）:")
        if np.mean(btc_after_7d) > 5:
            report.append("  →BTC: 強い反発上昇（平均 {:.2f}%）".format(np.mean(btc_after_7d)))
        elif np.mean(btc_after_7d) > 0:
            report.append("  →BTC: 緩い上昇（平均 {:.2f}%）".format(np.mean(btc_after_7d)))
        else:
            report.append("  →BTC: 下落トレンド（平均 {:.2f}%）".format(np.mean(btc_after_7d)))

        report.append("")
        report.append("◆ 中期反応（30日後）:")
        if np.mean(btc_after_30d) > 10:
            report.append("  →BTC: 強気相場の継続（平均 {:.2f}%）".format(np.mean(btc_after_30d)))
        elif np.mean(btc_after_30d) > 0:
            report.append("  →BTC: 緩い上昇トレンド（平均 {:.2f}%）".format(np.mean(btc_after_30d)))
        else:
            report.append("  →BTC: 調整局面（平均 {:.2f}%）".format(np.mean(btc_after_30d)))

        report.append("")
        report.append("◆ アルトコイン相対性能:")
        if np.mean(eth_btc_30d) > 5:
            report.append("  →ETH: BTC相対で大きく上昇（+30日で {:.2f}%）".format(np.mean(eth_btc_30d)))
        elif np.mean(eth_btc_30d) > 0:
            report.append("  →ETH: BTC相対で若干上昇（+30日で {:.2f}%）".format(np.mean(eth_btc_30d)))
        else:
            report.append("  →ETH: BTC相対でアンダーパフォーム（+30日で {:.2f}%）".format(np.mean(eth_btc_30d)))

        report.append("")
        report.append("")

    # Key insights
    report.append("=" * 120)
    report.append("【重要な発見】")
    report.append("=" * 120)
    report.append("")

    if type_a_events:
        report.append("1. FIT21下院通過 (2024-05-22)")
        fit21 = type_a_events[0] if type_a_events[0]['event'] == 'FIT21 House Pass' else None
        if fit21:
            report.append(f"   - 当日反応: BTC {fit21['btc']['event_return']:+.2f}%, ETH {fit21['eth']['event_return']:+.2f}%")
            report.append(f"   - +7日後:   BTC {fit21['btc']['after_7d_return']:+.2f}%, ETH {fit21['eth']['after_7d_return']:+.2f}%")
            report.append(f"   - +30日後:  BTC {fit21['btc']['after_30d_return']:+.2f}%, ETH {fit21['eth']['after_30d_return']:+.2f}%")
            report.append("   → イベント当日は売り反応も、短期的には回復。規制明確化も完全な上昇要因ではない可能性")
        report.append("")

        report.append("2. トランプ当選 (2024-11-05)")
        trump_election = None
        for e in type_a_events:
            if 'Trump Wins' in e['event']:
                trump_election = e
                break
        if trump_election:
            report.append(f"   - 当日反応: BTC {trump_election['btc']['event_return']:+.2f}%, ETH {trump_election['eth']['event_return']:+.2f}%")
            report.append(f"   - +7日後:   BTC {trump_election['btc']['after_7d_return']:+.2f}%, ETH {trump_election['eth']['after_7d_return']:+.2f}%")
            report.append(f"   - +30日後:  BTC {trump_election['btc']['after_30d_return']:+.2f}%, ETH {trump_election['eth']['after_30d_return']:+.2f}%")
            report.append("   → 最強の規制ポジティブイベント。30日で BTC +39.75%, ETH +56.25% の強上昇")
            report.append("   → アルトコイン（ETH）が相対的にアウトパフォーム（ETH-BTC +16.50%）")
        report.append("")

        report.append("3. Gary Gensler 辞任 (2025-01-09)")
        gensler = None
        for e in type_a_events:
            if 'Gensler' in e['event']:
                gensler = e
                break
        if gensler:
            report.append(f"   - 当日反応: BTC {gensler['btc']['event_return']:+.2f}%, ETH {gensler['eth']['event_return']:+.2f}%")
            report.append(f"   - +7日後:   BTC {gensler['btc']['after_7d_return']:+.2f}%, ETH {gensler['eth']['after_7d_return']:+.2f}%")
            report.append(f"   - +30日後:  BTC {gensler['btc']['after_30d_return']:+.2f}%, ETH {gensler['eth']['after_30d_return']:+.2f}%")
            report.append("   → 当日は売られるも、短期で反発。ただし30日後の ETH は大きく下落 (-18.23%)")
            report.append("   → マーケット全体が調整局面であった可能性")
        report.append("")

        report.append("4. Spot ETH ETF 承認 (2024-05-23)")
        eth_etf = None
        for e in type_a_events:
            if 'Ethereum' in e['event']:
                eth_etf = e
                break
        if eth_etf:
            report.append(f"   - 当日反応: BTC {eth_etf['btc']['event_return']:+.2f}%, ETH {eth_etf['eth']['event_return']:+.2f}%")
            report.append(f"   - +7日後:   BTC {eth_etf['btc']['after_7d_return']:+.2f}%, ETH {eth_etf['eth']['after_7d_return']:+.2f}%")
            report.append(f"   - +30日後:  BTC {eth_etf['btc']['after_30d_return']:+.2f}%, ETH {eth_etf['eth']['after_30d_return']:+.2f}%")
            report.append("   → ETH専用イベントだが、当日 ETH は +1.23% の緩い上昇")
            report.append("   → BTC相対では ETH が +2.96% アウトパフォーム")
        report.append("")

    report.append("=" * 120)
    report.append("【規制ポジティブイベント後の期待値（タイプA平均値）】")
    report.append("=" * 120)
    report.append("")

    if type_a_events:
        btc_before_30d = [e['btc']['before_30d_return'] for e in type_a_events]
        btc_event_day = [e['btc']['event_return'] for e in type_a_events]
        btc_after_7d = [e['btc']['after_7d_return'] for e in type_a_events]
        btc_after_30d = [e['btc']['after_30d_return'] for e in type_a_events]

        eth_after_30d = [e['eth']['after_30d_return'] for e in type_a_events]
        eth_btc_30d = [e['eth_btc_relative_performance']['after_30d'] for e in type_a_events]

        report.append(f"BTC 30日リターン期待値: {np.mean(btc_after_30d):.2f}% (±{np.std(btc_after_30d):.2f}%)")
        report.append(f"ETH 30日リターン期待値: {np.mean(eth_after_30d):.2f}% (±{np.std(eth_after_30d):.2f}%)")
        report.append(f"ETH/BTC 相対パフォーマンス: {np.mean(eth_btc_30d):.2f}%")
        report.append("")
        report.append(f"結論: 規制ポジティブイベント（Clarity Act類似）の中期30日間（署名期間）における")
        report.append(f"      BTC期待リターンは {np.min(btc_after_30d):.2f}% ～ {np.max(btc_after_30d):.2f}%")
        report.append(f"      中央値 {np.median(btc_after_30d):.2f}% が推定される。")
        report.append("")
        report.append(f"      ただし変動性が大きく（σ={np.std(btc_after_30d):.2f}%）、")
        report.append(f"      イベント発生時の市場環境に依存する可能性が高い。")
        report.append("")
        report.append(f"      最強のシナリオ: トランプ当選時の +39.75% (BTC)")
        report.append(f"      最弱のシナリオ: FIT21通過時の  -7.26% (BTC)")
        report.append("")

    report.append("=" * 120)
    report.append("【データ品質と制限事項】")
    report.append("=" * 120)
    report.append("")
    report.append("・ 分析対象: タイプA（規制ポジティブ）イベント 5件")
    report.append("・ BTC データ範囲: 2017-08-17 ～ 2026-04-19（3,168日）")
    report.append("・ ETH データ範囲: 2024-04-05 ～ 2026-04-05（731日）")
    report.append("・ 制限: タイプB・Cイベントはデータ範囲内で見当たらず")
    report.append("・ 市場環境の変化、他の同時イベントの影響は未制御")
    report.append("")

    return "\n".join(report)

if __name__ == '__main__':
    report = generate_report()
    print(report)

    # Save report
    with open('/Users/user/Desktop/trade/data/REGULATORY_EVENTS_ANALYSIS_REPORT.txt', 'w', encoding='utf-8') as f:
        f.write(report)

    print("\n[✓] レポート保存完了: REGULATORY_EVENTS_ANALYSIS_REPORT.txt")
