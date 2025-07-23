"""
🔧 WINDOWS UNICODE LOGGING FIX
Налаштування логування для коректної роботи з emoji та кирилицею в Windows
"""

import logging
import sys
import os

def setup_logging():
    """Налаштування логування з підтримкою UTF-8 для Windows"""
    
    # Формат логів
    fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    
    # Очищаємо існуючі handlers
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    
    root.setLevel(logging.INFO)

    # File handler з UTF-8
    try:
        file_handler = logging.FileHandler("trading_bot.log", encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create file handler: {e}")

    # Console handler з UTF-8 та fallback для Windows
    try:
        # Спробуємо встановити UTF-8 для Windows консолі
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            except Exception:
                pass  # Не критично якщо не вдалося
        
        # Створюємо console handler з UTF-8 та errors='replace'
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.encoding = 'utf-8'
        console_handler.setFormatter(fmt)
        root.addHandler(console_handler)
        
    except Exception as e:
        # Fallback - простий StreamHandler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)
        root.addHandler(console_handler)
        print(f"Warning: Using fallback console handler: {e}")

    return root

def get_logger(name: str = __name__):
    """Отримати logger з правильним налаштуванням"""
    return logging.getLogger(name)

if __name__ == "__main__":
    setup_logging()
    logger = get_logger("test")
    logger.info("[TEST] Тестування кирилиці та ASCII тегів")
    logger.warning("[WARNING] Перевірка попереджень")
    logger.error("[ERROR] Перевірка помилок")
    print("Логування налаштовано успішно!")
