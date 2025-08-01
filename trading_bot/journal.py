"""
Модуль для ведення торгового журналу.
"""
import csv
import logging
import os
from datetime import datetime
import pytz


class TradingJournal:
    """
    Клас для запису торгових операцій та виконання денного чек-листа.
    """

    def __init__(self, file_path: str = "logs/trading_journal.csv"):
        self.file_path = file_path
        self.logger = logging.getLogger(__name__)
        self._setup_file()

    def _setup_file(self):
        """
        Перевіряє наявність файлу журналу та створює його з заголовками,
        якщо потрібно.
        """
        if not os.path.exists(self.file_path):
            self.logger.info("Створення нового файлу журналу: %s",
                             self.file_path)
            try:
                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                with open(self.file_path, 'w', newline='',
                          encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "timestamp_utc", "symbol", "side", "entry_price",
                        "exit_price", "quantity", "pnl_usdt", "reason"
                    ])
            except IOError as e:
                self.logger.error("Не вдалося створити файл журналу: %s", e)

    def log_trade(self, symbol: str, side: str, entry_price: float,
                  exit_price: float, quantity: float, pnl: float,
                  reason: str = "TP/SL"):
        """
        Записує деталі закритої угоди в CSV-файл.
        """
        try:
            with open(self.file_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now(pytz.utc).isoformat(),
                    symbol,
                    side,
                    entry_price,
                    exit_price,
                    quantity,
                    f"{pnl:.4f}",
                    reason
                ])
            self.logger.info(
                "Угоду для %s записано в журнал. PnL: $%.2f", symbol, pnl
            )
        except IOError as e:
            self.logger.error("Помилка запису в журнал: %s", e)

    def get_daily_summary(self, date: str) -> dict:
        """
        Отримує підсумки торгового дня.

        :param date: Дата у форматі YYYY-MM-DD
        :return: Словник з торговою статистикою
        """
        total_pnl = 0.0
        total_trades = 0
        winning_trades = 0
        losing_trades = 0

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('timestamp_utc', '').startswith(date):
                        total_trades += 1
                        try:
                            pnl = float(row['pnl_usdt'])
                            total_pnl += pnl
                            if pnl > 0:
                                winning_trades += 1
                            else:
                                losing_trades += 1
                        except (ValueError, KeyError):
                            self.logger.warning(
                                "Некоректний формат PnL або відсутній ключ "
                                "у рядку: %s", row
                            )
        except (IOError, csv.Error) as e:
            self.logger.error(
                "Помилка при читанні журналу для підсумків: %s", e
            )

        win_rate = (winning_trades / total_trades * 100) \
            if total_trades > 0 else 0

        return {
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate
        }

    def perform_end_of_day_checklist(self):
        """
        Виконує чек-лист на кінець дня.
        """
        self.logger.info(
            "%s ВИКОНАННЯ ЧЕК-ЛИСТА НА КІНЕЦЬ ДНЯ %s", "="*20, "="*20
        )
        today_str = datetime.now(pytz.utc).strftime('%Y-%m-%d')

        # 1. Розрахунок загального PnL за день з файлу журналу.
        daily_summary = self.get_daily_summary(today_str)

        self.logger.info("--- Денний підсумок ---")
        self.logger.info("Загальний PnL за %s: $%.2f",
                         today_str, daily_summary['total_pnl'])
        self.logger.info("Всього угод: %d", daily_summary['total_trades'])
        self.logger.info("Прибуткових угод: %d",
                         daily_summary['winning_trades'])
        self.logger.info("Збиткових угод: %d", daily_summary['losing_trades'])
        self.logger.info("Вінрейт: %.2f%%", daily_summary['win_rate'])
        self.logger.info("--------------------")

        # 2. Збереження скрін-стрічки обсягів та OI.
        self.logger.warning(
            "Функціонал для збереження скріншотів обсягів та OI "
            "ще не реалізовано."
        )

        # 3. Актуалізація ризик-бюджету.
        self.logger.info(
            "Денний PnL розраховано. "
            "Переконайтеся, що капітал (equity) оновлено "
            "перед початком нової торгової сесії для коректного "
            "розрахунку ризиків."
        )
        self.logger.info("Чек-лист на кінець дня завершено.")