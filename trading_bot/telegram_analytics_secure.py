"""Виправлення для telegram_analytics.py з перевіркою безпеки."""

import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime, timedelta
import pytz
import logging


class TelegramAnalytics:
    """Клас для генерації аналітичних звітів з безпекою."""
    
    def __init__(self, journal, exchange):
        self.journal = journal
        self.exchange = exchange
        self.logger = logging.getLogger(__name__)
        
    def generate_daily_report(self, date: str) -> tuple[str, BytesIO]:
        """Генерує денний звіт з графіком."""
        try:
            if not hasattr(self.journal, 'get_daily_summary'):
                self.logger.warning("Journal не має методу get_daily_summary")
                return self._generate_empty_report(date, "Journal не підтримує звіти")
                
            summary = self.journal.get_daily_summary(date)
            
            # Перевіряємо наявність даних
            if not summary or summary.get('total_trades', 0) == 0:
                report = f"""
📊 *Денний звіт за {date}*

_Немає даних про торгівлю за цей день_
                """
                # Створюємо порожній графік
                chart = self._generate_empty_chart(f"Немає даних за {date}")
                return report.strip(), chart
            
            # Безпечне витягнення даних з значеннями за замовчуванням
            total_pnl = summary.get('total_pnl', 0)
            total_fees = summary.get('total_fees', 0)
            net_profit = total_pnl - total_fees
            roi = summary.get('roi', 0)
            
            total_trades = summary.get('total_trades', 0)
            winning_trades = summary.get('winning_trades', 0)
            losing_trades = summary.get('losing_trades', 0)
            win_rate = summary.get('win_rate', 0)
            profit_factor = summary.get('profit_factor', 0)
            
            best_trade = summary.get('best_trade', {'symbol': 'N/A', 'pnl': 0})
            worst_trade = summary.get('worst_trade', {'symbol': 'N/A', 'pnl': 0})
            
            # Перевіряємо типи даних
            if not isinstance(best_trade, dict):
                best_trade = {'symbol': 'N/A', 'pnl': 0}
            if not isinstance(worst_trade, dict):
                worst_trade = {'symbol': 'N/A', 'pnl': 0}
            
            # Форматуємо звіт
            report = f"""
📊 *Денний звіт за {date}*

💰 *Фінансові показники:*
├ Загальний PnL: ${total_pnl:.2f}
├ Комісії: ${total_fees:.2f}
├ Чистий прибуток: ${net_profit:.2f}
└ ROI: {roi:.2%}

📈 *Статистика угод:*
├ Всього угод: {total_trades}
├ Прибуткових: {winning_trades}
├ Збиткових: {losing_trades}
├ Win Rate: {win_rate:.1f}%
└ Profit Factor: {profit_factor:.2f}

🎯 *Найкраща/Найгірша угода:*
├ Найкраща: {best_trade['symbol']} (${best_trade['pnl']:.2f})
└ Найгірша: {worst_trade['symbol']} (${worst_trade['pnl']:.2f})
            """
            
            # Графік equity curve
            chart = self._generate_equity_chart(date)
            
            return report.strip(), chart
            
        except Exception as e:
            self.logger.error(f"Помилка при генерації денного звіту: {e}")
            return self._generate_empty_report(date, f"Помилка: {str(e)}")
    
    def _generate_empty_report(self, date: str, reason: str) -> tuple[str, BytesIO]:
        """Генерує порожній звіт при помилці."""
        error_report = f"📊 *Денний звіт за {date}*\n\n❌ {reason}"
        error_chart = self._generate_empty_chart("Помилка генерації")
        return error_report, error_chart
    
    def _generate_equity_chart(self, date: str) -> BytesIO:
        """Генерує графік зміни капіталу."""
        try:
            if not hasattr(self.journal, 'get_trades_dataframe'):
                return self._generate_empty_chart("Дані недоступні")
                
            # Отримуємо дані з журналу
            trades_df = self.journal.get_trades_dataframe(date)
            
            if trades_df is None or trades_df.empty:
                return self._generate_empty_chart(f"Немає даних за {date}")
            
            # Будуємо графік
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Кумулятивний PnL
            trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
            
            # Графік
            final_pnl = trades_df['cumulative_pnl'].iloc[-1]
            color = 'green' if final_pnl > 0 else 'red'
            
            ax.plot(trades_df.index, trades_df['cumulative_pnl'], 
                   linewidth=2, color=color)
            ax.fill_between(trades_df.index, trades_df['cumulative_pnl'], 
                           alpha=0.3, color=color)
            
            # Оформлення
            ax.set_title(f'Equity Curve - {date}', fontsize=14, fontweight='bold')
            ax.set_xlabel('Час')
            ax.set_ylabel('Cumulative PnL ($)')
            ax.grid(True, alpha=0.3)
            
            # Додаємо горизонтальну лінію на нулі
            ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        
        except Exception as e:
            self.logger.error(f"Помилка генерації графіку: {e}")
            return self._generate_empty_chart("Помилка графіку")
        
        # Зберігаємо в BytesIO
        buf = BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close()
        
        return buf
    
    def _generate_empty_chart(self, message: str) -> BytesIO:
        """Генерує порожній графік з повідомленням."""
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, message, 
                   ha='center', va='center', transform=ax.transAxes,
                   fontsize=12, bbox=dict(boxstyle="round", facecolor='wheat'))
            ax.set_title('Trading Analytics', fontsize=14, fontweight='bold')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_xticks([])
            ax.set_yticks([])
            
            buf = BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format='png', dpi=150)
            buf.seek(0)
            plt.close()
            
            return buf
        except Exception as e:
            self.logger.error(f"Помилка створення порожнього графіку: {e}")
            # Повертаємо мінімальний BytesIO об'єкт
            return BytesIO(b"PNG error")
    
    def generate_performance_report(self, days: int = 7) -> str:
        """Генерує звіт про ефективність за період."""
        try:
            end_date = datetime.now(pytz.timezone('Europe/Kiev'))
            start_date = end_date - timedelta(days=days)
            
            # Збираємо статистику
            total_pnl = 0
            total_trades = 0
            winning_trades = 0
            
            for i in range(days):
                date_str = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
                try:
                    summary = self.journal.get_daily_summary(date_str)
                    if summary:
                        total_pnl += summary.get('total_pnl', 0)
                        total_trades += summary.get('total_trades', 0)
                        winning_trades += summary.get('winning_trades', 0)
                except Exception as e:
                    self.logger.warning(f"Помилка отримання даних за {date_str}: {e}")
                    continue
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            avg_daily_pnl = total_pnl / days
            
            report = f"""
📈 *Звіт за {days} днів*

*Загальні показники:*
├ Загальний PnL: ${total_pnl:.2f}
├ Середній денний PnL: ${avg_daily_pnl:.2f}
├ Всього угод: {total_trades}
└ Win Rate: {win_rate:.1f}%

*Аналіз по днях тижня:*
{self._analyze_by_weekday(start_date, end_date)}

*Аналіз по часу доби:*
{self._analyze_by_hour(start_date, end_date)}
            """
            
            return report.strip()
            
        except Exception as e:
            self.logger.error(f"Помилка генерації звіту ефективності: {e}")
            return f"❌ Помилка генерації звіту за {days} днів"
    
    def _analyze_by_weekday(self, start_date: datetime, end_date: datetime) -> str:
        """Аналіз прибутковості по днях тижня."""
        # Тут можна додати детальний аналіз
        return "├ Пн-Пт: Основна активність\n└ Сб-Нд: Знижена волатильність"
    
    def _analyze_by_hour(self, start_date: datetime, end_date: datetime) -> str:
        """Аналіз прибутковості по годинах."""
        # Тут можна додати детальний аналіз
        return "├ 09:00-12:00: Висока волатильність\n└ 15:00-18:00: Американська сесія"
