from typing import Dict, List, Optional
import numpy as np


class PairSelector:
    """Filter and rank cryptocurrency pairs by statistical significance."""

    def __init__(
        self,
        min_p_value: float = 0.05,
        max_hurst: float = 0.5,
        min_sharpe: float = -1.0,
        exclude_patterns: Optional[List[str]] = None
    ):
        """
        Initialize pair selector with filtering criteria.

        Args:
            min_p_value: Maximum p-value for statistical significance (lower is better)
            max_hurst: Maximum Hurst exponent (lower = more mean-reverting)
            min_sharpe: Minimum Sharpe ratio (placeholder for future use)
            exclude_patterns: List of symbol patterns to exclude (e.g., ['BTC/USD'])
        """
        self.min_p_value = min_p_value
        self.max_hurst = max_hurst
        self.min_sharpe = min_sharpe
        self.exclude_patterns = exclude_patterns or []

    def filter_pairs(self, analysis_results: Dict) -> List[Dict]:
        """
        Filter pairs by statistical significance criteria.

        Args:
            analysis_results: Dict of {pair_name: analysis_result} from CointegrationAnalyzer

        Returns:
            List of filtered pair analysis results
        """
        filtered = []

        for pair_name, analysis in analysis_results.items():
            # Check if meets statistical criteria
            if analysis['johansen_p_value'] >= self.min_p_value:
                continue
            if analysis['hurst_exponent'] >= self.max_hurst:
                continue

            # Check if excluded by pattern
            symbol1, symbol2 = analysis['pair']
            excluded = False
            for pattern in self.exclude_patterns:
                if pattern == symbol1 or pattern == symbol2:
                    excluded = True
                    break

            if not excluded:
                filtered.append(analysis)

        return filtered

    def score_pair(self, analysis: Dict) -> float:
        """
        Calculate numerical score for a pair (0-100).

        Score favors:
        - Lower Hurst exponent (more mean-reverting)
        - Lower p-value (more statistically significant)

        Args:
            analysis: Single pair analysis result

        Returns:
            Score between 0 and 100
        """
        hurst = analysis['hurst_exponent']
        p_value = analysis['johansen_p_value']

        # Normalize to [0, 1] with reasonable bounds
        hurst_norm = min(hurst / 1.0, 1.0)  # Hurst typically 0-1
        p_norm = min(p_value / 0.1, 1.0)  # P-value bound at 0.1

        # Score = 100 × (1 - hurst_normalized) × (1 - p_value_normalized)
        score = 100.0 * (1.0 - hurst_norm) * (1.0 - p_norm)

        return float(score)

    def get_top_pairs(self, analysis_results: Dict, n: int = 15) -> List[Dict]:
        """
        Get top N pairs ranked by score.

        Args:
            analysis_results: Dict of all pair analysis results
            n: Number of top pairs to return

        Returns:
            List of top N pairs with scores, sorted descending by score
        """
        filtered = self.filter_pairs(analysis_results)

        # Calculate scores
        for pair in filtered:
            pair['score'] = self.score_pair(pair)

        # Sort by score descending
        sorted_pairs = sorted(filtered, key=lambda x: x['score'], reverse=True)

        return sorted_pairs[:n]
