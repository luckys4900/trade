import json
from pathlib import Path

import pandas as pd
import pytest

from SYSTEM import qwen_unified_live as live


class DummyLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def info(self, message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        return None

    def debug(self, message: str) -> None:
        return None


class DummyHL:
    def __init__(self, config: live.Config, logger: DummyLogger) -> None:
        self.config = config
        self.logger = logger
        self.position: dict | None = None
        self.authenticated = True

    def get_current_price(self, symbol: str) -> float:
        return 100.0

    def get_user_state(self) -> dict | None:
        return {"stub": True}

    def equity_margin_withdrawable_from_state(
        self, user_state: dict | None
    ) -> tuple[float, float, float]:
        return (1000.0, 0.0, 1000.0)

    def parse_position_from_state(
        self, user_state: dict | None, symbol: str
    ) -> dict | None:
        return self.position

    def get_balance(self) -> float:
        return 1000.0

    def get_position(self, symbol: str) -> dict | None:
        return self.position

    def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float | None = None,
        reduce_only: bool = False,
    ) -> dict:
        return {
            "status": "ok",
            "side": side,
            "size": size,
            "price": price,
            "reduce_only": reduce_only,
        }

    def get_size_decimals(self, symbol: str) -> int:
        return 4


@pytest.fixture
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> live.UnifiedEngine:
    monkeypatch.setattr(live, "HyperliquidClient", DummyHL)
    logger = DummyLogger()
    config = live.Config()
    config.state_file = str(tmp_path / "state.json")
    config.alignment_log_file = str(tmp_path / "alignment.json")
    config.log_dir = str(tmp_path / "logs")
    return live.UnifiedEngine(config, logger)


def test_save_state_persists_contrarian_state(engine: live.UnifiedEngine) -> None:
    engine.contrarian.in_pos = True
    engine.contrarian.side = "SHORT"
    engine.contrarian.size = 1.25
    engine.contrarian.entry_px = 101.0
    engine.last_processed_bar_ts = 4102444800000

    engine.save_state()

    saved = json.loads(Path(engine.c.state_file).read_text(encoding="utf-8"))
    assert saved["contrarian"]["in_pos"] is True
    assert saved["contrarian"]["side"] == "SHORT"
    assert saved["last_processed_bar_ts"] == 4102444800000


def test_read_contrarian_signal_returns_valid_payload(
    engine: live.UnifiedEngine, tmp_path: Path
) -> None:
    signal_path = tmp_path / "kronos_contrarian_signal.json"
    signal_path.write_text(
        json.dumps(
            {
                "valid": True,
                "timestamp": 4102444800000,
                "contrarian_direction": "LONG",
                "contrarian_signal": 1,
            }
        ),
        encoding="utf-8",
    )
    engine.c.contrarian_signal_file = str(signal_path)

    signal = engine._read_contrarian_signal()

    assert signal is not None
    assert signal["contrarian_direction"] == "LONG"


def test_run_once_invokes_contrarian_management(
    engine: live.UnifiedEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"exit": 0, "entry": 0}

    df = pd.DataFrame(
        [
            {
                "close": 100.0,
                "rsi": 50.0,
                "ocpm_trend": "RANGE",
                "atr": 2.0,
                "ocpm_long": 0,
                "ocpm_short": 0,
                "mr_long": 0,
                "mr_short": 0,
                "rsi_swing_long": 0,
                "rsi_swing_short": 0,
            }
        ]
    )
    df.index = pd.to_datetime(["2026-04-12 00:00:00"])

    monkeypatch.setattr(live, "fetch_ohlcv", lambda c, lg: df)
    monkeypatch.setattr(live, "compute_indicators", lambda value, c: value)
    monkeypatch.setattr(engine, "_save_account_state", lambda px, us: None)
    monkeypatch.setattr(engine, "_detect_confluence", lambda r: None)
    monkeypatch.setattr(engine, "_manage_ocpm_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_manage_mr_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_manage_rsi_swing_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_check_ocpm_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_check_mr_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_check_rsi_swing_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_sync_positions", lambda: None)
    monkeypatch.setattr(engine, "save_state", lambda: None)
    monkeypatch.setattr(
        engine,
        "_manage_contrarian_exit",
        lambda r, px: calls.__setitem__("exit", calls["exit"] + 1),
        raising=False,
    )
    monkeypatch.setattr(
        engine,
        "_check_contrarian_entry",
        lambda r, px, bal: calls.__setitem__("entry", calls["entry"] + 1),
        raising=False,
    )

    engine.run_once()

    assert calls["exit"] == 1
    assert calls["entry"] == 1


