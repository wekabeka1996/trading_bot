#!/usr/bin/env python3
"""
Тест нового плану 4.0_DEFINITIVE
"""
import json

def test_plan_4_0():
    print("🔍 ТЕСТ ПЛАНУ 4.0_DEFINITIVE")
    print("="*50)
    
    with open('data/trading_plan.json', 'r', encoding='utf-8') as f:
        plan = json.load(f)
    
    print(f"✅ Версія: {plan['plan_version']}")
    print(f"📅 Дата: {plan['plan_date']}")
    
    # Перевіряємо час активації
    setup_time = plan['trade_phases']['setup_orders']['time']
    print(f"⏰ Час активації: {setup_time}")
    
    if setup_time == "14:17":
        print("✅ Час змінено на 14:17 ✓")
    else:
        print(f"❌ Очікувався 14:17, але маємо {setup_time}")
    
    # Перевіряємо активи
    print(f"\n📊 АКТИВИ ({len(plan['active_assets'])}):")
    for asset in plan['active_assets']:
        symbol = asset['symbol']
        size = asset['position_size_pct']
        leverage = asset['leverage']
        margin = size / leverage
        print(f"   {symbol}: {size:.3f} (плече {leverage}x) → маржа {margin:.3f}")
    
    # Загальна маржа
    total_margin = sum(asset['position_size_pct'] / asset['leverage'] for asset in plan['active_assets'])
    print(f"\n📋 Загальна маржа: {total_margin:.3f} (ліміт: {plan['global_settings']['margin_limit_pct']})")
    
    if total_margin <= plan['global_settings']['margin_limit_pct']:
        print("✅ Маржа в межах ліміту")
    else:
        print("❌ Маржа перевищує ліміт!")
    
    print(f"\n🎯 ПЛАН 4.0_DEFINITIVE ГОТОВИЙ!")
    print(f"🕒 Активація о 14:17")
    print(f"📈 3 активи з загальною маржею {total_margin:.1%}")

if __name__ == "__main__":
    test_plan_4_0()
