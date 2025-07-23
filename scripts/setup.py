# Скрипт для запуску торгового бота
import sys
import os
import subprocess
import logging

def check_python_version():
    """Перевірка версії Python"""
    if sys.version_info < (3, 8):
        print("❌ Потрібен Python 3.8 або новіший")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")

def install_dependencies():
    """Встановлення залежностей"""
    print("📦 Встановлення залежностей...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Залежності встановлено")
    except subprocess.CalledProcessError:
        print("❌ Помилка встановлення залежностей")
        sys.exit(1)

def create_env_file():
    """Створення .env файлу з прикладом"""
    env_content = """# Налаштування торгового бота
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=True

# Telegram бот (опціонально)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Email (опціонально) 
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_PASSWORD=your_app_password

# Ризик-менеджмент
MAX_PORTFOLIO_RISK=2.5
EMERGENCY_STOP_LOSS=-10.0
"""
    
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✅ Створено .env файл - не забудьте заповнити API ключі!")

def main():
    """Головна функція запуску"""
    print("🤖 Автоматична торгова система v2.0")
    print("=" * 50)
    
    # Перевірки
    check_python_version()
    install_dependencies()
    create_env_file()
    
    print("\n🚀 Готово до запуску!")
    print("\n📋 Наступні кроки:")
    print("1. Відредагуйте .env файл з вашими API ключами")
    print("2. Перевірте config.json налаштування") 
    print("3. Запустіть: python main.py")
    print("\n⚠️  УВАГА: Спочатку тестуйте на testnet!")

if __name__ == "__main__":
    main()
