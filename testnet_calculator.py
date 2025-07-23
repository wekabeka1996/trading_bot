"""
💰 ТЕСТНЕТ PORTFOLIO CALCULATOR
Розрахунок розмірів позицій для тестнету
"""

from main import TradingBot
from logging_setup import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

def calculate_testnet_positions():
    """Розрахунок позицій для тестнету"""
    
    bot = TradingBot()
    
    print("="*60)
    print("💰 ТЕСТНЕТ - РОЗРАХУНОК ПОЗИЦІЙ")
    print("="*60)
    
    print(f"Загальний розмір портфеля: ${bot.portfolio_size}")
    print()
    print("Розподіл по активам:")
    print("-" * 50)
    
    total_value = 0
    
    for asset, params in bot.trading_params.items():
        position_size = bot.portfolio_size * params.weight
        total_value += position_size
        
        print(f"{asset:8} | {params.weight*100:5.1f}% | ${position_size:7.2f} | {params.symbol}")
        
        # Перевірка мінімальних лімітів
        if position_size < 10:
            print(f"         ⚠️  УВАГА: ${position_size:.2f} < $10 (мін. Binance)")
        elif position_size < 50:
            print(f"         ⚠️  Низько: ${position_size:.2f} < $50 (рекомендовано)")
        else:
            print(f"         ✅  ОК: ${position_size:.2f} ≥ $50")
    
    print("-" * 50)
    print(f"ВСЬОГО:     | 100.0% | ${total_value:7.2f}")
    print()
    
    # Перевірка збалансованості
    if abs(total_value - bot.portfolio_size) > 0.01:
        print("⚠️  УВАГА: Сума позицій не рівна розміру портфеля!")
    else:
        print("✅ Портфель збалансований")
    
    print()
    print("Мінімальні вимоги Binance:")
    print("- Spot: ~$10-15 USDT")
    print("- Futures: ~$5-10 USDT")
    print("- Рекомендовано для тестування: ≥$50")
    print()
    
    return bot.trading_params

if __name__ == "__main__":
    calculate_testnet_positions()