def test_run_once_only_advances_bar_on_new_closed_candle(
    engine: live.UnifiedEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build_df(count: int) -> pd.DataFrame:
        rows = []
        for _ in range(count):
            rows.append(
                {
                    "close": 100.0,
                    "rsi": 50.0,
                    "ocpm_trend": "RANGE",
                    "atr": 2.0,
                    "ocpm_long": 0,
                    "ocpm_short": 0,
                    "mr_long": 0,
                    "mr_short": 0,
                    "rsi_swing_long": 0,
                    "rsi_swing_short": 0,
                }
            )
        df = pd.DataFrame(rows)
        df.index = pd.date_range("2026-04-12 00:00:00", periods=count, freq="4h")
        return df

    datasets = [build_df(2), build_df(2), build_df(3)]
    monkeypatch.setattr(live, "fetch_ohlcv", lambda c, lg: datasets.pop(0))
    monkeypatch.setattr(live, "compute_indicators", lambda value, c: value)
    monkeypatch.setattr(engine, "_save_account_state", lambda px, us: None)
    monkeypatch.setattr(engine, "_detect_confluence", lambda r: None)
    monkeypatch.setattr(engine, "_manage_ocpm_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_manage_mr_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_manage_rsi_swing_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_manage_contrarian_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_check_ocpm_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_check_mr_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_check_rsi_swing_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_check_contrarian_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_sync_positions", lambda: None)
    monkeypatch.setattr(engine, "save_state", lambda: None)

    engine.run_once()
    first_bar = engine.current_bar
    first_ts = engine.last_processed_bar_ts

    engine.run_once()
    assert engine.current_bar == first_bar
    assert engine.last_processed_bar_ts == first_ts

    engine.run_once()
    assert engine.current_bar == first_bar + 1
    assert engine.last_processed_bar_ts > first_ts


def test_run_once_skips_entry_checks_without_new_closed_candle(
    engine: live.UnifiedEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"entry": 0}
    df = pd.DataFrame(
        [
            {
                "close": 100.0,
                "rsi": 50.0,
                "ocpm_trend": "RANGE",
                "atr": 2.0,
                "ocpm_long": 0,
                "ocpm_short": 0,
                "mr_long": 0,
                "mr_short": 0,
                "rsi_swing_long": 0,
                "rsi_swing_short": 0,
            },
            {
                "close": 101.0,
                "rsi": 51.0,
                "ocpm_trend": "RANGE",
                "atr": 2.0,
                "ocpm_long": 0,
                "ocpm_short": 0,
                "mr_long": 0,
                "mr_short": 0,
                "rsi_swing_long": 0,
                "rsi_swing_short": 0,
            },
        ]
    )
    df.index = pd.to_datetime(["2026-04-12 00:00:00", "2026-04-12 04:00:00"])

    monkeypatch.setattr(live, "fetch_ohlcv", lambda c, lg: df)
    monkeypatch.setattr(live, "compute_indicators", lambda value, c: value)
    monkeypatch.setattr(engine, "_save_account_state", lambda px, us: None)
    monkeypatch.setattr(engine, "_detect_confluence", lambda r: None)
    monkeypatch.setattr(engine, "_manage_ocpm_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_manage_mr_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_manage_rsi_swing_exit", lambda r, px: None)
    monkeypatch.setattr(engine, "_manage_contrarian_exit", lambda r, px: None)
    monkeypatch.setattr(
        engine,
        "_check_ocpm_entry",
        lambda r, px, bal: calls.__setitem__("entry", calls["entry"] + 1),
    )
    monkeypatch.setattr(engine, "_check_mr_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_check_rsi_swing_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_check_contrarian_entry", lambda r, px, bal: None)
    monkeypatch.setattr(engine, "_sync_positions", lambda: None)
    monkeypatch.setattr(engine, "save_state", lambda: None)

    engine.run_once()
    engine.run_once()

    assert calls["entry"] == 1


def test_sync_positions_includes_contrarian_and_avoids_double_count(
    engine: live.UnifiedEngine,
) -> None:
    engine.ocpm.in_pos = True
    engine.ocpm.side = "LONG"
    engine.ocpm.size = 1.0
    engine.rsi_swing.in_pos = True
    engine.rsi_swing.side = "LONG"
    engine.rsi_swing.size = 2.0
    engine.contrarian.in_pos = True
    engine.contrarian.side = "SHORT"
    engine.contrarian.size = 0.5
    engine.hl.position = {"side": "LONG", "size": 2.5, "entry": 100.0}

    engine._sync_positions()

    assert engine.lg.warnings == []


def test_contrarian_does_not_reenter_same_signal(
    engine: live.UnifiedEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal_ts = 4102444800000
    signal_path = tmp_path / "kronos_contrarian_signal.json"
    signal_path.write_text(
        json.dumps(
            {
                "valid": True,
                "timestamp": signal_ts,
                "contrarian_direction": "LONG",
                "contrarian_signal": 1,
            }
        ),
        encoding="utf-8",
    )
    engine.c.contrarian_signal_file = str(signal_path)
    engine.contrarian.last_signal_ts = signal_ts
    opened = {"count": 0}

    monkeypatch.setattr(engine, "_log_trade_alignment", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        engine,
        "_open_strat",
        lambda *args, **kwargs: opened.__setitem__("count", opened["count"] + 1),
    )

    engine._check_contrarian_entry(pd.Series({"atr": 2.0}), 100.0, 1000.0)

    assert opened["count"] == 0


def test_contrarian_skips_signal_older_than_eval_bar(
    engine: live.UnifiedEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal_path = tmp_path / "kronos_contrarian_signal.json"
    signal_path.write_text(
        json.dumps(
            {
                "valid": True,
                "timestamp": 1_700_000_000_000,
                "contrarian_direction": "LONG",
                "contrarian_signal": 1,
            }
        ),
        encoding="utf-8",
    )
    engine.c.contrarian_signal_file = str(signal_path)
    engine._current_eval_bar_ts = 1_800_000_000_000
    opened = {"count": 0}

    monkeypatch.setattr(
        engine,
        "_open_strat",
        lambda *args, **kwargs: (
            opened.__setitem__("count", opened["count"] + 1) or True
        ),
    )

    engine._check_contrarian_entry(pd.Series({"atr": 2.0}), 100.0, 1000.0)

    assert opened["count"] == 0


def test_round_order_size_rounds_down_to_exchange_precision() -> None:
    assert live.round_order_size(0.0005646559258475472, 4) == 0.0005


def test_place_order_uses_ioc_limit_and_rounded_size() -> None:
    class FakeInfo:
        def meta(self) -> dict:
            return {"universe": [{"name": "BTC", "szDecimals": 4}]}

    class FakeExchange:
        def __init__(self) -> None:
            self.payload = None

        def order(self, **kwargs):
            self.payload = kwargs
            return {"status": "ok"}

    client = live.HyperliquidClient.__new__(live.HyperliquidClient)
    client.config = live.Config()
    client.logger = DummyLogger()
    client._size_decimals_cache = {}
    client.info = FakeInfo()
    client.exchange = FakeExchange()
    client.authenticated = True
    client.OrderType = lambda **kwargs: kwargs

    result = client.place_order("BTC", "buy", 0.0005646559258475472, price=70000.12)

    assert result == {"status": "ok"}
    assert client.exchange.payload["sz"] == 0.0005
    assert client.exchange.payload["order_type"] == {"limit": {"tif": "Ioc"}}


def test_open_strat_stores_rounded_size(engine: live.UnifiedEngine) -> None:
    engine._open_strat(
        engine.contrarian, "LONG", 0.0005651622364528542, 70000.0, 69000.0, tp=72000.0
    )

    assert engine.contrarian.size == 0.0005


def test_place_order_rejects_unfilled_ioc_response() -> None:
    class FakeInfo:
        def meta(self) -> dict:
            return {"universe": [{"name": "BTC", "szDecimals": 4}]}

    class FakeExchange:
        def order(self, **kwargs):
            return {"response": {"data": {"statuses": [{"resting": {"oid": 1}}]}}}

    client = live.HyperliquidClient.__new__(live.HyperliquidClient)
    client.config = live.Config()
    client.logger = DummyLogger()
    client._size_decimals_cache = {}
    client.info = FakeInfo()
    client.exchange = FakeExchange()
    client.authenticated = True
    client.OrderType = lambda **kwargs: kwargs

    result = client.place_order("BTC", "buy", 0.001, price=70000.12)

    assert result is None


def test_contrarian_logs_alignment_only_after_successful_fill(
    engine: live.UnifiedEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal_path = tmp_path / "kronos_contrarian_signal.json"
    signal_path.write_text(
        json.dumps(
            {
                "valid": True,
                "timestamp": 4102444800000,
                "contrarian_direction": "LONG",
                "contrarian_signal": 1,
            }
        ),
        encoding="utf-8",
    )
    engine.c.contrarian_signal_file = str(signal_path)
    engine._current_eval_bar_ts = 4102440000000
    logged = {"count": 0}

    monkeypatch.setattr(engine, "_open_strat", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        engine,
        "_log_trade_alignment",
        lambda *args, **kwargs: logged.__setitem__("count", logged["count"] + 1),
    )

    engine._check_contrarian_entry(pd.Series({"atr": 2.0}), 100.0, 1000.0)

    assert logged["count"] == 0


def test_compute_indicators_adds_volatility_percentile() -> None:
    rows = []
    for i in range(80):
        rows.append(
            {
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.0 + i,
                "volume": 10_000.0 + i,
            }
        )
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-01-01", periods=len(rows), freq="4h")

    result = live.compute_indicators(df, live.Config())

    assert "vol_pct" in result.columns
    assert result["vol_pct"].iloc[-1] >= 0
    assert "ocpm_ema_regime" in result.columns
    assert "ocpm_hard_long_ok" in result.columns
    assert "ocpm_hard_short_ok" in result.columns


def test_ocpm_hard_regime_blocks_long_entry_when_not_satisfied(
    engine: live.UnifiedEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = {"count": 0}

    monkeypatch.setattr(engine, "_read_whale_signal", lambda: None)
    monkeypatch.setattr(engine, "_read_macro_state", lambda: None)
    monkeypatch.setattr(engine, "_read_kronos_signal", lambda: None)
    monkeypatch.setattr(engine, "_get_confluence_multiplier", lambda side: 1.0)
    monkeypatch.setattr(
        engine,
        "_open_strat",
        lambda *args, **kwargs: (
            opened.__setitem__("count", opened["count"] + 1) or True
        ),
    )

    row = pd.Series(
        {
            "atr": 2.0,
            "ocpm_trend": "UPTREND",
            "ocpm_long": 1,
            "ocpm_short": 0,
            "ocpm_donchian_high": 102.0,
            "ocpm_donchian_low": 98.0,
            "rsi_prev": 47.0,
            "rsi": 49.0,
            "ocpm_hard_long_ok": 0,
        }
    )
    engine._check_ocpm_entry(row, 100.0, 1000.0)

    assert opened["count"] == 0


def test_ocpm_hard_regime_allows_long_entry_when_satisfied(
    engine: live.UnifiedEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = {"count": 0}
    logged = {"count": 0}

    monkeypatch.setattr(engine, "_read_whale_signal", lambda: None)
    monkeypatch.setattr(engine, "_read_macro_state", lambda: None)
    monkeypatch.setattr(engine, "_read_kronos_signal", lambda: None)
    monkeypatch.setattr(engine, "_get_confluence_multiplier", lambda side: 1.0)
    monkeypatch.setattr(
        engine,
        "_open_strat",
        lambda *args, **kwargs: (
            opened.__setitem__("count", opened["count"] + 1) or True
        ),
    )
    monkeypatch.setattr(
        engine,
        "_log_trade_alignment",
        lambda *args, **kwargs: logged.__setitem__("count", logged["count"] + 1),
    )

    row = pd.Series(
        {
            "atr": 2.0,
            "ocpm_trend": "UPTREND",
            "ocpm_long": 1,
            "ocpm_short": 0,
            "ocpm_donchian_high": 102.0,
            "ocpm_donchian_low": 98.0,
            "rsi_prev": 47.0,
            "rsi": 49.0,
            "ocpm_hard_long_ok": 1,
        }
    )
    engine._check_ocpm_entry(row, 100.0, 1000.0)

    assert opened["count"] == 1
    assert logged["count"] == 1


def test_contrarian_skips_when_volatility_percentile_outside_gate(
    engine: live.UnifiedEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal_path = tmp_path / "kronos_contrarian_signal.json"
    signal_path.write_text(
        json.dumps(
            {
                "valid": True,
                "timestamp": 4102444800000,
                "contrarian_direction": "LONG",
                "contrarian_signal": 1,
            }
        ),
        encoding="utf-8",
    )
    engine.c.contrarian_signal_file = str(signal_path)
    engine._current_eval_bar_ts = 4102440000000
    opened = {"count": 0}

    monkeypatch.setattr(
        engine,
        "_open_strat",
        lambda *args, **kwargs: (
            opened.__setitem__("count", opened["count"] + 1) or True
        ),
    )

    engine._check_contrarian_entry(
        pd.Series({"atr": 2.0, "vol_pct": 90.0}), 100.0, 1000.0
    )

    assert opened["count"] == 0


def test_contrarian_opens_when_volatility_percentile_inside_gate(
    engine: live.UnifiedEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal_ts = 4102444800000
    signal_path = tmp_path / "kronos_contrarian_signal.json"
    signal_path.write_text(
        json.dumps(
            {
                "valid": True,
                "timestamp": signal_ts,
                "contrarian_direction": "LONG",
                "contrarian_signal": 1,
            }
        ),
        encoding="utf-8",
    )
    engine.c.contrarian_signal_file = str(signal_path)
    engine.c.contrarian_edge_filter_enabled = False
    engine._current_eval_bar_ts = 4102440000000
    logged = {"count": 0}

    monkeypatch.setattr(
        engine,
        "_log_trade_alignment",
        lambda *args, **kwargs: logged.__setitem__("count", logged["count"] + 1),
    )
    monkeypatch.setattr(
        engine,
        "_open_strat",
        lambda *args, **kwargs: True,
    )

    engine._check_contrarian_entry(
        pd.Series({"atr": 2.0, "vol_pct": 50.0}), 100.0, 1000.0
    )

    assert logged["count"] == 1
    assert engine.contrarian.last_signal_ts == signal_ts
