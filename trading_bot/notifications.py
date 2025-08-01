# trading_bot/notifications.py
# Модуль для надсилання сповіщень у Telegram.

import logging
import asyncio
import telegram
from telegram.constants import ParseMode

class TelegramNotifier:
    """
    Клас для надсилання повідомлень у Telegram.
    """
    def __init__(self, token: str, chat_id: str):
        self.logger = logging.getLogger(__name__)
        if not token or not chat_id:
            self.logger.warning("Токен або ID чату для Telegram не надано. Сповіщення вимкнено.")
            self.bot = None
            self.chat_id = None
            return
        
        try:
            self.bot = telegram.Bot(token=token)
            self.chat_id = chat_id
            self.logger.info("Telegram Notifier успішно ініціалізовано.")
        except Exception as e:
            self.logger.error(f"Помилка ініціалізації Telegram Notifier: {e}")
            self.bot = None
            self.chat_id = None

    def _send_async_message(self, message: str):
        """Асинхронний хелпер для надсилання повідомлення."""
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
    def send_message(self, text: str, level: str = "info"):
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

        self._send_async_message(message)
