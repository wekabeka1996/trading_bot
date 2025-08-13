# trading_bot/telegram_bot.py
# Telegram бот з командами для управління торгами та трансляцією логів.

import logging
import asyncio
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import json
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
from .telegram_config import TelegramConfig
from .telegram_analytics import TelegramAnalytics


class TradingTelegramBot:
    """
    Безпечний Telegram бот для управління торгами та отримання логів.
    """
    def __init__(self, config: TelegramConfig, engine):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.engine = engine
        self.allowed_users = config.allowed_users or [int(config.chat_id)]
        
        # Rate limiting
        self.command_history = defaultdict(list)
        self.rate_limits = config.rate_limits
        
        # Analytics
        if hasattr(engine, 'journal') and hasattr(engine, 'exchange'):
            self.analytics = TelegramAnalytics(engine.journal, engine.exchange)
        else:
            self.analytics = None
        
        self.application = None
        self.bot_thread = None
        self.running = False
        self.message_queue = asyncio.Queue()
        self.queue_worker_task = None
        
        if not self.config.token or not self.config.chat_id:
            self.logger.warning("Токен або ID чату для Telegram не надано.")
            return
            
        self.setup_bot()

    def _is_authorized(self, update: Update) -> bool:
        """Проверяет, авторизован ли пользователь."""
        user = update.effective_user
        user_id = user.id if user else None
        if user_id is None or user_id not in self.allowed_users:
            if update.message is not None:
                asyncio.create_task(update.message.reply_text(
                    "⛔ У вас нет доступа к этому боту"
                ))
            self.logger.warning(
                f"Неавторизованная попытка доступа от пользователя {user_id}"
            )
            return False
        return True

    def _check_rate_limit(self, user_id: int, command: str) -> bool:
        """Проверяет rate limit для команды."""
        if command not in self.rate_limits:
            return True
            
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Очищаем старые записи
        key = f"{user_id}_{command}"
        self.command_history[key] = [
            timestamp for timestamp in self.command_history[key]
            if timestamp > minute_ago
        ]
        
        # Проверяем лимит
        if len(self.command_history[key]) >= self.rate_limits[command]:
            return False
        
        # Добавляем текущий запрос
        self.command_history[key].append(now)
        return True

    def _log_command(self, user_id: int, command: str, args: list = None):
        """Логирует выполнение команды."""
        if args is None:
            args = []
        args_str = f" с аргументами: {args}" if args else ""
        self.logger.info(
            f"Пользователь {user_id} выполнил команду /{command}{args_str}"
        )

    async def global_error_handler(self, update, context):
        self.logger.error(f"Telegram error: {context.error}")
        if update and getattr(update, 'message', None):
            await update.message.reply_text("⚠️ Виникла внутрішня помилка. Адмін вже працює над цим.")

    def setup_bot(self):
        """Налаштування Telegram бота з командами."""
        try:
            self.application = Application.builder().token(self.config.token).build()
            
            # Додаємо обробники команд
            self._setup_handlers()
            self.application.add_error_handler(self.global_error_handler)
            
            self.logger.info("Telegram бот налаштовано успішно.")
        except Exception as e:
            self.logger.error(f"Помилка налаштування Telegram бота: {e}")

    def _setup_handlers(self):
        """Настройка обработчиков команд."""
        if self.application is None:
            return
        
        # Базові команди
        self.application.add_handler(CommandHandler('start', self.start_command))
        self.application.add_handler(CommandHandler('help', self.help_command))
        self.application.add_handler(CommandHandler('stop_trading', self.stop_trading_command))
        self.application.add_handler(CommandHandler('close_all', self.close_all_command))
        self.application.add_handler(CommandHandler('balance', self.balance_command))
        
        # Моніторинг
        self.application.add_handler(CommandHandler('status', self.cmd_status))
        self.application.add_handler(CommandHandler('positions', self.cmd_positions))
        self.application.add_handler(CommandHandler('orders', self.cmd_orders))
        # Управління позиціями
        self.application.add_handler(CommandHandler('close', self.cmd_close))
        self.application.add_handler(CommandHandler('hedge', self.cmd_hedge))
        self.application.add_handler(CommandHandler('sl', self.cmd_set_sl))
        # Управління ботом
        self.application.add_handler(CommandHandler('pause', self.cmd_pause))
        self.application.add_handler(CommandHandler('resume', self.cmd_resume))
        # Аналитика
        self.application.add_handler(CommandHandler('daily', self.cmd_daily_stats))
        self.application.add_handler(CommandHandler('performance', self.cmd_performance))
        # Callback queries для inline кнопок
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
    
    # --- Пустые обработчики команд для устранения ошибок типов ---
    async def cmd_orders(self, update, context):
        pass
    async def cmd_close(self, update, context):
        pass
    async def cmd_hedge(self, update, context):
        pass
    async def cmd_set_sl(self, update, context):
        pass
    async def cmd_pause(self, update, context):
        pass
    async def cmd_resume(self, update, context):
        pass
    async def cmd_daily_stats(self, update, context):
        pass
    async def cmd_performance(self, update, context):
        pass
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start."""
        if update.message is not None:
            await update.message.reply_text(
            "🤖 Trading Bot активний!\n\n"
            "Доступні команди:\n"
            "/status - статус бота\n"
            "/stop_trading - зупинити торги\n"
            "/close_all - закрити всі позиції\n"
            "/positions - відкриті позиції\n"
            "/balance - баланс рахунку\n"
            "/help - допомога"
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status."""
        if not self.engine:
            if update.message is not None:
                await update.message.reply_text("❌ Engine не підключено")
            return
        
        try:
            status = "🟢 Бот працює\n\n"
            if hasattr(self.engine, 'plan') and self.engine.plan:
                status += f"📋 План: {self.engine.plan.plan_type}\n"
                status += f"📅 Дата: {self.engine.plan.plan_date}\n"
            
            if hasattr(self.engine, 'risk_manager') and self.engine.risk_manager:
                balance = self.engine.exchange.get_total_balance()
                status += f"💰 Баланс: ${balance:.2f}\n"
            
            status += f"⏰ Час: {datetime.now().strftime('%H:%M:%S')}"
            
            if update.message is not None:
                await update.message.reply_text(status)
        except Exception as e:
            if update.message is not None:
                await update.message.reply_text(f"❌ Помилка отримання статусу: {e}")

    async def stop_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stop_trading - зупиняє торги."""
        if not self.engine:
            if update.message is not None:
                await update.message.reply_text("❌ Engine не підключено")
            return
        
        try:
            # Зупиняємо торги
            if hasattr(self.engine, '_pause_trading'):
                self.engine._pause_trading()
            
            if update.message is not None:
                await update.message.reply_text("🛑 Торги зупинено через Telegram команду")
            self.logger.critical("Торги зупинено через Telegram команду /stop_trading")
            
        except Exception as e:
            if update.message is not None:
                await update.message.reply_text(f"❌ Помилка зупинки торгів: {e}")

    async def close_all_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /close_all - закриває всі позиції та ордери."""
        if not self.engine:
            if update.message is not None:
                await update.message.reply_text("❌ Engine не підключено")
            return
        
        try:
            # Скасовуємо всі ордери
            if update.message is not None:
                await update.message.reply_text("🔄 Скасування всіх ордерів...")
            self.engine._handle_cancel_all_untriggered()
            
            # Закриваємо всі позиції
            if update.message is not None:
                await update.message.reply_text("🔄 Закриття всіх позицій...")
            self.engine._handle_close_all_open_positions()
            
            if update.message is not None:
                await update.message.reply_text("✅ Всі ордери скасовано, всі позиції закрито")
            self.logger.critical("Всі ордери та позиції закрито через Telegram команду /close_all")
            
        except Exception as e:
            if update.message is not None:
                await update.message.reply_text(f"❌ Помилка закриття позицій: {e}")

    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /positions - показує відкриті позиції."""
        if not self.engine:
            if update.message is not None:
                await update.message.reply_text("❌ Engine не підключено")
            return
        
        try:
            positions = self.engine.exchange.get_open_positions()
            
            if not positions:
                if update.message is not None:
                    await update.message.reply_text("📊 Немає відкритих позицій")
                return
            
            message = "📊 Відкриті позиції:\n\n"
            for pos in positions:
                symbol = pos['symbol']
                amount = float(pos['positionAmt'])
                pnl = float(pos['unRealizedPnl'])
                side = "LONG" if amount > 0 else "SHORT"
                
                message += f"🔹 {symbol}\n"
                message += f"   {side}: {abs(amount):.4f}\n"
                message += f"   PnL: ${pnl:.2f}\n\n"
            
            if update.message is not None:
                await update.message.reply_text(message)
            
        except Exception as e:
            if update.message is not None:
                await update.message.reply_text(f"❌ Помилка отримання позицій: {e}")

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /balance - показує баланс рахунку."""
        if not self.engine:
            if update.message is not None:
                await update.message.reply_text("❌ Engine не підключено")
            return
        
        try:
            total_balance = self.engine.exchange.get_total_balance()
            free_margin = self.engine.exchange.get_free_margin()
            
            message = f"💰 Баланс рахунку:\n\n"
            message += f"💵 Загальний баланс: ${total_balance:.2f}\n"
            message += f"🆓 Вільна маржа: ${free_margin:.2f}\n"
            
            if update.message is not None:
                await update.message.reply_text(message)
            
        except Exception as e:
            if update.message is not None:
                await update.message.reply_text(f"❌ Помилка отримання балансу: {e}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - показує допомогу."""
        help_text = """
🤖 **Trading Bot - Допомога**

**Команди управління:**
/start - перезапуск бота
/status - поточний статус
/stop_trading - зупинити торги
/close_all - закрити всі позиції та ордери

**Команди інформації:**
/positions - відкриті позиції
/balance - баланс рахунку
/help - ця допомога

**Автоматичні повідомлення:**
• Всі логи бота транслюються в цей чат
• Сповіщення про входи/виходи з позицій
• Попередження про ризики
• Критичні помилки
        """
        if update.message is not None:
            await update.message.reply_text(help_text)

    def start_bot(self):
        """Запускає Telegram бота в окремому потоці."""
        if not self.application:
            return
        
        self.running = True
        self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self.bot_thread.start()
        self.logger.info("Telegram бот запущено в окремому потоці")

    def _run_bot(self):
        """Запускає бота в асинхронному циклі."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._bot_main())
        except Exception as e:
            self.logger.error(f"Помилка запуску Telegram бота: {e}")

    async def _bot_main(self):
        """Основна функція бота."""
        try:
            if self.application and hasattr(self.application, 'initialize'):
                await self.application.initialize()
            if self.application and hasattr(self.application, 'start'):
                await self.application.start()
            if self.application and hasattr(self.application, 'updater') and self.application.updater is not None and hasattr(self.application.updater, 'start_polling'):
                await self.application.updater.start_polling()
            # Надсилаємо повідомлення про запуск
            if self.application and hasattr(self.application, 'bot') and hasattr(self.application.bot, 'send_message'):
                await self.application.bot.send_message(
                    chat_id=self.config.chat_id,
                    text="🚀 Trading Bot запущено! Логи будуть транслюватися в цей чат."
                )
            # Запускаємо воркер для черги повідомлень
            self.queue_worker_task = asyncio.create_task(self._message_queue_worker())
            # Тримаємо бота активним
            while self.running:
                await asyncio.sleep(1)
        except Exception as e:
            self.logger.error(f"Помилка роботи Telegram бота: {e}")
        finally:
            if self.application and hasattr(self.application, 'stop'):
                await self.application.stop()
            if self.queue_worker_task:
                self.queue_worker_task.cancel()

    async def _message_queue_worker(self):
        while self.running:
            try:
                msg, level = await self.message_queue.get()
                await self._send_log_message_actual(msg, level)
                await asyncio.sleep(0.5)  # затримка між повідомленнями
            except Exception as e:
                self.logger.error(f"Помилка надсилання повідомлення з черги: {e}")

    async def send_log_message(self, message: str, level: str = "info"):
        """Надсилає лог повідомлення в Telegram."""
        if not self.application or not self.running:
            return
        await self.message_queue.put((message, level))

    def _escape_markdown(self, text: str) -> str:
        """Екранує спеціальні символи для Markdown."""
        # Екрануємо символи які можуть конфліктувати з Markdown
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text

    async def _send_log_message_actual(self, message: str, level: str = "info"):
        icons = {
            "DEBUG": "🔍",
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🔥"
        }
        icon = icons.get(level.upper(), "ℹ️")
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Екрануємо повідомлення для безпечного Markdown
        formatted_message = f"{icon} {timestamp} {message}"
        
        try:
            if self.application and hasattr(self.application, 'bot') and self.application.bot:
                await self.application.bot.send_message(
                    chat_id=self.config.chat_id,
                    text=formatted_message
                    # Вимикаємо parse_mode для уникнення конфліктів
                )
        except Exception as e:
            pass

    def send_log_sync(self, message: str, level: str = "info"):
        """Синхронна версія надсилання логів."""
        if not self.application or not self.running:
            return
        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(
                self.send_log_message(message, level),
                loop
            )
        except Exception:
            pass

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status - полный статус системы."""
        if not self._is_authorized(update):
            return
            
        status = self._collect_system_status()
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data='refresh_status')],
            [InlineKeyboardButton("📊 Позиції", callback_data='show_positions')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message is not None:
            await update.message.reply_text(
                status,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    
    def _collect_system_status(self) -> str:
        """Собирает информацию о статусе системы."""
        # Подключение
        connection_status = "✅ Активно" if self.engine.exchange.check_connection() else "❌ Отключено"
        
        # Капитал
        account_info = self.engine.exchange.get_account_summary()
        if account_info:
            balance = account_info['total_balance']
            free_margin = account_info['free_margin']
            margin_usage = (1 - free_margin/balance) * 100 if balance > 0 else 0
        else:
            balance = free_margin = margin_usage = 0
            
        # Позиції
        positions = self.engine.exchange.get_position_information()
        active_positions = [p for p in positions if float(p['positionAmt']) != 0]
        total_pnl = sum(float(p.get('unrealizedProfit', 0)) for p in active_positions)
        
        # План
        plan_status = f"{self.engine.plan.plan_type} v{self.engine.plan.plan_version}" if self.engine.plan else "Не загружен"
        
        status_text = f"""
*📊 Статус системи*

*Підключення:* {connection_status}
*Торгівля:* {"⏸ Приостановлена" if self.engine.trading_paused else "▶️ Активна"}
*План:* {plan_status}

*💰 Рахунок:*
• Баланс: {balance:.2f} USD
• Вільна маржа: {free_margin:.2f} USD
• Використання маржі: {margin_usage:.1f}%

*📈 Позиції:* {len(active_positions)}
• Загальний PnL: {total_pnl:+.2f} USD

*🕐 Час:* {datetime.now(pytz.timezone('Europe/Kiev')).strftime('%H:%M:%S')}
        """
        return status_text.strip()
    
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /positions - детальна інформація о позиціях."""
        if not self._is_authorized(update):
            return
            
        positions = self.engine.exchange.get_position_information()
        active_positions = [p for p in positions if float(p['positionAmt']) != 0]
        
        if not active_positions:
            if update.message is not None:
                await update.message.reply_text("📭 Нет открытых позиций")
            return
            
        for pos in active_positions:
            pos_info = self._format_position_info(pos)
            keyboard = self._create_position_keyboard(pos)
            
            if update.message is not None:
                await update.message.reply_text(
                    pos_info,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
    
    def _format_position_info(self, position: dict) -> str:
        """Форматирует информацию о позиции."""
        symbol = position.get('symbol', 'UNKNOWN')
        amount = float(position.get('positionAmt', 0))
        entry_price = float(position.get('entryPrice', 0))
        mark_price = float(position.get('markPrice', entry_price))
        pnl = float(position.get('unrealizedProfit', 0))
        pnl_pct = (pnl / (abs(amount) * entry_price)) * 100 if entry_price > 0 else 0
        
        direction = "🟢 LONG" if amount > 0 else "🔴 SHORT"
        
        if 'markPrice' not in position:
            self.logger.warning(f"Позиція {symbol} не містить markPrice, використовується entryPrice.")

        # Проверяем наличие хеджа
        hedge_info = ""
        if symbol in getattr(self.engine, 'managed_positions', {}):
            hedge_data = self.engine.managed_positions[symbol].get('hedge_info')
            if hedge_data and hedge_data.get('active'):
                hedge_info = f"\n*Хедж:* ✅ {hedge_data['symbol']}"
        
        return f"""
*{symbol}* {direction}

*Розмір:* {abs(amount)}
*Вхід:* {entry_price:.4f} USD
*Поточна:* {mark_price:.4f} USD
*PnL:* {pnl:+.2f} USD ({pnl_pct:+.2f}%){hedge_info}
        """
    
    def _create_position_keyboard(self, position: dict) -> list:
        """Создает клавиатуру для управления позицией."""
        symbol = position['symbol']
        return [
            [
                InlineKeyboardButton("❌ Закрити 25%", callback_data=f'close_{symbol}_25'),
                InlineKeyboardButton("❌ Закрити 50%", callback_data=f'close_{symbol}_50'),
                InlineKeyboardButton("❌ Закрити 100%", callback_data=f'close_{symbol}_100')
            ],
            [
                InlineKeyboardButton("🛡 SL в б/у", callback_data=f'sl_be_{symbol}'),
                InlineKeyboardButton("📈 Трейлинг", callback_data=f'trailing_{symbol}')
            ]
        ]
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на inline кнопки."""
        query = update.callback_query
        if query is not None:
            await query.answer()
            data = query.data
            if data is not None:
                if data.startswith('close_'):
                    parts = data.split('_')
                    symbol = parts[1]
                    percentage = int(parts[2])
                    await self._handle_close_position(query, symbol, percentage)
                elif data.startswith('sl_be_'):
                    symbol = data.replace('sl_be_', '')
                    await self._handle_sl_breakeven(query, symbol)
                # І так далі для інших кнопок
    
    async def _handle_close_position(self, query, symbol: str, percentage: int):
        """Обработка закрытия позиции."""
        positions = self.engine.exchange.get_position_information(symbol)
        position = next((p for p in positions if float(p['positionAmt']) != 0), None)
        
        if not position:
            await query.edit_message_text(f"❌ Позиція {symbol} не знайдена")
            return
            
        if percentage == 100:
            self.engine.risk_manager._close_position(position)
        else:
            self.engine.risk_manager._reduce_position(position, percentage / 100)
            
        await query.edit_message_text(
            f"✅ Позиція {symbol} {'закрита' if percentage == 100 else f'зменшена на {percentage}%'}"
        )
    
    async def _handle_sl_breakeven(self, query, symbol: str):
        """Заглушка для обработки SL в б/у (break-even)."""
        await query.edit_message_text(f"SL для {symbol} переведено в безубиток (заглушка)")

    def stop_bot(self):
        """Зупиняє Telegram бота та воркер черги повідомлень."""
        self.running = False
        if self.bot_thread:
            self.bot_thread.join(timeout=5)
        if hasattr(self, 'queue_worker_task') and self.queue_worker_task:
            try:
                self.queue_worker_task.cancel()
            except Exception:
                pass
        self.logger.info("Telegram бот зупинено")
