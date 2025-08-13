# trading_bot/logger_config.py
# Налаштовує централізований логер для всього проєкту.

import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading_bot.telegram_bot import TradingTelegramBot


class TelegramLogHandler(logging.Handler):
    """
    Обробник логів, що надсилає повідомлення в Telegram.
    """
    def __init__(self, telegram_bot: "TradingTelegramBot"):
        super().__init__()
        self.telegram_bot = telegram_bot
        self.setLevel(logging.INFO)  # Відправляємо логи рівня INFO та вище

    def emit(self, record: logging.LogRecord):
        """
        Надсилає відформатований запис логу в Telegram.
        """
        if not self.telegram_bot or not hasattr(self.telegram_bot, 'send_log_sync'):
            return
            
        log_entry = self.format(record)
        
        # Використовуємо рівень логування для іконки
        level_name = record.levelname
        
        # Надсилаємо повідомлення через синхронний метод бота
        try:
            # Перевіряємо, чи бот готовий до відправки
            if self.telegram_bot.running:
                self.telegram_bot.send_log_sync(log_entry, level=level_name)
        except Exception:
            # Уникаємо рекурсивних помилок, якщо сам бот не працює
            self.handleError(record)

def setup_logger() -> None:
    """
    Ініціалізує файл- та консоль-логери з UTF-8 та єдиним форматом.
    """
    # Створюємо папку для логів, якщо її не існує
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Очищаємо стандартні обробники, щоб уникнути дублювання
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Файловий обробник
    file_handler = logging.FileHandler(
        "logs/trading.log",
        mode="a",
        encoding="utf-8",
    )

    # Консольний обробник
    stream_handler = logging.StreamHandler(sys.stdout)

    # Безпечна зміна кодування (Python ≥ 3.10)
    if hasattr(stream_handler, "reconfigure"):  # type: ignore[attr-defined]
        try:
            stream_handler.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except TypeError:
            # Деякі реалізації reconfigure не приймають encoding
            pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[file_handler, stream_handler],
    )

    # Приглушуємо «гучні» сторонні логери
    logging.getLogger("binance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("telegram").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.Updater").setLevel(logging.CRITICAL)
    logging.getLogger("telegram.ext.Application").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.CRITICAL)

    logging.info("=" * 50)
    logging.info("Логер успішно налаштовано. Нова сесія бота.")
    logging.info("=" * 50)

    # Handler для API-помилок
    api_error_handler = logging.FileHandler(
        "logs/api_errors.log",
        mode="a",
        encoding="utf-8"
    )
    api_error_handler.setLevel(logging.ERROR)
    api_error_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    ))
    api_logger = logging.getLogger("trading_bot.exchange_connector")
    api_logger.addHandler(api_error_handler)

