# trading_bot/notifications.py
# Модуль для надсилання сповіщень у Telegram.

import logging
import asyncio
import telegram
from telegram.constants import ParseMode
import httpx

class TelegramNotifier:
    """
    Клас для надсилання повідомлень у Telegram.
    """
    def __init__(self, token: str, chat_id: str):
        self.logger = logging.getLogger(__name__)
        if not token or not chat_id:
            self.logger.warning("Токен або ID чату для Telegram не надано. Сповіщення вимкнено.")
            self.bot: telegram.Bot | None = None
            self.chat_id: str | None = None
            return
        
        try:
            # Створюємо бота з підвищеним pool-лімітом через request
            from telegram.request import HTTPXRequest
            request = HTTPXRequest(
                connection_pool_size=20,
                pool_timeout=30.0,
                read_timeout=10.0,
                write_timeout=10.0
            )
            self.bot = telegram.Bot(token=token, request=request)
            self.chat_id = chat_id
            self.logger.info("Telegram Notifier успішно ініціалізовано з підвищеним pool-лімітом.")
        except Exception as e:
            self.logger.error(f"Помилка ініціалізації Telegram Notifier: {e}")
            self.bot = None
            self.chat_id = None

    def _send_async_message(self, message: str):
        """Асинхронний хелпер для надсилання повідомлення."""
        if not self.bot or not self.chat_id:
            return
            
        async def main():
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        # Використовуємо asyncio.run() для безпечного запуску async-функції
        # з синхронного коду. Це надійніше, ніж ручне управління циклом.
        try:
            asyncio.run(main())
        except Exception as e:
            # Помилка "Event loop is closed" може виникати при частих викликах з синхронного коду.
            # Це відома проблема, яку можна безпечно ігнорувати, перевіряючи текст помилки.
            if "Event loop is closed" not in str(e):
                self.logger.error(f"Не вдалося надіслати повідомлення в Telegram: {e}")
    def send_message(self, text: str, level: str = "info", delay: float = 0.5):
        """
        Надсилає повідомлення у вказаний чат.
        
        :param text: Текст повідомлення.
        :param level: Рівень важливості ('info', 'warning', 'critical').
        """
        if not self.bot:
            return

        icons = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "critical": "🔥",
            "trade": "📈"
        }
        icon = icons.get(level, "ℹ️")

        # Екрануємо символи для MARKDOWN_V2
        escaped_text = telegram.helpers.escape_markdown(text, version=2)
        message = f"*{icon} {level.upper()}*\n\n{escaped_text}"

        import time
        time.sleep(delay)  # Throttling: затримка між повідомленнями
        self._send_async_message(message)
