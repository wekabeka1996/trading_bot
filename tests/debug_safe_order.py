#!/usr/bin/env python3
"""
Дебаг SafeOrderManager - знаходимо де None
"""

import os
import sys
from dotenv import load_dotenv
import ccxt
import logging

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Завантажуємо .env
load_dotenv()

def debug_ticker_data():
    """Дебагуємо дані тікера для FIDA/USDT"""
    
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
        print("🔍 Завантажуємо дані для FIDA/USDT...")
        
        # Завантажуємо ринки
        markets = exchange.load_markets()
        
        # Отримуємо тікер
        ticker = exchange.fetch_ticker('FIDA/USDT')
        
        print("\n📊 Дані тікера FIDA/USDT:")
        print(f"  Last: {ticker.get('last')} (type: {type(ticker.get('last'))})")
        print(f"  Bid: {ticker.get('bid')} (type: {type(ticker.get('bid'))})")
        print(f"  Ask: {ticker.get('ask')} (type: {type(ticker.get('ask'))})")
        print(f"  BaseVolume: {ticker.get('baseVolume')} (type: {type(ticker.get('baseVolume'))})")
        print(f"  QuoteVolume: {ticker.get('quoteVolume')} (type: {type(ticker.get('quoteVolume'))})")
        
        # Перевіряємо всі None значення
        none_fields = []
        for key, value in ticker.items():
            if value is None:
                none_fields.append(key)
        
        if none_fields:
            print(f"\n⚠️  Поля з None значеннями: {none_fields}")
        else:
            print("\n✅ Жодних None значень не знайдено")
            
        # Тестуємо розрахунки з fallback
        last_price = ticker['last']
        bid_price = ticker.get('bid') or last_price * 0.999  
        ask_price = ticker.get('ask') or last_price * 1.001  
        
        print(f"\n🧮 Розрахунки з fallback:")
        print(f"  Last: ${last_price}")
        print(f"  Bid (calc): ${bid_price}")
        print(f"  Ask (calc): ${ask_price}")
        
        # Тестуємо операцію множення
        try:
            test_calc = ask_price * 1.001
            print(f"  Ask * 1.001 = ${test_calc}")
            print("✅ Множення працює!")
        except Exception as e:
            print(f"❌ Помилка множення: {e}")
            
    except Exception as e:
        print(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_ticker_data()
