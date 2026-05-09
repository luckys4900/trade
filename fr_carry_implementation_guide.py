"""
FR Carry Trade - 実装ガイド
============================

詳細分析の結果から、実装可能な改善案をコード化
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

# ============================================================
# 設定値
# ============================================================

class FRCarryConfig:
    """FR Carry Trade設定"""

    # Basic settings
    ACCOUNT_SIZE = 190  # USD
    LEVERAGE = 1

    # Fee models
    TAKER_ENTRY_COST = 0.00035 + 0.00050  # Taker fee + slippage
    MAKER_EXIT_COST = -0.0001 + 0.00025  # Maker rebate + half slippage

    # Strategy parameters
    HOLD_PERIOD_HOURS = 8  # Optimal from analysis
    COMPOSITE_EXIT_PRICE_PCT = 0.5  # Exit on 0.5% price move

    # Entry conditions
    FR_THRESHOLD_CONSERVATIVE = 0.00005  # 0.005%
    FR_THRESHOLD_MODERATE = 0.0001      # 0.010%
    FR_THRESHOLD_AGGRESSIVE = 0.00015   # 0.015%
    FR_THRESHOLD_BEST = 0.0003          # 0.030%

    # Risk management
    MAX_POSITION_SIZE = ACCOUNT_SIZE * LEVERAGE
    STOP_LOSS_PCT = 1.0  # Stop if down 1%
    TAKE_PROFIT_PCT = None  # Not applicable for carry

    # Monitoring
    CHECK_FREQUENCY_MINUTES = 30  # Monitor every 30 min
    MIN_SAMPLE_SIZE = 500  # Before deciding to continue


class FRCarryStrategy:
    """FR Carry Tradeストラテジー実装"""

    def __init__(self, config=None):
        self.config = config or FRCarryConfig()
        self.positions = []
        self.trades_log = []

    def should_enter(self, funding_rate, market_condition="normal"):
        """
        エントリー条件の判定

        Parameters:
        -----------
        funding_rate : float
            Current 8H funding rate (e.g., 0.00015)
        market_condition : str
            'normal', 'high_vol', 'anomaly'

        Returns:
        --------
        tuple: (should_enter, threshold_used, reason)
        """

        # Dynamic threshold based on market condition
        if market_condition == "high_vol":
            # Stricter entry in high volatility
            threshold = self.config.FR_THRESHOLD_AGGRESSIVE
            reason = "High volatility detected"
        elif market_condition == "anomaly":
            # Only enter on very high FR
            threshold = self.config.FR_THRESHOLD_BEST
            reason = "Anomaly condition"
        else:
            # Normal: use moderate threshold
            threshold = self.config.FR_THRESHOLD_MODERATE
            reason = "Normal condition"

        should_enter = funding_rate > threshold

        return should_enter, threshold, reason

    def entry_order(self, funding_rate, entry_price, direction="short"):
        """
        エントリーオーダーの作成

        Parameters:
        -----------
        funding_rate : float
            Current FR
        entry_price : float
            Entry price
        direction : str
            'short' for high FR
        """

        entry_cost_pct = self.config.TAKER_ENTRY_COST * 100

        order = {
            'timestamp': datetime.now().isoformat(),
            'direction': direction,
            'type': 'market',  # Market entry for speed
            'quantity': self.config.MAX_POSITION_SIZE / entry_price,
            'entry_price': entry_price,
            'funding_rate': funding_rate,
            'entry_cost_pct': entry_cost_pct,
            'status': 'submitted',
        }

        return order

    def exit_order(self, position, current_price, exit_reason):
        """
        エグジットオーダーの作成

        Parameters:
        -----------
        position : dict
            Open position
        current_price : float
            Current price
        exit_reason : str
            'time' (24h passed) or 'price' (±0.5% move)
        """

        # Use Maker order for exit (limit order)
        exit_cost_pct = self.config.MAKER_EXIT_COST * 100

        if exit_reason == "price":
            # Exit immediately at current price
            order_type = "market"
            exit_price = current_price
        else:
            # Exit via limit order (Maker)
            order_type = "limit"
            # Set limit slightly inside the spread to improve fill chance
            if position['direction'] == 'short':
                exit_price = current_price * (1 + 0.001)  # 0.1% above current
            else:
                exit_price = current_price * (1 - 0.001)  # 0.1% below current

        order = {
            'timestamp': datetime.now().isoformat(),
            'direction': position['direction'],
            'type': order_type,
            'quantity': position['quantity'],
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'exit_cost_pct': exit_cost_pct,
            'status': 'submitted',
        }

        return order

    def calculate_pnl(self, entry_price, exit_price, funding_rate, direction="short"):
        """
        P&Lの計算

        期待値 = 資金調達料 + 相場変動 - 手数料
        """

        # Funding P&L (from holding the position)
        funding_pnl_pct = funding_rate * 100

        # Price P&L (directional)
        if direction == "short":
            price_pnl_pct = (entry_price - exit_price) / entry_price * 100
        else:  # long
            price_pnl_pct = (exit_price - entry_price) / entry_price * 100

        # Total costs
        total_cost_pct = (self.config.TAKER_ENTRY_COST +
                         abs(self.config.MAKER_EXIT_COST)) * 100

        # Net P&L
        net_pnl_pct = price_pnl_pct + funding_pnl_pct - total_cost_pct

        return {
            'funding_pnl_pct': funding_pnl_pct,
            'price_pnl_pct': price_pnl_pct,
            'cost_pct': total_cost_pct,
            'net_pnl_pct': net_pnl_pct,
        }


# ============================================================
# 実装例
# ============================================================

def example_trading_flow():
    """
    実際のトレーディングフロー例
    """

    config = FRCarryConfig()
    strategy = FRCarryStrategy(config)

    print("=" * 100)
    print("FR CARRY TRADE - 実装例")
    print("=" * 100)

    # Example market data
    current_fr = 0.00012  # 0.012% (8H FR)
    current_price = 67000.0

    print(f"\n【市場データ】")
    print(f"  現在のFR: {current_fr*100:.4f}%")
    print(f"  現在の価格: ${current_price:,.2f}")
    print(f"  市場環境: normal")

    # Step 1: Entry decision
    print(f"\n【ステップ1】エントリー判断")

    should_enter, threshold, reason = strategy.should_enter(
        current_fr, market_condition="normal"
    )

    print(f"  使用閾値: {threshold*100:.5f}%")
    print(f"  理由: {reason}")
    print(f"  判定: {'エントリー' if should_enter else 'スキップ'}")

    if not should_enter:
        print(f"  理由: FR ({current_fr*100:.5f}%) < Threshold ({threshold*100:.5f}%)")
        return

    # Step 2: Entry order
    print(f"\n【ステップ2】エントリーオーダー作成")

    entry_order = strategy.entry_order(current_fr, current_price, direction="short")

    print(f"  方向: {entry_order['direction']}")
    print(f"  数量: {entry_order['quantity']:.8f} BTC")
    print(f"  エントリー価格: ${entry_order['entry_price']:,.2f}")
    print(f"  エントリーコスト: {entry_order['entry_cost_pct']:.4f}%")
    print(f"  ステータス: {entry_order['status']}")

    # Step 3: Hold and monitor
    print(f"\n【ステップ3】ホールドと監視")

    hold_period = config.HOLD_PERIOD_HOURS
    exit_condition = f"24h経過 OR 価格±{config.COMPOSITE_EXIT_PRICE_PCT}%変動"

    print(f"  ホールド期間: {hold_period}時間")
    print(f"  複合EXIT条件: {exit_condition}")
    print(f"  モニタリング頻度: {config.CHECK_FREQUENCY_MINUTES}分ごと")

    # Step 4: Exit decision
    print(f"\n【ステップ4】エグジット判断")

    # Simulate exit after 24h with price up 0.3%
    exit_price = current_price * 1.003
    exit_reason = "price"  # Price moved 0.3%, triggers exit

    print(f"  エグジット理由: {exit_reason}")
    print(f"  エグジット価格: ${exit_price:,.2f}")

    # Step 5: Exit order
    print(f"\n【ステップ5】エグジットオーダー作成")

    exit_order = strategy.exit_order(entry_order, exit_price, exit_reason)

    print(f"  オーダータイプ: {exit_order['type']}")
    print(f"  エグジット価格: ${exit_order['exit_price']:,.2f}")
    print(f"  エグジットコスト: {exit_order['exit_cost_pct']:.4f}%")

    # Step 6: P&L calculation
    print(f"\n【ステップ6】P&L計算")

    pnl = strategy.calculate_pnl(
        current_price, exit_price, current_fr, direction="short"
    )

    print(f"  資金調達料 P&L: {pnl['funding_pnl_pct']:+.4f}%")
    print(f"  相場変動 P&L: {pnl['price_pnl_pct']:+.4f}%")
    print(f"  手数料: {pnl['cost_pct']:.4f}%")
    print(f"  ---")
    print(f"  純利益: {pnl['net_pnl_pct']:+.4f}%")

    profit_dollars = pnl['net_pnl_pct'] / 100 * config.ACCOUNT_SIZE
    print(f"  利益: ${profit_dollars:+.2f}")

    # Step 7: Logging
    print(f"\n【ステップ7】トレード記録")

    trade_record = {
        'entry_time': entry_order['timestamp'],
        'exit_time': exit_order['timestamp'],
        'direction': entry_order['direction'],
        'entry_price': entry_order['entry_price'],
        'exit_price': exit_order['exit_price'],
        'fr': current_fr,
        'pnl_pct': pnl['net_pnl_pct'],
        'pnl_usd': profit_dollars,
        'exit_reason': exit_reason,
    }

    print(f"  記録: {json.dumps(trade_record, indent=2, default=str)}")


def scenario_analysis():
    """
    異なるシナリオでの期待値分析
    """

    print("\n" + "=" * 100)
    print("シナリオ分析: 異なるFRレベルでの期待値")
    print("=" * 100)

    config = FRCarryConfig()
    strategy = FRCarryStrategy(config)

    scenarios = [
        ("Low FR (0.005%)", 0.00005, 67000, 67100),  # Price up 0.15%
        ("Mid FR (0.015%)", 0.00015, 67000, 66700),  # Price down 0.45%
        ("High FR (0.030%)", 0.0003, 67000, 66500),  # Price down 0.75%
        ("Extreme FR (0.050%)", 0.0005, 67000, 67500),  # Price up 0.75%
    ]

    print(f"\n{'シナリオ':<20} {'FR%':<10} {'価格変動%':<12} "
          f"{'期待値%':<12} {'利益$':<10} {'判定':<10}")
    print("-" * 90)

    for scenario_name, fr, entry_px, exit_px in scenarios:
        pnl = strategy.calculate_pnl(entry_px, exit_px, fr, direction="short")
        profit_usd = pnl['net_pnl_pct'] / 100 * config.ACCOUNT_SIZE

        verdict = "✓ Entry" if fr > config.FR_THRESHOLD_MODERATE else "✗ Skip"

        price_change = (exit_px - entry_px) / entry_px * 100

        print(f"{scenario_name:<20} {fr*100:<10.4f} {price_change:<12.2f} "
              f"{pnl['net_pnl_pct']:<12.4f} {profit_usd:<10.2f} {verdict:<10}")


def monitoring_checklist():
    """
    運用時のチェックリスト
    """

    print("\n" + "=" * 100)
    print("FR Carry Trade - 運用チェックリスト")
    print("=" * 100)

    checklist = {
        "毎日チェック": [
            "□ FRの平均値が0.01%以上か?",
            "□ ボラティリティレベルの確認",
            "□ 24時間以内に3回の取引機会があるか?",
            "□ アカウント残高の確認",
        ],
        "毎週チェック": [
            "□ 勝率が50%以上か?",
            "□ P&L推移をグラフで確認",
            "□ ドローダウンが-1%以内か?",
            "□ 取引記録のログ確認",
        ],
        "毎月チェック": [
            "□ 月間EV計算 (目標: > 0%)",
            "□ Maker fee効果の測定",
            "□ 複合EXIT条件の有効性確認",
            "□ 統計的有意性の再計算",
            "□ 今月のサンプルサイズ (n >= 20?)",
        ],
        "四半期ごと": [
            "□ IN-SAMPLE vs OUT-OF-SAMPLE性能比較",
            "□ パラメータ最適化の再検討",
            "□ 戦略の継続/中止判断",
            "□ 他の通貨ペアの検討",
        ],
    }

    for period, items in checklist.items():
        print(f"\n【{period}】")
        for item in items:
            print(f"  {item}")


# ============================================================
# メイン実行
# ============================================================

if __name__ == "__main__":
    example_trading_flow()
    scenario_analysis()
    monitoring_checklist()

    print("\n" + "=" * 100)
    print("実装ガイド完了")
    print("=" * 100)
    print("""
    次のステップ:
    1. 実装コードをファイナライズ
    2. バックテストで検証
    3. ペーパートレーディングで試験
    4. 小規模ライブ取引で確認
    5. 統計的有意性が確認されたら本格運用

    統計的有意性の目安:
    - n >= 100取引
    - p-value < 0.05
    - OOS性能がIS性能と同等
    - Sharpe ratio > 1.0
    """)
