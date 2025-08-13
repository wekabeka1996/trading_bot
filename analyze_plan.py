#!/usr/bin/env python3
"""
Глибокий аналіз торгового плану відповідно до коду
"""

import logging
from datetime import datetime, timedelta
import pytz
from trading_bot.plan_parser import PlanParser
from trading_bot.engine import Engine

def analyze_trading_plan():
    """Повний аналіз торгового плану"""
    
    print("🔍 ГЛИБОКИЙ АНАЛІЗ ТОРГОВОГО ПЛАНУ")
    print("=" * 50)
    
    # Завантаження плану
    parser = PlanParser('data/trading_plan.json')
    if not parser.load_and_validate():
        print("❌ План не валідний!")
        return
        
    plan = parser.get_plan()
    if not plan:
        print("❌ План не завантажено!")
        return
        
    print(f"✅ План '{plan.plan_type}' v{plan.plan_version} завантажено")
    print(f"📅 Дата плану: {plan.plan_date}")
    print()
    
    # Аналіз активних активів
    print("📊 АНАЛІЗ АКТИВНИХ АКТИВІВ:")
    print("-" * 30)
    
    total_position_size = 0
    for i, asset in enumerate(plan.active_assets, 1):
        print(f"{i}. {asset.symbol} ({asset.strategy})")
        print(f"   📈 Плече: {asset.leverage}x")
        print(f"   💰 Розмір позиції: {asset.position_size_pct*100:.1f}%")
        print(f"   🏷️ Стратегія: {asset.strategy}")
        
        # Перевірка груп ордерів для OCO
        bullish = asset.order_groups.get("bullish")
        bearish = asset.order_groups.get("bearish") 
        
        if asset.strategy == "oco_breakout":
            if bullish and bearish:
                print(f"   ✅ OCO групи: bullish + bearish")
                print(f"      📈 BUY STOP: {bullish.trigger_price}")
                print(f"      📉 SELL STOP: {bearish.trigger_price}")
            else:
                print(f"   ❌ OCO групи: відсутні обидві групи!")
        else:
            print(f"   ⚠️ Стратегія '{asset.strategy}' не реалізована в коді!")
            
        total_position_size += asset.position_size_pct
        print()
    
    print(f"📊 Загальний розмір позицій: {total_position_size*100:.1f}%")
    if total_position_size > 1.0:
        print("⚠️ УВАГА: Загальний розмір позицій > 100%!")
    print()
    
    # Аналіз торгових фаз
    print("⏰ АНАЛІЗ ТОРГОВИХ ФАЗ:")
    print("-" * 25)
    
    # Список реалізованих методів у Engine
    implemented_actions = {
        'cancel_all_untriggered': '_handle_cancel_all_untriggered',
        'close_all_positions': '_handle_close_all_open_positions',
        'close_all_open_positions': '_handle_close_all_open_positions',
        'place_all_orders': '_handle_place_all_orders',
        'verify_conditions': '_handle_verify_conditions',
        'monitor_jobless_claims': '_handle_monitor_jobless_claims',
        'place_conditional_orders': '_handle_place_conditional_orders',
        'check_arb_conditions': '_handle_check_arb_conditions',
        'check_sol_entry': '_handle_check_sol_entry'
    }
    
    for phase_name, phase in plan.trade_phases.items():
        action = phase.action
        time_str = phase.time
        description = phase.description
        
        print(f"⏰ {time_str} - {phase_name}")
        print(f"   📝 Опис: {description}")
        print(f"   🎯 Дія: {action}")
        
        if action in implemented_actions:
            print(f"   ✅ Реалізовано: {implemented_actions[action]}")
        elif action:
            print(f"   ❌ НЕ реалізовано: _handle_{action}")
        else:
            print(f"   ❌ Дія не вказана!")
        print()
    
    # Аналіз ризик-тригерів
    print("⚡ АНАЛІЗ РИЗИК-ТРИГЕРІВ:")
    print("-" * 25)
    
    for trigger_name, trigger in plan.risk_triggers.items():
        print(f"🚨 {trigger_name}")
        print(f"   🎯 Дія: {trigger.action}")
        print(f"   📊 Поріг: {getattr(trigger, 'threshold', 'N/A')}")
        print(f"   📊 Поріг %: {getattr(trigger, 'threshold_pct', 'N/A')}")
        print(f"   ❌ Статус: НЕ реалізовано")
        print()
    
    # Аналіз глобальних налаштувань
    print("🌐 ГЛОБАЛЬНІ НАЛАШТУВАННЯ:")
    print("-" * 25)
    
    gs = plan.global_settings
    print(f"💼 Макс. ризик портфеля: {gs.max_portfolio_risk*100:.1f}%")
    print(f"🛑 Emergency stop-loss: {gs.emergency_stop_loss*100:.1f}%")
    print(f"🎯 Денна ціль прибутку: {gs.daily_profit_target*100:.1f}%")
    print(f"📈 Макс. позицій одночасно: {gs.max_concurrent_positions}")
    print(f"💰 Макс. сума на угоду: ${gs.max_notional_per_trade}")
    print(f"📊 Ліміт маржі: {gs.margin_limit_pct*100:.1f}%")
    print()
    
    # Критичні проблеми
    print("🚨 КРИТИЧНІ ПРОБЛЕМИ:")
    print("-" * 20)
    
    problems = []
    
    # Перевірка реалізації стратегій
    for asset in plan.active_assets:
        if asset.strategy != "oco_breakout":
            problems.append(f"Стратегія '{asset.strategy}' для {asset.symbol} не реалізована")
    
    # Перевірка фаз
    unimplemented_phases = []
    for phase_name, phase in plan.trade_phases.items():
        if phase.action and phase.action not in implemented_actions:
            unimplemented_phases.append(f"{phase_name} -> {phase.action}")
    
    if unimplemented_phases:
        problems.append(f"Нереалізовані фази: {', '.join(unimplemented_phases)}")
    
    # Перевірка OCO груп
    for asset in plan.active_assets:
        if asset.strategy == "oco_breakout":
            if not (asset.order_groups.get("bullish") and asset.order_groups.get("bearish")):
                problems.append(f"OCO для {asset.symbol}: відсутні bullish/bearish групи")
    
    if problems:
        for i, problem in enumerate(problems, 1):
            print(f"{i}. ❌ {problem}")
    else:
        print("✅ Критичних проблем не виявлено!")
    
    print()
    
    # Прогноз виконання
    print("🔮 ПРОГНОЗ ВИКОНАННЯ:")
    print("-" * 20)
    
    if not problems:
        print("✅ План буде виконуватися коректно")
        print("📈 Ордери будуть розміщені за OCO стратегією")
        print("⏰ Часові фази спрацюють згідно з розкладом")
    else:
        print("⚠️ План буде виконуватися частково")
        print("📈 OCO ордери будуть розміщені (якщо є обидві групи)")
        print("❌ Деякі фази будуть проігноровані")
        print("❌ Деякі стратегії не будуть працювати")
    
    return len(problems) == 0

if __name__ == "__main__":
    # Налаштування логування для тишини
    logging.getLogger().setLevel(logging.WARNING)
    
    success = analyze_trading_plan()
    print(f"\n🎯 ЗАГАЛЬНА ОЦІНКА: {'✅ ПЛАН ГОТОВИЙ' if success else '⚠️ ПОТРІБНІ ДООПРАЦЮВАННЯ'}")
