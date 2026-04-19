import json
from datetime import datetime
from typing import Dict, List
from pathlib import Path

class WhaleReporter:
    def __init__(self, output_dir: str = "data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_json_report(self, backtest_results: List[Dict]) -> Dict:
        roi_values = [r.get('roi_pct', 0) for r in backtest_results if 'roi_pct' in r]
        
        if not roi_values:
            return {"error": "No backtest results"}
        
        positive_count = sum(1 for r in roi_values if r > 0)
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_whales_analyzed": len(backtest_results),
                "average_roi_pct": sum(roi_values) / len(roi_values),
                "positive_count": positive_count,
                "win_rate_pct": (positive_count / len(roi_values) * 100),
                "max_roi_pct": max(roi_values),
                "min_roi_pct": min(roi_values)
            },
            "results": backtest_results
        }
        
        return report

    def generate_japanese_report(self, analysis: Dict) -> str:
        report = f"""
{'='*70}
BTC 大口ウォレット期待値分析レポート
{'='*70}

【分析日時】
{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}

【分析対象】
- ウォレット数: {analysis.get('total_whales_analyzed', 0)}個
- 平均ROI: {analysis.get('average_roi_pct', 0):+.2f}%
- 勝率: {analysis.get('win_rate_pct', 0):.1f}% ({analysis.get('positive_count', 0)}/{analysis.get('total_whales_analyzed', 0)})

【結論】
{analysis.get('conclusion', 'N/A')}

【詳細データ】
- 現在のBTC価格: ${analysis.get('current_btc_price', 'N/A'):,.0f}
- 分析期間: {analysis.get('analysis_days', 'N/A')}日

{'='*70}
"""
        return report

    def save_reports(self, json_report: Dict, japanese_text: str) -> tuple:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        json_file = self.output_dir / f"backtest_results_{timestamp}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_report, f, ensure_ascii=False, indent=2)
        
        txt_file = self.output_dir / f"backtest_report_{timestamp}.txt"
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(japanese_text)
        
        return json_file, txt_file
