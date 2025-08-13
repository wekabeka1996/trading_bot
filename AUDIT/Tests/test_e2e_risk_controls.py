import os
import pytest
import pytz
from unittest.mock import MagicMock

pytest.importorskip("binance")

import trading_bot.engine as eng_mod
from trading_bot.engine import Engine
from trading_bot.plan_parser import TradingPlan, GlobalSettings, PlanParser
from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal


@pytest.fixture(autouse=True)
def ensure_testnet_env(monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET", "true")


def build_engine(plan_date: str = "2025-08-08", emergency_sl: float = -0.03):
    plan = TradingPlan(
        plan_date=plan_date,
        plan_version="1.0",
        plan_type="e2e",
        risk_budget=0.01,
        global_settings=GlobalSettings(
            max_portfolio_risk=0.5,
            emergency_stop_loss=emergency_sl,
            daily_profit_target=0.02,
            max_concurrent_positions=3,
            max_notional_per_trade=1_000_000.0,
            margin_limit_pct=0.4,
        ),
        active_assets=[],
        trade_phases={},
        risk_triggers={},
        end_of_day_checklist=[],
    )
    # Создаём строго типизированные моки
    parser = MagicMock(spec=PlanParser)
    parser.load_and_validate.return_value = True
    parser.get_plan.return_value = plan

    exchange = MagicMock(spec=BinanceFuturesConnector)
    exchange.check_connection.return_value = True
    exchange.get_futures_account_balance.return_value = 10_000.0

    notifier = MagicMock(spec=TelegramNotifier)
    journal = MagicMock(spec=TradingJournal)
    journal.get_daily_pnl.return_value = 0.0

    engine = Engine(
        plan_parser=parser,
        exchange_connector=exchange,
        notifier=notifier,
        journal=journal,
    )
    assert engine._initial_setup() is True
    return engine


def test_kill_switch_triggers_close_and_pause(monkeypatch):
    eng = build_engine()
    # Equity $10,000; threshold = -$300; daily pnl = -$400 -> триггер
    eng.risk_manager.equity = 10_000.0
    monkeypatch.setattr(eng.journal, "get_daily_pnl", lambda date: -400.0)
    # перехват закрытия
    close_spy = MagicMock()
    monkeypatch.setattr(eng.risk_manager, "_close_all_positions", close_spy)

    eng._check_global_risks(pytz.utc.localize(eng_mod.datetime(2025, 8, 8, 10, 0)))

    assert eng.trading_paused is True
    close_spy.assert_called_once()
    # убедимся, что вызов сделан с reason="Kill-switch"
    assert any((kwargs.get("reason") == "Kill-switch") for args, kwargs in close_spy.call_args_list)


def test_time_stop_enforces_once(monkeypatch):
    eng = build_engine(plan_date="2025-08-08")
    # Условие kill-switch не сработает
    eng.risk_manager.equity = 10_000.0
    monkeypatch.setattr(eng.journal, "get_daily_pnl", lambda date: 0.0)

    # Подменяем datetime.now в модуле engine, чтобы локальное время было 23:10 EEST
    class FixedDateTime(eng_mod.datetime):
        @classmethod
        def now(cls, tz=None):
            # 20:10 UTC соответствует 23:10 EEST (UTC+3)
            return eng_mod.datetime(2025, 8, 8, 20, 10, tzinfo=pytz.utc)

    monkeypatch.setattr(eng_mod, "datetime", FixedDateTime)

    # Перехватываем закрытие всех позиций
    close_all_spy = MagicMock()
    eng._handle_close_all_open_positions = close_all_spy

    # Первый вызов должен закрыть позиции
    eng._check_global_risks(pytz.utc.localize(eng_mod.datetime(2025, 8, 8, 20, 10)))
    assert close_all_spy.call_count == 1

    # Повторный вызов в ту же дату не должен повторно закрывать
    eng._check_global_risks(pytz.utc.localize(eng_mod.datetime(2025, 8, 8, 20, 15)))
    assert close_all_spy.call_count == 1
