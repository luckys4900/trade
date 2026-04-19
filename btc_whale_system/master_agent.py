import logging
from datetime import datetime
from typing import Dict
from .whale_scraper import BlockchairScraper
from .whale_analyzer import WhaleAnalyzer
from .whale_backtester import WhaleBacktester
from .whale_reporter import WhaleReporter
from .database import WhaleDatabase

class MasterAgent:
    def __init__(self):
        self.scraper = BlockchairScraper()
        self.analyzer = WhaleAnalyzer()
        self.backtester = WhaleBacktester()
        self.reporter = WhaleReporter()
        self.db = WhaleDatabase()
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(__name__)
        handler = logging.FileHandler(f"logs/btc_whale_{datetime.now().strftime('%Y%m%d')}.log")
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

    def run_daily_cycle(self) -> Dict:
        self.logger.info("="*70)
        self.logger.info("Starting daily BTC whale discovery cycle")
        
        result = {
            "status": "started",
            "timestamp": datetime.now().isoformat(),
            "whales_discovered": 0,
            "whales_analyzed": 0,
            "report_files": []
        }
        
        try:
            self.logger.info("[Phase 1] Fetching whales from Blockchair...")
            whales = self.scraper.fetch_top_whales(min_btc=100, limit=50)
            
            if not whales:
                self.logger.warning("No whales found, using backup data")
                whales = self.scraper._load_backup_data()
            
            self.logger.info(f"  Found {len(whales)} whales")
            result['whales_discovered'] = len(whales)
            self.db.save_whales(whales)
            
            self.logger.info("[Phase 2] Analyzing ROI and running backtests...")
            backtest_results = []
            
            for whale in whales[:20]:
                roi_data = self.analyzer.calculate_roi(whale)
                
                if "error" not in roi_data:
                    self.db.save_roi_result(roi_data)
                    backtest = self.backtester.run_backtest(roi_data)
                    self.db.save_backtest_result(backtest)
                    backtest_results.append(backtest)
                    self.logger.info(f"  {whale['address'][:16]}: {roi_data['roi_pct']:+.2f}%")
            
            result['whales_analyzed'] = len(backtest_results)
            
            self.logger.info("[Phase 3] Generating reports...")
            json_report = self.reporter.generate_json_report(backtest_results)
            analysis = self._analyze_expected_value(json_report)
            japanese_report = self.reporter.generate_japanese_report(analysis)
            
            json_file, txt_file = self.reporter.save_reports(json_report, japanese_report)
            result['report_files'] = [str(json_file), str(txt_file)]
            
            self.logger.info(f"  Reports saved: {json_file}, {txt_file}")
            
            snapshot_file = self.db.export_daily_snapshot()
            result['snapshot_file'] = snapshot_file
            self.logger.info(f"  DB snapshot: {snapshot_file}")
            
            result['status'] = 'success'
            self.logger.info("Daily cycle completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error during daily cycle: {e}")
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result

    def _analyze_expected_value(self, json_report: Dict) -> Dict:
        summary = json_report.get('summary', {})
        win_rate = summary.get('win_rate_pct', 0)
        avg_roi = summary.get('average_roi_pct', 0)
        
        if win_rate >= 80 and avg_roi > 50:
            conclusion = "STRONG: 期待値が十分に正である。トレード推奨"
        elif win_rate >= 60 and avg_roi > 20:
            conclusion = "MODERATE: 期待値がある程度正である。さらなる検証推奨"
        else:
            conclusion = "WEAK: 期待値が不十分である。トレード非推奨"
        
        return {
            **summary,
            "conclusion": conclusion,
            "current_btc_price": self.analyzer.get_btc_price_current(),
            "analysis_days": 365
        }
