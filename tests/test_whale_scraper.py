import pytest
from unittest.mock import patch, MagicMock
from btc_whale_system.whale_scraper import BlockchairScraper


@pytest.fixture
def scraper():
    return BlockchairScraper()


def test_fetch_top_whales_success(scraper):
    """Top whalesの取得に成功"""
    mock_response = {
        "data": [
            {
                "address": "1A1z7agoat7SfNxBBwHqzj7hCoV7utwDu",
                "balance": 1000000000000000,  # satoshis
                "transaction_count": 1,
                "first_seen_receiving": 1231469665
            },
            {
                "address": "3J98t1WpEZ73CNmYviecrnyiWrnqRhWNLy",
                "balance": 14041100000000,
                "transaction_count": 2500,
                "first_seen_receiving": 1328613215
            }
        ]
    }

    with patch.object(scraper, '_request_blockchair') as mock_req:
        mock_req.return_value = mock_response
        whales = scraper.fetch_top_whales(min_btc=100, limit=10)

    assert len(whales) == 2
    assert whales[0]['address'] == "1A1z7agoat7SfNxBBwHqzj7hCoV7utwDu"
    assert whales[0]['balance_btc'] == 10000000.0
    assert whales[0]['first_seen_ts'] == 1231469665


def test_fetch_top_whales_retry_on_rate_limit(scraper):
    """Rate limitで自動リトライ"""
    with patch.object(scraper, '_request_blockchair') as mock_req:
        mock_req.side_effect = [
            Exception("429 Too Many Requests"),
            Exception("429 Too Many Requests"),
            {"data": []}  # 3回目で成功
        ]

        result = scraper.fetch_top_whales(min_btc=100, max_retries=3)
        assert result is not None
        assert mock_req.call_count == 3


def test_fetch_top_whales_fallback_on_error(scraper):
    """全リトライ失敗時、前日キャッシュを返す"""
    with patch.object(scraper, '_request_blockchair') as mock_req:
        mock_req.side_effect = Exception("API Error")
        with patch.object(scraper, '_load_backup_data') as mock_backup:
            mock_backup.return_value = [
                {"address": "cached_addr", "balance_btc": 100.0}
            ]

            result = scraper.fetch_top_whales(min_btc=100, max_retries=3)
            assert len(result) == 1
            assert result[0]['address'] == "cached_addr"
