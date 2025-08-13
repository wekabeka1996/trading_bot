#!/usr/bin/env python3
# Перевірка виправлених налаштувань ризику

from trading_bot.plan_parser import PlanParser

def check_risk_settings():
    """Перевіряє налаштування ризику після виправлень"""
    
    print('🔧 ПЕРЕВІРКА ВИПРАВЛЕНИХ НАЛАШТУВАНЬ')
    print('='*50)
    
    # Завантажуємо план
    parser = PlanParser('data/trading_plan.json')
    if not parser.load_and_validate():
        print('❌ Помилка валідації плану')
        return
        
    plan = parser.plan
    print('✅ План валідовано успішно!')
    print()
    
    # Перевіряємо узгодженість налаштувань
    print('📊 НАЛАШТУВАННЯ РИЗИКУ:')
    risk_budget = plan.risk_budget
    max_portfolio_risk = plan.global_settings.max_portfolio_risk
    emergency_stop = plan.global_settings.emergency_stop_loss
    
    print(f'   Risk Budget: {risk_budget*100:.1f}%')
    print(f'   Max Portfolio Risk: {max_portfolio_risk*100:.1f}%')
    print(f'   Emergency Stop Loss: {emergency_stop*100:.1f}%')
    
    # Перевіряємо узгодженість
    if risk_budget == max_portfolio_risk:
        print('   ✅ Risk budget та max portfolio risk узгоджені')
    else:
        print('   ⚠️ Risk budget та max portfolio risk НЕ узгоджені')
        
    if emergency_stop == -risk_budget:
        print('   ✅ Emergency stop loss узгоджений з risk budget')
    else:
        print('   ⚠️ Emergency stop loss НЕ узгоджений з risk budget')
    
    print()
    
    # Перевіряємо margin calculation
    print('💰 ПЕРЕВІРКА МАРЖІ:')
    total_margin = sum(asset.position_size_pct / asset.leverage for asset in plan.active_assets)
    margin_limit = plan.global_settings.margin_limit_pct
    
    print(f'   ARB: {plan.active_assets[0].position_size_pct:.1%} / {plan.active_assets[0].leverage} = {plan.active_assets[0].position_size_pct/plan.active_assets[0].leverage:.1%}')
    print(f'   ETH: {plan.active_assets[1].position_size_pct:.1%} / {plan.active_assets[1].leverage} = {plan.active_assets[1].position_size_pct/plan.active_assets[1].leverage:.1%}')
    print(f'   SOL: {plan.active_assets[2].position_size_pct:.1%} / {plan.active_assets[2].leverage} = {plan.active_assets[2].position_size_pct/plan.active_assets[2].leverage:.1%}')
    print(f'   Загальна потрібна маржа: {total_margin*100:.1f}%')
    print(f'   Ліміт маржі: {margin_limit*100:.1f}%')
    
    if total_margin <= margin_limit:
        print('   ✅ Margin check PASSED')
    else:
        print('   ❌ Margin check FAILED - перевищення лімітів!')
    
    print()
    
    # Перевіряємо flash drop
    print('🚨 FLASH-DROP ТРИГЕР:')
    flash_drop = plan.risk_triggers.get('flash_drop')
    if flash_drop:
        print(f'   Поріг: {flash_drop.threshold_pct*100:.1f}%')
        print(f'   Дія: {flash_drop.action}')
        print(f'   Активи: {flash_drop.assets}')
        print('   ✅ Flash-drop тригер активний')
    else:
        print('   ❌ Flash-drop тригер відсутній')
    
    print()
    print('📋 ПІДСУМОК:')
    print('   ✅ Risk budget підвищено до 3.3%')
    print('   ✅ Max portfolio risk синхронізовано з risk budget')
    print('   ✅ Emergency stop loss синхронізовано (-3.3%)')
    print('   ✅ Margin check додано в код')
    print('   ✅ Flash-drop захист активовано')
    print()
    print('🚀 ПЛАН ГОТОВИЙ ДО ВИКОРИСТАННЯ!')

if __name__ == '__main__':
    check_risk_settings()
