# trading_bot/utils.py
# Допоміжні функції, які використовуються в різних частинах проєкту.

import logging
import pandas as pd
import pandas_ta as ta
from decimal import Decimal, ROUND_DOWN

def round_down(value: float, decimals: int) -> float:
    """Округлює число вниз до вказаної кількості десяткових знаків."""
    with_decimals = Decimal(str(value))
    place = Decimal(str(10**-decimals))
    rounded = with_decimals.quantize(place, rounding=ROUND_DOWN)
    return float(rounded)

def get_exchange_filters(client, symbol: str) -> dict:
    """Отримує фільтри (правила) для торгової пари з біржі."""
    try:
        info = client.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == symbol:
                filters = {}
                for f in s['filters']:
                    filters[f['filterType']] = f
                return filters
    except Exception as e:
        logging.error(f"Не вдалося отримати фільтри для {symbol}: {e}")
    return {}

def calculate_atr(klines: list, length: int = 14) -> float | None:
    """
    Розраховує значення Average True Range (ATR).
    :param klines: Історичні дані свічок з Binance API.
    :param length: Період для розрахунку ATR.
    :return: Останнє значення ATR або None у разі помилки.
    """
    if not klines or len(klines) < length:
        logging.warning(f"Недостатньо даних для розрахунку ATR (потрібно {length}, отримано {len(klines)}).")
        return None
    
    try:
        # Створюємо DataFrame з потрібними колонками
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
            'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume',
            'taker_buy_quote_asset_volume', 'ignore'
        ])
        # Конвертуємо ціни у числовий формат
        df[['high', 'low', 'close']] = df[['high', 'low', 'close']].apply(pd.to_numeric)
        
        # Розраховуємо ATR за допомогою pandas_ta
        df.ta.atr(length=length, append=True)
        
        # Повертаємо останнє значення ATR
        last_atr = df[f'ATRr_{length}'].iloc[-1]
        return float(last_atr)
    except Exception as e:
        logging.error(f"Помилка при розрахунку ATR: {e}")
        return None
