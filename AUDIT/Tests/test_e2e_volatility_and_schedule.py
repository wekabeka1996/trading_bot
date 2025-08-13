import pytest
import pytz
from unittest.mock import MagicMock

pytest.importorskip("binance")

import trading_bot.engine as eng_mod
from trading_bot.engine import Engine
from trading_bot.plan_parser import TradingPlan, GlobalSettings, ActiveAsset, OrderGroup
from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal


def build_engine_with_mocks():
    plan = TradingPlan(
        plan_date="2025-08-08",
        plan_version="1.0",
        plan_type="e2e",
        risk_budget=0.01,
        global_settings=GlobalSettings(
            max_portfolio_risk=0.5,
            emergency_stop_loss=-0.03,
            daily_profit_target=0.02,
            max_concurrent_positions=3,
            max_notional_per_trade=1_000_000.0,
            margin_limit_pct=0.4,
        ),
        active_assets=[
            ActiveAsset(
                symbol="BTCUSDT",
                asset_type="futures",
                leverage=10,
                strategy="oco_breakout",
                position_size_pct=0.1,
                order_groups={
                    "bullish": OrderGroup(
                        order_type="STOP",
                        trigger_price=70000.0,
                        limit_price=None,
                        stop_loss=68000.0,
                        take_profit=[71000.0],
                        time_valid_from="2025-08-08T09:00:00+03:00",
                        time_valid_to="2025-08-08T22:00:00+03:00",
                    )
                },
            )
        ],
        trade_phases={},
        risk_triggers={},
        end_of_day_checklist=[],
    )

    parser = MagicMock()
    parser.load_and_validate.return_value = True
    parser.get_plan.return_value = plan

    exchange = MagicMock(spec=BinanceFuturesConnector)
    exchange.check_connection.return_value = True
    exchange.get_futures_account_balance.return_value = 10_000.0
    exchange.is_symbol_active.return_value = True

    notifier = MagicMock(spec=TelegramNotifier)
    journal = MagicMock(spec=TradingJournal)

    engine = Engine(
        plan_parser=parser,
        exchange_connector=exchange,
        notifier=notifier,
        journal=journal,
    )
    assert engine._initial_setup() is True
    return engine


def test_btc_volatility_cancels_orders(monkeypatch):
    eng = build_engine_with_mocks()
    # подготовим ордера, которые можно отменять
    monkeypatch.setattr(eng.exchange, "get_open_orders", lambda symbol: [{"orderId": 123}])
    cancel_spy = MagicMock()
    monkeypatch.setattr(eng.exchange, "cancel_order", cancel_spy)

    # Сымитируем историю цен с высокой волатильностью и отключим троттлинг
    prices = [100.0, 101.0, 98.0, 102.0, 90.0, 89.0]
    def price_seq_factory(seq):
        it = iter(seq)
        def _next_price(symbol):
            try:
                return next(it)
            except StopIteration:
                return seq[-1]
        return _next_price
    monkeypatch.setattr(eng.exchange, "get_current_price", price_seq_factory(prices))

    for i in range(len(prices)):
        eng.last_volatility_check = None
        eng._check_global_risks(pytz.utc.localize(eng_mod.datetime(2025, 8, 8, 10, i)))

    # должна была произойти отмена хотя бы одного ордера
    assert cancel_spy.call_count >= 1


def test_eest_gating_blocks_order_placement(monkeypatch):
    eng = build_engine_with_mocks()
    # запретим новые входы через гейтинг
    monkeypatch.setattr(eng, "_is_within_entry_hours_eest", lambda current: False)

    # Подстрахуемся: если бы метод был вызван, мы бы заметили
    place_spy = MagicMock()
    monkeypatch.setattr(eng, "_place_oco_breakout_orders", place_spy)

    eng._handle_place_all_orders()

    place_spy.assert_not_called()
