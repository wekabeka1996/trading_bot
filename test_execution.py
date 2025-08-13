#!/usr/bin/env python3
"""
Тестування реального виконання торгового плану
"""

import os
from datetime import datetime, timedelta
import pytz
from unittest.mock import Mock, MagicMock
from trading_bot.plan_parser import PlanParser
from trading_bot.engine import Engine
from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal

def test_plan_execution():
    """Тестує виконання плану з мок-об'єктами"""
    
    print("🧪 ТЕСТУВАННЯ ВИКОНАННЯ ТОРГОВОГО ПЛАНУ")
    print("=" * 45)
    
    # Створюємо мок-об'єкти
    mock_exchange = Mock(spec=BinanceFuturesConnector)
    mock_exchange.check_connection.return_value = True
    mock_exchange.is_symbol_active.return_value = True
    mock_exchange.get_current_price.return_value = 2000.0
    mock_exchange.get_futures_account_balance.return_value = 10000.0
    mock_exchange.get_free_margin.return_value = 8000.0
    mock_exchange.get_total_balance.return_value = 10000.0
    mock_exchange.get_open_orders.return_value = []
    mock_exchange.get_position_information.return_value = []
    mock_exchange.place_order.return_value = {'orderId': 12345}
    
    mock_notifier = Mock(spec=TelegramNotifier)
    mock_journal = Mock(spec=TradingJournal)
    
    # Завантажуємо план
    parser = PlanParser('data/trading_plan.json')
    if not parser.load_and_validate():
        print("❌ План не валідний!")
        return False
    
    # Створюємо engine
    engine = Engine(
        plan_parser=parser,
        exchange_connector=mock_exchange,
        notifier=mock_notifier,
        journal=mock_journal
    )
    
    # Ініціалізація
    if not engine._initial_setup():
        print("❌ Помилка ініціалізації!")
        return False
    
    print("✅ Engine ініціалізовано успішно")
    print(f"📋 План: {engine.plan.plan_type}")
    print(f"📊 Активів: {len(engine.plan.active_assets)}")
    print()
    
    # Тестуємо різні фази
    print("🕐 ТЕСТУВАННЯ ТОРГОВИХ ФАЗ:")
    print("-" * 30)
    
    # Моделюємо часи з плану (переводимо на сьогодні)
    kiev_tz = pytz.timezone('Europe/Kiev')
    today = datetime.now(kiev_tz).date()
    
    test_phases = [
        ("14:25", "pre_macro_check"),
        ("14:30", "macro_release"), 
        ("14:35", "setup_orders"),
        ("15:00", "monitor_arb"),
        ("16:00", "sol_activation"),
        ("19:00", "cancel_unfilled"),
        ("23:00", "end_of_day")
    ]
    
    for time_str, phase_name in test_phases:
        hour, minute = map(int, time_str.split(':'))
        test_time = kiev_tz.localize(
            datetime.combine(today, datetime.min.time())
        ).replace(hour=hour, minute=minute).astimezone(pytz.utc)
        
        print(f"⏰ {time_str} ({phase_name})")
        
        # Симулюємо поточний час
        original_executed = engine.executed_phases.copy()
        engine.executed_phases.clear()
        
        try:
            engine._process_trade_phases(test_time)
            
            if phase_name in engine.executed_phases:
                print(f"   ✅ Фаза виконана")
            else:
                print(f"   ❌ Фаза НЕ виконана")
                
        except Exception as e:
            print(f"   💥 Помилка: {e}")
        
        engine.executed_phases = original_executed
        print()
    
    # Тестуємо розміщення OCO ордерів
    print("📈 ТЕСТУВАННЯ OCO ОРДЕРІВ:")
    print("-" * 25)
    
    try:
        current_time = datetime.now(pytz.utc)
        
        for asset in engine.plan.active_assets:
            print(f"🔍 Тестую {asset.symbol}")
            
            if asset.strategy == "oco_breakout":
                bullish_group = asset.order_groups.get("bullish")
                bearish_group = asset.order_groups.get("bearish")
                
                if bullish_group and bearish_group:
                    try:
                        # Перевіряємо валідність часу
                        valid_bullish = engine._should_execute_order_group(bullish_group, current_time)
                        valid_bearish = engine._should_execute_order_group(bearish_group, current_time)
                        
                        print(f"   ⏰ Час валідний bullish: {valid_bullish}")
                        print(f"   ⏰ Час валідний bearish: {valid_bearish}")
                        
                        if valid_bullish or valid_bearish:
                            # Симулюємо розміщення
                            engine._place_oco_breakout_orders(asset)
                            print(f"   ✅ OCO ордери розміщені")
                        else:
                            print(f"   ⏰ Час для ордерів ще не настав")
                            
                    except Exception as e:
                        print(f"   💥 Помилка OCO: {e}")
                else:
                    print(f"   ❌ Відсутні bullish/bearish групи")
            else:
                print(f"   ⚠️ Стратегія {asset.strategy} не підтримується")
            print()
            
    except Exception as e:
        print(f"💥 Загальна помилка OCO: {e}")
    
    # Тестуємо ризик-менеджмент
    print("⚡ ТЕСТУВАННЯ РИЗИК-МЕНЕДЖМЕНТУ:")
    print("-" * 30)
    
    try:
        if engine.risk_manager:
            engine.risk_manager.update_equity()
            print("✅ Капітал оновлено")
            
            # Тестуємо розрахунок розміру позиції
            for asset in engine.plan.active_assets:
                bullish_group = asset.order_groups.get("bullish")
                if bullish_group:
                    size = engine.risk_manager.calculate_position_size(asset, bullish_group)
                    if size and size > 0:
                        print(f"✅ {asset.symbol}: розмір позиції {size}")
                    else:
                        print(f"❌ {asset.symbol}: не вдалося розрахувати розмір")
        else:
            print("❌ Risk Manager не ініціалізовано")
            
    except Exception as e:
        print(f"💥 Помилка ризик-менеджменту: {e}")
    
    print()
    
    # Підсумок
    print("📋 ПІДСУМОК ТЕСТУВАННЯ:")
    print("-" * 25)
    
    success_points = []
    issues = []
    
    # Перевірка ініціалізації
    if engine.plan and engine.risk_manager:
        success_points.append("✅ Ініціалізація successful")
    else:
        issues.append("❌ Проблеми з ініціалізацією")
    
    # Перевірка валідації плану
    if parser.load_and_validate():
        success_points.append("✅ План валідний")
    else:
        issues.append("❌ План невалідний")
    
    # Перевірка OCO стратегій
    oco_count = sum(1 for asset in engine.plan.active_assets 
                    if asset.strategy == "oco_breakout" and 
                    asset.order_groups.get("bullish") and 
                    asset.order_groups.get("bearish"))
    
    if oco_count == len(engine.plan.active_assets):
        success_points.append(f"✅ Всі {oco_count} активів мають повні OCO групи")
    else:
        issues.append(f"❌ Не всі активи мають повні OCO групи")
    
    print("🎯 УСПІХИ:")
    for point in success_points:
        print(f"   {point}")
    
    if issues:
        print("\n⚠️ ПРОБЛЕМИ:")
        for issue in issues:
            print(f"   {issue}")
    
    overall_success = len(issues) == 0
    print(f"\n🏆 ЗАГАЛЬНА ОЦІНКА: {'✅ ВІДМІННО' if overall_success else '⚠️ ПОТРЕБУЄ УВАГИ'}")
    
    return overall_success

if __name__ == "__main__":
    # Встановлюємо тестове середовище
    os.environ['EQUITY_OVERRIDE'] = '10000.0'
    
    success = test_plan_execution()
    
    print(f"\n🎯 РЕЗУЛЬТАТ: План {'ГОТОВИЙ ДО ВИКОНАННЯ' if success else 'ПОТРЕБУЄ ДООПРАЦЮВАНЬ'}")
