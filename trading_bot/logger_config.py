# trading_bot/logger_config.py
# Налаштовує централізований логер для всього проєкту.

import logging
import os
import sys

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
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.info("=" * 50)
    logging.info("Логер успішно налаштовано. Нова сесія бота.")
    logging.info("=" * 50)

