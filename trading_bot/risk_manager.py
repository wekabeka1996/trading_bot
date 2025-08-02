# trading_bot/risk_manager.py
# Модуль для управління ризиками та розрахунку розміру позицій.

import logging
import os
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
    def __init__(
        self,
        plan: TradingPlan,
        exchange: BinanceFuturesConnector,
        notifier: TelegramNotifier,
        journal: TradingJournal
    ):
        self.logger = logging.getLogger(__name__)
        self.plan = plan
        self.exchange = exchange
        self.notifier = notifier
        self.journal = journal
        self.equity = 0.0
        # Дозволяє перевизначити баланс для тестування
        self.equity_override = os.getenv('EQUITY_OVERRIDE')

    def update_equity(self):
        """Оновлює поточний капітал з біржі або з EQUITY_OVERRIDE."""
        if self.equity_override:
            self.equity = float(self.equity_override)
            self.logger.info(
                f"Використовується тестовий капітал: ${self.equity:.2f}"
            )
            return

        balance = self.exchange.get_futures_account_balance()
        if balance is not None:
            self.equity = balance
            self.logger.info(f"Капітал оновлено: ${self.equity:.2f}")
        else:
            self.logger.error("Не вдалося оновити капітал.")

    def _adjust_quantity_to_filters(
        self, quantity: float, filters: dict
    ) -> float | None:
        """Коригує кількість відповідно до фільтрів біржі (LOT_SIZE)."""
        lot_size_filter = filters.get('LOT_SIZE', {})
        min_qty = float(lot_size_filter.get('minQty', '0'))
        step_size = lot_size_filter.get('stepSize', '1')

        if quantity < min_qty:
            self.logger.warning(
                f"Розрахована кількість {quantity} менша за мінімально "
                f"дозволену {min_qty}. Ордер не буде розміщено."
            )
            return None

        precision = len(step_size.split('.')[1]) if '.' in step_size else 0
        quantity_decimal = Decimal(str(quantity))
        step_size_decimal = Decimal(step_size)

        adjusted_qty = (
            (quantity_decimal // step_size_decimal) * step_size_decimal
        )
        return float(
            adjusted_qty.quantize(
                Decimal('1e-' + str(precision)), rounding=ROUND_DOWN
            )
        )

    def calc_qty(
        self, asset: ActiveAsset, order_group: OrderGroup, oco: bool = True
    ) -> float | None:
        """
        Розрахунок розміру позиції з урахуванням нових правил.
        1. Ризик на угоду ділиться на кількість одночасних позицій.
        2. Враховується ліміт номінальної вартості (`max_notional_per_trade`).
        3. Враховується загальний ліміт маржі (`margin_limit_pct`).
        4. Обирається найменша кількість з усіх обмежень.
        """
        self.logger.info(
            f"Розрахунок розміру позиції для {asset.symbol} (OCO={oco})..."
        )
        self.update_equity()
        if self.equity <= 0:
            self.logger.error(
                "Капітал нульовий або не визначений. Розрахунок неможливий."
            )
            return None

        # --- Параметри з конфігурації ---
        global_settings = self.plan.global_settings
        risk_per_trade_scaled = (
            self.plan.risk_budget / global_settings.max_concurrent_positions
        )
        max_notional = global_settings.max_notional_per_trade
        margin_limit_pct = global_settings.margin_limit_pct

        # --- Параметри ордера ---
        is_limit_order = (
            "LIMIT" in order_group.order_type.upper() and
            order_group.limit_price is not None
        )
        entry_price = (
            order_group.limit_price if is_limit_order
            else order_group.trigger_price
        )
        # Додаткова перевірка, оскільки limit_price є Optional
        if entry_price is None:
            self.logger.error("Не вдалося визначити ціну входу.")
            return None

        stop_loss_price = order_group.stop_loss
        if entry_price <= 0 or stop_loss_price <= 0:
            self.logger.error(
                "Ціна входу або стоп-лосу не може бути нульовою."
            )
            return None
        stop_distance = abs(entry_price - stop_loss_price)
        if stop_distance == 0:
            self.logger.error("Відстань до стоп-лосу не може бути нульовою.")
            return None

        # --- 1. Розрахунок за ризиком ---
        risk_per_trade_usd = self.equity * risk_per_trade_scaled
        quantity_by_risk = risk_per_trade_usd / stop_distance

        # --- 2. Розрахунок за номінальною вартістю ---
        quantity_by_notional = max_notional / entry_price

        # --- 3. Розрахунок за лімітом маржі ---
        margin_multiplier = 2 if oco else 1
        total_margin_limit_usd = self.equity * margin_limit_pct

        current_positions = self.exchange.get_position_information()
        used_margin = sum(
            float(p.get('initialMargin', '0')) for p in current_positions
        )
        available_margin = total_margin_limit_usd - used_margin

        if available_margin <= 0:
            self.logger.warning(
                f"Немає доступної маржі. Ліміт: ${total_margin_limit_usd:.2f},"
                f" використано: ${used_margin:.2f}"
            )
            return None

        max_pos_notional = (
            (available_margin / margin_multiplier) * asset.leverage
        )
        quantity_by_margin = max_pos_notional / entry_price

        # --- 4. Вибір фінальної кількості ---
        quantity = min(
            quantity_by_risk, quantity_by_notional, quantity_by_margin
        )

        # --- Логування для діагностики ---
        self.logger.info("--- Деталі розрахунку QTY ---")
        self.logger.info(f"Загальний капітал: ${self.equity:.2f}")
        self.logger.info(
            f"Масштабований ризик на угоду: {risk_per_trade_scaled*100:.2f}% "
            f"(${risk_per_trade_usd:.2f})"
        )
        self.logger.info(f"Відстань до SL: {stop_distance}")
        self.logger.info(f"Qty за ризиком: {quantity_by_risk:.6f}")
        self.logger.info(
            f"Qty за номіналом (${max_notional}): {quantity_by_notional:.6f}"
        )
        self.logger.info(
            f"Qty за доступною маржею (${available_margin:.2f}): "
            f"{quantity_by_margin:.6f}"
        )
        self.logger.info(f"Обрана мінімальна кількість: {quantity:.6f}")

        final_notional = quantity * entry_price
        final_margin = final_notional / asset.leverage * margin_multiplier
        self.logger.info(
            f"Фінальна номінальна вартість: ${final_notional:.2f}"
        )
        self.logger.info(f"Фінальна необхідна маржа: ${final_margin:.2f}")
        self.logger.info("---------------------------------")

        if quantity <= 0:
            self.logger.error(
                "Розрахована кількість є нульовою або від'ємною."
            )
            return None

        # --- 5. Коригування за фільтрами біржі ---
        filters = self.exchange.get_exchange_filters(asset.symbol)
        if not filters:
            self.logger.error(
                f"Не вдалося отримати фільтри для {asset.symbol}"
            )
            return None

        adj_qty = self._adjust_quantity_to_filters(quantity, filters)
        if adj_qty is None or adj_qty <= 0:
            self.logger.error(f"Скоригована кількість {adj_qty} недійсна")
            return None

        self.logger.info(f"Остаточна кількість після фільтрів: {adj_qty:.6f}")
        return adj_qty

    def calculate_position_size(
        self, asset: ActiveAsset, order_group: OrderGroup
    ) -> float | None:
        """
        Визначає розмір позиції з урахуванням OCO (дві сторони),
        маржі, плеча, і risk-budget.
        """
        # Для OCO завжди враховуємо double margin
        return self.calc_qty(asset, order_group, oco=True)

    def open_hedge_position(
        self, main_position: dict, hedge_config: Hedge
    ) -> dict | None:
        """Відкриває хеджувальну позицію."""
        main_position_notional = abs(
            float(main_position['positionAmt']) *
            float(main_position['entryPrice'])
        )
        hedge_notional = main_position_notional * \
            (hedge_config.size_pct / 100)
        hedge_price = self.exchange.get_current_price(hedge_config.symbol)
        if not hedge_price:
            self.logger.error(
                "Не вдалося отримати ціну для хеджувального активу %s",
                hedge_config.symbol
            )
            return None

        hedge_quantity = hedge_notional / hedge_price
        filters = self.exchange.get_exchange_filters(hedge_config.symbol)
        if not filters:
            return None

        adjusted_quantity = self._adjust_quantity_to_filters(
            hedge_quantity, filters
        )
        if not adjusted_quantity:
            return None

        side = "SELL" if float(main_position['positionAmt']) > 0 else "BUY"
        self.logger.info(
            "Розміщення хеджувального ордера: %s, %s, кількість %s",
            hedge_config.symbol, side, adjusted_quantity
        )
        order = self.exchange.place_order(
            symbol=hedge_config.symbol, side=side, order_type="MARKET",
            quantity=adjusted_quantity
        )
        if order:
            self.notifier.send_message(
                f"Відкрито хедж-позицію: {hedge_config.symbol}, "
                f"кількість {adjusted_quantity}", level="trade"
            )
        return order

    def close_hedge_position(self, hedge_symbol: str):
        """Закриває хеджувальну позицію."""
        positions = self.exchange.get_position_information()
        hedge_position = next(
            (p for p in positions if p['symbol'] == hedge_symbol and
             float(p['positionAmt']) != 0), None
        )
        if not hedge_position:
            self.logger.warning(
                "Не знайдено активної хедж-позиції для %s, "
                "щоб її закрити.", hedge_symbol
            )
            return

        position_amount = float(hedge_position['positionAmt'])
        side_to_close = "BUY" if position_amount < 0 else "SELL"
        self.exchange.place_order(
            symbol=hedge_symbol, side=side_to_close, order_type="MARKET",
            quantity=abs(position_amount), reduceOnly=True
        )
        self.notifier.send_message(
            f"Закрито хедж-позицію: {hedge_symbol}", level="trade"
        )

    def handle_monitoring_action(
        self, action: str, position: dict, asset_plan: ActiveAsset
    ):
        """Обробляє дії моніторингу."""
        self.logger.info(
            "Виконання дії моніторингу '%s' для %s",
            action, position['symbol']
        )
        if action == "close_position_with_profit":
            self._close_position(position)
        elif action == "reduce_position_by_50_pct":
            self._reduce_position(position, 0.5)
        else:
            self.logger.warning("Невідома дія моніторингу: %s", action)

    def execute_risk_action(self, action: str):
        """Виконує глобальні ризикові дії."""
        self.logger.warning("Виконання глобальної ризикової дії: %s", action)
        if action == "close_all_longs_keep_hedge":
            self._close_all_positions(keep_hedge=True)
        elif action == "close_all_positions":
            self._close_all_positions(keep_hedge=False)
        else:
            self.logger.error("Невідома глобальна ризикова дія: %s", action)

    def _close_all_positions(self, keep_hedge: bool = False, reason: str = None):
        """Закриває всі відкриті позиції, опціонально зберігаючи хедж. reason — причина закриття (kill-switch)."""
        positions = self.exchange.get_position_information()
        if not positions:
            self.logger.info("Немає відкритих позицій для закриття.")
            return

        open_positions = [
            p for p in positions if float(p.get('positionAmt', '0')) != 0
        ]

        hedge_symbols = set()
        if keep_hedge:
            for asset in self.plan.active_assets:
                if asset.hedge:
                    hedge_symbols.add(asset.hedge.symbol)

        for position in open_positions:
            symbol = position['symbol']
            if keep_hedge and symbol in hedge_symbols:
                self.logger.info("Зберігаємо хедж-позицію %s", symbol)
                continue

            if reason:
                self.logger.warning(f"Закриваємо позицію {symbol} через: {reason}")
            self._close_position(position)

    def _close_position(self, position: dict):
        """Закриває вказану позицію."""
        symbol = position['symbol']
        amount = float(position['positionAmt'])
        side = "SELL" if amount > 0 else "BUY"
        self.logger.info(
            "Закриття позиції %s: %s, кількість %s",
            symbol, side, abs(amount)
        )
        self.exchange.place_order(
            symbol=symbol, side=side, order_type="MARKET",
            quantity=abs(amount), reduceOnly=True
        )
        self.notifier.send_message(
            f"Позицію {symbol} закрито за ринком.", level="trade"
        )

    def _reduce_position(self, position: dict, percentage: float):
        """Зменшує розмір позиції на вказаний відсоток."""
        symbol = position['symbol']
        amount = float(position['positionAmt'])
        reduce_amount = abs(amount * percentage)
        side = "SELL" if amount > 0 else "BUY"

        filters = self.exchange.get_exchange_filters(symbol)
        if not filters:
            return
        adjusted_amount = self._adjust_quantity_to_filters(
            reduce_amount, filters
        )
        if not adjusted_amount:
            return

        self.logger.info(
            "Зменшення позиції %s на %s%%: %s, кількість %s",
            symbol, percentage * 100, side, adjusted_amount
        )
        self.exchange.place_order(
            symbol=symbol, side=side, order_type="MARKET",
            quantity=adjusted_amount, reduceOnly=True
        )
        self.notifier.send_message(
            f"Позицію {symbol} зменшено на {percentage*100}%.",
            level="trade"
        )