# main.py
# Головний файл для запуску торгового бота.
"""Головний файл для запуску торгового бота."""

import os
import logging
from dotenv import load_dotenv

# --- Імпортуємо реальні модулі нашого проєкту ---
from trading_bot.logger_config import setup_logger
from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.plan_parser import PlanParser
from trading_bot.engine import Engine
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal  # <-- Імпортуємо Journal


def main():
    """
    Головна функція, що налаштовує та запускає бота.
    """
    # 1. Налаштування логера
    setup_logger()

    # 2. Завантаження конфігурації з .env файлу
    load_dotenv()
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_SECRET")  # Виправлено назву змінної
    use_testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not api_key or not api_secret:
        logging.critical(
            "Не вдалося знайти BINANCE_API_KEY або BINANCE_API_SECRET "
            "у вашому .env файлі."
        )
        return

    logging.info("API ключі успішно завантажено.")

    # 3. Визначення шляху до файлу з торговим планом
    plan_file_path = "data/trading_plan.json"
    if not os.path.exists(plan_file_path):
        logging.critical(
            "Файл плану не знайдено за шляхом: %s",
            plan_file_path
        )
        os.makedirs(os.path.dirname(plan_file_path), exist_ok=True)
        with open(plan_file_path, 'w', encoding='utf-8') as f:
            f.write('{}')
        logging.warning(
            "Створено порожній %s. Будь ласка, заповніть його.",
            plan_file_path
        )
        return

    # 4. Ініціалізація основних компонентів
    try:
        # Явно перетворюємо в рядки, щоб уникнути None
        notifier = TelegramNotifier(
            token=str(tg_token) if tg_token else "",
            chat_id=str(tg_chat_id) if tg_chat_id else ""
        )
        journal = TradingJournal()
        exchange_connector = BinanceFuturesConnector(
            api_key=api_key, api_secret=api_secret, testnet=use_testnet
        )
        plan_parser = PlanParser(plan_path=plan_file_path)
        engine = Engine(
            plan_parser=plan_parser,
            exchange_connector=exchange_connector,
            notifier=notifier,
            journal=journal
        )
    except (ValueError, TypeError) as e:
        logging.critical(
            "Помилка ініціалізації компонентів: %s", e, exc_info=True
        )
        notifier = None  # Визначаємо змінну для уникнення помилки
        return

    # 5. Запуск бота
    engine.run()


if __name__ == "__main__":
    main()
