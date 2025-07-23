#!/usr/bin/env python3
"""
🚀 РЕАЛЬНИЙ ТЕСТ БЕЗПЕЧНИХ ОРДЕРІВ
Створення справжніх ордерів з маленькими сумами для тестування
"""

import logging
from exchange_manager import ExchangeManager
from safe_order_manager import SafeOrderManager
from logging_setup import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

def test_real_safe_orders():
    """Реальний тест безпечних ордерів з мінімальними сумами"""
    
    print("🚀 РЕАЛЬНИЙ ТЕСТ БЕЗПЕЧНИХ ОРДЕРІВ")
    print("=" * 50)
    print("⚠️  УВАГА: Створюємо справжні ордери на тестнеті!")
    print("💰 Використовуємо мінімальні суми для безпеки")
    print()
    
    # Ініціалізуємо підключення
    exchange_manager = ExchangeManager()
    if not exchange_manager.initialize():
        print("❌ Не вдалося підключитися до біржі")
        return False
    
    print("✅ Підключення до біржі успішне")
    
    # Створюємо безпечний менеджер
    safe_manager = SafeOrderManager(exchange_manager.exchange)
    
    # Тестові параметри - МІНІМАЛЬНІ суми
    test_cases = [
        {"symbol": "DIA/USDT", "amount_usd": 6.0},     # $6 для DIA (мін $5)
        {"symbol": "PENDLE/USDT", "amount_usd": 6.0},  # $6 для PENDLE  
        {"symbol": "API3/USDT", "amount_usd": 6.0},    # $6 для API3
    ]
    
    results = []
    
    for test_case in test_cases:
        symbol = test_case["symbol"]
        amount_usd = test_case["amount_usd"]
        
        print(f"\n🎯 РЕАЛЬНИЙ ТЕСТ: {symbol}")
        print("-" * 40)
        
        try:
            # Завантажуємо інформацію про ринок
            if not safe_manager.load_market_info(symbol):
                print(f"❌ Не вдалося завантажити дані для {symbol}")
                continue
            
            # Отримуємо тікер
            ticker = safe_manager.tickers[symbol]
            current_price = ticker['last']
            amount = amount_usd / current_price
            
            print(f"💰 Поточна ціна: ${current_price}")
            print(f"📊 Кількість: {amount:.6f}")
            print(f"💵 Нотіонал: ${amount * current_price:.2f}")
            
            # Перевіряємо ліквідність
            liquidity_check = safe_manager.check_liquidity(symbol, amount_usd)
            if not liquidity_check["valid"]:
                print(f"❌ Ліквідність недостатня: {liquidity_check['reason']}")
                continue
            
            print(f"✅ Ліквідність ОК (24h: ${liquidity_check['volume_24h']:,.0f})")
            
            # Отримуємо безпечну ціну
            safe_price = safe_manager.get_safe_price(symbol, "buy")
            if not safe_price:
                print("❌ Не вдалося розрахувати безпечну ціну")
                continue
            
            price_diff = ((safe_price - current_price) / current_price) * 100
            print(f"🛡️ Безпечна ціна: ${safe_price} ({price_diff:+.2f}%)")
            
            # ========== СТВОРЮЄМО РЕАЛЬНИЙ ОРДЕР ==========
            print(f"\n🔥 СТВОРЮЮ РЕАЛЬНИЙ ОРДЕР НА БІРЖІ!")
            print(f"⚠️  Це справжній ордер на ${amount_usd:.2f}")
            
            order_result = safe_manager.create_safe_market_order_via_limit(
                symbol=symbol,
                side="buy",
                amount=amount
            )
            
            if "error" in order_result:
                print(f"❌ Помилка ордера: {order_result['error']}")
                results.append({
                    "symbol": symbol,
                    "amount_usd": amount_usd,
                    "success": False,
                    "error": order_result["error"]
                })
            else:
                print(f"✅ ОРДЕР СТВОРЕНО УСПІШНО!")
                print(f"  🆔 ID: {order_result.get('id')}")
                print(f"  📊 Status: {order_result.get('status')}")
                print(f"  💰 Price: ${order_result.get('price')}")
                print(f"  📈 Amount: {order_result.get('amount')}")
                print(f"  ✅ Filled: {order_result.get('filled', 0)}")
                
                results.append({
                    "symbol": symbol,
                    "amount_usd": amount_usd,
                    "success": True,
                    "order_id": order_result.get('id'),
                    "price": order_result.get('price'),
                    "filled": order_result.get('filled', 0)
                })
            
        except Exception as e:
            print(f"❌ Критична помилка для {symbol}: {e}")
            import traceback
            traceback.print_exc()
            
            results.append({
                "symbol": symbol,
                "amount_usd": amount_usd,
                "success": False,
                "error": str(e)
            })
    
    # Підсумки
    print(f"\n{'='*50}")
    print("📊 ПІДСУМКИ РЕАЛЬНИХ ТЕСТІВ")
    print("=" * 50)
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print(f"✅ Успішних ордерів: {len(successful)}")
    print(f"❌ Невдалих ордерів: {len(failed)}")
    
    if successful:
        print(f"\n🎉 УСПІШНІ ОРДЕРИ:")
        for result in successful:
            print(f"  • {result['symbol']}: ${result['amount_usd']:.2f} → ID {result['order_id']}")
    
    if failed:
        print(f"\n💥 ПОМИЛКИ:")
        for result in failed:
            print(f"  • {result['symbol']}: {result['error']}")
    
    total_spent = sum(r["amount_usd"] for r in successful)
    print(f"\n💸 Загальна сума: ${total_spent:.2f}")
    
    print(f"\n🏁 Реальний тест завершено!")
    return len(successful) > 0

if __name__ == "__main__":
    test_real_safe_orders()
