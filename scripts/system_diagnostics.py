"""
🔧 TRADING SYSTEM DIAGNOSTICS
Діагностика торгової системи перед запуском
"""

import asyncio
import logging
from datetime import datetime
from logging_setup import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

async def run_system_diagnostics():
    """Запуск повної діагностики системи"""
    
    logger.info("="*60)
    logger.info("[DIAGNOSTICS] Початок діагностики торгової системи")
    logger.info("="*60)
    
    # 1. Перевірка конфігурації
    logger.info("[CHECK 1/6] Перевірка конфігурації...")
    try:
        import json
        with open('config.json', 'r') as f:
            config = json.load(f)
        logger.info("[OK] Конфігурація завантажена")
        logger.info(f"  Біржа: {config.get('exchange', {}).get('name', 'НЕ ВКАЗАНО')}")
        logger.info(f"  Testnet: {config.get('exchange', {}).get('testnet', 'НЕ ВКАЗАНО')}")
    except Exception as e:
        logger.error(f"[ERROR] Конфігурація: {e}")
    
    # 2. Перевірка модулів
    logger.info("[CHECK 2/6] Перевірка модулів...")
    modules_to_check = [
        'entry_engine', 'oco_manager', 'risk_guard', 
        'hedge_manager', 'time_guard', 'market_data'
    ]
    
    for module in modules_to_check:
        try:
            __import__(module)
            logger.info(f"[OK] Модуль {module} завантажено")
        except Exception as e:
            logger.error(f"[ERROR] Модуль {module}: {e}")
    
    # 3. Перевірка торгових параметрів
    logger.info("[CHECK 3/6] Перевірка торгових параметрів...")
    try:
        from main import TradingBot
        bot = TradingBot()
        
        total_weight = sum(params.weight for params in bot.trading_params.values())
        logger.info(f"[OK] Загальна вага портфеля: {total_weight*100:.1f}%")
        
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(f"[WARNING] Вага портфеля не 100%: {total_weight*100:.1f}%")
        
        logger.info("[OK] Активи в портфелі:")
        for asset, params in bot.trading_params.items():
            size = bot.portfolio_size * params.weight
            logger.info(f"  {asset}: {params.weight*100:.1f}% (${size:.2f})")
            
            # Перевірка мінімального розміру
            if size < 10.0:
                logger.warning(f"    [WARNING] Розмір ${size:.2f} < $10 (мін. для Binance)")
                
    except Exception as e:
        logger.error(f"[ERROR] Торгові параметри: {e}")
    
    # 4. Перевірка цін (тестових)
    logger.info("[CHECK 4/6] Перевірка отримання цін...")
    try:
        bot = TradingBot()
        for asset, params in bot.trading_params.items():
            price = await bot.get_current_price(params.symbol)
            if price:
                logger.info(f"[OK] {params.symbol}: ${price}")
            else:
                logger.error(f"[ERROR] Не вдалося отримати ціну {params.symbol}")
    except Exception as e:
        logger.error(f"[ERROR] Перевірка цін: {e}")
    
    # 5. Перевірка часових вікон
    logger.info("[CHECK 5/6] Перевірка часових вікон...")
    try:
        current_time = datetime.now().strftime("%H:%M")
        logger.info(f"[OK] Поточний час: {current_time}")
        
        for asset, params in bot.trading_params.items():
            if bot.is_entry_time_valid(current_time, params):
                logger.info(f"[OK] {asset}: час входу дозволений")
            else:
                logger.info(f"[INFO] {asset}: час входу заборонений ({params.entry_time_start}-{params.entry_time_end})")
                
    except Exception as e:
        logger.error(f"[ERROR] Часові вікна: {e}")
    
    # 6. Перевірка ризик-параметрів
    logger.info("[CHECK 6/6] Перевірка ризик-параметрів...")
    try:
        max_leverage = max(params.max_leverage for params in bot.trading_params.values())
        avg_leverage = sum(params.max_leverage for params in bot.trading_params.values()) / len(bot.trading_params)
        
        logger.info(f"[OK] Максимальне плече: {max_leverage}x")
        logger.info(f"[OK] Середнє плече: {avg_leverage:.1f}x")
        
        if max_leverage > 5.0:
            logger.warning(f"[WARNING] Високе плече: {max_leverage}x")
            
        logger.info(f"[OK] Хедж коефіцієнт: β={bot.hedge_config['beta']}")
        
    except Exception as e:
        logger.error(f"[ERROR] Ризик-параметри: {e}")
    
    logger.info("="*60)
    logger.info("[DIAGNOSTICS] Діагностика завершена")
    logger.info("="*60)

def run_quick_test():
    """Швидкий тест основних функцій"""
    logger.info("[QUICK_TEST] Запуск швидкого тесту...")
    
    try:
        # Тест логування
        logger.info("[TEST] Логування працює")
        logger.warning("[TEST] Попередження працює") 
        logger.error("[TEST] Помилки працюють")
        
        # Тест імпортів
        from main import TradingBot, TradingParams
        logger.info("[TEST] Основні класи імпортуються")
        
        # Тест створення бота
        bot = TradingBot()
        logger.info("[TEST] TradingBot створюється")
        
        # Тест базових методів
        current_time = datetime.now().strftime("%H:%M")
        params = list(bot.trading_params.values())[0]
        is_valid = bot.is_entry_time_valid(current_time, params)
        logger.info(f"[TEST] Перевірка часу: {is_valid}")
        
        logger.info("[QUICK_TEST] Всі тести пройшли успішно!")
        return True
        
    except Exception as e:
        logger.error(f"[QUICK_TEST] Тест провалився: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Запуск діагностики торгової системи...")
    
    # Швидкий тест
    if run_quick_test():
        print("✅ Швидкий тест пройшов")
        
        # Повна діагностика
        print("🔍 Запуск повної діагностики...")
        asyncio.run(run_system_diagnostics())
        print("✅ Діагностика завершена")
    else:
        print("❌ Швидкий тест провалився - перевірте помилки в логах")
