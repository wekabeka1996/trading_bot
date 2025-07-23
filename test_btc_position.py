"""
🚀 ПРОСТИЙ ТЕСТ - ОДНА ПОЗИЦІЯ BTC/USDT
Тестуємо створення позиції на найліквіднішій парі
"""

import asyncio
import logging
from main import TradingBot

# Налаштовуємо логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_btc_position():
    """Тест створення однієї BTC позиції"""
    
    print("🚀 ТЕСТ ОДНІЄЇ BTC ПОЗИЦІЇ")
    print("=" * 40)
    
    try:
        # Створюємо бот БЕЗ конфігу (він сам завантажить config.json)
        bot = TradingBot()
        
        # Ініціалізуємо підключення
        connection_success = await bot.init_exchange()
        if not connection_success:
            print("❌ Не вдалося підключитися до біржі")
            return False
        
        print("✅ Підключення до біржі успішне")
        
        # Отримуємо поточну ціну BTC
        btc_price = await bot.get_current_price("BTC/USDT")
        print(f"💎 Поточна ціна BTC: ${btc_price}")
        
        # Розраховуємо МІНІМАЛЬНУ кількість (0.001 BTC)
        min_quantity = 0.001  # Мінімум для BTC/USDT
        position_size = min_quantity * btc_price
        
        print(f"📊 Мінімальна кількість: {min_quantity} BTC")
        print(f"💰 Потрібна сума: ${position_size:.2f}")
        print(f"💵 Очікувана вартість: ${min_quantity * btc_price:.2f}")
        
        if position_size > 200:  # Якщо занадто дорого для тесту
            print(f"⚠️  BTC занадто дорогий для тесту (${position_size:.2f})")
            print("🔄 Переходимо на більш доступну монету...")
            
            # Тестуємо ETH/USDT замість BTC
            eth_price = await bot.get_current_price("ETH/USDT")
            print(f"💎 Поточна ціна ETH: ${eth_price}")
            
            test_position_size = 50  # $50 для тесту
            quantity = test_position_size / eth_price
            
            print(f"🔢 Кількість ETH для купівлі: {quantity:.6f}")
            
            # Імпортуємо OrderDebugger
            from order_debugger import OrderDebugger
            
            # Створюємо тестовий ордер на ETH
            debugger = OrderDebugger(bot.exchange_manager.exchange)
            order_result = debugger.debug_create_order(
                symbol="ETH/USDT",
                side="buy", 
                amount=quantity,
                order_type="market"
            )
            
            symbol_used = "ETH/USDT"
        else:
            # Імпортуємо OrderDebugger
            from order_debugger import OrderDebugger
            
            # Створюємо тестовий ордер на BTC
            debugger = OrderDebugger(bot.exchange_manager.exchange)
            order_result = debugger.debug_create_order(
                symbol="BTC/USDT",
                side="buy", 
                amount=min_quantity,
                order_type="market"
            )
            
            symbol_used = "BTC/USDT"
        
        if "error" in order_result:
            print(f"❌ Помилка створення ордера: {order_result['error']}")
            return False
        else:
            print(f"✅ ОРДЕР СТВОРЕНО УСПІШНО!")
            print(f"  Символ: {symbol_used}")
            print(f"  ID: {order_result.get('id')}")
            print(f"  Статус: {order_result.get('status')}")
            print(f"  Виконано: {order_result.get('filled', 0)}")
            return True
            
    except Exception as e:
        print(f"❌ Критична помилка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_btc_position())
