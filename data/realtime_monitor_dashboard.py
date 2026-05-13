"""
Real-time Monitoring Dashboard for Clarity Act Pair Trading
Simple JSON-based monitoring for vote status and trading metrics
"""

import json
from datetime import datetime
from typing import Dict
import os


class RealtimeMonitorDashboard:
    """
    Create and update real-time monitoring dashboard
    Outputs: JSON files for easy viewing
    """

    def __init__(self, output_dir: str = "."):
        self.output_dir = output_dir
        self.dashboard_file = os.path.join(output_dir, "dashboard.json")
        self.init_dashboard()

    def init_dashboard(self):
        """Initialize dashboard structure"""
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "system_status": "initialized",
            "committee_vote": {
                "date": "2026-05-14",
                "time": "10:30 ET",
                "status": "pending",
                "outcome": None,
                "last_updated": None
            },
            "senate_floor_vote": {
                "date": None,
                "status": "not_confirmed",
                "polymarket_odds": None,
                "odds_trend": []
            },
            "strategy": {
                "status": "ready",
                "duration_days": None,
                "current_parameters": {
                    "ma_window": 10,
                    "stop_loss_percent": -2.5,
                    "position_fraction": 0.50
                },
                "trading_enabled": False
            },
            "market_data": {
                "btc_price": None,
                "eth_price": None,
                "btc_eth_ratio": None,
                "ratio_ma": None,
                "last_update": None
            },
            "positions": {
                "active_position": False,
                "entry_price": None,
                "entry_time": None,
                "current_pnl_percent": None
            },
            "alerts": [],
            "trade_log": {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "pnl": 0.0
            }
        }

        self.save_dashboard(dashboard)

    def save_dashboard(self, data: Dict):
        """Save dashboard to JSON file"""
        with open(self.dashboard_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def load_dashboard(self) -> Dict:
        """Load current dashboard"""
        if os.path.exists(self.dashboard_file):
            with open(self.dashboard_file, 'r') as f:
                return json.load(f)
        return None

    def update_committee_vote_status(self, status: str, outcome: str = None):
        """Update committee vote status"""
        dashboard = self.load_dashboard()
        dashboard["committee_vote"]["status"] = status
        dashboard["committee_vote"]["outcome"] = outcome
        dashboard["committee_vote"]["last_updated"] = datetime.now().isoformat()

        if status == "passed":
            dashboard["alerts"].append({
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "message": "Committee vote PASSED ✅"
            })
        elif status == "failed":
            dashboard["alerts"].append({
                "timestamp": datetime.now().isoformat(),
                "level": "CRITICAL",
                "message": "Committee vote FAILED ❌ - Strategy suspended"
            })

        self.save_dashboard(dashboard)

    def update_senate_vote_date(self, vote_date: str, odds: float = None):
        """Update Senate floor vote date when detected"""
        dashboard = self.load_dashboard()
        dashboard["senate_floor_vote"]["date"] = vote_date
        dashboard["senate_floor_vote"]["status"] = "confirmed"
        dashboard["senate_floor_vote"]["polymarket_odds"] = odds

        dashboard["alerts"].append({
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": f"Senate floor vote date CONFIRMED: {vote_date} | Odds: {odds}%"
        })

        self.save_dashboard(dashboard)

    def update_market_data(self, btc_price: float, eth_price: float, ratio: float, ma: float):
        """Update current market data"""
        dashboard = self.load_dashboard()
        dashboard["market_data"]["btc_price"] = btc_price
        dashboard["market_data"]["eth_price"] = eth_price
        dashboard["market_data"]["btc_eth_ratio"] = ratio
        dashboard["market_data"]["ratio_ma"] = ma
        dashboard["market_data"]["last_update"] = datetime.now().isoformat()

        self.save_dashboard(dashboard)

    def update_trading_status(self, enabled: bool, parameters: Dict = None):
        """Update trading status and parameters"""
        dashboard = self.load_dashboard()
        dashboard["strategy"]["trading_enabled"] = enabled

        if parameters:
            dashboard["strategy"]["current_parameters"].update(parameters)

        self.save_dashboard(dashboard)

    def record_position_entry(self, entry_price: float, entry_time: str = None):
        """Record position entry"""
        dashboard = self.load_dashboard()
        dashboard["positions"]["active_position"] = True
        dashboard["positions"]["entry_price"] = entry_price
        dashboard["positions"]["entry_time"] = entry_time or datetime.now().isoformat()

        dashboard["alerts"].append({
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": f"Position OPENED 📈 - Entry: {entry_price:.2f}"
        })

        self.save_dashboard(dashboard)

    def record_position_exit(self, exit_price: float, pnl_percent: float):
        """Record position exit"""
        dashboard = self.load_dashboard()
        dashboard["positions"]["active_position"] = False

        # Update trade log
        if pnl_percent > 0:
            dashboard["trade_log"]["winning_trades"] += 1
        else:
            dashboard["trade_log"]["losing_trades"] += 1

        dashboard["trade_log"]["total_trades"] += 1
        dashboard["trade_log"]["pnl"] += pnl_percent

        level = "INFO" if pnl_percent > 0 else "WARNING"
        message = f"Position CLOSED {'✅' if pnl_percent > 0 else '⚠️'} - Exit: {exit_price:.2f} | P&L: {pnl_percent:+.2f}%"

        dashboard["alerts"].append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        })

        self.save_dashboard(dashboard)

    def add_alert(self, level: str, message: str):
        """Add alert to dashboard"""
        dashboard = self.load_dashboard()
        dashboard["alerts"].append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        })

        # Keep only last 100 alerts
        dashboard["alerts"] = dashboard["alerts"][-100:]

        self.save_dashboard(dashboard)

    def get_summary(self) -> str:
        """Get text summary of dashboard"""
        dashboard = self.load_dashboard()

        summary = f"""
{'='*60}
CLARITY ACT PAIR TRADING - REAL-TIME DASHBOARD
{'='*60}

⏰ Timestamp: {dashboard['timestamp']}
📊 System Status: {dashboard['system_status']}

--- COMMITTEE VOTE ---
📅 Date: {dashboard['committee_vote']['date']} @ {dashboard['committee_vote']['time']}
🗳️  Status: {dashboard['committee_vote']['status'].upper()}
📊 Outcome: {dashboard['committee_vote']['outcome'] or 'Pending'}

--- SENATE FLOOR VOTE ---
📅 Date: {dashboard['senate_floor_vote']['date'] or 'Not confirmed'}
📊 Polymarket Odds: {dashboard['senate_floor_vote']['polymarket_odds']}%

--- MARKET DATA ---
₿ BTC: ${dashboard['market_data']['btc_price'] or 'N/A'}
Ξ ETH: ${dashboard['market_data']['eth_price'] or 'N/A'}
📈 BTC/ETH: {dashboard['market_data']['btc_eth_ratio'] or 'N/A'}

--- STRATEGY ---
🔄 Trading Enabled: {dashboard['strategy']['trading_enabled']}
📊 MA Window: {dashboard['strategy']['current_parameters']['ma_window']}
🛑 Stop Loss: {dashboard['strategy']['current_parameters']['stop_loss_percent']}%

--- POSITIONS ---
✅ Active: {dashboard['positions']['active_position']}
💰 Entry: {dashboard['positions']['entry_price'] or 'N/A'}

--- PERFORMANCE ---
✅ Wins: {dashboard['trade_log']['winning_trades']}
❌ Losses: {dashboard['trade_log']['losing_trades']}
📊 Total P&L: {dashboard['trade_log']['pnl']:+.2f}%

--- RECENT ALERTS ---
"""

        for alert in dashboard['alerts'][-5:]:
            summary += f"\n{alert['timestamp']} [{alert['level']}]: {alert['message']}"

        summary += f"\n{'='*60}\n"
        return summary


if __name__ == "__main__":
    dashboard = RealtimeMonitorDashboard()
    dashboard.init_dashboard()

    # Test updates
    dashboard.update_committee_vote_status("pending")
    dashboard.update_market_data(65000, 3500, 18.57, 18.50)
    dashboard.add_alert("INFO", "System initialized and ready for trading")

    print(dashboard.get_summary())
