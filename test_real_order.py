"""
🧪 ТЕСТ РЕАЛЬНОГО ОРДЕРА на Binance Futures Testnet
Перевірка створення ордера з правильними параметрами
"""

import os
import ccxt
from dotenv import load_dotenv

# Завантажуємо .env
load_dotenv()

def test_real_order():
    """Тест створення реального ордера з правильними параметрами"""
    
    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_SECRET')
    
    try:
        # Ініціалізуємо exchange
        exchange = ccxt.binance({
            "apiKey": API_KEY,
            "secret": API_SECRET,
            "enableRateLimit": True,
            "sandbox": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            }
        })

        print("🧪 ТЕСТ РЕАЛЬНОГО ОРДЕРА")
        print("=" * 40)
        
        # Перевіряємо баланс
        balance = exchange.fetch_balance()
        usdt_balance = balance['total'].get('USDT', 0)
        print(f"💰 USDT баланс: {usdt_balance}")
        
        if usdt_balance < 10:
            print("❌ Недостатньо USDT для тесту")
            return False
        
        # Отримуємо інформацію про символ BTC/USDT
        markets = exchange.load_markets()
        symbol = "BTC/USDT"
        market = markets[symbol]
        
        print(f"\n📊 Інформація про {symbol}:")
        print(f"  Min notional: {market['limits']['cost']['min']}")
        print(f"  Min quantity: {market['limits']['amount']['min']}")
        print(f"  Precision amount: {market['precision']['amount']}")
        print(f"  Precision price: {market['precision']['price']}")
        
        # Отримуємо поточну ціну
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        print(f"  Поточна ціна: ${current_price}")
        
        # Розраховуємо мінімальну кількість для тесту
        min_notional = market['limits']['cost']['min'] or 5.0
        test_notional = min_notional * 2  # Беремо в 2 рази більше мінімального
        quantity = test_notional / current_price
        
        # Округлюємо кількість до правильної точності
        precision = market['precision']['amount']
        if precision and precision < 1:
            # Для дробової точності (наприклад 1e-05) рахуємо кількість знаків
            decimal_places = len(str(precision).split('.')[-1].rstrip('0'))
            quantity = round(quantity, decimal_places)
        else:
            # Для цілих чисел
            quantity = round(quantity, 5)  # Стандартне округлення до 5 знаків
        
        print(f"\n🔬 ТЕСТОВИЙ ОРДЕР:")
        print(f"  Нотіонал: ${test_notional:.2f}")
        print(f"  Кількість: {quantity}")
        print(f"  Очікувана вартість: ${quantity * current_price:.2f}")
        
        # Створюємо тестовий ордер
        try:
            order = exchange.create_market_buy_order(
                symbol=symbol,
                amount=quantity,
                params={
                    "leverage": 1,  # Мінімальне плече
                    "reduceOnly": False
                }
            )
            
            print(f"\n✅ ОРДЕР СТВОРЕНО УСПІШНО!")
            print(f"  ID: {order['id']}")
            print(f"  Статус: {order['status']}")
            print(f"  Виконано: {order.get('filled', 0)}")
            print(f"  Залишок: {order.get('remaining', 0)}")
            
            return True
            
        except Exception as e:
            print(f"\n❌ ПОМИЛКА СТВОРЕННЯ ОРДЕРА: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Критична помилка: {e}")
        return False

if __name__ == "__main__":
    test_real_order()
