#!/usr/bin/env python3
"""
Готує план data/trading_plan.json до запуску на TESTNET:
- Встановлює план на сьогоднішню дату
- Заміщує активи на BTCUSDT та ETHUSDT
- Розраховує триггери/ліміти/SL/TP відносно поточних тестнет-цін
- Оновлює вікна часу (фази та validity) під поточний час EEST

Вимоги (.env):
- BINANCE_TESTNET_API_KEY
- BINANCE_TESTNET_SECRET

Опціонально:
- PRICE_FIXTURE_PATH (JSON з цінами), використовується як фолбек, якщо API недоступне
"""

from __future__ import annotations
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any

import pytz
from dotenv import load_dotenv

# Локальні імпорти після оновлення sys.path не потрібні — використовуємо відносні
from trading_bot.exchange_connector import BinanceFuturesConnector


def load_price_fixtures() -> Dict[str, float]:
    path = os.getenv("PRICE_FIXTURE_PATH", "AUDIT/runtime/prices.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k: float(v) for k, v in data.items()}
        except Exception:
            return {}
    return {}


def round4(x: float) -> float:
    return float(f"{x:.4f}")


def build_order_group(side: str, price: float) -> Dict[str, Any]:
    # Невелике відхилення від ринку (~0.1-0.15%)
    if side.upper() == "BUY":
        trigger = price * 1.001
        limit = price * 1.0015
        sl = price * 0.995
        tps = [price * 1.003]
        order_type = "BUY_STOP_LIMIT"
    else:
        trigger = price * 0.999
        limit = price * 0.9985
        sl = price * 1.005
        tps = [price * 0.997]
        order_type = "SELL_STOP_LIMIT"

    return {
        "order_type": order_type,
        "trigger_price": round4(trigger),
        "limit_price": round4(limit),
        "stop_loss": round4(sl),
        "take_profit": [round4(tp) for tp in tps],
        # Часові поля будуть заповнені нижче
        "time_valid_from": "",
        "time_valid_to": "",
    }


def main():
    load_dotenv()
    api_key = os.getenv("BINANCE_TESTNET_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_SECRET")
    if not api_key or not api_secret:
        print("[prepare] Вкажіть BINANCE_TESTNET_API_KEY і BINANCE_TESTNET_SECRET у .env")
        return 1

    # Ініціалізуємо тестнет-коннектор
    conn = BinanceFuturesConnector(api_key=api_key, api_secret=api_secret, testnet=True)

    # Ціни: API → фікстури → фолбек
    fixtures = load_price_fixtures()
    def get_price(sym: str) -> float | None:
        p = conn.get_current_price(sym)
        if p:
            return p
        return fixtures.get(sym)

    btc = get_price("BTCUSDT")
    eth = get_price("ETHUSDT")
    if not btc or not eth:
        print("[prepare] Не вдалося отримати ціни BTC/ETH (API або фікстури).")
        return 1

    # Час у EEST
    tz = pytz.timezone("Europe/Kiev")
    now_local = datetime.now(tz)
    date_str = now_local.strftime("%Y-%m-%d")

    # Фаза виставлення — через ~2 хв, скасування/закриття — +45 хв
    setup_time = (now_local + timedelta(minutes=2)).strftime("%H:%M")
    cancel_time = (now_local + timedelta(minutes=45)).strftime("%H:%M")

    # Вікна валідності ордерів (зараз → +45 хв) у ISO з таймзоною
    valid_from = (now_local).isoformat()
    valid_to = (now_local + timedelta(minutes=45)).isoformat()

    # Формуємо активи
    btc_groups = {
        "bullish": build_order_group("BUY", btc),
        "bearish": build_order_group("SELL", btc),
    }
    eth_groups = {
        "bullish": build_order_group("BUY", eth),
        "bearish": build_order_group("SELL", eth),
    }

    # Пропишемо вікна валідності
    for g in [*btc_groups.values(), *eth_groups.values()]:
        g["time_valid_from"] = valid_from
        g["time_valid_to"] = valid_to

    plan = {
        "plan_date": date_str,
        "plan_version": "testnet-auto",
        "plan_type": "risk_adjusted_ensemble",
        "plan_author": "AutoPrep",
        "risk_budget": 0.01,
        "global_settings": {
            "max_portfolio_risk": 0.025,
            "emergency_stop_loss": -0.025,
            "daily_profit_target": 0.035,
            "max_concurrent_positions": 2,
            "margin_limit_pct": 0.34,
            "max_notional_per_trade": 1000.0
        },
        "active_assets": [
            {
                "symbol": "BTCUSDT",
                "asset_type": "futures",
                "leverage": 3,
                "position_size_pct": 0.05,
                "strategy": "oco_breakout",
                "order_groups": btc_groups
            },
            {
                "symbol": "ETHUSDT",
                "asset_type": "futures",
                "leverage": 3,
                "position_size_pct": 0.02,
                "strategy": "oco_breakout",
                "order_groups": eth_groups
            }
        ],
        "fallback": {
            "activate_if": "no_positions_by_17:00",
            "strategy": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "entry_trigger": "price<=999999",
                "size_pct": 0.12,
                "leverage": 1,
                "expire": valid_to
            }
        },
        "trade_phases": {
            "setup_orders": {
                "time": setup_time,
                "action": "place_conditional_orders",
                "description": "Виставити OCO ордери"
            },
            "cancel_unfilled": {
                "time": cancel_time,
                "action": "cancel_all_untriggered",
                "description": "Скасувати невиконані"
            },
            "end_of_day": {
                "time": cancel_time,
                "action": "close_all_positions",
                "description": "Закрити всі позиції"
            }
        },
        "risk_triggers": {
            "btc_spike": {
                "threshold_pct": 1.5,
                "action": "close_all_positions",
                "assets": ["BTCUSDT", "ETHUSDT"]
            }
        },
        "end_of_day_checklist": [
            "close_all_positions_by_19:30",
            "calculate_realized_pnl"
        ]
    }

    os.makedirs("data", exist_ok=True)
    with open("data/trading_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    print("[prepare] План оновлено для TESTNET: data/trading_plan.json")
    print(f"[prepare] BTC={btc} ETH={eth} | setup={setup_time} cancel={cancel_time} (EEST)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
