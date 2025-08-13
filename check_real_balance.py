#!/usr/bin/env python3
# Перевірка реального балансу на Binance Futures

from dotenv import load_dotenv
import os
from trading_bot.exchange_connector import BinanceFuturesConnector

def main():
    load_dotenv()
    use_testnet = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_SECRET')
    equity_override = os.getenv('EQUITY_OVERRIDE')

    mode = 'TESTNET' if use_testnet else 'MAINNET (РЕАЛЬНІ ГРОШІ!)'
    print(f'🎯 Режим: {mode}')
    print(f'🔑 API ключ: {api_key[:10]}...')
    
    if equity_override:
        print(f'⚠️ УВАГА: Активна емуляція капіталу: ${equity_override}')
        print('   Для реальної торгівлі видаліть EQUITY_OVERRIDE з .env')
    else:
        print('✅ Емуляція капіталу ВИМКНЕНА - використовується реальний баланс')

    try:
        exchange = BinanceFuturesConnector(api_key, api_secret, testnet=use_testnet)
        
        if exchange.check_connection():
            print('\n✅ Підключення до Binance API успішне')
            
            # Отримуємо баланс
            balance = exchange.get_futures_account_balance()
            print(f'💰 Futures баланс: ${balance:.2f} USDT')
            
            # Детальна інформація про акаунт
            account_info = exchange.client.futures_account()
            available_balance = float(account_info['availableBalance'])
            total_balance = float(account_info['totalWalletBalance'])
            
            print(f'📊 Вільна маржа: ${available_balance:.2f}')
            print(f'📈 Загальний баланс: ${total_balance:.2f}')
            
            # Перевіримо чи є відкриті позиції
            positions = exchange.get_position_information()
            open_positions = [p for p in positions if float(p['positionAmt']) != 0]
            
            if open_positions:
                print(f'\n⚠️ ВІДКРИТІ ПОЗИЦІЇ ({len(open_positions)}):')
                for pos in open_positions:
                    symbol = pos['symbol']
                    amount = float(pos['positionAmt'])
                    entry_price = float(pos['entryPrice'])
                    pnl = float(pos['unRealizedPnl'])
                    side = 'LONG' if amount > 0 else 'SHORT'
                    print(f'   {symbol}: {side} {abs(amount):.4f} @ ${entry_price:.4f} (PnL: ${pnl:.2f})')
            else:
                print('\n✅ Немає відкритих позицій')
                
        else:
            print('❌ Помилка підключення до Binance API')
            
    except Exception as e:
        print(f'⚠️ Помилка: {e}')

if __name__ == '__main__':
    main()
