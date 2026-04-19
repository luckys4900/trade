import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

class PerformanceMetrics:
    """バックテストパフォーマンス評価クラス"""
    
    def __init__(self, stats: Dict[str, Any], config: Dict[str, Any] = None):
        self.stats = stats
        self.config = config or {}
    
    def evaluate(self) -> Tuple[bool, Dict[str, Any]]:
        """
        戦略を評価し、合格基準を満たすか判定
        
        Returns:
        --------
        Tuple[bool, Dict]: 合格/不合格, 評価結果詳細
        """
        metrics = self._calculate_metrics()
        passed = self._check_pass_criteria(metrics)
        
        return passed, {
            'metrics': metrics,
            'passed': passed,
            'details': self._get_evaluation_details(metrics)
        }
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        """主要パフォーマンス指標を計算"""
        return {
            'annual_return': self.stats['Return (Ann.) [%]'] / 100,
            'sharpe_ratio': self.stats['Sharpe Ratio'],
            'max_drawdown': self.stats['Max. Drawdown [%]'] / 100,
            'win_rate': self.stats['Win Rate [%]'] / 100,
            'total_trades': self.stats['# Trades'],
            'avg_trade': self.stats['Avg. Trade [%]'] / 100,
            'profit_factor': self.stats.get('Profit Factor', 0)
        }
    
    def _check_pass_criteria(self, metrics: Dict[str, Any]) -> bool:
        """合格基準をチェック"""
        criteria = self.config.get('EVALUATION_METRICS', {
            'min_annual_return': 0.8,
            'min_sharpe_ratio': 1.3,
            'max_drawdown': 0.25,
            'min_win_rate': 0.58,
            'min_trades_per_month': 100,
            'min_profit_factor': 1.6,
            'min_avg_trade': 0.004
        })
        
        # 月間トレード数を計算
        days = 365  # 1年間と仮定
        months = days / 30
        trades_per_month = metrics['total_trades'] / months
        
        # 合格判定
        checks = [
            metrics['annual_return'] >= criteria['min_annual_return'],
            metrics['sharpe_ratio'] >= criteria['min_sharpe_ratio'],
            abs(metrics['max_drawdown']) <= criteria['max_drawdown'],
            metrics['win_rate'] >= criteria['min_win_rate'],
            trades_per_month >= criteria['min_trades_per_month'],
            metrics['profit_factor'] >= criteria['min_profit_factor'],
            abs(metrics['avg_trade']) >= criteria['min_avg_trade']
        ]
        
        return all(checks)
    
    def _get_evaluation_details(self, metrics: Dict[str, Any]) -> Dict[str, str]:
        """評価結果の詳細を生成"""
        criteria = self.config.get('EVALUATION_METRICS', {
            'min_annual_return': 0.8,
            'min_sharpe_ratio': 1.3,
            'max_drawdown': 0.25,
            'min_win_rate': 0.58,
            'min_trades_per_month': 100,
            'min_profit_factor': 1.6,
            'min_avg_trade': 0.004
        })
        
        # 月間トレード数を計算
        days = 365
        months = days / 30
        trades_per_month = metrics['total_trades'] / months
        
        # 評価結果をフォーマット
        details = {
            f"年間リターン ({criteria['min_annual_return']*100:.0f}%以上)": 
                f"{metrics['annual_return']*100:.2f}% {'✓' if metrics['annual_return'] >= criteria['min_annual_return'] else '✗'}",
            f"シャープレシオ ({criteria['min_sharpe_ratio']:.1f}以上)": 
                f"{metrics['sharpe_ratio']:.2f} {'✓' if metrics['sharpe_ratio'] >= criteria['min_sharpe_ratio'] else '✗'}",
            f"最大ドローダウン ({criteria['max_drawdown']*100:.0f}%以下)": 
                f"{abs(metrics['max_drawdown'])*100:.2f}% {'✓' if abs(metrics['max_drawdown']) <= criteria['max_drawdown'] else '✗'}",
            f"勝率 ({criteria['min_win_rate']*100:.0f}%以上)": 
                f"{metrics['win_rate']*100:.2f}% {'✓' if metrics['win_rate'] >= criteria['min_win_rate'] else '✗'}",
            f"月間トレード数 ({criteria['min_trades_per_month']}以上)": 
                f"{trades_per_month:.1f}回 {'✓' if trades_per_month >= criteria['min_trades_per_month'] else '✗'}",
            f"プロフィットファクター ({criteria['min_profit_factor']:.1f}以上)": 
                f"{metrics['profit_factor']:.2f} {'✓' if metrics['profit_factor'] >= criteria['min_profit_factor'] else '✗'}",
            f"平均トレード ({criteria['min_avg_trade']*100:.2f}%以上)": 
                f"{abs(metrics['avg_trade'])*100:.2f}% {'✓' if abs(metrics['avg_trade']) >= criteria['min_avg_trade'] else '✗'}"
        }
        
        return details