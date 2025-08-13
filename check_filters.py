#!/usr/bin/env python3
"""
Скрипт для перевірки фільтрів символів з торгового плану.
Генерує precision map для використання у боті.
"""

import json
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException


def check_symbol_filters(client: Client, symbol: str) -> dict:
    """Отримує фільтри для символу."""
    try:
        info = client.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == symbol:
                filters = {}
                for f in s['filters']:
                    filters[f['filterType']] = f
                
                return {
                    'symbol': symbol,
                    'status': s['status'],
                    'lot_size': filters.get('LOT_SIZE', {}),
                    'price_filter': filters.get('PRICE_FILTER', {}),
                    'min_notional': filters.get('MIN_NOTIONAL', {}),
                    'market_lot_size': filters.get('MARKET_LOT_SIZE', {}),
                    'max_num_orders': filters.get('MAX_NUM_ORDERS', {})
                }
    except BinanceAPIException as e:
        print(f"Помилка отримання фільтрів для {symbol}: {e}")
        return {'symbol': symbol, 'error': str(e)}
    
    return {'symbol': symbol, 'error': 'Symbol not found'}


def main():
    # Читаємо план
    plan_path = 'data/trading_plan.json'
    if not os.path.exists(plan_path):
        print(f"План не знайдено: {plan_path}")
        return
    
    with open(plan_path, 'r', encoding='utf-8') as f:
        plan = json.load(f)
    
    # Ініціалізуємо клієнт (можна використати testnet=True для тестування)
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    if not api_key or not api_secret:
        print("BINANCE_API_KEY та BINANCE_API_SECRET мають бути встановлені")
        return
    
    client = Client(api_key, api_secret, testnet=True)
    
    # Отримуємо символи з плану
    symbols = [asset['symbol'] for asset in plan.get('active_assets', [])]
    
    print(f"Перевіряємо фільтри для {len(symbols)} символів...")
    print("=" * 80)
    
    results = {}
    
    for symbol in symbols:
        print(f"Перевіряю {symbol}...")
        filters = check_symbol_filters(client, symbol)
        results[symbol] = filters
        
        if 'error' in filters:
            print(f"  ❌ Помилка: {filters['error']}")
        else:
            status = filters['status']
            print(f"  📊 Статус: {status}")
            
            if status != 'TRADING':
                print(f"  ⛔ УВАГА: символ неактивний!")
            
            lot_size = filters.get('lot_size', {})
            price_filter = filters.get('price_filter', {})
            min_notional = filters.get('min_notional', {})
            
            print(f"  🔢 LOT_SIZE: stepSize={lot_size.get('stepSize')}, minQty={lot_size.get('minQty')}")
            print(f"  💰 PRICE_FILTER: tickSize={price_filter.get('tickSize')}")
            print(f"  📈 MIN_NOTIONAL: minNotional={min_notional.get('minNotional')}")
            print()
    
    # Збереження результатів
    output_path = 'data/symbol_filters.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Результати збережено у {output_path}")
    
    # Виводимо підсумок
    active_symbols = [s for s, f in results.items() if f.get('status') == 'TRADING']
    inactive_symbols = [s for s, f in results.items() if f.get('status') != 'TRADING']
    
    print(f"\n📊 Підсумок:")
    print(f"  ✅ Активні символи: {len(active_symbols)}")
    print(f"  ⛔ Неактивні символи: {len(inactive_symbols)}")
    
    if inactive_symbols:
        print(f"  Неактивні: {', '.join(inactive_symbols)}")


if __name__ == "__main__":
    main()
