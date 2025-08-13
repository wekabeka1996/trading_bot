import pytest

# Пропускаємо тести, якщо немає залежності binance
pytest.importorskip("binance")
from trading_bot.exchange_connector import BinanceFuturesConnector


def test_validate_stop_order_buy_ok():
    c = object.__new__(BinanceFuturesConnector)
    # BUY STOP-LIMIT: price must be > stopPrice
    BinanceFuturesConnector._validate_stop_order(c, 'BUY', 100.0, 100.5)


def test_validate_stop_order_buy_invalid():
    c = object.__new__(BinanceFuturesConnector)
    with pytest.raises(ValueError):
        BinanceFuturesConnector._validate_stop_order(c, 'BUY', 100.0, 99.5)


def test_validate_stop_order_sell_ok():
    c = object.__new__(BinanceFuturesConnector)
    BinanceFuturesConnector._validate_stop_order(c, 'SELL', 100.0, 99.5)


def test_validate_stop_order_sell_invalid():
    c = object.__new__(BinanceFuturesConnector)
    with pytest.raises(ValueError):
        BinanceFuturesConnector._validate_stop_order(c, 'SELL', 100.0, 100.5)
