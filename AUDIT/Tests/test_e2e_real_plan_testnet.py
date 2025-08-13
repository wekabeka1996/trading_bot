import os
import json
import pytest
import pytz
from unittest.mock import MagicMock
from datetime import datetime

# Требуются зависимости binance и реальные тестнет ключи в .env или окружении
pytest.importorskip("binance")

from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.plan_parser import PlanParser
from trading_bot.engine import Engine
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_TESTNET_E2E", "false").lower() != "true",
    reason="RUN_TESTNET_E2E!=true: интеграционный тест отключён по умолчанию"
)
@pytest.mark.skipif(
    os.getenv("BINANCE_TESTNET", "false").lower() != "true",
    reason="BINANCE_TESTNET!=true"
)
@pytest.mark.skipif(
    not (os.getenv("BINANCE_TESTNET_API_KEY") and os.getenv("BINANCE_TESTNET_SECRET")),
    reason="Нет тестнет API ключей в окружении"
)
def test_e2e_real_plan_on_testnet(monkeypatch):
    # 1) Подготовка коннектора testnet
    api_key = str(os.getenv("BINANCE_TESTNET_API_KEY"))
    api_secret = str(os.getenv("BINANCE_TESTNET_SECRET"))
    conn = BinanceFuturesConnector(api_key=api_key, api_secret=api_secret, testnet=True)
    assert conn.testnet is True

    # 2) Загружаем реальный план
    parser = PlanParser("data/trading_plan.json")
    assert parser.load_and_validate() is True
    plan = parser.get_plan()
    assert plan is not None

    # 3) Инжекция цен при необходимости
    prices_path = os.getenv("PRICE_FIXTURE_PATH", "AUDIT/runtime/prices.json")
    price_map = {}
    if os.path.exists(prices_path):
        with open(prices_path, "r", encoding="utf-8") as f:
            price_map = json.load(f)

    def get_price(symbol: str):
        if symbol in price_map:
            return float(price_map[symbol])
        return conn.get_current_price(symbol)

    # Подменяем метод получения цены в Engine через exchange
    monkeypatch.setattr(conn, "get_current_price", get_price)

    # 4) Глушим Telegram уведомления
    notifier = MagicMock(spec=TelegramNotifier)
    journal = TradingJournal()

    # 5) Инициализируем движок
    engine = Engine(
        plan_parser=parser,
        exchange_connector=conn,
        notifier=notifier,
        journal=journal,
    )
    assert engine._initial_setup() is True

    # Разрешим окно времени (гейтер фаз) и EEST-гейтинг
    monkeypatch.setattr(engine, "_should_execute_order_group", lambda og, now: True)
    monkeypatch.setattr(engine, "_is_within_entry_hours_eest", lambda now: True)

    # 6) Пытаемся выставить ордера по плану (в тестнете)
    engine._handle_place_all_orders()

    # 7) Проверяем, что по активам есть открытые ордера; затем чистим
    symbols = [a.symbol for a in plan.active_assets]
    placed = 0
    for sym in symbols:
        try:
            orders = conn.client.futures_get_open_orders(symbol=sym)
            if isinstance(orders, list) and orders:
                placed += len(orders)
                # cleanup: отменяем чтобы не замусоривать тестнет
                for o in orders:
                    try:
                        conn.client.futures_cancel_order(symbol=sym, orderId=o["orderId"])
                    except Exception:
                        pass
        except Exception:
            # если пара неактивна/ошибка — пропускаем
            continue

    assert placed >= 1, "Ожидалось, что хотя бы один ордер будет размещён на тестнете"
