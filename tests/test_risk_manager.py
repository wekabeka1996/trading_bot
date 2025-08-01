# tests/test_risk_manager.py
# Автоматичні тести для модуля RiskManager.
"""Автоматичні тести для модуля RiskManager."""
# pylint: disable=redefined-outer-name

from unittest.mock import MagicMock
import pytest

# Імпортуємо класи, які будемо тестувати та мокати
from trading_bot.risk_manager import RiskManager
from trading_bot.plan_parser import TradingPlan, ActiveAsset, OrderGroup
from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal

# --- Фікстури для створення тестових об'єктів ---


@pytest.fixture
def mock_notifier():
    """Створює мок-об'єкт для TelegramNotifier."""
    return MagicMock(spec=TelegramNotifier)


@pytest.fixture
def mock_journal():
    """Створює мок-об'єкт для TradingJournal."""
    return MagicMock(spec=TradingJournal)


@pytest.fixture
def mock_exchange_connector():
    """
    Створює мок-об'єкт для BinanceFuturesConnector з перевизначеними методами.
    """
    connector = MagicMock(spec=BinanceFuturesConnector)
    # $10,000 капітал
    connector.get_futures_account_balance.return_value = 10000.0

    # Налаштовуємо мок-метод напряму на об'єкті
    mock_filters = {
        'LOT_SIZE': {'minQty': '0.1', 'stepSize': '0.1'},
        'PRICE_FILTER': {'minPrice': '0.0001', 'tickSize': '0.0001'}
    }
    connector.get_exchange_filters.return_value = mock_filters

    yield connector


@pytest.fixture
def sample_trading_plan() -> TradingPlan:
    """Створює простий, але валідний торговий план для тестування."""
    plan_data = {
        "plan_date": "2025-07-28", "plan_version": "1.0", "plan_type": "test",
        "risk_budget": 0.01,  # 1% ризик на угоду
        "global_settings": {
            "max_portfolio_risk": 2.0,
            "emergency_stop_loss": -8.0,
            "daily_profit_target": 5.0,
            "max_concurrent_positions": 1
        },
        "active_assets": [],
        "trade_phases": {},
        "risk_triggers": {},
        "end_of_day_checklist": []
    }
    return TradingPlan.model_validate(plan_data)


# --- Тестовий клас для RiskManager ---


class TestRiskManager:
    """
    Групує тести, пов'язані з класом RiskManager.
    """
    def test_calculate_position_size_correctly(
        self, sample_trading_plan, mock_exchange_connector,
        mock_notifier, mock_journal
    ):
        """
        Перевіряє, чи правильно RiskManager розраховує розмір позиції з
        урахуванням double margin (OCO).
        """
        # Arrange
        risk_manager = RiskManager(
            plan=sample_trading_plan, exchange=mock_exchange_connector,
            notifier=mock_notifier, journal=mock_journal
        )
        asset_data = {
            "symbol": "LDOUSDT", "asset_type": "futures", "leverage": 3,
            "strategy": "test", "position_size_pct": 0, "order_groups": {}
        }
        test_asset = ActiveAsset.model_validate(asset_data)
        order_data = {
            "order_type": "BUY_STOP_LIMIT", "trigger_price": 1.142,
            "limit_price": 1.145, "stop_loss": 1.120,
            "take_profit": [1.160], "time_valid_from": "-",
            "time_valid_to": "-"
        }
        test_order_group = OrderGroup.model_validate(order_data)

        # Act
        calculated_size = risk_manager.calculate_position_size(
            test_asset, test_order_group
        )

        # Assert
        # Капітал = $10,000, Ризик = 1% ($100), Відстань до стопу = 0.022
        # Розмір = 100 / 0.022 = 4545.45...
        # але double margin (OCO) -> qty обмежено до 4000.0
        expected_size = 4000.0
        assert calculated_size is not None
        assert calculated_size == pytest.approx(expected_size)
        risk_manager.exchange.get_futures_account_balance.assert_called_once()
        risk_manager.exchange.get_exchange_filters.assert_called_once_with(
            "LDOUSDT"
        )

    def test_calculate_position_size_returns_none_if_below_min_qty(
        self, sample_trading_plan, mock_exchange_connector,
        mock_notifier, mock_journal
    ):
        """
        Перевіряє, що метод повертає None, якщо розрахований розмір
        менший за мінімальний.
        """
        # Arrange
        risk_manager = RiskManager(
            plan=sample_trading_plan, exchange=mock_exchange_connector,
            notifier=mock_notifier, journal=mock_journal
        )
        asset_data = {
            "symbol": "LDOUSDT", "asset_type": "futures", "leverage": 3,
            "strategy": "test", "position_size_pct": 0, "order_groups": {}
        }
        test_asset = ActiveAsset.model_validate(asset_data)
        order_data = {
            "order_type": "BUY_STOP_LIMIT", "trigger_price": 1.142,
            "limit_price": 1.145, "stop_loss": 1.120,
            "take_profit": [1.160], "time_valid_from": "-",
            "time_valid_to": "-"
        }
        test_order_group = OrderGroup.model_validate(order_data)

        # Act & Assert
        # Змінюємо значення, що повертається моком, для цього тесту
        filters = {'LOT_SIZE': {'minQty': '5000.0', 'stepSize': '0.1'}}
        mock_exchange_connector.get_exchange_filters.return_value = filters
        calculated_size = risk_manager.calculate_position_size(
            test_asset, test_order_group
        )
        assert calculated_size is None
