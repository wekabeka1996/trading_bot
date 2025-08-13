import pytest

pytest.importorskip("binance")

from trading_bot.exchange_connector import BinanceFuturesConnector


class DummyConn(BinanceFuturesConnector):
    def __init__(self):
        pass
    def get_exchange_filters(self, symbol: str) -> dict:
        return {
            'LOT_SIZE': {'stepSize': '0.001'},
            'PRICE_FILTER': {'tickSize': '0.1'},
            'MIN_NOTIONAL': {'notional': '10'}
        }


def test_min_notional_adjusts_quantity_reasonably():
    c = DummyConn()
    # Цена 100, qty 0.05 -> notional 5 < 10 => увеличит qty примерно до 0.101
    formatted = c.format_quantity_and_price(
        symbol='BTCUSDT', quantity=0.05, price=100.0, stop_price=None
    )
    assert float(formatted['quantity']) >= 0.1


def test_min_notional_blocks_risk_escalation():
    c = DummyConn()
    # Цена очень малая => требуемое увеличение в >5x приведёт к ошибке
    with pytest.raises(ValueError):
        c.format_quantity_and_price(symbol='BTCUSDT', quantity=1.0, price=0.0001, stop_price=None)
