#!/usr/bin/env python3
"""
Одноразовый прогон плана на Binance Futures Testnet:
- Загружает план из data/trading_plan.json
- Подставляет цены из AUDIT/runtime/prices.json (если есть)
- Ослабляет тайм-гейтинг для запуска «прямо сейчас»
- Выставляет условные ордера по плану, затем безопасно их отменяет

Требуемые переменные окружения:
- BINANCE_TESTNET=true
- BINANCE_TESTNET_API_KEY
- BINANCE_TESTNET_SECRET

Опционально:
- PRICE_FIXTURE_PATH (путь к JSON с ценами)
- TESTNET_SYMBOL_MAP (JSON-строка вида {"LEVERUSDT":"BTCUSDT"})
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict

# Добавляем корень проекта в sys.path, чтобы работали импорты пакета trading_bot при запуске из scripts/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.plan_parser import PlanParser
from trading_bot.engine import Engine
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal
from dotenv import load_dotenv


def load_price_map() -> Dict[str, float]:
    path = os.getenv("PRICE_FIXTURE_PATH", "AUDIT/runtime/prices.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: float(v) for k, v in data.items()}
        except Exception:
            pass
    return {}


def main():
    # Подхватываем .env, но не переопределяем уже выставленные переменные из среды
    load_dotenv(override=False)
    assert os.getenv("BINANCE_TESTNET", "false").lower() == "true", "BINANCE_TESTNET must be true"
    api_key = os.getenv("BINANCE_TESTNET_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("Provide BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_SECRET in environment")

    # Подготовка коннектора и плана
    conn = BinanceFuturesConnector(api_key=api_key, api_secret=api_secret, testnet=True)
    parser = PlanParser("data/trading_plan.json")
    assert parser.load_and_validate() is True

    # Необязательная карта замены символов для тестнета
    symbol_map_env = os.getenv("TESTNET_SYMBOL_MAP")
    symbol_map: Dict[str, str] = {}
    if symbol_map_env:
        try:
            symbol_map = json.loads(symbol_map_env)
        except Exception:
            symbol_map = {}
    # Авто-фолбек: якщо мапа не задана — примусово мапимо всі не BTC/ETH до BTCUSDT/ETHUSDT (через один)
    if not symbol_map:
        try:
            tmp_map: Dict[str, str] = {}
            # Визначимо порядок активів з плану, щоб рівномірно розкидати між BTC та ETH
            if parser.plan and getattr(parser.plan, 'active_assets', None):
                i = 0
                for a in parser.plan.active_assets:
                    if a.symbol not in ("BTCUSDT", "ETHUSDT"):
                        tmp_map[a.symbol] = "BTCUSDT" if (i % 2 == 0) else "ETHUSDT"
                        i += 1
            if tmp_map:
                symbol_map = tmp_map
        except Exception:
            pass

    # Подмена get_current_price на фикстуры
    price_map = load_price_map()

    def get_price(symbol: str):
        # Поддержка тестовой замены символов (если указана)
        target = symbol_map.get(symbol, symbol)
        if target in price_map:
            return float(price_map[target])
        return conn.get_current_price(target)

    # Monkeypatch метода цены в коннекторе
    setattr(conn, "get_current_price", get_price)

    # Создаем движок
    notifier = TelegramNotifier(token="", chat_id="")  # глушим реальные уведомления
    journal = TradingJournal()
    engine = Engine(plan_parser=parser, exchange_connector=conn, notifier=notifier, journal=journal)
    assert engine._initial_setup() is True

    # Ослабляем гейтинги для одноразового запуска
    setattr(engine, "_should_execute_order_group", lambda og, now: True)
    setattr(engine, "_is_within_entry_hours_eest", lambda now: True)

    # Если задана карта символов, перепишем символы активов прямо в плане движка (только для запуска)
    if symbol_map and engine.plan and getattr(engine.plan, "active_assets", None):
        # Увеличим лимит нотиона, чтобы не упираться в 35 USDT на крупные пары
        try:
            if getattr(engine.plan, 'global_settings', None):
                engine.plan.global_settings.max_notional_per_trade = 1000.0
        except Exception:
            pass
        for asset in engine.plan.active_assets:
            if asset.symbol in symbol_map:
                asset.symbol = symbol_map[asset.symbol]
                # Нормализуем цены ордеров вокруг текущей цены mapped-символа, чтобы пройти биржевые фильтры
                try:
                    gp = get_price(asset.symbol)
                    if gp is None:
                        api_p = conn.get_current_price(asset.symbol)
                        if api_p is None:
                            continue
                        cp = float(api_p)
                    else:
                        cp = float(gp)
                    og = getattr(asset, 'order_groups', {}) or {}
                    for _, grp in og.items():
                        ot = (getattr(grp, 'order_type', '') or '').upper()
                        if 'BUY_STOP_LIMIT' in ot:
                            grp.trigger_price = cp * 1.001
                            grp.limit_price = cp * 1.0015
                            grp.stop_loss = cp * 0.995
                            grp.take_profit = [cp * 1.003]
                        elif 'SELL_STOP_LIMIT' in ot:
                            grp.trigger_price = cp * 0.999
                            grp.limit_price = cp * 0.9985
                            grp.stop_loss = cp * 1.005
                            grp.take_profit = [cp * 0.997]
                except Exception:
                    pass

    print(f"[Testnet] {datetime.utcnow().isoformat()}Z — placing conditional orders…")
    engine._handle_place_all_orders()

    # Сбор открытых ордеров и последующая отмена
    placed = 0
    symbols = [a.symbol for a in engine.plan.active_assets] if engine.plan else []
    for sym in symbols:
        try:
            orders = conn.client.futures_get_open_orders(symbol=sym)
            if isinstance(orders, list) and orders:
                placed += len(orders)
                for o in orders:
                    try:
                        conn.client.futures_cancel_order(symbol=sym, orderId=o["orderId"])
                    except Exception:
                        pass
        except Exception:
            # Символ может быть недоступен на тестнете — игнорируем
            continue

    print(f"[Testnet] Open orders placed (and canceled): {placed}")
    if placed == 0:
        print("[Testnet] Warning: no orders were placed. Check testnet symbol availability or set TESTNET_SYMBOL_MAP.")


if __name__ == "__main__":
    main()
