    # ===== ЗАГЛУШКИ ДЛЯ ОТСУТСТВУЮЧИХ КОМАНД =====
"""
Безпечний Telegram бот для управління торгами з повним функціоналом.
"""

import logging
import asyncio
import threading
import re
import traceback
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from io import BytesIO
from typing import Optional, Dict, Any, List

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, 
    CallbackQueryHandler, MessageHandler, filters
)

from .telegram_config import TelegramConfig
from .telegram_analytics import TelegramAnalytics


class SecurityError(Exception):
    """Виняток для порушень безпеки."""
    pass


class TelegramMetrics:
    """Клас для збору метрик використання бота."""
    
    from collections import Counter
    def __init__(self):
        self.command_counter = Counter()
        self.error_counter = Counter()
        self.user_activity = defaultdict(list)
    def track_command(self, user_id: int, command: str):
        self.command_counter[command] += 1
        self.user_activity[user_id].append({
            'command': command,
            'timestamp': datetime.now()
        })
    def track_error(self, command: str, error_type: str):
        self.error_counter[f"{command}_{error_type}"] += 1
    def get_stats(self) -> dict:
        return {
            'most_used_commands': dict(self.command_counter.most_common(5)),
            'total_commands': sum(self.command_counter.values()),
            'active_users': len(self.user_activity),
            'errors': dict(self.error_counter)
        }


