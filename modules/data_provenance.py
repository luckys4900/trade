from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DataSource(Enum):
    JQUANTS = "J-Quants公式"
    YFINANCE_REALTIME = "yfinance(実データ)"
    YFINANCE_CACHED = "yfinanceキャッシュ"
    SYNTHETIC = "合成データ"
    MANUAL_INPUT = "CLI手入力"
    PROXY_CME = "CME先物プロキシ"
    UNKNOWN = "出所不明"


@dataclass
class DataProvenance:
    source: DataSource
    fetched_at: datetime
    as_of: datetime
    fallback_chain: list[str]

    @property
    def is_trustworthy_for_live_trading(self) -> bool:
        return self.source in {
            DataSource.JQUANTS,
            DataSource.YFINANCE_REALTIME,
            DataSource.MANUAL_INPUT,
            DataSource.PROXY_CME,
        }

    @property
    def warning_level(self) -> str:
        if self.source == DataSource.SYNTHETIC:
            return "CRITICAL: 合成データ。実取引判断に使用禁止。"
        if self.source == DataSource.YFINANCE_CACHED:
            return "WARN: キャッシュデータ。鮮度確認必須。"
        if self.source == DataSource.UNKNOWN:
            return "CRITICAL: 出所不明。レポート廃棄推奨。"
        return ""


def render_data_provenance_block(provenance: DataProvenance) -> str:
    suitability = "適合" if provenance.is_trustworthy_for_live_trading else "不適格"
    chain = " -> ".join(provenance.fallback_chain)
    warning = provenance.warning_level
    warning_line = warning if warning else "なし"
    return (
        "## Data Provenance\n\n"
        "| 項目 | 値 |\n"
        "|---|---|\n"
        f"| データソース | **{provenance.source.value}** |\n"
        f"| 取得時刻 | {provenance.fetched_at.strftime('%Y-%m-%d %H:%M:%S JST')} |\n"
        f"| データas-of | {provenance.as_of.strftime('%Y-%m-%d %H:%M:%S JST')} |\n"
        f"| 試行チェーン | {chain} |\n"
        f"| 実取引判断適性 | {'✅' if provenance.is_trustworthy_for_live_trading else '❌'} {suitability} |\n"
        f"| 警告 | {warning_line} |\n\n"
        "### 影響範囲\n"
        f"- 前日OHLC: {provenance.source.value}\n"
        f"- ATR/RVOL: {provenance.source.value}\n"
        f"- 窓埋め統計: {provenance.source.value}\n"
        f"- モメンタム指標: {provenance.source.value}\n"
    )

