# trading_bot/risk_manager.py
# Модуль для управління ризиками та розрахунку розміру позицій.

import logging
from decimal import Decimal, ROUND_DOWN

from trading_bot.plan_parser import TradingPlan, ActiveAsset, OrderGroup, Hedge
from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal

class RiskManager:
    """
    Клас для управління ризиками, розрахунку розміру позицій та виконання
    правил ризик-менеджменту з торгового плану.
    """
    def __init__(self, plan: TradingPlan, exchange: BinanceFuturesConnector, notifier: TelegramNotifier, journal: TradingJournal):
        self.logger = logging.getLogger(__name__)
        self.plan = plan
        self.exchange = exchange
        self.notifier = notifier
        self.journal = journal
        self.equity = 0.0

    def update_equity(self):
        """Оновлює поточний капітал з біржі."""
        balance = self.exchange.get_futures_account_balance()
        if balance is not None:
            self.equity = balance
            self.logger.info(f"Капітал оновлено: ${self.equity:.2f}")
        else:
            self.logger.error("Не вдалося оновити капітал.")

    def _adjust_quantity_to_filters(self, quantity: float, filters: dict) -> float | None:
        """Коригує кількість відповідно до фільтрів біржі (LOT_SIZE)."""
        lot_size_filter = filters.get('LOT_SIZE', {})
        min_qty = float(lot_size_filter.get('minQty', '0'))
        step_size = lot_size_filter.get('stepSize', '1')

        if quantity < min_qty:
            self.logger.warning(f"Розрахована кількість {quantity} менша за мінімально дозволену {min_qty}. Ордер не буде розміщено.")
            return None

        precision = len(step_size.split('.')[1]) if '.' in step_size else 0
        quantity_decimal = Decimal(str(quantity))
        step_size_decimal = Decimal(step_size)
        
        adjusted_qty = (quantity_decimal // step_size_decimal) * step_size_decimal
        return float(adjusted_qty.quantize(Decimal('1e-' + str(precision)), rounding=ROUND_DOWN))


    def calc_qty(self, asset: ActiveAsset, order_group: OrderGroup, oco: bool = True) -> float | None:
        """
        Новий алгоритм розрахунку розміру позиції з урахуванням маржі, плеча, OCO, і автоматичного зменшення qty при -2019.
        oco=True означає, що враховується double margin (дві сторони OCO).
        """
        self.logger.info(f"[NEW] Розрахунок розміру позиції для {asset.symbol} (OCO={oco})...")
        self.update_equity()
        if self.equity <= 0:
            self.logger.error("Капітал дорівнює нулю або не визначений. Розрахунок неможливий.")
            return None

        risk_per_trade_usd = self.equity * self.plan.risk_budget
        self.logger.info(f"Загальний капітал: ${self.equity:.2f}, Ризик на угоду: ${risk_per_trade_usd:.2f}")

        # Визначаємо ціну входу в залежності від типу ордера
        if "LIMIT" in order_group.order_type.upper():
            entry_price = order_group.limit_price
        else:
            entry_price = order_group.trigger_price

        stop_loss_price = order_group.stop_loss
        if entry_price <= 0 or stop_loss_price <= 0:
            self.logger.error("Ціна входу або стоп-лосу не може бути нульовою.")
            return None

        stop_distance = abs(entry_price - stop_loss_price)
        if stop_distance == 0:
            self.logger.error("Відстань до стоп-лосу не може бути нульовою.")
            return None

        # 1. Початковий розрахунок qty по ризику
        quantity = risk_per_trade_usd / stop_distance

        # 2. Перевірка маржі з урахуванням OCO (дві сторони блокують margin)
        notional_value = quantity * entry_price
        required_margin = notional_value / asset.leverage
        if oco:
            required_margin *= 2
        margin_limit = self.equity * 0.95
        if required_margin > margin_limit:
            self.logger.warning(
                f"[NEW] Позиція для {asset.symbol} вимагає занадто багато маржі! Необхідно: ${required_margin:.2f}, Ліміт: ${margin_limit:.2f}. Qty буде зменшено.")
            # Автоматичне зменшення qty до максимальної допустимої маржі
            max_qty = (margin_limit / (2 if oco else 1)) * asset.leverage / entry_price
            quantity = min(quantity, max_qty)
            self.logger.info(f"[NEW] Qty скориговано до {quantity:.6f} через margin guard.")

        filters = self.exchange.get_exchange_filters(asset.symbol)
        if not filters:
            self.logger.error(f"Не вдалося отримати фільтри для {asset.symbol}, неможливо скоригувати кількість.")
            return None
        adj_qty = self._adjust_quantity_to_filters(quantity, filters)
        if adj_qty is None or adj_qty <= 0:
            self.logger.error(f"[NEW] Скоригована кількість {adj_qty} недійсна. Ордер не буде розміщено.")
            return None
        return adj_qty

    def calculate_position_size(self, asset: ActiveAsset, order_group: OrderGroup) -> float | None:
        """
        Визначає розмір позиції з урахуванням OCO (дві сторони), маржі, плеча, і risk-budget.
        """
        # Для OCO завжди враховуємо double margin
        return self.calc_qty(asset, order_group, oco=True)

    # --- Методи-заглушки для майбутньої реалізації ---
    def open_hedge_position(self, main_position: dict, hedge_config: Hedge): 
        """Відкриває хеджувальну позицію (поки заглушка)."""
        self.logger.info("Функція open_hedge_position не реалізована.")
    
    def close_hedge_position(self, hedge_symbol: str): 
        """Закриває хеджувальну позицію (поки заглушка)."""
        self.logger.info("Функція close_hedge_position не реалізована.")
    
    def handle_monitoring_action(self, action: str, position: dict, asset_plan: ActiveAsset): 
        """Обробляє дії моніторингу (поки заглушка)."""
        self.logger.info(f"Дія моніторингу '{action}' не реалізована.")
    
    def execute_risk_action(self, action: str): 
        """Виконує ризикові дії (поки заглушка)."""
        self.logger.info(f"Ризикова дія '{action}' не реалізована.")
    
    def _close_all_long_positions(self, keep_hedge: bool): 
        """Закриває всі лонг позиції (поки заглушка)."""
        self.logger.info("Функція _close_all_long_positions не реалізована.")