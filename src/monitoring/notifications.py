# Модуль для сповіщень (Telegram + Email)
import asyncio
import aiohttp
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, config: Dict):
        """
        Ініціалізація менеджера сповіщень
        
        Args:
            config: Конфігурація з налаштуваннями Telegram та Email
        """
        self.config = config
        self.telegram_enabled = config.get('telegram', {}).get('enabled', False)
        self.email_enabled = config.get('email', {}).get('enabled', False)
        
        # Telegram налаштування
        if self.telegram_enabled:
            self.telegram_token = config['telegram']['bot_token']
            self.telegram_chat_id = config['telegram']['chat_id']
            
        # Email налаштування
        if self.email_enabled:
            self.smtp_server = config['email']['smtp_server']
            self.smtp_port = config['email']['smtp_port']
            self.email = config['email']['email']
            self.email_password = config['email']['password']
        
        logger.info(f"🔔 Сповіщення: Telegram={'✅' if self.telegram_enabled else '❌'}, Email={'✅' if self.email_enabled else '❌'}")
    
    async def send_telegram_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """Відправка повідомлення в Telegram"""
        if not self.telegram_enabled:
            return False
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        
        payload = {
            'chat_id': self.telegram_chat_id,
            'text': message,
            'parse_mode': parse_mode
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.debug("✅ Telegram повідомлення відправлено")
                        return True
                    else:
                        logger.error(f"❌ Помилка Telegram: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Помилка відправки Telegram: {e}")
            return False
    
    async def send_email(self, subject: str, message: str) -> bool:
        """Відправка Email"""
        if not self.email_enabled:
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email
            msg['To'] = self.email  # Відправляємо собі
            msg['Subject'] = subject
            
            msg.attach(MIMEText(message, 'html'))
            
            # Відправка через SMTP
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email, self.email_password)
                server.send_message(msg)
            
            logger.debug("✅ Email відправлено")
            return True
            
        except Exception as e:
            logger.error(f"❌ Помилка відправки Email: {e}")
            return False
    
    async def notify_position_opened(self, symbol: str, side: str, size: float, 
                                   price: float, leverage: float):
        """Сповіщення про відкриття позиції"""
        emoji = "🟢" if side.lower() == 'buy' else "🔴"
        
        message = f"""
{emoji} <b>ПОЗИЦІЯ ВІДКРИТА</b>

💰 <b>Символ:</b> {symbol}
📊 <b>Напрямок:</b> {side.upper()}
💵 <b>Розмір:</b> ${size:.2f}
💲 <b>Ціна входу:</b> ${price:.4f}
⚡ <b>Плече:</b> {leverage}x
🕐 <b>Час:</b> {datetime.now().strftime('%H:%M:%S')}
        """
        
        await self.send_telegram_message(message)
        await self.send_email(f"Позиція відкрита: {symbol}", message.replace('<b>', '').replace('</b>', ''))
    
    async def notify_position_closed(self, symbol: str, pnl: float, pnl_percent: float, 
                                   reason: str):
        """Сповіщення про закриття позиції"""
        emoji = "✅" if pnl > 0 else "❌"
        pnl_emoji = "💰" if pnl > 0 else "💸"
        
        message = f"""
{emoji} <b>ПОЗИЦІЯ ЗАКРИТА</b>

💰 <b>Символ:</b> {symbol}
{pnl_emoji} <b>P&L:</b> ${pnl:.2f} ({pnl_percent:+.2f}%)
📋 <b>Причина:</b> {reason}
🕐 <b>Час:</b> {datetime.now().strftime('%H:%M:%S')}
        """
        
        await self.send_telegram_message(message)
        await self.send_email(f"Позиція закрита: {symbol}", message.replace('<b>', '').replace('</b>', ''))
    
    async def notify_risk_warning(self, warning_type: str, details: str):
        """Сповіщення про ризики"""
        message = f"""
⚠️ <b>ПОПЕРЕДЖЕННЯ ПРО РИЗИК</b>

🚨 <b>Тип:</b> {warning_type}
📝 <b>Деталі:</b> {details}
🕐 <b>Час:</b> {datetime.now().strftime('%H:%M:%S')}

<i>Перевірте портфель!</i>
        """
        
        await self.send_telegram_message(message)
        await self.send_email(f"⚠️ Ризик-попередження: {warning_type}", message.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', ''))
    
    async def notify_emergency_stop(self, total_loss: float, positions_closed: int):
        """Сповіщення про екстрену зупинку"""
        message = f"""
🚨 <b>ЕКСТРЕНА ЗУПИНКА!</b>

💸 <b>Загальний збиток:</b> ${total_loss:.2f}
🔒 <b>Позицій закрито:</b> {positions_closed}
⏰ <b>Час:</b> {datetime.now().strftime('%H:%M:%S')}

<b>⚠️ ВСІХ ПОЗИЦІЇ ЗАКРИТО!</b>
<i>Перевірте налаштування ризик-менеджменту</i>
        """
        
        await self.send_telegram_message(message)
        await self.send_email("🚨 ЕКСТРЕНА ЗУПИНКА ТОРГІВЛІ", message.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', ''))
    
    async def notify_market_event(self, event_type: str, description: str):
        """Сповіщення про ринкові події"""
        emoji_map = {
            'powell_speech': '🎤',
            'pmi_data': '📊',
            'btc_dominance': '₿',
            'funding_rate': '💱',
            'news': '📰'
        }
        
        emoji = emoji_map.get(event_type, '📈')
        
        message = f"""
{emoji} <b>РИНКОВА ПОДІЯ</b>

📋 <b>Тип:</b> {event_type.replace('_', ' ').title()}
📝 <b>Опис:</b> {description}
🕐 <b>Час:</b> {datetime.now().strftime('%H:%M:%S')}
        """
        
        await self.send_telegram_message(message)
    
    async def send_daily_report(self, report_data: Dict):
        """Щоденний звіт"""
        total_pnl = report_data.get('total_pnl', 0)
        trades_count = report_data.get('trades_count', 0)
        win_rate = report_data.get('win_rate', 0)
        active_positions = report_data.get('active_positions', 0)
        
        pnl_emoji = "💰" if total_pnl > 0 else "💸" if total_pnl < 0 else "➖"
        
        message = f"""
📊 <b>ЩОДЕННИЙ ЗВІТ</b>

{pnl_emoji} <b>P&L за день:</b> ${total_pnl:.2f}
📈 <b>Кількість угод:</b> {trades_count}
🎯 <b>Відсоток прибуткових:</b> {win_rate:.1f}%
🔄 <b>Активних позицій:</b> {active_positions}

📅 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y')}
        """
        
        await self.send_telegram_message(message)
        await self.send_email("📊 Щоденний торговий звіт", message.replace('<b>', '').replace('</b>', ''))
    
    async def notify_system_status(self, status: str, uptime: str, last_trade: str):
        """Сповіщення про статус системи"""
        status_emoji = "🟢" if status == "running" else "🔴" if status == "stopped" else "🟡"
        
        message = f"""
{status_emoji} <b>СТАТУС СИСТЕМИ</b>

⚡ <b>Стан:</b> {status.upper()}
⏱️ <b>Час роботи:</b> {uptime}
🕐 <b>Остання угода:</b> {last_trade}
📅 <b>Час:</b> {datetime.now().strftime('%H:%M:%S')}
        """
        
        await self.send_telegram_message(message)
    
    # Швидкі методи для критичних подій
    async def alert_high_volatility(self, symbol: str, volatility: float):
        """Попередження про високу волатильність"""
        await self.notify_risk_warning(
            "Висока волатільність", 
            f"{symbol}: {volatility:.2f}% за годину"
        )
    
    async def alert_funding_rate_spike(self, symbol: str, funding_rate: float):
        """Попередження про стрибок funding rate"""
        await self.notify_market_event(
            "funding_rate",
            f"{symbol} funding rate: {funding_rate:.3f}% (перегрів ринку)"
        )
    
    async def alert_btc_dominance_change(self, dominance: float, threshold: float):
        """Попередження про зміну BTC домінації"""
        await self.notify_market_event(
            "btc_dominance",
            f"BTC домінація: {dominance:.1f}% (поріг {threshold:.1f}%)"
        )

# Тестування сповіщень
async def test_notifications(config: Dict):
    """Тест всіх типів сповіщень"""
    notifier = NotificationManager(config)
    
    logger.info("🧪 Тестування сповіщень...")
    
    # Тест базового повідомлення
    await notifier.send_telegram_message("🤖 Тест торгового бота - система працює!")
    
    # Тест відкриття позиції
    await notifier.notify_position_opened("BTCUSDT", "buy", 100.0, 45000.0, 2.0)
    
    # Тест закриття позиції
    await notifier.notify_position_closed("BTCUSDT", 15.50, 3.2, "Take Profit")
    
    # Тест попередження
    await notifier.notify_risk_warning("Високий ризик", "VaR перевищує 3%")
    
    logger.info("✅ Тестування завершено")
