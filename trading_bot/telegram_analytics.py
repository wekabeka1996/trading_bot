"""Модуль аналитики для Telegram-бота."""

import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime, timedelta
import pytz

class TelegramAnalytics:
    """Класс для генерации аналитических отчетов."""
    
    def __init__(self, journal: 'TradingJournal', exchange: 'BinanceFuturesConnector'):
        self.journal = journal
        self.exchange = exchange
        
    def generate_daily_report(self, date: str) -> tuple[str, BytesIO]:
        """Генерирует дневной отчет с графиком."""
        summary = self.journal.get_daily_summary(date)
        
        # Текстовый отчет
        report = f"""
📊 *Дневной отчет за {date}*

💰 *Финансовые показатели:*
├ Общий PnL: ${summary['total_pnl']:.2f}
├ Комиссии: ${summary.get('total_fees', 0):.2f}
├ Чистая прибыль: ${summary['total_pnl'] - summary.get('total_fees', 0):.2f}
└ ROI: {summary.get('roi', 0):.2%}

📈 *Статистика сделок:*
├ Всего сделок: {summary['total_trades']}
├ Прибыльных: {summary['winning_trades']}
├ Убыточных: {summary['losing_trades']}
├ Win Rate: {summary['win_rate']:.1f}%
└ Profit Factor: {summary.get('profit_factor', 0):.2f}

🎯 *Лучшая/Худшая сделка:*
├ Лучшая: {summary.get('best_trade', 'N/A')}
└ Худшая: {summary.get('worst_trade', 'N/A')}
        """
        
        # График equity curve
        chart = self._generate_equity_chart(date)
        
        return report.strip(), chart
    
    def _generate_equity_chart(self, date: str) -> BytesIO:
        """Генерирует график изменения капитала."""
        # Получаем данные из журнала
        trades_df = self.journal.get_trades_dataframe(date)
        
        if trades_df.empty:
            # Пустой график если нет данных
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, 'Нет данных для отображения', 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title(f'Equity Curve - {date}')
        else:
            # Строим график
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Кумулятивный PnL
            trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
            
            # График
            ax.plot(trades_df.index, trades_df['cumulative_pnl'], 
                   linewidth=2, color='green' if trades_df['cumulative_pnl'].iloc[-1] > 0 else 'red')
            ax.fill_between(trades_df.index, trades_df['cumulative_pnl'], 
                           alpha=0.3, color='green' if trades_df['cumulative_pnl'].iloc[-1] > 0 else 'red')
            
            # Оформление
            ax.set_title(f'Equity Curve - {date}', fontsize=14, fontweight='bold')
            ax.set_xlabel('Время')
            ax.set_ylabel('Cumulative PnL ($)')
            ax.grid(True, alpha=0.3)
            
            # Добавляем горизонтальную линию на нуле
            ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        
        # Сохраняем в BytesIO
        buf = BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close()
        
        return buf
    
    def generate_performance_report(self, days: int = 7) -> str:
        """Генерирует отчет о производительности за период."""
        end_date = datetime.now(pytz.timezone('Europe/Kiev'))
        start_date = end_date - timedelta(days=days)
        
        # Собираем статистику
        total_pnl = 0
        total_trades = 0
        winning_trades = 0
        
        for i in range(days):
            date = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
            summary = self.journal.get_daily_summary(date)
            total_pnl += summary['total_pnl']
            total_trades += summary['total_trades']
            winning_trades += summary['winning_trades']
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        avg_daily_pnl = total_pnl / days
        
        report = f"""
📈 *Отчет за {days} дней*

*Общие показатели:*
├ Общий PnL: ${total_pnl:.2f}
├ Средний дневной PnL: ${avg_daily_pnl:.2f}
├ Всего сделок: {total_trades}
└ Win Rate: {win_rate:.1f}%

*Анализ по дням недели:*
{self._analyze_by_weekday(start_date, end_date)}

*Анализ по времени суток:*
{self._analyze_by_hour(start_date, end_date)}
        """
        
        return report.strip()
    
    def _analyze_by_weekday(self, start_date: datetime, end_date: datetime) -> str:
        """Анализ прибыльности по дням недели."""
        # Здесь можно добавить детальный анализ
        return "├ Пн-Пт: Основная активность\n└ Сб-Вс: Сниженная волатильность"
    
    def _analyze_by_hour(self, start_date: datetime, end_date: datetime) -> str:
        """Анализ прибыльности по часам."""
        # Здесь можно добавить детальный анализ
        return "├ 09:00-12:00: Высокая волатильность\n└ 15:00-18:00: Американская сессия"