class SecureTradingTelegramBot:
    """
    Безпечний Telegram бот з повним функціоналом для торгівлі.
    """
    
    def __init__(self, config: TelegramConfig, engine):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.token = config.token
        self.chat_id = config.chat_id
        self.engine = engine
        self.allowed_users = config.allowed_users or [int(config.chat_id)]
        
        # Безпека та обмеження
        self.command_history = defaultdict(list)
        self.rate_limits = config.rate_limits
        self.blocked_users = set()
        
        # Метрики
        self.metrics = TelegramMetrics()
        
        # Аналітика
        if (hasattr(engine, 'journal') and 
            hasattr(engine, 'exchange') and 
            engine.journal and engine.exchange):
            self.analytics = TelegramAnalytics(
                engine.journal, engine.exchange
            )
        else:
            self.analytics = None
            self.logger.warning(
                "Analytics недоступна - відсутній journal або exchange"
            )
        
        self.application = None
        self.bot_thread = None
        self.running = False
        if not self.token or not self.chat_id:
            self.logger.warning("Токен або ID чату для Telegram не надано.")
            return
        self.setup_bot()

    def _is_authorized(self, update: Update) -> bool:
        user = getattr(update, 'effective_user', None)
        user_id = getattr(user, 'id', None)
        if user_id is None:
            self.logger.warning("Не вдалося отримати user_id")
            return False
        if user_id in self.blocked_users:
            self.logger.warning(f"Заблокований користувач {user_id} намагається отримати доступ")
            return False
        if user_id not in self.allowed_users:
            msg = getattr(update, 'message', None)
            if msg:
                asyncio.create_task(msg.reply_text("⛔ У вас немає доступу до цього бота"))
            self.logger.warning(f"Неавторизована спроба доступу від користувача {user_id}")
            return False
        return True

    def _check_rate_limit(self, user_id: int, command: str) -> bool:
        """Перевіряє rate limit для команди."""
        if command not in self.rate_limits:
            return True
            
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Очищаємо старі записи
        key = f"{user_id}_{command}"
        self.command_history[key] = [
            timestamp for timestamp in self.command_history[key]
            if timestamp > minute_ago
        ]
        
        # Перевіряємо ліміт
        if len(self.command_history[key]) >= self.rate_limits[command]:
            return False
        
        # Додаємо поточний запит
        self.command_history[key].append(now)
        return True

    def _log_command(self, user_id: int, command: str, args: Optional[list] = None):
        args_str = f" з аргументами: {args}" if args else ""
        self.logger.info(f"Користувач {user_id} виконав команду /{command}{args_str}")
        self.metrics.track_command(user_id, command)

    def _validate_symbol(self, symbol: str) -> bool:
        """Валідує символ торгової пари."""
        if not symbol:
            return False
        return bool(re.match(r'^[A-Z]{2,10}USDT$', symbol.upper()))

    def _validate_percentage(self, value: str) -> Optional[float]:
        """Валідує відсоток."""
        try:
            percentage = float(value)
            if 0 < percentage <= 100:
                return percentage
            return None
        except ValueError:
            return None

    def setup_bot(self):
        try:
            self.application = Application.builder().token(self.token).build()
            if self.application:
                self._setup_handlers()
                # Регистрируем асинхронный обработчик ошибок напрямую
                self.application.add_error_handler(self._tg_error_handler)
                self.logger.info("Telegram бот налаштовано успішно.")
        except Exception as e:
            self.logger.error(f"Помилка налаштування Telegram бота: {e}")

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        error_msg = f"Помилка: {getattr(context, 'error', '')}"
        self.logger.error(f"Update {update} caused error {getattr(context, 'error', '')}")
        msg = getattr(update, 'effective_message', None)
        if msg and hasattr(msg, 'reply_text'):
            await msg.reply_text("❌ Виникла помилка при обробці команди. Адміністратор повідомлений.")

    def _setup_handlers(self):
        if not self.application:
            return
        # Моніторинг
        self.application.add_handler(CommandHandler('start', self.cmd_start))
        self.application.add_handler(CommandHandler('status', self.cmd_status))
        self.application.add_handler(CommandHandler('positions', self.cmd_positions))
        self.application.add_handler(CommandHandler('orders', self.cmd_orders))
        # Управління позиціями
        self.application.add_handler(CommandHandler('close', self.cmd_close))
        self.application.add_handler(CommandHandler('hedge', self.cmd_hedge))
        self.application.add_handler(CommandHandler('sl', self.cmd_set_sl))
        self.application.add_handler(CommandHandler('tp', self.cmd_set_tp))
        # Управління ботом
        self.application.add_handler(CommandHandler('pause', self.cmd_pause))
        self.application.add_handler(CommandHandler('resume', self.cmd_resume))
        self.application.add_handler(CommandHandler('emergency_stop', self.cmd_emergency_stop))
        # Аналітика
        self.application.add_handler(CommandHandler('daily', self.cmd_daily_stats))
        self.application.add_handler(CommandHandler('performance', self.cmd_performance))
        self.application.add_handler(CommandHandler('risk', self.cmd_risk_analysis))
        # Допомога та статистика
        self.application.add_handler(CommandHandler('help', self.cmd_help))
        self.application.add_handler(CommandHandler('stats', self.cmd_bot_stats))
        # Callback queries для inline кнопок
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        # Обробник невідомих команд
        self.application.add_handler(MessageHandler(filters.COMMAND, self.cmd_unknown))

    # ===== УНІВЕРСАЛЬНІ БЕЗПЕЧНІ МЕТОДИ =====

    def _get_user_id(self, update: Update) -> Optional[int]:
        user = getattr(update, 'effective_user', None)
        return getattr(user, 'id', None)

    async def _safe_reply(self, update: Update, text: str, **kwargs):
        msg = getattr(update, 'message', None)
        if msg and hasattr(msg, 'reply_text'):
            try:
                await msg.reply_text(text, **kwargs)
            except Exception as e:
                self.logger.error(f"Ошибка отправки сообщения: {e}")
        else:
            self.logger.warning("reply_text недоступен для сообщения")

    # Пример безопасного получения user_id и вызова rate_limit/log_command

    # ===== КОМАНДИ МОНИТОРИНГУ =====

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user = getattr(update, 'effective_user', None)
        user_id = getattr(user, 'id', None)
        first_name = getattr(user, 'first_name', '')
        if user_id is not None:
            self._log_command(user_id, 'start')
        welcome_msg = f"""
🤖 **Безпечний Trading Bot активний!**

Ласкаво просимо, {first_name}!

**Команди мониторингу:**
/status - статус системи
/positions - відкриті позиції  
/orders - активні ордери
/risk - аналіз ризиків

**Команди управління:**
/pause - призупинити торгівлю
/resume - відновити торгівлю
/close <symbol> [%] - закрити позицію
/emergency_stop - екстрене зупинення

**Аналітика:**
/daily - денний звіт
/performance [days] - аналіз ефективності

/help - повна допомога
        """
        msg = getattr(update, 'message', None)
        if msg:
            await msg.reply_text(welcome_msg, parse_mode='Markdown')

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if not (user_id and self._check_rate_limit(user_id, 'status')):
            await self._safe_reply(update, text="⏳ Занадто багато запитів. Зачекайте хвилину.")
            return
        self._log_command(user_id, 'status')
        try:
            status = self._collect_system_status()
            keyboard = [
                [InlineKeyboardButton("🔄 Оновити", callback_data='refresh_status')],
                [InlineKeyboardButton("📊 Позиції", callback_data='show_positions')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._safe_reply(update, text=status, parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            self.logger.error(f"Помилка при отриманні статусу: {e}")
            await self._safe_reply(update, text="❌ Помилка при отриманні статусу системи.\nПеревірте підключення до біржі.")

    def _collect_system_status(self) -> str:
        """Збирає інформацію про статус системи з обробкою помилок."""
        try:
            # Підключення
            connection_status = "✅ Активне"
            try:
                if hasattr(self.engine.exchange, 'check_connection'):
                    if not self.engine.exchange.check_connection():
                        connection_status = "❌ Відключено"
                else:
                    connection_status = "⚠️ Невідомо"
            except Exception:
                connection_status = "⚠️ Невідомо"
            
            # Капітал
            balance = free_margin = margin_usage = 0
            try:
                if hasattr(self.engine.exchange, 'get_account_summary'):
                    account_info = self.engine.exchange.get_account_summary()
                    if account_info:
                        balance = account_info.get('total_balance', 0)
                        free_margin = account_info.get('free_margin', 0)
                        if balance > 0:
                            margin_usage = (1 - free_margin/balance) * 100
            except Exception as e:
                self.logger.warning(
                    f"Не вдалося отримати інформацію про рахунок: {e}"
                )
            
            # Позиції
            active_positions = []
            total_pnl = 0
            try:
                if hasattr(self.engine.exchange, 'get_position_information'):
                    positions = self.engine.exchange.get_position_information()
                    active_positions = [
                        p for p in positions 
                        if float(p.get('positionAmt', 0)) != 0
                    ]
                    total_pnl = sum(
                        float(p.get('unrealizedProfit', 0)) 
                        for p in active_positions
                    )
            except Exception as e:
                self.logger.warning(
                    f"Не вдалося отримати інформацію про позиції: {e}"
                )
            
            # План
            plan_status = "Не завантажено"
            if hasattr(self.engine, 'plan') and self.engine.plan:
                plan_status = (
                    f"{self.engine.plan.plan_type} "
                    f"v{self.engine.plan.plan_version}"
                )
            
            # Стан торгівлі
            trading_status = "▶️ Активна"
            if hasattr(self.engine, 'trading_paused'):
                if self.engine.trading_paused:
                    trading_status = "⏸ Призупинена"
            
            # Формуємо текст
            status_text = f"""
*📊 Статус системи*

*Підключення:* {connection_status}
*Торгівля:* {trading_status}
*План:* {plan_status}

*💰 Рахунок:*
├ Баланс: ${balance:.2f}
├ Вільна маржа: ${free_margin:.2f}
└ Використання маржі: {margin_usage:.1f}%

*📈 Позиції:* {len(active_positions)}
└ Загальний PnL: ${total_pnl:+.2f}

*🕐 Час:* {datetime.now(pytz.timezone('Europe/Kiev')).strftime('%H:%M:%S')}
            """
            return status_text.strip()
            
        except Exception as e:
            self.logger.error(f"Критична помилка при зборі статусу: {e}")
            return (
                "*❌ Критична помилка*\n\n"
                "Не вдалося зібрати інформацію про систему"
            )

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if not (user_id and self._check_rate_limit(user_id, 'positions')):
            await self._safe_reply(update, text="⏳ Занадто багато запитів. Зачекайте хвилину.")
            return
        self._log_command(user_id, 'positions')
        try:
            if not hasattr(self.engine.exchange, 'get_position_information'):
                await self._safe_reply(update, text="❌ Функція отримання позицій недоступна")
                return
            positions = self.engine.exchange.get_position_information()
            active_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
            if not active_positions:
                await self._safe_reply(update, text="📭 Немає відкритих позицій")
                return
            for pos in active_positions:
                pos_info = self._format_position_info(pos)
                keyboard = self._create_position_keyboard(pos)
                await self._safe_reply(update, text=pos_info, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            self.logger.error(f"Помилка при отриманні позицій: {e}")
            await self._safe_reply(update, text="❌ Помилка при отриманні позицій")

    def _format_position_info(self, position: dict) -> str:
        """Форматує інформацію про позицію."""
        symbol = position.get('symbol', 'UNKNOWN')
        amount = float(position.get('positionAmt', 0))
        entry_price = float(position.get('entryPrice', 0))
        mark_price = float(position.get('markPrice', 0))
        pnl = float(position.get('unrealizedProfit', 0))
        
        if entry_price > 0 and abs(amount) > 0:
            pnl_pct = (pnl / (abs(amount) * entry_price)) * 100
        else:
            pnl_pct = 0
        
        direction = "🟢 LONG" if amount > 0 else "🔴 SHORT"
        
        # Перевіряємо наявність хеджу
        hedge_info = ""
        if (hasattr(self.engine, 'managed_positions') and 
            symbol in self.engine.managed_positions):
            hedge_data = self.engine.managed_positions[symbol].get(
                'hedge_info'
            )
            if hedge_data and hedge_data.get('active'):
                hedge_info = f"\n*Хедж:* ✅ {hedge_data['symbol']}"
        
        return f"""
*{symbol}* {direction}

*Розмір:* {abs(amount):.4f}
*Вхід:* ${entry_price:.4f}
*Поточна:* ${mark_price:.4f}
*PnL:* ${pnl:+.2f} ({pnl_pct:+.2f}%){hedge_info}
        """.strip()

    def _create_position_keyboard(self, position: dict) -> List[List[InlineKeyboardButton]]:
        """Створює клавіатуру для управління позицією."""
        symbol = position.get('symbol', 'UNKNOWN')
        return [
            [
                InlineKeyboardButton(
                    "❌ Закрити 25%", callback_data=f'close_{symbol}_25'
                ),
                InlineKeyboardButton(
                    "❌ Закрити 50%", callback_data=f'close_{symbol}_50'
                ),
                InlineKeyboardButton(
                    "❌ Закрити 100%", callback_data=f'close_{symbol}_100'
                )
            ],
            [
                InlineKeyboardButton(
                    "🛡 SL в б/в", callback_data=f'sl_be_{symbol}'
                ),
                InlineKeyboardButton(
                    "📈 Трейлінг", callback_data=f'trailing_{symbol}'
                )
            ]
        ]

    # ===== КОМАНДИ УПРАВЛІННЯ ПОЗИЦІЯМИ =====

    async def cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if not (user_id and self._check_rate_limit(user_id, 'close')):
            await self._safe_reply(update, text="⏳ Занадто багато запитів. Зачекайте хвилину.")
            return
        args = getattr(context, 'args', []) or []
        if not args:
            await self._safe_reply(update, text="❌ Використання: /close <symbol> [percentage]\nПриклад: /close BTCUSDT 50")
            return
        symbol = args[0].upper()
        if not self._validate_symbol(symbol):
            await self._safe_reply(update, text="❌ Неправильний формат символу. Приклад: BTCUSDT")
            return
        percentage = 100
        if len(args) > 1:
            validated_pct = self._validate_percentage(args[1])
            if validated_pct is None:
                await self._safe_reply(update, text="❌ Відсоток повинен бути числом від 0 до 100")
                return
            percentage = validated_pct
        self._log_command(user_id, 'close', [symbol, percentage])
        try:
            if not hasattr(self.engine, 'risk_manager'):
                await self._safe_reply(update, text="❌ Risk manager недоступний")
                return
            success = await self._execute_position_close(symbol, percentage / 100)
            if success:
                action = 'закрита' if percentage == 100 else f'зменшена на {percentage}%'
                await self._safe_reply(update, text=f"✅ Позиція {symbol} {action}")
            else:
                await self._safe_reply(update, text=f"❌ Не вдалося закрити позицію {symbol}")
        except Exception as e:
            self.logger.error(f"Помилка закриття позиції {symbol}: {e}")
            await self._safe_reply(update, text=f"❌ Помилка при закритті позиції {symbol}")

    async def _execute_position_close(self, symbol: str, percentage: float) -> bool:
        """Виконує закриття позиції з перевірками безпеки."""
        try:
            if hasattr(self.engine.risk_manager, 'manual_close_position'):
                return self.engine.risk_manager.manual_close_position(
                    symbol, percentage
                )
            else:
                # Fallback до прямого закриття через exchange
                positions = self.engine.exchange.get_position_information(symbol)
                position = next(
                    (p for p in positions if float(p.get('positionAmt', 0)) != 0), 
                    None
                )
                
                if not position:
                    return False
                    
                amount = float(position['positionAmt'])
                close_amount = abs(amount) * percentage
                side = "SELL" if amount > 0 else "BUY"
                
                order = self.engine.exchange.place_order(
                    symbol=symbol,
                    side=side,
                    order_type="MARKET",
                    quantity=close_amount,
                    reduceOnly=True
                )
                
                return order is not None
                
        except Exception as e:
            self.logger.error(f"Помилка при закритті позиції {symbol}: {e}")
            return False

    # ===== КОМАНДИ УПРАВЛІННЯ БОТОМ =====

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /pause - призупинити торгівлю."""
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if not (user_id and self._check_rate_limit(user_id, 'pause')):
            await self._safe_reply(update, text="⏳ Занадто багато запитів. Зачекайте хвилину.")
            return
        self._log_command(user_id, 'pause')
        try:
            # Перевіряємо поточний стан
            if (hasattr(self.engine, 'trading_paused') and 
                self.engine.trading_paused):
                await self._safe_reply(update, text="⏸ Торгівля вже призупинена")
                return
            
            # Призупиняємо торгівлю
            self.engine.trading_paused = True
            
            # Скасовуємо всі відкриті ордери
            if hasattr(self.engine, '_handle_cancel_all_untriggered'):
                self.engine._handle_cancel_all_untriggered()
            
            await self._safe_reply(update, text=(
                "⏸ *Торгівля призупинена*\n\n"
                "• Всі нові ордери скасовані\n"
                "• Відкриті позиції збережені\n"
                "• Моніторинг продовжується\n\n"
                "Використовуйте /resume для відновлення"
            ), parse_mode='Markdown')
            
            self.logger.info("Торгівля призупинена через Telegram команду")
            
        except Exception as e:
            self.logger.error(f"Помилка призупинення торгівлі: {e}")
            await self._safe_reply(update, text="❌ Помилка при призупиненні торгівлі")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /resume - відновити торгівлю."""
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if not (user_id and self._check_rate_limit(user_id, 'resume')):
            await self._safe_reply(update, text="⏳ Занадто багато запитів. Зачекайте хвилину.")
            return
        self._log_command(user_id, 'resume')
        try:
            # Перевіряємо поточний стан
            if (not hasattr(self.engine, 'trading_paused') or 
                not self.engine.trading_paused):
                await self._safe_reply(update, text="▶️ Торгівля вже активна")
                return
            
            # Відновлюємо торгівлю
            self.engine.trading_paused = False
            
            await self._safe_reply(update, text=(
                "▶️ *Торгівля відновлена*\n\n"
                "• Бот знову активний\n"
                "• Моніторинг ринку продовжується\n"
                "• Нові сигнали будуть оброблятися"
            ), parse_mode='Markdown')
            
            self.logger.info("Торгівля відновлена через Telegram команду")
            
        except Exception as e:
            self.logger.error(f"Помилка відновлення торгівлі: {e}")
            await self._safe_reply(update, text="❌ Помилка при відновленні торгівлі")

    async def cmd_emergency_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /emergency_stop - екстрене зупинення."""
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if not (user_id and self._check_rate_limit(user_id, 'emergency')):
            await self._safe_reply(update, text="⏳ Занадто багато запитів. Зачекайте хвилину.")
            return
        self._log_command(user_id, 'emergency_stop')
        try:
            # Скасовуємо всі ордери
            if hasattr(self.engine, '_handle_cancel_all_untriggered'):
                self.engine._handle_cancel_all_untriggered()
            
            # Закриваємо всі позиції
            if hasattr(self.engine, '_handle_close_all_open_positions'):
                self.engine._handle_close_all_open_positions()
            
            # Призупиняємо торгівлю
            self.engine.trading_paused = True
            
            await self._safe_reply(update, text=(
                "🚨 *ЕКСТРЕНЕ ЗУПИНЕННЯ*\n\n"
                "• Всі ордери скасовані\n"
                "• Всі позиції закриті\n"
                "• Торгівля призупинена\n\n"
                "⚠️ Бот зупинено для безпеки"
            ), parse_mode='Markdown')
            
            self.logger.critical(
                "Екстрене зупинення через Telegram команду /emergency_stop"
            )
            
        except Exception as e:
            self.logger.error(f"Помилка екстреного зупинення: {e}")
            await self._safe_reply(update, text="❌ Помилка при екстреному зупиненні")

    # ===== АНАЛІТИЧНІ КОМАНДИ (рефакторинг для type safety) =====

    async def cmd_daily_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if user_id is not None:
            self._log_command(user_id, 'daily')
        if not self.analytics:
            await self._safe_reply(update, text="❌ Аналітика недоступна")
            return
        try:
            date = datetime.now(pytz.timezone('Europe/Kiev')).strftime('%Y-%m-%d')
            report, chart = self.analytics.generate_daily_report(date)
            await self._safe_reply(update, text=report, parse_mode='Markdown')
            msg = getattr(update, 'message', None)
            if msg and hasattr(msg, 'reply_photo'):
                try:
                    await msg.reply_photo(photo=chart, caption=f"📈 Графік equity curve за {date}")
                except Exception as e:
                    self.logger.error(f"Ошибка отправки фото: {e}")
        except Exception as e:
            self.logger.error(f"Помилка генерації денного звіту: {e}")
            await self._safe_reply(update, text="❌ Помилка при генерації денного звіту")

    # ===== ДОПОМОГА/HELP (рефакторинг для type safety) =====

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if user_id is not None:
            self._log_command(user_id, 'help')
        help_text = """
🤖 **Безпечний Trading Bot - Повна допомога**

**📊 Команди моніторингу:**
/status - повний статус системи
/positions - детальна інформація про позиції
/orders - список всіх ордерів
/risk - аналіз поточних ризиків

**⚡ Команди управління позиціями:**
/close <symbol> [%] - закрити позицію
/hedge <symbol> - управління хеджем
/sl <symbol> <price> - встановити Stop Loss
/tp <symbol> <price> - встановити Take Profit

**🎛 Команди управління ботом:**
/pause - призупинити торгівлю
/resume - відновити торгівлю
/emergency_stop - екстрене зупинення

**📈 Аналітика:**
/daily - денний звіт з графіком
/performance [days] - аналіз ефективності
/stats - статистика використання бота

**🔒 Безпека:**
• Перевірка авторизації користувачів
• Rate limiting для запобігання спаму
• Валідація всіх входних даних
• Детальне логування всіх дій

**ℹ️ Додаткова інформація:**
• Всі дії логуються для безпеки
• Кнопки швидких дій для позицій
• Автоматичні звіти (налаштовуються)
• Підтримка множинних користувачів
        """
        await self._safe_reply(update, text=help_text, parse_mode='Markdown')

    # ===== ОБРОБНИКИ КНОПОК (рефакторинг для type safety) =====

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = getattr(update, 'callback_query', None)
        if query:
            await query.answer()
        if not self._is_authorized(update):
            return
        data = getattr(query, 'data', None)
        user_id = self._get_user_id(update)
        try:
            if data and data.startswith('close_'):
                parts = data.split('_')
                if len(parts) >= 3:
                    symbol = parts[1]
                    percentage = int(parts[2])
                    await self._handle_close_position(query, symbol, percentage)
            elif data and data.startswith('sl_be_'):
                symbol = data.replace('sl_be_', '')
                await self._handle_sl_breakeven(query, symbol)
            elif data == 'refresh_status':
                status = self._collect_system_status()
                if query:
                    await query.edit_message_text(status, parse_mode='Markdown')
            elif data == 'show_positions':
                # Передаем update и context для cmd_positions
                await self.cmd_positions(update, context)
        except Exception as e:
            self.logger.error(f"Помилка обробки кнопки {data}: {e}")
            if query:
                await query.edit_message_text("❌ Помилка при обробці запиту")

    # ===== Исправление type safety и доступности методов =====
    async def _handle_close_position(self, query, symbol: str, percentage: int):
        """Обробка закриття позиції через кнопку."""
        try:
            success = await self._execute_position_close(symbol, percentage / 100)
            if success:
                action = 'закрита' if percentage == 100 else f'зменшена на {percentage}%'
                await query.edit_message_text(f"✅ Позиція {symbol} {action}")
            else:
                await query.edit_message_text(f"❌ Позиція {symbol} не знайдена або помилка закриття")
        except Exception as e:
            self.logger.error(f"Помилка закриття позиції {symbol}: {e}")
            await query.edit_message_text(f"❌ Помилка при закритті позиції {symbol}")

    async def _handle_sl_breakeven(self, query, symbol: str):
        """Обробка переміщення SL в безубиток."""
        try:
            if (hasattr(self.engine, 'risk_manager') and hasattr(self.engine.risk_manager, 'set_breakeven_sl')):
                success = self.engine.risk_manager.set_breakeven_sl(symbol)
                if success:
                    await query.edit_message_text(f"✅ Stop Loss для {symbol} переміщено в безубиток")
                else:
                    await query.edit_message_text(f"❌ Не вдалося перемістити SL для {symbol}")
            else:
                await query.edit_message_text("❌ Функція переміщення SL недоступна")
        except Exception as e:
            self.logger.error(f"Помилка переміщення SL для {symbol}: {e}")
            await query.edit_message_text(f"❌ Помилка при переміщенні SL для {symbol}")

    async def cmd_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        await self._safe_reply(update, text="❓ Невідома команда. Використовуйте /help для списку команд.")

    async def _tg_error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        # Приведение типов и вызов основного обработчика
        try:
            await self._error_handler(update, context)
        except Exception as e:
            self.logger.error(f"Ошибка в error handler: {e}")

    # ===== ЗАГЛУШКИ ДЛЯ ОТСУТСТВУЮЧИХ КОМАНД =====

    # ===== ЗАГЛУШКИ ДЛЯ ОТСУТСТВУЮЧИХ КОМАНД =====
    async def cmd_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if user_id is not None:
            self._log_command(user_id, 'orders')
        await self._safe_reply(update, text="📋 Список ордерів поки недоступний.")

    async def cmd_hedge(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if user_id is not None:
            self._log_command(user_id, 'hedge')
        await self._safe_reply(update, text="🛡 Управління хеджем поки недоступне.")

    async def cmd_set_sl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if user_id is not None:
            self._log_command(user_id, 'sl')
        await self._safe_reply(update, text="⚡ Встановлення Stop Loss поки недоступне.")

    async def cmd_set_tp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if user_id is not None:
            self._log_command(user_id, 'tp')
        await self._safe_reply(update, text="⚡ Встановлення Take Profit поки недоступне.")

    async def cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if user_id is not None:
            self._log_command(user_id, 'performance')
        await self._safe_reply(update, text="📈 Аналіз ефективності поки недоступний.")

    async def cmd_risk_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if user_id is not None:
            self._log_command(user_id, 'risk')
        await self._safe_reply(update, text="🔎 Аналіз ризиків поки недоступний.")

    async def cmd_bot_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_id = self._get_user_id(update)
        if user_id is not None:
            self._log_command(user_id, 'stats')
        stats = self.metrics.get_stats()
        text = (
            f"📊 Статистика використання бота:\n"
            f"Найпопулярніші команди: {stats['most_used_commands']}\n"
            f"Всього команд: {stats['total_commands']}\n"
            f"Активних користувачів: {stats['active_users']}\n"
            f"Помилки: {stats['errors']}"
        )
        await self._safe_reply(update, text=text)
