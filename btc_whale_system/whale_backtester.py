from typing import Dict

class WhaleBacktester:
    def run_backtest(self, roi_data: Dict) -> Dict:
        entry_value = roi_data['inflow_value_usd']
        exit_value = roi_data['current_value_usd']
        pnl = exit_value - entry_value
        roi_pct = roi_data['roi_pct']
        holding_days = roi_data['holding_days']
        annualized_roi = roi_pct / (holding_days / 365.0) if holding_days > 0 else 0
        
        return {
            "address": roi_data['address'],
            "strategy": "Buy & Hold",
            "entry_date": roi_data['inflow_date'],
            "entry_price_usd": roi_data['inflow_price_usd'],
            "entry_amount_usd": entry_value,
            "exit_date": roi_data['current_date'],
            "exit_price_usd": roi_data['current_price_usd'],
            "exit_amount_usd": exit_value,
            "absolute_pnl_usd": pnl,
            "roi_pct": roi_pct,
            "holding_days": holding_days,
            "annualized_roi_pct": annualized_roi
        }
