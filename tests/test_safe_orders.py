#!/usr/bin/env python3
"""
🧪 ТЕСТ БЕЗПЕЧНОГО МЕНЕДЖЕРА ОРДЕРІВ
Тестування SafeOrderManager для вирішення проблем з PERCENT_PRICE та ліквідністю
"""

import logging
from exchange_manager import ExchangeManager
from safe_order_manager import SafeOrderManager
from logging_setup import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

def test_safe_order_manager():
    """Тестування безпечного створення ордерів"""
    
    print("🧪 ТЕСТ БЕЗПЕЧНОГО МЕНЕДЖЕРА ОРДЕРІВ")
    print("=" * 50)
    
    # Ініціалізуємо підключення
    exchange_manager = ExchangeManager()
    if not exchange_manager.initialize():
        print("❌ Не вдалося підключитися до біржі")
        return False
    
    print("✅ Підключення до біржі успішне")
    
    # Створюємо безпечний менеджер
    safe_manager = SafeOrderManager(exchange_manager.exchange)
    
    # Тестові параметри (малі суми для безпеки)
    test_symbols = ["BTC/USDT", "PENDLE/USDT", "DIA/USDT"]
    test_amount_usd = 10.0  # $10 для тесту
    
    for symbol in test_symbols:
        print(f"\n🔍 Тестування {symbol}")
        print("-" * 30)
        
        try:
            # Завантажуємо інформацію про ринок
            if not safe_manager.load_market_info(symbol):
                print(f"❌ Не вдалося завантажити дані для {symbol}")
                continue
            
            # Отримуємо тікер
            ticker = safe_manager.tickers[symbol]
            current_price = ticker['last']
            amount = test_amount_usd / current_price
            
            print(f"💰 Поточна ціна: ${current_price}")
            print(f"📊 Кількість: {amount:.6f}")
            print(f"💵 Нотіонал: ${amount * current_price:.2f}")
            
            # Перевіряємо ліквідність
            liquidity_check = safe_manager.check_liquidity(symbol, test_amount_usd)
            print(f"🏊 Ліквідність: {'✅ ОК' if liquidity_check['valid'] else '❌ ' + liquidity_check['reason']}")
            
            if liquidity_check["valid"]:
                print(f"  24h Volume: ${liquidity_check['volume_24h']:,.0f}")
                print(f"  Order %: {liquidity_check['order_percent']:.4f}%")
            
            # Отримуємо безпечну ціну
            safe_price = safe_manager.get_safe_price(symbol, "buy")
            if safe_price:
                print(f"🛡️ Безпечна ціна: ${safe_price}")
                price_diff = ((safe_price - current_price) / current_price) * 100
                print(f"  Різниця: {price_diff:+.2f}%")
            else:
                print("❌ Не вдалося розрахувати безпечну ціну")
            
            # ТЕСТОВИЙ ОРДЕР (ЗАКОМЕНТОВАНО ДЛЯ БЕЗПЕКИ)
            print("🚫 Реальний ордер пропущено (тестовий режим)")
            # order_result = safe_manager.create_safe_market_order_via_limit(symbol, "buy", amount)
            # if "error" not in order_result:
            #     print(f"✅ Тестовий ордер успішний: {order_result.get('id')}")
            # else:
            #     print(f"❌ Помилка тестового ордера: {order_result['error']}")
            
        except Exception as e:
            print(f"❌ Помилка тестування {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*50}")
    print("🏁 Тест безпечного менеджера завершено")
    return True

if __name__ == "__main__":
    test_safe_order_manager()
