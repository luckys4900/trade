"""
Senate Banking Committee Vote Monitor - Real-time Tracking
Clarity Act HR3633 Committee Markup Vote
Date: 2026-05-14 10:30 AM ET
"""

import requests
import json
from datetime import datetime
from typing import Dict, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CongressGovMonitor:
    """
    監視: Congress.govから委員会投票状況をリアルタイム追跡
    """

    def __init__(self):
        self.bill_url = "https://api.congress.gov/v3/bill/119/hr/3633"
        self.committee_name = "Senate Banking Committee"
        self.committee_markup_date = datetime(2026, 5, 14, 10, 30)
        self.last_update = None

    def check_committee_status(self) -> Dict:
        """
        Check current status of Senate Banking Committee markup vote
        Returns: {
            'status': 'pending'/'in_progress'/'passed'/'failed',
            'timestamp': datetime,
            'details': str
        }
        """
        try:
            params = {"format": "json", "limit": 100}
            response = requests.get(self.bill_url, params=params, timeout=10)

            if response.status_code != 200:
                logger.error(f"Congress.gov API error: {response.status_code}")
                return self._unknown_status()

            data = response.json()
            self.last_update = datetime.now()

            # Search for recent committee actions
            if "bill" in data:
                actions = data["bill"].get("actions", [])

                # Look for Banking Committee actions
                for action in actions:
                    if "Banking" in action.get("text", ""):
                        action_date = action.get("actionDate", "")
                        action_text = action.get("text", "")

                        # Committee vote indicators
                        if "passed" in action_text.lower():
                            return self._format_status("passed", action_text)
                        elif "defeated" in action_text.lower() or "failed" in action_text.lower():
                            return self._format_status("failed", action_text)
                        elif "pending" in action_text.lower() or "scheduled" in action_text.lower():
                            return self._format_status("pending", action_text)

            return self._pending_status()

        except Exception as e:
            logger.error(f"Error checking committee status: {e}")
            return self._unknown_status()

    def get_vote_details(self) -> Dict:
        """
        Get detailed vote breakdown if available
        Returns: {
            'republican_votes': int,
            'democrat_votes': int,
            'total_votes': int,
            'outcome': str
        }
        """
        # Note: Detailed vote breakdown may not be available immediately
        # This is a placeholder for when vote results are published
        try:
            response = requests.get(
                f"{self.bill_url}/actions",
                params={"format": "json"},
                timeout=10
            )

            if response.status_code == 200:
                # Parse vote details when available
                pass

        except Exception as e:
            logger.error(f"Error getting vote details: {e}")

        return self._unknown_vote_details()

    def _format_status(self, status: str, details: str) -> Dict:
        return {
            "status": status,
            "timestamp": self.last_update or datetime.now(),
            "details": details,
            "committee": self.committee_name
        }

    def _pending_status(self) -> Dict:
        return {
            "status": "pending",
            "timestamp": datetime.now(),
            "details": f"Committee markup scheduled for {self.committee_markup_date.strftime('%Y-%m-%d %H:%M ET')}",
            "committee": self.committee_name
        }

    def _unknown_status(self) -> Dict:
        return {
            "status": "unknown",
            "timestamp": datetime.now(),
            "details": "Could not retrieve status from Congress.gov",
            "committee": self.committee_name
        }

    def _unknown_vote_details(self) -> Dict:
        return {
            "republican_votes": None,
            "democrat_votes": None,
            "total_votes": None,
            "outcome": None
        }


class PolymarketMonitor:
    """
    監視: Polymarketのオッズを自動追跡
    """

    def __init__(self):
        self.polymarket_url = "https://polymarket.com/event/clarity-act-signed-into-law-in-2026"
        self.api_base = "https://api.polymarket.com"
        self.odds_history = []

    def get_current_odds(self) -> Tuple[Optional[float], Dict]:
        """
        Get current Polymarket odds for Clarity Act passage
        Returns: (odds_percent, metadata)
        """
        try:
            # Note: Polymarket API structure may vary
            # This is a generalized approach
            response = requests.get(f"{self.api_base}/markets", timeout=10)

            if response.status_code == 200:
                markets = response.json()

                # Search for Clarity Act market
                for market in markets:
                    if "clarity" in market.get("question", "").lower():
                        yes_odds = market.get("yes_price")
                        no_odds = market.get("no_price")

                        if yes_odds:
                            odds_percent = yes_odds * 100
                            self.odds_history.append({
                                "timestamp": datetime.now(),
                                "odds": odds_percent,
                                "yes_price": yes_odds,
                                "no_price": no_odds
                            })
                            return odds_percent, {"yes": yes_odds, "no": no_odds}

            return None, {"error": "Market not found"}

        except Exception as e:
            logger.error(f"Error fetching Polymarket odds: {e}")
            return None, {"error": str(e)}

    def get_odds_trend(self) -> list:
        """
        Get recent odds trend (last 24 hours or last N readings)
        Returns: list of {timestamp, odds} dicts
        """
        return self.odds_history[-100:] if self.odds_history else []

    def estimate_market_probability(self) -> float:
        """
        Estimate implied probability from current odds
        """
        if not self.odds_history:
            return None

        latest = self.odds_history[-1]
        return latest["odds"]


class VoteResultAnalyzer:
    """
    分析: 投票結果に基づく戦略判定
    """

    def __init__(self):
        self.congress_monitor = CongressGovMonitor()
        self.polymarket_monitor = PolymarketMonitor()

    def should_proceed_with_strategy(self) -> Tuple[bool, str]:
        """
        Determine if strategy should proceed based on vote outcome
        Returns: (proceed, reason)
        """
        committee_status = self.congress_monitor.check_committee_status()
        polymarket_odds, _ = self.polymarket_monitor.get_current_odds()

        # Committee vote passed
        if committee_status["status"] == "passed":
            if polymarket_odds and polymarket_odds > 50:
                return True, f"Committee vote PASSED. Polymarket odds: {polymarket_odds:.1f}%. Proceeding with strategy."
            else:
                return True, f"Committee vote PASSED. Proceeding with strategy (low market odds, but legal progress made)."

        # Committee vote failed
        elif committee_status["status"] == "failed":
            return False, "Committee vote FAILED. Strategy suspended. Bill will need rework or 2030+ timeline."

        # Still pending
        elif committee_status["status"] == "pending":
            return None, f"Committee vote still pending. Expected: {self.congress_monitor.committee_markup_date}"

        else:
            return None, "Vote status unknown. Check Congress.gov directly."

    def generate_report(self) -> Dict:
        """
        Generate comprehensive status report
        """
        committee_status = self.congress_monitor.check_committee_status()
        polymarket_odds, polymarket_meta = self.polymarket_monitor.get_current_odds()
        proceed, reason = self.should_proceed_with_strategy()

        return {
            "timestamp": datetime.now().isoformat(),
            "committee_status": committee_status,
            "polymarket_odds": polymarket_odds,
            "polymarket_metadata": polymarket_meta,
            "strategy_proceed": proceed,
            "reason": reason,
            "odds_trend": self.polymarket_monitor.get_odds_trend()[-5:] if self.polymarket_monitor.get_odds_trend() else []
        }


if __name__ == "__main__":
    analyzer = VoteResultAnalyzer()
    report = analyzer.generate_report()
    print(json.dumps(report, indent=2, default=str))
