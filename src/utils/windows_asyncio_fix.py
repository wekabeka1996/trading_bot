"""
🔧 WINDOWS ASYNCIO FIX
Виправлення проблем з asyncio на Windows для торгової системи
"""

import asyncio
import sys
import logging

logger = logging.getLogger(__name__)

def fix_windows_asyncio():
    """Виправлення проблем з SelectorEventLoop на Windows"""
    
    if sys.platform == "win32":
        try:
            # Для Windows використовуємо WindowsProactorEventLoopPolicy
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            logger.info("[ASYNCIO_FIX] Windows ProactorEventLoop активовано")
            
            # Альтернативно можна використовувати SelectorEventLoop
            # loop = asyncio.SelectorEventLoop()
            # asyncio.set_event_loop(loop)
            
        except Exception as e:
            logger.warning(f"[ASYNCIO_FIX] Не вдалося змінити event loop policy: {e}")
    
    return True

def get_windows_compatible_loop():
    """Отримати Windows-сумісний event loop"""
    
    if sys.platform == "win32":
        try:
            # Створюємо новий ProactorEventLoop
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
            logger.info("[ASYNCIO_FIX] Новий ProactorEventLoop створено")
            return loop
        except Exception as e:
            logger.warning(f"[ASYNCIO_FIX] Fallback до стандартного loop: {e}")
            return asyncio.get_event_loop()
    else:
        return asyncio.get_event_loop()

if __name__ == "__main__":
    fix_windows_asyncio()
    print("✅ Windows asyncio налаштування виправлено")
