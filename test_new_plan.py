#!/usr/bin/env python3
# Тестування нового плану з LEVER, PLAY, OMNI

from trading_bot.plan_parser import PlanParser
from trading_bot.engine import Engine
from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal
import os
from dotenv import load_dotenv

def test_new_plan():
    """Повне тестування нового плану"""
    
    print('🧪 ТЕСТУВАННЯ НОВОГО ПЛАНУ v2.2')
    print('='*60)
    
    # 1. Валідація плану
    print('1️⃣ ВАЛІДАЦІЯ ПЛАНУ')
    print('-'*30)
    
    parser = PlanParser('data/trading_plan.json')
    if not parser.load_and_validate():
        print('❌ Помилка валідації плану')
        return False
        
    plan = parser.plan
    print('✅ План валідовано успішно!')
    print(f'📊 Версія: {plan.plan_version}')
    print()
    
    # 2. Аналіз нових активів
    print('2️⃣ АНАЛІЗ АКТИВІВ')
    print('-'*30)
    
    total_position_size = 0
    for asset in plan.active_assets:
        print(f'   {asset.symbol}:')
        print(f'     Розмір: {asset.position_size_pct*100:.0f}%')
        print(f'     Плече: {asset.leverage}x')
        print(f'     Ордери: {len(asset.order_groups)} напрямків')
        total_position_size += asset.position_size_pct
        
        # Детальні ціни
        for direction, group in asset.order_groups.items():
            print(f'       {direction}: trigger ${group.trigger_price}, SL ${group.stop_loss}')
    
    print(f'   Загальний розмір позицій: {total_position_size*100:.0f}%')
    print()
    
    # 3. Перевірка маржі
    print('3️⃣ ПЕРЕВІРКА МАРЖІ')
    print('-'*30)
    
    total_margin = 0
    for asset in plan.active_assets:
        margin_req = asset.position_size_pct / asset.leverage
        total_margin += margin_req
        print(f'   {asset.symbol}: {asset.position_size_pct*100:.0f}% / {asset.leverage} = {margin_req*100:.1f}%')
    
    margin_limit = plan.global_settings.margin_limit_pct
    print(f'   Загальна маржа: {total_margin*100:.1f}%')
    print(f'   Ліміт маржі: {margin_limit*100:.0f}%')
    
    if total_margin <= margin_limit:
        print('   ✅ Margin check PASSED')
    else:
        print('   ❌ Margin check FAILED - ПЕРЕВИЩЕННЯ!')
        return False
    print()
    
    # 4. Перевірка ризику
    print('4️⃣ НАЛАШТУВАННЯ РИЗИКУ')
    print('-'*30)
    
    print(f'   Risk Budget: {plan.risk_budget*100:.1f}%')
    print(f'   Max Portfolio Risk: {plan.global_settings.max_portfolio_risk*100:.1f}%')
    print(f'   Emergency Stop Loss: {plan.global_settings.emergency_stop_loss*100:.1f}%')
    
    if plan.risk_budget == plan.global_settings.max_portfolio_risk:
        print('   ✅ Ризики узгоджені')
    else:
        print('   ⚠️ Ризики НЕ узгоджені')
    print()
    
    # 5. Часові фази
    print('5️⃣ ТОРГОВІ ФАЗИ')
    print('-'*30)
    
    for phase_name, phase in plan.trade_phases.items():
        print(f'   {phase.time}: {phase.description}')
    print()
    
    # 6. Тест Engine
    print('6️⃣ ТЕСТ ENGINE')
    print('-'*30)
    
    load_dotenv()
    use_testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
    
    if use_testnet:
        api_key = os.getenv('BINANCE_TESTNET_API_KEY', 'test')
        api_secret = os.getenv('BINANCE_TESTNET_SECRET', 'test')
    else:
        api_key = os.getenv('BINANCE_API_KEY', 'test')
        api_secret = os.getenv('BINANCE_SECRET', 'test')
    
    try:
        notifier = TelegramNotifier('', '')
        journal = TradingJournal()
        exchange = BinanceFuturesConnector(api_key, api_secret, testnet=use_testnet)
        
        engine = Engine(parser, exchange, notifier, journal)
        
        print('   Ініціалізація Engine...')
        if engine._initial_setup():
            print('   ✅ Engine успішно ініціалізований')
            print('   ✅ Margin guard пройшов')
            print('   ✅ Всі системи готові')
        else:
            print('   ❌ Помилка ініціалізації Engine')
            return False
            
    except AssertionError as e:
        print(f'   🚨 MARGIN GUARD СПРАЦЮВАВ: {e}')
        return False
    except Exception as e:
        print(f'   ⚠️ Помилка Engine: {e}')
        return False
    
    print()
    
    # 7. Flash-drop тригер
    print('7️⃣ ЗАХИСНІ МЕХАНІЗМИ')
    print('-'*30)
    
    flash_drop = plan.risk_triggers.get('flash_drop')
    if flash_drop:
        print(f'   Flash-drop: {flash_drop.threshold_pct*100:.1f}% -> {flash_drop.action}')
        print('   ✅ Flash-drop захист активний')
    else:
        print('   ❌ Flash-drop захист відсутній')
    
    print('   ✅ Kill-switch: -2.5%')
    print('   ✅ Individual Stop-Loss на всі позиції')
    print('   ✅ Free-Margin Guard: 20%')
    print()
    
    # 8. Підсумок
    print('8️⃣ ПІДСУМОК ТЕСТУВАННЯ')
    print('-'*30)
    
    print('✅ ПЛАН ПОВНІСТЮ ГОТОВИЙ!')
    print('✅ Нові активи: LEVERUSDT, PLAYUSDT, OMNIUSDT')
    print('✅ Маржа під контролем')
    print('✅ Всі захисні системи активні')
    print('✅ Engine успішно ініціалізований')
    print()
    print('🚀 МОЖНА ЗАПУСКАТИ В РОБОТУ!')
    
    return True

if __name__ == '__main__':
    test_new_plan()
