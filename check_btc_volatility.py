#!/usr/bin/env python3
"""
Тест функції відстеження 5-хвилинної волатільності BTC
"""
import asyncio
import sys
sys.path.append('.')

from market_data_collector import MarketDataCollector

async def test_btc_5m_volatility():
    """Тестуємо розрахунок 5m волатільності BTC"""
    
    print("🔍 ТЕСТ ВОЛАТІЛЬНОСТІ BTC (5m)")
    print("="*50)
    
    collector = MarketDataCollector()
    
    try:
        # Ініціалізуємо клієнт
        await collector.initialize()
        
        # Тест різних інтервалів
        intervals = ['5m', '15m', '1h']
        
        for interval in intervals:
            volatility = await collector.calculate_volatility(
                symbol='BTCUSDT', 
                period=20, 
                interval=interval
            )
            
            volatility_pct = volatility * 100  # Конвертуємо в відсотки
            
            print(f"📊 {interval:>3} волатільність: {volatility_pct:.2f}%")
            
            # Перевіряємо тригер 3%
            if volatility_pct > 3.0:
                print(f"🚨 ТРИГЕР! Волатільність {volatility_pct:.2f}% > 3%")
                print("🔔 Потрібно скасувати всі ордери!")
            else:
                print(f"✅ Волатільність {volatility_pct:.2f}% в нормі")
            
            print("-" * 30)
        
        # Додатковий тест для кількох періодів
        print("\n📈 ТЕСТ РІЗНИХ ПЕРІОДІВ (5m):")
        periods = [10, 20, 50]
        
        for period in periods:
            volatility = await collector.calculate_volatility(
                symbol='BTCUSDT', 
                period=period, 
                interval='5m'
            )
            
            volatility_pct = volatility * 100
            print(f"   {period:>2} періодів: {volatility_pct:.2f}%")
            
    except Exception as e:
        print(f"❌ Помилка: {e}")
    
    finally:
        await collector.close()

if __name__ == "__main__":
    asyncio.run(test_btc_5m_volatility())
