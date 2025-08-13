#!/usr/bin/env python3
"""
Тестовий скрипт для перевірки структури фільтрів API Binance
"""
import sys
import json
import os
from dotenv import load_dotenv
sys.path.append('c:/trading_bot')

from trading_bot.exchange_connector import BinanceFuturesConnector

def test_api_filters():
    try:
        # Завантажуємо змінні з .env
        load_dotenv()
        
        use_testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"
        
        if use_testnet:
            api_key = os.getenv("BINANCE_TESTNET_API_KEY")
            api_secret = os.getenv("BINANCE_TESTNET_SECRET")
            print("🧪 Використовується TESTNET режим")
        else:
            api_key = os.getenv("BINANCE_API_KEY")
            api_secret = os.getenv("BINANCE_SECRET")
            print("💰 Використовується MAINNET режим")
        
        if not api_key or not api_secret:
            print("❌ API ключі не знайдені!")
            return
            
        print("🔍 Створюємо підключення до Binance...")
        exchange = BinanceFuturesConnector(api_key, api_secret, testnet=use_testnet)
        
        print("📊 Отримуємо інформацію про біржу...")
        info = exchange.client.futures_exchange_info()
        
        print("🔎 Шукаємо фільтри для PLAYUSDT...")
        for symbol_info in info['symbols']:
            if symbol_info['symbol'] == 'PLAYUSDT':
                print(f"✅ Знайдено PLAYUSDT на {'MAINNET' if not exchange.testnet else 'TESTNET'}")
                print("📋 Фільтри:")
                
                for f in symbol_info['filters']:
                    if 'NOTIONAL' in f['filterType']:
                        print(f"  🎯 {f['filterType']}:")
                        print(f"     Структура: {json.dumps(f, indent=6)}")
                        print(f"     Ключі: {list(f.keys())}")
                        
                        # Перевіряємо які ключі існують
                        if 'minNotional' in f:
                            print(f"     ✅ minNotional: {f['minNotional']}")
                        if 'notional' in f:
                            print(f"     ✅ notional: {f['notional']}")
                break
        else:
            print("❌ PLAYUSDT не знайдено")
            
    except Exception as e:
        print(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_filters()
