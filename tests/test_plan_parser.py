# tests/test_plan_parser.py
# Автоматичні тести для модуля PlanParser.

import pytest
import json
from trading_bot.plan_parser import PlanParser

# --- Тестові дані ---

VALID_PLAN_DATA = {
  "plan_date": "2025-07-28",
  "plan_version": "1.0",
  "plan_type": "test_type",
  "risk_budget": 0.01,
  "global_settings": {
    "max_portfolio_risk": 2.0,
    "emergency_stop_loss": -8.0,
    "daily_profit_target": 5.0,
    "max_concurrent_positions": 1
  },
  "active_assets": [
    {
      "symbol": "LDOUSDT",
      "asset_type": "futures",
      "leverage": 3,
      "strategy": "oco_breakout",
      "position_size_pct": 0.34,
      "order_groups": {
        "bullish": {
          "order_type": "BUY_STOP_LIMIT",
          "trigger_price": 1.142,
          "limit_price": 1.145,
          "stop_loss": 1.120,
          "take_profit": [1.160, 1.195],
          "time_valid_from": "2025-07-27T23:00:00+03:00",
          "time_valid_to": "2025-07-28T11:00:00+03:00"
        }
      }
    }
  ],
  "trade_phases": {
    "setup_orders": {
      "start_time": "23:00",
      "action": "place_all_orders",
      "description": "place both OCO groups"
    }
  },
  "risk_triggers": {
    "btc_eth_flash_drop": {
      "threshold_pct": 5.0,
      "assets": ["BTCUSDT", "ETHUSDT"],
      "action": "close_longs_keep_hedge"
    }
  },
  "end_of_day_checklist": [
    "position_closed_or_sl_in_profit"
  ]
}

INVALID_PLAN_DATA = {
  "plan_date": "2025-07-28",
  # "plan_version" is missing, which should cause a validation error
  "plan_type": "test_type",
  "risk_budget": 0.01
}

# --- Тести ---

def test_load_and_validate_success(tmp_path):
    """
    Перевіряє, що парсер успішно завантажує та валідує коректний JSON.
    """
    # Arrange: Створюємо тимчасовий файл плану з валідними даними
    plan_file = tmp_path / "trading_plan.json"
    plan_file.write_text(json.dumps(VALID_PLAN_DATA))
    
    parser = PlanParser(plan_path=str(plan_file))

    # Act
    is_valid = parser.load_and_validate()

    # Assert
    assert is_valid is True
    assert parser.get_plan() is not None
    assert parser.get_plan().plan_version == "1.0"

def test_load_and_validate_file_not_found():
    """
    Перевіряє, що парсер повертає False, якщо файл не знайдено.
    """
    # Arrange
    parser = PlanParser(plan_path="non_existent_file.json")

    # Act
    is_valid = parser.load_and_validate()

    # Assert
    assert is_valid is False

def test_load_and_validate_invalid_json_format(tmp_path):
    """
    Перевіряє, що парсер повертає False при некоректному форматі JSON.
    """
    # Arrange
    plan_file = tmp_path / "invalid_plan.json"
    plan_file.write_text("{'key': 'not a valid json'}") # Неправильний JSON з одинарними лапками
    
    parser = PlanParser(plan_path=str(plan_file))

    # Act
    is_valid = parser.load_and_validate()

    # Assert
    assert is_valid is False

def test_load_and_validate_validation_error(tmp_path):
    """
    Перевіряє, що парсер повертає False, якщо структура плану не відповідає схемі Pydantic.
    """
    # Arrange
    plan_file = tmp_path / "incomplete_plan.json"
    plan_file.write_text(json.dumps(INVALID_PLAN_DATA))
    
    parser = PlanParser(plan_path=str(plan_file))

    # Act
    is_valid = parser.load_and_validate()

    # Assert
    assert is_valid is False
