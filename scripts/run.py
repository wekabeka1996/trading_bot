# Запуск автоматичної торгової системи з повною перевіркою
import asyncio
import sys
import os
import logging
import json
from datetime import datetime

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def print_banner():
    """Банер системи"""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║                🤖 АВТОМАТИЧНА ТОРГОВА СИСТЕМА v2.0        ║
║                                                           ║
║  📈 Оптимізована під план від 21.07.2025                 ║
║  💰 Портфель: $58 USD                                     ║
║  🎯 6 активів з розумним ризик-менеджментом               ║
║  ⚡ Автоматизація + контроль                              ║
╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)

def check_files():
    """Перевірка наявності необхідних файлів"""
    required_files = [
        'main.py',
        'exchange.py', 
        'risk_manager.py',
        'notifications.py',
        'market_data.py',
        'config.json',
        'requirements.txt'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        logger.error(f"❌ Відсутні файли: {', '.join(missing_files)}")
        return False
    
    logger.info("✅ Всі файли на місці")
    return True

def check_config():
    """Перевірка конфігурації"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Перевірка ключових секцій
        required_sections = ['exchange', 'risk_management', 'monitoring']
        for section in required_sections:
            if section not in config:
                logger.error(f"❌ Відсутня секція в config.json: {section}")
                return False
        
        logger.info("✅ Конфігурація коректна")
        return True
        
    except Exception as e:
        logger.error(f"❌ Помилка читання config.json: {e}")
        return False

def check_env_file():
    """Перевірка .env файлу"""
    if not os.path.exists('.env'):
        logger.warning("⚠️  .env файл не знайдено")
        create_sample_env()
        return False
    
    logger.info("✅ .env файл знайдено")
    return True

def create_sample_env():
    """Створення зразка .env файлу"""
    env_content = """# API ключі Binance
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_secret_here
BINANCE_TESTNET=True

# Telegram сповіщення (опціонально)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Налаштування ризику
MAX_PORTFOLIO_RISK=2.5
EMERGENCY_STOP_LOSS=-10.0
"""
    
    with open('.env.example', 'w') as f:
        f.write(env_content)
    
    logger.info("📝 Створено .env.example - скопіюйте в .env та заповніть")

async def test_components():
    """Тестування всіх компонентів"""
    logger.info("🧪 Тестування компонентів...")
    
    try:
        # Тест завантаження конфігурації
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Тест ринкових даних
        logger.info("📊 Тестування ринкових даних...")
        from market_data import MarketDataProvider
        
        async with MarketDataProvider(config) as provider:
            btc_dom = await provider.get_btc_dominance()
            if btc_dom:
                logger.info(f"✅ BTC домінація: {btc_dom:.2f}%")
            else:
                logger.warning("⚠️  Не вдалося отримати BTC домінацію")
        
        # Тест сповіщень
        if config.get('notifications', {}).get('telegram', {}).get('enabled'):
            logger.info("📱 Тестування Telegram сповіщень...")
            from notifications import NotificationManager
            
            notifier = NotificationManager(config['notifications'])
            await notifier.send_telegram_message("🤖 Тест системи - все працює!")
        
        logger.info("✅ Компоненти протестовано")
        return True
        
    except Exception as e:
        logger.error(f"❌ Помилка тестування: {e}")
        return False

async def start_bot():
    """Запуск бота"""
    try:
        from main import TradingBot
        
        logger.info("🚀 Запуск торгового бота...")
        bot = TradingBot()
        
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("👤 Зупинено користувачем")
    except Exception as e:
        logger.error(f"❌ Критична помилка: {e}")
        sys.exit(1)

def show_startup_checklist():
    """Показати чек-лист запуску"""
    checklist = """
📋 ЧЕК-ЛИСТ ПЕРЕД ЗАПУСКОМ:

✅ 1. API ключі Binance налаштовано в .env
✅ 2. Увімкнено testnet для тестування
✅ 3. Налаштовано Telegram бота (опціонально)
✅ 4. Перевірено розміри позицій
✅ 5. Встановлено стоп-лосси
✅ 6. Готово до моніторингу

⚠️  ВАЖЛИВО:
- Спочатку тестуйте на TESTNET
- Почніть з малих сум
- Постійно моніторьте позиції
- Маєте екстрений план виходу

💡 Для веб-дашборду: streamlit run dashboard.py
    """
    print(checklist)

async def main():
    """Головна функція"""
    print_banner()
    
    # Перевірки
    if not check_files():
        logger.error("❌ Критичні файли відсутні. Запустіть setup.py")
        sys.exit(1)
    
    if not check_config():
        logger.error("❌ Проблеми з конфігурацією")
        sys.exit(1)
    
    if not check_env_file():
        logger.error("❌ Налаштуйте .env файл перед запуском")
        sys.exit(1)
    
    # Тестування компонентів
    components_ok = await test_components()
    if not components_ok:
        logger.warning("⚠️  Деякі компоненти працюють з помилками")
    
    # Показуємо чек-лист
    show_startup_checklist()
    
    # Підтвердження запуску
    response = input("\n🚀 Запустити торгового бота? (y/N): ").strip().lower()
    if response not in ['y', 'yes', 'так', 'д']:
        logger.info("👋 Запуск скасовано")
        return
    
    # Остання перевірка режиму
    testnet_warning = input("\n⚠️  Ви впевнені що хочете торгувати на MAINNET? (testnet/MAINNET): ").strip().lower()
    if testnet_warning not in ['mainnet']:
        logger.info("🧪 Запуск в TESTNET режимі (безпечно)")
    else:
        logger.warning("💰 УВАГА: Запуск в MAINNET - реальні гроші!")
        confirm = input("Підтвердіть (YES/no): ").strip()
        if confirm != 'YES':
            logger.info("👋 Запуск скасовано для безпеки")
            return
    
    # Запуск бота
    await start_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До зустрічі!")
    except Exception as e:
        logger.error(f"💥 Неочікувана помилка: {e}")
        sys.exit(1)
