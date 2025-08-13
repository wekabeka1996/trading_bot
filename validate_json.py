#!/usr/bin/env python3
"""
Перевірка валідності trading_plan.json
"""
import json
import sys
import os

def check_trading_plan():
    """Перевіряє валідність JSON файлу"""
    
    plan_file = "data/trading_plan.json"
    
    if not os.path.exists(plan_file):
        print(f"❌ Файл {plan_file} не знайдено")
        return False
    
    try:
        print("🔍 Перевірка JSON валідності...")
        
        # Читаємо з UTF-8
        with open(plan_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print("✅ JSON синтаксис валідний!")
        print(f"📋 План: {data.get('plan_version', 'unknown')}")
        print(f"📅 Дата: {data.get('plan_date', 'unknown')}")
        
        # Перевіряємо основні секції
        required_sections = [
            'plan_date', 'plan_version', 'active_assets', 
            'global_settings', 'trade_phases', 'risk_triggers'
        ]
        
        for section in required_sections:
            if section in data:
                print(f"✅ {section}")
            else:
                print(f"❌ Відсутня секція: {section}")
        
        print(f"\n📊 Активів: {len(data.get('active_assets', []))}")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON помилка: {e}")
        print(f"   Рядок {e.lineno}, позиція {e.colno}")
        return False
    except UnicodeDecodeError as e:
        print(f"❌ Помилка кодування: {e}")
        return False
    except Exception as e:
        print(f"❌ Неочікувана помилка: {e}")
        return False

if __name__ == "__main__":
    success = check_trading_plan()
    sys.exit(0 if success else 1)
