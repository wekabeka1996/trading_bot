import os
import pytest

pytest.importorskip("binance")

from trading_bot.exchange_connector import BinanceFuturesConnector


def test_connector_uses_testnet_url(monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET", "true")
    # Ключи могут быть пустыми в тесте — клиент создаётся без сетевых вызовов
    conn = BinanceFuturesConnector(api_key="x", api_secret="y", testnet=True)
    assert conn.testnet is True
    # Проверяем, что URL установлен на тестнет
    assert hasattr(conn.client, "FUTURES_TESTNET_URL")
    assert conn.client.API_URL == conn.client.FUTURES_TESTNET_URL
