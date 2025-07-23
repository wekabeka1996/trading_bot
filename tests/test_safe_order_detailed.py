#!/usr/bin/env python3
"""
Тестуємо SafeOrderManager з детальним логуванням
"""

import os
import sys
from dotenv import load_dotenv
import ccxt
import logging
from safe_order_manager import SafeOrderManager

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Завантажуємо .env
load_dotenv()

def test_safe_order_manager():
    """Тестуємо SafeOrderManager з FIDA/USDT"""
    
    # Ініціалізуємо біржу
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_SECRET_KEY'),
        'sandbox': True,  # Тестнет
        'options': {
            'defaultType': 'future'  # Futures
        }
    })
    
    try:
        print("🧪 Тестуємо SafeOrderManager...")
        
        # Створюємо SafeOrderManager
        safe_manager = SafeOrderManager(exchange)
        
        # Тестуємо з маленьким ордером
        symbol = 'FIDA/USDT'
        side = 'buy'
        amount = 1.0  # 1 FIDA (мінімум)
        
        print(f"\n📋 Параметри тесту:")
        print(f"  Symbol: {symbol}")
        print(f"  Side: {side}")
        print(f"  Amount: {amount}")
        
        # Викликаємо створення ордера
        result = safe_manager.create_safe_market_order_via_limit(symbol, side, amount)
        
        print(f"\n📄 Результат:")
        if 'error' in result:
            print(f"❌ Помилка: {result['error']}")
        else:
            print(f"✅ Успіх!")
            print(f"  Order ID: {result.get('id')}")
            print(f"  Status: {result.get('status')}")
            print(f"  Price: ${result.get('price')}")
            print(f"  Amount: {result.get('amount')}")
            
    except Exception as e:
        print(f"❌ Критична помилка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_safe_order_manager()
