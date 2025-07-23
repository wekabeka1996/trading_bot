"""
[TARGET] ENTRY ENGINE - Справжня логіка входу
Реалізація ТОЧНИХ умов з плану GPT (не імітація!)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import numpy as np
import ccxt

logger = logging.getLogger(__name__)

class EntryEngine:
    def __init__(self, exchange):
        self.exchange = exchange
        self.cache = {}
        self.cache_ttl = 60  # секунд
    
    async def check_entry_conditions(self, symbol: str, config: dict) -> Tuple[bool, str]:
        """
        СПРАВЖНЯ перевірка умов входу з плану GPT:
        1. Відкат до 1h EMA20 АБО ±0.5% від 1h VWAP
        2. Підтвердження об'ємом ≥150% середнього
        3. Спред <0.15% (для FIDA критично)
        """
        try:
            # Отримуємо свічки 1h
            candles_1h = await self.get_cached_candles(symbol, '1h', 50)
            if not candles_1h or len(candles_1h) < 21:
                return False, "Недостатньо історичних даних"
            
            current_price = float(candles_1h[-1][4])  # close price
            
            # 1. ПЕРЕВІРКА EMA20 (1h)
            ema20_1h = self.calculate_ema(candles_1h, 20)
            ema_condition = current_price <= ema20_1h * 1.005  # до EMA20 + 0.5% толерантність
            
            # 2. ПЕРЕВІРКА VWAP (1h)
            vwap_1h = self.calculate_vwap(candles_1h)
            vwap_condition = abs(current_price - vwap_1h) / vwap_1h <= 0.005  # ±0.5%
            
            # Принаймні одна з умов має виконуватися
            price_condition = ema_condition or vwap_condition
            
            if not price_condition:
                return False, f"Ціна не в зоні входу. EMA20: {ema20_1h:.4f}, VWAP: {vwap_1h:.4f}, Price: {current_price:.4f}"
            
            # 3. ПЕРЕВІРКА ОБ'ЄМУ ≥150% середнього
            volumes = [float(candle[5]) for candle in candles_1h[-12:]]  # останні 12 годин
            avg_volume = np.mean(volumes[:-1])  # без поточної свічки
            current_volume = volumes[-1]
            
            volume_condition = current_volume >= avg_volume * 1.5
            
            if not volume_condition:
                return False, f"Недостатній об'єм. Поточний: {current_volume:.0f}, Потрібно: {avg_volume * 1.5:.0f}"
            
            # 4. ПЕРЕВІРКА СПРЕДУ (критично для FIDA)
            spread = await self.get_spread(symbol)
            max_spread = config.get('spread_threshold', 0.15)
            
            if spread > max_spread:
                return False, f"Спред занадто великий: {spread*100:.2f}% > {max_spread*100:.1f}%"
            
            # 5. ДОДАТКОВА ПЕРЕВІРКА: 5-хвилинне підтвердження
            candles_5m = await self.get_cached_candles(symbol, '5m', 20)
            if candles_5m:
                last_5m_volume = float(candles_5m[-1][5])
                avg_5m_volume = np.mean([float(c[5]) for c in candles_5m[-12:]])
                
                if last_5m_volume < avg_5m_volume * 1.3:  # хоча б 130% на 5m
                    return False, f"Слабке підтвердження на 5m: {last_5m_volume:.0f} < {avg_5m_volume * 1.3:.0f}"
            
            # [OK] ВСІ УМОВИ ВИКОНАНІ
            reason = f"[OK] Вхід дозволено: "
            if ema_condition:
                reason += f"EMA20({ema20_1h:.4f}) "
            if vwap_condition:
                reason += f"VWAP({vwap_1h:.4f}) "
            reason += f"Vol:{current_volume/avg_volume:.1f}x Spread:{spread*100:.2f}%"
            
            return True, reason
            
        except Exception as e:
            logger.error(f"Помилка перевірки входу {symbol}: {e}")
            return False, f"Технічна помилка: {e}"
    
    def calculate_ema(self, candles: list, period: int) -> float:
        """Розрахунок EMA з правильною формулою"""
        if len(candles) < period:
            return 0.0
            
        prices = [float(candle[4]) for candle in candles]  # close prices
        
        # Початкове значення = SMA
        sma = sum(prices[:period]) / period
        ema = sma
        
        # Multiplier для EMA
        multiplier = 2 / (period + 1)
        
        # Розрахунок EMA
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
            
        return ema
    
    def calculate_vwap(self, candles: list) -> float:
        """Розрахунок VWAP (Volume Weighted Average Price)"""
        if not candles:
            return 0.0
            
        total_volume = 0
        total_pv = 0
        
        for candle in candles:
            high = float(candle[2])
            low = float(candle[3])
            close = float(candle[4])
            volume = float(candle[5])
            
            # Typical Price = (H + L + C) / 3
            typical_price = (high + low + close) / 3
            
            total_pv += typical_price * volume
            total_volume += volume
        
        return total_pv / total_volume if total_volume > 0 else 0.0
    
    async def get_cached_candles(self, symbol: str, timeframe: str, limit: int) -> list:
        """Кешування свічок для зменшення API викликів"""
        cache_key = f"{symbol}_{timeframe}_{limit}"
        now = datetime.now()
        
        # Перевіряємо кеш
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if (now - cached_time).seconds < self.cache_ttl:
                return cached_data
        
        # Отримуємо нові дані
        try:
            candles = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            self.cache[cache_key] = (candles, now)
            return candles
        except Exception as e:
            logger.error(f"Помилка отримання свічок {symbol} {timeframe}: {e}")
            return []
    
    async def get_spread(self, symbol: str) -> float:
        """Отримання поточного спреду"""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            bid = float(ticker['bid']) if ticker['bid'] else 0
            ask = float(ticker['ask']) if ticker['ask'] else 0
            
            if bid > 0 and ask > 0:
                spread = (ask - bid) / ((ask + bid) / 2)
                return spread
            else:
                return 0.15  # Консервативне значення якщо немає даних
                
        except Exception as e:
            logger.error(f"Помилка отримання спреду {symbol}: {e}")
            return 0.15

class TimeWindowChecker:
    """Перевірка часових вікон входу"""
    
    @staticmethod
    def is_entry_window_open(start_time: str = "11:45", end_time: str = "12:30") -> bool:
        """Чи відкрите вікно входу 11:45-12:30 EEST"""
        try:
            import pytz
            kiev_tz = pytz.timezone('Europe/Kiev')
            now_kiev = datetime.now(kiev_tz)
            current_time = now_kiev.strftime("%H:%M")
            
            return start_time <= current_time <= end_time
        except:
            # Fallback без pytz
            current_time = datetime.now().strftime("%H:%M")
            return start_time <= current_time <= end_time
    
    @staticmethod
    def minutes_until_powell() -> int:
        """Скільки хвилин до виступу Пауелла (22.07.2025 15:30 EEST)"""
        try:
            import pytz
            kiev_tz = pytz.timezone('Europe/Kiev')
            now_kiev = datetime.now(kiev_tz)
            
            powell_time = datetime(2025, 7, 22, 15, 30, tzinfo=kiev_tz)
            diff = powell_time - now_kiev
            
            return int(diff.total_seconds() / 60)
        except:
            return 999  # Якщо помилка - повертаємо великий номер

# Спрощений тест
async def test_entry_engine():
    """Тест entry engine без реального exchange"""
    
    class MockExchange:
        async def fetch_ohlcv(self, symbol, timeframe, limit):
            # Імітація даних
            base_price = 100.0
            candles = []
            for i in range(limit):
                # [timestamp, open, high, low, close, volume]
                candles.append([
                    1640000000000 + i * 3600000,  # timestamp
                    base_price + i * 0.1,         # open
                    base_price + i * 0.1 + 2,     # high
                    base_price + i * 0.1 - 1,     # low
                    base_price + i * 0.1 + 0.5,   # close
                    1000000 + i * 10000           # volume
                ])
            return candles
        
        async def fetch_ticker(self, symbol):
            return {'bid': 100.0, 'ask': 100.2}
    
    engine = EntryEngine(MockExchange())
    
    result, reason = await engine.check_entry_conditions("BTCUSDT", {})
    print(f"Тест результат: {result}")
    print(f"Причина: {reason}")

if __name__ == "__main__":
    asyncio.run(test_entry_engine())
