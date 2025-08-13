#!/usr/bin/env python3
"""
Тестування валідації торгового плану без обов'язкових полів
"""

import json
import tempfile
import os
from trading_bot.plan_parser import PlanParser

def test_plan_without_strategy():
    """Тестує, що станеться без поля strategy"""
    
    # Мінімальний план без strategy
    test_plan = {
        "plan_date": "2025-08-08",
        "plan_version": "2.0", 
        "plan_type": "test",
        "risk_budget": 0.025,
        "global_settings": {
            "max_portfolio_risk": 0.025,
            "emergency_stop_loss": -0.025,
            "daily_profit_target": 0.035,
            "max_concurrent_positions": 3,
            "max_notional_per_trade": 35.0,
            "margin_limit_pct": 0.30
        },
        "active_assets": [
            {
                "symbol": "ETHUSDT",
                "asset_type": "futures", 
                "leverage": 3,
                # "strategy": "macro_long",  # ВІДСУТНЄ ПОЛЕ
                "position_size_pct": 0.35,
                "order_groups": {
                    "bullish": {
                        "order_type": "BUY_STOP_LIMIT",
                        "trigger_price": 1900,
                        "limit_price": 1910,
                        "stop_loss": 1843,
                        "take_profit": [1975, 2033],
                        "time_valid_from": "2025-08-08T14:35:00+03:00",
                        "time_valid_to": "2025-08-08T19:00:00+03:00"
                    }
                }
            }
        ],
        "trade_phases": {},
        "risk_triggers": {},
        "end_of_day_checklist": []
    }
    
    # Створюємо тимчасовий файл
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_plan, f, indent=2)
        temp_file = f.name
    
    try:
        # Тестуємо завантаження
        parser = PlanParser(temp_file)
        result = parser.load_and_validate()
        
        if result:
            print("✅ План завантажено успішно БЕЗ поля strategy")
            plan = parser.get_plan()
            if plan:
                print(f"План містить {len(plan.active_assets)} активів")
                for asset in plan.active_assets:
                    print(f"Актив: {asset.symbol}")
                    if hasattr(asset, 'strategy'):
                        print(f"  Strategy: {asset.strategy}")
                    else:
                        print("  Strategy: ВІДСУТНЄ")
        else:
            print("❌ План НЕ завантажено - валідація не пройшла")
            
    except Exception as e:
        print(f"❌ Помилка: {e}")
        
    finally:
        # Видаляємо тимчасовий файл
        os.unlink(temp_file)

def test_plan_with_empty_strategy():
    """Тестує план з порожнім strategy"""
    
    test_plan = {
        "plan_date": "2025-08-08",
        "plan_version": "2.0", 
        "plan_type": "test",
        "risk_budget": 0.025,
        "global_settings": {
            "max_portfolio_risk": 0.025,
            "emergency_stop_loss": -0.025,
            "daily_profit_target": 0.035,
            "max_concurrent_positions": 3,
            "max_notional_per_trade": 35.0,
            "margin_limit_pct": 0.30
        },
        "active_assets": [
            {
                "symbol": "ETHUSDT",
                "asset_type": "futures", 
                "leverage": 3,
                "strategy": "",  # ПОРОЖНЄ ПОЛЕ
                "position_size_pct": 0.35,
                "order_groups": {
                    "bullish": {
                        "order_type": "BUY_STOP_LIMIT",
                        "trigger_price": 1900,
                        "limit_price": 1910,
                        "stop_loss": 1843,
                        "take_profit": [1975, 2033],
                        "time_valid_from": "2025-08-08T14:35:00+03:00",
                        "time_valid_to": "2025-08-08T19:00:00+03:00"
                    }
                }
            }
        ],
        "trade_phases": {},
        "risk_triggers": {},
        "end_of_day_checklist": []
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_plan, f, indent=2)
        temp_file = f.name
    
    try:
        parser = PlanParser(temp_file)
        result = parser.load_and_validate()
        
        if result:
            print("✅ План з порожнім strategy завантажено успішно")
            plan = parser.get_plan()
            if plan:
                for asset in plan.active_assets:
                    print(f"Актив: {asset.symbol}, Strategy: '{asset.strategy}'")
        else:
            print("❌ План з порожнім strategy НЕ завантажено")
            
    except Exception as e:
        print(f"❌ Помилка з порожнім strategy: {e}")
        
    finally:
        os.unlink(temp_file)

if __name__ == "__main__":
    print("=== Тестування валідації торгового плану ===\n")
    
    print("1. Тест без поля strategy:")
    test_plan_without_strategy()
    
    print("\n2. Тест з порожнім strategy:")
    test_plan_with_empty_strategy()
